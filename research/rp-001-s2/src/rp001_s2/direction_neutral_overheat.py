"""Direction-neutral intraday overheat screening, episodes, and labels."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from types import MappingProxyType


_HISTORICAL_SESSION_COUNT = 60
_MINIMUM_FAMILY_OBSERVATIONS = 40
_MAXIMUM_SAME_BURST_GAP = 30
_EPISODE_CLOSE_INACTIVE_MINUTES = 60
_ROBUST_SIGMA_NORMALIZATION = 1.4826
_MINIMUM_SIGMA_OBSERVATIONS = 40
_BARRIER_SIGMA_MULTIPLE = 2.0


class ScreenState(str, Enum):
    CANDIDATE = "candidate"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class LabelHorizon(str, Enum):
    MINUTES_5 = "5m"
    MINUTES_30 = "30m"
    MINUTES_120 = "120m"
    SESSION_1 = "1S"


_HORIZON_MARKET_MINUTES: Mapping[LabelHorizon, int] = MappingProxyType(
    {
        LabelHorizon.MINUTES_5: 5,
        LabelHorizon.MINUTES_30: 30,
        LabelHorizon.MINUTES_120: 120,
        LabelHorizon.SESSION_1: 390,
    }
)


class PassageLabel(str, Enum):
    UP_FIRST = "up_first"
    DOWN_FIRST = "down_first"
    BOTH_SAME_MINUTE = "both_same_minute"
    NO_PASSAGE = "no_passage"
    CENSORED = "censored"
    SIGMA_NOT_ESTIMABLE = "sigma_not_estimable"


@dataclass(frozen=True)
class DirectionNeutralObservation:
    symbol: str
    session_ordinal: int
    minute_of_day: int
    market_minute_ordinal: int
    minute_end_utc: datetime
    available_at_utc: datetime
    session_id: str
    session_date: date
    source_window_sha256: str
    signed_return: float
    log_low: float
    log_high: float
    log_close: float
    family_scores: Mapping[str, float | None]

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("observation_symbol_invalid")
        if not _is_nonnegative_integer(self.session_ordinal):
            raise ValueError("observation_session_ordinal_invalid")
        if not _is_nonnegative_integer(self.minute_of_day) or self.minute_of_day >= 1_440:
            raise ValueError("observation_minute_of_day_invalid")
        if not _is_nonnegative_integer(self.market_minute_ordinal):
            raise ValueError("observation_market_minute_ordinal_invalid")
        if not _is_utc_datetime(self.minute_end_utc) or not _is_utc_datetime(
            self.available_at_utc
        ) or self.available_at_utc < self.minute_end_utc:
            raise ValueError("observation_timestamp_invalid")
        if (
            type(self.session_id) is not str
            or not self.session_id
            or self.session_id != self.session_id.strip()
        ):
            raise ValueError("observation_session_invalid")
        if type(self.session_date) is not date:
            raise ValueError("observation_session_invalid")
        if not _is_sha256(self.source_window_sha256):
            raise ValueError("observation_source_window_sha256_invalid")
        prices = (self.signed_return, self.log_low, self.log_high, self.log_close)
        if any(not _is_finite_number(value) for value in prices):
            raise ValueError("observation_price_invalid")
        if not self.log_low <= self.log_close <= self.log_high:
            raise ValueError("observation_price_invalid")
        if not isinstance(self.family_scores, Mapping) or not self.family_scores:
            raise ValueError("observation_family_scores_invalid")

        normalized_scores: dict[str, float | None] = {}
        for family, score in self.family_scores.items():
            if type(family) is not str or not family or family != family.strip():
                raise ValueError("observation_family_scores_invalid")
            if score is not None and (
                not _is_finite_number(score) or float(score) < 0.0
            ):
                raise ValueError("observation_family_scores_invalid")
            normalized_scores[family] = None if score is None else float(score)
        object.__setattr__(
            self,
            "family_scores",
            MappingProxyType(dict(sorted(normalized_scores.items()))),
        )


@dataclass(frozen=True)
class FamilyScreen:
    family: str
    observation_count: int
    score: float | None
    p99: float | None
    p999: float | None
    exceeds_p99: bool | None
    exceeds_p999: bool | None

    @property
    def available(self) -> bool:
        return (
            self.score is not None
            and self.p99 is not None
            and self.p999 is not None
        )


@dataclass(frozen=True)
class ScreeningResult:
    observation: DirectionNeutralObservation
    state: ScreenState
    family_screens: tuple[FamilyScreen, ...]


@dataclass(frozen=True)
class OverheatBurst:
    candidate_market_minute_ordinals: tuple[int, ...]

    @property
    def start_market_minute_ordinal(self) -> int:
        return self.candidate_market_minute_ordinals[0]

    @property
    def end_market_minute_ordinal(self) -> int:
        return self.candidate_market_minute_ordinals[-1]


@dataclass(frozen=True)
class OverheatEpisode:
    anchor: DirectionNeutralObservation
    bursts: tuple[OverheatBurst, ...]
    closed_at_market_minute_ordinal: int | None
    coverage_complete: bool
    right_censored: bool

    @property
    def start_market_minute_ordinal(self) -> int:
        return self.anchor.market_minute_ordinal


@dataclass(frozen=True)
class FirstPassageResult:
    horizon: LabelHorizon
    label: PassageLabel
    sigma: float | None
    sigma_horizon_market_minutes: int
    lower_barrier: float | None
    upper_barrier: float | None
    passage_market_minute_ordinal: int | None
    horizon_end_market_minute_ordinal: int | None


@dataclass
class _OpenEpisode:
    anchor: DirectionNeutralObservation
    burst_ordinals: list[list[int]]
    last_candidate_ordinal: int
    consecutive_inactive_minutes: int = 0
    coverage_complete: bool = True

    @classmethod
    def start(cls, observation: DirectionNeutralObservation) -> _OpenEpisode:
        ordinal = observation.market_minute_ordinal
        return cls(
            anchor=observation,
            burst_ordinals=[[ordinal]],
            last_candidate_ordinal=ordinal,
        )

    def add_candidate(self, observation: DirectionNeutralObservation) -> None:
        ordinal = observation.market_minute_ordinal
        if ordinal - self.last_candidate_ordinal <= _MAXIMUM_SAME_BURST_GAP:
            self.burst_ordinals[-1].append(ordinal)
        else:
            self.burst_ordinals.append([ordinal])
        self.last_candidate_ordinal = ordinal
        self.consecutive_inactive_minutes = 0

    def add_inactive_minute(self) -> None:
        self.consecutive_inactive_minutes += 1

    def mark_unknown(self) -> None:
        self.coverage_complete = False
        self.consecutive_inactive_minutes = 0

    def result(self, closed_at: int | None) -> OverheatEpisode:
        return OverheatEpisode(
            anchor=self.anchor,
            bursts=tuple(
                OverheatBurst(tuple(ordinals)) for ordinals in self.burst_ordinals
            ),
            closed_at_market_minute_ordinal=closed_at,
            coverage_complete=self.coverage_complete,
            right_censored=closed_at is None,
        )


def screen_observation(
    target: DirectionNeutralObservation,
    observations: Sequence[DirectionNeutralObservation],
) -> ScreeningResult:
    """Screen one observation without using its session or any future session."""
    if not isinstance(target, DirectionNeutralObservation):
        raise ValueError("screen_target_invalid")
    values = tuple(observations)
    if any(not isinstance(value, DirectionNeutralObservation) for value in values):
        raise ValueError("screen_history_invalid")

    history = _comparable_history(target, values)
    family_universe = tuple(
        sorted(
            {
                family
                for observation in (target,) + history
                for family in observation.family_scores
            }
        )
    )
    family_screens = tuple(
        _screen_family(family, target.family_scores.get(family), history)
        for family in family_universe
    )
    p99_count = sum(screen.exceeds_p99 is True for screen in family_screens)
    p999_count = sum(screen.exceeds_p999 is True for screen in family_screens)
    if p99_count >= 2 or p999_count >= 1:
        state = ScreenState.CANDIDATE
    elif all(screen.available for screen in family_screens):
        state = ScreenState.INACTIVE
    else:
        state = ScreenState.UNKNOWN
    return ScreeningResult(
        observation=target,
        state=state,
        family_screens=family_screens,
    )


def group_episodes(
    screening_results: Sequence[ScreeningResult],
) -> tuple[OverheatEpisode, ...]:
    """Group candidate minutes using tradable-minute ordinals only."""
    values = tuple(screening_results)
    if any(not isinstance(result, ScreeningResult) for result in values):
        raise ValueError("episode_screening_result_invalid")
    if len({result.observation.symbol for result in values}) > 1:
        raise ValueError("episode_symbol_mismatch")
    ordered = tuple(
        sorted(
            values,
            key=lambda result: result.observation.market_minute_ordinal,
        )
    )
    ordinals = tuple(
        result.observation.market_minute_ordinal for result in ordered
    )
    if len(ordinals) != len(set(ordinals)):
        raise ValueError("episode_market_minute_duplicate")

    episodes: list[OverheatEpisode] = []
    current: _OpenEpisode | None = None
    previous_ordinal: int | None = None
    for result in ordered:
        ordinal = result.observation.market_minute_ordinal
        if (
            current is not None
            and previous_ordinal is not None
            and ordinal != previous_ordinal + 1
        ):
            current.mark_unknown()

        if result.state is ScreenState.CANDIDATE:
            if current is None:
                current = _OpenEpisode.start(result.observation)
            else:
                current.add_candidate(result.observation)
        elif current is not None and result.state is ScreenState.UNKNOWN:
            current.mark_unknown()
        elif current is not None and result.state is ScreenState.INACTIVE:
            current.add_inactive_minute()
            if (
                current.consecutive_inactive_minutes
                == _EPISODE_CLOSE_INACTIVE_MINUTES
            ):
                episodes.append(current.result(closed_at=ordinal))
                current = None
        elif not isinstance(result.state, ScreenState):
            raise ValueError("episode_screen_state_invalid")
        previous_ordinal = ordinal

    if current is not None:
        episodes.append(current.result(closed_at=None))
    return tuple(episodes)


def label_first_passage(
    anchor: DirectionNeutralObservation,
    observations: Sequence[DirectionNeutralObservation],
    horizon: LabelHorizon,
) -> FirstPassageResult:
    """Label passage with pre-anchor one-minute MAD scaled by sqrt(horizon)."""
    if not isinstance(anchor, DirectionNeutralObservation):
        raise ValueError("label_anchor_invalid")
    if not isinstance(horizon, LabelHorizon):
        raise ValueError("label_horizon_invalid")
    values = tuple(observations)
    if any(not isinstance(value, DirectionNeutralObservation) for value in values):
        raise ValueError("label_observation_invalid")

    same_symbol = tuple(value for value in values if value.symbol == anchor.symbol)
    sigma = _ex_ante_sigma(anchor, same_symbol, horizon)
    if sigma is None:
        return FirstPassageResult(
            horizon=horizon,
            label=PassageLabel.SIGMA_NOT_ESTIMABLE,
            sigma=None,
            sigma_horizon_market_minutes=_horizon_market_minutes(horizon),
            lower_barrier=None,
            upper_barrier=None,
            passage_market_minute_ordinal=None,
            horizon_end_market_minute_ordinal=None,
        )

    lower_barrier = anchor.log_close - _BARRIER_SIGMA_MULTIPLE * sigma
    upper_barrier = anchor.log_close + _BARRIER_SIGMA_MULTIPLE * sigma
    horizon_end = _horizon_end_ordinal(anchor, same_symbol, horizon)
    if horizon_end is None:
        return _passage_result(
            horizon=horizon,
            label=PassageLabel.CENSORED,
            sigma=sigma,
            lower_barrier=lower_barrier,
            upper_barrier=upper_barrier,
            passage_ordinal=None,
            horizon_end=None,
        )

    future_by_ordinal = _future_by_ordinal(anchor, same_symbol, horizon_end)
    for ordinal in range(anchor.market_minute_ordinal + 1, horizon_end + 1):
        future = future_by_ordinal.get(ordinal)
        if future is None:
            return _passage_result(
                horizon=horizon,
                label=PassageLabel.CENSORED,
                sigma=sigma,
                lower_barrier=lower_barrier,
                upper_barrier=upper_barrier,
                passage_ordinal=None,
                horizon_end=horizon_end,
            )
        passage = _barrier_passage(future, lower_barrier, upper_barrier)
        if passage is not None:
            return _passage_result(
                horizon=horizon,
                label=passage,
                sigma=sigma,
                lower_barrier=lower_barrier,
                upper_barrier=upper_barrier,
                passage_ordinal=ordinal,
                horizon_end=horizon_end,
            )
    return _passage_result(
        horizon=horizon,
        label=PassageLabel.NO_PASSAGE,
        sigma=sigma,
        lower_barrier=lower_barrier,
        upper_barrier=upper_barrier,
        passage_ordinal=None,
        horizon_end=horizon_end,
    )


def _comparable_history(
    target: DirectionNeutralObservation,
    observations: tuple[DirectionNeutralObservation, ...],
) -> tuple[DirectionNeutralObservation, ...]:
    first_session = target.session_ordinal - _HISTORICAL_SESSION_COUNT
    history = tuple(
        sorted(
            (
                observation
                for observation in observations
                if observation.symbol == target.symbol
                and observation.minute_of_day == target.minute_of_day
                and first_session
                <= observation.session_ordinal
                < target.session_ordinal
                and observation.minute_end_utc <= target.available_at_utc
                and observation.available_at_utc <= target.available_at_utc
            ),
            key=lambda observation: observation.session_ordinal,
        )
    )
    session_ordinals = tuple(value.session_ordinal for value in history)
    if len(session_ordinals) != len(set(session_ordinals)):
        raise ValueError("screen_history_duplicate_session")
    return history


def _screen_family(
    family: str,
    score: float | None,
    history: tuple[DirectionNeutralObservation, ...],
) -> FamilyScreen:
    historical_scores = tuple(
        value
        for observation in history
        if (value := observation.family_scores.get(family)) is not None
    )
    if len(historical_scores) < _MINIMUM_FAMILY_OBSERVATIONS:
        return FamilyScreen(
            family=family,
            observation_count=len(historical_scores),
            score=score,
            p99=None,
            p999=None,
            exceeds_p99=None,
            exceeds_p999=None,
        )
    p99 = _type7_quantile(historical_scores, 0.99)
    p999 = _type7_quantile(historical_scores, 0.999)
    return FamilyScreen(
        family=family,
        observation_count=len(historical_scores),
        score=score,
        p99=p99,
        p999=p999,
        exceeds_p99=None if score is None else score > p99,
        exceeds_p999=None if score is None else score > p999,
    )


def _ex_ante_sigma(
    anchor: DirectionNeutralObservation,
    observations: tuple[DirectionNeutralObservation, ...],
    horizon: LabelHorizon,
) -> float | None:
    historical_returns = tuple(
        observation.signed_return
        for observation in observations
        if observation.market_minute_ordinal < anchor.market_minute_ordinal
        and observation.minute_end_utc <= anchor.available_at_utc
        and observation.available_at_utc <= anchor.available_at_utc
    )
    if len(historical_returns) < _MINIMUM_SIGMA_OBSERVATIONS:
        return None
    center = _median(historical_returns)
    mad = _median(tuple(abs(value - center) for value in historical_returns))
    sigma = (
        _ROBUST_SIGMA_NORMALIZATION
        * mad
        * math.sqrt(float(_horizon_market_minutes(horizon)))
    )
    return sigma if math.isfinite(sigma) and sigma > 0.0 else None


def _horizon_end_ordinal(
    anchor: DirectionNeutralObservation,
    observations: tuple[DirectionNeutralObservation, ...],
    horizon: LabelHorizon,
) -> int | None:
    if horizon is not LabelHorizon.SESSION_1:
        return anchor.market_minute_ordinal + _horizon_market_minutes(horizon)
    endpoints = tuple(
        observation
        for observation in observations
        if observation.session_ordinal == anchor.session_ordinal + 1
        and observation.minute_of_day == anchor.minute_of_day
        and observation.market_minute_ordinal > anchor.market_minute_ordinal
    )
    if len(endpoints) > 1:
        raise ValueError("label_session_endpoint_duplicate")
    return None if not endpoints else endpoints[0].market_minute_ordinal


def _future_by_ordinal(
    anchor: DirectionNeutralObservation,
    observations: tuple[DirectionNeutralObservation, ...],
    horizon_end: int,
) -> dict[int, DirectionNeutralObservation]:
    future: dict[int, DirectionNeutralObservation] = {}
    for observation in observations:
        ordinal = observation.market_minute_ordinal
        if not anchor.market_minute_ordinal < ordinal <= horizon_end:
            continue
        if ordinal in future:
            raise ValueError("label_future_market_minute_duplicate")
        if observation.minute_end_utc <= anchor.minute_end_utc:
            raise ValueError("label_future_temporal_order_invalid")
        if observation.minute_end_utc <= anchor.available_at_utc:
            continue
        future[ordinal] = observation
    return future


def _barrier_passage(
    observation: DirectionNeutralObservation,
    lower_barrier: float,
    upper_barrier: float,
) -> PassageLabel | None:
    crossed_up = observation.log_high >= upper_barrier
    crossed_down = observation.log_low <= lower_barrier
    if crossed_up and crossed_down:
        return PassageLabel.BOTH_SAME_MINUTE
    if crossed_up:
        return PassageLabel.UP_FIRST
    if crossed_down:
        return PassageLabel.DOWN_FIRST
    return None


def _passage_result(
    *,
    horizon: LabelHorizon,
    label: PassageLabel,
    sigma: float,
    lower_barrier: float,
    upper_barrier: float,
    passage_ordinal: int | None,
    horizon_end: int | None,
) -> FirstPassageResult:
    return FirstPassageResult(
        horizon=horizon,
        label=label,
        sigma=sigma,
        sigma_horizon_market_minutes=_horizon_market_minutes(horizon),
        lower_barrier=lower_barrier,
        upper_barrier=upper_barrier,
        passage_market_minute_ordinal=passage_ordinal,
        horizon_end_market_minute_ordinal=horizon_end,
    )


def _horizon_market_minutes(horizon: LabelHorizon) -> int:
    return _HORIZON_MARKET_MINUTES[horizon]


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


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _is_nonnegative_integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _is_utc_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
