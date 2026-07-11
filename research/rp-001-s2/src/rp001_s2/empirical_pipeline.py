"""Research-only direction-neutral minute archive empirical pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

from rp001_s2.archive_contract import CollectionScope
from rp001_s2.direction_neutral_overheat import (
    CompetitivePathLabel,
    CompetitivePathResult,
    DirectionNeutralObservation,
    LabelHorizon,
    OverheatEpisode,
    ScreeningResult,
    group_episodes,
    label_competitive_path,
    screen_observation,
)
from rp001_s2.archive_storage import CanonicalMinuteBar
from rp001_s2.empirical_archive_loader import (
    VerifiedDailySeries,
    load_verified_daily_series,
    require_development_scopes,
)
from rp001_s2.overheat_features import (
    DirectionNeutralFeatureDataset,
    FeatureBuildError,
    FeatureMarket,
    FeatureSession,
    build_direction_neutral_features,
)
from rp001_s2.overheat_oof import (
    FAMILY_NAMES,
    CompetitivePathExample,
    ExcludedOOFRow,
    FamilyThresholdFlags,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ANALYSIS_INPUT_SCHEMA = "rp001-s2-direction-neutral-analysis-input.v1"
_EXAMPLE_EVIDENCE_SCHEMA = "rp001-s2-competitive-path-example-evidence.v1"
_PIPELINE_EVIDENCE_SCHEMA = "rp001-s2-empirical-pipeline-evidence.v1"


class EmpiricalPipelineError(ValueError):
    """Stable empirical transformation refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EpisodeCompetitivePath:
    episode: OverheatEpisode
    screening: ScreeningResult
    label: CompetitivePathResult
    example: CompetitivePathExample | None
    source_evidence_sha256: str


class ExcludedEpisodeReason(str, Enum):
    FAMILY_CONTRACT_MISMATCH = "family_contract_mismatch"
    FAMILY_THRESHOLD_UNAVAILABLE = "family_threshold_unavailable"
    INTRABAR_RANGE_UNAVAILABLE = "intrabar_range_unavailable"


@dataclass(frozen=True)
class ExcludedEpisode:
    row_id: str
    symbol: str
    session_id: str
    horizon: LabelHorizon
    label: CompetitivePathLabel
    reason: ExcludedEpisodeReason
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason, ExcludedEpisodeReason):
            raise ValueError("excluded_episode_reason_invalid")


@dataclass(frozen=True)
class SeriesSessionCoverage:
    symbol: str
    session_date: date
    regular_minutes: int
    observed_offsets: tuple[int, ...]
    missing_offsets: tuple[int, ...]
    unexpected_offsets: tuple[int, ...]
    duplicate_offsets: tuple[int, ...]
    complete: bool
    source_evidence_sha256: str


@dataclass(frozen=True)
class CommonSessionCoverageEntry:
    session: FeatureSession
    target: SeriesSessionCoverage
    benchmark: SeriesSessionCoverage
    included: bool
    source_evidence_sha256: str


@dataclass(frozen=True)
class CommonSessionCoverageLedger:
    entries: tuple[CommonSessionCoverageEntry, ...]
    included_sessions: tuple[FeatureSession, ...]
    excluded_sessions: tuple[FeatureSession, ...]
    source_evidence_sha256: str


@dataclass(frozen=True)
class DirectionNeutralDatasetAnalysis:
    screening_results: tuple[ScreeningResult, ...]
    episodes: tuple[OverheatEpisode, ...]
    episode_results: tuple[EpisodeCompetitivePath, ...]
    examples: tuple[CompetitivePathExample, ...]
    excluded_episodes: tuple[ExcludedEpisode, ...]
    source_evidence_sha256: str

    @property
    def excluded_episode_count(self) -> int:
        return len(self.excluded_episodes)

    @property
    def oof_upstream_exclusions(self) -> tuple[ExcludedOOFRow, ...]:
        return _oof_exclusions(self.excluded_episodes)


