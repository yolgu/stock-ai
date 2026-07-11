"""Exploratory uncertainty for frozen competitive-path development OOF results."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from rp001_s2.direction_neutral_overheat import CompetitivePathLabel, LabelHorizon
from rp001_s2.overheat_oof import (
    CANDIDATE_MODEL_IDS,
    CLASS_ORDER,
    MODEL_IDS,
    CompetitivePathDevelopmentOOF,
    DevelopmentFold,
    ExcludedOOFRow,
    OOFMetrics,
    OOFProbabilityRow,
    SessionInterval,
    _row_mask_sha256,
    multiclass_brier_score,
)


BOOTSTRAP_SEED = 20260711
BOOTSTRAP_REPLICATES = 10_000
BLOCK_LENGTH_SESSIONS = 5
GLOBAL_FAMILYWISE_COMPARISON_COUNT = 72
FAMILYWISE_ALPHA = 0.05
MINIMUM_EFFECT_DELTA = 0.005
BASELINE_MODEL_IDS = MODEL_IDS[:2]
PRNG_METHOD = "splitmix64_uint64_rejection_randrange.v1"


class ExploratoryEvidenceStatus(str, Enum):
    EXPLORATORY_FOLLOWUP_NOT_ADOPTION_EVIDENCE = (
        "exploratory_followup_not_adoption_evidence"
    )


class PrimaryLoss(str, Enum):
    PER_ROW_MULTICLASS_BRIER = "per_row_multiclass_brier"


class InferenceUnit(str, Enum):
    VALIDATION_SESSION = "equally_weighted_validation_session"


class BootstrapMethod(str, Enum):
    FOLD_SEGMENTED_CIRCULAR_MOVING_BLOCK_PERCENTILE = (
        "synchronized_fold_segmented_circular_moving_session_blocks_"
        "one_sided_bonferroni_type7_percentile"
    )


class CandidateDecisionReasonCode(str, Enum):
    PASSED_BOTH_PREDECLARED_BASELINES = "passed_both_predeclared_baselines"
    ADJUSTED_LOWER_BOUND_NOT_ABOVE_DELTA = (
        "adjusted_lower_bound_not_above_minimum_effect_delta"
    )


class OverheatUncertaintyError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OverheatUncertaintyContract:
    primary_loss: PrimaryLoss
    inference_unit: InferenceUnit
    bootstrap_method: BootstrapMethod
    prng_method: str
    seed: int
    replicates: int
    block_length_sessions: int
    global_familywise_comparison_count: int
    familywise_alpha: float
    per_comparison_alpha: float
    minimum_effect_delta: float

    def __post_init__(self) -> None:
        if (
            self.primary_loss is not PrimaryLoss.PER_ROW_MULTICLASS_BRIER
            or self.inference_unit is not InferenceUnit.VALIDATION_SESSION
            or self.bootstrap_method
            is not BootstrapMethod.FOLD_SEGMENTED_CIRCULAR_MOVING_BLOCK_PERCENTILE
            or self.prng_method != PRNG_METHOD
            or self.seed != BOOTSTRAP_SEED
            or self.replicates != BOOTSTRAP_REPLICATES
            or self.block_length_sessions != BLOCK_LENGTH_SESSIONS
            or self.global_familywise_comparison_count
            != GLOBAL_FAMILYWISE_COMPARISON_COUNT
            or self.familywise_alpha != FAMILYWISE_ALPHA
            or self.per_comparison_alpha
            != FAMILYWISE_ALPHA / GLOBAL_FAMILYWISE_COMPARISON_COUNT
            or self.minimum_effect_delta != MINIMUM_EFFECT_DELTA
        ):
            raise OverheatUncertaintyError("uncertainty_contract_invalid")


@dataclass(frozen=True)
class OverheatUncertaintyComparison:
    candidate_model_id: str
    baseline_model_id: str
    observed_improvement: float
    adjusted_lower_bound: float
    bootstrap_probability_above_delta: float
    session_count: int
    row_count: int
    replicate_distribution_sha256: str
    passed: bool

    def __post_init__(self) -> None:
        if (
            self.candidate_model_id not in CANDIDATE_MODEL_IDS
            or self.baseline_model_id not in BASELINE_MODEL_IDS
            or not _finite(self.observed_improvement)
            or not _finite(self.adjusted_lower_bound)
            or not _probability(self.bootstrap_probability_above_delta)
            or type(self.session_count) is not int
            or self.session_count < BLOCK_LENGTH_SESSIONS
            or type(self.row_count) is not int
            or self.row_count < self.session_count
            or not _is_sha256(self.replicate_distribution_sha256)
            or type(self.passed) is not bool
            or self.passed
            != (self.adjusted_lower_bound > MINIMUM_EFFECT_DELTA)
        ):
            raise OverheatUncertaintyError("comparison_result_invalid")


@dataclass(frozen=True)
class CandidateDecisionReason:
    code: CandidateDecisionReasonCode
    baseline_model_id: str | None

    def __post_init__(self) -> None:
        failed = (
            self.code
            is CandidateDecisionReasonCode.ADJUSTED_LOWER_BOUND_NOT_ABOVE_DELTA
        )
        if not isinstance(self.code, CandidateDecisionReasonCode) or (
            failed and self.baseline_model_id not in BASELINE_MODEL_IDS
        ) or (not failed and self.baseline_model_id is not None):
            raise OverheatUncertaintyError("candidate_reason_invalid")


@dataclass(frozen=True)
class OverheatCandidateUncertainty:
    candidate_model_id: str
    comparisons: tuple[OverheatUncertaintyComparison, ...]
    passed: bool
    reasons: tuple[CandidateDecisionReason, ...]

    def __post_init__(self) -> None:
        comparisons_are_typed = all(
            isinstance(value, OverheatUncertaintyComparison)
            for value in self.comparisons
        )
        failed_baselines = (
            tuple(
                value.baseline_model_id
                for value in self.comparisons
                if not value.passed
            )
            if comparisons_are_typed
            else ()
        )
        expected_reasons = (
            tuple(
                (
                    CandidateDecisionReasonCode.ADJUSTED_LOWER_BOUND_NOT_ABOVE_DELTA,
                    baseline_model_id,
                )
                for baseline_model_id in failed_baselines
            )
            if failed_baselines
            else (
                (
                    CandidateDecisionReasonCode.PASSED_BOTH_PREDECLARED_BASELINES,
                    None,
                ),
            )
        )
        if (
            self.candidate_model_id not in CANDIDATE_MODEL_IDS
            or not comparisons_are_typed
            or tuple(value.baseline_model_id for value in self.comparisons)
            != BASELINE_MODEL_IDS
            or any(
                value.candidate_model_id != self.candidate_model_id
                for value in self.comparisons
            )
            or type(self.passed) is not bool
            or self.passed != (not failed_baselines)
            or any(
                not isinstance(reason, CandidateDecisionReason)
                for reason in self.reasons
            )
            or tuple(
                (reason.code, reason.baseline_model_id) for reason in self.reasons
            )
            != expected_reasons
        ):
            raise OverheatUncertaintyError("candidate_result_invalid")


@dataclass(frozen=True)
class CompetitivePathOOFUncertainty:
    status: ExploratoryEvidenceStatus
    result_tuning_performed: bool
    contract: OverheatUncertaintyContract
    horizon: LabelHorizon
    input_dataset_sha256: str
    row_mask_sha256: str
    excluded_rows_sha256: str
    validation_evidence_sha256: str
    frozen_session_axis: tuple[str, ...]
    validation_session_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    baseline_model_ids: tuple[str, ...]
    candidate_model_ids: tuple[str, ...]
    common_validation_row_ids: tuple[str, ...]
    excluded_row_count: int
    comparisons: tuple[OverheatUncertaintyComparison, ...]
    candidates: tuple[OverheatCandidateUncertainty, ...]
    result_sha256: str

    def __post_init__(self) -> None:
        comparisons_are_typed = all(
            isinstance(value, OverheatUncertaintyComparison)
            for value in self.comparisons
        )
        candidates_are_typed = all(
            isinstance(value, OverheatCandidateUncertainty)
            for value in self.candidates
        )
        expected_pairs = tuple(
            (candidate_model_id, baseline_model_id)
            for candidate_model_id in CANDIDATE_MODEL_IDS
            for baseline_model_id in BASELINE_MODEL_IDS
        )
        if (
            self.status
            is not ExploratoryEvidenceStatus.EXPLORATORY_FOLLOWUP_NOT_ADOPTION_EVIDENCE
            or self.result_tuning_performed is not False
            or not isinstance(self.contract, OverheatUncertaintyContract)
            or not isinstance(self.horizon, LabelHorizon)
            or any(
                not _is_sha256(value)
                for value in (
                    self.input_dataset_sha256,
                    self.row_mask_sha256,
                    self.excluded_rows_sha256,
                    self.validation_evidence_sha256,
                    self.result_sha256,
                )
            )
            or self.model_ids != MODEL_IDS
            or self.baseline_model_ids != BASELINE_MODEL_IDS
            or self.candidate_model_ids != CANDIDATE_MODEL_IDS
            or type(self.excluded_row_count) is not int
            or self.excluded_row_count < 0
            or not comparisons_are_typed
            or tuple(
                (value.candidate_model_id, value.baseline_model_id)
                for value in self.comparisons
            )
            != expected_pairs
            or len(self.comparisons)
            != len(CANDIDATE_MODEL_IDS) * len(BASELINE_MODEL_IDS)
            or not candidates_are_typed
            or tuple(value.candidate_model_id for value in self.candidates)
            != CANDIDATE_MODEL_IDS
            or any(
                candidate.comparisons
                != tuple(
                    comparison
                    for comparison in self.comparisons
                    if comparison.candidate_model_id
                    == candidate.candidate_model_id
                )
                for candidate in self.candidates
            )
        ):
            raise OverheatUncertaintyError("uncertainty_result_invalid")

    @property
    def claim(self) -> str:
        return self.status.value


@dataclass(frozen=True)
class _ValidatedOOF:
    axis: tuple[str, ...]
    folds: tuple[DevelopmentFold, ...]
    excluded_rows: tuple[ExcludedOOFRow, ...]
    common_row_ids: tuple[str, ...]
    canonical_keys: tuple[tuple[str, str], ...]
    rows_by_model: Mapping[str, Mapping[tuple[str, str], OOFProbabilityRow]]
    validation_sessions: tuple[str, ...]
    fold_session_segments: tuple[tuple[str, ...], ...]


class _RandomRange(Protocol):
    def randrange(self, stop: int) -> int: ...


class _SplitMix64:
    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        if type(seed) is not int:
            raise OverheatUncertaintyError("prng_seed_invalid")
        self._state = seed & self._MASK

    def next_uint64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & self._MASK
        value = self._state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & self._MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & self._MASK
        return (value ^ (value >> 31)) & self._MASK

    def randrange(self, stop: int) -> int:
        if type(stop) is not int or not 0 < stop <= 1 << 64:
            raise OverheatUncertaintyError("prng_stop_invalid")
        limit = (1 << 64) - ((1 << 64) % stop)
        while True:
            value = self.next_uint64()
            if value < limit:
                return value % stop


def evaluate_competitive_path_oof_uncertainty(
    oof: CompetitivePathDevelopmentOOF,
    *,
    global_familywise_comparison_count: int,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
    block_length_sessions: int = BLOCK_LENGTH_SESSIONS,
    delta: float = MINIMUM_EFFECT_DELTA,
    familywise_alpha: float = FAMILYWISE_ALPHA,
) -> CompetitivePathOOFUncertainty:
    """Evaluate all predeclared candidate-baseline OOF contrasts as exploratory."""
    _validate_formal_constants(
        global_familywise_comparison_count=global_familywise_comparison_count,
        seed=seed,
        replicates=replicates,
        block_length_sessions=block_length_sessions,
        delta=delta,
        familywise_alpha=familywise_alpha,
    )
    validated = _validate_oof(oof)
    contract = OverheatUncertaintyContract(
        primary_loss=PrimaryLoss.PER_ROW_MULTICLASS_BRIER,
        inference_unit=InferenceUnit.VALIDATION_SESSION,
        bootstrap_method=(
            BootstrapMethod.FOLD_SEGMENTED_CIRCULAR_MOVING_BLOCK_PERCENTILE
        ),
        prng_method=PRNG_METHOD,
        seed=seed,
        replicates=replicates,
        block_length_sessions=block_length_sessions,
        global_familywise_comparison_count=global_familywise_comparison_count,
        familywise_alpha=familywise_alpha,
        per_comparison_alpha=(
            familywise_alpha / global_familywise_comparison_count
        ),
        minimum_effect_delta=delta,
    )
    session_improvements = _session_improvements(oof, validated)
    distributions = _bootstrap_distributions(
        session_improvements,
        validated,
        seed=seed,
        replicates=replicates,
        block_length_sessions=block_length_sessions,
    )
    comparisons = _build_comparisons(
        session_improvements,
        distributions,
        row_count=len(validated.canonical_keys),
        contract=contract,
    )
    candidates = _build_candidate_decisions(comparisons)
    excluded_rows_sha256 = _excluded_rows_sha256(validated.excluded_rows)
    validation_evidence_sha256 = _validation_evidence_sha256(oof, validated)
    result_sha256 = _result_sha256(
        oof,
        validated,
        contract,
        excluded_rows_sha256,
        validation_evidence_sha256,
        comparisons,
        candidates,
    )
    return CompetitivePathOOFUncertainty(
        status=(
            ExploratoryEvidenceStatus.EXPLORATORY_FOLLOWUP_NOT_ADOPTION_EVIDENCE
        ),
        result_tuning_performed=False,
        contract=contract,
        horizon=oof.horizon,
        input_dataset_sha256=oof.input_dataset_sha256,
        row_mask_sha256=oof.row_mask_sha256,
        excluded_rows_sha256=excluded_rows_sha256,
        validation_evidence_sha256=validation_evidence_sha256,
        frozen_session_axis=validated.axis,
        validation_session_ids=validated.validation_sessions,
        model_ids=oof.model_ids,
        baseline_model_ids=BASELINE_MODEL_IDS,
        candidate_model_ids=oof.candidate_model_ids,
        common_validation_row_ids=validated.common_row_ids,
        excluded_row_count=len(validated.excluded_rows),
        comparisons=comparisons,
        candidates=candidates,
        result_sha256=result_sha256,
    )


def _validate_formal_constants(
    *,
    global_familywise_comparison_count: int,
    seed: int,
    replicates: int,
    block_length_sessions: int,
    delta: float,
    familywise_alpha: float,
) -> None:
    checks = (
        (
            type(global_familywise_comparison_count) is int
            and global_familywise_comparison_count
            == GLOBAL_FAMILYWISE_COMPARISON_COUNT,
            "global_familywise_comparison_count_mismatch",
        ),
        (type(seed) is int and seed == BOOTSTRAP_SEED, "bootstrap_seed_mismatch"),
        (
            type(replicates) is int and replicates == BOOTSTRAP_REPLICATES,
            "bootstrap_replicates_mismatch",
        ),
        (
            type(block_length_sessions) is int
            and block_length_sessions == BLOCK_LENGTH_SESSIONS,
            "bootstrap_block_length_mismatch",
        ),
        (
            type(delta) is float and delta == MINIMUM_EFFECT_DELTA,
            "minimum_effect_delta_mismatch",
        ),
        (
            type(familywise_alpha) is float
            and familywise_alpha == FAMILYWISE_ALPHA,
            "familywise_alpha_mismatch",
        ),
    )
    for valid, code in checks:
        if not valid:
            raise OverheatUncertaintyError(code)


def _validate_oof(oof: CompetitivePathDevelopmentOOF) -> _ValidatedOOF:
    if not isinstance(oof, CompetitivePathDevelopmentOOF):
        raise OverheatUncertaintyError("competitive_path_development_oof_required")
    if not isinstance(oof.horizon, LabelHorizon):
        raise OverheatUncertaintyError("label_horizon_invalid")
    if oof.class_order != CLASS_ORDER:
        raise OverheatUncertaintyError("class_order_mismatch")
    if oof.model_ids != MODEL_IDS or oof.candidate_model_ids != CANDIDATE_MODEL_IDS:
        raise OverheatUncertaintyError("model_contract_mismatch")
    if not _is_sha256(oof.input_dataset_sha256) or not _is_sha256(
        oof.row_mask_sha256
    ):
        raise OverheatUncertaintyError("oof_evidence_sha256_invalid")
    axis = _validated_strings(oof.frozen_session_axis, "frozen_session_axis_invalid")
    axis_index = {session: index for index, session in enumerate(axis)}
    folds = _validated_folds(oof.folds, len(axis))
    common_row_ids = _validated_strings(
        oof.common_validation_row_ids,
        "common_validation_row_ids_invalid",
        allow_empty=True,
    )
    if not common_row_ids or not oof.predictions:
        raise OverheatUncertaintyError("empty_validation_rows")
    excluded_rows = _validated_excluded_rows(
        oof.excluded_rows,
        axis_index,
        oof.horizon,
        frozenset(common_row_ids),
    )
    rows_by_model = _validated_prediction_rows(
        oof.predictions,
        axis_index,
        folds,
        oof.horizon,
        frozenset(common_row_ids),
    )
    canonical_keys = _aligned_canonical_keys(
        rows_by_model,
        common_row_ids,
        axis_index,
    )
    if oof.row_mask_sha256 != _row_mask_sha256(
        axis,
        oof.horizon,
        folds,
        canonical_keys,
        excluded_rows,
    ):
        raise OverheatUncertaintyError("row_mask_sha256_mismatch")
    validation_sessions, fold_session_segments = _validation_session_segments(
        canonical_keys,
        rows_by_model[BASELINE_MODEL_IDS[0]],
        folds,
        axis_index,
    )
    _validate_metrics(oof.metrics, rows_by_model, canonical_keys)
    return _ValidatedOOF(
        axis=axis,
        folds=folds,
        excluded_rows=excluded_rows,
        common_row_ids=common_row_ids,
        canonical_keys=canonical_keys,
        rows_by_model=rows_by_model,
        validation_sessions=validation_sessions,
        fold_session_segments=fold_session_segments,
    )


def _validated_folds(
    values: Sequence[DevelopmentFold],
    axis_length: int,
) -> tuple[DevelopmentFold, ...]:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError("development_folds_invalid")
    folds = tuple(values)
    if not folds or any(not isinstance(value, DevelopmentFold) for value in folds):
        raise OverheatUncertaintyError("development_folds_invalid")
    if any(
        type(fold.fold_id) is not str
        or not fold.fold_id
        or fold.fold_id != fold.fold_id.strip()
        or any(
            not _valid_session_interval(interval, axis_length)
            for interval in (
                fold.train,
                fold.purge,
                fold.validation,
                fold.embargo,
            )
        )
        or fold.train.start != 0
        or fold.train.stop != fold.purge.start
        or fold.purge.stop != fold.validation.start
        or fold.validation.start >= fold.validation.stop
        or fold.validation.stop != fold.embargo.start
        for fold in folds
    ) or len({fold.fold_id for fold in folds}) != len(folds):
        raise OverheatUncertaintyError("development_folds_invalid")
    ordered = tuple(sorted(folds, key=lambda value: value.validation.start))
    if ordered != folds or any(
        previous.validation.stop > current.validation.start
        or previous.embargo.stop != current.train.stop
        for previous, current in zip(folds, folds[1:])
    ):
        raise OverheatUncertaintyError("development_folds_invalid")
    return folds


def _valid_session_interval(value: object, axis_length: int) -> bool:
    return (
        isinstance(value, SessionInterval)
        and type(value.start) is int
        and type(value.stop) is int
        and 0 <= value.start <= value.stop <= axis_length
    )


def _validated_excluded_rows(
    values: Sequence[ExcludedOOFRow],
    axis_index: Mapping[str, int],
    horizon: LabelHorizon,
    common_row_ids: frozenset[str],
) -> tuple[ExcludedOOFRow, ...]:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError("excluded_rows_invalid")
    rows = tuple(values)
    if any(
        not isinstance(row, ExcludedOOFRow)
        or row.horizon is not horizon
        or row.session_id not in axis_index
        or row.row_id in common_row_ids
        or not _is_sha256(row.source_evidence_sha256)
        for row in rows
    ) or len({row.row_id for row in rows}) != len(rows):
        raise OverheatUncertaintyError("excluded_rows_invalid")
    return tuple(sorted(rows, key=lambda row: (axis_index[row.session_id], row.row_id)))


def _validated_prediction_rows(
    values: Sequence[OOFProbabilityRow],
    axis_index: Mapping[str, int],
    folds: tuple[DevelopmentFold, ...],
    horizon: LabelHorizon,
    common_row_ids: frozenset[str],
) -> dict[str, dict[tuple[str, str], OOFProbabilityRow]]:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError("prediction_rows_invalid")
    rows = tuple(values)
    fold_by_id = {fold.fold_id: fold for fold in folds}
    by_model: dict[str, dict[tuple[str, str], OOFProbabilityRow]] = {
        model_id: {} for model_id in MODEL_IDS
    }
    for row in rows:
        _validate_prediction_row(
            row,
            axis_index,
            fold_by_id,
            horizon,
            common_row_ids,
        )
        key = (row.fold_id, row.row_id)
        model_rows = by_model[row.model_id]
        if key in model_rows:
            raise OverheatUncertaintyError("prediction_identity_mismatch")
        model_rows[key] = row
    expected_row_ids = set(common_row_ids)
    if any(
        {row.row_id for row in model_rows.values()} != expected_row_ids
        for model_rows in by_model.values()
    ):
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    return by_model


def _validate_prediction_row(
    row: OOFProbabilityRow,
    axis_index: Mapping[str, int],
    fold_by_id: Mapping[str, DevelopmentFold],
    horizon: LabelHorizon,
    common_row_ids: frozenset[str],
) -> None:
    if not isinstance(row, OOFProbabilityRow) or row.model_id not in MODEL_IDS:
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    identity_values = (row.fold_id, row.row_id, row.symbol, row.session_id)
    if any(
        type(value) is not str or not value or value != value.strip()
        for value in identity_values
    ):
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    fold = fold_by_id.get(row.fold_id)
    if (
        fold is None
        or row.row_id not in common_row_ids
        or row.session_id not in axis_index
        or not fold.validation.start
        <= axis_index[row.session_id]
        < fold.validation.stop
    ):
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    if (
        not isinstance(row.label, CompetitivePathLabel)
        or row.label not in CLASS_ORDER
        or row.label is CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE
    ):
        raise OverheatUncertaintyError("prediction_label_invalid")
    if not _is_sha256(row.source_evidence_sha256):
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    _validate_probability_vector(row.probabilities)
    if not isinstance(horizon, LabelHorizon):
        raise OverheatUncertaintyError("label_horizon_invalid")


def _aligned_canonical_keys(
    rows_by_model: Mapping[str, Mapping[tuple[str, str], OOFProbabilityRow]],
    common_row_ids: tuple[str, ...],
    axis_index: Mapping[str, int],
) -> tuple[tuple[str, str], ...]:
    reference = rows_by_model[BASELINE_MODEL_IDS[0]]
    reference_keys = set(reference)
    for candidate_model_id in CANDIDATE_MODEL_IDS:
        for baseline_model_id in BASELINE_MODEL_IDS:
            candidate = rows_by_model[candidate_model_id]
            baseline = rows_by_model[baseline_model_id]
            if set(candidate) != set(baseline):
                raise OverheatUncertaintyError("prediction_identity_mismatch")
            for key in reference_keys:
                candidate_row = candidate[key]
                baseline_row = baseline[key]
                if candidate_row.label is not baseline_row.label:
                    raise OverheatUncertaintyError("prediction_label_mismatch")
                if _identity(candidate_row) != _identity(baseline_row):
                    raise OverheatUncertaintyError("prediction_identity_mismatch")
    canonical_keys = tuple(
        sorted(
            reference_keys,
            key=lambda key: (
                axis_index[reference[key].session_id],
                reference[key].row_id,
            ),
        )
    )
    if tuple(reference[key].row_id for key in canonical_keys) != common_row_ids:
        raise OverheatUncertaintyError("common_validation_row_ids_mismatch")
    return canonical_keys


def _validation_session_segments(
    canonical_keys: tuple[tuple[str, str], ...],
    reference: Mapping[tuple[str, str], OOFProbabilityRow],
    folds: tuple[DevelopmentFold, ...],
    axis_index: Mapping[str, int],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    fold_sessions = {
        fold.fold_id: {
            reference[key].session_id
            for key in canonical_keys
            if reference[key].fold_id == fold.fold_id
        }
        for fold in folds
    }
    segments = tuple(
        tuple(sorted(fold_sessions[fold.fold_id], key=axis_index.__getitem__))
        for fold in folds
    )
    if any(not segment for segment in segments):
        raise OverheatUncertaintyError("empty_validation_fold_sessions")
    if any(len(segment) < BLOCK_LENGTH_SESSIONS for segment in segments):
        raise OverheatUncertaintyError("insufficient_validation_sessions")
    sessions = tuple(
        sorted(
            {session for segment in segments for session in segment},
            key=axis_index.__getitem__,
        )
    )
    if sum(len(segment) for segment in segments) != len(sessions):
        raise OverheatUncertaintyError("prediction_identity_mismatch")
    return sessions, segments


def _validate_metrics(
    values: Sequence[OOFMetrics],
    rows_by_model: Mapping[str, Mapping[tuple[str, str], OOFProbabilityRow]],
    canonical_keys: tuple[tuple[str, str], ...],
) -> None:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError("oof_metrics_invalid")
    metrics = tuple(values)
    if (
        len(metrics) != len(MODEL_IDS)
        or any(not isinstance(metric, OOFMetrics) for metric in metrics)
        or tuple(metric.model_id for metric in metrics) != MODEL_IDS
    ):
        raise OverheatUncertaintyError("oof_metrics_invalid")
    for metric in metrics:
        rows = tuple(rows_by_model[metric.model_id][key] for key in canonical_keys)
        recomputed = multiclass_brier_score(
            tuple(row.label for row in rows),
            tuple(row.probabilities for row in rows),
            CLASS_ORDER,
        )
        if (
            type(metric.row_count) is not int
            or metric.row_count != len(rows)
            or not _finite(metric.multiclass_brier)
            or not _finite(metric.log_loss)
            or not _probability(metric.top_class_ece)
            or not math.isclose(
                metric.multiclass_brier,
                recomputed,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise OverheatUncertaintyError("oof_metric_probability_mismatch")


def _session_improvements(
    oof: CompetitivePathDevelopmentOOF,
    validated: _ValidatedOOF,
) -> dict[tuple[str, str], tuple[float, ...]]:
    class_index = {label: index for index, label in enumerate(oof.class_order)}
    result: dict[tuple[str, str], tuple[float, ...]] = {}
    for candidate_model_id in CANDIDATE_MODEL_IDS:
        for baseline_model_id in BASELINE_MODEL_IDS:
            grouped = {session_id: [] for session_id in validated.validation_sessions}
            for key in validated.canonical_keys:
                candidate = validated.rows_by_model[candidate_model_id][key]
                baseline = validated.rows_by_model[baseline_model_id][key]
                target_index = class_index[candidate.label]
                improvement = _brier_loss(
                    baseline.probabilities,
                    target_index,
                ) - _brier_loss(candidate.probabilities, target_index)
                grouped[candidate.session_id].append(improvement)
            result[(candidate_model_id, baseline_model_id)] = tuple(
                statistics.fmean(grouped[session_id])
                for session_id in validated.validation_sessions
            )
    return result


def _bootstrap_distributions(
    session_improvements: Mapping[tuple[str, str], tuple[float, ...]],
    validated: _ValidatedOOF,
    *,
    seed: int,
    replicates: int,
    block_length_sessions: int,
) -> dict[tuple[str, str], tuple[float, ...]]:
    session_index = {
        session_id: index
        for index, session_id in enumerate(validated.validation_sessions)
    }
    generator = _SplitMix64(seed)
    distributions: dict[tuple[str, str], list[float]] = {
        key: [] for key in session_improvements
    }
    for _replicate in range(replicates):
        sampled_indices = tuple(
            session_index[segment[index]]
            for segment in validated.fold_session_segments
            for index in _draw_circular_session_indices(
                session_count=len(segment),
                block_length_sessions=block_length_sessions,
                generator=generator,
            )
        )
        for key, improvements in session_improvements.items():
            distributions[key].append(
                statistics.fmean(improvements[index] for index in sampled_indices)
            )
    return {key: tuple(values) for key, values in distributions.items()}


def _draw_circular_session_indices(
    *,
    session_count: int,
    block_length_sessions: int,
    generator: _RandomRange,
) -> tuple[int, ...]:
    if (
        type(session_count) is not int
        or session_count < block_length_sessions
        or type(block_length_sessions) is not int
        or block_length_sessions <= 0
    ):
        raise OverheatUncertaintyError("circular_block_input_invalid")
    sampled: list[int] = []
    while len(sampled) < session_count:
        start = generator.randrange(session_count)
        sampled.extend(
            (start + offset) % session_count
            for offset in range(block_length_sessions)
        )
    return tuple(sampled[:session_count])


def _build_comparisons(
    session_improvements: Mapping[tuple[str, str], tuple[float, ...]],
    distributions: Mapping[tuple[str, str], tuple[float, ...]],
    *,
    row_count: int,
    contract: OverheatUncertaintyContract,
) -> tuple[OverheatUncertaintyComparison, ...]:
    comparisons: list[OverheatUncertaintyComparison] = []
    for candidate_model_id in CANDIDATE_MODEL_IDS:
        for baseline_model_id in BASELINE_MODEL_IDS:
            key = (candidate_model_id, baseline_model_id)
            session_values = session_improvements[key]
            distribution = distributions[key]
            lower_bound = _type7_quantile(
                distribution,
                contract.per_comparison_alpha,
            )
            comparisons.append(
                OverheatUncertaintyComparison(
                    candidate_model_id=candidate_model_id,
                    baseline_model_id=baseline_model_id,
                    observed_improvement=statistics.fmean(session_values),
                    adjusted_lower_bound=lower_bound,
                    bootstrap_probability_above_delta=(
                        sum(
                            value > contract.minimum_effect_delta
                            for value in distribution
                        )
                        / len(distribution)
                    ),
                    session_count=len(session_values),
                    row_count=row_count,
                    replicate_distribution_sha256=_distribution_sha256(
                        candidate_model_id,
                        baseline_model_id,
                        distribution,
                        contract,
                    ),
                    passed=lower_bound > contract.minimum_effect_delta,
                )
            )
    return tuple(comparisons)


def _build_candidate_decisions(
    comparisons: tuple[OverheatUncertaintyComparison, ...],
) -> tuple[OverheatCandidateUncertainty, ...]:
    results: list[OverheatCandidateUncertainty] = []
    for candidate_model_id in CANDIDATE_MODEL_IDS:
        candidate_comparisons = tuple(
            value
            for value in comparisons
            if value.candidate_model_id == candidate_model_id
        )
        failed = tuple(value for value in candidate_comparisons if not value.passed)
        reasons = (
            tuple(
                CandidateDecisionReason(
                    code=(
                        CandidateDecisionReasonCode.ADJUSTED_LOWER_BOUND_NOT_ABOVE_DELTA
                    ),
                    baseline_model_id=value.baseline_model_id,
                )
                for value in failed
            )
            if failed
            else (
                CandidateDecisionReason(
                    code=(
                        CandidateDecisionReasonCode.PASSED_BOTH_PREDECLARED_BASELINES
                    ),
                    baseline_model_id=None,
                ),
            )
        )
        results.append(
            OverheatCandidateUncertainty(
                candidate_model_id=candidate_model_id,
                comparisons=candidate_comparisons,
                passed=not failed,
                reasons=reasons,
            )
        )
    return tuple(results)


def _distribution_sha256(
    candidate_model_id: str,
    baseline_model_id: str,
    distribution: tuple[float, ...],
    contract: OverheatUncertaintyContract,
) -> str:
    return _canonical_sha256(
        {
            "schemaVersion": "rp001-s2-overheat-bootstrap-distribution.v1",
            "candidateModelId": candidate_model_id,
            "baselineModelId": baseline_model_id,
            "method": contract.bootstrap_method.value,
            "prngMethod": contract.prng_method,
            "seed": contract.seed,
            "replicates": contract.replicates,
            "blockLengthSessions": contract.block_length_sessions,
            "valuesHex": tuple(float(value).hex() for value in distribution),
        }
    )


def _excluded_rows_sha256(rows: tuple[ExcludedOOFRow, ...]) -> str:
    return _canonical_sha256(
        {
            "schemaVersion": "rp001-s2-overheat-uncertainty-exclusions.v1",
            "rows": tuple(_excluded_row_body(row) for row in rows),
        }
    )


def _validation_evidence_sha256(
    oof: CompetitivePathDevelopmentOOF,
    validated: _ValidatedOOF,
) -> str:
    return _canonical_sha256(
        {
            "schemaVersion": "rp001-s2-overheat-uncertainty-validation.v1",
            "horizon": oof.horizon.value,
            "classOrder": tuple(label.value for label in oof.class_order),
            "modelIds": oof.model_ids,
            "candidateModelIds": oof.candidate_model_ids,
            "baselineModelIds": BASELINE_MODEL_IDS,
            "frozenSessionAxis": validated.axis,
            "folds": tuple(_fold_body(fold) for fold in validated.folds),
            "commonValidationRowIds": validated.common_row_ids,
            "rows": tuple(
                {
                    "identity": _prediction_identity_body(
                        validated.rows_by_model[BASELINE_MODEL_IDS[0]][key]
                    ),
                    "modelProbabilitiesHex": tuple(
                        (
                            model_id,
                            tuple(
                                float(value).hex()
                                for value in validated.rows_by_model[model_id][
                                    key
                                ].probabilities
                            ),
                        )
                        for model_id in MODEL_IDS
                    ),
                }
                for key in validated.canonical_keys
            ),
        }
    )


def _result_sha256(
    oof: CompetitivePathDevelopmentOOF,
    validated: _ValidatedOOF,
    contract: OverheatUncertaintyContract,
    excluded_rows_sha256: str,
    validation_evidence_sha256: str,
    comparisons: tuple[OverheatUncertaintyComparison, ...],
    candidates: tuple[OverheatCandidateUncertainty, ...],
) -> str:
    return _canonical_sha256(
        {
            "schemaVersion": "rp001-s2-overheat-uncertainty-result.v1",
            "status": (
                ExploratoryEvidenceStatus.EXPLORATORY_FOLLOWUP_NOT_ADOPTION_EVIDENCE.value
            ),
            "resultTuningPerformed": False,
            "inputDatasetSha256": oof.input_dataset_sha256,
            "rowMaskSha256": oof.row_mask_sha256,
            "horizon": oof.horizon.value,
            "classOrder": tuple(label.value for label in oof.class_order),
            "modelIds": oof.model_ids,
            "baselineModelIds": BASELINE_MODEL_IDS,
            "candidateModelIds": oof.candidate_model_ids,
            "frozenSessionAxis": validated.axis,
            "validationSessionIds": validated.validation_sessions,
            "folds": tuple(_fold_body(fold) for fold in validated.folds),
            "commonValidationRowIds": validated.common_row_ids,
            "excludedRows": tuple(
                _excluded_row_body(row) for row in validated.excluded_rows
            ),
            "excludedRowsSha256": excluded_rows_sha256,
            "validationEvidenceSha256": validation_evidence_sha256,
            "contract": _contract_body(contract),
            "comparisons": tuple(
                _comparison_body(value) for value in comparisons
            ),
            "candidates": tuple(_candidate_body(value) for value in candidates),
        }
    )


def _contract_body(contract: OverheatUncertaintyContract) -> dict[str, object]:
    return {
        "primaryLoss": contract.primary_loss.value,
        "inferenceUnit": contract.inference_unit.value,
        "bootstrapMethod": contract.bootstrap_method.value,
        "prngMethod": contract.prng_method,
        "seed": contract.seed,
        "replicates": contract.replicates,
        "blockLengthSessions": contract.block_length_sessions,
        "globalFamilywiseComparisonCount": (
            contract.global_familywise_comparison_count
        ),
        "familywiseAlphaHex": float(contract.familywise_alpha).hex(),
        "perComparisonAlphaHex": float(contract.per_comparison_alpha).hex(),
        "minimumEffectDeltaHex": float(contract.minimum_effect_delta).hex(),
    }


def _comparison_body(
    comparison: OverheatUncertaintyComparison,
) -> dict[str, object]:
    return {
        "candidateModelId": comparison.candidate_model_id,
        "baselineModelId": comparison.baseline_model_id,
        "observedImprovementHex": float(comparison.observed_improvement).hex(),
        "adjustedLowerBoundHex": float(comparison.adjusted_lower_bound).hex(),
        "bootstrapProbabilityAboveDeltaHex": float(
            comparison.bootstrap_probability_above_delta
        ).hex(),
        "sessionCount": comparison.session_count,
        "rowCount": comparison.row_count,
        "replicateDistributionSha256": comparison.replicate_distribution_sha256,
        "passed": comparison.passed,
    }


def _candidate_body(candidate: OverheatCandidateUncertainty) -> dict[str, object]:
    return {
        "candidateModelId": candidate.candidate_model_id,
        "passed": candidate.passed,
        "reasons": tuple(
            {
                "code": reason.code.value,
                "baselineModelId": reason.baseline_model_id,
            }
            for reason in candidate.reasons
        ),
    }


def _fold_body(fold: DevelopmentFold) -> dict[str, object]:
    return {
        "foldId": fold.fold_id,
        "train": (fold.train.start, fold.train.stop),
        "purge": (fold.purge.start, fold.purge.stop),
        "validation": (fold.validation.start, fold.validation.stop),
        "embargo": (fold.embargo.start, fold.embargo.stop),
    }


def _excluded_row_body(row: ExcludedOOFRow) -> dict[str, str]:
    return {
        "rowId": row.row_id,
        "symbol": row.symbol,
        "sessionId": row.session_id,
        "horizon": row.horizon.value,
        "label": row.label.value,
        "reason": row.reason,
        "sourceEvidenceSha256": row.source_evidence_sha256,
    }


def _prediction_identity_body(row: OOFProbabilityRow) -> dict[str, str]:
    return {
        "foldId": row.fold_id,
        "rowId": row.row_id,
        "symbol": row.symbol,
        "sessionId": row.session_id,
        "label": row.label.value,
        "sourceEvidenceSha256": row.source_evidence_sha256,
    }


def _identity(row: OOFProbabilityRow) -> tuple[str, str, str, str, str, str]:
    return (
        row.fold_id,
        row.row_id,
        row.symbol,
        row.session_id,
        row.label.value,
        row.source_evidence_sha256,
    )


def _brier_loss(probabilities: Sequence[float], target_index: int) -> float:
    return sum(
        (float(probability) - float(index == target_index)) ** 2
        for index, probability in enumerate(probabilities)
    )


def _type7_quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered or not _probability(probability):
        raise OverheatUncertaintyError("quantile_input_invalid")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _validated_strings(
    values: Sequence[str],
    code: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError(code)
    normalized = tuple(values)
    if (
        not normalized and not allow_empty
        or any(
            type(value) is not str or not value or value != value.strip()
            for value in normalized
        )
        or len(set(normalized)) != len(normalized)
    ):
        raise OverheatUncertaintyError(code)
    return normalized


def _validate_probability_vector(values: Sequence[float]) -> None:
    if isinstance(values, (str, bytes)):
        raise OverheatUncertaintyError("probability_vector_invalid")
    probabilities = tuple(values)
    if (
        len(probabilities) != len(CLASS_ORDER)
        or any(
            not _finite(value) or float(value) < 0.0 or float(value) > 1.0
            for value in probabilities
        )
        or not math.isclose(
            sum(float(value) for value in probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise OverheatUncertaintyError("probability_vector_invalid")


def _canonical_sha256(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _probability(value: object) -> bool:
    return _finite(value) and 0.0 <= float(value) <= 1.0


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
