from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, NoReturn

from rp001.sensitive_value_policy import find_sensitive_values


LOCAL_LEDGER_SCHEMA_VERSION = "rp001-local-ledger-entry.v1"

_OWN_HASH_KEYS = frozenset(
    {
        "artifactSha256",
        "selfSha256",
        "recordSha256",
    }
)
_LEDGER_RECORD_KEYS = frozenset(
    {
        "schemaVersion",
        "eventType",
        "occurredAt",
        "payload",
        "previousRecordSha256",
        "sequence",
    }
)
_EVENT_BODY_NAME = re.compile(r"(?P<sequence>[0-9]{6})\.json")
_EVENT_SIDECAR_NAME = re.compile(r"(?P<sequence>[0-9]{6})\.json\.sha256")
_SHA256_SIDECAR = re.compile(rb"[0-9a-f]{64}\n")
_MAX_LOCAL_SEQUENCE = 999_999


class LocalEvidenceError(ValueError):
    """Raised when local canonical evidence is invalid or cannot be published."""


class LocalLedgerAppendError(LocalEvidenceError):
    """Raised after an append attempt with explicit commit state."""

    def __init__(self, message: str, *, event_published: bool) -> None:
        super().__init__(message)
        self.event_published = event_published


@dataclass(frozen=True)
class LocalArtifactBinding:
    path: Path
    sidecar_path: Path
    artifact_sha256: str


@dataclass(frozen=True)
class LocalLedgerEntry:
    sequence: int
    path: Path
    sidecar_path: Path
    record_sha256: str


@dataclass(frozen=True)
class LocalLedgerState:
    sequence: int
    record_sha256: str | None


@dataclass(frozen=True)
class _FilesystemIdentity:
    device: int
    inode: int


@dataclass
class _PinnedDirectoryChain:
    descriptors: list[int]
    child_names: list[str]

    @property
    def directory_descriptor(self) -> int:
        return self.descriptors[-1]

    @property
    def identity(self) -> _FilesystemIdentity:
        return _filesystem_identity(os.fstat(self.directory_descriptor))

    def verify(self) -> None:
        for parent, child, name in zip(
            self.descriptors[:-1],
            self.descriptors[1:],
            self.child_names,
            strict=True,
        ):
            opened = os.fstat(child)
            try:
                attached = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except OSError as error:
                raise LocalEvidenceError(
                    "trusted directory chain changed during operation"
                ) from error
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(attached.st_mode)
                or _filesystem_identity(opened) != _filesystem_identity(attached)
            ):
                raise LocalEvidenceError(
                    "trusted directory chain changed during operation"
                )

    def close(self) -> None:
        for descriptor in reversed(self.descriptors):
            os.close(descriptor)
        self.descriptors.clear()


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeEncodeError,
        ValueError,
    ) as error:
        raise LocalEvidenceError(
            "value cannot be serialized as canonical JSON"
        ) from error


