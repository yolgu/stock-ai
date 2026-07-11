from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rp001.autonomy.controller as controller_module
from rp001.autonomy.controller import (
    ActionResultError,
    AutonomousResearchController,
    AutonomousResearchError,
)
from rp001.autonomy.goal_contract import compile_goal_document
from rp001.autonomy.policy import NextActionKind
from rp001.local_evidence import (
    LocalLedgerAppendError,
    canonical_json_bytes,
    sha256_bytes,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CLI_PATH = REPOSITORY_ROOT / "research" / "rp-001" / "autonomous_research.py"
PYTHON = Path(
    "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)


class AutonomousControllerCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.output_root = self.root / "research" / "rp-001" / "autonomy-runs"
        self.confirmation_root = self.root / "released-confirmation"
        self.live_root = self.root / ".storage" / "rp001-live"
        self.confirmation_root.mkdir(parents=True)
        self.live_root.mkdir(parents=True)
        self.program_root = self.output_root / "RP-001-AUTO-PRESET-001"
        self.goal_path = self.root / "goal-objective.md"
        self.goal_source = b"Study direction-neutral market overheating.\n"
        self.goal_path.write_bytes(self.goal_source)
        self.spec_input = self.root / "program-spec-input.json"
        self.spec_input.write_bytes(canonical_json_bytes(self._spec_body()))
        self.controller = AutonomousResearchController(
            repository_root=self.root,
            preset_output_root=self.output_root,
            live_collection_roots=(self.live_root,),
            confirmation_release_root=self.confirmation_root,
        )

    def test_bootstrap_publishes_goal_spec_and_replayable_ledger(self) -> None:
        summary = self._bootstrap()

        self.assertEqual("AWAITING_DATA_RELEASE", summary.state.value)
        self.assertTrue((self.program_root / "goal-source.md").is_file())
        self.assertTrue((self.program_root / "program-spec.json").is_file())
        self.assertTrue(
            (self.program_root / "ledger" / "events" / "000001.json").is_file()
        )
        status = self.controller.status(self.program_root)
        self.assertEqual(summary, status.snapshot)
        self.assertEqual(1, status.ledger_state.sequence)

    def test_bootstrap_goal_derives_program_root_from_plain_goal(self) -> None:
        goal_source = b"[GOAL-RP-001 v1.0]\nComplete immutable research Goal.\n"
        self.goal_path.write_bytes(goal_source)
        expected_spec = compile_goal_document(goal_source)
        expected_root = self.output_root / expected_spec.program_id

        summary = self.controller.bootstrap_goal(
            goal_path=self.goal_path,
            program_root=None,
            occurred_at="2026-07-11T10:00:00Z",
        )

        self.assertEqual("AWAITING_DATA_RELEASE", summary.state.value)
        published = json.loads((expected_root / "program-spec.json").read_text())
        self.assertEqual(hashlib.sha256(goal_source).hexdigest(), published["goalSha256"])
        self.assertEqual(expected_spec.program_id, published["programId"])
        self.assertEqual(goal_source, self.goal_path.read_bytes())

    def test_bootstrap_goal_replays_existing_program_without_second_event(self) -> None:
        goal_source = b"[GOAL-RP-001 v1.0]\nResume the same bounded Goal.\n"
        self.goal_path.write_bytes(goal_source)
        program_root = self.output_root / compile_goal_document(goal_source).program_id

        first = self.controller.bootstrap_goal(
            goal_path=self.goal_path,
            program_root=None,
            occurred_at="2026-07-11T10:00:00Z",
        )
        repeated = self.controller.bootstrap_goal(
            goal_path=self.goal_path,
            program_root=None,
            occurred_at="2026-07-11T10:01:00Z",
        )

        self.assertEqual(first, repeated)
        self.assertEqual(1, self.controller.status(program_root).ledger_state.sequence)

    def test_bootstrap_goal_rejects_sensitive_value_before_any_write(self) -> None:
        goal_source = (
            b"# Autonomous research Goal\n\ncredential: "
            + ("ts" + "ck_" + "live_" + "A1" * 12).encode("ascii")
            + b"\n"
        )
        self.goal_path.write_bytes(goal_source)
        expected_root = (
            self.output_root / compile_goal_document(goal_source).program_id
        )

        with self.assertRaisesRegex(
            AutonomousResearchError,
            "goal_sensitive_value",
        ):
            self.controller.bootstrap_goal(
                goal_path=self.goal_path,
                program_root=None,
                occurred_at="2026-07-11T10:00:00Z",
            )

        self.assertFalse(expected_root.exists())

    def test_bootstrap_preserves_bindings_only_when_ledger_event_was_committed(self) -> None:
        for event_published in (False, True):
            with self.subTest(event_published=event_published):
                program_root = self.output_root / "RP-001-AUTO-PRESET-001"
                ledger = _FailingBootstrapLedger(event_published)
                with mock.patch.object(
                    AutonomousResearchController,
                    "_ledger",
                    return_value=ledger,
                ):
                    with self.assertRaises(LocalLedgerAppendError):
                        self.controller.bootstrap(
                            goal_path=self.goal_path,
                            program_spec_input_path=self.spec_input,
                            program_root=program_root,
                            occurred_at="2026-07-11T10:00:00Z",
                        )

                self.assertEqual(
                    event_published,
                    (program_root / "goal-source.md").exists(),
                )
                self.assertEqual(
                    event_published,
                    (program_root / "program-spec.json").exists(),
                )
                if event_published:
                    for path in (
                        program_root / "goal-source.md",
                        program_root / "program-spec.json",
                    ):
                        path.unlink()
                        Path(f"{path}.sha256").unlink()

    def test_next_is_read_only_and_stable_until_ledger_changes(self) -> None:
        self._bootstrap()

        first = self.controller.next_action(self.program_root)
        second = self.controller.next_action(self.program_root)

        self.assertEqual(NextActionKind.WAIT_FOR_DATA_RELEASE, first.kind)
        self.assertEqual(first, second)
        self.assertEqual(1, self.controller.status(self.program_root).ledger_state.sequence)
        contract = first.to_canonical_dict(self.root)
        self.assertIn("inputBindings", contract)
        self.assertIn("allowedWritePaths", contract)
        self.assertIn("requiredValidators", contract)
        self.assertIn("successEventType", contract)
        self.assertIn("failureEventType", contract)
        self.assertIn("resourceBudget", contract)
        self.assertEqual("development", contract["dataRequest"]["role"])
        self.assertEqual(
            "research-data/releases/RP-001",
            contract["dataRequest"]["manifestDirectory"],
        )

    def test_register_release_then_validate_and_commit_one_action(self) -> None:
        self._bootstrap()
        manifest = self.root / "research-data" / "release-001" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-001",
            role="development",
            manifest_path=manifest,
            occurred_at="2026-07-11T10:01:00Z",
        )
        action = self.controller.next_action(self.program_root)
        self.assertEqual(NextActionKind.VALIDATE_DATA_RELEASE, action.kind)

        report = self.program_root / "artifacts" / action.action_id / "report.json"
        report.parent.mkdir(parents=True)
        report.write_bytes(canonical_json_bytes({"status": "valid"}))
        report_sha256 = sha256_bytes(report.read_bytes())
        Path(f"{report}.sha256").write_text(
            f"{report_sha256}\n",
            encoding="ascii",
        )
        result_path = self.program_root / "action-result.json"
        result_path.write_bytes(
            canonical_json_bytes(
                {
                    "schemaVersion": "rp001-autonomous-action-result.v1",
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "fromState": "VALIDATE_MEASUREMENT",
                    "toState": "FREEZE_CYCLE_SPEC",
                    "status": "succeeded",
                    "artifactBindings": [
                        {
                            "path": report.relative_to(self.root).as_posix(),
                            "sha256": report_sha256,
                        }
                    ],
                    "facts": {},
                }
            )
        )

        committed = self.controller.commit_result(
            self.program_root,
            result_path,
            occurred_at="2026-07-11T10:02:00Z",
        )

        self.assertEqual("FREEZE_CYCLE_SPEC", committed.state.value)
        self.assertEqual(
            NextActionKind.FREEZE_CYCLE_SPEC,
            self.controller.next_action(self.program_root).kind,
        )
        with self.assertRaisesRegex(ActionResultError, "action_id_reused"):
            self.controller.commit_result(
                self.program_root,
                result_path,
                occurred_at="2026-07-11T10:03:00Z",
            )

    def test_verify_detects_rehashed_committed_artifact_mutation(self) -> None:
        self._bootstrap()
        manifest = self.root / "research-data" / "release-verify" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-VERIFY-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-VERIFY-001",
            role="development",
            manifest_path=manifest,
            occurred_at="2026-07-11T10:01:00Z",
        )
        action = self.controller.next_action(self.program_root)
        artifact = action.allowed_write_directory / "measurement.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(canonical_json_bytes({"status": "valid"}))
        result = self._bound_result(action, artifact, "verify-result.json")
        self.controller.commit_result(
            self.program_root,
            result,
            occurred_at="2026-07-11T10:02:00Z",
        )

        artifact.write_bytes(canonical_json_bytes({"status": "mutated"}))
        mutated_sha256 = sha256_bytes(artifact.read_bytes())
        Path(f"{artifact}.sha256").write_text(
            f"{mutated_sha256}\n",
            encoding="ascii",
        )

        with self.assertRaisesRegex(
            AutonomousResearchError,
            "committed_artifact_hash_mismatch",
        ):
            self.controller.verify(self.program_root)

    def test_data_release_manifest_rejects_sensitive_values(self) -> None:
        self._bootstrap()
        manifest = self.root / "sensitive-manifest.json"
        manifest.write_bytes(
            canonical_json_bytes(
                {"credential": "ts" + "sk_" + "test_" + "B2" * 12}
            )
        )

        with self.assertRaisesRegex(
            AutonomousResearchError,
            "release_manifest_sensitive_value",
        ):
            self.controller.register_data_release(
                self.program_root,
                release_id="DEV-SENSITIVE-001",
                role="development",
                manifest_path=manifest,
                occurred_at="2026-07-11T10:01:00Z",
            )

        manifest.write_bytes(b'{"value":NaN}')
        with self.assertRaisesRegex(
            AutonomousResearchError,
            "release_manifest_invalid",
        ):
            self.controller.register_data_release(
                self.program_root,
                release_id="DEV-NONFINITE-001",
                role="development",
                manifest_path=manifest,
                occurred_at="2026-07-11T10:02:00Z",
            )

    def test_confirmation_manifest_is_not_read_before_formula_freeze(self) -> None:
        self._bootstrap()
        sealed = self.confirmation_root / "sealed-confirmation.json"
        sealed.write_bytes(canonical_json_bytes({"releaseId": "CONF-SEALED-001"}))
        original = controller_module._read_regular_bytes

        def reject_sealed_read(path: Path, error: str) -> bytes:
            if path == sealed:
                raise AssertionError("confirmation_read_before_freeze")
            return original(path, error)

        with mock.patch.object(
            controller_module,
            "_read_regular_bytes",
            side_effect=reject_sealed_read,
        ):
            with self.assertRaisesRegex(
                AutonomousResearchError,
                "confirmation_not_frozen",
            ):
                self.controller.register_data_release(
                    self.program_root,
                    release_id="CONF-SEALED-001",
                    role="confirmation",
                    manifest_path=sealed,
                    occurred_at="2026-07-11T10:01:00Z",
                )

    def test_rejects_artifact_outside_preset_output_or_with_wrong_hash(self) -> None:
        self._bootstrap()
        manifest = self.root / "release-manifest.json"
        manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-001",
            role="development",
            manifest_path=manifest,
            occurred_at="2026-07-11T10:01:00Z",
        )
        action = self.controller.next_action(self.program_root)
        external = self.root / "outside.json"
        external.write_bytes(canonical_json_bytes({"status": "valid"}))
        for path, digest in (
            (external, sha256_bytes(external.read_bytes())),
            (
                self.program_root / "artifacts" / "missing.json",
                "f" * 64,
            ),
        ):
            with self.subTest(path=path):
                result_path = self.root / f"result-{len(path.name)}.json"
                result_path.write_bytes(
                    canonical_json_bytes(
                        {
                            "schemaVersion": "rp001-autonomous-action-result.v1",
                            "actionId": action.action_id,
                            "actionKind": action.kind.value,
                            "fromState": "VALIDATE_MEASUREMENT",
                            "toState": "FREEZE_CYCLE_SPEC",
                            "status": "succeeded",
                            "artifactBindings": [
                                {
                                    "path": path.relative_to(self.root).as_posix(),
                                    "sha256": digest,
                                }
                            ],
                            "facts": {},
                        }
                    )
                )

                with self.assertRaises(ActionResultError):
                    self.controller.validate_result(self.program_root, result_path)

    def test_accepts_hashed_binary_artifact_and_rejects_noncanonical_json(self) -> None:
        self._bootstrap()
        manifest = self.root / "release-manifest.json"
        manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-001",
            role="development",
            manifest_path=manifest,
            occurred_at="2026-07-11T10:01:00Z",
        )
        action = self.controller.next_action(self.program_root)
        action.allowed_write_directory.mkdir(parents=True)

        binary = action.allowed_write_directory / "oof.parquet"
        binary.write_bytes(b"PAR1\x00\xffsynthetic\x00PAR1")
        binary_result = self._bound_result(action, binary, "binary-result.json")
        self.assertTrue(
            self.controller.validate_result(self.program_root, binary_result)
        )

        noncanonical = action.allowed_write_directory / "report.json"
        noncanonical.write_bytes(b'{ "status": "valid" }')
        noncanonical_result = self._bound_result(
            action,
            noncanonical,
            "noncanonical-result.json",
        )
        with self.assertRaisesRegex(ActionResultError, "artifact_canonical_json_invalid"):
            self.controller.validate_result(self.program_root, noncanonical_result)

        sensitive_result = self._bound_result(
            action,
            binary,
            "sensitive-result.json",
            facts={"diagnostic": "ts" + "ck_" + "live_" + "A1" * 12},
        )
        with self.assertRaisesRegex(ActionResultError, "action_result_sensitive_value"):
            self.controller.validate_result(self.program_root, sensitive_result)

    def test_cli_status_outputs_canonical_json_without_modifying_state(self) -> None:
        self._bootstrap()
        completed = subprocess.run(
            [
                str(PYTHON),
                "-B",
                str(CLI_PATH),
                "status",
                "--repository-root",
                str(self.root),
                "--preset-output-root",
                str(self.output_root),
                "--confirmation-release-root",
                str(self.confirmation_root),
                "--program-root",
                str(self.program_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(REPOSITORY_ROOT / "research" / "rp-001" / "src")},
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual("AWAITING_DATA_RELEASE", output["state"])
        self.assertEqual(1, output["ledgerSequence"])
        self.assertEqual(1, self.controller.status(self.program_root).ledger_state.sequence)

    def test_cli_bootstrap_goal_does_not_require_program_root(self) -> None:
        goal_source = b"[GOAL-RP-001 v1.0]\nCLI plain Goal bootstrap.\n"
        self.goal_path.write_bytes(goal_source)
        expected_spec = compile_goal_document(goal_source)
        completed = subprocess.run(
            [
                str(PYTHON),
                "-B",
                str(CLI_PATH),
                "bootstrap-goal",
                "--repository-root",
                str(self.root),
                "--preset-output-root",
                str(self.output_root),
                "--confirmation-release-root",
                str(self.confirmation_root),
                "--goal",
                str(self.goal_path),
                "--occurred-at",
                "2026-07-11T10:00:00Z",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(REPOSITORY_ROOT / "research" / "rp-001" / "src")},
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(expected_spec.program_id, output["programId"])
        self.assertTrue(
            (self.output_root / expected_spec.program_id / "program-spec.json").is_file()
        )

    def test_pause_and_resume_are_append_only(self) -> None:
        self._bootstrap()

        paused = self.controller.pause(
            self.program_root,
            occurred_at="2026-07-11T10:01:00Z",
        )
        self.assertTrue(paused.paused_by_user)
        self.assertEqual(
            NextActionKind.NONE,
            self.controller.next_action(self.program_root).kind,
        )

        resumed = self.controller.resume(
            self.program_root,
            occurred_at="2026-07-11T10:02:00Z",
        )
        self.assertFalse(resumed.paused_by_user)
        self.assertEqual(
            NextActionKind.WAIT_FOR_DATA_RELEASE,
            self.controller.next_action(self.program_root).kind,
        )

    def test_open_p0_is_append_only_and_preempts_next_action(self) -> None:
        self._bootstrap()

        snapshot = self.controller.open_p0(
            self.program_root,
            blocker_id="P0-LEAK-001",
            reason="future_information_leakage",
            occurred_at="2026-07-11T10:01:00Z",
        )

        self.assertEqual(frozenset({"P0-LEAK-001"}), snapshot.open_p0_blockers)
        action = self.controller.next_action(self.program_root)
        self.assertEqual(NextActionKind.REPAIR_P0, action.kind)
        self.assertEqual("open_p0_blocker:P0-LEAK-001", action.reason)

    def _bootstrap(self):
        return self.controller.bootstrap(
            goal_path=self.goal_path,
            program_spec_input_path=self.spec_input,
            program_root=self.program_root,
            occurred_at="2026-07-11T10:00:00Z",
        )

    def _bound_result(
        self,
        action,
        artifact: Path,
        name: str,
        facts: dict[str, object] | None = None,
    ) -> Path:
        digest = sha256_bytes(artifact.read_bytes())
        Path(f"{artifact}.sha256").write_text(f"{digest}\n", encoding="ascii")
        result = action.allowed_write_directory / name
        result.write_bytes(
            canonical_json_bytes(
                {
                    "schemaVersion": "rp001-autonomous-action-result.v1",
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "fromState": action.current_state,
                    "toState": "FREEZE_CYCLE_SPEC",
                    "status": "succeeded",
                    "artifactBindings": [
                        {
                            "path": artifact.relative_to(self.root).as_posix(),
                            "sha256": digest,
                        }
                    ],
                    "facts": facts or {},
                }
            )
        )
        return result

    def _spec_body(self) -> dict[str, object]:
        return {
            "schemaVersion": "rp001-autonomous-program-spec.v1",
            "programId": "RP-001-AUTO-PRESET-001",
            "goalSha256": hashlib.sha256(self.goal_source).hexdigest(),
            "objective": "Study direction-neutral market overheating.",
            "dataReleaseDirectory": "research-data/releases/RP-001",
            "requiredQuestionIds": ["RQ-001"],
            "allowedActions": [
                "VALIDATE_DATA_RELEASE",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                "RUN_SYNTHETIC_FALSIFICATION",
                "RUN_DEVELOPMENT_OOF",
                "DIAGNOSE_RESULT",
                "CREATE_FORMULA_VERSION",
                "FREEZE_CONFIRMATION",
                "RUN_CONFIRMATION_ONCE",
                "EVALUATE_ECONOMIC_RISK",
                "DECIDE_CYCLE",
            ],
            "searchBudget": {
                "initialFamiliesPerCycle": 3,
                "maximumEmpiricalCycles": 12,
                "maximumMechanismClasses": 8,
                "maximumTotalCandidateFamilies": 12,
                "maximumVersionsPerFamily": 5,
                "minimumEmpiricalCyclesBeforeExhaustion": 2,
                "minimumMechanismClasses": 4,
                "minimumTotalCandidateFamilies": 6,
                "maximumConfirmationUsesPerRelease": 1,
                "maximumStepsPerActivation": 8,
            },
            "terminalClaim": (
                "no_adoptable_formula_within_registered_search_space"
            ),
        }

class _FailingBootstrapLedger:
    def __init__(self, event_published: bool) -> None:
        self._event_published = event_published

    def require_empty(self) -> None:
        return None

    def append(self, event_type: str, payload: object, occurred_at: str) -> None:
        raise LocalLedgerAppendError(
            "synthetic bootstrap append failure",
            event_published=self._event_published,
        )


if __name__ == "__main__":
    unittest.main()
