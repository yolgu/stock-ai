import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from validation import (  # noqa: E402
    BarrierDefinition,
    BarrierOutcomeEvaluator,
    CandidateDefinition,
    CandidateRegistry,
    CausalProbabilityCalibrator,
    CompositeScoreDefinition,
    DailyFeatureEngine,
    EventEpisodeCatalog,
    JeffreysPosterior,
    MovingBlockBootstrap,
    OutcomeDefinition,
    OutcomeLabelEngine,
    ReliefOutcomeLabelEngine,
    WalkForwardSplitter,
    XorShift32,
    benjamini_hochberg,
    beta_binomial_predictive,
    binary_metrics,
    circular_shift_placebo,
    holm_adjust,
    paired_brier_bootstrap,
    past_only_midrank_percentile,
    percentile_order_statistic,
    registered_random_seed,
)


def make_candles(count: int = 90) -> pd.DataFrame:
    index = pd.date_range("2025-01-02", periods=count, freq="B", tz="UTC")
    trend = np.linspace(100.0, 145.0, count)
    cycle = 1.5 * np.sin(np.arange(count) / 4.0)
    close = trend + cycle
    open_price = close - 0.25 * np.cos(np.arange(count) / 3.0)
    high = np.maximum(open_price, close) + 1.0
    low = np.minimum(open_price, close) - 1.0
    volume = 1_000_000.0 + 20_000.0 * (np.arange(count) % 11)
    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


class PastOnlyPercentileTest(unittest.TestCase):
    def test_uses_only_prior_observations_and_midranks_ties(self) -> None:
        values = pd.Series([1.0, 2.0, 2.0, 4.0, 3.0])

        result = past_only_midrank_percentile(
            values,
            minimum_sessions=3,
            maximum_sessions=4,
        )

        self.assertTrue(result.iloc[:3].isna().all())
        self.assertEqual(result.iloc[3], 1.0)
        self.assertEqual(result.iloc[4], 0.75)


class DailyFeatureEngineTest(unittest.TestCase):
    def test_future_price_mutation_does_not_change_features_at_signal_time(self) -> None:
        candles = make_candles()
        signal_position = 69
        engine = DailyFeatureEngine(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
        )

        original = engine.compute(candles)
        mutated_candles = candles.copy()
        mutated_candles.iloc[signal_position + 1 :, 0:4] *= 10.0
        mutated_candles.iloc[signal_position + 1 :, 4] *= 100.0
        mutated = engine.compute(mutated_candles)

        pd.testing.assert_series_equal(
            original.iloc[signal_position],
            mutated.iloc[signal_position],
            check_names=False,
        )

    def test_all_available_model_features_are_bounded_unit_scores(self) -> None:
        features = DailyFeatureEngine(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
        ).compute(make_candles(160))
        bounded_columns = DailyFeatureEngine.MODEL_FEATURE_NAMES

        for column in bounded_columns:
            available = features[column].dropna()
            self.assertGreater(len(available), 0, column)
            self.assertTrue(available.between(0.0, 1.0).all(), column)

    def test_rolling_features_remain_missing_until_every_required_input_exists(self) -> None:
        features = DailyFeatureEngine(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
        ).compute(make_candles(80))

        self.assertTrue(features["atr14"].iloc[:14].isna().all())
        self.assertTrue(np.isfinite(features["atr14"].iloc[14]))
        self.assertTrue(features["vwapPersistenceProxy"].iloc[:23].isna().all())
        self.assertTrue(np.isfinite(features["vwapPersistenceProxy"].iloc[23]))
        self.assertTrue(features["vwapDownPressure"].iloc[:23].isna().all())
        self.assertTrue(np.isfinite(features["vwapDownPressure"].iloc[23]))
        self.assertTrue(math.isnan(features["persistence"].iloc[0]))
        self.assertTrue(math.isnan(features["persistence"].iloc[1]))
        self.assertTrue(math.isnan(features["noNewLow"].iloc[0]))

    def test_zero_signal_volume_makes_every_volume_dependent_feature_unavailable(self) -> None:
        candles = make_candles(180)
        candles.loc[candles.index[-1], "volume"] = 0.0

        features = DailyFeatureEngine(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
        ).compute(candles)

        volume_dependent = [
            "volumeSurprise",
            "volume20",
            "vwap20",
            "vwapPersistenceProxy",
            "vwapDownPressure",
            "liquidityProxy",
            "profitBreadth",
            "profitGainMass",
            "vwapExtension",
        ]
        self.assertTrue(features.loc[candles.index[-1], volume_dependent].isna().all())
        self.assertTrue(math.isfinite(features["momentum5"].iloc[-1]))


