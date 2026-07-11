"""Compile a Goal-bound mapping into an immutable program specification."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from rp001.autonomy.model import (
    ActionKind,
    BOUNDED_TERMINAL_CLAIM,
    PROGRAM_SPEC_SCHEMA_VERSION,
    ProgramSpec,
    REQUIRED_RESEARCH_ACTIONS,
    SearchBudget,
)


_PRESET_OBJECTIVE = (
    "Execute the supplied immutable Goal under bounded RP-001 autonomous "
    "research controls."
)
_PRESET_DATA_RELEASE_DIRECTORY = "research-data/releases/RP-001"
_PRESET_QUESTION_IDS = ("RQ-001", "RQ-002", "RQ-003", "RQ-004", "RQ-005")
_PRESET_SEARCH_BUDGET = SearchBudget(
    initial_families_per_cycle=3,
    maximum_versions_per_family=5,
    minimum_empirical_cycles_before_exhaustion=2,
    maximum_empirical_cycles=12,
    minimum_mechanism_classes=4,
    maximum_mechanism_classes=8,
    minimum_total_candidate_families=6,
    maximum_total_candidate_families=12,
    maximum_confirmation_uses_per_release=1,
    maximum_steps_per_activation=8,
)


class GoalContractError(ValueError):
    """Raised when a Goal cannot safely initialize a research program."""


_PROGRAM_FIELDS = frozenset(
    {
        "schemaVersion",
        "programId",
        "goalSha256",
        "objective",
        "dataReleaseDirectory",
        "requiredQuestionIds",
        "allowedActions",
        "searchBudget",
        "terminalClaim",
    }
)
_SEARCH_BUDGET_FIELDS = frozenset(
    {
        "initialFamiliesPerCycle",
        "maximumVersionsPerFamily",
        "minimumEmpiricalCyclesBeforeExhaustion",
        "maximumEmpiricalCycles",
        "minimumMechanismClasses",
        "maximumMechanismClasses",
        "minimumTotalCandidateFamilies",
        "maximumTotalCandidateFamilies",
        "maximumConfirmationUsesPerRelease",
        "maximumStepsPerActivation",
    }
)


def compile_program_spec(
    goal_source: bytes,
    value: Mapping[str, object],
) -> ProgramSpec:
    """Validate and bind one finite research program to its Goal bytes."""
    if set(value) != _PROGRAM_FIELDS:
        raise GoalContractError("program_spec_fields_invalid")
    expected_goal_sha256 = hashlib.sha256(goal_source).hexdigest()
    if value.get("goalSha256") != expected_goal_sha256:
        raise GoalContractError("goal_hash_mismatch")
    budget = _search_budget(value.get("searchBudget"))
    try:
        actions = tuple(ActionKind(item) for item in _text_list(value.get("allowedActions")))
        questions = _text_list(value.get("requiredQuestionIds"))
    except (TypeError, ValueError):
        raise GoalContractError("allowed_actions_invalid") from None
    try:
        return ProgramSpec(
            schema_version=_text(value.get("schemaVersion")),
            program_id=_text(value.get("programId")),
            goal_sha256=expected_goal_sha256,
            objective=_text(value.get("objective")),
            data_release_directory=_text(value.get("dataReleaseDirectory")),
            required_question_ids=questions,
            allowed_actions=actions,
            search_budget=budget,
            terminal_claim=_text(value.get("terminalClaim")),
        )
    except ValueError as error:
        raise GoalContractError(str(error)) from None


def compile_goal_document(goal_source: bytes) -> ProgramSpec:
    """Compile an unchanged, complete Goal with the frozen runtime preset."""
    try:
        goal_text = goal_source.decode("utf-8")
    except UnicodeDecodeError:
        raise GoalContractError("goal_source_invalid") from None
    if not goal_text.strip():
        raise GoalContractError("goal_source_invalid")
    goal_sha256 = hashlib.sha256(goal_source).hexdigest()
    return compile_program_spec(
        goal_source,
        {
            "schemaVersion": PROGRAM_SPEC_SCHEMA_VERSION,
            "programId": f"RP-001-AUTO-{goal_sha256[:20].upper()}",
            "goalSha256": goal_sha256,
            "objective": _PRESET_OBJECTIVE,
            "dataReleaseDirectory": _PRESET_DATA_RELEASE_DIRECTORY,
            "requiredQuestionIds": list(_PRESET_QUESTION_IDS),
            "allowedActions": [
                action.value
                for action in ActionKind
                if action in REQUIRED_RESEARCH_ACTIONS
            ],
            "searchBudget": _PRESET_SEARCH_BUDGET.to_canonical_dict(),
            "terminalClaim": BOUNDED_TERMINAL_CLAIM,
        },
    )


def _search_budget(value: object) -> SearchBudget:
    if not isinstance(value, Mapping) or set(value) != _SEARCH_BUDGET_FIELDS:
        raise GoalContractError("search_budget_invalid")
    try:
        return SearchBudget(
            initial_families_per_cycle=_integer(value["initialFamiliesPerCycle"]),
            maximum_versions_per_family=_integer(value["maximumVersionsPerFamily"]),
            minimum_empirical_cycles_before_exhaustion=_integer(
                value["minimumEmpiricalCyclesBeforeExhaustion"]
            ),
            maximum_empirical_cycles=_integer(value["maximumEmpiricalCycles"]),
            minimum_mechanism_classes=_integer(value["minimumMechanismClasses"]),
            maximum_mechanism_classes=_integer(value["maximumMechanismClasses"]),
            minimum_total_candidate_families=_integer(
                value["minimumTotalCandidateFamilies"]
            ),
            maximum_total_candidate_families=_integer(
                value["maximumTotalCandidateFamilies"]
            ),
            maximum_confirmation_uses_per_release=_integer(
                value["maximumConfirmationUsesPerRelease"]
            ),
            maximum_steps_per_activation=_integer(
                value["maximumStepsPerActivation"]
            ),
        )
    except (KeyError, TypeError, ValueError):
        raise GoalContractError("search_budget_invalid") from None


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("text_invalid")
    return value


def _text_list(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError("text_list_invalid")
    return tuple(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("integer_invalid")
    return value
