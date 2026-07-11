from __future__ import annotations

import math
import unittest
from datetime import date, timedelta

from rp001_s2.discovery import (
    Abstention,
    AbstentionReason,
    CandidateFamily,
    FormulaBasis,
    ConstrainedLogisticModel,
    DailyObservation,
    IneligibleOnsetLabel,
    OnsetLabel,
    TrainingRow,
    build_forecast_features,
    candidate_basis,
    fit_constrained_logistic,
    label_upside_regime_onset,
    model_kkt_residual,
    predict_probability,
)


def _observations(
    *,
    count: int = 45,
    close_scale: float = 1.0,
    volume_scale: float = 1.0,
) -> tuple[DailyObservation, ...]:
    values: list[DailyObservation] = []
    close = 100.0
    return_pattern = (0.012, -0.008, 0.004, -0.003, 0.009, -0.006, 0.002)
    start = date(2025, 1, 1)
    for index in range(count):
        return_step = return_pattern[index % len(return_pattern)]
        close *= math.exp(return_step)
        volume = (1_000_000.0 + 17_000.0 * (index % 7)) * volume_scale
        values.append(
            DailyObservation(
                adjusted_close=close * close_scale,
                native_close=close * close_scale,
                native_volume=volume,
                currency="USD",
                series_id="TEST",
                session_id=(start + timedelta(days=index)).isoformat(),
                available_as_of_signal=True,
            )
        )
    return tuple(values)


class ForecastFeatureContractTest(unittest.TestCase):
    def test_requires_twenty_two_point_in_time_rows(self) -> None:
        result = build_forecast_features(_observations(), 20)

        self.assertEqual(
            result,
            Abstention(
                AbstentionReason.INSUFFICIENT_HISTORY,
                "22 observations ending at the signal session are required",
            ),
        )

    def test_future_rows_do_not_change_features(self) -> None:
        source = _observations(count=35)
        before = build_forecast_features(source, 25)
        extended = source + tuple(
            DailyObservation(
                adjusted_close=1_000_000.0 + index,
                native_close=1_000_000.0 + index,
                native_volume=9_000_000.0 + index,
                currency="USD",
                series_id="TEST",
                session_id=(date(2027, 1, 1) + timedelta(days=index)).isoformat(),
                available_as_of_signal=True,
            )
            for index in range(5)
        )

        self.assertEqual(before, build_forecast_features(extended, 25))

    def test_price_scale_and_split_neutral_turnover_are_invariant(self) -> None:
        source = _observations(count=35)
        scaled = tuple(
            DailyObservation(
                adjusted_close=row.adjusted_close * 10.0,
                native_close=row.native_close * 10.0,
                native_volume=row.native_volume / 10.0,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=row.available_as_of_signal,
            )
            for row in source
        )

        original_features = build_forecast_features(source, 25)
        scaled_features = build_forecast_features(scaled, 25)
        self.assertNotIsInstance(original_features, Abstention)
        self.assertNotIsInstance(scaled_features, Abstention)
        assert not isinstance(original_features, Abstention)
        assert not isinstance(scaled_features, Abstention)
        self.assertNotEqual(
            original_features.source_window_sha256,
            scaled_features.source_window_sha256,
        )
        for name in (
            "z1",
            "m3",
            "m5",
            "m10",
            "m20",
            "trend_consistency_10",
            "acceleration_3_vs_10",
            "return_curvature",
            "turnover_surprise",
            "return_scale",
            "turnover_scale",
        ):
            self.assertAlmostEqual(
                getattr(original_features, name),
                getattr(scaled_features, name),
                places=12,
            )

    def test_missing_or_zero_volume_abstains_without_imputation(self) -> None:
        source = list(_observations(count=35))
        source[25] = DailyObservation(
            adjusted_close=source[25].adjusted_close,
            native_close=source[25].native_close,
            native_volume=0.0,
            currency="USD",
            series_id="TEST",
            session_id=source[25].session_id,
            available_as_of_signal=True,
        )

        result = build_forecast_features(tuple(source), 25)

        self.assertIsInstance(result, Abstention)
        assert isinstance(result, Abstention)
        self.assertEqual(result.reason, AbstentionReason.NONPOSITIVE_REQUIRED_VALUE)

    def test_unavailable_row_abstains(self) -> None:
        source = list(_observations(count=35))
        row = source[24]
        source[24] = DailyObservation(
            adjusted_close=row.adjusted_close,
            native_close=row.native_close,
            native_volume=row.native_volume,
            currency=row.currency,
            series_id=row.series_id,
            session_id=row.session_id,
            available_as_of_signal=False,
        )

        result = build_forecast_features(tuple(source), 25)

        self.assertIsInstance(result, Abstention)
        assert isinstance(result, Abstention)
        self.assertEqual(result.reason, AbstentionReason.UNAVAILABLE_AS_OF_SIGNAL)

    def test_constant_series_and_nonfinite_values_abstain(self) -> None:
        source = tuple(
            DailyObservation(
                adjusted_close=100.0,
                native_close=100.0,
                native_volume=1_000_000.0,
                currency="USD",
                series_id="TEST",
                session_id=(date(2025, 1, 1) + timedelta(days=index)).isoformat(),
                available_as_of_signal=True,
            )
            for index in range(30)
        )
        constant = build_forecast_features(source, 25)
        self.assertIsInstance(constant, Abstention)
        assert isinstance(constant, Abstention)
        self.assertEqual(constant.reason, AbstentionReason.ZERO_VARIATION)

        invalid = list(_observations(count=35))
        row = invalid[25]
        invalid[25] = DailyObservation(
            adjusted_close=row.adjusted_close,
            native_close=float("inf"),
            native_volume=row.native_volume,
            currency=row.currency,
            series_id=row.series_id,
            session_id=row.session_id,
            available_as_of_signal=True,
        )
        nonfinite = build_forecast_features(tuple(invalid), 25)
        self.assertIsInstance(nonfinite, Abstention)
        assert isinstance(nonfinite, Abstention)
        self.assertEqual(nonfinite.reason, AbstentionReason.NONFINITE_REQUIRED_VALUE)

    def test_piecewise_native_split_is_quarantined(self) -> None:
        source = list(_observations(count=35))
        for index in range(24, len(source)):
            row = source[index]
            source[index] = DailyObservation(
                adjusted_close=row.adjusted_close,
                native_close=row.native_close / 2.0,
                native_volume=row.native_volume * 2.0,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=True,
            )

        result = build_forecast_features(tuple(source), 25)

        self.assertIsInstance(result, Abstention)
        assert isinstance(result, Abstention)
        self.assertEqual(result.reason, AbstentionReason.SUSPECTED_CORPORATE_ACTION)


