"""Nested purged development evaluation for RP-001-S2 cycle 001."""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rp001_s2.discovery import (
    CandidateFamily,
    ConstrainedLogisticModel,
    ForecastFeatures,
    TrainingRow,
    candidate_basis,
    fit_constrained_logistic,
    predict_probability,
)


_OUTER_MINIMUM_TRAINING = 252
_OUTER_VALIDATION = 63
_INNER_MINIMUM_TRAINING = 126
_INNER_VALIDATION = 42
_PURGE = 10
_EMBARGO = 10
_L2_GRID = (0.01, 0.1, 1.0, 10.0)
_DIRECTIONAL_EDGES = (-8.0, -1.5, -0.5, 0.5, 1.5, 8.0)


@dataclass(frozen=True)
class HalfOpenInterval:
    start: int
    stop: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.stop < self.start:
            raise ValueError("interval_invalid")


@dataclass(frozen=True)
class PurgedFold:
    fold_id: str
    train: HalfOpenInterval
    purge: HalfOpenInterval
    validation: HalfOpenInterval
    embargo: HalfOpenInterval


@dataclass(frozen=True)
class EvaluationExample:
    row_id: str
    symbol: str
    session_index: int
    session_id: str
    features: ForecastFeatures
    outcome: bool
    onset_offset_sessions: int | None

    def __post_init__(self) -> None:
        if not self.row_id or not self.symbol or not self.session_id:
            raise ValueError("evaluation_example_identity_required")
        if self.session_index < 0:
            raise ValueError("session_index_invalid")
        if self.outcome != (self.onset_offset_sessions is not None):
            raise ValueError("onset_offset_outcome_mismatch")


@dataclass(frozen=True)
class PredictionRow:
    family_id: str
    fold_id: str
    row_id: str
    symbol: str
    session_id: str
    outcome: bool
    onset_offset_sessions: int | None
    candidate_probability: float
    baseline_constant_probability: float
    baseline_trend_probability: float


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float | None
    alarm_count: int
    recall: float
    false_alarm_rate: float
    precision: float | None
    selection_rule: str


@dataclass(frozen=True)
class FrozenFamilyModel:
    family_id: str
    selected_l2_penalty: float
    model: ConstrainedLogisticModel
    alarm_threshold: float | None


@dataclass(frozen=True)
class DevelopmentEvaluation:
    family_ids: tuple[str, ...]
    folds: tuple[PurgedFold, ...]
    predictions: tuple[PredictionRow, ...]
    fold_selected_l2: tuple[tuple[str, str, float], ...]
    frozen_models: tuple[FrozenFamilyModel, ...]
    baseline_constant_probability: float
    baseline_directional_counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ContrastInference:
    family_id: str
    baseline_id: str
    brier_improvement: float
    bootstrap_standard_error: float | None
    simultaneous_lower_bound_95: float | None
    passed_delta_0_005: bool


@dataclass(frozen=True)
class MaxTInference:
    method: str
    seed: int
    replicates: int
    block_length_sessions: int
    simultaneous_critical_value: float | None
    contrasts: tuple[ContrastInference, ...]


def build_development_folds(session_count: int) -> tuple[PurgedFold, ...]:
    """Build the frozen expanding outer plan on the common session axis."""
    return _build_folds(
        session_count=session_count,
        minimum_training=_OUTER_MINIMUM_TRAINING,
        validation_length=_OUTER_VALIDATION,
        prefix="development",
    )


