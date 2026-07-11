from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Callable, TypeVar, cast

import rp001.interim_evaluation as evaluation
from rp001.sensitive_value_policy import find_sensitive_values


T = TypeVar("T")


def _key(**overrides: str) -> evaluation.CommonEvaluationKey:
    values = {
        "outcome_id": "price_volume_upside_continuation_10d",
        "fold_id": "fold-001",
        "sample_role": "unseen_historical_confirmation",
        "training_mapping_id": "mapping-001",
    }
    values.update(overrides)
    return evaluation.CommonEvaluationKey(**values)


def _row(
    row_number: int,
    *,
    evaluation_key: evaluation.CommonEvaluationKey | None = None,
    series_id: str = "SERIES-A",
    session_id: str | None = None,
    time_index: int | None = None,
    global_session_index: int | None = None,
    outcome: bool = False,
    candidate_probability: float = 0.1,
    b1_probability: float = 0.2,
    b2_probability: float = 0.3,
) -> evaluation.CommonEvaluationRow:
    return evaluation.CommonEvaluationRow(
        evaluation_key=evaluation_key or _key(),
        row_id=f"row-{row_number:04d}",
        series_id=series_id,
        session_id=session_id or f"session-{row_number:04d}",
        time_index=row_number if time_index is None else time_index,
        global_session_index=(
            row_number
            if global_session_index is None
            else global_session_index
        ),
        outcome=outcome,
        candidate_probability=candidate_probability,
        b1_probability=b1_probability,
        b2_probability=b2_probability,
    )


def _call_or_fail(
    testcase: unittest.TestCase,
    callback: Callable[[], T],
) -> T:
    try:
        return callback()
    except NotImplementedError:
        testcase.fail("evaluation behavior is not implemented")


def _assert_contract_error(
    testcase: unittest.TestCase,
    callback: Callable[[], object],
    expected_code: str,
) -> None:
    try:
        callback()
    except NotImplementedError:
        testcase.fail("evaluation behavior is not implemented")
    except evaluation.InterimEvaluationContractError as error:
        testcase.assertEqual(expected_code, error.code)
    else:
        testcase.fail(f"expected contract error: {expected_code}")


def _forecast(
    testcase: unittest.TestCase,
    rows: tuple[evaluation.CommonEvaluationRow, ...],
    selection_context: evaluation.CandidateSelectionContext = (
        evaluation.CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION
    ),
    *,
    replicates: int = 32,
) -> evaluation.CommonForecastEvaluation:
    return _call_or_fail(
        testcase,
        lambda: evaluation.evaluate_common_forecasts(
            rows,
            selection_context,
            seed=evaluation.BOOTSTRAP_SEED,
            block_length=evaluation.BOOTSTRAP_BLOCK_LENGTH,
            replicates=replicates,
        ),
    )


def _zero_cost() -> evaluation.CostScenario:
    return evaluation.CostScenario(
        fees_bps=0.0,
        fx_bps=0.0,
        slippage_bps=0.0,
        market_impact_bps=0.0,
        tax_bps=0.0,
        borrow_hedge_bps=0.0,
    )


def _trade(
    ordinal: int,
    gross_simple_return: float,
    *,
    series_id: str = "SERIES-A",
    entry_index: int | None = None,
    exit_index: int | None = None,
    direction: evaluation.TradeDirection = evaluation.TradeDirection.LONG,
) -> evaluation.HypotheticalTrade:
    start = ordinal * 2 if entry_index is None else entry_index
    stop = start + 1 if exit_index is None else exit_index
    return evaluation.HypotheticalTrade(
        series_id=series_id,
        entry_session_id=f"entry-{ordinal:04d}",
        exit_session_id=f"exit-{ordinal:04d}",
        entry_index=start,
        exit_index=stop,
        gross_simple_return=gross_simple_return,
        direction=direction,
    )


