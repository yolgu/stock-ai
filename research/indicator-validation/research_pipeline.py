from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from validation import (
    BarrierDefinition,
    CandidateDefinition,
    CandidateRegistry,
    CausalProbabilityCalibrator,
    DailyFeatureEngine,
    EventEpisodeCatalog,
    JeffreysPosterior,
    OutcomeDefinition,
    OutcomeLabelEngine,
    ReliefOutcomeLabelEngine,
    WalkForwardSplitter,
    beta_binomial_predictive,
    binary_metrics,
    paired_brier_bootstrap,
)


@dataclass(frozen=True)
class HypothesisDefinition:
    identifier: str
    family: str
    candidate_identifier: str
    candidate_kind: str
    outcome_identifier: str
    horizon: int


@dataclass(frozen=True)
class ResearchProtocol:
    version: str
    data_cutoff: str
    horizons: tuple[int, ...]
    candidate_registry: CandidateRegistry
    outcome_definitions: Mapping[str, OutcomeDefinition | "SpecialOutcomeDefinition"]
    calibration_bin_count: int
    calibration_minimum_valid_pairs: int
    percentile_minimum_sessions: int
    percentile_maximum_sessions: int
    purge_sessions: int
    embargo_sessions: int
    bootstrap_block_lengths: tuple[int, ...]
    bootstrap_repetitions: int
    seed: int
    hypotheses: tuple[HypothesisDefinition, ...]
    minimum_event_count: int
    anchor_dates: Mapping[str, str]
    primary_holm_hypotheses: tuple[str, ...]
    candidate_complexity: Mapping[str, tuple[int, int]]
    significance_alpha: float
    four_month_start_date: str
    four_month_end_date: str

    @classmethod
    def from_file(cls, file_path: Path) -> "ResearchProtocol":
        document = json.loads(file_path.read_text(encoding="utf-8"))
        research = _require_mapping(document, "research")
        protocol = _require_mapping(document, "protocol")
        candidate_families = document.get("candidateFamilies")
        if not isinstance(candidate_families, list):
            raise ValueError("Preregistration candidateFamilies must be an array")

        candidates: list[CandidateDefinition] = []
        for family in candidate_families:
            if not isinstance(family, dict):
                raise ValueError("Candidate family must be an object")
            family_identifier = _require_text(family, "id")
            family_candidates = family.get("candidates")
            if not isinstance(family_candidates, list):
                raise ValueError("Candidate family candidates must be an array")
            for candidate in family_candidates:
                if not isinstance(candidate, dict):
                    raise ValueError("Candidate must be an object")
                weights = candidate.get("weights")
                candidates.append(
                    CandidateDefinition(
                        identifier=_require_text(candidate, "id"),
                        family=family_identifier,
                        kind=_require_text(candidate, "kind"),
                        formula=candidate.get("formula"),
                        weights=(
                            {str(key): float(value) for key, value in weights.items()}
                            if isinstance(weights, dict)
                            else None
                        ),
                        primary_outcome=_require_text(
                            candidate,
                            "outcomeDefinitionId",
                        ),
                        outcome_ids=tuple(
                            _require_text_list(candidate, "outcomeDefinitionIds")
                        ),
                        applicable_horizons=tuple(
                            _require_integer_list(candidate, "applicableHorizons")
                        ),
                        outcome_applicable_horizons=_read_outcome_horizon_map(
                            candidate.get("outcomeApplicableHorizons")
                        ),
                    )
                )

        percentile = _require_mapping(protocol, "percentile")
        percentile_window = _require_mapping(percentile, "referenceWindow")
        walk_forward = _require_mapping(protocol, "walkForward")
        purge = _require_mapping(walk_forward, "purge")
        embargo = _require_mapping(walk_forward, "embargo")
        bootstrap = _require_mapping(protocol, "bootstrap")
        calibration = _read_calibration_contract(protocol)
        outcome_definitions = _read_standard_outcomes(
            document,
            tuple(_require_integer_list(protocol, "horizons")),
        )
        significance = _require_mapping(protocol, "significance")
        primary_conclusions = _require_mapping(significance, "primaryConclusions")
        selection = _require_mapping(document, "selection")
        windows = _require_mapping(protocol, "windows")
        current_window = _require_mapping(windows, "current")
        four_month = _require_mapping(current_window, "fourMonth")

        return cls(
            version=_require_text(research, "version"),
            data_cutoff=_require_text(research, "dataCutoff"),
            horizons=tuple(_require_integer_list(protocol, "horizons")),
            candidate_registry=CandidateRegistry(candidates),
            outcome_definitions=outcome_definitions,
            calibration_bin_count=_require_positive_integer(
                _require_mapping(calibration, "quantileBins"),
                "binCount",
            ),
            calibration_minimum_valid_pairs=_require_positive_integer(
                _require_mapping(calibration, "trainingPairs"),
                "minimumValidPairs",
            ),
            percentile_minimum_sessions=_require_positive_integer(
                percentile_window,
                "minFiniteValues",
            ),
            percentile_maximum_sessions=_require_positive_integer(
                percentile_window,
                "maxSessions",
            ),
            purge_sessions=_require_non_negative_integer(purge, "sessions"),
            embargo_sessions=_require_non_negative_integer(embargo, "sessions"),
            bootstrap_block_lengths=tuple(
                _require_integer_list(bootstrap, "blockLengths")
            ),
            bootstrap_repetitions=_require_positive_integer(
                bootstrap,
                "repetitions",
            ),
            seed=_require_non_negative_integer(research, "seed"),
            hypotheses=_read_hypotheses(protocol),
            minimum_event_count=_require_positive_integer(
                _require_mapping(protocol, "minimumEvents"),
                "count",
            ),
            anchor_dates=_read_anchor_dates(document),
            primary_holm_hypotheses=tuple(
                _require_text_list(primary_conclusions, "hypotheses")
            ),
            candidate_complexity=_read_candidate_complexity(selection),
            significance_alpha=_require_positive_number(significance, "alpha"),
            four_month_start_date=_require_text(four_month, "startDate"),
            four_month_end_date=_require_text(four_month, "endDate"),
        )


