import json
import sys
import unittest
from pathlib import Path

import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = RESEARCH_DIRECTORY.parents[1]
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from formula_ledger import (  # noqa: E402
    PROOF_OBLIGATIONS,
    build_formula_ledger,
    load_formula_ledger,
    render_formula_ledger_markdown,
    validate_formula_ledger,
)
from formula_reference import (  # noqa: E402
    documented_chart_fomo,
    documented_chart_panic,
    documented_potential_ptp,
    production_profit_taking_actual,
    production_profit_taking_linear,
)
from validation import CandidateDefinition, CandidateRegistry  # noqa: E402


LEDGER_PATH = RESEARCH_DIRECTORY / "formula-ledger.json"
REPORT_PATH = (
    REPOSITORY_ROOT
    / "docs/codex/research/2026-07-10-formula-ledger-and-equivalence.md"
)


class FormulaLedgerContractTest(unittest.TestCase):
    def test_checked_in_ledger_is_canonical_complete_and_source_exhaustive(self) -> None:
        checked_in = load_formula_ledger(LEDGER_PATH)
        generated = build_formula_ledger()

        self.assertEqual(checked_in, generated)
        report = validate_formula_ledger(checked_in, REPOSITORY_ROOT)

        self.assertEqual(report.formula_count, 224)
        self.assertEqual(report.source_declaration_count, 172)
        self.assertEqual(report.excluded_source_declaration_count, 17)
        self.assertEqual(report.validation_error_count, 0)
        self.assertEqual(report.unclaimed_source_declaration_count, 0)
        self.assertEqual(report.invalid_source_locator_count, 0)
        self.assertEqual(report.missing_proof_obligation_count, 0)
        self.assertEqual(report.duplicate_formula_id_count, 0)
        self.assertEqual(
            set(checked_in["proofObligations"]),
            set(PROOF_OBLIGATIONS),
        )

    def test_every_formula_has_the_full_contract_and_ten_proof_verdicts(self) -> None:
        ledger = build_formula_ledger()
        required_fields = {
            "id",
            "version",
            "family",
            "name",
            "purpose",
            "predictionTarget",
            "inputs",
            "inputUnits",
            "observationFrequency",
            "lookback",
            "expression",
            "outputRange",
            "normalization",
            "missingPolicy",
            "weights",
            "thresholds",
            "sources",
            "mappings",
            "judgment",
            "proofs",
            "repair",
            "equivalence",
        }

        for formula in ledger["formulas"]:
            self.assertEqual(set(formula), required_fields, formula["id"])
            self.assertEqual(set(formula["proofs"]), set(PROOF_OBLIGATIONS), formula["id"])
            for obligation in PROOF_OBLIGATIONS:
                proof = formula["proofs"][obligation]
                self.assertIn("status", proof, f"{formula['id']}:{obligation}")
                self.assertTrue(proof.get("evidence"), f"{formula['id']}:{obligation}")
            self.assertGreater(len(formula["inputs"]), 0, formula["id"])
            self.assertEqual(set(formula["inputUnits"]), set(formula["inputs"]), formula["id"])
        serialized = json.dumps(ledger, ensure_ascii=False)
        self.assertNotIn("documented_inputs_unresolved", serialized)
        self.assertNotIn("TBD", serialized)
        self.assertNotIn("TODO", serialized)

    def test_documented_names_do_not_hide_repaired_daily_proxy_provenance(self) -> None:
        formulas = {formula["id"]: formula for formula in build_formula_ledger()["formulas"]}

        for formula_id in (
            "fomo.return_impulse.daily_proxy.v1",
            "fomo.return_acceleration.daily_proxy.v1",
            "panic.liquidity_proxy.daily_proxy.v1",
            "fomo.chart_fomo.documented_weights_daily_proxy.v1",
            "panic.chart_panic.documented_weights_daily_proxy.v1",
        ):
            formula = formulas[formula_id]
            self.assertIn(formula["judgment"], {"repairable", "proxy_only"})
            self.assertEqual(
                formula["equivalence"]["documentToReference"]["status"],
                "repaired_proxy",
            )
            self.assertNotEqual(formula["repair"]["before"], formula["repair"]["after"])

    def test_production_reward_hacking_counterexamples_are_machine_readable(self) -> None:
        formulas = {formula["id"]: formula for formula in build_formula_ledger()["formulas"]}
        hidden_floor = formulas["ptp.production.hidden_floor_score.v1"]
        future_leak = formulas["ptp.production.unbounded_asof_input.v1"]

        self.assertEqual(hidden_floor["judgment"], "reject")
        self.assertEqual(
            hidden_floor["equivalence"]["referenceToProduction"]["status"],
            "non_equivalent",
        )
        self.assertIn(
            "42",
            hidden_floor["equivalence"]["referenceToProduction"]["counterexample"],
        )
        self.assertIn(
            "65",
            hidden_floor["equivalence"]["referenceToProduction"]["counterexample"],
        )
        self.assertEqual(future_leak["proofs"]["causality"]["status"], "counterexample")
        self.assertIn("101.0000", future_leak["proofs"]["causality"]["counterexample"])
        self.assertIn("498.8066", future_leak["proofs"]["causality"]["counterexample"])

    def test_validator_rejects_a_missing_proof_and_an_unclaimed_document_formula(self) -> None:
        ledger = build_formula_ledger()
        mutated = json.loads(json.dumps(ledger))
        del mutated["formulas"][0]["proofs"][PROOF_OBLIGATIONS[0]]
        mutated["formulas"][1]["judgment"] = "looks_good"
        mutated["formulas"][1]["inputUnits"].pop(mutated["formulas"][1]["inputs"][0])
        mutated["sourceDeclarationExclusions"] = []

        report = validate_formula_ledger(mutated, REPOSITORY_ROOT)

        self.assertGreater(report.missing_proof_obligation_count, 0)
        self.assertGreater(report.unclaimed_source_declaration_count, 0)
        self.assertGreaterEqual(report.structural_error_count, 2)
        self.assertGreater(report.validation_error_count, 0)

    def test_checked_in_markdown_is_a_deterministic_ledger_projection(self) -> None:
        ledger = build_formula_ledger()
        expected = render_formula_ledger_markdown(
            ledger,
            validate_formula_ledger(ledger, REPOSITORY_ROOT),
        )

        self.assertEqual(REPORT_PATH.read_text(encoding="utf-8"), expected)
        self.assertIn("누락 수식 선언: 0", expected)
        self.assertIn("fomo.return_impulse.daily_proxy.v1", expected)
        self.assertIn("ptp.production.hidden_floor_score.v1", expected)