class InterimEvaluationPublicApiTest(unittest.TestCase):
    def test_bootstrap_schema_exposes_global_order_and_truthful_scope(self) -> None:
        row_fields = evaluation.CommonEvaluationRow.__dataclass_fields__
        bootstrap_fields = evaluation.PairedBootstrapResult.__dataclass_fields__

        self.assertIn("global_session_index", row_fields)
        self.assertIn("nonoverlapping_block_capacity", bootstrap_fields)
        self.assertIn("inference_scope", bootstrap_fields)
        self.assertIn(
            "symbol_superpopulation_uncertainty", bootstrap_fields
        )
        self.assertNotIn(
            "effective_independent_block_count", bootstrap_fields
        )

    def test_evaluation_module_exposes_the_frozen_research_api(self) -> None:
        required_symbols = {
            "ALARM_THRESHOLD",
            "BOOTSTRAP_BLOCK_LENGTH",
            "BOOTSTRAP_REPLICATES",
            "BOOTSTRAP_SEED",
            "BOOTSTRAP_INFERENCE_SCOPE",
            "BootstrapStatus",
            "OPERATIONAL_DISPOSITION",
            "OVERLAP_POLICY",
            "PRIMARY_BRIER_DELTA",
            "TEMPORAL_IDENTIFICATION_STATUS",
            "USAGE_SCOPE",
            "CalibrationBin",
            "CalibrationSummary",
            "CandidateComparison",
            "CandidateComparisonStatus",
            "CandidateSelectionContext",
            "CommonEvaluationKey",
            "CommonEvaluationRow",
            "CommonForecastEvaluation",
            "CostScenario",
            "EconomicEvaluationStatus",
            "EconomicEvaluationUnavailable",
            "EconomicPerformance",
            "ForecastMetrics",
            "ForecastModel",
            "HypotheticalTrade",
            "InterimEvaluationContractError",
            "MetricStatus",
            "PairedBootstrapResult",
            "RateEstimate",
            "ShortExecutionEvidence",
            "SYMBOL_SUPERPOPULATION_UNCERTAINTY",
            "TailRiskEstimate",
            "TailRiskStatus",
            "TemporalMetricIdentification",
            "TradeDirection",
            "evaluate_common_forecasts",
            "evaluate_hypothetical_trades",
            "moving_block_bootstrap",
        }
        missing_symbols = sorted(
            symbol for symbol in required_symbols if not hasattr(evaluation, symbol)
        )
        self.assertEqual(
            [],
            missing_symbols,
            f"missing frozen evaluation symbols: {missing_symbols}",
        )

    def test_research_boundary_constants_are_exact_and_dataclasses_are_frozen(
        self,
    ) -> None:
        self.assertEqual("research_only", evaluation.USAGE_SCOPE)
        self.assertEqual(
            "NoTrade/no integration", evaluation.OPERATIONAL_DISPOSITION
        )
        self.assertEqual(0.005, evaluation.PRIMARY_BRIER_DELTA)
        self.assertEqual(0.50, evaluation.ALARM_THRESHOLD)
        self.assertEqual(20260710, evaluation.BOOTSTRAP_SEED)
        self.assertEqual(20, evaluation.BOOTSTRAP_BLOCK_LENGTH)
        self.assertEqual(2000, evaluation.BOOTSTRAP_REPLICATES)
        self.assertEqual(
            "one_position_at_a_time_per_series_closed_intervals",
            evaluation.OVERLAP_POLICY,
        )
        row = _row(1)
        with self.assertRaises(FrozenInstanceError):
            row.row_id = "changed"  # type: ignore[misc]


