from __future__ import annotations

import math
import statistics
import unittest
from dataclasses import replace

from rp001_s2.direction_neutral_overheat import CompetitivePathLabel, LabelHorizon
from rp001_s2.overheat_oof import (
    CANDIDATE_MODEL_IDS,
    CLASS_ORDER,
    MODEL_IDS,
    CompetitivePathDevelopmentOOF,
    DevelopmentFold,
    ExcludedOOFRow,
    OOFHyperparameters,
    OOFMetrics,
    OOFProbabilityRow,
    SessionInterval,
    _row_mask_sha256,
    multiclass_brier_score,
)
from rp001_s2.overheat_uncertainty import (
    BLOCK_LENGTH_SESSIONS,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    FAMILYWISE_ALPHA,
    GLOBAL_FAMILYWISE_COMPARISON_COUNT,
    MINIMUM_EFFECT_DELTA,
    PRNG_METHOD,
    CandidateDecisionReasonCode,
    CompetitivePathOOFUncertainty,
    ExploratoryEvidenceStatus,
    InferenceUnit,
    OverheatCandidateUncertainty,
    OverheatUncertaintyComparison,
    PrimaryLoss,
    _draw_circular_session_indices,
    evaluate_competitive_path_oof_uncertainty,
)


_HORIZON = LabelHorizon.MINUTES_30


def _probabilities_for_brier_loss(
    loss: float,
    label: CompetitivePathLabel,
) -> tuple[float, ...]:
    error_mass = math.sqrt(loss / (1.0 + 1.0 / (len(CLASS_ORDER) - 1)))
    target_probability = 1.0 - error_mass
    other_probability = error_mass / (len(CLASS_ORDER) - 1)
    return tuple(
        target_probability if candidate is label else other_probability
        for candidate in CLASS_ORDER
    )


def _recompute_row_mask(
    oof: CompetitivePathDevelopmentOOF,
) -> CompetitivePathDevelopmentOOF:
    reference = {
        row.row_id: row
        for row in oof.predictions
        if row.model_id == MODEL_IDS[0]
    }
    identities = tuple(
        (reference[row_id].fold_id, row_id)
        for row_id in oof.common_validation_row_ids
    )
    return replace(
        oof,
        row_mask_sha256=_row_mask_sha256(
            oof.frozen_session_axis,
            oof.horizon,
            oof.folds,
            identities,
            oof.excluded_rows,
        ),
    )