@dataclass(frozen=True)
class DirectionNeutralEmpiricalResult:
    target_series: VerifiedDailySeries
    benchmark_series: VerifiedDailySeries
    session_coverage: CommonSessionCoverageLedger
    feature_dataset: DirectionNeutralFeatureDataset
    screening_results: tuple[ScreeningResult, ...]
    episodes: tuple[OverheatEpisode, ...]
    episode_results: tuple[EpisodeCompetitivePath, ...]
    examples: tuple[CompetitivePathExample, ...]
    excluded_episodes: tuple[ExcludedEpisode, ...]
    horizon: LabelHorizon
    source_evidence_sha256: str

    @property
    def excluded_episode_count(self) -> int:
        return len(self.excluded_episodes)

    @property
    def oof_upstream_exclusions(self) -> tuple[ExcludedOOFRow, ...]:
        return _oof_exclusions(self.excluded_episodes)


@dataclass(frozen=True)
class _CoverageMarketContract:
    timezone: ZoneInfo
    open_time: time


_COVERAGE_MARKETS = {
    FeatureMarket.US_REGULAR: _CoverageMarketContract(
        timezone=ZoneInfo("America/New_York"),
        open_time=time(9, 30),
    ),
    FeatureMarket.KR_REGULAR: _CoverageMarketContract(
        timezone=ZoneInfo("Asia/Seoul"),
        open_time=time(9, 0),
    ),
}


def run_direction_neutral_empirical_pipeline(
    *,
    archive_root: Path,
    target_scopes: Sequence[CollectionScope],
    benchmark_scopes: Sequence[CollectionScope],
    market: FeatureMarket,
    sessions: Sequence[FeatureSession],
    horizon: LabelHorizon,
) -> DirectionNeutralEmpiricalResult:
    """Load explicit development scopes and derive competitive-path examples."""
    target_scope_values = tuple(target_scopes)
    benchmark_scope_values = tuple(benchmark_scopes)
    require_development_scopes(target_scope_values + benchmark_scope_values)
    if not isinstance(market, FeatureMarket):
        raise EmpiricalPipelineError("feature_market_invalid")
    if not isinstance(horizon, LabelHorizon):
        raise EmpiricalPipelineError("label_horizon_invalid")
    session_values = tuple(sessions)
    _validate_feature_sessions(session_values)

    target = load_verified_daily_series(
        root=archive_root,
        scopes=target_scope_values,
    )
    benchmark = load_verified_daily_series(
        root=archive_root,
        scopes=benchmark_scope_values,
    )
    if not target.bars or not benchmark.bars:
        raise EmpiricalPipelineError("insufficient_loadable_daily_archives")
    if (
        target.provider != benchmark.provider
        or target.feed != benchmark.feed
        or target.adjustment_mode != benchmark.adjustment_mode
        or target.symbol == benchmark.symbol
    ):
        raise EmpiricalPipelineError("pipeline_scope_mismatch")
    coverage = _common_session_coverage(
        target=target,
        benchmark=benchmark,
        sessions=session_values,
        market=market,
    )
    if not coverage.included_sessions:
        raise EmpiricalPipelineError("no_common_complete_feature_sessions")
    try:
        dataset = build_direction_neutral_features(
            symbol_bars=_bars_for_sessions(
                target,
                coverage.included_sessions,
                market,
            ),
            benchmark_bars=_bars_for_sessions(
                benchmark,
                coverage.included_sessions,
                market,
            ),
            market=market,
            sessions=session_values,
        )
    except FeatureBuildError as error:
        raise EmpiricalPipelineError(f"feature_build_failed_{error.code}") from None

    archive_input_evidence = _hash_body(
        {
            "schemaVersion": _PIPELINE_EVIDENCE_SCHEMA,
            "targetSeriesEvidenceSha256": target.source_evidence_sha256,
            "benchmarkSeriesEvidenceSha256": benchmark.source_evidence_sha256,
            "market": market.value,
            "horizon": horizon.value,
            "sessionCoverageSha256": coverage.source_evidence_sha256,
            "featureSessions": [
                {
                    "sessionDate": session.session_date.isoformat(),
                    "regularMinutes": session.regular_minutes,
                }
                for session in session_values
            ],
        }
    )
    analysis = analyze_direction_neutral_dataset(
        dataset=dataset,
        horizon=horizon,
        input_evidence_sha256=archive_input_evidence,
    )
    return DirectionNeutralEmpiricalResult(
        target_series=target,
        benchmark_series=benchmark,
        session_coverage=coverage,
        feature_dataset=dataset,
        screening_results=analysis.screening_results,
        episodes=analysis.episodes,
        episode_results=analysis.episode_results,
        examples=analysis.examples,
        excluded_episodes=analysis.excluded_episodes,
        horizon=horizon,
        source_evidence_sha256=analysis.source_evidence_sha256,
    )


