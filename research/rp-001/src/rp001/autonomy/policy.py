"""Deterministic next-action policy for bounded autonomous research."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rp001.autonomy.model import ProgramSnapshot, ProgramSpec, ResearchState


class NextActionKind(str, Enum):
    REPAIR_P0 = "REPAIR_P0"
    WAIT_FOR_DATA_RELEASE = "WAIT_FOR_DATA_RELEASE"
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
    NONE = "NONE"


@dataclass(frozen=True)
class NextAction:
    kind: NextActionKind
    reason: str


_STATE_ACTIONS = {
    ResearchState.AWAITING_DATA_RELEASE: NextActionKind.WAIT_FOR_DATA_RELEASE,
    ResearchState.VALIDATE_MEASUREMENT: NextActionKind.VALIDATE_DATA_RELEASE,
    ResearchState.FREEZE_CYCLE_SPEC: NextActionKind.FREEZE_CYCLE_SPEC,
    ResearchState.GENERATE_HYPOTHESIS: NextActionKind.GENERATE_HYPOTHESIS,
    ResearchState.IMPLEMENT_FORMULA: NextActionKind.IMPLEMENT_FORMULA,
    ResearchState.SYNTHETIC_FALSIFICATION: (
        NextActionKind.RUN_SYNTHETIC_FALSIFICATION
    ),
    ResearchState.DEVELOPMENT_OOF: NextActionKind.RUN_DEVELOPMENT_OOF,
    ResearchState.DIAGNOSE_RESULT: NextActionKind.DIAGNOSE_RESULT,
    ResearchState.CREATE_NEXT_FORMULA_VERSION: (
        NextActionKind.CREATE_FORMULA_VERSION
    ),
    ResearchState.FREEZE_CONFIRMATION: NextActionKind.FREEZE_CONFIRMATION,
    ResearchState.CONFIRM_ONCE: NextActionKind.RUN_CONFIRMATION_ONCE,
    ResearchState.ECONOMIC_RISK_EVALUATION: (
        NextActionKind.EVALUATE_ECONOMIC_RISK
    ),
    ResearchState.CYCLE_DECISION: NextActionKind.DECIDE_CYCLE,
}


def decide_next_action(spec: ProgramSpec, snapshot: ProgramSnapshot) -> NextAction:
    """Choose the only permitted next action from verified state."""
    if snapshot.paused_by_user:
        return NextAction(NextActionKind.NONE, "paused_by_user")
    if snapshot.open_p0_blockers:
        blocker_id = sorted(snapshot.open_p0_blockers)[0]
        return NextAction(
            NextActionKind.REPAIR_P0,
            f"open_p0_blocker:{blocker_id}",
        )
    if snapshot.state is ResearchState.PROGRAM_VERSION_TERMINAL:
        return NextAction(NextActionKind.NONE, "program_version_terminal")
    if snapshot.state is ResearchState.NEXT_CYCLE:
        if (
            snapshot.adoptable_candidate_found
            and set(spec.required_question_ids) <= snapshot.completed_question_ids
        ):
            return NextAction(
                NextActionKind.FINALIZE_PROGRAM_VERSION,
                "adoptable_formula_confirmed",
            )
        if _hard_budget_exhausted(spec, snapshot) and not _minimum_coverage_met(
            spec,
            snapshot,
        ):
            return NextAction(
                NextActionKind.NONE,
                "registered_search_budget_exhausted_before_minimum_coverage",
            )
        if _bounded_search_exhausted(spec, snapshot):
            return NextAction(
                NextActionKind.FINALIZE_PROGRAM_VERSION,
                spec.terminal_claim,
            )
        return NextAction(NextActionKind.START_NEXT_CYCLE, "next_cycle_required")
    action = _STATE_ACTIONS[snapshot.state]
    return NextAction(action, f"state_requires_{action.value.lower()}")


def _bounded_search_exhausted(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
) -> bool:
    return (
        _minimum_coverage_met(spec, snapshot)
        and _hard_budget_exhausted(spec, snapshot)
    )


def _minimum_coverage_met(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
) -> bool:
    budget = spec.search_budget
    return (
        snapshot.completed_cycle_count
        >= budget.minimum_empirical_cycles_before_exhaustion
        and set(spec.required_question_ids) <= snapshot.completed_question_ids
        and len(snapshot.mechanism_classes) >= budget.minimum_mechanism_classes
        and len(snapshot.candidate_families)
        >= budget.minimum_total_candidate_families
    )


def _hard_budget_exhausted(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
) -> bool:
    budget = spec.search_budget
    return (
        snapshot.completed_cycle_count >= budget.maximum_empirical_cycles
        or len(snapshot.candidate_families)
        >= budget.maximum_total_candidate_families
    )