class CompositeScoreDefinitionTest(unittest.TestCase):
    def test_composite_is_unavailable_when_any_component_is_missing(self) -> None:
        definition = CompositeScoreDefinition(
            identifier="example",
            weights={"a": 0.6, "b": 0.4},
        )
        features = pd.DataFrame(
            {
                "a": [0.5, 0.5],
                "b": [0.25, np.nan],
            }
        )

        score = definition.score(features)

        self.assertEqual(score.iloc[0], 40.0)
        self.assertTrue(math.isnan(score.iloc[1]))

    def test_composite_rejects_weights_that_do_not_sum_to_one(self) -> None:
        with self.assertRaisesRegex(ValueError, "sum to one"):
            CompositeScoreDefinition(
                identifier="invalid",
                weights={"a": 0.8, "b": 0.8},
            )

    def test_composite_uses_only_the_registered_absolute_weight_tolerance(self) -> None:
        with self.assertRaisesRegex(ValueError, "sum to one"):
            CompositeScoreDefinition(
                identifier="too-loose",
                weights={"a": 0.5, "b": 0.5000000005},
            )


class BarrierOutcomeEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = BarrierDefinition(
            target_direction="lower",
            target_atr_multiple=1.0,
            opposite_direction="upper",
            opposite_atr_multiple=0.5,
        )
        self.evaluator = BarrierOutcomeEvaluator()

    def test_success_is_the_first_target_barrier_passage(self) -> None:
        future = pd.DataFrame(
            {
                "high": [100.2, 101.0],
                "low": [98.8, 97.5],
            }
        )

        outcome = self.evaluator.evaluate(
            signal_close=100.0,
            signal_atr=1.0,
            future_candles=future,
            definition=self.definition,
            requested_horizon=2,
        )

        self.assertEqual(outcome.status, "success")
        self.assertEqual(outcome.first_passage_offset, 1)

    def test_opposite_first_is_failure_and_same_session_dual_hit_is_ambiguous(self) -> None:
        opposite_first = pd.DataFrame(
            {
                "high": [100.6, 100.2],
                "low": [99.5, 98.5],
            }
        )
        dual_hit = pd.DataFrame({"high": [100.6], "low": [98.9]})

        failure = self.evaluator.evaluate(
            100.0,
            1.0,
            opposite_first,
            self.definition,
            requested_horizon=2,
        )
        ambiguous = self.evaluator.evaluate(
            100.0,
            1.0,
            dual_hit,
            self.definition,
            requested_horizon=1,
        )

        self.assertEqual(failure.status, "failure")
        self.assertEqual(failure.first_passage_offset, 1)
        self.assertEqual(ambiguous.status, "ambiguous_excluded")

    def test_neither_hit_is_failure_but_short_tail_is_right_censored(self) -> None:
        neither = pd.DataFrame(
            {
                "high": [100.2, 100.3],
                "low": [99.4, 99.2],
            }
        )

        complete = self.evaluator.evaluate(
            100.0,
            1.0,
            neither,
            self.definition,
            requested_horizon=2,
        )
        censored = self.evaluator.evaluate(
            100.0,
            1.0,
            neither.iloc[:1],
            self.definition,
            requested_horizon=2,
        )
        short_tail_target_hit = self.evaluator.evaluate(
            100.0,
            1.0,
            pd.DataFrame({"high": [100.2], "low": [98.8]}),
            self.definition,
            requested_horizon=2,
        )

        self.assertEqual(complete.status, "failure")
        self.assertIsNone(complete.first_passage_offset)
        self.assertEqual(censored.status, "right_censored_excluded")
        self.assertEqual(short_tail_target_hit.status, "right_censored_excluded")


