import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from research_pipeline import ResearchProtocol, TossCandleArchive  # noqa: E402
from study_runner import (  # noqa: E402
    MultipleTestingController,
    RegisteredFormulaSelector,
    TrialResearchEngine,
)
from run_validation import (  # noqa: E402
    SECRET_PATTERN,
    _read_volume_unit_amendment,
    _validate_runtime_dependencies,
    _validate_trial_ledger,
    _preflight_verification_document,
    _data_quality_document,
    _validate_archives_against_manifest,
    build_output_documents,
    build_source_windows,
    candidate_unavailability_for_window,
    parse_arguments,
    resolve_study_inputs,
    volume_dependent_candidate_ids,
)


def market(start: str, count: int = 1_100) -> pd.DataFrame:
    index = pd.date_range(start, periods=count, freq="B", tz="UTC")
    close = 100.0 + np.arange(count) * 0.1
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(count, 1_000_000.0),
        },
        index=index,
    )


def preflight_data_quality() -> dict[str, object]:
    def session_dates(start: str, end: str, sessions: int) -> list[str]:
        dates = pd.date_range(start, periods=sessions - 1, freq="D").strftime(
            "%Y-%m-%d"
        ).tolist()
        return [*dates, end]

    return {
        "credentialPatternFiles": [],
        "windows": [
            {
                "id": "tslaPrimary",
                "symbol": "TSLA",
                "sessions": 360,
                "sessionDates": session_dates("2020-07-23", "2021-12-23", 360),
                "startDate": "2020-07-23",
                "endDate": "2021-12-23",
            },
            {
                "id": "tslaSensitivity",
                "symbol": "TSLA",
                "sessions": 360,
                "sessionDates": session_dates("2020-08-12", "2022-01-13", 360),
                "startDate": "2020-08-12",
                "endDate": "2022-01-13",
            },
            {
                "id": "nvdaPrimary",
                "symbol": "NVDA",
                "sessions": 360,
                "sessionDates": session_dates("2023-05-25", "2024-10-29", 360),
                "startDate": "2023-05-25",
                "endDate": "2024-10-29",
            },
            {
                "id": "muLatest120",
                "symbol": "MU",
                "sessions": 120,
                "sessionDates": session_dates("2026-01-15", "2026-07-09", 120),
                "startDate": "2026-01-15",
                "endDate": "2026-07-09",
            },
            {
                "id": "hynixLatest120",
                "symbol": "000660",
                "sessions": 120,
                "sessionDates": session_dates("2026-01-13", "2026-07-09", 120),
                "startDate": "2026-01-13",
                "endDate": "2026-07-09",
            },
        ],
    }


def complete_preflight_result(protocol: ResearchProtocol) -> dict[str, object]:
    stage_names = (
        "tslaOof",
        "tslaSensitivity",
        "nvdaExternal",
        "muHoldout",
        "hynixHoldout",
    )
    trial_results = [
        {
            "trialId": hypothesis.identifier,
            "familyId": hypothesis.family,
            "candidateId": hypothesis.candidate_identifier,
            "candidateKind": hypothesis.candidate_kind,
            "outcomeId": hypothesis.outcome_identifier,
            "horizon": hypothesis.horizon,
            "stages": {
                "tslaOof": {
                    "status": "probability_unavailable",
                    "symbol": "TSLA",
                },
                "tslaSensitivity": {
                    "status": "calibration_unavailable",
                    "symbol": "TSLA",
                },
                "nvdaExternal": {
                    "status": "calibration_unavailable",
                    "symbol": "NVDA",
                },
                "muHoldout": {
                    "status": "calibration_unavailable",
                    "symbol": "MU",
                },
                "hynixHoldout": {
                    "status": "calibration_unavailable",
                    "symbol": "000660",
                },
            },
        }
        for hypothesis in protocol.hypotheses
    ]
    tsla_dates = preflight_data_quality()["windows"][0]["sessionDates"]
    metrics = [
        {
            "trialId": hypothesis.identifier,
            "stage": stage,
            "symbol": trial_results[index]["stages"][stage]["symbol"],
            "status": trial_results[index]["stages"][stage]["status"],
            "metrics": None,
            "baselineMetrics": None,
            "pairedBrierBootstrap": None,
            "placebo": None,
            "alerts": None,
            "calibration": None,
            "fourMonthSubset": None,
            "unavailabilityReason": None,
        }
        for index, hypothesis in enumerate(protocol.hypotheses)
        for stage in stage_names
    ]
    result = {
        "trialResults": trial_results,
        "frozenCalibrators": [
            {
                "trialId": hypothesis.identifier,
                "status": "calibration_unavailable",
                "reason": "fixture",
            }
            for hypothesis in protocol.hypotheses
        ],
        "predictions": [
            {
                "trialId": hypothesis.identifier,
                "stage": "tslaOof",
                "symbol": "TSLA",
                "date": date,
                "sessionOrdinal": ordinal,
            }
            for hypothesis in protocol.hypotheses
            for ordinal, date in enumerate(tsla_dates)
        ],
        "metrics": metrics,
    }
    result["multipleTesting"] = MultipleTestingController(protocol).apply(
        {
            metric["trialId"]: metric
            for metric in metrics
            if metric["stage"] == "tslaOof"
        }
    )
    predictions_by_trial: dict[str, list[dict[str, object]]] = {}
    for prediction in result["predictions"]:
        predictions_by_trial.setdefault(prediction["trialId"], []).append(prediction)
    result["selection"] = RegisteredFormulaSelector(
        protocol,
        TrialResearchEngine(protocol),
    ).select(
        {
            trial["trialId"]: {
                **trial["stages"]["tslaOof"],
                "predictions": predictions_by_trial[trial["trialId"]],
            }
            for trial in trial_results
        }
    )
    result["adoptionDecision"] = {
        "status": "adoption_not_identifiable",
        "adoptableFormulaCount": 0,
        "reason": "external_adoption_rule_not_preregistered",
        "tslaExploratoryCandidateCount": result["selection"][
            "selectedForExternalCount"
        ],
        "externalStagesDescriptiveOnly": True,
        "multipleTestingPromotionAllowed": False,
    }
    return result


