"""Immutable storage for the official two-file US instrument directory."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import zstandard

from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.us_instrument_directory import (
    CollectedUsInstrumentDirectory,
    DirectoryInstrument,
    UsInstrumentDirectory,
    parse_us_instrument_directory,
)


_SCHEMA_VERSION = "rp001-s2-official-us-instrument-directory-archive.v1"
_IDENTITY_DOMAIN = "rp001_s2.official_us_instrument_directory_archive"
_MASTER_SCHEMA_VERSION = "rp001-s2-official-us-instrument-master.v1"
_MINIMUM_FREE_BYTES = 50 * 1024**3
_NASDAQ_ENDPOINT = "nasdaq_listed_symbol_directory"
_OTHER_ENDPOINT = "other_listed_symbol_directory"
_NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_NASDAQ_RAW_PATH = Path("raw/nasdaqlisted.txt.zst")
_OTHER_RAW_PATH = Path("raw/otherlisted.txt.zst")
_MASTER_PATH = Path("instrument-master.json")
_MASTER_SHA256_PATH = Path("instrument-master.json.sha256")
_MANIFEST_PATH = Path("manifest.json")
_MANIFEST_SHA256_PATH = Path("manifest.json.sha256")
_EXPECTED_ARTIFACT_PATHS = frozenset(
    {
        _NASDAQ_RAW_PATH,
        _OTHER_RAW_PATH,
        _MASTER_PATH,
        _MASTER_SHA256_PATH,
        _MANIFEST_PATH,
        _MANIFEST_SHA256_PATH,
    }
)
_MAX_RAW_BODY_BYTES = 16 * 1024 * 1024

FreeBytes = Callable[[Path], int]


class InstrumentDirectoryStorageError(ValueError):
    """Stable immutable-storage failure with no cleanup side effects."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredInstrumentDirectory:
    content_identity: str
    archive_directory: Path
    nasdaq_raw_path: Path
    other_raw_path: Path
    master_path: Path
    master_sha256_path: Path
    manifest_path: Path
    manifest_sha256_path: Path
    master_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class _ValidatedInput:
    collection: CollectedUsInstrumentDirectory
    nasdaq_capture: RawHttpCapture
    other_capture: RawHttpCapture
    nasdaq_body: bytes
    other_body: bytes


