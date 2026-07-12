"""Deterministic validators that recompute scientific Gates from raw evidence."""

from __future__ import annotations

import math
import ast
from dataclasses import dataclass
from typing import Callable

from rp001.autonomy.scientific_contracts import (
    CycleSpec,
    FormulaVersion,
    ScientificContractError,
)


class ScientificEvidenceError(ValueError):
    """Raised when raw scientific evidence does not pass its frozen Gate."""


@dataclass(frozen=True)
class ScientificValidationReceipt:
    validator_name: str
    metrics: dict[str, object]
    outcome: str = "passed"


@dataclass(frozen=True)
class DatasetMeasurements:
    correct_predictions: int
    total_predictions: int
    gross_returns: list[float]
    costs: list[float]
    input_rows: list[dict[str, float]]
    folds: list[dict[str, int]]
    baseline_metric: float


class ScientificEvidenceValidator:
    _VALIDATOR_NAMES = {
        "PREREGISTER": "preregistration_contract",
        "DERIVE_FORMULA": "formula_contract",
        "FALSIFICATION": "falsification_suite",
        "ADVERSARIAL_REVIEW": "adversarial_review",
        "VERIFY_MATHEMATICS": "mathematical_validity",
        "VERIFY_EQUIVALENCE": "formula_equivalence",
        "DEVELOPMENT_OOF": "temporal_oof",
        "CONFIRM_ONCE": "sealed_confirmation",
        "ECONOMIC_RISK": "economic_tail_risk",
        "INDEPENDENT_REPRODUCTION": "independent_reproduction",
        "INCREMENTAL_INTEGRATION": "incremental_integration",
    }

    def supports(self, action_kind: str) -> bool:
        return action_kind in self._VALIDATOR_NAMES

    def validator_name(self, action_kind: str) -> str:
        try:
            return self._VALIDATOR_NAMES[action_kind]
        except KeyError:
            raise ScientificEvidenceError("scientific_validator_unavailable") from None

    def measure_dataset(
        self,
        value: dict[str, object],
        *,
        formula_expression: str,
    ) -> DatasetMeasurements:
        if value.get("schemaVersion") != "quant-research-dataset.v2":
            raise ScientificEvidenceError("dataset_schema_invalid")
        records = value.get("records")
        folds = value.get("folds")
        baseline_metric = self._probability(value.get("baselineMetric"))
        if not isinstance(records, list) or len(records) < 20 or not isinstance(folds, list):
            raise ScientificEvidenceError("dataset_invalid")
        correct = 0
        gross_returns: list[float] = []
        costs: list[float] = []
        input_rows: list[dict[str, float]] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                "availableAt",
                "signalAt",
                "features",
                "label",
                "grossReturn",
                "cost",
            }:
                raise ScientificEvidenceError("dataset_invalid")
            available_at = record["availableAt"]
            signal_at = record["signalAt"]
            label = record["label"]
            if (
                type(available_at) is not int
                or type(signal_at) is not int
                or available_at > signal_at
                or type(label) is not int
                or label not in {0, 1}
                or not isinstance(record["features"], dict)
                or not record["features"]
            ):
                raise ScientificEvidenceError("dataset_invalid")
            features = {
                str(name): self._number(feature)
                for name, feature in record["features"].items()
            }
            score = self._evaluate_expression(formula_expression, features)
            predicted = 1 if score > 0.0 else 0
            correct += int(predicted == label)
            direction = 1.0 if score > 0.0 else -1.0
            gross_returns.append(direction * self._number(record["grossReturn"]))
            costs.append(self._number(record["cost"]))
            input_rows.append(features)
        normalized_folds: list[dict[str, int]] = []
        for fold in folds:
            if not isinstance(fold, dict) or set(fold) != {
                "trainStop",
                "validationStart",
                "validationStop",
            } or any(type(value) is not int for value in fold.values()):
                raise ScientificEvidenceError("dataset_invalid")
            normalized_folds.append(dict(fold))
        return DatasetMeasurements(
            correct_predictions=correct,
            total_predictions=len(records),
            gross_returns=gross_returns,
            costs=costs,
            input_rows=input_rows,
            folds=normalized_folds,
            baseline_metric=baseline_metric,
        )

    def adversarial_findings(
        self,
        *,
        primary_expression: str,
        implementation_expression: str,
        input_rows: list[dict[str, float]],
        tolerance: float,
    ) -> list[dict[str, object]]:
        feature_names = sorted({name for row in input_rows for name in row})
        findings: list[dict[str, object]] = []
        for magnitude in (-1_000_000.0, 0.0, 1_000_000.0):
            row = {name: magnitude for name in feature_names}
            try:
                primary = self._evaluate_expression(primary_expression, row)
                implementation = self._evaluate_independently(
                    implementation_expression,
                    row,
                )
            except ScientificEvidenceError:
                findings.append(
                    {
                        "findingId": f"EXTREME-{magnitude}",
                        "severity": "critical",
                        "resolved": False,
                    }
                )
                continue
            if abs(primary - implementation) > tolerance:
                findings.append(
                    {
                        "findingId": f"EQUIVALENCE-{magnitude}",
                        "severity": "critical",
                        "resolved": False,
                    }
                )
        return findings

    def falsification_cases(
        self,
        *,
        primary_expression: str,
        implementation_expression: str,
        input_rows: list[dict[str, float]],
        tolerance: float,
    ) -> list[dict[str, float]]:
        feature_names = sorted({name for row in input_rows for name in row})
        probe_rows = list(input_rows)
        probe_rows.extend(
            {name: magnitude for name in feature_names}
            for magnitude in (
                -1_000_000.0,
                -100_000.0,
                -10_000.0,
                -1_000.0,
                -100.0,
                -10.0,
                0.0,
                10.0,
                100.0,
                1_000.0,
                10_000.0,
                100_000.0,
                1_000_000.0,
            )
        )
        return [
            {
                "expected": self._evaluate_expression(primary_expression, row),
                "observed": self._evaluate_independently(
                    implementation_expression,
                    row,
                ),
                "tolerance": tolerance,
            }
            for row in probe_rows
        ]

    def validate(
        self,
        action_kind: str,
        evidence: dict[str, object],
    ) -> ScientificValidationReceipt:
        if evidence.get("schemaVersion") != "quant-scientific-evidence.v2":
            raise ScientificEvidenceError("scientific_evidence_schema_invalid")
        validators: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
            "PREREGISTER": self._validate_preregistration,
            "DERIVE_FORMULA": self._validate_formula_contract,
            "FALSIFICATION": self._validate_falsification,
            "ADVERSARIAL_REVIEW": self._validate_adversarial_review,
            "VERIFY_MATHEMATICS": self._validate_mathematical_validity,
            "VERIFY_EQUIVALENCE": self._validate_equivalence,
            "DEVELOPMENT_OOF": self._validate_temporal_oof,
            "CONFIRM_ONCE": self._validate_confirmation,
            "ECONOMIC_RISK": self._validate_economic_risk,
            "INDEPENDENT_REPRODUCTION": self._validate_reproduction,
            "INCREMENTAL_INTEGRATION": self._validate_incremental_integration,
        }
        validator = validators.get(action_kind)
        if validator is None:
            raise ScientificEvidenceError("scientific_validator_unavailable")
        metrics = validator(evidence)
        outcome = str(metrics.pop("computedOutcome", "passed"))
        return ScientificValidationReceipt(
            validator_name=self._VALIDATOR_NAMES[action_kind],
            metrics=metrics,
            outcome=outcome,
        )

    def _validate_formula_contract(
        self,
        evidence: dict[str, object],
    ) -> dict[str, object]:
        value = evidence.get("formulaVersion")
        if not isinstance(value, dict):
            raise ScientificEvidenceError("formula_contract_invalid")
        try:
            formula = FormulaVersion(
                formula_id=str(value["formulaId"]),
                parent_formula_id=(
                    str(value["parentFormulaId"])
                    if value["parentFormulaId"] is not None
                    else None
                ),
                mechanism_class=str(value["mechanismClass"]),
                candidate_family=str(value["candidateFamily"]),
                formula_expression=str(value["formulaExpression"]),
                implementation_path=str(value["implementationPath"]),
                implementation_sha256=str(value["implementationSha256"]),
                input_fields=tuple(value["inputFields"]),
                changed_axes=tuple(value["changedAxes"]),
                missing_policy=str(value["missingPolicy"]),
                ood_policy=str(value["oodPolicy"]),
                availability_rule=str(value["availabilityRule"]),
            )
        except (KeyError, TypeError, ScientificContractError):
            raise ScientificEvidenceError("formula_contract_invalid") from None
        if formula.to_canonical_dict() != value:
            raise ScientificEvidenceError("formula_contract_invalid")
        self._evaluate_expression(
            formula.formula_expression,
            {name: 1.0 for name in formula.input_fields},
        )
        return {
            "formulaId": formula.formula_id,
            "formulaExpression": formula.formula_expression,
            "implementationPath": formula.implementation_path,
            "implementationDigest": formula.implementation_sha256,
        }

    def _validate_preregistration(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        value = evidence.get("cycleSpec")
        if not isinstance(value, dict):
            raise ScientificEvidenceError("preregistration_invalid")
        try:
            spec = CycleSpec(
                cycle_id=str(value["cycleId"]),
                question_id=str(value["questionId"]),
                estimand=str(value["estimand"]),
                horizon=str(value["horizon"]),
                universe_id=str(value["universeId"]),
                development_release_id=str(value["developmentReleaseId"]),
                baseline_ids=tuple(value["baselineIds"]),
                metric_ids=tuple(value["metricIds"]),
                minimum_effect_delta=value["minimumEffectDelta"],
                fold_count=value["foldCount"],
                purge_sessions=value["purgeSessions"],
                embargo_sessions=value["embargoSessions"],
                seed=value["seed"],
                cost_model_id=str(value["costModelId"]),
                multiplicity_family_id=str(value["multiplicityFamilyId"]),
                confirmation_policy=str(value["confirmationPolicy"]),
            )
        except (KeyError, TypeError, ScientificContractError):
            raise ScientificEvidenceError("preregistration_invalid") from None
        if spec.to_canonical_dict() != value:
            raise ScientificEvidenceError("preregistration_invalid")
        cvar_alpha = self._probability(evidence.get("cvarAlpha"))
        maximum_loss_cvar = self._positive_number(evidence.get("maximumLossCvar"))
        development_alpha = self._probability(evidence.get("developmentAlpha"))
        maximum_repairable = self._probability(
            evidence.get("maximumRepairableFraction")
        )
        null_accuracy = self._probability(evidence.get("nullAccuracy"))
        numeric_tolerance = self._positive_number(evidence.get("numericTolerance"))
        return {
            "minimumEffectDelta": float(spec.minimum_effect_delta),
            "foldCount": float(spec.fold_count),
            "purgeSessions": float(spec.purge_sessions),
            "embargoSessions": float(spec.embargo_sessions),
            "cvarAlpha": cvar_alpha,
            "maximumLossCvar": maximum_loss_cvar,
            "developmentAlpha": development_alpha,
            "maximumRepairableFraction": maximum_repairable,
            "nullAccuracy": null_accuracy,
            "numericTolerance": numeric_tolerance,
        }

    def _validate_equivalence(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        rows = evidence.get("inputRows")
        primary_expression = evidence.get("primaryExpression")
        implementation_expression = evidence.get("implementationExpression")
        if (
            not isinstance(rows, list)
            or not rows
            or not isinstance(primary_expression, str)
            or not isinstance(implementation_expression, str)
        ):
            raise ScientificEvidenceError("equivalence_failed")
        pairs = [
            (
                self._evaluate_expression(primary_expression, self._variables(row)),
                self._evaluate_independently(
                    implementation_expression,
                    self._variables(row),
                ),
            )
            for row in rows
        ]
        tolerance = self._positive_number(evidence.get("absoluteTolerance"))
        maximum_error = max(abs(reference - candidate) for reference, candidate in pairs)
        if maximum_error > tolerance:
            raise ScientificEvidenceError("equivalence_failed")
        return {"maximumAbsoluteError": maximum_error, "absoluteTolerance": tolerance}

    def _validate_mathematical_validity(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        rows = evidence.get("inputRows")
        expression = evidence.get("formulaExpression")
        if not isinstance(rows, list) or not rows or not isinstance(expression, str):
            raise ScientificEvidenceError("mathematical_validity_failed")
        outputs = [
            self._evaluate_expression(expression, self._variables(row))
            for row in rows
        ]
        if max(outputs) == min(outputs):
            raise ScientificEvidenceError("mathematical_validity_failed")
        return {
            "minimumOutput": min(outputs),
            "maximumOutput": max(outputs),
            "evaluatedRowCount": float(len(outputs)),
        }

    def _validate_temporal_oof(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        embargo = evidence.get("embargoSessions")
        folds = evidence.get("folds")
        if type(embargo) is not int or embargo < 0 or not isinstance(folds, list) or not folds:
            raise ScientificEvidenceError("temporal_oof_failed")
        for fold in folds:
            if not isinstance(fold, dict):
                raise ScientificEvidenceError("temporal_oof_failed")
            train_stop = fold.get("trainStop")
            validation_start = fold.get("validationStart")
            validation_stop = fold.get("validationStop")
            if (
                type(train_stop) is not int
                or type(validation_start) is not int
                or type(validation_stop) is not int
                or train_stop + embargo >= validation_start
                or validation_start >= validation_stop
            ):
                raise ScientificEvidenceError("temporal_oof_failed")
        correct = evidence.get("correctPredictions")
        total = evidence.get("totalPredictions")
        null_accuracy = self._probability(evidence.get("nullAccuracy"))
        alpha = self._probability(evidence.get("developmentAlpha"))
        if type(correct) is not int or type(total) is not int or not 0 <= correct <= total or total < 1:
            raise ScientificEvidenceError("temporal_oof_failed")
        p_value = self._binomial_tail(correct, total, null_accuracy)
        if p_value > alpha:
            raise ScientificEvidenceError("development_oof_failed")
        return {
            "foldCount": float(len(folds)),
            "embargoSessions": float(embargo),
            "exactBinomialPValue": p_value,
            "developmentAlpha": alpha,
        }

    def _validate_confirmation(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        correct = evidence.get("correctPredictions")
        total = evidence.get("totalPredictions")
        null_accuracy = self._probability(evidence.get("nullAccuracy"))
        alpha = self._probability(evidence.get("confirmationAlpha"))
        if type(correct) is not int or type(total) is not int or not 0 <= correct <= total or total < 1:
            raise ScientificEvidenceError("confirmation_failed")
        p_value = self._binomial_tail(correct, total, null_accuracy)
        if p_value > alpha:
            raise ScientificEvidenceError("confirmation_failed")
        return {"exactBinomialPValue": p_value, "confirmationAlpha": alpha}

    @staticmethod
    def _binomial_tail(correct: int, total: int, null_accuracy: float) -> float:
        return sum(
            math.comb(total, successes)
            * null_accuracy**successes
            * (1.0 - null_accuracy) ** (total - successes)
            for successes in range(correct, total + 1)
        )

    def _validate_economic_risk(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        gross = self._numeric_vector(evidence.get("grossReturns"))
        costs = self._numeric_vector(evidence.get("costs"))
        cvar_alpha = self._probability(evidence.get("cvarAlpha"))
        maximum_loss_cvar = self._positive_number(evidence.get("maximumLossCvar"))
        if len(gross) != len(costs):
            raise ScientificEvidenceError("economic_risk_failed")
        net = [value - cost for value, cost in zip(gross, costs, strict=True)]
        mean_net = sum(net) / len(net)
        tail_count = max(1, math.ceil(len(net) * cvar_alpha))
        loss_cvar = -sum(sorted(net)[:tail_count]) / tail_count
        if mean_net <= 0.0 or loss_cvar > maximum_loss_cvar:
            raise ScientificEvidenceError("economic_risk_failed")
        return {"meanNetReturn": mean_net, "lossCvar": loss_cvar}

    def _validate_reproduction(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        primary_expression = evidence.get("primaryExpression")
        reproduction_expression = evidence.get("reproductionExpression")
        rows = evidence.get("inputRows")
        if (
            not isinstance(primary_expression, str)
            or not isinstance(reproduction_expression, str)
            or primary_expression.strip() == reproduction_expression.strip()
            or not isinstance(rows, list)
            or not rows
        ):
            raise ScientificEvidenceError("reproduction_failed")
        tolerance = self._positive_number(evidence.get("absoluteTolerance"))
        primary: list[float] = []
        reproduced: list[float] = []
        for row in rows:
            if not isinstance(row, dict) or not row:
                raise ScientificEvidenceError("reproduction_failed")
            variables = {str(name): self._number(value) for name, value in row.items()}
            primary.append(self._evaluate_expression(primary_expression, variables))
            reproduced.append(
                self._evaluate_independently(reproduction_expression, variables)
            )
        maximum_error = max(abs(left - right) for left, right in zip(primary, reproduced, strict=True))
        if maximum_error > tolerance:
            raise ScientificEvidenceError("reproduction_failed")
        return {"maximumAbsoluteError": maximum_error, "absoluteTolerance": tolerance}

    @classmethod
    def _evaluate_expression(
        cls,
        expression: str,
        variables: dict[str, float],
    ) -> float:
        try:
            root = ast.parse(expression, mode="eval")
            return cls._evaluate_node(root.body, variables)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
            raise ScientificEvidenceError("formula_expression_invalid") from None

    @classmethod
    def _evaluate_node(cls, node: ast.AST, variables: dict[str, float]) -> float:
        if isinstance(node, ast.Constant):
            return cls._number(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            return variables[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = cls._evaluate_node(node.operand, variables)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow),
        ):
            left = cls._evaluate_node(node.left, variables)
            right = cls._evaluate_node(node.right, variables)
            operations = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.Pow: lambda: left**right,
            }
            return cls._number(operations[type(node.op)]())
        raise ScientificEvidenceError("formula_expression_invalid")

    @classmethod
    def _evaluate_independently(
        cls,
        expression: str,
        variables: dict[str, float],
    ) -> float:
        """Evaluate through a postfix machine independent of the primary walker."""
        try:
            root = ast.parse(expression, mode="eval")
        except SyntaxError:
            raise ScientificEvidenceError("formula_expression_invalid") from None
        instructions: list[tuple[str, object]] = []
        cls._emit_postfix(root.body, instructions)
        stack: list[float] = []
        try:
            for opcode, operand in instructions:
                if opcode == "value":
                    stack.append(cls._number(operand))
                elif opcode == "variable":
                    stack.append(variables[str(operand)])
                elif opcode == "unary":
                    value = stack.pop()
                    stack.append(value if operand == "+" else -value)
                else:
                    right = stack.pop()
                    left = stack.pop()
                    operations = {
                        "+": lambda: left + right,
                        "-": lambda: left - right,
                        "*": lambda: left * right,
                        "/": lambda: left / right,
                        "**": lambda: left**right,
                    }
                    stack.append(cls._number(operations[str(operand)]()))
        except (KeyError, IndexError, ZeroDivisionError, OverflowError):
            raise ScientificEvidenceError("formula_expression_invalid") from None
        if len(stack) != 1:
            raise ScientificEvidenceError("formula_expression_invalid")
        return stack[0]

    @classmethod
    def _emit_postfix(
        cls,
        node: ast.AST,
        instructions: list[tuple[str, object]],
    ) -> None:
        if isinstance(node, ast.Constant):
            instructions.append(("value", node.value))
            return
        if isinstance(node, ast.Name):
            instructions.append(("variable", node.id))
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            cls._emit_postfix(node.operand, instructions)
            instructions.append(("unary", "+" if isinstance(node.op, ast.UAdd) else "-"))
            return
        if isinstance(node, ast.BinOp) and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow),
        ):
            cls._emit_postfix(node.left, instructions)
            cls._emit_postfix(node.right, instructions)
            symbols = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Div: "/",
                ast.Pow: "**",
            }
            instructions.append(("binary", symbols[type(node.op)]))
            return
        raise ScientificEvidenceError("formula_expression_invalid")

    def _validate_incremental_integration(
        self,
        evidence: dict[str, object],
    ) -> dict[str, float]:
        champion = self._number(evidence.get("championMetric"))
        challenger = self._number(evidence.get("challengerMetric"))
        minimum_effect_delta = self._positive_number(
            evidence.get("minimumEffectDelta")
        )
        improvement = challenger - champion
        if improvement < minimum_effect_delta:
            raise ScientificEvidenceError("incremental_integration_failed")
        return {
            "championMetric": champion,
            "challengerMetric": challenger,
            "improvement": improvement,
            "minimumEffectDelta": minimum_effect_delta,
        }

    def _validate_falsification(
        self,
        evidence: dict[str, object],
    ) -> dict[str, object]:
        cases = evidence.get("stressCases")
        maximum_repairable = self._probability(
            evidence.get("maximumRepairableFraction")
        )
        repair_axis_count = evidence.get("repairAxisCount")
        if not isinstance(cases, list) or not cases or type(repair_axis_count) is not int:
            raise ScientificEvidenceError("falsification_evidence_invalid")
        violations = 0
        for case in cases:
            if not isinstance(case, dict):
                raise ScientificEvidenceError("falsification_evidence_invalid")
            expected = self._number(case.get("expected"))
            observed = self._number(case.get("observed"))
            tolerance = self._positive_number(case.get("tolerance"))
            if abs(expected - observed) > tolerance:
                violations += 1
        violation_fraction = violations / len(cases)
        if violations == 0:
            outcome = "passed"
        elif violation_fraction <= maximum_repairable and repair_axis_count == 1:
            outcome = "repairable"
        else:
            outcome = "refuted"
        return {
            "computedOutcome": outcome,
            "caseCount": float(len(cases)),
            "violationCount": float(violations),
            "violationFraction": violation_fraction,
            "maximumRepairableFraction": maximum_repairable,
        }

    def _validate_adversarial_review(
        self,
        evidence: dict[str, object],
    ) -> dict[str, object]:
        primary_digest = evidence.get("primaryImplementationDigest")
        reviewer_digest = evidence.get("reviewerImplementationDigest")
        findings = evidence.get("findings")
        if (
            not isinstance(primary_digest, str)
            or not isinstance(reviewer_digest, str)
            or primary_digest == reviewer_digest
            or not isinstance(findings, list)
        ):
            raise ScientificEvidenceError("adversarial_review_invalid")
        unresolved_critical = 0
        for finding in findings:
            if (
                not isinstance(finding, dict)
                or set(finding) != {"findingId", "severity", "resolved"}
                or not isinstance(finding.get("findingId"), str)
                or finding.get("severity") not in {"critical", "important", "minor"}
                or type(finding.get("resolved")) is not bool
            ):
                raise ScientificEvidenceError("adversarial_review_invalid")
            if finding["severity"] == "critical" and finding["resolved"] is False:
                unresolved_critical += 1
        if unresolved_critical:
            raise ScientificEvidenceError("adversarial_review_failed")
        return {
            "findingCount": float(len(findings)),
            "unresolvedCriticalCount": 0.0,
        }

    @classmethod
    def _numeric_pairs(cls, value: object) -> list[tuple[float, float]]:
        if not isinstance(value, list) or not value:
            raise ScientificEvidenceError("equivalence_failed")
        pairs: list[tuple[float, float]] = []
        for pair in value:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ScientificEvidenceError("equivalence_failed")
            pairs.append((cls._number(pair[0]), cls._number(pair[1])))
        return pairs

    @classmethod
    def _variables(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict) or not value:
            raise ScientificEvidenceError("input_row_invalid")
        return {str(name): cls._number(item) for name, item in value.items()}

    @classmethod
    def _numeric_vector(cls, value: object) -> list[float]:
        if not isinstance(value, list) or not value:
            raise ScientificEvidenceError("numeric_vector_invalid")
        return [cls._number(item) for item in value]

    @staticmethod
    def _number(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ScientificEvidenceError("number_invalid")
        return float(value)

    @classmethod
    def _positive_number(cls, value: object) -> float:
        number = cls._number(value)
        if number <= 0.0:
            raise ScientificEvidenceError("positive_number_invalid")
        return number

    @classmethod
    def _probability(cls, value: object) -> float:
        number = cls._number(value)
        if not 0.0 < number < 1.0:
            raise ScientificEvidenceError("probability_invalid")
        return number
