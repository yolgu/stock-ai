"""Immutable, lossless storage for direction-neutral minute archives."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import duckdb
import pyarrow as pa
import pyarrow.parquet as parquet
import zstandard

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import (
    CollectionScope,
    ResearchDataKind,
    ResearchViewAccess,
)


_MINIMUM_FREE_BYTES: int = 50 * 1024**3
_SCHEMA_VERSION_V1: str = "rp001-s2-immutable-minute-archive.v1"
_SCHEMA_VERSION_V2: str = "rp001-s2-immutable-minute-archive.v2"
_FAILURE_EVIDENCE_SCHEMA_VERSION: str = (
    "rp001-s2-immutable-minute-failure-evidence.v1"
)
_FAILURE_EVIDENCE_DOMAIN: str = "rp001_s2.immutable_minute_failure_evidence"
_CANONICAL_RELATIVE_PATH: Path = Path("canonical/minute-bars.parquet")
_OCCURRENCE_RELATIVE_PATH: Path = Path("canonical/minute-bar-occurrences.parquet")
_CANONICAL_COLUMNS: tuple[str, ...] = (
    "provider",
    "feed",
    "instrument_id",
    "symbol",
    "source_timestamp",
    "event_start_utc",
    "bar_end_utc",
    "received_at_utc",
    "research_available_at_utc",
    "session_date",
    "session_type",
    "currency",
    "adjustment_mode",
    "numeric_fidelity",
    "quality_status",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "raw_body_sha256",
    "capture_ordinal",
    "source_row_index",
)
_BAR_VIEW_NAME: str = "canonical_minute_bars"
_OCCURRENCE_VIEW_NAME: str = "canonical_minute_bar_occurrences"
_OCCURRENCE_COLUMNS: tuple[str, ...] = (
    "event_start_utc",
    "raw_body_sha256",
    "capture_ordinal",
    "source_row_index",
    "occurrence_order",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UNSIGNED_DECIMAL_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_JSON_NONNEGATIVE_NUMBER_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)
_HTTP_METHOD_PATTERN = re.compile(r"^[A-Z]+$")
_STABLE_ERROR_CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_JSON_NUMBER_FIDELITY: str = "json_number_lexeme"
_DECIMAL_STRING_FIDELITY: str = "decimal_string_lexeme"
_FORBIDDEN_IDENTIFIER_CATEGORIES: frozenset[str] = frozenset({"Cc", "Cf"})
_ALLOWED_CAPTURE_HEADERS: frozenset[str] = frozenset(
    {
        "content-type",
        "etag",
        "last-modified",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)

FreeBytes = Callable[[Path], int]


class ArchiveStorageError(ValueError):
    """Stable storage failure that never deletes or samples evidence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AcquisitionTerminalStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    DATA_UNAVAILABLE = "data_unavailable"
    FAILED = "failed"
    INVALID = "invalid"


@dataclass(frozen=True)
class AcquisitionCompletion:
    requested_start_reached: bool
    completion_reason: str
    terminal_status: AcquisitionTerminalStatus
    analysis_row_count: int
    audit_row_count: int
    returned_row_count: int

    def __post_init__(self) -> None:
        counts = (
            self.analysis_row_count,
            self.audit_row_count,
            self.returned_row_count,
        )
        if (
            type(self.requested_start_reached) is not bool
            or type(self.completion_reason) is not str
            or not self.completion_reason
            or self.completion_reason != self.completion_reason.strip()
            or not isinstance(self.terminal_status, AcquisitionTerminalStatus)
            or any(type(count) is not int or count < 0 for count in counts)
            or self.returned_row_count
            != self.analysis_row_count + self.audit_row_count
        ):
            raise ArchiveStorageError("acquisition_completion_invalid")
        if self.terminal_status is AcquisitionTerminalStatus.COMPLETED:
            valid_terminal = (
                self.requested_start_reached
                and self.completion_reason != "provider_terminal_before_start"
            )
        elif self.terminal_status is AcquisitionTerminalStatus.PARTIAL:
            valid_terminal = (
                not self.requested_start_reached
                and self.completion_reason == "provider_terminal_before_start"
                and self.returned_row_count > 0
            )
        elif self.terminal_status is AcquisitionTerminalStatus.DATA_UNAVAILABLE:
            valid_terminal = (
                not self.requested_start_reached
                and self.completion_reason
                in {"data_unavailable", "empty_provider_terminal"}
                and self.returned_row_count == 0
            )
        else:
            valid_terminal = (
                not self.requested_start_reached
                and _STABLE_ERROR_CODE_PATTERN.fullmatch(self.completion_reason)
                is not None
                and self.returned_row_count == 0
            )
        if not valid_terminal:
            raise ArchiveStorageError("acquisition_completion_invalid")

    def to_canonical_body(self) -> dict[str, object]:
        return {
            "requestedStartReached": self.requested_start_reached,
            "completionReason": self.completion_reason,
            "terminalStatus": self.terminal_status.value,
            "analysisRowCount": self.analysis_row_count,
            "auditRowCount": self.audit_row_count,
            "returnedRowCount": self.returned_row_count,
        }


@dataclass(frozen=True)
class CanonicalMinuteBar:
    """Cross-provider canonical minute observation with immutable raw lineage."""

    provider: str
    feed: str
    instrument_id: str
    symbol: str
    source_timestamp: str
    event_start_utc: str
    bar_end_utc: str
    received_at_utc: str
    research_available_at_utc: str
    session_date: str
    session_type: str
    currency: str
    adjustment_mode: str
    numeric_fidelity: str
    quality_status: str
    open_price: CanonicalScalar
    high_price: CanonicalScalar
    low_price: CanonicalScalar
    close_price: CanonicalScalar
    volume: CanonicalScalar
    raw_body_sha256: str
    capture_ordinal: int
    source_row_index: int
    occurrences: tuple[tuple[str, int, int], ...]

    def __post_init__(self) -> None:
        identifiers = (
            self.provider,
            self.feed,
            self.instrument_id,
            self.symbol,
            self.session_type,
            self.currency,
            self.adjustment_mode,
            self.numeric_fidelity,
            self.quality_status,
        )
        if any(not _is_canonical_identifier(value) for value in identifiers):
            raise ArchiveStorageError("canonical_minute_bar_invalid")
        source = _parse_source_timestamp(self.source_timestamp)
        event_start = _parse_canonical_utc(self.event_start_utc, minute_grid=True)
        bar_end = _parse_canonical_utc(self.bar_end_utc, minute_grid=True)
        received = _parse_canonical_utc(self.received_at_utc, minute_grid=False)
        available = _parse_canonical_utc(
            self.research_available_at_utc,
            minute_grid=False,
        )
        if (
            source != event_start
            or bar_end != event_start + timedelta(minutes=1)
            or available < bar_end
            or available < received
            or not _is_canonical_date(self.session_date)
        ):
            raise ArchiveStorageError("canonical_minute_bar_invalid")
        open_price = _price_decimal(self.open_price, self.numeric_fidelity)
        high_price = _price_decimal(self.high_price, self.numeric_fidelity)
        low_price = _price_decimal(self.low_price, self.numeric_fidelity)
        close_price = _price_decimal(self.close_price, self.numeric_fidelity)
        _volume_decimal(self.volume, self.numeric_fidelity)
        if (
            low_price > high_price
            or not low_price <= open_price <= high_price
            or not low_price <= close_price <= high_price
        ):
            raise ArchiveStorageError("canonical_minute_bar_invalid")
        if (
            _SHA256_PATTERN.fullmatch(self.raw_body_sha256) is None
            or type(self.capture_ordinal) is not int
            or self.capture_ordinal < 0
            or type(self.source_row_index) is not int
            or self.source_row_index < 0
        ):
            raise ArchiveStorageError("canonical_minute_bar_invalid")
        if not _valid_occurrence_identity(
            self.occurrences,
            (self.raw_body_sha256, self.capture_ordinal, self.source_row_index),
        ):
            raise ArchiveStorageError("canonical_minute_bar_invalid")


