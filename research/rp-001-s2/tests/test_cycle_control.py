from __future__ import annotations

import unittest

from rp001_s2.cycle_control import decide_development_cycle


class DevelopmentCycleControlTest(unittest.TestCase):
    def test_all_failed_candidates_force_next_cycle_without_program_terminal(self) -> None:
        result = {
            "cycleId": "RP-001-S2-CYCLE-001",
            "runId": "S2-EVAL-20260711-001",
            "passedFamilies": [],
            "confirmationAuthorized": False,
            "confirmationPriceVolumeOpened": False,
            "familyMetrics": [
                {
                    "familyId": "worse",
                    "candidateBrier": 0.21,
                    "baselineB1Brier": 0.20,
                    "baselineB2Brier": 0.22,
                    "developmentGate": "fail",
                },
                {
                    "familyId": "weak_improvement",
                    "candidateBrier": 0.19,
                    "baselineB1Brier": 0.20,
                    "baselineB2Brier": 0.21,
                    "developmentGate": "fail",
                },
            ],
            "failureDiagnosis": [
                {"familyId": "worse", "status": "fail", "reasons": ["discrimination"]},
                {"familyId": "weak_improvement", "status": "fail", "reasons": ["uncertainty"]},
            ],
        }

        decision = decide_development_cycle(result)

        self.assertEqual("CycleTerminal", decision["cycleStatus"])
        self.assertEqual("NEXT_CYCLE", decision["nextState"])
        self.assertFalse(decision["programTerminal"])
        self.assertFalse(decision["confirmationAuthorized"])
        self.assertFalse(decision["confirmationPriceVolumeOpened"])
        self.assertEqual(
            ["reject_current_version", "repair_as_new_formula_version"],
            [item["disposition"] for item in decision["candidateDecisions"]],
        )

    def test_any_passing_candidate_transitions_to_confirmation_freeze(self) -> None:
        result = {
            "cycleId": "RP-001-S2-CYCLE-002",
            "runId": "S2-EVAL-20260711-002",
            "passedFamilies": ["passed"],
            "confirmationAuthorized": True,
            "confirmationPriceVolumeOpened": False,
            "familyMetrics": [
                {
                    "familyId": "passed",
                    "candidateBrier": 0.18,
                    "baselineB1Brier": 0.20,
                    "baselineB2Brier": 0.21,
                    "developmentGate": "pass",
                }
            ],
            "failureDiagnosis": [
                {"familyId": "passed", "status": "pass", "reasons": []}
            ],
        }

        decision = decide_development_cycle(result)

        self.assertEqual("DevelopmentScreenPassed", decision["cycleStatus"])
        self.assertEqual("FREEZE_CONFIRMATION", decision["nextState"])
        self.assertFalse(decision["programTerminal"])
        self.assertTrue(decision["confirmationAuthorized"])
        self.assertFalse(decision["confirmationPriceVolumeOpened"])
        self.assertEqual("retain_for_confirmation_freeze", decision["candidateDecisions"][0]["disposition"])

    def test_inconsistent_confirmation_or_family_evidence_is_rejected(self) -> None:
        result = {
            "cycleId": "RP-001-S2-CYCLE-001",
            "runId": "S2-EVAL-20260711-001",
            "passedFamilies": [],
            "confirmationAuthorized": True,
            "confirmationPriceVolumeOpened": False,
            "familyMetrics": [],
            "failureDiagnosis": [],
        }

        with self.assertRaisesRegex(ValueError, "development_result_inconsistent"):
            decide_development_cycle(result)


if __name__ == "__main__":
    unittest.main()
