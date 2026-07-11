"""Cross-provider canonical minute-bar conversion for immutable archives."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.alpaca_boundary import _valid_scope as _valid_alpaca_scope
from rp001_s2.alpaca_measurement import (
    AlpacaMeasuredMinuteBar,
    AlpacaMinuteCollection,
)
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.archive_storage import ArchiveStorageError, CanonicalMinuteBar
from rp001_s2.intraday_measurement import IntradayCandleCollection, MeasuredBar


_SESSION_TIMEZONES = {
    "USD": ZoneInfo("America/New_York"),
    "KRW": ZoneInfo("Asia/Seoul"),
}
_SESSION_TYPE = "provider_all_unclassified"
_TOSS_NUMERIC_FIDELITY = "decimal_string_lexeme"
_ALPACA_NUMERIC_FIDELITY = "json_number_lexeme"
_TOSS_ADJUSTMENT_FLAGS = {"native": False, "adjusted": True}


class MinuteCanonicalizationError(ValueError):
    """Stable rejection of an invalid provider-to-archive conversion."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonicalize_toss_collection(
    scope: CollectionScope,
    collection: IntradayCandleCollection,
) -> tuple[CanonicalMinuteBar, ...]:
    """Convert every unique Toss analysis and audit row without coalescing scope."""
    _validate_toss_scope(scope, collection)
    captures = _require_captures(collection.captures)
    tagged_rows = tuple(
        (row, _toss_analysis_quality(scope, row, captures))
        for row in collection.analysis_rows
    ) + tuple(
        (row, _toss_audit_quality(scope, row, captures))
        for row in collection.audit_only_rows
    )
    currencies = {row.currency for row, _quality in tagged_rows}
    if len(currencies) > 1:
        raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")
    return _canonicalize_rows(
        scope=scope,
        captures=captures,
        tagged_rows=tagged_rows,
        numeric_fidelity=_TOSS_NUMERIC_FIDELITY,
    )


def canonicalize_alpaca_collection(
    collection: AlpacaMinuteCollection,
) -> tuple[CanonicalMinuteBar, ...]:
    """Convert one immutable Alpaca feed/adjustment collection."""
    if not isinstance(collection, AlpacaMinuteCollection):
        raise MinuteCanonicalizationError("INVALID_INPUT")
    scope = collection.scope
    if not _valid_alpaca_scope(scope) or type(collection.rows) is not tuple:
        raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")
    captures = _require_captures(collection.captures)
    tagged_rows: tuple[tuple[AlpacaMeasuredMinuteBar, str], ...] = tuple(
        (row, "verified_completed") for row in collection.rows
    )
    for row in collection.rows:
        if not isinstance(row, AlpacaMeasuredMinuteBar):
            raise MinuteCanonicalizationError("INVALID_INPUT")
        event_start = _canonical_utc(row.normalized_instant)
        bar_end = _canonical_utc(row.bar_end)
        received = _canonical_utc(_capture_for(row, captures).received_at)
        if (
            row.currency != "USD"
            or not scope.start_at <= event_start
            or bar_end > scope.end_at
            or received < bar_end
        ):
            raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")
    return _canonicalize_rows(
        scope=scope,
        captures=captures,
        tagged_rows=tagged_rows,
        numeric_fidelity=_ALPACA_NUMERIC_FIDELITY,
    )


def _validate_toss_scope(
    scope: CollectionScope,
    collection: IntradayCandleCollection,
) -> None:
    if not isinstance(scope, CollectionScope) or not isinstance(
        collection,
        IntradayCandleCollection,
    ):
        raise MinuteCanonicalizationError("INVALID_INPUT")
    expected_adjusted = _TOSS_ADJUSTMENT_FLAGS.get(scope.adjustment_mode)
    try:
        collection_start = _aware_instant(collection.start_at)
        collection_end = _aware_instant(collection.end_at)
    except MinuteCanonicalizationError:
        raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH") from None
    if (
        scope.provider != "toss"
        or scope.feed != "provider_all"
        or scope.interval != "1m"
        or scope.session_scope != "provider_all"
        or collection.symbol != scope.symbol
        or collection.interval != scope.interval
        or expected_adjusted is None
        or collection.adjusted is not expected_adjusted
        or collection_start != scope.start_at
        or collection_end != scope.end_at
        or type(collection.analysis_rows) is not tuple
        or type(collection.audit_only_rows) is not tuple
    ):
        raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")


def _toss_analysis_quality(
    scope: CollectionScope,
    row: MeasuredBar,
    captures: tuple[RawHttpCapture, ...],
) -> str:
    if not isinstance(row, MeasuredBar):
        raise MinuteCanonicalizationError("INVALID_INPUT")
    event_start = _canonical_utc(row.normalized_instant)
    bar_end = _canonical_utc(row.bar_end)
    received = _canonical_utc(_capture_for(row, captures).received_at)
    if (
        event_start < scope.start_at
        or bar_end > scope.end_at
        or received < bar_end
    ):
        raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")
    return "verified_completed"


def _toss_audit_quality(
    scope: CollectionScope,
    row: MeasuredBar,
    captures: tuple[RawHttpCapture, ...],
) -> str:
    if not isinstance(row, MeasuredBar):
        raise MinuteCanonicalizationError("INVALID_INPUT")
    event_start = _canonical_utc(row.normalized_instant)
    bar_end = _canonical_utc(row.bar_end)
    received = _canonical_utc(_capture_for(row, captures).received_at)
    if event_start < scope.start_at or bar_end > scope.end_at:
        return "audit_out_of_scope"
    if received < bar_end:
        return "audit_partial"
    raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")