def run_purged_oof(
    examples: Sequence[EvaluationExample],
    *,
    session_count: int,
) -> DevelopmentEvaluation:
    """Run all candidates and two baselines on one model-independent mask."""
    values = tuple(examples)
    _validate_examples(values, session_count)
    folds = build_development_folds(session_count)
    if len(folds) < 3:
        raise ValueError("insufficient_development_folds")
    predictions: list[PredictionRow] = []
    selected_l2: list[tuple[str, str, float]] = []
    for fold in folds:
        training = _rows_in(values, fold.train)
        validation = _rows_in(values, fold.validation)
        if not training or not validation:
            raise ValueError("empty_fold_rows")
        constant = _jeffreys_probability(training)
        directional = _directional_counts(training)
        for family in CandidateFamily:
            l2_penalty = _select_l2(training, family, fold.train.stop)
            selected_l2.append((fold.fold_id, family.value, l2_penalty))
            model = fit_constrained_logistic(
                _candidate_training_rows(training, family),
                l2_penalty=l2_penalty,
            )
            for row in validation:
                predictions.append(
                    PredictionRow(
                        family_id=family.value,
                        fold_id=fold.fold_id,
                        row_id=row.row_id,
                        symbol=row.symbol,
                        session_id=row.session_id,
                        outcome=row.outcome,
                        onset_offset_sessions=row.onset_offset_sessions,
                        candidate_probability=predict_probability(
                            model,
                            candidate_basis(family, row.features),
                        ),
                        baseline_constant_probability=constant,
                        baseline_trend_probability=_directional_probability(
                            row.features.z1,
                            directional,
                        ),
                    )
                )

    final_l2: dict[CandidateFamily, float] = {}
    frozen_models: list[FrozenFamilyModel] = []
    for family in CandidateFamily:
        selected = _select_l2(values, family, session_count)
        final_l2[family] = selected
        model = fit_constrained_logistic(
            _candidate_training_rows(values, family),
            l2_penalty=selected,
        )
        family_predictions = tuple(
            row for row in predictions if row.family_id == family.value
        )
        threshold = choose_alarm_threshold(family_predictions)
        frozen_models.append(
            FrozenFamilyModel(
                family_id=family.value,
                selected_l2_penalty=selected,
                model=model,
                alarm_threshold=threshold.threshold,
            )
        )
    baseline_constant = _jeffreys_probability(values)
    baseline_directional = _directional_counts(values)
    return DevelopmentEvaluation(
        family_ids=tuple(family.value for family in CandidateFamily),
        folds=folds,
        predictions=tuple(predictions),
        fold_selected_l2=tuple(selected_l2),
        frozen_models=tuple(frozen_models),
        baseline_constant_probability=baseline_constant,
        baseline_directional_counts=baseline_directional,
    )


def choose_alarm_threshold(rows: Sequence[PredictionRow]) -> ThresholdSelection:
    """Freeze the type-7 90th percentile of nested development OOF probabilities."""
    values = tuple(rows)
    if not values:
        return ThresholdSelection(
            threshold=None,
            alarm_count=0,
            recall=0.0,
            false_alarm_rate=0.0,
            precision=None,
            selection_rule="not_estimable_no_development_predictions",
        )
    threshold = _type7_quantile(
        tuple(row.candidate_probability for row in values),
        0.90,
    )
    alarms = tuple(row for row in values if row.candidate_probability >= threshold)
    positives = sum(row.outcome for row in values)
    negatives = len(values) - positives
    true_positives = sum(row.outcome for row in alarms)
    false_positives = len(alarms) - true_positives
    return ThresholdSelection(
        threshold=threshold,
        alarm_count=len(alarms),
        recall=true_positives / positives if positives else 0.0,
        false_alarm_rate=false_positives / negatives if negatives else 0.0,
        precision=true_positives / len(alarms) if alarms else None,
        selection_rule="development_nested_oof_type7_probability_quantile_0.90",
    )


def brier_score(outcomes: Sequence[bool], probabilities: Sequence[float]) -> float:
    outcome_values = tuple(outcomes)
    probability_values = tuple(probabilities)
    if not outcome_values or len(outcome_values) != len(probability_values):
        raise ValueError("brier_rows_invalid")
    if any(not 0.0 <= value <= 1.0 for value in probability_values):
        raise ValueError("probability_out_of_domain")
    return sum(
        (float(outcome) - probability) ** 2
        for outcome, probability in zip(
            outcome_values,
            probability_values,
            strict=True,
        )
    ) / len(outcome_values)


