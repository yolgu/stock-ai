from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from rp001.toss_research_collector import CanonicalScalar
from rp001_s2.archive_storage import CanonicalMinuteBar
from rp001_s2.overheat_features import (
    FeatureMarket,
    FeatureSession,
    build_direction_neutral_features,
)


def _bar(
    symbol: str,
    event_start: datetime,
    *,
    close: str,
    open_price: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: str = "100",
    raw_character: str = "a",
) -> CanonicalMinuteBar:
    resolved_open = close if open_price is None else open_price
    resolved_high = close if high is None else high
    resolved_low = close if low is None else low
    event_text = event_start.isoformat(timespec="seconds").replace("+00:00", "Z")
    end_text = (event_start + timedelta(minutes=1)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    received_text = (event_start + timedelta(days=100)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    raw_sha256 = raw_character * 64
    return CanonicalMinuteBar(
        provider="toss",
        feed="provider_all",
        instrument_id=symbol,
        symbol=symbol,
        source_timestamp=event_text,
        event_start_utc=event_text,
        bar_end_utc=end_text,
        received_at_utc=received_text,
        research_available_at_utc=received_text,
        session_date=event_start.date().isoformat(),
        session_type="provider_all_unclassified",
        currency="USD",
        adjustment_mode="adjusted",
        numeric_fidelity="decimal_string_lexeme",
        quality_status="verified_completed",
        open_price=CanonicalScalar("json_string", resolved_open),
        high_price=CanonicalScalar("json_string", resolved_high),
        low_price=CanonicalScalar("json_string", resolved_low),
        close_price=CanonicalScalar("json_string", close),
        volume=CanonicalScalar("json_string", volume),
        raw_body_sha256=raw_sha256,
        capture_ordinal=0,
        source_row_index=int(event_start.timestamp()) % 1_000_000,
        occurrences=(
            (raw_sha256, 0, int(event_start.timestamp()) % 1_000_000),
        ),
    )


def _session(
    symbol: str,
    session_date: datetime,
    closes: tuple[str, ...],
    *,
    price_scale: float = 1.0,
    raw_character: str = "a",
) -> tuple[CanonicalMinuteBar, ...]:
    start = session_date.replace(hour=13, minute=30, tzinfo=timezone.utc)
    bars: list[CanonicalMinuteBar] = []
    for index, close in enumerate(closes):
        scaled = float(close) * price_scale
        bars.append(
            _bar(
                symbol,
                start + timedelta(minutes=index),
                close=f"{scaled:.6f}",
                high=f"{scaled * 1.001:.6f}",
                low=f"{scaled * 0.999:.6f}",
                volume=str(100 + index),
                raw_character=raw_character,
            )
        )
    return tuple(bars)


def _inverse_session(
    symbol: str,
    session_date: datetime,
    closes: tuple[str, ...],
    *,
    raw_character: str = "a",
) -> tuple[CanonicalMinuteBar, ...]:
    start = session_date.replace(hour=13, minute=30, tzinfo=timezone.utc)
    bars: list[CanonicalMinuteBar] = []
    for index, close in enumerate(closes):
        source = float(close)
        inverse = 10_000 / source
        bars.append(
            _bar(
                symbol,
                start + timedelta(minutes=index),
                close=f"{inverse:.12f}",
                high=f"{10_000 / (source * 0.999):.12f}",
                low=f"{10_000 / (source * 1.001):.12f}",
                volume=str(100 + index),
                raw_character=raw_character,
            )
        )
    return tuple(bars)


def _sessions(*values: datetime) -> tuple[FeatureSession, ...]:
    return tuple(FeatureSession(value.date(), 390) for value in values)


class DirectionNeutralFeatureTest(unittest.TestCase):
    def test_gap_is_not_reused_as_intraday_return_or_realized_volatility(self) -> None:
        first = datetime(2026, 7, 8, tzinfo=timezone.utc)
        second = datetime(2026, 7, 9, tzinfo=timezone.utc)
        symbol = _session("AAPL", first, ("100",) * 390) + _session(
            "AAPL", second, ("120",) * 5
        )
        benchmark = _session(
            "SPY", first, ("500",) * 390, raw_character="b"
        ) + _session("SPY", second, ("500",) * 5, raw_character="b")

        dataset = build_direction_neutral_features(
            symbol_bars=symbol,
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=(
                FeatureSession(first.date(), 390),
                FeatureSession(second.date(), 390),
            ),
        )

        opening = next(
            item for item in dataset.observations if item.session_date == second.date()
        )
        self.assertGreater(opening.family_scores["absolute_gap"], 0.18)
        self.assertEqual(
            opening.family_scores["absolute_market_residual_return"],
            0.0,
        )
        fifth = tuple(
            item for item in dataset.observations if item.session_date == second.date()
        )[-1]
        self.assertEqual(fifth.family_scores["realized_volatility_5m"], 0.0)
        self.assertEqual(fifth.family_scores["absolute_gap"], 0.0)

    def test_explicit_session_axis_preserves_missing_session_coverage_gap(self) -> None:
        first = datetime(2026, 7, 8, tzinfo=timezone.utc)
        missing = datetime(2026, 7, 9, tzinfo=timezone.utc)
        third = datetime(2026, 7, 10, tzinfo=timezone.utc)
        symbol = _session("AAPL", first, ("100",) * 390) + _session(
            "AAPL", third, ("101",)
        )
        benchmark = _session(
            "SPY", first, ("500",) * 390, raw_character="b"
        ) + _session("SPY", third, ("501",), raw_character="b")

        dataset = build_direction_neutral_features(
            symbol_bars=symbol,
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=(
                FeatureSession(first.date(), 390),
                FeatureSession(missing.date(), 390),
                FeatureSession(third.date(), 390),
            ),
        )

        before = next(
            item
            for item in reversed(dataset.observations)
            if item.session_date == first.date()
        )
        after = next(
            item for item in dataset.observations if item.session_date == third.date()
        )
        self.assertEqual(after.session_ordinal - before.session_ordinal, 2)
        self.assertEqual(after.market_minute_ordinal - before.market_minute_ordinal, 391)
        self.assertIsNone(after.family_scores["absolute_gap"])

    def test_realized_volatility_hash_binds_the_predecessor_of_first_return(self) -> None:
        session = datetime(2026, 7, 8, tzinfo=timezone.utc)
        symbol = _session(
            "AAPL", session, ("100", "101", "102", "103", "104", "105")
        )
        benchmark = _session(
            "SPY", session, ("500", "501", "502", "503", "504", "505"), raw_character="b"
        )
        sessions = (FeatureSession(session.date(), 390),)
        original = build_direction_neutral_features(
            symbol_bars=symbol,
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=sessions,
        ).observations[-1]
        changed_predecessor = replace(
            symbol[0],
            close_price=CanonicalScalar("json_string", "50"),
            high_price=CanonicalScalar("json_string", "100"),
            low_price=CanonicalScalar("json_string", "49"),
            raw_body_sha256="c" * 64,
            occurrences=(("c" * 64, 0, symbol[0].source_row_index),),
        )

        changed = build_direction_neutral_features(
            symbol_bars=(changed_predecessor,) + symbol[1:],
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=sessions,
        ).observations[-1]

        self.assertNotEqual(
            original.family_scores["realized_volatility_5m"],
            changed.family_scores["realized_volatility_5m"],
        )
        self.assertNotEqual(
            original.source_window_sha256,
            changed.source_window_sha256,
        )

    def test_builds_traceable_proxy_features_on_regular_market_minutes(self) -> None:
        first = datetime(2026, 7, 8, tzinfo=timezone.utc)
        second = datetime(2026, 7, 9, tzinfo=timezone.utc)
        symbol_bars = _session("AAPL", first, ("100", "101", "102", "101", "103")) + _session(
            "AAPL", second, ("105", "106", "104", "107", "108")
        )
        benchmark_bars = _session("SPY", first, ("500", "501", "502", "501", "503"), raw_character="b") + _session(
            "SPY", second, ("504", "505", "504", "506", "507"), raw_character="b"
        )

        dataset = build_direction_neutral_features(
            symbol_bars=symbol_bars,
            benchmark_bars=benchmark_bars,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(first, second),
        )

        self.assertEqual(dataset.claim_level, "price_volume_regime_proxy_only")
        self.assertEqual(
            dataset.availability_basis,
            "completed_bar_end_plus_one_second_proxy",
        )
        self.assertEqual(len(dataset.observations), 10)
        target = dataset.observations[-1]
        self.assertEqual(target.symbol, "AAPL")
        self.assertEqual(target.minute_of_day, 9 * 60 + 34)
        self.assertEqual(
            target.available_at_utc,
            target.minute_end_utc + timedelta(seconds=1),
        )
        self.assertEqual(
            set(target.family_scores),
            {
                "absolute_gap",
                "absolute_market_residual_return",
                "intrabar_log_range",
                "realized_volatility_5m",
                "same_minute_volume",
            },
        )
        self.assertTrue(all(value is None or value >= 0 for value in target.family_scores.values()))
        self.assertEqual(len(target.source_window_sha256), 64)

    def test_future_rows_and_future_revisions_do_not_change_current_features(self) -> None:
        session = datetime(2026, 7, 8, tzinfo=timezone.utc)
        symbol = _session("AAPL", session, ("100", "101", "102", "103", "104", "105"))
        benchmark = _session("SPY", session, ("500", "501", "502", "503", "504", "505"), raw_character="b")
        original = build_direction_neutral_features(
            symbol_bars=symbol,
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[4]
        changed_future = replace(
            symbol[5],
            open_price=CanonicalScalar("json_string", "999"),
            close_price=CanonicalScalar("json_string", "999"),
            high_price=CanonicalScalar("json_string", "1000"),
            low_price=CanonicalScalar("json_string", "998"),
            raw_body_sha256="c" * 64,
            occurrences=(("c" * 64, 0, symbol[5].source_row_index),),
        )

        repeated = build_direction_neutral_features(
            symbol_bars=symbol[:5] + (changed_future,),
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[4]

        self.assertEqual(original.family_scores, repeated.family_scores)
        self.assertEqual(original.source_window_sha256, repeated.source_window_sha256)

    def test_price_scale_does_not_change_direction_neutral_price_families(self) -> None:
        session = datetime(2026, 7, 8, tzinfo=timezone.utc)
        symbol = _session("AAPL", session, ("100", "101", "99", "102", "98"))
        benchmark = _session("SPY", session, ("500", "501", "499", "502", "498"), raw_character="b")
        scaled_symbol = _session(
            "AAPL", session, ("100", "101", "99", "102", "98"), price_scale=10
        )
        scaled_benchmark = _session(
            "SPY", session, ("500", "501", "499", "502", "498"), price_scale=10, raw_character="b"
        )

        base = build_direction_neutral_features(
            symbol_bars=symbol,
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[-1]
        scaled = build_direction_neutral_features(
            symbol_bars=scaled_symbol,
            benchmark_bars=scaled_benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[-1]

        for family in (
            "absolute_gap",
            "absolute_market_residual_return",
            "intrabar_log_range",
            "realized_volatility_5m",
        ):
            with self.subTest(family=family):
                self.assertAlmostEqual(
                    base.family_scores[family],
                    scaled.family_scores[family],
                    places=12,
                )

    def test_return_sign_reversal_does_not_change_overheat_family_scores(self) -> None:
        session = datetime(2026, 7, 8, tzinfo=timezone.utc)
        closes = ("100", "101", "99", "102", "98")
        benchmark_closes = ("500", "501", "499", "502", "498")
        base = build_direction_neutral_features(
            symbol_bars=_session("AAPL", session, closes),
            benchmark_bars=_session(
                "SPY", session, benchmark_closes, raw_character="b"
            ),
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[-1]
        reversed_result = build_direction_neutral_features(
            symbol_bars=_inverse_session("AAPL", session, closes),
            benchmark_bars=_inverse_session(
                "SPY", session, benchmark_closes, raw_character="b"
            ),
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        ).observations[-1]

        for family in (
            "absolute_market_residual_return",
            "intrabar_log_range",
            "realized_volatility_5m",
            "same_minute_volume",
        ):
            with self.subTest(family=family):
                self.assertAlmostEqual(
                    base.family_scores[family],
                    reversed_result.family_scores[family],
                    places=10,
                )

    def test_missing_minute_is_not_filled_or_reweighted(self) -> None:
        session = datetime(2026, 7, 8, tzinfo=timezone.utc)
        symbol = _session("AAPL", session, ("100", "101", "102", "103", "104"))
        benchmark = _session("SPY", session, ("500", "501", "502", "503", "504"), raw_character="b")

        dataset = build_direction_neutral_features(
            symbol_bars=symbol[:2] + symbol[3:],
            benchmark_bars=benchmark,
            market=FeatureMarket.US_REGULAR,
            sessions=_sessions(session),
        )

        ordinals = tuple(item.market_minute_ordinal for item in dataset.observations)
        self.assertEqual(len(ordinals), 3)
        self.assertEqual(ordinals[2] - ordinals[1], 3)
        self.assertIsNone(dataset.observations[-1].family_scores["realized_volatility_5m"])
        self.assertNotEqual(
            dataset.observations[-1].source_window_sha256,
            hashlib.sha256(b"").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
