from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from event_catalog import (
    MarketGroundTruthEvent,
    build_ground_truth_catalog,
    build_phase_catalog,
    build_signal_catalog,
    cluster_market_events,
    match_lead_times,
)
from research_pipeline import (
    HypothesisDefinition,
    ResearchProtocol,
    SpecialOutcomeDefinition,
    select_prediction_episode_starts,
)
from validation import (
    CausalProbabilityCalibrator,
    DailyFeatureEngine,
    FittedProbabilityCalibrator,
    JeffreysPosterior,
    OutcomeDefinition,
    OutcomeLabelEngine,
    ReliefOutcomeLabelEngine,
    WalkForwardSplitter,
    beta_binomial_predictive,
    benjamini_hochberg,
    binary_metrics,
    circular_shift_placebo,
    paired_brier_bootstrap,
    registered_random_seed,
    holm_adjust,
)


class CalibrationUnavailableError(ValueError):
    """Raised only when the frozen TSLA calibrator lacks registered pairs."""


@dataclass(frozen=True)
class PreparedStudyWindow:
    identifier: str
    symbol: str
    role: str
    market: pd.DataFrame
    analysis_start: int
    analysis_end: int
    features: pd.DataFrame
    scores: pd.DataFrame
    labels: Mapping[tuple[str, int], pd.DataFrame]
    eligibility: Mapping[tuple[str, int], pd.Series]
    candidate_unavailability_reasons: Mapping[str, str] = field(default_factory=dict)

    @property
    def analysis_sessions(self) -> int:
        return self.analysis_end - self.analysis_start


