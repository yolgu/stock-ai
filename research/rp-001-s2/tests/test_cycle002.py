from __future__ import annotations

import hashlib
import math
import unittest
from datetime import date, timedelta

from rp001_s2.cycle002 import (
    Cycle002Abstention,
    Cycle002Family,
    Cycle002Features,
    RegimeEndLabel,
    build_cycle002_features,
    cycle002_basis,
    hypothetical_avoided_continuation_loss,
    label_upside_regime_end,
)
from rp001_s2.cycle002_evaluation import (
    Cycle002Example,
    run_cycle002_purged_oof,
)
from rp001_s2.discovery import DailyObservation, ForecastFeatures
from rp001_s2.evaluation import synchronized_block_max_t


def _base_features(index: int = 60, **overrides: float) -> ForecastFeatures:
    values: dict[str, float | int | str] = {
        "z1": -1.25,
        "m3": 0.5,
        "m5": 2.0,
        "m10": 1.5,
        "m20": 1.5,
        "trend_consistency_10": 0.6,
        "acceleration_3_vs_10": -1.0,
        "return_curvature": -1.25,
        "turnover_surprise": 1.5,
        "return_scale": 0.01,
        "turnover_scale": 0.2,
        "as_of_index": index,
        "series_id": "TEST",
        "signal_session_id": f"S{index:04d}",
        "source_window_sha256": hashlib.sha256(str(index).encode()).hexdigest(),
    }
    values.update(overrides)
    return ForecastFeatures(**values)  # type: ignore[arg-type]


def _cycle_features(index: int = 60, **overrides: float) -> Cycle002Features:
    base_overrides = {
        key: value
        for key, value in overrides.items()
        if key not in {"active_duration_sessions", "cumulative_runup"}
    }
    return Cycle002Features(
        base=_base_features(index, **base_overrides),
        active_duration_sessions=int(overrides.get("active_duration_sessions", 5)),
        cumulative_runup=float(overrides.get("cumulative_runup", 2.5)),
        full_source_window_sha256=hashlib.sha256(f"full:{index}".encode()).hexdigest(),
    )


def _observations(
    count: int = 75,
    signal_index: int = 60,
    *,
    active_at_signal: bool = True,
) -> tuple[DailyObservation, ...]:
    historical_pattern = (0.010, -0.009, 0.005, -0.004, 0.007, -0.006, 0.003)
    returns = [historical_pattern[index % len(historical_pattern)] for index in range(count)]
    if active_at_signal:
        for index in range(signal_index - 4, signal_index + 1):
            returns[index] = 0.018
    for index in range(signal_index + 1, min(signal_index + 11, count)):
        returns[index] = -0.020
    close = 100.0
    start = date(2025, 1, 1)
    rows: list[DailyObservation] = []
    for index, step in enumerate(returns):
        close *= math.exp(step)
        rows.append(
            DailyObservation(
                adjusted_close=close,
                native_close=close,
                native_volume=1_000_000.0 + 17_000.0 * (index % 9),
                currency="USD",
                series_id="TEST",
                session_id=(start + timedelta(days=index)).isoformat(),
                available_as_of_signal=True,
            )
        )
    return tuple(rows)


def _replace_future_returns(
    source: tuple[DailyObservation, ...],
    signal_index: int,
    future_returns: tuple[float, ...],
) -> tuple[DailyObservation, ...]:
    rows = list(source)
    close = float(rows[signal_index].adjusted_close)
    for offset, step in enumerate(future_returns, start=1):
        close *= math.exp(step)
        old = rows[signal_index + offset]
        rows[signal_index + offset] = DailyObservation(
            adjusted_close=close,
            native_close=close,
            native_volume=old.native_volume,
            currency=old.currency,
            series_id=old.series_id,
            session_id=old.session_id,
            available_as_of_signal=True,
        )
    return tuple(rows)