def _development_oof(
    *,
    axis: tuple[str, ...] | None = None,
    row_sessions: tuple[str, ...] | None = None,
    losses_by_model: dict[str, tuple[float, ...]] | None = None,
    reverse_prediction_rows: bool = False,
) -> CompetitivePathDevelopmentOOF:
    frozen_axis = axis or tuple(f"session-{index:02d}" for index in range(6))
    sessions = row_sessions or frozen_axis
    default_losses = {
        MODEL_IDS[0]: tuple(0.30 for _session in sessions),
        MODEL_IDS[1]: tuple(0.40 for _session in sessions),
        CANDIDATE_MODEL_IDS[0]: tuple(0.10 for _session in sessions),
        CANDIDATE_MODEL_IDS[1]: tuple(0.10 for _session in sessions),
        CANDIDATE_MODEL_IDS[2]: tuple(0.10 for _session in sessions),
    }
    if losses_by_model is not None:
        default_losses.update(losses_by_model)
    if any(len(values) != len(sessions) for values in default_losses.values()):
        raise ValueError("test_loss_count_mismatch")

    labels = tuple(CLASS_ORDER[index % len(CLASS_ORDER)] for index in range(len(sessions)))
    row_ids = tuple(f"row-{index:03d}" for index in range(len(sessions)))
    predictions: list[OOFProbabilityRow] = []
    metrics: list[OOFMetrics] = []
    for model_id in MODEL_IDS:
        model_rows = tuple(
            OOFProbabilityRow(
                model_id=model_id,
                fold_id="development_01",
                row_id=row_id,
                symbol="AAPL" if index % 2 == 0 else "MSFT",
                session_id=session_id,
                label=labels[index],
                source_evidence_sha256=f"{index + 1:064x}",
                probabilities=_probabilities_for_brier_loss(
                    default_losses[model_id][index],
                    labels[index],
                ),
            )
            for index, (row_id, session_id) in enumerate(
                zip(row_ids, sessions, strict=True)
            )
        )
        predictions.extend(reversed(model_rows) if reverse_prediction_rows else model_rows)
        metrics.append(
            OOFMetrics(
                model_id=model_id,
                row_count=len(model_rows),
                multiclass_brier=multiclass_brier_score(
                    tuple(row.label for row in model_rows),
                    tuple(row.probabilities for row in model_rows),
                    CLASS_ORDER,
                ),
                log_loss=0.5,
                top_class_ece=0.1,
            )
        )

    return _recompute_row_mask(
        CompetitivePathDevelopmentOOF(
            horizon=_HORIZON,
            class_order=CLASS_ORDER,
            model_ids=MODEL_IDS,
            candidate_model_ids=CANDIDATE_MODEL_IDS,
            frozen_session_axis=frozen_axis,
            folds=(
                DevelopmentFold(
                    fold_id="development_01",
                    train=SessionInterval(0, 0),
                    purge=SessionInterval(0, 0),
                    validation=SessionInterval(0, len(frozen_axis)),
                    embargo=SessionInterval(len(frozen_axis), len(frozen_axis)),
                ),
            ),
            excluded_rows=(),
            common_validation_row_ids=row_ids,
            row_mask_sha256="a" * 64,
            input_dataset_sha256="b" * 64,
            predictions=tuple(predictions),
            metrics=tuple(metrics),
            hyperparameters=OOFHyperparameters(),
        )
    )


def _evaluate(
    oof: CompetitivePathDevelopmentOOF,
) -> CompetitivePathOOFUncertainty:
    return evaluate_competitive_path_oof_uncertainty(
        oof,
        global_familywise_comparison_count=GLOBAL_FAMILYWISE_COMPARISON_COUNT,
    )


def _comparison(
    result: CompetitivePathOOFUncertainty,
    candidate_model_id: str,
    baseline_model_id: str,
) -> OverheatUncertaintyComparison:
    return next(
        value
        for value in result.comparisons
        if value.candidate_model_id == candidate_model_id
        and value.baseline_model_id == baseline_model_id
    )


def _candidate(
    result: CompetitivePathOOFUncertainty,
    candidate_model_id: str,
) -> OverheatCandidateUncertainty:
    return next(
        value
        for value in result.candidates
        if value.candidate_model_id == candidate_model_id
    )


