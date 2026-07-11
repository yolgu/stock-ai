import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from research_pipeline import HypothesisDefinition, ResearchProtocol  # noqa: E402
from study_runner import (  # noqa: E402
    FormulaStudyRunner,
    FrozenCalibrationArtifact,
    MultipleTestingController,
    PreparedStudyWindow,
    RegisteredFormulaSelector,
    StudyWindowPreparer,
    TrialResearchEngine,
    descriptive_four_month_subset,
)


def make_market(count: int = 900, start: str = "2018-01-02") -> pd.DataFrame:
    index = pd.date_range(start, periods=count, freq="B", tz="UTC")
    increments = 0.001 + 0.012 * np.sin(np.arange(count) / 7.0)
    close = 100.0 * np.exp(np.cumsum(increments))
    open_price = close * (1.0 - 0.002 * np.cos(np.arange(count) / 3.0))
    high = np.maximum(open_price, close) * 1.012
    low = np.minimum(open_price, close) * 0.988
    volume = 1_000_000.0 + 20_000.0 * (np.arange(count) % 23)
    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


class StudyWindowPreparerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )

    def test_precomputes_all_candidates_and_censors_every_window_tail(self) -> None:
        market = make_market()

        window = StudyWindowPreparer(self.protocol).prepare(
            identifier="TSLA-primary",
            symbol="TSLA",
            role="candidate_selection",
            market=market,
            analysis_start=300,
            analysis_sessions=360,
        )

        self.assertEqual(window.scores.shape[1], 19)
        self.assertEqual(len(window.market), 660)
        labels = window.labels[("panicContinuation", 10)]
        self.assertEqual(
            labels["status"].iloc[-10:].tolist(),
            ["right_censored_excluded"] * 10,
        )
        self.assertTrue(labels["label"].iloc[-10:].isna().all())

    def test_data_unit_failure_makes_dependent_candidates_unavailable_instead_of_zero(self) -> None:
        market = make_market()

        window = StudyWindowPreparer(self.protocol).prepare(
            identifier="TSLA-primary",
            symbol="TSLA",
            role="candidate_selection",
            market=market,
            analysis_start=300,
            analysis_sessions=360,
            candidate_unavailability_reasons={
                "fomo.documented": "unadjusted_split_volume_unit",
            },
        )

        self.assertTrue(window.scores["fomo.documented"].isna().all())
        self.assertTrue(
            window.scores["fomo.baseline.momentum5"].notna().any()
        )
        self.assertEqual(
            window.candidate_unavailability_reasons["fomo.documented"],
            "unadjusted_split_volume_unit",
        )
        hypothesis = next(
            item
            for item in self.protocol.hypotheses
            if item.identifier == "fomo.documented::fomoContinuation@1"
        )
        result = TrialResearchEngine(
            self.protocol,
            bootstrap_repetitions=1,
            placebo_repetitions=1,
        ).evaluate_oof(window, hypothesis)
        self.assertEqual(result["status"], "data_unavailable")
        self.assertEqual(
            result["unavailabilityReason"],
            "unadjusted_split_volume_unit",
        )
        self.assertIsNone(result["alerts"])


class TrialResearchEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        cls.hypothesis = next(
            hypothesis
            for hypothesis in cls.protocol.hypotheses
            if hypothesis.identifier
            == "panic.baseline.drawdown3::panicContinuation@5"
        )
        preparer = StudyWindowPreparer(cls.protocol)
        cls.primary_window = preparer.prepare(
            identifier="TSLA-primary",
            symbol="TSLA",
            role="candidate_selection",
            market=make_market(),
            analysis_start=300,
            analysis_sessions=360,
        )
        cls.external_window = preparer.prepare(
            identifier="NVDA-primary",
            symbol="NVDA",
            role="external_replication",
            market=make_market(start="2020-01-02"),
            analysis_start=420,
            analysis_sessions=360,
        )

    def test_oof_execution_preserves_exact_fold_and_registered_metric_contracts(self) -> None:
        result = TrialResearchEngine(
            self.protocol,
            bootstrap_repetitions=20,
            placebo_repetitions=20,
        ).evaluate_oof(self.primary_window, self.hypothesis)

        self.assertEqual(len(result["predictions"]), 360)
        self.assertEqual([fold["testSessions"] for fold in result["folds"]], [120] * 3)
        self.assertEqual(result["pairedBrierBootstrap"]["foldCount"], 3)
        observed_alerts = sum(
            prediction["rawAlert"]
            for prediction in result["predictions"]
            if prediction["label"] is not None
            and prediction["probability"] is not None
        )
        self.assertEqual(
            result["metrics"]["truePositive"]
            + result["metrics"]["falsePositive"],
            observed_alerts,
        )
        self.assertTrue(math.isfinite(result["metrics"]["brierScore"]))

    def test_external_labels_cannot_change_a_frozen_tsla_probability_artifact(self) -> None:
        engine = TrialResearchEngine(
            self.protocol,
            bootstrap_repetitions=20,
            placebo_repetitions=20,
        )
        artifact = engine.fit_final(self.primary_window, self.hypothesis)
        original = engine.evaluate_frozen(
            self.external_window,
            self.hypothesis,
            artifact,
        )
        key = (self.hypothesis.outcome_identifier, self.hypothesis.horizon)
        mutated_labels = self.external_window.labels[key].copy()
        finite = mutated_labels["label"].notna()
        mutated_labels.loc[finite, "label"] = 1.0 - mutated_labels.loc[finite, "label"]
        labels = dict(self.external_window.labels)
        labels[key] = mutated_labels
        mutated_window = replace(self.external_window, labels=labels)

        mutated = engine.evaluate_frozen(mutated_window, self.hypothesis, artifact)

        self.assertEqual(original["artifactSha256"], artifact.sha256)
        self.assertEqual(mutated["artifactSha256"], artifact.sha256)
        self.assertEqual(
            [prediction["probability"] for prediction in original["predictions"]],
            [prediction["probability"] for prediction in mutated["predictions"]],
        )
        self.assertEqual(
            [prediction["rawAlert"] for prediction in original["predictions"]],
            [prediction["rawAlert"] for prediction in mutated["predictions"]],
        )

    def test_inference_is_unavailable_when_a_registered_fold_has_no_probability_pairs(self) -> None:
        records = [
            {
                "date": f"2026-07-{position + 1:02d}",
                "fold": fold,
                "score": 20.0 + position,
                "probability": None if fold == 1 else probability,
                "baselineProbability": 0.5,
                "alertThreshold": 80.0,
                "causalEligibility": True,
                "rawAlert": False,
                "status": "failure",
                "label": float(position % 2),
                "firstPassageOffset": None,
            }
            for position, (fold, probability) in enumerate(
                ((1, 0.2), (1, 0.8), (2, 0.2), (2, 0.8), (3, 0.2), (3, 0.8))
            )
        ]

        result = TrialResearchEngine(
            self.protocol,
            bootstrap_repetitions=3,
            placebo_repetitions=3,
        )._summarize(self.primary_window, self.hypothesis, records)

        self.assertEqual(result["status"], "inference_unavailable")
        self.assertEqual(
            result["pairedBrierBootstrap"]["status"],
            "bootstrap_unavailable",
        )
        self.assertEqual(result["pairedBrierBootstrap"]["emptyFoldIds"], [1])


