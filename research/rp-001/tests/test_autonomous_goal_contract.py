from __future__ import annotations

import hashlib
import unittest

from rp001.autonomy.goal_contract import (
    GoalContractError,
    compile_goal_document,
    compile_program_spec,
)


class AutonomousGoalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.goal_source = (
            b"[AUTONOMOUS_RESEARCH_GOAL]\n"
            b"Study direction-neutral market overheating.\n"
        )
        self.goal_sha256 = hashlib.sha256(self.goal_source).hexdigest()

    def test_compiles_goal_bound_finite_program_spec(self) -> None:
        spec = compile_program_spec(self.goal_source, self._valid_body())

        self.assertEqual("RP-001-AUTO-PRESET-001", spec.program_id)
        self.assertEqual(self.goal_sha256, spec.goal_sha256)
        self.assertEqual(
            "no_adoptable_formula_within_registered_search_space",
            spec.terminal_claim,
        )
        self.assertEqual(3, spec.search_budget.initial_families_per_cycle)
        self.assertEqual(5, spec.search_budget.maximum_versions_per_family)
        self.assertEqual(8, spec.search_budget.maximum_steps_per_activation)
        self.assertEqual(
            self._valid_body(),
            spec.to_canonical_dict(),
        )

    def test_rejects_goal_hash_that_does_not_bind_source(self) -> None:
        body = self._valid_body()
        body["goalSha256"] = "f" * 64

        with self.assertRaisesRegex(GoalContractError, "goal_hash_mismatch"):
            compile_program_spec(self.goal_source, body)

    def test_rejects_unbounded_or_incomplete_search_budget(self) -> None:
        cases = (
            ("missing", {"maximumStepsPerActivation": 8}),
            (
                "nonpositive",
                {
                    **self._valid_body()["searchBudget"],
                    "maximumVersionsPerFamily": 0,
                },
            ),
        )
        for case, search_budget in cases:
            with self.subTest(case=case):
                body = self._valid_body()
                body["searchBudget"] = search_budget

                with self.assertRaisesRegex(
                    GoalContractError,
                    "search_budget_invalid",
                ):
                    compile_program_spec(self.goal_source, body)

    def test_rejects_maximum_budget_below_required_coverage(self) -> None:
        body = self._valid_body()
        body["searchBudget"] = {
            **body["searchBudget"],
            "maximumMechanismClasses": 3,
        }

        with self.assertRaisesRegex(GoalContractError, "search_budget_invalid"):
            compile_program_spec(self.goal_source, body)

    def test_rejects_unscoped_terminal_claim(self) -> None:
        body = self._valid_body()
        body["terminalClaim"] = "no_formula_exists"

        with self.assertRaisesRegex(GoalContractError, "terminal_claim_invalid"):
            compile_program_spec(self.goal_source, body)

    def test_rejects_unknown_or_trading_action(self) -> None:
        for action in ("UNKNOWN", "PLACE_ORDER"):
            with self.subTest(action=action):
                body = self._valid_body()
                body["allowedActions"] = [action]

                with self.assertRaisesRegex(GoalContractError, "allowed_actions_invalid"):
                    compile_program_spec(self.goal_source, body)

    def test_rejects_program_missing_required_state_machine_action(self) -> None:
        body = self._valid_body()
        body["allowedActions"] = body["allowedActions"][:-1]

        with self.assertRaisesRegex(GoalContractError, "allowed_actions_invalid"):
            compile_program_spec(self.goal_source, body)

    def test_compiles_complete_plain_goal_with_frozen_runtime_preset(self) -> None:
        spec = compile_goal_document(self.goal_source)

        self.assertEqual(self.goal_sha256, spec.goal_sha256)
        self.assertEqual(
            f"RP-001-AUTO-{self.goal_sha256[:20].upper()}",
            spec.program_id,
        )
        self.assertEqual(
            ("RQ-001", "RQ-002", "RQ-003", "RQ-004", "RQ-005"),
            spec.required_question_ids,
        )
        self.assertEqual(12, spec.search_budget.maximum_total_candidate_families)

    def test_program_identity_is_stable_for_same_goal_and_changes_with_goal(self) -> None:
        first = compile_goal_document(self.goal_source)
        repeated = compile_goal_document(self.goal_source)
        changed = compile_goal_document(self.goal_source + b"\n")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first.goal_sha256, changed.goal_sha256)
        self.assertNotEqual(first.program_id, changed.program_id)

    def test_goal_document_rejects_empty_or_non_utf8_source(self) -> None:
        for source in (b"", b" \n\t", b"\xff"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(GoalContractError, "goal_source_invalid"):
                    compile_goal_document(source)

    def _valid_body(self) -> dict[str, object]:
        return {
            "schemaVersion": "rp001-autonomous-program-spec.v1",
            "programId": "RP-001-AUTO-PRESET-001",
            "goalSha256": self.goal_sha256,
            "objective": "Study direction-neutral market overheating.",
            "dataReleaseDirectory": "research-data/releases/RP-001",
            "requiredQuestionIds": ["RQ-001", "RQ-002"],
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


if __name__ == "__main__":
    unittest.main()
