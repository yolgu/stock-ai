"""PIT formulas for RP-001-S2 Cycle 002 upside-regime end discovery."""

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


_ACTIVE_M5_THRESHOLD = 1.0
_DURATION_CAP = 20
_FULL_HISTORY_ROWS = 41
_END_SEARCH_SESSIONS = 5
_PRIMARY_HORIZON_SESSIONS = 10
_STANDARDIZED_LIMIT = 8.0


class Cycle002Family(str, Enum):
    TAIL_STRETCH_REVERSION = "rp001_s2.m2.tail_stretch_reversion.v1"
    DECELERATION_DISTRIBUTION = "rp001_s2.m3.deceleration_distribution.v1"
    ACTIVE_DURATION_HAZARD = "rp001_s2.m4.active_duration_hazard.v1"


@dataclass(frozen=True)
class Cycle002Abstention:
    reason: str
    detail: str

    def __post_init__(self) -> None:
        if not self.reason or not self.detail:
            raise ValueError("cycle002_abstention_requires_reason_and_detail")


@dataclass(frozen=True)
class Cycle002Features:
    base: ForecastFeatures
    active_duration_sessions: int
    cumulative_runup: float
    full_source_window_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.base, ForecastFeatures):
            raise ValueError("cycle002_base_features_invalid")
        if (
            isinstance(self.active_duration_sessions, bool)
            or not isinstance(self.active_duration_sessions, int)
            or not 0 <= self.active_duration_sessions <= _DURATION_CAP
        ):
            raise ValueError("active_duration_out_of_domain")
        if not math.isfinite(self.cumulative_runup) or not (
            -_STANDARDIZED_LIMIT <= self.cumulative_runup <= _STANDARDIZED_LIMIT
        ):
            raise ValueError("cumulative_runup_out_of_domain")
        if not _is_sha256(self.full_source_window_sha256):
            raise ValueError("full_source_window_sha256_invalid")


@dataclass(frozen=True)
class RegimeEndLabel:
    outcome: bool
    end_offset_sessions: int | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not bool:
            raise ValueError("regime_end_outcome_must_be_bool")
        if self.outcome != (self.end_offset_sessions is not None):
            raise ValueError("regime_end_offset_outcome_mismatch")
        if self.end_offset_sessions is not None and not (
            1 <= self.end_offset_sessions <= _END_SEARCH_SESSIONS
        ):
            raise ValueError("regime_end_offset_out_of_domain")


@dataclass(frozen=True)
class IneligibleRegimeEndLabel:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("ineligible_regime_end_reason_required")


def build_cycle002_features(
    observations: Sequence[DailyObservation],
    as_of_index: int,
) -> Cycle002Features | Cycle002Abstention:
    """Build the shared 41-row PIT mask and active-state duration features."""
    if (
        isinstance(as_of_index, bool)
        or not isinstance(as_of_index, int)
        or as_of_index < _FULL_HISTORY_ROWS - 1
        or as_of_index >= len(observations)
    ):
        return Cycle002Abstention(
            "insufficient_history",
            "41 observations ending at the signal session are required",
        )
    state_features: list[ForecastFeatures] = []
    for state_index in range(as_of_index - _DURATION_CAP + 1, as_of_index + 1):
        value = build_forecast_features(observations, state_index)
        if isinstance(value, Abstention):
            return Cycle002Abstention(
                value.reason.value,
                f"state-history feature at index {state_index} abstained: {value.detail}",
            )
        state_features.append(value)
    current = state_features[-1]
    duration = 0
    for value in reversed(state_features):
        if value.m5 < _ACTIVE_M5_THRESHOLD:
            break
        duration += 1
    cumulative_runup = 0.0
    if duration > 0:
        current_close = observations[as_of_index].native_close
        prior_close = observations[as_of_index - duration].native_close
        if not _is_positive_finite(current_close) or not _is_positive_finite(prior_close):
            return Cycle002Abstention(
                "nonpositive_required_value",
                "duration run-up requires positive finite native closes",
            )
        cumulative_runup = (
            math.log(float(current_close)) - math.log(float(prior_close))
        ) / (math.sqrt(float(duration)) * current.return_scale)
    if not math.isfinite(cumulative_runup) or abs(cumulative_runup) > _STANDARDIZED_LIMIT:
        return Cycle002Abstention(
            "out_of_domain",
            "standardized duration run-up exceeds the closed [-8, 8] domain",
        )
    full_window = tuple(
        observations[as_of_index - (_FULL_HISTORY_ROWS - 1) : as_of_index + 1]
    )
    return Cycle002Features(
        base=current,
        active_duration_sessions=duration,
        cumulative_runup=cumulative_runup,
        full_source_window_sha256=_source_window_sha256(full_window),
    )


