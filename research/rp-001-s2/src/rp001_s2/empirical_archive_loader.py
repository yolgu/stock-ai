"""Verified loading of explicit daily minute scopes for empirical research."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pyarrow.parquet as parquet

from rp001.toss_research_collector import CanonicalScalar
from rp001_s2.archive_contract import (
    CollectionScope,
    SampleRole,
    TOSS_PROVIDER_DATE_DAILY_FEED,
    is_supported_toss_minute_scope,
)
from rp001_s2.archive_storage import (
    AcquisitionTerminalStatus,
    ArchiveStorageError,
    CanonicalMinuteBar,
    ImmutableArchiveStorage,
    StoredArchive,
)


_ARCHIVE_SCHEMA_VERSION = "rp001-s2-immutable-minute-archive.v2"
_EVIDENCE_SCHEMA_VERSION = "rp001-s2-verified-daily-series-evidence.v1"
_CANONICAL_RELATIVE_PATH = Path("canonical/minute-bars.parquet")
_OCCURRENCE_RELATIVE_PATH = Path("canonical/minute-bar-occurrences.parquet")


class EmpiricalArchiveError(ValueError):
    """Stable refusal at the research archive boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DailyScopeLedgerStatus(str, Enum):
    LOADED = "loaded"
    PARTIAL_LOADED = "partial_loaded"
    MISSING = "missing"
    NON_RESUMABLE = "non_resumable"


