"""Goal-driven autonomous research runtime for RP-001."""

from rp001.autonomy.goal_contract import (
    GoalContractError,
    compile_goal_document,
    compile_program_spec,
)
from rp001.autonomy.model import (
    ActionKind,
    DataReleaseBinding,
    ProgramSpec,
    ResearchState,
    SearchBudget,
)

__all__ = (
    "ActionKind",
    "DataReleaseBinding",
    "GoalContractError",
    "ProgramSpec",
    "ResearchState",
    "SearchBudget",
    "compile_goal_document",
    "compile_program_spec",
)
