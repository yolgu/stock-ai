from __future__ import annotations

import hashlib
import json
import math
import unittest
from dataclasses import fields, replace

import rp001.interim_candidates as interim_candidates

from rp001.interim_candidates import (
    BASELINE_FORMULAS,
    CANDIDATE_FORMULAS,
    CANDIDATE_HEADS,
    FORMULA_CONTRACT,
    Abstention,
    AbstentionReason,
    BaselineFormulaId,
    BinomialTrainingCount,
    BlockedValidationPlan,
    BrierEvaluationKey,
    BrierEvaluationRow,
    CandidateFormulaId,
    CandidateHeadId,
    CandidateRawScores,
    CensoringReason,
    CensoredFutureLabels,
    DailyPriceVolumeObservation,
    FeatureVector,
    FixedValidationPlan,
    FutureContinuationLabels,
    InterimCandidateContractError,
    LifecycleStatus,
    OperationalDisposition,
    OutcomeId,
    PointInTimeFeatureSet,
    PrimaryBrierGateEvaluation,
    Probability,
    ConstructStatus,
    UsageScope,
    build_fixed_validation_plan,
    build_price_volume_features,
    candidate_probability,
    constant_baseline_probability,
    directional_shock_baseline_probability,
    evaluate_primary_brier_gate,
    jeffreys_probability,
    label_future_continuation,
    score_candidate_heads,
)


def _observation(
    *,
    adjusted_close: float | None = 100.0,
    native_close: float | None = 100.0,
    native_volume: float | None = 1_000_000.0,
    currency: str | None = "USD",
    series_id: str | None = "SERIES-A",
    session_id: str | None = "session",
    available_as_of_signal: bool = True,
) -> DailyPriceVolumeObservation:
    return DailyPriceVolumeObservation(
        adjusted_close=adjusted_close,
        native_close=native_close,
        native_volume=native_volume,
        currency=currency,
        series_id=series_id,
        session_id=session_id,
        available_as_of_signal=available_as_of_signal,
    )


def _nontrivial_observations(count: int = 30) -> list[DailyPriceVolumeObservation]:
    adjusted_close = 100.0
    observations: list[DailyPriceVolumeObservation] = []
    for index in range(count):
        if index > 0:
            daily_return = (
                (((index * 7) % 11) - 5) * 0.002
                + (0.0005 if index % 2 else -0.0003)
            )
            adjusted_close *= math.exp(daily_return)
        native_close = 60.0 * math.exp(
            0.0007 * index + 0.002 * ((index % 3) - 1)
        )
        native_volume = 900_000.0 * math.exp(
            0.006 * (((index * 3) % 7) - 3) + 0.0004 * index
        )
        observations.append(
            _observation(
                adjusted_close=adjusted_close,
                native_close=native_close,
                native_volume=native_volume,
                session_id=f"S{index:03d}",
            )
        )
    return observations


def _extreme_finite_observations() -> list[DailyPriceVolumeObservation]:
    observations: list[DailyPriceVolumeObservation] = []
    for index in range(22):
        is_large = index % 2 == 0
        observations.append(
            _observation(
                adjusted_close=1e300 if is_large else 1e-300,
                native_close=1e300 if is_large else 1e-300,
                native_volume=1e100 if is_large else 1e-100,
                session_id=f"E{index:03d}",
            )
        )
    return observations


def _scalar_median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _scalar_mad(values: list[float]) -> float:
    center = _scalar_median(values)
    deviations = [abs(value - center) for value in values]
    return _scalar_median(deviations)


def _reference_features(
    observations: list[DailyPriceVolumeObservation],
    as_of_index: int,
) -> dict[str, float]:
    returns: list[float] = []
    for index in range(as_of_index - 20, as_of_index + 1):
        current = observations[index].adjusted_close
        previous = observations[index - 1].adjusted_close
        assert current is not None
        assert previous is not None
        returns.append(math.log(current / previous))

    historical_returns = returns[:20]
    sigma = 1.4826 * _scalar_mad(historical_returns)
    turnover_logs: list[float] = []
    for index in range(as_of_index - 20, as_of_index + 1):
        native_close = observations[index].native_close
        native_volume = observations[index].native_volume
        assert native_close is not None
        assert native_volume is not None
        turnover_logs.append(math.log(native_close * native_volume))
    historical_turnover_logs = turnover_logs[:20]
    nu = 1.4826 * _scalar_mad(historical_turnover_logs)

    prior_adjusted_closes = [
        observations[index].adjusted_close
        for index in range(as_of_index - 20, as_of_index)
    ]
    assert all(value is not None for value in prior_adjusted_closes)
    prior_values = [float(value) for value in prior_adjusted_closes]
    prior_close = observations[as_of_index - 1].adjusted_close
    assert prior_close is not None
    return {
        "z1": returns[-1] / sigma,
        "m5": sum(returns[-5:]) / (math.sqrt(5.0) * sigma),
        "d20": math.log(max(prior_values) / prior_close)
        / (math.sqrt(20.0) * sigma),
        "u20": math.log(prior_close / min(prior_values))
        / (math.sqrt(20.0) * sigma),
        "zv": (
            turnover_logs[-1] - _scalar_median(historical_turnover_logs)
        )
        / nu,
        "return_scale": sigma,
        "turnover_scale": nu,
    }


