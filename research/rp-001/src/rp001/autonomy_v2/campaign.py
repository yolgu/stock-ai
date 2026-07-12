"""Immutable contracts for bounded Champion-Challenger campaigns."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from enum import Enum

from rp001.autonomy.multiplicity import confirmation_wave_alpha


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CampaignDecisionError(ValueError):
    """Raised when a campaign decision violates its frozen budget."""


class CampaignState(str, Enum):
    INGESTED = "INGESTED"
    DEFINE_RESEARCH_QUESTION = "DEFINE_RESEARCH_QUESTION"
    REGISTER_DATA_CONTRACT = "REGISTER_DATA_CONTRACT"
    AWAITING_DEVELOPMENT_RELEASE = "AWAITING_DEVELOPMENT_RELEASE"
    START_PROGRAM_VERSION = "START_PROGRAM_VERSION"
    RUN_PROGRAM_VERSION = "RUN_PROGRAM_VERSION"
    EVALUATE_CHAMPION = "EVALUATE_CHAMPION"
    REGISTER_NEXT_FRONTIER = "REGISTER_NEXT_FRONTIER"
    START_NEXT_PROGRAM_VERSION = "START_NEXT_PROGRAM_VERSION"
    DIAGNOSE_STAGNATION = "DIAGNOSE_STAGNATION"
    CAMPAIGN_TERMINAL = "CAMPAIGN_TERMINAL"


@dataclass(frozen=True)
class ResearchCampaignSpec:
    campaign_id: str
    goal_sha256: str
    preset_version: str = "quant-formula-discovery.v2"
    maximum_program_versions: int = 16
    maximum_cycles_per_version: int = 12
    maximum_candidate_families_per_version: int = 12
    maximum_formula_versions_per_family: int = 5
    maximum_actions_per_goal_turn: int = 1
    program_alpha: float = 0.05
    minimum_effect_delta: float = 0.02
    development_alpha: float = 0.05
    null_accuracy: float = 0.5
    numeric_tolerance: float = 0.000001
    fold_count: int = 3
    purge_sessions: int = 1
    embargo_sessions: int = 2
    cvar_alpha: float = 0.2
    maximum_loss_cvar: float = 0.02
    maximum_repairable_fraction: float = 0.25

    def confirmation_alpha(self, version_index: int) -> float:
        if version_index > self.maximum_program_versions:
            raise CampaignDecisionError("program_version_budget_exhausted")
        return confirmation_wave_alpha(
            version_index,
            program_alpha=self.program_alpha,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": "quant-research-campaign-spec.v2",
            "campaignId": self.campaign_id,
            "goalSha256": self.goal_sha256,
            "presetVersion": self.preset_version,
            "maximumProgramVersions": self.maximum_program_versions,
            "maximumCyclesPerVersion": self.maximum_cycles_per_version,
            "maximumCandidateFamiliesPerVersion": (
                self.maximum_candidate_families_per_version
            ),
            "maximumFormulaVersionsPerFamily": (
                self.maximum_formula_versions_per_family
            ),
            "maximumActionsPerGoalTurn": self.maximum_actions_per_goal_turn,
            "programAlpha": self.program_alpha,
            "minimumEffectDelta": self.minimum_effect_delta,
            "developmentAlpha": self.development_alpha,
            "nullAccuracy": self.null_accuracy,
            "numericTolerance": self.numeric_tolerance,
            "foldCount": self.fold_count,
            "purgeSessions": self.purge_sessions,
            "embargoSessions": self.embargo_sessions,
            "cvarAlpha": self.cvar_alpha,
            "maximumLossCvar": self.maximum_loss_cvar,
            "maximumRepairableFraction": self.maximum_repairable_fraction,
        }


_REQUIRED_GATES = (
    "goal_boundary",
    "question_identifiability",
    "data_lineage",
    "preregistration",
    "mathematical_validity",
    "temporal_integrity",
    "development_oof",
    "external_confirmation",
    "economic_risk",
    "independent_reproduction",
    "adversarial_review",
    "incremental_integration",
)


@dataclass(frozen=True)
class ChampionEvidence:
    formula_sha256: str
    improvement: float
    minimum_effect_delta: float
    gates: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.formula_sha256) is None:
            raise CampaignDecisionError("formula_sha256_invalid")
        values = (self.improvement, self.minimum_effect_delta)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ) or self.minimum_effect_delta <= 0.0:
            raise CampaignDecisionError("effect_invalid")
        if (
            tuple(name for name, _passed in self.gates) != _REQUIRED_GATES
            or any(type(passed) is not bool for _name, passed in self.gates)
        ):
            raise CampaignDecisionError("gate_set_invalid")

    @classmethod
    def passing(
        cls,
        *,
        formula_sha256: str,
        improvement: float,
        minimum_effect_delta: float,
    ) -> "ChampionEvidence":
        return cls(
            formula_sha256=formula_sha256,
            improvement=improvement,
            minimum_effect_delta=minimum_effect_delta,
            gates=tuple((name, True) for name in _REQUIRED_GATES),
        )

    @staticmethod
    def required_gate_names() -> tuple[str, ...]:
        return _REQUIRED_GATES

    def with_gate(self, gate: str, passed: bool) -> "ChampionEvidence":
        if gate not in _REQUIRED_GATES or type(passed) is not bool:
            raise CampaignDecisionError("gate_invalid")
        return replace(
            self,
            gates=tuple(
                (name, passed if name == gate else value)
                for name, value in self.gates
            ),
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "formulaSha256": self.formula_sha256,
            "improvement": self.improvement,
            "minimumEffectDelta": self.minimum_effect_delta,
            "gates": {name: passed for name, passed in self.gates},
        }

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> "ChampionEvidence":
        gates = value.get("gates")
        if not isinstance(gates, dict):
            raise CampaignDecisionError("gate_set_invalid")
        try:
            return cls(
                formula_sha256=str(value["formulaSha256"]),
                improvement=float(value["improvement"]),
                minimum_effect_delta=float(value["minimumEffectDelta"]),
                gates=tuple((name, gates.get(name)) for name in _REQUIRED_GATES),
            )
        except (KeyError, TypeError, ValueError):
            raise CampaignDecisionError("champion_evidence_invalid") from None


@dataclass(frozen=True)
class ProgramVersionDecision:
    promote: bool
    next_state: CampaignState
    terminal_outcome: str | None


def compile_campaign_spec(goal_source: bytes) -> ResearchCampaignSpec:
    if not goal_source.strip():
        raise CampaignDecisionError("goal_source_invalid")
    digest = hashlib.sha256(goal_source).hexdigest()
    return ResearchCampaignSpec(
        campaign_id=f"QR-CAMPAIGN-{digest[:20].upper()}",
        goal_sha256=digest,
    )


def decide_program_version(
    spec: ResearchCampaignSpec,
    *,
    version_index: int,
    evidence: ChampionEvidence,
) -> ProgramVersionDecision:
    if type(version_index) is not int or not 1 <= version_index <= spec.maximum_program_versions:
        raise CampaignDecisionError("program_version_index_invalid")
    promote = (
        all(passed for _name, passed in evidence.gates)
        and evidence.improvement >= evidence.minimum_effect_delta
    )
    if version_index == spec.maximum_program_versions:
        outcome = (
            "champion_selected_within_registered_campaign"
            if promote
            else "no_adoptable_formula_within_registered_campaign"
        )
        return ProgramVersionDecision(
            promote=promote,
            next_state=CampaignState.CAMPAIGN_TERMINAL,
            terminal_outcome=outcome,
        )
    return ProgramVersionDecision(
        promote=promote,
        next_state=CampaignState.START_NEXT_PROGRAM_VERSION,
        terminal_outcome=None,
    )
