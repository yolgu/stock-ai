"""Point-in-time formulas for RP-001-S2 discovery cycle 001.

The module contains no transport, persistence, trading, account, or asset code.
It models one estimand only: an observable upside-price onset within five
sessions that remains positive at session ten. Human psychology is not
identified by these formulas.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum


_MAD_NORMALIZATION = 1.4826
_SCALE_FLOOR = 1e-6
_STANDARDIZED_FEATURE_LIMIT = 8.0
_ONSET_INACTIVE_M5_LIMIT = 1.0
_ONSET_EXCURSION = 2.0
_ONSET_PERSISTENCE = 1.0
_PRIMARY_HORIZON_SESSIONS = 10
_EARLY_ONSET_WINDOW_SESSIONS = 5
_TRAINING_ITERATIONS = 1_000
_HESSIAN_FLOOR = 1e-9
_CONVERGENCE_TOLERANCE = 1e-10
_KKT_TOLERANCE = 1e-6
_SUSPECTED_SPLIT_LOG_RETURN = math.log(1.35)


class AbstentionReason(str, Enum):
    INSUFFICIENT_HISTORY = "insufficient_history"
    MISSING_REQUIRED_VALUE = "missing_required_value"
    MISSING_REQUIRED_METADATA = "missing_required_metadata"
    UNAVAILABLE_AS_OF_SIGNAL = "unavailable_as_of_signal"
    NONPOSITIVE_REQUIRED_VALUE = "nonpositive_required_value"
    NONFINITE_REQUIRED_VALUE = "nonfinite_required_value"
    MULTIPLE_CURRENCIES = "multiple_currencies"
    MULTIPLE_SERIES = "multiple_series"
    ZERO_VARIATION = "zero_variation"
    OUT_OF_DOMAIN = "out_of_domain"
    SESSION_ORDER_INVALID = "session_order_invalid"
    SUSPECTED_CORPORATE_ACTION = "suspected_corporate_action"


class CandidateFamily(str, Enum):
    MULTI_HORIZON_TREND = "rp001_s2.m1.multi_horizon_trend.v1"
    ACCELERATION_CURVATURE = "rp001_s2.m2.acceleration_curvature.v1"
    VOLUME_CONFIRMED_GATE = "rp001_s2.m1.volume_confirmed_gate.v1"


@dataclass(frozen=True)
class DailyObservation:
    adjusted_close: float | None
    native_close: float | None
    native_volume: float | None
    currency: str | None
    series_id: str | None
    session_id: str | None
    available_as_of_signal: bool


@dataclass(frozen=True)
class Abstention:
    reason: AbstentionReason
    detail: str


@dataclass(frozen=True)
class ForecastFeatures:
    z1: float
    m3: float
    m5: float
    m10: float
    m20: float
    trend_consistency_10: float
    acceleration_3_vs_10: float
    return_curvature: float
    turnover_surprise: float
    return_scale: float
    turnover_scale: float
    as_of_index: int
    series_id: str
    signal_session_id: str
    source_window_sha256: str

    def __post_init__(self) -> None:
        numeric_values = (
            self.z1,
            self.m3,
            self.m5,
            self.m10,
            self.m20,
            self.trend_consistency_10,
            self.acceleration_3_vs_10,
            self.return_curvature,
            self.turnover_surprise,
            self.return_scale,
            self.turnover_scale,
        )
        if any(not _is_finite(value) for value in numeric_values):
            raise ValueError("forecast_features_must_be_finite")
        if self.return_scale <= 0.0 or self.turnover_scale <= 0.0:
            raise ValueError("forecast_feature_scales_must_be_positive")
        if not 0.0 <= self.trend_consistency_10 <= 1.0:
            raise ValueError("trend_consistency_out_of_domain")
        standardized_values = (
            self.z1,
            self.m3,
            self.m5,
            self.m10,
            self.m20,
            self.acceleration_3_vs_10,
            self.return_curvature,
            self.turnover_surprise,
        )
        if any(
            abs(value) > _STANDARDIZED_FEATURE_LIMIT
            for value in standardized_values
        ):
            raise ValueError("standardized_feature_out_of_domain")
        if self.as_of_index < 0:
            raise ValueError("as_of_index_out_of_domain")
        if not self.series_id or not self.signal_session_id:
            raise ValueError("forecast_feature_metadata_required")
        if not _is_sha256(self.source_window_sha256):
            raise ValueError("source_window_sha256_invalid")


@dataclass(frozen=True)
class OnsetLabel:
    outcome: bool
    onset_offset_sessions: int | None

    def __post_init__(self) -> None:
        if self.outcome and self.onset_offset_sessions is None:
            raise ValueError("positive_onset_requires_offset")
        if not self.outcome and self.onset_offset_sessions is not None:
            raise ValueError("negative_onset_forbids_offset")
        if self.onset_offset_sessions is not None and not (
            1 <= self.onset_offset_sessions <= _EARLY_ONSET_WINDOW_SESSIONS
        ):
            raise ValueError("onset_offset_out_of_domain")


@dataclass(frozen=True)
class IneligibleOnsetLabel:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("ineligible_onset_reason_required")


@dataclass(frozen=True)
class FormulaBasis:
    formula_id: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.formula_id:
            raise ValueError("formula_id_required")
        if not self.values or any(
            not _is_finite(value) or not 0.0 <= value <= 1.0
            for value in self.values
        ):
            raise ValueError("formula_basis_out_of_domain")


@dataclass(frozen=True)
class TrainingRow:
    basis: FormulaBasis
    outcome: bool

    def __post_init__(self) -> None:
        if not isinstance(self.basis, FormulaBasis):
            raise ValueError("training_basis_invalid")
        if type(self.outcome) is not bool:
            raise ValueError("training_outcome_must_be_bool")


@dataclass(frozen=True)
class ConstrainedLogisticModel:
    formula_id: str
    intercept: float
    nonnegative_weights: tuple[float, ...]
    l2_penalty: float

    def __post_init__(self) -> None:
        if not self.formula_id:
            raise ValueError("formula_id_required")
        if not _is_finite(self.intercept):
            raise ValueError("model_intercept_must_be_finite")
        if not self.nonnegative_weights or any(
            not _is_finite(weight) or weight < 0.0
            for weight in self.nonnegative_weights
        ):
            raise ValueError("model_weights_must_be_finite_nonnegative")
        if not _is_finite(self.l2_penalty) or self.l2_penalty <= 0.0:
            raise ValueError("l2_penalty_out_of_domain")


def build_forecast_features(
    observations: Sequence[DailyObservation],
    as_of_index: int,
) -> ForecastFeatures | Abstention:
    """Build features from exactly the 22 rows ending at ``as_of_index``."""
    if (
        isinstance(as_of_index, bool)
        or not isinstance(as_of_index, int)
        or as_of_index < 21
        or as_of_index >= len(observations)
    ):
        return Abstention(
            AbstentionReason.INSUFFICIENT_HISTORY,
            "22 observations ending at the signal session are required",
        )
    window = tuple(observations[as_of_index - 21 : as_of_index + 1])
    problem = _validate_window(window)
    if problem is not None:
        return problem
    try:
        return _calculate_features(window, as_of_index)
    except (OverflowError, ValueError, ZeroDivisionError):
        return Abstention(
            AbstentionReason.NONFINITE_REQUIRED_VALUE,
            "required values cannot produce finite logarithmic features",
        )


def candidate_basis(
    family: CandidateFamily,
    features: ForecastFeatures | Abstention,
) -> FormulaBasis:
    """Return a bounded monotone basis for one registered mechanism family."""
    if isinstance(features, Abstention):
        raise ValueError("candidate_basis_requires_features")
    if not isinstance(family, CandidateFamily):
        raise ValueError("candidate_family_invalid")
    if family is CandidateFamily.MULTI_HORIZON_TREND:
        return FormulaBasis(
            family.value,
            (
                _ramp(features.m3, 0.25, 2.5),
                _ramp(features.m10, 0.25, 2.5),
                _ramp(features.trend_consistency_10, 0.5, 0.9),
                _ramp(features.turnover_surprise, 0.0, 3.0),
            ),
        )
    if family is CandidateFamily.ACCELERATION_CURVATURE:
        acceleration = _ramp(features.acceleration_3_vs_10, 0.0, 2.0)
        curvature = _ramp(features.return_curvature, 0.0, 2.0)
        turnover = _ramp(features.turnover_surprise, 0.0, 3.0)
        return FormulaBasis(
            family.value,
            (
                acceleration,
                curvature,
                turnover,
                acceleration * curvature,
            ),
        )
    momentum = _ramp(features.m5, 0.25, 2.5)
    shock = _ramp(features.z1, 0.25, 2.5)
    long_trend = _ramp(features.m10, 0.25, 2.5)
    consistency = _ramp(features.trend_consistency_10, 0.5, 0.9)
    turnover = _ramp(features.turnover_surprise, 0.0, 3.0)
    return FormulaBasis(
        family.value,
        (
            math.sqrt(momentum * turnover),
            math.sqrt(shock * turnover),
            (long_trend * consistency * turnover) ** (1.0 / 3.0),
        ),
    )


def fit_constrained_logistic(
    rows: Sequence[TrainingRow],
    *,
    l2_penalty: float,
) -> ConstrainedLogisticModel:
    """Fit deterministic logistic weights projected onto the nonnegative cone."""
    training_rows = tuple(rows)
    if not training_rows:
        raise ValueError("training_rows_required")
    if not _is_finite(l2_penalty) or l2_penalty <= 0.0:
        raise ValueError("l2_penalty_out_of_domain")
    if len({row.outcome for row in training_rows}) != 2:
        raise ValueError("training_requires_both_outcomes")
    formula_id = training_rows[0].basis.formula_id
    if any(row.basis.formula_id != formula_id for row in training_rows):
        raise ValueError("formula_family_mismatch")
    dimension = len(training_rows[0].basis.values)
    if any(len(row.basis.values) != dimension for row in training_rows):
        raise ValueError("basis_dimension_mismatch")

    return _fit_active_set_logistic(
        training_rows,
        formula_id=formula_id,
        dimension=dimension,
        l2_penalty=float(l2_penalty),
    )


def predict_probability(
    model: ConstrainedLogisticModel,
    basis: FormulaBasis,
) -> float:
    """Evaluate the frozen constrained-logistic equation."""
    if basis.formula_id != model.formula_id:
        raise ValueError("formula_family_mismatch")
    values = tuple(float(value) for value in basis.values)
    if len(values) != len(model.nonnegative_weights):
        raise ValueError("basis_dimension_mismatch")
    if any(not _is_finite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("basis_out_of_domain")
    linear = model.intercept + sum(
        weight * value
        for weight, value in zip(model.nonnegative_weights, values, strict=True)
    )
    return _sigmoid(linear)


def model_kkt_residual(
    rows: Sequence[TrainingRow],
    model: ConstrainedLogisticModel,
) -> float:
    """Return the normalized KKT residual used by the frozen fit contract."""
    values = tuple(rows)
    if not values or any(row.basis.formula_id != model.formula_id for row in values):
        raise ValueError("formula_family_mismatch")
    return _kkt_residual(values, model)


def label_upside_regime_onset(
    observations: Sequence[DailyObservation],
    as_of_index: int,
    features: ForecastFeatures,
) -> OnsetLabel | IneligibleOnsetLabel:
    """Label a new upside price-regime onset using future rows only here."""
    if features.as_of_index != as_of_index:
        return IneligibleOnsetLabel("feature_as_of_mismatch")
    reproduced = build_forecast_features(observations, as_of_index)
    if isinstance(reproduced, Abstention) or reproduced != features:
        return IneligibleOnsetLabel("source_window_mismatch")
    if features.m5 >= _ONSET_INACTIVE_M5_LIMIT:
        return IneligibleOnsetLabel("active_upside_regime_at_signal")
    if len(observations) - as_of_index - 1 < _PRIMARY_HORIZON_SESSIONS:
        return IneligibleOnsetLabel("insufficient_future")
    current = observations[as_of_index]
    if not _is_positive_finite(current.adjusted_close):
        return IneligibleOnsetLabel("invalid_current_close")
    standardized_returns: list[float] = []
    try:
        prior_future_session = date.fromisoformat(features.signal_session_id)
    except ValueError:
        return IneligibleOnsetLabel("invalid_future_session_order")
    for offset in range(1, _PRIMARY_HORIZON_SESSIONS + 1):
        future = observations[as_of_index + offset]
        if (
            future.series_id != features.series_id
            or future.currency != current.currency
            or not _is_positive_finite(future.adjusted_close)
        ):
            return IneligibleOnsetLabel("invalid_future_row")
        try:
            future_session = date.fromisoformat(str(future.session_id))
        except ValueError:
            return IneligibleOnsetLabel("invalid_future_session_order")
        if future_session <= prior_future_session:
            return IneligibleOnsetLabel("invalid_future_session_order")
        prior_future_session = future_session
        standardized_returns.append(
            (
                math.log(float(future.adjusted_close))
                - math.log(float(current.adjusted_close))
            )
            / features.return_scale
        )
    onset_offset = next(
        (
            index + 1
            for index, value in enumerate(
                standardized_returns[:_EARLY_ONSET_WINDOW_SESSIONS]
            )
            if value >= _ONSET_EXCURSION
        ),
        None,
    )
    outcome = (
        onset_offset is not None
        and standardized_returns[-1] >= _ONSET_PERSISTENCE
    )
    return OnsetLabel(
        outcome=outcome,
        onset_offset_sessions=onset_offset if outcome else None,
    )


def _calculate_features(
    window: tuple[DailyObservation, ...],
    as_of_index: int,
) -> ForecastFeatures | Abstention:
    native_logs = tuple(math.log(float(row.native_close)) for row in window)
    returns = tuple(
        native_logs[index] - native_logs[index - 1]
        for index in range(1, len(native_logs))
    )
    if any(abs(value) >= _SUSPECTED_SPLIT_LOG_RETURN for value in returns):
        return Abstention(
            AbstentionReason.SUSPECTED_CORPORATE_ACTION,
            "native return exceeds the frozen corporate-action quarantine",
        )
    historical_returns = returns[:20]
    return_scale = _MAD_NORMALIZATION * _median_absolute_deviation(
        historical_returns
    )
    turnover_logs = tuple(
        math.log(float(row.native_close)) + math.log(float(row.native_volume))
        for row in window[1:]
    )
    historical_turnover = turnover_logs[:20]
    turnover_scale = _MAD_NORMALIZATION * _median_absolute_deviation(
        historical_turnover
    )
    if return_scale < _SCALE_FLOOR or turnover_scale < _SCALE_FLOOR:
        return Abstention(
            AbstentionReason.ZERO_VARIATION,
            "return or turnover MAD scale is below 1e-6",
        )
    z1 = returns[-1] / return_scale
    m3 = sum(returns[-3:]) / (math.sqrt(3.0) * return_scale)
    m5 = sum(returns[-5:]) / (math.sqrt(5.0) * return_scale)
    m10 = sum(returns[-10:]) / (math.sqrt(10.0) * return_scale)
    m20 = sum(returns[-20:]) / (math.sqrt(20.0) * return_scale)
    prior_five_mean = sum(returns[-6:-1]) / 5.0
    curvature = (returns[-1] - prior_five_mean) / return_scale
    turnover_surprise = (
        turnover_logs[-1] - _median(historical_turnover)
    ) / turnover_scale
    standardized = (
        z1,
        m3,
        m5,
        m10,
        m20,
        m3 - m10,
        curvature,
        turnover_surprise,
    )
    if any(abs(value) > _STANDARDIZED_FEATURE_LIMIT for value in standardized):
        return Abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "standardized feature exceeds the closed [-8, 8] domain",
        )
    return ForecastFeatures(
        z1=z1,
        m3=m3,
        m5=m5,
        m10=m10,
        m20=m20,
        trend_consistency_10=sum(value > 0.0 for value in returns[-10:]) / 10.0,
        acceleration_3_vs_10=m3 - m10,
        return_curvature=curvature,
        turnover_surprise=turnover_surprise,
        return_scale=return_scale,
        turnover_scale=turnover_scale,
        as_of_index=as_of_index,
        series_id=str(window[-1].series_id),
        signal_session_id=str(window[-1].session_id),
        source_window_sha256=_source_window_sha256(window),
    )


def _validate_window(
    window: tuple[DailyObservation, ...],
) -> Abstention | None:
    currencies: set[str] = set()
    series_ids: set[str] = set()
    prior_session: date | None = None
    for row in window:
        for name, value in (
            ("adjusted_close", row.adjusted_close),
            ("native_close", row.native_close),
            ("native_volume", row.native_volume),
        ):
            if value is None:
                return Abstention(
                    AbstentionReason.MISSING_REQUIRED_VALUE,
                    f"missing required {name}",
                )
            if not _is_finite(value):
                return Abstention(
                    AbstentionReason.NONFINITE_REQUIRED_VALUE,
                    f"nonfinite required {name}",
                )
            if value <= 0.0:
                return Abstention(
                    AbstentionReason.NONPOSITIVE_REQUIRED_VALUE,
                    f"nonpositive required {name}",
                )
        if not row.currency or not row.series_id or not row.session_id:
            return Abstention(
                AbstentionReason.MISSING_REQUIRED_METADATA,
                "currency, series_id, and session_id are required",
            )
        if row.available_as_of_signal is not True:
            return Abstention(
                AbstentionReason.UNAVAILABLE_AS_OF_SIGNAL,
                "required row was unavailable at signal time",
            )
        currencies.add(row.currency)
        series_ids.add(row.series_id)
        try:
            session = date.fromisoformat(row.session_id)
        except ValueError:
            return Abstention(
                AbstentionReason.SESSION_ORDER_INVALID,
                "session_id must be an ISO date",
            )
        if prior_session is not None and session <= prior_session:
            return Abstention(
                AbstentionReason.SESSION_ORDER_INVALID,
                "session_id values must be strictly increasing",
            )
        prior_session = session
    if len(currencies) != 1:
        return Abstention(
            AbstentionReason.MULTIPLE_CURRENCIES,
            "required rows must use one currency",
        )
    if len(series_ids) != 1:
        return Abstention(
            AbstentionReason.MULTIPLE_SERIES,
            "required rows must use one series_id",
        )
    return None


def _source_window_sha256(window: tuple[DailyObservation, ...]) -> str:
    body = [
        {
            "adjustedClose": row.adjusted_close,
            "availableAsOfSignal": row.available_as_of_signal,
            "currency": row.currency,
            "nativeClose": row.native_close,
            "nativeVolume": row.native_volume,
            "seriesId": row.series_id,
            "sessionId": row.session_id,
        }
        for row in window
    ]
    source = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(source).hexdigest()


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _median_absolute_deviation(values: Sequence[float]) -> float:
    center = _median(values)
    return _median(tuple(abs(value - center) for value in values))


def _ramp(value: float, lower: float, upper: float) -> float:
    if value <= lower:
        return 0.0
    if value >= upper:
        return 1.0
    return (value - lower) / (upper - lower)


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _fit_active_set_logistic(
    rows: tuple[TrainingRow, ...],
    *,
    formula_id: str,
    dimension: int,
    l2_penalty: float,
) -> ConstrainedLogisticModel:
    successes = sum(int(row.outcome) for row in rows)
    prevalence = (successes + 0.5) / (len(rows) + 1.0)
    intercept = math.log(prevalence / (1.0 - prevalence))
    weights = [0.0] * dimension
    active = set(range(dimension))
    for _active_iteration in range(2 * dimension + 4):
        ordered_active = tuple(sorted(active))
        parameters = [intercept] + [weights[index] for index in ordered_active]
        converged = False
        for _newton_iteration in range(_TRAINING_ITERATIONS):
            objective, gradient, hessian = _active_objective_derivatives(
                rows,
                parameters,
                ordered_active,
                l2_penalty,
            )
            scaled_gradient = max(abs(value) for value in gradient) / len(rows)
            if scaled_gradient <= _KKT_TOLERANCE / 10.0:
                converged = True
                break
            newton_step = _solve_linear_system(hessian, gradient)
            direction = tuple(-value for value in newton_step)
            directional_derivative = sum(
                first * second
                for first, second in zip(gradient, direction, strict=True)
            )
            step_size = 1.0
            accepted = False
            while step_size >= 2.0**-30:
                candidate = [
                    value + step_size * change
                    for value, change in zip(
                        parameters,
                        direction,
                        strict=True,
                    )
                ]
                candidate_objective = _active_objective(
                    rows,
                    candidate,
                    ordered_active,
                    l2_penalty,
                )
                if candidate_objective <= (
                    objective + 1e-4 * step_size * directional_derivative
                ):
                    parameters = candidate
                    accepted = True
                    break
                step_size *= 0.5
            if not accepted:
                raise ValueError("training_did_not_converge")
        if not converged:
            raise ValueError("training_did_not_converge")
        intercept = parameters[0]
        for offset, index in enumerate(ordered_active, start=1):
            weights[index] = parameters[offset]

        negative = tuple(index for index in active if weights[index] < 0.0)
        if negative:
            removed = min(negative, key=lambda index: weights[index])
            active.remove(removed)
            weights[removed] = 0.0
            continue
        weights = [max(0.0, value) for value in weights]
        candidate_model = ConstrainedLogisticModel(
            formula_id=formula_id,
            intercept=intercept,
            nonnegative_weights=tuple(weights),
            l2_penalty=l2_penalty,
        )
        full_gradients = _weight_gradients(rows, candidate_model)
        violating_inactive = tuple(
            index
            for index in range(dimension)
            if index not in active and full_gradients[index] < -_KKT_TOLERANCE
        )
        if violating_inactive:
            active.add(min(violating_inactive, key=lambda index: full_gradients[index]))
            continue
        if _kkt_residual(rows, candidate_model) > _KKT_TOLERANCE:
            raise ValueError("training_did_not_converge")
        return candidate_model
    raise ValueError("training_did_not_converge")


def _active_objective_derivatives(
    rows: tuple[TrainingRow, ...],
    parameters: Sequence[float],
    active: tuple[int, ...],
    l2_penalty: float,
) -> tuple[float, list[float], list[list[float]]]:
    dimension = len(parameters)
    gradient = [0.0] * dimension
    hessian = [[0.0] * dimension for _ in range(dimension)]
    objective = 0.0
    for row in rows:
        vector = (1.0,) + tuple(row.basis.values[index] for index in active)
        linear = sum(
            coefficient * value
            for coefficient, value in zip(parameters, vector, strict=True)
        )
        probability = _sigmoid(linear)
        objective += _logistic_loss(row.outcome, linear)
        error = probability - float(row.outcome)
        curvature = probability * (1.0 - probability)
        for first in range(dimension):
            gradient[first] += error * vector[first]
            for second in range(dimension):
                hessian[first][second] += (
                    curvature * vector[first] * vector[second]
                )
    for offset in range(1, dimension):
        objective += 0.5 * l2_penalty * parameters[offset] ** 2
        gradient[offset] += l2_penalty * parameters[offset]
        hessian[offset][offset] += l2_penalty
    hessian[0][0] = max(hessian[0][0], _HESSIAN_FLOOR)
    return objective, gradient, hessian


def _active_objective(
    rows: tuple[TrainingRow, ...],
    parameters: Sequence[float],
    active: tuple[int, ...],
    l2_penalty: float,
) -> float:
    objective = 0.0
    for row in rows:
        vector = (1.0,) + tuple(row.basis.values[index] for index in active)
        linear = sum(
            coefficient * value
            for coefficient, value in zip(parameters, vector, strict=True)
        )
        objective += _logistic_loss(row.outcome, linear)
    objective += 0.5 * l2_penalty * sum(
        value * value for value in parameters[1:]
    )
    return objective


def _logistic_loss(outcome: bool, linear: float) -> float:
    if linear >= 0.0:
        return (1.0 - float(outcome)) * linear + math.log1p(math.exp(-linear))
    return -float(outcome) * linear + math.log1p(math.exp(linear))


def _solve_linear_system(
    matrix: Sequence[Sequence[float]],
    right_hand_side: Sequence[float],
) -> tuple[float, ...]:
    size = len(right_hand_side)
    augmented = [
        [float(value) for value in row] + [float(right_hand_side[index])]
        for index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < _HESSIAN_FLOOR:
            raise ValueError("training_did_not_converge")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return tuple(augmented[index][size] for index in range(size))


def _weight_gradients(
    rows: Sequence[TrainingRow],
    model: ConstrainedLogisticModel,
) -> tuple[float, ...]:
    probabilities = tuple(predict_probability(model, row.basis) for row in rows)
    return tuple(
        (
            model.l2_penalty * weight
            + sum(
                (probability - float(row.outcome)) * row.basis.values[index]
                for probability, row in zip(probabilities, rows, strict=True)
            )
        )
        / len(rows)
        for index, weight in enumerate(model.nonnegative_weights)
    )


def _kkt_residual(
    rows: Sequence[TrainingRow],
    model: ConstrainedLogisticModel,
) -> float:
    probabilities = tuple(
        predict_probability(model, row.basis) for row in rows
    )
    count = float(len(rows))
    intercept_gradient = sum(
        probability - float(row.outcome)
        for probability, row in zip(probabilities, rows, strict=True)
    ) / count
    violations = [abs(intercept_gradient)]
    for weight, gradient in zip(
        model.nonnegative_weights,
        _weight_gradients(rows, model),
        strict=True,
    ):
        violations.append(
            abs(gradient) if weight > _CONVERGENCE_TOLERANCE else max(0.0, -gradient)
        )
    return max(violations)


def _is_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _is_positive_finite(value: float | None) -> bool:
    return value is not None and _is_finite(value) and value > 0.0


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
