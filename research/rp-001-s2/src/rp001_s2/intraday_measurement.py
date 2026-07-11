"""Lossless, read-only intraday measurement primitives for RP-001-S2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable
from urllib.parse import urlencode

from rp001.toss_research_collector import (
    CanonicalScalar,
    CollectorError,
    HttpRequest,
    HttpResponse,
    RawHttpCapture,
    _canonical_scalar,
    _make_capture,
    _parse_json,
    _parse_timestamp,
    _positive_decimal_scalar,
    _send_allowed_get_no_raise,
)


_CANDLES_URL = "https://openapi.tossinvest.com/api/v1/candles"
_UNSIGNED_DECIMAL_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_CANDLE_FIELDS = frozenset(
    {"timestamp", "openPrice", "highPrice", "lowPrice", "closePrice", "volume", "currency"}
)

Transport = Callable[[HttpRequest], HttpResponse]
TokenSupplier = Callable[[], str]
Clock = Callable[[], datetime]


class MeasurementError(ValueError):
    """Sanitized measurement failure with preserved safe raw captures."""

    def __init__(self, code: str, captures: tuple[RawHttpCapture, ...] = ()) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


@dataclass(frozen=True)
class MeasuredBar:
    timestamp: str
    normalized_instant: str
    bar_end: str
    available_at: str
    open_price: CanonicalScalar
    high_price: CanonicalScalar
    low_price: CanonicalScalar
    close_price: CanonicalScalar
    volume: CanonicalScalar
    currency: str
    source_body_sha256: str
    source_capture_ordinal: int
    source_row_index: int
    provider_order: int
    occurrences: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class IntradayCandleCollection:
    symbol: str
    interval: str
    adjusted: bool
    start_at: str
    end_at: str
    analysis_rows: tuple[MeasuredBar, ...]
    audit_only_rows: tuple[MeasuredBar, ...]
    captures: tuple[RawHttpCapture, ...]
    inclusive_overlap_count: int
    requested_start_reached: bool
    completion_reason: str


@dataclass(frozen=True)
class _ParsedPage:
    rows: tuple[MeasuredBar, ...]
    instants: tuple[datetime, ...]
    next_before: str | None


class IntradayMeasurementCollector:
    """Collect lossless 1m candle pages without daily-candle assumptions."""

    def __init__(self, transport: Transport, token_supplier: TokenSupplier, clock: Clock) -> None:
        if not callable(transport) or not callable(token_supplier) or not callable(clock):
            raise MeasurementError("INVALID_INPUT")
        self._transport = transport
        self._token_supplier = token_supplier
        self._clock = clock

    def collect_candles(
        self,
        *,
        symbol: str,
        interval: str,
        adjusted: bool,
        start_at: str,
        end_at: str,
        initial_before: str,
        count: int,
        page_limit: int,
    ) -> IntradayCandleCollection:
        start = _parse_input_instant(start_at)
        end = _parse_input_instant(end_at)
        before_instant = _parse_input_instant(initial_before)
        if (
            not symbol
            or interval != "1m"
            or type(adjusted) is not bool
            or type(count) is not int
            or count != 200
            or type(page_limit) is not int
            or not 1 <= page_limit <= 64
            or start >= end
            or before_instant < end
        ):
            raise MeasurementError("INVALID_INPUT")

        rows_by_instant: dict[datetime, MeasuredBar] = {}
        captures: list[RawHttpCapture] = []
        seen_cursors = {initial_before}
        cursor = initial_before
        previous_oldest: datetime | None = None
        overlap_count = 0
        provider_order = 0
        requested_start_reached = False
        completion_reason: str | None = None

        for page_ordinal in range(page_limit):
            query = (
                ("symbol", symbol),
                ("interval", interval),
                ("count", str(count)),
                ("adjusted", "true" if adjusted else "false"),
                ("before", cursor),
            )
            try:
                capture, value = self._receive_json(f"{interval}_candles_v1", _CANDLES_URL, query)
                captures.append(capture)
                page = _parse_candle_page(value, capture, page_ordinal, provider_order)
                provider_order += len(page.rows)
                previous_oldest = _validate_page_order(page, previous_oldest, capture, cursor)
                if not page.rows:
                    if page.next_before is None:
                        completion_reason = "empty_provider_terminal"
                        break
                    raise MeasurementError("NO_PAGINATION_PROGRESS", tuple(captures))

                new_count = 0
                for row, instant in zip(page.rows, page.instants, strict=True):
                    existing = rows_by_instant.get(instant)
                    if existing is None:
                        rows_by_instant[instant] = row
                        new_count += 1
                        continue
                    if not _same_observation(existing, row):
                        raise MeasurementError("CONFLICTING_DUPLICATE", tuple(captures))
                    overlap_count += 1
                    rows_by_instant[instant] = _append_occurrence(existing, row)

                requested_start_reached = any(
                    instant <= start for instant in page.instants
                )
                if requested_start_reached:
                    completion_reason = "start_boundary_reached"
                    break
                if page.next_before is None:
                    completion_reason = "provider_terminal_before_start"
                    break
                if new_count == 0:
                    raise MeasurementError("NO_PAGINATION_PROGRESS", tuple(captures))
                if page.next_before in seen_cursors:
                    raise MeasurementError("REPEATED_CURSOR", tuple(captures))
                if page_ordinal + 1 == page_limit:
                    raise MeasurementError("PAGE_LIMIT_EXCEEDED", tuple(captures))
                seen_cursors.add(page.next_before)
                cursor = page.next_before
            except MeasurementError as error:
                combined = list(captures)
                for capture in error.captures:
                    if capture not in combined:
                        combined.append(capture)
                raise MeasurementError(error.code, tuple(combined)) from None
            except CollectorError as error:
                safe = tuple(captures) + tuple(
                    item for item in error.captures if item not in captures
                )
                raise MeasurementError(error.code, safe) from None

        if completion_reason is None:
            raise MeasurementError("COLLECTION_INCOMPLETE", tuple(captures))
        ordered = tuple(rows_by_instant[key] for key in sorted(rows_by_instant))
        analysis = tuple(
            row
            for row in ordered
            if start <= _parse_input_instant(row.timestamp)
            and _parse_grid_instant(row.bar_end) <= end
            and _parse_grid_instant(row.bar_end)
            <= _parse_any_instant(row.available_at)
        )
        audit = tuple(row for row in ordered if row not in analysis)
        _validate_collection_currency(ordered, tuple(captures))
        return IntradayCandleCollection(
            symbol=symbol,
            interval=interval,
            adjusted=adjusted,
            start_at=start_at,
            end_at=end_at,
            analysis_rows=analysis,
            audit_only_rows=audit,
            captures=tuple(captures),
            inclusive_overlap_count=overlap_count,
            requested_start_reached=requested_start_reached,
            completion_reason=completion_reason,
        )

    def _receive_json(
        self,
        endpoint_id: str,
        endpoint_url: str,
        query: tuple[tuple[str, str], ...],
    ) -> tuple[RawHttpCapture, object]:
        url = f"{endpoint_url}?{urlencode(query)}"
        result = _send_allowed_get_no_raise(self._transport, self._token_supplier, url)
        if result.error_code is not None or result.response is None:
            raise MeasurementError(result.error_code or "INVALID_HTTP_RESPONSE")
        capture = _make_capture(endpoint_id, url, query, result.response, self._clock)
        if not 200 <= result.response.status < 300:
            raise MeasurementError("HTTP_STATUS", (capture,))
        if dict(result.response.headers).get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise MeasurementError("INVALID_CONTENT_TYPE", (capture,))
        try:
            return capture, _parse_json(result.response.body, capture)
        except CollectorError as error:
            raise MeasurementError(error.code, error.captures) from None


def _parse_candle_page(
    value: object,
    capture: RawHttpCapture,
    capture_ordinal: int,
    provider_order_offset: int,
) -> _ParsedPage:
    if not isinstance(value, dict) or frozenset(value) != {"result"}:
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,))
    result = value["result"]
    if (
        not isinstance(result, dict)
        or "candles" not in result
        or not frozenset(result).issubset({"candles", "nextBefore"})
        or not isinstance(result["candles"], list)
        or len(result["candles"]) > 200
    ):
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,))
    rows: list[MeasuredBar] = []
    instants: list[datetime] = []
    seen: set[datetime] = set()
    for row_index, raw in enumerate(result["candles"]):
        row, instant = _parse_candle_row(
            raw, capture, capture_ordinal, row_index, provider_order_offset + row_index
        )
        if instant in seen:
            raise MeasurementError("DUPLICATE_WITHIN_PAGE", (capture,))
        seen.add(instant)
        rows.append(row)
        instants.append(instant)
    next_before = result.get("nextBefore")
    if next_before is not None:
        if not isinstance(next_before, str):
            raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,))
        try:
            _parse_input_instant(next_before)
        except MeasurementError:
            raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,)) from None
    return _ParsedPage(tuple(rows), tuple(instants), next_before)


def _parse_candle_row(
    value: object,
    capture: RawHttpCapture,
    capture_ordinal: int,
    row_index: int,
    provider_order: int,
) -> tuple[MeasuredBar, datetime]:
    if not isinstance(value, dict) or frozenset(value) != _CANDLE_FIELDS:
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,))
    timestamp = value["timestamp"]
    currency = value["currency"]
    if not isinstance(timestamp, str) or not isinstance(currency, str) or not currency:
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,))
    try:
        instant = _parse_input_instant(timestamp)
    except MeasurementError:
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,)) from None
    try:
        open_price = _positive_decimal_scalar(value["openPrice"])
        high_price = _positive_decimal_scalar(value["highPrice"])
        low_price = _positive_decimal_scalar(value["lowPrice"])
        close_price = _positive_decimal_scalar(value["closePrice"])
        volume = _nonnegative_decimal_scalar(value["volume"])
    except CollectorError:
        raise MeasurementError("INVALID_CANDLE_SHAPE", (capture,)) from None
    low = _decimal(low_price)
    high = _decimal(high_price)
    if low > high or not low <= _decimal(open_price) <= high or not low <= _decimal(close_price) <= high:
        raise MeasurementError("OHLC_INVARIANT", (capture,))
    normalized = instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    bar_end = (instant + timedelta(minutes=1)).astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    occurrence = (capture.body_sha256, capture_ordinal, row_index)
    return (
        MeasuredBar(
            timestamp=timestamp,
            normalized_instant=normalized,
            bar_end=bar_end,
            available_at=capture.received_at,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
            currency=currency,
            source_body_sha256=capture.body_sha256,
            source_capture_ordinal=capture_ordinal,
            source_row_index=row_index,
            provider_order=provider_order,
            occurrences=(occurrence,),
        ),
        instant,
    )


def _validate_page_order(
    page: _ParsedPage,
    previous_oldest: datetime | None,
    capture: RawHttpCapture,
    requested_before: str,
) -> datetime | None:
    if not page.instants:
        return previous_oldest
    if any(older > newer for newer, older in zip(page.instants, page.instants[1:])):
        raise MeasurementError("PAGE_ORDER_INVALID", (capture,))
    if page.instants[0] > _parse_input_instant(requested_before):
        raise MeasurementError("CANDLE_AFTER_BEFORE", (capture,))
    if previous_oldest is not None and page.instants[0] > previous_oldest:
        raise MeasurementError("PAGE_ORDER_INVALID", (capture,))
    return page.instants[-1]


def _same_observation(left: MeasuredBar, right: MeasuredBar) -> bool:
    return (
        left.timestamp == right.timestamp
        and left.normalized_instant == right.normalized_instant
        and left.open_price == right.open_price
        and left.high_price == right.high_price
        and left.low_price == right.low_price
        and left.close_price == right.close_price
        and left.volume == right.volume
        and left.currency == right.currency
    )


def _append_occurrence(existing: MeasuredBar, duplicate: MeasuredBar) -> MeasuredBar:
    return MeasuredBar(
        timestamp=existing.timestamp,
        normalized_instant=existing.normalized_instant,
        bar_end=existing.bar_end,
        available_at=existing.available_at,
        open_price=existing.open_price,
        high_price=existing.high_price,
        low_price=existing.low_price,
        close_price=existing.close_price,
        volume=existing.volume,
        currency=existing.currency,
        source_body_sha256=existing.source_body_sha256,
        source_capture_ordinal=existing.source_capture_ordinal,
        source_row_index=existing.source_row_index,
        provider_order=existing.provider_order,
        occurrences=existing.occurrences + duplicate.occurrences,
    )


def _validate_collection_currency(
    rows: tuple[MeasuredBar, ...],
    captures: tuple[RawHttpCapture, ...],
) -> None:
    if len({row.currency for row in rows}) > 1:
        raise MeasurementError("CURRENCY_MISMATCH", captures)


def _parse_input_instant(value: str) -> datetime:
    parsed = _parse_any_instant(value)
    if parsed.second != 0 or parsed.microsecond != 0:
        raise MeasurementError("INVALID_TIMESTAMP")
    return parsed


def _parse_grid_instant(value: str) -> datetime:
    return _parse_input_instant(value)


def _parse_any_instant(value: str) -> datetime:
    try:
        return _parse_timestamp(value)
    except CollectorError:
        raise MeasurementError("INVALID_TIMESTAMP") from None


def _decimal(value: CanonicalScalar) -> Decimal:
    return Decimal(value.text)


def _nonnegative_decimal_scalar(value: object) -> CanonicalScalar:
    scalar = _canonical_scalar(value)
    if _UNSIGNED_DECIMAL_PATTERN.fullmatch(scalar.text) is None:
        raise CollectorError("INVALID_SCALAR")
    return scalar
