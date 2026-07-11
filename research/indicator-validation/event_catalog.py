from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd


_FAKE_RELIEF_OUTCOME = "fakeRelief"
_RELIEF_CONFIRMED_OUTCOME = "reliefConfirmed"


@dataclass(frozen=True)
class GroundTruthOrigin:
    ordinal: int
    date: str
    target_offset: int
    target_ordinal: int
    target_date: str


@dataclass(frozen=True)
class GroundTruthEpisode:
    symbol: str
    outcome_id: str
    horizon: int
    origin_ordinal: int
    origin_date: str
    target_offset: int
    target_ordinal: int
    target_date: str
    suppressed_through_ordinal: int
    merged_origins: tuple[GroundTruthOrigin, ...]


@dataclass(frozen=True)
class GroundTruthCatalog:
    symbol: str
    outcome_id: str
    horizon: int
    session_dates: tuple[str, ...]
    episodes: tuple[GroundTruthEpisode, ...]


@dataclass(frozen=True)
class SignalEpisode:
    symbol: str
    candidate_id: str
    outcome_id: str
    horizon: int
    alert_ordinal: int
    alert_date: str
    suppressed_through_ordinal: int


@dataclass(frozen=True)
class SignalCatalog:
    symbol: str
    candidate_id: str
    outcome_id: str
    horizon: int
    session_dates: tuple[str, ...]
    episodes: tuple[SignalEpisode, ...]


@dataclass(frozen=True)
class LeadTimeMatch:
    symbol: str
    candidate_id: str
    outcome_id: str
    horizon: int
    alert_ordinal: int
    alert_date: str
    status: Literal["matched", "lead_time_unavailable"]
    origin_ordinal: int | None
    origin_date: str | None
    target_ordinal: int | None
    target_date: str | None
    lead_time_sessions: int | None


@dataclass(frozen=True)
class UnidentifiablePhase:
    phase: str
    status: Literal["phase_not_identifiable"]
    reason: str


@dataclass(frozen=True)
class PhaseEpisode:
    symbol: str
    outcome_id: str
    horizon: int
    origin_ordinal: int
    origin_date: str
    prodrome_dates: tuple[str, ...]
    start_date: str
    full_target_offset: int
    full_target_date: str
    extreme_offset: int
    extreme_date: str
    confirmation_offset: int | None
    confirmation_date: str | None
    fake_relief_offset: int | None
    fake_relief_date: str | None
    end_offset: int
    end_date: str
    end_reason: Literal["confirmation", "vertical_barrier"]
    phase_not_identifiable: tuple[UnidentifiablePhase, ...]


@dataclass(frozen=True)
class PhaseCatalog:
    symbol: str
    outcome_id: str
    horizon: int
    session_dates: tuple[str, ...]
    episodes: tuple[PhaseEpisode, ...]


@dataclass(frozen=True)
class MarketGroundTruthEvent:
    symbol: str
    outcome_id: str
    horizon: int
    target_direction: Literal["upper", "lower"]
    target_date: str


@dataclass(frozen=True)
class WeightedMarketEvent:
    event: MarketGroundTruthEvent
    global_event_weight: float


@dataclass(frozen=True)
class MarketEventCluster:
    identifier: str
    target_direction: Literal["upper", "lower"]
    representative_target_date: str
    members: tuple[WeightedMarketEvent, ...]


@dataclass
class _GroundTruthAccumulator:
    origin: GroundTruthOrigin
    suppressed_through_ordinal: int
    merged_origins: list[GroundTruthOrigin]