def analyze_direction_neutral_dataset(
    *,
    dataset: DirectionNeutralFeatureDataset,
    horizon: LabelHorizon,
    input_evidence_sha256: str,
) -> DirectionNeutralDatasetAnalysis:
    """Screen every point in time, group episodes, label, and make OOF rows."""
    if not isinstance(dataset, DirectionNeutralFeatureDataset):
        raise EmpiricalPipelineError("feature_dataset_invalid")
    if not isinstance(horizon, LabelHorizon):
        raise EmpiricalPipelineError("label_horizon_invalid")
    if (
        type(input_evidence_sha256) is not str
        or _SHA256_PATTERN.fullmatch(input_evidence_sha256) is None
    ):
        raise EmpiricalPipelineError("input_evidence_sha256_invalid")
    observations = tuple(dataset.observations)
    screening_results = _screen_by_minute_of_day(observations)
    episodes = group_episodes(screening_results)
    screen_by_ordinal = {
        result.observation.market_minute_ordinal: result
        for result in screening_results
    }
    if len(screen_by_ordinal) != len(screening_results):
        raise EmpiricalPipelineError("screening_observation_duplicate")
    analysis_input_sha256 = _analysis_input_sha256(
        dataset,
        horizon,
        input_evidence_sha256,
    )
    episode_results: list[EpisodeCompetitivePath] = []
    excluded_episodes: list[ExcludedEpisode] = []
    for episode in episodes:
        screening = screen_by_ordinal[episode.anchor.market_minute_ordinal]
        label = label_competitive_path(
            episode.anchor,
            observations,
            episode,
            horizon,
        )
        row_id = _episode_row_id(screening, horizon)
        evidence_sha256 = _episode_evidence_sha256(
            screening=screening,
            episode=episode,
            label=label,
            analysis_input_sha256=analysis_input_sha256,
        )
        exclusion_reason = _example_exclusion_reason(screening)
        example = None
        if exclusion_reason is None:
            example = _competitive_path_example(
                screening=screening,
                label=label,
                horizon=horizon,
                row_id=row_id,
                evidence_sha256=evidence_sha256,
            )
        else:
            excluded_episodes.append(
                ExcludedEpisode(
                    row_id=row_id,
                    symbol=screening.observation.symbol,
                    session_id=screening.observation.session_id,
                    horizon=horizon,
                    label=label.label,
                    reason=exclusion_reason,
                    source_evidence_sha256=evidence_sha256,
                )
            )
        episode_results.append(
            EpisodeCompetitivePath(
                episode=episode,
                screening=screening,
                label=label,
                example=example,
                source_evidence_sha256=evidence_sha256,
            )
        )
    values = tuple(episode_results)
    examples = tuple(
        value.example for value in values if value.example is not None
    )
    excluded = tuple(excluded_episodes)
    pipeline_evidence_sha256 = _hash_body(
        {
            "schemaVersion": _PIPELINE_EVIDENCE_SCHEMA,
            "analysisInputSha256": analysis_input_sha256,
            "screeningResults": [
                _screening_body(result) for result in screening_results
            ],
            "episodeExamples": [
                {
                    "rowId": value.example.row_id,
                    "sourceEvidenceSha256": value.example.source_evidence_sha256,
                }
                for value in values
                if value.example is not None
            ],
            "excludedEpisodes": [
                {
                    "rowId": value.row_id,
                    "reason": value.reason.value,
                    "sourceEvidenceSha256": value.source_evidence_sha256,
                }
                for value in excluded
            ],
        }
    )
    return DirectionNeutralDatasetAnalysis(
        screening_results=screening_results,
        episodes=episodes,
        episode_results=values,
        examples=examples,
        excluded_episodes=excluded,
        source_evidence_sha256=pipeline_evidence_sha256,
    )


