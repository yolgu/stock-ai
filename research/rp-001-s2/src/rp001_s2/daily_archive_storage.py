"""Immutable raw and canonical storage for whole-period daily scopes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as parquet
import zstandard

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
)


_SCHEMA_VERSION = "rp001-s2-immutable-daily-archive.v1"
_FAILURE_SCHEMA_VERSION = "rp001-s2-immutable-daily-failure-evidence.v1"
_CANONICAL_PATH = Path("canonical/daily-bars.parquet")
_MINIMUM_FREE_BYTES = 50 * 1024**3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NEW_YORK = ZoneInfo("America/New_York")
_PRICE_FIELDS = ("open", "high", "low", "close", "volume")


class DailyArchiveStorageError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CanonicalDailyBar:
    provider: str
    feed: str
    instrument_id: str
    symbol: str
    source_timestamp: str
    session_date: str
    received_at_utc: str
    research_available_at_utc: str
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
        try:
            source = _parse_timestamp(self.source_timestamp)
            received = _parse_timestamp(self.received_at_utc)
            available = _parse_timestamp(self.research_available_at_utc)
            prices = tuple(
                _decimal(value)
                for value in (
                    self.open_price,
                    self.high_price,
                    self.low_price,
                    self.close_price,
                    self.volume,
                )
            )
        except (TypeError, ValueError, InvalidOperation):
            raise DailyArchiveStorageError("canonical_daily_bar_invalid") from None
        open_price, high_price, low_price, close_price, volume = prices
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
        primary = (
            self.raw_body_sha256,
            self.capture_ordinal,
            self.source_row_index,
        )
        if (
            any(not isinstance(value, str) or not value for value in identifiers)
            or _session_date(source, self.currency) != self.session_date
            or available < received
            or low_price <= 0
            or not low_price <= open_price <= high_price
            or not low_price <= close_price <= high_price
            or volume < 0
            or _SHA256.fullmatch(self.raw_body_sha256) is None
            or type(self.capture_ordinal) is not int
            or self.capture_ordinal < 0
            or type(self.source_row_index) is not int
            or self.source_row_index < 0
            or not self.occurrences
            or self.occurrences[0] != primary
            or len(set(self.occurrences)) != len(self.occurrences)
            or any(
                _SHA256.fullmatch(sha256) is None
                or type(ordinal) is not int
                or ordinal < 0
                or type(row_index) is not int
                or row_index < 0
                for sha256, ordinal, row_index in self.occurrences
            )
        ):
            raise DailyArchiveStorageError("canonical_daily_bar_invalid")


@dataclass(frozen=True)
class StoredDailyArchive:
    acquisition_key: str
    archive_directory: Path
    raw_paths: tuple[Path, ...]
    canonical_path: Path
    manifest_path: Path
    manifest_sha256_path: Path


@dataclass(frozen=True)
class StoredDailyFailureEvidence:
    acquisition_key: str
    evidence_digest: str
    evidence_directory: Path
    raw_paths: tuple[Path, ...]
    manifest_path: Path
    manifest_sha256_path: Path


class ImmutableDailyArchiveStorage:
    def __init__(
        self,
        root: Path,
        *,
        free_bytes: object | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise DailyArchiveStorageError("archive_root_invalid")
        self._root = root
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    def write_archive(
        self,
        *,
        scope: CollectionScope,
        captures: tuple[RawHttpCapture, ...],
        rows: tuple[CanonicalDailyBar, ...],
        completion: AcquisitionCompletion,
    ) -> StoredDailyArchive:
        _validate_archive_input(scope, captures, rows, completion)
        final = self._root / scope.acquisition_key
        if final.exists():
            raise DailyArchiveStorageError("archive_already_exists")
        self._root.mkdir(parents=True, exist_ok=True)
        if self._free_bytes(self._root) < _MINIMUM_FREE_BYTES:
            raise DailyArchiveStorageError("blocked_storage_capacity")
        staging = Path(
            tempfile.mkdtemp(prefix=f".{scope.acquisition_key}.", dir=self._root)
        )
        try:
            stored = self._write_staging(
                staging,
                scope,
                captures,
                rows,
                completion,
            )
            os.rename(staging, final)
            published = StoredDailyArchive(
                acquisition_key=stored.acquisition_key,
                archive_directory=final,
                raw_paths=tuple(final / path.relative_to(staging) for path in stored.raw_paths),
                canonical_path=final / stored.canonical_path.relative_to(staging),
                manifest_path=final / "manifest.json",
                manifest_sha256_path=final / "manifest.json.sha256",
            )
            self.verify_archive(published)
            return published
        except FileExistsError:
            raise DailyArchiveStorageError("archive_already_exists") from None
        except DailyArchiveStorageError:
            raise
        except Exception:
            raise DailyArchiveStorageError("archive_write_failed") from None
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def find_verified_archive(
        self,
        scope: CollectionScope,
    ) -> StoredDailyArchive | None:
        directory = self._root / scope.acquisition_key
        if not directory.exists():
            return None
        try:
            manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
            raw = manifest["rawArtifacts"]
            if not isinstance(raw, list):
                raise ValueError
            stored = StoredDailyArchive(
                acquisition_key=scope.acquisition_key,
                archive_directory=directory,
                raw_paths=tuple(directory / artifact["path"] for artifact in raw),
                canonical_path=directory / _CANONICAL_PATH,
                manifest_path=directory / "manifest.json",
                manifest_sha256_path=directory / "manifest.json.sha256",
            )
            self.verify_archive(stored)
            if manifest["scope"] != scope.to_canonical_body():
                raise DailyArchiveStorageError("archive_verification_failed")
            return stored
        except DailyArchiveStorageError:
            raise
        except Exception:
            raise DailyArchiveStorageError("archive_verification_failed") from None

    def verify_archive(self, stored: StoredDailyArchive) -> None:
        try:
            self._verify_archive(stored)
        except Exception:
            raise DailyArchiveStorageError("archive_verification_failed") from None

    def write_failure_evidence(
        self,
        *,
        scope: CollectionScope,
        captures: tuple[RawHttpCapture, ...],
        error_code: str,
    ) -> StoredDailyFailureEvidence:
        if (
            not isinstance(scope, CollectionScope)
            or scope.interval != "1d"
            or type(captures) is not tuple
            or any(not isinstance(capture, RawHttpCapture) for capture in captures)
            or not isinstance(error_code, str)
            or not error_code
        ):
            raise DailyArchiveStorageError("failure_evidence_invalid")
        bodies = tuple(_decode_capture(capture) for capture in captures)
        digest = hashlib.sha256(
            _canonical_json_bytes(
                {
                    "scope": scope.acquisition_identity_body(),
                    "errorCode": error_code,
                    "captureSha256s": [capture.body_sha256 for capture in captures],
                }
            )
        ).hexdigest()
        directory = self._root / "failure-evidence" / scope.acquisition_key / digest
        stored = StoredDailyFailureEvidence(
            acquisition_key=scope.acquisition_key,
            evidence_digest=digest,
            evidence_directory=directory,
            raw_paths=tuple(
                directory / f"raw/{ordinal:06d}.json.zst"
                for ordinal in range(len(captures))
            ),
            manifest_path=directory / "manifest.json",
            manifest_sha256_path=directory / "manifest.json.sha256",
        )
        if directory.exists():
            self.verify_failure_evidence(stored)
            return stored
        parent = directory.parent
        parent.mkdir(parents=True, exist_ok=True)
        if self._free_bytes(self._root) < _MINIMUM_FREE_BYTES:
            raise DailyArchiveStorageError("blocked_storage_capacity")
        staging = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=parent))
        try:
            (staging / "raw").mkdir()
            compressor = zstandard.ZstdCompressor(level=9)
            artifacts: list[dict[str, object]] = []
            for ordinal, (capture, body) in enumerate(
                zip(captures, bodies, strict=True)
            ):
                compressed = compressor.compress(body)
                relative = Path(f"raw/{ordinal:06d}.json.zst")
                _write_new(staging / relative, compressed)
                artifacts.append(
                    {
                        "captureOrdinal": ordinal,
                        "endpointId": capture.endpoint_id,
                        "method": capture.method,
                        "status": capture.status,
                        "receivedAt": capture.received_at,
                        "path": relative.as_posix(),
                        "uncompressedSha256": capture.body_sha256,
                        "storedSha256": hashlib.sha256(compressed).hexdigest(),
                    }
                )
            manifest = {
                "schemaVersion": _FAILURE_SCHEMA_VERSION,
                "acquisitionKey": scope.acquisition_key,
                "evidenceDigest": digest,
                "scope": scope.to_canonical_body(),
                "errorCode": error_code,
                "rawArtifacts": artifacts,
            }
            source = _canonical_json_bytes(manifest)
            _write_new(staging / "manifest.json", source)
            _write_new(
                staging / "manifest.json.sha256",
                f"{hashlib.sha256(source).hexdigest()}\n".encode("ascii"),
            )
            os.rename(staging, directory)
            self.verify_failure_evidence(stored)
            return stored
        except FileExistsError:
            self.verify_failure_evidence(stored)
            return stored
        except DailyArchiveStorageError:
            raise
        except Exception:
            raise DailyArchiveStorageError("failure_evidence_write_failed") from None
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def verify_failure_evidence(
        self,
        stored: StoredDailyFailureEvidence,
    ) -> None:
        try:
            source = _read_regular(stored.manifest_path)
            digest = hashlib.sha256(source).hexdigest()
            if _read_regular(stored.manifest_sha256_path) != f"{digest}\n".encode("ascii"):
                raise ValueError
            manifest = json.loads(source.decode("utf-8"))
            if (
                _canonical_json_bytes(manifest) != source
                or manifest["schemaVersion"] != _FAILURE_SCHEMA_VERSION
                or manifest["acquisitionKey"] != stored.acquisition_key
                or manifest["evidenceDigest"] != stored.evidence_digest
                or len(manifest["rawArtifacts"]) != len(stored.raw_paths)
            ):
                raise ValueError
            decompressor = zstandard.ZstdDecompressor()
            for ordinal, (artifact, path) in enumerate(
                zip(manifest["rawArtifacts"], stored.raw_paths, strict=True)
            ):
                compressed = _read_regular(path)
                body = decompressor.decompress(compressed)
                if (
                    artifact["captureOrdinal"] != ordinal
                    or hashlib.sha256(compressed).hexdigest() != artifact["storedSha256"]
                    or hashlib.sha256(body).hexdigest()
                    != artifact["uncompressedSha256"]
                ):
                    raise ValueError
        except Exception:
            raise DailyArchiveStorageError(
                "failure_evidence_verification_failed"
            ) from None

    def _write_staging(
        self,
        staging: Path,
        scope: CollectionScope,
        captures: tuple[RawHttpCapture, ...],
        rows: tuple[CanonicalDailyBar, ...],
        completion: AcquisitionCompletion,
    ) -> StoredDailyArchive:
        raw_directory = staging / "raw"
        canonical_directory = staging / "canonical"
        raw_directory.mkdir()
        canonical_directory.mkdir()
        compressor = zstandard.ZstdCompressor(level=9)
        raw_paths: list[Path] = []
        raw_artifacts: list[dict[str, object]] = []
        for ordinal, capture in enumerate(captures):
            body = _decode_capture(capture)
            compressed = compressor.compress(body)
            relative = Path(f"raw/{ordinal:06d}.json.zst")
            path = staging / relative
            _write_new(path, compressed)
            raw_paths.append(path)
            raw_artifacts.append(
                {
                    "captureOrdinal": ordinal,
                    "endpointId": capture.endpoint_id,
                    "method": capture.method,
                    "sanitizedUrl": capture.sanitized_url,
                    "query": [
                        {"name": name, "value": value}
                        for name, value in capture.query
                    ],
                    "status": capture.status,
                    "responseHeaders": [
                        {"name": name, "value": value}
                        for name, value in capture.headers
                    ],
                    "receivedAt": capture.received_at,
                    "path": relative.as_posix(),
                    "uncompressedBytes": len(body),
                    "uncompressedSha256": capture.body_sha256,
                    "storedBytes": len(compressed),
                    "storedSha256": hashlib.sha256(compressed).hexdigest(),
                }
            )
        canonical_path = staging / _CANONICAL_PATH
        table = _daily_table(rows)
        parquet.write_table(table, canonical_path, compression="zstd")
        canonical_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
        manifest = {
            "schemaVersion": _SCHEMA_VERSION,
            "acquisitionKey": scope.acquisition_key,
            "scope": scope.to_canonical_body(),
            "acquisitionCompletion": completion.to_canonical_body(),
            "rawArtifacts": raw_artifacts,
            "canonicalArtifact": {
                "path": _CANONICAL_PATH.as_posix(),
                "compression": "ZSTD",
                "rowCount": len(rows),
                "sha256": canonical_sha256,
            },
        }
        manifest_source = _canonical_json_bytes(manifest)
        manifest_path = staging / "manifest.json"
        _write_new(manifest_path, manifest_source)
        sidecar = staging / "manifest.json.sha256"
        _write_new(
            sidecar,
            f"{hashlib.sha256(manifest_source).hexdigest()}\n".encode("ascii"),
        )
        return StoredDailyArchive(
            acquisition_key=scope.acquisition_key,
            archive_directory=staging,
            raw_paths=tuple(raw_paths),
            canonical_path=canonical_path,
            manifest_path=manifest_path,
            manifest_sha256_path=sidecar,
        )

    def _verify_archive(self, stored: StoredDailyArchive) -> None:
        if (
            not isinstance(stored, StoredDailyArchive)
            or stored.archive_directory.is_symlink()
            or not stored.archive_directory.is_dir()
            or stored.archive_directory.name != stored.acquisition_key
        ):
            raise ValueError
        source = _read_regular(stored.manifest_path)
        digest = hashlib.sha256(source).hexdigest()
        if _read_regular(stored.manifest_sha256_path) != f"{digest}\n".encode("ascii"):
            raise ValueError
        manifest = json.loads(source.decode("utf-8"))
        if (
            _canonical_json_bytes(manifest) != source
            or manifest.get("schemaVersion") != _SCHEMA_VERSION
            or manifest.get("acquisitionKey") != stored.acquisition_key
        ):
            raise ValueError
        raw_artifacts = manifest["rawArtifacts"]
        if len(raw_artifacts) != len(stored.raw_paths):
            raise ValueError
        raw_rows: dict[tuple[int, int], dict[str, str]] = {}
        raw_hashes: dict[int, str] = {}
        decompressor = zstandard.ZstdDecompressor()
        for ordinal, (artifact, path) in enumerate(
            zip(raw_artifacts, stored.raw_paths, strict=True)
        ):
            compressed = _read_regular(path)
            body = decompressor.decompress(compressed)
            if (
                artifact["captureOrdinal"] != ordinal
                or artifact["path"] != path.relative_to(stored.archive_directory).as_posix()
                or hashlib.sha256(compressed).hexdigest() != artifact["storedSha256"]
                or hashlib.sha256(body).hexdigest() != artifact["uncompressedSha256"]
            ):
                raise ValueError
            raw_hashes[ordinal] = artifact["uncompressedSha256"]
            for row_index, row in enumerate(_raw_daily_rows(body)):
                raw_rows[(ordinal, row_index)] = row
        canonical_artifact = manifest["canonicalArtifact"]
        canonical_source = _read_regular(stored.canonical_path)
        if (
            canonical_artifact["path"] != _CANONICAL_PATH.as_posix()
            or hashlib.sha256(canonical_source).hexdigest()
            != canonical_artifact["sha256"]
        ):
            raise ValueError
        records = parquet.read_table(stored.canonical_path).to_pylist()
        if len(records) != canonical_artifact["rowCount"]:
            raise ValueError
        for record in records:
            _verify_record_lineage(record, raw_rows, raw_hashes)


def _validate_archive_input(
    scope: object,
    captures: object,
    rows: object,
    completion: object,
) -> None:
    if (
        not isinstance(scope, CollectionScope)
        or scope.interval != "1d"
        or type(captures) is not tuple
        or any(not isinstance(value, RawHttpCapture) for value in captures)
        or type(rows) is not tuple
        or any(not isinstance(value, CanonicalDailyBar) for value in rows)
        or not isinstance(completion, AcquisitionCompletion)
        or completion.terminal_status
        in {AcquisitionTerminalStatus.FAILED, AcquisitionTerminalStatus.INVALID}
        or completion.returned_row_count != len(rows)
    ):
        raise DailyArchiveStorageError("archive_input_invalid")
    previous: str | None = None
    for row in rows:
        if (
            row.provider != scope.provider
            or row.feed != scope.feed
            or row.instrument_id != scope.instrument_id
            or row.symbol != scope.symbol
            or row.adjustment_mode != scope.adjustment_mode
            or (previous is not None and row.source_timestamp <= previous)
        ):
            raise DailyArchiveStorageError("archive_input_invalid")
        previous = row.source_timestamp


def _daily_table(rows: tuple[CanonicalDailyBar, ...]) -> pa.Table:
    records: list[dict[str, object]] = []
    for row in rows:
        record: dict[str, object] = {
            "provider": row.provider,
            "feed": row.feed,
            "instrument_id": row.instrument_id,
            "symbol": row.symbol,
            "source_timestamp": row.source_timestamp,
            "session_date": row.session_date,
            "received_at_utc": row.received_at_utc,
            "research_available_at_utc": row.research_available_at_utc,
            "session_type": row.session_type,
            "currency": row.currency,
            "adjustment_mode": row.adjustment_mode,
            "numeric_fidelity": row.numeric_fidelity,
            "quality_status": row.quality_status,
            "raw_body_sha256": row.raw_body_sha256,
            "capture_ordinal": row.capture_ordinal,
            "source_row_index": row.source_row_index,
            "occurrences_json": json.dumps(
                [list(value) for value in row.occurrences],
                separators=(",", ":"),
            ),
        }
        for name, value in zip(
            _PRICE_FIELDS,
            (
                row.open_price,
                row.high_price,
                row.low_price,
                row.close_price,
                row.volume,
            ),
            strict=True,
        ):
            record[f"{name}_kind"] = value.kind
            record[f"{name}_text"] = value.text
        records.append(record)
    schema = pa.schema(
        [
            *(pa.field(name, pa.string()) for name in (
                "provider", "feed", "instrument_id", "symbol",
                "source_timestamp", "session_date", "received_at_utc",
                "research_available_at_utc", "session_type", "currency",
                "adjustment_mode", "numeric_fidelity", "quality_status",
            )),
            *(pa.field(f"{name}_{suffix}", pa.string()) for name in _PRICE_FIELDS for suffix in ("kind", "text")),
            pa.field("raw_body_sha256", pa.string()),
            pa.field("capture_ordinal", pa.int64()),
            pa.field("source_row_index", pa.int64()),
            pa.field("occurrences_json", pa.string()),
        ]
    )
    return pa.Table.from_pylist(records, schema=schema)


def _verify_record_lineage(
    record: dict[str, object],
    raw_rows: dict[tuple[int, int], dict[str, str]],
    raw_hashes: dict[int, str],
) -> None:
    occurrences = json.loads(record["occurrences_json"])
    expected = {
        "timestamp": record["source_timestamp"],
        "openPrice": record["open_text"],
        "highPrice": record["high_text"],
        "lowPrice": record["low_text"],
        "closePrice": record["close_text"],
        "volume": record["volume_text"],
        "currency": record["currency"],
    }
    if not occurrences:
        raise ValueError
    for sha256, ordinal, row_index in occurrences:
        if raw_hashes.get(ordinal) != sha256 or raw_rows.get((ordinal, row_index)) != expected:
            raise ValueError
    if occurrences[0] != [
        record["raw_body_sha256"],
        record["capture_ordinal"],
        record["source_row_index"],
    ]:
        raise ValueError


def _raw_daily_rows(body: bytes) -> tuple[dict[str, str], ...]:
    value = json.loads(body.decode("utf-8"))
    result = value.get("result") if isinstance(value, dict) else None
    rows = result.get("candles") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError
    required = {
        "timestamp", "openPrice", "highPrice", "lowPrice", "closePrice",
        "volume", "currency",
    }
    if any(
        not isinstance(row, dict)
        or set(row) != required
        or any(not isinstance(item, str) for item in row.values())
        for row in rows
    ):
        raise ValueError
    return tuple(rows)


def _decode_capture(capture: RawHttpCapture) -> bytes:
    try:
        body = base64.b64decode(capture.body_base64, validate=True)
    except Exception:
        raise DailyArchiveStorageError("raw_capture_invalid") from None
    if hashlib.sha256(body).hexdigest() != capture.body_sha256:
        raise DailyArchiveStorageError("raw_capture_invalid")
    return body


def _decimal(value: CanonicalScalar) -> Decimal:
    if not isinstance(value, CanonicalScalar):
        raise ValueError
    result = Decimal(value.text)
    if not result.is_finite():
        raise ValueError
    return result


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None:
        raise ValueError
    return parsed


def _session_date(value: datetime, currency: str) -> str:
    if currency == "KRW":
        return value.date().isoformat()
    if currency == "USD":
        return value.astimezone(_NEW_YORK).date().isoformat()
    raise ValueError


def _write_new(path: Path, source: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError
    return path.read_bytes()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