def synchronized_block_max_t(
    rows: Sequence[PredictionRow],
    *,
    seed: int = 20260711,
    replicates: int = 2000,
    block_length_sessions: int = 20,
    delta: float = 0.005,
) -> MaxTInference:
    """Compute six synchronized candidate-vs-baseline simultaneous bounds."""
    values = tuple(rows)
    family_ids = tuple(sorted({row.family_id for row in values}))
    if len(family_ids) != 3 or replicates <= 1 or block_length_sessions <= 0:
        raise ValueError("max_t_input_invalid")
    by_family = {
        family: tuple(row for row in values if row.family_id == family)
        for family in family_ids
    }
    reference_keys = tuple(
        (row.fold_id, row.row_id, row.session_id, row.outcome)
        for row in by_family[family_ids[0]]
    )
    if any(
        tuple(
            (row.fold_id, row.row_id, row.session_id, row.outcome)
            for row in by_family[family]
        )
        != reference_keys
        for family in family_ids[1:]
    ):
        raise ValueError("max_t_common_mask_mismatch")
    sessions = tuple(dict.fromkeys(row.session_id for row in by_family[family_ids[0]]))
    if len(sessions) < block_length_sessions:
        raise ValueError("max_t_insufficient_sessions")
    session_differences: dict[tuple[str, str], dict[str, tuple[float, ...]]] = {}
    observed: dict[tuple[str, str], float] = {}
    for family in family_ids:
        family_rows = by_family[family]
        for baseline_id in ("B1", "B2"):
            grouped: dict[str, list[float]] = {session: [] for session in sessions}
            all_values: list[float] = []
            for row in family_rows:
                baseline = (
                    row.baseline_constant_probability
                    if baseline_id == "B1"
                    else row.baseline_trend_probability
                )
                difference = (
                    (float(row.outcome) - baseline) ** 2
                    - (float(row.outcome) - row.candidate_probability) ** 2
                )
                grouped[row.session_id].append(difference)
                all_values.append(difference)
            key = (family, baseline_id)
            session_differences[key] = {
                session: tuple(grouped[session]) for session in sessions
            }
            observed[key] = statistics.fmean(all_values)

    generator = random.Random(seed)
    replicate_estimates: dict[tuple[str, str], list[float]] = {
        key: [] for key in observed
    }
    maximum_start = len(sessions) - block_length_sessions
    for _replicate in range(replicates):
        sampled_sessions: list[str] = []
        while len(sampled_sessions) < len(sessions):
            start = generator.randint(0, maximum_start)
            sampled_sessions.extend(sessions[start : start + block_length_sessions])
        sampled_sessions = sampled_sessions[: len(sessions)]
        for key, grouped in session_differences.items():
            sampled = [
                value
                for session in sampled_sessions
                for value in grouped[session]
            ]
            replicate_estimates[key].append(statistics.fmean(sampled))
    standard_errors = {
        key: statistics.stdev(estimates)
        for key, estimates in replicate_estimates.items()
    }
    usable = tuple(key for key, error in standard_errors.items() if error > 0.0)
    if not usable:
        critical: float | None = None
    else:
        maxima = tuple(
            max(
                (observed[key] - replicate_estimates[key][index])
                / standard_errors[key]
                for key in usable
            )
            for index in range(replicates)
        )
        critical = _type7_quantile(maxima, 0.95)
    contrasts: list[ContrastInference] = []
    for key in sorted(observed):
        error = standard_errors[key]
        lower = None if critical is None or error <= 0.0 else observed[key] - critical * error
        contrasts.append(
            ContrastInference(
                family_id=key[0],
                baseline_id=key[1],
                brier_improvement=observed[key],
                bootstrap_standard_error=error if error > 0.0 else None,
                simultaneous_lower_bound_95=lower,
                passed_delta_0_005=lower is not None and lower > delta,
            )
        )
    return MaxTInference(
        method="synchronized_moving_session_blocks_studentized_maxT",
        seed=seed,
        replicates=replicates,
        block_length_sessions=block_length_sessions,
        simultaneous_critical_value=critical,
        contrasts=tuple(contrasts),
    )