def cluster_market_events(
    events: list[MarketGroundTruthEvent],
) -> tuple[MarketEventCluster, ...]:
    """Apply the frozen greedy, non-chaining calendar-day clustering rule."""
    ordered = sorted(
        events,
        key=lambda event: (
            event.target_date,
            event.symbol,
            event.outcome_id,
            event.horizon,
        ),
    )
    parsed_dates = [_validated_market_event(event) for event in ordered]
    assigned = [False] * len(ordered)
    clusters: list[MarketEventCluster] = []
    for anchor_index, anchor in enumerate(ordered):
        if assigned[anchor_index]:
            continue
        anchor_date = parsed_dates[anchor_index]
        member_indexes = [anchor_index]
        assigned[anchor_index] = True
        for candidate_index in range(anchor_index + 1, len(ordered)):
            candidate = ordered[candidate_index]
            member_symbols = {ordered[index].symbol for index in member_indexes}
            if (
                assigned[candidate_index]
                or candidate.target_direction != anchor.target_direction
                or candidate.outcome_id != anchor.outcome_id
                or candidate.horizon != anchor.horizon
                or candidate.symbol in member_symbols
            ):
                continue
            if abs((parsed_dates[candidate_index] - anchor_date).days) <= 1:
                assigned[candidate_index] = True
                member_indexes.append(candidate_index)
        cluster_size = len(member_indexes)
        clusters.append(
            MarketEventCluster(
                identifier=f"market-cluster-{len(clusters) + 1:04d}",
                target_direction=anchor.target_direction,
                representative_target_date=anchor.target_date,
                members=tuple(
                    WeightedMarketEvent(
                        event=ordered[index],
                        global_event_weight=1.0 / cluster_size,
                    )
                    for index in member_indexes
                ),
            )
        )
    return tuple(clusters)


def _validated_market_event(event: MarketGroundTruthEvent) -> date:
    _require_non_blank(event.symbol, "Symbol")
    _require_non_blank(event.outcome_id, "Outcome identifier")
    _require_positive_horizon(event.horizon)
    if event.target_direction not in {"upper", "lower"}:
        raise ValueError("Market event target direction is invalid")
    try:
        return date.fromisoformat(event.target_date)
    except (TypeError, ValueError) as error:
        raise ValueError("Market event target date is invalid") from error


def build_ground_truth_catalog(
    symbol: str,
    outcome_id: str,
    horizon: int,
    label_frame: pd.DataFrame,
) -> GroundTruthCatalog:
    """Build candidate-independent episodes on the complete actual-session axis."""
    _require_non_blank(symbol, "Symbol")
    _require_non_blank(outcome_id, "Outcome identifier")
    _require_positive_horizon(horizon)
    session_dates = _actual_session_dates(label_frame.index)
    required_columns = {"status", "label", "firstPassageOffset"}
    if outcome_id == _FAKE_RELIEF_OUTCOME:
        required_columns.add("terminalOffset")
    _require_columns(label_frame, required_columns)

    retained: list[_GroundTruthAccumulator] = []
    for ordinal, (_, row) in enumerate(label_frame.iterrows()):
        if not _is_success(row):
            continue
        origin = _ground_truth_origin(
            ordinal,
            session_dates,
            _target_offset_value(outcome_id, row),
            horizon,
        )
        if retained and ordinal <= retained[-1].suppressed_through_ordinal:
            retained[-1].merged_origins.append(origin)
            continue
        retained.append(
            _GroundTruthAccumulator(
                origin=origin,
                suppressed_through_ordinal=ordinal + horizon,
                merged_origins=[],
            )
        )

    episodes = tuple(
        _to_ground_truth_episode(symbol, outcome_id, horizon, entry)
        for entry in retained
    )
    return GroundTruthCatalog(
        symbol=symbol,
        outcome_id=outcome_id,
        horizon=horizon,
        session_dates=session_dates,
        episodes=episodes,
    )


def build_signal_catalog(
    symbol: str,
    candidate_id: str,
    outcome_id: str,
    horizon: int,
    alerts: pd.Series,
) -> SignalCatalog:
    """Build raw signal episodes without accepting or inspecting future labels."""
    _require_non_blank(symbol, "Symbol")
    _require_non_blank(candidate_id, "Candidate identifier")
    _require_non_blank(outcome_id, "Outcome identifier")
    _require_positive_horizon(horizon)
    session_dates = _actual_session_dates(alerts.index)

    episodes: list[SignalEpisode] = []
    suppressed_through_ordinal = -1
    previous_alert = False
    for ordinal, value in enumerate(alerts.to_numpy(dtype=object)):
        current_alert = _read_alert(value)
        upward_crossing = current_alert and not previous_alert
        if upward_crossing and ordinal > suppressed_through_ordinal:
            episodes.append(
                SignalEpisode(
                    symbol=symbol,
                    candidate_id=candidate_id,
                    outcome_id=outcome_id,
                    horizon=horizon,
                    alert_ordinal=ordinal,
                    alert_date=session_dates[ordinal],
                    suppressed_through_ordinal=ordinal + horizon,
                )
            )
            suppressed_through_ordinal = ordinal + horizon
        previous_alert = current_alert

    return SignalCatalog(
        symbol=symbol,
        candidate_id=candidate_id,
        outcome_id=outcome_id,
        horizon=horizon,
        session_dates=session_dates,
        episodes=tuple(episodes),
    )