class ImmutableInstrumentDirectoryStorage:
    """Write and verify one content-addressed official directory snapshot."""

    def __init__(
        self,
        root: Path,
        *,
        free_bytes: FreeBytes | None = None,
    ) -> None:
        root_identity = _private_root_identity(root)
        self._root = root
        self._root_identity = root_identity
        self._free_bytes = free_bytes or _disk_free_bytes

    def write_collection(
        self,
        collection: CollectedUsInstrumentDirectory,
    ) -> StoredInstrumentDirectory:
        validated = _validate_collection(collection)
        content_identity = _content_identity(
            validated.nasdaq_capture.body_sha256,
            validated.other_capture.body_sha256,
        )
        archive_directory = self._root / content_identity
        self._require_root()
        try:
            archive_directory.mkdir(mode=0o700)
            (archive_directory / "raw").mkdir(mode=0o700)
        except FileExistsError:
            raise InstrumentDirectoryStorageError(
                "directory_archive_already_exists"
            ) from None
        except OSError:
            raise InstrumentDirectoryStorageError(
                "directory_archive_write_failed"
            ) from None

        compressor = zstandard.ZstdCompressor(level=9)
        nasdaq_compressed = compressor.compress(validated.nasdaq_body)
        other_compressed = compressor.compress(validated.other_body)
        nasdaq_raw_path = archive_directory / _NASDAQ_RAW_PATH
        other_raw_path = archive_directory / _OTHER_RAW_PATH
        self._write_new(nasdaq_raw_path, nasdaq_compressed)
        self._write_new(other_raw_path, other_compressed)

        lineage = _raw_lineage(validated)
        master_body = _master_body(validated.collection.directory, lineage)
        master_bytes = _canonical_json_bytes(master_body)
        master_sha256 = hashlib.sha256(master_bytes).hexdigest()
        master_path = archive_directory / _MASTER_PATH
        master_sha256_path = archive_directory / _MASTER_SHA256_PATH
        self._write_new(master_path, master_bytes)
        self._write_new(
            master_sha256_path,
            _sidecar_bytes(master_sha256),
        )

        manifest_body = _manifest_body(
            content_identity=content_identity,
            validated=validated,
            nasdaq_compressed=nasdaq_compressed,
            other_compressed=other_compressed,
            master_bytes=master_bytes,
            master_sha256=master_sha256,
        )
        manifest_bytes = _canonical_json_bytes(manifest_body)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = archive_directory / _MANIFEST_PATH
        manifest_sha256_path = archive_directory / _MANIFEST_SHA256_PATH
        self._write_new(manifest_path, manifest_bytes)
        self._write_new(
            manifest_sha256_path,
            _sidecar_bytes(manifest_sha256),
        )
        return StoredInstrumentDirectory(
            content_identity=content_identity,
            archive_directory=archive_directory,
            nasdaq_raw_path=nasdaq_raw_path,
            other_raw_path=other_raw_path,
            master_path=master_path,
            master_sha256_path=master_sha256_path,
            manifest_path=manifest_path,
            manifest_sha256_path=manifest_sha256_path,
            master_sha256=master_sha256,
            manifest_sha256=manifest_sha256,
        )

    def verify_archive(self, stored: StoredInstrumentDirectory) -> None:
        try:
            self._verify_archive(stored)
        except Exception:
            raise InstrumentDirectoryStorageError(
                "directory_archive_verification_failed"
            ) from None

    def _verify_archive(self, stored: StoredInstrumentDirectory) -> None:
        self._require_root()
        if not isinstance(stored, StoredInstrumentDirectory):
            raise ValueError
        archive_directory = self._root / stored.content_identity
        expected_paths = {
            "archive_directory": archive_directory,
            "nasdaq_raw_path": archive_directory / _NASDAQ_RAW_PATH,
            "other_raw_path": archive_directory / _OTHER_RAW_PATH,
            "master_path": archive_directory / _MASTER_PATH,
            "master_sha256_path": archive_directory / _MASTER_SHA256_PATH,
            "manifest_path": archive_directory / _MANIFEST_PATH,
            "manifest_sha256_path": archive_directory / _MANIFEST_SHA256_PATH,
        }
        if any(getattr(stored, name) != path for name, path in expected_paths.items()):
            raise ValueError
        _require_real_directory(archive_directory)
        _require_real_directory(archive_directory / "raw")
        actual_artifacts = frozenset(
            path.relative_to(archive_directory)
            for path in archive_directory.rglob("*")
            if path.is_file() or path.is_symlink()
        )
        if actual_artifacts != _EXPECTED_ARTIFACT_PATHS:
            raise ValueError
        for relative_path in _EXPECTED_ARTIFACT_PATHS:
            _require_regular_private_file(archive_directory / relative_path)

        master_bytes = stored.master_path.read_bytes()
        manifest_bytes = stored.manifest_path.read_bytes()
        if (
            hashlib.sha256(master_bytes).hexdigest() != stored.master_sha256
            or hashlib.sha256(manifest_bytes).hexdigest() != stored.manifest_sha256
            or stored.master_sha256_path.read_bytes()
            != _sidecar_bytes(stored.master_sha256)
            or stored.manifest_sha256_path.read_bytes()
            != _sidecar_bytes(stored.manifest_sha256)
        ):
            raise ValueError
        master = _load_canonical_json(master_bytes)
        manifest = _load_canonical_json(manifest_bytes)

        raw_artifacts = manifest.get("rawArtifacts")
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != 2:
            raise ValueError
        nasdaq_metadata, other_metadata = raw_artifacts
        nasdaq_body = _verify_raw_artifact(
            stored.nasdaq_raw_path,
            nasdaq_metadata,
            "nasdaqlisted",
            _NASDAQ_RAW_PATH,
        )
        other_body = _verify_raw_artifact(
            stored.other_raw_path,
            other_metadata,
            "otherlisted",
            _OTHER_RAW_PATH,
        )
        derived_identity = _content_identity(
            hashlib.sha256(nasdaq_body).hexdigest(),
            hashlib.sha256(other_body).hexdigest(),
        )
        if derived_identity != stored.content_identity:
            raise ValueError
        directory = parse_us_instrument_directory(nasdaq_body, other_body)
        lineage = {
            "nasdaqlisted": _lineage_from_manifest(nasdaq_metadata),
            "otherlisted": _lineage_from_manifest(other_metadata),
        }
        expected_master_bytes = _canonical_json_bytes(
            _master_body(directory, lineage)
        )
        if master_bytes != expected_master_bytes:
            raise ValueError
        expected_manifest = _manifest_from_verified_artifacts(
            content_identity=derived_identity,
            nasdaq_metadata=nasdaq_metadata,
            other_metadata=other_metadata,
            master_bytes=master_bytes,
            master_sha256=stored.master_sha256,
        )
        if manifest != expected_manifest:
            raise ValueError

    def _write_new(self, path: Path, body: bytes) -> None:
        self._require_capacity()
        try:
            with path.open("xb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                destination.write(body)
        except FileExistsError:
            raise InstrumentDirectoryStorageError(
                "directory_archive_already_exists"
            ) from None
        except OSError:
            raise InstrumentDirectoryStorageError(
                "directory_archive_write_failed"
            ) from None

    def _require_capacity(self) -> None:
        self._require_root()
        try:
            available = self._free_bytes(self._root)
        except Exception:
            raise InstrumentDirectoryStorageError(
                "blocked_storage_capacity"
            ) from None
        if type(available) is not int or available < _MINIMUM_FREE_BYTES:
            raise InstrumentDirectoryStorageError("blocked_storage_capacity")

    def _require_root(self) -> None:
        if _private_root_identity(self._root) != self._root_identity:
            raise InstrumentDirectoryStorageError(
                "directory_storage_root_invalid"
            )


def _validate_collection(value: object) -> _ValidatedInput:
    if (
        not isinstance(value, CollectedUsInstrumentDirectory)
        or type(value.captures) is not tuple
        or len(value.captures) != 2
        or not isinstance(value.directory, UsInstrumentDirectory)
    ):
        raise InstrumentDirectoryStorageError("directory_collection_invalid")
    nasdaq_capture, other_capture = value.captures
    nasdaq_body = _capture_body(
        nasdaq_capture,
        _NASDAQ_ENDPOINT,
        _NASDAQ_URL,
    )
    other_body = _capture_body(
        other_capture,
        _OTHER_ENDPOINT,
        _OTHER_URL,
    )
    try:
        parsed = parse_us_instrument_directory(nasdaq_body, other_body)
    except ValueError:
        raise InstrumentDirectoryStorageError("directory_collection_invalid") from None
    if parsed != value.directory:
        raise InstrumentDirectoryStorageError("directory_collection_invalid")
    return _ValidatedInput(
        collection=value,
        nasdaq_capture=nasdaq_capture,
        other_capture=other_capture,
        nasdaq_body=nasdaq_body,
        other_body=other_body,
    )


def _capture_body(
    capture: object,
    endpoint_id: str,
    url: str,
) -> bytes:
    if (
        not isinstance(capture, RawHttpCapture)
        or capture.endpoint_id != endpoint_id
        or capture.method != "GET"
        or capture.sanitized_url != url
        or capture.query != ()
        or capture.status != 200
        or not _canonical_received_at(capture.received_at)
    ):
        raise InstrumentDirectoryStorageError("directory_collection_invalid")
    try:
        body = base64.b64decode(capture.body_base64, validate=True)
    except Exception:
        raise InstrumentDirectoryStorageError("directory_collection_invalid") from None
    if (
        base64.b64encode(body).decode("ascii") != capture.body_base64
        or hashlib.sha256(body).hexdigest() != capture.body_sha256
    ):
        raise InstrumentDirectoryStorageError("directory_collection_invalid")
    return body


def _content_identity(nasdaq_sha256: str, other_sha256: str) -> str:
    body = {
        "identityDomain": _IDENTITY_DOMAIN,
        "rawBodySha256": {
            "nasdaqlisted": nasdaq_sha256,
            "otherlisted": other_sha256,
        },
        "schemaVersion": _SCHEMA_VERSION,
    }
    return hashlib.sha256(_canonical_json_bytes(body)).hexdigest()


def _raw_lineage(validated: _ValidatedInput) -> dict[str, dict[str, str]]:
    return {
        "nasdaqlisted": {
            "bodySha256": validated.nasdaq_capture.body_sha256,
            "endpointId": validated.nasdaq_capture.endpoint_id,
            "receivedAt": validated.nasdaq_capture.received_at,
        },
        "otherlisted": {
            "bodySha256": validated.other_capture.body_sha256,
            "endpointId": validated.other_capture.endpoint_id,
            "receivedAt": validated.other_capture.received_at,
        },
    }


def _master_body(
    directory: UsInstrumentDirectory,
    lineage: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    return {
        "eligibleSymbols": list(directory.eligible_symbols),
        "etfAssetClassStatus": directory.etf_asset_class_status,
        "fileCreationTimes": {
            "nasdaqlisted": directory.nasdaq_file_created_at,
            "otherlisted": directory.other_file_created_at,
        },
        "rawLineage": {
            name: dict(lineage[name])
            for name in ("nasdaqlisted", "otherlisted")
        },
        "records": [
            _record_body(record, lineage[record.source_directory]["bodySha256"])
            for record in directory.records
        ],
        "schemaVersion": _MASTER_SCHEMA_VERSION,
    }


def _record_body(
    record: DirectoryInstrument,
    raw_body_sha256: str,
) -> dict[str, object]:
    return {
        "eligibility": record.eligibility.value,
        "isEtf": record.is_etf,
        "isTestIssue": record.is_test_issue,
        "listingMarket": record.listing_market,
        "providerSymbol": record.provider_symbol,
        "rawBodySha256": raw_body_sha256,
        "securityName": record.security_name,
        "sourceDirectory": record.source_directory,
        "symbol": record.symbol,
    }


def _manifest_body(
    *,
    content_identity: str,
    validated: _ValidatedInput,
    nasdaq_compressed: bytes,
    other_compressed: bytes,
    master_bytes: bytes,
    master_sha256: str,
) -> dict[str, object]:
    raw_artifacts = [
        _raw_artifact_body(
            "nasdaqlisted",
            _NASDAQ_RAW_PATH,
            validated.nasdaq_capture,
            validated.nasdaq_body,
            nasdaq_compressed,
        ),
        _raw_artifact_body(
            "otherlisted",
            _OTHER_RAW_PATH,
            validated.other_capture,
            validated.other_body,
            other_compressed,
        ),
    ]
    return _manifest_structure(
        content_identity,
        raw_artifacts,
        len(master_bytes),
        master_sha256,
    )


def _raw_artifact_body(
    source_directory: str,
    relative_path: Path,
    capture: RawHttpCapture,
    raw_body: bytes,
    compressed: bytes,
) -> dict[str, object]:
    return {
        "compression": "ZSTD",
        "endpointId": capture.endpoint_id,
        "path": relative_path.as_posix(),
        "receivedAt": capture.received_at,
        "sourceDirectory": source_directory,
        "storedBytes": len(compressed),
        "storedSha256": hashlib.sha256(compressed).hexdigest(),
        "uncompressedBytes": len(raw_body),
        "uncompressedSha256": capture.body_sha256,
    }


def _manifest_structure(
    content_identity: str,
    raw_artifacts: list[dict[str, object]],
    master_bytes: int,
    master_sha256: str,
) -> dict[str, object]:
    return {
        "canonicalArtifact": {
            "bytes": master_bytes,
            "path": _MASTER_PATH.as_posix(),
            "sha256": master_sha256,
            "sidecarPath": _MASTER_SHA256_PATH.as_posix(),
        },
        "contentIdentity": content_identity,
        "identityDomain": _IDENTITY_DOMAIN,
        "rawArtifacts": raw_artifacts,
        "schemaVersion": _SCHEMA_VERSION,
    }


def _verify_raw_artifact(
    path: Path,
    metadata: object,
    source_directory: str,
    expected_path: Path,
) -> bytes:
    if not isinstance(metadata, dict):
        raise ValueError
    expected_fields = {
        "compression",
        "endpointId",
        "path",
        "receivedAt",
        "sourceDirectory",
        "storedBytes",
        "storedSha256",
        "uncompressedBytes",
        "uncompressedSha256",
    }
    if set(metadata) != expected_fields:
        raise ValueError
    compressed = path.read_bytes()
    if (
        metadata["compression"] != "ZSTD"
        or metadata["sourceDirectory"] != source_directory
        or metadata["path"] != expected_path.as_posix()
        or metadata["storedBytes"] != len(compressed)
        or metadata["storedSha256"] != hashlib.sha256(compressed).hexdigest()
        or not _canonical_received_at(metadata["receivedAt"])
    ):
        raise ValueError
    body = zstandard.ZstdDecompressor().decompress(
        compressed,
        max_output_size=_MAX_RAW_BODY_BYTES,
    )
    if (
        metadata["uncompressedBytes"] != len(body)
        or metadata["uncompressedSha256"] != hashlib.sha256(body).hexdigest()
    ):
        raise ValueError
    return body


def _lineage_from_manifest(metadata: object) -> dict[str, str]:
    if not isinstance(metadata, dict):
        raise ValueError
    return {
        "bodySha256": str(metadata["uncompressedSha256"]),
        "endpointId": str(metadata["endpointId"]),
        "receivedAt": str(metadata["receivedAt"]),
    }


def _manifest_from_verified_artifacts(
    *,
    content_identity: str,
    nasdaq_metadata: object,
    other_metadata: object,
    master_bytes: bytes,
    master_sha256: str,
) -> dict[str, object]:
    if not isinstance(nasdaq_metadata, dict) or not isinstance(
        other_metadata,
        dict,
    ):
        raise ValueError
    return _manifest_structure(
        content_identity,
        [nasdaq_metadata, other_metadata],
        len(master_bytes),
        master_sha256,
    )


def _load_canonical_json(body: bytes) -> dict[str, object]:
    value = json.loads(body)
    if not isinstance(value, dict) or _canonical_json_bytes(value) != body:
        raise ValueError
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sidecar_bytes(sha256: str) -> bytes:
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise ValueError
    return f"{sha256}\n".encode("ascii")


def _canonical_received_at(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except (ValueError, TypeError, OverflowError):
        return False
    return (
        parsed.tzinfo is not None
        and parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00",
            "Z",
        )
        == value
    )


def _private_root_identity(root: object) -> tuple[int, int]:
    if not isinstance(root, Path):
        raise InstrumentDirectoryStorageError("directory_storage_root_invalid")
    try:
        root_stat = root.lstat()
    except OSError:
        raise InstrumentDirectoryStorageError(
            "directory_storage_root_invalid"
        ) from None
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or stat.S_IMODE(root_stat.st_mode) & 0o077
    ):
        raise InstrumentDirectoryStorageError("directory_storage_root_invalid")
    return root_stat.st_dev, root_stat.st_ino


def _require_real_directory(path: Path) -> None:
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ValueError


def _require_regular_private_file(path: Path) -> None:
    value = path.lstat()
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or stat.S_IMODE(value.st_mode) & 0o077
    ):
        raise ValueError


def _disk_free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free