def _read_hypotheses(protocol: Mapping[str, Any]) -> tuple[HypothesisDefinition, ...]:
    registry = _require_mapping(protocol, "hypothesisRegistry")
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Preregistration hypothesis entries must be an array")
    hypotheses: list[HypothesisDefinition] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Preregistration hypothesis entry must be an object")
        hypotheses.append(
            HypothesisDefinition(
                identifier=_require_text(entry, "hypothesisId"),
                family=_require_text(entry, "familyId"),
                candidate_identifier=_require_text(entry, "candidateId"),
                candidate_kind=_require_text(entry, "candidateKind"),
                outcome_identifier=_require_text(entry, "outcomeDefinitionId"),
                horizon=_require_positive_integer(entry, "horizon"),
            )
        )
    expected_count = _require_positive_integer(registry, "expectedCount")
    identifiers = [hypothesis.identifier for hypothesis in hypotheses]
    if len(hypotheses) != expected_count or len(set(identifiers)) != len(identifiers):
        raise ValueError("Preregistration hypothesis registry count is inconsistent")
    if identifiers != sorted(identifiers):
        raise ValueError("Preregistration hypotheses must use code-point order")
    return tuple(hypotheses)


def _read_anchor_dates(document: Mapping[str, Any]) -> Mapping[str, str]:
    anchors = document.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("Preregistration anchors must be an array")
    anchor_dates: dict[str, str] = {}
    for anchor in anchors:
        if not isinstance(anchor, dict):
            raise ValueError("Preregistration anchor must be an object")
        key = f"{_require_text(anchor, 'symbol')}:{_require_text(anchor, 'role')}"
        if key in anchor_dates:
            raise ValueError("Preregistration anchor role must be unique per symbol")
        anchor_dates[key] = _require_text(anchor, "date")
    return anchor_dates