def match_lead_times(
    signal_catalog: SignalCatalog,
    ground_truth_catalog: GroundTruthCatalog,
) -> tuple[LeadTimeMatch, ...]:
    """Match each alert to the earliest eligible candidate-independent target."""
    _require_matching_catalog_scope(signal_catalog, ground_truth_catalog)
    matches: list[LeadTimeMatch] = []
    for signal in signal_catalog.episodes:
        eligible_targets = [
            episode
            for episode in ground_truth_catalog.episodes
            if signal.alert_ordinal
            <= episode.target_ordinal
            <= signal.alert_ordinal + signal.horizon
        ]
        target = min(
            eligible_targets,
            key=lambda episode: (episode.target_ordinal, episode.origin_ordinal),
            default=None,
        )
        matches.append(_lead_time_match(signal, target))
    return tuple(matches)


def build_phase_catalog(
    ground_truth_catalog: GroundTruthCatalog,
    label_frame: pd.DataFrame,
    prior_session_dates: tuple[str, ...] = (),
) -> PhaseCatalog:
    """Describe only phases whose dates are fixed by the registered label frame."""
    session_dates = _actual_session_dates(label_frame.index)
    if session_dates != ground_truth_catalog.session_dates:
        raise ValueError("Phase labels and ground truth must share an actual-session axis")
    _require_columns(label_frame, {"firstPassageOffset"})
    _validate_prior_session_dates(prior_session_dates, session_dates)

    episodes = tuple(
        _phase_episode(
            ground_truth_catalog,
            episode,
            label_frame,
            prior_session_dates,
        )
        for episode in ground_truth_catalog.episodes
    )
    return PhaseCatalog(
        symbol=ground_truth_catalog.symbol,
        outcome_id=ground_truth_catalog.outcome_id,
        horizon=ground_truth_catalog.horizon,
        session_dates=session_dates,
        episodes=episodes,
    )


def _phase_episode(
    catalog: GroundTruthCatalog,
    episode: GroundTruthEpisode,
    label_frame: pd.DataFrame,
    prior_session_dates: tuple[str, ...],
) -> PhaseEpisode:
    row = label_frame.iloc[episode.origin_ordinal]
    if not _is_success(row):
        raise ValueError("Phase origin does not match its ground truth episode")
    phase_target_offset = _positive_session_offset(
        _target_offset_value(catalog.outcome_id, row)
    )
    if phase_target_offset != episode.target_offset:
        raise ValueError("Phase origin does not match its ground truth episode")
    full_target_offset = _phase_offset(
        row,
        "firstPassageOffset",
        catalog.horizon,
        required=True,
    )
    assert full_target_offset is not None
    full_target_date = _session_date_at_offset(
        catalog.session_dates,
        episode.origin_ordinal,
        full_target_offset,
    )
    confirmation_offset = _phase_offset(
        row,
        "confirmationOffset",
        catalog.horizon,
        required=catalog.outcome_id == _RELIEF_CONFIRMED_OUTCOME,
    )
    fake_relief_offset = (
        _phase_offset(
            row,
            "terminalOffset",
            catalog.horizon,
            required=True,
        )
        if catalog.outcome_id == _FAKE_RELIEF_OUTCOME
        else None
    )
    end_offset = (
        confirmation_offset if confirmation_offset is not None else catalog.horizon
    )
    end_reason: Literal["confirmation", "vertical_barrier"] = (
        "confirmation"
        if confirmation_offset is not None
        else "vertical_barrier"
    )
    context_dates = prior_session_dates + catalog.session_dates
    context_origin_ordinal = len(prior_session_dates) + episode.origin_ordinal
    return PhaseEpisode(
        symbol=catalog.symbol,
        outcome_id=catalog.outcome_id,
        horizon=catalog.horizon,
        origin_ordinal=episode.origin_ordinal,
        origin_date=episode.origin_date,
        prodrome_dates=context_dates[
            max(0, context_origin_ordinal - 5) : context_origin_ordinal
        ],
        start_date=episode.origin_date,
        full_target_offset=full_target_offset,
        full_target_date=full_target_date,
        extreme_offset=full_target_offset,
        extreme_date=full_target_date,
        confirmation_offset=confirmation_offset,
        confirmation_date=_optional_session_date(
            catalog.session_dates,
            episode.origin_ordinal,
            confirmation_offset,
        ),
        fake_relief_offset=fake_relief_offset,
        fake_relief_date=_optional_session_date(
            catalog.session_dates,
            episode.origin_ordinal,
            fake_relief_offset,
        ),
        end_offset=end_offset,
        end_date=_session_date_at_offset(
            catalog.session_dates,
            episode.origin_ordinal,
            end_offset,
        ),
        end_reason=end_reason,
        phase_not_identifiable=(
            UnidentifiablePhase(
                "early",
                "phase_not_identifiable",
                "half_barrier_rule_unspecified",
            ),
            UnidentifiablePhase(
                "middle",
                "phase_not_identifiable",
                "half_barrier_rule_unspecified",
            ),
            UnidentifiablePhase(
                "firstRebound",
                "phase_not_identifiable",
                "rebound_rule_unspecified",
            ),
        ),
    )