class EventEpisodeCatalogTest(unittest.TestCase):
    def test_suppresses_reentry_through_t_plus_h_inclusive(self) -> None:
        signals = pd.Series(
            [False, False, True, True, False, True, True, False, False, False, True]
        )

        starts = EventEpisodeCatalog().select_starts(signals, horizon=3)

        self.assertEqual(starts.tolist(), [2, 10])

    def test_continuously_high_signal_is_not_reentered_after_suppression(self) -> None:
        starts = EventEpisodeCatalog().select_starts(
            pd.Series([False, True, True, True, True, True, True]),
            horizon=2,
        )

        self.assertEqual(starts.tolist(), [1])


class WalkForwardSplitterTest(unittest.TestCase):
    def test_builds_three_actual_120_session_blocks_with_past_only_training(self) -> None:
        splitter = WalkForwardSplitter(
            block_sessions=120,
            purge_sessions=10,
            embargo_sessions=10,
        )

        folds = splitter.split(
            total_sessions=720,
            analysis_start=360,
            block_count=3,
        )

        self.assertEqual([fold.test_size for fold in folds], [120, 120, 120])
        self.assertEqual(
            [(fold.test_start, fold.test_end) for fold in folds],
            [(360, 480), (480, 600), (600, 720)],
        )
        for fold in folds:
            self.assertLessEqual(fold.train_end, fold.test_start - 10)
            self.assertEqual(fold.embargo_end, min(fold.test_end + 10, 720))

    def test_excludes_every_prior_test_embargo_from_later_training(self) -> None:
        splitter = WalkForwardSplitter(
            block_sessions=120,
            purge_sessions=10,
            embargo_sessions=10,
        )

        folds = splitter.split(
            total_sessions=720,
            analysis_start=360,
            block_count=3,
        )

        third_fold_training = set(folds[2].training_positions)
        self.assertIn(479, third_fold_training)
        self.assertNotIn(480, third_fold_training)
        self.assertNotIn(489, third_fold_training)
        self.assertIn(490, third_fold_training)
        self.assertEqual(folds[2].train_size, 580)


class JeffreysPosteriorTest(unittest.TestCase):
    def test_zero_event_posterior_is_finite_and_matches_arcsine_quantiles(self) -> None:
        posterior = JeffreysPosterior(successes=0, failures=0)

        summary = posterior.summary()

        expected_lower = math.sin(math.pi * 0.025 / 2.0) ** 2
        self.assertAlmostEqual(summary.median, 0.5, places=8)
        self.assertAlmostEqual(summary.lower, expected_lower, places=6)
        self.assertAlmostEqual(summary.upper, 1.0 - expected_lower, places=6)

    def test_posterior_mean_is_jeffreys_smoothed_success_rate(self) -> None:
        posterior = JeffreysPosterior(successes=8, failures=2)

        self.assertAlmostEqual(posterior.mean, 8.5 / 11.0)
        summary = posterior.summary()
        self.assertLess(summary.lower, summary.median)
        self.assertLess(summary.median, summary.upper)