class CandidateFormulaContractTest(unittest.TestCase):
    def test_all_three_families_have_bounded_basis_values(self) -> None:
        features = build_forecast_features(_observations(count=35), 25)
        self.assertNotIsInstance(features, Abstention)

        for family in CandidateFamily:
            basis = candidate_basis(family, features)
            self.assertGreaterEqual(len(basis.values), 3)
            self.assertTrue(all(0.0 <= value <= 1.0 for value in basis.values))

    def test_family_basis_matches_hand_calculated_piecewise_equations(self) -> None:
        features = build_forecast_features(_observations(count=35), 25)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        reference = type(features)(
            **{
                **features.__dict__,
                "z1": 1.375,
                "m3": 1.375,
                "m5": 1.375,
                "m10": 2.5,
                "trend_consistency_10": 0.7,
                "acceleration_3_vs_10": 1.0,
                "return_curvature": 1.0,
                "turnover_surprise": 1.5,
            }
        )

        for actual, expected in zip(
            candidate_basis(
                CandidateFamily.MULTI_HORIZON_TREND,
                reference,
            ).values,
            (0.5, 1.0, 0.5, 0.5),
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=14)
        self.assertEqual(
            candidate_basis(CandidateFamily.ACCELERATION_CURVATURE, reference).values,
            (0.5, 0.5, 0.5, 0.25),
        )
        gated = candidate_basis(CandidateFamily.VOLUME_CONFIRMED_GATE, reference).values
        self.assertAlmostEqual(gated[0], 0.5, places=14)
        self.assertAlmostEqual(gated[1], 0.5, places=14)
        self.assertAlmostEqual(gated[2], 0.25 ** (1.0 / 3.0), places=14)

    def test_probability_matches_the_frozen_logistic_equation(self) -> None:
        model = ConstrainedLogisticModel(
            formula_id=CandidateFamily.VOLUME_CONFIRMED_GATE.value,
            intercept=-1.0,
            nonnegative_weights=(0.5, 1.0, 0.25),
            l2_penalty=1.0,
        )
        basis = FormulaBasis(
            CandidateFamily.VOLUME_CONFIRMED_GATE.value,
            (0.2, 0.4, 0.8),
        )

        expected = 1.0 / (1.0 + math.exp(-(-1.0 + 0.5 * 0.2 + 1.0 * 0.4 + 0.25 * 0.8)))

        self.assertAlmostEqual(predict_probability(model, basis), expected, places=14)

    def test_nonnegative_weights_make_probability_basis_monotone(self) -> None:
        model = ConstrainedLogisticModel(
            formula_id=CandidateFamily.VOLUME_CONFIRMED_GATE.value,
            intercept=-2.0,
            nonnegative_weights=(0.2, 0.7, 1.4),
            l2_penalty=0.1,
        )

        low = predict_probability(
            model,
            FormulaBasis(model.formula_id, (0.1, 0.2, 0.3)),
        )
        high = predict_probability(
            model,
            FormulaBasis(model.formula_id, (0.2, 0.3, 0.4)),
        )

        self.assertGreater(high, low)

    def test_training_projects_all_signal_weights_nonnegative(self) -> None:
        rows = tuple(
            TrainingRow(
                basis=FormulaBasis(
                    CandidateFamily.VOLUME_CONFIRMED_GATE.value,
                    (index / 20.0, 1.0 - index / 20.0, (index % 4) / 3.0),
                ),
                outcome=index >= 12,
            )
            for index in range(21)
        )

        model = fit_constrained_logistic(rows, l2_penalty=1.0)

        self.assertTrue(all(weight >= 0.0 for weight in model.nonnegative_weights))
        self.assertTrue(math.isfinite(model.intercept))
        self.assertLessEqual(model_kkt_residual(rows, model), 1e-6)

    def test_wrong_basis_dimension_is_rejected(self) -> None:
        model = ConstrainedLogisticModel(
            formula_id=CandidateFamily.VOLUME_CONFIRMED_GATE.value,
            intercept=0.0,
            nonnegative_weights=(1.0, 1.0, 1.0),
            l2_penalty=1.0,
        )

        with self.assertRaisesRegex(ValueError, "basis_dimension_mismatch"):
            predict_probability(
                model,
                FormulaBasis(model.formula_id, (0.1, 0.2)),
            )

    def test_model_rejects_basis_from_another_formula_family(self) -> None:
        model = ConstrainedLogisticModel(
            formula_id=CandidateFamily.MULTI_HORIZON_TREND.value,
            intercept=0.0,
            nonnegative_weights=(1.0, 1.0, 1.0, 1.0),
            l2_penalty=1.0,
        )

        with self.assertRaisesRegex(ValueError, "formula_family_mismatch"):
            predict_probability(
                model,
                FormulaBasis(
                    CandidateFamily.ACCELERATION_CURVATURE.value,
                    (0.1, 0.2, 0.3, 0.4),
                ),
            )

    def test_one_class_or_zero_penalty_training_is_invalid(self) -> None:
        rows = tuple(
            TrainingRow(
                basis=FormulaBasis(
                    CandidateFamily.MULTI_HORIZON_TREND.value,
                    (0.1, 0.2, 0.3, 0.4),
                ),
                outcome=False,
            )
            for _ in range(10)
        )

        with self.assertRaisesRegex(ValueError, "training_requires_both_outcomes"):
            fit_constrained_logistic(rows, l2_penalty=1.0)
        mixed = rows[:-1] + (
            TrainingRow(rows[-1].basis, True),
        )
        with self.assertRaisesRegex(ValueError, "l2_penalty_out_of_domain"):
            fit_constrained_logistic(mixed, l2_penalty=0.0)

        with self.assertRaisesRegex(ValueError, "training_outcome_must_be_bool"):
            TrainingRow(rows[0].basis, 1)  # type: ignore[arg-type]

    def test_direct_out_of_domain_feature_construction_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "standardized_feature_out_of_domain"):
            features = build_forecast_features(_observations(count=35), 25)
            assert not isinstance(features, Abstention)
            type(features)(
                **{
                    **features.__dict__,
                    "z1": 100.0,
                }
            )

    def test_every_volume_confirmed_gate_term_requires_turnover(self) -> None:
        features = build_forecast_features(_observations(count=35), 25)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        no_turnover = type(features)(
            **{
                **features.__dict__,
                "turnover_surprise": -1.0,
            }
        )

        basis = candidate_basis(CandidateFamily.VOLUME_CONFIRMED_GATE, no_turnover)

        self.assertEqual(basis.values, (0.0, 0.0, 0.0))