class Cycle002FeatureAndFormulaContractTest(unittest.TestCase):
    def test_features_use_full_forty_one_row_pit_window(self) -> None:
        source = list(_observations())
        before = build_cycle002_features(tuple(source), 60)
        self.assertNotIsInstance(before, Cycle002Abstention)
        assert isinstance(before, Cycle002Features)

        future_changed = list(source)
        future = future_changed[70]
        future_changed[70] = DailyObservation(
            adjusted_close=1_000_000.0,
            native_close=1_000_000.0,
            native_volume=future.native_volume,
            currency=future.currency,
            series_id=future.series_id,
            session_id=future.session_id,
            available_as_of_signal=True,
        )
        self.assertEqual(before, build_cycle002_features(tuple(future_changed), 60))

        extra_history_changed = list(source)
        old = extra_history_changed[25]
        extra_history_changed[25] = DailyObservation(
            adjusted_close=old.adjusted_close,
            native_close=float(old.native_close) * math.exp(0.001),
            native_volume=old.native_volume,
            currency=old.currency,
            series_id=old.series_id,
            session_id=old.session_id,
            available_as_of_signal=True,
        )
        after = build_cycle002_features(tuple(extra_history_changed), 60)
        self.assertNotIsInstance(after, Cycle002Abstention)
        assert isinstance(after, Cycle002Features)
        self.assertEqual(before.base.source_window_sha256, after.base.source_window_sha256)
        self.assertNotEqual(before.full_source_window_sha256, after.full_source_window_sha256)

    def test_three_end_hazard_families_match_frozen_equations(self) -> None:
        features = _cycle_features()

        stretch = cycle002_basis(Cycle002Family.TAIL_STRETCH_REVERSION, features)
        self.assertEqual((0.5, 0.4, 0.5), stretch.values[:3])
        self.assertAlmostEqual((0.5 * 0.4 * 0.5) ** (1.0 / 3.0), stretch.values[3], places=14)

        distribution = cycle002_basis(Cycle002Family.DECELERATION_DISTRIBUTION, features)
        self.assertEqual((0.5, 0.4, 0.5), distribution.values[:3])
        self.assertAlmostEqual((0.5 * 0.5 * 0.5) ** (1.0 / 3.0), distribution.values[3], places=14)

        duration = cycle002_basis(Cycle002Family.ACTIVE_DURATION_HAZARD, features)
        self.assertEqual((0.8, 2.0 / 7.0, 0.5), duration.values[:3])
        self.assertAlmostEqual(math.sqrt((2.0 / 7.0) * 0.5), duration.values[3], places=14)

    def test_all_formula_values_are_bounded_and_family_ids_are_distinct(self) -> None:
        bases = tuple(cycle002_basis(family, _cycle_features()) for family in Cycle002Family)

        self.assertEqual(3, len({basis.formula_id for basis in bases}))
        self.assertTrue(
            all(
                all(0.0 <= value <= 1.0 for value in basis.values)
                for basis in bases
            )
        )