class RunValidationArgumentsTest(unittest.TestCase):
    def test_runtime_lock_and_trial_ledger_match_the_executable_protocol(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )

        _validate_runtime_dependencies()
        _validate_trial_ledger(protocol)

    def test_detects_the_provider_specific_live_credential_prefixes(self) -> None:
        self.assertIsNotNone(SECRET_PATTERN.search(b"tsck_live_fixture"))
        self.assertIsNotNone(SECRET_PATTERN.search(b"tssk_live_fixture"))

    def test_requires_exactly_one_run_or_verify_mode(self) -> None:
        self.assertEqual(parse_arguments(["--run"]).mode, "run")
        self.assertEqual(parse_arguments(["--verify"]).mode, "verify")
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_arguments([])
            with self.assertRaises(SystemExit):
                parse_arguments(["--run", "--verify"])


class SourceWindowContractTest(unittest.TestCase):
    def test_volume_unit_amendment_is_the_single_source_of_truth(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        amendment = _read_volume_unit_amendment()

        self.assertEqual(
            sorted(amendment["affectedCandidateIds"]),
            sorted(volume_dependent_candidate_ids(protocol)),
        )
        self.assertEqual(
            {
                (entry["symbol"], entry["effectiveTradingDate"])
                for entry in amendment["observedUnitBreaks"]
            },
            {
                ("TSLA", "2020-08-31"),
                ("TSLA", "2022-08-25"),
                ("NVDA", "2021-07-20"),
                ("NVDA", "2024-06-10"),
            },
        )

    def test_identifies_every_candidate_that_depends_on_unadjusted_volume_units(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )

        identifiers = volume_dependent_candidate_ids(protocol)

        self.assertEqual(
            identifiers,
            {
                "fomo.documented",
                "fomo.equal",
                "fomo.deduplicated",
                "fomo.baseline.volume20",
                "panic.documented",
                "panic.equal",
                "panic.deduplicated",
                "panic.baseline.volume20",
                "potentialPtp.documented",
                "potentialPtp.equal",
                "potentialPtp.breadth",
                "potentialPtp.baseline.vwapExtension",
            },
        )

    def test_loaded_archives_must_match_manifest_metadata_and_cutoff(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        archives = {
            symbol: TossCandleArchive(
                symbol,
                "KRW" if symbol == "000660" else "USD",
                market("2026-07-01", count=10),
            )
            for symbol in ("TSLA", "NVDA", "MU", "000660")
        }
        manifest = {
            "archives": [
                {
                    "symbol": symbol,
                    "currency": archive.currency,
                    "rows": len(archive.market),
                    "start": archive.market.index[0].strftime("%Y-%m-%d"),
                    "end": archive.market.index[-1].strftime("%Y-%m-%d"),
                }
                for symbol, archive in archives.items()
            ]
        }
        manifest["archives"][0]["rows"] = 9

        with self.assertRaisesRegex(ValueError, "row count"):
            _validate_archives_against_manifest(manifest, archives, protocol)

        manifest["archives"][0]["rows"] = 10
        with self.assertRaisesRegex(ValueError, "cutoff"):
            _validate_archives_against_manifest(manifest, archives, protocol)

    def test_builds_frozen_anchors_and_single_current_holdouts(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        archives = {
            "TSLA": TossCandleArchive("TSLA", "USD", market("2019-01-02")),
            "NVDA": TossCandleArchive("NVDA", "USD", market("2022-01-03")),
            "MU": TossCandleArchive("MU", "USD", market("2022-01-03")),
            "000660": TossCandleArchive("000660", "KRW", market("2022-01-03")),
        }

        windows = build_source_windows(protocol, archives)

        self.assertEqual(
            windows["tslaPrimary"].analysis_market.index[0].strftime("%Y-%m-%d"),
            "2020-07-23",
        )
        self.assertEqual(
            windows["tslaSensitivity"].analysis_market.index[0].strftime("%Y-%m-%d"),
            "2020-08-12",
        )
        self.assertEqual(
            windows["nvdaPrimary"].analysis_market.index[0].strftime("%Y-%m-%d"),
            "2023-05-25",
        )
        self.assertEqual(len(windows["muLatest120"].analysis_market), 120)
        self.assertEqual(len(windows["hynixLatest120"].analysis_market), 120)
        self.assertEqual(
            len(candidate_unavailability_for_window(protocol, windows["tslaPrimary"])),
            12,
        )
        self.assertEqual(
            len(candidate_unavailability_for_window(protocol, windows["nvdaPrimary"])),
            12,
        )
        self.assertEqual(
            candidate_unavailability_for_window(protocol, windows["muLatest120"]),
            {},
        )
        quality = _data_quality_document(
            RESEARCH_DIRECTORY / "data",
            {"fetchedAt": "2026-07-09T00:00:00Z"},
            archives,
            windows,
            protocol,
        )
        self.assertEqual(
            quality["volumeUnitIntegrity"]["status"],
            "unadjusted_split_units_detected",
        )
        self.assertEqual(
            quality["volumeUnitIntegrity"]["candidateDisposition"],
            "data_unavailable_not_zero",
        )
        self.assertEqual(
            len(quality["volumeUnitIntegrity"]["unavailableCandidateIds"]),
            12,
        )
        self.assertEqual(len(quality["windows"][0]["sessionDates"]), 360)
        self.assertEqual(
            quality["windows"][0]["sessionDates"][0],
            quality["windows"][0]["startDate"],
        )


class OutputProvenanceTest(unittest.TestCase):
    def test_preflight_never_promotes_tsla_selection_without_a_registered_external_rule(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )
        result = complete_preflight_result(protocol)

        verification = _preflight_verification_document(
            result,
            preflight_data_quality(),
            protocol,
        )

        self.assertEqual(verification["conclusion"], "adoption_not_identifiable")
        self.assertEqual(verification["tslaExploratoryCandidateCount"], 0)
        self.assertEqual(verification["adoptableFormulaCount"], 0)
        self.assertEqual(
            verification["runtimeEnvironment"]["numpyVersion"],
            np.__version__,
        )
        self.assertEqual(
            verification["runtimeEnvironment"]["pandasVersion"],
            pd.__version__,
        )
        self.assertEqual(
            verification["postWriteVerificationCommand"],
            "python3 research/indicator-validation/run_validation.py --verify",
        )
        feasibility = {
            item["horizon"]: item
            for item in verification["latest120MinimumEventFeasibility"]
        }
        self.assertEqual(feasibility[5]["maximumObservableEpisodes"], 20)
        self.assertEqual(feasibility[10]["maximumObservableEpisodes"], 10)
        self.assertFalse(feasibility[5]["minimumEventGateReachable"])
        self.assertFalse(feasibility[10]["minimumEventGateReachable"])

        duplicated = dict(result)
        duplicated["trialResults"] = list(result["trialResults"])
        duplicated["trialResults"][-1] = result["trialResults"][0]
        with self.assertRaisesRegex(ValueError, "trial identifiers"):
            _preflight_verification_document(
                duplicated,
                preflight_data_quality(),
                protocol,
            )

        missing_predictions = dict(result)
        missing_predictions["predictions"] = []
        with self.assertRaisesRegex(ValueError, "prediction coverage"):
            _preflight_verification_document(
                missing_predictions,
                preflight_data_quality(),
                protocol,
            )

        forged_oof_unavailability = dict(result)
        forged_oof_unavailability["predictions"] = []
        forged_oof_unavailability["trialResults"] = [
            {
                **trial,
                "stages": {
                    **trial["stages"],
                    "tslaOof": {
                        "status": "calibration_unavailable",
                        "symbol": "TSLA",
                    },
                },
            }
            for trial in result["trialResults"]
        ]
        forged_oof_unavailability["metrics"] = [
            {
                **metric,
                "status": (
                    "calibration_unavailable"
                    if metric["stage"] == "tslaOof"
                    else metric["status"]
                ),
            }
            for metric in result["metrics"]
        ]
        forged_oof_unavailability["multipleTesting"] = (
            MultipleTestingController(protocol).apply(
                {
                    metric["trialId"]: metric
                    for metric in forged_oof_unavailability["metrics"]
                    if metric["stage"] == "tslaOof"
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "impossible status"):
            _preflight_verification_document(
                forged_oof_unavailability,
                preflight_data_quality(),
                protocol,
            )

        forged_adoption = dict(result)
        forged_adoption["adoptionDecision"] = {
            "status": "adopted",
            "adoptableFormulaCount": len(protocol.hypotheses),
            "reason": "unregistered_rule",
        }
        with self.assertRaisesRegex(ValueError, "adoption decision"):
            _preflight_verification_document(
                forged_adoption,
                preflight_data_quality(),
                protocol,
            )

        forged_selection = dict(result)
        forged_selection["selection"] = {
            "groupCount": result["selection"]["groupCount"],
            "selectedForExternalCount": result["selection"][
                "selectedForExternalCount"
            ],
            "conditionallyValidCount": 0,
            "selectionScope": "tsla_oof_exploratory_only",
            "adoptionAllowed": False,
        }
        with self.assertRaisesRegex(ValueError, "selection differs"):
            _preflight_verification_document(
                forged_selection,
                preflight_data_quality(),
                protocol,
            )

    def test_every_primary_output_directly_carries_input_and_analysis_provenance(self) -> None:
        result = {
            "protocolVersion": "1.4.0",
            "hypothesisCount": 0,
            "trialResults": [],
            "predictions": [],
            "metrics": [],
            "multipleTesting": {},
            "events": {},
            "selection": {},
            "adoptionDecision": {
                "status": "adoption_not_identifiable",
                "adoptableFormulaCount": 0,
            },
            "frozenCalibrators": [],
        }
        data_quality = {"dataManifestSha256": "a" * 64}
        verification = {"conclusion": "fixture"}

        documents = build_output_documents(result, data_quality, verification)

        self.assertEqual(len(documents), 8)
        for _, _, document in documents:
            self.assertEqual(
                document["provenance"]["dataManifestSha256"],
                "a" * 64,
            )
            self.assertEqual(document["provenance"]["protocolVersion"], "1.4.0")
            self.assertIn("analysisVersion", document["provenance"])
        selection_document = next(
            document
            for identifier, _, document in documents
            if identifier == "selection"
        )
        self.assertEqual(
            selection_document["adoptionDecision"]["status"],
            "adoption_not_identifiable",
        )

    def test_run_inputs_include_the_exact_analysis_sources(self) -> None:
        inputs = resolve_study_inputs(RESEARCH_DIRECTORY / "data")
        identifiers = {artifact.identifier for artifact in inputs}
        data_manifest = next(
            artifact for artifact in inputs if artifact.identifier == "data-manifest"
        )

        self.assertIn("code:study-runner", identifiers)
        self.assertIn("code:validation", identifiers)
        self.assertIn("code:formula-ledger", identifiers)
        self.assertIn("code:formula-reference", identifiers)
        self.assertIn("artifact:formula-ledger", identifiers)
        self.assertIn("amendment:volume-unit-integrity", identifiers)
        self.assertIn("production:quant-indicators", identifiers)
        self.assertIn("dependency:python-lock", identifiers)
        self.assertIn("formula:panic", identifiers)
        self.assertIn("formula:fomo", identifiers)
        self.assertEqual(
            data_manifest.expected_sha256,
            "ed5126ed94c6316e5bc0389f33443f3e3a38576a55164eda758016ff5d37dae9",
        )


if __name__ == "__main__":
    unittest.main()
