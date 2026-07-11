"""Read-only translation from S2 development results to autonomy state facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rp001_s2.cycle_control import decide_development_cycle


@dataclass(frozen=True)
class S2DevelopmentOutcome:
    """Validated S2 evidence expressed in controller-neutral domain language."""

    cycle_id: str
    development_run_id: str
    cycle_status: str
    controller_to_state: str
    program_terminal: bool
    confirmation_authorized: bool
    successor_available: bool | None
    candidate_decisions: tuple[Mapping[str, object], ...]
    event_type: str = "ExperimentCompleted"

    def experiment_facts(self) -> dict[str, object]:
        return {
            "cycleId": self.cycle_id,
            "developmentRunId": self.development_run_id,
            "cycleStatus": self.cycle_status,
            "programTerminal": self.program_terminal,
            "confirmationAuthorized": self.confirmation_authorized,
            "candidateDecisions": [dict(value) for value in self.candidate_decisions],
        }

    def diagnosis_facts(self) -> dict[str, object]:
        if self.controller_to_state != "DIAGNOSE_RESULT":
            raise ValueError("diagnosis_not_required")
        if self.successor_available is None:
            raise ValueError("successor_availability_missing")
        result: dict[str, object] = {
            "successorAvailable": self.successor_available
        }
        if self.successor_available:
            successor = next(
                value
                for value in self.candidate_decisions
                if value.get("disposition") == "repair_as_new_formula_version"
            )
            result["successorFamily"] = _required_text(successor, "familyId")
        return result

    def formula_batch_facts(self) -> dict[str, object]:
        return {
            "candidateFamilies": [
                _required_text(value, "familyId")
                for value in self.candidate_decisions
            ]
        }

    def cycle_decision_facts(self) -> dict[str, object]:
        if self.cycle_status != "CycleTerminal":
            raise ValueError("cycle_not_terminal")
        return {
            "cycleCompleted": True,
            "cycleStatus": self.cycle_status,
        }


def adapt_development_result(
    result: Mapping[str, object],
) -> S2DevelopmentOutcome:
    """Map an immutable S2 result without editing its source artifact."""
    decision = decide_development_cycle(result)
    cycle_status = _required_text(decision, "cycleStatus")
    confirmation_authorized = _required_bool(decision, "confirmationAuthorized")
    program_terminal = _required_bool(decision, "programTerminal")
    if program_terminal:
        raise ValueError("s2_program_terminal_forbidden")
    candidate_decisions = _mapping_sequence(decision.get("candidateDecisions"))
    if cycle_status == "DevelopmentScreenPassed":
        controller_to_state = "FREEZE_CONFIRMATION"
        successor_available: bool | None = None
    elif cycle_status == "CycleTerminal":
        controller_to_state = "DIAGNOSE_RESULT"
        successor_available = any(
            candidate.get("disposition") == "repair_as_new_formula_version"
            for candidate in candidate_decisions
        )
    else:
        raise ValueError("s2_cycle_status_invalid")
    return S2DevelopmentOutcome(
        cycle_id=_required_text(decision, "cycleId"),
        development_run_id=_required_text(decision, "developmentRunId"),
        cycle_status=cycle_status,
        controller_to_state=controller_to_state,
        program_terminal=program_terminal,
        confirmation_authorized=confirmation_authorized,
        successor_available=successor_available,
        candidate_decisions=candidate_decisions,
    )


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError("s2_autonomy_decision_invalid")
    return result


def _required_bool(value: Mapping[str, object], key: str) -> bool:
    result = value.get(key)
    if type(result) is not bool:
        raise ValueError("s2_autonomy_decision_invalid")
    return result


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or any(not isinstance(item, Mapping) for item in value)
    ):
        raise ValueError("s2_autonomy_decision_invalid")
    return tuple(dict(item) for item in value)