def _read_candidate_complexity(
    selection: Mapping[str, Any],
) -> Mapping[str, tuple[int, int]]:
    values = _require_mapping(selection, "candidateComplexity")
    complexity: dict[str, tuple[int, int]] = {}
    for candidate_identifier, value in values.items():
        if not isinstance(candidate_identifier, str) or not isinstance(value, dict):
            raise ValueError("Preregistration candidate complexity is invalid")
        effective_inputs = _require_non_negative_integer(value, "effectiveInputCount")
        nonlinear_gates = _require_non_negative_integer(value, "nonlinearGateCount")
        complexity[candidate_identifier] = (effective_inputs, nonlinear_gates)
    return complexity


def _read_calibration_contract(protocol: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = protocol.get("probabilityCalibration")
    if isinstance(direct, dict):
        return direct
    scoring = protocol.get("candidateScoring")
    if isinstance(scoring, dict) and isinstance(scoring.get("probabilityCalibration"), dict):
        return scoring["probabilityCalibration"]
    raise ValueError("Preregistration probability calibration contract is missing")


@dataclass(frozen=True)
class SpecialOutcomeDefinition:
    identifier: str
    applicable_horizons: tuple[int, ...]


def _read_standard_outcomes(
    document: Mapping[str, Any],
    default_horizons: tuple[int, ...],
) -> dict[str, OutcomeDefinition | SpecialOutcomeDefinition]:
    raw_definitions = _require_mapping(document, "outcomeDefinitions")
    definitions: dict[str, OutcomeDefinition | SpecialOutcomeDefinition] = {}
    for identifier, value in raw_definitions.items():
        if not isinstance(value, dict):
            continue
        target = value.get("target")
        opposite = value.get("opposite")
        if not isinstance(target, dict) or not isinstance(opposite, dict):
            if identifier in {"reliefConfirmed", "fakeRelief"}:
                horizons = value.get("applicableHorizons")
                if not isinstance(horizons, list):
                    raise ValueError(
                        f"Special outcome {identifier} requires applicable horizons"
                    )
                definitions[identifier] = SpecialOutcomeDefinition(
                    identifier=identifier,
                    applicable_horizons=tuple(int(horizon) for horizon in horizons),
                )
            continue
        horizons = value.get("applicableHorizons", default_horizons)
        if not isinstance(horizons, list) and not isinstance(horizons, tuple):
            raise ValueError(f"Outcome {identifier} applicableHorizons is invalid")
        definitions[identifier] = OutcomeDefinition(
            identifier=identifier,
            barrier=BarrierDefinition(
                target_direction=_require_text(target, "direction"),
                target_atr_multiple=_require_positive_number(target, "atrMultiple"),
                opposite_direction=_require_text(opposite, "direction"),
                opposite_atr_multiple=_require_positive_number(opposite, "atrMultiple"),
            ),
            applicable_horizons=tuple(int(horizon) for horizon in horizons),
        )
    return definitions


def _read_outcome_horizon_map(
    value: object,
) -> Mapping[str, tuple[int, ...]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Candidate outcomeApplicableHorizons must be an object")
    result: dict[str, tuple[int, ...]] = {}
    for outcome_id, horizons in value.items():
        if not isinstance(outcome_id, str) or not isinstance(horizons, list):
            raise ValueError("Candidate outcome horizon map is invalid")
        if not all(isinstance(horizon, int) and horizon > 0 for horizon in horizons):
            raise ValueError("Candidate outcome horizons must be positive integers")
        result[outcome_id] = tuple(horizons)
    return result


@dataclass(frozen=True)
class TossCandleArchive:
    symbol: str
    currency: str
    market: pd.DataFrame

    @classmethod
    def from_file(cls, symbol: str, file_path: Path) -> "TossCandleArchive":
        values = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(values, list) or not values:
            raise ValueError("Toss candle archive must be a non-empty array")

        records: list[dict[str, object]] = []
        currencies: set[str] = set()
        trading_dates: list[str] = []
        for value in values:
            if not isinstance(value, dict):
                raise ValueError("Toss candle record must be an object")
            timestamp = _require_text(value, "timestamp")
            parsed_timestamp = pd.to_datetime(timestamp, utc=True, errors="coerce")
            if pd.isna(parsed_timestamp):
                raise ValueError("Toss candle timestamp is invalid")
            trading_date = timestamp[:10]
            if len(trading_date) != 10:
                raise ValueError("Toss candle trading date is invalid")
            currency = _require_text(value, "currency")
            currencies.add(currency)
            trading_dates.append(trading_date)
            records.append(
                {
                    "date": pd.Timestamp(trading_date, tz="UTC"),
                    "open": _require_decimal_text(value, "openPrice", allow_zero=False),
                    "high": _require_decimal_text(value, "highPrice", allow_zero=False),
                    "low": _require_decimal_text(value, "lowPrice", allow_zero=False),
                    "close": _require_decimal_text(value, "closePrice", allow_zero=False),
                    "volume": _require_decimal_text(value, "volume", allow_zero=True),
                }
            )

        if len(set(trading_dates)) != len(trading_dates):
            raise ValueError("Toss candle archive requires unique trading dates")
        if len(currencies) != 1:
            raise ValueError("Toss candle archive must use one currency")
        market = pd.DataFrame.from_records(records).set_index("date")
        if not market.index.is_monotonic_increasing:
            raise ValueError("Toss candle archive must be ascending")
        DailyFeatureEngine._validated_market_frame(market)
        return cls(symbol=symbol, currency=next(iter(currencies)), market=market)


@dataclass(frozen=True)
class ResearchWindow:
    symbol: str
    market: pd.DataFrame
    analysis_start: int
    analysis_end: int
    kind: str

    @property
    def analysis_market(self) -> pd.DataFrame:
        return self.market.iloc[self.analysis_start : self.analysis_end]


class ResearchWindowBuilder:
    def anchored(
        self,
        symbol: str,
        market: pd.DataFrame,
        anchor_date: str,
        sessions: int,
    ) -> ResearchWindow:
        matching_positions = np.flatnonzero(
            market.index.strftime("%Y-%m-%d").to_numpy() == anchor_date
        )
        if len(matching_positions) != 1:
            raise ValueError(f"Anchor date {anchor_date} is not one actual session")
        analysis_start = int(matching_positions[0])
        analysis_end = analysis_start + sessions
        if analysis_end > len(market):
            raise ValueError("Anchored window lacks requested actual sessions")
        return ResearchWindow(
            symbol=symbol,
            market=market,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            kind="anchored",
        )

    def latest(
        self,
        symbol: str,
        market: pd.DataFrame,
        sessions: int,
    ) -> ResearchWindow:
        if sessions <= 0 or len(market) < sessions:
            raise ValueError("Latest window lacks requested actual sessions")
        return ResearchWindow(
            symbol=symbol,
            market=market,
            analysis_start=len(market) - sessions,
            analysis_end=len(market),
            kind="latest",
        )


def select_prediction_episode_starts(
    prediction_records: Sequence[Mapping[str, object]],
    horizon: int,
) -> pd.Index:
    dates: list[str] = []
    alert_flags: list[bool] = []
    threshold_contract_present = any(
        "score" in record
        or "alertThreshold" in record
        or "causalEligibility" in record
        for record in prediction_records
    )
    crossing_flags: list[bool] = []
    previous_eligible_score: float | None = None
    for record in prediction_records:
        date = record.get("date")
        alert = record.get("alert")
        if not isinstance(date, str) or not isinstance(alert, (bool, np.bool_)):
            raise ValueError("Prediction episodes require dated boolean alerts")
        dates.append(date)
        alert_flags.append(bool(alert))
        if threshold_contract_present:
            score = _finite_or_none(record.get("score"))
            threshold = _finite_or_none(record.get("alertThreshold"))
            eligibility = record.get("causalEligibility", score is not None)
            if not isinstance(eligibility, (bool, np.bool_)):
                raise ValueError("Prediction episode eligibility must be boolean")
            crossing_flags.append(
                bool(
                    alert
                    and bool(eligibility)
                    and score is not None
                    and threshold is not None
                    and (
                        previous_eligible_score is None
                        or previous_eligible_score < threshold
                    )
                )
            )
            previous_eligible_score = (
                score if bool(eligibility) and score is not None else None
            )
    if threshold_contract_present:
        return _select_registered_crossings(dates, crossing_flags, horizon)
    return EventEpisodeCatalog().select_starts(
        pd.Series(alert_flags, index=dates, dtype=bool),
        horizon,
    )


def _select_registered_crossings(
    dates: Sequence[str],
    crossing_flags: Sequence[bool],
    horizon: int,
) -> pd.Index:
    if horizon <= 0:
        raise ValueError("Episode horizon must be positive")
    starts: list[str] = []
    blocked_through_position = -1
    for position, (date, crossing) in enumerate(
        zip(dates, crossing_flags, strict=True)
    ):
        if crossing and position > blocked_through_position:
            starts.append(date)
            blocked_through_position = position + horizon
    return pd.Index(starts)


class CandidateTrialEvaluator:
    def __init__(
        self,
        percentile_minimum_sessions: int = 60,
        percentile_maximum_sessions: int = 252,
        calibration_bin_count: int = 5,
        purge_sessions: int = 10,
        embargo_sessions: int = 10,
        bootstrap_block_lengths: tuple[int, ...] = (5, 10, 20),
        bootstrap_repetitions: int = 2_000,
        seed: int = 20260710,
    ) -> None:
        self.feature_engine = DailyFeatureEngine(
            percentile_minimum_sessions,
            percentile_maximum_sessions,
        )
        self.calibration_bin_count = calibration_bin_count
        self.purge_sessions = purge_sessions
        self.embargo_sessions = embargo_sessions
        self.bootstrap_block_lengths = bootstrap_block_lengths
        self.bootstrap_repetitions = bootstrap_repetitions
        self.seed = seed

    def evaluate(
        self,
        symbol: str,
        market: pd.DataFrame,
        analysis_start: int,
        analysis_sessions: int,
        block_sessions: int,
        candidate: CandidateDefinition,
        outcome: OutcomeDefinition | SpecialOutcomeDefinition,
        horizon: int,
    ) -> dict[str, object]:
        if (
            horizon not in candidate.horizons_for_outcome(outcome.identifier)
            or horizon not in outcome.applicable_horizons
        ):
            raise ValueError(
                "Candidate is not applicable to the requested outcome and horizon"
            )
        if analysis_sessions % block_sessions != 0:
            raise ValueError("Analysis sessions must contain complete blocks")
        analysis_end = analysis_start + analysis_sessions
        if analysis_end > len(market):
            raise ValueError("Analysis window exceeds market history")

        study_market = market.iloc[:analysis_end]
        features = self.feature_engine.compute(study_market)
        scores = CandidateRegistry([candidate]).score_all(features)[candidate.identifier]
        eligibility = self._eligibility(
            outcome.identifier,
            study_market,
            features["atr14"],
        )
        if isinstance(outcome, SpecialOutcomeDefinition):
            assert eligibility is not None
            labels = ReliefOutcomeLabelEngine().label(
                study_market,
                features["atr14"],
                outcome.identifier,
                horizon,
                eligibility,
            )
        else:
            labels = OutcomeLabelEngine({outcome.identifier: outcome}).label(
                study_market,
                features["atr14"],
                outcome.identifier,
                horizon,
                eligibility=eligibility,
            )
        splitter = WalkForwardSplitter(
            block_sessions=block_sessions,
            purge_sessions=self.purge_sessions,
            embargo_sessions=self.embargo_sessions,
        )
        folds = splitter.split(
            total_sessions=len(study_market),
            analysis_start=analysis_start,
            block_count=analysis_sessions // block_sessions,
        )

        fold_records: list[dict[str, object]] = []
        prediction_records: list[dict[str, object]] = []
        observed_labels: list[float] = []
        predicted_probabilities: list[float] = []
        baseline_probabilities: list[float] = []
        alert_flags: list[bool] = []
        observation_fold_ids: list[int] = []

        for fold_number, fold in enumerate(folds, start=1):
            training_positions = list(fold.training_positions)
            training_scores = scores.iloc[training_positions]
            training_labels = labels["label"].iloc[training_positions]
            fitted = CausalProbabilityCalibrator(
                bin_count=self.calibration_bin_count,
                alert_quantile=0.8,
            ).fit(training_scores, training_labels)
            all_observed_training_labels = pd.to_numeric(
                training_labels,
                errors="coerce",
            ).dropna()
            if len(all_observed_training_labels) < 30:
                raise ValueError("Training fold has fewer than 30 observed labels")
            training_successes = int(all_observed_training_labels.sum())
            training_base_rate = (
                training_successes + 0.5
            ) / (len(all_observed_training_labels) + 1.0)
            test_scores = scores.iloc[fold.test_start : fold.test_end]
            test_labels = labels.iloc[fold.test_start : fold.test_end]
            test_probabilities = fitted.predict(test_scores)
            training_end_date = study_market.index[fold.train_end - 1].strftime(
                "%Y-%m-%d"
            )
            observed_count = 0

            for position in range(len(test_scores)):
                date = test_scores.index[position].strftime("%Y-%m-%d")
                label_value = test_labels["label"].iloc[position]
                probability_value = test_probabilities.iloc[position]
                score_value = test_scores.iloc[position]
                observed = np.isfinite(label_value) and np.isfinite(probability_value)
                alert = bool(
                    np.isfinite(score_value)
                    and score_value >= fitted.alert_threshold
                )
                if observed:
                    observed_count += 1
                    observed_labels.append(float(label_value))
                    predicted_probabilities.append(float(probability_value))
                    baseline_probabilities.append(training_base_rate)
                    alert_flags.append(alert)
                    observation_fold_ids.append(fold_number)
                prediction_records.append(
                    {
                        "date": date,
                        "fold": fold_number,
                        "trainingEnd": training_end_date,
                        "score": _finite_or_none(score_value),
                        "probability": _finite_or_none(probability_value),
                        "baselineProbability": training_base_rate,
                        "alertThreshold": fitted.alert_threshold,
                        "alert": alert,
                        "status": str(test_labels["status"].iloc[position]),
                        "label": _finite_or_none(label_value),
                    }
                )

            fold_records.append(
                {
                    "fold": fold_number,
                    "trainingSessions": fold.train_size,
                    "testSessions": fold.test_size,
                    "observedOutcomes": observed_count,
                    "trainingEnd": training_end_date,
                    "testStart": study_market.index[fold.test_start].strftime("%Y-%m-%d"),
                    "testEnd": study_market.index[fold.test_end - 1].strftime("%Y-%m-%d"),
                    "embargoEndPosition": fold.embargo_end,
                    "alertThreshold": fitted.alert_threshold,
                    "trainingBaseRate": training_base_rate,
                }
            )

        if not observed_labels:
            raise ValueError("Trial has no observed out-of-sample outcomes")
        observed_array = np.asarray(observed_labels, dtype=float)
        probability_array = np.asarray(predicted_probabilities, dtype=float)
        baseline_array = np.asarray(baseline_probabilities, dtype=float)
        metrics = binary_metrics(
            observed_array,
            probability_array,
            predicted_classes=np.asarray(alert_flags, dtype=bool),
        )
        baseline_metrics = binary_metrics(observed_array, baseline_array)
        bootstrap = paired_brier_bootstrap(
            observed_array,
            baseline_array,
            probability_array,
            block_lengths=self.bootstrap_block_lengths,
            repetitions=self.bootstrap_repetitions,
            seed=self.seed,
            fold_ids=np.asarray(observation_fold_ids, dtype=int),
        )

        event_dates = select_prediction_episode_starts(prediction_records, horizon)
        label_by_date = {
            str(record["date"]): float(record["label"])
            for record in prediction_records
            if record["label"] is not None
        }
        observed_event_dates = [
            date for date in event_dates if str(date) in label_by_date
        ]
        event_labels = [
            int(label_by_date[str(date)]) for date in observed_event_dates
        ]
        successes = sum(event_labels)
        failures = len(event_labels) - successes
        posterior = JeffreysPosterior(successes, failures).summary()

        return {
            "symbol": symbol,
            "candidateId": candidate.identifier,
            "family": candidate.family,
            "outcomeId": outcome.identifier,
            "horizon": horizon,
            "folds": fold_records,
            "metrics": metrics,
            "baselineMetrics": baseline_metrics,
            "pairedBrierBootstrap": bootstrap,
            "alerts": {
                "rawEpisodes": len(event_dates),
                "observed": len(event_labels),
                "excluded": len(event_dates) - len(event_labels),
                "successes": successes,
                "failures": failures,
                "dates": [str(date) for date in observed_event_dates],
                "rawDates": [str(date) for date in event_dates],
            },
            "posterior": {
                "distribution": f"Beta({successes + 0.5},{failures + 0.5})",
                "mean": posterior.mean,
                "median": posterior.median,
                "lower95": posterior.lower,
                "upper95": posterior.upper,
                "next10SuccessCountProbability": beta_binomial_predictive(
                    successes,
                    failures,
                    10,
                ),
            },
            "predictions": prediction_records,
        }

    @staticmethod
    def _eligibility(
        outcome_identifier: str,
        market: pd.DataFrame,
        atr14: pd.Series,
    ) -> pd.Series | None:
        close = market["close"]
        if outcome_identifier == "profitTakingLike":
            return (close / close.shift(20) - 1.0) >= 2.0 * atr14 / close
        if outcome_identifier.startswith("relief") or outcome_identifier == "fakeRelief":
            prior_high = close.shift(1).rolling(5, min_periods=5).max()
            return (prior_high - close) >= 1.5 * atr14
        return None


def _finite_or_none(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _require_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"Preregistration {key} must be an object")
    return result


def _require_text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"Preregistration {key} must be non-blank text")
    return result.strip()


def _require_text_list(value: Mapping[str, Any], key: str) -> list[str]:
    result = value.get(key)
    if not isinstance(result, list) or not result or not all(
        isinstance(item, str) and item for item in result
    ):
        raise ValueError(f"Preregistration {key} must be a text array")
    return result


def _require_integer_list(value: Mapping[str, Any], key: str) -> list[int]:
    result = value.get(key)
    if not isinstance(result, list) or not result or not all(
        isinstance(item, int) and item > 0 for item in result
    ):
        raise ValueError(f"Preregistration {key} must be a positive integer array")
    return result


def _require_positive_integer(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or result <= 0:
        raise ValueError(f"Preregistration {key} must be a positive integer")
    return result


def _require_non_negative_integer(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or result < 0:
        raise ValueError(f"Preregistration {key} must be a non-negative integer")
    return result


def _require_positive_number(value: Mapping[str, Any], key: str) -> float:
    result = value.get(key)
    if not isinstance(result, (int, float)) or isinstance(result, bool) or result <= 0:
        raise ValueError(f"Preregistration {key} must be a positive number")
    return float(result)


def _require_decimal_text(
    value: Mapping[str, Any],
    key: str,
    allow_zero: bool,
) -> float:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise ValueError(f"Toss candle {key} must be decimal text")
    try:
        number = float(raw)
    except ValueError as error:
        raise ValueError(f"Toss candle {key} must be decimal text") from error
    if not math.isfinite(number) or number < 0.0 or (not allow_zero and number == 0.0):
        raise ValueError(f"Toss candle {key} is outside its domain")
    return number