def _canonicalize_rows(
    *,
    scope: CollectionScope,
    captures: tuple[RawHttpCapture, ...],
    tagged_rows: tuple[
        tuple[MeasuredBar | AlpacaMeasuredMinuteBar, str],
        ...,
    ],
    numeric_fidelity: str,
) -> tuple[CanonicalMinuteBar, ...]:
    bars: list[tuple[datetime, CanonicalMinuteBar]] = []
    seen_events: set[datetime] = set()
    for row, quality_status in tagged_rows:
        event_start = _canonical_utc(row.normalized_instant)
        if event_start in seen_events:
            raise MinuteCanonicalizationError("DUPLICATE_EVENT")
        seen_events.add(event_start)
        capture = _capture_for(row, captures)
        _validate_lineage(row, captures, capture)
        currency = _supported_currency(row.currency)
        bar_end = _canonical_utc(row.bar_end)
        received = _canonical_utc(capture.received_at)
        if row.available_at != capture.received_at:
            raise MinuteCanonicalizationError("LINEAGE_INVALID")
        try:
            bar = CanonicalMinuteBar(
                provider=scope.provider,
                feed=scope.feed,
                instrument_id=scope.instrument_id,
                symbol=scope.symbol,
                source_timestamp=row.source_timestamp
                if isinstance(row, AlpacaMeasuredMinuteBar)
                else row.timestamp,
                event_start_utc=row.normalized_instant,
                bar_end_utc=row.bar_end,
                received_at_utc=capture.received_at,
                research_available_at_utc=_format_utc(max(received, bar_end)),
                session_date=event_start.astimezone(
                    _SESSION_TIMEZONES[currency]
                ).date().isoformat(),
                session_type=_SESSION_TYPE,
                currency=currency,
                adjustment_mode=scope.adjustment_mode,
                numeric_fidelity=numeric_fidelity,
                quality_status=quality_status,
                open_price=row.open_price,
                high_price=row.high_price,
                low_price=row.low_price,
                close_price=row.close_price,
                volume=row.volume,
                raw_body_sha256=row.source_body_sha256,
                capture_ordinal=row.source_capture_ordinal,
                source_row_index=row.source_row_index,
                occurrences=row.occurrences,
            )
        except ArchiveStorageError:
            raise MinuteCanonicalizationError("CANONICAL_CONTRACT_INVALID") from None
        bars.append((event_start, bar))
    return tuple(bar for _event, bar in sorted(bars, key=lambda item: item[0]))


def _require_captures(value: object) -> tuple[RawHttpCapture, ...]:
    if type(value) is not tuple or any(
        not isinstance(capture, RawHttpCapture) for capture in value
    ):
        raise MinuteCanonicalizationError("LINEAGE_INVALID")
    return value


def _capture_for(
    row: MeasuredBar | AlpacaMeasuredMinuteBar,
    captures: tuple[RawHttpCapture, ...],
) -> RawHttpCapture:
    ordinal = row.source_capture_ordinal
    if type(ordinal) is not int or not 0 <= ordinal < len(captures):
        raise MinuteCanonicalizationError("LINEAGE_INVALID")
    return captures[ordinal]


def _validate_lineage(
    row: MeasuredBar | AlpacaMeasuredMinuteBar,
    captures: tuple[RawHttpCapture, ...],
    primary_capture: RawHttpCapture,
) -> None:
    primary = (
        row.source_body_sha256,
        row.source_capture_ordinal,
        row.source_row_index,
    )
    if (
        primary_capture.body_sha256 != row.source_body_sha256
        or type(row.source_row_index) is not int
        or row.source_row_index < 0
        or type(row.occurrences) is not tuple
        or not row.occurrences
        or row.occurrences[0] != primary
    ):
        raise MinuteCanonicalizationError("LINEAGE_INVALID")
    validated_occurrences: list[tuple[str, int, int]] = []
    for occurrence in row.occurrences:
        if type(occurrence) is not tuple or len(occurrence) != 3:
            raise MinuteCanonicalizationError("LINEAGE_INVALID")
        raw_sha256, capture_ordinal, source_row_index = occurrence
        if (
            type(capture_ordinal) is not int
            or not 0 <= capture_ordinal < len(captures)
            or captures[capture_ordinal].body_sha256 != raw_sha256
            or type(source_row_index) is not int
            or source_row_index < 0
        ):
            raise MinuteCanonicalizationError("LINEAGE_INVALID")
        validated_occurrences.append(
            (raw_sha256, capture_ordinal, source_row_index)
        )
    if len(set(validated_occurrences)) != len(validated_occurrences):
        raise MinuteCanonicalizationError("LINEAGE_INVALID")


def _supported_currency(value: object) -> str:
    if type(value) is not str or value not in _SESSION_TIMEZONES:
        raise MinuteCanonicalizationError("UNSUPPORTED_CURRENCY")
    return value


def _canonical_utc(value: str) -> datetime:
    parsed = _aware_instant(value)
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or value != _format_utc(
        parsed
    ):
        raise MinuteCanonicalizationError("TIMESTAMP_INVALID")
    return parsed


def _aware_instant(value: str) -> datetime:
    if type(value) is not str:
        raise MinuteCanonicalizationError("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except (ValueError, OverflowError):
        raise MinuteCanonicalizationError("TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise MinuteCanonicalizationError("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