class OnsetLabelContractTest(unittest.TestCase):
    def test_future_rows_are_used_only_by_the_label(self) -> None:
        source = list(_observations(count=40))
        signal_index = 25
        features = build_forecast_features(tuple(source), signal_index)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        signal_close = source[signal_index].adjusted_close
        for offset in range(1, 11):
            row = source[signal_index + offset]
            multiplier = math.exp(0.04 * min(offset, 5))
            if offset > 5:
                multiplier = math.exp(0.12)
            source[signal_index + offset] = DailyObservation(
                adjusted_close=signal_close * multiplier,
                native_close=signal_close * multiplier,
                native_volume=row.native_volume,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=True,
            )

        unchanged = build_forecast_features(tuple(source), signal_index)
        label = label_upside_regime_onset(tuple(source), signal_index, features)

        self.assertEqual(unchanged, features)
        self.assertIsInstance(label, OnsetLabel)
        assert isinstance(label, OnsetLabel)
        self.assertTrue(label.outcome)
        self.assertIsNotNone(label.onset_offset_sessions)

    def test_active_signal_state_is_excluded_from_onset_estimand(self) -> None:
        source = list(_observations(count=40))
        signal_index = 25
        for offset in range(signal_index - 4, signal_index + 1):
            prior = source[offset - 1]
            row = source[offset]
            source[offset] = DailyObservation(
                adjusted_close=prior.adjusted_close * 1.02,
                native_close=prior.native_close * 1.02,
                native_volume=row.native_volume,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=True,
            )
        features = build_forecast_features(tuple(source), signal_index)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)

        result = label_upside_regime_onset(tuple(source), signal_index, features)

        self.assertEqual(
            result,
            IneligibleOnsetLabel("active_upside_regime_at_signal"),
        )

    def test_day_six_crossing_is_not_onset_by_five_persistent_at_ten(self) -> None:
        source = list(_observations(count=40))
        signal_index = 25
        features = build_forecast_features(tuple(source), signal_index)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        signal_close = source[signal_index].adjusted_close
        for offset in range(1, 11):
            row = source[signal_index + offset]
            multiplier = 1.0 if offset < 6 else math.exp(3.0 * features.return_scale)
            source[signal_index + offset] = DailyObservation(
                adjusted_close=signal_close * multiplier,
                native_close=signal_close * multiplier,
                native_volume=row.native_volume,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=True,
            )

        result = label_upside_regime_onset(tuple(source), signal_index, features)

        self.assertEqual(result, OnsetLabel(False, None))

    def test_early_excursion_without_day_ten_persistence_is_negative(self) -> None:
        source = list(_observations(count=40))
        signal_index = 25
        features = build_forecast_features(tuple(source), signal_index)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        signal_close = source[signal_index].adjusted_close
        for offset in range(1, 11):
            row = source[signal_index + offset]
            standardized = 3.0 if offset <= 5 else 0.5
            source[signal_index + offset] = DailyObservation(
                adjusted_close=signal_close * math.exp(
                    standardized * features.return_scale
                ),
                native_close=row.native_close,
                native_volume=row.native_volume,
                currency=row.currency,
                series_id=row.series_id,
                session_id=row.session_id,
                available_as_of_signal=True,
            )

        result = label_upside_regime_onset(tuple(source), signal_index, features)

        self.assertEqual(result, OnsetLabel(False, None))

    def test_shuffled_session_window_abstains(self) -> None:
        source = list(_observations(count=35))
        source[23], source[24] = source[24], source[23]

        result = build_forecast_features(tuple(source), 25)

        self.assertIsInstance(result, Abstention)
        assert isinstance(result, Abstention)
        self.assertEqual(result.reason, AbstentionReason.SESSION_ORDER_INVALID)

    def test_shuffled_future_label_horizon_is_ineligible(self) -> None:
        source = list(_observations(count=40))
        signal_index = 25
        features = build_forecast_features(tuple(source), signal_index)
        self.assertNotIsInstance(features, Abstention)
        assert not isinstance(features, Abstention)
        source[signal_index + 1], source[signal_index + 2] = (
            source[signal_index + 2],
            source[signal_index + 1],
        )

        result = label_upside_regime_onset(tuple(source), signal_index, features)

        self.assertEqual(result, IneligibleOnsetLabel("invalid_future_session_order"))


if __name__ == "__main__":
    unittest.main()
