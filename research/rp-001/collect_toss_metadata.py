"""Run one metadata-only Toss research collection without trading access."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import inspect
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, Protocol, TextIO, cast
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    Request,
    build_opener,
)

from rp001.local_evidence import (
    LOCAL_LEDGER_SCHEMA_VERSION,
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerEntry,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001.sample_selection import (
    CANDIDATE_POOL,
    DESIRED_SELECTION_COUNT,
    SampleSelectionContractError,
    SampleSelectionResult,
    select_metadata_sample,
)
from rp001.sensitive_value_policy import find_sensitive_values
from rp001.toss_research_collector import (
    CollectorError,
    HttpRequest,
    HttpResponse,
    MetadataCollection,
    RawHttpCapture,
    TossResearchCollector,
)


_OAUTH_URL = "https://openapi.tossinvest.com/oauth2/token"
_STOCKS_URL = "https://openapi.tossinvest.com/api/v1/stocks"
_SAMPLE_DESIGN_SCHEMA = "rp001-metadata-sample-design.v1"
_SAMPLE_DESIGN_STATUS = "metadata_design_frozen_price_unopened"
_FORMULA_PROTOCOL_VERSION = "1.0.1"
_PROGRAM_ID = "RP-001"
_GOAL_VERSION = "1.2-COMPACT"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_STRICT_UTC_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)
_LOCK_FILENAME = ".freeze-interim-scope.lock"
_RUN_LOCK_DIRECTORY_NAME = ".rp001-metadata-run-locks"
_CANONICAL_LEDGER_RELATIVE_PATH = Path(
    "research/rp-001/local-ledgers/interim-program"
)
_TIMEOUT_SECONDS = 30.0
_OAUTH_RESPONSE_LIMIT_BYTES = 1024 * 1024
_METADATA_RESPONSE_LIMIT_BYTES = 2 * 1024 * 1024
_OWN_HASH_KEYS = frozenset(
    {"artifactSha256", "selfSha256", "recordSha256"}
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
_LEDGER_BODY_NAME = re.compile(r"(?P<sequence>[0-9]{6})\.json")
_LEDGER_SIDECAR_NAME = re.compile(
    r"(?P<sequence>[0-9]{6})\.json\.sha256"
)
_MAX_LOCAL_LEDGER_SEQUENCE = 999_999


class UrlOpener(Protocol):
    def open(self, request: Request, timeout: float) -> object:
        """Open one HTTP request."""


class MetadataRunError(ValueError):
    """Sanitized metadata-run failure with a stable machine code."""

    def __init__(
        self,
        code: str,
        artifact_hashes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.code = code
        self.artifact_hashes = artifact_hashes
        super().__init__(f"{code}: metadata-only research run failed")


@dataclass(frozen=True)
class MetadataRunArguments:
    repository_root: Path
    credentials_path: Path
    sample_design_path: Path
    sample_design_sha256: str
    formula_contract_path: Path
    formula_contract_sha256: str
    source_contract_path: Path
    source_contract_sha256: str
    runner_source_path: Path
    runner_source_sha256: str
    runner_test_path: Path
    runner_test_sha256: str
    formula_source_path: Path
    formula_source_sha256: str
    formula_test_path: Path
    formula_test_sha256: str
    collector_source_path: Path
    collector_source_sha256: str
    collector_test_path: Path
    collector_test_sha256: str
    selection_source_path: Path
    selection_source_sha256: str
    selection_test_path: Path
    selection_test_sha256: str
    local_evidence_source_path: Path
    local_evidence_source_sha256: str
    local_evidence_test_path: Path
    local_evidence_test_sha256: str
    sensitive_policy_source_path: Path
    sensitive_policy_source_sha256: str
    sensitive_policy_test_path: Path
    sensitive_policy_test_sha256: str
    output_directory: Path
    ledger_directory: Path
    run_id: str


@dataclass(frozen=True)
class MetadataRunSummary:
    run_id: str
    status: str
    record_count: int
    selected_symbols: tuple[str, ...]
    artifact_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Credentials:
    client_identifier: str
    private_credential: str


@dataclass(frozen=True)
class _VerifiedFile:
    role: str
    path: Path
    relative_path: str
    sha256: str

    def to_lineage_body(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.relative_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _VerifiedInputs:
    sample_design: Mapping[str, object]
    formula_contract: Mapping[str, object]
    source_contract: Mapping[str, object]
    files: tuple[_VerifiedFile, ...]


@dataclass(frozen=True)
class _TerminalFailure:
    code: str
    stage: str
    request_attempted: bool
    response_received: bool | str
    metadata_opened: bool | str
    sensitive_raw_omitted: bool
    raw_response_omitted: bool
    captures: tuple[RawHttpCapture, ...]


@dataclass(frozen=True)
class _AcquisitionOutcome:
    collection: MetadataCollection | None
    failure: _TerminalFailure | None


@dataclass(frozen=True)
class _RunPaths:
    raw: Path
    processed: Path
    selection: Path
    exposure: Path
    manifest: Path
    failure: Path

    @property
    def run_directory(self) -> Path:
        return self.raw.parent

    @property
    def output_root(self) -> Path:
        return self.run_directory.parent

    def all_paths(self) -> tuple[Path, ...]:
        return (
            self.raw,
            self.processed,
            self.selection,
            self.exposure,
            self.manifest,
            self.failure,
        )


ArtifactStoreFactory = Callable[[], LocalArtifactStore]
LedgerFactory = Callable[[Path], object]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class _RepositoryCapability:
    declared_path: Path
    path: Path
    descriptor: int
    identity: _DirectoryIdentity
    parent_descriptor: int
    name: str

    def verify(self) -> None:
        _assert_child_directory_attachment(
            self.parent_descriptor,
            self.name,
            self.descriptor,
            self.identity,
        )


@dataclass(frozen=True)
class _PinnedDirectory:
    repository: _RepositoryCapability
    path: Path
    descriptor: int
    identity: _DirectoryIdentity


@dataclass(frozen=True)
class _PinnedFile:
    parent_descriptor: int
    name: str
    descriptor: int
    identity: _DirectoryIdentity


@dataclass(frozen=True)
class _HeldNamespaceLock:
    directory: _PinnedDirectory
    lock_file: _PinnedFile
    lock_parent: _PinnedDirectory | None = None

    def verify(self) -> None:
        _assert_pinned_directory(self.directory)
        if self.lock_parent is not None:
            _assert_child_directory_attachment(
                self.directory.descriptor,
                self.lock_parent.path.name,
                self.lock_parent.descriptor,
                self.lock_parent.identity,
            )
        _assert_regular_file_attachment(
            self.lock_file.parent_descriptor,
            self.lock_file.name,
            self.lock_file.descriptor,
            self.lock_file.identity,
            error_code="NAMESPACE_IDENTITY_CHANGED",
            required_mode=0o600,
        )


class _CredentialCapability:
    def __init__(
        self,
        parent_descriptor: int,
        parent_verifier: Callable[[], None],
        name: str,
        descriptor: int,
        identity: _DirectoryIdentity,
        owned_parent_descriptors: tuple[int, ...],
    ) -> None:
        self._parent_descriptor = parent_descriptor
        self._parent_verifier = parent_verifier
        self._name = name
        self._descriptor = descriptor
        self._identity = identity
        self._owned_parent_descriptors = owned_parent_descriptors

    def read(self) -> bytes:
        self.verify()
        try:
            os.lseek(self._descriptor, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(self._descriptor, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            raise MetadataRunError("CREDENTIAL_FILE_INVALID") from None
        self.verify()
        return b"".join(chunks)

    def verify(self) -> None:
        try:
            self._parent_verifier()
            _assert_regular_file_attachment(
                self._parent_descriptor,
                self._name,
                self._descriptor,
                self._identity,
                error_code="CREDENTIAL_PATH_INVALID",
                required_mode=0o600,
            )
        except MetadataRunError as error:
            if error.code == "CREDENTIAL_PATH_INVALID":
                raise
            raise MetadataRunError("CREDENTIAL_PATH_INVALID") from None

    def close(self) -> None:
        os.close(self._descriptor)
        for descriptor in self._owned_parent_descriptors:
            os.close(descriptor)


class _NamespaceGuard:
    def __init__(
        self,
        output: _PinnedDirectory,
        ledger: _PinnedDirectory,
        locks: tuple[_HeldNamespaceLock, ...] = (),
    ) -> None:
        self.output = output
        self.ledger = ledger
        self._locks = locks

    def verify(self) -> None:
        _assert_pinned_directory(self.output)
        _assert_pinned_directory(self.ledger)
        for held_lock in self._locks:
            held_lock.verify()


class _TransactionalArtifactStore:
    def __init__(
        self,
        guard: _NamespaceGuard,
        run_paths: _RunPaths,
        delegate: LocalArtifactStore | None,
    ) -> None:
        self._guard = guard
        self._run_paths = run_paths
        self._delegate = delegate
        self._run_descriptor: int | None = None
        self._run_identity: _DirectoryIdentity | None = None
        self._created_run_directory = False

    def require_run_absent(self) -> None:
        self._verify_namespace()
        if _entry_exists_at(
            self._guard.output.descriptor,
            self._run_paths.run_directory.name,
        ):
            raise MetadataRunError("OUTPUT_ALREADY_EXISTS")
        self._verify_namespace()

    def claim_run_directory(self) -> None:
        self._ensure_run_directory()
        self._verify_namespace()

    def publish_json(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> LocalArtifactBinding:
        self._require_artifact_path(path)
        source = _publishable_document_source(value)
        artifact_sha256 = sha256_bytes(source)
        sidecar_source = f"{artifact_sha256}\n".encode("ascii")
        self._verify_namespace()
        run_descriptor = self._ensure_run_directory()
        try:
            if self._delegate is None:
                _publish_pair_at(
                    run_descriptor,
                    path.name,
                    source,
                    f"{path.name}.sha256",
                    sidecar_source,
                    operation_label=f"artifact:{path.name}",
                    identity_verifier=self._verify_namespace,
                )
                binding = LocalArtifactBinding(
                    path=path,
                    sidecar_path=Path(f"{path}.sha256"),
                    artifact_sha256=artifact_sha256,
                )
            else:
                binding = self._publish_with_delegate(
                    path,
                    value,
                    source,
                    artifact_sha256,
                )
            self._verify_namespace()
            return binding
        except BaseException as caught:
            cleanup_error = self._cleanup_expected_pair(
                path,
                artifact_sha256,
                source,
            )
            namespace_error = self._namespace_error_or_none()
            if namespace_error is not None:
                raise namespace_error from None
            if cleanup_error is not None:
                raise cleanup_error from None
            raise caught

    def rollback_publication(self, binding: LocalArtifactBinding) -> None:
        self._require_artifact_path(binding.path)
        expected_sidecar = Path(f"{binding.path}.sha256")
        if binding.sidecar_path != expected_sidecar:
            raise LocalEvidenceError("local artifact binding is invalid")
        namespace_before = self._namespace_error_or_none()
        cleanup_error = self._cleanup_expected_pair(
            binding.path,
            binding.artifact_sha256,
            None,
        )
        _run_lifecycle_observer("artifact_rolled_back", binding.path.name)
        namespace_after = self._namespace_error_or_none()
        if namespace_before is not None or namespace_after is not None:
            raise MetadataRunError("NAMESPACE_IDENTITY_CHANGED")
        if cleanup_error is not None:
            raise cleanup_error

    def require_terminal_namespace(self, *, success: bool) -> None:
        self._verify_namespace()
        descriptor = self._ensure_run_directory()
        try:
            names = set(os.listdir(descriptor))
        except OSError as error:
            raise LocalEvidenceError(
                "failed to inspect terminal artifact namespace"
            ) from error
        self._verify_namespace()
        success_paths = (
            self._run_paths.raw,
            self._run_paths.processed,
            self._run_paths.selection,
            self._run_paths.exposure,
            self._run_paths.manifest,
        )
        success_names = {
            name
            for path in success_paths
            for name in (path.name, f"{path.name}.sha256")
        }
        failure_names = {
            self._run_paths.failure.name,
            f"{self._run_paths.failure.name}.sha256",
        }
        declared_names = success_names | failure_names
        if names - declared_names:
            raise LocalEvidenceError(
                "terminal artifact namespace contains unexpected entries"
            )
        if success:
            if names & failure_names:
                raise LocalEvidenceError(
                    "success and failure terminal sets conflict"
                )
            if names & success_names:
                raise LocalEvidenceError(
                    "success terminal artifact already exists"
                )
        else:
            if names & success_names:
                raise LocalEvidenceError(
                    "success and failure terminal sets conflict"
                )
            if names & failure_names:
                raise LocalEvidenceError(
                    "terminal failure artifact already exists"
                )
        self._verify_namespace()

    def terminal_artifact_mismatches(
        self,
        bindings: Sequence[LocalArtifactBinding],
    ) -> tuple[tuple[str, str], ...]:
        self._verify_namespace()
        descriptor = self._ensure_run_directory()
        expected_names: set[str] = set()
        for binding in bindings:
            self._require_artifact_path(binding.path)
            expected_names.add(binding.path.name)
            expected_names.add(f"{binding.path.name}.sha256")
        try:
            actual_names = set(os.listdir(descriptor))
        except OSError as error:
            raise LocalEvidenceError(
                "failed to inspect terminal artifact set"
            ) from error
        mismatches: set[tuple[str, str]] = set()
        if actual_names - expected_names:
            mismatches.add(("run_directory", "unexpected_entry"))
        for binding in bindings:
            body_name = binding.path.name
            sidecar_name = f"{body_name}.sha256"
            role = body_name.removesuffix(".json")
            if body_name not in actual_names:
                mismatches.add((role, "body_missing_or_invalid"))
            else:
                try:
                    body = _read_exact_file_at(descriptor, body_name)
                except (FileNotFoundError, LocalEvidenceError, OSError):
                    mismatches.add((role, "body_missing_or_invalid"))
                else:
                    if sha256_bytes(body) != binding.artifact_sha256:
                        mismatches.add((role, "body_hash_mismatch"))
            if sidecar_name not in actual_names:
                mismatches.add((role, "sidecar_missing_or_invalid"))
            else:
                try:
                    sidecar = _read_exact_file_at(descriptor, sidecar_name)
                except (FileNotFoundError, LocalEvidenceError, OSError):
                    mismatches.add((role, "sidecar_missing_or_invalid"))
                else:
                    expected_sidecar = (
                        f"{binding.artifact_sha256}\n".encode("ascii")
                    )
                    if sidecar != expected_sidecar:
                        mismatches.add((role, "sidecar_hash_mismatch"))
        self._verify_namespace()
        return tuple(sorted(mismatches))

    def remove_run_directory_if_empty(self) -> None:
        if not self._created_run_directory or self._run_descriptor is None:
            return
        namespace_before = self._namespace_error_or_none()
        try:
            names = tuple(os.listdir(self._run_descriptor))
        except OSError as error:
            raise LocalEvidenceError("failed to inspect run directory") from error
        if names:
            raise LocalEvidenceError("run directory is not empty")
        expected_identity = self._run_identity
        if expected_identity is None:
            raise LocalEvidenceError("run directory identity is unavailable")
        try:
            path_metadata = os.stat(
                self._run_paths.run_directory.name,
                dir_fd=self._guard.output.descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise LocalEvidenceError("run directory path is unavailable") from error
        if _directory_identity(path_metadata) != expected_identity:
            raise LocalEvidenceError("run directory identity changed")
        try:
            os.rmdir(
                self._run_paths.run_directory.name,
                dir_fd=self._guard.output.descriptor,
            )
            os.fsync(self._guard.output.descriptor)
        except OSError as error:
            raise LocalEvidenceError("failed to remove empty run directory") from error
        os.close(self._run_descriptor)
        self._run_descriptor = None
        self._run_identity = None
        self._created_run_directory = False
        namespace_after = self._namespace_error_or_none()
        if namespace_before is not None or namespace_after is not None:
            raise MetadataRunError("NAMESPACE_IDENTITY_CHANGED")

    def close(self) -> None:
        if self._run_descriptor is not None:
            os.close(self._run_descriptor)
            self._run_descriptor = None

    def _verify_namespace(self) -> None:
        self._guard.verify()
        if self._run_descriptor is None or self._run_identity is None:
            return
        _assert_child_directory_attachment(
            self._guard.output.descriptor,
            self._run_paths.run_directory.name,
            self._run_descriptor,
            self._run_identity,
        )

    def _namespace_error_or_none(self) -> MetadataRunError | None:
        try:
            self._verify_namespace()
        except BaseException:
            return MetadataRunError("NAMESPACE_IDENTITY_CHANGED")
        return None

    def _ensure_run_directory(self) -> int:
        if self._run_descriptor is not None:
            return self._run_descriptor
        name = self._run_paths.run_directory.name
        try:
            os.mkdir(name, 0o700, dir_fd=self._guard.output.descriptor)
        except FileExistsError:
            raise LocalEvidenceError("local artifact destination already exists") from None
        except OSError:
            raise LocalEvidenceError("failed to prepare run directory") from None
        self._created_run_directory = True
        try:
            descriptor = _open_child_directory(
                self._guard.output.descriptor,
                name,
                create=False,
                error_code="EVIDENCE_PUBLICATION_FAILED",
            )
        except BaseException:
            try:
                os.rmdir(name, dir_fd=self._guard.output.descriptor)
            except OSError:
                pass
            self._created_run_directory = False
            raise
        metadata = os.fstat(descriptor)
        self._run_descriptor = descriptor
        self._run_identity = _directory_identity(metadata)
        self._verify_namespace()
        return descriptor

    def _publish_with_delegate(
        self,
        path: Path,
        value: Mapping[str, object],
        source: bytes,
        artifact_sha256: str,
    ) -> LocalArtifactBinding:
        delegate = self._delegate
        if delegate is None:
            raise LocalEvidenceError("artifact delegate is unavailable")
        binding = delegate.publish_json(path, value)
        if (
            not isinstance(binding, LocalArtifactBinding)
            or binding.path != path
            or binding.sidecar_path != Path(f"{path}.sha256")
            or binding.artifact_sha256 != artifact_sha256
        ):
            raise LocalEvidenceError("artifact delegate returned an invalid binding")
        body = _read_exact_file_at(self._ensure_run_directory(), path.name)
        sidecar = _read_exact_file_at(
            self._ensure_run_directory(),
            f"{path.name}.sha256",
        )
        if body != source or sidecar != f"{artifact_sha256}\n".encode("ascii"):
            raise LocalEvidenceError("artifact delegate published unexpected bytes")
        _run_lifecycle_observer("artifact_published", path.name)
        return binding

    def _cleanup_expected_pair(
        self,
        path: Path,
        artifact_sha256: str,
        expected_body: bytes | None,
    ) -> BaseException | None:
        first_error: BaseException | None = None
        if self._run_descriptor is not None:
            try:
                _remove_exact_pair_at(
                    self._run_descriptor,
                    path.name,
                    artifact_sha256,
                    expected_body,
                )
            except BaseException as error:
                first_error = error
        if self._delegate is not None:
            try:
                _remove_exact_pair_by_path(
                    path,
                    artifact_sha256,
                    expected_body,
                )
            except BaseException as error:
                if first_error is None:
                    first_error = error
        return first_error

    def _require_artifact_path(self, path: Path) -> None:
        if path.parent != self._run_paths.run_directory:
            raise LocalEvidenceError("artifact path is outside the run directory")
        if path not in self._run_paths.all_paths():
            raise LocalEvidenceError("artifact path is not declared")


class _TransactionalLedger:
    def __init__(
        self,
        guard: _NamespaceGuard,
        ledger_directory: Path,
        delegate: object | None,
    ) -> None:
        self._guard = guard
        self._ledger_directory = ledger_directory
        self._delegate = delegate
        self._events_descriptor: int | None = None
        self._events_identity: _DirectoryIdentity | None = None

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> LocalLedgerEntry:
        self._verify_namespace()
        descriptor = self._ensure_events_directory()
        self._verify_namespace()
        prior_sequence, previous_sha256 = _validate_ledger_entries_at(descriptor)
        sequence = prior_sequence + 1
        if sequence > _MAX_LOCAL_LEDGER_SEQUENCE:
            raise LocalEvidenceError("local ledger sequence is exhausted")
        record: dict[str, object] = {
            "schemaVersion": LOCAL_LEDGER_SCHEMA_VERSION,
            "eventType": event_type,
            "occurredAt": occurred_at,
            "payload": dict(payload),
            "previousRecordSha256": previous_sha256,
            "sequence": sequence,
        }
        source = _publishable_document_source(record)
        expected_sha256 = sha256_bytes(source)
        before_names = frozenset(os.listdir(descriptor))
        body_name = f"{sequence:06d}.json"
        try:
            _run_lifecycle_observer("before_ledger_append", body_name)
            self._verify_namespace()
            if self._delegate is None:
                _publish_pair_at(
                    descriptor,
                    body_name,
                    source,
                    f"{body_name}.sha256",
                    f"{expected_sha256}\n".encode("ascii"),
                    operation_label=f"ledger:{sequence:06d}",
                    identity_verifier=self._verify_namespace,
                    preserve_complete_pair_on_interrupt=True,
                )
                _run_lifecycle_observer(
                    "ledger_event_published",
                    body_name,
                )
            else:
                append = getattr(self._delegate, "append", None)
                if not callable(append):
                    raise LocalEvidenceError("ledger delegate is invalid")
                returned = append(event_type, payload, occurred_at)
                _require_matching_ledger_entry(
                    returned,
                    self._ledger_directory,
                    sequence,
                    expected_sha256,
                )
            self._verify_namespace()
            entry = self._reconcile_exact_tail(
                sequence,
                source,
                expected_sha256,
            )
            self._verify_namespace()
            return entry
        except BaseException as caught:
            namespace_error = self._namespace_error_or_none()
            if namespace_error is not None:
                try:
                    _remove_exact_pair_at(
                        descriptor,
                        body_name,
                        expected_sha256,
                        source,
                    )
                except LocalEvidenceError:
                    pass
                raise namespace_error from None
            committed = self._try_reconcile_exact_tail(
                sequence,
                source,
                expected_sha256,
            )
            if committed is not None:
                return committed
            after_names = frozenset(os.listdir(descriptor))
            if after_names != before_names:
                raise MetadataRunError("LEDGER_COMMIT_MISMATCH") from None
            raise caught

    def claim_events_directory(self) -> None:
        self._ensure_events_directory()
        self._verify_namespace()

    def close(self) -> None:
        if self._events_descriptor is not None:
            os.close(self._events_descriptor)
            self._events_descriptor = None
            self._events_identity = None

    def _verify_namespace(self) -> None:
        self._guard.verify()
        if self._events_descriptor is None or self._events_identity is None:
            return
        _assert_child_directory_attachment(
            self._guard.ledger.descriptor,
            "events",
            self._events_descriptor,
            self._events_identity,
        )

    def _namespace_error_or_none(self) -> MetadataRunError | None:
        try:
            self._verify_namespace()
        except BaseException:
            return MetadataRunError("NAMESPACE_IDENTITY_CHANGED")
        return None

    def _ensure_events_directory(self) -> int:
        if self._events_descriptor is None:
            self._events_descriptor = _open_child_directory(
                self._guard.ledger.descriptor,
                "events",
                create=True,
                error_code="EVIDENCE_PUBLICATION_FAILED",
            )
            self._events_identity = _directory_identity(
                os.fstat(self._events_descriptor)
            )
            self._verify_namespace()
        return self._events_descriptor

    def _reconcile_exact_tail(
        self,
        sequence: int,
        source: bytes,
        expected_sha256: str,
    ) -> LocalLedgerEntry:
        descriptor = self._ensure_events_directory()
        self._verify_namespace()
        body_name = f"{sequence:06d}.json"
        sidecar_name = f"{body_name}.sha256"
        if (
            _read_exact_file_at(descriptor, body_name) != source
            or _read_exact_file_at(descriptor, sidecar_name)
            != f"{expected_sha256}\n".encode("ascii")
        ):
            raise MetadataRunError("LEDGER_COMMIT_MISMATCH")
        prior_sequence, tail_sha256 = _validate_ledger_entries_at(descriptor)
        if prior_sequence != sequence or tail_sha256 != expected_sha256:
            raise MetadataRunError("LEDGER_COMMIT_MISMATCH")
        self._verify_namespace()
        return LocalLedgerEntry(
            sequence=sequence,
            path=self._ledger_directory / "events" / body_name,
            sidecar_path=self._ledger_directory / "events" / sidecar_name,
            record_sha256=expected_sha256,
        )

    def _try_reconcile_exact_tail(
        self,
        sequence: int,
        source: bytes,
        expected_sha256: str,
    ) -> LocalLedgerEntry | None:
        try:
            return self._reconcile_exact_tail(
                sequence,
                source,
                expected_sha256,
            )
        except (LocalEvidenceError, MetadataRunError, OSError):
            return None


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise MetadataRunError("INVALID_ARGUMENTS")


class UrllibMetadataTransport:
    """Strict urllib adapter for the sole metadata GET endpoint."""

    def __init__(
        self,
        opener: UrlOpener,
        timeout_seconds: float,
        namespace_verifier: Callable[[], None] | None = None,
    ) -> None:
        if not callable(getattr(opener, "open", None)):
            raise MetadataRunError("TRANSPORT_CONFIGURATION_INVALID")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise MetadataRunError("TRANSPORT_CONFIGURATION_INVALID")
        self._opener = opener
        self._timeout_seconds = float(timeout_seconds)
        self._namespace_verifier = namespace_verifier or _no_op_verifier
        self.request_attempted = False
        self.response_received = False
        self.response_complete = False
        self.failure_code: str | None = None

    def __call__(self, request: HttpRequest) -> HttpResponse:
        failure_code: str | None = None
        try:
            return self._send(request)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except MetadataRunError as error:
            failure_code = error.code
            self.failure_code = error.code
        except Exception:
            failure_code = "METADATA_TRANSPORT_ERROR"
            self.failure_code = failure_code
        del request
        if failure_code is None:
            failure_code = "METADATA_TRANSPORT_ERROR"
        raise MetadataRunError(failure_code)

    def _send(self, request: HttpRequest) -> HttpResponse:
        _require_allowed_metadata_request(request)
        outgoing = Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        self.request_attempted = True
        try:
            self._namespace_verifier()
            received = self._opener.open(
                outgoing,
                timeout=self._timeout_seconds,
            )
            self._namespace_verifier()
        except HTTPError as error:
            self._namespace_verifier()
            self.response_received = True
            response = _http_error_response(
                error,
                "METADATA_TRANSPORT_ERROR",
                _METADATA_RESPONSE_LIMIT_BYTES,
                "METADATA_RESPONSE_TOO_LARGE",
            )
            self.response_complete = True
            self._namespace_verifier()
            return response
        except MetadataRunError:
            raise
        except Exception:
            raise MetadataRunError("METADATA_TRANSPORT_ERROR") from None
        self.response_received = True
        response = _url_response(
            received,
            "METADATA_TRANSPORT_ERROR",
            _METADATA_RESPONSE_LIMIT_BYTES,
            "METADATA_RESPONSE_TOO_LARGE",
        )
        self.response_complete = True
        self._namespace_verifier()
        return response


def run_metadata_collection(
    arguments: MetadataRunArguments,
    *,
    opener: UrlOpener | None = None,
    clock: Clock | None = None,
    artifact_store_factory: ArtifactStoreFactory = LocalArtifactStore,
    ledger_factory: LedgerFactory = AppendOnlyLocalLedger,
) -> MetadataRunSummary:
    """Verify frozen inputs, collect metadata, and append one terminal event."""
    failure_code: str | None = None
    failure_artifact_hashes: tuple[tuple[str, str], ...] = ()
    try:
        return _run_metadata_collection_once(
            arguments,
            opener=opener,
            clock=clock,
            artifact_store_factory=artifact_store_factory,
            ledger_factory=ledger_factory,
        )
    except MetadataRunError as error:
        failure_code = error.code
        failure_artifact_hashes = error.artifact_hashes
    except Exception:
        failure_code = "INTERNAL_RUN_ERROR"
    del opener
    if failure_code is None:
        failure_code = "INTERNAL_RUN_ERROR"
    raise MetadataRunError(failure_code, failure_artifact_hashes)


def _run_metadata_collection_once(
    arguments: MetadataRunArguments,
    *,
    opener: UrlOpener | None,
    clock: Clock | None,
    artifact_store_factory: ArtifactStoreFactory,
    ledger_factory: LedgerFactory,
) -> MetadataRunSummary:
    effective_clock = clock or _system_clock
    effective_opener = opener or _build_redirect_rejecting_opener()
    repository = _require_repository_root(arguments.repository_root)
    output: _PinnedDirectory | None = None
    pinned_ledger: _PinnedDirectory | None = None
    trust_anchor_lock_acquired = False
    repository_lock_acquired = False
    try:
        run_paths = _build_run_paths(arguments, repository)
        ledger_directory = _resolve_repository_namespace_path(
            repository,
            arguments.ledger_directory,
            "LEDGER_PATH_INVALID",
        )
        _require_canonical_ledger_directory(ledger_directory, repository)
        _acquire_exclusive_lock(
            repository.parent_descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        trust_anchor_lock_acquired = True
        repository.verify()
        _acquire_exclusive_lock(
            repository.descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        repository_lock_acquired = True
        repository.verify()
        output = _pin_repository_directory(
            repository,
            run_paths.output_root,
            create=True,
            error_code="OUTPUT_PATH_INVALID",
        )
        pinned_ledger = _pin_repository_directory(
            repository,
            ledger_directory,
            create=True,
            error_code="LEDGER_PATH_INVALID",
        )
        with _exclusive_output_run_lock(
            repository,
            output,
            arguments.run_id,
        ) as locked_output:
            _require_output_run_absent(output, arguments.run_id)
            with _exclusive_ledger_lock(
                repository,
                pinned_ledger,
            ) as locked_ledger:
                _run_lifecycle_observer("locks_acquired", "namespace_roots")
                with _pinned_namespace_guard(
                    output,
                    pinned_ledger,
                    locked_output=locked_output,
                    locked_ledger=locked_ledger,
                ) as guard:
                    verified = _verify_frozen_inputs(arguments, repository)
                    guard.verify()
                    repository_root = repository.path
                    credential: _CredentialCapability | None = None
                    delegate_store = (
                        None
                        if artifact_store_factory is LocalArtifactStore
                        else artifact_store_factory()
                    )
                    store = _TransactionalArtifactStore(
                        guard,
                        run_paths,
                        delegate_store,
                    )
                    delegate_ledger = (
                        None
                        if ledger_factory is AppendOnlyLocalLedger
                        else ledger_factory(ledger_directory)
                    )
                    ledger = _TransactionalLedger(
                        guard,
                        ledger_directory,
                        delegate_ledger,
                    )
                    try:
                        store.require_run_absent()
                        credential = _open_credential_capability(
                            repository,
                            arguments.credentials_path,
                        )
                        store.claim_run_directory()
                        ledger.claim_events_directory()
                        guard.verify()
                        acquisition = _acquire_metadata_no_raise(
                            credential,
                            effective_opener,
                            effective_clock,
                            guard.verify,
                        )
                        guard.verify()
                        if acquisition.failure is not None:
                            artifact_hashes = _publish_terminal_failure(
                                arguments=arguments,
                                repository_root=repository_root,
                                verified=verified,
                                run_paths=run_paths,
                                failure=acquisition.failure,
                                store=store,
                                ledger=ledger,
                                clock=effective_clock,
                            )
                            raise MetadataRunError(
                                acquisition.failure.code,
                                artifact_hashes,
                            )
                        collection = acquisition.collection
                        if collection is None:
                            raise MetadataRunError("INTERNAL_RUN_ERROR")
                        return _collect_and_publish(
                            arguments=arguments,
                            repository_root=repository_root,
                            verified=verified,
                            run_paths=run_paths,
                            collection=collection,
                            store=store,
                            ledger=ledger,
                            clock=effective_clock,
                        )
                    except BaseException as caught:
                        try:
                            store.remove_run_directory_if_empty()
                        except (LocalEvidenceError, MetadataRunError):
                            pass
                        if isinstance(caught, LocalEvidenceError):
                            raise MetadataRunError(
                                "EVIDENCE_PUBLICATION_FAILED"
                            ) from None
                        raise caught
                    finally:
                        if credential is not None:
                            credential.close()
                        ledger.close()
                        store.close()
    finally:
        if pinned_ledger is not None:
            os.close(pinned_ledger.descriptor)
        if output is not None:
            os.close(output.descriptor)
        if repository_lock_acquired:
            _release_exclusive_lock(
                repository.descriptor,
                "LEDGER_LOCK_UNAVAILABLE",
            )
        if trust_anchor_lock_acquired:
            _release_exclusive_lock(
                repository.parent_descriptor,
                "LEDGER_LOCK_UNAVAILABLE",
            )
        _close_repository_capability(repository)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(
        description="Collect one Toss stock-metadata research sample.",
    )
    for option in (
        "repository-root",
        "credentials-path",
        "sample-design-path",
        "formula-contract-path",
        "source-contract-path",
        "runner-source-path",
        "runner-test-path",
        "formula-source-path",
        "formula-test-path",
        "collector-source-path",
        "collector-test-path",
        "selection-source-path",
        "selection-test-path",
        "local-evidence-source-path",
        "local-evidence-test-path",
        "sensitive-policy-source-path",
        "sensitive-policy-test-path",
        "output-directory",
        "ledger-directory",
    ):
        parser.add_argument(f"--{option}", required=True, type=Path)
    for option in (
        "sample-design-sha256",
        "formula-contract-sha256",
        "source-contract-sha256",
        "runner-source-sha256",
        "runner-test-sha256",
        "formula-source-sha256",
        "formula-test-sha256",
        "collector-source-sha256",
        "collector-test-sha256",
        "selection-source-sha256",
        "selection-test-sha256",
        "local-evidence-source-sha256",
        "local-evidence-test-sha256",
        "sensitive-policy-source-sha256",
        "sensitive-policy-test-sha256",
    ):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    opener: UrlOpener | None = None,
    clock: Clock | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    parsed_run_id = "unavailable"
    try:
        namespace = build_argument_parser().parse_args(argv)
        arguments = MetadataRunArguments(**vars(namespace))
        parsed_run_id = arguments.run_id
        summary = run_metadata_collection(
            arguments,
            opener=opener,
            clock=clock,
        )
    except MetadataRunError as error:
        _write_summary(
            output_stream,
            MetadataRunSummary(
                run_id=_safe_run_id(parsed_run_id),
                status="failed",
                record_count=0,
                selected_symbols=(),
                artifact_hashes=error.artifact_hashes,
            ),
        )
        error_stream.write(f"{error.code}\n")
        return 1
    _write_summary(output_stream, summary)
    return 0


def _acquire_metadata_no_raise(
    credential: _CredentialCapability,
    opener: UrlOpener,
    clock: Clock,
    namespace_verifier: Callable[[], None] | None = None,
) -> _AcquisitionOutcome:
    verify_namespace = namespace_verifier or _no_op_verifier
    stage = "credential"
    request_attempted = False
    response_received = False
    transport: UrllibMetadataTransport | None = None
    try:
        credentials = _load_credentials(credential)
        stage = "auth"
        form = urlencode(
            (
                ("grant_type", "client_credentials"),
                ("client_id", credentials.client_identifier),
                ("client_secret", credentials.private_credential),
            )
        ).encode("ascii")
        request = Request(
            _OAUTH_URL,
            data=form,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        request_attempted = True
        try:
            verify_namespace()
            received = opener.open(request, timeout=_TIMEOUT_SECONDS)
            verify_namespace()
        except HTTPError as error:
            verify_namespace()
            response_received = True
            auth_response = _http_error_response(
                error,
                "AUTH_TRANSPORT_ERROR",
                _OAUTH_RESPONSE_LIMIT_BYTES,
                "AUTH_RESPONSE_TOO_LARGE",
            )
        else:
            response_received = True
            auth_response = _url_response(
                received,
                "AUTH_TRANSPORT_ERROR",
                _OAUTH_RESPONSE_LIMIT_BYTES,
                "AUTH_RESPONSE_TOO_LARGE",
            )
            verify_namespace()
        if auth_response.status < 200 or auth_response.status >= 300:
            raise MetadataRunError("AUTH_HTTP_STATUS")
        try:
            payload = json.loads(auth_response.body.decode("utf-8"))
        except Exception:
            raise MetadataRunError("AUTH_RESPONSE_INVALID") from None
        if not isinstance(payload, dict):
            raise MetadataRunError("AUTH_RESPONSE_INVALID")
        ephemeral = payload.get("access_token")
        if (
            not isinstance(ephemeral, str)
            or not ephemeral
            or any(character in ephemeral for character in "\r\n\x00")
        ):
            raise MetadataRunError("AUTH_RESPONSE_INVALID")

        stage = "metadata"
        request_attempted = False
        response_received = False
        transport = UrllibMetadataTransport(
            opener,
            _TIMEOUT_SECONDS,
            namespace_verifier=verify_namespace,
        )
        collector = TossResearchCollector(
            transport=transport,
            token_supplier=lambda: ephemeral,
            clock=clock,
        )
        collection = collector.collect_metadata(CANDIDATE_POOL)
        return _AcquisitionOutcome(collection=collection, failure=None)
    except BaseException as caught:
        interrupted = isinstance(
            caught,
            (KeyboardInterrupt, SystemExit, GeneratorExit),
        )
        if interrupted:
            code = "RUN_INTERRUPTED"
        elif isinstance(caught, CollectorError):
            code = caught.code
        elif isinstance(caught, MetadataRunError):
            code = caught.code
        elif stage == "credential":
            code = "CREDENTIAL_FILE_INVALID"
        elif stage == "auth":
            code = "AUTH_TRANSPORT_ERROR"
        else:
            code = "METADATA_TRANSPORT_ERROR"

        captures = caught.captures if isinstance(caught, CollectorError) else ()
        if stage == "metadata" and transport is not None:
            request_attempted = transport.request_attempted
            response_received = transport.response_received
            if transport.failure_code is not None:
                code = transport.failure_code
        if stage != "metadata":
            metadata_opened: bool | str = False
        elif captures:
            metadata_opened = True
        elif code == "SENSITIVE_RESPONSE" and response_received:
            metadata_opened = True
        elif transport is not None and transport.response_complete:
            metadata_opened = True
        elif response_received:
            metadata_opened = "unknown"
        else:
            metadata_opened = False
        sensitive_raw_omitted = code == "SENSITIVE_RESPONSE"
        raw_response_omitted = bool(response_received and not captures)
        failure = _TerminalFailure(
            code=code,
            stage=stage,
            request_attempted=request_attempted,
            response_received=response_received,
            metadata_opened=metadata_opened,
            sensitive_raw_omitted=sensitive_raw_omitted,
            raw_response_omitted=raw_response_omitted,
            captures=captures,
        )
        return _AcquisitionOutcome(collection=None, failure=failure)


def _collect_and_publish(
    *,
    arguments: MetadataRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    run_paths: _RunPaths,
    collection: MetadataCollection,
    store: _TransactionalArtifactStore,
    ledger: _TransactionalLedger,
    clock: Clock,
) -> MetadataRunSummary:
    published: list[LocalArtifactBinding] = []
    ledger_entry: LocalLedgerEntry | None = None
    failure_code = "INTERNAL_RUN_ERROR"
    failure_stage = "selection"
    try:
        selection = _select_sample(collection, arguments)
        failure_stage = "evidence"
        bindings = _publish_success_artifacts(
            arguments=arguments,
            repository_root=repository_root,
            verified=verified,
            run_paths=run_paths,
            collection=collection,
            selection=selection,
            store=store,
            clock=clock,
            published=published,
        )
        manifest_binding = bindings[-1]
        pre_commit_mismatches = store.terminal_artifact_mismatches(bindings)
        if pre_commit_mismatches:
            raise MetadataRunError("EVIDENCE_INTEGRITY_LOST")
        ledger_entry = ledger.append(
            event_type="toss_metadata_collection_succeeded",
            payload={
                "runId": arguments.run_id,
                "sampleRole": "metadata_only",
                "recordCount": len(collection.records),
                "selectedSymbols": list(selection.selected_symbols),
                "manifest": _binding_body(manifest_binding, repository_root),
            },
            occurred_at=_safe_evidence_timestamp(clock),
        )
        post_commit_mismatches = store.terminal_artifact_mismatches(bindings)
        if post_commit_mismatches:
            _raise_committed_terminal_invalidated(
                arguments=arguments,
                terminal_event_type="success",
                terminal_entry=ledger_entry,
                mismatches=post_commit_mismatches,
                ledger=ledger,
                clock=clock,
            )
        artifact_hashes = tuple(
            (path.name.removesuffix(".json"), binding.artifact_sha256)
            for path, binding in zip(
                (
                    run_paths.raw,
                    run_paths.processed,
                    run_paths.selection,
                    run_paths.exposure,
                    run_paths.manifest,
                ),
                bindings,
                strict=True,
            )
        ) + (("ledgerEvent", ledger_entry.record_sha256),)
        return MetadataRunSummary(
            run_id=arguments.run_id,
            status="succeeded",
            record_count=len(collection.records),
            selected_symbols=selection.selected_symbols,
            artifact_hashes=artifact_hashes,
        )
    except BaseException as caught:
        if ledger_entry is not None:
            if (
                isinstance(caught, MetadataRunError)
                and caught.code == "EVIDENCE_INTEGRITY_LOST"
            ):
                raise caught
            _raise_committed_terminal_invalidated(
                arguments=arguments,
                terminal_event_type="success",
                terminal_entry=ledger_entry,
                mismatches=(("run", "post_commit_processing_error"),),
                ledger=ledger,
                clock=clock,
            )
        if isinstance(caught, SampleSelectionContractError):
            failure_code = caught.code
        elif isinstance(caught, MetadataRunError):
            failure_code = caught.code
        elif isinstance(caught, LocalEvidenceError):
            failure_code = "EVIDENCE_PUBLICATION_FAILED"
        elif isinstance(caught, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            failure_code = "RUN_INTERRUPTED"
        else:
            failure_code = "INTERNAL_RUN_ERROR"

    try:
        _rollback_bindings(store, published)
    except MetadataRunError as rollback_error:
        if rollback_error.code == "NAMESPACE_IDENTITY_CHANGED":
            failure_code = rollback_error.code
        else:
            try:
                store.remove_run_directory_if_empty()
            except (LocalEvidenceError, MetadataRunError):
                pass
            raise
    if failure_code == "NAMESPACE_IDENTITY_CHANGED":
        try:
            store.remove_run_directory_if_empty()
        except (LocalEvidenceError, MetadataRunError):
            pass
        raise MetadataRunError(failure_code) from None
    failure = _TerminalFailure(
        code=failure_code,
        stage=failure_stage,
        request_attempted=True,
        response_received=True,
        metadata_opened=True,
        sensitive_raw_omitted=False,
        raw_response_omitted=False,
        captures=(collection.capture,),
    )
    try:
        failure_artifact_hashes = _publish_terminal_failure(
            arguments=arguments,
            repository_root=repository_root,
            verified=verified,
            run_paths=run_paths,
            failure=failure,
            store=store,
            ledger=ledger,
            clock=clock,
        )
    except BaseException as caught:
        if (
            isinstance(caught, MetadataRunError)
            and caught.code == "EVIDENCE_INTEGRITY_LOST"
        ):
            raise caught
        try:
            store.remove_run_directory_if_empty()
        except (LocalEvidenceError, MetadataRunError):
            pass
        raise MetadataRunError("EVIDENCE_PUBLICATION_FAILED") from None
    raise MetadataRunError(
        failure_code,
        failure_artifact_hashes,
    ) from None


def _raise_committed_terminal_invalidated(
    *,
    arguments: MetadataRunArguments,
    terminal_event_type: str,
    terminal_entry: LocalLedgerEntry,
    mismatches: Sequence[tuple[str, str]],
    ledger: _TransactionalLedger,
    clock: Clock,
) -> NoReturn:
    terminal_hash_role = (
        "ledgerSuccessEvent"
        if terminal_event_type == "success"
        else "ledgerFailureEvent"
    )
    terminal_hashes = (
        (terminal_hash_role, terminal_entry.record_sha256),
    )
    payload: dict[str, object] = {
        "mismatches": [
            {"category": category, "role": role}
            for role, category in mismatches
        ],
        "runId": arguments.run_id,
    }
    if terminal_event_type == "success":
        payload["invalidatedSuccessEventSha256"] = (
            terminal_entry.record_sha256
        )
    else:
        payload.update(
            {
                "invalidatedTerminalEventSha256": terminal_entry.record_sha256,
                "terminalEventType": "failure",
            }
        )
    try:
        invalidation_entry = ledger.append(
            event_type="toss_metadata_collection_invalidated",
            payload=payload,
            occurred_at=_safe_evidence_timestamp(clock),
        )
    except BaseException:
        raise MetadataRunError(
            "EVIDENCE_INTEGRITY_LOST",
            terminal_hashes,
        ) from None
    raise MetadataRunError(
        "EVIDENCE_INTEGRITY_LOST",
        terminal_hashes
        + (("ledgerInvalidationEvent", invalidation_entry.record_sha256),),
    ) from None


def _publish_success_artifacts(
    *,
    arguments: MetadataRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    run_paths: _RunPaths,
    collection: MetadataCollection,
    selection: SampleSelectionResult,
    store: _TransactionalArtifactStore,
    clock: Clock,
    published: list[LocalArtifactBinding],
) -> tuple[LocalArtifactBinding, ...]:
    store.require_terminal_namespace(success=True)
    raw_binding = _publish(
        store,
        run_paths.raw,
        _raw_capture_body(arguments.run_id, collection.capture),
        published,
    )
    processed_binding = _publish(
        store,
        run_paths.processed,
        _processed_metadata_body(
            arguments.run_id,
            collection,
            raw_binding,
            repository_root,
        ),
        published,
    )
    selection_binding = _publish(
        store,
        run_paths.selection,
        selection.to_canonical_body(),
        published,
    )
    exposure_binding = _publish(
        store,
        run_paths.exposure,
        _exposure_body(
            arguments.run_id,
            collection,
            raw_binding,
            processed_binding,
            repository_root,
            clock,
        ),
        published,
    )
    prior_bindings = (
        raw_binding,
        processed_binding,
        selection_binding,
        exposure_binding,
    )
    manifest_binding = _publish(
        store,
        run_paths.manifest,
        _manifest_body(
            arguments=arguments,
            repository_root=repository_root,
            verified=verified,
            collection=collection,
            selection=selection,
            bindings=prior_bindings,
            clock=clock,
        ),
        published,
    )
    return prior_bindings + (manifest_binding,)


def _publish_terminal_failure(
    *,
    arguments: MetadataRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    run_paths: _RunPaths,
    failure: _TerminalFailure,
    store: _TransactionalArtifactStore,
    ledger: _TransactionalLedger,
    clock: Clock,
) -> tuple[tuple[str, str], ...]:
    store.require_terminal_namespace(success=False)
    source_lineage = [value.to_lineage_body() for value in verified.files]
    published: list[LocalArtifactBinding] = []
    failure_binding = _publish(
        store,
        run_paths.failure,
        {
            "schemaVersion": "rp001-toss-metadata-failure.v1",
            "programId": _PROGRAM_ID,
            "goalVersion": _GOAL_VERSION,
            "runId": arguments.run_id,
            "status": "failed",
            "errorCode": failure.code,
            "sampleRole": "metadata_only",
            "stage": failure.stage,
            "requestAttempted": failure.request_attempted,
            "responseReceived": failure.response_received,
            "metadataOpened": failure.metadata_opened,
            "sensitiveRawOmitted": failure.sensitive_raw_omitted,
            "rawResponseOmitted": failure.raw_response_omitted,
            "priceVolumeOutcomePerformanceOpened": False,
            "failedAt": _safe_evidence_timestamp(clock),
            "sourceLineage": source_lineage,
            "captures": [
                _capture_body(capture) for capture in failure.captures
            ],
        },
        published,
    )
    pre_commit_mismatches = store.terminal_artifact_mismatches(
        (failure_binding,)
    )
    if pre_commit_mismatches:
        try:
            _rollback_bindings(store, published)
            store.remove_run_directory_if_empty()
        except (LocalEvidenceError, MetadataRunError):
            pass
        raise MetadataRunError("EVIDENCE_INTEGRITY_LOST")
    try:
        ledger_entry = ledger.append(
            event_type="toss_metadata_collection_failed",
            payload={
                "runId": arguments.run_id,
                "sampleRole": "metadata_only",
                "errorCode": failure.code,
                "stage": failure.stage,
                "sourceLineage": source_lineage,
                "failureArtifact": _binding_body(
                    failure_binding,
                    repository_root,
                ),
            },
            occurred_at=_safe_evidence_timestamp(clock),
        )
    except BaseException as caught:
        if (
            isinstance(caught, MetadataRunError)
            and caught.code == "LEDGER_COMMIT_MISMATCH"
        ):
            raise
        try:
            _rollback_bindings(store, published)
            store.remove_run_directory_if_empty()
        except (LocalEvidenceError, MetadataRunError):
            raise MetadataRunError("EVIDENCE_ROLLBACK_FAILED") from None
        raise LocalEvidenceError("terminal failure event could not be appended") from None
    post_commit_mismatches = store.terminal_artifact_mismatches(
        (failure_binding,)
    )
    if post_commit_mismatches:
        _raise_committed_terminal_invalidated(
            arguments=arguments,
            terminal_event_type="failure",
            terminal_entry=ledger_entry,
            mismatches=post_commit_mismatches,
            ledger=ledger,
            clock=clock,
        )
    return (
        ("failure", failure_binding.artifact_sha256),
        ("ledgerEvent", ledger_entry.record_sha256),
    )


def _select_sample(
    collection: MetadataCollection,
    arguments: MetadataRunArguments,
) -> SampleSelectionResult:
    payloads = tuple(
        {
            "symbol": record.symbol,
            "name": record.name,
            "englishName": record.english_name,
            "isinCode": record.isin_code,
            "market": record.market,
            "securityType": record.security_type,
            "isCommonShare": record.is_common_share,
            "status": record.status,
            "currency": record.currency,
            "sharesOutstanding": record.shares_outstanding.text,
        }
        for record in collection.records
    )
    return select_metadata_sample(
        payloads,
        formula_source_sha256=arguments.formula_source_sha256,
        formula_artifact_sha256=arguments.formula_contract_sha256,
    )


def _raw_capture_body(run_id: str, capture: RawHttpCapture) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-toss-metadata-raw-capture.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "sampleRole": "metadata_only",
        "capture": _capture_body(capture),
    }


def _capture_body(capture: RawHttpCapture) -> dict[str, object]:
    return {
        "endpointId": capture.endpoint_id,
        "method": capture.method,
        "sanitizedUrl": capture.sanitized_url,
        "query": [list(value) for value in capture.query],
        "status": capture.status,
        "headers": [list(value) for value in capture.headers],
        "receivedAt": capture.received_at,
        "bodyBase64": capture.body_base64,
        "bodySha256": capture.body_sha256,
    }


def _processed_metadata_body(
    run_id: str,
    collection: MetadataCollection,
    raw_binding: LocalArtifactBinding,
    repository_root: Path,
) -> dict[str, object]:
    records = [
        {
            "symbol": record.symbol,
            "name": record.name,
            "englishName": record.english_name,
            "isinCode": record.isin_code,
            "market": record.market,
            "securityType": record.security_type,
            "isCommonShare": record.is_common_share,
            "status": record.status,
            "currency": record.currency,
            "sharesOutstanding": record.shares_outstanding.text,
            "sharesOutstandingJsonKind": record.shares_outstanding.kind,
        }
        for record in collection.records
    ]
    return {
        "schemaVersion": "rp001-toss-processed-metadata.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "sampleRole": "metadata_only",
        "receivedAt": collection.capture.received_at,
        "recordCount": len(records),
        "records": records,
        "rawSource": _binding_body(raw_binding, repository_root),
    }


def _exposure_body(
    run_id: str,
    collection: MetadataCollection,
    raw_binding: LocalArtifactBinding,
    processed_binding: LocalArtifactBinding,
    repository_root: Path,
    clock: Clock,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-sample-exposure.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "sampleRole": "metadata_only",
        "metadataOpened": True,
        "priceVolumeOutcomePerformanceOpened": False,
        "symbols": list(CANDIDATE_POOL),
        "receivedAt": collection.capture.received_at,
        "recordedAt": _utc_timestamp(clock),
        "rawSource": _binding_body(raw_binding, repository_root),
        "processedSource": _binding_body(processed_binding, repository_root),
    }


def _manifest_body(
    *,
    arguments: MetadataRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    collection: MetadataCollection,
    selection: SampleSelectionResult,
    bindings: tuple[LocalArtifactBinding, ...],
    clock: Clock,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-toss-metadata-manifest.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": arguments.run_id,
        "status": "succeeded",
        "usageScope": "research_only",
        "operationalDisposition": "NoTrade/no integration",
        "sampleRole": "metadata_only",
        "createdAt": _utc_timestamp(clock),
        "request": {
            "endpointId": collection.capture.endpoint_id,
            "method": collection.capture.method,
            "query": [list(value) for value in collection.capture.query],
            "receivedAt": collection.capture.received_at,
        },
        "recordCount": len(collection.records),
        "selectedSymbols": list(selection.selected_symbols),
        "sourceLineage": [value.to_lineage_body() for value in verified.files],
        "publishedArtifacts": [
            _binding_body(binding, repository_root) for binding in bindings
        ],
        "providerLimitations": {
            "publicationTimestamp": "not_documented",
            "revisionPolicy": "not_documented",
            "licenseAndRedistributionScope": (
                "not_documented_local_research_only_no_redistribution"
            ),
        },
    }


def _publish(
    store: _TransactionalArtifactStore,
    path: Path,
    body: Mapping[str, object],
    published: list[LocalArtifactBinding],
) -> LocalArtifactBinding:
    binding = store.publish_json(path, body)
    published.append(binding)
    return binding


def _rollback_bindings(
    store: _TransactionalArtifactStore,
    bindings: Sequence[LocalArtifactBinding],
) -> None:
    first_error: BaseException | None = None
    for binding in reversed(bindings):
        try:
            store.rollback_publication(binding)
        except BaseException as error:
            if first_error is None:
                first_error = error
    if first_error is not None:
        if (
            isinstance(first_error, MetadataRunError)
            and first_error.code == "NAMESPACE_IDENTITY_CHANGED"
        ):
            raise first_error
        raise MetadataRunError("EVIDENCE_ROLLBACK_FAILED") from None


def _verify_frozen_inputs(
    arguments: MetadataRunArguments,
    repository: _RepositoryCapability,
) -> _VerifiedInputs:
    declared = (
        (
            "sample_design",
            arguments.sample_design_path,
            arguments.sample_design_sha256,
            True,
        ),
        (
            "formula_contract",
            arguments.formula_contract_path,
            arguments.formula_contract_sha256,
            True,
        ),
        (
            "source_contract",
            arguments.source_contract_path,
            arguments.source_contract_sha256,
            True,
        ),
        (
            "runner_source",
            arguments.runner_source_path,
            arguments.runner_source_sha256,
            False,
        ),
        (
            "runner_test",
            arguments.runner_test_path,
            arguments.runner_test_sha256,
            False,
        ),
        (
            "formula_source",
            arguments.formula_source_path,
            arguments.formula_source_sha256,
            False,
        ),
        (
            "formula_test",
            arguments.formula_test_path,
            arguments.formula_test_sha256,
            False,
        ),
        (
            "collector_source",
            arguments.collector_source_path,
            arguments.collector_source_sha256,
            False,
        ),
        (
            "collector_test",
            arguments.collector_test_path,
            arguments.collector_test_sha256,
            False,
        ),
        (
            "selection_source",
            arguments.selection_source_path,
            arguments.selection_source_sha256,
            False,
        ),
        (
            "selection_test",
            arguments.selection_test_path,
            arguments.selection_test_sha256,
            False,
        ),
        (
            "local_evidence_source",
            arguments.local_evidence_source_path,
            arguments.local_evidence_source_sha256,
            False,
        ),
        (
            "local_evidence_test",
            arguments.local_evidence_test_path,
            arguments.local_evidence_test_sha256,
            False,
        ),
        (
            "sensitive_policy_source",
            arguments.sensitive_policy_source_path,
            arguments.sensitive_policy_source_sha256,
            False,
        ),
        (
            "sensitive_policy_test",
            arguments.sensitive_policy_test_path,
            arguments.sensitive_policy_test_sha256,
            False,
        ),
    )
    files: list[_VerifiedFile] = []
    json_values: dict[str, Mapping[str, object]] = {}
    for role, declared_path, expected_sha256, canonical_json in declared:
        _require_sha256(expected_sha256)
        relative_path = _repository_input_relative_argument(
            repository,
            declared_path,
            "INPUT_PATH_INVALID",
        )
        path = repository.path / relative_path
        source = _read_repository_regular_file(
            repository,
            relative_path,
            "FROZEN_INPUT_INVALID",
        )
        actual_sha256 = sha256_bytes(source)
        if actual_sha256 != expected_sha256:
            raise MetadataRunError("INPUT_HASH_MISMATCH")
        if canonical_json:
            _require_sidecar(repository, relative_path, expected_sha256)
            json_values[role] = _load_canonical_object(source)
        files.append(
            _VerifiedFile(
                role=role,
                path=path,
                relative_path=relative_path.as_posix(),
                sha256=actual_sha256,
            )
        )

    _validate_execution_source_paths(tuple(files), repository)
    sample_design = json_values["sample_design"]
    formula_contract = json_values["formula_contract"]
    source_contract = json_values["source_contract"]
    _validate_formula_contract(formula_contract, arguments, repository)
    _validate_sample_design(sample_design, arguments, repository)
    _validate_source_contract(source_contract, arguments, repository)
    return _VerifiedInputs(
        sample_design=sample_design,
        formula_contract=formula_contract,
        source_contract=source_contract,
        files=tuple(files),
    )


def _validate_execution_source_paths(
    files: tuple[_VerifiedFile, ...],
    repository: _RepositoryCapability,
) -> None:
    by_role = {value.role: value for value in files}
    actual_paths = {
        "runner_source": _execution_source_relative_path(
            __file__,
            repository,
        ),
        "collector_source": _object_execution_source_relative_path(
            TossResearchCollector,
            repository,
        ),
        "selection_source": _object_execution_source_relative_path(
            select_metadata_sample,
            repository,
        ),
        "local_evidence_source": _object_execution_source_relative_path(
            LocalArtifactStore,
            repository,
        ),
        "sensitive_policy_source": _object_execution_source_relative_path(
            find_sensitive_values,
            repository,
        ),
    }
    for role, actual_relative_path in actual_paths.items():
        verified = by_role.get(role)
        if (
            verified is None
            or verified.relative_path != actual_relative_path.as_posix()
        ):
            raise MetadataRunError("EXECUTION_SOURCE_MISMATCH")
        actual_source = _read_repository_regular_file(
            repository,
            actual_relative_path,
            "EXECUTION_SOURCE_MISMATCH",
        )
        if sha256_bytes(actual_source) != verified.sha256:
            raise MetadataRunError("EXECUTION_SOURCE_MISMATCH")


def _object_execution_source_relative_path(
    value: object,
    repository: _RepositoryCapability,
) -> Path:
    try:
        source_path = inspect.getsourcefile(value)
    except (OSError, TypeError):
        source_path = None
    if source_path is None:
        raise MetadataRunError("EXECUTION_SOURCE_MISMATCH")
    return _execution_source_relative_path(source_path, repository)


def _execution_source_relative_path(
    value: str,
    repository: _RepositoryCapability,
) -> Path:
    try:
        return _repository_relative_argument(
            repository,
            Path(value),
            "EXECUTION_SOURCE_MISMATCH",
        )
    except MetadataRunError:
        raise MetadataRunError("EXECUTION_SOURCE_MISMATCH") from None


def _validate_formula_contract(
    value: Mapping[str, object],
    arguments: MetadataRunArguments,
    repository_root: _RepositoryCapability,
) -> None:
    implementation = value.get("implementationBinding")
    if not isinstance(implementation, Mapping):
        raise MetadataRunError("FORMULA_CONTRACT_INVALID")
    expected = {
        "sourcePath": _relative_argument_path(
            arguments.formula_source_path,
            repository_root,
        ),
        "sourceSha256": arguments.formula_source_sha256,
        "testPath": _relative_argument_path(
            arguments.formula_test_path,
            repository_root,
        ),
        "testSha256": arguments.formula_test_sha256,
    }
    if dict(implementation) != expected:
        raise MetadataRunError("FORMULA_CONTRACT_INVALID")
    formula_body = value.get("formulaContract")
    if (
        value.get("decisionScope") != "research_only"
        or value.get("operationalDisposition") != "NoTrade/no integration"
        or not isinstance(formula_body, Mapping)
        or formula_body.get("protocol_version") != _FORMULA_PROTOCOL_VERSION
    ):
        raise MetadataRunError("FORMULA_CONTRACT_INVALID")


def _validate_sample_design(
    value: Mapping[str, object],
    arguments: MetadataRunArguments,
    repository_root: _RepositoryCapability,
) -> None:
    exposure = value.get("exposureState")
    formula_binding = value.get("formulaBinding")
    selection_binding = value.get("selectionImplementation")
    ranking = value.get("ranking")
    if not all(
        isinstance(item, Mapping)
        for item in (exposure, formula_binding, selection_binding, ranking)
    ):
        raise MetadataRunError("SAMPLE_DESIGN_INVALID")
    exposure = cast(Mapping[str, object], exposure)
    formula_binding = cast(Mapping[str, object], formula_binding)
    selection_binding = cast(Mapping[str, object], selection_binding)
    ranking = cast(Mapping[str, object], ranking)
    if (
        value.get("schemaVersion") != _SAMPLE_DESIGN_SCHEMA
        or value.get("status") != _SAMPLE_DESIGN_STATUS
        or value.get("programId") != _PROGRAM_ID
        or value.get("goalVersion") != _GOAL_VERSION
        or value.get("usageScope") != "research_only"
        or value.get("operationalDisposition") != "NoTrade/no integration"
        or value.get("candidatePool") != list(CANDIDATE_POOL)
        or value.get("desiredSelectionCount") != DESIRED_SELECTION_COUNT
        or exposure.get("metadataOpened") is not False
        or exposure.get("priceVolumeOutcomePerformanceOpened") is not False
        or exposure.get("selectedSymbols") != "pending_metadata_eligibility"
    ):
        raise MetadataRunError("SAMPLE_DESIGN_INVALID")
    if dict(formula_binding) != {
        "path": _relative_argument_path(
            arguments.formula_contract_path,
            repository_root,
        ),
        "protocolVersion": _FORMULA_PROTOCOL_VERSION,
        "sha256": arguments.formula_contract_sha256,
        "sourcePath": _relative_argument_path(
            arguments.formula_source_path,
            repository_root,
        ),
        "sourceSha256": arguments.formula_source_sha256,
    }:
        raise MetadataRunError("SAMPLE_DESIGN_INVALID")
    if dict(selection_binding) != {
        "sourcePath": _relative_argument_path(
            arguments.selection_source_path,
            repository_root,
        ),
        "sourceSha256": arguments.selection_source_sha256,
        "testPath": _relative_argument_path(
            arguments.selection_test_path,
            repository_root,
        ),
        "testSha256": arguments.selection_test_sha256,
    }:
        raise MetadataRunError("SAMPLE_DESIGN_INVALID")
    if (
        ranking.get("formulaSourceSha256") != arguments.formula_source_sha256
        or ranking.get("selectionRule")
        != "first_six_eligible_in_frozen_rank_order"
        or ranking.get("replacementAfterPriceOpen") != "forbidden"
        or ranking.get("rankedPool")
        != _expected_ranked_pool(arguments.formula_source_sha256)
    ):
        raise MetadataRunError("SAMPLE_DESIGN_INVALID")


def _validate_source_contract(
    value: Mapping[str, object],
    arguments: MetadataRunArguments,
    repository_root: _RepositoryCapability,
) -> None:
    bindings = value.get("bindings")
    exposure = value.get("exposureState")
    credential_boundary = value.get("credentialBoundary")
    transport_gate = value.get("liveTransportGate")
    forbidden = value.get("forbiddenRequests")
    provider = value.get("provider")
    metadata_fail_closed = value.get("metadataFailClosed")
    raw_lineage = value.get("rawLineage")
    quality_evidence = value.get("qualityEvidence")
    supersedes = value.get("supersedes")
    if not all(
        isinstance(item, Mapping)
        for item in (
            bindings,
            exposure,
            credential_boundary,
            transport_gate,
            forbidden,
            provider,
            metadata_fail_closed,
            raw_lineage,
            quality_evidence,
            supersedes,
        )
    ):
        raise MetadataRunError("SOURCE_CONTRACT_INVALID")
    bindings = cast(Mapping[str, object], bindings)
    exposure = cast(Mapping[str, object], exposure)
    credential_boundary = cast(Mapping[str, object], credential_boundary)
    transport_gate = cast(Mapping[str, object], transport_gate)
    forbidden = cast(Mapping[str, object], forbidden)
    provider = cast(Mapping[str, object], provider)
    metadata_fail_closed = cast(Mapping[str, object], metadata_fail_closed)
    raw_lineage = cast(Mapping[str, object], raw_lineage)
    quality_evidence = cast(Mapping[str, object], quality_evidence)
    supersedes = cast(Mapping[str, object], supersedes)
    frozen_at = _parse_strict_utc_timestamp(
        value.get("frozenAt"),
        "SOURCE_CONTRACT_INVALID",
    )
    finalized_at = _parse_strict_utc_timestamp(
        value.get("finalizedAt"),
        "SOURCE_CONTRACT_INVALID",
    )
    if (
        set(value)
        != {
            "allowedRequests",
            "bindings",
            "canonicalLedgerPath",
            "credentialBoundary",
            "decisionScope",
            "deferredUntilSampleFreeze",
            "exposureState",
            "forbiddenRequests",
            "finalizedAt",
            "frozenAt",
            "frozenAtMeaning",
            "goalVersion",
            "liveTransportGate",
            "metadataFailClosed",
            "operationalDisposition",
            "programId",
            "provider",
            "qualityEvidence",
            "rawLineage",
            "schemaVersion",
            "status",
            "supersedes",
        }
        or value.get("schemaVersion")
        != "rp001-toss-read-only-source-contract.v1.2"
        or value.get("status") != "read_only_metadata_runner_authorized"
        or value.get("programId") != _PROGRAM_ID
        or value.get("goalVersion") != _GOAL_VERSION
        or value.get("decisionScope") != "research_only"
        or value.get("operationalDisposition") != "NoTrade/no integration"
        or value.get("canonicalLedgerPath")
        != "research/rp-001/local-ledgers/interim-program"
        or value.get("frozenAt") != "2026-07-10T22:35:20Z"
        or value.get("frozenAtMeaning")
        != "metadata_only_policy_boundary_before_runner_finalization"
        or finalized_at < frozen_at
        or dict(supersedes) != _expected_source_contract_supersedes()
        or dict(provider) != _expected_source_contract_provider()
        or value.get("allowedRequests") != _expected_allowed_requests()
        or value.get("deferredUntilSampleFreeze")
        != _expected_deferred_requests()
        or dict(metadata_fail_closed)
        != _expected_metadata_fail_closed()
        or dict(raw_lineage) != _expected_raw_lineage()
        or dict(quality_evidence) != _expected_quality_evidence()
        or dict(exposure)
        != {
            "metadataOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "priceVolumeOutcomePerformanceOpened": False,
        }
        or dict(credential_boundary)
        != {
            "credentialValuesInCommandLineArtifactLogError": "forbidden",
            "oauthResponsePersistence": "forbidden",
            "pathClass": "repository_dot_storage_0600_pinned_regular_file",
            "tokenLifecycle": "ephemeral_credential_frame_only",
            "tokenOrAuthorizationInTraceback": "forbidden",
        }
        or dict(transport_gate)
        != {
            "allowedHost": "openapi.tossinvest.com",
            "allowedScheme": "https",
            "automaticRedirects": "forbidden",
            "httpErrorBodyLineage": "required_if_non_sensitive",
            "networkErrors": "sanitized_no_provider_body_reflection",
            "redirectStatusHandling": (
                "return_as_http_response_without_following"
            ),
        }
        or dict(forbidden)
        != {
            "additionalMarketEndpoints": ["prices", "trades", "orderbook"],
            "families": ["order", "account", "asset"],
            "mutatingMarketMethods": ["POST", "PUT", "PATCH", "DELETE"],
            "operatingAppIntegration": True,
        }
    ):
        raise MetadataRunError("SOURCE_CONTRACT_INVALID")
    expected_bindings: dict[str, object] = {
        "runner": {
            "sourcePath": _relative_argument_path(
                arguments.runner_source_path,
                repository_root,
            ),
            "sourceSha256": arguments.runner_source_sha256,
            "testPath": _relative_argument_path(
                arguments.runner_test_path,
                repository_root,
            ),
            "testSha256": arguments.runner_test_sha256,
        },
        "collector": {
            "sourcePath": _relative_argument_path(
                arguments.collector_source_path,
                repository_root,
            ),
            "sourceSha256": arguments.collector_source_sha256,
            "testPath": _relative_argument_path(
                arguments.collector_test_path,
                repository_root,
            ),
            "testSha256": arguments.collector_test_sha256,
        },
        "formulaContract": {
            "path": _relative_argument_path(
                arguments.formula_contract_path,
                repository_root,
            ),
            "protocolVersion": _FORMULA_PROTOCOL_VERSION,
            "sha256": arguments.formula_contract_sha256,
        },
        "metadataSampleDesign": {
            "path": _relative_argument_path(
                arguments.sample_design_path,
                repository_root,
            ),
            "sha256": arguments.sample_design_sha256,
        },
        "selection": {
            "sourcePath": _relative_argument_path(
                arguments.selection_source_path,
                repository_root,
            ),
            "sourceSha256": arguments.selection_source_sha256,
            "testPath": _relative_argument_path(
                arguments.selection_test_path,
                repository_root,
            ),
            "testSha256": arguments.selection_test_sha256,
        },
        "localEvidence": {
            "sourcePath": _relative_argument_path(
                arguments.local_evidence_source_path,
                repository_root,
            ),
            "sourceSha256": arguments.local_evidence_source_sha256,
            "testPath": _relative_argument_path(
                arguments.local_evidence_test_path,
                repository_root,
            ),
            "testSha256": arguments.local_evidence_test_sha256,
        },
        "sensitiveValuePolicy": {
            "sourcePath": _relative_argument_path(
                arguments.sensitive_policy_source_path,
                repository_root,
            ),
            "sourceSha256": arguments.sensitive_policy_source_sha256,
            "testPath": _relative_argument_path(
                arguments.sensitive_policy_test_path,
                repository_root,
            ),
            "testSha256": arguments.sensitive_policy_test_sha256,
        },
    }
    if dict(bindings) != expected_bindings:
        raise MetadataRunError("SOURCE_CONTRACT_INVALID")


def _expected_allowed_requests() -> list[dict[str, object]]:
    return [
        {
            "method": "POST",
            "path": "/oauth2/token",
            "purpose": "ephemeral_authentication_only",
            "responsePersistence": "forbidden",
        },
        {
            "method": "GET",
            "parameters": ["symbols"],
            "path": "/api/v1/stocks",
            "purpose": "metadata_only_sample_selection",
        },
    ]


def _expected_deferred_requests() -> list[dict[str, object]]:
    return [
        {
            "method": "GET",
            "parameters": [
                "symbol",
                "interval=1d",
                "count=200",
                "adjusted",
                "before",
            ],
            "path": "/api/v1/candles",
            "purpose": "predeclared_daily_price_volume",
            "reason": (
                "price_volume_open_forbidden_during_metadata_only_selection"
            ),
            "successorContract": "required_after_metadata_sample_freeze",
        },
    ]


def _expected_source_contract_supersedes() -> dict[str, object]:
    return {
        "path": (
            "research/rp-001/contracts/"
            "toss-read-only-source-contract-v1.1.json"
        ),
        "reason": (
            "bind_metadata_runner_execution_lineage_and_restrict_"
            "live_transport_to_metadata_only"
        ),
        "sha256": (
            "05b01946678f473291c825843d42255c66d483c7268e5747f8ca44459df5a89b"
        ),
    }


def _expected_source_contract_provider() -> dict[str, object]:
    return {
        "baseUrl": "https://openapi.tossinvest.com",
        "name": "Toss Securities OpenAPI",
        "officialSpecificationUrl": (
            "https://openapi.tossinvest.com/openapi-docs/latest/openapi.json"
        ),
        "rawSha256": (
            "2c54ebfd038a8c135f4b7f9036c42934d8ab9906c026251a7ae827b81e8e6aa8"
        ),
        "version": "1.2.2",
    }


def _expected_metadata_fail_closed() -> dict[str, object]:
    return {
        "allOtherFields": "UNREGISTERED_METADATA_FIELD",
        "exactRequestedSymbolSet": True,
        "requiredFields": [
            "symbol",
            "name",
            "englishName",
            "isinCode",
            "market",
            "securityType",
            "isCommonShare",
            "status",
            "currency",
            "sharesOutstanding",
        ],
        "safeExtraFields": [
            "listDate",
            "delistDate",
            "leverageFactor",
            "koreanMarketDetail",
        ],
        "sampleRole": "metadata_only",
    }


def _expected_raw_lineage() -> dict[str, object]:
    return {
        "canonicalBodySidecarNoSelfHash": True,
        "captureBeforeDomainParsing": True,
        "exactBodyBase64AndSha256": True,
        "priorSafeCaptureRetention": True,
        "receivedAtRequired": True,
        "responseHeaderAllowlist": True,
        "sensitiveCurrentResponseCaptureCount": 0,
    }


def _expected_quality_evidence() -> dict[str, object]:
    return {
        "collectorTestsPassed": 62,
        "collectorTestsTotal": 62,
        "criticalFindings": 0,
        "finalReviewVerdict": "APPROVE",
        "importantFindings": 0,
        "localEvidenceTestsPassed": 21,
        "localEvidenceTestsTotal": 21,
        "minorFindings": 0,
        "preflightHistory": [
            "runner_metadata_only_transport_and_source_lineage_reviewed",
            "namespace_toctou_and_interrupt_recovery_reviewed",
            "credential_path_class_fail_closed",
            "fragmented_http_body_lineage_reviewed",
        ],
        "programRegressionTestsPassed": 374,
        "programRegressionTestsTotal": 374,
        "reviewScope": [
            "parent_fd_trust_anchor_active_lifecycle",
            "post_return_external_cas_deferred",
        ],
        "reviewVerdicts": {
            "collector": "APPROVE_C0_I0_M0",
            "localEvidence": "APPROVE_C0_I0_M0",
            "runner": "APPROVE_C0_I0_M0",
            "selection": "APPROVE_C0_I0_M0",
            "sensitiveValuePolicy": "APPROVE_C0_I0_M0",
        },
        "runnerTestsPassed": 87,
        "runnerTestsTotal": 87,
        "runnerDependencyRegressionTestsPassed": 266,
        "runnerDependencyRegressionTestsTotal": 266,
        "selectionTestsPassed": 33,
        "selectionTestsTotal": 33,
        "sensitivePolicyTestsPassed": 6,
        "sensitivePolicyTestsTotal": 6,
    }


def _expected_ranked_pool(formula_source_sha256: str) -> list[dict[str, object]]:
    ranked = []
    for symbol in CANDIDATE_POOL:
        hash_input = f"{formula_source_sha256}:{symbol}"
        ranked.append(
            (
                hashlib.sha256(hash_input.encode("ascii")).hexdigest(),
                symbol,
                hash_input,
            )
        )
    ranked.sort(key=lambda value: (value[0], value[1]))
    return [
        {
            "rank": rank,
            "rankingDigest": digest,
            "selectionBasisHashInput": hash_input,
            "symbol": symbol,
        }
        for rank, (digest, symbol, hash_input) in enumerate(ranked, start=1)
    ]


def _load_credentials(capability: _CredentialCapability) -> _Credentials:
    source = capability.read()
    try:
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except MetadataRunError:
        raise
    except Exception:
        raise MetadataRunError("CREDENTIAL_FILE_INVALID") from None
    if not isinstance(value, dict):
        raise MetadataRunError("CREDENTIAL_FILE_INVALID")
    client_identifier = value.get("clientId")
    private_credential = value.get("clientSecret")
    if (
        not isinstance(client_identifier, str)
        or not client_identifier
        or not isinstance(private_credential, str)
        or not private_credential
        or any(character in client_identifier for character in "\r\n\x00")
        or any(character in private_credential for character in "\r\n\x00")
    ):
        raise MetadataRunError("CREDENTIAL_FILE_INVALID")
    return _Credentials(client_identifier, private_credential)


def _require_allowed_metadata_request(request: HttpRequest) -> None:
    if not isinstance(request, HttpRequest) or request.method != "GET":
        raise MetadataRunError("ENDPOINT_NOT_ALLOWED")
    parsed = urlsplit(request.url)
    query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "openapi.tossinvest.com"
        or parsed.path != "/api/v1/stocks"
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or len(query) != 1
        or query[0][0] != "symbols"
        or not query[0][1]
    ):
        raise MetadataRunError("ENDPOINT_NOT_ALLOWED")
    headers = {name.lower(): value for name, value in request.headers.items()}
    authorization = headers.get("authorization")
    if (
        set(headers) != {"accept", "authorization"}
        or headers.get("accept") != "application/json"
        or not isinstance(authorization, str)
        or not authorization.startswith("Bearer ")
        or authorization == "Bearer "
        or any(character in authorization for character in "\r\n\x00")
    ):
        raise MetadataRunError("ENDPOINT_NOT_ALLOWED")


def _url_response(
    value: object,
    error_code: str,
    body_limit: int,
    oversized_code: str,
) -> HttpResponse:
    try:
        status = getattr(value, "status")
        headers = _copy_response_headers(getattr(value, "headers"))
        body = _read_bounded_body(
            value,
            body_limit,
            error_code,
            oversized_code,
        )
    except MetadataRunError:
        _close_quietly(value)
        raise
    except Exception:
        _close_quietly(value)
        raise MetadataRunError(error_code) from None
    _close_quietly(value)
    if (
        type(status) is not int
        or status < 100
        or status > 599
        or not isinstance(body, bytes)
    ):
        raise MetadataRunError(error_code)
    return HttpResponse(status=status, headers=headers, body=body)


def _http_error_response(
    error: HTTPError,
    error_code: str,
    body_limit: int,
    oversized_code: str,
) -> HttpResponse:
    try:
        body = _read_bounded_body(
            error,
            body_limit,
            error_code,
            oversized_code,
        )
        headers = _copy_response_headers(error.headers)
        status = error.code
    except MetadataRunError:
        _close_quietly(error)
        raise
    except Exception:
        _close_quietly(error)
        raise MetadataRunError(error_code) from None
    _close_quietly(error)
    if type(status) is not int or not isinstance(body, bytes):
        raise MetadataRunError(error_code)
    return HttpResponse(status=status, headers=headers, body=body)


def _read_bounded_body(
    reader: object,
    body_limit: int,
    error_code: str,
    oversized_code: str,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            chunk = reader.read(body_limit + 1 - total)
        except Exception:
            raise MetadataRunError(error_code) from None
        if not isinstance(chunk, bytes):
            raise MetadataRunError(error_code)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > body_limit:
            raise MetadataRunError(oversized_code)


def _copy_response_headers(value: object) -> Mapping[str, str]:
    try:
        items = value.items()
        copied = {str(name): str(header_value) for name, header_value in items}
    except Exception:
        raise MetadataRunError("INVALID_HTTP_RESPONSE") from None
    return MappingProxyType(copied)


def _close_quietly(value: object) -> None:
    try:
        close = getattr(value, "close", None)
        if callable(close):
            close()
    except Exception:
        return


def _build_redirect_rejecting_opener() -> OpenerDirector:
    return build_opener(_RejectRedirectHandler())


def _build_run_paths(
    arguments: MetadataRunArguments,
    repository: _RepositoryCapability,
) -> _RunPaths:
    if _RUN_ID_PATTERN.fullmatch(arguments.run_id) is None:
        raise MetadataRunError("RUN_ID_INVALID")
    output_root = _resolve_repository_namespace_path(
        repository,
        arguments.output_directory,
        "OUTPUT_PATH_INVALID",
    )
    run_directory = output_root / arguments.run_id
    return _RunPaths(
        raw=run_directory / "raw-metadata.json",
        processed=run_directory / "processed-metadata.json",
        selection=run_directory / "sample-selection.json",
        exposure=run_directory / "metadata-exposure.json",
        manifest=run_directory / "manifest.json",
        failure=run_directory / "failure.json",
    )


def _require_canonical_ledger_directory(
    ledger_directory: Path,
    repository: _RepositoryCapability,
) -> None:
    expected = repository.path / _CANONICAL_LEDGER_RELATIVE_PATH
    if ledger_directory != expected:
        raise MetadataRunError("LEDGER_PATH_INVALID")


def _require_repository_root(path: Path) -> _RepositoryCapability:
    declared_path = Path(os.path.abspath(path))
    try:
        declared_metadata = os.lstat(declared_path)
        canonical_path = declared_path.resolve(strict=True)
        parent_descriptor = os.open(
            canonical_path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except (OSError, RuntimeError):
        raise MetadataRunError("REPOSITORY_ROOT_INVALID") from None
    if not stat.S_ISDIR(declared_metadata.st_mode):
        os.close(parent_descriptor)
        raise MetadataRunError("REPOSITORY_ROOT_INVALID")
    try:
        descriptor = _open_child_directory(
            parent_descriptor,
            canonical_path.name,
            create=False,
            error_code="REPOSITORY_ROOT_INVALID",
        )
        identity = _directory_identity(os.fstat(descriptor))
        if identity != _directory_identity(declared_metadata):
            raise MetadataRunError("REPOSITORY_ROOT_INVALID")
        capability = _RepositoryCapability(
            declared_path=declared_path,
            path=canonical_path,
            descriptor=descriptor,
            identity=identity,
            parent_descriptor=parent_descriptor,
            name=canonical_path.name,
        )
        capability.verify()
        return capability
    except BaseException:
        if "descriptor" in locals():
            os.close(descriptor)
        os.close(parent_descriptor)
        raise


def _close_repository_capability(repository: _RepositoryCapability) -> None:
    os.close(repository.descriptor)
    os.close(repository.parent_descriptor)


def _repository_relative_argument(
    repository: _RepositoryCapability,
    value: Path,
    error_code: str,
) -> Path:
    candidate = value if value.is_absolute() else repository.declared_path / value
    lexical = Path(os.path.abspath(candidate))
    for possible_root in (repository.declared_path, repository.path):
        try:
            relative = lexical.relative_to(possible_root)
        except ValueError:
            continue
        if relative.parts:
            return relative
    raise MetadataRunError(error_code)


def _repository_input_relative_argument(
    repository: _RepositoryCapability,
    value: Path,
    error_code: str,
) -> Path:
    candidate = value if value.is_absolute() else repository.declared_path / value
    try:
        repository.verify()
        canonical = candidate.resolve(strict=True)
        repository.verify()
        relative = canonical.relative_to(repository.path)
    except (MetadataRunError, OSError, RuntimeError, ValueError):
        raise MetadataRunError(error_code) from None
    if not relative.parts:
        raise MetadataRunError(error_code)
    return relative


def _resolve_repository_namespace_path(
    repository: _RepositoryCapability,
    value: Path,
    error_code: str,
) -> Path:
    relative = _repository_relative_argument(repository, value, error_code)
    return repository.path / relative


def _open_credential_capability(
    repository: _RepositoryCapability,
    value: Path,
) -> _CredentialCapability:
    repository.verify()
    candidate = value if value.is_absolute() else repository.declared_path / value
    lexical = Path(os.path.abspath(candidate))
    repository_relative: Path | None = None
    for possible_root in (repository.declared_path, repository.path):
        try:
            repository_relative = lexical.relative_to(possible_root)
            break
        except ValueError:
            continue
    if repository_relative is None:
        raise MetadataRunError("CREDENTIAL_PATH_INVALID")
    if not repository_relative.parts:
        raise MetadataRunError("CREDENTIAL_PATH_INVALID")
    if repository_relative.parts[0] != ".storage":
        raise MetadataRunError("CREDENTIAL_PATH_INVALID")
    parent_path = repository.path / repository_relative.parent
    parent_descriptor = _open_repository_directory(
        repository,
        parent_path,
        create=False,
        error_code="CREDENTIAL_PATH_INVALID",
    )
    parent = _PinnedDirectory(
        repository=repository,
        path=parent_path,
        descriptor=parent_descriptor,
        identity=_directory_identity(os.fstat(parent_descriptor)),
    )
    try:
        descriptor, identity = _open_regular_file_at(
            parent_descriptor,
            repository_relative.name,
            error_code="CREDENTIAL_FILE_INVALID",
            required_mode=0o600,
        )
    except BaseException:
        os.close(parent_descriptor)
        raise
    capability = _CredentialCapability(
        parent_descriptor=parent_descriptor,
        parent_verifier=lambda: _assert_pinned_directory(parent),
        name=repository_relative.name,
        descriptor=descriptor,
        identity=identity,
        owned_parent_descriptors=(parent_descriptor,),
    )
    try:
        capability.verify()
    except BaseException:
        capability.close()
        raise
    return capability


def _relative_argument_path(
    value: Path,
    repository: _RepositoryCapability,
) -> str:
    return _repository_input_relative_argument(
        repository,
        value,
        "INPUT_PATH_INVALID",
    ).as_posix()


def _relative_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        raise MetadataRunError("INPUT_PATH_INVALID") from None


def _read_repository_regular_file(
    repository: _RepositoryCapability,
    relative_path: Path,
    error_code: str,
    *,
    required_mode: int | None = None,
) -> bytes:
    parent_path = repository.path / relative_path.parent
    parent_descriptor = _open_repository_directory(
        repository,
        parent_path,
        create=False,
        error_code=error_code,
    )
    parent = _PinnedDirectory(
        repository=repository,
        path=parent_path,
        descriptor=parent_descriptor,
        identity=_directory_identity(os.fstat(parent_descriptor)),
    )
    descriptor = -1
    try:
        descriptor, identity = _open_regular_file_at(
            parent_descriptor,
            relative_path.name,
            error_code=error_code,
            required_mode=required_mode,
        )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        _assert_pinned_directory(parent)
        _assert_regular_file_attachment(
            parent_descriptor,
            relative_path.name,
            descriptor,
            identity,
            error_code=error_code,
            required_mode=required_mode,
        )
        return b"".join(chunks)
    except OSError:
        raise MetadataRunError(error_code) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


@contextmanager
def _pinned_namespace_guard(
    output: _PinnedDirectory,
    ledger: _PinnedDirectory,
    *,
    locked_output: _HeldNamespaceLock | None = None,
    locked_ledger: _HeldNamespaceLock | None = None,
) -> Iterator[_NamespaceGuard]:
    locks = tuple(
        held_lock
        for held_lock in (locked_output, locked_ledger)
        if held_lock is not None
    )
    guard = _NamespaceGuard(output, ledger, locks)
    try:
        guard.verify()
        yield guard
    finally:
        guard.verify()


def _directory_identity(metadata: os.stat_result) -> _DirectoryIdentity:
    return _DirectoryIdentity(device=metadata.st_dev, inode=metadata.st_ino)


def _assert_pinned_directory(pinned: _PinnedDirectory) -> None:
    try:
        pinned.repository.verify()
        descriptor = _open_repository_directory(
            pinned.repository,
            pinned.path,
            create=False,
            error_code="NAMESPACE_IDENTITY_CHANGED",
        )
    except MetadataRunError:
        raise MetadataRunError("NAMESPACE_IDENTITY_CHANGED") from None
    try:
        current_identity = _directory_identity(os.fstat(descriptor))
    except OSError:
        raise MetadataRunError("NAMESPACE_IDENTITY_CHANGED") from None
    finally:
        os.close(descriptor)
    if current_identity != pinned.identity:
        raise MetadataRunError("NAMESPACE_IDENTITY_CHANGED")


def _assert_child_directory_attachment(
    parent_descriptor: int,
    name: str,
    child_descriptor: int,
    expected_identity: _DirectoryIdentity,
    *,
    error_code: str = "NAMESPACE_IDENTITY_CHANGED",
) -> None:
    try:
        held_metadata = os.fstat(child_descriptor)
        path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISDIR(held_metadata.st_mode)
        or not stat.S_ISDIR(path_metadata.st_mode)
        or _directory_identity(held_metadata) != expected_identity
        or _directory_identity(path_metadata) != expected_identity
    ):
        raise MetadataRunError(error_code)
    try:
        opened_descriptor = _open_child_directory(
            parent_descriptor,
            name,
            create=False,
            error_code=error_code,
        )
    except MetadataRunError:
        raise MetadataRunError(error_code) from None
    try:
        if _directory_identity(os.fstat(opened_descriptor)) != expected_identity:
            raise MetadataRunError(error_code)
    finally:
        os.close(opened_descriptor)


def _assert_regular_file_attachment(
    parent_descriptor: int,
    name: str,
    file_descriptor: int,
    expected_identity: _DirectoryIdentity,
    *,
    error_code: str,
    required_mode: int | None = None,
) -> None:
    try:
        held_metadata = os.fstat(file_descriptor)
        path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISREG(held_metadata.st_mode)
        or not stat.S_ISREG(path_metadata.st_mode)
        or _directory_identity(held_metadata) != expected_identity
        or _directory_identity(path_metadata) != expected_identity
        or (
            required_mode is not None
            and (
                stat.S_IMODE(held_metadata.st_mode) != required_mode
                or stat.S_IMODE(path_metadata.st_mode) != required_mode
            )
        )
    ):
        raise MetadataRunError(error_code)
    try:
        opened_descriptor, opened_identity = _open_regular_file_at(
            parent_descriptor,
            name,
            error_code=error_code,
            required_mode=required_mode,
        )
    except MetadataRunError:
        raise MetadataRunError(error_code) from None
    try:
        if opened_identity != expected_identity:
            raise MetadataRunError(error_code)
    finally:
        os.close(opened_descriptor)


def _namespace_error_or_none(
    guard: _NamespaceGuard,
) -> MetadataRunError | None:
    try:
        guard.verify()
    except BaseException:
        return MetadataRunError("NAMESPACE_IDENTITY_CHANGED")
    return None


def _entry_exists_at(directory_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise LocalEvidenceError("failed to inspect evidence destination") from error
    return True


def _require_output_run_absent(
    output: _PinnedDirectory,
    run_id: str,
) -> None:
    _assert_pinned_directory(output)
    if _entry_exists_at(output.descriptor, run_id):
        raise MetadataRunError("OUTPUT_ALREADY_EXISTS")
    _assert_pinned_directory(output)


def _publishable_document_source(value: Mapping[str, object]) -> bytes:
    source = canonical_json_bytes(value)
    if _contains_own_hash_key(value):
        raise LocalEvidenceError("own-hash keys are prohibited in artifact bodies")
    if find_sensitive_values(source.decode("utf-8")):
        raise LocalEvidenceError("sensitive values are prohibited in artifact bodies")
    return source


def _contains_own_hash_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            (isinstance(key, str) and key in _OWN_HASH_KEYS)
            or _contains_own_hash_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_own_hash_key(nested) for nested in value)
    return False


def _publish_pair_at(
    directory_descriptor: int,
    body_name: str,
    body_source: bytes,
    sidecar_name: str,
    sidecar_source: bytes,
    *,
    operation_label: str,
    identity_verifier: Callable[[], None],
    preserve_complete_pair_on_interrupt: bool = False,
) -> None:
    identity_verifier()
    if _entry_exists_at(directory_descriptor, body_name) or _entry_exists_at(
        directory_descriptor,
        sidecar_name,
    ):
        raise LocalEvidenceError("evidence destination already exists")
    expected_sha256 = sha256_bytes(body_source)
    try:
        _write_exclusive_file_at(
            directory_descriptor,
            body_name,
            body_source,
            identity_verifier,
        )
        _run_lifecycle_observer("pair_body_published", operation_label)
        identity_verifier()
        _write_exclusive_file_at(
            directory_descriptor,
            sidecar_name,
            sidecar_source,
            identity_verifier,
        )
        identity_verifier()
        os.fsync(directory_descriptor)
        _run_lifecycle_observer("pair_published", operation_label)
        identity_verifier()
    except BaseException:
        complete = _pair_matches_at(
            directory_descriptor,
            body_name,
            expected_sha256,
            body_source,
        )
        if not (preserve_complete_pair_on_interrupt and complete):
            _remove_exact_pair_at(
                directory_descriptor,
                body_name,
                expected_sha256,
                body_source,
            )
        raise


def _write_exclusive_file_at(
    directory_descriptor: int,
    name: str,
    source: bytes,
    identity_verifier: Callable[[], None],
) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    created = False
    try:
        identity_verifier()
        descriptor = os.open(
            name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        created = True
        offset = 0
        while offset < len(source):
            identity_verifier()
            written = os.write(descriptor, source[offset:])
            if written <= 0:
                raise OSError("evidence write made no progress")
            offset += written
        identity_verifier()
        os.fsync(descriptor)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        if created:
            try:
                os.unlink(name, dir_fd=directory_descriptor)
            except OSError:
                pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _pair_matches_at(
    directory_descriptor: int,
    body_name: str,
    expected_sha256: str,
    expected_body: bytes | None,
) -> bool:
    sidecar_name = f"{body_name}.sha256"
    try:
        body = _read_exact_file_at(directory_descriptor, body_name)
        sidecar = _read_exact_file_at(directory_descriptor, sidecar_name)
    except (FileNotFoundError, LocalEvidenceError):
        return False
    return (
        sha256_bytes(body) == expected_sha256
        and (expected_body is None or body == expected_body)
        and sidecar == f"{expected_sha256}\n".encode("ascii")
    )


def _remove_exact_pair_at(
    directory_descriptor: int,
    body_name: str,
    expected_sha256: str,
    expected_body: bytes | None,
) -> None:
    sidecar_name = f"{body_name}.sha256"
    body_exists = _entry_exists_at(directory_descriptor, body_name)
    sidecar_exists = _entry_exists_at(directory_descriptor, sidecar_name)
    if body_exists:
        body = _read_exact_file_at(directory_descriptor, body_name)
        if sha256_bytes(body) != expected_sha256 or (
            expected_body is not None and body != expected_body
        ):
            raise LocalEvidenceError("artifact body changed before rollback")
    if sidecar_exists:
        sidecar = _read_exact_file_at(directory_descriptor, sidecar_name)
        if sidecar != f"{expected_sha256}\n".encode("ascii"):
            raise LocalEvidenceError("artifact sidecar changed before rollback")
    try:
        if sidecar_exists:
            os.unlink(sidecar_name, dir_fd=directory_descriptor)
        if body_exists:
            os.unlink(body_name, dir_fd=directory_descriptor)
        if body_exists or sidecar_exists:
            os.fsync(directory_descriptor)
    except OSError as error:
        raise LocalEvidenceError("failed to roll back artifact pair") from error


def _remove_exact_pair_by_path(
    body_path: Path,
    expected_sha256: str,
    expected_body: bytes | None,
) -> None:
    sidecar_path = Path(f"{body_path}.sha256")
    for path, expected in (
        (body_path, expected_body),
        (sidecar_path, f"{expected_sha256}\n".encode("ascii")),
    ):
        if not os.path.lexists(path):
            continue
        try:
            metadata = os.lstat(path)
            source = path.read_bytes()
        except OSError as error:
            raise LocalEvidenceError("failed to inspect delegated artifact") from error
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalEvidenceError("delegated artifact is not a regular file")
        if path == body_path:
            if sha256_bytes(source) != expected_sha256 or (
                expected is not None and source != expected
            ):
                raise LocalEvidenceError("delegated artifact body changed")
        elif source != expected:
            raise LocalEvidenceError("delegated artifact sidecar changed")
    try:
        if os.path.lexists(sidecar_path):
            sidecar_path.unlink()
        if os.path.lexists(body_path):
            body_path.unlink()
    except OSError as error:
        raise LocalEvidenceError("failed to clean delegated artifact") from error


def _read_exact_file_at(directory_descriptor: int, name: str) -> bytes:
    try:
        path_metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        raise
    except OSError as error:
        raise LocalEvidenceError("failed to inspect evidence file") from error
    if not stat.S_ISREG(path_metadata.st_mode):
        raise LocalEvidenceError("evidence file is not a real regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise LocalEvidenceError("failed to open evidence file") from error
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_metadata.st_mode)
            or _directory_identity(opened_metadata)
            != _directory_identity(path_metadata)
        ):
            raise LocalEvidenceError("evidence file identity changed")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final_metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if _directory_identity(final_metadata) != _directory_identity(path_metadata):
            raise LocalEvidenceError("evidence file identity changed")
        return b"".join(chunks)
    except OSError as error:
        raise LocalEvidenceError("failed to read evidence file") from error
    finally:
        os.close(descriptor)


def _validate_ledger_entries_at(
    events_descriptor: int,
) -> tuple[int, str | None]:
    try:
        names = tuple(os.listdir(events_descriptor))
    except OSError as error:
        raise LocalEvidenceError("failed to read local ledger") from error
    bodies: dict[int, str] = {}
    sidecars: dict[int, str] = {}
    for name in names:
        try:
            metadata = os.stat(
                name,
                dir_fd=events_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise LocalEvidenceError("failed to inspect ledger entry") from error
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalEvidenceError("ledger entries must be real regular files")
        body_match = _LEDGER_BODY_NAME.fullmatch(name)
        if body_match is not None:
            bodies[int(body_match.group("sequence"))] = name
            continue
        sidecar_match = _LEDGER_SIDECAR_NAME.fullmatch(name)
        if sidecar_match is not None:
            sidecars[int(sidecar_match.group("sequence"))] = name
            continue
        raise LocalEvidenceError("local ledger contains an unexpected entry")
    if set(bodies) != set(sidecars):
        raise LocalEvidenceError("local ledger body and sidecar sets differ")
    sequences = sorted(bodies)
    if sequences != list(range(1, len(sequences) + 1)):
        raise LocalEvidenceError("local ledger sequence is not contiguous")
    previous_sha256: str | None = None
    for sequence in sequences:
        source = _read_exact_file_at(events_descriptor, bodies[sequence])
        sidecar = _read_exact_file_at(events_descriptor, sidecars[sequence])
        actual_sha256 = sha256_bytes(source)
        if sidecar != f"{actual_sha256}\n".encode("ascii"):
            raise LocalEvidenceError("local ledger record hash mismatch")
        try:
            record = _load_canonical_object(source)
        except MetadataRunError:
            raise LocalEvidenceError("local ledger record is not canonical") from None
        if _publishable_document_source(dict(record)) != source:
            raise LocalEvidenceError("local ledger record is invalid")
        if (
            set(record) != _LEDGER_RECORD_KEYS
            or record.get("schemaVersion") != LOCAL_LEDGER_SCHEMA_VERSION
            or type(record.get("sequence")) is not int
            or record.get("sequence") != sequence
            or not isinstance(record.get("eventType"), str)
            or not isinstance(record.get("occurredAt"), str)
            or not isinstance(record.get("payload"), dict)
            or record.get("previousRecordSha256") != previous_sha256
        ):
            raise LocalEvidenceError("local ledger record contract is invalid")
        previous_sha256 = actual_sha256
    return len(sequences), previous_sha256


def _require_matching_ledger_entry(
    value: object,
    ledger_directory: Path,
    sequence: int,
    expected_sha256: str,
) -> None:
    expected_path = ledger_directory / "events" / f"{sequence:06d}.json"
    if (
        not isinstance(value, LocalLedgerEntry)
        or value.sequence != sequence
        or value.path != expected_path
        or value.sidecar_path != Path(f"{expected_path}.sha256")
        or value.record_sha256 != expected_sha256
    ):
        raise LocalEvidenceError("ledger delegate returned an invalid entry")


def _run_lifecycle_observer(operation: str, target: str) -> None:
    del operation, target


def _no_op_verifier() -> None:
    return None


def _require_sidecar(
    repository: _RepositoryCapability,
    relative_path: Path,
    expected_sha256: str,
) -> None:
    sidecar = relative_path.with_name(f"{relative_path.name}.sha256")
    source = _read_repository_regular_file(
        repository,
        sidecar,
        "FROZEN_INPUT_INVALID",
    )
    if source != f"{expected_sha256}\n".encode("ascii"):
        raise MetadataRunError("FROZEN_INPUT_INVALID")


def _load_canonical_object(source: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except MetadataRunError:
        raise
    except Exception:
        raise MetadataRunError("FROZEN_INPUT_INVALID") from None
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise MetadataRunError("FROZEN_INPUT_INVALID")
    return MappingProxyType(value)


def _unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, nested in pairs:
        if key in value:
            raise MetadataRunError("FROZEN_INPUT_INVALID")
        value[key] = nested
    return value


def _reject_json_constant(value: str) -> NoReturn:
    del value
    raise MetadataRunError("FROZEN_INPUT_INVALID")


def _require_sha256(value: object) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise MetadataRunError("INPUT_HASH_INVALID")


def _parse_strict_utc_timestamp(
    value: object,
    error_code: str,
) -> datetime:
    if (
        not isinstance(value, str)
        or _STRICT_UTC_TIMESTAMP_PATTERN.fullmatch(value) is None
    ):
        raise MetadataRunError(error_code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise MetadataRunError(error_code) from None
    return parsed.replace(tzinfo=timezone.utc)


@contextmanager
def _exclusive_output_run_lock(
    repository: _RepositoryCapability,
    output: _PinnedDirectory,
    run_id: str,
) -> Iterator[_HeldNamespaceLock]:
    repository.verify()
    _assert_pinned_directory(output)
    try:
        lock_directory_descriptor = _open_child_directory(
            output.descriptor,
            _RUN_LOCK_DIRECTORY_NAME,
            create=True,
            error_code="OUTPUT_LOCK_UNAVAILABLE",
        )
        lock_parent = _PinnedDirectory(
            repository=repository,
            path=output.path / _RUN_LOCK_DIRECTORY_NAME,
            descriptor=lock_directory_descriptor,
            identity=_directory_identity(os.fstat(lock_directory_descriptor)),
        )
    except BaseException:
        raise
    lock_digest = hashlib.sha256(
        f"{output.path.as_posix()}\0{run_id}".encode("utf-8")
    ).hexdigest()
    lock_name = f"{lock_digest}.lock"
    try:
        lock_descriptor = _open_real_lock_file(
            lock_directory_descriptor,
            lock_name,
            "OUTPUT_LOCK_UNAVAILABLE",
        )
    except BaseException:
        os.close(lock_directory_descriptor)
        raise
    try:
        _acquire_exclusive_lock(lock_descriptor, "OUTPUT_LOCK_UNAVAILABLE")
    except BaseException:
        os.close(lock_descriptor)
        os.close(lock_directory_descriptor)
        raise
    held = _HeldNamespaceLock(
        directory=output,
        lock_parent=lock_parent,
        lock_file=_PinnedFile(
            parent_descriptor=lock_directory_descriptor,
            name=lock_name,
            descriptor=lock_descriptor,
            identity=_directory_identity(os.fstat(lock_descriptor)),
        ),
    )
    try:
        held.verify()
        yield held
    finally:
        try:
            held.verify()
        finally:
            os.close(lock_descriptor)
            os.close(lock_directory_descriptor)


@contextmanager
def _exclusive_ledger_lock(
    repository: _RepositoryCapability,
    ledger: _PinnedDirectory,
) -> Iterator[_HeldNamespaceLock]:
    repository.verify()
    _assert_pinned_directory(ledger)
    try:
        _acquire_exclusive_lock(
            ledger.descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
    except BaseException:
        raise
    try:
        lock_descriptor = _open_real_lock_file(
            ledger.descriptor,
            _LOCK_FILENAME,
            "LEDGER_LOCK_UNAVAILABLE",
        )
    except BaseException:
        _release_exclusive_lock(
            ledger.descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        raise
    try:
        _acquire_exclusive_lock(lock_descriptor, "LEDGER_LOCK_UNAVAILABLE")
    except BaseException:
        os.close(lock_descriptor)
        _release_exclusive_lock(
            ledger.descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        raise
    held = _HeldNamespaceLock(
        directory=ledger,
        lock_file=_PinnedFile(
            parent_descriptor=ledger.descriptor,
            name=_LOCK_FILENAME,
            descriptor=lock_descriptor,
            identity=_directory_identity(os.fstat(lock_descriptor)),
        ),
    )
    try:
        held.verify()
        yield held
    finally:
        try:
            held.verify()
        finally:
            os.close(lock_descriptor)
            _release_exclusive_lock(
                ledger.descriptor,
                "LEDGER_LOCK_UNAVAILABLE",
            )


def _open_repository_directory(
    repository: _RepositoryCapability,
    target: Path,
    *,
    create: bool,
    error_code: str,
) -> int:
    try:
        relative = target.relative_to(repository.path)
    except ValueError:
        raise MetadataRunError(error_code) from None
    try:
        repository.verify()
        descriptor = os.dup(repository.descriptor)
    except OSError:
        raise MetadataRunError(error_code) from None
    try:
        for part in relative.parts:
            child_descriptor = _open_child_directory(
                descriptor,
                part,
                create=create,
                error_code=error_code,
            )
            os.close(descriptor)
            descriptor = child_descriptor
        repository.verify()
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _pin_repository_directory(
    repository: _RepositoryCapability,
    target: Path,
    *,
    create: bool,
    error_code: str,
) -> _PinnedDirectory:
    descriptor = _open_repository_directory(
        repository,
        target,
        create=create,
        error_code=error_code,
    )
    pinned = _PinnedDirectory(
        repository=repository,
        path=target,
        descriptor=descriptor,
        identity=_directory_identity(os.fstat(descriptor)),
    )
    try:
        _assert_pinned_directory(pinned)
    except BaseException:
        os.close(descriptor)
        raise
    return pinned


def _open_child_directory(
    parent_descriptor: int,
    name: str,
    *,
    create: bool,
    error_code: str,
) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        except OSError:
            raise MetadataRunError(error_code) from None
    try:
        path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        raise MetadataRunError(error_code) from None
    if not stat.S_ISDIR(path_metadata.st_mode):
        raise MetadataRunError(error_code)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened_metadata = os.fstat(descriptor)
    except OSError:
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISDIR(opened_metadata.st_mode)
        or opened_metadata.st_dev != path_metadata.st_dev
        or opened_metadata.st_ino != path_metadata.st_ino
    ):
        os.close(descriptor)
        raise MetadataRunError(error_code)
    return descriptor


def _open_regular_file_at(
    parent_descriptor: int,
    name: str,
    *,
    error_code: str,
    required_mode: int | None = None,
) -> tuple[int, _DirectoryIdentity]:
    try:
        path_metadata = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISREG(path_metadata.st_mode)
        or (
            required_mode is not None
            and stat.S_IMODE(path_metadata.st_mode) != required_mode
        )
    ):
        raise MetadataRunError(error_code)
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened_metadata = os.fstat(descriptor)
    except OSError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISREG(opened_metadata.st_mode)
        or _directory_identity(opened_metadata)
        != _directory_identity(path_metadata)
        or (
            required_mode is not None
            and stat.S_IMODE(opened_metadata.st_mode) != required_mode
        )
    ):
        os.close(descriptor)
        raise MetadataRunError(error_code)
    return descriptor, _directory_identity(opened_metadata)


def _open_real_lock_file(
    directory_descriptor: int,
    name: str,
    error_code: str,
) -> int:
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        try:
            descriptor = os.open(
                name,
                flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_descriptor,
            )
            created = True
        except FileExistsError:
            descriptor = os.open(name, flags, dir_fd=directory_descriptor)
        if created:
            os.fchmod(descriptor, 0o600)
        opened_metadata = os.fstat(descriptor)
        path_metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise MetadataRunError(error_code) from None
    if (
        not stat.S_ISREG(opened_metadata.st_mode)
        or not stat.S_ISREG(path_metadata.st_mode)
        or opened_metadata.st_dev != path_metadata.st_dev
        or opened_metadata.st_ino != path_metadata.st_ino
        or stat.S_IMODE(opened_metadata.st_mode) != 0o600
    ):
        os.close(descriptor)
        raise MetadataRunError(error_code)
    return descriptor


def _acquire_exclusive_lock(descriptor: int, error_code: str) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError:
        raise MetadataRunError(error_code) from None


def _release_exclusive_lock(descriptor: int, error_code: str) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        raise MetadataRunError(error_code) from None


def _binding_body(
    binding: LocalArtifactBinding,
    repository_root: Path,
) -> dict[str, object]:
    return {
        "path": _relative_path(binding.path, repository_root),
        "sha256": binding.artifact_sha256,
    }


def _utc_timestamp(clock: Clock) -> str:
    try:
        value = clock()
    except Exception:
        raise MetadataRunError("CLOCK_INVALID") from None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MetadataRunError("CLOCK_INVALID")
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _safe_evidence_timestamp(clock: Clock) -> str:
    try:
        return _utc_timestamp(clock)
    except BaseException:
        normalized = datetime.now(timezone.utc).replace(microsecond=0)
        return normalized.isoformat().replace("+00:00", "Z")


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def _safe_run_id(value: str) -> str:
    return value if _RUN_ID_PATTERN.fullmatch(value) is not None else "unavailable"


def _write_summary(stream: TextIO, summary: MetadataRunSummary) -> None:
    body: dict[str, object] = {
        "runId": summary.run_id,
        "status": summary.status,
        "count": summary.record_count,
        "selectedSymbols": list(summary.selected_symbols),
        "artifactHashes": dict(summary.artifact_hashes),
    }
    stream.write(canonical_json_bytes(body).decode("utf-8") + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
