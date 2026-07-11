"""Frozen scientific contracts for one autonomous research cycle."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ScientificContractError(ValueError):
    """Raised when a scientific contract leaves an unsafe degree of freedom."""


@dataclass(frozen=True)
class CycleSpec:
    cycle_id: str
    question_id: str
    estimand: str
    horizon: str
    universe_id: str
    development_release_id: str
    baseline_ids: tuple[str, ...]
    metric_ids: tuple[str, ...]
    minimum_effect_delta: float
    fold_count: int
    purge_sessions: int
    embargo_sessions: int
    seed: int
    cost_model_id: str
    multiplicity_family_id: str
    confirmation_policy: str = "one_shot_physical_release"

    def __post_init__(self) -> None:
        identifiers = (
            self.cycle_id,
            self.question_id,
            self.universe_id,
            self.development_release_id,
            self.cost_model_id,
            self.multiplicity_family_id,
        )
        if any(_IDENTIFIER.fullmatch(value) is None for value in identifiers):
            raise ScientificContractError("cycle_identifier_invalid")
        if not self.estimand or not self.horizon:
            raise ScientificContractError("cycle_estimand_invalid")
        if (
            len(self.baseline_ids) < 2
            or len(set(self.baseline_ids)) != len(self.baseline_ids)
            or any(_IDENTIFIER.fullmatch(value) is None for value in self.baseline_ids)
        ):
            raise ScientificContractError("cycle_baselines_invalid")
        if (
            not self.metric_ids
            or len(set(self.metric_ids)) != len(self.metric_ids)
            or any(_IDENTIFIER.fullmatch(value) is None for value in self.metric_ids)
        ):
            raise ScientificContractError("cycle_metrics_invalid")
        if (
            isinstance(self.minimum_effect_delta, bool)
            or not isinstance(self.minimum_effect_delta, (int, float))
            or not math.isfinite(float(self.minimum_effect_delta))
            or self.minimum_effect_delta <= 0.0
        ):
            raise ScientificContractError("cycle_minimum_effect_invalid")
        if type(self.fold_count) is not int or self.fold_count < 3:
            raise ScientificContractError("cycle_fold_count_invalid")
        if (
            type(self.purge_sessions) is not int
            or self.purge_sessions < 0
            or type(self.embargo_sessions) is not int
            or self.embargo_sessions < 0
        ):
            raise ScientificContractError("cycle_temporal_guard_invalid")
        if type(self.seed) is not int or self.seed < 0:
            raise ScientificContractError("cycle_seed_invalid")
        if self.confirmation_policy != "one_shot_physical_release":
            raise ScientificContractError("cycle_confirmation_policy_invalid")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "cycleId": self.cycle_id,
            "questionId": self.question_id,
            "estimand": self.estimand,
            "horizon": self.horizon,
            "universeId": self.universe_id,
            "developmentReleaseId": self.development_release_id,
            "baselineIds": list(self.baseline_ids),
            "metricIds": list(self.metric_ids),
            "minimumEffectDelta": self.minimum_effect_delta,
            "foldCount": self.fold_count,
            "purgeSessions": self.purge_sessions,
            "embargoSessions": self.embargo_sessions,
            "seed": self.seed,
            "costModelId": self.cost_model_id,
            "multiplicityFamilyId": self.multiplicity_family_id,
            "confirmationPolicy": self.confirmation_policy,
        }


@dataclass(frozen=True)
class FormulaVersion:
    formula_id: str
    parent_formula_id: str | None
    mechanism_class: str
    candidate_family: str
    formula_expression: str
    implementation_path: str
    implementation_sha256: str
    input_fields: tuple[str, ...]
    changed_axes: tuple[str, ...]
    missing_policy: str
    ood_policy: str
    availability_rule: str

    def __post_init__(self) -> None:
        identifiers = (
            self.formula_id,
            self.mechanism_class,
            self.candidate_family,
        )
        if any(_IDENTIFIER.fullmatch(value) is None for value in identifiers):
            raise ScientificContractError("formula_identifier_invalid")
        if (
            self.parent_formula_id is not None
            and _IDENTIFIER.fullmatch(self.parent_formula_id) is None
        ):
            raise ScientificContractError("formula_parent_invalid")
        if not self.formula_expression.strip():
            raise ScientificContractError("formula_expression_invalid")
        implementation_path = PurePosixPath(self.implementation_path)
        if (
            implementation_path.is_absolute()
            or not implementation_path.parts
            or ".." in implementation_path.parts
        ):
            raise ScientificContractError("formula_implementation_path_invalid")
        if _SHA256.fullmatch(self.implementation_sha256) is None:
            raise ScientificContractError("formula_implementation_hash_invalid")
        if (
            not self.input_fields
            or len(set(self.input_fields)) != len(self.input_fields)
            or any(_IDENTIFIER.fullmatch(value) is None for value in self.input_fields)
        ):
            raise ScientificContractError("formula_input_fields_invalid")
        if (
            len(set(self.changed_axes)) != len(self.changed_axes)
            or any(_IDENTIFIER.fullmatch(value) is None for value in self.changed_axes)
            or (self.parent_formula_id is None and self.changed_axes)
            or (self.parent_formula_id is not None and len(self.changed_axes) != 1)
        ):
            raise ScientificContractError("formula_changed_axes_invalid")
        if self.missing_policy != "abstain":
            raise ScientificContractError("formula_missing_policy_invalid")
        if self.ood_policy != "abstain":
            raise ScientificContractError("formula_ood_policy_invalid")
        if self.availability_rule != "available_at <= signal_at":
            raise ScientificContractError("formula_availability_rule_invalid")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "formulaId": self.formula_id,
            "parentFormulaId": self.parent_formula_id,
            "mechanismClass": self.mechanism_class,
            "candidateFamily": self.candidate_family,
            "formulaExpression": self.formula_expression,
            "implementationPath": self.implementation_path,
            "implementationSha256": self.implementation_sha256,
            "inputFields": list(self.input_fields),
            "changedAxes": list(self.changed_axes),
            "missingPolicy": self.missing_policy,
            "oodPolicy": self.ood_policy,
            "availabilityRule": self.availability_rule,
        }