class StatisticalUtilitiesTest(unittest.TestCase):
    def test_xorshift32_matches_the_frozen_preregistered_transition(self) -> None:
        generator = XorShift32(seed=1)

        self.assertEqual(
            [generator.next_uint32() for _ in range(6)],
            [270369, 67634689, 2647435461, 307599695, 2398689233, 745495504],
        )

    def test_registered_seed_uses_every_frozen_trial_ordinal(self) -> None:
        self.assertEqual(
            registered_random_seed(
                base_seed=20260710,
                candidate_ordinal=0,
                outcome_ordinal=0,
                horizon=5,
                block_length=10,
                fold_ordinal=0,
                purpose_ordinal=1,
            ),
            21342329,
        )

    def test_moving_block_bootstrap_consumes_xorshift_uniforms_in_order(self) -> None:
        samples = MovingBlockBootstrap(
            block_length=2,
            repetitions=2,
            seed=1,
        ).resample_indices(sample_size=5)

        np.testing.assert_array_equal(
            samples,
            np.asarray(
                [
                    [0, 1, 0, 1, 2],
                    [0, 1, 2, 3, 0],
                ],
                dtype=int,
            ),
        )

    def test_paired_bootstrap_resolves_a_frozen_seed_per_block_and_fold(self) -> None:
        resolved: list[tuple[int, int]] = []

        paired_brier_bootstrap(
            labels=np.asarray([0, 1, 0, 1, 0, 1], dtype=float),
            baseline_probabilities=np.full(6, 0.5),
            candidate_probabilities=np.asarray(
                [0.1, 0.9, 0.2, 0.8, 0.3, 0.7],
                dtype=float,
            ),
            fold_ids=np.asarray([0, 0, 0, 1, 1, 1], dtype=int),
            block_lengths=(2,),
            repetitions=3,
            seed_resolver=lambda block_length, fold_ordinal: (
                resolved.append((block_length, fold_ordinal)) or 1
            ),
        )

        self.assertEqual(resolved, [(2, 0), (2, 1)])

    def test_paired_bootstrap_preserves_absolute_one_based_fold_ordinals(self) -> None:
        resolved: list[tuple[int, int]] = []

        paired_brier_bootstrap(
            labels=np.asarray([0, 1, 0, 1], dtype=float),
            baseline_probabilities=np.full(4, 0.5),
            candidate_probabilities=np.asarray([0.1, 0.9, 0.2, 0.8]),
            fold_ids=np.asarray([2, 2, 3, 3], dtype=int),
            expected_fold_ids=(2, 3),
            block_lengths=(2,),
            repetitions=3,
            seed_resolver=lambda block_length, fold_ordinal: (
                resolved.append((block_length, fold_ordinal)) or 1
            ),
        )

        self.assertEqual(resolved, [(2, 1), (2, 2)])

    def test_paired_bootstrap_is_unavailable_when_an_expected_fold_has_no_pairs(self) -> None:
        resolved: list[tuple[int, int]] = []

        summary = paired_brier_bootstrap(
            labels=np.asarray([0, 1, 0, 1], dtype=float),
            baseline_probabilities=np.full(4, 0.5),
            candidate_probabilities=np.asarray([0.1, 0.9, 0.2, 0.8]),
            fold_ids=np.asarray([2, 2, 3, 3], dtype=int),
            expected_fold_ids=(1, 2, 3),
            block_lengths=(2,),
            repetitions=3,
            seed_resolver=lambda block_length, fold_ordinal: (
                resolved.append((block_length, fold_ordinal)) or 1
            ),
        )

        self.assertEqual(summary["status"], "bootstrap_unavailable")
        self.assertEqual(summary["emptyFoldIds"], [1])
        self.assertEqual(resolved, [])

    def test_circular_shift_placebo_uses_registered_within_fold_offsets(self) -> None:
        labels = np.asarray([0, 0, 1, 1, 0, 1], dtype=float)

        summary = circular_shift_placebo(
            labels=labels,
            baseline_probabilities=np.full(6, 0.5),
            candidate_probabilities=labels,
            fold_ids=np.zeros(6, dtype=int),
            horizon=1,
            repetitions=3,
            seed_resolver=lambda fold_ordinal: 1,
        )

        self.assertEqual(summary["status"], "available")
        self.assertAlmostEqual(summary["observedBrierDifference"], 0.25)
        self.assertAlmostEqual(summary["lower95"], -5.0 / 12.0)
        self.assertAlmostEqual(summary["median"], -5.0 / 12.0)
        self.assertAlmostEqual(summary["upper95"], -1.0 / 12.0)
        self.assertAlmostEqual(summary["observedRankFraction"], 1.0)
        self.assertAlmostEqual(summary["upperTailPValue"], 0.25)
        self.assertEqual(summary["allowedOffsetsByFold"], [[2, 4]])

    def test_circular_shift_placebo_is_unavailable_without_a_legal_offset(self) -> None:
        summary = circular_shift_placebo(
            labels=np.asarray([0, 1, 0], dtype=float),
            baseline_probabilities=np.full(3, 0.5),
            candidate_probabilities=np.asarray([0.2, 0.8, 0.2], dtype=float),
            fold_ids=np.zeros(3, dtype=int),
            horizon=1,
            repetitions=3,
            seed_resolver=lambda fold_ordinal: 1,
        )

        self.assertEqual(summary, {"status": "placebo_unavailable"})

    def test_circular_shift_placebo_is_unavailable_for_an_empty_expected_fold(self) -> None:
        summary = circular_shift_placebo(
            labels=np.asarray([0, 1, 0, 1], dtype=float),
            baseline_probabilities=np.full(4, 0.5),
            candidate_probabilities=np.asarray([0.2, 0.8, 0.2, 0.8]),
            fold_ids=np.asarray([2, 2, 3, 3], dtype=int),
            expected_fold_ids=(1, 2, 3),
            horizon=1,
            repetitions=3,
            seed_resolver=lambda fold_ordinal: 1,
        )

        self.assertEqual(summary["status"], "placebo_unavailable")
        self.assertEqual(summary["reason"], "empty_expected_fold")
        self.assertEqual(summary["emptyFoldIds"], [1])

    def test_binary_metrics_reward_calibrated_discrimination(self) -> None:
        labels = np.array([0, 0, 1, 1], dtype=float)
        probabilities = np.array([0.1, 0.2, 0.8, 0.9], dtype=float)

        metrics = binary_metrics(labels, probabilities, threshold=0.5)

        self.assertAlmostEqual(metrics["brierScore"], 0.025)
        self.assertAlmostEqual(metrics["rocAuc"], 1.0)
        self.assertAlmostEqual(metrics["prAuc"], 1.0)

    def test_binary_metrics_uses_the_registered_raw_score_alerts_for_mcc(self) -> None:
        metrics = binary_metrics(
            labels=np.asarray([0, 0, 1, 1], dtype=float),
            probabilities=np.asarray([0.6, 0.7, 0.8, 0.9], dtype=float),
            predicted_classes=np.asarray([False, False, True, True], dtype=bool),
        )

        self.assertAlmostEqual(metrics["mcc"], 1.0)
        self.assertEqual(metrics["truePositive"], 2.0)
        self.assertEqual(metrics["trueNegative"], 2.0)
        self.assertAlmostEqual(metrics["mcc"], 1.0)

    def test_pr_auc_is_invariant_to_row_order_inside_probability_ties(self) -> None:
        first = binary_metrics([1.0, 0.0], [0.5, 0.5])
        second = binary_metrics([0.0, 1.0], [0.5, 0.5])

        self.assertAlmostEqual(first["prAuc"], 0.5)
        self.assertAlmostEqual(second["prAuc"], 0.5)

    def test_brier_score_respects_registered_market_cluster_weights(self) -> None:
        labels = np.array([0.0, 1.0])
        probabilities = np.array([0.7, 0.6])
        weights = np.array([0.9, 0.1])

        metrics = binary_metrics(
            labels,
            probabilities,
            sample_weights=weights,
        )

        self.assertAlmostEqual(metrics["brierScore"], 0.9 * 0.49 + 0.1 * 0.16)

    def test_benjamini_hochberg_adjustment_is_monotone_in_rank_order(self) -> None:
        adjusted = benjamini_hochberg([0.01, 0.04, 0.03, 0.2])

        self.assertEqual(len(adjusted), 4)
        self.assertAlmostEqual(adjusted[0], 0.04)
        self.assertAlmostEqual(adjusted[2], 0.05333333333333334)
        self.assertAlmostEqual(adjusted[1], 0.05333333333333334)
        self.assertAlmostEqual(adjusted[3], 0.2)

    def test_moving_block_bootstrap_is_seeded_and_preserves_sample_length(self) -> None:
        bootstrap = MovingBlockBootstrap(
            block_length=3,
            repetitions=5,
            seed=20260710,
        )
        values = np.arange(8, dtype=float)

        first = bootstrap.resample_indices(len(values))
        second = bootstrap.resample_indices(len(values))

        np.testing.assert_array_equal(first, second)
        self.assertEqual(first.shape, (5, 8))
        self.assertTrue(((first >= 0) & (first < len(values))).all())

    def test_moving_block_bootstrap_uses_the_full_short_fold_as_one_block(self) -> None:
        samples = MovingBlockBootstrap(
            block_length=20,
            repetitions=3,
            seed=20260710,
        ).resample_indices(3)

        np.testing.assert_array_equal(
            samples,
            np.array([[0, 1, 2], [0, 1, 2], [0, 1, 2]]),
        )

    def test_percentile_confidence_interval_uses_a_non_interpolated_order_statistic(self) -> None:
        values = np.array([4.0, 1.0, 3.0, 2.0])

        self.assertEqual(percentile_order_statistic(values, 0.25), 1.0)
        self.assertEqual(percentile_order_statistic(values, 0.975), 4.0)

    def test_beta_binomial_predictive_distribution_is_normalized(self) -> None:
        distribution = beta_binomial_predictive(
            successes=8,
            failures=2,
            future_events=5,
        )

        self.assertEqual(len(distribution), 6)
        self.assertAlmostEqual(sum(distribution), 1.0)
        expected_successes = 5.0 * 8.5 / 11.0
        actual_successes = sum(
            success_count * probability
            for success_count, probability in enumerate(distribution)
        )
        self.assertAlmostEqual(actual_successes, expected_successes)

    def test_paired_brier_bootstrap_reports_positive_improvement(self) -> None:
        labels = np.array([0.0, 1.0] * 30)
        baseline = np.full(len(labels), 0.5)
        candidate = np.where(labels == 1.0, 0.8, 0.2)

        summary = paired_brier_bootstrap(
            labels,
            baseline,
            candidate,
            fold_ids=np.array([0] * 20 + [1] * 40),
            block_lengths=(5, 10, 20),
            repetitions=200,
            seed=20260710,
        )

        self.assertGreater(summary["brierDifference"], 0.0)
        self.assertGreater(summary["conservativeLower"], 0.0)
        self.assertLess(summary["oneSidedPValue"], 0.05)
        self.assertEqual(summary["foldCount"], 2)

    def test_paired_brier_bootstrap_can_reverse_under_cluster_weights(self) -> None:
        labels = np.array([0.0, 1.0] * 30)
        baseline = np.array([0.5, 0.5] * 30)
        candidate = np.array([0.69, 0.9] * 30)
        weights = np.array([0.9, 0.1] * 30)

        unweighted = paired_brier_bootstrap(
            labels,
            baseline,
            candidate,
            block_lengths=(5,),
            repetitions=50,
            seed=20260710,
        )
        weighted = paired_brier_bootstrap(
            labels,
            baseline,
            candidate,
            sample_weights=weights,
            block_lengths=(5,),
            repetitions=50,
            seed=20260710,
        )

        self.assertGreater(unweighted["brierDifference"], 0.0)
        self.assertLess(weighted["brierDifference"], 0.0)

    def test_holm_adjustment_controls_the_smallest_hypothesis_first(self) -> None:
        adjusted = holm_adjust([0.01, 0.04, 0.03, 0.2])

        self.assertEqual(adjusted, [0.04, 0.09, 0.09, 0.2])


