from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from unittest import mock
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerTransaction,
    canonical_json_bytes,
)
import rp001.program_completion as PROGRAM_COMPLETION
from rp001.program_completion import (
    COMPLETION_ARTIFACT_PATHS,
    FINAL_REPORT_PATH,
    PUBLIC_COMPLETION_ERROR_CODES,
    ProgramCompletionError,
    ProgramCompletionService,
)
from rp001.sensitive_value_policy import find_sensitive_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPLETED_AT = "2026-07-11T04:00:00Z"
EXPECTED_ARTIFACT_PATHS = (
    Path("research/rp-001/final/EB-002-program-terminal-evidence.json"),
    Path("research/rp-001/final/completion-traceability.json"),
    Path("research/rp-001/final/DR-002-no-adoptable-formula.json"),
    Path("research/rp-001/reports/RP001-20260711-final-research-report.md"),
    Path("research/rp-001/final/PC-001-program-completion.json"),
)
FOUNDATION_IMMUTABLE_PATHS = (
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/object.json",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/goal-v1.0.md",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/README.md",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/question-map.md",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/study-portfolio.md",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/integration-contract.md",
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior/seen-data-register.json",
)
PREDECESSOR_LEDGER_PATH = Path(
    "research/rp-001/local-ledgers/interim-program"
)
PROGRAM_COMPLETION_EVENT_PATH = (
    PREDECESSOR_LEDGER_PATH / "events/000019.json"
)


def _remove_terminal_completion_state(fixture_root: Path) -> None:
    terminal_body_paths = (
        *EXPECTED_ARTIFACT_PATHS,
        PROGRAM_COMPLETION_EVENT_PATH,
    )
    for relative_path in terminal_body_paths:
        body_path = fixture_root / relative_path
        body_path.unlink(missing_ok=True)
        Path(f"{body_path}.sha256").unlink(missing_ok=True)


class _FailingTransaction:
    def __init__(self, delegate: LocalLedgerTransaction) -> None:
        self._delegate = delegate

    def validate(self) -> object:
        return self._delegate.validate()

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        del event_type, payload, occurred_at
        raise RuntimeError("injected ledger failure")


class _FailingLedger:
    def __init__(self, ledger_directory: Path) -> None:
        self._delegate = AppendOnlyLocalLedger(ledger_directory)

    @contextmanager
    def transaction(self) -> Iterator[_FailingTransaction]:
        with self._delegate.transaction() as transaction:
            yield _FailingTransaction(transaction)


def _failing_ledger_factory(ledger_directory: Path) -> _FailingLedger:
    return _FailingLedger(ledger_directory)


class _CommitThenRaiseNonTransactionalLedger:
    def __init__(self, ledger_directory: Path) -> None:
        self._delegate = AppendOnlyLocalLedger(ledger_directory)

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        self._delegate.append(event_type, payload, occurred_at)
        raise RuntimeError("injected failure after nontransactional commit")


class _ExitFailureAfterCommitLedger:
    def __init__(self, ledger_directory: Path) -> None:
        self._delegate = AppendOnlyLocalLedger(ledger_directory)

    @contextmanager
    def transaction(self) -> Iterator[LocalLedgerTransaction]:
        with self._delegate.transaction() as transaction:
            yield transaction
        raise LocalEvidenceError("injected transaction exit failure")


class _PostAppendValidationFailureTransaction:
    def __init__(self, delegate: LocalLedgerTransaction) -> None:
        self._delegate = delegate
        self._append_returned = False

    def validate(self) -> object:
        if self._append_returned:
            raise LocalEvidenceError("injected post-append validation failure")
        return self._delegate.validate()

    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        entry = self._delegate.append(event_type, payload, occurred_at)
        self._append_returned = True
        return entry


class _PostAppendValidationFailureLedger:
    def __init__(self, ledger_directory: Path) -> None:
        self._delegate = AppendOnlyLocalLedger(ledger_directory)

    @contextmanager
    def transaction(self) -> Iterator[_PostAppendValidationFailureTransaction]:
        with self._delegate.transaction() as transaction:
            yield _PostAppendValidationFailureTransaction(transaction)


class ProgramCompletionBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ProgramCompletionService(REPOSITORY_ROOT)
        self.package = self.service.build(COMPLETED_AT)

    def _json_artifact(self, relative_path: Path) -> dict[str, object]:
        artifact = self.package.require_artifact(relative_path)
        value = json.loads(artifact.source.decode("utf-8"))
        self.assertIsInstance(value, dict)
        return value

    def test_invalid_calendar_timestamp_and_unregistered_error_codes_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.build("2026-99-99T99:99:99Z")
        self.assertEqual("INVALID_COMPLETION_TIMESTAMP", raised.exception.code)
        self.assertIn("INVALID_COMPLETION_TIMESTAMP", PUBLIC_COMPLETION_ERROR_CODES)
        with self.assertRaises(ValueError):
            ProgramCompletionError("UNREGISTERED\nCODE", "unsafe")

    def test_build_resolves_all_studies_without_inventing_registered_runs(
        self,
    ) -> None:
        evidence = self._json_artifact(
            Path("research/rp-001/final/EB-002-program-terminal-evidence.json")
        )
        terminals = evidence["studyTerminals"]
        self.assertIsInstance(terminals, list)
        self.assertEqual(8, len(terminals))
        status_by_study = {
            terminal["studySlot"]: terminal["terminalStatus"]
            for terminal in terminals
        }
        self.assertEqual(
            {
                "ST-ONT-001": "supported",
                "ST-DAT-001": "supported",
                "ST-BEH-001": "data_unavailable",
                "ST-VAL-001": "data_unavailable",
                "ST-MIC-001": "data_unavailable",
                "ST-EXE-001": "data_unavailable",
                "ST-RSK-001": "data_unavailable",
                "ST-SYN-001": "data_unavailable",
            },
            status_by_study,
        )
        self.assertTrue(
            all(terminal["registeredProtocolExperimentRunIds"] == [] for terminal in terminals)
        )
        behavior = next(
            terminal
            for terminal in terminals
            if terminal["studySlot"] == "ST-BEH-001"
        )
        self.assertEqual(
            ["RP001-EVAL-20260711-001"], behavior["researchOnlyRunIds"]
        )
        self.assertEqual("not_identifiable", behavior["directConstructStatus"])
        self.assertEqual(
            "research_only_insufficient_or_rejected",
            behavior["proxyEvidenceStatus"],
        )
        data_audit = next(
            terminal
            for terminal in terminals
            if terminal["studySlot"] == "ST-DAT-001"
        )
        self.assertEqual("supported", data_audit["auditOutcome"])
        self.assertEqual(
            "data_unavailable_for_confirmatory_adoption",
            data_audit["inputAvailabilityOutcome"],
        )

    def test_registered_five_session_study_is_separate_from_executed_ten_session_proxy(
        self,
    ) -> None:
        evidence = self._json_artifact(
            Path("research/rp-001/final/EB-002-program-terminal-evidence.json")
        )
        behavior = next(
            terminal
            for terminal in evidence["studyTerminals"]
            if terminal["studySlot"] == "ST-BEH-001"
        )
        expected_proxy = {
            "proxyQuestionId": "RQ-003-PV10-v1",
            "proxyProtocolId": "SP-003-PV10-v1",
            "proxyEstimand": "10-session binary continuation",
            "primaryHorizonSessions": 10,
            "outcomeIds": [
                "price_volume_upside_continuation_10d",
                "price_volume_downside_continuation_10d",
            ],
        }
        self.assertEqual("RQ-003", behavior["questionId"])
        self.assertEqual("SP-003", behavior["protocolId"])
        self.assertEqual(5, behavior["registeredPrimaryHorizonSessions"])
        self.assertEqual("data_unavailable", behavior["terminalStatus"])
        for key, value in expected_proxy.items():
            self.assertEqual(value, behavior[key])
            self.assertEqual(value, evidence["executedFormulaEvidence"][key])

        decision = self._json_artifact(
            Path("research/rp-001/final/DR-002-no-adoptable-formula.json")
        )
        g1 = next(
            gate
            for gate in decision["gateDispositions"]
            if gate["gateId"] == "G1"
        )
        self.assertIn("RQ-003/SP-003", g1["reason"])
        self.assertIn("RQ-003-PV10-v1/SP-003-PV10-v1", g1["reason"])

    def test_report_semantically_projects_historical_and_successor_source_scopes(
        self,
    ) -> None:
        evidence = self._json_artifact(
            Path("research/rp-001/final/EB-002-program-terminal-evidence.json")
        )
        scope = evidence["evidenceScope"]
        snapshot = scope["sourceMatrixSnapshot"]
        successor = scope["candleSuccessorObservation"]
        self.assertEqual("historical_design_snapshot", snapshot["role"])
        self.assertFalse(snapshot["liveApiCalled"])
        self.assertEqual("successor_live_read_only_observation", successor["role"])
        self.assertEqual(5250, successor["analysisRowCount"])
        self.assertTrue(successor["priceVolumeOpened"])
        self.assertFalse(successor["ordersAccountsAssetsAccessed"])
        self.assertFalse(scope["providerWideAbsenceClaim"])

        report = self.package.require_artifact(FINAL_REPORT_PATH).source.decode(
            "utf-8"
        )
        self.assertIn("RQ-003/SP-003의 5거래일 직접 행동 연구", report)
        self.assertIn("RQ-003-PV10-v1/SP-003-PV10-v1", report)
        self.assertIn("10-session binary continuation", report)
        self.assertIn("historical design snapshot", report)
        self.assertIn("liveApiCalled=false", report)
        self.assertIn("successor live read-only observation", report)
        self.assertIn("제공자 전체 또는 법적 부재를 뜻하지 않습니다", report)
        self.assertIn(
            f"[EB-002#{snapshot['claimId']}; {snapshot['binding']['path']}]",
            report,
        )
        self.assertIn(
            f"[EB-002#{successor['claimId']}; {successor['binding']['path']}]",
            report,
        )

        completion = self._json_artifact(
            Path("research/rp-001/final/PC-001-program-completion.json")
        )
        self.assertEqual(
            "not_available_deferred_external_anchor",
            completion["securityDisposition"][
                "coordinatedLocalRewriteDetection"
            ],
        )

    def test_completion_traceability_preserves_254_frozen_rows_and_separates_coverage_from_fulfillment(
        self,
    ) -> None:
        completion_trace = self._json_artifact(
            Path("research/rp-001/final/completion-traceability.json")
        )
        source_trace = json.loads(
            (
                REPOSITORY_ROOT
                / "research/meta-research/objects/programs/"
                "RP-001-quantitative-market-behavior/traceability.json"
            ).read_text(encoding="utf-8")
        )["traceability"]
        projected = completion_trace["requirements"]
        self.assertEqual(254, len(projected))
        self.assertEqual(
            [
                (row["sourceRequirementId"], row["questionIds"], row["studySlots"])
                for row in source_trace
            ],
            [
                (row["sourceRequirementId"], row["questionIds"], row["studySlots"])
                for row in projected
            ],
        )
        self.assertEqual(1.0, completion_trace["coverage"]["requirementCoverage"])
        self.assertLess(
            completion_trace["coverage"]["fulfilledCount"],
            completion_trace["coverage"]["requirementCount"],
        )
        self.assertNotIn(
            "unfulfilled",
            {row["requirementDisposition"] for row in projected},
        )
        self.assertTrue(all(isinstance(row["fulfilled"], bool) for row in projected))
        self.assertEqual(
            sum(row["fulfilled"] for row in projected),
            completion_trace["coverage"]["fulfilledCount"],
        )
        self.assertEqual(
            254,
            sum(completion_trace["coverage"]["dispositionCounts"].values()),
        )
        self.assertEqual(
            "fulfilled_at_final_handoff",
            projected[244]["requirementDisposition"],
        )
        self.assertFalse(projected[244]["fulfilled"])
        disposition_by_id = {
            row["sourceRequirementId"]: row["requirementDisposition"]
            for row in projected
        }
        self.assertEqual(
            "not_applicable_due_to_prior_gate",
            disposition_by_id["REQ-163"],
        )
        self.assertEqual(
            "superseded_scope_by_active_goal",
            disposition_by_id["REQ-164"],
        )
        self.assertEqual("terminal_negative", disposition_by_id["REQ-197"])
        self.assertEqual("terminal_negative", disposition_by_id["REQ-198"])
        self.assertEqual("fulfilled", disposition_by_id["REQ-209"])
        self.assertEqual("fulfilled", disposition_by_id["REQ-229"])
        self.assertEqual("fulfilled", disposition_by_id["REQ-230"])
        self.assertTrue(
            all(
                row["evidenceRefs"]
                and row["decisionIds"] == ["DR-002"]
                and row["reportPaths"] == [FINAL_REPORT_PATH.as_posix()]
                for row in projected
            )
        )

    def test_numeric_report_claims_bind_evidence_bundle_and_source_paths(self) -> None:
        evidence = self._json_artifact(
            Path("research/rp-001/final/EB-002-program-terminal-evidence.json")
        )
        report = self.package.require_artifact(EXPECTED_ARTIFACT_PATHS[3]).source.decode(
            "utf-8"
        )
        for claim in evidence["numericClaims"]:
            expected_reference = (
                f"[EB-002#{claim['claimId']}; {claim['source']['path']}]"
            )
            self.assertIn(expected_reference, report)
        self.assertEqual(
            "counter_conclusion_refuted",
            evidence["adversarialReview"]["result"],
        )

    def test_program_completion_reports_resolution_metrics_without_gate_pass_claim(self) -> None:
        completion = self._json_artifact(
            Path("research/rp-001/final/PC-001-program-completion.json")
        )
        metrics = completion["governanceResolutionMetrics"]
        self.assertEqual(
            {
                "questionCompleteness",
                "identifiabilityCoverage",
                "baselineCoverage",
                "falsificationCoverage",
                "temporalIntegrity",
                "trialDisclosure",
                "claimTraceability",
            },
            {metric["metricId"] for metric in metrics},
        )
        self.assertTrue(
            all(metric["value"] == 1.0 and not metric["gatePassImplied"] for metric in metrics)
        )

    def test_program_completion_records_exhaustive_immutable_sidecar_policy(
        self,
    ) -> None:
        completion = self._json_artifact(
            Path("research/rp-001/final/PC-001-program-completion.json")
        )
        bindings = completion["immutableInputBindings"]
        self.assertIsInstance(bindings, list)
        by_path = {binding["path"]: binding for binding in bindings}
        for path in FOUNDATION_IMMUTABLE_PATHS:
            self.assertEqual(
                "legacy_absent/forbidden",
                by_path[path]["sidecarPolicy"],
            )
        formula_path = (
            "research/rp-001/contracts/"
            "interim-formula-contract-v1.0.1.json"
        )
        self.assertEqual("required", by_path[formula_path]["sidecarPolicy"])
        policy_summary = completion["immutableInputPolicySummary"]
        self.assertEqual(17, policy_summary["required"])
        self.assertEqual(
            len(bindings),
            sum(policy_summary.values()),
        )
        runtime_bindings = completion["reproducibilityManifest"][
            "runtimeSourceBindings"
        ]
        self.assertTrue(runtime_bindings)
        self.assertTrue(
            all(
                binding["sidecarPolicy"] == "legacy_absent/forbidden"
                for binding in runtime_bindings
            )
        )

    def test_decision_is_no_adoptable_notrade_and_preserves_failed_gates(
        self,
    ) -> None:
        decision = self._json_artifact(
            Path("research/rp-001/final/DR-002-no-adoptable-formula.json")
        )
        self.assertEqual("no_adoptable_formula", decision["decision"])
        self.assertFalse(decision["operationalUseAllowed"])
        self.assertEqual("NoTrade/no integration", decision["operationalDisposition"])
        gate_results = {
            row["gateId"]: row["result"] for row in decision["gateDispositions"]
        }
        self.assertEqual("fail", gate_results["G2"])
        self.assertEqual("fail", gate_results["G3"])
        self.assertEqual("fail", gate_results["G6"])
        self.assertEqual("not_evaluated", gate_results["G7b"])
        self.assertEqual("not_evaluated", gate_results["G8"])
        self.assertEqual("not_evaluated", gate_results["G9"])
        self.assertEqual("not_evaluated", gate_results["G10"])
        self.assertEqual(
            {
                "external_artifact_cas",
                "multi_anchor_signed_receipts",
                "third_party_identity_infrastructure",
                "global_six_digit_id_allocator",
                "sealed_full_cli",
                "final_evidence_decision_completion",
                "reproduction_rights_external_sink",
            },
            {item["capabilityId"] for item in decision["deferredCapabilities"]},
        )
        self.assertTrue(
            all(
                item["status"] == "deferred_until_final_adoption"
                for item in decision["deferredCapabilities"]
            )
        )

    def test_active_goal_and_all_must_hold_rules_have_separate_coverage(self) -> None:
        evidence = self._json_artifact(
            Path("research/rp-001/final/EB-002-program-terminal-evidence.json")
        )
        coverage = evidence["activeGoalCoverage"]
        self.assertEqual("1.2-COMPACT", coverage["goalVersion"])
        self.assertEqual(11, coverage["mustHoldRuleCount"])
        self.assertEqual(11, coverage["tracedMustHoldRuleCount"])
        self.assertEqual(1.0, coverage["mustHoldRuleCoverage"])
        self.assertTrue(
            all(row["status"] == "fulfilled" for row in coverage["mustHoldRules"])
        )

    def test_package_is_canonical_secret_free_and_has_no_self_hash_keys(
        self,
    ) -> None:
        self.assertEqual(EXPECTED_ARTIFACT_PATHS, self.package.paths)
        for artifact in self.package.artifacts:
            self.assertEqual((), find_sensitive_values(artifact.source.decode("utf-8")))
            if artifact.media_type == "application/json":
                value = json.loads(artifact.source.decode("utf-8"))
                self.assertEqual(artifact.source, canonical_json_bytes(value))
                serialized = artifact.source.decode("utf-8")
                self.assertNotIn('"artifactSha256"', serialized)
                self.assertNotIn('"selfSha256"', serialized)
                self.assertNotIn('"recordSha256"', serialized)


class ProgramCompletionPublicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.publication_root = Path(self.temporary_directory.name).resolve()
        self.service = ProgramCompletionService(
            REPOSITORY_ROOT,
            publication_root=self.publication_root,
        )
        source_ledger = REPOSITORY_ROOT / PREDECESSOR_LEDGER_PATH
        destination_ledger = self.publication_root / PREDECESSOR_LEDGER_PATH
        destination_ledger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_ledger, destination_ledger)
        _remove_terminal_completion_state(self.publication_root)

    def test_finalize_publishes_detached_hashes_then_appends_one_event(self) -> None:
        summary = self.service.finalize(COMPLETED_AT)
        self.assertEqual(5, summary.artifact_count)
        for relative_path in EXPECTED_ARTIFACT_PATHS:
            body_path = self.publication_root / relative_path
            sidecar_path = Path(f"{body_path}.sha256")
            self.assertTrue(body_path.is_file())
            self.assertTrue(sidecar_path.is_file())
            self.assertEqual(
                f"{hashlib.sha256(body_path.read_bytes()).hexdigest()}\n",
                sidecar_path.read_text(encoding="ascii"),
            )
        event_path = (
            self.publication_root
            / PROGRAM_COMPLETION_EVENT_PATH
        )
        self.assertTrue(event_path.is_file())
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertEqual("rp001_program_completed_no_adoptable_formula", event["eventType"])
        self.assertEqual("PC-001", event["payload"]["completionId"])
        self.assertEqual(
            "6a542d150a36ef650cea10a6ea613686eb16e0a6764038e0e21beb028422ab07",
            event["previousRecordSha256"],
        )
        self.assertEqual(5, len(event["payload"]["artifactBindings"]))

    def test_ledger_failure_rolls_back_every_published_body_and_sidecar(self) -> None:
        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.finalize(
                COMPLETED_AT,
                ledger_factory=_failing_ledger_factory,
            )
        self.assertEqual("LEDGER_APPEND_FAILED", raised.exception.code)
        for relative_path in EXPECTED_ARTIFACT_PATHS:
            body_path = self.publication_root / relative_path
            self.assertFalse(body_path.exists())
            self.assertFalse(Path(f"{body_path}.sha256").exists())

    def test_nontransactional_ledger_is_rejected_before_artifacts_or_event(self) -> None:
        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.finalize(
                COMPLETED_AT,
                ledger_factory=_CommitThenRaiseNonTransactionalLedger,
            )

        self.assertEqual("LEDGER_APPEND_FAILED", raised.exception.code)
        for relative_path in EXPECTED_ARTIFACT_PATHS:
            body_path = self.publication_root / relative_path
            self.assertFalse(body_path.exists())
            self.assertFalse(Path(f"{body_path}.sha256").exists())
        self.assertFalse(
            (
                self.publication_root
                / PREDECESSOR_LEDGER_PATH
                / "events/000019.json"
            ).exists()
        )

    def test_transaction_exit_failure_after_exact_commit_preserves_publication(
        self,
    ) -> None:
        summary = self.service.finalize(
            COMPLETED_AT,
            ledger_factory=_ExitFailureAfterCommitLedger,
        )

        self.assertEqual("finalized", summary.mode)
        self.assertTrue(
            (
                self.publication_root
                / PREDECESSOR_LEDGER_PATH
                / "events/000019.json"
            ).is_file()
        )
        for relative_path in EXPECTED_ARTIFACT_PATHS:
            self.assertTrue((self.publication_root / relative_path).is_file())
            self.assertTrue(
                Path(f"{self.publication_root / relative_path}.sha256").is_file()
            )

    def test_post_append_validation_failure_after_exact_commit_preserves_publication(
        self,
    ) -> None:
        summary = self.service.finalize(
            COMPLETED_AT,
            ledger_factory=_PostAppendValidationFailureLedger,
        )

        self.assertEqual("finalized", summary.mode)
        self.assertTrue(
            (
                self.publication_root
                / PREDECESSOR_LEDGER_PATH
                / "events/000019.json"
            ).is_file()
        )
        for relative_path in EXPECTED_ARTIFACT_PATHS:
            body_path = self.publication_root / relative_path
            self.assertTrue(body_path.is_file())
            self.assertTrue(Path(f"{body_path}.sha256").is_file())

    def test_existing_output_is_never_overwritten(self) -> None:
        occupied = self.publication_root / COMPLETION_ARTIFACT_PATHS[0]
        LocalArtifactStore(self.publication_root.resolve()).publish_json(
            occupied,
            {"occupied": True},
        )
        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.finalize(COMPLETED_AT)
        self.assertEqual("OUTPUT_ALREADY_EXISTS", raised.exception.code)
        self.assertEqual({"occupied": True}, json.loads(occupied.read_text(encoding="utf-8")))

    def test_verify_is_read_only_and_detects_self_consistent_body_rehash(self) -> None:
        self.service.finalize(COMPLETED_AT)
        tracked_paths = [
            path
            for relative_path in EXPECTED_ARTIFACT_PATHS
            for path in (
                self.publication_root / relative_path,
                Path(f"{self.publication_root / relative_path}.sha256"),
            )
        ]
        tracked_paths.extend(
            sorted((self.publication_root / PREDECESSOR_LEDGER_PATH / "events").iterdir())
        )
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked_paths}

        summary = self.service.verify()

        self.assertEqual("verified", summary.mode)
        self.assertEqual(
            before,
            {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked_paths},
        )

        decision_path = self.publication_root / EXPECTED_ARTIFACT_PATHS[2]
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["decision"] = "tampered"
        tampered_source = canonical_json_bytes(decision)
        decision_path.write_bytes(tampered_source)
        Path(f"{decision_path}.sha256").write_text(
            f"{hashlib.sha256(tampered_source).hexdigest()}\n",
            encoding="ascii",
        )
        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.verify()
        self.assertEqual("PUBLICATION_DRIFT", raised.exception.code)

    def test_verify_rejects_noncanonical_event_with_extra_key_and_valid_sidecar(
        self,
    ) -> None:
        self.service.finalize(COMPLETED_AT)
        event_path = (
            self.publication_root
            / PREDECESSOR_LEDGER_PATH
            / "events/000019.json"
        )
        event = json.loads(event_path.read_text(encoding="utf-8"))
        event["unexpected"] = True
        source = json.dumps(event, indent=2, sort_keys=True).encode("utf-8")
        event_path.write_bytes(source)
        Path(f"{event_path}.sha256").write_text(
            f"{hashlib.sha256(source).hexdigest()}\n",
            encoding="ascii",
        )

        with self.assertRaises(ProgramCompletionError) as raised:
            self.service.verify()

        self.assertEqual("LEDGER_BINDING_INVALID", raised.exception.code)

    def test_publication_root_ancestor_symlink_cannot_redirect_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            external = root / "external"
            external.mkdir()
            redirected_root = root / "redirected-root"
            redirected_root.symlink_to(external, target_is_directory=True)
            source_ledger = REPOSITORY_ROOT / PREDECESSOR_LEDGER_PATH
            destination_ledger = external / PREDECESSOR_LEDGER_PATH
            destination_ledger.parent.mkdir(parents=True)
            shutil.copytree(source_ledger, destination_ledger)
            _remove_terminal_completion_state(external)
            with self.assertRaises(ProgramCompletionError):
                ProgramCompletionService(
                    REPOSITORY_ROOT,
                    publication_root=redirected_root,
                ).finalize(COMPLETED_AT)

            self.assertFalse(
                (external / EXPECTED_ARTIFACT_PATHS[0]).exists()
            )
            self.assertFalse(
                (destination_ledger / "events/000019.json").exists()
            )


