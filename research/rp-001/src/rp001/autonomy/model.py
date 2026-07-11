"""Domain objects for bounded autonomous research programs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


PROGRAM_SPEC_SCHEMA_VERSION = "rp001-autonomous-program-spec.v1"
BOUNDED_TERMINAL_CLAIM = (
    "no_adoptable_formula_within_registered_search_space"
)

_PROGRAM_ID = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
_QUESTION_ID = re.compile(r"^RQ-[0-9]{3}$")


class ResearchState(str, Enum):
    AWAITING_DATA_RELEASE = "AWAITING_DATA_RELEASE"
    VALIDATE_MEASUREMENT = "VALIDATE_MEASUREMENT"
    FREEZE_CYCLE_SPEC = "FREEZE_CYCLE_SPEC"
    GENERATE_HYPOTHESIS = "GENERATE_HYPOTHESIS"
    IMPLEMENT_FORMULA = "IMPLEMENT_FORMULA"
    SYNTHETIC_FALSIFICATION = "SYNTHETIC_FALSIFICATION"
    DEVELOPMENT_OOF = "DEVELOPMENT_OOF"
    DIAGNOSE_RESULT = "DIAGNOSE_RESULT"
    CREATE_NEXT_FORMULA_VERSION = "CREATE_NEXT_FORMULA_VERSION"
    FREEZE_CONFIRMATION = "FREEZE_CONFIRMATION"
    CONFIRM_ONCE = "CONFIRM_ONCE"
    ECONOMIC_RISK_EVALUATION = "ECONOMIC_RISK_EVALUATION"
    CYCLE_DECISION = "CYCLE_DECISION"
    NEXT_CYCLE = "NEXT_CYCLE"
    PROGRAM_VERSION_TERMINAL = "PROGRAM_VERSION_TERMINAL"


class ActionKind(str, Enum):
    REPAIR_P0 = "REPAIR_P0"
    VALIDATE_DATA_RELEASE = "VALIDATE_DATA_RELEASE"
    FREEZE_CYCLE_SPEC = "FREEZE_CYCLE_SPEC"
    GENERATE_HYPOTHESIS = "GENERATE_HYPOTHESIS"
    IMPLEMENT_FORMULA = "IMPLEMENT_FORMULA"
    RUN_SYNTHETIC_FALSIFICATION = "RUN_SYNTHETIC_FALSIFICATION"
    RUN_DEVELOPMENT_OOF = "RUN_DEVELOPMENT_OOF"
    DIAGNOSE_RESULT = "DIAGNOSE_RESULT"
    CREATE_FORMULA_VERSION = "CREATE_FORMULA_VERSION"
    FREEZE_CONFIRMATION = "FREEZE_CONFIRMATION"
    RUN_CONFIRMATION_ONCE = "RUN_CONFIRMATION_ONCE"
    EVALUATE_ECONOMIC_RISK = "EVALUATE_ECONOMIC_RISK"
    DECIDE_CYCLE = "DECIDE_CYCLE"
    START_NEXT_CYCLE = "START_NEXT_CYCLE"
    FINALIZE_PROGRAM_VERSION = "FINALIZE_PROGRAM_VERSION"


REQUIRED_RESEARCH_ACTIONS = frozenset(
    {
        ActionKind.VALIDATE_DATA_RELEASE,
        ActionKind.FREEZE_CYCLE_SPEC,
        ActionKind.GENERATE_HYPOTHESIS,
        ActionKind.IMPLEMENT_FORMULA,
        ActionKind.RUN_SYNTHETIC_FALSIFICATION,
        ActionKind.RUN_DEVELOPMENT_OOF,
        ActionKind.DIAGNOSE_RESULT,
        ActionKind.CREATE_FORMULA_VERSION,
        ActionKind.FREEZE_CONFIRMATION,
        ActionKind.RUN_CONFIRMATION_ONCE,
        ActionKind.EVALUATE_ECONOMIC_RISK,
        ActionKind.DECIDE_CYCLE,
    }
)


@dataclass(frozen=True)
class DataReleaseBinding:
    release_id: str
    role: str
    manifest_path: str
    manifest_sha256: str
    formula_version_sha256: str | None = None

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "releaseId": self.release_id,
            "role": self.role,
            "manifestPath": self.manifest_path,
            "manifestSha256": self.manifest_sha256,
            "formulaVersionSha256": self.formula_version_sha256,
        }


@dataclass(frozen=True)
class SearchBudget:
    initial_families_per_cycle: int
    maximum_versions_per_family: int
    minimum_empirical_cycles_before_exhaustion: int
    maximum_empirical_cycles: int
    minimum_mechanism_classes: int
    maximum_mechanism_classes: int
    minimum_total_candidate_families: int
    maximum_total_candidate_families: int
    maximum_confirmation_uses_per_release: int
    maximum_steps_per_activation: int

    def __post_init__(self) -> None:
        values = (
            self.initial_families_per_cycle,
            self.maximum_versions_per_family,
            self.minimum_empirical_cycles_before_exhaustion,
            self.maximum_empirical_cycles,
            self.minimum_mechanism_classes,
            self.maximum_mechanism_classes,
            self.minimum_total_candidate_families,
            self.maximum_total_candidate_families,
            self.maximum_confirmation_uses_per_release,
            self.maximum_steps_per_activation,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("search_budget_invalid")
        if (
            self.minimum_empirical_cycles_before_exhaustion
            > self.maximum_empirical_cycles
            or self.minimum_mechanism_classes > self.maximum_mechanism_classes
            or self.minimum_total_candidate_families
            > self.maximum_total_candidate_families
            or self.minimum_mechanism_classes
            > self.minimum_total_candidate_families
            or self.maximum_mechanism_classes
            > self.maximum_total_candidate_families
            or self.initial_families_per_cycle
            > self.maximum_total_candidate_families
            or self.maximum_empirical_cycles * self.initial_families_per_cycle
            < self.maximum_total_candidate_families
            or self.maximum_confirmation_uses_per_release != 1
        ):
            raise ValueError("search_budget_invalid")

    def to_canonical_dict(self) -> dict[str, int]:
        return {
            "initialFamiliesPerCycle": self.initial_families_per_cycle,
            "maximumVersionsPerFamily": self.maximum_versions_per_family,
            "minimumEmpiricalCyclesBeforeExhaustion": (
                self.minimum_empirical_cycles_before_exhaustion
            ),
            "maximumEmpiricalCycles": self.maximum_empirical_cycles,
            "minimumMechanismClasses": self.minimum_mechanism_classes,
            "maximumMechanismClasses": self.maximum_mechanism_classes,
            "minimumTotalCandidateFamilies": self.minimum_total_candidate_families,
            "maximumTotalCandidateFamilies": self.maximum_total_candidate_families,
            "maximumConfirmationUsesPerRelease": (
                self.maximum_confirmation_uses_per_release
            ),
            "maximumStepsPerActivation": self.maximum_steps_per_activation,
        }


@dataclass(frozen=True)
class ProgramSpec:
    program_id: str
    goal_sha256: str
    objective: str
    data_release_directory: str
    required_question_ids: tuple[str, ...]
    allowed_actions: tuple[ActionKind, ...]
    search_budget: SearchBudget
    terminal_claim: str = BOUNDED_TERMINAL_CLAIM
    schema_version: str = PROGRAM_SPEC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _PROGRAM_ID.fullmatch(self.program_id):
            raise ValueError("program_id_invalid")
        if not self.objective.strip():
            raise ValueError("objective_invalid")
        path = PurePosixPath(self.data_release_directory)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError("data_release_directory_invalid")
        if (
            not self.required_question_ids
            or len(set(self.required_question_ids)) != len(self.required_question_ids)
            or any(
                _QUESTION_ID.fullmatch(value) is None
                for value in self.required_question_ids
            )
        ):
            raise ValueError("required_question_ids_invalid")
        if (
            not self.allowed_actions
            or len(set(self.allowed_actions)) != len(self.allowed_actions)
            or set(self.allowed_actions) != REQUIRED_RESEARCH_ACTIONS
        ):
            raise ValueError("allowed_actions_invalid")
        if self.terminal_claim != BOUNDED_TERMINAL_CLAIM:
            raise ValueError("terminal_claim_invalid")
        if self.schema_version != PROGRAM_SPEC_SCHEMA_VERSION:
            raise ValueError("schema_version_invalid")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "programId": self.program_id,
            "goalSha256": self.goal_sha256,
            "objective": self.objective,
            "dataReleaseDirectory": self.data_release_directory,
            "requiredQuestionIds": list(self.required_question_ids),
            "allowedActions": [value.value for value in self.allowed_actions],
            "searchBudget": self.search_budget.to_canonical_dict(),
            "terminalClaim": self.terminal_claim,
        }


@dataclass(frozen=True)
class ProgramSnapshot:
    state: ResearchState
    bootstrapped: bool
    program_id: str | None
    program_spec_sha256: str | None
    committed_action_ids: frozenset[str]
    registered_release_ids: frozenset[str]
    release_bindings: tuple[DataReleaseBinding, ...]
    burned_confirmation_release_ids: frozenset[str]
    burned_confirmation_manifest_sha256: frozenset[str]
    open_p0_blockers: frozenset[str]
    completed_cycle_count: int
    active_question_id: str | None
    completed_question_ids: frozenset[str]
    mechanism_classes: frozenset[str]
    candidate_families: frozenset[str]
    cycle_candidate_families: frozenset[str]
    formula_version_counts: tuple[tuple[str, int], ...]
    active_candidate_family: str | None
    successor_available: bool
    confirmation_frozen: bool
    frozen_formula_version_sha256: str | None
    confirmation_passed: bool
    economic_risk_passed: bool
    adoptable_candidate_found: bool
    paused_by_user: bool
    program_terminal: bool
    terminal_outcome: str | None

    @classmethod
    def initial(cls) -> "ProgramSnapshot":
        return cls(
            state=ResearchState.AWAITING_DATA_RELEASE,
            bootstrapped=False,
            program_id=None,
            program_spec_sha256=None,
            committed_action_ids=frozenset(),
            registered_release_ids=frozenset(),
            release_bindings=(),
            burned_confirmation_release_ids=frozenset(),
            burned_confirmation_manifest_sha256=frozenset(),
            open_p0_blockers=frozenset(),
            completed_cycle_count=0,
            active_question_id=None,
            completed_question_ids=frozenset(),
            mechanism_classes=frozenset(),
            candidate_families=frozenset(),
            cycle_candidate_families=frozenset(),
            formula_version_counts=(),
            active_candidate_family=None,
            successor_available=True,
            confirmation_frozen=False,
            frozen_formula_version_sha256=None,
            confirmation_passed=False,
            economic_risk_passed=False,
            adoptable_candidate_found=False,
            paused_by_user=False,
            program_terminal=False,
            terminal_outcome=None,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "bootstrapped": self.bootstrapped,
            "programId": self.program_id,
            "programSpecSha256": self.program_spec_sha256,
            "committedActionIds": sorted(self.committed_action_ids),
            "registeredReleaseIds": sorted(self.registered_release_ids),
            "releaseBindings": [
                binding.to_canonical_dict() for binding in self.release_bindings
            ],
            "burnedConfirmationReleaseIds": sorted(
                self.burned_confirmation_release_ids
            ),
            "burnedConfirmationManifestSha256": sorted(
                self.burned_confirmation_manifest_sha256
            ),
            "openP0Blockers": sorted(self.open_p0_blockers),
            "completedCycleCount": self.completed_cycle_count,
            "activeQuestionId": self.active_question_id,
            "completedQuestionIds": sorted(self.completed_question_ids),
            "mechanismClasses": sorted(self.mechanism_classes),
            "candidateFamilies": sorted(self.candidate_families),
            "cycleCandidateFamilies": sorted(self.cycle_candidate_families),
            "formulaVersionCounts": {
                family: count for family, count in self.formula_version_counts
            },
            "activeCandidateFamily": self.active_candidate_family,
            "successorAvailable": self.successor_available,
            "confirmationFrozen": self.confirmation_frozen,
            "frozenFormulaVersionSha256": self.frozen_formula_version_sha256,
            "confirmationPassed": self.confirmation_passed,
            "economicRiskPassed": self.economic_risk_passed,
            "adoptableCandidateFound": self.adoptable_candidate_found,
            "pausedByUser": self.paused_by_user,
            "programTerminal": self.program_terminal,
            "terminalOutcome": self.terminal_outcome,
        }