def _lead_time_match(
    signal: SignalEpisode,
    target: GroundTruthEpisode | None,
) -> LeadTimeMatch:
    if target is None:
        return LeadTimeMatch(
            symbol=signal.symbol,
            candidate_id=signal.candidate_id,
            outcome_id=signal.outcome_id,
            horizon=signal.horizon,
            alert_ordinal=signal.alert_ordinal,
            alert_date=signal.alert_date,
            status="lead_time_unavailable",
            origin_ordinal=None,
            origin_date=None,
            target_ordinal=None,
            target_date=None,
            lead_time_sessions=None,
        )
    return LeadTimeMatch(
        symbol=signal.symbol,
        candidate_id=signal.candidate_id,
        outcome_id=signal.outcome_id,
        horizon=signal.horizon,
        alert_ordinal=signal.alert_ordinal,
        alert_date=signal.alert_date,
        status="matched",
        origin_ordinal=target.origin_ordinal,
        origin_date=target.origin_date,
        target_ordinal=target.target_ordinal,
        target_date=target.target_date,
        lead_time_sessions=target.target_ordinal - signal.alert_ordinal,
    )


def _require_matching_catalog_scope(
    signals: SignalCatalog,
    ground_truth: GroundTruthCatalog,
) -> None:
    signal_scope = (signals.symbol, signals.outcome_id, signals.horizon)
    ground_truth_scope = (
        ground_truth.symbol,
        ground_truth.outcome_id,
        ground_truth.horizon,
    )
    if signal_scope != ground_truth_scope:
        raise ValueError("Signal and ground-truth catalog scopes must match")
    if signals.session_dates != ground_truth.session_dates:
        raise ValueError("Signal and ground-truth actual-session axes must match")


def _to_ground_truth_episode(
    symbol: str,
    outcome_id: str,
    horizon: int,
    entry: _GroundTruthAccumulator,
) -> GroundTruthEpisode:
    return GroundTruthEpisode(
        symbol=symbol,
        outcome_id=outcome_id,
        horizon=horizon,
        origin_ordinal=entry.origin.ordinal,
        origin_date=entry.origin.date,
        target_offset=entry.origin.target_offset,
        target_ordinal=entry.origin.target_ordinal,
        target_date=entry.origin.target_date,
        suppressed_through_ordinal=entry.suppressed_through_ordinal,
        merged_origins=tuple(entry.merged_origins),
    )