def _select_l2(
    training: Sequence[EvaluationExample],
    family: CandidateFamily,
    session_count: int,
) -> float:
    inner_folds = _build_folds(
        session_count=session_count,
        minimum_training=_INNER_MINIMUM_TRAINING,
        validation_length=_INNER_VALIDATION,
        prefix="inner",
    )
    if not inner_folds:
        return max(_L2_GRID)
    scores: list[tuple[float, float]] = []
    for penalty in _L2_GRID:
        outcomes: list[bool] = []
        probabilities: list[float] = []
        valid = True
        for fold in inner_folds:
            fit_rows = _rows_in(training, fold.train)
            validation_rows = _rows_in(training, fold.validation)
            if not fit_rows or not validation_rows:
                valid = False
                break
            model = fit_constrained_logistic(
                _candidate_training_rows(fit_rows, family),
                l2_penalty=penalty,
            )
            outcomes.extend(row.outcome for row in validation_rows)
            probabilities.extend(
                predict_probability(
                    model,
                    candidate_basis(family, row.features),
                )
                for row in validation_rows
            )
        if valid and outcomes:
            scores.append((brier_score(outcomes, probabilities), penalty))
    if not scores:
        return max(_L2_GRID)
    minimum = min(score for score, _penalty in scores)
    tied = tuple(
        penalty
        for score, penalty in scores
        if math.isclose(score, minimum, rel_tol=0.0, abs_tol=1e-15)
    )
    return max(tied)


def _build_folds(
    *,
    session_count: int,
    minimum_training: int,
    validation_length: int,
    prefix: str,
) -> tuple[PurgedFold, ...]:
    if session_count < 0:
        raise ValueError("session_count_invalid")
    folds: list[PurgedFold] = []
    train_stop = minimum_training
    while True:
        purge = HalfOpenInterval(train_stop, train_stop + _PURGE)
        validation = HalfOpenInterval(
            purge.stop,
            purge.stop + validation_length,
        )
        embargo = HalfOpenInterval(validation.stop, validation.stop + _EMBARGO)
        if embargo.stop > session_count:
            break
        folds.append(
            PurgedFold(
                fold_id=f"{prefix}_{len(folds) + 1:02d}",
                train=HalfOpenInterval(0, train_stop),
                purge=purge,
                validation=validation,
                embargo=embargo,
            )
        )
        train_stop = validation.stop
    return tuple(folds)


def _validate_examples(
    examples: tuple[EvaluationExample, ...],
    session_count: int,
) -> None:
    if not examples:
        raise ValueError("evaluation_examples_required")
    row_ids = {row.row_id for row in examples}
    if len(row_ids) != len(examples):
        raise ValueError("duplicate_evaluation_row_id")
    if any(row.session_index >= session_count for row in examples):
        raise ValueError("evaluation_session_out_of_domain")


def _rows_in(
    examples: Sequence[EvaluationExample],
    interval: HalfOpenInterval,
) -> tuple[EvaluationExample, ...]:
    return tuple(
        row
        for row in examples
        if interval.start <= row.session_index < interval.stop
    )


def _candidate_training_rows(
    examples: Sequence[EvaluationExample],
    family: CandidateFamily,
) -> tuple[TrainingRow, ...]:
    return tuple(
        TrainingRow(
            basis=candidate_basis(family, row.features),
            outcome=row.outcome,
        )
        for row in examples
    )


def _jeffreys_probability(examples: Sequence[EvaluationExample]) -> float:
    values = tuple(examples)
    successes = sum(row.outcome for row in values)
    return (successes + 0.5) / (len(values) + 1.0)


def _directional_counts(
    examples: Sequence[EvaluationExample],
) -> tuple[tuple[int, int], ...]:
    counts = [[0, 0] for _ in range(5)]
    for row in examples:
        index = _bin_index(row.features.z1)
        counts[index][0] += int(row.outcome)
        counts[index][1] += 1
    return tuple((successes, trials) for successes, trials in counts)


def _directional_probability(
    z1: float,
    counts: Sequence[tuple[int, int]],
) -> float:
    successes, trials = counts[_bin_index(z1)]
    return (successes + 0.5) / (trials + 1.0)


def _bin_index(value: float) -> int:
    if not math.isfinite(value) or not -8.0 <= value <= 8.0:
        raise ValueError("directional_feature_out_of_domain")
    for index, upper in enumerate(_DIRECTIONAL_EDGES[1:-1]):
        if value < upper:
            return index
    return 4


def _type7_quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered or not 0.0 <= probability <= 1.0:
        raise ValueError("quantile_input_invalid")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])
