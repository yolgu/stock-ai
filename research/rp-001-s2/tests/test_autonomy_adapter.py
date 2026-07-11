from __future__ import annotations

import unittest

from rp001_s2.autonomy_adapter import adapt_development_result


class S2AutonomyAdapterTest(unittest.TestCase):
    def test_failed_screen_enters_diagnosis_without_program_terminal(self) -> None:
        outcome = adapt_development_result(
            self._result(
                cycle_id="RP-001-S2-CYCLE-001",
                run_id="S2-EVAL-001",
                candidate_brier=0.19,
                development_gate="fail",
            )
        )

        self.assertEqual("ExperimentCompleted", outcome.event_type)
        self.assertEqual("DIAGNOSE_RESULT", outcome.controller_to_state)
        self.assertEqual("CycleTerminal", outcome.cycle_status)
        self.assertFalse(outcome.program_terminal)
        self.assertFalse(outcome.confirmation_authorized)
        self.assertTrue(outcome.successor_available)
        self.assertEqual(
            {
                "successorAvailable": True,
                "successorFamily": "candidate-family",
            },
            outcome.diagnosis_facts(),
        )
        self.assertEqual(
            {"candidateFamilies": ["candidate-family"]},
            outcome.formula_batch_facts(),
        )
        self.assertEqual(
            {"cycleCompleted": True, "cycleStatus": "CycleTerminal"},
            outcome.cycle_decision_facts(),
        )

    def test_passed_screen_enters_confirmation_freeze(self) -> None:
        outcome = adapt_development_result(
            self._result(
                cycle_id="RP-001-S2-CYCLE-002",
                run_id="S2-EVAL-002",
                candidate_brier=0.18,
                development_gate="pass",
            )
        )

        self.assertEqual("FREEZE_CONFIRMATION", outcome.controller_to_state)
        self.assertEqual("DevelopmentScreenPassed", outcome.cycle_status)
        self.assertFalse(outcome.program_terminal)
        self.assertTrue(outcome.confirmation_authorized)
        with self.assertRaisesRegex(ValueError, "cycle_not_terminal"):
            outcome.cycle_decision_facts()

    def test_multiple_failed_cycles_remain_cycle_terminal_only(self) -> None:
        outcomes = [
            adapt_development_result(
                self._result(
                    cycle_id=f"RP-001-S2-CYCLE-{index:03d}",
                    run_id=f"S2-EVAL-{index:03d}",
                    candidate_brier=0.21,
                    development_gate="fail",
                )
            )
            for index in range(1, 4)
        ]

        self.assertEqual(
            ["DIAGNOSE_RESULT", "DIAGNOSE_RESULT", "DIAGNOSE_RESULT"],
            [outcome.controller_to_state for outcome in outcomes],
        )
        self.assertEqual([False, False, False], [item.program_terminal for item in outcomes])

    @staticmethod
    def _result(
        *,
        cycle_id: str,
        run_id: str,
        candidate_brier: float,
        development_gate: str,
    ) -> dict[str, object]:
        passed = development_gate == "pass"
        family_id = "candidate-family"
        return {
            "cycleId": cycle_id,
            "runId": run_id,
            "passedFamilies": [family_id] if passed else [],
            "confirmationAuthorized": passed,
            "confirmationPriceVolumeOpened": False,
            "familyMetrics": [
                {
                    "familyId": family_id,
                    "candidateBrier": candidate_brier,
                    "baselineB1Brier": 0.20,
                    "baselineB2Brier": 0.21,
                    "developmentGate": development_gate,
                }
            ],
            "failureDiagnosis": [
                {
                    "familyId": family_id,
                    "status": development_gate,
                    "reasons": [] if passed else ["uncertainty"],
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()