def _competitive_path_example(
    *,
    screening: ScreeningResult,
    label: CompetitivePathResult,
    horizon: LabelHorizon,
    row_id: str,
    evidence_sha256: str,
) -> CompetitivePathExample:
    screens = {value.family: value for value in screening.family_screens}
    family_flags = {
        family: FamilyThresholdFlags(
            exceeds_p99=screens[family].exceeds_p99 is True,
            exceeds_p999=screens[family].exceeds_p999 is True,
        )
        for family in FAMILY_NAMES
    }
    range_value = screening.observation.family_scores.get("intrabar_log_range")
    if range_value is None:
        raise EmpiricalPipelineError("episode_exclusion_contract_broken")
    anchor = screening.observation
    return CompetitivePathExample(
        row_id=row_id,
        symbol=anchor.symbol,
        session_id=anchor.session_id,
        sample_role="development",
        horizon=horizon,
        label=label.label,
        family_flags=family_flags,
        signed_return=anchor.signed_return,
        intrabar_log_range=range_value,
        source_evidence_sha256=evidence_sha256,
    )


def _example_exclusion_reason(
    screening: ScreeningResult,
) -> ExcludedEpisodeReason | None:
    screens = {value.family: value for value in screening.family_screens}
    if set(screens) != set(FAMILY_NAMES):
        return ExcludedEpisodeReason.FAMILY_CONTRACT_MISMATCH
    if screening.observation.family_scores.get("intrabar_log_range") is None:
        return ExcludedEpisodeReason.INTRABAR_RANGE_UNAVAILABLE
    if any(
        screens[family].exceeds_p99 is None
        or screens[family].exceeds_p999 is None
        for family in FAMILY_NAMES
    ):
        return ExcludedEpisodeReason.FAMILY_THRESHOLD_UNAVAILABLE
    return None


def _episode_row_id(
    screening: ScreeningResult,
    horizon: LabelHorizon,
) -> str:
    anchor = screening.observation
    return (
        f"{anchor.symbol}:{anchor.session_id}:"
        f"{anchor.market_minute_ordinal}:{horizon.value}"
    )


def _episode_evidence_sha256(
    *,
    screening: ScreeningResult,
    episode: OverheatEpisode,
    label: CompetitivePathResult,
    analysis_input_sha256: str,
) -> str:
    return _hash_body(
        {
            "schemaVersion": _EXAMPLE_EVIDENCE_SCHEMA,
            "analysisInputSha256": analysis_input_sha256,
            "screening": _screening_body(screening),
            "episode": _episode_body(episode),
            "label": _label_body(label),
        }
    )


