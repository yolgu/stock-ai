"""Private immutable storage for sampled Toss forward microstructure evidence."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pyarrow as pa
import pyarrow.parquet as parquet
import zstandard

from rp001.toss_research_collector import (
    CanonicalScalar,
    CollectorError,
    RawHttpCapture,
)
from rp001_s2 import toss_forward_microstructure as forward
from rp001_s2 import toss_boundary
from rp001_s2.toss_forward_microstructure import (
    SampledOrderbookLevel,
    SampledOrderbookSnapshot,
    SampledTradeObservation,
    SampledTradeStream,
)


_SCHEMA_VERSION = "rp001-s2-toss-forward-archive.v1"
_IDENTITY_DOMAIN = "rp001_s2.toss_forward_archive"
_FAILURE_SCHEMA_VERSION = "rp001-s2-toss-forward-failure-evidence.v1"
_FAILURE_IDENTITY_DOMAIN = "rp001_s2.toss_forward_failure_evidence"
_MINIMUM_FREE_BYTES = 50 * 1024**3
_SUCCESS_DIRECTORY = Path("success")
_TRADES_PATH = Path("canonical/trades.parquet")
_ORDERBOOK_PATH = Path("canonical/orderbook-levels.parquet")
_MANIFEST_PATH = Path("manifest.json")
_MANIFEST_SHA256_PATH = Path("manifest.json.sha256")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
_ALLOWED_CAPTURE_HEADERS = frozenset(
    {
        "content-type",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "retry-after",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)
_AUTH_CAPTURE_HEADERS = _ALLOWED_CAPTURE_HEADERS - {"retry-after"}
_TRADE_SCHEMA = pa.schema(
    (
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("measurement_kind", pa.string(), nullable=False),
        pa.field("completeness", pa.string(), nullable=False),
        pa.field("aggressor_side_status", pa.string(), nullable=False),
        pa.field("order_id_status", pa.string(), nullable=False),
        pa.field("ofi_status", pa.string(), nullable=False),
        pa.field("price_lexeme", pa.string(), nullable=False),
        pa.field("volume_lexeme", pa.string(), nullable=False),
        pa.field("numeric_fidelity", pa.string(), nullable=False),
        pa.field("source_timestamp", pa.string(), nullable=False),
        pa.field("normalized_event_at", pa.string(), nullable=False),
        pa.field("received_at", pa.string(), nullable=False),
        pa.field("currency", pa.string(), nullable=False),
        pa.field("source_body_sha256", pa.string(), nullable=False),
        pa.field("source_capture_ordinal", pa.int64(), nullable=False),
        pa.field("source_row_index", pa.int64(), nullable=False),
        pa.field("duplicate_status", pa.string(), nullable=False),
        pa.field("ambiguous_occurrences_json", pa.string(), nullable=False),
    )
)
_ORDERBOOK_SCHEMA = pa.schema(
    (
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("measurement_kind", pa.string(), nullable=False),
        pa.field("completeness", pa.string(), nullable=False),
        pa.field("aggressor_side_status", pa.string(), nullable=False),
        pa.field("order_id_status", pa.string(), nullable=False),
        pa.field("ofi_status", pa.string(), nullable=False),
        pa.field("source_timestamp", pa.string(), nullable=True),
        pa.field("normalized_event_at", pa.string(), nullable=True),
        pa.field("received_at", pa.string(), nullable=False),
        pa.field("currency", pa.string(), nullable=False),
        pa.field("side", pa.string(), nullable=False),
        pa.field("level", pa.int64(), nullable=False),
        pa.field("price_lexeme", pa.string(), nullable=False),
        pa.field("volume_lexeme", pa.string(), nullable=False),
        pa.field("numeric_fidelity", pa.string(), nullable=False),
        pa.field("source_body_sha256", pa.string(), nullable=False),
        pa.field("source_capture_ordinal", pa.int64(), nullable=False),
        pa.field("source_row_index", pa.int64(), nullable=False),
    )
)

FreeBytes = Callable[[Path], int]


class ForwardArchiveError(ValueError):
    """Stable failure from the sampled forward archive boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredForwardArchive:
    symbol: str
    content_identity: str
    archive_directory: Path
    raw_paths: tuple[Path, ...]
    trades_path: Path
    orderbook_path: Path
    manifest_path: Path
    manifest_sha256_path: Path


@dataclass(frozen=True)
class StoredForwardFailureEvidence:
    symbol: str
    evidence_digest: str
    evidence_directory: Path
    raw_paths: tuple[Path, ...]
    manifest_path: Path
    manifest_sha256_path: Path


@dataclass(frozen=True)
class _PreparedArchive:
    stored: StoredForwardArchive
    artifact_bytes: tuple[tuple[Path, bytes], ...]
    manifest_bytes: bytes


@dataclass(frozen=True)
class _PreparedFailureEvidence:
    stored: StoredForwardFailureEvidence
    artifact_bytes: tuple[tuple[Path, bytes], ...]
    manifest_bytes: bytes