def cycle002_basis(
    family: Cycle002Family,
    features: Cycle002Features | Cycle002Abstention,
) -> FormulaBasis:
    """Return one bounded basis for the frozen Cycle 002 mechanism families."""
    if isinstance(features, Cycle002Abstention):
        raise ValueError("cycle002_basis_requires_features")
    if not isinstance(family, Cycle002Family):
        raise ValueError("cycle002_family_invalid")
    base = features.base
    if family is Cycle002Family.TAIL_STRETCH_REVERSION:
        m5 = _ramp(base.m5, 1.0, 3.0)
        m10 = _ramp(base.m10, 0.5, 3.0)
        m20 = _ramp(base.m20, 0.0, 3.0)
        return FormulaBasis(
            family.value,
            (m5, m10, m20, (m5 * m10 * m20) ** (1.0 / 3.0)),
        )
    if family is Cycle002Family.DECELERATION_DISTRIBUTION:
        negative_shock = _ramp(-base.z1, 0.0, 2.5)
        deceleration = _ramp(base.m10 - base.m3, 0.0, 2.5)
        negative_curvature = _ramp(-base.return_curvature, 0.0, 2.5)
        turnover = _ramp(base.turnover_surprise, 0.0, 3.0)
        return FormulaBasis(
            family.value,
            (
                negative_shock,
                deceleration,
                negative_curvature,
                (negative_shock * negative_curvature * turnover) ** (1.0 / 3.0),
            ),
        )
    early_age = _ramp(float(features.active_duration_sessions), 1.0, 6.0)
    mature_age = _ramp(float(features.active_duration_sessions), 3.0, 10.0)
    runup = _ramp(features.cumulative_runup, 1.0, 4.0)
    return FormulaBasis(
        family.value,
        (early_age, mature_age, runup, math.sqrt(mature_age * runup)),
    )


def label_upside_regime_end(
    observations: Sequence[DailyObservation],
    as_of_index: int,
    features: Cycle002Features,
) -> RegimeEndLabel | IneligibleRegimeEndLabel:
    """Label a persistent end of an active upside price regime using future rows."""
    if features.base.as_of_index != as_of_index:
        return IneligibleRegimeEndLabel("feature_as_of_mismatch")
    reproduced = build_cycle002_features(observations, as_of_index)
    if isinstance(reproduced, Cycle002Abstention) or reproduced != features:
        return IneligibleRegimeEndLabel("source_window_mismatch")
    if features.base.m5 < _ACTIVE_M5_THRESHOLD:
        return IneligibleRegimeEndLabel("inactive_upside_regime_at_signal")
    if len(observations) - as_of_index - 1 < _PRIMARY_HORIZON_SESSIONS:
        return IneligibleRegimeEndLabel("insufficient_future")
    current = observations[as_of_index]
    try:
        prior_session = date.fromisoformat(features.base.signal_session_id)
    except ValueError:
        return IneligibleRegimeEndLabel("invalid_future_session_order")
    for offset in range(1, _PRIMARY_HORIZON_SESSIONS + 1):
        future = observations[as_of_index + offset]
        if (
            future.series_id != features.base.series_id
            or future.currency != current.currency
            or not _is_positive_finite(future.adjusted_close)
        ):
            return IneligibleRegimeEndLabel("invalid_future_row")
        try:
            session = date.fromisoformat(str(future.session_id))
        except ValueError:
            return IneligibleRegimeEndLabel("invalid_future_session_order")
        if session <= prior_session:
            return IneligibleRegimeEndLabel("invalid_future_session_order")
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
    end_offset = next(
        (
            offset
            for offset, value in enumerate(
                rolling_momentum[:_END_SEARCH_SESSIONS],
                start=1,
            )
            if value <= 0.0
        ),
        None,
    )
    outcome = end_offset is not None and rolling_momentum[-1] <= 0.0
    return RegimeEndLabel(
        outcome=outcome,
        end_offset_sessions=end_offset if outcome else None,
    )


def hypothetical_avoided_continuation_loss(
    next_session_close: float,
    horizon_close: float,
    *,
    cost_bps: float,
) -> float:
    """Return research-only avoided long loss after an end alarm, net of costs."""
    if (
        not _is_positive_finite(next_session_close)
        or not _is_positive_finite(horizon_close)
        or not math.isfinite(cost_bps)
        or cost_bps < 0.0
    ):
        raise ValueError("hypothetical_economics_input_invalid")
    continuation_return = float(horizon_close) / float(next_session_close) - 1.0
    return -continuation_return - cost_bps / 10_000.0


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