class CandidateRegistryTest(unittest.TestCase):
    def test_scores_composites_and_baselines_without_dynamic_reweighting(self) -> None:
        registry = CandidateRegistry(
            [
                CandidateDefinition(
                    identifier="family.composite",
                    family="family",
                    kind="composite",
                    formula=None,
                    weights={"a": 0.75, "b": 0.25},
                    primary_outcome="outcome",
                    outcome_ids=("outcome",),
                    applicable_horizons=(1,),
                ),
                CandidateDefinition(
                    identifier="family.baseline",
                    family="family",
                    kind="baseline",
                    formula="a",
                    weights=None,
                    primary_outcome="outcome",
                    outcome_ids=("outcome",),
                    applicable_horizons=(1,),
                ),
            ]
        )
        features = pd.DataFrame({"a": [0.8, 0.8], "b": [0.4, np.nan]})

        scores = registry.score_all(features)

        self.assertEqual(scores["family.composite"].iloc[0], 70.0)
        self.assertTrue(math.isnan(scores["family.composite"].iloc[1]))
        self.assertEqual(scores["family.baseline"].tolist(), [80.0, 80.0])


class OutcomeLabelEngineTest(unittest.TestCase):
    def test_builds_causal_first_passage_labels_and_preserves_exclusions(self) -> None:
        candles = pd.DataFrame(
            {
                "open": [100.0, 100.0, 99.0, 100.0],
                "high": [100.5, 100.2, 101.0, 100.2],
                "low": [99.5, 98.8, 97.5, 99.5],
                "close": [100.0, 99.0, 100.0, 100.0],
                "volume": [1000.0] * 4,
            }
        )
        atr = pd.Series([1.0] * 4)
        engine = OutcomeLabelEngine(
            {
                "panic": OutcomeDefinition(
                    identifier="panic",
                    barrier=BarrierDefinition("lower", 1.0, "upper", 0.5),
                    applicable_horizons=(2,),
                )
            }
        )

        labels = engine.label(candles, atr, outcome_id="panic", horizon=2)

        self.assertEqual(labels.iloc[0]["status"], "success")
        self.assertEqual(labels.iloc[0]["label"], 1.0)
        self.assertEqual(labels.iloc[1]["status"], "ambiguous_excluded")
        self.assertTrue(math.isnan(labels.iloc[1]["label"]))
        self.assertEqual(labels.iloc[2]["status"], "right_censored_excluded")
        self.assertEqual(labels.iloc[3]["status"], "right_censored_excluded")

    def test_missing_eligibility_is_unavailable_instead_of_truthy(self) -> None:
        candles = pd.DataFrame(
            {
                "open": [100.0, 100.0],
                "high": [101.0, 102.0],
                "low": [99.0, 98.0],
                "close": [100.0, 100.0],
                "volume": [1000.0, 1000.0],
            }
        )
        engine = OutcomeLabelEngine(
            {
                "panic": OutcomeDefinition(
                    identifier="panic",
                    barrier=BarrierDefinition("lower", 1.0, "upper", 0.5),
                    applicable_horizons=(1,),
                )
            }
        )

        labels = engine.label(
            candles,
            pd.Series([1.0, 1.0]),
            "panic",
            1,
            eligibility=pd.Series([np.nan, False]),
        )

        self.assertEqual(labels.iloc[0]["status"], "unavailable_excluded")
        self.assertEqual(labels.iloc[1]["status"], "ineligible_excluded")


