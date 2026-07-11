from __future__ import annotations

import hashlib
import math
import unittest
from datetime import date, timedelta

from rp001_s2.cycle003 import (
    Cycle003Abstention,
    Cycle003Family,
    Cycle003Features,
    RecoveryLabel,
    build_cycle003_features,
    cycle003_basis,
    hypothetical_recovery_long_return,
    label_downside_regime_recovery,
)
from rp001_s2.cycle003_evaluation import (
    Cycle003Example,
    Cycle003PredictionRow,
    choose_cycle003_alarm_threshold,
    run_cycle003_purged_oof,
)
from rp001_s2.discovery import DailyObservation, ForecastFeatures
from rp001_s2.evaluation import synchronized_block_max_t


def _base_features(index: int = 60, **overrides: float) -> ForecastFeatures:
    values: dict[str, float | int | str] = {
        "z1": 1.25,
        "m3": -0.5,
        "m5": -2.0,
        "m10": -1.5,
        "m20": -1.5,
        "trend_consistency_10": 0.4,
        "acceleration_3_vs_10": 1.0,
        "return_curvature": 1.25,
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


def _cycle_features(index: int = 60, **overrides: float) -> Cycle003Features:
    base_overrides = {
        key: value
        for key, value in overrides.items()
        if key not in {"downside_duration_sessions", "cumulative_drawdown"}
    }
    return Cycle003Features(
        base=_base_features(index, **base_overrides),
        downside_duration_sessions=int(overrides.get("downside_duration_sessions", 5)),
        cumulative_drawdown=float(overrides.get("cumulative_drawdown", 2.5)),
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
            returns[index] = -0.018
    for index in range(signal_index + 1, min(signal_index + 11, count)):
        returns[index] = 0.020
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


class Cycle003FeatureFormulaContractTest(unittest.TestCase):
    def test_features_are_pit_and_bind_all_forty_one_rows(self) -> None:
        source = list(_observations())
        before = build_cycle003_features(tuple(source), 60)
        self.assertNotIsInstance(before, Cycle003Abstention)
        assert isinstance(before, Cycle003Features)

        future = source[70]
        source[70] = DailyObservation(
            adjusted_close=8_000_000.0,
            native_close=8_000_000.0,
            native_volume=future.native_volume,
            currency=future.currency,
            series_id=future.series_id,
            session_id=future.session_id,
            available_as_of_signal=True,
        )
        self.assertEqual(before, build_cycle003_features(tuple(source), 60))

        source = list(_observations())
        history = source[25]
        source[25] = DailyObservation(
            adjusted_close=history.adjusted_close,
            native_close=float(history.native_close) * math.exp(0.001),
            native_volume=history.native_volume,
            currency=history.currency,
            series_id=history.series_id,
            session_id=history.session_id,
            available_as_of_signal=True,
        )
        after = build_cycle003_features(tuple(source), 60)
        self.assertNotIsInstance(after, Cycle003Abstention)
        assert isinstance(after, Cycle003Features)
        self.assertEqual(before.base.source_window_sha256, after.base.source_window_sha256)
        self.assertNotEqual(before.full_source_window_sha256, after.full_source_window_sha256)

    def test_three_recovery_families_match_frozen_equations(self) -> None:
        features = _cycle_features()
        capitulation = cycle003_basis(
            Cycle003Family.DOWNSIDE_DECELERATION_CAPITULATION,
            features,
        )
        self.assertEqual((0.5, 0.4, 0.5), capitulation.values[:3])
        self.assertAlmostEqual(0.5, capitulation.values[3], places=14)

        stretch = cycle003_basis(Cycle003Family.LOWER_TAIL_STRETCH_REVERSAL, features)
        self.assertEqual((0.5, 0.4, 0.5), stretch.values[:3])
        self.assertAlmostEqual((0.5 * 0.4 * 0.5) ** (1.0 / 3.0), stretch.values[3], places=14)

        duration = cycle003_basis(
            Cycle003Family.DOWNSIDE_DURATION_RECOVERY_HAZARD,
            features,
        )
        self.assertEqual((0.8, 2.0 / 7.0, 0.5), duration.values[:3])
        self.assertAlmostEqual(math.sqrt((2.0 / 7.0) * 0.5), duration.values[3], places=14)

    def test_all_family_ids_are_distinct_and_bases_are_bounded(self) -> None:
        bases = tuple(cycle003_basis(family, _cycle_features()) for family in Cycle003Family)
        self.assertEqual(3, len({basis.formula_id for basis in bases}))
        self.assertTrue(
            all(all(0.0 <= value <= 1.0 for value in basis.values) for basis in bases)
        )


class Cycle003RecoveryLabelContractTest(unittest.TestCase):
    def test_active_downside_regime_recovery_uses_only_future_label_rows(self) -> None:
        source = _observations()
        features = build_cycle003_features(source, 60)
        self.assertNotIsInstance(features, Cycle003Abstention)
        assert isinstance(features, Cycle003Features)
        self.assertLessEqual(features.base.m5, -1.0)

        label = label_downside_regime_recovery(source, 60, features)

        self.assertIsInstance(label, RecoveryLabel)
        assert isinstance(label, RecoveryLabel)
        self.assertTrue(label.outcome)
        self.assertIsNotNone(label.recovery_offset_sessions)

    def test_inactive_downside_signal_is_ineligible(self) -> None:
        source = _observations(active_at_signal=False)
        features = build_cycle003_features(source, 60)
        self.assertNotIsInstance(features, Cycle003Abstention)
        assert isinstance(features, Cycle003Features)
        self.assertGreater(features.base.m5, -1.0)

        label = label_downside_regime_recovery(source, 60, features)

        self.assertEqual("inactive_downside_regime_at_signal", label.reason)

    def test_early_recovery_that_relapses_by_session_ten_is_negative(self) -> None:
        source = _observations()
        features = build_cycle003_features(source, 60)
        self.assertNotIsInstance(features, Cycle003Abstention)
        assert isinstance(features, Cycle003Features)
        relapsed = _replace_future_returns(source, 60, (0.020,) * 5 + (-0.030,) * 5)

        label = label_downside_regime_recovery(relapsed, 60, features)

        self.assertIsInstance(label, RecoveryLabel)
        assert isinstance(label, RecoveryLabel)
        self.assertFalse(label.outcome)

    def test_first_recovery_after_session_five_is_negative(self) -> None:
        source = _observations()
        features = build_cycle003_features(source, 60)
        self.assertNotIsInstance(features, Cycle003Abstention)
        assert isinstance(features, Cycle003Features)
        day_six = _replace_future_returns(source, 60, (-0.005,) * 5 + (0.030,) * 5)

        label = label_downside_regime_recovery(day_six, 60, features)

        self.assertIsInstance(label, RecoveryLabel)
        assert isinstance(label, RecoveryLabel)
        self.assertFalse(label.outcome)

    def test_session_eleven_change_affects_neither_features_nor_label(self) -> None:
        source = list(_observations())
        features = build_cycle003_features(tuple(source), 60)
        self.assertNotIsInstance(features, Cycle003Abstention)
        assert isinstance(features, Cycle003Features)
        label = label_downside_regime_recovery(tuple(source), 60, features)
        old = source[71]
        source[71] = DailyObservation(
            adjusted_close=7_000_000.0,
            native_close=7_000_000.0,
            native_volume=old.native_volume,
            currency=old.currency,
            series_id=old.series_id,
            session_id=old.session_id,
            available_as_of_signal=True,
        )
        self.assertEqual(features, build_cycle003_features(tuple(source), 60))
        self.assertEqual(
            label,
            label_downside_regime_recovery(tuple(source), 60, features),
        )


class Cycle003ThresholdEconomicsContractTest(unittest.TestCase):
    def test_q90_ties_do_not_expand_alarm_count(self) -> None:
        rows = tuple(
            Cycle003PredictionRow(
                family_id="F",
                fold_id="fold",
                row_id=str(index),
                symbol="A",
                session_id=f"S{index:02d}",
                outcome=index % 4 == 0,
                recovery_offset_sessions=2 if index % 4 == 0 else None,
                candidate_probability=0.25,
                baseline_constant_probability=0.25,
                baseline_trend_probability=0.25,
            )
            for index in range(20)
        )

        selection = choose_cycle003_alarm_threshold(rows)

        self.assertEqual(0, selection.alarm_count)
        self.assertGreater(float(selection.threshold), 0.25)

    def test_recovery_economics_uses_long_return_sign(self) -> None:
        self.assertAlmostEqual(
            0.09,
            hypothetical_recovery_long_return(100.0, 110.0, cost_bps=100.0),
            places=14,
        )
        self.assertAlmostEqual(
            -0.11,
            hypothetical_recovery_long_return(100.0, 90.0, cost_bps=100.0),
            places=14,
        )


class Cycle003EvaluationContractTest(unittest.TestCase):
    def test_all_candidates_use_identical_purged_oof_rows(self) -> None:
        examples = tuple(
            Cycle003Example(
                row_id=f"A:{index}",
                symbol="A",
                session_index=index,
                session_id=f"S{index:04d}",
                features=_cycle_features(
                    index,
                    z1=2.5 * ((index % 17) / 16.0),
                    m3=-2.0 + 2.0 * ((index % 17) / 16.0),
                    m5=-1.0 - 2.0 * ((index % 17) / 16.0),
                    m10=-0.5 - 2.5 * ((index % 17) / 16.0),
                    m20=-3.0 * ((index % 17) / 16.0),
                    return_curvature=2.5 * ((index % 17) / 16.0),
                    turnover_surprise=3.0 * ((index % 17) / 16.0),
                    downside_duration_sessions=1 + index % 10,
                    cumulative_drawdown=1.0 + 3.0 * ((index % 17) / 16.0),
                ),
                outcome=(index % 17) >= 13,
                recovery_offset_sessions=2 if (index % 17) >= 13 else None,
            )
            for index in range(875)
        )

        result = run_cycle003_purged_oof(examples, session_count=875)

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