class CommonForecastEvaluationTest(unittest.TestCase):
    def test_metrics_use_natural_log_fixed_threshold_and_ten_calibration_bins(
        self,
    ) -> None:
        rows = (
            _row(1, outcome=False, candidate_probability=0.1,
                 b1_probability=0.2, b2_probability=0.3),
            _row(2, outcome=True, candidate_probability=0.9,
                 b1_probability=0.8, b2_probability=0.7),
            _row(3, outcome=True, candidate_probability=0.6,
                 b1_probability=0.4, b2_probability=0.6),
            _row(4, outcome=False, candidate_probability=0.6,
                 b1_probability=0.4, b2_probability=0.4),
        )

        result = _forecast(self, rows)

        self.assertIsInstance(result, evaluation.CommonForecastEvaluation)
        self.assertEqual(_key(), result.evaluation_key)
        self.assertEqual(4, result.row_count)
        self.assertEqual(1, result.effective_series_count)
        candidate = result.candidate
        self.assertEqual(evaluation.ForecastModel.CANDIDATE, candidate.model)
        self.assertAlmostEqual(0.135, candidate.brier_score, delta=1e-15)
        expected_log_loss = -(
            math.log(0.9)
            + math.log(0.9)
            + math.log(0.6)
            + math.log(0.4)
        ) / 4.0
        self.assertAlmostEqual(
            expected_log_loss, candidate.log_loss, delta=1e-15
        )
        self.assertEqual(0.50, candidate.threshold)
        self.assertEqual((2, 1, 1, 0), (
            candidate.true_positives,
            candidate.false_positives,
            candidate.true_negatives,
            candidate.false_negatives,
        ))
        self.assertEqual(3, candidate.alarm_count)
        self.assertEqual(0.5, candidate.prevalence)
        self.assertEqual(
            evaluation.RateEstimate(
                evaluation.MetricStatus.ESTIMATED, 2.0 / 3.0, 2, 3
            ),
            candidate.precision,
        )
        self.assertEqual(
            evaluation.RateEstimate(
                evaluation.MetricStatus.ESTIMATED, 1.0, 2, 2
            ),
            candidate.recall,
        )
        self.assertEqual(
            evaluation.RateEstimate(
                evaluation.MetricStatus.ESTIMATED, 0.5, 1, 2
            ),
            candidate.false_alarm_rate,
        )
        self.assertEqual(
            evaluation.RateEstimate(
                evaluation.MetricStatus.ESTIMATED, 0.0, 0, 2
            ),
            candidate.miss_rate,
        )
        self.assertEqual(10, len(candidate.calibration.bins))
        for index, calibration_bin in enumerate(candidate.calibration.bins):
            self.assertEqual(index, calibration_bin.index)
            self.assertAlmostEqual(index / 10.0, calibration_bin.lower_bound)
            self.assertAlmostEqual(
                (index + 1) / 10.0, calibration_bin.upper_bound
            )
            self.assertFalse(calibration_bin.upper_bound_inclusive)
        self.assertEqual(1, candidate.calibration.bins[1].count)
        self.assertEqual(2, candidate.calibration.bins[6].count)
        self.assertEqual(1, candidate.calibration.bins[9].count)
        self.assertEqual(0, candidate.calibration.bins[0].count)
        self.assertIsNone(candidate.calibration.bins[0].mean_probability)
        self.assertIsNone(candidate.calibration.bins[0].observed_frequency)
        self.assertAlmostEqual(
            0.10,
            candidate.calibration.expected_calibration_error,
            delta=1e-15,
        )
        self.assertAlmostEqual(
            0.10,
            candidate.calibration.maximum_calibration_error,
            delta=1e-15,
        )
        self.assertEqual(evaluation.USAGE_SCOPE, result.usage_scope)
        self.assertEqual(
            evaluation.OPERATIONAL_DISPOSITION,
            result.operational_disposition,
        )

    def test_zero_denominator_rates_are_explicit_and_never_zero_filled(
        self,
    ) -> None:
        rows = (
            _row(1, outcome=False, candidate_probability=0.2),
            _row(2, outcome=False, candidate_probability=0.3),
        )

        metrics = _forecast(self, rows).candidate

        unavailable = evaluation.MetricStatus.NOT_ESTIMABLE_ZERO_DENOMINATOR
        self.assertEqual(unavailable, metrics.precision.status)
        self.assertIsNone(metrics.precision.value)
        self.assertEqual((0, 0), (
            metrics.precision.numerator, metrics.precision.denominator
        ))
        self.assertEqual(unavailable, metrics.recall.status)
        self.assertIsNone(metrics.recall.value)
        self.assertEqual(unavailable, metrics.miss_rate.status)
        self.assertIsNone(metrics.miss_rate.value)
        self.assertEqual(evaluation.MetricStatus.ESTIMATED,
                         metrics.false_alarm_rate.status)
        self.assertEqual(0.0, metrics.false_alarm_rate.value)

    def test_probability_exactly_point_five_is_an_alarm(self) -> None:
        row = _row(1, outcome=True, candidate_probability=0.5,
                   b1_probability=0.5, b2_probability=0.5)

        result = _forecast(self, (row,))

        self.assertEqual(1, result.candidate.alarm_count)
        self.assertEqual(1, result.candidate.true_positives)

    def test_candidate_comparison_uses_best_baseline_and_selection_context(
        self,
    ) -> None:
        rows = tuple(
            _row(
                row_number,
                outcome=row_number % 2 == 0,
                candidate_probability=(
                    0.9 if row_number % 2 == 0 else 0.1
                ),
                b1_probability=0.8 if row_number % 2 == 0 else 0.2,
                b2_probability=0.7 if row_number % 2 == 0 else 0.3,
            )
            for row_number in range(1, 49)
        )

        prespecified = _forecast(
            self,
            rows,
            evaluation.CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION,
        ).comparison
        selected = _forecast(
            self,
            rows,
            evaluation.CandidateSelectionContext.SELECTED_FROM_MULTIPLE_CANDIDATES,
        ).comparison

        self.assertEqual(
            evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            prespecified.best_baseline_model,
        )
        self.assertAlmostEqual(
            0.03, prespecified.candidate_brier_improvement, delta=1e-15
        )
        self.assertAlmostEqual(
            math.log(0.9 / 0.8),
            prespecified.candidate_log_loss_improvement,
            delta=1e-15,
        )
        self.assertEqual(0.005, prespecified.primary_delta)
        self.assertEqual(
            evaluation.CandidateComparisonStatus.MEETS_DELTA_PRE_SPECIFIED,
            prespecified.status,
        )
        self.assertEqual(
            evaluation.CandidateComparisonStatus.MEETS_DELTA_SELECTION_ADJUSTMENT_REQUIRED,
            selected.status,
        )
        self.assertIs(
            evaluation.CandidateSelectionContext.SELECTED_FROM_MULTIPLE_CANDIDATES,
            selected.selection_context,
        )

        weaker_rows = tuple(
            replace(row, candidate_probability=row.b1_probability)
            for row in rows
        )
        weaker = _forecast(self, weaker_rows).comparison
        self.assertEqual(
            evaluation.CandidateComparisonStatus.DOES_NOT_MEET_DELTA_PRE_SPECIFIED,
            weaker.status,
        )

    def test_point_improvement_above_delta_is_insufficient_when_ci_crosses_delta(
        self,
    ) -> None:
        rows = tuple(
            _row(
                row_number,
                outcome=False,
                candidate_probability=0.3 if row_number <= 35 else 0.6,
                b1_probability=0.5,
                b2_probability=0.55,
            )
            for row_number in range(1, 61)
        )

        result = _forecast(self, rows, replicates=2000)

        self.assertGreater(
            result.comparison.candidate_brier_improvement,
            evaluation.PRIMARY_BRIER_DELTA,
        )
        interval = result.bootstrap.brier_improvement_interval
        self.assertIsNotNone(interval)
        self.assertLessEqual(
            cast(evaluation.PercentileInterval, interval).lower,
            evaluation.PRIMARY_BRIER_DELTA,
        )
        self.assertGreater(
            cast(evaluation.PercentileInterval, interval).upper,
            evaluation.PRIMARY_BRIER_DELTA,
        )
        self.assertEqual(
            "insufficient_evidence",
            result.comparison.status.value,
        )

    def test_temporal_metrics_are_not_inferred_from_binary_continuation_labels(
        self,
    ) -> None:
        temporal = _forecast(self, (_row(1),)).temporal_identification

        self.assertEqual(
            "not_identifiable_from_binary_continuation_label",
            evaluation.TEMPORAL_IDENTIFICATION_STATUS,
        )
        self.assertEqual(
            {evaluation.TEMPORAL_IDENTIFICATION_STATUS},
            {
                temporal.onset_error_status,
                temporal.lead_time_status,
                temporal.segment_iou_status,
                temporal.end_error_status,
            },
        )

    def test_mixed_keys_masks_boundaries_and_duplicate_identifiers_are_rejected(
        self,
    ) -> None:
        base = _row(1)
        invalid_cases: tuple[
            tuple[tuple[evaluation.CommonEvaluationRow, ...], str], ...
        ] = (
            ((), "empty_common_evaluation_rows"),
            ((replace(base, evaluation_key=_key(fold_id="fold-002")), base),
             "mixed_common_evaluation_key"),
            ((replace(base, candidate_probability=cast(float, None)),),
             "incomplete_common_row_mask"),
            ((replace(base, b1_probability=cast(float, None)),),
             "incomplete_common_row_mask"),
            ((replace(base, b2_probability=cast(float, None)),),
             "incomplete_common_row_mask"),
            ((replace(base, candidate_probability=0.0),),
             "boundary_probability_requires_explicit_abstention"),
            ((replace(base, candidate_probability=1.0),),
             "boundary_probability_requires_explicit_abstention"),
            ((replace(base, b1_probability=math.nan),),
             "probability_must_be_finite_open_interval"),
            ((replace(base, b2_probability=math.inf),),
             "probability_must_be_finite_open_interval"),
            ((replace(base, outcome=cast(bool, 1)),), "outcome_must_be_bool"),
            ((replace(base, row_id=" "),), "row_id_must_be_nonblank"),
            ((replace(base, series_id=" "),), "series_id_must_be_nonblank"),
            ((replace(base, session_id=" "),), "session_id_must_be_nonblank"),
            ((replace(base, time_index=cast(int, True)),),
             "time_index_must_be_nonnegative_integer"),
            ((replace(base, time_index=-1),),
             "time_index_must_be_nonnegative_integer"),
            ((replace(base, global_session_index=cast(int, True)),),
             "global_session_index_must_be_nonnegative_integer"),
            ((replace(base, global_session_index=-1),),
             "global_session_index_must_be_nonnegative_integer"),
            ((base, replace(base, session_id="other", time_index=2)),
             "duplicate_row_id"),
            ((base, replace(base, row_id="other", time_index=2)),
             "duplicate_series_session_id"),
            ((base, replace(base, row_id="other", session_id="other",
                            global_session_index=2)),
             "duplicate_series_time_index"),
        )
        for rows, error_code in invalid_cases:
            with self.subTest(error_code=error_code):
                _assert_contract_error(
                    self,
                    lambda rows=rows: evaluation.evaluate_common_forecasts(
                        rows,
                        evaluation.CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION,
                        replicates=8,
                    ),
                    error_code,
                )

        invalid_key_fields = (
            "outcome_id", "fold_id", "sample_role", "training_mapping_id"
        )
        for field_name in invalid_key_fields:
            with self.subTest(field_name=field_name):
                invalid_key = replace(_key(), **{field_name: " "})
                _assert_contract_error(
                    self,
                    lambda invalid_key=invalid_key: evaluation.evaluate_common_forecasts(
                        (replace(base, evaluation_key=invalid_key),),
                        evaluation.CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION,
                        replicates=8,
                    ),
                    "evaluation_key_fields_must_be_nonblank",
                )

        _assert_contract_error(
            self,
            lambda: evaluation.evaluate_common_forecasts(
                (base,),
                cast(evaluation.CandidateSelectionContext, "pre_specified"),
                replicates=8,
            ),
            "selection_context_must_be_typed",
        )

    def test_same_session_id_is_allowed_across_distinct_series(self) -> None:
        rows = (
            _row(1, series_id="SERIES-A", session_id="2026-01-02",
                 global_session_index=0),
            _row(2, series_id="SERIES-B", session_id="2026-01-02",
                 global_session_index=0),
        )

        result = _forecast(self, rows)

        self.assertEqual(2, result.row_count)
        self.assertEqual(2, result.effective_series_count)

    def test_global_session_mapping_is_bijective_and_series_order_is_monotonic(
        self,
    ) -> None:
        same_session_conflict = (
            _row(1, series_id="SERIES-A", session_id="session-shared",
                 time_index=0, global_session_index=10),
            _row(2, series_id="SERIES-B", session_id="session-shared",
                 time_index=0, global_session_index=11),
        )
        same_index_conflict = (
            _row(1, series_id="SERIES-A", session_id="session-a",
                 time_index=0, global_session_index=10),
            _row(2, series_id="SERIES-B", session_id="session-b",
                 time_index=0, global_session_index=10),
        )
        nonmonotonic_local_order = (
            _row(1, series_id="SERIES-A", session_id="session-a",
                 time_index=9, global_session_index=10),
            _row(2, series_id="SERIES-A", session_id="session-b",
                 time_index=8, global_session_index=11),
        )

        for rows, error_code in (
            (same_session_conflict,
             "session_global_index_mapping_must_be_bijective"),
            (same_index_conflict,
             "session_global_index_mapping_must_be_bijective"),
            (nonmonotonic_local_order,
             "series_time_index_must_increase_with_global_session_index"),
        ):
            with self.subTest(error_code=error_code):
                _assert_contract_error(
                    self,
                    lambda rows=rows: evaluation.evaluate_common_forecasts(
                        rows,
                        evaluation.CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION,
                        replicates=8,
                    ),
                    error_code,
                )