def _screen_by_minute_of_day(
    observations: tuple[DirectionNeutralObservation, ...],
) -> tuple[ScreeningResult, ...]:
    grouped: dict[int, list[DirectionNeutralObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.minute_of_day, []).append(observation)
    groups = {minute: tuple(values) for minute, values in grouped.items()}
    return tuple(
        screen_observation(observation, groups[observation.minute_of_day])
        for observation in observations
    )


def _validate_feature_sessions(sessions: tuple[FeatureSession, ...]) -> None:
    if not sessions or any(
        not isinstance(session, FeatureSession) for session in sessions
    ):
        raise EmpiricalPipelineError("feature_session_invalid")
    dates = tuple(session.session_date for session in sessions)
    if any(current <= previous for previous, current in zip(dates, dates[1:])):
        raise EmpiricalPipelineError("feature_session_invalid")


def _common_session_coverage(
    *,
    target: VerifiedDailySeries,
    benchmark: VerifiedDailySeries,
    sessions: tuple[FeatureSession, ...],
    market: FeatureMarket,
) -> CommonSessionCoverageLedger:
    contract = _COVERAGE_MARKETS[market]
    regular_minutes = {
        session.session_date: session.regular_minutes for session in sessions
    }
    target_offsets = _regular_offsets_by_date(
        target.bars,
        contract,
        regular_minutes,
    )
    benchmark_offsets = _regular_offsets_by_date(
        benchmark.bars,
        contract,
        regular_minutes,
    )
    entries: list[CommonSessionCoverageEntry] = []
    for session in sessions:
        target_audit = _series_session_coverage(
            series=target,
            session=session,
            observed_offsets=target_offsets.get(session.session_date, ()),
        )
        benchmark_audit = _series_session_coverage(
            series=benchmark,
            session=session,
            observed_offsets=benchmark_offsets.get(session.session_date, ()),
        )
        included = target_audit.complete and benchmark_audit.complete
        entry_hash = _hash_body(
            {
                "schemaVersion": "rp001-s2-common-session-coverage-entry.v1",
                "sessionDate": session.session_date.isoformat(),
                "regularMinutes": session.regular_minutes,
                "targetCoverageSha256": target_audit.source_evidence_sha256,
                "benchmarkCoverageSha256": (
                    benchmark_audit.source_evidence_sha256
                ),
                "included": included,
            }
        )
        entries.append(
            CommonSessionCoverageEntry(
                session=session,
                target=target_audit,
                benchmark=benchmark_audit,
                included=included,
                source_evidence_sha256=entry_hash,
            )
        )
    values = tuple(entries)
    included_sessions = tuple(
        entry.session for entry in values if entry.included
    )
    excluded_sessions = tuple(
        entry.session for entry in values if not entry.included
    )
    evidence_sha256 = _hash_body(
        {
            "schemaVersion": "rp001-s2-common-session-coverage-ledger.v1",
            "entries": [
                {
                    "sessionDate": entry.session.session_date.isoformat(),
                    "included": entry.included,
                    "sourceEvidenceSha256": entry.source_evidence_sha256,
                }
                for entry in values
            ],
        }
    )
    return CommonSessionCoverageLedger(
        entries=values,
        included_sessions=included_sessions,
        excluded_sessions=excluded_sessions,
        source_evidence_sha256=evidence_sha256,
    )


def _series_session_coverage(
    *,
    series: VerifiedDailySeries,
    session: FeatureSession,
    observed_offsets: tuple[int, ...],
) -> SeriesSessionCoverage:
    expected = tuple(range(session.regular_minutes))
    observed_set = set(observed_offsets)
    expected_set = set(expected)
    duplicates = tuple(
        offset
        for offset in sorted(observed_set)
        if observed_offsets.count(offset) > 1
    )
    missing = tuple(sorted(expected_set - observed_set))
    unexpected = tuple(sorted(observed_set - expected_set))
    complete = observed_offsets == expected
    evidence_sha256 = _hash_body(
        {
            "schemaVersion": "rp001-s2-series-session-coverage.v1",
            "seriesEvidenceSha256": series.source_evidence_sha256,
            "symbol": series.symbol,
            "sessionDate": session.session_date.isoformat(),
            "regularMinutes": session.regular_minutes,
            "observedOffsets": list(observed_offsets),
            "missingOffsets": list(missing),
            "unexpectedOffsets": list(unexpected),
            "duplicateOffsets": list(duplicates),
            "complete": complete,
        }
    )
    return SeriesSessionCoverage(
        symbol=series.symbol,
        session_date=session.session_date,
        regular_minutes=session.regular_minutes,
        observed_offsets=observed_offsets,
        missing_offsets=missing,
        unexpected_offsets=unexpected,
        duplicate_offsets=duplicates,
        complete=complete,
        source_evidence_sha256=evidence_sha256,
    )


def _regular_offsets_by_date(
    bars: tuple[CanonicalMinuteBar, ...],
    contract: _CoverageMarketContract,
    regular_minutes_by_date: dict[date, int],
) -> dict[date, tuple[int, ...]]:
    grouped: dict[date, list[int]] = {}
    open_minute = contract.open_time.hour * 60 + contract.open_time.minute
    for bar in bars:
        if bar.quality_status != "verified_completed":
            continue
        local = _event_start(bar).astimezone(contract.timezone)
        regular_minutes = regular_minutes_by_date.get(local.date())
        if regular_minutes is None:
            continue
        offset = local.hour * 60 + local.minute - open_minute
        if 0 <= offset < regular_minutes:
            grouped.setdefault(local.date(), []).append(offset)
    return {
        session_date: tuple(sorted(offsets))
        for session_date, offsets in grouped.items()
    }


def _bars_for_sessions(
    series: VerifiedDailySeries,
    included_sessions: tuple[FeatureSession, ...],
    market: FeatureMarket,
) -> tuple[CanonicalMinuteBar, ...]:
    contract = _COVERAGE_MARKETS[market]
    regular_minutes = {
        session.session_date: session.regular_minutes
        for session in included_sessions
    }
    open_minute = contract.open_time.hour * 60 + contract.open_time.minute
    selected: list[CanonicalMinuteBar] = []
    for bar in series.bars:
        if bar.quality_status != "verified_completed":
            continue
        local = _event_start(bar).astimezone(contract.timezone)
        session_minutes = regular_minutes.get(local.date())
        if session_minutes is None:
            continue
        offset = local.hour * 60 + local.minute - open_minute
        if 0 <= offset < session_minutes:
            selected.append(bar)
    return tuple(selected)


def _oof_exclusions(
    excluded_episodes: tuple[ExcludedEpisode, ...],
) -> tuple[ExcludedOOFRow, ...]:
    return tuple(
        ExcludedOOFRow(
            row_id=episode.row_id,
            symbol=episode.symbol,
            session_id=episode.session_id,
            horizon=episode.horizon,
            label=episode.label,
            reason=episode.reason.value,
            source_evidence_sha256=episode.source_evidence_sha256,
        )
        for episode in excluded_episodes
    )


def _event_start(bar: CanonicalMinuteBar) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            bar.event_start_utc[:-1] + "+00:00"
            if bar.event_start_utc.endswith("Z")
            else bar.event_start_utc
        )
    except (TypeError, ValueError, OverflowError):
        raise EmpiricalPipelineError("coverage_timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise EmpiricalPipelineError("coverage_timestamp_invalid")
    return parsed.astimezone(timezone.utc)


def _analysis_input_sha256(
    dataset: DirectionNeutralFeatureDataset,
    horizon: LabelHorizon,
    input_evidence_sha256: str,
) -> str:
    return _hash_body(
        {
            "schemaVersion": _ANALYSIS_INPUT_SCHEMA,
            "inputEvidenceSha256": input_evidence_sha256,
            "symbol": dataset.symbol,
            "benchmarkSymbol": dataset.benchmark_symbol,
            "market": dataset.market.value,
            "claimLevel": dataset.claim_level,
            "availabilityBasis": dataset.availability_basis,
            "horizon": horizon.value,
            "observations": [
                {
                    "sessionId": value.session_id,
                    "marketMinuteOrdinal": value.market_minute_ordinal,
                    "sourceWindowSha256": value.source_window_sha256,
                }
                for value in dataset.observations
            ],
        }
    )


def _screening_body(screening: ScreeningResult) -> dict[str, object]:
    return {
        "symbol": screening.observation.symbol,
        "sessionId": screening.observation.session_id,
        "marketMinuteOrdinal": screening.observation.market_minute_ordinal,
        "sourceWindowSha256": screening.observation.source_window_sha256,
        "state": screening.state.value,
        "families": [
            {
                "family": value.family,
                "observationCount": value.observation_count,
                "score": value.score,
                "p99": value.p99,
                "p999": value.p999,
                "exceedsP99": value.exceeds_p99,
                "exceedsP999": value.exceeds_p999,
            }
            for value in screening.family_screens
        ],
    }


def _episode_body(episode: OverheatEpisode) -> dict[str, object]:
    return {
        "anchorMarketMinuteOrdinal": episode.anchor.market_minute_ordinal,
        "bursts": [
            list(burst.candidate_market_minute_ordinals)
            for burst in episode.bursts
        ],
        "closedAtMarketMinuteOrdinal": episode.closed_at_market_minute_ordinal,
        "coverageComplete": episode.coverage_complete,
        "rightCensored": episode.right_censored,
    }


def _label_body(label: CompetitivePathResult) -> dict[str, object]:
    return {
        "horizon": label.horizon.value,
        "label": label.label.value,
        "reason": label.reason,
        "sigma": label.sigma,
        "lowerBarrier": label.lower_barrier,
        "upperBarrier": label.upper_barrier,
        "firstPassageMarketMinuteOrdinal": (
            label.first_passage_market_minute_ordinal
        ),
        "secondPassageMarketMinuteOrdinal": (
            label.second_passage_market_minute_ordinal
        ),
        "horizonEndMarketMinuteOrdinal": (
            label.horizon_end_market_minute_ordinal
        ),
    }


def _hash_body(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