@dataclass(frozen=True)
class DailyScopeLedgerEntry:
    acquisition_key: str
    symbol: str
    start_at: str
    end_at: str
    status: DailyScopeLedgerStatus
    reason: str
    row_count: int
    manifest_sha256: str | None

    def to_evidence_body(self) -> dict[str, object]:
        return {
            "acquisitionKey": self.acquisition_key,
            "symbol": self.symbol,
            "startAt": self.start_at,
            "endAt": self.end_at,
            "status": self.status.value,
            "reason": self.reason,
            "rowCount": self.row_count,
            "manifestSha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class VerifiedDailySeries:
    provider: str
    feed: str
    instrument_id: str
    symbol: str
    adjustment_mode: str
    bars: tuple[CanonicalMinuteBar, ...]
    ledger: tuple[DailyScopeLedgerEntry, ...]
    source_evidence_sha256: str


def require_development_scopes(scopes: Sequence[CollectionScope]) -> None:
    """Reject any confirmation role before reading an archive directory."""
    values = tuple(scopes)
    if any(
        isinstance(scope, CollectionScope)
        and scope.sample_role is SampleRole.CONFIRMATION
        for scope in values
    ):
        raise EmpiricalArchiveError("confirmation_archive_sealed")


def load_verified_daily_series(
    *,
    root: Path,
    scopes: Sequence[CollectionScope],
) -> VerifiedDailySeries:
    """Verify and concatenate complete daily v2 archives without imputation."""
    if not isinstance(root, Path) or not root.is_dir():
        raise EmpiricalArchiveError("archive_root_invalid")
    values = tuple(scopes)
    require_development_scopes(values)
    identity = _validate_daily_scopes(values)
    values = tuple(
        sorted(
            values,
            key=lambda scope: (
                scope.start_at,
                scope.end_at,
                scope.acquisition_key,
            ),
        )
    )
    storage = ImmutableArchiveStorage(root)
    ledger: list[DailyScopeLedgerEntry] = []
    loaded_bars: list[CanonicalMinuteBar] = []

    for scope in values:
        archive_directory = root / scope.acquisition_key
        if not archive_directory.exists():
            if _has_failure_evidence(root, scope.acquisition_key):
                raise EmpiricalArchiveError("scope_failure_evidence_present")
            ledger.append(
                _ledger_entry(
                    scope,
                    DailyScopeLedgerStatus.MISSING,
                    reason="archive_directory_missing",
                )
            )
            continue

        manifest, manifest_bytes = _read_manifest_metadata(archive_directory)
        if manifest.get("schemaVersion") != _ARCHIVE_SCHEMA_VERSION:
            if manifest.get("schemaVersion") == "rp001-s2-immutable-minute-archive.v1":
                raise EmpiricalArchiveError("v2_archive_required")
            raise EmpiricalArchiveError("archive_verification_failed")
        stored_scope = manifest.get("scope")
        if (
            isinstance(stored_scope, dict)
            and stored_scope.get("sampleRole") == SampleRole.CONFIRMATION.value
        ):
            raise EmpiricalArchiveError("confirmation_archive_sealed")
        if stored_scope != scope.to_canonical_body():
            raise EmpiricalArchiveError("archive_scope_mismatch")
        stored = _stored_archive(root, scope, manifest)
        try:
            storage.verify_archive(stored)
            completion = storage.load_resumable_completion(stored)
        except ArchiveStorageError:
            raise EmpiricalArchiveError("archive_verification_failed") from None

        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        loadable = completion.terminal_status in {
            AcquisitionTerminalStatus.COMPLETED,
            AcquisitionTerminalStatus.PARTIAL,
        }
        if not loadable:
            ledger.append(
                _ledger_entry(
                    scope,
                    DailyScopeLedgerStatus.NON_RESUMABLE,
                    reason=(
                        f"{completion.terminal_status.value}:"
                        f"{completion.completion_reason}"
                    ),
                    row_count=completion.returned_row_count,
                    manifest_sha256=manifest_sha256,
                )
            )
            continue

        bars = _reconstruct_bars(stored)
        if len(bars) != completion.returned_row_count:
            raise EmpiricalArchiveError("archive_verification_failed")
        loaded_bars.extend(bars)
        ledger_status = (
            DailyScopeLedgerStatus.LOADED
            if completion.terminal_status is AcquisitionTerminalStatus.COMPLETED
            else DailyScopeLedgerStatus.PARTIAL_LOADED
        )
        ledger.append(
            _ledger_entry(
                scope,
                ledger_status,
                reason=(
                    f"{completion.terminal_status.value}:"
                    f"{completion.completion_reason}"
                ),
                row_count=len(bars),
                manifest_sha256=manifest_sha256,
            )
        )

    bars = _merge_daily_bars(tuple(loaded_bars))
    evidence_sha256 = _series_evidence_sha256(identity, tuple(ledger))
    return VerifiedDailySeries(
        provider=identity[0],
        feed=identity[1],
        instrument_id=identity[2],
        symbol=identity[3],
        adjustment_mode=identity[4],
        bars=bars,
        ledger=tuple(ledger),
        source_evidence_sha256=evidence_sha256,
    )


def _validate_daily_scopes(
    scopes: tuple[CollectionScope, ...],
) -> tuple[str, str, str, str, str]:
    if not scopes or any(not isinstance(scope, CollectionScope) for scope in scopes):
        raise EmpiricalArchiveError("daily_scope_invalid")
    if len({scope.acquisition_key for scope in scopes}) != len(scopes):
        raise EmpiricalArchiveError("duplicate_daily_scope")
    for scope in scopes:
        if (
            not is_supported_toss_minute_scope(scope)
            or scope.provider != "toss"
            or scope.feed != TOSS_PROVIDER_DATE_DAILY_FEED
        ):
            raise EmpiricalArchiveError("daily_scope_invalid")
    identities = {
        (
            scope.provider,
            scope.feed,
            scope.instrument_id,
            scope.symbol,
            scope.adjustment_mode,
        )
        for scope in scopes
    }
    if len(identities) != 1:
        raise EmpiricalArchiveError("daily_series_scope_mismatch")
    identity = next(iter(identities))
    if identity[4] != "native":
        raise EmpiricalArchiveError("daily_scope_invalid")
    return identity


def _has_failure_evidence(root: Path, acquisition_key: str) -> bool:
    failure_directory = root / "failure-evidence" / acquisition_key
    try:
        return failure_directory.is_dir() and any(failure_directory.iterdir())
    except OSError:
        raise EmpiricalArchiveError("archive_verification_failed") from None


def _read_manifest_metadata(
    archive_directory: Path,
) -> tuple[dict[str, object], bytes]:
    try:
        manifest_bytes = (archive_directory / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise EmpiricalArchiveError("archive_verification_failed") from None
    if not isinstance(manifest, dict):
        raise EmpiricalArchiveError("archive_verification_failed")
    return manifest, manifest_bytes


def _stored_archive(
    root: Path,
    scope: CollectionScope,
    manifest: dict[str, object],
) -> StoredArchive:
    raw_artifacts = manifest.get("rawArtifacts")
    if not isinstance(raw_artifacts, list):
        raise EmpiricalArchiveError("archive_verification_failed")
    archive_directory = root / scope.acquisition_key
    return StoredArchive(
        acquisition_key=scope.acquisition_key,
        archive_directory=archive_directory,
        raw_paths=tuple(
            archive_directory / f"raw/{ordinal:06d}.json.zst"
            for ordinal in range(len(raw_artifacts))
        ),
        canonical_path=archive_directory / _CANONICAL_RELATIVE_PATH,
        occurrence_path=archive_directory / _OCCURRENCE_RELATIVE_PATH,
        manifest_path=archive_directory / "manifest.json",
        manifest_sha256_path=archive_directory / "manifest.json.sha256",
    )


def _reconstruct_bars(stored: StoredArchive) -> tuple[CanonicalMinuteBar, ...]:
    try:
        canonical_rows = parquet.read_table(stored.canonical_path).to_pylist()
        occurrence_rows = parquet.read_table(stored.occurrence_path).to_pylist()
    except Exception:
        raise EmpiricalArchiveError("archive_verification_failed") from None
    occurrences_by_event: dict[str, list[tuple[str, int, int]]] = {}
    occurrence_orders: dict[str, list[int]] = {}
    for row in occurrence_rows:
        try:
            event_start = row["event_start_utc"]
            occurrence = (
                row["raw_body_sha256"],
                row["capture_ordinal"],
                row["source_row_index"],
            )
            occurrence_order = row["occurrence_order"]
        except (KeyError, TypeError):
            raise EmpiricalArchiveError("archive_verification_failed") from None
        occurrences_by_event.setdefault(event_start, []).append(occurrence)
        occurrence_orders.setdefault(event_start, []).append(occurrence_order)
    if any(
        orders != list(range(len(orders)))
        for orders in occurrence_orders.values()
    ):
        raise EmpiricalArchiveError("archive_verification_failed")

    bars: list[CanonicalMinuteBar] = []
    for row in canonical_rows:
        try:
            fidelity = row["numeric_fidelity"]
            event_start = row["event_start_utc"]
            occurrences = tuple(occurrences_by_event[event_start])
            bars.append(
                CanonicalMinuteBar(
                    provider=row["provider"],
                    feed=row["feed"],
                    instrument_id=row["instrument_id"],
                    symbol=row["symbol"],
                    source_timestamp=row["source_timestamp"],
                    event_start_utc=event_start,
                    bar_end_utc=row["bar_end_utc"],
                    received_at_utc=row["received_at_utc"],
                    research_available_at_utc=row["research_available_at_utc"],
                    session_date=row["session_date"],
                    session_type=row["session_type"],
                    currency=row["currency"],
                    adjustment_mode=row["adjustment_mode"],
                    numeric_fidelity=fidelity,
                    quality_status=row["quality_status"],
                    open_price=_scalar(row["open_price"], fidelity),
                    high_price=_scalar(row["high_price"], fidelity),
                    low_price=_scalar(row["low_price"], fidelity),
                    close_price=_scalar(row["close_price"], fidelity),
                    volume=_scalar(row["volume"], fidelity),
                    raw_body_sha256=row["raw_body_sha256"],
                    capture_ordinal=row["capture_ordinal"],
                    source_row_index=row["source_row_index"],
                    occurrences=occurrences,
                )
            )
        except (ArchiveStorageError, KeyError, TypeError, ValueError):
            raise EmpiricalArchiveError("archive_verification_failed") from None
    return tuple(bars)


def _scalar(value: object, fidelity: object) -> CanonicalScalar:
    if not isinstance(value, Decimal):
        raise EmpiricalArchiveError("archive_verification_failed")
    if fidelity == "decimal_string_lexeme":
        kind = "json_string"
    elif fidelity == "json_number_lexeme":
        kind = "json_number"
    else:
        raise EmpiricalArchiveError("archive_verification_failed")
    return CanonicalScalar(kind=kind, text=format(value, "f"))


def _merge_daily_bars(
    bars: tuple[CanonicalMinuteBar, ...],
) -> tuple[CanonicalMinuteBar, ...]:
    by_event: dict[str, CanonicalMinuteBar] = {}
    for bar in sorted(bars, key=lambda value: value.event_start_utc):
        existing = by_event.get(bar.event_start_utc)
        if existing is None:
            by_event[bar.event_start_utc] = bar
            continue
        if _measurement_identity(existing) != _measurement_identity(bar):
            raise EmpiricalArchiveError("conflicting_minute_duplicate")
        merged_occurrences = existing.occurrences + tuple(
            occurrence
            for occurrence in bar.occurrences
            if occurrence not in existing.occurrences
        )
        by_event[bar.event_start_utc] = replace(
            existing,
            occurrences=merged_occurrences,
        )
    return tuple(by_event[event] for event in sorted(by_event))


def _measurement_identity(bar: CanonicalMinuteBar) -> tuple[object, ...]:
    return (
        bar.provider,
        bar.feed,
        bar.instrument_id,
        bar.symbol,
        bar.event_start_utc,
        bar.bar_end_utc,
        bar.session_date,
        bar.session_type,
        bar.currency,
        bar.adjustment_mode,
        bar.numeric_fidelity,
        bar.quality_status,
        Decimal(bar.open_price.text),
        Decimal(bar.high_price.text),
        Decimal(bar.low_price.text),
        Decimal(bar.close_price.text),
        Decimal(bar.volume.text),
    )


def _ledger_entry(
    scope: CollectionScope,
    status: DailyScopeLedgerStatus,
    *,
    reason: str,
    row_count: int = 0,
    manifest_sha256: str | None = None,
) -> DailyScopeLedgerEntry:
    return DailyScopeLedgerEntry(
        acquisition_key=scope.acquisition_key,
        symbol=scope.symbol,
        start_at=scope.start_at.isoformat().replace("+00:00", "Z"),
        end_at=scope.end_at.isoformat().replace("+00:00", "Z"),
        status=status,
        reason=reason,
        row_count=row_count,
        manifest_sha256=manifest_sha256,
    )


def _series_evidence_sha256(
    identity: tuple[str, str, str, str, str],
    ledger: tuple[DailyScopeLedgerEntry, ...],
) -> str:
    body = {
        "schemaVersion": _EVIDENCE_SCHEMA_VERSION,
        "seriesIdentity": {
            "provider": identity[0],
            "feed": identity[1],
            "instrumentId": identity[2],
            "symbol": identity[3],
            "adjustmentMode": identity[4],
        },
        "dailyScopes": [entry.to_evidence_body() for entry in ledger],
    }
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