class FormulaReferenceCalculatorTest(unittest.TestCase):
    def test_reference_composites_match_the_registered_absolute_weights(self) -> None:
        self.assertEqual(
            documented_chart_fomo(
                return_impulse=0.8,
                return_acceleration=0.6,
                volume_surprise=0.7,
                range_chase=0.5,
                vwap_persistence=0.4,
                pullback_hold=0.9,
            ),
            65.0,
        )
        self.assertEqual(
            documented_chart_panic(
                down_move_impulse=0.9,
                volume_surprise=0.8,
                vwap_down_pressure=0.7,
                breakdown_cascade=0.6,
                liquidity_proxy=0.5,
            ),
            75.0,
        )
        self.assertEqual(
            documented_potential_ptp(
                profit_breadth=0.8,
                profit_gain_mass=0.6,
                vwap_extension=0.4,
            ),
            65.0,
        )

    def test_reference_exposes_the_hidden_production_floor(self) -> None:
        causes = {
            "profitBurden": 100.0,
            "realizedSellPressure": 3.0,
            "overheadSupplyPressure": 0.0,
            "liquidityImpactRisk": 56.0,
        }

        self.assertEqual(production_profit_taking_linear(causes), 42.0)
        self.assertEqual(production_profit_taking_actual(causes), 65.0)

    def test_independent_reference_matches_research_composite_arithmetic(self) -> None:
        candidates = [
            CandidateDefinition(
                identifier="fomo.documented",
                family="fomo",
                kind="composite",
                formula=None,
                weights={
                    "returnImpulse": 0.24,
                    "returnAccel": 0.16,
                    "volumeSurprise": 0.22,
                    "rangeChase": 0.16,
                    "vwapPersistenceProxy": 0.14,
                    "pullbackHold": 0.08,
                },
                primary_outcome="fomoContinuation",
                outcome_ids=("fomoContinuation",),
                applicable_horizons=(5,),
            ),
            CandidateDefinition(
                identifier="panic.documented",
                family="panic",
                kind="composite",
                formula=None,
                weights={
                    "downMoveImpulse": 0.30,
                    "volumeSurprise": 0.25,
                    "vwapDownPressure": 0.20,
                    "breakdownCascade": 0.15,
                    "liquidityProxy": 0.10,
                },
                primary_outcome="panicContinuation",
                outcome_ids=("panicContinuation",),
                applicable_horizons=(5,),
            ),
            CandidateDefinition(
                identifier="potentialPtp.documented",
                family="potentialPtp",
                kind="composite",
                formula=None,
                weights={
                    "profitBreadth": 0.45,
                    "profitGainMass": 0.35,
                    "vwapExtension": 0.20,
                },
                primary_outcome="profitTakingLike",
                outcome_ids=("profitTakingLike",),
                applicable_horizons=(5,),
            ),
        ]
        features = pd.DataFrame(
            {
                "returnImpulse": [0.8],
                "returnAccel": [0.6],
                "volumeSurprise": [0.7],
                "rangeChase": [0.5],
                "vwapPersistenceProxy": [0.4],
                "pullbackHold": [0.9],
                "downMoveImpulse": [0.9],
                "vwapDownPressure": [0.7],
                "breakdownCascade": [0.6],
                "liquidityProxy": [0.5],
                "profitBreadth": [0.8],
                "profitGainMass": [0.6],
                "vwapExtension": [0.4],
            }
        )

        scores = CandidateRegistry(candidates).score_all(features).iloc[0]

        self.assertAlmostEqual(
            scores["fomo.documented"],
            documented_chart_fomo(
                return_impulse=0.8,
                return_acceleration=0.6,
                volume_surprise=0.7,
                range_chase=0.5,
                vwap_persistence=0.4,
                pullback_hold=0.9,
            ),
        )
        self.assertAlmostEqual(
            scores["panic.documented"],
            documented_chart_panic(
                down_move_impulse=0.9,
                volume_surprise=0.7,
                vwap_down_pressure=0.7,
                breakdown_cascade=0.6,
                liquidity_proxy=0.5,
            ),
        )
        self.assertAlmostEqual(
            scores["potentialPtp.documented"],
            documented_potential_ptp(
                profit_breadth=0.8,
                profit_gain_mass=0.6,
                vwap_extension=0.4,
            ),
        )


if __name__ == "__main__":
    unittest.main()