class MovingBlockBootstrapTest(unittest.TestCase):
    @staticmethod
    def _constant_improvement_rows() -> tuple[evaluation.CommonEvaluationRow, ...]:
        rows: list[evaluation.CommonEvaluationRow] = []
        row_number = 0
        for series_id in ("SERIES-B", "SERIES-A"):
            for time_index in range(48):
                row_number += 1
                outcome = time_index % 2 == 1
                rows.append(
                    _row(
                        row_number,
                        series_id=series_id,
                        session_id=f"session-{time_index:03d}",
                        time_index=time_index,
                        global_session_index=time_index,
                        outcome=outcome,
                        candidate_probability=0.9 if outcome else 0.1,
                        b1_probability=0.8 if outcome else 0.2,
                        b2_probability=0.7 if outcome else 0.3,
                    )
                )
        return tuple(rows)

    def test_bootstrap_is_deterministic_session_synchronized_and_finite(self) -> None:
        rows = self._constant_improvement_rows()

        first = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                rows,
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )
        reordered = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                tuple(reversed(rows)),
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )

        self.assertIsInstance(first, evaluation.PairedBootstrapResult)
        self.assertEqual(first, reordered)
        self.assertEqual(evaluation.BootstrapStatus.ESTIMATED, first.status)
        self.assertIsNone(first.reason)
        self.assertEqual(20260710, first.seed)
        self.assertEqual(20, first.block_length)
        self.assertEqual(2000, first.replicates)
        self.assertEqual(
            "synchronized_moving_blocks_of_ordered_common_session_clusters",
            first.method,
        )
        self.assertEqual(96, first.effective_row_count)
        self.assertEqual(48, first.effective_session_count)
        self.assertEqual(2, first.effective_series_count)
        self.assertEqual(2, first.nonoverlapping_block_capacity)
        self.assertEqual(
            "fixed_registered_universe_conditional_on_observed_symbols",
            first.inference_scope,
        )
        self.assertEqual(
            "not_estimated", first.symbol_superpopulation_uncertainty
        )
        self.assertFalse(
            hasattr(first, "effective_independent_block_count")
        )
        self.assertAlmostEqual(
            0.03, first.observed_brier_improvement, delta=1e-15
        )
        expected_log_improvement = math.log(0.9 / 0.8)
        self.assertAlmostEqual(
            expected_log_improvement,
            first.observed_log_loss_improvement,
            delta=1e-15,
        )
        self.assertAlmostEqual(
            0.03, first.brier_improvement_interval.lower, delta=1e-15
        )
        self.assertAlmostEqual(
            0.03, first.brier_improvement_interval.upper, delta=1e-15
        )
        self.assertAlmostEqual(
            expected_log_improvement,
            first.log_loss_improvement_interval.lower,
            delta=1e-15,
        )
        self.assertAlmostEqual(
            expected_log_improvement,
            first.log_loss_improvement_interval.upper,
            delta=1e-15,
        )
        for interval in (
            first.brier_improvement_interval,
            first.log_loss_improvement_interval,
        ):
            self.assertEqual(0.95, interval.confidence_level)
            self.assertTrue(math.isfinite(interval.lower))
            self.assertTrue(math.isfinite(interval.upper))
            self.assertLessEqual(interval.lower, interval.upper)

    def test_synchronized_session_blocks_do_not_shrink_ci_for_cloned_series(
        self,
    ) -> None:
        one_series = tuple(
            _row(
                row_number,
                series_id="SERIES-A",
                session_id=f"session-{row_number:03d}",
                time_index=row_number,
                outcome=False,
                candidate_probability=0.3 if row_number <= 35 else 0.6,
                b1_probability=0.5,
                b2_probability=0.55,
            )
            for row_number in range(1, 61)
        )
        cloned_rows = one_series + tuple(
            replace(
                row,
                row_id=f"clone-{row.row_id}",
                series_id="SERIES-B",
            )
            for row in one_series
        )

        original = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                one_series,
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )
        cloned = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                tuple(reversed(cloned_rows)),
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )

        self.assertEqual(
            original.brier_improvement_interval,
            cloned.brier_improvement_interval,
        )
        self.assertEqual(
            original.log_loss_improvement_interval,
            cloned.log_loss_improvement_interval,
        )
        self.assertEqual(60, cloned.effective_session_count)
        self.assertEqual(2, cloned.effective_series_count)

    def test_global_session_order_ignores_shifted_series_local_indices(
        self,
    ) -> None:
        def rows_with_b_offset(
            b_offset: int,
        ) -> tuple[evaluation.CommonEvaluationRow, ...]:
            rows: list[evaluation.CommonEvaluationRow] = []
            for local_index in range(30):
                b_global_index = local_index
                rows.append(
                    _row(
                        b_global_index + 1,
                        series_id="SERIES-B",
                        session_id=f"session-{b_global_index:03d}",
                        time_index=b_offset + local_index,
                        global_session_index=b_global_index,
                        outcome=False,
                        candidate_probability=0.1,
                        b1_probability=0.5,
                        b2_probability=0.55,
                    )
                )
                a_global_index = 30 + local_index
                rows.append(
                    _row(
                        a_global_index + 1,
                        series_id="SERIES-A",
                        session_id=f"session-{a_global_index:03d}",
                        time_index=local_index,
                        global_session_index=a_global_index,
                        outcome=False,
                        candidate_probability=0.7,
                        b1_probability=0.5,
                        b2_probability=0.55,
                    )
                )
            return tuple(rows)

        shifted = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                rows_with_b_offset(30),
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )
        reset = _call_or_fail(
            self,
            lambda: evaluation.moving_block_bootstrap(
                rows_with_b_offset(0),
                evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
            ),
        )

        self.assertEqual(shifted, reset)

    def test_insufficient_session_history_returns_no_degenerate_interval(
        self,
    ) -> None:
        for session_count in (20, 21):
            with self.subTest(session_count=session_count):
                rows = tuple(
                    _row(
                        row_number,
                        outcome=row_number % 2 == 0,
                        candidate_probability=(
                            0.9 if row_number % 2 == 0 else 0.1
                        ),
                        b1_probability=(
                            0.8 if row_number % 2 == 0 else 0.2
                        ),
                        b2_probability=(
                            0.7 if row_number % 2 == 0 else 0.3
                        ),
                    )
                    for row_number in range(1, session_count + 1)
                )

                result = _call_or_fail(
                    self,
                    lambda rows=rows: evaluation.moving_block_bootstrap(
                        rows,
                        evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
                    ),
                )

                self.assertEqual(
                    evaluation.BootstrapStatus.INSUFFICIENT_BOOTSTRAP_HISTORY,
                    result.status,
                )
                self.assertEqual(
                    "insufficient_bootstrap_history",
                    getattr(result, "reason", None),
                )
                self.assertIsNone(result.brier_improvement_interval)
                self.assertIsNone(result.log_loss_improvement_interval)
                self.assertEqual(
                    session_count,
                    getattr(result, "effective_session_count", None),
                )
                self.assertEqual(
                    1,
                    getattr(
                        result,
                        "nonoverlapping_block_capacity",
                        None,
                    ),
                )
                forecast = _forecast(self, rows)
                self.assertEqual(
                    evaluation.CandidateComparisonStatus.INSUFFICIENT_EVIDENCE,
                    forecast.comparison.status,
                )

    def test_bootstrap_configuration_and_baseline_are_validated(self) -> None:
        rows = self._constant_improvement_rows()
        cases = (
            ({"seed": True}, "bootstrap_seed_must_be_integer"),
            ({"block_length": 0}, "bootstrap_block_length_must_be_positive"),
            ({"replicates": 0}, "bootstrap_replicates_must_be_positive"),
        )
        for kwargs, error_code in cases:
            with self.subTest(error_code=error_code):
                _assert_contract_error(
                    self,
                    lambda kwargs=kwargs: evaluation.moving_block_bootstrap(
                        rows,
                        evaluation.ForecastModel.B1_JEFFREYS_CONSTANT,
                        **kwargs,
                    ),
                    error_code,
                )
        _assert_contract_error(
            self,
            lambda: evaluation.moving_block_bootstrap(
                rows, evaluation.ForecastModel.CANDIDATE
            ),
            "bootstrap_baseline_must_be_b1_or_b2",
        )