@dataclass(frozen=True)
class StoredArchive:
    acquisition_key: str
    archive_directory: Path
    raw_paths: tuple[Path, ...]
    canonical_path: Path
    occurrence_path: Path
    manifest_path: Path
    manifest_sha256_path: Path


@dataclass(frozen=True)
class StoredFailureEvidence:
    acquisition_key: str
    evidence_digest: str
    evidence_directory: Path
    raw_paths: tuple[Path, ...]
    canonical_path: Path
    occurrence_path: Path
    manifest_path: Path
    manifest_sha256_path: Path

    @property
    def archive_directory(self) -> Path:
        return self.evidence_directory


class ArchiveViews:
    """Policy-checked DuckDB views over one verified immutable archive."""

    def __init__(
        self,
        *,
        canonical_path: Path,
        occurrence_path: Path,
        manifest: dict[str, object],
        access: ResearchViewAccess,
    ) -> None:
        self._manifest = manifest
        self._access = access
        self._connection = duckdb.connect(database=":memory:")
        self._connection.read_parquet(str(canonical_path)).create_view(_BAR_VIEW_NAME)
        self._connection.read_parquet(str(occurrence_path)).create_view(
            _OCCURRENCE_VIEW_NAME
        )

    def __enter__(self) -> ArchiveViews:
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        del exception_type, exception, traceback
        self.close()

    def close(self) -> None:
        self._connection.close()

    def query(
        self,
        data_kind: ResearchDataKind,
    ) -> tuple[tuple[object, ...], ...]:
        self._access.require_read(data_kind)
        if data_kind is ResearchDataKind.RAW_ARCHIVE_METADATA:
            return self._raw_metadata_rows()
        if data_kind is ResearchDataKind.RAW_ARCHIVE_HASH:
            return self._raw_hash_rows()
        if data_kind is ResearchDataKind.RAW_ARCHIVE_ROW_COUNT:
            occurrence = self._manifest["occurrenceArtifact"]
            if not isinstance(occurrence, dict):
                raise ArchiveStorageError("archive_query_failed")
            return ((occurrence["rowCount"],),)
        if data_kind is ResearchDataKind.BAR_VALUES:
            rows = self._connection.execute(
                f"SELECT {', '.join(_CANONICAL_COLUMNS)} "
                f"FROM {_BAR_VIEW_NAME} "
                "ORDER BY event_start_utc, capture_ordinal, source_row_index"
            ).fetchall()
            return tuple(tuple(row) for row in rows)
        return ()

    def query_bar_occurrences(self) -> tuple[tuple[object, ...], ...]:
        self._access.require_read(ResearchDataKind.BAR_VALUES)
        rows = self._connection.execute(
            f"SELECT {', '.join(_OCCURRENCE_COLUMNS)} "
            f"FROM {_OCCURRENCE_VIEW_NAME} "
            "ORDER BY event_start_utc, occurrence_order"
        ).fetchall()
        return tuple(tuple(row) for row in rows)

    def _raw_metadata_rows(self) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                artifact["captureOrdinal"],
                artifact["endpointId"],
                artifact["receivedAt"],
                artifact["status"],
                artifact["path"],
            )
            for artifact in self._raw_artifacts()
        )

    def _raw_hash_rows(self) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                artifact["captureOrdinal"],
                artifact["uncompressedSha256"],
                artifact["storedSha256"],
            )
            for artifact in self._raw_artifacts()
        )

    def _raw_artifacts(self) -> tuple[dict[str, object], ...]:
        artifacts = self._manifest["rawArtifacts"]
        if not isinstance(artifacts, list) or any(
            not isinstance(artifact, dict) for artifact in artifacts
        ):
            raise ArchiveStorageError("archive_query_failed")
        return tuple(artifacts)