class ReliefOutcomeLabelEngineTest(unittest.TestCase):
    def _market(self, fake_relief: bool) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        close = [100.0, 98.0, 96.0, 94.0, 93.0, 92.0, 94.0, 96.0, 97.0, 97.0, 97.0]
        low = [99.0, 97.0, 95.0, 93.0, 92.0, 90.0, 91.5, 89.0 if fake_relief else 91.0, 92.0, 93.0, 93.0]
        high = [101.0, 99.0, 97.0, 95.0, 94.0, 93.0, 94.0, 97.0, 98.0, 98.0, 98.0]
        market = pd.DataFrame(
            {
                "open": close,
                "high": high,
                "low": low,
                "close": close,
                "volume": [1000.0] * len(close),
            }
        )
        atr = pd.Series([2.0] * len(close))
        eligibility = pd.Series([False] * 5 + [True] + [False] * 5)
        return market, atr, eligibility

    def test_requires_two_post_rebound_sessions_for_confirmed_relief(self) -> None:
        market, atr, eligibility = self._market(fake_relief=False)

        labels = ReliefOutcomeLabelEngine().label(
            market,
            atr,
            outcome_id="reliefConfirmed",
            horizon=3,
            eligibility=eligibility,
        )

        self.assertEqual(labels.iloc[5]["status"], "success")
        self.assertEqual(labels.iloc[5]["label"], 1.0)
        self.assertEqual(labels.iloc[5]["firstPassageOffset"], 1)
        self.assertEqual(labels.iloc[5]["confirmationOffset"], 3)

    def test_fake_relief_breaks_the_fixed_episode_low_before_confirmation(self) -> None:
        market, atr, eligibility = self._market(fake_relief=True)

        labels = ReliefOutcomeLabelEngine().label(
            market,
            atr,
            outcome_id="fakeRelief",
            horizon=5,
            eligibility=eligibility,
        )

        self.assertEqual(labels.iloc[5]["status"], "success")
        self.assertEqual(labels.iloc[5]["label"], 1.0)
        self.assertEqual(labels.iloc[5]["firstPassageOffset"], 1)
        self.assertEqual(labels.iloc[5]["terminalOffset"], 2)

    def test_fake_relief_requires_the_full_registered_post_rebound_tail(self) -> None:
        market, atr, eligibility = self._market(fake_relief=True)
        market = market.iloc[:8].copy()
        atr = atr.iloc[:8].copy()
        eligibility = eligibility.iloc[:8].copy()

        labels = ReliefOutcomeLabelEngine().label(
            market,
            atr,
            outcome_id="fakeRelief",
            horizon=5,
            eligibility=eligibility,
        )

        self.assertEqual(labels.iloc[5]["status"], "right_censored_excluded")
        self.assertIsNone(labels.iloc[5]["label"])
        self.assertIsNone(labels.iloc[5]["firstPassageOffset"])
        self.assertIsNone(labels.iloc[5]["terminalOffset"])

    def test_fake_relief_is_not_defined_for_three_sessions(self) -> None:
        market, atr, eligibility = self._market(fake_relief=True)

        with self.assertRaisesRegex(ValueError, "not applicable"):
            ReliefOutcomeLabelEngine().label(
                market,
                atr,
                outcome_id="fakeRelief",
                horizon=3,
                eligibility=eligibility,
            )

    def test_confirmed_relief_requires_the_full_registered_horizon_tail(self) -> None:
        market, atr, eligibility = self._market(fake_relief=False)
        market = market.iloc[:8].copy()
        atr = atr.iloc[:8].copy()
        eligibility = eligibility.iloc[:8].copy()
        market.loc[7, "close"] = 91.0

        labels = ReliefOutcomeLabelEngine().label(
            market,
            atr,
            outcome_id="reliefConfirmed",
            horizon=3,
            eligibility=eligibility,
        )

        self.assertEqual(labels.iloc[5]["status"], "right_censored_excluded")
        self.assertIsNone(labels.iloc[5]["label"])