class FormulaStudyRunnerTest(unittest.TestCase):
    def test_unexpected_final_fit_value_error_is_not_mislabeled_as_calibration_unavailable(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        protocol = replace(
            full_protocol,
            hypotheses=(full_protocol.hypotheses[0],),
        )
        runner = FormulaStudyRunner(
            protocol,
            bootstrap_repetitions=1,
            placebo_repetitions=1,
        )
        runner.engine.evaluate_oof = lambda window, hypothesis: {
            "trialId": hypothesis.identifier,
            "symbol": "TSLA",
            "status": "insufficient_evidence",
            "predictions": [],
            "metrics": None,
            "pairedBrierBootstrap": None,
            "alerts": {"observedEpisodes": 0},
        }

        def fail_final_fit(
            window: object,
            hypothesis: HypothesisDefinition,
        ) -> FrozenCalibrationArtifact:
            raise ValueError("unexpected final-fit implementation failure")

        runner.engine.fit_final = fail_final_fit
        runner._build_events = lambda stages: {}
        windows = {identifier: object() for identifier in runner.REQUIRED_WINDOWS}

        with self.assertRaisesRegex(ValueError, "unexpected final-fit"):
            runner.run_prepared(windows)

    def test_event_phases_include_five_pre_anchor_prodrome_sessions(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        hypothesis = next(
            item
            for item in protocol.hypotheses
            if item.identifier
            == "fomo.baseline.momentum5::fomoContinuation@1"
        )
        index = pd.date_range("2026-06-22", periods=8, freq="B", tz="UTC")
        market = pd.DataFrame(
            {
                "open": np.arange(100.0, 108.0),
                "high": np.arange(101.0, 109.0),
                "low": np.arange(99.0, 107.0),
                "close": np.arange(100.0, 108.0),
                "volume": np.full(8, 1_000.0),
            },
            index=index,
        )
        labels = pd.DataFrame(
            {
                "status": ["failure"] * 5 + ["success", "failure", "failure"],
                "label": [0.0] * 5 + [1.0, 0.0, 0.0],
                "firstPassageOffset": [np.nan] * 5 + [1.0, np.nan, np.nan],
            },
            index=index,
        )
        window = PreparedStudyWindow(
            identifier="prodrome-fixture",
            symbol="TSLA",
            role="candidate_selection",
            market=market,
            analysis_start=5,
            analysis_end=8,
            features=pd.DataFrame({"atr14": [2.0] * 8}, index=index),
            scores=pd.DataFrame(index=index),
            labels={(hypothesis.outcome_identifier, hypothesis.horizon): labels},
            eligibility={
                (hypothesis.outcome_identifier, hypothesis.horizon): pd.Series(
                    [True] * 8, index=index
                )
            },
        )
        predictions = [
            {
                "date": date.strftime("%Y-%m-%d"),
                "score": 20.0,
                "alertThreshold": 80.0,
                "causalEligibility": True,
                "rawAlert": False,
                "label": float(position == 0),
            }
            for position, date in enumerate(index[5:])
        ]

        events = FormulaStudyRunner(
            protocol,
            bootstrap_repetitions=1,
            placebo_repetitions=1,
        )._build_events(
            [(hypothesis, "tslaOof", window, {"predictions": predictions})]
        )

        prodrome_dates = events["phases"][0]["episodes"][0]["prodrome_dates"]
        self.assertEqual(
            prodrome_dates,
            [date.strftime("%Y-%m-%d") for date in index[:5]],
        )
        phase_market = events["phases"][0]["episodes"][0]["market"]
        self.assertEqual(
            phase_market["start"],
            {
                "date": "2026-06-29",
                "close": 105.0,
                "atr14": 2.0,
                "volume": 1_000.0,
            },
        )
        self.assertEqual(phase_market["end"]["date"], "2026-06-30")
        self.assertEqual(phase_market["end"]["close"], 106.0)

    def test_event_signal_dates_use_the_same_registered_threshold_crossings_as_alert_metrics(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        hypothesis = next(
            item
            for item in protocol.hypotheses
            if item.identifier
            == "fomo.baseline.momentum5::fomoContinuation@1"
        )
        index = pd.date_range("2026-07-01", periods=3, freq="B", tz="UTC")
        market = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.0, 101.0, 102.0],
                "volume": [1_000.0, 1_000.0, 1_000.0],
            },
            index=index,
        )
        labels = pd.DataFrame(
            {
                "status": ["failure", "failure", "failure"],
                "label": [0.0, 0.0, 0.0],
                "firstPassageOffset": [np.nan, np.nan, np.nan],
            },
            index=index,
        )
        window = PreparedStudyWindow(
            identifier="threshold-crossing-fixture",
            symbol="TSLA",
            role="candidate_selection",
            market=market,
            analysis_start=0,
            analysis_end=3,
            features=pd.DataFrame(index=index),
            scores=pd.DataFrame(index=index),
            labels={(hypothesis.outcome_identifier, hypothesis.horizon): labels},
            eligibility={
                (hypothesis.outcome_identifier, hypothesis.horizon): pd.Series(
                    [True, True, True], index=index
                )
            },
        )
        predictions = [
            {
                "date": date.strftime("%Y-%m-%d"),
                "score": score,
                "alertThreshold": threshold,
                "causalEligibility": True,
                "rawAlert": True,
                "label": 0.0,
            }
            for date, score, threshold in zip(
                index,
                (82.0, 85.0, 95.0),
                (80.0, 80.0, 90.0),
                strict=True,
            )
        ]

        events = FormulaStudyRunner(
            protocol,
            bootstrap_repetitions=1,
            placebo_repetitions=1,
        )._build_events(
            [(hypothesis, "tslaOof", window, {"predictions": predictions})]
        )

        signal_dates = [
            episode["alert_date"]
            for episode in events["signals"][0]["catalog"]["episodes"]
        ]
        self.assertEqual(signal_dates, ["2026-07-01", "2026-07-03"])

    def test_runs_every_registered_trial_and_freezes_one_artifact_per_trial(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        selected_hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier
            in {
                "fomo.baseline.momentum5::fomoContinuation@5",
                "panic.baseline.drawdown3::panicContinuation@5",
            }
        )
        protocol = replace(full_protocol, hypotheses=selected_hypotheses)
        preparer = StudyWindowPreparer(protocol)
        market = make_market()
        primary = preparer.prepare(
            "tsla-primary",
            "TSLA",
            "candidate_selection",
            market,
            300,
            360,
        )
        external = preparer.prepare(
            "nvda-primary",
            "NVDA",
            "external_replication",
            market,
            420,
            360,
        )
        current = preparer.prepare(
            "mu-latest",
            "MU",
            "holdout",
            market,
            780,
            120,
        )
        hynix = replace(current, identifier="000660-latest", symbol="000660")
        sensitivity = replace(
            primary,
            identifier="tsla-sensitivity",
            role="sensitivity",
        )

        runner = FormulaStudyRunner(
            protocol,
            bootstrap_repetitions=10,
            placebo_repetitions=10,
        )
        lifecycle: list[tuple[str, str]] = []
        original_evaluate_oof = runner.engine.evaluate_oof
        original_fit_final = runner.engine.fit_final

        def observed_evaluate_oof(
            window: PreparedStudyWindow,
            hypothesis: HypothesisDefinition,
        ) -> dict[str, object]:
            lifecycle.append(("oof", hypothesis.identifier))
            return original_evaluate_oof(window, hypothesis)

        def observed_fit_final(
            window: PreparedStudyWindow,
            hypothesis: HypothesisDefinition,
        ) -> FrozenCalibrationArtifact:
            lifecycle.append(("fit", hypothesis.identifier))
            return original_fit_final(window, hypothesis)

        runner.engine.evaluate_oof = observed_evaluate_oof
        runner.engine.fit_final = observed_fit_final
        result = runner.run_prepared(
            {
                "tslaPrimary": primary,
                "tslaSensitivity": sensitivity,
                "nvdaPrimary": external,
                "muLatest120": current,
                "hynixLatest120": hynix,
            }
        )

        self.assertEqual(len(result["trialResults"]), 2)
        self.assertEqual(len(result["frozenCalibrators"]), 2)
        self.assertEqual(len(result["events"]["groundTruth"]), 10)
        self.assertEqual(len(result["events"]["signals"]), 10)
        self.assertIn("marketClusters", result["events"])
        self.assertEqual(
            result["events"]["globalMetrics"]["status"],
            "not_identifiable",
        )
        self.assertFalse(result["events"]["globalMetrics"]["claimsAllowed"])
        self.assertEqual(
            result["events"]["marketClusterWeightApplication"],
            "event_catalog_only_no_global_probability_metric",
        )
        self.assertEqual(
            result["adoptionDecision"]["status"],
            "adoption_not_identifiable",
        )
        self.assertEqual(result["adoptionDecision"]["adoptableFormulaCount"], 0)
        self.assertEqual(
            result["adoptionDecision"]["reason"],
            "external_adoption_rule_not_preregistered",
        )
        interval_availability = result["metrics"][0]["intervalAvailability"]
        self.assertEqual(interval_availability["brierDifference"]["status"], "available")
        self.assertEqual(interval_availability["prAuc"]["status"], "not_identifiable")
        self.assertEqual(interval_availability["mcc"]["status"], "not_identifiable")
        self.assertEqual(interval_availability["leadTime"]["status"], "not_identifiable")
        self.assertEqual(
            {trial["trialId"] for trial in result["trialResults"]},
            {hypothesis.identifier for hypothesis in selected_hypotheses},
        )
        self.assertEqual(
            [phase for phase, _ in lifecycle],
            ["oof", "oof", "fit", "fit"],
        )
        for trial in result["trialResults"]:
            artifact_hashes = {
                stage["artifactSha256"]
                for stage in trial["stages"].values()
                if "artifactSha256" in stage
            }
            self.assertEqual(len(artifact_hashes), 1)


