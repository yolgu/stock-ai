"""Deterministic scientific workflow for one bounded ProgramVersion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class WorkflowError(ValueError):
    """Raised when a scientific Gate is skipped or misreported."""


class ProgramVersionState(str, Enum):
    PREREGISTER = "PREREGISTER"
    GENERATE_HYPOTHESES = "GENERATE_HYPOTHESES"
    DERIVE_FORMULA = "DERIVE_FORMULA"
    VERIFY_MATHEMATICS = "VERIFY_MATHEMATICS"
    IMPLEMENT_REFERENCE = "IMPLEMENT_REFERENCE"
    VERIFY_EQUIVALENCE = "VERIFY_EQUIVALENCE"
    DEVELOPMENT_OOF = "DEVELOPMENT_OOF"
    FALSIFICATION = "FALSIFICATION"
    FREEZE_CANDIDATE = "FREEZE_CANDIDATE"
    AWAITING_CONFIRMATION_RELEASE = "AWAITING_CONFIRMATION_RELEASE"
    CONFIRM_ONCE = "CONFIRM_ONCE"
    ECONOMIC_RISK = "ECONOMIC_RISK"
    INDEPENDENT_REPRODUCTION = "INDEPENDENT_REPRODUCTION"
    ADVERSARIAL_REVIEW = "ADVERSARIAL_REVIEW"
    INCREMENTAL_INTEGRATION = "INCREMENTAL_INTEGRATION"
    VERSION_DECISION = "VERSION_DECISION"
    VERSION_TERMINAL = "VERSION_TERMINAL"


@dataclass(frozen=True)
class ProgramVersionSnapshot:
    state: ProgramVersionState
    candidate_families_remaining: int
    formula_version_index: int
    maximum_formula_versions_per_family: int
    completed_empirical_cycles: int
    maximum_empirical_cycles: int
    failed_noncompensatory_gates: tuple[str, ...] = ()

    @classmethod
    def initial(
        cls,
        *,
        candidate_families_remaining: int,
        maximum_formula_versions_per_family: int,
        maximum_empirical_cycles: int = 12,
    ) -> "ProgramVersionSnapshot":
        if (
            type(candidate_families_remaining) is not int
            or candidate_families_remaining < 1
            or type(maximum_formula_versions_per_family) is not int
            or maximum_formula_versions_per_family < 1
            or type(maximum_empirical_cycles) is not int
            or maximum_empirical_cycles < 1
        ):
            raise WorkflowError("workflow_budget_invalid")
        return cls(
            state=ProgramVersionState.PREREGISTER,
            candidate_families_remaining=candidate_families_remaining,
            formula_version_index=1,
            maximum_formula_versions_per_family=(
                maximum_formula_versions_per_family
            ),
            completed_empirical_cycles=0,
            maximum_empirical_cycles=maximum_empirical_cycles,
            failed_noncompensatory_gates=(),
        )


_PASS_TRANSITIONS = {
    ProgramVersionState.PREREGISTER: ProgramVersionState.GENERATE_HYPOTHESES,
    ProgramVersionState.GENERATE_HYPOTHESES: ProgramVersionState.DERIVE_FORMULA,
    ProgramVersionState.DERIVE_FORMULA: ProgramVersionState.VERIFY_MATHEMATICS,
    ProgramVersionState.VERIFY_MATHEMATICS: ProgramVersionState.IMPLEMENT_REFERENCE,
    ProgramVersionState.IMPLEMENT_REFERENCE: ProgramVersionState.VERIFY_EQUIVALENCE,
    ProgramVersionState.VERIFY_EQUIVALENCE: ProgramVersionState.DEVELOPMENT_OOF,
    ProgramVersionState.DEVELOPMENT_OOF: ProgramVersionState.FALSIFICATION,
    ProgramVersionState.FALSIFICATION: ProgramVersionState.FREEZE_CANDIDATE,
    ProgramVersionState.FREEZE_CANDIDATE: (
        ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
    ),
    ProgramVersionState.CONFIRM_ONCE: ProgramVersionState.ECONOMIC_RISK,
    ProgramVersionState.ECONOMIC_RISK: ProgramVersionState.INDEPENDENT_REPRODUCTION,
    ProgramVersionState.INDEPENDENT_REPRODUCTION: (
        ProgramVersionState.ADVERSARIAL_REVIEW
    ),
    ProgramVersionState.ADVERSARIAL_REVIEW: (
        ProgramVersionState.INCREMENTAL_INTEGRATION
    ),
    ProgramVersionState.INCREMENTAL_INTEGRATION: (
        ProgramVersionState.VERSION_DECISION
    ),
    ProgramVersionState.VERSION_DECISION: ProgramVersionState.VERSION_TERMINAL,
}


_NONCOMPENSATORY_GATES = frozenset(
    {
        ProgramVersionState.CONFIRM_ONCE,
        ProgramVersionState.ECONOMIC_RISK,
        ProgramVersionState.INDEPENDENT_REPRODUCTION,
        ProgramVersionState.ADVERSARIAL_REVIEW,
        ProgramVersionState.INCREMENTAL_INTEGRATION,
    }
)


class ProgramVersionWorkflow:
    def advance(
        self,
        snapshot: ProgramVersionSnapshot,
        *,
        outcome: str,
    ) -> ProgramVersionSnapshot:
        """Apply one registered outcome without allowing Gate skips."""
        if snapshot.state is ProgramVersionState.VERSION_TERMINAL:
            raise WorkflowError("program_version_terminal")
        if snapshot.state is ProgramVersionState.FALSIFICATION:
            return self._advance_falsification(snapshot, outcome)
        if snapshot.state in _NONCOMPENSATORY_GATES and outcome == "failed":
            return replace(
                snapshot,
                state=ProgramVersionState.VERSION_DECISION,
                failed_noncompensatory_gates=(
                    snapshot.failed_noncompensatory_gates
                    + (snapshot.state.value,)
                ),
            )
        if outcome != "passed":
            raise WorkflowError("workflow_outcome_invalid")
        next_state = _PASS_TRANSITIONS.get(snapshot.state)
        if next_state is None:
            raise WorkflowError("workflow_transition_invalid")
        return replace(
            snapshot,
            state=next_state,
            completed_empirical_cycles=(
                snapshot.completed_empirical_cycles + 1
                if snapshot.state is ProgramVersionState.DEVELOPMENT_OOF
                else snapshot.completed_empirical_cycles
            ),
        )

    @staticmethod
    def release_confirmation(
        snapshot: ProgramVersionSnapshot,
    ) -> ProgramVersionSnapshot:
        if snapshot.state is not ProgramVersionState.AWAITING_CONFIRMATION_RELEASE:
            raise WorkflowError("confirmation_release_state_invalid")
        return replace(snapshot, state=ProgramVersionState.CONFIRM_ONCE)

    @staticmethod
    def _advance_falsification(
        snapshot: ProgramVersionSnapshot,
        outcome: str,
    ) -> ProgramVersionSnapshot:
        if outcome == "passed":
            return replace(snapshot, state=ProgramVersionState.FREEZE_CANDIDATE)
        if outcome == "repairable":
            if snapshot.completed_empirical_cycles >= snapshot.maximum_empirical_cycles:
                return replace(snapshot, state=ProgramVersionState.VERSION_DECISION)
            if (
                snapshot.formula_version_index
                >= snapshot.maximum_formula_versions_per_family
            ):
                raise WorkflowError("formula_version_budget_exhausted")
            return replace(
                snapshot,
                state=ProgramVersionState.DERIVE_FORMULA,
                formula_version_index=snapshot.formula_version_index + 1,
            )
        if outcome == "refuted":
            if (
                snapshot.candidate_families_remaining == 1
                or snapshot.completed_empirical_cycles
                >= snapshot.maximum_empirical_cycles
            ):
                return replace(snapshot, state=ProgramVersionState.VERSION_DECISION)
            return replace(
                snapshot,
                state=ProgramVersionState.GENERATE_HYPOTHESES,
                candidate_families_remaining=(
                    snapshot.candidate_families_remaining - 1
                ),
                formula_version_index=1,
            )
        raise WorkflowError("falsification_outcome_invalid")
