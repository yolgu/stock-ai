"""Nested purged OOF evaluation for RP-001-S2 Cycle 002."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from rp001_s2.cycle002 import Cycle002Family, Cycle002Features, cycle002_basis
from rp001_s2.discovery import (
    ConstrainedLogisticModel,
    TrainingRow,
    fit_constrained_logistic,
    predict_probability,
)
from rp001_s2.evaluation import (
    HalfOpenInterval,
    PurgedFold,
    brier_score,
    build_development_folds,
    choose_alarm_threshold,
)


_INNER_MINIMUM_TRAINING = 126
_INNER_VALIDATION = 42
_PURGE = 10
_EMBARGO = 10
_L2_GRID = (0.01, 0.1, 1.0, 10.0)
_DIRECTIONAL_EDGES = (-8.0, -1.5, -0.5, 0.5, 1.5, 8.0)


@dataclass(frozen=True)
class Cycle002Example:
    row_id: str
    symbol: str
    session_index: int
    session_id: str
    features: Cycle002Features
    outcome: bool
    end_offset_sessions: int | None

    def __post_init__(self) -> None:
        if not self.row_id or not self.symbol or not self.session_id:
            raise ValueError("cycle002_example_identity_required")
        if self.session_index < 0:
            raise ValueError("cycle002_session_index_invalid")
        if type(self.outcome) is not bool or self.outcome != (
            self.end_offset_sessions is not None
        ):
            raise ValueError("cycle002_end_offset_outcome_mismatch")


@dataclass(frozen=True)
class Cycle002PredictionRow:
    family_id: str
    fold_id: str
    row_id: str
    symbol: str
    session_id: str
    outcome: bool
    end_offset_sessions: int | None
    candidate_probability: float
    baseline_constant_probability: float
    baseline_trend_probability: float


@dataclass(frozen=True)
class FrozenCycle002Model:
    family_id: str
    selected_l2_penalty: float
    model: ConstrainedLogisticModel
    alarm_threshold: float | None


@dataclass(frozen=True)
class Cycle002DevelopmentEvaluation:
    family_ids: tuple[str, ...]
    folds: tuple[PurgedFold, ...]
    predictions: tuple[Cycle002PredictionRow, ...]
    fold_selected_l2: tuple[tuple[str, str, float], ...]
    frozen_models: tuple[FrozenCycle002Model, ...]
    baseline_constant_probability: float
    baseline_directional_counts: tuple[tuple[int, int], ...]


def run_cycle002_purged_oof(
    examples: Sequence[Cycle002Example],
    *,
    session_count: int,
) -> Cycle002DevelopmentEvaluation:
    """Compare all Cycle 002 families and baselines on one eligible row mask."""
    values = tuple(examples)
    _validate_examples(values, session_count)
    folds = build_development_folds(session_count)
    if len(folds) < 3:
        raise ValueError("insufficient_development_folds")
    predictions: list[Cycle002PredictionRow] = []
    selected_l2: list[tuple[str, str, float]] = []
    for fold in folds:
        training = _rows_in(values, fold.train)
        validation = _rows_in(values, fold.validation)
        if not training or not validation:
            raise ValueError("empty_fold_rows")
        constant = _jeffreys_probability(training)
        directional = _directional_counts(training)
        for family in Cycle002Family:
            penalty = _select_l2(training, family, fold.train.stop)
            selected_l2.append((fold.fold_id, family.value, penalty))
            model = fit_constrained_logistic(
                _candidate_training_rows(training, family),
                l2_penalty=penalty,
            )
            for row in validation:
                predictions.append(
                    Cycle002PredictionRow(
                        family_id=family.value,
                        fold_id=fold.fold_id,
                        row_id=row.row_id,
                        symbol=row.symbol,
                        session_id=row.session_id,
                        outcome=row.outcome,
                        end_offset_sessions=row.end_offset_sessions,
                        candidate_probability=predict_probability(
                            model,
                            cycle002_basis(family, row.features),
                        ),
                        baseline_constant_probability=constant,
                        baseline_trend_probability=_directional_probability(
                            row.features.base.z1,
                            directional,
                        ),
                    )
                )
    frozen_models: list[FrozenCycle002Model] = []
    for family in Cycle002Family:
        penalty = _select_l2(values, family, session_count)
        model = fit_constrained_logistic(
            _candidate_training_rows(values, family),
            l2_penalty=penalty,
        )
        family_predictions = tuple(
            row for row in predictions if row.family_id == family.value
        )
        threshold = choose_alarm_threshold(family_predictions)  # type: ignore[arg-type]
        frozen_models.append(
            FrozenCycle002Model(
                family_id=family.value,
                selected_l2_penalty=penalty,
                model=model,
                alarm_threshold=threshold.threshold,
            )
        )
    return Cycle002DevelopmentEvaluation(
        family_ids=tuple(family.value for family in Cycle002Family),
        folds=folds,
        predictions=tuple(predictions),
        fold_selected_l2=tuple(selected_l2),
        frozen_models=tuple(frozen_models),
        baseline_constant_probability=_jeffreys_probability(values),
        baseline_directional_counts=_directional_counts(values),
    )


def _select_l2(
    training: Sequence[Cycle002Example],
    family: Cycle002Family,
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
                predict_probability(model, cycle002_basis(family, row.features))
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
    examples: tuple[Cycle002Example, ...],
    session_count: int,
) -> None:
    if not examples:
        raise ValueError("evaluation_examples_required")
    if len({row.row_id for row in examples}) != len(examples):
        raise ValueError("duplicate_evaluation_row_id")
    if any(row.session_index >= session_count for row in examples):
        raise ValueError("evaluation_session_out_of_domain")


def _rows_in(
    examples: Sequence[Cycle002Example],
    interval: HalfOpenInterval,
) -> tuple[Cycle002Example, ...]:
    return tuple(
        row
        for row in examples
        if interval.start <= row.session_index < interval.stop
    )


def _candidate_training_rows(
    examples: Sequence[Cycle002Example],
    family: Cycle002Family,
) -> tuple[TrainingRow, ...]:
    return tuple(
        TrainingRow(
            basis=cycle002_basis(family, row.features),
            outcome=row.outcome,
        )
        for row in examples
    )


def _jeffreys_probability(examples: Sequence[Cycle002Example]) -> float:
    values = tuple(examples)
    return (sum(row.outcome for row in values) + 0.5) / (len(values) + 1.0)


def _directional_counts(
    examples: Sequence[Cycle002Example],
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
