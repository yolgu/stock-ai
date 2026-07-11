from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace

from rp001.autonomy.goal_contract import compile_program_spec
from rp001.autonomy.model import ProgramSnapshot, ResearchState
from rp001.autonomy.policy import NextActionKind, decide_next_action


class NextActionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        goal_source = b"bounded autonomous research goal"
        self.spec = compile_program_spec(
            goal_source,
            {
                "schemaVersion": "rp001-autonomous-program-spec.v1",
                "programId": "RP-001-AUTO-PRESET-001",
                "goalSha256": hashlib.sha256(goal_source).hexdigest(),
                "objective": "Study direction-neutral overheating.",
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
            },
        )

    def test_p0_repair_preempts_empirical_run(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.DEVELOPMENT_OOF,
            open_p0_blockers=frozenset({"P0-001"}),
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.REPAIR_P0, action.kind)
        self.assertEqual("open_p0_blocker:P0-001", action.reason)

    def test_runnable_empirical_state_forces_run_instead_of_planning(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.DEVELOPMENT_OOF,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.RUN_DEVELOPMENT_OOF, action.kind)
        self.assertNotEqual("PLAN_MORE", action.kind.value)

    def test_waits_only_when_data_release_is_required(self) -> None:
        action = decide_next_action(self.spec, ProgramSnapshot.initial())

        self.assertEqual(NextActionKind.WAIT_FOR_DATA_RELEASE, action.kind)

    def test_user_pause_preempts_all_runnable_work(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.DEVELOPMENT_OOF,
            paused_by_user=True,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.NONE, action.kind)
        self.assertEqual("paused_by_user", action.reason)

    def test_starts_next_cycle_until_registered_search_minimum_is_met(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=1,
            mechanism_classes=frozenset({"duration", "liquidity"}),
            candidate_families=frozenset({"f1", "f2", "f3"}),
            successor_available=False,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.START_NEXT_CYCLE, action.kind)

    def test_minimum_coverage_does_not_allow_subjective_early_terminal(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=2,
            mechanism_classes=frozenset({"m1", "m2", "m3", "m4"}),
            candidate_families=frozenset({"f1", "f2", "f3", "f4", "f5", "f6"}),
            completed_question_ids=frozenset({"RQ-001"}),
            successor_available=False,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.START_NEXT_CYCLE, action.kind)

    def test_finalizes_only_after_hard_budget_and_minimum_coverage(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=4,
            mechanism_classes=frozenset({"m1", "m2", "m3", "m4"}),
            candidate_families=frozenset(f"f{index}" for index in range(12)),
            completed_question_ids=frozenset({"RQ-001"}),
            successor_available=False,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.FINALIZE_PROGRAM_VERSION, action.kind)
        self.assertEqual(
            "no_adoptable_formula_within_registered_search_space",
            action.reason,
        )

    def test_confirmed_candidate_finalizes_without_exhausting_failure_budget(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=1,
            adoptable_candidate_found=True,
            completed_question_ids=frozenset({"RQ-001"}),
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.FINALIZE_PROGRAM_VERSION, action.kind)
        self.assertEqual("adoptable_formula_confirmed", action.reason)

    def test_hard_budget_without_minimum_coverage_stops_without_false_terminal(self) -> None:
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=12,
            mechanism_classes=frozenset({"m1", "m2", "m3"}),
            candidate_families=frozenset(f"f{index}" for index in range(12)),
            successor_available=False,
        )

        action = decide_next_action(self.spec, snapshot)

        self.assertEqual(NextActionKind.NONE, action.kind)
        self.assertEqual(
            "registered_search_budget_exhausted_before_minimum_coverage",
            action.reason,
        )

    def test_incomplete_registered_question_prevents_false_terminal(self) -> None:
        spec = replace(
            self.spec,
            required_question_ids=("RQ-001", "RQ-002"),
        )
        snapshot = replace(
            ProgramSnapshot.initial(),
            state=ResearchState.NEXT_CYCLE,
            completed_cycle_count=2,
            mechanism_classes=frozenset({"m1", "m2", "m3", "m4"}),
            candidate_families=frozenset({"f1", "f2", "f3", "f4", "f5", "f6"}),
            completed_question_ids=frozenset({"RQ-001"}),
            successor_available=False,
        )

        action = decide_next_action(spec, snapshot)

        self.assertEqual(NextActionKind.START_NEXT_CYCLE, action.kind)


if __name__ == "__main__":
    unittest.main()