class RegisteredFormulaSelectorTest(unittest.TestCase):
    def test_unavailable_pairwise_ci_cannot_expand_the_uncertainty_set(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        identifiers = {
            "fomo.baseline.momentum5::fomoContinuation@5",
            "fomo.deduplicated::fomoContinuation@5",
        }
        hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier in identifiers
        )
        protocol = replace(full_protocol, hypotheses=hypotheses)
        labels = [0.0, 1.0] * 3

        def result_for(
            hypothesis_id: str,
            probabilities: list[float | None],
            brier: float,
        ) -> dict[str, object]:
            return {
                "trialId": hypothesis_id,
                "status": "evaluated",
                "metrics": {"brierScore": brier},
                "pairedBrierBootstrap": {
                    "status": "available",
                    "conservativeLower": 0.05,
                },
                "alerts": {"observedEpisodes": 30},
                "predictions": [
                    {
                        "date": f"session-{position:03d}",
                        "fold": position // 2 + 1,
                        "label": labels[position],
                        "probability": probabilities[position],
                    }
                    for position in range(6)
                ],
            }

        by_id = {
            "fomo.baseline.momentum5::fomoContinuation@5": result_for(
                "fomo.baseline.momentum5::fomoContinuation@5",
                [None, None, 0.2, 0.8, 0.2, 0.8],
                0.04,
            ),
            "fomo.deduplicated::fomoContinuation@5": result_for(
                "fomo.deduplicated::fomoContinuation@5",
                [0.1, 0.9, 0.1, 0.9, 0.1, 0.9],
                0.01,
            ),
        }

        decision = RegisteredFormulaSelector(
            protocol,
            TrialResearchEngine(
                protocol,
                bootstrap_repetitions=10,
                placebo_repetitions=10,
            ),
        ).select(by_id)["groups"][0]

        self.assertEqual(decision["uncertaintySetCandidateIds"], ["fomo.deduplicated"])
        self.assertIn("uncertainty_set_inference_available", decision["failedGates"])
        self.assertIsNone(decision["selectedCandidateId"])

    def test_empty_candidate_common_mask_returns_no_valid_formula_without_crashing(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        identifiers = {
            "fomo.baseline.momentum5::fomoContinuation@5",
            "fomo.deduplicated::fomoContinuation@5",
        }
        hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier in identifiers
        )
        protocol = replace(full_protocol, hypotheses=hypotheses)

        def result_for(
            hypothesis_id: str,
            probabilities: list[float | None],
        ) -> dict[str, object]:
            return {
                "trialId": hypothesis_id,
                "status": "evaluated",
                "metrics": {"brierScore": 0.1},
                "pairedBrierBootstrap": {
                    "status": "available",
                    "conservativeLower": 0.05,
                },
                "alerts": {"observedEpisodes": 30},
                "predictions": [
                    {
                        "date": f"session-{position:03d}",
                        "fold": position // 2 + 1,
                        "label": float(position % 2),
                        "probability": probabilities[position],
                    }
                    for position in range(6)
                ],
            }

        by_id = {
            "fomo.baseline.momentum5::fomoContinuation@5": result_for(
                "fomo.baseline.momentum5::fomoContinuation@5",
                [0.2, 0.8, None, None, None, None],
            ),
            "fomo.deduplicated::fomoContinuation@5": result_for(
                "fomo.deduplicated::fomoContinuation@5",
                [None, None, 0.2, 0.8, 0.2, 0.8],
            ),
        }

        decision = RegisteredFormulaSelector(
            protocol,
            TrialResearchEngine(
                protocol,
                bootstrap_repetitions=10,
                placebo_repetitions=10,
            ),
        ).select(by_id)["groups"][0]

        self.assertEqual(decision["finalStatus"], "no_valid_formula")
        self.assertEqual(decision["reason"], "common_candidate_mask_unavailable")
        self.assertIsNone(decision["selectedCandidateId"])

    def test_uncertainty_set_prefers_the_simpler_candidate_when_the_ci_contains_zero(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        identifiers = {
            "fomo.baseline.momentum5::fomoContinuation@5",
            "fomo.deduplicated::fomoContinuation@5",
        }
        hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier in identifiers
        )
        protocol = replace(full_protocol, hypotheses=hypotheses)
        labels = np.asarray([0.0, 1.0] * 30)

        def calibrated_probability(label: float, positive: float) -> float:
            return positive if label == 1.0 else 1.0 - positive

        baseline_probabilities = np.asarray(
            [
                calibrated_probability(label, 0.64 if position % 2 == 0 else 0.56)
                for position, label in enumerate(labels)
            ]
        )
        complex_probabilities = np.asarray(
            [
                calibrated_probability(label, 0.60 if position % 2 == 0 else 0.605)
                for position, label in enumerate(labels)
            ]
        )

        def result_for(
            hypothesis_id: str,
            probabilities: np.ndarray,
        ) -> dict[str, object]:
            return {
                "trialId": hypothesis_id,
                "status": "evaluated",
                "metrics": {
                    "brierScore": float(np.mean((probabilities - labels) ** 2))
                },
                "pairedBrierBootstrap": {
                    "status": "available",
                    "conservativeLower": 0.05,
                },
                "alerts": {"observedEpisodes": 30},
                "predictions": [
                    {
                        "date": f"session-{position:03d}",
                        "fold": position // 20 + 1,
                        "label": float(labels[position]),
                        "probability": float(probabilities[position]),
                    }
                    for position in range(len(labels))
                ],
            }

        by_id = {
            "fomo.baseline.momentum5::fomoContinuation@5": result_for(
                "fomo.baseline.momentum5::fomoContinuation@5",
                baseline_probabilities,
            ),
            "fomo.deduplicated::fomoContinuation@5": result_for(
                "fomo.deduplicated::fomoContinuation@5",
                complex_probabilities,
            ),
        }
        engine = TrialResearchEngine(
            protocol,
            bootstrap_repetitions=200,
            placebo_repetitions=20,
        )
        decision = RegisteredFormulaSelector(protocol, engine).select(by_id)[
            "groups"
        ][0]

        self.assertEqual(decision["pointWinnerCandidateId"], "fomo.deduplicated")
        self.assertEqual(
            decision["uncertaintySetCandidateIds"],
            ["fomo.baseline.momentum5", "fomo.deduplicated"],
        )
        self.assertEqual(
            decision["registeredWinnerCandidateId"],
            "fomo.baseline.momentum5",
        )
        self.assertEqual(
            decision["selectedCandidateId"],
            "fomo.baseline.momentum5",
        )

    def test_complex_formula_uses_the_strongest_baseline_on_one_paired_common_mask(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        identifiers = {
            "fomo.baseline.momentum5::fomoContinuation@5",
            "fomo.baseline.volume20::fomoContinuation@5",
            "fomo.deduplicated::fomoContinuation@5",
        }
        hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier in identifiers
        )
        protocol = replace(full_protocol, hypotheses=hypotheses)
        labels = np.asarray([0.0, 1.0] * 30)
        hard_positions = set(range(0, 4)) | set(range(20, 24)) | set(range(40, 44))

        def probability(label: float, positive: float) -> float:
            return positive if label == 1.0 else 1.0 - positive

        def result_for(
            hypothesis_id: str,
            probabilities: list[float | None],
        ) -> dict[str, object]:
            paired = [
                (label, predicted)
                for label, predicted in zip(labels, probabilities, strict=True)
                if predicted is not None
            ]
            brier = float(
                np.mean(
                    [
                        (float(predicted) - float(label)) ** 2
                        for label, predicted in paired
                    ]
                )
            )
            return {
                "trialId": hypothesis_id,
                "status": "evaluated",
                "metrics": {"brierScore": brier},
                "pairedBrierBootstrap": {
                    "status": "available",
                    "conservativeLower": 0.05,
                },
                "alerts": {"observedEpisodes": 30},
                "predictions": [
                    {
                        "date": f"session-{position:03d}",
                        "fold": position // 20 + 1,
                        "label": float(labels[position]),
                        "probability": probabilities[position],
                    }
                    for position in range(len(labels))
                ],
            }

        candidate = [probability(label, 0.95) for label in labels]
        marginally_best_baseline = [
            0.5 if position in hard_positions else probability(label, 0.99)
            for position, label in enumerate(labels)
        ]
        paired_strongest_baseline = [
            probability(label, 0.6) if position in hard_positions else None
            for position, label in enumerate(labels)
        ]
        by_id = {
            "fomo.baseline.momentum5::fomoContinuation@5": result_for(
                "fomo.baseline.momentum5::fomoContinuation@5",
                marginally_best_baseline,
            ),
            "fomo.baseline.volume20::fomoContinuation@5": result_for(
                "fomo.baseline.volume20::fomoContinuation@5",
                paired_strongest_baseline,
            ),
            "fomo.deduplicated::fomoContinuation@5": result_for(
                "fomo.deduplicated::fomoContinuation@5",
                candidate,
            ),
        }

        decision = RegisteredFormulaSelector(
            protocol,
            TrialResearchEngine(
                protocol,
                bootstrap_repetitions=20,
                placebo_repetitions=20,
            ),
        ).select(by_id)["groups"][0]

        self.assertEqual(
            decision["marginalBestFormulaBaselineCandidateId"],
            "fomo.baseline.momentum5",
        )
        self.assertEqual(
            decision["bestFormulaBaselineCandidateId"],
            "fomo.baseline.volume20",
        )
        self.assertEqual(
            decision["complexVersusBaseline"]["commonObservationCount"],
            12,
        )

    def test_complex_formula_requires_common_date_baseline_and_base_rate_wins(self) -> None:
        full_protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        identifiers = {
            "fomo.baseline.momentum5::fomoContinuation@5",
            "fomo.baseline.volume20::fomoContinuation@5",
            "fomo.deduplicated::fomoContinuation@5",
        }
        hypotheses = tuple(
            hypothesis
            for hypothesis in full_protocol.hypotheses
            if hypothesis.identifier in identifiers
        )
        protocol = replace(full_protocol, hypotheses=hypotheses)
        labels = np.asarray([0.0, 1.0] * 30)

        def trial_result(hypothesis_id: str, probabilities: np.ndarray) -> dict[str, object]:
            predictions = [
                {
                    "date": f"2026-01-{position + 1:02d}",
                    "fold": position // 20 + 1,
                    "label": float(labels[position]),
                    "probability": float(probabilities[position]),
                }
                for position in range(len(labels))
            ]
            brier = float(np.mean((probabilities - labels) ** 2))
            return {
                "trialId": hypothesis_id,
                "status": "evaluated",
                "metrics": {"brierScore": brier},
                "pairedBrierBootstrap": {"conservativeLower": 0.05},
                "alerts": {"observedEpisodes": 30},
                "predictions": predictions,
            }

        by_id = {
            "fomo.baseline.momentum5::fomoContinuation@5": trial_result(
                "fomo.baseline.momentum5::fomoContinuation@5",
                np.full(len(labels), 0.5),
            ),
            "fomo.baseline.volume20::fomoContinuation@5": trial_result(
                "fomo.baseline.volume20::fomoContinuation@5",
                np.where(labels == 1.0, 0.7, 0.3),
            ),
            "fomo.deduplicated::fomoContinuation@5": trial_result(
                "fomo.deduplicated::fomoContinuation@5",
                np.where(labels == 1.0, 0.95, 0.05),
            ),
        }

        selection = RegisteredFormulaSelector(
            protocol,
            TrialResearchEngine(
                protocol,
                bootstrap_repetitions=20,
                placebo_repetitions=20,
            ),
        ).select(by_id)

        self.assertEqual(len(selection["groups"]), 1)
        decision = selection["groups"][0]
        self.assertEqual(
            decision["selectedCandidateId"],
            "fomo.deduplicated",
        )
        self.assertEqual(
            decision["finalStatus"],
            "selected_for_external_evaluation",
        )
        self.assertGreater(
            decision["complexVersusBaseline"]["conservativeLower"],
            0.0,
        )
        self.assertFalse(decision["commonMask"]["winnerChanged"])