def _ground_truth_origin(
    ordinal: int,
    session_dates: tuple[str, ...],
    offset_value: object,
    horizon: int,
) -> GroundTruthOrigin:
    target_offset = _positive_session_offset(offset_value)
    if target_offset > horizon:
        raise ValueError("Successful origin target offset exceeds its horizon")
    target_ordinal = ordinal + target_offset
    if target_ordinal >= len(session_dates):
        raise ValueError("Successful origin target falls outside the label frame")
    return GroundTruthOrigin(
        ordinal=ordinal,
        date=session_dates[ordinal],
        target_offset=target_offset,
        target_ordinal=target_ordinal,
        target_date=session_dates[target_ordinal],
    )


def _target_offset_value(outcome_id: str, row: pd.Series) -> object:
    if outcome_id == _FAKE_RELIEF_OUTCOME:
        return row["terminalOffset"]
    return row["firstPassageOffset"]


def _phase_offset(
    row: pd.Series,
    column: str,
    horizon: int,
    required: bool,
) -> int | None:
    if column not in row.index or pd.isna(row[column]):
        if required:
            raise ValueError(f"Successful phase requires {column}")
        return None
    offset = _positive_session_offset(row[column])
    if offset > horizon:
        raise ValueError(f"Successful phase {column} exceeds its horizon")
    return offset


def _session_date_at_offset(
    session_dates: tuple[str, ...],
    origin_ordinal: int,
    offset: int,
) -> str:
    target_ordinal = origin_ordinal + offset
    if target_ordinal >= len(session_dates):
        raise ValueError("Phase offset falls outside the label frame")
    return session_dates[target_ordinal]


def _optional_session_date(
    session_dates: tuple[str, ...],
    origin_ordinal: int,
    offset: int | None,
) -> str | None:
    if offset is None:
        return None
    return _session_date_at_offset(session_dates, origin_ordinal, offset)


def _is_success(row: pd.Series) -> bool:
    status_success = row["status"] == "success"
    label = row["label"]
    if pd.isna(label):
        label_success = False
    else:
        try:
            numeric_label = float(label)
        except (TypeError, ValueError) as error:
            raise ValueError("Observed outcome requires a binary label") from error
        if not np.isfinite(numeric_label) or numeric_label not in {0.0, 1.0}:
            raise ValueError("Observed outcome requires a binary label")
        label_success = numeric_label == 1.0
    if status_success != label_success:
        raise ValueError("Success status and binary label disagree")
    return status_success


def _read_alert(value: object) -> bool:
    if pd.isna(value):
        return False
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError("Raw alerts must be boolean or unavailable")
    return bool(value)


def _positive_session_offset(value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or pd.isna(value):
        raise ValueError("Successful origin requires a positive target offset")
    numeric = float(value)
    if not np.isfinite(numeric) or numeric < 1.0 or not numeric.is_integer():
        raise ValueError("Successful origin requires a positive target offset")
    return int(numeric)


def _actual_session_dates(index: pd.Index) -> tuple[str, ...]:
    if len(index) == 0:
        raise ValueError("Actual-session index must not be empty")
    if index.has_duplicates:
        raise ValueError("Actual-session index must contain unique dates")
    try:
        timestamps = pd.DatetimeIndex(pd.to_datetime(index, utc=True, errors="raise"))
    except (TypeError, ValueError) as error:
        raise ValueError("Actual-session index must contain valid dates") from error
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Actual-session index must be chronological")
    dates = tuple(timestamp.date().isoformat() for timestamp in timestamps)
    if len(set(dates)) != len(dates):
        raise ValueError("Actual-session index must contain one row per trading date")
    return dates


def _validate_prior_session_dates(
    prior_session_dates: tuple[str, ...],
    session_dates: tuple[str, ...],
) -> None:
    try:
        parsed = tuple(date.fromisoformat(value) for value in prior_session_dates)
    except (TypeError, ValueError) as error:
        raise ValueError("Prior session dates must be ISO calendar dates") from error
    if tuple(sorted(parsed)) != parsed or len(set(parsed)) != len(parsed):
        raise ValueError("Prior session dates must be unique and chronological")
    if parsed and parsed[-1] >= date.fromisoformat(session_dates[0]):
        raise ValueError("Prior session dates must precede the analysis window")


def _require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Label frame is missing columns: {sorted(missing)}")


def _require_non_blank(value: str, description: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be non-blank")


def _require_positive_horizon(horizon: int) -> None:
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("Episode horizon must be a positive integer")
