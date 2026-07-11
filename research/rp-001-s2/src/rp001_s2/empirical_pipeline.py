"""Research-only direction-neutral minute archive empirical pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rp001_s2.archive_contract import CollectionScope
from rp001_s2.direction_neutral_overheat import (
    CompetitivePathResult,
    LabelHorizon,
    OverheatEpisode,
    ScreeningResult,
    group_episodes,
    label_competitive_path,
    screen_observation,
)
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
    example: CompetitivePathExample


@dataclass(frozen=True)
class DirectionNeutralDatasetAnalysis:
    screening_results: tuple[ScreeningResult, ...]
    episodes: tuple[OverheatEpisode, ...]
    episode_results: tuple[EpisodeCompetitivePath, ...]
    examples: tuple[CompetitivePathExample, ...]
    source_evidence_sha256: str


@dataclass(frozen=True)
class DirectionNeutralEmpiricalResult:
    target_series: VerifiedDailySeries
    benchmark_series: VerifiedDailySeries
    feature_dataset: DirectionNeutralFeatureDataset
    screening_results: tuple[ScreeningResult, ...]
    episodes: tuple[OverheatEpisode, ...]
    episode_results: tuple[EpisodeCompetitivePath, ...]
    examples: tuple[CompetitivePathExample, ...]
    horizon: LabelHorizon
    source_evidence_sha256: str


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

    target = load_verified_daily_series(
        root=archive_root,
        scopes=target_scope_values,
    )
    benchmark = load_verified_daily_series(
        root=archive_root,
        scopes=benchmark_scope_values,
    )
    if not target.bars or not benchmark.bars:
        raise EmpiricalPipelineError("insufficient_complete_daily_archives")
    if (
        target.provider != benchmark.provider
        or target.feed != benchmark.feed
        or target.adjustment_mode != benchmark.adjustment_mode
        or target.symbol == benchmark.symbol
    ):
        raise EmpiricalPipelineError("pipeline_scope_mismatch")
    try:
        dataset = build_direction_neutral_features(
            symbol_bars=target.bars,
            benchmark_bars=benchmark.bars,
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
        feature_dataset=dataset,
        screening_results=analysis.screening_results,
        episodes=analysis.episodes,
        episode_results=analysis.episode_results,
        examples=analysis.examples,
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
    screening_results = tuple(
        screen_observation(observation, observations)
        for observation in observations
    )
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
    for episode in episodes:
        screening = screen_by_ordinal[episode.anchor.market_minute_ordinal]
        label = label_competitive_path(
            episode.anchor,
            observations,
            episode,
            horizon,
        )
        example = _competitive_path_example(
            screening=screening,
            episode=episode,
            label=label,
            horizon=horizon,
            analysis_input_sha256=analysis_input_sha256,
        )
        episode_results.append(
            EpisodeCompetitivePath(
                episode=episode,
                screening=screening,
                label=label,
                example=example,
            )
        )
    values = tuple(episode_results)
    examples = tuple(value.example for value in values)
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
            ],
        }
    )
    return DirectionNeutralDatasetAnalysis(
        screening_results=screening_results,
        episodes=episodes,
        episode_results=values,
        examples=examples,
        source_evidence_sha256=pipeline_evidence_sha256,
    )


def _competitive_path_example(
    *,
    screening: ScreeningResult,
    episode: OverheatEpisode,
    label: CompetitivePathResult,
    horizon: LabelHorizon,
    analysis_input_sha256: str,
) -> CompetitivePathExample:
    screens = {value.family: value for value in screening.family_screens}
    if set(screens) != set(FAMILY_NAMES):
        raise EmpiricalPipelineError("oof_family_contract_mismatch")
    if any(
        screens[family].exceeds_p99 is None
        or screens[family].exceeds_p999 is None
        for family in FAMILY_NAMES
    ):
        raise EmpiricalPipelineError("oof_family_threshold_unavailable")
    family_flags = {
        family: FamilyThresholdFlags(
            exceeds_p99=screens[family].exceeds_p99 is True,
            exceeds_p999=screens[family].exceeds_p999 is True,
        )
        for family in FAMILY_NAMES
    }
    range_value = screening.observation.family_scores.get("intrabar_log_range")
    if range_value is None:
        raise EmpiricalPipelineError("oof_intrabar_range_unavailable")
    evidence_sha256 = _hash_body(
        {
            "schemaVersion": _EXAMPLE_EVIDENCE_SCHEMA,
            "analysisInputSha256": analysis_input_sha256,
            "screening": _screening_body(screening),
            "episode": _episode_body(episode),
            "label": _label_body(label),
        }
    )
    anchor = screening.observation
    row_id = (
        f"{anchor.symbol}:{anchor.session_id}:"
        f"{anchor.market_minute_ordinal}:{horizon.value}"
    )
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
