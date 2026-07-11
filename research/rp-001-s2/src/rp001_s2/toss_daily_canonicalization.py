"""Bind Toss daily rows back to exact raw response occurrences."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rp001.toss_research_collector import (
    CandleCollection,
    CandleRow,
    RawHttpCapture,
)
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.daily_archive_storage import CanonicalDailyBar


_NEW_YORK = ZoneInfo("America/New_York")
_ROW_FIELDS = {
    "timestamp", "openPrice", "highPrice", "lowPrice", "closePrice",
    "volume", "currency",
}


class DailyCanonicalizationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonicalize_toss_daily_collection(
    scope: CollectionScope,
    collection: CandleCollection,
) -> tuple[CanonicalDailyBar, ...]:
    _validate_scope(scope, collection)
    occurrences = _raw_occurrences(collection.captures)
    rows: list[CanonicalDailyBar] = []
    for row in collection.analysis_rows:
        values = _row_values(row)
        candidates = occurrences.get(row.timestamp)
        if not candidates:
            raise DailyCanonicalizationError("raw_lineage_missing")
        if any(candidate[3] != values for candidate in candidates):
            raise DailyCanonicalizationError("conflicting_duplicate")
        first_sha256, first_ordinal, first_index, _ = candidates[0]
        received_at = collection.captures[first_ordinal].received_at
        rows.append(
            CanonicalDailyBar(
                provider=scope.provider,
                feed=scope.feed,
                instrument_id=scope.instrument_id,
                symbol=scope.symbol,
                source_timestamp=row.timestamp,
                session_date=_session_date(row.timestamp, row.currency),
                received_at_utc=received_at,
                research_available_at_utc=received_at,
                session_type=scope.session_scope,
                currency=row.currency,
                adjustment_mode=scope.adjustment_mode,
                numeric_fidelity="decimal_string_lexeme",
                quality_status="verified_provider_response",
                open_price=row.open_price,
                high_price=row.high_price,
                low_price=row.low_price,
                close_price=row.close_price,
                volume=row.volume,
                raw_body_sha256=first_sha256,
                capture_ordinal=first_ordinal,
                source_row_index=first_index,
                occurrences=tuple(
                    (sha256, ordinal, row_index)
                    for sha256, ordinal, row_index, _values in candidates
                ),
            )
        )
    return tuple(sorted(rows, key=lambda value: value.source_timestamp))


def _validate_scope(scope: object, collection: object) -> None:
    expected_adjusted = (
        scope.adjustment_mode == "adjusted"
        if isinstance(scope, CollectionScope)
        else None
    )
    if (
        not isinstance(scope, CollectionScope)
        or scope.provider != "toss"
        or scope.feed != "provider_all"
        or scope.interval != "1d"
        or scope.adjustment_mode not in {"native", "adjusted"}
        or not isinstance(collection, CandleCollection)
        or collection.symbol != scope.symbol
        or collection.adjusted is not expected_adjusted
        or collection.start != scope.start_at.date()
        or collection.end != scope.end_at.date() - timedelta(days=1)
    ):
        raise DailyCanonicalizationError("scope_mismatch")


def _raw_occurrences(
    captures: tuple[RawHttpCapture, ...],
) -> dict[str, list[tuple[str, int, int, dict[str, str]]]]:
    occurrences: dict[
        str,
        list[tuple[str, int, int, dict[str, str]]],
    ] = defaultdict(list)
    for ordinal, capture in enumerate(captures):
        try:
            body = base64.b64decode(capture.body_base64, validate=True)
            if hashlib.sha256(body).hexdigest() != capture.body_sha256:
                raise ValueError
            value = json.loads(body.decode("utf-8"))
            result = value["result"]
            raw_rows = result["candles"]
            if not isinstance(raw_rows, list):
                raise ValueError
        except Exception:
            raise DailyCanonicalizationError("raw_capture_invalid") from None
        for row_index, raw in enumerate(raw_rows):
            if (
                not isinstance(raw, dict)
                or set(raw) != _ROW_FIELDS
                or any(not isinstance(item, str) for item in raw.values())
            ):
                raise DailyCanonicalizationError("raw_capture_invalid")
            timestamp = raw["timestamp"]
            occurrences[timestamp].append(
                (capture.body_sha256, ordinal, row_index, raw)
            )
    return occurrences


def _row_values(row: CandleRow) -> dict[str, str]:
    return {
        "timestamp": row.timestamp,
        "openPrice": row.open_price.text,
        "highPrice": row.high_price.text,
        "lowPrice": row.low_price.text,
        "closePrice": row.close_price.text,
        "volume": row.volume.text,
        "currency": row.currency,
    }


def _session_date(value: str, currency: str) -> str:
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None:
        raise DailyCanonicalizationError("timestamp_invalid")
    if currency == "KRW":
        return parsed.date().isoformat()
    if currency == "USD":
        return parsed.astimezone(_NEW_YORK).date().isoformat()
    raise DailyCanonicalizationError("currency_not_supported")