class ImmutableArchiveStorage:
    """Write each acquisition identity once as raw, canonical, and manifest artifacts."""

    def __init__(
        self,
        root: Path,
        *,
        free_bytes: FreeBytes | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise ArchiveStorageError("archive_root_invalid")
        self._root = root
        self._free_bytes = free_bytes or _disk_free_bytes

    def write_archive(
        self,
        *,
        scope: CollectionScope,
        captures: tuple[RawHttpCapture, ...],
        rows: tuple[CanonicalMinuteBar, ...],
        completion: AcquisitionCompletion,
    ) -> StoredArchive:
        if not isinstance(scope, CollectionScope) or not isinstance(
            completion,
            AcquisitionCompletion,
        ):
            raise ArchiveStorageError("archive_input_invalid")
        raw_bodies = _decode_raw_captures(captures)
        capture_requests = tuple(
            _capture_request_body(capture) for capture in captures
        )
        _validate_bars(scope, rows, captures)
        if (
            completion.terminal_status
            in {
                AcquisitionTerminalStatus.FAILED,
                AcquisitionTerminalStatus.INVALID,
            }
            or completion.returned_row_count != len(rows)
        ):
            raise ArchiveStorageError("acquisition_completion_invalid")

        archive_directory = self._root / scope.acquisition_key
        self._require_capacity(self._root)
        try:
            archive_directory.mkdir()
            (archive_directory / "raw").mkdir()
            (archive_directory / "canonical").mkdir()
        except FileExistsError:
            raise ArchiveStorageError("archive_already_exists") from None
        except OSError:
            raise ArchiveStorageError("archive_write_failed") from None

        raw_artifacts: list[dict[str, object]] = []
        raw_paths: list[Path] = []
        compressor = zstandard.ZstdCompressor(level=9)
        for ordinal, (capture, raw_body, capture_request) in enumerate(
            zip(captures, raw_bodies, capture_requests, strict=True)
        ):
            relative_path = Path(f"raw/{ordinal:06d}.json.zst")
            raw_path = archive_directory / relative_path
            compressed = compressor.compress(raw_body)
            self._write_new_bytes(raw_path, compressed)
            raw_paths.append(raw_path)
            raw_artifacts.append(
                _raw_artifact_body(
                    ordinal,
                    relative_path,
                    capture,
                    capture_request,
                    raw_body,
                    compressed,
                )
            )

        canonical_path = archive_directory / _CANONICAL_RELATIVE_PATH
        table = _canonical_table(rows)
        self._write_new_parquet(canonical_path, table)
        canonical_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()

        occurrence_path = archive_directory / _OCCURRENCE_RELATIVE_PATH
        occurrence_table = _occurrence_table(rows)
        self._write_new_parquet(occurrence_path, occurrence_table)
        occurrence_sha256 = hashlib.sha256(occurrence_path.read_bytes()).hexdigest()

        manifest = {
            "schemaVersion": _SCHEMA_VERSION_V2,
            "acquisitionKey": scope.acquisition_key,
            "scope": scope.to_canonical_body(),
            "acquisitionCompletion": completion.to_canonical_body(),
            "rawArtifacts": raw_artifacts,
            "canonicalArtifact": {
                "compression": "ZSTD",
                "path": _CANONICAL_RELATIVE_PATH.as_posix(),
                "rowCount": len(rows),
                "sha256": canonical_sha256,
            },
            "occurrenceArtifact": {
                "compression": "ZSTD",
                "path": _OCCURRENCE_RELATIVE_PATH.as_posix(),
                "rowCount": occurrence_table.num_rows,
                "sha256": occurrence_sha256,
            },
        }
        manifest_path = archive_directory / "manifest.json"
        manifest_bytes = _canonical_json_bytes(manifest)
        self._write_new_bytes(manifest_path, manifest_bytes)
        manifest_sha256_path = archive_directory / "manifest.json.sha256"
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self._write_new_bytes(
            manifest_sha256_path,
            f"{manifest_sha256}\n".encode("ascii"),
        )
        return StoredArchive(
            acquisition_key=scope.acquisition_key,
            archive_directory=archive_directory,
            raw_paths=tuple(raw_paths),
            canonical_path=canonical_path,
            occurrence_path=occurrence_path,
            manifest_path=manifest_path,
            manifest_sha256_path=manifest_sha256_path,
        )

    def verify_archive(self, stored: StoredArchive) -> None:
        """Verify every immutable byte and canonical-row lineage binding."""
        try:
            self._verify_archive(stored)
        except Exception:
            raise ArchiveStorageError("archive_verification_failed") from None

    def write_failure_evidence(
        self,
        *,
        scope: CollectionScope,
        captures: tuple[RawHttpCapture, ...],
        completion: AcquisitionCompletion,
    ) -> StoredFailureEvidence:
        if (
            not isinstance(scope, CollectionScope)
            or not isinstance(completion, AcquisitionCompletion)
            or completion.terminal_status
            not in {
                AcquisitionTerminalStatus.FAILED,
                AcquisitionTerminalStatus.INVALID,
            }
        ):
            raise ArchiveStorageError("failure_evidence_invalid")
        raw_bodies = _decode_raw_captures(captures)
        capture_requests = tuple(
            _capture_request_body(capture) for capture in captures
        )
        evidence_digest = _failure_evidence_digest_from_captures(
            scope,
            captures,
            capture_requests,
            completion,
        )
        evidence_root = self._root / "failure-evidence" / scope.acquisition_key
        evidence_directory = evidence_root / evidence_digest
        stored = _stored_failure_evidence(
            scope.acquisition_key,
            evidence_digest,
            evidence_directory,
            len(captures),
        )
        if evidence_directory.exists():
            self.verify_failure_evidence(stored)
            return stored

        self._require_capacity(self._root)
        try:
            evidence_root.mkdir(parents=True, exist_ok=True)
            evidence_directory.mkdir()
            (evidence_directory / "raw").mkdir()
            (evidence_directory / "canonical").mkdir()
        except FileExistsError:
            self.verify_failure_evidence(stored)
            return stored
        except OSError:
            raise ArchiveStorageError("failure_evidence_write_failed") from None

        compressor = zstandard.ZstdCompressor(level=9)
        raw_artifacts: list[dict[str, object]] = []
        for ordinal, (capture, raw_body, capture_request) in enumerate(
            zip(captures, raw_bodies, capture_requests, strict=True)
        ):
            relative_path = Path(f"raw/{ordinal:06d}.json.zst")
            compressed = compressor.compress(raw_body)
            self._write_new_bytes(evidence_directory / relative_path, compressed)
            raw_artifacts.append(
                _raw_artifact_body(
                    ordinal,
                    relative_path,
                    capture,
                    capture_request,
                    raw_body,
                    compressed,
                )
            )

        canonical_table = _canonical_table(())
        self._write_new_parquet(stored.canonical_path, canonical_table)
        canonical_sha256 = hashlib.sha256(
            stored.canonical_path.read_bytes()
        ).hexdigest()
        occurrence_table = _occurrence_table(())
        self._write_new_parquet(stored.occurrence_path, occurrence_table)
        occurrence_sha256 = hashlib.sha256(
            stored.occurrence_path.read_bytes()
        ).hexdigest()
        manifest = {
            "schemaVersion": _FAILURE_EVIDENCE_SCHEMA_VERSION,
            "evidenceDigest": evidence_digest,
            "acquisitionKey": scope.acquisition_key,
            "scope": scope.to_canonical_body(),
            "acquisitionCompletion": completion.to_canonical_body(),
            "rawArtifacts": raw_artifacts,
            "canonicalArtifact": {
                "compression": "ZSTD",
                "path": _CANONICAL_RELATIVE_PATH.as_posix(),
                "rowCount": 0,
                "sha256": canonical_sha256,
            },
            "occurrenceArtifact": {
                "compression": "ZSTD",
                "path": _OCCURRENCE_RELATIVE_PATH.as_posix(),
                "rowCount": 0,
                "sha256": occurrence_sha256,
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        self._write_new_bytes(stored.manifest_path, manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        self._write_new_bytes(
            stored.manifest_sha256_path,
            f"{manifest_sha256}\n".encode("ascii"),
        )
        return stored

    def verify_failure_evidence(self, stored: StoredFailureEvidence) -> None:
        try:
            self._verify_failure_evidence(stored)
        except Exception:
            raise ArchiveStorageError(
                "failure_evidence_verification_failed"
            ) from None

    def _verify_failure_evidence(self, stored: StoredFailureEvidence) -> None:
        if not isinstance(stored, StoredFailureEvidence):
            raise ValueError
        expected_directory = (
            self._root
            / "failure-evidence"
            / stored.acquisition_key
            / stored.evidence_digest
        )
        if (
            stored.evidence_directory != expected_directory
            or stored.canonical_path
            != expected_directory / _CANONICAL_RELATIVE_PATH
            or stored.occurrence_path
            != expected_directory / _OCCURRENCE_RELATIVE_PATH
            or stored.manifest_path != expected_directory / "manifest.json"
            or stored.manifest_sha256_path
            != expected_directory / "manifest.json.sha256"
        ):
            raise ValueError
        expected_raw_paths = tuple(
            expected_directory / f"raw/{ordinal:06d}.json.zst"
            for ordinal in range(len(stored.raw_paths))
        )
        if stored.raw_paths != expected_raw_paths:
            raise ValueError

        manifest_bytes = stored.manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if stored.manifest_sha256_path.read_bytes() != f"{manifest_sha256}\n".encode(
            "ascii"
        ):
            raise ValueError
        manifest = json.loads(manifest_bytes)
        if manifest_bytes != _canonical_json_bytes(manifest):
            raise ValueError
        _validate_failure_evidence_manifest_identity(manifest, stored)
        raw_hashes = _verify_raw_artifacts(manifest, stored, _SCHEMA_VERSION_V2)
        primary_lineage = _verify_canonical_artifact(manifest, stored, raw_hashes)
        _verify_occurrence_artifact(manifest, stored, raw_hashes, primary_lineage)
        if primary_lineage:
            raise ValueError
        completion = _acquisition_completion_from_metadata(
            manifest["acquisitionCompletion"]
        )
        if completion.terminal_status not in {
            AcquisitionTerminalStatus.FAILED,
            AcquisitionTerminalStatus.INVALID,
        }:
            raise ValueError
        expected_digest = _failure_evidence_digest_from_manifest(manifest)
        if expected_digest != stored.evidence_digest:
            raise ValueError

    def load_resumable_completion(
        self,
        stored: StoredArchive,
    ) -> AcquisitionCompletion:
        self.verify_archive(stored)
        manifest = json.loads(stored.manifest_path.read_bytes())
        if _manifest_schema_version(manifest) != _SCHEMA_VERSION_V2:
            raise ArchiveStorageError("archive_not_resumable")
        try:
            return _acquisition_completion_from_metadata(
                manifest["acquisitionCompletion"]
            )
        except (ArchiveStorageError, KeyError, TypeError, ValueError):
            raise ArchiveStorageError("archive_not_resumable") from None

    def open_views(
        self,
        stored: StoredArchive,
        access: ResearchViewAccess,
    ) -> ArchiveViews:
        if not isinstance(access, ResearchViewAccess):
            raise ArchiveStorageError("research_view_invalid")
        self.verify_archive(stored)
        manifest = json.loads(stored.manifest_path.read_bytes())
        return ArchiveViews(
            canonical_path=stored.canonical_path,
            occurrence_path=stored.occurrence_path,
            manifest=manifest,
            access=access,
        )

    def _verify_archive(self, stored: StoredArchive) -> None:
        if not isinstance(stored, StoredArchive):
            raise ValueError
        expected_directory = self._root / stored.acquisition_key
        if (
            stored.archive_directory != expected_directory
            or stored.manifest_path != expected_directory / "manifest.json"
            or stored.manifest_sha256_path
            != expected_directory / "manifest.json.sha256"
            or stored.canonical_path != expected_directory / _CANONICAL_RELATIVE_PATH
            or stored.occurrence_path
            != expected_directory / _OCCURRENCE_RELATIVE_PATH
        ):
            raise ValueError

        manifest_bytes = stored.manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if stored.manifest_sha256_path.read_bytes() != f"{manifest_sha256}\n".encode(
            "ascii"
        ):
            raise ValueError
        manifest = json.loads(manifest_bytes)
        if manifest_bytes != _canonical_json_bytes(manifest):
            raise ValueError
        schema_version = _manifest_schema_version(manifest)
        _validate_manifest_identity(manifest, stored, schema_version)
        raw_hashes = _verify_raw_artifacts(manifest, stored, schema_version)
        primary_lineage = _verify_canonical_artifact(manifest, stored, raw_hashes)
        _verify_occurrence_artifact(manifest, stored, raw_hashes, primary_lineage)
        if schema_version == _SCHEMA_VERSION_V2:
            _verify_acquisition_completion(manifest, len(primary_lineage))

    def _write_new_bytes(self, path: Path, value: bytes) -> None:
        self._require_capacity(path.parent)
        try:
            with path.open("xb") as output:
                output.write(value)
        except FileExistsError:
            raise ArchiveStorageError("archive_already_exists") from None
        except OSError:
            raise ArchiveStorageError("archive_write_failed") from None

    def _write_new_parquet(self, path: Path, table: pa.Table) -> None:
        self._require_capacity(path.parent)
        try:
            with path.open("xb") as output:
                parquet.write_table(
                    table,
                    output,
                    compression="zstd",
                    use_dictionary=False,
                    write_statistics=True,
                )
        except FileExistsError:
            raise ArchiveStorageError("archive_already_exists") from None
        except (OSError, pa.ArrowException):
            raise ArchiveStorageError("archive_write_failed") from None

    def _require_capacity(self, path: Path) -> None:
        try:
            available = self._free_bytes(path)
        except Exception:
            raise ArchiveStorageError("blocked_storage_capacity") from None
        if type(available) is not int or available < _MINIMUM_FREE_BYTES:
            raise ArchiveStorageError("blocked_storage_capacity")


def _disk_free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _decode_raw_captures(captures: tuple[RawHttpCapture, ...]) -> tuple[bytes, ...]:
    if (
        type(captures) is not tuple
        or not captures
        or any(not isinstance(capture, RawHttpCapture) for capture in captures)
    ):
        raise ArchiveStorageError("archive_input_invalid")
    bodies: list[bytes] = []
    for capture in captures:
        try:
            body = base64.b64decode(capture.body_base64, validate=True)
        except (ValueError, TypeError):
            raise ArchiveStorageError("raw_capture_invalid") from None
        if hashlib.sha256(body).hexdigest() != capture.body_sha256:
            raise ArchiveStorageError("raw_capture_invalid")
        bodies.append(body)
    return tuple(bodies)


def _capture_request_body(capture: RawHttpCapture) -> dict[str, object]:
    if (
        type(capture.method) is not str
        or _HTTP_METHOD_PATTERN.fullmatch(capture.method) is None
        or type(capture.sanitized_url) is not str
        or not capture.sanitized_url
        or any(character in capture.sanitized_url for character in "\r\n\x00")
        or type(capture.query) is not tuple
        or type(capture.headers) is not tuple
        or type(capture.status) is not int
        or not 100 <= capture.status <= 599
        or not _is_canonical_identifier(capture.endpoint_id)
    ):
        raise ArchiveStorageError("raw_capture_invalid")
    query = _ordered_capture_pairs(capture.query)
    _require_sanitized_url_query(capture.sanitized_url, capture.query)
    headers = _ordered_capture_pairs(
        capture.headers,
        allowed_names=_ALLOWED_CAPTURE_HEADERS,
        unique_names=True,
    )
    try:
        _parse_canonical_utc(capture.received_at, minute_grid=False)
    except ArchiveStorageError:
        raise ArchiveStorageError("raw_capture_invalid") from None
    return {
        "method": capture.method,
        "sanitizedUrl": capture.sanitized_url,
        "query": query,
        "responseHeaders": headers,
    }


def _raw_artifact_body(
    ordinal: int,
    relative_path: Path,
    capture: RawHttpCapture,
    capture_request: dict[str, object],
    raw_body: bytes,
    compressed: bytes,
) -> dict[str, object]:
    return {
        "captureOrdinal": ordinal,
        "endpointId": capture.endpoint_id,
        **capture_request,
        "receivedAt": capture.received_at,
        "status": capture.status,
        "path": relative_path.as_posix(),
        "uncompressedBytes": len(raw_body),
        "uncompressedSha256": hashlib.sha256(raw_body).hexdigest(),
        "storedBytes": len(compressed),
        "storedSha256": hashlib.sha256(compressed).hexdigest(),
    }


def _failure_evidence_digest_from_captures(
    scope: CollectionScope,
    captures: tuple[RawHttpCapture, ...],
    capture_requests: tuple[dict[str, object], ...],
    completion: AcquisitionCompletion,
) -> str:
    raw_captures = [
        {
            "captureOrdinal": ordinal,
            "endpointId": capture.endpoint_id,
            **capture_request,
            "receivedAt": capture.received_at,
            "status": capture.status,
            "bodySha256": capture.body_sha256,
        }
        for ordinal, (capture, capture_request) in enumerate(
            zip(captures, capture_requests, strict=True)
        )
    ]
    return _failure_evidence_digest(
        scope.acquisition_key,
        scope.to_canonical_body(),
        completion.to_canonical_body(),
        raw_captures,
    )


def _failure_evidence_digest_from_manifest(manifest: dict[str, object]) -> str:
    raw_artifacts = manifest["rawArtifacts"]
    if not isinstance(raw_artifacts, list):
        raise ValueError
    raw_captures: list[dict[str, object]] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, dict):
            raise ValueError
        raw_captures.append(
            {
                "captureOrdinal": artifact["captureOrdinal"],
                "endpointId": artifact["endpointId"],
                "method": artifact["method"],
                "sanitizedUrl": artifact["sanitizedUrl"],
                "query": artifact["query"],
                "responseHeaders": artifact["responseHeaders"],
                "receivedAt": artifact["receivedAt"],
                "status": artifact["status"],
                "bodySha256": artifact["uncompressedSha256"],
            }
        )
    return _failure_evidence_digest(
        manifest["acquisitionKey"],
        manifest["scope"],
        manifest["acquisitionCompletion"],
        raw_captures,
    )


def _failure_evidence_digest(
    acquisition_key: object,
    scope: object,
    completion: object,
    raw_captures: object,
) -> str:
    identity = {
        "schemaVersion": _FAILURE_EVIDENCE_SCHEMA_VERSION,
        "identityDomain": _FAILURE_EVIDENCE_DOMAIN,
        "acquisitionKey": acquisition_key,
        "scope": scope,
        "acquisitionCompletion": completion,
        "rawCaptures": raw_captures,
    }
    return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def _stored_failure_evidence(
    acquisition_key: str,
    evidence_digest: str,
    evidence_directory: Path,
    capture_count: int,
) -> StoredFailureEvidence:
    return StoredFailureEvidence(
        acquisition_key=acquisition_key,
        evidence_digest=evidence_digest,
        evidence_directory=evidence_directory,
        raw_paths=tuple(
            evidence_directory / f"raw/{ordinal:06d}.json.zst"
            for ordinal in range(capture_count)
        ),
        canonical_path=evidence_directory / _CANONICAL_RELATIVE_PATH,
        occurrence_path=evidence_directory / _OCCURRENCE_RELATIVE_PATH,
        manifest_path=evidence_directory / "manifest.json",
        manifest_sha256_path=evidence_directory / "manifest.json.sha256",
    )


def _ordered_capture_pairs(
    pairs: tuple[tuple[str, str], ...],
    *,
    allowed_names: frozenset[str] | None = None,
    unique_names: bool = False,
) -> list[dict[str, str]]:
    ordered: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2:
            raise ArchiveStorageError("raw_capture_invalid")
        name, value = pair
        if (
            type(name) is not str
            or not name
            or type(value) is not str
            or any(character in name or character in value for character in "\r\n\x00")
            or (allowed_names is not None and name not in allowed_names)
            or (unique_names and name in seen_names)
        ):
            raise ArchiveStorageError("raw_capture_invalid")
        seen_names.add(name)
        ordered.append({"name": name, "value": value})
    return ordered


def _require_sanitized_url_query(
    sanitized_url: str,
    query: tuple[tuple[str, str], ...],
) -> None:
    try:
        parsed = urlsplit(sanitized_url)
        parsed_query = tuple(
            parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
        )
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and parsed_query == query
        )
    except (TypeError, UnicodeError, ValueError):
        valid = False
    if not valid:
        raise ArchiveStorageError("raw_capture_invalid")


def _validate_bars(
    scope: CollectionScope,
    rows: tuple[CanonicalMinuteBar, ...],
    captures: tuple[RawHttpCapture, ...],
) -> None:
    if type(rows) is not tuple or any(
        not isinstance(row, CanonicalMinuteBar) for row in rows
    ):
        raise ArchiveStorageError("archive_input_invalid")
    if scope.interval != "1m":
        raise ArchiveStorageError("archive_input_invalid")
    previous_event_start: datetime | None = None
    lineage_keys: set[tuple[int, int]] = set()
    for bar in rows:
        event_start = _parse_canonical_utc(bar.event_start_utc, minute_grid=True)
        if (
            bar.provider != scope.provider
            or bar.feed != scope.feed
            or bar.instrument_id != scope.instrument_id
            or bar.symbol != scope.symbol
            or bar.adjustment_mode != scope.adjustment_mode
            or not 0 <= bar.capture_ordinal < len(captures)
            or bar.raw_body_sha256 != captures[bar.capture_ordinal].body_sha256
            or bar.received_at_utc != captures[bar.capture_ordinal].received_at
            or (previous_event_start is not None and event_start <= previous_event_start)
        ):
            raise ArchiveStorageError("canonical_lineage_invalid")
        for raw_sha256, capture_ordinal, source_row_index in bar.occurrences:
            lineage_key = (capture_ordinal, source_row_index)
            if (
                not 0 <= capture_ordinal < len(captures)
                or raw_sha256 != captures[capture_ordinal].body_sha256
                or lineage_key in lineage_keys
            ):
                raise ArchiveStorageError("canonical_lineage_invalid")
            lineage_keys.add(lineage_key)
        previous_event_start = event_start


def _canonical_table(rows: tuple[CanonicalMinuteBar, ...]) -> pa.Table:
    columns: dict[str, pa.Array] = {
        "provider": _string_array(tuple(bar.provider for bar in rows)),
        "feed": _string_array(tuple(bar.feed for bar in rows)),
        "instrument_id": _string_array(tuple(bar.instrument_id for bar in rows)),
        "symbol": _string_array(tuple(bar.symbol for bar in rows)),
        "source_timestamp": _string_array(
            tuple(bar.source_timestamp for bar in rows)
        ),
        "event_start_utc": _string_array(tuple(bar.event_start_utc for bar in rows)),
        "bar_end_utc": _string_array(tuple(bar.bar_end_utc for bar in rows)),
        "received_at_utc": _string_array(tuple(bar.received_at_utc for bar in rows)),
        "research_available_at_utc": _string_array(
            tuple(bar.research_available_at_utc for bar in rows)
        ),
        "session_date": _string_array(tuple(bar.session_date for bar in rows)),
        "session_type": _string_array(tuple(bar.session_type for bar in rows)),
        "currency": _string_array(tuple(bar.currency for bar in rows)),
        "adjustment_mode": _string_array(
            tuple(bar.adjustment_mode for bar in rows)
        ),
        "numeric_fidelity": _string_array(
            tuple(bar.numeric_fidelity for bar in rows)
        ),
        "quality_status": _string_array(tuple(bar.quality_status for bar in rows)),
        "open_price": _decimal_array(tuple(bar.open_price for bar in rows)),
        "high_price": _decimal_array(tuple(bar.high_price for bar in rows)),
        "low_price": _decimal_array(tuple(bar.low_price for bar in rows)),
        "close_price": _decimal_array(tuple(bar.close_price for bar in rows)),
        "volume": _decimal_array(tuple(bar.volume for bar in rows)),
        "raw_body_sha256": pa.array(
            (bar.raw_body_sha256 for bar in rows), type=pa.string()
        ),
        "capture_ordinal": pa.array(
            (bar.capture_ordinal for bar in rows), type=pa.uint32()
        ),
        "source_row_index": pa.array(
            (bar.source_row_index for bar in rows), type=pa.uint32()
        ),
    }
    return pa.table(columns)


def _occurrence_table(rows: tuple[CanonicalMinuteBar, ...]) -> pa.Table:
    event_starts: list[str] = []
    raw_hashes: list[str] = []
    capture_ordinals: list[int] = []
    source_row_indexes: list[int] = []
    occurrence_orders: list[int] = []
    for bar in rows:
        for occurrence_order, occurrence in enumerate(bar.occurrences):
            raw_sha256, capture_ordinal, source_row_index = occurrence
            event_starts.append(bar.event_start_utc)
            raw_hashes.append(raw_sha256)
            capture_ordinals.append(capture_ordinal)
            source_row_indexes.append(source_row_index)
            occurrence_orders.append(occurrence_order)
    return pa.table(
        {
            "event_start_utc": pa.array(event_starts, type=pa.string()),
            "raw_body_sha256": pa.array(raw_hashes, type=pa.string()),
            "capture_ordinal": pa.array(capture_ordinals, type=pa.uint32()),
            "source_row_index": pa.array(source_row_indexes, type=pa.uint32()),
            "occurrence_order": pa.array(occurrence_orders, type=pa.uint32()),
        }
    )


def _string_array(values: tuple[str, ...]) -> pa.Array:
    return pa.array(values, type=pa.string())


def _decimal_array(values: tuple[CanonicalScalar, ...]) -> pa.Array:
    decimals: list[Decimal] = []
    scale = 0
    for value in values:
        if not isinstance(value, CanonicalScalar):
            raise ArchiveStorageError("canonical_scalar_invalid")
        try:
            decimal_value = Decimal(value.text)
        except (InvalidOperation, ValueError):
            raise ArchiveStorageError("canonical_scalar_invalid") from None
        if not decimal_value.is_finite():
            raise ArchiveStorageError("canonical_scalar_invalid")
        decimals.append(decimal_value)
        scale = max(scale, -decimal_value.as_tuple().exponent)
    try:
        return pa.array(decimals, type=pa.decimal128(38, scale))
    except (pa.ArrowException, ValueError):
        raise ArchiveStorageError("canonical_scalar_invalid") from None


def _price_decimal(value: CanonicalScalar, numeric_fidelity: str) -> Decimal:
    decimal_value = _validated_scalar_decimal(value, numeric_fidelity)
    if decimal_value <= 0:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return decimal_value


def _volume_decimal(value: CanonicalScalar, numeric_fidelity: str) -> Decimal:
    decimal_value = _validated_scalar_decimal(value, numeric_fidelity)
    if decimal_value < 0:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return decimal_value


def _validated_scalar_decimal(
    value: CanonicalScalar,
    numeric_fidelity: str,
) -> Decimal:
    if not isinstance(value, CanonicalScalar):
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    if numeric_fidelity == _JSON_NUMBER_FIDELITY:
        valid_lexeme = (
            value.kind == "json_number"
            and _JSON_NONNEGATIVE_NUMBER_PATTERN.fullmatch(value.text) is not None
        )
    elif numeric_fidelity == _DECIMAL_STRING_FIDELITY:
        valid_lexeme = (
            value.kind == "json_string"
            and _UNSIGNED_DECIMAL_PATTERN.fullmatch(value.text) is not None
        )
    else:
        valid_lexeme = False
    if not valid_lexeme:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    try:
        decimal_value = Decimal(value.text)
    except (InvalidOperation, ValueError):
        raise ArchiveStorageError("canonical_minute_bar_invalid") from None
    if not decimal_value.is_finite():
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return decimal_value


def _parse_source_timestamp(value: str) -> datetime:
    parsed = _parse_aware_timestamp(value)
    if parsed.second != 0 or parsed.microsecond != 0:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return parsed.astimezone(timezone.utc)


def _parse_canonical_utc(value: str, *, minute_grid: bool) -> datetime:
    parsed = _parse_aware_timestamp(value)
    if parsed.utcoffset() != timedelta(0):
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    normalized = parsed.isoformat().replace("+00:00", "Z")
    if value != normalized or (
        minute_grid and (parsed.second != 0 or parsed.microsecond != 0)
    ):
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return parsed


def _parse_aware_timestamp(value: str) -> datetime:
    if type(value) is not str:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except (ValueError, OverflowError):
        raise ArchiveStorageError("canonical_minute_bar_invalid") from None
    if parsed.tzinfo is None:
        raise ArchiveStorageError("canonical_minute_bar_invalid")
    return parsed


def _is_canonical_date(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value


def _is_canonical_identifier(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and unicodedata.normalize("NFC", value) == value
        and not any(
            unicodedata.category(character) in _FORBIDDEN_IDENTIFIER_CATEGORIES
            for character in value
        )
    )


def _valid_occurrence_identity(
    occurrences: object,
    primary: tuple[str, int, int],
) -> bool:
    if type(occurrences) is not tuple or not occurrences:
        return False
    identities: list[tuple[str, int, int]] = []
    for occurrence in occurrences:
        if type(occurrence) is not tuple or len(occurrence) != 3:
            return False
        raw_sha256, capture_ordinal, source_row_index = occurrence
        if (
            type(raw_sha256) is not str
            or _SHA256_PATTERN.fullmatch(raw_sha256) is None
            or type(capture_ordinal) is not int
            or capture_ordinal < 0
            or type(source_row_index) is not int
            or source_row_index < 0
        ):
            return False
        identities.append((raw_sha256, capture_ordinal, source_row_index))
    return identities[0] == primary and len(set(identities)) == len(identities)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest_schema_version(manifest: object) -> str:
    if not isinstance(manifest, dict):
        raise ValueError
    schema_version = manifest.get("schemaVersion")
    if schema_version not in {_SCHEMA_VERSION_V1, _SCHEMA_VERSION_V2}:
        raise ValueError
    return schema_version


def _validate_manifest_identity(
    manifest: object,
    stored: StoredArchive,
    schema_version: str,
) -> None:
    expected_fields = {
        "schemaVersion",
        "acquisitionKey",
        "scope",
        "rawArtifacts",
        "canonicalArtifact",
        "occurrenceArtifact",
    }
    if schema_version == _SCHEMA_VERSION_V2:
        expected_fields.add("acquisitionCompletion")
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise ValueError
    if (
        manifest["schemaVersion"] != schema_version
        or manifest["acquisitionKey"] != stored.acquisition_key
        or stored.archive_directory.name != stored.acquisition_key
    ):
        raise ValueError
    scope = manifest["scope"]
    if not isinstance(scope, dict) or "sampleRole" not in scope:
        raise ValueError
    acquisition_identity = dict(scope)
    acquisition_identity.pop("sampleRole")
    acquisition_digest = hashlib.sha256(
        _canonical_json_bytes(acquisition_identity)
    ).hexdigest()
    if acquisition_digest != stored.acquisition_key:
        raise ValueError


def _validate_failure_evidence_manifest_identity(
    manifest: object,
    stored: StoredFailureEvidence,
) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {
        "schemaVersion",
        "evidenceDigest",
        "acquisitionKey",
        "scope",
        "acquisitionCompletion",
        "rawArtifacts",
        "canonicalArtifact",
        "occurrenceArtifact",
    }:
        raise ValueError
    if (
        manifest["schemaVersion"] != _FAILURE_EVIDENCE_SCHEMA_VERSION
        or manifest["evidenceDigest"] != stored.evidence_digest
        or manifest["acquisitionKey"] != stored.acquisition_key
        or _SHA256_PATTERN.fullmatch(stored.evidence_digest) is None
    ):
        raise ValueError
    scope = manifest["scope"]
    if not isinstance(scope, dict) or "sampleRole" not in scope:
        raise ValueError
    acquisition_identity = dict(scope)
    acquisition_identity.pop("sampleRole")
    acquisition_digest = hashlib.sha256(
        _canonical_json_bytes(acquisition_identity)
    ).hexdigest()
    if acquisition_digest != stored.acquisition_key:
        raise ValueError


def _verify_raw_artifacts(
    manifest: dict[str, object],
    stored: StoredArchive,
    schema_version: str,
) -> dict[int, str]:
    raw_artifacts = manifest["rawArtifacts"]
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(stored.raw_paths):
        raise ValueError
    raw_hashes: dict[int, str] = {}
    for ordinal, artifact in enumerate(raw_artifacts):
        expected_relative_path = f"raw/{ordinal:06d}.json.zst"
        expected_fields = {
            "captureOrdinal",
            "endpointId",
            "receivedAt",
            "status",
            "path",
            "uncompressedBytes",
            "uncompressedSha256",
            "storedBytes",
            "storedSha256",
        }
        if schema_version == _SCHEMA_VERSION_V2:
            expected_fields.update(
                {"method", "sanitizedUrl", "query", "responseHeaders"}
            )
        if not isinstance(artifact, dict) or set(artifact) != expected_fields:
            raise ValueError
        if (
            artifact["captureOrdinal"] != ordinal
            or artifact["path"] != expected_relative_path
            or stored.raw_paths[ordinal]
            != stored.archive_directory / expected_relative_path
            or type(artifact["uncompressedBytes"]) is not int
            or type(artifact["storedBytes"]) is not int
        ):
            raise ValueError
        if schema_version == _SCHEMA_VERSION_V2:
            _verify_capture_request_body(artifact)
        compressed = stored.raw_paths[ordinal].read_bytes()
        if (
            len(compressed) != artifact["storedBytes"]
            or hashlib.sha256(compressed).hexdigest() != artifact["storedSha256"]
        ):
            raise ValueError
        raw_body = zstandard.ZstdDecompressor().decompress(
            compressed,
            max_output_size=artifact["uncompressedBytes"],
        )
        if (
            len(raw_body) != artifact["uncompressedBytes"]
            or hashlib.sha256(raw_body).hexdigest()
            != artifact["uncompressedSha256"]
        ):
            raise ValueError
        raw_hashes[ordinal] = artifact["uncompressedSha256"]
    return raw_hashes


def _verify_capture_request_body(artifact: dict[str, object]) -> None:
    query = _stored_capture_pairs(artifact["query"])
    headers = _stored_capture_pairs(artifact["responseHeaders"])
    if (
        type(artifact["method"]) is not str
        or _HTTP_METHOD_PATTERN.fullmatch(artifact["method"]) is None
        or type(artifact["sanitizedUrl"]) is not str
        or not artifact["sanitizedUrl"]
        or any(
            character in artifact["sanitizedUrl"]
            for character in "\r\n\x00"
        )
        or not _is_canonical_identifier(artifact["endpointId"])
        or type(artifact["status"]) is not int
        or not 100 <= artifact["status"] <= 599
    ):
        raise ValueError
    try:
        _require_sanitized_url_query(artifact["sanitizedUrl"], query)
        _parse_canonical_utc(artifact["receivedAt"], minute_grid=False)
        expected_query = _ordered_capture_pairs(query)
        expected_headers = _ordered_capture_pairs(
            headers,
            allowed_names=_ALLOWED_CAPTURE_HEADERS,
            unique_names=True,
        )
    except ArchiveStorageError:
        raise ValueError from None
    if (
        artifact["query"] != expected_query
        or artifact["responseHeaders"] != expected_headers
    ):
        raise ValueError


def _stored_capture_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "value"}:
            raise ValueError
        name = item["name"]
        pair_value = item["value"]
        if type(name) is not str or type(pair_value) is not str:
            raise ValueError
        pairs.append((name, pair_value))
    return tuple(pairs)


def _verify_acquisition_completion(
    manifest: dict[str, object],
    canonical_row_count: int,
) -> None:
    completion = _acquisition_completion_from_metadata(
        manifest["acquisitionCompletion"]
    )
    if (
        completion.terminal_status
        not in {
            AcquisitionTerminalStatus.COMPLETED,
            AcquisitionTerminalStatus.PARTIAL,
            AcquisitionTerminalStatus.DATA_UNAVAILABLE,
        }
        or completion.returned_row_count != canonical_row_count
    ):
        raise ValueError


def _acquisition_completion_from_metadata(
    metadata: object,
) -> AcquisitionCompletion:
    if not isinstance(metadata, dict) or set(metadata) != {
        "requestedStartReached",
        "completionReason",
        "terminalStatus",
        "analysisRowCount",
        "auditRowCount",
        "returnedRowCount",
    }:
        raise ValueError
    try:
        completion = AcquisitionCompletion(
            requested_start_reached=metadata["requestedStartReached"],
            completion_reason=metadata["completionReason"],
            terminal_status=AcquisitionTerminalStatus(metadata["terminalStatus"]),
            analysis_row_count=metadata["analysisRowCount"],
            audit_row_count=metadata["auditRowCount"],
            returned_row_count=metadata["returnedRowCount"],
        )
    except (ArchiveStorageError, TypeError, ValueError):
        raise ValueError from None
    if metadata != completion.to_canonical_body():
        raise ValueError
    return completion


def _verify_canonical_artifact(
    manifest: dict[str, object],
    stored: StoredArchive,
    raw_hashes: dict[int, str],
) -> dict[str, tuple[str, int, int]]:
    artifact = manifest["canonicalArtifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "compression",
        "path",
        "rowCount",
        "sha256",
    }:
        raise ValueError
    canonical_bytes = stored.canonical_path.read_bytes()
    if (
        artifact["compression"] != "ZSTD"
        or artifact["path"] != _CANONICAL_RELATIVE_PATH.as_posix()
        or type(artifact["rowCount"]) is not int
        or hashlib.sha256(canonical_bytes).hexdigest() != artifact["sha256"]
    ):
        raise ValueError
    parquet_file = parquet.ParquetFile(stored.canonical_path)
    metadata = parquet_file.metadata
    if metadata.num_rows != artifact["rowCount"]:
        raise ValueError
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            if row_group.column(column_index).compression != "ZSTD":
                raise ValueError
    table = parquet_file.read()
    if tuple(table.column_names) != _CANONICAL_COLUMNS:
        raise ValueError
    for name in ("open_price", "high_price", "low_price", "close_price", "volume"):
        if not pa.types.is_decimal(table.schema.field(name).type):
            raise ValueError
    primary_lineage: dict[str, tuple[str, int, int]] = {}
    for event_start, raw_sha256, capture_ordinal, row_index in zip(
        table.column("event_start_utc").to_pylist(),
        table.column("raw_body_sha256").to_pylist(),
        table.column("capture_ordinal").to_pylist(),
        table.column("source_row_index").to_pylist(),
        strict=True,
    ):
        if (
            type(event_start) is not str
            or event_start in primary_lineage
            or type(capture_ordinal) is not int
            or raw_hashes.get(capture_ordinal) != raw_sha256
            or type(row_index) is not int
            or row_index < 0
        ):
            raise ValueError
        primary_lineage[event_start] = (raw_sha256, capture_ordinal, row_index)
    return primary_lineage


def _verify_occurrence_artifact(
    manifest: dict[str, object],
    stored: StoredArchive,
    raw_hashes: dict[int, str],
    primary_lineage: dict[str, tuple[str, int, int]],
) -> None:
    artifact = manifest["occurrenceArtifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "compression",
        "path",
        "rowCount",
        "sha256",
    }:
        raise ValueError
    occurrence_bytes = stored.occurrence_path.read_bytes()
    if (
        artifact["compression"] != "ZSTD"
        or artifact["path"] != _OCCURRENCE_RELATIVE_PATH.as_posix()
        or type(artifact["rowCount"]) is not int
        or hashlib.sha256(occurrence_bytes).hexdigest() != artifact["sha256"]
    ):
        raise ValueError
    parquet_file = parquet.ParquetFile(stored.occurrence_path)
    metadata = parquet_file.metadata
    if metadata.num_rows != artifact["rowCount"]:
        raise ValueError
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            if row_group.column(column_index).compression != "ZSTD":
                raise ValueError
    table = parquet_file.read()
    if tuple(table.column_names) != _OCCURRENCE_COLUMNS:
        raise ValueError
    observed_orders: dict[str, list[int]] = {}
    seen_lineage: set[tuple[int, int]] = set()
    for event_start, raw_sha256, capture_ordinal, row_index, occurrence_order in zip(
        *(table.column(name).to_pylist() for name in _OCCURRENCE_COLUMNS),
        strict=True,
    ):
        lineage_key = (capture_ordinal, row_index)
        if (
            event_start not in primary_lineage
            or type(capture_ordinal) is not int
            or raw_hashes.get(capture_ordinal) != raw_sha256
            or type(row_index) is not int
            or row_index < 0
            or type(occurrence_order) is not int
            or occurrence_order < 0
            or lineage_key in seen_lineage
        ):
            raise ValueError
        if occurrence_order == 0 and primary_lineage[event_start] != (
            raw_sha256,
            capture_ordinal,
            row_index,
        ):
            raise ValueError
        seen_lineage.add(lineage_key)
        observed_orders.setdefault(event_start, []).append(occurrence_order)
    if set(observed_orders) != set(primary_lineage):
        raise ValueError
    if any(orders != list(range(len(orders))) for orders in observed_orders.values()):
        raise ValueError