class MultipleTestingControllerTest(unittest.TestCase):
    def test_holm_retains_all_fixed_hypotheses_when_three_are_unavailable(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        available_id = protocol.primary_holm_hypotheses[0]
        results = {
            available_id: {
                "status": "evaluated",
                "pairedBrierBootstrap": {"oneSidedPValue": 0.01},
            }
        }

        adjusted = MultipleTestingController(protocol).apply(results)

        self.assertEqual(len(adjusted["holmPrimary"]), 4)
        by_id = {
            result["trialId"]: result for result in adjusted["holmPrimary"]
        }
        self.assertAlmostEqual(by_id[available_id]["adjustedPValue"], 0.04)
        for trial_id in protocol.primary_holm_hypotheses[1:]:
            self.assertEqual(by_id[trial_id]["status"], "insufficient")
            self.assertEqual(by_id[trial_id]["rawPValue"], 1.0)
            self.assertFalse(by_id[trial_id]["significant"])


class FourMonthSubsetTest(unittest.TestCase):
    def test_reports_the_subset_without_creating_a_second_inference_stage(self) -> None:
        records = [
            {
                "date": "2026-03-09",
                "label": 0.0,
                "probability": 0.2,
                "rawAlert": False,
            },
            {
                "date": "2026-03-10",
                "label": 1.0,
                "probability": 0.8,
                "rawAlert": True,
            },
            {
                "date": "2026-07-09",
                "label": 0.0,
                "probability": 0.1,
                "rawAlert": False,
            },
        ]

        summary = descriptive_four_month_subset(
            records,
            start_date="2026-03-10",
            end_date="2026-07-09",
        )

        self.assertEqual(summary["sessions"], 2)
        self.assertEqual(summary["observedPairs"], 2)
        self.assertFalse(summary["duplicateAggregationAllowed"])
        self.assertAlmostEqual(summary["metrics"]["brierScore"], 0.025)


if __name__ == "__main__":
    unittest.main()