def _reference_source_window_sha256(
    observations: list[DailyPriceVolumeObservation], as_of_index: int
) -> str:
    canonical_rows: list[dict[str, float | str | bool | None]] = []
    for offset, index in enumerate(
        range(as_of_index - 21, as_of_index + 1)
    ):
        observation = observations[index]
        canonical_row: dict[str, float | str | bool | None] = {
            "adjusted_close": observation.adjusted_close,
            "available_as_of_signal": observation.available_as_of_signal,
            "currency": observation.currency,
            "series_id": observation.series_id,
            "session_id": observation.session_id,
        }
        if offset > 0:
            canonical_row["native_close"] = observation.native_close
            canonical_row["native_volume"] = observation.native_volume
        canonical_rows.append(canonical_row)
    canonical_bytes = json.dumps(
        canonical_rows,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _point_in_time_features(
    vector: FeatureVector,
    *,
    return_scale: float = 0.1,
    turnover_scale: float = 0.2,
    as_of_index: int = 21,
) -> PointInTimeFeatureSet:
    return PointInTimeFeatureSet(
        vector=vector,
        return_scale=return_scale,
        turnover_scale=turnover_scale,
        as_of_index=as_of_index,
        series_id="SERIES-A",
        signal_session_id=f"S{as_of_index:03d}",
        source_window_sha256="0" * 64,
    )


def _reference_ramp(value: float, lower: float, upper: float) -> float:
    if value <= lower:
        return 0.0
    if value >= upper:
        return 1.0
    return (value - lower) / (upper - lower)


def _reference_scores(features: FeatureVector) -> dict[str, float]:
    return {
        "sf": (
            0.45 * _reference_ramp(features.m5, 0.5, 3.0)
            + 0.35 * _reference_ramp(features.zv, 0.0, 3.0)
            + 0.20 * _reference_ramp(features.z1, 0.25, 2.5)
        ),
        "sp": (
            0.45 * _reference_ramp(features.d20, 0.5, 3.0)
            + 0.35 * _reference_ramp(-features.z1, 0.25, 2.5)
            + 0.20 * _reference_ramp(features.zv, 0.0, 3.0)
        ),
        "st": (
            0.45 * _reference_ramp(features.u20, 0.5, 3.0)
            + 0.35 * _reference_ramp(-features.z1, 0.25, 2.5)
            + 0.20 * _reference_ramp(features.zv, 0.0, 3.0)
        ),
        "sr": (
            0.45 * _reference_ramp(features.d20, 0.5, 3.0)
            + 0.35 * _reference_ramp(features.z1, 0.25, 2.5)
            + 0.20 * _reference_ramp(features.zv, 0.0, 3.0)
        ),
    }


def _z1_boundary_observations(
    current_return_multiple: float,
) -> list[DailyPriceVolumeObservation]:
    historical_return_scale = 0.01
    sigma = 1.4826 * historical_return_scale
    returns = [
        -historical_return_scale if index % 2 else historical_return_scale
        for index in range(1, 21)
    ]
    returns.append(current_return_multiple * sigma)
    closes = [100.0]
    for daily_return in returns:
        closes.append(closes[-1] * math.exp(daily_return))

    observations: list[DailyPriceVolumeObservation] = []
    turnover_center = math.log(100_000_000.0)
    for index, adjusted_close in enumerate(closes):
        if 1 <= index <= 20:
            turnover_log = turnover_center + (-0.1 if index % 2 else 0.1)
        else:
            turnover_log = turnover_center
        native_close = 100.0
        native_volume = math.exp(turnover_log) / native_close
        observations.append(
            _observation(
                adjusted_close=adjusted_close,
                native_close=native_close,
                native_volume=native_volume,
                session_id=f"Z{index:03d}",
            )
        )
    return observations


def _z1_adjacent_boundary_observations() -> tuple[
    list[DailyPriceVolumeObservation],
    list[DailyPriceVolumeObservation],
    float,
    float,
]:
    observations = _z1_boundary_observations(8.0)
    current_close = observations[21].adjusted_close
    prior_close = observations[20].adjusted_close
    assert current_close is not None
    assert prior_close is not None
    historical_returns = []
    for index in range(1, 21):
        current = observations[index].adjusted_close
        previous = observations[index - 1].adjusted_close
        assert current is not None
        assert previous is not None
        historical_returns.append(math.log(current) - math.log(previous))
    return_scale = 1.4826 * _scalar_mad(historical_returns)

    for _ in range(10_000):
        current = list(observations)
        current[21] = replace(current[21], adjusted_close=current_close)
        current_z1 = (
            math.log(current_close) - math.log(prior_close)
        ) / return_scale
        next_close = math.nextafter(current_close, math.inf)
        next_rows = list(current)
        next_rows[21] = replace(next_rows[21], adjusted_close=next_close)
        next_z1 = (
            math.log(next_close) - math.log(prior_close)
        ) / return_scale
        if current_z1 <= 8.0 < next_z1:
            return current, next_rows, current_z1, next_z1
        current_close = (
            next_close
            if current_z1 <= 8.0
            else math.nextafter(current_close, -math.inf)
        )
    raise AssertionError("could not bracket the exact z1 boundary")


def _label_fixture(
    standardized_future_returns: list[float],
    extra_rows: int = 0,
) -> tuple[list[DailyPriceVolumeObservation], PointInTimeFeatureSet]:
    observations = _nontrivial_observations(22)
    feature_set = build_price_volume_features(observations, 21)
    assert isinstance(feature_set, PointInTimeFeatureSet)
    current_close = observations[feature_set.as_of_index].adjusted_close
    assert current_close is not None
    for offset, standardized_return in enumerate(
        standardized_future_returns, start=1
    ):
        observations.append(
            _observation(
                adjusted_close=current_close
                * math.exp(standardized_return * feature_set.return_scale),
                session_id=f"L{offset:03d}",
            )
        )
    for offset in range(extra_rows):
        observations.append(
            _observation(
                adjusted_close=current_close * (1.0 + 0.01 * offset),
                session_id=f"X{offset:03d}",
            )
        )
    return observations, feature_set


def _standardized_return(
    future_close: float, current_close: float, return_scale: float
) -> float:
    return (
        math.log(future_close) - math.log(current_close)
    ) / return_scale


def _adjacent_lower_bound_closes(
    current_close: float, return_scale: float, threshold: float
) -> tuple[float, float]:
    candidate = current_close * math.exp(threshold * return_scale)
    for _ in range(10_000):
        previous = math.nextafter(candidate, -math.inf)
        candidate_value = _standardized_return(
            candidate, current_close, return_scale
        )
        previous_value = _standardized_return(
            previous, current_close, return_scale
        )
        if previous_value < threshold <= candidate_value:
            return previous, candidate
        candidate = (
            math.nextafter(candidate, math.inf)
            if candidate_value < threshold
            else previous
        )
    raise AssertionError("could not bracket lower label threshold")


def _adjacent_upper_bound_closes(
    current_close: float, return_scale: float, threshold: float
) -> tuple[float, float]:
    candidate = current_close * math.exp(threshold * return_scale)
    for _ in range(10_000):
        following = math.nextafter(candidate, math.inf)
        candidate_value = _standardized_return(
            candidate, current_close, return_scale
        )
        following_value = _standardized_return(
            following, current_close, return_scale
        )
        if candidate_value <= threshold < following_value:
            return candidate, following
        candidate = (
            math.nextafter(candidate, -math.inf)
            if candidate_value > threshold
            else following
        )
    raise AssertionError("could not bracket upper label threshold")


class _TrackingObservations(list[DailyPriceVolumeObservation]):
    def __init__(self, values: list[DailyPriceVolumeObservation]) -> None:
        super().__init__(values)
        self.accessed_indices: list[int] = []

    def __getitem__(
        self, index: int | slice
    ) -> DailyPriceVolumeObservation | list[DailyPriceVolumeObservation]:
        if isinstance(index, int):
            self.accessed_indices.append(index)
        return super().__getitem__(index)


class InterimCandidatePortfolioTest(unittest.TestCase):
    def test_portfolio_freezes_exact_formula_outcome_and_head_mappings(self) -> None:
        self.assertEqual(
            tuple(metadata.formula_id for metadata in BASELINE_FORMULAS),
            (
                BaselineFormulaId.JEFFREYS_CONSTANT.value,
                BaselineFormulaId.DIRECTIONAL_SHOCK_BINS.value,
            ),
        )
        self.assertEqual(
            tuple(metadata.formula_id for metadata in CANDIDATE_FORMULAS),
            (
                CandidateFormulaId.UPSIDE_CONTINUATION.value,
                CandidateFormulaId.DOWNSIDE_CONTINUATION.value,
                CandidateFormulaId.EXTREME_REVERSAL.value,
            ),
        )
        self.assertEqual(
            tuple(outcome.value for outcome in OutcomeId),
            (
                "price_volume_upside_continuation_10d",
                "price_volume_downside_continuation_10d",
            ),
        )
        self.assertEqual(len(CANDIDATE_HEADS), 4)
        head_mapping = {
            head.head_id: (head.family_id, head.outcome_id)
            for head in CANDIDATE_HEADS
        }
        self.assertEqual(
            head_mapping,
            {
                CandidateHeadId.SF: (
                    CandidateFormulaId.UPSIDE_CONTINUATION,
                    OutcomeId.UPSIDE_CONTINUATION,
                ),
                CandidateHeadId.SP: (
                    CandidateFormulaId.DOWNSIDE_CONTINUATION,
                    OutcomeId.DOWNSIDE_CONTINUATION,
                ),
                CandidateHeadId.ST: (
                    CandidateFormulaId.EXTREME_REVERSAL,
                    OutcomeId.DOWNSIDE_CONTINUATION,
                ),
                CandidateHeadId.SR: (
                    CandidateFormulaId.EXTREME_REVERSAL,
                    OutcomeId.UPSIDE_CONTINUATION,
                ),
            },
        )

    def test_formula_metadata_is_explicit_research_proxy_notrade(self) -> None:
        metadata_records = BASELINE_FORMULAS + CANDIDATE_FORMULAS
        self.assertEqual(len(metadata_records), 5)
        for metadata in metadata_records:
            with self.subTest(formula_id=metadata.formula_id):
                self.assertIs(
                    metadata.lifecycle_status,
                    LifecycleStatus.EXPLORATORY_CANDIDATE,
                )
                self.assertIs(metadata.usage_scope, UsageScope.RESEARCH_ONLY)
                self.assertIs(
                    metadata.construct_status, ConstructStatus.PROXY_ONLY
                )
                self.assertIs(
                    metadata.operational_disposition,
                    OperationalDisposition.NO_TRADE_NO_INTEGRATION,
                )
                self.assertFalse(hasattr(metadata, "terminal_status"))
                self.assertEqual(
                    metadata.candidate_input_class, "optional_input_candidate"
                )
                self.assertTrue(metadata.definition_domain)
                self.assertEqual((metadata.range_min, metadata.range_max), (0.0, 1.0))
                self.assertEqual(metadata.units, "dimensionless")
                self.assertTrue(metadata.point_in_time_availability)
                self.assertTrue(metadata.missing_policy)
                self.assertTrue(metadata.out_of_domain_policy)
                self.assertTrue(metadata.abstention_policy)
                self.assertTrue(metadata.expected_failure_regimes)
                self.assertEqual(
                    metadata.adjustment_method,
                    "provider_adjusted_undocumented",
                )
                self.assertEqual(metadata.revision_policy, "not_documented")
                self.assertEqual(metadata.publication_timestamp, "not_documented")
                self.assertEqual(
                    set(metadata.collector_boundary_responsibilities),
                    {
                        "raw_hash",
                        "processed_hash",
                        "receivedAt",
                        "adjusted_request_mode",
                        "native_request_mode",
                        "timestamp_presence",
                        "currency_presence",
                        "session_id_presence",
                    },
                )

        forbidden_claim_terms = (
            "fomo",
            "panic",
            "profit-taking",
            "profit_taking",
            "profit taking",
            "recovery",
        )
        rendered_metadata = repr(metadata_records).lower()
        for term in forbidden_claim_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, rendered_metadata)

    def test_observation_contract_contains_only_documented_math_inputs(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(DailyPriceVolumeObservation)),
            (
                "adjusted_close",
                "native_close",
                "native_volume",
                "currency",
                "series_id",
                "session_id",
                "available_as_of_signal",
            ),
        )

    def test_candidate_scores_match_independent_scalar_reference(self) -> None:
        fixtures = (
            FeatureVector(z1=0.0, m5=0.0, d20=0.0, u20=0.0, zv=0.0),
            FeatureVector(z1=1.375, m5=1.75, d20=1.75, u20=1.75, zv=1.5),
            FeatureVector(z1=3.0, m5=4.0, d20=4.0, u20=4.0, zv=4.0),
            FeatureVector(z1=-3.0, m5=4.0, d20=4.0, u20=4.0, zv=4.0),
        )
        for features in fixtures:
            with self.subTest(features=features):
                actual = score_candidate_heads(
                    _point_in_time_features(features)
                )
                self.assertIsInstance(actual, CandidateRawScores)
                assert isinstance(actual, CandidateRawScores)
                expected = _reference_scores(features)
                for head in ("sf", "sp", "st", "sr"):
                    with self.subTest(head=head):
                        value = getattr(actual, head)
                        self.assertAlmostEqual(value, expected[head], delta=1e-12)
                        self.assertGreaterEqual(value, 0.0)
                        self.assertLessEqual(value, 1.0)
        with self.assertRaises(InterimCandidateContractError):
            score_candidate_heads(fixtures[0])

    def test_candidate_scoring_enforces_exact_scale_floor(self) -> None:
        feature_set = _point_in_time_features(
            FeatureVector(z1=0.0, m5=0.0, d20=0.0, u20=0.0, zv=0.0)
        )
        for scale_field in ("return_scale", "turnover_scale"):
            with self.subTest(scale_field=scale_field):
                below_floor = replace(feature_set, **{scale_field: 5e-7})
                result = score_candidate_heads(below_floor)
                self.assertIsInstance(result, Abstention)
                assert isinstance(result, Abstention)
                self.assertEqual(
                    result.reason, AbstentionReason.ZERO_VARIATION
                )

        exact_floor = replace(
            feature_set,
            return_scale=1e-6,
            turnover_scale=1e-6,
        )
        self.assertIsInstance(
            score_candidate_heads(exact_floor), CandidateRawScores
        )

    def test_jeffreys_mean_and_count_invariant(self) -> None:
        probability = jeffreys_probability(
            BinomialTrainingCount(successes=9, trials=39)
        )
        self.assertIsInstance(probability, Probability)
        assert isinstance(probability, Probability)
        self.assertEqual(probability.value, 0.2375)

        invalid_counts = ((-1, 1), (2, 1), (0, -1))
        for successes, trials in invalid_counts:
            with self.subTest(successes=successes, trials=trials):
                with self.assertRaises(InterimCandidateContractError):
                    BinomialTrainingCount(successes=successes, trials=trials)

    def test_constant_and_binned_calibrators_enforce_minimum_counts(self) -> None:
        self.assertIsInstance(
            constant_baseline_probability(
                BinomialTrainingCount(successes=50, trials=99)
            ),
            Abstention,
        )
        self.assertIsInstance(
            constant_baseline_probability(
                BinomialTrainingCount(successes=50, trials=100)
            ),
            Probability,
        )

        directional_counts = tuple(
            BinomialTrainingCount(successes=10, trials=20) for _ in range(5)
        )
        insufficient_directional = list(directional_counts)
        insufficient_directional[2] = BinomialTrainingCount(
            successes=9, trials=19
        )
        self.assertIsInstance(
            directional_shock_baseline_probability(
                OutcomeId.UPSIDE_CONTINUATION,
                z1=0.0,
                bin_counts=tuple(insufficient_directional),
            ),
            Abstention,
        )
        self.assertIsInstance(
            directional_shock_baseline_probability(
                OutcomeId.UPSIDE_CONTINUATION,
                z1=0.0,
                bin_counts=directional_counts,
            ),
            Probability,
        )

        candidate_counts = list(directional_counts)
        candidate_counts[2] = BinomialTrainingCount(successes=9, trials=19)
        self.assertIsInstance(
            candidate_probability(0.5, tuple(candidate_counts)),
            Abstention,
        )
        self.assertIsInstance(
            candidate_probability(0.5, directional_counts),
            Probability,
        )

    def test_directional_shock_bins_use_exact_boundaries_and_outcome_signs(self) -> None:
        counts = tuple(
            BinomialTrainingCount(successes=index, trials=20)
            for index in range(5)
        )
        cases = (
            (-8.0, 0),
            (-1.500000000001, 0),
            (-1.5, 1),
            (-0.5, 2),
            (0.5, 3),
            (1.5, 4),
            (8.0, 4),
        )
        for z1, expected_bin in cases:
            with self.subTest(z1=z1):
                result = directional_shock_baseline_probability(
                    OutcomeId.UPSIDE_CONTINUATION,
                    z1=z1,
                    bin_counts=counts,
                )
                self.assertIsInstance(result, Probability)
                assert isinstance(result, Probability)
                self.assertEqual(
                    result.value, (expected_bin + 0.5) / 21.0
                )

        downside_result = directional_shock_baseline_probability(
            OutcomeId.DOWNSIDE_CONTINUATION,
            z1=1.5,
            bin_counts=counts,
        )
        self.assertIsInstance(downside_result, Probability)
        assert isinstance(downside_result, Probability)
        self.assertEqual(downside_result.value, 1.5 / 21.0)
        for outside in (-8.0001, 8.0001):
            with self.subTest(outside=outside):
                self.assertIsInstance(
                    directional_shock_baseline_probability(
                        OutcomeId.UPSIDE_CONTINUATION,
                        z1=outside,
                        bin_counts=counts,
                    ),
                    Abstention,
                )

    def test_candidate_probability_bins_use_exact_boundaries(self) -> None:
        counts = tuple(
            BinomialTrainingCount(successes=index, trials=20)
            for index in range(5)
        )
        cases = (
            (0.0, 0),
            (0.199999999999, 0),
            (0.2, 1),
            (0.4, 2),
            (0.6, 3),
            (0.8, 4),
            (1.0, 4),
        )
        for raw_score, expected_bin in cases:
            with self.subTest(raw_score=raw_score):
                result = candidate_probability(raw_score, counts)
                self.assertIsInstance(result, Probability)
                assert isinstance(result, Probability)
                self.assertEqual(
                    result.value, (expected_bin + 0.5) / 21.0
                )
        for outside in (-0.0001, 1.0001):
            with self.subTest(outside=outside):
                self.assertIsInstance(
                    candidate_probability(outside, counts), Abstention
                )

    def test_feature_builder_ignores_every_row_after_signal_time(self) -> None:
        observations = _nontrivial_observations(35)
        as_of_index = 21
        original_features = build_price_volume_features(
            observations, as_of_index
        )
        self.assertIsInstance(original_features, PointInTimeFeatureSet)
        assert isinstance(original_features, PointInTimeFeatureSet)
        self.assertEqual(original_features.series_id, "SERIES-A")
        self.assertEqual(original_features.signal_session_id, "S021")
        self.assertEqual(
            original_features.source_window_sha256,
            _reference_source_window_sha256(observations, as_of_index),
        )

        mutated = list(observations)
        for index in range(as_of_index + 1, len(mutated)):
            mutated[index] = _observation(
                adjusted_close=None,
                native_close=-1.0,
                native_volume=float("nan"),
                currency="OTHER",
                series_id="SERIES-B",
                session_id=None,
                available_as_of_signal=False,
            )
        mutated_features = build_price_volume_features(mutated, as_of_index)
        self.assertEqual(mutated_features, original_features)
        self.assertEqual(
            score_candidate_heads(mutated_features),
            score_candidate_heads(original_features),
        )

    def test_feature_builder_explicitly_abstains_on_invalid_required_inputs(self) -> None:
        observations = _nontrivial_observations(22)
        cases = (
            (
                "missing adjusted close",
                0,
                {"adjusted_close": None},
                AbstentionReason.MISSING_REQUIRED_VALUE,
            ),
            (
                "missing native close",
                21,
                {"native_close": None},
                AbstentionReason.MISSING_REQUIRED_VALUE,
            ),
            (
                "missing native volume",
                21,
                {"native_volume": None},
                AbstentionReason.MISSING_REQUIRED_VALUE,
            ),
            (
                "missing currency",
                10,
                {"currency": None},
                AbstentionReason.MISSING_REQUIRED_METADATA,
            ),
            (
                "missing series",
                10,
                {"series_id": None},
                AbstentionReason.MISSING_REQUIRED_METADATA,
            ),
            (
                "missing session",
                10,
                {"session_id": None},
                AbstentionReason.MISSING_REQUIRED_METADATA,
            ),
            (
                "unavailable",
                10,
                {"available_as_of_signal": False},
                AbstentionReason.UNAVAILABLE_AS_OF_SIGNAL,
            ),
            (
                "zero adjusted close",
                10,
                {"adjusted_close": 0.0},
                AbstentionReason.NONPOSITIVE_REQUIRED_VALUE,
            ),
            (
                "negative native close",
                10,
                {"native_close": -1.0},
                AbstentionReason.NONPOSITIVE_REQUIRED_VALUE,
            ),
            (
                "zero native volume",
                10,
                {"native_volume": 0.0},
                AbstentionReason.NONPOSITIVE_REQUIRED_VALUE,
            ),
            (
                "nonfinite adjusted close",
                10,
                {"adjusted_close": float("inf")},
                AbstentionReason.NONFINITE_REQUIRED_VALUE,
            ),
            (
                "nonfinite native volume",
                10,
                {"native_volume": float("nan")},
                AbstentionReason.NONFINITE_REQUIRED_VALUE,
            ),
            (
                "currency change",
                10,
                {"currency": "KRW"},
                AbstentionReason.MULTIPLE_CURRENCIES,
            ),
            (
                "series change",
                10,
                {"series_id": "SERIES-B"},
                AbstentionReason.MULTIPLE_SERIES,
            ),
        )
        for name, index, changes, expected_reason in cases:
            with self.subTest(name=name):
                mutated = list(observations)
                mutated[index] = replace(mutated[index], **changes)
                result = build_price_volume_features(mutated, 21)
                self.assertIsInstance(result, Abstention)
                assert isinstance(result, Abstention)
                self.assertEqual(result.reason, expected_reason)

    def test_feature_builder_abstains_on_zero_mad_and_out_of_domain(self) -> None:
        observations = _nontrivial_observations(22)
        constant_return = [
            replace(
                observation,
                adjusted_close=100.0 * math.exp(0.01 * index),
            )
            for index, observation in enumerate(observations)
        ]
        sigma_result = build_price_volume_features(constant_return, 21)
        self.assertIsInstance(sigma_result, Abstention)
        assert isinstance(sigma_result, Abstention)
        self.assertEqual(sigma_result.reason, AbstentionReason.ZERO_VARIATION)

        constant_turnover = [
            replace(
                observation,
                native_close=100.0,
                native_volume=1_000_000.0,
            )
            for observation in observations
        ]
        nu_result = build_price_volume_features(constant_turnover, 21)
        self.assertIsInstance(nu_result, Abstention)
        assert isinstance(nu_result, Abstention)
        self.assertEqual(nu_result.reason, AbstentionReason.ZERO_VARIATION)

        inside_rows, outside_rows, inside_z1, outside_z1 = (
            _z1_adjacent_boundary_observations()
        )
        self.assertLessEqual(inside_z1, 8.0)
        self.assertGreater(outside_z1, 8.0)
        inside_close = inside_rows[21].adjusted_close
        outside_close = outside_rows[21].adjusted_close
        assert inside_close is not None
        assert outside_close is not None
        self.assertEqual(math.nextafter(inside_close, math.inf), outside_close)

        exact_boundary = build_price_volume_features(inside_rows, 21)
        self.assertIsInstance(exact_boundary, PointInTimeFeatureSet)
        assert isinstance(exact_boundary, PointInTimeFeatureSet)
        self.assertEqual(exact_boundary.vector.z1, inside_z1)

        outside = build_price_volume_features(outside_rows, 21)
        self.assertIsInstance(outside, Abstention)
        assert isinstance(outside, Abstention)
        self.assertEqual(outside.reason, AbstentionReason.OUT_OF_DOMAIN)

    def test_feature_and_score_invariance_to_units_and_split_representation(self) -> None:
        observations = _nontrivial_observations(22)
        original = build_price_volume_features(observations, 21)
        self.assertIsInstance(original, PointInTimeFeatureSet)
        assert isinstance(original, PointInTimeFeatureSet)

        scaled = [
            replace(
                observation,
                adjusted_close=(
                    None
                    if observation.adjusted_close is None
                    else observation.adjusted_close * 100.0
                ),
                native_close=(
                    None
                    if observation.native_close is None
                    else observation.native_close * 100.0
                ),
            )
            for observation in observations
        ]
        split_represented = [
            replace(
                observation,
                native_close=(
                    None
                    if observation.native_close is None
                    else observation.native_close / 2.0
                ),
                native_volume=(
                    None
                    if observation.native_volume is None
                    else observation.native_volume * 2.0
                ),
            )
            for observation in observations
        ]
        for transformed in (scaled, split_represented):
            with self.subTest(transformation=transformed is scaled):
                features = build_price_volume_features(transformed, 21)
                self.assertIsInstance(features, PointInTimeFeatureSet)
                assert isinstance(features, PointInTimeFeatureSet)
                for feature_name in ("z1", "m5", "d20", "u20", "zv"):
                    self.assertAlmostEqual(
                        getattr(features.vector, feature_name),
                        getattr(original.vector, feature_name),
                        delta=1e-12,
                    )
                self.assertAlmostEqual(
                    features.return_scale, original.return_scale, delta=1e-12
                )
                self.assertAlmostEqual(
                    features.turnover_scale,
                    original.turnover_scale,
                    delta=1e-12,
                )
                scores = score_candidate_heads(features)
                original_scores = score_candidate_heads(original)
                self.assertIsInstance(scores, CandidateRawScores)
                self.assertIsInstance(original_scores, CandidateRawScores)
                assert isinstance(scores, CandidateRawScores)
                assert isinstance(original_scores, CandidateRawScores)
                for head in ("sf", "sp", "st", "sr"):
                    self.assertAlmostEqual(
                        getattr(scores, head),
                        getattr(original_scores, head),
                        delta=1e-12,
                    )

    def test_feature_builder_matches_independent_scalar_reference(self) -> None:
        observations = _nontrivial_observations(22)
        actual = build_price_volume_features(observations, 21)
        self.assertIsInstance(actual, PointInTimeFeatureSet)
        assert isinstance(actual, PointInTimeFeatureSet)
        expected = _reference_features(observations, 21)
        for feature_name in ("z1", "m5", "d20", "u20", "zv"):
            with self.subTest(feature_name=feature_name):
                self.assertAlmostEqual(
                    getattr(actual.vector, feature_name),
                    expected[feature_name],
                    delta=1e-12,
                )
        self.assertAlmostEqual(
            actual.return_scale, expected["return_scale"], delta=1e-12
        )
        self.assertAlmostEqual(
            actual.turnover_scale,
            expected["turnover_scale"],
            delta=1e-12,
        )
        self.assertEqual(actual.as_of_index, 21)
        self.assertEqual(actual.series_id, "SERIES-A")
        self.assertEqual(actual.signal_session_id, "S021")
        self.assertEqual(
            actual.source_window_sha256,
            _reference_source_window_sha256(observations, 21),
        )

    def test_log_space_handles_finite_extreme_prices_and_turnover(self) -> None:
        observations = _extreme_finite_observations()
        feature_set = build_price_volume_features(observations, 21)
        self.assertIsInstance(feature_set, PointInTimeFeatureSet)
        assert isinstance(feature_set, PointInTimeFeatureSet)
        for value in (
            feature_set.vector.z1,
            feature_set.vector.m5,
            feature_set.vector.d20,
            feature_set.vector.u20,
            feature_set.vector.zv,
            feature_set.return_scale,
            feature_set.turnover_scale,
        ):
            self.assertTrue(math.isfinite(value))
        self.assertIsInstance(
            score_candidate_heads(feature_set), CandidateRawScores
        )

        for offset in range(1, 11):
            observations.append(
                _observation(
                    adjusted_close=1e300,
                    native_close=1e300,
                    native_volume=1e100,
                    session_id=f"EF{offset:03d}",
                )
            )
        labels = label_future_continuation(
            observations,
            feature_set.as_of_index,
            feature_set,
        )
        self.assertEqual(
            labels,
            FutureContinuationLabels(False, False),
        )

    def test_future_labels_match_exact_continuation_examples(self) -> None:
        upside_path = [2.1, 0.4, 0.3, 0.2, 0.1, 0.2, 0.3, 0.4, 0.8, 1.1]
        upside_observations, upside_features = _label_fixture(upside_path)
        upside = label_future_continuation(
            upside_observations,
            upside_features.as_of_index,
            upside_features,
        )
        self.assertIsInstance(upside, FutureContinuationLabels)
        assert isinstance(upside, FutureContinuationLabels)
        self.assertTrue(upside.upside_continuation)
        self.assertFalse(upside.downside_continuation)

        downside_path = [
            -2.1,
            -0.4,
            -0.3,
            -0.2,
            -0.1,
            -0.2,
            -0.3,
            -0.4,
            -0.8,
            -1.1,
        ]
        downside_observations, downside_features = _label_fixture(
            downside_path
        )
        downside = label_future_continuation(
            downside_observations,
            downside_features.as_of_index,
            downside_features,
        )
        self.assertIsInstance(downside, FutureContinuationLabels)
        assert isinstance(downside, FutureContinuationLabels)
        self.assertFalse(downside.upside_continuation)
        self.assertTrue(downside.downside_continuation)

        neutral_observations, neutral_features = _label_fixture([0.0] * 10)
        neither = label_future_continuation(
            neutral_observations,
            neutral_features.as_of_index,
            neutral_features,
        )
        self.assertEqual(
            neither,
            FutureContinuationLabels(
                upside_continuation=False,
                downside_continuation=False,
            ),
        )

        current_close = neutral_observations[
            neutral_features.as_of_index
        ].adjusted_close
        assert current_close is not None
        below_two, at_or_above_two = _adjacent_lower_bound_closes(
            current_close, neutral_features.return_scale, 2.0
        )
        below_one, at_or_above_one = _adjacent_lower_bound_closes(
            current_close, neutral_features.return_scale, 1.0
        )
        self.assertEqual(math.nextafter(below_two, math.inf), at_or_above_two)
        self.assertLess(
            _standardized_return(
                below_two, current_close, neutral_features.return_scale
            ),
            2.0,
        )
        self.assertGreaterEqual(
            _standardized_return(
                at_or_above_two,
                current_close,
                neutral_features.return_scale,
            ),
            2.0,
        )
        exact_upside_rows = list(neutral_observations)
        exact_upside_rows[neutral_features.as_of_index + 1] = replace(
            exact_upside_rows[neutral_features.as_of_index + 1],
            adjusted_close=at_or_above_two,
        )
        exact_upside_rows[neutral_features.as_of_index + 10] = replace(
            exact_upside_rows[neutral_features.as_of_index + 10],
            adjusted_close=at_or_above_one,
        )
        exact_upside = label_future_continuation(
            exact_upside_rows,
            neutral_features.as_of_index,
            neutral_features,
        )
        self.assertIsInstance(exact_upside, FutureContinuationLabels)
        assert isinstance(exact_upside, FutureContinuationLabels)
        self.assertTrue(exact_upside.upside_continuation)
        below_upside_rows = list(exact_upside_rows)
        below_upside_rows[neutral_features.as_of_index + 1] = replace(
            below_upside_rows[neutral_features.as_of_index + 1],
            adjusted_close=below_two,
        )
        below_upside = label_future_continuation(
            below_upside_rows,
            neutral_features.as_of_index,
            neutral_features,
        )
        self.assertIsInstance(below_upside, FutureContinuationLabels)
        assert isinstance(below_upside, FutureContinuationLabels)
        self.assertFalse(below_upside.upside_continuation)

        at_or_below_negative_two, above_negative_two = (
            _adjacent_upper_bound_closes(
                current_close, neutral_features.return_scale, -2.0
            )
        )
        at_or_below_negative_one, _above_negative_one = (
            _adjacent_upper_bound_closes(
                current_close, neutral_features.return_scale, -1.0
            )
        )
        self.assertEqual(
            math.nextafter(at_or_below_negative_two, math.inf),
            above_negative_two,
        )
        exact_downside_rows = list(neutral_observations)
        exact_downside_rows[neutral_features.as_of_index + 1] = replace(
            exact_downside_rows[neutral_features.as_of_index + 1],
            adjusted_close=at_or_below_negative_two,
        )
        exact_downside_rows[neutral_features.as_of_index + 10] = replace(
            exact_downside_rows[neutral_features.as_of_index + 10],
            adjusted_close=at_or_below_negative_one,
        )
        exact_downside = label_future_continuation(
            exact_downside_rows,
            neutral_features.as_of_index,
            neutral_features,
        )
        self.assertIsInstance(exact_downside, FutureContinuationLabels)
        assert isinstance(exact_downside, FutureContinuationLabels)
        self.assertTrue(exact_downside.downside_continuation)
        above_downside_rows = list(exact_downside_rows)
        above_downside_rows[neutral_features.as_of_index + 1] = replace(
            above_downside_rows[neutral_features.as_of_index + 1],
            adjusted_close=above_negative_two,
        )
        above_downside = label_future_continuation(
            above_downside_rows,
            neutral_features.as_of_index,
            neutral_features,
        )
        self.assertIsInstance(above_downside, FutureContinuationLabels)
        assert isinstance(above_downside, FutureContinuationLabels)
        self.assertFalse(above_downside.downside_continuation)

    def test_future_labels_are_censored_for_invalid_or_incomplete_future(self) -> None:
        valid, feature_set = _label_fixture([0.0] * 10)
        for invalid_close in (None, 0.0, float("inf")):
            with self.subTest(invalid_close=invalid_close):
                mutated = list(valid)
                invalid_index = feature_set.as_of_index + 5
                mutated[invalid_index] = replace(
                    mutated[invalid_index], adjusted_close=invalid_close
                )
                self.assertIsInstance(
                    label_future_continuation(
                        mutated,
                        feature_set.as_of_index,
                        feature_set,
                    ),
                    CensoredFutureLabels,
                )

        longer_series = _nontrivial_observations(35)
        for as_of_index in range(25, 35):
            with self.subTest(as_of_index=as_of_index):
                row_features = build_price_volume_features(
                    longer_series, as_of_index
                )
                self.assertIsInstance(row_features, PointInTimeFeatureSet)
                assert isinstance(row_features, PointInTimeFeatureSet)
                self.assertIsInstance(
                    label_future_continuation(
                        longer_series, as_of_index, row_features
                    ),
                    CensoredFutureLabels,
                )

    def test_future_labels_never_access_beyond_t_plus_ten(self) -> None:
        values, feature_set = _label_fixture([0.0] * 10, extra_rows=5)
        observations = _TrackingObservations(values)
        result = label_future_continuation(
            observations,
            feature_set.as_of_index,
            feature_set,
        )
        self.assertIsInstance(result, FutureContinuationLabels)
        self.assertTrue(observations.accessed_indices)
        self.assertLessEqual(
            max(observations.accessed_indices),
            feature_set.as_of_index + 10,
        )

    def test_future_labels_require_matching_pit_feature_provenance(self) -> None:
        observations, feature_set = _label_fixture([0.0] * 10)
        result = label_future_continuation(
            observations,
            feature_set.as_of_index + 1,
            feature_set,
        )
        self.assertIsInstance(result, CensoredFutureLabels)
        assert isinstance(result, CensoredFutureLabels)
        self.assertEqual(
            result.reason, CensoringReason.FEATURE_AS_OF_MISMATCH
        )

        cross_series = [
            replace(observation, series_id="SERIES-B")
            for observation in observations
        ]
        series_result = label_future_continuation(
            cross_series,
            feature_set.as_of_index,
            feature_set,
        )
        self.assertIsInstance(series_result, CensoredFutureLabels)
        assert isinstance(series_result, CensoredFutureLabels)
        self.assertEqual(series_result.reason, CensoringReason.SERIES_MISMATCH)

        changed_session = list(observations)
        changed_session[feature_set.as_of_index] = replace(
            changed_session[feature_set.as_of_index],
            session_id="CHANGED-SESSION",
        )
        session_result = label_future_continuation(
            changed_session,
            feature_set.as_of_index,
            feature_set,
        )
        self.assertIsInstance(session_result, CensoredFutureLabels)
        assert isinstance(session_result, CensoredFutureLabels)
        self.assertEqual(
            session_result.reason,
            CensoringReason.SIGNAL_SESSION_MISMATCH,
        )

        changed_past = list(observations)
        changed_index = feature_set.as_of_index - 5
        changed_close = changed_past[changed_index].adjusted_close
        assert changed_close is not None
        changed_past[changed_index] = replace(
            changed_past[changed_index],
            adjusted_close=changed_close * 1.0001,
        )
        window_result = label_future_continuation(
            changed_past,
            feature_set.as_of_index,
            feature_set,
        )
        self.assertIsInstance(window_result, CensoredFutureLabels)
        assert isinstance(window_result, CensoredFutureLabels)
        self.assertEqual(
            window_result.reason,
            CensoringReason.SOURCE_WINDOW_MISMATCH,
        )

        tampered_feature_sets = (
            replace(
                feature_set,
                return_scale=feature_set.return_scale * 2.0,
            ),
            replace(
                feature_set,
                turnover_scale=feature_set.turnover_scale * 2.0,
            ),
            replace(
                feature_set,
                vector=replace(
                    feature_set.vector,
                    z1=feature_set.vector.z1 + 0.01,
                ),
            ),
        )
        for tampered_feature_set in tampered_feature_sets:
            with self.subTest(tampered_feature_set=tampered_feature_set):
                tampered_result = label_future_continuation(
                    observations,
                    feature_set.as_of_index,
                    tampered_feature_set,
                )
                self.assertIsInstance(
                    tampered_result, CensoredFutureLabels
                )
                assert isinstance(tampered_result, CensoredFutureLabels)
                self.assertEqual(
                    tampered_result.reason,
                    CensoringReason.SOURCE_WINDOW_MISMATCH,
                )
        with self.assertRaises(TypeError):
            label_future_continuation(
                observations,
                feature_set.as_of_index,
                sigma_t=0.1,
            )

    def test_n607_fixed_walk_forward_layout_is_exact(self) -> None:
        plan = build_fixed_validation_plan(607)
        self.assertIsInstance(plan, FixedValidationPlan)
        assert isinstance(plan, FixedValidationPlan)
        self.assertEqual(len(plan.folds), 3)
        expected = (
            ((0, 252), (252, 262), (262, 325), (325, 335)),
            ((0, 325), (325, 335), (335, 398), (398, 408)),
            ((0, 398), (398, 408), (408, 471), (471, 481)),
        )
        actual = tuple(
            (
                (fold.train.start, fold.train.stop),
                (fold.purge.start, fold.purge.stop),
                (fold.validation.start, fold.validation.stop),
                (fold.embargo.start, fold.embargo.stop),
            )
            for fold in plan.folds
        )
        self.assertEqual(actual, expected)
        self.assertEqual(
            (plan.terminal_purge.start, plan.terminal_purge.stop),
            (471, 481),
        )
        self.assertEqual(
            (plan.terminal_holdout.start, plan.terminal_holdout.stop),
            (481, 607),
        )
        self.assertEqual(plan.terminal_mapping_fit_count, 1)
        self.assertEqual(
            (
                plan.terminal_mapping_fit_source.start,
                plan.terminal_mapping_fit_source.stop,
            ),
            (0, 471),
        )
        for index, fold in enumerate(plan.folds):
            with self.subTest(fold=index + 1):
                self.assertEqual(fold.train.stop, fold.purge.start)
                self.assertEqual(fold.purge.stop, fold.validation.start)
                self.assertEqual(fold.validation.stop, fold.embargo.start)
                self.assertLessEqual(
                    fold.validation.stop, plan.terminal_purge.start
                )
                if index > 0:
                    self.assertEqual(
                        fold.train.stop,
                        plan.folds[index - 1].validation.stop,
                    )

    def test_validation_plan_blocks_below_three_oof_folds(self) -> None:
        for session_count in (0, 606):
            with self.subTest(session_count=session_count):
                plan = build_fixed_validation_plan(session_count)
                self.assertIsInstance(plan, BlockedValidationPlan)
                assert isinstance(plan, BlockedValidationPlan)
                self.assertLess(plan.available_oof_folds, 3)
                self.assertEqual(plan.minimum_oof_folds, 3)

    def test_terminal_fit_purge_keeps_labels_before_holdout(self) -> None:
        cases = (
            (607, 470, 480, 481),
            (608, 471, 481, 482),
            (679, 542, 552, 553),
            (680, 543, 553, 554),
        )
        for session_count, last_signal, label_end, holdout_start in cases:
            with self.subTest(session_count=session_count):
                plan = build_fixed_validation_plan(session_count)
                self.assertIsInstance(plan, FixedValidationPlan)
                assert isinstance(plan, FixedValidationPlan)
                self.assertEqual(
                    plan.terminal_mapping_fit_source.stop - 1,
                    last_signal,
                )
                self.assertEqual(last_signal + 10, label_end)
                self.assertEqual(plan.terminal_holdout.start, holdout_start)
                self.assertLess(label_end, holdout_start)
                for fold in plan.folds:
                    self.assertLessEqual(
                        fold.validation.stop,
                        plan.terminal_purge.start,
                    )

    def test_formula_contract_records_pending_merc_and_fixed_formula_contract(self) -> None:
        self.assertEqual(
            FORMULA_CONTRACT.schema_version,
            "rp001-interim-formula-contract.v1",
        )
        self.assertEqual(FORMULA_CONTRACT.goal_version, "1.2-COMPACT")
        self.assertEqual(FORMULA_CONTRACT.study_id, "ST-BEH-001")
        self.assertEqual(FORMULA_CONTRACT.predecessor_question_id, "RQ-003")
        self.assertEqual(FORMULA_CONTRACT.question_id, "RQ-003-PV10-v1")
        self.assertEqual(FORMULA_CONTRACT.predecessor_protocol_id, "SP-003")
        self.assertEqual(FORMULA_CONTRACT.protocol_id, "SP-003-PV10-v1")
        self.assertEqual(FORMULA_CONTRACT.protocol_version, "1.0.1")
        self.assertEqual(
            FORMULA_CONTRACT.protocol_status, "pending_sample_freeze"
        )
        self.assertEqual(
            FORMULA_CONTRACT.predecessor_change_policy,
            "no_replacement_or_modification",
        )
        self.assertNotEqual(
            FORMULA_CONTRACT.question_id,
            FORMULA_CONTRACT.predecessor_question_id,
        )
        self.assertNotEqual(
            FORMULA_CONTRACT.protocol_id,
            FORMULA_CONTRACT.predecessor_protocol_id,
        )
        self.assertEqual(FORMULA_CONTRACT.estimand_id, "onset_forecast")
        self.assertEqual(FORMULA_CONTRACT.primary_horizon_sessions, 10)
        self.assertEqual(FORMULA_CONTRACT.secondary_horizons, ())
        self.assertEqual(FORMULA_CONTRACT.deterministic_seed, 20260710)
        self.assertEqual(
            FORMULA_CONTRACT.primary_metric_id,
            "brier_improvement_over_best_baseline",
        )
        self.assertEqual(FORMULA_CONTRACT.brier_improvement_delta, 0.005)
        self.assertEqual(FORMULA_CONTRACT.alarm_probability_threshold, 0.50)
        self.assertEqual(FORMULA_CONTRACT.minimum_training_sessions, 252)
        self.assertEqual(FORMULA_CONTRACT.purge_sessions, 10)
        self.assertEqual(FORMULA_CONTRACT.validation_sessions, 63)
        self.assertEqual(FORMULA_CONTRACT.embargo_sessions, 10)
        self.assertEqual(FORMULA_CONTRACT.terminal_holdout_sessions, 126)
        self.assertEqual(FORMULA_CONTRACT.minimum_oof_folds, 3)
        self.assertEqual(
            FORMULA_CONTRACT.terminal_mapping_policy,
            "fit_once_on_pre_holdout_only",
        )
        self.assertTrue(FORMULA_CONTRACT.same_eligible_row_mask_required)
        self.assertEqual(
            FORMULA_CONTRACT.eligible_row_requirements,
            (
                "all_common_price_volume_features_present",
                "uncensored_outcome_label",
            ),
        )
        self.assertEqual(
            FORMULA_CONTRACT.missing_input_policy,
            "abstain_without_zero_fill_or_reweight",
        )
        self.assertEqual(
            FORMULA_CONTRACT.primary_brier_gate,
            "Brier(candidate) <= min(Brier(B1), Brier(B2)) - 0.005",
        )
        self.assertIs(
            FORMULA_CONTRACT.lifecycle_status,
            LifecycleStatus.EXPLORATORY_CANDIDATE,
        )
        self.assertIs(FORMULA_CONTRACT.usage_scope, UsageScope.RESEARCH_ONLY)
        self.assertIs(
            FORMULA_CONTRACT.construct_status, ConstructStatus.PROXY_ONLY
        )
        self.assertIs(
            FORMULA_CONTRACT.operational_disposition,
            OperationalDisposition.NO_TRADE_NO_INTEGRATION,
        )
        self.assertFalse(hasattr(FORMULA_CONTRACT, "terminal_status"))
        self.assertEqual(FORMULA_CONTRACT.merc_status, "pending_sample_freeze")
        self.assertEqual(
            FORMULA_CONTRACT.pending_merc_sections,
            (
                "sample_role",
                "universe",
                "period",
                "cost_contract",
                "trial_ledger",
                "raw_processed_manifest",
                "leakage_evidence",
                "failure_disclosure_rules",
            ),
        )

    def test_primary_brier_gate_uses_one_common_row_collection(self) -> None:
        evaluation_key = BrierEvaluationKey(
            outcome_id=OutcomeId.UPSIDE_CONTINUATION,
            fold_id="fold-1",
            sample_role="development_validation",
            training_mapping_id="mapping-1",
        )
        passing_rows = (
            BrierEvaluationRow(
                evaluation_key, "row-1", False, 0.1, 0.2, 0.3
            ),
            BrierEvaluationRow(
                evaluation_key, "row-2", True, 0.9, 0.8, 0.7
            ),
        )
        result = evaluate_primary_brier_gate(passing_rows)
        self.assertIsInstance(result, PrimaryBrierGateEvaluation)
        self.assertEqual(result.evaluation_key, evaluation_key)
        self.assertEqual(result.row_count, 2)
        self.assertAlmostEqual(result.candidate_brier, 0.01, delta=1e-15)
        self.assertAlmostEqual(
            result.jeffreys_constant_brier, 0.04, delta=1e-15
        )
        self.assertAlmostEqual(
            result.directional_shock_brier, 0.09, delta=1e-15
        )
        self.assertTrue(result.passed)

        weaker_only_rows = (
            BrierEvaluationRow(
                evaluation_key, "row-1", False, 0.25, 0.2, 0.3
            ),
            BrierEvaluationRow(
                evaluation_key, "row-2", True, 0.75, 0.8, 0.7
            ),
        )
        self.assertFalse(
            evaluate_primary_brier_gate(weaker_only_rows).passed
        )
        with self.assertRaises(InterimCandidateContractError):
            evaluate_primary_brier_gate(())
        try:
            evaluate_primary_brier_gate((object(),))
        except Exception as error:
            self.assertIsInstance(error, InterimCandidateContractError)
        else:
            self.fail("non-row Brier input must be rejected")
        with self.assertRaises(InterimCandidateContractError):
            evaluate_primary_brier_gate(
                (
                    BrierEvaluationRow(
                        evaluation_key, "duplicate", False, 0.1, 0.2, 0.3
                    ),
                    BrierEvaluationRow(
                        evaluation_key, "duplicate", True, 0.9, 0.8, 0.7
                    ),
                )
            )
        invalid_rows = (
            BrierEvaluationRow(
                evaluation_key, "blank-probability", False, -0.1, 0.2, 0.3
            ),
            BrierEvaluationRow(
                evaluation_key, "nan-probability", False, 0.1, math.nan, 0.3
            ),
            BrierEvaluationRow(
                evaluation_key, "high-probability", False, 0.1, 0.2, 1.1
            ),
            BrierEvaluationRow(
                evaluation_key, "integer-outcome", 1, 0.1, 0.2, 0.3
            ),
            BrierEvaluationRow(evaluation_key, "", False, 0.1, 0.2, 0.3),
        )
        for invalid_row in invalid_rows:
            with self.subTest(invalid_row=invalid_row):
                with self.assertRaises(InterimCandidateContractError):
                    evaluate_primary_brier_gate((invalid_row,))

        mixed_keys = (
            replace(evaluation_key, outcome_id=OutcomeId.DOWNSIDE_CONTINUATION),
            replace(evaluation_key, fold_id="fold-2"),
            replace(evaluation_key, sample_role="terminal_holdout"),
            replace(evaluation_key, training_mapping_id="mapping-2"),
        )
        for mixed_key in mixed_keys:
            with self.subTest(mixed_key=mixed_key):
                with self.assertRaises(InterimCandidateContractError):
                    evaluate_primary_brier_gate(
                        (
                            passing_rows[0],
                            replace(passing_rows[1], evaluation_key=mixed_key),
                        )
                    )

        for field_name in ("fold_id", "sample_role", "training_mapping_id"):
            with self.subTest(blank_key_field=field_name):
                with self.assertRaises(InterimCandidateContractError):
                    replace(evaluation_key, **{field_name: " "})

        self.assertFalse(
            hasattr(interim_candidates, "passes_primary_brier_gate")
        )
        with self.assertRaises(TypeError):
            evaluate_primary_brier_gate(
                candidate_brier=0.01,
                jeffreys_constant_brier=0.04,
                directional_shock_brier=0.09,
            )


if __name__ == "__main__":
    unittest.main()