def _type7(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


class _ReferenceSplitMix64:
    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self._state = seed & self._MASK

    def next_uint64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & self._MASK
        value = self._state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & self._MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & self._MASK
        return (value ^ (value >> 31)) & self._MASK

    def randrange(self, stop: int) -> int:
        limit = (1 << 64) - ((1 << 64) % stop)
        while True:
            value = self.next_uint64()
            if value < limit:
                return value % stop


def _reference_circular_distribution(
    session_improvements: tuple[float, ...],
) -> tuple[float, ...]:
    generator = _ReferenceSplitMix64(BOOTSTRAP_SEED)
    distribution: list[float] = []
    for _replicate in range(BOOTSTRAP_REPLICATES):
        sampled: list[float] = []
        while len(sampled) < len(session_improvements):
            start = generator.randrange(len(session_improvements))
            sampled.extend(
                session_improvements[
                    (start + offset) % len(session_improvements)
                ]
                for offset in range(BLOCK_LENGTH_SESSIONS)
            )
        distribution.append(statistics.fmean(sampled[: len(session_improvements)]))
    return tuple(distribution)


def _reference_fold_segmented_distribution(
    session_improvements: tuple[float, ...],
    segment_lengths: tuple[int, ...],
) -> tuple[float, ...]:
    generator = _ReferenceSplitMix64(BOOTSTRAP_SEED)
    distribution: list[float] = []
    segment_starts: list[int] = []
    offset = 0
    for length in segment_lengths:
        segment_starts.append(offset)
        offset += length
    for _replicate in range(BOOTSTRAP_REPLICATES):
        sampled: list[float] = []
        for segment_start, segment_length in zip(
            segment_starts,
            segment_lengths,
            strict=True,
        ):
            segment = session_improvements[
                segment_start : segment_start + segment_length
            ]
            segment_sample: list[float] = []
            while len(segment_sample) < segment_length:
                start = generator.randrange(segment_length)
                segment_sample.extend(
                    segment[(start + index) % segment_length]
                    for index in range(BLOCK_LENGTH_SESSIONS)
                )
            sampled.extend(segment_sample[:segment_length])
        distribution.append(statistics.fmean(sampled))
    return tuple(distribution)


def _two_fold_oof(
    improvements: tuple[float, ...],
) -> CompetitivePathDevelopmentOOF:
    axis = tuple(f"session-{index}" for index in range(len(improvements)))
    oof = _development_oof(
        axis=axis,
        losses_by_model={
            MODEL_IDS[0]: tuple(0.50 for _session in axis),
            CANDIDATE_MODEL_IDS[0]: tuple(
                0.50 - improvement for improvement in improvements
            ),
        },
    )
    boundary = len(axis) // 2
    folds = (
        DevelopmentFold(
            fold_id="development_01",
            train=SessionInterval(0, 0),
            purge=SessionInterval(0, 0),
            validation=SessionInterval(0, boundary),
            embargo=SessionInterval(boundary, boundary),
        ),
        DevelopmentFold(
            fold_id="development_02",
            train=SessionInterval(0, boundary),
            purge=SessionInterval(boundary, boundary),
            validation=SessionInterval(boundary, len(axis)),
            embargo=SessionInterval(len(axis), len(axis)),
        ),
    )
    predictions = tuple(
        replace(
            row,
            fold_id=(
                "development_01"
                if int(row.row_id.removeprefix("row-")) < boundary
                else "development_02"
            ),
        )
        for row in oof.predictions
    )
    return _recompute_row_mask(
        replace(oof, folds=folds, predictions=predictions)
    )


def _replace_prediction_loss(
    oof: CompetitivePathDevelopmentOOF,
    *,
    model_id: str,
    row_id: str,
    loss: float,
) -> CompetitivePathDevelopmentOOF:
    predictions = tuple(
        replace(
            row,
            probabilities=_probabilities_for_brier_loss(loss, row.label),
        )
        if row.model_id == model_id and row.row_id == row_id
        else row
        for row in oof.predictions
    )
    model_rows = tuple(row for row in predictions if row.model_id == model_id)
    metrics = tuple(
        replace(
            metric,
            multiclass_brier=multiclass_brier_score(
                tuple(row.label for row in model_rows),
                tuple(row.probabilities for row in model_rows),
                CLASS_ORDER,
            ),
        )
        if metric.model_id == model_id
        else metric
        for metric in oof.metrics
    )
    return replace(oof, predictions=predictions, metrics=metrics)


class _StartSequence:
    def __init__(self, starts: tuple[int, ...]) -> None:
        self._starts = list(starts)

    def randrange(self, stop: int) -> int:
        value = self._starts.pop(0)
        if not 0 <= value < stop:
            raise AssertionError("test_start_outside_range")
        return value


class CompetitivePathOOFUncertaintyTest(unittest.TestCase):
    def test_exact_paired_multiclass_brier_matches_hand_calculation(self) -> None:
        oof = _development_oof(axis=tuple(f"session-{index}" for index in range(5)))

        result = _evaluate(oof)

        comparison = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[0])
        baseline = _probabilities_for_brier_loss(0.30, CLASS_ORDER[0])
        candidate = _probabilities_for_brier_loss(0.10, CLASS_ORDER[0])
        expected = sum(
            (probability - float(index == 0)) ** 2
            for index, probability in enumerate(baseline)
        ) - sum(
            (probability - float(index == 0)) ** 2
            for index, probability in enumerate(candidate)
        )
        self.assertAlmostEqual(comparison.observed_improvement, expected, places=14)
        self.assertAlmostEqual(comparison.adjusted_lower_bound, expected, places=14)
        self.assertEqual(comparison.bootstrap_probability_above_delta, 1.0)
        self.assertEqual(comparison.session_count, 5)
        self.assertEqual(comparison.row_count, 5)
        self.assertEqual(result.contract.primary_loss, PrimaryLoss.PER_ROW_MULTICLASS_BRIER)

    def test_observed_improvement_equally_weights_sessions_with_unequal_rows(self) -> None:
        axis = tuple(f"session-{index}" for index in range(5))
        row_sessions = (axis[0],) * 10 + axis[1:]
        candidate_losses = (0.40,) * 10 + (0.10,) * 4
        oof = _development_oof(
            axis=axis,
            row_sessions=row_sessions,
            losses_by_model={
                CANDIDATE_MODEL_IDS[0]: candidate_losses,
            },
        )

        result = _evaluate(oof)

        comparison = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[0])
        equally_weighted = statistics.fmean((-0.10, 0.20, 0.20, 0.20, 0.20))
        row_weighted = statistics.fmean((-0.10,) * 10 + (0.20,) * 4)
        self.assertAlmostEqual(comparison.observed_improvement, equally_weighted, places=14)
        self.assertNotAlmostEqual(comparison.observed_improvement, row_weighted, places=8)
        self.assertEqual(comparison.session_count, 5)
        self.assertEqual(comparison.row_count, 14)
        self.assertEqual(result.contract.inference_unit, InferenceUnit.VALIDATION_SESSION)

    def test_bonferroni_lower_percentile_matches_circular_block_reference(self) -> None:
        axis = tuple(f"session-{index}" for index in range(6))
        improvements = (-0.04, 0.01, 0.03, 0.08, 0.12, 0.20)
        oof = _development_oof(
            axis=axis,
            losses_by_model={
                MODEL_IDS[0]: tuple(0.30 for _session in axis),
                CANDIDATE_MODEL_IDS[0]: tuple(
                    0.30 - improvement for improvement in improvements
                ),
            },
        )

        result = _evaluate(oof)

        comparison = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[0])
        distribution = _reference_circular_distribution(improvements)
        expected_lower = _type7(
            distribution,
            FAMILYWISE_ALPHA / GLOBAL_FAMILYWISE_COMPARISON_COUNT,
        )
        expected_probability = sum(
            value > MINIMUM_EFFECT_DELTA for value in distribution
        ) / len(distribution)
        self.assertAlmostEqual(comparison.adjusted_lower_bound, expected_lower, places=14)
        self.assertAlmostEqual(
            comparison.bootstrap_probability_above_delta,
            expected_probability,
            places=14,
        )
        self.assertAlmostEqual(
            result.contract.per_comparison_alpha,
            FAMILYWISE_ALPHA / GLOBAL_FAMILYWISE_COMPARISON_COUNT,
            places=18,
        )

    def test_is_deterministic_marks_every_output_exploratory_and_exposes_no_replicates(
        self,
    ) -> None:
        axis = tuple(f"session-{index}" for index in range(6))
        losses = tuple(0.08 + index * 0.01 for index in range(len(axis)))
        oof = _development_oof(
            axis=axis,
            losses_by_model={CANDIDATE_MODEL_IDS[0]: losses},
        )

        first = _evaluate(oof)
        second = _evaluate(oof)

        self.assertEqual(first, second)
        self.assertEqual(
            first.status,
            ExploratoryEvidenceStatus.EXPLORATORY_FOLLOWUP_NOT_ADOPTION_EVIDENCE,
        )
        self.assertEqual(
            first.claim,
            "exploratory_followup_not_adoption_evidence",
        )
        self.assertFalse(first.result_tuning_performed)
        self.assertEqual(first.contract.seed, BOOTSTRAP_SEED)
        self.assertEqual(first.contract.prng_method, PRNG_METHOD)
        self.assertEqual(first.contract.replicates, BOOTSTRAP_REPLICATES)
        self.assertEqual(
            first.contract.global_familywise_comparison_count,
            GLOBAL_FAMILYWISE_COMPARISON_COUNT,
        )
        self.assertEqual(len(first.result_sha256), 64)
        for comparison in first.comparisons:
            self.assertTrue(math.isfinite(comparison.observed_improvement))
            self.assertTrue(math.isfinite(comparison.adjusted_lower_bound))
            self.assertTrue(
                math.isfinite(comparison.bootstrap_probability_above_delta)
            )
            self.assertEqual(len(comparison.replicate_distribution_sha256), 64)
            self.assertFalse(hasattr(comparison, "replicate_distribution"))
            self.assertFalse(hasattr(comparison, "bootstrap_replicates"))

    def test_preserves_frozen_axis_and_draws_circular_session_blocks(self) -> None:
        axis = tuple(f"session-{index}" for index in range(6))
        oof = _development_oof(axis=axis, reverse_prediction_rows=True)

        result = _evaluate(oof)
        sampled = _draw_circular_session_indices(
            session_count=6,
            block_length_sessions=5,
            generator=_StartSequence((4, 1)),
        )

        self.assertEqual(result.validation_session_ids, axis)
        self.assertEqual(sampled, (4, 5, 0, 1, 2, 1))

    def test_circular_blocks_preserve_each_validation_fold_boundary(self) -> None:
        improvements = (
            -0.10,
            -0.05,
            0.00,
            0.05,
            0.10,
            0.15,
            0.20,
            0.25,
            0.30,
            0.35,
        )
        oof = _two_fold_oof(improvements)

        result = _evaluate(oof)

        comparison = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[0])
        distribution = _reference_fold_segmented_distribution(improvements, (5, 5))
        self.assertEqual(result.validation_session_ids, oof.frozen_session_axis)
        self.assertAlmostEqual(
            comparison.adjusted_lower_bound,
            _type7(
                distribution,
                FAMILYWISE_ALPHA / GLOBAL_FAMILYWISE_COMPARISON_COUNT,
            ),
            places=14,
        )

    def test_rejects_stale_row_mask_and_impossible_fold_boundaries(self) -> None:
        oof = _development_oof()
        fold = oof.folds[0]
        impossible_fold = replace(
            fold,
            train=SessionInterval(0, 1),
        )

        with self.assertRaisesRegex(ValueError, "row_mask_sha256_mismatch"):
            _evaluate(replace(oof, row_mask_sha256="f" * 64))
        with self.assertRaisesRegex(ValueError, "development_folds_invalid"):
            _evaluate(replace(oof, folds=(impossible_fold,)))

    def test_prng_transition_has_a_runtime_independent_golden_vector(self) -> None:
        from rp001_s2 import overheat_uncertainty

        generator_type = getattr(overheat_uncertainty, "_SplitMix64", None)
        self.assertIsNotNone(generator_type)
        generator = generator_type(0)

        self.assertEqual(
            tuple(generator.next_uint64() for _index in range(4)),
            (
                0xE220A8397B1DCDAF,
                0x6E789E6AA1B965F4,
                0x06C45D188009454F,
                0xF88BB8A8724C81EC,
            ),
        )

    def test_rejects_identity_label_probability_and_metric_mismatches(self) -> None:
        oof = _development_oof()
        candidate_index = next(
            index
            for index, row in enumerate(oof.predictions)
            if row.model_id == CANDIDATE_MODEL_IDS[0]
        )
        candidate_row = oof.predictions[candidate_index]
        cases = (
            (
                replace(oof, predictions=oof.predictions[:-1]),
                "prediction_identity_mismatch",
            ),
            (
                replace(
                    oof,
                    predictions=oof.predictions[:candidate_index]
                    + (
                        replace(candidate_row, label=CLASS_ORDER[1]),
                    )
                    + oof.predictions[candidate_index + 1 :],
                ),
                "prediction_label_mismatch",
            ),
            (
                replace(
                    oof,
                    predictions=oof.predictions[:candidate_index]
                    + (
                        replace(
                            candidate_row,
                            probabilities=(math.nan,) + candidate_row.probabilities[1:],
                        ),
                    )
                    + oof.predictions[candidate_index + 1 :],
                ),
                "probability_vector_invalid",
            ),
            (
                replace(
                    oof,
                    metrics=(
                        replace(
                            oof.metrics[0],
                            multiclass_brier=oof.metrics[0].multiclass_brier + 0.01,
                        ),
                    )
                    + oof.metrics[1:],
                ),
                "oof_metric_probability_mismatch",
            ),
        )

        for invalid, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    _evaluate(invalid)

    def test_rejects_any_attempt_to_change_the_formal_inference_constants(self) -> None:
        oof = _development_oof()
        cases = (
            (
                {"global_familywise_comparison_count": 71},
                "global_familywise_comparison_count_mismatch",
            ),
            ({"seed": BOOTSTRAP_SEED + 1}, "bootstrap_seed_mismatch"),
            (
                {"replicates": BOOTSTRAP_REPLICATES - 1},
                "bootstrap_replicates_mismatch",
            ),
            (
                {"block_length_sessions": BLOCK_LENGTH_SESSIONS - 1},
                "bootstrap_block_length_mismatch",
            ),
            ({"delta": MINIMUM_EFFECT_DELTA + 0.001}, "minimum_effect_delta_mismatch"),
            ({"familywise_alpha": 0.10}, "familywise_alpha_mismatch"),
        )

        for changed, message in cases:
            arguments = {
                "global_familywise_comparison_count": (
                    GLOBAL_FAMILYWISE_COMPARISON_COUNT
                ),
            }
            arguments.update(changed)
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    evaluate_competitive_path_oof_uncertainty(oof, **arguments)

    def test_candidate_pass_requires_lower_bound_above_delta_against_both_baselines(
        self,
    ) -> None:
        axis = tuple(f"session-{index}" for index in range(5))
        oof = _development_oof(
            axis=axis,
            losses_by_model={
                MODEL_IDS[0]: tuple(0.40 for _session in axis),
                MODEL_IDS[1]: tuple(0.10 for _session in axis),
                CANDIDATE_MODEL_IDS[0]: tuple(0.20 for _session in axis),
            },
        )

        result = _evaluate(oof)

        versus_b1 = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[0])
        versus_b2 = _comparison(result, CANDIDATE_MODEL_IDS[0], MODEL_IDS[1])
        decision = _candidate(result, CANDIDATE_MODEL_IDS[0])
        self.assertTrue(versus_b1.passed)
        self.assertFalse(versus_b2.passed)
        self.assertFalse(decision.passed)
        self.assertEqual(
            tuple(reason.code for reason in decision.reasons),
            (CandidateDecisionReasonCode.ADJUSTED_LOWER_BOUND_NOT_ABOVE_DELTA,),
        )
        self.assertEqual(
            tuple(reason.baseline_model_id for reason in decision.reasons),
            (MODEL_IDS[1],),
        )
        self.assertEqual(
            tuple(value.baseline_model_id for value in decision.comparisons),
            MODEL_IDS[:2],
        )

    def test_result_hash_binds_inputs_exclusions_and_validation_evidence_only_losses_use_rows(
        self,
    ) -> None:
        oof = _development_oof()
        original = _evaluate(oof)
        changed_input = _evaluate(replace(oof, input_dataset_sha256="c" * 64))
        exclusion = ExcludedOOFRow(
            row_id="excluded-row-001",
            symbol="AAPL",
            session_id=oof.frozen_session_axis[0],
            horizon=oof.horizon,
            label=CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE,
            reason="censored_or_not_identifiable",
            source_evidence_sha256="d" * 64,
        )
        changed_exclusion = _evaluate(
            _recompute_row_mask(replace(
                oof,
                excluded_rows=(exclusion,),
                input_dataset_sha256="f" * 64,
            ))
        )
        changed_prediction = _evaluate(
            _replace_prediction_loss(
                oof,
                model_id=CANDIDATE_MODEL_IDS[0],
                row_id=oof.common_validation_row_ids[0],
                loss=0.11,
            )
        )
        changed_source = _evaluate(
            replace(
                oof,
                input_dataset_sha256="1" * 64,
                predictions=tuple(
                    replace(row, source_evidence_sha256="2" * 64)
                    if row.row_id == oof.common_validation_row_ids[0]
                    else row
                    for row in oof.predictions
                ),
            )
        )

        self.assertEqual(original.comparisons, changed_input.comparisons)
        self.assertEqual(original.comparisons, changed_exclusion.comparisons)
        self.assertNotEqual(original.result_sha256, changed_input.result_sha256)
        self.assertNotEqual(original.result_sha256, changed_exclusion.result_sha256)
        self.assertNotEqual(
            original.excluded_rows_sha256,
            changed_exclusion.excluded_rows_sha256,
        )
        self.assertNotEqual(
            original.validation_evidence_sha256,
            changed_prediction.validation_evidence_sha256,
        )
        self.assertNotEqual(original.result_sha256, changed_prediction.result_sha256)
        self.assertEqual(original.comparisons, changed_source.comparisons)
        self.assertNotEqual(
            original.validation_evidence_sha256,
            changed_source.validation_evidence_sha256,
        )
        self.assertNotEqual(original.result_sha256, changed_source.result_sha256)
        self.assertNotEqual(
            _comparison(
                original,
                CANDIDATE_MODEL_IDS[0],
                MODEL_IDS[0],
            ).replicate_distribution_sha256,
            _comparison(
                changed_prediction,
                CANDIDATE_MODEL_IDS[0],
                MODEL_IDS[0],
            ).replicate_distribution_sha256,
        )

    def test_rejects_empty_or_insufficient_observed_validation_sessions(self) -> None:
        oof = _development_oof()
        empty = replace(
            oof,
            common_validation_row_ids=(),
            predictions=(),
            metrics=(),
        )
        short = _development_oof(
            axis=tuple(f"session-{index}" for index in range(4)),
        )

        with self.assertRaisesRegex(ValueError, "empty_validation_rows"):
            _evaluate(empty)
        with self.assertRaisesRegex(ValueError, "insufficient_validation_sessions"):
            _evaluate(short)

    def test_public_result_types_reject_contradictory_decisions(self) -> None:
        result = _evaluate(_development_oof())
        comparison = result.comparisons[0]
        candidate = result.candidates[0]

        with self.assertRaisesRegex(ValueError, "comparison_result_invalid"):
            replace(comparison, passed=not comparison.passed)
        with self.assertRaisesRegex(ValueError, "comparison_result_invalid"):
            replace(
                comparison,
                adjusted_lower_bound=MINIMUM_EFFECT_DELTA,
                passed=True,
            )
        at_delta = replace(
            comparison,
            adjusted_lower_bound=MINIMUM_EFFECT_DELTA,
            passed=False,
        )
        self.assertFalse(at_delta.passed)
        with self.assertRaisesRegex(ValueError, "candidate_result_invalid"):
            replace(candidate, passed=not candidate.passed)
        with self.assertRaisesRegex(ValueError, "uncertainty_result_invalid"):
            replace(result, comparisons=tuple(reversed(result.comparisons)))


if __name__ == "__main__":
    unittest.main()
