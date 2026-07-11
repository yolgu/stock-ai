"""Nested purged OOF evaluation for RP-001-S2 Cycle 003."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from rp001_s2.cycle003 import Cycle003Family, Cycle003Features, cycle003_basis
from rp001_s2.discovery import (
    ConstrainedLogisticModel,
    TrainingRow,
    fit_constrained_logistic,
    predict_probability,
)
from rp001_s2.evaluation import (
    HalfOpenInterval,
    PurgedFold,
    ThresholdSelection,
    brier_score,
    build_development_folds,
)


_INNER_MINIMUM_TRAINING = 126
_INNER_VALIDATION = 42
_PURGE = 10
_EMBARGO = 10
_L2_GRID = (0.01, 0.1, 1.0, 10.0)
_DIRECTIONAL_EDGES = (-8.0, -1.5, -0.5, 0.5, 1.5, 8.0)


@dataclass(frozen=True)
class Cycle003Example:
    row_id: str
    symbol: str
    session_index: int
    session_id: str
    features: Cycle003Features
    outcome: bool
    recovery_offset_sessions: int | None

    def __post_init__(self) -> None:
        if not self.row_id or not self.symbol or not self.session_id:
            raise ValueError("cycle003_example_identity_required")
        if self.session_index < 0:
            raise ValueError("cycle003_session_index_invalid")
        if type(self.outcome) is not bool or self.outcome != (
            self.recovery_offset_sessions is not None
        ):
            raise ValueError("cycle003_recovery_offset_outcome_mismatch")


@dataclass(frozen=True)
class Cycle003PredictionRow:
    family_id: str
    fold_id: str
    row_id: str
    symbol: str
    session_id: str
    outcome: bool
    recovery_offset_sessions: int | None
    candidate_probability: float
    baseline_constant_probability: float
    baseline_trend_probability: float


@dataclass(frozen=True)
class FrozenCycle003Model:
    family_id: str
    selected_l2_penalty: float
    model: ConstrainedLogisticModel
    alarm_threshold: float | None


@dataclass(frozen=True)
class Cycle003DevelopmentEvaluation:
    family_ids: tuple[str, ...]
    folds: tuple[PurgedFold, ...]
    predictions: tuple[Cycle003PredictionRow, ...]
    fold_selected_l2: tuple[tuple[str, str, float], ...]
    frozen_models: tuple[FrozenCycle003Model, ...]
    baseline_constant_probability: float
    baseline_directional_counts: tuple[tuple[int, int], ...]


def run_cycle003_purged_oof(
    examples: Sequence[Cycle003Example],
    *,
    session_count: int,
) -> Cycle003DevelopmentEvaluation:
    """Compare all Cycle 003 recovery families on one eligible row mask."""
    values = tuple(examples)
    _validate_examples(values, session_count)
    folds = build_development_folds(session_count)
    if len(folds) < 3:
        raise ValueError("insufficient_development_folds")
    predictions: list[Cycle003PredictionRow] = []
    selected_l2: list[tuple[str, str, float]] = []
    for fold in folds:
        training = _rows_in(values, fold.train)
        validation = _rows_in(values, fold.validation)
        if not training or not validation:
            raise ValueError("empty_fold_rows")
        constant = _jeffreys_probability(training)
        directional = _directional_counts(training)
        for family in Cycle003Family:
            penalty = _select_l2(training, family, fold.train.stop)
            selected_l2.append((fold.fold_id, family.value, penalty))
            model = fit_constrained_logistic(
                _candidate_training_rows(training, family),
                l2_penalty=penalty,
            )
            for row in validation:
                predictions.append(
                    Cycle003PredictionRow(
                        family_id=family.value,
                        fold_id=fold.fold_id,
                        row_id=row.row_id,
                        symbol=row.symbol,
                        session_id=row.session_id,
                        outcome=row.outcome,
                        recovery_offset_sessions=row.recovery_offset_sessions,
                        candidate_probability=predict_probability(
                            model,
                            cycle003_basis(family, row.features),
                        ),
                        baseline_constant_probability=constant,
                        baseline_trend_probability=_directional_probability(
                            row.features.base.z1,
                            directional,
                        ),
                    )
                )
    frozen_models: list[FrozenCycle003Model] = []
    for family in Cycle003Family:
        penalty = _select_l2(values, family, session_count)
        model = fit_constrained_logistic(
            _candidate_training_rows(values, family),
            l2_penalty=penalty,
        )
        family_predictions = tuple(
            row for row in predictions if row.family_id == family.value
        )
        threshold = choose_cycle003_alarm_threshold(family_predictions)
        frozen_models.append(
            FrozenCycle003Model(
                family_id=family.value,
                selected_l2_penalty=penalty,
                model=model,
                alarm_threshold=threshold.threshold,
            )
        )
    return Cycle003DevelopmentEvaluation(
        family_ids=tuple(family.value for family in Cycle003Family),
        folds=folds,
        predictions=tuple(predictions),
        fold_selected_l2=tuple(selected_l2),
        frozen_models=tuple(frozen_models),
        baseline_constant_probability=_jeffreys_probability(values),
        baseline_directional_counts=_directional_counts(values),
    )


def choose_cycle003_alarm_threshold(
    rows: Sequence[Cycle003PredictionRow],
) -> ThresholdSelection:
    """Use the next representable value above Q90 so ties cannot inflate alarms."""
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
    probabilities = tuple(row.candidate_probability for row in values)
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError("probability_out_of_domain")
    threshold = math.nextafter(_type7_quantile(probabilities, 0.90), math.inf)
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
        selection_rule="development_nested_oof_strictly_above_type7_quantile_0.90",
    )


def _select_l2(
    training: Sequence[Cycle003Example],
    family: Cycle003Family,
    session_count: int,
) -> float:
    inner_folds = _build_inner_folds(session_count)
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
            try:
                model = fit_constrained_logistic(
                    _candidate_training_rows(fit_rows, family),
                    l2_penalty=penalty,
                )
            except ValueError:
                valid = False
                break
            outcomes.extend(row.outcome for row in validation_rows)
            probabilities.extend(
                predict_probability(model, cycle003_basis(family, row.features))
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


def _build_inner_folds(session_count: int) -> tuple[PurgedFold, ...]:
    if session_count < 0:
        raise ValueError("session_count_invalid")
    folds: list[PurgedFold] = []
    train_stop = _INNER_MINIMUM_TRAINING
    while True:
        purge = HalfOpenInterval(train_stop, train_stop + _PURGE)
        validation = HalfOpenInterval(purge.stop, purge.stop + _INNER_VALIDATION)
        embargo = HalfOpenInterval(validation.stop, validation.stop + _EMBARGO)
        if embargo.stop > session_count:
            break
        folds.append(
            PurgedFold(
                fold_id=f"inner_{len(folds) + 1:02d}",
                train=HalfOpenInterval(0, train_stop),
                purge=purge,
                validation=validation,
                embargo=embargo,
            )
        )
        train_stop = validation.stop
    return tuple(folds)


def _validate_examples(
    examples: tuple[Cycle003Example, ...],
    session_count: int,
) -> None:
    if not examples:
        raise ValueError("evaluation_examples_required")
    if len({row.row_id for row in examples}) != len(examples):
        raise ValueError("duplicate_evaluation_row_id")
    if any(row.session_index >= session_count for row in examples):
        raise ValueError("evaluation_session_out_of_domain")


def _rows_in(
    examples: Sequence[Cycle003Example],
    interval: HalfOpenInterval,
) -> tuple[Cycle003Example, ...]:
    return tuple(
        row
        for row in examples
        if interval.start <= row.session_index < interval.stop
    )


def _candidate_training_rows(
    examples: Sequence[Cycle003Example],
    family: Cycle003Family,
) -> tuple[TrainingRow, ...]:
    return tuple(
        TrainingRow(
            basis=cycle003_basis(family, row.features),
            outcome=row.outcome,
        )
        for row in examples
    )


def _jeffreys_probability(examples: Sequence[Cycle003Example]) -> float:
    values = tuple(examples)
    return (sum(row.outcome for row in values) + 0.5) / (len(values) + 1.0)


def _directional_counts(
    examples: Sequence[Cycle003Example],
) -> tuple[tuple[int, int], ...]:
    counts = [[0, 0] for _ in range(5)]
    for row in examples:
        index = _bin_index(row.features.base.z1)
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
