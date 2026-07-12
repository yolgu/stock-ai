from __future__ import annotations

import unittest

from rp001.autonomy_v2.scientific_validation import (
    ScientificEvidenceError,
    ScientificEvidenceValidator,
)


class ScientificEvidenceValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ScientificEvidenceValidator()

    def test_equivalence_is_recomputed_from_raw_pairs(self) -> None:
        receipt = self.validator.validate(
            "VERIFY_EQUIVALENCE",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "primaryExpression": "x",
                "implementationExpression": "x + 0.00000001",
                "inputRows": [{"x": 1.0}, {"x": 2.0}],
                "absoluteTolerance": 0.000001,
            },
        )

        self.assertEqual("formula_equivalence", receipt.validator_name)
        self.assertLess(receipt.metrics["maximumAbsoluteError"], 0.000001)

        with self.assertRaisesRegex(ScientificEvidenceError, "equivalence_failed"):
            self.validator.validate(
                "VERIFY_EQUIVALENCE",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "primaryExpression": "x",
                    "implementationExpression": "x + 0.1",
                    "inputRows": [{"x": 1.0}],
                    "absoluteTolerance": 0.000001,
                },
            )

    def test_preregistration_freezes_effect_temporal_and_risk_thresholds(self) -> None:
        receipt = self.validator.validate(
            "PREREGISTER",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "cycleSpec": {
                    "cycleId": "CYCLE-001",
                    "questionId": "RQ-PRED",
                    "estimand": "next-session direction accuracy",
                    "horizon": "one-session",
                    "universeId": "UNI-001",
                    "developmentReleaseId": "DEV-001",
                    "baselineIds": ["BASE-NAIVE", "BASE-LOGIT"],
                    "metricIds": ["ACCURACY"],
                    "minimumEffectDelta": 0.02,
                    "foldCount": 3,
                    "purgeSessions": 1,
                    "embargoSessions": 2,
                    "seed": 7,
                    "costModelId": "COST-001",
                    "multiplicityFamilyId": "FAMILY-001",
                    "confirmationPolicy": "one_shot_physical_release",
                },
                "cvarAlpha": 0.2,
                "maximumLossCvar": 0.02,
                "developmentAlpha": 0.05,
                "maximumRepairableFraction": 0.25,
                "nullAccuracy": 0.5,
                "numericTolerance": 0.000001,
            },
        )

        self.assertEqual(0.02, receipt.metrics["minimumEffectDelta"])
        self.assertEqual(2.0, receipt.metrics["embargoSessions"])

    def test_temporal_oof_rejects_overlap_and_missing_embargo(self) -> None:
        with self.assertRaisesRegex(ScientificEvidenceError, "temporal_oof_failed"):
            self.validator.validate(
                "DEVELOPMENT_OOF",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "embargoSessions": 2,
                    "correctPredictions": 18,
                    "totalPredictions": 20,
                    "nullAccuracy": 0.5,
                    "developmentAlpha": 0.05,
                    "folds": [
                        {
                            "trainStop": 10,
                            "validationStart": 11,
                            "validationStop": 20,
                        }
                    ],
                },
            )

    def test_confirmation_recomputes_exact_binomial_tail(self) -> None:
        receipt = self.validator.validate(
            "CONFIRM_ONCE",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "correctPredictions": 18,
                "totalPredictions": 20,
                "nullAccuracy": 0.5,
                "confirmationAlpha": 0.01,
            },
        )

        self.assertLess(receipt.metrics["exactBinomialPValue"], 0.01)

        with self.assertRaisesRegex(ScientificEvidenceError, "confirmation_failed"):
            self.validator.validate(
                "CONFIRM_ONCE",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "correctPredictions": 11,
                    "totalPredictions": 20,
                    "nullAccuracy": 0.5,
                    "confirmationAlpha": 0.01,
                },
            )

    def test_cost_and_tail_risk_are_recomputed_from_returns(self) -> None:
        receipt = self.validator.validate(
            "ECONOMIC_RISK",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "grossReturns": [0.04, 0.03, 0.02, -0.01, 0.01],
                "costs": [0.005, 0.005, 0.005, 0.005, 0.005],
                "cvarAlpha": 0.2,
                "maximumLossCvar": 0.02,
                "developmentAlpha": 0.05,
            },
        )

        self.assertGreater(receipt.metrics["meanNetReturn"], 0.0)
        self.assertLessEqual(receipt.metrics["lossCvar"], 0.02)

    def test_reproduction_requires_independent_output_identity(self) -> None:
        with self.assertRaisesRegex(ScientificEvidenceError, "reproduction_failed"):
            self.validator.validate(
                "INDEPENDENT_REPRODUCTION",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "primaryExpression": "x",
                    "reproductionExpression": "x + 0.1",
                    "inputRows": [{"x": 1.0}, {"x": 2.0}],
                    "absoluteTolerance": 0.000001,
                },
            )

    def test_incremental_improvement_is_recomputed(self) -> None:
        receipt = self.validator.validate(
            "INCREMENTAL_INTEGRATION",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "championMetric": 0.50,
                "challengerMetric": 0.53,
                "minimumEffectDelta": 0.02,
            },
        )

        self.assertAlmostEqual(0.03, receipt.metrics["improvement"])

        with self.assertRaisesRegex(
            ScientificEvidenceError,
            "incremental_integration_failed",
        ):
            self.validator.validate(
                "INCREMENTAL_INTEGRATION",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "championMetric": 0.50,
                    "challengerMetric": 0.51,
                    "minimumEffectDelta": 0.02,
                },
            )

    def test_formula_contract_rejects_mutating_multiple_axes(self) -> None:
        with self.assertRaisesRegex(ScientificEvidenceError, "formula_contract_invalid"):
            self.validator.validate(
                "DERIVE_FORMULA",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "formulaVersion": {
                        "formulaId": "FORMULA-002",
                        "parentFormulaId": "FORMULA-001",
                        "mechanismClass": "momentum",
                        "candidateFamily": "family-a",
                        "formulaExpression": "x + y",
                        "implementationPath": "impl/formula.py",
                        "implementationSha256": "a" * 64,
                        "inputFields": ["x", "y"],
                        "changedAxes": ["weight", "window"],
                        "missingPolicy": "abstain",
                        "oodPolicy": "abstain",
                        "availabilityRule": "available_at <= signal_at",
                    },
                },
            )

    def test_falsification_outcome_is_computed_from_stress_cases(self) -> None:
        receipt = self.validator.validate(
            "FALSIFICATION",
            {
                "schemaVersion": "quant-scientific-evidence.v2",
                "stressCases": [
                    {"expected": 1.0, "observed": 1.0, "tolerance": 0.01},
                    {"expected": 2.0, "observed": 2.2, "tolerance": 0.01},
                    {"expected": 3.0, "observed": 3.0, "tolerance": 0.01},
                    {"expected": 4.0, "observed": 4.0, "tolerance": 0.01},
                ],
                "maximumRepairableFraction": 0.25,
                "repairAxisCount": 1,
            },
        )

        self.assertEqual("repairable", receipt.outcome)
        self.assertEqual(1.0, receipt.metrics["violationCount"])

    def test_adversarial_review_rejects_unresolved_critical_finding(self) -> None:
        with self.assertRaisesRegex(ScientificEvidenceError, "adversarial_review_failed"):
            self.validator.validate(
                "ADVERSARIAL_REVIEW",
                {
                    "schemaVersion": "quant-scientific-evidence.v2",
                    "primaryImplementationDigest": "a" * 64,
                    "reviewerImplementationDigest": "b" * 64,
                    "findings": [
                        {
                            "findingId": "FINDING-001",
                            "severity": "critical",
                            "resolved": False,
                        }
                    ],
                },
            )

    def test_dataset_measurements_are_derived_from_formula_and_point_in_time_rows(self) -> None:
        records = [
            {
                "availableAt": index,
                "signalAt": index,
                "features": {"x": 1.0 if index % 2 == 0 else -1.0},
                "label": 1 if index % 2 == 0 else 0,
                "grossReturn": 0.02 if index % 2 == 0 else -0.02,
                "cost": 0.005,
            }
            for index in range(20)
        ]

        measurements = self.validator.measure_dataset(
            {
                "schemaVersion": "quant-research-dataset.v2",
                "baselineMetric": 0.5,
                "folds": [
                    {"trainStop": 5, "validationStart": 8, "validationStop": 12}
                ],
                "records": records,
            },
            formula_expression="x",
        )

        self.assertEqual(20, measurements.correct_predictions)
        self.assertEqual(20, measurements.total_predictions)
        self.assertTrue(all(value == 0.02 for value in measurements.gross_returns))


if __name__ == "__main__":
    unittest.main()