class Cycle002RegimeEndLabelContractTest(unittest.TestCase):
    def test_active_upside_regime_end_is_labeled_only_from_future_rows(self) -> None:
        source = _observations()
        features = build_cycle002_features(source, 60)
        self.assertNotIsInstance(features, Cycle002Abstention)
        assert isinstance(features, Cycle002Features)
        self.assertGreaterEqual(features.base.m5, 1.0)

        label = label_upside_regime_end(source, 60, features)

        self.assertIsInstance(label, RegimeEndLabel)
        assert isinstance(label, RegimeEndLabel)
        self.assertTrue(label.outcome)
        self.assertIsNotNone(label.end_offset_sessions)
        self.assertEqual(features, build_cycle002_features(source, 60))

    def test_inactive_signal_state_is_ineligible(self) -> None:
        source = _observations(active_at_signal=False)
        features = build_cycle002_features(source, 60)
        self.assertNotIsInstance(features, Cycle002Abstention)
        assert isinstance(features, Cycle002Features)
        self.assertLess(features.base.m5, 1.0)

        label = label_upside_regime_end(source, 60, features)

        self.assertEqual("inactive_upside_regime_at_signal", label.reason)

    def test_early_end_that_recovers_by_session_ten_is_negative(self) -> None:
        source = _observations()
        features = build_cycle002_features(source, 60)
        self.assertNotIsInstance(features, Cycle002Abstention)
        assert isinstance(features, Cycle002Features)
        recovered = _replace_future_returns(
            source,
            60,
            (-0.020,) * 5 + (0.030,) * 5,
        )

        label = label_upside_regime_end(recovered, 60, features)

        self.assertIsInstance(label, RegimeEndLabel)
        assert isinstance(label, RegimeEndLabel)
        self.assertFalse(label.outcome)

    def test_first_end_after_search_window_is_negative(self) -> None:
        source = _observations()
        features = build_cycle002_features(source, 60)
        self.assertNotIsInstance(features, Cycle002Abstention)
        assert isinstance(features, Cycle002Features)
        day_six_end = _replace_future_returns(
            source,
            60,
            (0.005,) * 5 + (-0.030,) * 5,
        )

        label = label_upside_regime_end(day_six_end, 60, features)

        self.assertIsInstance(label, RegimeEndLabel)
        assert isinstance(label, RegimeEndLabel)
        self.assertFalse(label.outcome)

    def test_rows_after_session_ten_change_neither_features_nor_label(self) -> None:
        source = list(_observations())
        features = build_cycle002_features(tuple(source), 60)
        self.assertNotIsInstance(features, Cycle002Abstention)
        assert isinstance(features, Cycle002Features)
        label = label_upside_regime_end(tuple(source), 60, features)
        old = source[71]
        source[71] = DailyObservation(
            adjusted_close=9_000_000.0,
            native_close=9_000_000.0,
            native_volume=old.native_volume,
            currency=old.currency,
            series_id=old.series_id,
            session_id=old.session_id,
            available_as_of_signal=True,
        )

        self.assertEqual(features, build_cycle002_features(tuple(source), 60))
        self.assertEqual(label, label_upside_regime_end(tuple(source), 60, features))


class Cycle002ResearchEconomicsContractTest(unittest.TestCase):
    def test_end_alarm_uses_avoided_long_loss_not_long_entry_return(self) -> None:
        self.assertAlmostEqual(
            0.09,
            hypothetical_avoided_continuation_loss(100.0, 90.0, cost_bps=100.0),
            places=14,
        )
        self.assertAlmostEqual(
            -0.11,
            hypothetical_avoided_continuation_loss(100.0, 110.0, cost_bps=100.0),
            places=14,
        )


class Cycle002EvaluationContractTest(unittest.TestCase):
    def test_all_families_use_identical_purged_oof_rows(self) -> None:
        examples = tuple(
            Cycle002Example(
                row_id=f"A:{index}",
                symbol="A",
                session_index=index,
                session_id=f"S{index:04d}",
                features=_cycle_features(
                    index,
                    z1=2.5 * ((index % 17) / 16.0) - 1.25,
                    m3=2.0 * ((index % 17) / 16.0),
                    m5=1.0 + 2.0 * ((index % 17) / 16.0),
                    m10=0.5 + 2.5 * ((index % 17) / 16.0),
                    m20=3.0 * ((index % 17) / 16.0),
                    return_curvature=2.5 * ((index % 17) / 16.0) - 1.25,
                    turnover_surprise=3.0 * ((index % 17) / 16.0),
                    active_duration_sessions=1 + index % 10,
                    cumulative_runup=1.0 + 3.0 * ((index % 17) / 16.0),
                ),
                outcome=(index % 17) >= 13,
                end_offset_sessions=2 if (index % 17) >= 13 else None,
            )
            for index in range(875)
        )

        result = run_cycle002_purged_oof(examples, session_count=875)

        reference = {
            row.row_id
            for row in result.predictions
            if row.family_id == result.family_ids[0]
        }
        for family_id in result.family_ids:
            self.assertEqual(
                reference,
                {
                    row.row_id
                    for row in result.predictions
                    if row.family_id == family_id
                },
            )
        inference = synchronized_block_max_t(
            result.predictions,
            replicates=100,
            block_length_sessions=20,
        )
        self.assertEqual(6, len(inference.contrasts))


if __name__ == "__main__":
    unittest.main()