class ProgramCompletionImmutableInputTest(unittest.TestCase):
    def test_symlink_repository_root_default_publication_is_rejected_without_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name).resolve()
            outside = root / "outside"
            (outside / "research").mkdir(parents=True)
            shutil.copytree(
                REPOSITORY_ROOT / "research/meta-research",
                outside / "research/meta-research",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "research/rp-001",
                outside / "research/rp-001",
            )
            _remove_terminal_completion_state(outside)
            repository_alias = root / "repository-alias"
            repository_alias.symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ProgramCompletionError) as raised:
                ProgramCompletionService(repository_alias).finalize(COMPLETED_AT)

            self.assertEqual("UNSAFE_PUBLICATION_PATH", raised.exception.code)
            for relative_path in EXPECTED_ARTIFACT_PATHS:
                self.assertFalse((outside / relative_path).exists())
                self.assertFalse(Path(f"{outside / relative_path}.sha256").exists())
            self.assertFalse(
                (
                    outside
                    / PREDECESSOR_LEDGER_PATH
                    / "events/000019.json"
                ).exists()
            )

    def test_semantically_incompatible_proxy_contract_is_rejected_even_if_rehashed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            repository_copy = Path(directory_name).resolve()
            (repository_copy / "research").mkdir()
            shutil.copytree(
                REPOSITORY_ROOT / "research/meta-research",
                repository_copy / "research/meta-research",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "research/rp-001",
                repository_copy / "research/rp-001",
            )
            _remove_terminal_completion_state(repository_copy)
            contract_path = repository_copy / (
                "research/rp-001/contracts/"
                "interim-formula-contract-v1.0.1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["formulaContract"]["primary_horizon_sessions"] = 9
            source = canonical_json_bytes(contract)
            source_sha256 = hashlib.sha256(source).hexdigest()
            contract_path.write_bytes(source)
            Path(f"{contract_path}.sha256").write_text(
                f"{source_sha256}\n",
                encoding="ascii",
            )

            with mock.patch.dict(
                PROGRAM_COMPLETION._EXPECTED_IMMUTABLE_HASHES,
                {PROGRAM_COMPLETION._FORMULA_CONTRACT_PATH: source_sha256},
            ):
                with self.assertRaises(ProgramCompletionError) as raised:
                    ProgramCompletionService(repository_copy).build(COMPLETED_AT)

            self.assertEqual("IMMUTABLE_INPUT_INVALID", raised.exception.code)

    def test_required_formula_contract_sidecar_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            repository_copy = Path(directory_name).resolve()
            (repository_copy / "research").mkdir()
            shutil.copytree(
                REPOSITORY_ROOT / "research/meta-research",
                repository_copy / "research/meta-research",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "research/rp-001",
                repository_copy / "research/rp-001",
            )
            _remove_terminal_completion_state(repository_copy)
            sidecar_path = repository_copy / (
                "research/rp-001/contracts/"
                "interim-formula-contract-v1.0.1.json.sha256"
            )
            sidecar_path.unlink()

            with self.assertRaises(ProgramCompletionError) as raised:
                ProgramCompletionService(repository_copy).build(COMPLETED_AT)

            self.assertEqual("IMMUTABLE_HASH_MISMATCH", raised.exception.code)

    def test_self_consistent_source_and_sidecar_rehash_cannot_replace_frozen_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            repository_copy = Path(directory_name).resolve()
            (repository_copy / "research").mkdir()
            shutil.copytree(
                REPOSITORY_ROOT / "research/meta-research",
                repository_copy / "research/meta-research",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "research/rp-001",
                repository_copy / "research/rp-001",
            )
            _remove_terminal_completion_state(repository_copy)
            contract_path = (
                repository_copy
                / "research/rp-001/contracts/interim-formula-contract-v1.0.1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["decisionScope"] = "tampered"
            tampered_source = canonical_json_bytes(contract)
            contract_path.write_bytes(tampered_source)
            Path(f"{contract_path}.sha256").write_text(
                f"{hashlib.sha256(tampered_source).hexdigest()}\n",
                encoding="ascii",
            )

            with self.assertRaises(ProgramCompletionError) as raised:
                ProgramCompletionService(repository_copy).build(COMPLETED_AT)

            self.assertEqual("IMMUTABLE_HASH_MISMATCH", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
