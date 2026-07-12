from __future__ import annotations

import unittest

from rp001.autonomy_v2.workflow import (
    ProgramVersionSnapshot,
    ProgramVersionState,
    ProgramVersionWorkflow,
    WorkflowError,
)


class ProgramVersionWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = ProgramVersionWorkflow()

    def test_success_path_visits_every_scientific_gate_in_order(self) -> None:
        snapshot = ProgramVersionSnapshot.initial(
            candidate_families_remaining=3,
            maximum_formula_versions_per_family=5,
        )
        expected = (
            ProgramVersionState.PREREGISTER,
            ProgramVersionState.GENERATE_HYPOTHESES,
            ProgramVersionState.DERIVE_FORMULA,
            ProgramVersionState.VERIFY_MATHEMATICS,
            ProgramVersionState.IMPLEMENT_REFERENCE,
            ProgramVersionState.VERIFY_EQUIVALENCE,
            ProgramVersionState.DEVELOPMENT_OOF,
            ProgramVersionState.FALSIFICATION,
            ProgramVersionState.FREEZE_CANDIDATE,
            ProgramVersionState.AWAITING_CONFIRMATION_RELEASE,
            ProgramVersionState.CONFIRM_ONCE,
            ProgramVersionState.ECONOMIC_RISK,
            ProgramVersionState.INDEPENDENT_REPRODUCTION,
            ProgramVersionState.ADVERSARIAL_REVIEW,
            ProgramVersionState.INCREMENTAL_INTEGRATION,
            ProgramVersionState.VERSION_DECISION,
            ProgramVersionState.VERSION_TERMINAL,
        )

        visited = [snapshot.state]
        while snapshot.state is not ProgramVersionState.VERSION_TERMINAL:
            snapshot = (
                self.workflow.release_confirmation(snapshot)
                if snapshot.state
                is ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
                else self.workflow.advance(snapshot, outcome="passed")
            )
            visited.append(snapshot.state)

        self.assertEqual(expected, tuple(visited))

    def test_repairable_falsification_changes_one_version_and_rechecks_math(self) -> None:
        snapshot = self._at(ProgramVersionState.FALSIFICATION)

        repaired = self.workflow.advance(snapshot, outcome="repairable")

        self.assertEqual(ProgramVersionState.DERIVE_FORMULA, repaired.state)
        self.assertEqual(2, repaired.formula_version_index)

    def test_refuted_candidate_uses_registered_successor_not_model_boolean(self) -> None:
        snapshot = self._at(ProgramVersionState.FALSIFICATION)

        next_candidate = self.workflow.advance(snapshot, outcome="refuted")

        self.assertEqual(ProgramVersionState.GENERATE_HYPOTHESES, next_candidate.state)
        self.assertEqual(2, next_candidate.candidate_families_remaining)
        self.assertEqual(1, next_candidate.formula_version_index)

    def test_confirmation_failure_cannot_reach_economic_or_adoption_gate(self) -> None:
        snapshot = self._at(ProgramVersionState.CONFIRM_ONCE)

        failed = self.workflow.advance(snapshot, outcome="failed")

        self.assertEqual(ProgramVersionState.VERSION_DECISION, failed.state)
        with self.assertRaises(WorkflowError):
            self.workflow.advance(failed, outcome="promote")

    def test_empirical_cycle_budget_prevents_unbounded_successors(self) -> None:
        snapshot = ProgramVersionSnapshot.initial(
            candidate_families_remaining=20,
            maximum_formula_versions_per_family=5,
            maximum_empirical_cycles=1,
        )
        while snapshot.state is not ProgramVersionState.FALSIFICATION:
            snapshot = self.workflow.advance(snapshot, outcome="passed")

        exhausted = self.workflow.advance(snapshot, outcome="refuted")

        self.assertEqual(1, exhausted.completed_empirical_cycles)
        self.assertEqual(ProgramVersionState.VERSION_DECISION, exhausted.state)

    def _at(self, target: ProgramVersionState) -> ProgramVersionSnapshot:
        snapshot = ProgramVersionSnapshot.initial(
            candidate_families_remaining=3,
            maximum_formula_versions_per_family=5,
        )
        while snapshot.state is not target:
            snapshot = (
                self.workflow.release_confirmation(snapshot)
                if snapshot.state
                is ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
                else self.workflow.advance(snapshot, outcome="passed")
            )
        return snapshot


if __name__ == "__main__":
    unittest.main()
