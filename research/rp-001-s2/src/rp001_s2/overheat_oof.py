"""Frozen development OOF evaluation for direction-neutral competitive paths."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from rp001_s2.direction_neutral_overheat import CompetitivePathLabel, LabelHorizon


FAMILY_NAMES = (
    "absolute_gap",
    "absolute_market_residual_return",
    "intrabar_log_range",
    "realized_volatility_5m",
    "same_minute_volume",
)
CLASS_ORDER = tuple(
    label
    for label in CompetitivePathLabel
    if label is not CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE
)
MODEL_IDS = (
    "b1_jeffreys_unconditional",
    "b2_signed_return_sign",
    "c1_screen_breadth",
    "c2_family_flags",
    "c3_flags_signed_return_range",
)
CANDIDATE_MODEL_IDS = MODEL_IDS[2:]

_MINIMUM_TRAINING_SESSIONS = 60
_VALIDATION_SESSIONS = 20
_PURGE_SESSIONS = 1
_EMBARGO_SESSIONS = 1
_MINIMUM_FOLDS = 3
_B2_SHRINKAGE = 6.0
_SOFTMAX_ITERATIONS = 400
_SOFTMAX_LEARNING_RATE = 0.05
_SOFTMAX_L2 = 0.1
_ECE_BINS = 10
_PROBABILITY_FLOOR = 1e-15
_FIXED_SEED = 20260711

Predictor = Callable[["CompetitivePathExample"], tuple[float, ...]]


@dataclass(frozen=True)
class FamilyThresholdFlags:
    exceeds_p99: bool
    exceeds_p999: bool

    def __post_init__(self) -> None:
        if (
            type(self.exceeds_p99) is not bool
            or type(self.exceeds_p999) is not bool
            or self.exceeds_p999 and not self.exceeds_p99
        ):
            raise ValueError("family_flags_invalid")


@dataclass(frozen=True)
class CompetitivePathExample:
    row_id: str
    symbol: str
    session_id: str
    sample_role: str
    horizon: LabelHorizon
    label: CompetitivePathLabel
    family_flags: Mapping[str, FamilyThresholdFlags]
    signed_return: float
    intrabar_log_range: float
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        for value in (self.row_id, self.symbol, self.session_id):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError("example_identity_invalid")
        if self.sample_role != "development":
            raise ValueError("development_sample_role_required")
        if not isinstance(self.horizon, LabelHorizon):
            raise ValueError("label_horizon_invalid")
        if not isinstance(self.label, CompetitivePathLabel):
            raise ValueError("competitive_path_label_invalid")
        if not isinstance(self.family_flags, Mapping):
            raise ValueError("family_flags_invalid")
        normalized = dict(self.family_flags)
        if set(normalized) != set(FAMILY_NAMES) or any(
            not isinstance(value, FamilyThresholdFlags)
            for value in normalized.values()
        ):
            raise ValueError("family_flags_invalid")
        if not _finite(self.signed_return) or not _finite(
            self.intrabar_log_range
        ) or float(self.intrabar_log_range) < 0.0:
            raise ValueError("example_feature_invalid")
        if not _is_sha256(self.source_evidence_sha256):
            raise ValueError("source_evidence_sha256_invalid")
        object.__setattr__(
            self,
            "family_flags",
            MappingProxyType(
                {family: normalized[family] for family in FAMILY_NAMES}
            ),
        )


@dataclass(frozen=True)
class SessionInterval:
    start: int
    stop: int

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.stop) is not int
            or self.start < 0
            or self.stop < self.start
        ):
            raise ValueError("session_interval_invalid")


@dataclass(frozen=True)
class DevelopmentFold:
    fold_id: str
    train: SessionInterval
    purge: SessionInterval
    validation: SessionInterval
    embargo: SessionInterval


@dataclass(frozen=True)
class ExcludedOOFRow:
    row_id: str
    symbol: str
    session_id: str
    horizon: LabelHorizon
    label: CompetitivePathLabel
    reason: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        for value in (self.row_id, self.symbol, self.session_id, self.reason):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError("excluded_oof_identity_invalid")
        if not isinstance(self.horizon, LabelHorizon):
            raise ValueError("label_horizon_invalid")
        if not isinstance(self.label, CompetitivePathLabel):
            raise ValueError("competitive_path_label_invalid")
        if not _is_sha256(self.source_evidence_sha256):
            raise ValueError("source_evidence_sha256_invalid")


@dataclass(frozen=True)
class OOFProbabilityRow:
    model_id: str
    fold_id: str
    row_id: str
    symbol: str
    session_id: str
    label: CompetitivePathLabel
    source_evidence_sha256: str
    probabilities: tuple[float, ...]


@dataclass(frozen=True)
class OOFMetrics:
    model_id: str
    row_count: int
    multiclass_brier: float
    log_loss: float
    top_class_ece: float


@dataclass(frozen=True)
class OOFHyperparameters:
    seed: int = _FIXED_SEED
    softmax_initialization: str = "all_zero"
    randomness: str = "none"
    b2_shrinkage: float = _B2_SHRINKAGE
    softmax_iterations: int = _SOFTMAX_ITERATIONS
    softmax_learning_rate: float = _SOFTMAX_LEARNING_RATE
    softmax_l2: float = _SOFTMAX_L2
    ece_bins: int = _ECE_BINS


@dataclass(frozen=True)
class CompetitivePathDevelopmentOOF:
    horizon: LabelHorizon
    class_order: tuple[CompetitivePathLabel, ...]
    model_ids: tuple[str, ...]
    candidate_model_ids: tuple[str, ...]
    frozen_session_axis: tuple[str, ...]
    folds: tuple[DevelopmentFold, ...]
    excluded_rows: tuple[ExcludedOOFRow, ...]
    common_validation_row_ids: tuple[str, ...]
    row_mask_sha256: str
    input_dataset_sha256: str
    predictions: tuple[OOFProbabilityRow, ...]
    metrics: tuple[OOFMetrics, ...]
    hyperparameters: OOFHyperparameters


@dataclass(frozen=True)
class _Scale:
    mean: float
    standard_deviation: float

    def transform(self, value: float) -> float:
        return (value - self.mean) / self.standard_deviation


@dataclass(frozen=True)
class _C3Scaling:
    signed_return: _Scale
    intrabar_log_range: _Scale


@dataclass(frozen=True)
class _SoftmaxModel:
    weights: tuple[tuple[float, ...], ...]

    def predict(self, features: tuple[float, ...]) -> tuple[float, ...]:
        vector = (1.0,) + features
        if any(len(row) != len(vector) for row in self.weights):
            raise ValueError("softmax_feature_dimension_mismatch")
        scores = tuple(
            sum(weight * value for weight, value in zip(row, vector, strict=True))
            for row in self.weights
        )
        return _softmax(scores)


def run_competitive_path_development_oof(
    examples: Sequence[CompetitivePathExample],
    *,
    frozen_session_axis: Sequence[str],
    horizon: LabelHorizon,
    upstream_exclusions: Sequence[ExcludedOOFRow],
) -> CompetitivePathDevelopmentOOF:
    """Evaluate two baselines and three fixed candidates on one OOF row mask."""
    if not isinstance(horizon, LabelHorizon):
        raise ValueError("label_horizon_invalid")
    axis = _validate_session_axis(frozen_session_axis)
    axis_index = {session_id: index for index, session_id in enumerate(axis)}
    rows = _validate_and_order_examples(tuple(examples), axis_index, horizon)
    upstream = _validate_upstream_exclusions(
        upstream_exclusions,
        rows,
        axis_index,
        horizon,
    )
    folds = _build_folds(len(axis))
    if len(folds) < _MINIMUM_FOLDS:
        raise ValueError("insufficient_development_folds")

    censored = tuple(
        ExcludedOOFRow(
            row_id=row.row_id,
            symbol=row.symbol,
            session_id=row.session_id,
            horizon=row.horizon,
            label=row.label,
            reason="censored_or_not_identifiable",
            source_evidence_sha256=row.source_evidence_sha256,
        )
        for row in rows
        if row.label is CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE
    )
    excluded = tuple(
        sorted(
            upstream + censored,
            key=lambda row: (axis_index[row.session_id], row.row_id),
        )
    )
    eligible = tuple(
        row
        for row in rows
        if row.label is not CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE
    )
    predictions: list[OOFProbabilityRow] = []
    common_row_ids: list[str] = []
    for fold in folds:
        training = _rows_in(eligible, fold.train, axis_index)
        validation = _rows_in(eligible, fold.validation, axis_index)
        if not training or not validation:
            raise ValueError("empty_development_fold_rows")
        common_row_ids.extend(row.row_id for row in validation)
        predictors = _fit_fold_predictors(training)
        for model_id in MODEL_IDS:
            predictor = predictors[model_id]
            for row in validation:
                probabilities = predictor(row)
                _validate_probability_vector(probabilities, len(CLASS_ORDER))
                predictions.append(
                    OOFProbabilityRow(
                        model_id=model_id,
                        fold_id=fold.fold_id,
                        row_id=row.row_id,
                        symbol=row.symbol,
                        session_id=row.session_id,
                        label=row.label,
                        source_evidence_sha256=row.source_evidence_sha256,
                        probabilities=probabilities,
                    )
                )

    prediction_tuple = tuple(predictions)
    common_identity = _validate_common_prediction_identity(prediction_tuple)
    if tuple(common_row_ids) != tuple(row_id for _fold_id, row_id in common_identity):
        raise ValueError("common_row_identity_mismatch")
    metrics = tuple(
        _metrics_for(model_id, prediction_tuple) for model_id in MODEL_IDS
    )
    return CompetitivePathDevelopmentOOF(
        horizon=horizon,
        class_order=CLASS_ORDER,
        model_ids=MODEL_IDS,
        candidate_model_ids=CANDIDATE_MODEL_IDS,
        frozen_session_axis=axis,
        folds=folds,
        excluded_rows=excluded,
        common_validation_row_ids=tuple(common_row_ids),
        row_mask_sha256=_row_mask_sha256(
            axis,
            horizon,
            folds,
            common_identity,
            excluded,
        ),
        input_dataset_sha256=_input_dataset_sha256(
            axis,
            horizon,
            rows,
            excluded,
        ),
        predictions=prediction_tuple,
        metrics=metrics,
        hyperparameters=OOFHyperparameters(),
    )


def multiclass_brier_score(
    labels: Sequence[CompetitivePathLabel],
    probabilities: Sequence[Sequence[float]],
    class_order: Sequence[CompetitivePathLabel] = CLASS_ORDER,
) -> float:
    truth, rows, classes = _validate_metric_inputs(labels, probabilities, class_order)
    class_index = {label: index for index, label in enumerate(classes)}
    total = 0.0
    for label, probability_row in zip(truth, rows, strict=True):
        target = class_index[label]
        total += sum(
            (probability - (1.0 if index == target else 0.0)) ** 2
            for index, probability in enumerate(probability_row)
        )
    return total / len(truth)


def multiclass_log_loss(
    labels: Sequence[CompetitivePathLabel],
    probabilities: Sequence[Sequence[float]],
    class_order: Sequence[CompetitivePathLabel] = CLASS_ORDER,
) -> float:
    truth, rows, classes = _validate_metric_inputs(labels, probabilities, class_order)
    class_index = {label: index for index, label in enumerate(classes)}
    return -sum(
        math.log(max(probability_row[class_index[label]], _PROBABILITY_FLOOR))
        for label, probability_row in zip(truth, rows, strict=True)
    ) / len(truth)


def top_class_ece(
    labels: Sequence[CompetitivePathLabel],
    probabilities: Sequence[Sequence[float]],
    class_order: Sequence[CompetitivePathLabel] = CLASS_ORDER,
    *,
    bin_count: int = _ECE_BINS,
) -> float:
    truth, rows, classes = _validate_metric_inputs(labels, probabilities, class_order)
    if type(bin_count) is not int or bin_count <= 0:
        raise ValueError("ece_bin_count_invalid")
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for label, probability_row in zip(truth, rows, strict=True):
        predicted_index = max(range(len(classes)), key=lambda index: probability_row[index])
        confidence = probability_row[predicted_index]
        bin_index = min(int(confidence * bin_count), bin_count - 1)
        bins[bin_index].append((confidence, classes[predicted_index] is label))
    total = 0.0
    for values in bins:
        if not values:
            continue
        average_confidence = sum(value[0] for value in values) / len(values)
        accuracy = sum(value[1] for value in values) / len(values)
        total += len(values) / len(truth) * abs(average_confidence - accuracy)
    return total


def _fit_fold_predictors(
    training: tuple[CompetitivePathExample, ...],
) -> Mapping[str, Predictor]:
    unconditional = _jeffreys_distribution(training)
    sign_distributions = _signed_return_distributions(training, unconditional)
    c3_scaling = _fit_c3_scaling(training)
    c1_model = _fit_softmax(training, "c1_screen_breadth", None)
    c2_model = _fit_softmax(training, "c2_family_flags", None)
    c3_model = _fit_softmax(training, "c3_flags_signed_return_range", c3_scaling)

    def b1(_row: CompetitivePathExample) -> tuple[float, ...]:
        return unconditional

    def b2(row: CompetitivePathExample) -> tuple[float, ...]:
        return sign_distributions[_sign_bucket(row.signed_return)]

    def c1(row: CompetitivePathExample) -> tuple[float, ...]:
        return c1_model.predict(_candidate_features("c1_screen_breadth", row, None))

    def c2(row: CompetitivePathExample) -> tuple[float, ...]:
        return c2_model.predict(_candidate_features("c2_family_flags", row, None))

    def c3(row: CompetitivePathExample) -> tuple[float, ...]:
        return c3_model.predict(
            _candidate_features("c3_flags_signed_return_range", row, c3_scaling)
        )

    return MappingProxyType(
        {
            MODEL_IDS[0]: b1,
            MODEL_IDS[1]: b2,
            MODEL_IDS[2]: c1,
            MODEL_IDS[3]: c2,
            MODEL_IDS[4]: c3,
        }
    )


def _fit_softmax(
    training: tuple[CompetitivePathExample, ...],
    model_id: str,
    scaling: _C3Scaling | None,
) -> _SoftmaxModel:
    features = tuple(
        _candidate_features(model_id, row, scaling) for row in training
    )
    outcomes = tuple(CLASS_ORDER.index(row.label) for row in training)
    dimension = len(features[0]) + 1
    weights = [[0.0] * dimension for _ in CLASS_ORDER]
    row_count = float(len(training))
    for _iteration in range(_SOFTMAX_ITERATIONS):
        gradients = [[0.0] * dimension for _ in CLASS_ORDER]
        for feature_row, outcome in zip(features, outcomes, strict=True):
            vector = (1.0,) + feature_row
            probabilities = _softmax(
                tuple(
                    sum(
                        weight * value
                        for weight, value in zip(class_weights, vector, strict=True)
                    )
                    for class_weights in weights
                )
            )
            for class_index, probability in enumerate(probabilities):
                error = probability - (1.0 if class_index == outcome else 0.0)
                for feature_index, value in enumerate(vector):
                    gradients[class_index][feature_index] += error * value / row_count
        for class_index, class_weights in enumerate(weights):
            for feature_index in range(dimension):
                penalty = (
                    0.0
                    if feature_index == 0
                    else _SOFTMAX_L2 * class_weights[feature_index]
                )
                class_weights[feature_index] -= _SOFTMAX_LEARNING_RATE * (
                    gradients[class_index][feature_index] + penalty
                )
    return _SoftmaxModel(tuple(tuple(row) for row in weights))


def _candidate_features(
    model_id: str,
    row: CompetitivePathExample,
    scaling: _C3Scaling | None,
) -> tuple[float, ...]:
    p99_count = float(
        sum(row.family_flags[family].exceeds_p99 for family in FAMILY_NAMES)
    )
    p999_count = float(
        sum(row.family_flags[family].exceeds_p999 for family in FAMILY_NAMES)
    )
    if model_id == "c1_screen_breadth":
        return (p99_count, p999_count)
    flags = tuple(
        value
        for family in FAMILY_NAMES
        for value in (
            float(row.family_flags[family].exceeds_p99),
            float(row.family_flags[family].exceeds_p999),
        )
    )
    if model_id == "c2_family_flags":
        return flags
    if model_id == "c3_flags_signed_return_range" and scaling is not None:
        return flags + (
            scaling.signed_return.transform(row.signed_return),
            scaling.intrabar_log_range.transform(row.intrabar_log_range),
        )
    raise ValueError("candidate_model_invalid")


def _fit_c3_scaling(
    training: tuple[CompetitivePathExample, ...],
) -> _C3Scaling:
    return _C3Scaling(
        signed_return=_fit_scale(tuple(row.signed_return for row in training)),
        intrabar_log_range=_fit_scale(
            tuple(row.intrabar_log_range for row in training)
        ),
    )


def _fit_scale(values: tuple[float, ...]) -> _Scale:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    standard_deviation = math.sqrt(variance)
    return _Scale(mean, standard_deviation if standard_deviation > 1e-12 else 1.0)


def _jeffreys_distribution(
    training: tuple[CompetitivePathExample, ...],
) -> tuple[float, ...]:
    counts = [0] * len(CLASS_ORDER)
    for row in training:
        counts[CLASS_ORDER.index(row.label)] += 1
    denominator = len(training) + 0.5 * len(CLASS_ORDER)
    return tuple((count + 0.5) / denominator for count in counts)


def _signed_return_distributions(
    training: tuple[CompetitivePathExample, ...],
    unconditional: tuple[float, ...],
) -> Mapping[int, tuple[float, ...]]:
    counts = {bucket: [0] * len(CLASS_ORDER) for bucket in (-1, 0, 1)}
    totals = {bucket: 0 for bucket in (-1, 0, 1)}
    for row in training:
        bucket = _sign_bucket(row.signed_return)
        counts[bucket][CLASS_ORDER.index(row.label)] += 1
        totals[bucket] += 1
    return MappingProxyType(
        {
            bucket: tuple(
                (counts[bucket][index] + _B2_SHRINKAGE * unconditional[index])
                / (totals[bucket] + _B2_SHRINKAGE)
                for index in range(len(CLASS_ORDER))
            )
            for bucket in (-1, 0, 1)
        }
    )


def _sign_bucket(value: float) -> int:
    return -1 if value < 0.0 else 1 if value > 0.0 else 0


def _softmax(scores: tuple[float, ...]) -> tuple[float, ...]:
    maximum = max(scores)
    exponentials = tuple(math.exp(score - maximum) for score in scores)
    denominator = sum(exponentials)
    raw = tuple(value / denominator for value in exponentials)
    floored = tuple(max(value, _PROBABILITY_FLOOR) for value in raw)
    total = sum(floored)
    return tuple(value / total for value in floored)


def _build_folds(session_count: int) -> tuple[DevelopmentFold, ...]:
    folds: list[DevelopmentFold] = []
    train_stop = _MINIMUM_TRAINING_SESSIONS
    while True:
        purge = SessionInterval(train_stop, train_stop + _PURGE_SESSIONS)
        validation = SessionInterval(
            purge.stop,
            purge.stop + _VALIDATION_SESSIONS,
        )
        embargo = SessionInterval(
            validation.stop,
            validation.stop + _EMBARGO_SESSIONS,
        )
        if embargo.stop > session_count:
            break
        folds.append(
            DevelopmentFold(
                fold_id=f"development_{len(folds) + 1:02d}",
                train=SessionInterval(0, train_stop),
                purge=purge,
                validation=validation,
                embargo=embargo,
            )
        )
        train_stop = embargo.stop
    return tuple(folds)


def _validate_session_axis(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("frozen_session_axis_invalid")
    axis = tuple(values)
    if not axis or any(
        type(value) is not str or not value or value != value.strip()
        for value in axis
    ) or len(set(axis)) != len(axis):
        raise ValueError("frozen_session_axis_invalid")
    return axis


def _validate_and_order_examples(
    rows: tuple[CompetitivePathExample, ...],
    axis_index: Mapping[str, int],
    horizon: LabelHorizon,
) -> tuple[CompetitivePathExample, ...]:
    if not rows or any(not isinstance(row, CompetitivePathExample) for row in rows):
        raise ValueError("competitive_path_examples_required")
    if len({row.row_id for row in rows}) != len(rows):
        raise ValueError("duplicate_competitive_path_row_id")
    if any(row.session_id not in axis_index for row in rows):
        raise ValueError("example_session_outside_frozen_axis")
    if any(row.horizon is not horizon for row in rows):
        raise ValueError("mixed_label_horizons")
    return tuple(sorted(rows, key=lambda row: (axis_index[row.session_id], row.row_id)))


def _validate_upstream_exclusions(
    values: Sequence[ExcludedOOFRow],
    examples: tuple[CompetitivePathExample, ...],
    axis_index: Mapping[str, int],
    horizon: LabelHorizon,
) -> tuple[ExcludedOOFRow, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("upstream_exclusions_invalid")
    rows = tuple(values)
    if any(not isinstance(row, ExcludedOOFRow) for row in rows):
        raise ValueError("upstream_exclusions_invalid")
    row_ids = tuple(row.row_id for row in rows)
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("duplicate_upstream_exclusion_row_id")
    if any(row.session_id not in axis_index for row in rows):
        raise ValueError("upstream_exclusion_session_outside_frozen_axis")
    if any(row.horizon is not horizon for row in rows):
        raise ValueError("mixed_label_horizons")
    example_row_ids = {row.row_id for row in examples}
    if any(row.row_id in example_row_ids for row in rows):
        raise ValueError("upstream_exclusion_row_overlap")
    return tuple(
        sorted(rows, key=lambda row: (axis_index[row.session_id], row.row_id))
    )


def _rows_in(
    rows: tuple[CompetitivePathExample, ...],
    interval: SessionInterval,
    axis_index: Mapping[str, int],
) -> tuple[CompetitivePathExample, ...]:
    return tuple(
        row
        for row in rows
        if interval.start <= axis_index[row.session_id] < interval.stop
    )


def _validate_common_prediction_identity(
    rows: tuple[OOFProbabilityRow, ...],
) -> tuple[tuple[str, str], ...]:
    identities = {
        model_id: tuple(
            (row.fold_id, row.row_id) for row in rows if row.model_id == model_id
        )
        for model_id in MODEL_IDS
    }
    reference = identities[MODEL_IDS[0]]
    if not reference or any(value != reference for value in identities.values()):
        raise ValueError("common_row_identity_mismatch")
    return reference


def _metrics_for(
    model_id: str,
    predictions: tuple[OOFProbabilityRow, ...],
) -> OOFMetrics:
    rows = tuple(row for row in predictions if row.model_id == model_id)
    labels = tuple(row.label for row in rows)
    probabilities = tuple(row.probabilities for row in rows)
    return OOFMetrics(
        model_id=model_id,
        row_count=len(rows),
        multiclass_brier=multiclass_brier_score(labels, probabilities),
        log_loss=multiclass_log_loss(labels, probabilities),
        top_class_ece=top_class_ece(labels, probabilities),
    )


def _validate_metric_inputs(
    labels: Sequence[CompetitivePathLabel],
    probabilities: Sequence[Sequence[float]],
    class_order: Sequence[CompetitivePathLabel],
) -> tuple[
    tuple[CompetitivePathLabel, ...],
    tuple[tuple[float, ...], ...],
    tuple[CompetitivePathLabel, ...],
]:
    truth = tuple(labels)
    rows = tuple(tuple(row) for row in probabilities)
    classes = tuple(class_order)
    if (
        not truth
        or len(truth) != len(rows)
        or not classes
        or len(set(classes)) != len(classes)
        or any(label not in classes for label in truth)
    ):
        raise ValueError("multiclass_metric_input_invalid")
    for row in rows:
        _validate_probability_vector(row, len(classes), allow_zero=True)
    return truth, rows, classes


def _validate_probability_vector(
    probabilities: tuple[float, ...],
    class_count: int,
    *,
    allow_zero: bool = False,
) -> None:
    if (
        len(probabilities) != class_count
        or any(
            not _finite(value)
            or value < 0.0
            or value > 1.0
            or not allow_zero and value == 0.0
            for value in probabilities
        )
        or not math.isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ValueError("probability_vector_invalid")


def _row_mask_sha256(
    axis: tuple[str, ...],
    horizon: LabelHorizon,
    folds: tuple[DevelopmentFold, ...],
    identities: tuple[tuple[str, str], ...],
    excluded: tuple[ExcludedOOFRow, ...],
) -> str:
    body = json.dumps(
        {
            "axis": axis,
            "horizon": horizon.value,
            "excluded": tuple(_excluded_oof_body(row) for row in excluded),
            "folds": tuple(
                (
                    fold.fold_id,
                    (fold.train.start, fold.train.stop),
                    (fold.purge.start, fold.purge.stop),
                    (fold.validation.start, fold.validation.stop),
                    (fold.embargo.start, fold.embargo.stop),
                )
                for fold in folds
            ),
            "rows": identities,
            "schemaVersion": "rp001-s2-competitive-path-oof-mask.v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _input_dataset_sha256(
    axis: tuple[str, ...],
    horizon: LabelHorizon,
    rows: tuple[CompetitivePathExample, ...],
    excluded: tuple[ExcludedOOFRow, ...],
) -> str:
    body = json.dumps(
        {
            "axis": axis,
            "horizon": horizon.value,
            "excluded": tuple(_excluded_oof_body(row) for row in excluded),
            "rows": tuple(
                {
                    "familyFlags": tuple(
                        (
                            family,
                            row.family_flags[family].exceeds_p99,
                            row.family_flags[family].exceeds_p999,
                        )
                        for family in FAMILY_NAMES
                    ),
                    "horizon": row.horizon.value,
                    "intrabarLogRangeHex": float(row.intrabar_log_range).hex(),
                    "label": row.label.value,
                    "rowId": row.row_id,
                    "sampleRole": row.sample_role,
                    "sessionId": row.session_id,
                    "signedReturnHex": float(row.signed_return).hex(),
                    "sourceEvidenceSha256": row.source_evidence_sha256,
                    "symbol": row.symbol,
                }
                for row in rows
            ),
            "schemaVersion": "rp001-s2-competitive-path-oof-input.v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _excluded_oof_body(row: ExcludedOOFRow) -> dict[str, str]:
    return {
        "rowId": row.row_id,
        "symbol": row.symbol,
        "sessionId": row.session_id,
        "horizon": row.horizon.value,
        "label": row.label.value,
        "reason": row.reason,
        "sourceEvidenceSha256": row.source_evidence_sha256,
    }


def _finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
