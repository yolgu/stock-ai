"""PIT formulas for RP-001-S2 Cycle 003 downside-regime recovery discovery."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from rp001_s2.discovery import (
    Abstention,
    DailyObservation,
    ForecastFeatures,
    FormulaBasis,
    build_forecast_features,
)


_ACTIVE_DOWNSIDE_M5_THRESHOLD = -1.0
_DURATION_CAP = 20
_FULL_HISTORY_ROWS = 41
_RECOVERY_SEARCH_SESSIONS = 5
_PRIMARY_HORIZON_SESSIONS = 10
_STANDARDIZED_LIMIT = 8.0


class Cycle003Family(str, Enum):
    DOWNSIDE_DECELERATION_CAPITULATION = (
        "rp001_s2.m3.downside_deceleration_capitulation.v1"
    )
    LOWER_TAIL_STRETCH_REVERSAL = "rp001_s2.m2.lower_tail_stretch_reversal.v1"
    DOWNSIDE_DURATION_RECOVERY_HAZARD = (
        "rp001_s2.m4.downside_duration_recovery_hazard.v1"
    )


@dataclass(frozen=True)
class Cycle003Abstention:
    reason: str
    detail: str

    def __post_init__(self) -> None:
        if not self.reason or not self.detail:
            raise ValueError("cycle003_abstention_requires_reason_and_detail")


@dataclass(frozen=True)
class Cycle003Features:
    base: ForecastFeatures
    downside_duration_sessions: int
    cumulative_drawdown: float
    full_source_window_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.base, ForecastFeatures):
            raise ValueError("cycle003_base_features_invalid")
        if (
            isinstance(self.downside_duration_sessions, bool)
            or not isinstance(self.downside_duration_sessions, int)
            or not 0 <= self.downside_duration_sessions <= _DURATION_CAP
        ):
            raise ValueError("downside_duration_out_of_domain")
        if not math.isfinite(self.cumulative_drawdown) or not (
            -_STANDARDIZED_LIMIT <= self.cumulative_drawdown <= _STANDARDIZED_LIMIT
        ):
            raise ValueError("cumulative_drawdown_out_of_domain")
        if not _is_sha256(self.full_source_window_sha256):
            raise ValueError("full_source_window_sha256_invalid")


@dataclass(frozen=True)
class RecoveryLabel:
    outcome: bool
    recovery_offset_sessions: int | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not bool:
            raise ValueError("recovery_outcome_must_be_bool")
        if self.outcome != (self.recovery_offset_sessions is not None):
            raise ValueError("recovery_offset_outcome_mismatch")
        if self.recovery_offset_sessions is not None and not (
            1 <= self.recovery_offset_sessions <= _RECOVERY_SEARCH_SESSIONS
        ):
            raise ValueError("recovery_offset_out_of_domain")


@dataclass(frozen=True)
class IneligibleRecoveryLabel:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("ineligible_recovery_reason_required")


def build_cycle003_features(
    observations: Sequence[DailyObservation],
    as_of_index: int,
) -> Cycle003Features | Cycle003Abstention:
    """Build the common 41-row PIT downside-state history and duration features."""
    if (
        isinstance(as_of_index, bool)
        or not isinstance(as_of_index, int)
        or as_of_index < _FULL_HISTORY_ROWS - 1
        or as_of_index >= len(observations)
    ):
        return Cycle003Abstention(
            "insufficient_history",
            "41 observations ending at the signal session are required",
        )
    state_features: list[ForecastFeatures] = []
    for state_index in range(as_of_index - _DURATION_CAP + 1, as_of_index + 1):
        value = build_forecast_features(observations, state_index)
        if isinstance(value, Abstention):
            return Cycle003Abstention(
                value.reason.value,
                f"state-history feature at index {state_index} abstained: {value.detail}",
            )
        state_features.append(value)
    current = state_features[-1]
    duration = 0
    for value in reversed(state_features):
        if value.m5 > _ACTIVE_DOWNSIDE_M5_THRESHOLD:
            break
        duration += 1
    cumulative_drawdown = 0.0
    if duration > 0:
        current_close = observations[as_of_index].native_close
        prior_close = observations[as_of_index - duration].native_close
        if not _is_positive_finite(current_close) or not _is_positive_finite(prior_close):
            return Cycle003Abstention(
                "nonpositive_required_value",
                "duration drawdown requires positive finite native closes",
            )
        cumulative_drawdown = (
            math.log(float(prior_close)) - math.log(float(current_close))
        ) / (math.sqrt(float(duration)) * current.return_scale)
    if not math.isfinite(cumulative_drawdown) or abs(cumulative_drawdown) > _STANDARDIZED_LIMIT:
        return Cycle003Abstention(
            "out_of_domain",
            "standardized duration drawdown exceeds the closed [-8, 8] domain",
        )
    full_window = tuple(
        observations[as_of_index - (_FULL_HISTORY_ROWS - 1) : as_of_index + 1]
    )
    return Cycle003Features(
        base=current,
        downside_duration_sessions=duration,
        cumulative_drawdown=cumulative_drawdown,
        full_source_window_sha256=_source_window_sha256(full_window),
    )


def cycle003_basis(
    family: Cycle003Family,
    features: Cycle003Features | Cycle003Abstention,
) -> FormulaBasis:
    """Return one bounded basis for a Cycle 003 recovery mechanism family."""
    if isinstance(features, Cycle003Abstention):
        raise ValueError("cycle003_basis_requires_features")
    if not isinstance(family, Cycle003Family):
        raise ValueError("cycle003_family_invalid")
    base = features.base
    if family is Cycle003Family.DOWNSIDE_DECELERATION_CAPITULATION:
        positive_shock = _ramp(base.z1, 0.0, 2.5)
        acceleration = _ramp(base.m3 - base.m10, 0.0, 2.5)
        positive_curvature = _ramp(base.return_curvature, 0.0, 2.5)
        turnover = _ramp(base.turnover_surprise, 0.0, 3.0)
        return FormulaBasis(
            family.value,
            (
                positive_shock,
                acceleration,
                positive_curvature,
                (positive_shock * positive_curvature * turnover) ** (1.0 / 3.0),
            ),
        )
    if family is Cycle003Family.LOWER_TAIL_STRETCH_REVERSAL:
        m5 = _ramp(-base.m5, 1.0, 3.0)
        m10 = _ramp(-base.m10, 0.5, 3.0)
        m20 = _ramp(-base.m20, 0.0, 3.0)
        return FormulaBasis(
            family.value,
            (m5, m10, m20, (m5 * m10 * m20) ** (1.0 / 3.0)),
        )
    early_age = _ramp(float(features.downside_duration_sessions), 1.0, 6.0)
    mature_age = _ramp(float(features.downside_duration_sessions), 3.0, 10.0)
    drawdown = _ramp(features.cumulative_drawdown, 1.0, 4.0)
    return FormulaBasis(
        family.value,
        (early_age, mature_age, drawdown, math.sqrt(mature_age * drawdown)),
    )


def label_downside_regime_recovery(
    observations: Sequence[DailyObservation],
    as_of_index: int,
    features: Cycle003Features,
) -> RecoveryLabel | IneligibleRecoveryLabel:
    """Label persistent recovery from an active downside price regime."""
    if features.base.as_of_index != as_of_index:
        return IneligibleRecoveryLabel("feature_as_of_mismatch")
    reproduced = build_cycle003_features(observations, as_of_index)
    if isinstance(reproduced, Cycle003Abstention) or reproduced != features:
        return IneligibleRecoveryLabel("source_window_mismatch")
    if features.base.m5 > _ACTIVE_DOWNSIDE_M5_THRESHOLD:
        return IneligibleRecoveryLabel("inactive_downside_regime_at_signal")
    if len(observations) - as_of_index - 1 < _PRIMARY_HORIZON_SESSIONS:
        return IneligibleRecoveryLabel("insufficient_future")
    current = observations[as_of_index]
    try:
        prior_session = date.fromisoformat(features.base.signal_session_id)
    except ValueError:
        return IneligibleRecoveryLabel("invalid_future_session_order")
    for offset in range(1, _PRIMARY_HORIZON_SESSIONS + 1):
        future = observations[as_of_index + offset]
        if (
            future.series_id != features.base.series_id
            or future.currency != current.currency
            or not _is_positive_finite(future.adjusted_close)
        ):
            return IneligibleRecoveryLabel("invalid_future_row")
        try:
            session = date.fromisoformat(str(future.session_id))
        except ValueError:
            return IneligibleRecoveryLabel("invalid_future_session_order")
        if session <= prior_session:
            return IneligibleRecoveryLabel("invalid_future_session_order")
        prior_session = session
    denominator = math.sqrt(5.0) * features.base.return_scale
    rolling_momentum = tuple(
        (
            math.log(float(observations[as_of_index + offset].adjusted_close))
            - math.log(float(observations[as_of_index + offset - 5].adjusted_close))
        )
        / denominator
        for offset in range(1, _PRIMARY_HORIZON_SESSIONS + 1)
    )
    recovery_offset = next(
        (
            offset
            for offset, value in enumerate(
                rolling_momentum[:_RECOVERY_SEARCH_SESSIONS],
                start=1,
            )
            if value >= 0.0
        ),
        None,
    )
    outcome = recovery_offset is not None and rolling_momentum[-1] >= 0.0
    return RecoveryLabel(
        outcome=outcome,
        recovery_offset_sessions=recovery_offset if outcome else None,
    )


def hypothetical_recovery_long_return(
    next_session_close: float,
    horizon_close: float,
    *,
    cost_bps: float,
) -> float:
    """Return research-only next-close to session-ten long return net of costs."""
    if (
        not _is_positive_finite(next_session_close)
        or not _is_positive_finite(horizon_close)
        or not math.isfinite(cost_bps)
        or cost_bps < 0.0
    ):
        raise ValueError("hypothetical_economics_input_invalid")
    return (
        float(horizon_close) / float(next_session_close)
        - 1.0
        - cost_bps / 10_000.0
    )


def _source_window_sha256(window: Sequence[DailyObservation]) -> str:
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


def _ramp(value: float, lower: float, upper: float) -> float:
    if value <= lower:
        return 0.0
    if value >= upper:
        return 1.0
    return (value - lower) / (upper - lower)


def _is_positive_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
