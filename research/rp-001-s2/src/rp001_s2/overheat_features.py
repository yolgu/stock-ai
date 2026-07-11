"""Bottom-up, direction-neutral minute features for overheat research."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from zoneinfo import ZoneInfo

from rp001_s2.archive_storage import CanonicalMinuteBar
from rp001_s2.direction_neutral_overheat import DirectionNeutralObservation


class FeatureMarket(str, Enum):
    US_REGULAR = "us_regular"
    KR_REGULAR = "kr_regular"


@dataclass(frozen=True)
class DirectionNeutralFeatureDataset:
    symbol: str
    benchmark_symbol: str
    market: FeatureMarket
    claim_level: str
    availability_basis: str
    observations: tuple[DirectionNeutralObservation, ...]


@dataclass(frozen=True)
class _MarketContract:
    timezone: ZoneInfo
    currency: str
    open_time: time
    close_time: time
    minutes_per_session: int


@dataclass(frozen=True)
class _PreparedBar:
    source: CanonicalMinuteBar
    event_start: datetime
    bar_end: datetime
    local_date: str
    minute_of_day: int
    session_offset: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


_MARKETS = {
    FeatureMarket.US_REGULAR: _MarketContract(
        timezone=ZoneInfo("America/New_York"),
        currency="USD",
        open_time=time(9, 30),
        close_time=time(16, 0),
        minutes_per_session=390,
    ),
    FeatureMarket.KR_REGULAR: _MarketContract(
        timezone=ZoneInfo("Asia/Seoul"),
        currency="KRW",
        open_time=time(9, 0),
        close_time=time(15, 30),
        minutes_per_session=390,
    ),
}
_CLAIM_LEVEL = "price_volume_regime_proxy_only"
_AVAILABILITY_BASIS = "completed_bar_end_plus_one_second_proxy"
_SOURCE_WINDOW_SCHEMA = "rp001-s2-direction-neutral-feature-window.v1"


class FeatureBuildError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_direction_neutral_features(
    *,
    symbol_bars: Sequence[CanonicalMinuteBar],
    benchmark_bars: Sequence[CanonicalMinuteBar],
    market: FeatureMarket,
) -> DirectionNeutralFeatureDataset:
    """Build point-in-time proxy ingredients without filling missing minutes."""
    if not isinstance(market, FeatureMarket):
        raise FeatureBuildError("feature_market_invalid")
    contract = _MARKETS[market]
    prepared_symbol = _prepare_series(tuple(symbol_bars), contract)
    prepared_benchmark = _prepare_series(tuple(benchmark_bars), contract)
    if not prepared_symbol or not prepared_benchmark:
        raise FeatureBuildError("feature_input_empty")
    symbol = prepared_symbol[0].source.symbol
    benchmark_symbol = prepared_benchmark[0].source.symbol
    if symbol == benchmark_symbol:
        raise FeatureBuildError("feature_benchmark_invalid")
    _require_compatible_scopes(prepared_symbol, prepared_benchmark)

    session_dates = tuple(sorted({bar.local_date for bar in prepared_symbol}))
    session_ordinals = {
        session_date: ordinal for ordinal, session_date in enumerate(session_dates)
    }
    symbol_returns = _returns(prepared_symbol)
    benchmark_returns = _returns(prepared_benchmark)
    benchmark_by_event = {
        bar.event_start: bar for bar in prepared_benchmark
    }
    benchmark_index_by_event = {
        bar.event_start: index for index, bar in enumerate(prepared_benchmark)
    }
    benchmark_return_by_event = {
        bar.event_start: value
        for bar, value in zip(prepared_benchmark, benchmark_returns, strict=True)
    }
    session_gaps = _session_gaps(prepared_symbol)

    observations: list[DirectionNeutralObservation] = []
    for index, (bar, signed_return) in enumerate(
        zip(prepared_symbol, symbol_returns, strict=True)
    ):
        if signed_return is None:
            continue
        market_minute_ordinal = (
            session_ordinals[bar.local_date] * contract.minutes_per_session
            + bar.session_offset
        )
        benchmark_bar = benchmark_by_event.get(bar.event_start)
        benchmark_return = benchmark_return_by_event.get(bar.event_start)
        residual = (
            None
            if benchmark_bar is None or benchmark_return is None
            else abs(signed_return - benchmark_return)
        )
        realized = _realized_volatility(
            prepared_symbol,
            symbol_returns,
            index,
            session_ordinals,
            contract,
        )
        benchmark_index = benchmark_index_by_event.get(bar.event_start)
        benchmark_sources = (
            ()
            if benchmark_index is None
            else prepared_benchmark[max(0, benchmark_index - 1) : benchmark_index + 1]
        )
        gap, gap_source = session_gaps[bar.local_date]
        source_hash = _source_window_hash(
            prepared_symbol,
            index,
            benchmark_sources,
            gap_source,
        )
        available_at = bar.bar_end + timedelta(seconds=1)
        observations.append(
            DirectionNeutralObservation(
                symbol=symbol,
                session_ordinal=session_ordinals[bar.local_date],
                minute_of_day=bar.minute_of_day,
                market_minute_ordinal=market_minute_ordinal,
                minute_end_utc=bar.bar_end,
                available_at_utc=available_at,
                session_id=bar.local_date,
                session_date=datetime.fromisoformat(bar.local_date).date(),
                source_window_sha256=source_hash,
                signed_return=signed_return,
                log_low=math.log(bar.low_price),
                log_high=math.log(bar.high_price),
                log_close=math.log(bar.close_price),
                family_scores={
                    "absolute_gap": gap,
                    "absolute_market_residual_return": residual,
                    "intrabar_log_range": math.log(bar.high_price / bar.low_price),
                    "realized_volatility_5m": realized,
                    "same_minute_volume": bar.volume,
                },
            )
        )
    return DirectionNeutralFeatureDataset(
        symbol=symbol,
        benchmark_symbol=benchmark_symbol,
        market=market,
        claim_level=_CLAIM_LEVEL,
        availability_basis=_AVAILABILITY_BASIS,
        observations=tuple(observations),
    )


def _prepare_series(
    bars: tuple[CanonicalMinuteBar, ...],
    contract: _MarketContract,
) -> tuple[_PreparedBar, ...]:
    prepared: list[_PreparedBar] = []
    identity: tuple[str, str, str, str, str] | None = None
    seen_events: set[datetime] = set()
    for source in bars:
        if not isinstance(source, CanonicalMinuteBar):
            raise FeatureBuildError("feature_input_invalid")
        if source.quality_status != "verified_completed":
            continue
        current_identity = (
            source.provider,
            source.feed,
            source.instrument_id,
            source.symbol,
            source.adjustment_mode,
        )
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise FeatureBuildError("feature_scope_mismatch")
        if source.instrument_id != source.symbol or source.currency != contract.currency:
            raise FeatureBuildError("feature_scope_mismatch")
        event_start = _utc(source.event_start_utc)
        bar_end = _utc(source.bar_end_utc)
        if bar_end != event_start + timedelta(minutes=1):
            raise FeatureBuildError("feature_timestamp_invalid")
        local = event_start.astimezone(contract.timezone)
        if not contract.open_time <= local.time() < contract.close_time:
            continue
        if event_start in seen_events:
            raise FeatureBuildError("feature_duplicate_event")
        seen_events.add(event_start)
        session_offset = (
            local.hour * 60
            + local.minute
            - (contract.open_time.hour * 60 + contract.open_time.minute)
        )
        open_price = _positive(source.open_price.text)
        high_price = _positive(source.high_price.text)
        low_price = _positive(source.low_price.text)
        close_price = _positive(source.close_price.text)
        volume = _nonnegative(source.volume.text)
        if (
            low_price > high_price
            or not low_price <= open_price <= high_price
            or not low_price <= close_price <= high_price
        ):
            raise FeatureBuildError("feature_ohlcv_invalid")
        prepared.append(
            _PreparedBar(
                source=source,
                event_start=event_start,
                bar_end=bar_end,
                local_date=local.date().isoformat(),
                minute_of_day=local.hour * 60 + local.minute,
                session_offset=session_offset,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
            )
        )
    prepared.sort(key=lambda bar: bar.event_start)
    if any(
        current.event_start <= previous.event_start
        for previous, current in zip(prepared, prepared[1:])
    ):
        raise FeatureBuildError("feature_event_order_invalid")
    return tuple(prepared)


def _require_compatible_scopes(
    symbol: tuple[_PreparedBar, ...],
    benchmark: tuple[_PreparedBar, ...],
) -> None:
    left = symbol[0].source
    right = benchmark[0].source
    if (
        left.provider != right.provider
        or left.feed != right.feed
        or left.adjustment_mode != right.adjustment_mode
        or left.currency != right.currency
    ):
        raise FeatureBuildError("feature_scope_mismatch")


def _returns(bars: tuple[_PreparedBar, ...]) -> tuple[float | None, ...]:
    values: list[float | None] = []
    previous: _PreparedBar | None = None
    for bar in bars:
        if previous is None:
            values.append(math.log(bar.close_price / bar.open_price))
        elif bar.local_date != previous.local_date:
            values.append(math.log(bar.close_price / previous.close_price))
        elif bar.session_offset == previous.session_offset + 1:
            values.append(math.log(bar.close_price / previous.close_price))
        else:
            values.append(None)
        previous = bar
    return tuple(values)


def _session_gaps(
    bars: tuple[_PreparedBar, ...],
) -> dict[str, tuple[float | None, _PreparedBar | None]]:
    grouped: dict[str, list[_PreparedBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.local_date, []).append(bar)
    gaps: dict[str, tuple[float | None, _PreparedBar | None]] = {}
    previous_close_bar: _PreparedBar | None = None
    for session_date in sorted(grouped):
        session = grouped[session_date]
        gap = (
            None
            if previous_close_bar is None or session[0].session_offset != 0
            else abs(
                math.log(session[0].open_price / previous_close_bar.close_price)
            )
        )
        gaps[session_date] = (gap, previous_close_bar)
        previous_close_bar = session[-1]
    return gaps


def _realized_volatility(
    bars: tuple[_PreparedBar, ...],
    returns: tuple[float | None, ...],
    index: int,
    session_ordinals: dict[str, int],
    contract: _MarketContract,
) -> float | None:
    if index < 4:
        return None
    window_bars = bars[index - 4 : index + 1]
    ordinals = tuple(
        session_ordinals[bar.local_date] * contract.minutes_per_session
        + bar.session_offset
        for bar in window_bars
    )
    if any(current != previous + 1 for previous, current in zip(ordinals, ordinals[1:])):
        return None
    window_returns = returns[index - 4 : index + 1]
    if any(value is None for value in window_returns):
        return None
    return math.sqrt(
        sum(value * value for value in window_returns if value is not None)
    )


def _source_window_hash(
    bars: tuple[_PreparedBar, ...],
    index: int,
    benchmark_sources: tuple[_PreparedBar, ...],
    gap_source: _PreparedBar | None,
) -> str:
    window = bars[max(0, index - 4) : index + 1]
    source_bars = list(window) + list(benchmark_sources)
    if gap_source is not None:
        source_bars.append(gap_source)
    unique_sources: dict[tuple[str, int, int], _PreparedBar] = {}
    for source_bar in source_bars:
        source = source_bar.source
        unique_sources[
            (source.raw_body_sha256, source.capture_ordinal, source.source_row_index)
        ] = source_bar
    sources: list[dict[str, object]] = [
        {
            "captureOrdinal": bar.source.capture_ordinal,
            "eventStartUtc": bar.source.event_start_utc,
            "rawBodySha256": bar.source.raw_body_sha256,
            "sourceRowIndex": bar.source.source_row_index,
            "symbol": bar.source.symbol,
        }
        for bar in sorted(
            unique_sources.values(),
            key=lambda value: (
                value.event_start,
                value.source.symbol,
                value.source.capture_ordinal,
                value.source.source_row_index,
            ),
        )
    ]
    body = json.dumps(
        {"schemaVersion": _SOURCE_WINDOW_SCHEMA, "sources": sources},
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except (TypeError, ValueError, OverflowError):
        raise FeatureBuildError("feature_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FeatureBuildError("feature_timestamp_invalid")
    return parsed.astimezone(timezone.utc)


def _positive(value: str) -> float:
    parsed = _decimal(value)
    if parsed <= 0:
        raise FeatureBuildError("feature_ohlcv_invalid")
    return float(parsed)


def _nonnegative(value: str) -> float:
    parsed = _decimal(value)
    if parsed < 0:
        raise FeatureBuildError("feature_ohlcv_invalid")
    return float(parsed)


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise FeatureBuildError("feature_ohlcv_invalid") from None
    if not parsed.is_finite():
        raise FeatureBuildError("feature_ohlcv_invalid")
    return parsed