def sha256_bytes(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def decode_canonical_local_ledger_record(
    source: bytes,
    *,
    expected_sequence: int,
    expected_previous_sha256: str | None,
) -> Mapping[str, object]:
    record = _load_canonical_json_object(source)
    _validate_publishable_document(record, source)
    if set(record) != _LEDGER_RECORD_KEYS:
        raise LocalEvidenceError("local ledger record keys are invalid")
    if record.get("schemaVersion") != LOCAL_LEDGER_SCHEMA_VERSION:
        raise LocalEvidenceError("local ledger schemaVersion is invalid")
    if type(record.get("sequence")) is not int:
        raise LocalEvidenceError("local ledger sequence type is invalid")
    if record["sequence"] != expected_sequence:
        raise LocalEvidenceError("local ledger record sequence is invalid")
    if not isinstance(record.get("eventType"), str):
        raise LocalEvidenceError("local ledger eventType is invalid")
    if not isinstance(record.get("occurredAt"), str):
        raise LocalEvidenceError("local ledger occurredAt is invalid")
    if not isinstance(record.get("payload"), dict):
        raise LocalEvidenceError("local ledger payload is invalid")
    if record.get("previousRecordSha256") != expected_previous_sha256:
        raise LocalEvidenceError("local ledger predecessor hash is invalid")
    return record


def cast_path(value: Path | None) -> Path:
    if value is None:
        raise LocalEvidenceError("trusted root is required")
    return value


def require_trusted_directory_root(path: Path) -> Path:
    if ".." in path.parts:
        raise LocalEvidenceError("trusted root must not contain parent traversal")
    absolute = path if path.is_absolute() else Path.cwd() / path
    chain = _open_trusted_directory_chain(
        absolute,
        absolute,
        create=False,
    )
    try:
        chain.verify()
        return absolute
    finally:
        chain.close()


def _open_trusted_directory_chain(
    trusted_root: Path,
    directory: Path,
    *,
    create: bool,
) -> _PinnedDirectoryChain:
    if not trusted_root.is_absolute() or not directory.is_absolute():
        raise LocalEvidenceError("trusted paths must be absolute")
    try:
        relative = directory.relative_to(trusted_root)
    except ValueError as error:
        raise LocalEvidenceError("directory escapes trusted root") from error
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        root_descriptor = os.open(Path(trusted_root.anchor), flags)
    except OSError as error:
        raise LocalEvidenceError("trusted filesystem root is unavailable") from error
    chain = _PinnedDirectoryChain([root_descriptor], [])
    root_parts = trusted_root.parts[1:]
    try:
        for index, component in enumerate(root_parts + relative.parts):
            parent = chain.directory_descriptor
            can_create = create and index >= len(root_parts)
            try:
                child = os.open(component, flags, dir_fd=parent)
            except FileNotFoundError:
                if not can_create:
                    raise LocalEvidenceError(
                        "trusted directory is unavailable"
                    ) from None
                try:
                    os.mkdir(component, mode=0o700, dir_fd=parent)
                    os.fsync(parent)
                    child = os.open(component, flags, dir_fd=parent)
                except OSError as error:
                    raise LocalEvidenceError(
                        "failed to create trusted directory"
                    ) from error
            except OSError as error:
                raise LocalEvidenceError(
                    "trusted directory contains an unsafe component"
                ) from error
            chain.descriptors.append(child)
            chain.child_names.append(component)
            chain.verify()
        return chain
    except BaseException:
        chain.close()
        raise


def _entry_exists_at(directory_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise LocalEvidenceError("failed to inspect artifact destination") from error
    return True


def _stage_bytes_at(
    directory_descriptor: int,
    destination_name: str,
    source: bytes,
) -> tuple[str, _FilesystemIdentity]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    staged_name = ""
    try:
        for _attempt in range(32):
            staged_name = (
                f".{destination_name}.{secrets.token_hex(12)}.tmp"
            )
            try:
                descriptor = os.open(
                    staged_name,
                    flags,
                    0o600,
                    dir_fd=directory_descriptor,
                )
                break
            except FileExistsError:
                continue
        if descriptor < 0:
            raise LocalEvidenceError("failed to reserve staged artifact")
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        metadata = os.stat(
            staged_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalEvidenceError("staged artifact is not a regular file")
        return staged_name, _filesystem_identity(metadata)
    except OSError as error:
        if staged_name:
            try:
                os.unlink(staged_name, dir_fd=directory_descriptor)
            except OSError:
                pass
        raise LocalEvidenceError("failed to stage local artifact") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _require_entry_identity_at(
    directory_descriptor: int,
    name: str,
    expected_identity: _FilesystemIdentity,
) -> None:
    try:
        metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        raise LocalEvidenceError("local artifact attachment changed") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or _filesystem_identity(metadata) != expected_identity
    ):
        raise LocalEvidenceError("local artifact attachment changed")


def _unlink_entry_at(
    directory_descriptor: int,
    name: str,
    expected_identity: _FilesystemIdentity,
) -> None:
    _require_entry_identity_at(directory_descriptor, name, expected_identity)
    os.unlink(name, dir_fd=directory_descriptor)


def _cleanup_entries_at(
    directory_descriptor: int,
    entries: list[tuple[str, _FilesystemIdentity]],
) -> None:
    for name, identity in reversed(entries):
        try:
            _unlink_entry_at(directory_descriptor, name, identity)
        except (LocalEvidenceError, OSError) as error:
            raise LocalEvidenceError(
                "failed to clean local artifact entries"
            ) from error


def _read_regular_bytes_at(
    directory_descriptor: int,
    name: str,
    label: str,
) -> tuple[bytes, _FilesystemIdentity]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise LocalEvidenceError(f"failed to read {label}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalEvidenceError(f"{label} must be a regular file")
        identity = _filesystem_identity(metadata)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            source = stream.read()
        after = os.fstat(descriptor)
        if (
            _filesystem_identity(after) != identity
            or after.st_size != len(source)
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            raise LocalEvidenceError(f"{label} changed during read")
        _require_entry_identity_at(directory_descriptor, name, identity)
        return source, identity
    except OSError as error:
        raise LocalEvidenceError(f"failed to read {label}") from error
    finally:
        os.close(descriptor)


class LocalArtifactStore:
    def __init__(self, trusted_root: Path | None = None) -> None:
        self._trusted_root = trusted_root

    def publish_json(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> LocalArtifactBinding:
        source = canonical_json_bytes(value)
        _validate_publishable_document(value, source)
        return self._publish_source(path, source)

    def publish_bytes(self, path: Path, source: bytes) -> LocalArtifactBinding:
        try:
            decoded = source.decode("utf-8")
        except UnicodeDecodeError as error:
            raise LocalEvidenceError(
                "local artifact bytes must be UTF-8"
            ) from error
        if find_sensitive_values(decoded):
            raise LocalEvidenceError(
                "sensitive values are prohibited in artifact bodies"
            )
        return self._publish_source(path, source)

    def ensure_directory(self, path: Path) -> _FilesystemIdentity:
        chain = self._open_directory(path, create=True)
        try:
            chain.verify()
            return chain.identity
        finally:
            chain.close()

    def rollback_publication(self, binding: LocalArtifactBinding) -> None:
        expected_sidecar_path = Path(f"{binding.path}.sha256")
        if binding.sidecar_path != expected_sidecar_path:
            raise LocalEvidenceError("local artifact binding is invalid")
        chain, body_name = self._open_parent(binding.path, create=False)
        try:
            sidecar_name = f"{body_name}.sha256"
            body_source, body_identity = _read_regular_bytes_at(
                chain.directory_descriptor,
                body_name,
                "local artifact body",
            )
            sidecar_source, sidecar_identity = _read_regular_bytes_at(
                chain.directory_descriptor,
                sidecar_name,
                "local artifact sidecar",
            )
            if (
                sha256_bytes(body_source) != binding.artifact_sha256
                or sidecar_source
                != f"{binding.artifact_sha256}\n".encode("ascii")
            ):
                raise LocalEvidenceError(
                    "local artifact changed before rollback"
                )
            chain.verify()
            _unlink_entry_at(
                chain.directory_descriptor,
                body_name,
                body_identity,
            )
            _unlink_entry_at(
                chain.directory_descriptor,
                sidecar_name,
                sidecar_identity,
            )
            chain.verify()
            os.fsync(chain.directory_descriptor)
        except OSError as error:
            raise LocalEvidenceError(
                "failed to roll back local artifact"
            ) from error
        finally:
            chain.close()

    def _publish_source(self, path: Path, source: bytes) -> LocalArtifactBinding:
        chain, body_name = self._open_parent(path, create=True)
        artifact_sha256 = sha256_bytes(source)
        sidecar_name = f"{body_name}.sha256"
        staged: list[tuple[str, _FilesystemIdentity]] = []
        published: list[tuple[str, _FilesystemIdentity]] = []
        try:
            chain.verify()
            if _entry_exists_at(chain.directory_descriptor, body_name) or _entry_exists_at(
                chain.directory_descriptor,
                sidecar_name,
            ):
                raise LocalEvidenceError(
                    "local artifact destination already exists"
                )
            staged.append(
                _stage_bytes_at(
                    chain.directory_descriptor,
                    body_name,
                    source,
                )
            )
            staged.append(
                _stage_bytes_at(
                    chain.directory_descriptor,
                    sidecar_name,
                    f"{artifact_sha256}\n".encode("ascii"),
                )
            )
            publication_plan = (
                (staged[1], sidecar_name),
                (staged[0], body_name),
            )
            for (staged_name, staged_identity), destination_name in publication_plan:
                chain.verify()
                os.link(
                    staged_name,
                    destination_name,
                    src_dir_fd=chain.directory_descriptor,
                    dst_dir_fd=chain.directory_descriptor,
                    follow_symlinks=False,
                )
                published.append((destination_name, staged_identity))
                _require_entry_identity_at(
                    chain.directory_descriptor,
                    destination_name,
                    staged_identity,
                )
            chain.verify()
            os.fsync(chain.directory_descriptor)
        except FileExistsError as error:
            _cleanup_entries_at(chain.directory_descriptor, published)
            raise LocalEvidenceError(
                "local artifact destination already exists"
            ) from error
        except LocalEvidenceError:
            _cleanup_entries_at(chain.directory_descriptor, published)
            raise
        except OSError as error:
            _cleanup_entries_at(chain.directory_descriptor, published)
            raise LocalEvidenceError(
                "failed to publish local artifact"
            ) from error
        finally:
            try:
                _cleanup_entries_at(chain.directory_descriptor, staged)
            finally:
                chain.close()
        return LocalArtifactBinding(
            path=path,
            sidecar_path=Path(f"{path}.sha256"),
            artifact_sha256=artifact_sha256,
        )

    def _open_parent(
        self,
        path: Path,
        *,
        create: bool,
    ) -> tuple[_PinnedDirectoryChain, str]:
        absolute, relative = self._relative_destination(path)
        if not relative.name or relative.name in {".", ".."}:
            raise LocalEvidenceError("local artifact destination is invalid")
        chain = _open_trusted_directory_chain(
            cast_path(self._trusted_root),
            absolute.parent,
            create=create,
        )
        return chain, relative.name

    def _open_directory(
        self,
        path: Path,
        *,
        create: bool,
    ) -> _PinnedDirectoryChain:
        absolute, _relative = self._relative_destination(path)
        return _open_trusted_directory_chain(
            cast_path(self._trusted_root),
            absolute,
            create=create,
        )

    def _relative_destination(self, path: Path) -> tuple[Path, Path]:
        trusted_root = cast_path(self._trusted_root)
        if not trusted_root.is_absolute():
            raise LocalEvidenceError("trusted root must be absolute")
        absolute = path if path.is_absolute() else Path.cwd() / path
        try:
            relative = absolute.relative_to(trusted_root)
        except ValueError as error:
            raise LocalEvidenceError(
                "local artifact escapes trusted root"
            ) from error
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise LocalEvidenceError("local artifact destination is invalid")
        return absolute, relative


class LocalLedgerTransaction:
    def __init__(
        self,
        ledger: "AppendOnlyLocalLedger",
        chain: _PinnedDirectoryChain,
    ) -> None:
        self._ledger = ledger
        self._chain = chain

    def validate(self) -> LocalLedgerState:
        self.verify()
        sequence, record_sha256 = self._ledger._validate_existing_entries(
            self._chain.identity
        )
        self.verify()
        return LocalLedgerState(sequence, record_sha256)

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> LocalLedgerEntry:
        return self._ledger._append_locked(
            self,
            event_type,
            payload,
            occurred_at,
        )

    def verify(self) -> None:
        self._chain.verify()


class AppendOnlyLocalLedger:
    def __init__(self, ledger_directory: Path) -> None:
        if not ledger_directory.is_absolute():
            raise LocalEvidenceError("ledger directory must be absolute")
        self._ledger_directory = ledger_directory
        self._events_directory = ledger_directory / "events"
        self._trusted_root = ledger_directory.parent
        self._store = LocalArtifactStore(self._trusted_root)

    @contextmanager
    def transaction(self) -> Iterator[LocalLedgerTransaction]:
        chain = _open_trusted_directory_chain(
            self._trusted_root,
            self._events_directory,
            create=True,
        )
        locked = False
        try:
            fcntl.flock(chain.directory_descriptor, fcntl.LOCK_EX)
            locked = True
            chain.verify()
            yield LocalLedgerTransaction(self, chain)
            chain.verify()
        except OSError as error:
            raise LocalEvidenceError("local ledger lock failed") from error
        finally:
            if locked:
                fcntl.flock(chain.directory_descriptor, fcntl.LOCK_UN)
            chain.close()

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> LocalLedgerEntry:
        with self.transaction() as transaction:
            return transaction.append(event_type, payload, occurred_at)

    def require_empty(self) -> None:
        with self.transaction() as transaction:
            if transaction.validate().sequence != 0:
                raise LocalEvidenceError("local ledger must be empty")

    def _append_locked(
        self,
        transaction: LocalLedgerTransaction,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> LocalLedgerEntry:
        prior = transaction.validate()
        sequence = prior.sequence + 1
        if sequence > _MAX_LOCAL_SEQUENCE:
            raise LocalEvidenceError("local ledger sequence is exhausted")
        path = self._events_directory / f"{sequence:06d}.json"
        record: dict[str, object] = {
            "schemaVersion": LOCAL_LEDGER_SCHEMA_VERSION,
            "eventType": event_type,
            "occurredAt": occurred_at,
            "payload": dict(payload),
            "previousRecordSha256": prior.record_sha256,
            "sequence": sequence,
        }
        transaction.verify()
        binding = self._store.publish_json(path, record)
        try:
            transaction.verify()
            after = transaction.validate()
            if (
                after.sequence != sequence
                or after.record_sha256 != binding.artifact_sha256
            ):
                raise LocalEvidenceError(
                    "local ledger append postcondition failed"
                )
        except BaseException as error:
            raise LocalLedgerAppendError(
                "local ledger changed after event publication",
                event_published=True,
            ) from error
        return LocalLedgerEntry(
            sequence=sequence,
            path=binding.path,
            sidecar_path=binding.sidecar_path,
            record_sha256=binding.artifact_sha256,
        )

    def _validate_existing_entries(
        self,
        events_identity: _FilesystemIdentity,
    ) -> tuple[int, str | None]:
        chain = _open_trusted_directory_chain(
            self._trusted_root,
            self._events_directory,
            create=False,
        )
        try:
            if chain.identity != events_identity:
                raise LocalEvidenceError(
                    "local ledger events directory changed"
                )
            chain.verify()
            try:
                children = tuple(os.listdir(chain.directory_descriptor))
            except OSError as error:
                raise LocalEvidenceError("failed to read local ledger") from error
            body_names: dict[int, str] = {}
            sidecar_names: dict[int, str] = {}
            for name in children:
                metadata = os.stat(
                    name,
                    dir_fd=chain.directory_descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISREG(metadata.st_mode):
                    raise LocalEvidenceError(
                        "local ledger entries must be real regular files"
                    )
                body_match = _EVENT_BODY_NAME.fullmatch(name)
                sidecar_match = _EVENT_SIDECAR_NAME.fullmatch(name)
                if body_match is not None:
                    body_names[int(body_match.group("sequence"))] = name
                elif sidecar_match is not None:
                    sidecar_names[int(sidecar_match.group("sequence"))] = name
                else:
                    raise LocalEvidenceError(
                        "local ledger contains an unexpected entry"
                    )
            if set(body_names) != set(sidecar_names):
                raise LocalEvidenceError(
                    "local ledger body and sidecar sets differ"
                )
            sequences = sorted(body_names)
            if sequences != list(range(1, len(sequences) + 1)):
                raise LocalEvidenceError(
                    "local ledger sequence is not contiguous"
                )
            previous_record_sha256: str | None = None
            for sequence in sequences:
                previous_record_sha256 = self._validate_entry_at(
                    chain.directory_descriptor,
                    body_names[sequence],
                    sidecar_names[sequence],
                    sequence,
                    previous_record_sha256,
                )
            chain.verify()
            return len(sequences), previous_record_sha256
        except OSError as error:
            raise LocalEvidenceError("failed to inspect local ledger") from error
        finally:
            chain.close()

    @staticmethod
    def _validate_entry_at(
        directory_descriptor: int,
        body_name: str,
        sidecar_name: str,
        expected_sequence: int,
        expected_previous_sha256: str | None,
    ) -> str:
        source, _body_identity = _read_regular_bytes_at(
            directory_descriptor,
            body_name,
            "local ledger record",
        )
        sidecar_source, _sidecar_identity = _read_regular_bytes_at(
            directory_descriptor,
            sidecar_name,
            "local ledger sidecar",
        )
        if _SHA256_SIDECAR.fullmatch(sidecar_source) is None:
            raise LocalEvidenceError("local ledger sidecar is invalid")
        actual_sha256 = sha256_bytes(source)
        if sidecar_source != f"{actual_sha256}\n".encode("ascii"):
            raise LocalEvidenceError("local ledger record hash mismatch")
        decode_canonical_local_ledger_record(
            source,
            expected_sequence=expected_sequence,
            expected_previous_sha256=expected_previous_sha256,
        )
        return actual_sha256


def _validate_publishable_document(value: object, source: bytes) -> None:
    if _contains_own_hash_key(value):
        raise LocalEvidenceError("own-hash keys are prohibited in artifact bodies")
    if find_sensitive_values(source.decode("utf-8")):
        raise LocalEvidenceError("sensitive values are prohibited in artifact bodies")


def _contains_own_hash_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            (isinstance(key, str) and key in _OWN_HASH_KEYS)
            or _contains_own_hash_key(nested_value)
            for key, nested_value in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_own_hash_key(item) for item in value)
    return False


def _read_bytes(path: Path, label: str) -> bytes:
    source, _identity = _read_real_regular_bytes(path, label)
    return source


def _read_real_regular_bytes(
    path: Path,
    label: str,
) -> tuple[bytes, _FilesystemIdentity]:
    try:
        path_metadata = os.lstat(path)
    except OSError as error:
        raise LocalEvidenceError(f"failed to read {label}") from error
    if not stat.S_ISREG(path_metadata.st_mode):
        raise LocalEvidenceError(f"{label} must be a real regular file")
    identity = _filesystem_identity(path_metadata)

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise LocalEvidenceError(f"failed to read {label}") from error
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_metadata.st_mode)
            or _filesystem_identity(opened_metadata) != identity
        ):
            raise LocalEvidenceError(f"{label} changed while being opened")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            source = stream.read()
    except OSError as error:
        raise LocalEvidenceError(f"failed to read {label}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return source, identity


def _require_file_identity(
    path: Path,
    expected_identity: _FilesystemIdentity,
) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise LocalEvidenceError(
            "local artifact changed before rollback"
        ) from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or _filesystem_identity(metadata) != expected_identity
    ):
        raise LocalEvidenceError("local artifact changed before rollback")


def _unlink_matching_hard_link(path: Path, staged_path: Path) -> bool:
    try:
        path_metadata = os.lstat(path)
        staged_metadata = os.lstat(staged_path)
        if (
            not stat.S_ISREG(path_metadata.st_mode)
            or not stat.S_ISREG(staged_metadata.st_mode)
            or _filesystem_identity(path_metadata)
            != _filesystem_identity(staged_metadata)
        ):
            return False
        path.unlink()
    except OSError:
        return False
    return True


def _verify_real_directory(
    directory: Path,
    label: str,
    expected_identity: _FilesystemIdentity | None = None,
) -> _FilesystemIdentity:
    descriptor, identity = _open_real_directory(
        directory,
        label,
        expected_identity,
    )
    os.close(descriptor)
    return identity


def _open_real_directory(
    directory: Path,
    label: str,
    expected_identity: _FilesystemIdentity | None = None,
) -> tuple[int, _FilesystemIdentity]:
    try:
        path_metadata = os.lstat(directory)
    except OSError as error:
        raise LocalEvidenceError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(path_metadata.st_mode):
        raise LocalEvidenceError(f"{label} must be a real directory")
    identity = _filesystem_identity(path_metadata)
    if expected_identity is not None and identity != expected_identity:
        raise LocalEvidenceError(f"{label} changed during publication")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(directory, flags)
    except OSError as error:
        raise LocalEvidenceError(f"{label} is unavailable") from error
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened_metadata.st_mode)
            or _filesystem_identity(opened_metadata) != identity
        ):
            raise LocalEvidenceError(f"{label} changed while being opened")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, identity


def _filesystem_identity(metadata: os.stat_result) -> _FilesystemIdentity:
    return _FilesystemIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def _load_canonical_json_object(source: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except LocalEvidenceError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError, ValueError) as error:
        raise LocalEvidenceError("local ledger record is invalid JSON") from error
    if not isinstance(value, dict):
        raise LocalEvidenceError("local ledger record must be a JSON object")
    if canonical_json_bytes(value) != source:
        raise LocalEvidenceError("local ledger record is not canonical JSON")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, nested_value in pairs:
        if key in value:
            raise LocalEvidenceError("local ledger record has duplicate keys")
        value[key] = nested_value
    return value


def _reject_json_constant(_constant: str) -> NoReturn:
    raise LocalEvidenceError("local ledger record contains an invalid number")