class ImmutableTossForwardStorage:
    """Persist sampled forward evidence under one private append-only root."""

    def __init__(
        self,
        root: Path,
        *,
        free_bytes: FreeBytes | None = None,
    ) -> None:
        self._root = root
        self._root_identity = _private_root_identity(root)
        self._free_bytes = free_bytes or _disk_free_bytes

    def write_archive(
        self,
        *,
        trade_stream: SampledTradeStream,
        orderbook_snapshot: SampledOrderbookSnapshot,
    ) -> StoredForwardArchive:
        prepared = _prepare_archive(
            self._root,
            trade_stream,
            orderbook_snapshot,
        )
        if prepared.stored.archive_directory.exists():
            return self._verified_identical_archive(prepared)

        self._require_capacity()
        success_root = self._root / _SUCCESS_DIRECTORY
        try:
            success_root.mkdir(mode=0o700, exist_ok=True)
            _require_real_private_directory(success_root)
            prepared.stored.archive_directory.mkdir(mode=0o700)
            (prepared.stored.archive_directory / "raw").mkdir(mode=0o700)
            (prepared.stored.archive_directory / "canonical").mkdir(mode=0o700)
        except FileExistsError:
            return self._verified_identical_archive(prepared)
        except OSError:
            raise ForwardArchiveError("forward_archive_write_failed") from None

        for relative_path, body in prepared.artifact_bytes:
            self._write_new(prepared.stored.archive_directory / relative_path, body)
        self._write_new(prepared.stored.manifest_path, prepared.manifest_bytes)
        self._write_new(
            prepared.stored.manifest_sha256_path,
            _sidecar_bytes(hashlib.sha256(prepared.manifest_bytes).hexdigest()),
        )
        self.verify_archive(prepared.stored)
        return prepared.stored

    def verify_archive(self, stored: StoredForwardArchive) -> None:
        try:
            self._verify_archive(stored)
        except Exception:
            raise ForwardArchiveError(
                "forward_archive_verification_failed"
            ) from None

    def write_failure_evidence(
        self,
        *,
        symbol: str,
        error_code: str,
        captures: tuple[RawHttpCapture, ...],
    ) -> StoredForwardFailureEvidence:
        prepared = _prepare_failure_evidence(
            self._root,
            symbol,
            error_code,
            captures,
        )
        if prepared.stored.evidence_directory.exists():
            return self._verified_identical_failure_evidence(prepared)

        self._require_capacity()
        failure_root = self._root / "failure-evidence"
        symbol_root = failure_root / symbol
        try:
            failure_root.mkdir(mode=0o700, exist_ok=True)
            _require_real_private_directory(failure_root)
            symbol_root.mkdir(mode=0o700, exist_ok=True)
            _require_real_private_directory(symbol_root)
            prepared.stored.evidence_directory.mkdir(mode=0o700)
            (prepared.stored.evidence_directory / "raw").mkdir(mode=0o700)
        except FileExistsError:
            return self._verified_identical_failure_evidence(prepared)
        except OSError:
            raise ForwardArchiveError(
                "forward_failure_evidence_write_failed"
            ) from None

        for relative_path, body in prepared.artifact_bytes:
            self._write_new(prepared.stored.evidence_directory / relative_path, body)
        self._write_new(
            prepared.stored.manifest_path,
            prepared.manifest_bytes,
        )
        self._write_new(
            prepared.stored.manifest_sha256_path,
            _sidecar_bytes(hashlib.sha256(prepared.manifest_bytes).hexdigest()),
        )
        self.verify_failure_evidence(prepared.stored)
        return prepared.stored

    def verify_failure_evidence(
        self,
        stored: StoredForwardFailureEvidence,
    ) -> None:
        try:
            self._verify_failure_evidence(stored)
        except Exception:
            raise ForwardArchiveError(
                "forward_failure_evidence_verification_failed"
            ) from None

    def _verify_archive(self, stored: StoredForwardArchive) -> None:
        self._require_root()
        if not isinstance(stored, StoredForwardArchive):
            raise ValueError
        expected = _stored_archive(
            self._root,
            stored.symbol,
            stored.content_identity,
        )
        if stored != expected:
            raise ValueError
        _require_archive_layout(stored)

        manifest_bytes = stored.manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if (
            stored.manifest_sha256_path.read_bytes()
            != _sidecar_bytes(manifest_sha256)
        ):
            raise ValueError
        manifest = _load_canonical_json(manifest_bytes)
        if not isinstance(manifest, dict) or set(manifest) != {
            "schemaVersion",
            "identityDomain",
            "contentIdentity",
            "symbol",
            "claims",
            "orderbookSnapshot",
            "rawArtifacts",
            "canonicalArtifacts",
        }:
            raise ValueError
        if (
            manifest["schemaVersion"] != _SCHEMA_VERSION
            or manifest["identityDomain"] != _IDENTITY_DOMAIN
            or manifest["contentIdentity"] != stored.content_identity
            or manifest["symbol"] != stored.symbol
        ):
            raise ValueError

        raw_artifacts = manifest["rawArtifacts"]
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) != 2:
            raise ValueError
        captures = tuple(
            _verify_raw_artifact(
                stored.raw_paths[ordinal],
                artifact,
                ordinal,
                stored.symbol,
            )
            for ordinal, artifact in enumerate(raw_artifacts)
        )
        if _content_identity(stored.symbol, captures) != stored.content_identity:
            raise ValueError

        claims = manifest["claims"]
        if claims != {
            "tradeStream": _fixed_claims("sampled_trade_stream"),
            "orderbookSnapshot": _fixed_claims(
                "sampled_orderbook_snapshot"
            ),
        }:
            raise ValueError
        canonical_artifacts = manifest["canonicalArtifacts"]
        if not isinstance(canonical_artifacts, dict) or set(
            canonical_artifacts
        ) != {"trades", "orderbookLevels"}:
            raise ValueError
        _verify_parquet_artifact(
            stored.trades_path,
            canonical_artifacts["trades"],
            _TRADES_PATH,
            _TRADE_SCHEMA,
        )
        _verify_parquet_artifact(
            stored.orderbook_path,
            canonical_artifacts["orderbookLevels"],
            _ORDERBOOK_PATH,
            _ORDERBOOK_SCHEMA,
        )
        _verify_trade_rows(stored.trades_path, stored.symbol, captures[0])
        _verify_orderbook_rows(
            stored.orderbook_path,
            stored.symbol,
            captures[1],
            manifest["orderbookSnapshot"],
        )
        expected_trade_stream, expected_orderbook_snapshot = (
            _reconstruct_success_evidence(stored.symbol, captures)
        )
        if (
            not parquet.read_table(stored.trades_path).equals(
                _trade_table(expected_trade_stream)
            )
            or not parquet.read_table(stored.orderbook_path).equals(
                _orderbook_table(expected_orderbook_snapshot)
            )
        ):
            raise ValueError

    def _verify_failure_evidence(
        self,
        stored: StoredForwardFailureEvidence,
    ) -> None:
        self._require_root()
        if not isinstance(stored, StoredForwardFailureEvidence):
            raise ValueError
        expected_directory = (
            self._root
            / "failure-evidence"
            / stored.symbol
            / stored.evidence_digest
        )
        if (
            stored.evidence_directory != expected_directory
            or stored.manifest_path != expected_directory / _MANIFEST_PATH
            or stored.manifest_sha256_path
            != expected_directory / _MANIFEST_SHA256_PATH
            or _SHA256_PATTERN.fullmatch(stored.evidence_digest) is None
        ):
            raise ValueError
        _require_real_private_directory(expected_directory)
        _require_real_private_directory(expected_directory / "raw")
        for raw_path in stored.raw_paths:
            if raw_path.parent != expected_directory / "raw":
                raise ValueError

        manifest_bytes = stored.manifest_path.read_bytes()
        if (
            stored.manifest_sha256_path.read_bytes()
            != _sidecar_bytes(hashlib.sha256(manifest_bytes).hexdigest())
        ):
            raise ValueError
        manifest = _load_canonical_json(manifest_bytes)
        if not isinstance(manifest, dict) or set(manifest) != {
            "schemaVersion",
            "identityDomain",
            "evidenceDigest",
            "symbol",
            "errorCode",
            "captureEvidence",
        }:
            raise ValueError
        if (
            manifest["schemaVersion"] != _FAILURE_SCHEMA_VERSION
            or manifest["identityDomain"] != _FAILURE_IDENTITY_DOMAIN
            or manifest["evidenceDigest"] != stored.evidence_digest
            or manifest["symbol"] != stored.symbol
            or type(manifest["errorCode"]) is not str
            or _ERROR_CODE_PATTERN.fullmatch(manifest["errorCode"]) is None
        ):
            raise ValueError
        capture_evidence = manifest["captureEvidence"]
        if not isinstance(capture_evidence, list):
            raise ValueError
        exact_paths: list[Path] = []
        identity_captures: list[dict[str, object]] = []
        for ordinal, evidence in enumerate(capture_evidence):
            identity_capture, raw_path = _verify_failure_capture_evidence(
                expected_directory,
                stored.symbol,
                ordinal,
                evidence,
            )
            identity_captures.append(identity_capture)
            if raw_path is not None:
                exact_paths.append(raw_path)
        if stored.raw_paths != tuple(exact_paths):
            raise ValueError
        expected_paths = frozenset(
            {
                *(path.relative_to(expected_directory) for path in exact_paths),
                _MANIFEST_PATH,
                _MANIFEST_SHA256_PATH,
            }
        )
        actual_paths = frozenset(
            path.relative_to(expected_directory)
            for path in expected_directory.rglob("*")
            if path.is_file() or path.is_symlink()
        )
        if actual_paths != expected_paths:
            raise ValueError
        for path in actual_paths:
            _require_regular_private_file(expected_directory / path)
        expected_digest = _failure_evidence_digest(
            stored.symbol,
            manifest["errorCode"],
            identity_captures,
        )
        if expected_digest != stored.evidence_digest:
            raise ValueError

    def _verified_identical_archive(
        self,
        prepared: _PreparedArchive,
    ) -> StoredForwardArchive:
        self.verify_archive(prepared.stored)
        expected_files = {
            relative_path: body
            for relative_path, body in prepared.artifact_bytes
        }
        expected_files[_MANIFEST_PATH] = prepared.manifest_bytes
        expected_files[_MANIFEST_SHA256_PATH] = _sidecar_bytes(
            hashlib.sha256(prepared.manifest_bytes).hexdigest()
        )
        if any(
            (prepared.stored.archive_directory / relative_path).read_bytes()
            != body
            for relative_path, body in expected_files.items()
        ):
            raise ForwardArchiveError("forward_archive_conflict")
        return prepared.stored

    def _verified_identical_failure_evidence(
        self,
        prepared: _PreparedFailureEvidence,
    ) -> StoredForwardFailureEvidence:
        self.verify_failure_evidence(prepared.stored)
        expected_files = {
            relative_path: body
            for relative_path, body in prepared.artifact_bytes
        }
        expected_files[_MANIFEST_PATH] = prepared.manifest_bytes
        expected_files[_MANIFEST_SHA256_PATH] = _sidecar_bytes(
            hashlib.sha256(prepared.manifest_bytes).hexdigest()
        )
        if any(
            (prepared.stored.evidence_directory / relative_path).read_bytes()
            != body
            for relative_path, body in expected_files.items()
        ):
            raise ForwardArchiveError("forward_failure_evidence_conflict")
        return prepared.stored

    def _write_new(self, path: Path, body: bytes) -> None:
        self._require_capacity()
        try:
            with path.open("xb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                destination.write(body)
        except FileExistsError:
            raise ForwardArchiveError("forward_archive_conflict") from None
        except OSError:
            raise ForwardArchiveError("forward_archive_write_failed") from None

    def _require_capacity(self) -> None:
        self._require_root()
        try:
            available = self._free_bytes(self._root)
        except Exception:
            raise ForwardArchiveError("blocked_storage_capacity") from None
        if type(available) is not int or available < _MINIMUM_FREE_BYTES:
            raise ForwardArchiveError("blocked_storage_capacity")

    def _require_root(self) -> None:
        if _private_root_identity(self._root) != self._root_identity:
            raise ForwardArchiveError("forward_storage_root_invalid")


def _prepare_archive(
    root: Path,
    trade_stream: SampledTradeStream,
    orderbook_snapshot: SampledOrderbookSnapshot,
) -> _PreparedArchive:
    symbol, captures = _validate_success_evidence(
        trade_stream,
        orderbook_snapshot,
    )
    raw_bodies = tuple(_capture_body(capture) for capture in captures)
    compressor = zstandard.ZstdCompressor(level=9)
    compressed_bodies = tuple(compressor.compress(body) for body in raw_bodies)
    trade_table = _trade_table(trade_stream)
    orderbook_table = _orderbook_table(orderbook_snapshot)
    trade_bytes = _parquet_bytes(trade_table)
    orderbook_bytes = _parquet_bytes(orderbook_table)
    content_identity = _content_identity(symbol, captures)
    stored = _stored_archive(root, symbol, content_identity)
    raw_artifacts = [
        _raw_artifact_body(
            ordinal,
            capture,
            raw_body,
            compressed,
        )
        for ordinal, (capture, raw_body, compressed) in enumerate(
            zip(captures, raw_bodies, compressed_bodies, strict=True)
        )
    ]
    manifest = {
        "schemaVersion": _SCHEMA_VERSION,
        "identityDomain": _IDENTITY_DOMAIN,
        "contentIdentity": content_identity,
        "symbol": symbol,
        "claims": {
            "tradeStream": _claims(trade_stream),
            "orderbookSnapshot": _claims(orderbook_snapshot),
        },
        "orderbookSnapshot": {
            "sourceTimestamp": orderbook_snapshot.source_timestamp,
            "normalizedEventAt": orderbook_snapshot.normalized_event_at,
            "receivedAt": orderbook_snapshot.received_at,
            "currency": orderbook_snapshot.currency,
        },
        "rawArtifacts": raw_artifacts,
        "canonicalArtifacts": {
            "trades": _parquet_artifact_body(
                _TRADES_PATH,
                trade_table.num_rows,
                trade_bytes,
            ),
            "orderbookLevels": _parquet_artifact_body(
                _ORDERBOOK_PATH,
                orderbook_table.num_rows,
                orderbook_bytes,
            ),
        },
    }
    artifact_bytes = tuple(
        (
            Path(f"raw/{ordinal:06d}.json.zst"),
            compressed,
        )
        for ordinal, compressed in enumerate(compressed_bodies)
    ) + (
        (_TRADES_PATH, trade_bytes),
        (_ORDERBOOK_PATH, orderbook_bytes),
    )
    return _PreparedArchive(
        stored=stored,
        artifact_bytes=artifact_bytes,
        manifest_bytes=_canonical_json_bytes(manifest),
    )


def _prepare_failure_evidence(
    root: Path,
    symbol: object,
    error_code: object,
    captures: object,
) -> _PreparedFailureEvidence:
    if (
        not forward._valid_symbol(symbol)
        or type(error_code) is not str
        or _ERROR_CODE_PATTERN.fullmatch(error_code) is None
        or type(captures) is not tuple
        or any(not isinstance(capture, RawHttpCapture) for capture in captures)
    ):
        raise ForwardArchiveError("forward_failure_evidence_invalid")
    compressor = zstandard.ZstdCompressor(level=9)
    capture_evidence: list[dict[str, object]] = []
    identity_captures: list[dict[str, object]] = []
    artifact_bytes: list[tuple[Path, bytes]] = []
    raw_ordinals: list[int] = []
    for ordinal, capture in enumerate(captures):
        identity_capture = _failure_capture_identity(
            symbol,
            ordinal,
            capture,
        )
        identity_captures.append(identity_capture)
        if identity_capture["rawAvailability"] == "redacted_at_auth_boundary":
            capture_evidence.append(identity_capture)
            continue
        raw_body = _capture_body(capture)
        compressed = compressor.compress(raw_body)
        relative_path = Path(f"raw/{ordinal:06d}.json.zst")
        capture_evidence.append(
            {
                **identity_capture,
                "path": relative_path.as_posix(),
                "uncompressedBytes": len(raw_body),
                "storedBytes": len(compressed),
                "storedSha256": hashlib.sha256(compressed).hexdigest(),
            }
        )
        artifact_bytes.append((relative_path, compressed))
        raw_ordinals.append(ordinal)
    evidence_digest = _failure_evidence_digest(
        symbol,
        error_code,
        identity_captures,
    )
    stored = _stored_failure_evidence(
        root,
        symbol,
        evidence_digest,
        tuple(raw_ordinals),
    )
    manifest = {
        "schemaVersion": _FAILURE_SCHEMA_VERSION,
        "identityDomain": _FAILURE_IDENTITY_DOMAIN,
        "evidenceDigest": evidence_digest,
        "symbol": symbol,
        "errorCode": error_code,
        "captureEvidence": capture_evidence,
    }
    return _PreparedFailureEvidence(
        stored=stored,
        artifact_bytes=tuple(artifact_bytes),
        manifest_bytes=_canonical_json_bytes(manifest),
    )


def _failure_capture_identity(
    symbol: str,
    ordinal: int,
    capture: RawHttpCapture,
) -> dict[str, object]:
    if capture.endpoint_id == "oauth_client_credentials_v1":
        _validate_auth_redacted_capture(capture)
        raw_availability = "redacted_at_auth_boundary"
    elif capture.endpoint_id == forward._TRADES_ENDPOINT_ID:
        _validate_capture(
            capture,
            symbol,
            forward._TRADES_ENDPOINT_ID,
            forward._trades_url(symbol),
            success=False,
        )
        _capture_body(capture)
        raw_availability = "exact"
    elif capture.endpoint_id == forward._ORDERBOOK_ENDPOINT_ID:
        _validate_capture(
            capture,
            symbol,
            forward._ORDERBOOK_ENDPOINT_ID,
            forward._orderbook_url(symbol),
            success=False,
        )
        _capture_body(capture)
        raw_availability = "exact"
    else:
        raise ForwardArchiveError("forward_failure_evidence_invalid")
    return {
        "captureOrdinal": ordinal,
        "endpointId": capture.endpoint_id,
        "method": capture.method,
        "sanitizedUrl": capture.sanitized_url,
        "query": _pairs_body(capture.query),
        "status": capture.status,
        "responseHeaders": _pairs_body(capture.headers),
        "receivedAt": capture.received_at,
        "bodySha256": capture.body_sha256,
        "rawAvailability": raw_availability,
    }


def _validate_auth_redacted_capture(capture: RawHttpCapture) -> None:
    if (
        capture.method != "POST"
        or capture.sanitized_url != toss_boundary._OAUTH_URL
        or capture.query != ()
        or type(capture.status) is not int
        or not 100 <= capture.status <= 599
        or not _canonical_utc(capture.received_at)
        or capture.body_base64 != ""
        or _SHA256_PATTERN.fullmatch(capture.body_sha256) is None
        or not _valid_capture_headers(
            capture.headers,
            allowed_headers=_AUTH_CAPTURE_HEADERS,
        )
    ):
        raise ForwardArchiveError("forward_failure_evidence_invalid")


def _failure_evidence_digest(
    symbol: str,
    error_code: str,
    identity_captures: list[dict[str, object]],
) -> str:
    identity = {
        "schemaVersion": _FAILURE_SCHEMA_VERSION,
        "identityDomain": _FAILURE_IDENTITY_DOMAIN,
        "symbol": symbol,
        "errorCode": error_code,
        "captureEvidence": identity_captures,
    }
    return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def _stored_failure_evidence(
    root: Path,
    symbol: str,
    evidence_digest: str,
    raw_ordinals: tuple[int, ...],
) -> StoredForwardFailureEvidence:
    evidence_directory = root / "failure-evidence" / symbol / evidence_digest
    return StoredForwardFailureEvidence(
        symbol=symbol,
        evidence_digest=evidence_digest,
        evidence_directory=evidence_directory,
        raw_paths=tuple(
            evidence_directory / f"raw/{ordinal:06d}.json.zst"
            for ordinal in raw_ordinals
        ),
        manifest_path=evidence_directory / _MANIFEST_PATH,
        manifest_sha256_path=evidence_directory / _MANIFEST_SHA256_PATH,
    )


def _validate_success_evidence(
    trade_stream: object,
    orderbook_snapshot: object,
) -> tuple[str, tuple[RawHttpCapture, RawHttpCapture]]:
    if (
        not isinstance(trade_stream, SampledTradeStream)
        or not isinstance(orderbook_snapshot, SampledOrderbookSnapshot)
        or trade_stream.symbol != orderbook_snapshot.symbol
        or type(trade_stream.captures) is not tuple
        or len(trade_stream.captures) != 1
        or not isinstance(trade_stream.captures[0], RawHttpCapture)
        or not isinstance(orderbook_snapshot.capture, RawHttpCapture)
        or _claims(trade_stream)
        != _fixed_claims("sampled_trade_stream")
        or _claims(orderbook_snapshot)
        != _fixed_claims("sampled_orderbook_snapshot")
    ):
        raise ForwardArchiveError("forward_archive_input_invalid")
    symbol = trade_stream.symbol
    trade_capture = trade_stream.captures[0]
    orderbook_capture = orderbook_snapshot.capture
    _validate_capture(
        trade_capture,
        symbol,
        forward._TRADES_ENDPOINT_ID,
        forward._trades_url(symbol),
        success=True,
    )
    _validate_capture(
        orderbook_capture,
        symbol,
        forward._ORDERBOOK_ENDPOINT_ID,
        forward._orderbook_url(symbol),
        success=True,
    )
    _validate_trade_observations(trade_stream, trade_capture)
    _validate_orderbook_snapshot(orderbook_snapshot, orderbook_capture)
    expected_trade_stream, expected_orderbook_snapshot = (
        _reconstruct_success_evidence(
            symbol,
            (trade_capture, orderbook_capture),
        )
    )
    if (
        trade_stream != expected_trade_stream
        or orderbook_snapshot != expected_orderbook_snapshot
    ):
        raise ForwardArchiveError("forward_archive_input_invalid")
    return symbol, (trade_capture, orderbook_capture)


def _reconstruct_success_evidence(
    symbol: str,
    captures: tuple[RawHttpCapture, RawHttpCapture],
) -> tuple[SampledTradeStream, SampledOrderbookSnapshot]:
    trade_capture, orderbook_capture = captures
    try:
        trade_value = forward._parse_json(
            _capture_body(trade_capture),
            trade_capture,
        )
        orderbook_value = forward._parse_json(
            _capture_body(orderbook_capture),
            orderbook_capture,
        )
        trade_stream = SampledTradeStream(
            symbol=symbol,
            observations=forward._parse_trades(
                trade_value,
                trade_capture,
                0,
            ),
            captures=(trade_capture,),
        )
        orderbook_snapshot = forward._parse_orderbook(
            orderbook_value,
            symbol,
            orderbook_capture,
            1,
        )
    except (
        CollectorError,
        ForwardArchiveError,
        forward.ForwardMicrostructureError,
    ):
        raise ForwardArchiveError("forward_archive_input_invalid") from None
    return trade_stream, orderbook_snapshot


def _validate_capture(
    capture: RawHttpCapture,
    symbol: str,
    endpoint_id: str,
    expected_url: str,
    *,
    success: bool,
) -> None:
    del symbol
    expected_query = tuple(
        parse_qsl(
            urlsplit(expected_url).query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    )
    if (
        capture.endpoint_id != endpoint_id
        or capture.method != "GET"
        or capture.sanitized_url != expected_url
        or capture.query != expected_query
        or type(capture.status) is not int
        or not 100 <= capture.status <= 599
        or (success and not 200 <= capture.status < 300)
        or not _canonical_utc(capture.received_at)
        or not _valid_capture_headers(capture.headers)
    ):
        raise ForwardArchiveError("forward_archive_input_invalid")


def _capture_body(capture: RawHttpCapture) -> bytes:
    try:
        body = base64.b64decode(capture.body_base64, validate=True)
    except (TypeError, ValueError):
        raise ForwardArchiveError("forward_archive_input_invalid") from None
    if hashlib.sha256(body).hexdigest() != capture.body_sha256:
        raise ForwardArchiveError("forward_archive_input_invalid")
    return body


def _validate_trade_observations(
    stream: SampledTradeStream,
    capture: RawHttpCapture,
) -> None:
    if type(stream.observations) is not tuple:
        raise ForwardArchiveError("forward_archive_input_invalid")
    for observation in stream.observations:
        if (
            not isinstance(observation, SampledTradeObservation)
            or not _valid_scalar(observation.price)
            or not _valid_scalar(observation.volume)
            or observation.source_body_sha256 != capture.body_sha256
            or observation.source_capture_ordinal != 0
            or type(observation.source_row_index) is not int
            or observation.source_row_index < 0
            or observation.received_at != capture.received_at
            or observation.source_occurrence
            != (capture.body_sha256, 0, observation.source_row_index)
            or type(observation.ambiguous_occurrences) is not tuple
        ):
            raise ForwardArchiveError("forward_archive_input_invalid")


def _validate_orderbook_snapshot(
    snapshot: SampledOrderbookSnapshot,
    capture: RawHttpCapture,
) -> None:
    if (
        snapshot.source_body_sha256 != capture.body_sha256
        or snapshot.source_capture_ordinal != 1
        or snapshot.source_row_index != 0
        or snapshot.received_at != capture.received_at
        or type(snapshot.asks) is not tuple
        or type(snapshot.bids) is not tuple
    ):
        raise ForwardArchiveError("forward_archive_input_invalid")
    expected_row_index = 0
    for side, levels in (("ask", snapshot.asks), ("bid", snapshot.bids)):
        for level_index, level in enumerate(levels):
            if (
                not isinstance(level, SampledOrderbookLevel)
                or level.side != side
                or level.level != level_index
                or not _valid_scalar(level.price)
                or not _valid_scalar(level.volume)
                or level.source_body_sha256 != capture.body_sha256
                or level.source_capture_ordinal != 1
                or level.source_row_index != expected_row_index
            ):
                raise ForwardArchiveError("forward_archive_input_invalid")
            expected_row_index += 1


def _valid_scalar(value: object) -> bool:
    return (
        isinstance(value, CanonicalScalar)
        and value.kind == "json_string"
        and isinstance(value.text, str)
        and bool(value.text)
        and value.text == value.text.strip()
    )


def _claims(value: object) -> dict[str, str]:
    try:
        return {
            "measurementKind": value.measurement_kind,
            "completeness": value.completeness,
            "aggressorSideStatus": value.aggressor_side_status,
            "orderIdStatus": value.order_id_status,
            "ofiStatus": value.ofi_status,
        }
    except AttributeError:
        raise ForwardArchiveError("forward_archive_input_invalid") from None


def _fixed_claims(measurement_kind: str) -> dict[str, str]:
    return {
        "measurementKind": measurement_kind,
        "completeness": "not_complete_exchange_tape",
        "aggressorSideStatus": "not_identifiable",
        "orderIdStatus": "not_available",
        "ofiStatus": "not_identifiable",
    }


def _trade_table(stream: SampledTradeStream) -> pa.Table:
    rows = [
        {
            "symbol": stream.symbol,
            "measurement_kind": stream.measurement_kind,
            "completeness": stream.completeness,
            "aggressor_side_status": stream.aggressor_side_status,
            "order_id_status": stream.order_id_status,
            "ofi_status": stream.ofi_status,
            "price_lexeme": observation.price.text,
            "volume_lexeme": observation.volume.text,
            "numeric_fidelity": "json_string_lexeme",
            "source_timestamp": observation.source_timestamp,
            "normalized_event_at": observation.normalized_event_at,
            "received_at": observation.received_at,
            "currency": observation.currency,
            "source_body_sha256": observation.source_body_sha256,
            "source_capture_ordinal": observation.source_capture_ordinal,
            "source_row_index": observation.source_row_index,
            "duplicate_status": observation.duplicate_status,
            "ambiguous_occurrences_json": _canonical_json_bytes(
                [list(occurrence) for occurrence in observation.ambiguous_occurrences]
            ).decode("utf-8"),
        }
        for observation in stream.observations
    ]
    return pa.Table.from_pylist(rows, schema=_TRADE_SCHEMA)


def _orderbook_table(snapshot: SampledOrderbookSnapshot) -> pa.Table:
    rows = [
        {
            "symbol": snapshot.symbol,
            "measurement_kind": snapshot.measurement_kind,
            "completeness": snapshot.completeness,
            "aggressor_side_status": snapshot.aggressor_side_status,
            "order_id_status": snapshot.order_id_status,
            "ofi_status": snapshot.ofi_status,
            "source_timestamp": snapshot.source_timestamp,
            "normalized_event_at": snapshot.normalized_event_at,
            "received_at": snapshot.received_at,
            "currency": snapshot.currency,
            "side": level.side,
            "level": level.level,
            "price_lexeme": level.price.text,
            "volume_lexeme": level.volume.text,
            "numeric_fidelity": "json_string_lexeme",
            "source_body_sha256": level.source_body_sha256,
            "source_capture_ordinal": level.source_capture_ordinal,
            "source_row_index": level.source_row_index,
        }
        for level in snapshot.asks + snapshot.bids
    ]
    return pa.Table.from_pylist(rows, schema=_ORDERBOOK_SCHEMA)


def _parquet_bytes(table: pa.Table) -> bytes:
    destination = pa.BufferOutputStream()
    parquet.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )
    return destination.getvalue().to_pybytes()


def _content_identity(
    symbol: str,
    captures: tuple[RawHttpCapture, RawHttpCapture],
) -> str:
    identity = {
        "schemaVersion": _SCHEMA_VERSION,
        "identityDomain": _IDENTITY_DOMAIN,
        "symbol": symbol,
        "captures": [
            {
                "endpointId": capture.endpoint_id,
                "receivedAt": capture.received_at,
                "bodySha256": capture.body_sha256,
            }
            for capture in captures
        ],
    }
    return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def _stored_archive(
    root: Path,
    symbol: str,
    content_identity: str,
) -> StoredForwardArchive:
    archive_directory = root / _SUCCESS_DIRECTORY / content_identity
    return StoredForwardArchive(
        symbol=symbol,
        content_identity=content_identity,
        archive_directory=archive_directory,
        raw_paths=tuple(
            archive_directory / f"raw/{ordinal:06d}.json.zst"
            for ordinal in range(2)
        ),
        trades_path=archive_directory / _TRADES_PATH,
        orderbook_path=archive_directory / _ORDERBOOK_PATH,
        manifest_path=archive_directory / _MANIFEST_PATH,
        manifest_sha256_path=archive_directory / _MANIFEST_SHA256_PATH,
    )


def _raw_artifact_body(
    ordinal: int,
    capture: RawHttpCapture,
    raw_body: bytes,
    compressed: bytes,
) -> dict[str, object]:
    return {
        "captureOrdinal": ordinal,
        "endpointId": capture.endpoint_id,
        "method": capture.method,
        "sanitizedUrl": capture.sanitized_url,
        "query": _pairs_body(capture.query),
        "status": capture.status,
        "responseHeaders": _pairs_body(capture.headers),
        "receivedAt": capture.received_at,
        "path": f"raw/{ordinal:06d}.json.zst",
        "uncompressedBytes": len(raw_body),
        "uncompressedSha256": hashlib.sha256(raw_body).hexdigest(),
        "storedBytes": len(compressed),
        "storedSha256": hashlib.sha256(compressed).hexdigest(),
    }


def _parquet_artifact_body(
    path: Path,
    row_count: int,
    body: bytes,
) -> dict[str, object]:
    return {
        "compression": "ZSTD",
        "path": path.as_posix(),
        "rowCount": row_count,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _pairs_body(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in pairs]


def _valid_capture_headers(
    value: object,
    *,
    allowed_headers: frozenset[str] = _ALLOWED_CAPTURE_HEADERS,
) -> bool:
    if type(value) is not tuple:
        return False
    names: set[str] = set()
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            return False
        name, header_value = pair
        if (
            type(name) is not str
            or name not in allowed_headers
            or name in names
            or type(header_value) is not str
            or any(character in header_value for character in "\r\n\x00")
        ):
            return False
        names.add(name)
    return True


def _verify_failure_capture_evidence(
    evidence_directory: Path,
    symbol: str,
    ordinal: int,
    value: object,
) -> tuple[dict[str, object], Path | None]:
    common_fields = {
        "captureOrdinal",
        "endpointId",
        "method",
        "sanitizedUrl",
        "query",
        "status",
        "responseHeaders",
        "receivedAt",
        "bodySha256",
        "rawAvailability",
    }
    if not isinstance(value, dict) or not common_fields.issubset(value):
        raise ValueError
    if (
        value["captureOrdinal"] != ordinal
        or type(value["endpointId"]) is not str
        or type(value["method"]) is not str
        or type(value["sanitizedUrl"]) is not str
        or type(value["status"]) is not int
        or not 100 <= value["status"] <= 599
        or not _canonical_utc(value["receivedAt"])
        or _SHA256_PATTERN.fullmatch(value["bodySha256"]) is None
    ):
        raise ValueError
    query = _pairs_from_body(value["query"])
    headers = _pairs_from_body(value["responseHeaders"])
    identity_capture = {
        field: value[field]
        for field in (
            "captureOrdinal",
            "endpointId",
            "method",
            "sanitizedUrl",
            "query",
            "status",
            "responseHeaders",
            "receivedAt",
            "bodySha256",
            "rawAvailability",
        )
    }
    if value["rawAvailability"] == "redacted_at_auth_boundary":
        if set(value) != common_fields:
            raise ValueError
        capture = RawHttpCapture(
            endpoint_id=value["endpointId"],
            method=value["method"],
            sanitized_url=value["sanitizedUrl"],
            query=query,
            status=value["status"],
            headers=headers,
            received_at=value["receivedAt"],
            body_base64="",
            body_sha256=value["bodySha256"],
        )
        try:
            _validate_auth_redacted_capture(capture)
        except ForwardArchiveError:
            raise ValueError from None
        return identity_capture, None
    exact_fields = common_fields | {
        "path",
        "uncompressedBytes",
        "storedBytes",
        "storedSha256",
    }
    if (
        value["rawAvailability"] != "exact"
        or set(value) != exact_fields
        or value["path"] != f"raw/{ordinal:06d}.json.zst"
        or type(value["uncompressedBytes"]) is not int
        or type(value["storedBytes"]) is not int
        or _SHA256_PATTERN.fullmatch(value["storedSha256"]) is None
    ):
        raise ValueError
    raw_path = evidence_directory / value["path"]
    compressed = raw_path.read_bytes()
    if (
        len(compressed) != value["storedBytes"]
        or hashlib.sha256(compressed).hexdigest() != value["storedSha256"]
    ):
        raise ValueError
    raw_body = zstandard.ZstdDecompressor().decompress(
        compressed,
        max_output_size=value["uncompressedBytes"],
    )
    if (
        len(raw_body) != value["uncompressedBytes"]
        or hashlib.sha256(raw_body).hexdigest() != value["bodySha256"]
    ):
        raise ValueError
    capture = RawHttpCapture(
        endpoint_id=value["endpointId"],
        method=value["method"],
        sanitized_url=value["sanitizedUrl"],
        query=query,
        status=value["status"],
        headers=headers,
        received_at=value["receivedAt"],
        body_base64=base64.b64encode(raw_body).decode("ascii"),
        body_sha256=value["bodySha256"],
    )
    try:
        _failure_capture_identity(symbol, ordinal, capture)
    except ForwardArchiveError:
        raise ValueError from None
    return identity_capture, raw_path


def _require_archive_layout(stored: StoredForwardArchive) -> None:
    _require_real_private_directory(stored.archive_directory)
    _require_real_private_directory(stored.archive_directory / "raw")
    _require_real_private_directory(stored.archive_directory / "canonical")
    expected_paths = frozenset(
        {
            Path("raw/000000.json.zst"),
            Path("raw/000001.json.zst"),
            _TRADES_PATH,
            _ORDERBOOK_PATH,
            _MANIFEST_PATH,
            _MANIFEST_SHA256_PATH,
        }
    )
    actual_paths = frozenset(
        path.relative_to(stored.archive_directory)
        for path in stored.archive_directory.rglob("*")
        if path.is_file() or path.is_symlink()
    )
    if actual_paths != expected_paths:
        raise ValueError
    for path in actual_paths:
        _require_regular_private_file(stored.archive_directory / path)


def _verify_raw_artifact(
    path: Path,
    value: object,
    ordinal: int,
    symbol: str,
) -> RawHttpCapture:
    if not isinstance(value, dict) or set(value) != {
        "captureOrdinal",
        "endpointId",
        "method",
        "sanitizedUrl",
        "query",
        "status",
        "responseHeaders",
        "receivedAt",
        "path",
        "uncompressedBytes",
        "uncompressedSha256",
        "storedBytes",
        "storedSha256",
    }:
        raise ValueError
    expected_endpoint = (
        forward._TRADES_ENDPOINT_ID
        if ordinal == 0
        else forward._ORDERBOOK_ENDPOINT_ID
    )
    expected_url = (
        forward._trades_url(symbol)
        if ordinal == 0
        else forward._orderbook_url(symbol)
    )
    if (
        value["captureOrdinal"] != ordinal
        or value["endpointId"] != expected_endpoint
        or value["method"] != "GET"
        or value["sanitizedUrl"] != expected_url
        or value["path"] != f"raw/{ordinal:06d}.json.zst"
        or type(value["status"]) is not int
        or not 200 <= value["status"] < 300
        or not _canonical_utc(value["receivedAt"])
        or type(value["uncompressedBytes"]) is not int
        or type(value["storedBytes"]) is not int
        or _SHA256_PATTERN.fullmatch(value["uncompressedSha256"]) is None
        or _SHA256_PATTERN.fullmatch(value["storedSha256"]) is None
    ):
        raise ValueError
    query = _pairs_from_body(value["query"])
    headers = _pairs_from_body(value["responseHeaders"])
    expected_query = tuple(
        parse_qsl(
            urlsplit(expected_url).query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    )
    if query != expected_query or not _valid_capture_headers(headers):
        raise ValueError
    compressed = path.read_bytes()
    if (
        len(compressed) != value["storedBytes"]
        or hashlib.sha256(compressed).hexdigest() != value["storedSha256"]
    ):
        raise ValueError
    raw_body = zstandard.ZstdDecompressor().decompress(
        compressed,
        max_output_size=value["uncompressedBytes"],
    )
    if (
        len(raw_body) != value["uncompressedBytes"]
        or hashlib.sha256(raw_body).hexdigest()
        != value["uncompressedSha256"]
    ):
        raise ValueError
    return RawHttpCapture(
        endpoint_id=value["endpointId"],
        method=value["method"],
        sanitized_url=value["sanitizedUrl"],
        query=query,
        status=value["status"],
        headers=headers,
        received_at=value["receivedAt"],
        body_base64=base64.b64encode(raw_body).decode("ascii"),
        body_sha256=value["uncompressedSha256"],
    )


def _pairs_from_body(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError
    pairs: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, dict) or set(pair) != {"name", "value"}:
            raise ValueError
        name = pair["name"]
        pair_value = pair["value"]
        if type(name) is not str or type(pair_value) is not str:
            raise ValueError
        pairs.append((name, pair_value))
    return tuple(pairs)


def _verify_parquet_artifact(
    path: Path,
    value: object,
    expected_path: Path,
    expected_schema: pa.Schema,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "compression",
        "path",
        "rowCount",
        "sha256",
    }:
        raise ValueError
    body = path.read_bytes()
    if (
        value["compression"] != "ZSTD"
        or value["path"] != expected_path.as_posix()
        or type(value["rowCount"]) is not int
        or hashlib.sha256(body).hexdigest() != value["sha256"]
    ):
        raise ValueError
    parquet_file = parquet.ParquetFile(path)
    metadata = parquet_file.metadata
    if metadata.num_rows != value["rowCount"]:
        raise ValueError
    for row_group_index in range(metadata.num_row_groups):
        row_group = metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            if row_group.column(column_index).compression != "ZSTD":
                raise ValueError
    if parquet_file.schema_arrow != expected_schema:
        raise ValueError


def _verify_trade_rows(
    path: Path,
    symbol: str,
    capture: RawHttpCapture,
) -> None:
    for row in parquet.read_table(path).to_pylist():
        if (
            row["symbol"] != symbol
            or row["measurement_kind"] != "sampled_trade_stream"
            or row["completeness"] != "not_complete_exchange_tape"
            or row["aggressor_side_status"] != "not_identifiable"
            or row["order_id_status"] != "not_available"
            or row["ofi_status"] != "not_identifiable"
            or row["numeric_fidelity"] != "json_string_lexeme"
            or row["source_body_sha256"] != capture.body_sha256
            or row["source_capture_ordinal"] != 0
            or type(row["source_row_index"]) is not int
            or row["source_row_index"] < 0
            or row["received_at"] != capture.received_at
        ):
            raise ValueError
        _load_canonical_json_list(row["ambiguous_occurrences_json"])


def _verify_orderbook_rows(
    path: Path,
    symbol: str,
    capture: RawHttpCapture,
    snapshot: object,
) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "sourceTimestamp",
        "normalizedEventAt",
        "receivedAt",
        "currency",
    }:
        raise ValueError
    if snapshot["receivedAt"] != capture.received_at:
        raise ValueError
    seen: dict[str, list[int]] = {"ask": [], "bid": []}
    for row_index, row in enumerate(parquet.read_table(path).to_pylist()):
        if (
            row["symbol"] != symbol
            or row["measurement_kind"] != "sampled_orderbook_snapshot"
            or row["completeness"] != "not_complete_exchange_tape"
            or row["aggressor_side_status"] != "not_identifiable"
            or row["order_id_status"] != "not_available"
            or row["ofi_status"] != "not_identifiable"
            or row["source_timestamp"] != snapshot["sourceTimestamp"]
            or row["normalized_event_at"] != snapshot["normalizedEventAt"]
            or row["received_at"] != snapshot["receivedAt"]
            or row["currency"] != snapshot["currency"]
            or row["side"] not in seen
            or row["numeric_fidelity"] != "json_string_lexeme"
            or row["source_body_sha256"] != capture.body_sha256
            or row["source_capture_ordinal"] != 1
            or row["source_row_index"] != row_index
        ):
            raise ValueError
        seen[row["side"]].append(row["level"])
    if any(levels != list(range(len(levels))) for levels in seen.values()):
        raise ValueError


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_canonical_json(value: bytes) -> object:
    parsed = json.loads(value)
    if _canonical_json_bytes(parsed) != value:
        raise ValueError
    return parsed


def _load_canonical_json_list(value: object) -> list[object]:
    if not isinstance(value, str):
        raise ValueError
    parsed = _load_canonical_json(value.encode("utf-8"))
    if not isinstance(parsed, list):
        raise ValueError
    return parsed


def _sidecar_bytes(sha256: str) -> bytes:
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise ValueError
    return f"{sha256}\n".encode("ascii")


def _canonical_utc(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError, OverflowError):
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
        raise ForwardArchiveError("forward_storage_root_invalid")
    try:
        root_stat = root.lstat()
    except OSError:
        raise ForwardArchiveError("forward_storage_root_invalid") from None
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or stat.S_IMODE(root_stat.st_mode) & 0o077
    ):
        raise ForwardArchiveError("forward_storage_root_invalid")
    return root_stat.st_dev, root_stat.st_ino


def _require_real_private_directory(path: Path) -> None:
    value = path.lstat()
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or value.st_uid != os.getuid()
        or stat.S_IMODE(value.st_mode) & 0o077
    ):
        raise ValueError


def _require_regular_private_file(path: Path) -> None:
    value = path.lstat()
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or value.st_uid != os.getuid()
        or stat.S_IMODE(value.st_mode) & 0o077
    ):
        raise ValueError


def _disk_free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free
