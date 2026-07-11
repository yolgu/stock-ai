from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import math
import shutil
import stat
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from rp001.local_evidence import (
    LocalArtifactStore,
    LocalEvidenceError,
    canonical_json_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPOSITORY_ROOT / "research/rp-001/run_interim_evaluation.py"
SAMPLE_SHA256 = "aaf7a9442e2f7c17cd7321200b80ab5405ca35e49eafe79a35d953edf42b3ecb"
MERC_SHA256 = "efa61aa526a4887128c7d78916c23645bda43091b726973f99be9793f65a1ae3"
SELECTED_SYMBOLS = ("AMZN", "CAT", "XOM", "AAPL", "AMD", "COST")


def load_module(path: Path, module_name: str) -> object:
    specification = importlib.util.spec_from_file_location(module_name, path)
    if specification is None or specification.loader is None:
        raise AssertionError("test module could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


RUNNER = (
    load_module(RUNNER_PATH, "rp001_run_interim_evaluation_test_target")
    if RUNNER_PATH.exists()
    else None
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_clock() -> datetime:
    return datetime(2026, 7, 11, 3, 4, 5, tzinfo=timezone.utc)


def nested_paths(value: object) -> Iterator[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in {"path", "sourcePath", "testPath"} and isinstance(
                nested, str
            ):
                yield nested
            yield from nested_paths(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from nested_paths(nested)


def lossless_decimal(value: float) -> dict[str, str]:
    return {"kind": "json_string", "text": format(value, ".12f")}


def lossless_integer(value: float) -> dict[str, str]:
    return {"kind": "json_string", "text": str(round(value))}


def session_dates(count: int) -> tuple[str, ...]:
    first = date(2023, 1, 3)
    last = date(2026, 6, 30)
    span = (last - first).days
    return tuple(
        (first + timedelta(days=round(index * span / (count - 1)))).isoformat()
        for index in range(count)
    )


def analysis_row(
    session_date: str,
    adjusted_close: float,
    native_close: float,
    native_volume: float,
) -> dict[str, object]:
    def candle(close: float, volume: float) -> dict[str, object]:
        return {
            "openPrice": lossless_decimal(close),
            "highPrice": lossless_decimal(close),
            "lowPrice": lossless_decimal(close),
            "closePrice": lossless_decimal(close),
            "volume": lossless_integer(volume),
        }

    return {
        "sessionDate": session_date,
        "timestamp": f"{session_date}T21:00:00Z",
        "currency": "USD",
        "adjusted": candle(adjusted_close, native_volume),
        "native": candle(native_close, native_volume),
    }


class InterimEvaluationRunnerScaffoldTest(unittest.TestCase):
    def test_interim_evaluation_runner_module_exists(self) -> None:
        self.assertTrue(RUNNER_PATH.is_file())


@unittest.skipIf(RUNNER is None, "interim evaluation runner is not implemented")
class InterimEvaluationRunnerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name).resolve()
        self._copy_frozen_tree(
            "research/rp-001/contracts/selected-sample-freeze-v1.json"
        )
        self._copy_frozen_tree(
            "research/rp-001/contracts/st-beh-interim-merc-v1.json"
        )
        self.candle_run_directory = (
            self.repository_root
            / "research/rp-001/candle-runs/RP001-CANDLE-FIXTURE-001"
        )
        raw = LocalArtifactStore(self.repository_root.resolve()).publish_json(
            self.candle_run_directory / "raw-candles.json",
            {
                "schemaVersion": "rp001-toss-raw-candles.v1",
                "programId": "RP-001",
                "runId": "RP001-CANDLE-FIXTURE-001",
                "captureCount": 12,
                "captures": [],
            },
        )
        processed = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(
            self.candle_run_directory / "processed-candles.json",
            self._processed_candles(raw.artifact_sha256),
        )
        self.processed_sha256 = processed.artifact_sha256
        self.output_directory = Path("research/rp-001/evaluation-runs")
        self.ledger_directory = Path(
            "research/rp-001/local-ledgers/evaluation-program"
        )
        self.arguments = RUNNER.InterimEvaluationRunArguments(
            repository_root=self.repository_root,
            processed_candles_path=Path(
                "research/rp-001/candle-runs/"
                "RP001-CANDLE-FIXTURE-001/processed-candles.json"
            ),
            processed_candles_sha256=self.processed_sha256,
            sample_freeze_path=Path(
                "research/rp-001/contracts/selected-sample-freeze-v1.json"
            ),
            sample_freeze_sha256=SAMPLE_SHA256,
            merc_freeze_path=Path(
                "research/rp-001/contracts/st-beh-interim-merc-v1.json"
            ),
            merc_freeze_sha256=MERC_SHA256,
            output_directory=self.output_directory,
            ledger_directory=self.ledger_directory,
            run_id="RP001-EVAL-FIXTURE-001",
        )

    def _copy_frozen_tree(self, first_relative_path: str) -> None:
        pending = [first_relative_path]
        copied: set[str] = set()
        while pending:
            relative_path = pending.pop()
            if relative_path in copied:
                continue
            source = REPOSITORY_ROOT / relative_path
            if not source.is_file():
                continue
            destination = self.repository_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.add(relative_path)
            sidecar = Path(f"{source}.sha256")
            if sidecar.is_file():
                shutil.copyfile(sidecar, Path(f"{destination}.sha256"))
            if source.suffix == ".json":
                pending.extend(nested_paths(json.loads(source.read_text())))

    def _processed_candles(self, raw_sha256: str) -> dict[str, object]:
        dates = session_dates(607)
        periodic_returns = (
            0.004,
            -0.002,
            0.003,
            -0.004,
            0.001,
            0.005,
            -0.003,
            0.002,
            -0.005,
            0.0005,
        )
        symbols: list[dict[str, object]] = []
        for symbol_index, symbol in enumerate(SELECTED_SYMBOLS):
            prices = [100.0 + symbol_index * 10.0]
            for index in range(1, len(dates)):
                prices.append(
                    prices[-1]
                    * math.exp(periodic_returns[index % len(periodic_returns)])
                )
            rows = [
                analysis_row(
                    session_date,
                    prices[index],
                    prices[index],
                    1_000_000.0
                    * math.exp(((index + symbol_index) % 7 - 3) * 0.03),
                )
                for index, session_date in enumerate(dates)
            ]
            symbols.append(
                {
                    "symbol": symbol,
                    "analysisRows": rows,
                    "auditOnlyRows": {"adjusted": [], "native": []},
                }
            )
        return {
            "schemaVersion": "rp001-toss-daily-candle-processed.v1",
            "programId": "RP-001",
            "goalVersion": "1.2-COMPACT",
            "runId": "RP001-CANDLE-FIXTURE-001",
            "sampleRole": "unseen_historical_confirmation",
            "interval": "1d",
            "timezone": "America/New_York",
            "requestedRange": {
                "startDate": "2023-01-03",
                "endDate": "2026-06-30",
                "inclusive": True,
            },
            "availability": {
                "signalTiming": "official_daily_close_usable_next_session",
                "providerSessionMembership": "not_documented",
            },
            "rawArtifact": {
                "path": (
                    "research/rp-001/candle-runs/"
                    "RP001-CANDLE-FIXTURE-001/raw-candles.json"
                ),
                "sha256": raw_sha256,
            },
            "symbols": symbols,
        }

    def _run_directory(self) -> Path:
        return (
            self.repository_root / self.output_directory / self.arguments.run_id
        )

    def _run(self) -> object:
        return RUNNER.run_interim_evaluation(
            self.arguments,
            clock=fixed_clock,
        )


class InterimEvaluationRunnerContractTest(InterimEvaluationRunnerFixture):
    def test_success_runs_frozen_four_head_evaluation_and_publishes_evidence(
        self,
    ) -> None:
        summary = self._run()

        self.assertEqual(summary.status, "succeeded")
        self.assertEqual(summary.symbol_count, 6)
        self.assertEqual(summary.session_count, 607)
        self.assertEqual(summary.evaluation_count, 16)
        run_directory = self._run_directory()
        self.assertEqual(
            {path.name for path in run_directory.iterdir()},
            {
                "result.json",
                "result.json.sha256",
                "trial.json",
                "trial.json.sha256",
                "manifest.json",
                "manifest.json.sha256",
            },
        )
        result = json.loads((run_directory / "result.json").read_text())
        trial = json.loads((run_directory / "trial.json").read_text())
        manifest = json.loads((run_directory / "manifest.json").read_text())
        self.assertEqual(result["usageScope"], "research_only")
        self.assertEqual(
            result["operationalDisposition"], "NoTrade/no integration"
        )
        self.assertEqual(result["symbols"], list(SELECTED_SYMBOLS))
        self.assertEqual(result["validation"]["developmentFoldCount"], 3)
        self.assertEqual(result["validation"]["evaluationCount"], 16)
        self.assertEqual(
            {item["headId"] for item in result["evaluations"]},
            {"SF", "SP", "ST", "SR"},
        )
        self.assertTrue(
            all(
                item["selectionContext"]
                == "selected_from_multiple_candidates"
                for item in result["evaluations"]
            )
        )
        self.assertTrue(
            all(item["metrics"]["calibrationBinCount"] == 10 for item in result["evaluations"])
        )
        self.assertTrue(
            all(item["bootstrap"]["seed"] == 20260710 for item in result["evaluations"])
        )
        self.assertTrue(
            all(item["bootstrap"]["blockLength"] == 20 for item in result["evaluations"])
        )
        self.assertTrue(
            all(item["bootstrap"]["replicates"] == 2000 for item in result["evaluations"])
        )
        self.assertEqual(
            result["multipleComparisons"],
            {
                "candidateFamilySize": 4,
                "selectionContext": "selected_from_multiple_candidates",
                "supportWithoutSeparateFamilywiseAdjustment": False,
                "unadjusted95PercentIntervals": "descriptive_only",
            },
        )
        self.assertEqual(
            [item["totalBps"] for item in result["economics"]["costScenarios"]],
            [100.0, 300.0],
        )
        self.assertEqual(
            result["economics"]["minimumTailObservations"], 20
        )
        self.assertEqual(
            result["economics"]["downsideShortEconomics"],
            "not_identifiable_without_borrow_and_execution_data",
        )
        self.assertEqual(
            result["economics"]["multiSymbolPortfolioEconomics"],
            "not_identifiable_without_portfolio_weights_and_common_calendar",
        )
        self.assertEqual(result["counts"]["inputAnalysisRows"], 607 * 6)
        self.assertEqual(result["counts"]["invalidRowCount"], 0)
        self.assertEqual(result["counts"]["failureCount"], 0)
        self.assertEqual(
            result["leakageEvidence"]["sourceWindowMismatchCount"], 0
        )
        self.assertGreater(
            result["leakageEvidence"]["featureAvailabilityCheckCount"], 0
        )
        self.assertEqual(
            result["leakageEvidence"]["featureAvailabilityViolationCount"],
            0,
        )
        self.assertGreater(
            result["leakageEvidence"]["futureLabelRowCheckCount"], 0
        )
        self.assertTrue(
            result["leakageEvidence"]["futureLabelRowsExcludedFromFeatures"]
        )
        self.assertGreater(
            result["leakageEvidence"]["sourceWindowCheckCount"], 0
        )
        self.assertEqual(
            result["postResultTuning"], "forbidden_not_performed"
        )
        self.assertEqual(trial["status"], "completed")
        self.assertEqual(trial["evaluationCount"], 16)
        self.assertEqual(
            trial["frozenInputs"]["selectedSampleFreeze"]["sha256"],
            SAMPLE_SHA256,
        )
        self.assertEqual(
            trial["frozenInputs"]["mercFreeze"]["sha256"], MERC_SHA256
        )
        self.assertEqual(manifest["publishedArtifactCount"], 2)
        self.assertEqual(
            manifest["postResultTuning"], "forbidden_not_performed"
        )
        for path in run_directory.glob("*.json"):
            source = path.read_bytes()
            self.assertEqual(source, canonical_json_bytes(json.loads(source)))
            self.assertEqual(
                Path(f"{path}.sha256").read_text(encoding="ascii"),
                f"{sha256_path(path)}\n",
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(find_sensitive_values(source.decode("utf-8")), ())
        event_paths = tuple(
            (self.repository_root / self.ledger_directory / "events").glob(
                "*.json"
            )
        )
        self.assertEqual(len(event_paths), 1)
        event = json.loads(event_paths[0].read_text())
        self.assertEqual(event["eventType"], "rp001_interim_evaluation_completed")

    def test_result_separates_row_order_integrity_from_source_vintage_pit(
        self,
    ) -> None:
        self._run()

        result = json.loads(
            (self._run_directory() / "result.json").read_text()
        )
        leakage = result["leakageEvidence"]
        self.assertNotIn("pointInTimeFeatures", leakage)
        self.assertNotIn("futureRowsUsedOnlyForLabels", leakage)
        self.assertEqual(
            leakage["rowOrderFeatureWindowIntegrity"], "verified"
        )
        self.assertEqual(
            leakage["featureWindowIndexBoundary"],
            "indices_at_or_before_t_only",
        )
        self.assertEqual(leakage["futureRowsUsage"], "labels_only")
        self.assertEqual(
            leakage["sourceVintagePointInTime"], "not_identifiable"
        )
        self.assertEqual(
            leakage["providerPublicationTimestamp"], "not_documented"
        )
        self.assertEqual(
            leakage["providerRevisionPolicy"], "not_documented"
        )
        self.assertEqual(
            leakage["confirmatoryAdoptionPointInTimeGate"],
            "not_identifiable",
        )
        self.assertEqual(
            leakage["metricsEvidenceClass"],
            "research_only_price_volume_proxy",
        )

    def test_processed_hash_mismatch_publishes_failure_only_and_appends_event(
        self,
    ) -> None:
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256="0" * 64,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(raised.exception.code, "INPUT_HASH_MISMATCH")
        run_directory = self._run_directory()
        self.assertEqual(
            {path.name for path in run_directory.iterdir()},
            {"failure.json", "failure.json.sha256"},
        )
        failure = json.loads((run_directory / "failure.json").read_text())
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["errorCode"], "INPUT_HASH_MISMATCH")
        self.assertEqual(failure["counts"]["failureCount"], 1)
        self.assertEqual(failure["counts"]["invalidRowCount"], 0)
        self.assertEqual(
            failure["frozenInputs"]["selectedSampleFreeze"]["sha256"],
            SAMPLE_SHA256,
        )
        self.assertEqual(
            failure["frozenInputs"]["mercFreeze"]["sha256"], MERC_SHA256
        )
        self.assertEqual(failure["usageScope"], "research_only")
        self.assertEqual(
            failure["operationalDisposition"], "NoTrade/no integration"
        )
        event_paths = tuple(
            (self.repository_root / self.ledger_directory / "events").glob(
                "*.json"
            )
        )
        self.assertEqual(len(event_paths), 1)
        event = json.loads(event_paths[0].read_text())
        self.assertEqual(event["eventType"], "rp001_interim_evaluation_failed")

    def test_exact_scope_is_rejected_before_any_formula_evaluation(self) -> None:
        processed_path = (
            self.repository_root / self.arguments.processed_candles_path
        )
        processed = json.loads(processed_path.read_text())
        processed["symbols"][0]["symbol"] = "MSFT"
        processed_path.unlink()
        Path(f"{processed_path}.sha256").unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(processed_path, processed)
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256=binding.artifact_sha256,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(raised.exception.code, "DATA_SCOPE_MISMATCH")
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["stage"], "input_validation")
        self.assertEqual(failure["counts"]["failureCount"], 1)

    def test_invalid_lossless_row_is_counted_in_failure_evidence(self) -> None:
        processed_path = (
            self.repository_root / self.arguments.processed_candles_path
        )
        processed = json.loads(processed_path.read_text())
        processed["symbols"][0]["analysisRows"][0]["adjusted"][
            "closePrice"
        ]["kind"] = "float"
        processed_path.unlink()
        Path(f"{processed_path}.sha256").unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(processed_path, processed)
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256=binding.artifact_sha256,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(raised.exception.code, "DATA_SCHEMA_INVALID")
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["counts"]["failureCount"], 1)
        self.assertEqual(failure["counts"]["invalidRowCount"], 1)

    def test_future_timestamp_is_rejected_before_point_in_time_features(
        self,
    ) -> None:
        processed_path = (
            self.repository_root / self.arguments.processed_candles_path
        )
        processed = json.loads(processed_path.read_text())
        processed["symbols"][0]["analysisRows"][0]["timestamp"] = (
            "2099-01-03T21:00:00Z"
        )
        processed_path.unlink()
        Path(f"{processed_path}.sha256").unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(processed_path, processed)
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256=binding.artifact_sha256,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(
            raised.exception.code, "POINT_IN_TIME_AVAILABILITY_INVALID"
        )
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["stage"], "input_validation")
        self.assertEqual(failure["counts"]["invalidRowCount"], 1)

    def test_unused_ohlc_lexeme_is_validated_before_feature_conversion(
        self,
    ) -> None:
        processed_path = (
            self.repository_root / self.arguments.processed_candles_path
        )
        processed = json.loads(processed_path.read_text())
        processed["symbols"][0]["analysisRows"][0]["adjusted"][
            "highPrice"
        ]["text"] = "1e3"
        processed_path.unlink()
        Path(f"{processed_path}.sha256").unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(processed_path, processed)
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256=binding.artifact_sha256,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(raised.exception.code, "DATA_SCHEMA_INVALID")
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["counts"]["invalidRowCount"], 1)

    def test_adjusted_volume_requires_lossless_unsigned_integer_lexeme(
        self,
    ) -> None:
        processed_path = (
            self.repository_root / self.arguments.processed_candles_path
        )
        processed = json.loads(processed_path.read_text())
        processed["symbols"][0]["analysisRows"][0]["adjusted"]["volume"][
            "text"
        ] = "1.5"
        processed_path.unlink()
        Path(f"{processed_path}.sha256").unlink()
        binding = LocalArtifactStore(
            self.repository_root.resolve()
        ).publish_json(processed_path, processed)
        self.arguments = dataclasses.replace(
            self.arguments,
            processed_candles_sha256=binding.artifact_sha256,
        )

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            self._run()

        self.assertEqual(raised.exception.code, "DATA_SCHEMA_INVALID")
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["counts"]["invalidRowCount"], 1)

    def test_ledger_failure_rolls_back_success_before_failure_evidence(
        self,
    ) -> None:
        class RejectingLedger:
            def append(
                self,
                event_type: str,
                payload: Mapping[str, object],
                occurred_at: str,
            ) -> object:
                del event_type, payload, occurred_at
                raise LocalEvidenceError("injected ledger failure")

        with self.assertRaises(RUNNER.InterimEvaluationRunError) as raised:
            RUNNER.run_interim_evaluation(
                self.arguments,
                clock=fixed_clock,
                ledger_factory=lambda _path: RejectingLedger(),
            )

        self.assertEqual(raised.exception.code, "LEDGER_APPEND_FAILED")
        self.assertEqual(
            {path.name for path in self._run_directory().iterdir()},
            {"failure.json", "failure.json.sha256"},
        )
        failure = json.loads(
            (self._run_directory() / "failure.json").read_text()
        )
        self.assertEqual(failure["errorCode"], "LEDGER_APPEND_FAILED")
        self.assertFalse(
            (
                self.repository_root / self.ledger_directory / "events"
            ).exists()
        )

    def test_rollback_failure_blocks_conflicting_failure_publication(
        self,
    ) -> None:
        class RejectingLedger:
            def append(
                self,
                event_type: str,
                payload: Mapping[str, object],
                occurred_at: str,
            ) -> object:
                del event_type, payload, occurred_at
                raise LocalEvidenceError("injected ledger failure")

        def reject_rollback(
            _store: LocalArtifactStore,
            _binding: object,
        ) -> None:
            raise LocalEvidenceError("injected rollback failure")

        with mock.patch.object(
            RUNNER.LocalArtifactStore,
            "rollback_publication",
            new=reject_rollback,
        ):
            with self.assertRaises(
                RUNNER.InterimEvaluationRunError
            ) as raised:
                RUNNER.run_interim_evaluation(
                    self.arguments,
                    clock=fixed_clock,
                    ledger_factory=lambda _path: RejectingLedger(),
                )

        self.assertEqual(raised.exception.code, "EVIDENCE_ROLLBACK_FAILED")
        self.assertEqual(
            {path.name for path in self._run_directory().iterdir()},
            {
                "result.json",
                "result.json.sha256",
                "trial.json",
                "trial.json.sha256",
                "manifest.json",
                "manifest.json.sha256",
                "terminal-invalidation.json",
                "terminal-invalidation.json.sha256",
            },
        )
        self.assertFalse((self._run_directory() / "failure.json").exists())
        invalidation_path = (
            self._run_directory() / "terminal-invalidation.json"
        )
        invalidation_source = invalidation_path.read_bytes()
        invalidation = json.loads(invalidation_source)
        self.assertEqual(
            invalidation_source, canonical_json_bytes(invalidation)
        )
        self.assertEqual(
            Path(f"{invalidation_path}.sha256").read_text(encoding="ascii"),
            f"{sha256_path(invalidation_path)}\n",
        )
        self.assertEqual(stat.S_IMODE(invalidation_path.stat().st_mode), 0o600)
        self.assertEqual(
            find_sensitive_values(invalidation_source.decode("utf-8")), ()
        )
        self.assertEqual(invalidation["status"], "invalidated")
        self.assertEqual(
            invalidation["errorCode"], "EVIDENCE_ROLLBACK_FAILED"
        )
        self.assertEqual(
            invalidation["terminalAuthority"],
            "terminal_invalidation_supersedes_success_artifacts",
        )
        self.assertFalse(
            invalidation["retainedSuccessArtifactsAuthoritative"]
        )
        self.assertEqual(
            invalidation["invalidatedArtifactRoles"],
            ["result", "trial", "manifest"],
        )
        self.assertFalse(
            (
                self.repository_root / self.ledger_directory / "events"
            ).exists()
        )

    def test_invalidation_event_is_appended_when_ledger_recovers(
        self,
    ) -> None:
        class RejectThenRecordLedger:
            def __init__(self) -> None:
                self.call_count = 0
                self.events: list[
                    tuple[str, Mapping[str, object], str]
                ] = []

            def append(
                self,
                event_type: str,
                payload: Mapping[str, object],
                occurred_at: str,
            ) -> object:
                self.call_count += 1
                if self.call_count == 1:
                    raise LocalEvidenceError("injected ledger failure")
                self.events.append((event_type, payload, occurred_at))
                return object()

        def reject_rollback(
            _store: LocalArtifactStore,
            _binding: object,
        ) -> None:
            raise LocalEvidenceError("injected rollback failure")

        ledger = RejectThenRecordLedger()
        with mock.patch.object(
            RUNNER.LocalArtifactStore,
            "rollback_publication",
            new=reject_rollback,
        ):
            with self.assertRaises(RUNNER.InterimEvaluationRunError):
                RUNNER.run_interim_evaluation(
                    self.arguments,
                    clock=fixed_clock,
                    ledger_factory=lambda _path: ledger,
                )

        self.assertEqual(len(ledger.events), 1)
        event_type, payload, occurred_at = ledger.events[0]
        self.assertEqual(
            event_type, "rp001_interim_evaluation_invalidated"
        )
        self.assertEqual(payload["status"], "invalidated")
        self.assertFalse(payload["retainedSuccessArtifactsAuthoritative"])
        self.assertEqual(occurred_at, "2026-07-11T03:04:05Z")


if __name__ == "__main__":
    unittest.main()