class CausalProbabilityCalibratorTest(unittest.TestCase):
    def test_fits_threshold_and_probabilities_on_training_only(self) -> None:
        training_scores = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
        training_labels = pd.Series([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=float)
        calibrator = CausalProbabilityCalibrator(
            bin_count=5,
            alert_quantile=0.8,
            minimum_valid_pairs=10,
        )

        fitted = calibrator.fit(training_scores, training_labels)
        probabilities = fitted.predict(pd.Series([15.0, 95.0, np.nan]))

        self.assertAlmostEqual(fitted.alert_threshold, 80.0)
        self.assertEqual(fitted.bin_edges, (20.0, 40.0, 60.0, 80.0))
        self.assertLess(probabilities.iloc[0], probabilities.iloc[1])
        self.assertTrue(math.isnan(probabilities.iloc[2]))
        self.assertTrue(probabilities.dropna().between(0.0, 1.0).all())

    def test_future_labels_cannot_change_an_already_fitted_model(self) -> None:
        scores = pd.Series([10, 20, 30, 40, 50, 60, 70, 80], dtype=float)
        labels = pd.Series([0, 0, 0, 1, 1, 1, 0, 1], dtype=float)
        calibrator = CausalProbabilityCalibrator(
            bin_count=3,
            minimum_valid_pairs=6,
        )
        fitted_before = calibrator.fit(scores.iloc[:6], labels.iloc[:6])

        before = fitted_before.predict(pd.Series([25.0, 55.0]))
        labels.iloc[6:] = 1.0 - labels.iloc[6:]
        fitted_after = calibrator.fit(scores.iloc[:6], labels.iloc[:6])
        after = fitted_after.predict(pd.Series([25.0, 55.0]))

        pd.testing.assert_series_equal(before, after)

    def test_rejects_fewer_than_thirty_valid_training_pairs_by_default(self) -> None:
        scores = pd.Series(np.arange(29), dtype=float)
        labels = pd.Series(np.arange(29) % 2, dtype=float)

        with self.assertRaisesRegex(ValueError, "30 valid training pairs"):
            CausalProbabilityCalibrator(bin_count=5).fit(scores, labels)

    def test_infinite_scores_do_not_count_as_valid_training_pairs(self) -> None:
        scores = pd.Series([float(index) for index in range(29)] + [np.inf])
        labels = pd.Series([float(index % 2) for index in range(30)])

        with self.assertRaisesRegex(ValueError, "30 valid training pairs"):
            CausalProbabilityCalibrator(bin_count=5).fit(scores, labels)


if __name__ == "__main__":
    unittest.main()
