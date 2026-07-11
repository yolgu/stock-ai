from __future__ import annotations

import unittest

from rp001.autonomy.scientific_contracts import (
    CycleSpec,
    FormulaVersion,
    ScientificContractError,
)


class ScientificCycleContractTest(unittest.TestCase):
    def test_accepts_complete_cycle_spec_with_two_baselines(self) -> None:
        spec = self._cycle_spec()

        self.assertEqual("CYCLE-001", spec.cycle_id)
        self.assertEqual(("B1", "B2"), spec.baseline_ids)
        self.assertEqual(0.005, spec.minimum_effect_delta)
        self.assertEqual(
            "one_shot_physical_release",
            spec.confirmation_policy,
        )
        self.assertEqual("FAMILY-CYCLE-001", spec.to_canonical_dict()["multiplicityFamilyId"])

    def test_rejects_cycle_without_two_baselines_or_positive_effect(self) -> None:
        cases = (
            {"baseline_ids": ("B1",)},
            {"minimum_effect_delta": 0.0},
            {"fold_count": 1},
            {"purge_sessions": -1},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                values = self._cycle_values()
                values.update(overrides)

                with self.assertRaises(ScientificContractError):
                    CycleSpec(**values)

    def test_accepts_one_axis_formula_successor(self) -> None:
        formula = FormulaVersion(
            formula_id="FORMULA-002",
            parent_formula_id="FORMULA-001",
            mechanism_class="duration",
            candidate_family="hsmm_duration",
            formula_expression="sigmoid(alpha + beta * duration_t)",
            implementation_path="research/runtime/formula_002.py",
            implementation_sha256="a" * 64,
            input_fields=("duration_t",),
            changed_axes=("duration_transform",),
            missing_policy="abstain",
            ood_policy="abstain",
            availability_rule="available_at <= signal_at",
        )

        self.assertEqual(("duration_transform",), formula.changed_axes)
        self.assertEqual("FORMULA-001", formula.parent_formula_id)

    def test_rejects_successor_that_changes_multiple_axes(self) -> None:
        with self.assertRaisesRegex(
            ScientificContractError,
            "formula_changed_axes_invalid",
        ):
            FormulaVersion(
                formula_id="FORMULA-002",
                parent_formula_id="FORMULA-001",
                mechanism_class="duration",
                candidate_family="hsmm_duration",
                formula_expression="sigmoid(alpha + beta * duration_t)",
                implementation_path="research/runtime/formula_002.py",
                implementation_sha256="a" * 64,
                input_fields=("duration_t", "volume_t"),
                changed_axes=("duration_transform", "volume_transform"),
                missing_policy="abstain",
                ood_policy="abstain",
                availability_rule="available_at <= signal_at",
            )

    def test_rejects_zero_fill_or_reweight_missing_policy(self) -> None:
        for missing_policy in ("zero_fill", "reweight_available_inputs"):
            with self.subTest(missing_policy=missing_policy):
                with self.assertRaisesRegex(
                    ScientificContractError,
                    "formula_missing_policy_invalid",
                ):
                    FormulaVersion(
                        formula_id="FORMULA-001",
                        parent_formula_id=None,
                        mechanism_class="duration",
                        candidate_family="hsmm_duration",
                        formula_expression="duration_t",
                        implementation_path="research/runtime/formula_001.py",
                        implementation_sha256="a" * 64,
                        input_fields=("duration_t",),
                        changed_axes=(),
                        missing_policy=missing_policy,
                        ood_policy="abstain",
                        availability_rule="available_at <= signal_at",
                    )

    def _cycle_spec(self) -> CycleSpec:
        return CycleSpec(**self._cycle_values())

    def _cycle_values(self) -> dict[str, object]:
        return {
            "cycle_id": "CYCLE-001",
            "question_id": "RQ-003",
            "estimand": "incremental_oof_brier_improvement",
            "horizon": "30m",
            "universe_id": "UNIVERSE-OVERHEATING-001",
            "development_release_id": "DEV-RELEASE-001",
            "baseline_ids": ("B1", "B2"),
            "metric_ids": ("brier", "log_loss", "calibration"),
            "minimum_effect_delta": 0.005,
            "fold_count": 3,
            "purge_sessions": 10,
            "embargo_sessions": 10,
            "seed": 20260711,
            "cost_model_id": "COST-STRESS-001",
            "multiplicity_family_id": "FAMILY-CYCLE-001",
        }


if __name__ == "__main__":
    unittest.main()
