from __future__ import annotations

import hashlib
import unittest

from rp001.autonomy_v2.campaign import (
    CampaignDecisionError,
    CampaignState,
    ChampionEvidence,
    compile_campaign_spec,
    decide_program_version,
)


class CampaignContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.goal_source = (
            b"[QUANT_RESEARCH_GOAL]\n"
            b"Develop a direction-neutral overheating formula.\n"
        )
        self.spec = compile_campaign_spec(self.goal_source)

    def test_campaign_identity_and_budgets_are_goal_bound(self) -> None:
        digest = hashlib.sha256(self.goal_source).hexdigest()

        self.assertEqual(f"QR-CAMPAIGN-{digest[:20].upper()}", self.spec.campaign_id)
        self.assertEqual(16, self.spec.maximum_program_versions)
        self.assertEqual(12, self.spec.maximum_cycles_per_version)
        self.assertEqual(1, self.spec.maximum_actions_per_goal_turn)
        self.assertEqual(0.5, self.spec.null_accuracy)
        self.assertEqual(0.02, self.spec.minimum_effect_delta)
        self.assertEqual(0.000001, self.spec.numeric_tolerance)
        self.assertAlmostEqual(0.025, self.spec.confirmation_alpha(1))
        self.assertLessEqual(
            sum(self.spec.confirmation_alpha(index) for index in range(1, 17)),
            self.spec.program_alpha,
        )

    def test_candidate_promotes_only_when_every_noncompensatory_gate_passes(self) -> None:
        passing = ChampionEvidence.passing(
            formula_sha256="a" * 64,
            improvement=0.02,
            minimum_effect_delta=0.01,
        )

        promoted = decide_program_version(self.spec, version_index=1, evidence=passing)

        self.assertTrue(promoted.promote)
        self.assertEqual(CampaignState.START_NEXT_PROGRAM_VERSION, promoted.next_state)

        for gate in ChampionEvidence.required_gate_names():
            with self.subTest(gate=gate):
                failed = passing.with_gate(gate, False)
                decision = decide_program_version(
                    self.spec,
                    version_index=1,
                    evidence=failed,
                )
                self.assertFalse(decision.promote)

    def test_high_improvement_cannot_compensate_for_failed_gate(self) -> None:
        evidence = ChampionEvidence.passing(
            formula_sha256="b" * 64,
            improvement=10.0,
            minimum_effect_delta=0.01,
        ).with_gate("temporal_integrity", False)

        decision = decide_program_version(self.spec, version_index=1, evidence=evidence)

        self.assertFalse(decision.promote)

    def test_campaign_terminates_only_at_registered_version_budget(self) -> None:
        evidence = ChampionEvidence.passing(
            formula_sha256="c" * 64,
            improvement=0.02,
            minimum_effect_delta=0.01,
        )

        terminal = decide_program_version(
            self.spec,
            version_index=16,
            evidence=evidence,
        )

        self.assertEqual(CampaignState.CAMPAIGN_TERMINAL, terminal.next_state)
        with self.assertRaises(CampaignDecisionError):
            decide_program_version(self.spec, version_index=17, evidence=evidence)

    def test_gate_values_must_be_real_booleans(self) -> None:
        body = ChampionEvidence.passing(
            formula_sha256="e" * 64,
            improvement=0.02,
            minimum_effect_delta=0.01,
        ).to_canonical_dict()
        body["gates"]["temporal_integrity"] = "pass"

        with self.assertRaises(CampaignDecisionError):
            ChampionEvidence.from_mapping(body)


if __name__ == "__main__":
    unittest.main()
