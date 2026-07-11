from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rp001.autonomy.controller import (
    ActionResultError,
    AutonomousResearchController,
    AutonomousResearchError,
)
from rp001.autonomy.goal_contract import compile_goal_document
from rp001.autonomy.policy import NextActionKind
from rp001.local_evidence import canonical_json_bytes, sha256_bytes


class AutonomousResearchEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.output_root = self.root / "research" / "rp-001" / "autonomy-runs"
        self.confirmation_root = self.root / "released-confirmation"
        self.confirmation_root.mkdir(parents=True)
        self.goal_source = (
            b"[GOAL-RP-001 v1.0]\n"
            b"Synthetic complete autonomous research Goal.\n"
        )
        self.program_root = (
            self.output_root
            / compile_goal_document(self.goal_source).program_id
        )
        self.controller = self._controller()
        self.clock = 0

    def test_goal_only_resume_and_hard_budget_bounded_terminal(self) -> None:
        self._bootstrap_goal()
        first_wait = self.controller.next_action(self.program_root)
        self.assertEqual(NextActionKind.WAIT_FOR_DATA_RELEASE, first_wait.kind)
        self.assertEqual(first_wait, self.controller.next_action(self.program_root))

        manifest = self.root / "research-data" / "development" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-E2E-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-E2E-001",
            role="development",
            manifest_path=manifest,
            occurred_at=self._occurred_at(),
        )
        validation_action = self.controller.next_action(self.program_root)
        self.assertEqual(
            "DEV-E2E-001",
            validation_action.input_bindings[-1]["bindingId"],
        )

        failed_result = self._result(
            validation_action,
            to_state="VALIDATE_MEASUREMENT",
            status="failed",
        )
        self.controller.validate_result(self.program_root, failed_result)
        restarted = self._controller()
        self.assertEqual(validation_action, restarted.next_action(self.program_root))
        restarted.commit_result(
            self.program_root,
            failed_result,
            occurred_at=self._occurred_at(),
        )
        with self.assertRaisesRegex(ActionResultError, "action_id_reused"):
            restarted.commit_result(
                self.program_root,
                failed_result,
                occurred_at=self._occurred_at(),
            )
        self.controller = restarted

        self._commit("FREEZE_CYCLE_SPEC")
        for index in range(12):
            self._complete_failed_cycle(index)
            if index < 11:
                self.assertEqual(
                    NextActionKind.START_NEXT_CYCLE,
                    self.controller.next_action(self.program_root).kind,
                )
                self._commit("FREEZE_CYCLE_SPEC")
        final_action = self.controller.next_action(self.program_root)
        self.assertEqual(NextActionKind.FINALIZE_PROGRAM_VERSION, final_action.kind)
        self._commit(
            "PROGRAM_VERSION_TERMINAL",
            {
                "terminalOutcome": (
                    "no_adoptable_formula_within_registered_search_space"
                )
            },
        )

        terminal = self.controller.verify(self.program_root)
        self.assertTrue(terminal.snapshot.program_terminal)
        self.assertEqual(12, terminal.snapshot.completed_cycle_count)
        self.assertEqual(
            {f"mechanism-{index}" for index in range(8)},
            set(terminal.snapshot.mechanism_classes),
        )
        self.assertEqual(
            {f"family-{index}" for index in range(12)},
            set(terminal.snapshot.candidate_families),
        )
        self.assertEqual(
            NextActionKind.NONE,
            self.controller.next_action(self.program_root).kind,
        )

    def test_ledger_body_tampering_is_detected_after_bootstrap(self) -> None:
        self._bootstrap_goal()
        event = self.program_root / "ledger" / "events" / "000001.json"
        source = event.read_bytes()
        event.write_bytes(source.replace(b"autonomy", b"Autonomy", 1))

        with self.assertRaises(AutonomousResearchError):
            self.controller.status(self.program_root)

    def test_confirmation_manifest_requires_frozen_physical_release_root(self) -> None:
        self._bootstrap_goal()
        development = self.root / "research-data" / "development" / "manifest.json"
        development.parent.mkdir(parents=True)
        development.write_bytes(canonical_json_bytes({"releaseId": "DEV-E2E-001"}))
        self.controller.register_data_release(
            self.program_root,
            release_id="DEV-E2E-001",
            role="development",
            manifest_path=development,
            occurred_at=self._occurred_at(),
        )
        self._commit("FREEZE_CYCLE_SPEC")
        self._commit("GENERATE_HYPOTHESIS", {"questionId": "RQ-001"})
        self._commit("IMPLEMENT_FORMULA", {"mechanismClass": "duration"})
        self._commit("SYNTHETIC_FALSIFICATION", {"candidateFamily": "duration-family"})
        self._commit("DEVELOPMENT_OOF")
        self._commit("FREEZE_CONFIRMATION")
        self._commit("AWAITING_DATA_RELEASE")
        request = self.controller.next_action(self.program_root).to_canonical_dict(
            self.root
        )["dataRequest"]
        self.assertEqual("confirmation", request["role"])
        self.assertEqual(1, request["maximumUses"])
        self.assertEqual(
            self.controller.status(
                self.program_root
            ).snapshot.frozen_formula_version_sha256,
            request["formulaVersionSha256"],
        )

        outside = self.root / "outside-confirmation.json"
        outside.write_bytes(canonical_json_bytes({"releaseId": "CONF-E2E-001"}))
        with self.assertRaises(AutonomousResearchError):
            self.controller.register_data_release(
                self.program_root,
                release_id="DEV-WRONG-ROLE-001",
                role="development",
                manifest_path=outside,
                occurred_at=self._occurred_at(),
            )
        with self.assertRaises(AutonomousResearchError):
            self.controller.register_data_release(
                self.program_root,
                release_id="CONF-E2E-001",
                role="confirmation",
                manifest_path=outside,
                occurred_at=self._occurred_at(),
            )

        released = self.confirmation_root / "manifest.json"
        released.write_bytes(canonical_json_bytes({"releaseId": "CONF-E2E-001"}))
        snapshot = self.controller.register_data_release(
            self.program_root,
            release_id="CONF-E2E-001",
            role="confirmation",
            manifest_path=released,
            occurred_at=self._occurred_at(),
        )

        self.assertEqual("CONFIRM_ONCE", snapshot.state.value)
        self.assertIn("CONF-E2E-001", snapshot.burned_confirmation_release_ids)
        self.assertEqual(
            snapshot.frozen_formula_version_sha256,
            snapshot.release_bindings[-1].formula_version_sha256,
        )

    def _complete_failed_cycle(self, index: int) -> None:
        question_index = min(index, 4) + 1
        mechanism_index = min(index, 7)
        self._commit(
            "GENERATE_HYPOTHESIS",
            {"questionId": f"RQ-{question_index:03d}"},
        )
        self._commit(
            "IMPLEMENT_FORMULA",
            {"mechanismClass": f"mechanism-{mechanism_index}"},
        )
        self._commit(
            "SYNTHETIC_FALSIFICATION",
            {"candidateFamily": f"family-{index}"},
        )
        self._commit("DEVELOPMENT_OOF")
        self._commit("DIAGNOSE_RESULT")
        self._commit("CYCLE_DECISION", {"successorAvailable": False})
        self._commit(
            "NEXT_CYCLE",
            {
                "cycleCompleted": True,
                "cycleStatus": "CycleTerminal",
                "questionTerminal": index < 5,
            },
        )

    def _commit(
        self,
        to_state: str,
        facts: dict[str, object] | None = None,
    ) -> None:
        action = self.controller.next_action(self.program_root)
        result = self._result(action, to_state=to_state, facts=facts)
        self.controller.validate_result(self.program_root, result)
        self.controller.commit_result(
            self.program_root,
            result,
            occurred_at=self._occurred_at(),
        )

    def _result(
        self,
        action,
        *,
        to_state: str,
        status: str = "succeeded",
        facts: dict[str, object] | None = None,
    ) -> Path:
        action.allowed_write_directory.mkdir(parents=True, exist_ok=True)
        artifact = action.allowed_write_directory / "evidence.json"
        artifact.write_bytes(
            canonical_json_bytes(
                {
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "status": status,
                }
            )
        )
        digest = sha256_bytes(artifact.read_bytes())
        Path(f"{artifact}.sha256").write_text(f"{digest}\n", encoding="ascii")
        result_facts = dict(facts or {})
        if action.kind is NextActionKind.FREEZE_CONFIRMATION:
            result_facts["formulaVersionSha256"] = digest
        result = action.allowed_write_directory / "action-result.json"
        result.write_bytes(
            canonical_json_bytes(
                {
                    "schemaVersion": "rp001-autonomous-action-result.v1",
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "fromState": action.current_state,
                    "toState": to_state,
                    "status": status,
                    "artifactBindings": [
                        {
                            "path": artifact.relative_to(self.root).as_posix(),
                            "sha256": digest,
                        }
                    ],
                    "facts": result_facts,
                }
            )
        )
        return result

    def _bootstrap_goal(self) -> None:
        goal = self.root / "goal.md"
        goal.write_bytes(self.goal_source)
        self.controller.bootstrap_goal(
            goal_path=goal,
            program_root=None,
            occurred_at=self._occurred_at(),
        )

    def _controller(self) -> AutonomousResearchController:
        return AutonomousResearchController(
            repository_root=self.root,
            preset_output_root=self.output_root,
            live_collection_roots=(self.root / ".storage" / "live-collection",),
            confirmation_release_root=self.confirmation_root,
        )

    def _occurred_at(self) -> str:
        hour = 13 + self.clock // 60
        minute = self.clock % 60
        value = f"2026-07-11T{hour:02d}:{minute:02d}:00Z"
        self.clock += 1
        return value


if __name__ == "__main__":
    unittest.main()