@dataclass(frozen=True)
class FrozenCalibrationArtifact:
    candidate_identifier: str
    outcome_identifier: str
    horizon: int
    source_window_identifier: str
    source_start_date: str
    source_end_date: str
    valid_training_pairs: int
    valid_base_rate_labels: int
    bin_edges: tuple[float, ...]
    bin_probabilities: tuple[float, ...]
    alert_threshold: float
    base_rate: float

    def to_document(self) -> dict[str, object]:
        return {
            "candidateId": self.candidate_identifier,
            "outcomeId": self.outcome_identifier,
            "horizon": self.horizon,
            "sourceWindowId": self.source_window_identifier,
            "sourceStartDate": self.source_start_date,
            "sourceEndDate": self.source_end_date,
            "validTrainingPairs": self.valid_training_pairs,
            "validBaseRateLabels": self.valid_base_rate_labels,
            "binEdges": list(self.bin_edges),
            "binProbabilities": list(self.bin_probabilities),
            "alertThreshold": self.alert_threshold,
            "baseRate": self.base_rate,
        }

    @property
    def sha256(self) -> str:
        canonical = json.dumps(
            self.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def calibrator(self) -> FittedProbabilityCalibrator:
        return FittedProbabilityCalibrator(
            bin_edges=self.bin_edges,
            bin_probabilities=self.bin_probabilities,
            alert_threshold=self.alert_threshold,
        )


class StudyWindowPreparer:
    def __init__(self, protocol: ResearchProtocol) -> None:
        self.protocol = protocol
        self.feature_engine = DailyFeatureEngine(
            protocol.percentile_minimum_sessions,
            protocol.percentile_maximum_sessions,
        )

    def prepare(
        self,
        identifier: str,
        symbol: str,
        role: str,
        market: pd.DataFrame,
        analysis_start: int,
        analysis_sessions: int,
        candidate_unavailability_reasons: Mapping[str, str] | None = None,
    ) -> PreparedStudyWindow:
        analysis_end = analysis_start + analysis_sessions
        if analysis_start < 0 or analysis_sessions <= 0 or analysis_end > len(market):
            raise ValueError("Study window is outside available market sessions")
        bounded_market = market.iloc[:analysis_end].copy()
        features = self.feature_engine.compute(bounded_market)
        scores = self.protocol.candidate_registry.score_all(features)
        unavailability_reasons = dict(candidate_unavailability_reasons or {})
        unknown_candidates = set(unavailability_reasons) - set(scores.columns)
        if unknown_candidates:
            raise ValueError(
                "Candidate unavailability contains unknown identifiers: "
                f"{sorted(unknown_candidates)}"
            )
        for candidate_identifier in unavailability_reasons:
            scores[candidate_identifier] = np.nan
        labels: dict[tuple[str, int], pd.DataFrame] = {}
        eligibility: dict[tuple[str, int], pd.Series] = {}
        trial_keys = sorted(
            {
                (hypothesis.outcome_identifier, hypothesis.horizon)
                for hypothesis in self.protocol.hypotheses
            }
        )
        for outcome_identifier, horizon in trial_keys:
            outcome = self.protocol.outcome_definitions[outcome_identifier]
            causal_eligibility = self._eligibility(
                outcome_identifier,
                bounded_market,
                features["atr14"],
            )
            eligibility[(outcome_identifier, horizon)] = (
                pd.Series(True, index=bounded_market.index, dtype=bool)
                if causal_eligibility is None
                else causal_eligibility
            )
            if isinstance(outcome, SpecialOutcomeDefinition):
                if causal_eligibility is None:
                    raise ValueError("Special relief outcomes require eligibility")
                labels[(outcome_identifier, horizon)] = ReliefOutcomeLabelEngine().label(
                    bounded_market,
                    features["atr14"],
                    outcome_identifier,
                    horizon,
                    causal_eligibility,
                )
            else:
                labels[(outcome_identifier, horizon)] = OutcomeLabelEngine(
                    {outcome_identifier: outcome}
                ).label(
                    bounded_market,
                    features["atr14"],
                    outcome_identifier,
                    horizon,
                    eligibility=causal_eligibility,
                )
        return PreparedStudyWindow(
            identifier=identifier,
            symbol=symbol,
            role=role,
            market=bounded_market,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            features=features,
            scores=scores,
            labels=labels,
            eligibility=eligibility,
            candidate_unavailability_reasons=unavailability_reasons,
        )

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


class TrialResearchEngine:
    def __init__(
        self,
        protocol: ResearchProtocol,
        bootstrap_repetitions: int | None = None,
        placebo_repetitions: int | None = None,
    ) -> None:
        self.protocol = protocol
        self.bootstrap_repetitions = (
            protocol.bootstrap_repetitions
            if bootstrap_repetitions is None
            else bootstrap_repetitions
        )
        self.placebo_repetitions = (
            protocol.bootstrap_repetitions
            if placebo_repetitions is None
            else placebo_repetitions
        )
        if self.bootstrap_repetitions <= 0 or self.placebo_repetitions <= 0:
            raise ValueError("Trial repetitions must be positive")
        candidate_identifiers = sorted(
            candidate.identifier
            for candidate in protocol.candidate_registry.candidates
        )
        outcome_identifiers = sorted(protocol.outcome_definitions)
        self.candidate_ordinals = {
            identifier: ordinal
            for ordinal, identifier in enumerate(candidate_identifiers)
        }
        self.outcome_ordinals = {
            identifier: ordinal
            for ordinal, identifier in enumerate(outcome_identifiers)
        }

    def evaluate_oof(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
        block_sessions: int = 120,
    ) -> dict[str, object]:
        if window.analysis_sessions % block_sessions != 0:
            raise ValueError("OOF window requires complete registered blocks")
        scores, labels, eligibility = self._trial_series(window, hypothesis)
        folds = WalkForwardSplitter(
            block_sessions=block_sessions,
            purge_sessions=self.protocol.purge_sessions,
            embargo_sessions=self.protocol.embargo_sessions,
        ).split(
            total_sessions=len(window.market),
            analysis_start=window.analysis_start,
            block_count=window.analysis_sessions // block_sessions,
        )
        prediction_records: list[dict[str, object]] = []
        fold_records: list[dict[str, object]] = []
        for fold_number, fold in enumerate(folds, start=1):
            training_positions = list(fold.training_positions)
            training_scores = scores.iloc[training_positions]
            training_labels = labels["label"].iloc[training_positions]
            fitted = self._fit_calibrator(training_scores, training_labels)
            training_base_rate = self._fit_base_rate(training_labels)
            test_scores = scores.iloc[fold.test_start : fold.test_end]
            test_probabilities = (
                pd.Series(np.nan, index=test_scores.index, dtype=float)
                if fitted is None
                else fitted.predict(test_scores)
            )
            for local_position, absolute_position in enumerate(
                range(fold.test_start, fold.test_end)
            ):
                prediction_records.append(
                    self._prediction_record(
                        window=window,
                        hypothesis=hypothesis,
                        absolute_position=absolute_position,
                        fold_number=fold_number,
                        score=test_scores.iloc[local_position],
                        probability=test_probabilities.iloc[local_position],
                        base_rate=training_base_rate,
                        alert_threshold=(
                            None if fitted is None else fitted.alert_threshold
                        ),
                        labels=labels,
                        eligibility=eligibility,
                    )
                )
            fold_records.append(
                {
                    "fold": fold_number,
                    "trainingSessions": fold.train_size,
                    "testSessions": fold.test_size,
                    "calibratorStatus": (
                        "available" if fitted is not None else "calibration_unavailable"
                    ),
                    "baseRateStatus": (
                        "available"
                        if training_base_rate is not None
                        else "base_rate_unavailable"
                    ),
                    "trainingEnd": window.market.index[fold.train_end - 1].strftime(
                        "%Y-%m-%d"
                    ),
                    "testStart": window.market.index[fold.test_start].strftime(
                        "%Y-%m-%d"
                    ),
                    "testEnd": window.market.index[fold.test_end - 1].strftime(
                        "%Y-%m-%d"
                    ),
                    "excludedPriorEmbargoRanges": [
                        [start, end] for start, end in fold.excluded_training_ranges
                    ],
                }
            )
        result = self._summarize(window, hypothesis, prediction_records)
        result["folds"] = fold_records
        result["stage"] = "candidate_selection_oof"
        return result

    def fit_final(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
    ) -> FrozenCalibrationArtifact:
        unavailability_reason = window.candidate_unavailability_reasons.get(
            hypothesis.candidate_identifier
        )
        if unavailability_reason is not None:
            raise CalibrationUnavailableError(unavailability_reason)
        scores, labels, _ = self._trial_series(window, hypothesis)
        analysis_scores = scores.iloc[window.analysis_start : window.analysis_end]
        analysis_labels = labels["label"].iloc[
            window.analysis_start : window.analysis_end
        ]
        fitted = self._fit_calibrator(analysis_scores, analysis_labels)
        base_rate = self._fit_base_rate(analysis_labels)
        if fitted is None or base_rate is None:
            raise CalibrationUnavailableError(
                "TSLA final artifact has insufficient registered pairs"
            )
        valid_pairs = pd.DataFrame(
            {"score": analysis_scores, "label": analysis_labels}
        ).replace([np.inf, -np.inf], np.nan).dropna()
        valid_labels = pd.to_numeric(analysis_labels, errors="coerce").dropna()
        return FrozenCalibrationArtifact(
            candidate_identifier=hypothesis.candidate_identifier,
            outcome_identifier=hypothesis.outcome_identifier,
            horizon=hypothesis.horizon,
            source_window_identifier=window.identifier,
            source_start_date=window.market.index[window.analysis_start].strftime(
                "%Y-%m-%d"
            ),
            source_end_date=window.market.index[window.analysis_end - 1].strftime(
                "%Y-%m-%d"
            ),
            valid_training_pairs=len(valid_pairs),
            valid_base_rate_labels=len(valid_labels),
            bin_edges=fitted.bin_edges,
            bin_probabilities=fitted.bin_probabilities,
            alert_threshold=fitted.alert_threshold,
            base_rate=base_rate,
        )

    def evaluate_frozen(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
        artifact: FrozenCalibrationArtifact,
    ) -> dict[str, object]:
        self._validate_artifact(hypothesis, artifact)
        scores, labels, eligibility = self._trial_series(window, hypothesis)
        test_scores = scores.iloc[window.analysis_start : window.analysis_end]
        probabilities = artifact.calibrator().predict(test_scores)
        prediction_records = [
            self._prediction_record(
                window=window,
                hypothesis=hypothesis,
                absolute_position=absolute_position,
                fold_number=1,
                score=test_scores.iloc[local_position],
                probability=probabilities.iloc[local_position],
                base_rate=artifact.base_rate,
                alert_threshold=artifact.alert_threshold,
                labels=labels,
                eligibility=eligibility,
            )
            for local_position, absolute_position in enumerate(
                range(window.analysis_start, window.analysis_end)
            )
        ]
        result = self._summarize(window, hypothesis, prediction_records)
        result["stage"] = window.role
        result["artifactSha256"] = artifact.sha256
        return result

    def _trial_series(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
    ) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
        if hypothesis.candidate_identifier not in window.scores:
            raise KeyError("Prepared window is missing a registered candidate")
        key = (hypothesis.outcome_identifier, hypothesis.horizon)
        if key not in window.labels or key not in window.eligibility:
            raise KeyError("Prepared window is missing a registered outcome")
        return (
            window.scores[hypothesis.candidate_identifier],
            window.labels[key],
            window.eligibility[key],
        )

    def _fit_calibrator(
        self,
        scores: pd.Series,
        labels: pd.Series,
    ) -> FittedProbabilityCalibrator | None:
        try:
            return CausalProbabilityCalibrator(
                bin_count=self.protocol.calibration_bin_count,
                alert_quantile=0.8,
                minimum_valid_pairs=self.protocol.calibration_minimum_valid_pairs,
            ).fit(scores, labels)
        except ValueError as error:
            if "at least" not in str(error):
                raise
            return None

    def _fit_base_rate(self, labels: pd.Series) -> float | None:
        observed = pd.to_numeric(labels, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(observed) < self.protocol.calibration_minimum_valid_pairs:
            return None
        if not observed.isin([0.0, 1.0]).all():
            raise ValueError("Base-rate labels must be binary")
        return float((observed.sum() + 0.5) / (len(observed) + 1.0))

    def _prediction_record(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
        absolute_position: int,
        fold_number: int,
        score: object,
        probability: object,
        base_rate: float | None,
        alert_threshold: float | None,
        labels: pd.DataFrame,
        eligibility: pd.Series,
    ) -> dict[str, object]:
        score_value = _finite_or_none(score)
        probability_value = _finite_or_none(probability)
        eligibility_value = eligibility.iloc[absolute_position]
        causally_eligible = bool(
            not pd.isna(eligibility_value) and bool(eligibility_value)
        )
        raw_alert = bool(
            causally_eligible
            and score_value is not None
            and alert_threshold is not None
            and score_value >= alert_threshold
        )
        label_value = _finite_or_none(labels["label"].iloc[absolute_position])
        first_passage_offset = labels["firstPassageOffset"].iloc[absolute_position]
        return {
            "date": window.market.index[absolute_position].strftime("%Y-%m-%d"),
            "sessionOrdinal": absolute_position - window.analysis_start,
            "fold": fold_number,
            "score": score_value,
            "probability": probability_value,
            "baselineProbability": base_rate,
            "alertThreshold": alert_threshold,
            "causalEligibility": causally_eligible,
            "rawAlert": raw_alert,
            "status": str(labels["status"].iloc[absolute_position]),
            "label": label_value,
            "firstPassageOffset": (
                None if pd.isna(first_passage_offset) else int(first_passage_offset)
            ),
        }

    def _summarize(
        self,
        window: PreparedStudyWindow,
        hypothesis: HypothesisDefinition,
        prediction_records: list[dict[str, object]],
    ) -> dict[str, object]:
        paired_records = [
            record
            for record in prediction_records
            if record["label"] is not None
            and record["probability"] is not None
            and record["baselineProbability"] is not None
        ]
        if not paired_records:
            unavailability_reason = window.candidate_unavailability_reasons.get(
                hypothesis.candidate_identifier
            )
            return {
                "trialId": hypothesis.identifier,
                "symbol": window.symbol,
                "windowId": window.identifier,
                "status": (
                    "data_unavailable"
                    if unavailability_reason is not None
                    else "probability_unavailable"
                ),
                "unavailabilityReason": unavailability_reason,
                "predictions": prediction_records,
                "metrics": None,
                "pairedBrierBootstrap": None,
                "placebo": {"status": "placebo_unavailable"},
                "alerts": (
                    None
                    if unavailability_reason is not None
                    else self._alert_summary(prediction_records, hypothesis.horizon)
                ),
            }
        labels = np.asarray([record["label"] for record in paired_records], dtype=float)
        probabilities = np.asarray(
            [record["probability"] for record in paired_records], dtype=float
        )
        baseline_probabilities = np.asarray(
            [record["baselineProbability"] for record in paired_records], dtype=float
        )
        raw_alerts = np.asarray(
            [record["rawAlert"] for record in paired_records], dtype=bool
        )
        fold_ids = np.asarray([record["fold"] for record in paired_records], dtype=int)
        expected_fold_ids = tuple(
            dict.fromkeys(int(record["fold"]) for record in prediction_records)
        )
        metrics = binary_metrics(
            labels,
            probabilities,
            predicted_classes=raw_alerts,
        )
        bootstrap = paired_brier_bootstrap(
            labels,
            baseline_probabilities,
            probabilities,
            fold_ids=fold_ids,
            expected_fold_ids=expected_fold_ids,
            block_lengths=self.protocol.bootstrap_block_lengths,
            repetitions=self.bootstrap_repetitions,
            seed_resolver=lambda block_length, fold_ordinal: self._seed(
                hypothesis,
                block_length,
                fold_ordinal,
                purpose_ordinal=1,
            ),
        )
        placebo = circular_shift_placebo(
            labels,
            baseline_probabilities,
            probabilities,
            fold_ids=fold_ids,
            expected_fold_ids=expected_fold_ids,
            horizon=hypothesis.horizon,
            repetitions=self.placebo_repetitions,
            seed_resolver=lambda fold_ordinal: self._seed(
                hypothesis,
                block_length=0,
                fold_ordinal=fold_ordinal,
                purpose_ordinal=2,
            ),
        )
        alert_summary = self._alert_summary(prediction_records, hypothesis.horizon)
        if bootstrap.get("status") != "available":
            status = "inference_unavailable"
        elif (
            int(alert_summary["observedEpisodes"])
            >= self.protocol.minimum_event_count
        ):
            status = "evaluated"
        else:
            status = "insufficient_evidence"
        return {
            "trialId": hypothesis.identifier,
            "symbol": window.symbol,
            "windowId": window.identifier,
            "status": status,
            "predictions": prediction_records,
            "metrics": metrics,
            "baselineMetrics": binary_metrics(labels, baseline_probabilities),
            "pairedBrierBootstrap": bootstrap,
            "placebo": placebo,
            "alerts": alert_summary,
            "calibration": _calibration_table(labels, probabilities),
        }

    def _alert_summary(
        self,
        prediction_records: list[dict[str, object]],
        horizon: int,
    ) -> dict[str, object]:
        starts = select_prediction_episode_starts(
            [
                {
                    "date": record["date"],
                    "score": record["score"],
                    "alertThreshold": record["alertThreshold"],
                    "causalEligibility": record["causalEligibility"],
                    "alert": record["rawAlert"],
                }
                for record in prediction_records
            ],
            horizon,
        )
        records_by_date = {
            str(record["date"]): record for record in prediction_records
        }
        observed_starts = [
            start
            for start in starts
            if records_by_date[str(start)]["label"] is not None
        ]
        successes = sum(
            int(records_by_date[str(start)]["label"])
            for start in observed_starts
        )
        failures = len(observed_starts) - successes
        posterior = JeffreysPosterior(successes, failures).summary()
        return {
            "rawEpisodes": len(starts),
            "observedEpisodes": len(observed_starts),
            "excludedEpisodes": len(starts) - len(observed_starts),
            "successes": successes,
            "failures": failures,
            "rawDates": [str(start) for start in starts],
            "observedDates": [str(start) for start in observed_starts],
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
        }

    def _seed(
        self,
        hypothesis: HypothesisDefinition,
        block_length: int,
        fold_ordinal: int,
        purpose_ordinal: int,
    ) -> int:
        return registered_random_seed(
            base_seed=self.protocol.seed,
            candidate_ordinal=self.candidate_ordinals[
                hypothesis.candidate_identifier
            ],
            outcome_ordinal=self.outcome_ordinals[
                hypothesis.outcome_identifier
            ],
            horizon=hypothesis.horizon,
            block_length=block_length,
            fold_ordinal=fold_ordinal,
            purpose_ordinal=purpose_ordinal,
        )

    def compare_predictions(
        self,
        hypothesis: HypothesisDefinition,
        candidate_result: Mapping[str, object],
        comparator_result: Mapping[str, object],
        comparison_dates: Sequence[str] | None = None,
    ) -> dict[str, object]:
        candidate_by_date = _paired_prediction_map(candidate_result)
        comparator_by_date = _paired_prediction_map(comparator_result)
        available_common_dates = set(candidate_by_date) & set(comparator_by_date)
        common_dates = (
            sorted(available_common_dates)
            if comparison_dates is None
            else sorted(set(comparison_dates))
        )
        if not set(common_dates).issubset(available_common_dates):
            raise ValueError("Candidate comparison mask contains unavailable dates")
        if not common_dates:
            raise ValueError("Candidate comparison has no common observations")
        candidate_fold_ids = _result_fold_ids(candidate_result)
        comparator_fold_ids = _result_fold_ids(comparator_result)
        if candidate_fold_ids != comparator_fold_ids:
            raise ValueError("Candidate comparison requires identical registered folds")
        labels: list[float] = []
        candidate_probabilities: list[float] = []
        comparator_probabilities: list[float] = []
        fold_ids: list[int] = []
        for date in common_dates:
            candidate = candidate_by_date[date]
            comparator = comparator_by_date[date]
            if candidate["label"] != comparator["label"]:
                raise ValueError("Candidate comparison labels must be shared")
            labels.append(float(candidate["label"]))
            candidate_probabilities.append(float(candidate["probability"]))
            comparator_probabilities.append(float(comparator["probability"]))
            fold_ids.append(int(candidate["fold"]))
        comparison = paired_brier_bootstrap(
            labels,
            comparator_probabilities,
            candidate_probabilities,
            fold_ids=fold_ids,
            expected_fold_ids=candidate_fold_ids,
            block_lengths=self.protocol.bootstrap_block_lengths,
            repetitions=self.bootstrap_repetitions,
            seed_resolver=lambda block_length, fold_ordinal: self._seed(
                hypothesis,
                block_length,
                fold_ordinal,
                purpose_ordinal=1,
            ),
        )
        comparison["commonObservationCount"] = len(common_dates)
        return comparison

    @staticmethod
    def _validate_artifact(
        hypothesis: HypothesisDefinition,
        artifact: FrozenCalibrationArtifact,
    ) -> None:
        if (
            artifact.candidate_identifier != hypothesis.candidate_identifier
            or artifact.outcome_identifier != hypothesis.outcome_identifier
            or artifact.horizon != hypothesis.horizon
        ):
            raise ValueError("Frozen artifact does not match hypothesis")


class RegisteredFormulaSelector:
    COMPLEX_KINDS = {"composite", "repaired"}

    def __init__(
        self,
        protocol: ResearchProtocol,
        engine: TrialResearchEngine,
    ) -> None:
        self.protocol = protocol
        self.engine = engine

    def select(
        self,
        tsla_oof_results: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        grouped: dict[tuple[str, str, int], list[HypothesisDefinition]] = {}
        for hypothesis in self.protocol.hypotheses:
            grouped.setdefault(
                (
                    hypothesis.family,
                    hypothesis.outcome_identifier,
                    hypothesis.horizon,
                ),
                [],
            ).append(hypothesis)

        decisions = [
            self._select_group(group_key, hypotheses, tsla_oof_results)
            for group_key, hypotheses in sorted(grouped.items())
        ]
        return {
            "groupCount": len(decisions),
            "selectedForExternalCount": sum(
                decision["finalStatus"] == "selected_for_external_evaluation"
                for decision in decisions
            ),
            "conditionallyValidCount": 0,
            "selectionScope": "tsla_oof_exploratory_only",
            "adoptionAllowed": False,
            "groups": decisions,
        }

    def _select_group(
        self,
        group_key: tuple[str, str, int],
        hypotheses: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        family, outcome_identifier, horizon = group_key
        available = [
            hypothesis
            for hypothesis in hypotheses
            if hypothesis.identifier in results
            and results[hypothesis.identifier].get("status") == "evaluated"
            and isinstance(results[hypothesis.identifier].get("metrics"), dict)
        ]
        coverage = [
            self._coverage_record(hypothesis, results.get(hypothesis.identifier))
            for hypothesis in hypotheses
        ]
        if not available:
            return {
                "familyId": family,
                "outcomeId": outcome_identifier,
                "horizon": horizon,
                "registeredWinnerCandidateId": None,
                "selectedCandidateId": None,
                "finalStatus": "no_valid_formula",
                "reason": "minimum_event_gate_or_probability_unavailable",
                "coverage": coverage,
                "commonMask": {
                    "observations": 0,
                    "winnerCandidateId": None,
                    "winnerChanged": False,
                },
                "complexVersusBaseline": None,
            }

        marginal_winner = self._choose(available, results)
        common_dates = self._common_prediction_dates(available, results)
        common_mask = self._common_mask(available, results, marginal_winner)
        if not common_dates:
            return {
                "familyId": family,
                "outcomeId": outcome_identifier,
                "horizon": horizon,
                "pointWinnerCandidateId": None,
                "registeredWinnerCandidateId": None,
                "uncertaintySetCandidateIds": [],
                "uncertaintyComparisons": [],
                "selectedCandidateId": None,
                "finalStatus": "no_valid_formula",
                "reason": "common_candidate_mask_unavailable",
                "failedGates": ["common_date_mask_availability"],
                "coverage": coverage,
                "commonMask": common_mask,
                "complexVersusBaseline": None,
            }
        point_winner_identifier = common_mask["winnerCandidateId"]
        point_winner = (
            marginal_winner
            if point_winner_identifier is None
            else next(
                hypothesis
                for hypothesis in available
                if hypothesis.candidate_identifier == point_winner_identifier
            )
        )
        (
            uncertainty_candidates,
            uncertainty_comparisons,
            uncertainty_gate_passed,
        ) = self._uncertainty_set(point_winner, available, results, common_dates)
        winner = min(
            uncertainty_candidates,
            key=lambda hypothesis: (
                self.protocol.candidate_complexity[
                    hypothesis.candidate_identifier
                ],
                hypothesis.candidate_identifier,
            ),
        )
        baseline_hypotheses = [
            hypothesis
            for hypothesis in available
            if hypothesis.candidate_kind == "baseline"
            or (
                family == "relief"
                and hypothesis.candidate_identifier == "relief.originalProxy"
            )
        ]
        best_baseline = (
            None if not baseline_hypotheses else self._choose(baseline_hypotheses, results)
        )
        marginal_best_baseline = best_baseline
        baseline_common_dates: list[str] = []
        baseline_brier_by_candidate: dict[str, float] = {}
        if baseline_hypotheses:
            (
                best_baseline,
                baseline_common_dates,
                baseline_brier_by_candidate,
            ) = self._best_baseline_on_common_mask(
                winner,
                baseline_hypotheses,
                results,
            )
        complex_comparison: dict[str, object] | None = None
        complex_gate_passed = True
        if winner.candidate_kind in self.COMPLEX_KINDS:
            if best_baseline is None:
                complex_gate_passed = False
            else:
                complex_comparison = self.engine.compare_predictions(
                    winner,
                    results[winner.identifier],
                    results[best_baseline.identifier],
                    comparison_dates=baseline_common_dates,
                )
                complex_comparison["comparatorCandidateId"] = (
                    best_baseline.candidate_identifier
                )
                complex_comparison["brierByBaselineCandidate"] = (
                    baseline_brier_by_candidate
                )
                complex_gate_passed = (
                    complex_comparison.get("status") == "available"
                    and float(complex_comparison["conservativeLower"]) > 0.0
                )
        base_rate_comparison = results[winner.identifier].get(
            "pairedBrierBootstrap"
        )
        base_rate_gate_passed = bool(
            isinstance(base_rate_comparison, dict)
            and float(base_rate_comparison.get("conservativeLower", -math.inf)) > 0.0
        )
        mask_gate_passed = bool(common_dates)
        selected = (
            winner
            if (
                complex_gate_passed
                and base_rate_gate_passed
                and mask_gate_passed
                and uncertainty_gate_passed
            )
            else None
        )
        failed_gates = [
            gate
            for gate, passed in (
                ("complex_formula_baseline_gate", complex_gate_passed),
                ("training_base_rate_gate", base_rate_gate_passed),
                ("common_date_mask_availability", mask_gate_passed),
                ("uncertainty_set_inference_available", uncertainty_gate_passed),
            )
            if not passed
        ]
        return {
            "familyId": family,
            "outcomeId": outcome_identifier,
            "horizon": horizon,
            "pointWinnerCandidateId": point_winner.candidate_identifier,
            "registeredWinnerCandidateId": winner.candidate_identifier,
            "uncertaintySetCandidateIds": sorted(
                hypothesis.candidate_identifier
                for hypothesis in uncertainty_candidates
            ),
            "uncertaintyComparisons": uncertainty_comparisons,
            "marginalBestFormulaBaselineCandidateId": (
                None
                if marginal_best_baseline is None
                else marginal_best_baseline.candidate_identifier
            ),
            "bestFormulaBaselineCandidateId": (
                None
                if best_baseline is None
                else best_baseline.candidate_identifier
            ),
            "selectedCandidateId": (
                None if selected is None else selected.candidate_identifier
            ),
            "finalStatus": (
                "selected_for_external_evaluation"
                if selected is not None
                else "no_valid_formula"
            ),
            "validationCeiling": "conditionally_valid_external_rule_not_preregistered",
            "failedGates": failed_gates,
            "coverage": coverage,
            "commonMask": common_mask,
            "complexVersusBaseline": complex_comparison,
        }

    def _uncertainty_set(
        self,
        point_winner: HypothesisDefinition,
        hypotheses: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
        common_dates: list[str],
    ) -> tuple[list[HypothesisDefinition], list[dict[str, object]], bool]:
        uncertainty_candidates = [point_winner]
        comparisons: list[dict[str, object]] = []
        inference_available = True
        for hypothesis in hypotheses:
            if hypothesis.identifier == point_winner.identifier:
                continue
            comparison = self.engine.compare_predictions(
                point_winner,
                results[point_winner.identifier],
                results[hypothesis.identifier],
                comparison_dates=common_dates,
            )
            comparison_record = {
                "candidateId": hypothesis.candidate_identifier,
                **comparison,
            }
            comparisons.append(comparison_record)
            if comparison.get("status") != "available":
                inference_available = False
                continue
            statistically_indistinguishable = (
                float(comparison["conservativeLower"]) <= 0.0
                <= float(comparison["conservativeUpper"])
            )
            if statistically_indistinguishable:
                uncertainty_candidates.append(hypothesis)
        return uncertainty_candidates, comparisons, inference_available

    @staticmethod
    def _common_prediction_dates(
        hypotheses: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
    ) -> list[str]:
        prediction_maps = [
            _paired_prediction_map(results[hypothesis.identifier])
            for hypothesis in hypotheses
        ]
        if not prediction_maps:
            return []
        return sorted(
            set.intersection(*(set(predictions) for predictions in prediction_maps))
        )

    def _best_baseline_on_common_mask(
        self,
        winner: HypothesisDefinition,
        baselines: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
    ) -> tuple[HypothesisDefinition | None, list[str], dict[str, float]]:
        prediction_maps = {
            hypothesis.identifier: _paired_prediction_map(results[hypothesis.identifier])
            for hypothesis in (winner, *baselines)
        }
        common_dates = set.intersection(
            *(set(predictions) for predictions in prediction_maps.values())
        )
        if not common_dates:
            return None, [], {}
        ordered_dates = sorted(common_dates)
        brier_by_candidate = {
            baseline.candidate_identifier: float(
                np.mean(
                    [
                        (
                            float(prediction_maps[baseline.identifier][date]["probability"])
                            - float(prediction_maps[baseline.identifier][date]["label"])
                        )
                        ** 2
                        for date in ordered_dates
                    ]
                )
            )
            for baseline in baselines
        }
        minimum_brier = min(brier_by_candidate.values())
        strongest = min(
            (
                baseline
                for baseline in baselines
                if abs(
                    brier_by_candidate[baseline.candidate_identifier]
                    - minimum_brier
                )
                <= 1.0e-12
            ),
            key=lambda baseline: (
                self.protocol.candidate_complexity[baseline.candidate_identifier],
                baseline.candidate_identifier,
            ),
        )
        return strongest, ordered_dates, brier_by_candidate

    def _choose(
        self,
        hypotheses: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
    ) -> HypothesisDefinition:
        brier_by_identifier = {
            hypothesis.identifier: float(
                results[hypothesis.identifier]["metrics"]["brierScore"]
            )
            for hypothesis in hypotheses
        }
        minimum_brier = min(brier_by_identifier.values())
        tied = [
            hypothesis
            for hypothesis in hypotheses
            if abs(brier_by_identifier[hypothesis.identifier] - minimum_brier)
            <= 1.0e-12
        ]
        return min(
            tied,
            key=lambda hypothesis: (
                self.protocol.candidate_complexity[
                    hypothesis.candidate_identifier
                ],
                hypothesis.candidate_identifier,
            ),
        )

    def _common_mask(
        self,
        hypotheses: list[HypothesisDefinition],
        results: Mapping[str, Mapping[str, object]],
        registered_winner: HypothesisDefinition,
    ) -> dict[str, object]:
        prediction_maps = {
            hypothesis.identifier: _paired_prediction_map(results[hypothesis.identifier])
            for hypothesis in hypotheses
        }
        common_dates = set.intersection(
            *(set(predictions) for predictions in prediction_maps.values())
        )
        if not common_dates:
            return {
                "observations": 0,
                "winnerCandidateId": None,
                "winnerChanged": True,
                "brierByCandidate": {},
            }
        brier_by_candidate: dict[str, float] = {}
        for hypothesis in hypotheses:
            predictions = prediction_maps[hypothesis.identifier]
            losses = [
                (
                    float(predictions[date]["probability"])
                    - float(predictions[date]["label"])
                )
                ** 2
                for date in sorted(common_dates)
            ]
            brier_by_candidate[hypothesis.candidate_identifier] = float(
                np.mean(losses)
            )
        minimum_brier = min(brier_by_candidate.values())
        tied_candidate_ids = [
            candidate_identifier
            for candidate_identifier, brier in brier_by_candidate.items()
            if abs(brier - minimum_brier) <= 1.0e-12
        ]
        common_winner = min(
            tied_candidate_ids,
            key=lambda candidate_identifier: (
                self.protocol.candidate_complexity[candidate_identifier],
                candidate_identifier,
            ),
        )
        return {
            "observations": len(common_dates),
            "winnerCandidateId": common_winner,
            "winnerChanged": (
                common_winner != registered_winner.candidate_identifier
            ),
            "brierByCandidate": brier_by_candidate,
        }

    @staticmethod
    def _coverage_record(
        hypothesis: HypothesisDefinition,
        result: Mapping[str, object] | None,
    ) -> dict[str, object]:
        predictions = [] if result is None else result.get("predictions", [])
        valid = sum(
            record.get("label") is not None
            and record.get("probability") is not None
            for record in predictions
        )
        return {
            "candidateId": hypothesis.candidate_identifier,
            "status": None if result is None else result.get("status"),
            "validProbabilityLabels": valid,
            "testSessions": len(predictions),
            "coverage": 0.0 if not predictions else valid / len(predictions),
        }


class MultipleTestingController:
    def __init__(self, protocol: ResearchProtocol) -> None:
        self.protocol = protocol

    def apply(
        self,
        tsla_oof_results: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        grouped: dict[tuple[str, str, int], list[HypothesisDefinition]] = {}
        for hypothesis in self.protocol.hypotheses:
            grouped.setdefault(
                (
                    hypothesis.family,
                    hypothesis.outcome_identifier,
                    hypothesis.horizon,
                ),
                [],
            ).append(hypothesis)
        bh_families: list[dict[str, object]] = []
        for group_key, hypotheses in sorted(grouped.items()):
            valid: list[tuple[HypothesisDefinition, float]] = []
            excluded: list[str] = []
            for hypothesis in hypotheses:
                result = tsla_oof_results.get(hypothesis.identifier)
                bootstrap = (
                    None
                    if result is None
                    else result.get("pairedBrierBootstrap")
                )
                if (
                    result is None
                    or result.get("status") != "evaluated"
                    or not isinstance(bootstrap, dict)
                    or bootstrap.get("oneSidedPValue") is None
                ):
                    excluded.append(hypothesis.identifier)
                    continue
                valid.append(
                    (
                        hypothesis,
                        float(bootstrap["oneSidedPValue"]),
                    )
                )
            adjusted_values = benjamini_hochberg(
                [raw_p_value for _, raw_p_value in valid]
            )
            family, outcome_identifier, horizon = group_key
            bh_families.append(
                {
                    "familyId": family,
                    "outcomeId": outcome_identifier,
                    "horizon": horizon,
                    "included": [
                        {
                            "trialId": hypothesis.identifier,
                            "rawPValue": raw_p_value,
                            "adjustedPValue": adjusted_p_value,
                            "significant": (
                                adjusted_p_value < self.protocol.significance_alpha
                            ),
                        }
                        for (hypothesis, raw_p_value), adjusted_p_value in zip(
                            valid,
                            adjusted_values,
                            strict=True,
                        )
                    ],
                    "excludedTrialIds": excluded,
                }
            )

        holm_raw_values: list[float] = []
        holm_statuses: list[str] = []
        for trial_identifier in self.protocol.primary_holm_hypotheses:
            result = tsla_oof_results.get(trial_identifier)
            bootstrap = (
                None if result is None else result.get("pairedBrierBootstrap")
            )
            if (
                result is None
                or result.get("status") != "evaluated"
                or not isinstance(bootstrap, dict)
                or bootstrap.get("oneSidedPValue") is None
            ):
                holm_raw_values.append(1.0)
                holm_statuses.append("insufficient")
            else:
                holm_raw_values.append(float(bootstrap["oneSidedPValue"]))
                holm_statuses.append("evaluated")
        holm_adjusted_values = holm_adjust(holm_raw_values)
        holm_primary = [
            {
                "trialId": trial_identifier,
                "status": status,
                "rawPValue": raw_p_value,
                "adjustedPValue": adjusted_p_value,
                "significant": bool(
                    status == "evaluated"
                    and adjusted_p_value < self.protocol.significance_alpha
                ),
            }
            for trial_identifier, status, raw_p_value, adjusted_p_value in zip(
                self.protocol.primary_holm_hypotheses,
                holm_statuses,
                holm_raw_values,
                holm_adjusted_values,
                strict=True,
            )
        ]
        return {
            "alpha": self.protocol.significance_alpha,
            "bhSecondary": bh_families,
            "holmPrimary": holm_primary,
        }


class FormulaStudyRunner:
    REQUIRED_WINDOWS = (
        "tslaPrimary",
        "tslaSensitivity",
        "nvdaPrimary",
        "muLatest120",
        "hynixLatest120",
    )

    def __init__(
        self,
        protocol: ResearchProtocol,
        bootstrap_repetitions: int | None = None,
        placebo_repetitions: int | None = None,
    ) -> None:
        self.protocol = protocol
        self.engine = TrialResearchEngine(
            protocol,
            bootstrap_repetitions=bootstrap_repetitions,
            placebo_repetitions=placebo_repetitions,
        )

    def run_prepared(
        self,
        windows: Mapping[str, PreparedStudyWindow],
    ) -> dict[str, object]:
        missing_windows = set(self.REQUIRED_WINDOWS) - set(windows)
        if missing_windows:
            raise ValueError(f"Study runner is missing windows: {sorted(missing_windows)}")
        trial_results: list[dict[str, object]] = []
        frozen_calibrators: list[dict[str, object]] = []
        predictions: list[dict[str, object]] = []
        metrics: list[dict[str, object]] = []
        tsla_oof_results: dict[str, dict[str, object]] = {}
        stages_by_trial: dict[str, dict[str, dict[str, object]]] = {}
        event_stages: list[
            tuple[
                HypothesisDefinition,
                str,
                PreparedStudyWindow,
                Mapping[str, object],
            ]
        ] = []

        for hypothesis in self.protocol.hypotheses:
            oof = self.engine.evaluate_oof(windows["tslaPrimary"], hypothesis)
            tsla_oof_results[hypothesis.identifier] = oof
            stages: dict[str, dict[str, object]] = {
                "tslaOof": _stage_summary(oof)
            }
            self._collect_stage(
                predictions,
                metrics,
                hypothesis,
                "tslaOof",
                oof,
            )
            event_stages.append(
                (hypothesis, "tslaOof", windows["tslaPrimary"], oof)
            )
            stages_by_trial[hypothesis.identifier] = stages

        selection = RegisteredFormulaSelector(
            self.protocol,
            self.engine,
        ).select(tsla_oof_results)
        multiple_testing = MultipleTestingController(
            self.protocol
        ).apply(tsla_oof_results)

        for hypothesis in self.protocol.hypotheses:
            stages = stages_by_trial[hypothesis.identifier]
            external_windows = (
                ("tslaSensitivity", windows["tslaSensitivity"]),
                ("nvdaExternal", windows["nvdaPrimary"]),
                ("muHoldout", windows["muLatest120"]),
                ("hynixHoldout", windows["hynixLatest120"]),
            )
            try:
                artifact = self.engine.fit_final(
                    windows["tslaPrimary"],
                    hypothesis,
                )
            except CalibrationUnavailableError as error:
                artifact_document = {
                    "trialId": hypothesis.identifier,
                    "status": "calibration_unavailable",
                    "reason": str(error),
                }
                frozen_calibrators.append(artifact_document)
                for stage_name, external_window in external_windows:
                    unavailable_stage = {
                        "symbol": external_window.symbol,
                        "status": "calibration_unavailable",
                        "unavailabilityReason": str(error),
                    }
                    stages[stage_name] = _stage_summary(unavailable_stage)
                    self._collect_stage(
                        predictions,
                        metrics,
                        hypothesis,
                        stage_name,
                        unavailable_stage,
                    )
            else:
                artifact_document = {
                    "trialId": hypothesis.identifier,
                    "status": "available",
                    "sha256": artifact.sha256,
                    "artifact": artifact.to_document(),
                }
                frozen_calibrators.append(artifact_document)
                for stage_name, external_window in external_windows:
                    stage_result = self.engine.evaluate_frozen(
                        external_window,
                        hypothesis,
                        artifact,
                    )
                    if stage_name in {"muHoldout", "hynixHoldout"}:
                        stage_result["fourMonthSubset"] = (
                            descriptive_four_month_subset(
                                stage_result["predictions"],
                                self.protocol.four_month_start_date,
                                self.protocol.four_month_end_date,
                            )
                        )
                    stages[stage_name] = _stage_summary(stage_result)
                    self._collect_stage(
                        predictions,
                        metrics,
                        hypothesis,
                        stage_name,
                        stage_result,
                    )
                    event_stages.append(
                        (
                            hypothesis,
                            stage_name,
                            external_window,
                            stage_result,
                        )
                    )
            trial_results.append(
                {
                    "trialId": hypothesis.identifier,
                    "familyId": hypothesis.family,
                    "candidateId": hypothesis.candidate_identifier,
                    "candidateKind": hypothesis.candidate_kind,
                    "outcomeId": hypothesis.outcome_identifier,
                    "horizon": hypothesis.horizon,
                    "stages": stages,
                }
            )

        return {
            "protocolVersion": self.protocol.version,
            "hypothesisCount": len(self.protocol.hypotheses),
            "trialResults": trial_results,
            "frozenCalibrators": frozen_calibrators,
            "predictions": predictions,
            "metrics": metrics,
            "selection": selection,
            "multipleTesting": multiple_testing,
            "adoptionDecision": {
                "status": "adoption_not_identifiable",
                "reason": "external_adoption_rule_not_preregistered",
                "adoptableFormulaCount": 0,
                "tslaExploratoryCandidateCount": selection[
                    "selectedForExternalCount"
                ],
                "externalStagesDescriptiveOnly": True,
                "multipleTestingPromotionAllowed": False,
            },
            "events": self._build_events(event_stages),
        }

    @staticmethod
    def _collect_stage(
        predictions: list[dict[str, object]],
        metrics: list[dict[str, object]],
        hypothesis: HypothesisDefinition,
        stage_name: str,
        result: Mapping[str, object],
    ) -> None:
        for prediction in result.get("predictions", []):
            predictions.append(
                {
                    "trialId": hypothesis.identifier,
                    "stage": stage_name,
                    "symbol": result["symbol"],
                    **prediction,
                }
            )
        metrics.append(
            {
                "trialId": hypothesis.identifier,
                "stage": stage_name,
                "symbol": result["symbol"],
                "status": result["status"],
                "metrics": result.get("metrics"),
                "baselineMetrics": result.get("baselineMetrics"),
                "pairedBrierBootstrap": result.get("pairedBrierBootstrap"),
                "placebo": result.get("placebo"),
                "alerts": result.get("alerts"),
                "calibration": result.get("calibration"),
                "fourMonthSubset": result.get("fourMonthSubset"),
                "unavailabilityReason": result.get("unavailabilityReason"),
                "intervalAvailability": {
                    "brierDifference": {
                        "status": (
                            "available"
                            if isinstance(result.get("pairedBrierBootstrap"), dict)
                            and result["pairedBrierBootstrap"].get("status")
                            == "available"
                            else "not_identifiable"
                        )
                    },
                    "prAuc": {
                        "status": "not_identifiable",
                        "reason": "registered_resampling_statistic_incomplete",
                    },
                    "mcc": {
                        "status": "not_identifiable",
                        "reason": "registered_resampling_statistic_incomplete",
                    },
                    "leadTime": {
                        "status": "not_identifiable",
                        "reason": "registered_resampling_unit_incomplete",
                    },
                },
            }
        )

    def _build_events(
        self,
        stages: list[
            tuple[
                HypothesisDefinition,
                str,
                PreparedStudyWindow,
                Mapping[str, object],
            ]
        ],
    ) -> dict[str, object]:
        ground_truth_documents: list[dict[str, object]] = []
        phase_documents: list[dict[str, object]] = []
        signal_documents: list[dict[str, object]] = []
        cached_ground_truth: dict[tuple[str, str, int], object] = {}
        for hypothesis, stage_name, window, result in stages:
            key = (
                stage_name,
                hypothesis.outcome_identifier,
                hypothesis.horizon,
            )
            label_frame = window.labels[
                (hypothesis.outcome_identifier, hypothesis.horizon)
            ].iloc[window.analysis_start : window.analysis_end]
            ground_truth = cached_ground_truth.get(key)
            if ground_truth is None:
                ground_truth = build_ground_truth_catalog(
                    symbol=window.symbol,
                    outcome_id=hypothesis.outcome_identifier,
                    horizon=hypothesis.horizon,
                    label_frame=label_frame,
                )
                cached_ground_truth[key] = ground_truth
                prior_session_dates = tuple(
                    timestamp.strftime("%Y-%m-%d")
                    for timestamp in window.market.index[
                        max(0, window.analysis_start - 5) : window.analysis_start
                    ]
                )
                phase_catalog = build_phase_catalog(
                    ground_truth,
                    label_frame,
                    prior_session_dates=prior_session_dates,
                )
                ground_truth_documents.append(
                    {
                        "stage": stage_name,
                        **_dataclass_document(ground_truth),
                    }
                )
                phase_document = {
                    "stage": stage_name,
                    **_dataclass_document(phase_catalog),
                }
                for episode in phase_document["episodes"]:
                    episode["market"] = {
                        "start": self._market_observation(
                            window, str(episode["start_date"])
                        ),
                        "fullTarget": self._market_observation(
                            window, str(episode["full_target_date"])
                        ),
                        "extreme": self._market_observation(
                            window, str(episode["extreme_date"])
                        ),
                        "confirmation": self._optional_market_observation(
                            window, episode["confirmation_date"]
                        ),
                        "fakeRelief": self._optional_market_observation(
                            window, episode["fake_relief_date"]
                        ),
                        "end": self._market_observation(
                            window, str(episode["end_date"])
                        ),
                    }
                phase_documents.append(phase_document)
            predictions = result.get("predictions", [])
            if len(predictions) != len(label_frame):
                raise ValueError("Signal event axis must match the evaluation window")
            episode_starts = select_prediction_episode_starts(
                [
                    {
                        "date": record["date"],
                        "score": record["score"],
                        "alertThreshold": record["alertThreshold"],
                        "causalEligibility": record["causalEligibility"],
                        "alert": record["rawAlert"],
                    }
                    for record in predictions
                ],
                hypothesis.horizon,
            )
            episode_start_dates = set(str(date) for date in episode_starts)
            alerts = pd.Series(
                [
                    str(record["date"]) in episode_start_dates
                    for record in predictions
                ],
                index=label_frame.index,
                dtype=bool,
            )
            signal_catalog = build_signal_catalog(
                symbol=window.symbol,
                candidate_id=hypothesis.candidate_identifier,
                outcome_id=hypothesis.outcome_identifier,
                horizon=hypothesis.horizon,
                alerts=alerts,
            )
            lead_times = match_lead_times(signal_catalog, ground_truth)
            signal_documents.append(
                {
                    "trialId": hypothesis.identifier,
                    "stage": stage_name,
                    "catalog": _dataclass_document(signal_catalog),
                    "leadTimes": [
                        _dataclass_document(match) for match in lead_times
                    ],
                }
            )
        market_events: list[MarketGroundTruthEvent] = []
        for document in ground_truth_documents:
            if document["stage"] == "tslaSensitivity":
                continue
            outcome_identifier = str(document["outcome_id"])
            horizon = int(document["horizon"])
            target_direction = self._target_direction(outcome_identifier)
            for episode in document["episodes"]:
                market_events.append(
                    MarketGroundTruthEvent(
                        symbol=str(document["symbol"]),
                        outcome_id=outcome_identifier,
                        horizon=horizon,
                        target_direction=target_direction,
                        target_date=str(episode["target_date"]),
                    )
                )
        market_clusters = cluster_market_events(market_events)
        return {
            "groundTruth": ground_truth_documents,
            "phases": phase_documents,
            "signals": signal_documents,
            "marketClusters": [
                _dataclass_document(cluster) for cluster in market_clusters
            ],
            "marketClusterWeightApplication": (
                "event_catalog_only_no_global_probability_metric"
            ),
            "globalMetrics": {
                "status": "not_identifiable",
                "reason": "no_preregistered_daily_row_weight_mapping",
                "claimsAllowed": False,
            },
        }

    @staticmethod
    def _market_observation(
        window: PreparedStudyWindow,
        session_date: str,
    ) -> dict[str, object]:
        positions = np.flatnonzero(
            window.market.index.strftime("%Y-%m-%d").to_numpy() == session_date
        )
        if len(positions) != 1:
            raise ValueError("Phase market observation date is unavailable")
        position = int(positions[0])
        candle = window.market.iloc[position]
        atr14 = (
            None
            if "atr14" not in window.features
            else _finite_or_none(window.features["atr14"].iloc[position])
        )
        return {
            "date": session_date,
            "close": float(candle["close"]),
            "atr14": atr14,
            "volume": float(candle["volume"]),
        }

    @classmethod
    def _optional_market_observation(
        cls,
        window: PreparedStudyWindow,
        session_date: object,
    ) -> dict[str, object] | None:
        if session_date is None:
            return None
        return cls._market_observation(window, str(session_date))

    def _target_direction(self, outcome_identifier: str) -> str:
        outcome = self.protocol.outcome_definitions[outcome_identifier]
        if isinstance(outcome, OutcomeDefinition):
            return outcome.barrier.target_direction
        return "lower" if outcome_identifier == "fakeRelief" else "upper"


def _stage_summary(result: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in result.items()
        if key != "predictions"
    }


def descriptive_four_month_subset(
    prediction_records: list[Mapping[str, object]],
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    if start_date > end_date:
        raise ValueError("Four-month subset dates are reversed")
    subset = [
        record
        for record in prediction_records
        if start_date <= str(record["date"]) <= end_date
    ]
    paired = [
        record
        for record in subset
        if record.get("label") is not None
        and record.get("probability") is not None
    ]
    metrics = None
    if paired:
        metrics = binary_metrics(
            [float(record["label"]) for record in paired],
            [float(record["probability"]) for record in paired],
            predicted_classes=[bool(record["rawAlert"]) for record in paired],
        )
    return {
        "startDate": start_date,
        "endDate": end_date,
        "relationship": "subset_of_single_locked_120_session_holdout",
        "duplicateAggregationAllowed": False,
        "sessions": len(subset),
        "observedPairs": len(paired),
        "metrics": metrics,
        "inferenceStatus": "descriptive_only_not_reaggregated",
    }


def _calibration_table(
    labels: np.ndarray,
    probabilities: np.ndarray,
) -> list[dict[str, float | int]]:
    table: list[dict[str, float | int]] = []
    for probability in sorted(set(float(value) for value in probabilities)):
        mask = probabilities == probability
        table.append(
            {
                "predictedProbability": probability,
                "observations": int(np.count_nonzero(mask)),
                "observedFrequency": float(labels[mask].mean()),
            }
        )
    return table


def _finite_or_none(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _paired_prediction_map(
    result: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    return {
        str(record["date"]): record
        for record in result.get("predictions", [])
        if record.get("label") is not None
        and record.get("probability") is not None
    }


def _result_fold_ids(result: Mapping[str, object]) -> tuple[int, ...]:
    fold_ids = tuple(
        dict.fromkeys(
            int(record["fold"])
            for record in result.get("predictions", [])
            if record.get("fold") is not None
        )
    )
    if not fold_ids:
        raise ValueError("Candidate comparison has no registered folds")
    return fold_ids


def _dataclass_document(value: object) -> dict[str, object]:
    document = _json_compatible(asdict(value))
    if not isinstance(document, dict):
        raise TypeError("Dataclass document must be an object")
    return document


def _json_compatible(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value