class EconomicEvaluationTest(unittest.TestCase):
    def test_cost_scenario_has_only_explicit_roundtrip_components(self) -> None:
        scenario = evaluation.CostScenario(
            fees_bps=5.0,
            fx_bps=10.0,
            slippage_bps=10.0,
            market_impact_bps=5.0,
            tax_bps=2.0,
            borrow_hedge_bps=3.0,
        )

        self.assertEqual(35.0, scenario.total_bps)
        invalid_values = (-0.1, math.nan, math.inf, cast(float, True))
        for field_name in (
            "fees_bps",
            "fx_bps",
            "slippage_bps",
            "market_impact_bps",
            "tax_bps",
            "borrow_hedge_bps",
        ):
            for invalid_value in invalid_values:
                with self.subTest(
                    field_name=field_name, invalid_value=invalid_value
                ):
                    values = {
                        "fees_bps": 0.0,
                        "fx_bps": 0.0,
                        "slippage_bps": 0.0,
                        "market_impact_bps": 0.0,
                        "tax_bps": 0.0,
                        "borrow_hedge_bps": 0.0,
                    }
                    values[field_name] = invalid_value
                    _assert_contract_error(
                        self,
                        lambda values=values: evaluation.CostScenario(**values),
                        "cost_components_must_be_finite_nonnegative_bps",
                    )
        _assert_contract_error(
            self,
            lambda: evaluation.CostScenario(
                fees_bps=1e308,
                fx_bps=1e308,
                slippage_bps=0.0,
                market_impact_bps=0.0,
                tax_bps=0.0,
                borrow_hedge_bps=0.0,
            ),
            "cost_total_must_be_finite_bps",
        )

    def test_roundtrip_cost_is_subtracted_without_hidden_components(self) -> None:
        scenario = evaluation.CostScenario(
            fees_bps=5.0,
            fx_bps=10.0,
            slippage_bps=10.0,
            market_impact_bps=5.0,
            tax_bps=0.0,
            borrow_hedge_bps=0.0,
        )

        result = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (_trade(0, 0.10),),
                scenario,
                minimum_tail_observations=2,
            ),
        )

        self.assertIsInstance(result, evaluation.EconomicPerformance)
        performance = cast(evaluation.EconomicPerformance, result)
        self.assertEqual((0.10,), performance.gross_simple_returns)
        self.assertEqual(1, len(performance.net_simple_returns))
        self.assertAlmostEqual(
            0.097, performance.net_simple_returns[0], delta=1e-15
        )
        self.assertAlmostEqual(
            0.097, performance.arithmetic_mean_net_return, delta=1e-15
        )
        self.assertEqual(
            evaluation.TailRiskStatus.INSUFFICIENT_TRADES,
            performance.tail_risk.status,
        )
        self.assertIsNone(performance.tail_risk.value_at_risk)
        self.assertIsNone(performance.tail_risk.conditional_value_at_risk)
        self.assertEqual(evaluation.USAGE_SCOPE, performance.usage_scope)
        self.assertEqual(
            evaluation.OPERATIONAL_DISPOSITION,
            performance.operational_disposition,
        )

    def test_equity_median_and_max_drawdown_use_sequential_simple_returns(
        self,
    ) -> None:
        trades = tuple(
            _trade(index, gross_return)
            for index, gross_return in enumerate((0.10, -0.05, 0.02, -0.20))
        )

        result = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                tuple(reversed(trades)),
                _zero_cost(),
                minimum_tail_observations=5,
            ),
        )

        self.assertIsInstance(result, evaluation.EconomicPerformance)
        performance = cast(evaluation.EconomicPerformance, result)
        self.assertEqual(4, performance.trade_count)
        self.assertAlmostEqual(
            -0.0325,
            performance.arithmetic_mean_net_return,
            delta=1e-15,
        )
        self.assertAlmostEqual(-0.015, performance.median_net_return,
                               delta=1e-15)
        expected_curve = (1.0, 1.1, 1.045, 1.0659, 0.85272)
        self.assertEqual(len(expected_curve), len(performance.equity_curve))
        for actual, expected in zip(performance.equity_curve, expected_curve):
            self.assertAlmostEqual(expected, actual, delta=1e-15)
        self.assertAlmostEqual(-0.14728, performance.cumulative_return,
                               delta=1e-15)
        self.assertAlmostEqual(0.2248, performance.max_drawdown,
                               delta=1e-15)
        self.assertEqual(evaluation.OVERLAP_POLICY, performance.overlap_policy)
        self.assertTrue(hasattr(performance, "equity_sequence_policy"))
        self.assertEqual(
            evaluation.EQUITY_SEQUENCE_POLICY,
            performance.equity_sequence_policy,
        )

    def test_historical_var_and_cvar_use_exact_worst_tail_mass(
        self,
    ) -> None:
        returns = (-0.10,) * 19 + (-0.20,)
        trades = tuple(
            _trade(index, gross_return)
            for index, gross_return in enumerate(returns)
        )

        result = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                trades, _zero_cost(), minimum_tail_observations=20
            ),
        )

        self.assertIsInstance(result, evaluation.EconomicPerformance)
        tail = cast(evaluation.EconomicPerformance, result).tail_risk
        self.assertEqual(evaluation.TailRiskStatus.ESTIMATED, tail.status)
        self.assertEqual(0.95, tail.confidence_level)
        self.assertAlmostEqual(0.10, cast(float, tail.value_at_risk),
                               delta=1e-15)
        self.assertAlmostEqual(0.20,
                               cast(float, tail.conditional_value_at_risk),
                               delta=1e-15)
        self.assertEqual(
            "loss=-net_simple_return (positive_is_loss); "
            "empirical_nearest_rank_var; "
            "cvar=exact_worst_5_percent_mass_with_partial_boundary_weight",
            tail.loss_convention,
        )

    def test_empty_and_short_without_direct_cost_data_are_explicitly_unavailable(
        self,
    ) -> None:
        empty = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades((), _zero_cost()),
        )
        short = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (_trade(0, 0.05,
                        direction=evaluation.TradeDirection.DOWNSIDE_SHORT),),
                _zero_cost(),
                short_execution_evidence=(
                    evaluation.ShortExecutionEvidence.NOT_AVAILABLE
                ),
            ),
        )

        self.assertEqual(
            evaluation.EconomicEvaluationUnavailable(
                status=evaluation.EconomicEvaluationStatus.INSUFFICIENT_TRADES,
                trade_count=0,
                reason="no_hypothetical_trades",
                overlap_policy=evaluation.OVERLAP_POLICY,
                usage_scope=evaluation.USAGE_SCOPE,
                operational_disposition=evaluation.OPERATIONAL_DISPOSITION,
            ),
            empty,
        )
        self.assertIsInstance(short, evaluation.EconomicEvaluationUnavailable)
        unavailable = cast(evaluation.EconomicEvaluationUnavailable, short)
        self.assertEqual(
            evaluation.EconomicEvaluationStatus.NOT_IDENTIFIABLE_WITHOUT_BORROW_AND_EXECUTION_DATA,
            unavailable.status,
        )
        self.assertEqual(1, unavailable.trade_count)
        self.assertEqual(
            "not_identifiable_without_borrow_and_execution_data",
            unavailable.reason,
        )
        self.assertEqual(evaluation.OPERATIONAL_DISPOSITION,
                         unavailable.operational_disposition)

    def test_available_short_evidence_uses_explicit_borrow_cost(self) -> None:
        scenario = evaluation.CostScenario(
            fees_bps=5.0,
            fx_bps=0.0,
            slippage_bps=5.0,
            market_impact_bps=5.0,
            tax_bps=0.0,
            borrow_hedge_bps=15.0,
        )

        result = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (_trade(0, 0.05,
                        direction=evaluation.TradeDirection.DOWNSIDE_SHORT),),
                scenario,
                short_execution_evidence=(
                    evaluation.ShortExecutionEvidence.AVAILABLE
                ),
                minimum_tail_observations=2,
            ),
        )

        self.assertIsInstance(result, evaluation.EconomicPerformance)
        self.assertAlmostEqual(
            0.047,
            cast(evaluation.EconomicPerformance, result).net_simple_returns[0],
            delta=1e-15,
        )

    def test_closed_interval_overlap_within_series_is_rejected_not_dropped(
        self,
    ) -> None:
        first = _trade(0, 0.02, entry_index=0, exit_index=5)
        overlaps_at_exit = _trade(1, 0.03, entry_index=5, exit_index=6)
        same_interval_other_series = _trade(
            2, 0.04, series_id="SERIES-B", entry_index=0, exit_index=5
        )

        _assert_contract_error(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (first, overlaps_at_exit), _zero_cost()
            ),
            "overlapping_trades_within_series",
        )
        allowed = _call_or_fail(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (first, same_interval_other_series),
                _zero_cost(),
                minimum_tail_observations=3,
            ),
        )
        self.assertIsInstance(
            allowed, evaluation.EconomicEvaluationUnavailable
        )
        unavailable = cast(evaluation.EconomicEvaluationUnavailable, allowed)
        self.assertEqual(
            "not_identifiable_without_portfolio_weights_and_common_calendar",
            unavailable.status.value,
        )
        self.assertEqual(
            "not_identifiable_without_portfolio_weights_and_common_calendar",
            unavailable.reason,
        )

        for trade in (first, same_interval_other_series):
            with self.subTest(series_id=trade.series_id):
                per_series = _call_or_fail(
                    self,
                    lambda trade=trade: evaluation.evaluate_hypothetical_trades(
                        (trade,),
                        _zero_cost(),
                        minimum_tail_observations=3,
                    ),
                )
                self.assertIsInstance(
                    per_series, evaluation.EconomicPerformance
                )

    def test_trade_and_economic_configuration_invalid_values_are_rejected(
        self,
    ) -> None:
        valid = _trade(0, 0.01)
        invalid_trades = (
            (replace(valid, series_id=" "), "trade_ids_must_be_nonblank"),
            (replace(valid, entry_session_id=" "), "trade_ids_must_be_nonblank"),
            (replace(valid, exit_session_id=" "), "trade_ids_must_be_nonblank"),
            (replace(valid, entry_index=cast(int, True)),
             "trade_indices_must_be_nonnegative_increasing_integers"),
            (replace(valid, entry_index=-1),
             "trade_indices_must_be_nonnegative_increasing_integers"),
            (replace(valid, exit_index=valid.entry_index),
             "trade_indices_must_be_nonnegative_increasing_integers"),
            (replace(valid, gross_simple_return=math.nan),
             "gross_simple_return_must_be_finite_and_not_below_minus_one"),
            (replace(valid, gross_simple_return=math.inf),
             "gross_simple_return_must_be_finite_and_not_below_minus_one"),
            (replace(valid, gross_simple_return=-1.01),
             "gross_simple_return_must_be_finite_and_not_below_minus_one"),
            (replace(valid, gross_simple_return=cast(float, True)),
             "gross_simple_return_must_be_finite_and_not_below_minus_one"),
            (replace(valid, direction=cast(evaluation.TradeDirection, "long")),
             "trade_direction_must_be_typed"),
        )
        for invalid_trade, error_code in invalid_trades:
            with self.subTest(error_code=error_code):
                _assert_contract_error(
                    self,
                    lambda invalid_trade=invalid_trade: (
                        evaluation.evaluate_hypothetical_trades(
                            (invalid_trade,), _zero_cost()
                        )
                    ),
                    error_code,
                )

        _assert_contract_error(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (valid,),
                _zero_cost(),
                short_execution_evidence=cast(
                    evaluation.ShortExecutionEvidence, "available"
                ),
            ),
            "short_execution_evidence_must_be_typed",
        )
        for minimum in (0, cast(int, True)):
            with self.subTest(minimum=minimum):
                _assert_contract_error(
                    self,
                    lambda minimum=minimum: evaluation.evaluate_hypothetical_trades(
                        (valid,),
                        _zero_cost(),
                        minimum_tail_observations=minimum,
                    ),
                    "minimum_tail_observations_must_be_positive_integer",
                )
        high_cost = evaluation.CostScenario(
            fees_bps=101.0,
            fx_bps=0.0,
            slippage_bps=0.0,
            market_impact_bps=0.0,
            tax_bps=0.0,
            borrow_hedge_bps=0.0,
        )
        _assert_contract_error(
            self,
            lambda: evaluation.evaluate_hypothetical_trades(
                (_trade(0, -1.0),), high_cost
            ),
            "net_return_below_minus_one_not_supported_by_equity_contract",
        )


class InterimEvaluationSecurityTest(unittest.TestCase):
    def test_module_contains_no_sensitive_values_or_external_trading_surfaces(
        self,
    ) -> None:
        module_path = Path(cast(str, evaluation.__file__))
        source = module_path.read_text(encoding="utf-8")

        self.assertEqual((), find_sensitive_values(source))
        lowered = source.lower()
        forbidden_surfaces = (
            "/api/v1/orders",
            "/api/v1/accounts",
            "/api/v1/assets",
            "place_order(",
            "submit_order(",
            "account_balance",
            "asset_balance",
        )
        self.assertEqual(
            [],
            [surface for surface in forbidden_surfaces if surface in lowered],
        )


if __name__ == "__main__":
    unittest.main()
