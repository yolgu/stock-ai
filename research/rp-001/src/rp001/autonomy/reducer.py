"""Replay verified events into the current autonomous research state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import PurePosixPath

from rp001.autonomy.events import (
    ProgramEventError,
    required_identifier,
    required_mapping,
    required_sha256,
    required_text,
)
from rp001.autonomy.model import (
    ActionKind,
    DataReleaseBinding,
    ProgramSnapshot,
    ProgramSpec,
    ResearchState,
)
from rp001.local_evidence import canonical_json_bytes, sha256_bytes


_ACTION_TRANSITIONS: dict[
    ActionKind,
    tuple[ResearchState, frozenset[ResearchState]],
] = {
    ActionKind.REPAIR_P0: (
        ResearchState.AWAITING_DATA_RELEASE,
        frozenset({ResearchState.AWAITING_DATA_RELEASE}),
    ),
    ActionKind.VALIDATE_DATA_RELEASE: (
        ResearchState.VALIDATE_MEASUREMENT,
        frozenset(
            {
                ResearchState.FREEZE_CYCLE_SPEC,
                ResearchState.AWAITING_DATA_RELEASE,
            }
        ),
    ),
    ActionKind.FREEZE_CYCLE_SPEC: (
        ResearchState.FREEZE_CYCLE_SPEC,
        frozenset({ResearchState.GENERATE_HYPOTHESIS}),
    ),
    ActionKind.GENERATE_HYPOTHESIS: (
        ResearchState.GENERATE_HYPOTHESIS,
        frozenset({ResearchState.IMPLEMENT_FORMULA}),
    ),
    ActionKind.IMPLEMENT_FORMULA: (
        ResearchState.IMPLEMENT_FORMULA,
        frozenset({ResearchState.SYNTHETIC_FALSIFICATION}),
    ),
    ActionKind.RUN_SYNTHETIC_FALSIFICATION: (
        ResearchState.SYNTHETIC_FALSIFICATION,
        frozenset(
            {
                ResearchState.DEVELOPMENT_OOF,
                ResearchState.CREATE_NEXT_FORMULA_VERSION,
            }
        ),
    ),
    ActionKind.RUN_DEVELOPMENT_OOF: (
        ResearchState.DEVELOPMENT_OOF,
        frozenset(
            {
                ResearchState.DIAGNOSE_RESULT,
                ResearchState.FREEZE_CONFIRMATION,
            }
        ),
    ),
    ActionKind.DIAGNOSE_RESULT: (
        ResearchState.DIAGNOSE_RESULT,
        frozenset(
            {
                ResearchState.CREATE_NEXT_FORMULA_VERSION,
                ResearchState.CYCLE_DECISION,
            }
        ),
    ),
    ActionKind.CREATE_FORMULA_VERSION: (
        ResearchState.CREATE_NEXT_FORMULA_VERSION,
        frozenset({ResearchState.SYNTHETIC_FALSIFICATION}),
    ),
    ActionKind.FREEZE_CONFIRMATION: (
        ResearchState.FREEZE_CONFIRMATION,
        frozenset({ResearchState.AWAITING_DATA_RELEASE}),
    ),
    ActionKind.RUN_CONFIRMATION_ONCE: (
        ResearchState.CONFIRM_ONCE,
        frozenset(
            {
                ResearchState.ECONOMIC_RISK_EVALUATION,
                ResearchState.CYCLE_DECISION,
            }
        ),
    ),
    ActionKind.EVALUATE_ECONOMIC_RISK: (
        ResearchState.ECONOMIC_RISK_EVALUATION,
        frozenset({ResearchState.CYCLE_DECISION}),
    ),
    ActionKind.DECIDE_CYCLE: (
        ResearchState.CYCLE_DECISION,
        frozenset({ResearchState.NEXT_CYCLE}),
    ),
    ActionKind.START_NEXT_CYCLE: (
        ResearchState.NEXT_CYCLE,
        frozenset({ResearchState.FREEZE_CYCLE_SPEC}),
    ),
    ActionKind.FINALIZE_PROGRAM_VERSION: (
        ResearchState.NEXT_CYCLE,
        frozenset({ResearchState.PROGRAM_VERSION_TERMINAL}),
    ),
}


def replay_program_events(
    spec: ProgramSpec,
    events: Sequence[Mapping[str, object]],
) -> ProgramSnapshot:
    """Derive state from the event stream without trusting a checkpoint."""
    snapshot = ProgramSnapshot.initial()
    for event in events:
        event_type = required_text(event.get("eventType"), "event_type")
        payload = required_mapping(event.get("payload"), "event_payload")
        snapshot = _apply_event(spec, snapshot, event_type, payload)
    return snapshot


def _apply_event(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
    event_type: str,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    if event_type == "autonomy_program_bootstrapped":
        return _bootstrap(spec, snapshot, payload)
    if not snapshot.bootstrapped:
        raise ProgramEventError("program_not_bootstrapped")
    if event_type == "autonomy_data_release_registered":
        return _register_data_release(snapshot, payload)
    if event_type == "autonomy_action_committed":
        return _commit_action(spec, snapshot, payload)
    if event_type == "autonomy_p0_opened":
        return _open_p0(snapshot, payload)
    if event_type == "autonomy_p0_resolved":
        return _resolve_p0(snapshot, payload)
    if event_type == "autonomy_user_paused":
        return _pause(snapshot)
    if event_type == "autonomy_user_resumed":
        return _resume(snapshot)
    raise ProgramEventError("event_type_invalid")


def _bootstrap(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    if snapshot.bootstrapped:
        raise ProgramEventError("program_already_bootstrapped")
    program_id = required_text(payload.get("programId"), "program_id")
    spec_sha256 = required_sha256(
        payload.get("programSpecSha256"),
        "program_spec_sha256",
    )
    expected = sha256_bytes(canonical_json_bytes(spec.to_canonical_dict()))
    if program_id != spec.program_id or spec_sha256 != expected:
        raise ProgramEventError("program_binding_invalid")
    return replace(
        snapshot,
        bootstrapped=True,
        program_id=program_id,
        program_spec_sha256=spec_sha256,
    )


def _register_data_release(
    snapshot: ProgramSnapshot,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    if snapshot.state is not ResearchState.AWAITING_DATA_RELEASE:
        raise ProgramEventError("state_transition_invalid")
    release_id = required_identifier(payload.get("releaseId"), "release_id")
    manifest_sha256 = required_sha256(
        payload.get("manifestSha256"),
        "manifest_sha256",
    )
    manifest_path = required_text(payload.get("manifestPath"), "manifest_path")
    parsed_path = PurePosixPath(manifest_path)
    if parsed_path.is_absolute() or ".." in parsed_path.parts:
        raise ProgramEventError("manifest_path_invalid")
    role = required_text(payload.get("role"), "release_role")
    if release_id in snapshot.registered_release_ids:
        raise ProgramEventError("release_id_reused")
    if role == "development" and not snapshot.confirmation_frozen:
        if payload.get("formulaVersionSha256") is not None:
            raise ProgramEventError("release_formula_binding_invalid")
        formula_version_sha256 = None
        next_state = ResearchState.VALIDATE_MEASUREMENT
    elif role == "confirmation" and snapshot.confirmation_frozen:
        formula_version_sha256 = required_sha256(
            payload.get("formulaVersionSha256"),
            "formula_version_sha256",
        )
        if formula_version_sha256 != snapshot.frozen_formula_version_sha256:
            raise ProgramEventError("release_formula_binding_invalid")
        if (
            release_id in snapshot.burned_confirmation_release_ids
            or manifest_sha256 in snapshot.burned_confirmation_manifest_sha256
        ):
            raise ProgramEventError("confirmation_release_burned")
        next_state = ResearchState.CONFIRM_ONCE
    else:
        raise ProgramEventError("release_role_invalid")
    binding = DataReleaseBinding(
        release_id=release_id,
        role=role,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        formula_version_sha256=formula_version_sha256,
    )
    burned = snapshot.burned_confirmation_release_ids
    burned_hashes = snapshot.burned_confirmation_manifest_sha256
    if role == "confirmation":
        burned |= {release_id}
        burned_hashes |= {manifest_sha256}
    return replace(
        snapshot,
        state=next_state,
        registered_release_ids=snapshot.registered_release_ids | {release_id},
        release_bindings=(*snapshot.release_bindings, binding),
        burned_confirmation_release_ids=frozenset(burned),
        burned_confirmation_manifest_sha256=frozenset(burned_hashes),
    )


def _commit_action(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    action_id = required_identifier(payload.get("actionId"), "action_id")
    if action_id in snapshot.committed_action_ids:
        raise ProgramEventError("action_id_reused")
    try:
        action_kind = ActionKind(required_text(payload.get("actionKind"), "action_kind"))
        from_state = ResearchState(required_text(payload.get("fromState"), "from_state"))
        to_state = ResearchState(required_text(payload.get("toState"), "to_state"))
    except ValueError:
        raise ProgramEventError("state_transition_invalid") from None
    transition = _ACTION_TRANSITIONS.get(action_kind)
    if transition is None:
        raise ProgramEventError("state_transition_invalid")
    required_from_state, allowed_to_states = transition
    if action_kind is ActionKind.REPAIR_P0:
        if snapshot.state is not from_state or to_state is not from_state:
            raise ProgramEventError("state_transition_invalid")
    elif snapshot.state is not from_state or from_state is not required_from_state:
        raise ProgramEventError("state_transition_invalid")
    status = required_text(payload.get("status"), "action_status")
    if status not in {"succeeded", "failed", "invalid"}:
        raise ProgramEventError("action_status_invalid")
    if (
        status == "succeeded"
        and action_kind is not ActionKind.REPAIR_P0
        and to_state not in allowed_to_states
    ):
        raise ProgramEventError("state_transition_invalid")
    if status != "succeeded" and to_state is not from_state:
        raise ProgramEventError("state_transition_invalid")
    if action_kind not in spec.allowed_actions and action_kind not in {
        ActionKind.REPAIR_P0,
        ActionKind.START_NEXT_CYCLE,
        ActionKind.FINALIZE_PROGRAM_VERSION,
    }:
        raise ProgramEventError("action_not_allowed")
    facts = required_mapping(payload.get("facts"), "action_facts")
    if status == "succeeded":
        _validate_action_semantics(
            spec,
            snapshot,
            action_kind,
            to_state,
            facts,
            payload.get("artifactBindings"),
        )
    updated = replace(
        snapshot,
        state=to_state,
        committed_action_ids=snapshot.committed_action_ids | {action_id},
        program_terminal=(to_state is ResearchState.PROGRAM_VERSION_TERMINAL),
    )
    if status != "succeeded":
        return updated
    return _apply_action_facts(spec, updated, action_kind, facts)


def _validate_action_semantics(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
    action_kind: ActionKind,
    to_state: ResearchState,
    facts: Mapping[str, object],
    artifact_bindings: object,
) -> None:
    if action_kind is ActionKind.FREEZE_CONFIRMATION:
        formula_sha256 = required_sha256(
            facts.get("formulaVersionSha256"),
            "formula_version_binding",
        )
        if formula_sha256 not in _artifact_sha256_values(artifact_bindings):
            raise ProgramEventError("formula_version_binding_invalid")
        return
    if action_kind is ActionKind.RUN_CONFIRMATION_ONCE:
        passed = facts.get("confirmationPassed")
        if type(passed) is not bool:
            raise ProgramEventError("confirmation_result_invalid")
        expected = (
            ResearchState.ECONOMIC_RISK_EVALUATION
            if passed
            else ResearchState.CYCLE_DECISION
        )
        if to_state is not expected:
            raise ProgramEventError("confirmation_transition_invalid")
        return
    if action_kind is ActionKind.EVALUATE_ECONOMIC_RISK:
        if type(facts.get("economicRiskPassed")) is not bool:
            raise ProgramEventError("economic_risk_result_invalid")
        return
    if action_kind is ActionKind.DECIDE_CYCLE:
        if facts.get("cycleStatus") == "ConfirmationPassed" and not (
            snapshot.confirmation_passed and snapshot.economic_risk_passed
        ):
            raise ProgramEventError("adoption_gate_incomplete")
        return
    if action_kind is not ActionKind.DIAGNOSE_RESULT:
        return
    successor = facts.get("successorAvailable")
    if type(successor) is not bool:
        raise ProgramEventError("successor_available_invalid")
    expected = (
        ResearchState.CREATE_NEXT_FORMULA_VERSION
        if successor
        else ResearchState.CYCLE_DECISION
    )
    if to_state is not expected:
        raise ProgramEventError("diagnosis_transition_invalid")
    if successor:
        family = _successor_family(snapshot, facts)
        counts = dict(snapshot.formula_version_counts)
        if counts.get(family, 0) >= spec.search_budget.maximum_versions_per_family:
            raise ProgramEventError("formula_version_budget_exhausted")


def _apply_action_facts(
    spec: ProgramSpec,
    snapshot: ProgramSnapshot,
    action_kind: ActionKind,
    facts: Mapping[str, object],
) -> ProgramSnapshot:
    mechanism_classes = snapshot.mechanism_classes
    candidate_families = snapshot.candidate_families
    cycle_candidate_families = snapshot.cycle_candidate_families
    formula_version_counts = dict(snapshot.formula_version_counts)
    active_candidate_family = snapshot.active_candidate_family
    successor_available = snapshot.successor_available
    completed_cycle_count = snapshot.completed_cycle_count
    active_question_id = snapshot.active_question_id
    completed_question_ids = snapshot.completed_question_ids
    confirmation_frozen = snapshot.confirmation_frozen
    frozen_formula_version_sha256 = snapshot.frozen_formula_version_sha256
    confirmation_passed = snapshot.confirmation_passed
    economic_risk_passed = snapshot.economic_risk_passed
    adoptable_candidate_found = snapshot.adoptable_candidate_found
    terminal_outcome = snapshot.terminal_outcome
    open_p0_blockers = snapshot.open_p0_blockers
    if action_kind is ActionKind.REPAIR_P0:
        blocker_id = required_identifier(
            facts.get("resolvedBlockerId"),
            "resolved_blocker_id",
        )
        if blocker_id not in open_p0_blockers:
            raise ProgramEventError("blocker_not_open")
        open_p0_blockers = open_p0_blockers - {blocker_id}
    if action_kind is ActionKind.FREEZE_CYCLE_SPEC:
        question_value = facts.get("questionId")
        if question_value is None and len(spec.required_question_ids) == 1:
            question_id = spec.required_question_ids[0]
        else:
            question_id = required_identifier(question_value, "question_id")
        if question_id not in spec.required_question_ids:
            raise ProgramEventError("question_id_not_registered")
        active_question_id = question_id
    if action_kind is ActionKind.GENERATE_HYPOTHESIS:
        mechanism = required_identifier(facts.get("mechanismClass"), "mechanism_class")
        if (
            mechanism not in mechanism_classes
            and len(mechanism_classes) >= spec.search_budget.maximum_mechanism_classes
        ):
            raise ProgramEventError("mechanism_class_budget_exhausted")
        if (
            mechanism in mechanism_classes
            and len(mechanism_classes) < spec.search_budget.minimum_mechanism_classes
        ):
            raise ProgramEventError("mechanism_class_coverage_required")
        mechanism_classes |= {mechanism}
    if action_kind is ActionKind.IMPLEMENT_FORMULA:
        families = _candidate_family_batch(facts)
        family_set = frozenset(families)
        if family_set & candidate_families:
            raise ProgramEventError("candidate_family_reused")
        if (
            len(candidate_families) + len(family_set)
            > spec.search_budget.maximum_total_candidate_families
        ):
            raise ProgramEventError("candidate_family_budget_exhausted")
        if (
            len(cycle_candidate_families) + len(family_set)
            > spec.search_budget.initial_families_per_cycle
        ):
            raise ProgramEventError("cycle_family_budget_exhausted")
        candidate_families |= family_set
        cycle_candidate_families |= family_set
        for family in families:
            formula_version_counts[family] = 1
        active_candidate_family = families[0] if len(families) == 1 else None
    if action_kind is ActionKind.CREATE_FORMULA_VERSION:
        family = required_identifier(facts.get("candidateFamily"), "candidate_family")
        if family != active_candidate_family:
            raise ProgramEventError("candidate_family_mismatch")
        current_count = formula_version_counts.get(family, 0)
        if current_count >= spec.search_budget.maximum_versions_per_family:
            raise ProgramEventError("formula_version_budget_exhausted")
        formula_version_counts[family] = current_count + 1
    if action_kind is ActionKind.DIAGNOSE_RESULT:
        value = facts.get("successorAvailable")
        if type(value) is not bool:
            raise ProgramEventError("successor_available_invalid")
        successor_available = value
        if value:
            active_candidate_family = _successor_family(snapshot, facts)
    if action_kind is ActionKind.FREEZE_CONFIRMATION:
        confirmation_frozen = True
        frozen_formula_version_sha256 = required_sha256(
            facts.get("formulaVersionSha256"),
            "formula_version_sha256",
        )
        confirmation_passed = False
        economic_risk_passed = False
    if action_kind is ActionKind.RUN_CONFIRMATION_ONCE:
        confirmation_frozen = False
        confirmation_passed = facts.get("confirmationPassed") is True
        economic_risk_passed = False
    if action_kind is ActionKind.EVALUATE_ECONOMIC_RISK:
        economic_risk_passed = facts.get("economicRiskPassed") is True
    if action_kind is ActionKind.START_NEXT_CYCLE:
        cycle_candidate_families = frozenset()
        active_candidate_family = None
        successor_available = True
        confirmation_frozen = False
        frozen_formula_version_sha256 = None
        confirmation_passed = False
        economic_risk_passed = False
        active_question_id = None
    if action_kind is ActionKind.DECIDE_CYCLE:
        if facts.get("cycleCompleted") is not True:
            raise ProgramEventError("cycle_completion_invalid")
        cycle_status = required_text(facts.get("cycleStatus"), "cycle_status")
        if cycle_status not in {"CycleTerminal", "ConfirmationPassed"}:
            raise ProgramEventError("cycle_status_invalid")
        if cycle_status == "ConfirmationPassed":
            adoptable_candidate_found = True
        if active_question_id is None:
            raise ProgramEventError("cycle_question_binding_missing")
        question_terminal = facts.get("questionTerminal")
        if question_terminal is None and len(spec.required_question_ids) == 1:
            question_terminal = True
        if type(question_terminal) is not bool:
            raise ProgramEventError("question_terminal_invalid")
        if question_terminal:
            completed_question_ids |= {active_question_id}
        completed_cycle_count += 1
    if action_kind is ActionKind.FINALIZE_PROGRAM_VERSION:
        if not set(spec.required_question_ids) <= completed_question_ids:
            raise ProgramEventError("question_coverage_incomplete")
        expected_outcome = (
            "adoptable_formula_confirmed"
            if adoptable_candidate_found
            else spec.terminal_claim
        )
        if facts.get("terminalOutcome") != expected_outcome:
            raise ProgramEventError("terminal_outcome_invalid")
        terminal_outcome = expected_outcome
    return replace(
        snapshot,
        mechanism_classes=frozenset(mechanism_classes),
        candidate_families=frozenset(candidate_families),
        cycle_candidate_families=frozenset(cycle_candidate_families),
        formula_version_counts=tuple(sorted(formula_version_counts.items())),
        active_candidate_family=active_candidate_family,
        successor_available=successor_available,
        completed_cycle_count=completed_cycle_count,
        active_question_id=active_question_id,
        completed_question_ids=frozenset(completed_question_ids),
        confirmation_frozen=confirmation_frozen,
        frozen_formula_version_sha256=frozen_formula_version_sha256,
        confirmation_passed=confirmation_passed,
        economic_risk_passed=economic_risk_passed,
        adoptable_candidate_found=adoptable_candidate_found,
        terminal_outcome=terminal_outcome,
        open_p0_blockers=frozenset(open_p0_blockers),
    )


def _candidate_family_batch(facts: Mapping[str, object]) -> tuple[str, ...]:
    batch = facts.get("candidateFamilies")
    if batch is None:
        return (
            required_identifier(facts.get("candidateFamily"), "candidate_family"),
        )
    if (
        not isinstance(batch, Sequence)
        or isinstance(batch, (str, bytes))
        or not batch
    ):
        raise ProgramEventError("candidate_families_invalid")
    families = tuple(
        required_identifier(value, "candidate_family") for value in batch
    )
    if len(set(families)) != len(families):
        raise ProgramEventError("candidate_families_invalid")
    return families


def _artifact_sha256_values(value: object) -> frozenset[str]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
    ):
        raise ProgramEventError("formula_version_binding_invalid")
    hashes: set[str] = set()
    for binding in value:
        if not isinstance(binding, Mapping):
            raise ProgramEventError("formula_version_binding_invalid")
        hashes.add(required_sha256(binding.get("sha256"), "artifact_sha256"))
    return frozenset(hashes)


def _successor_family(
    snapshot: ProgramSnapshot,
    facts: Mapping[str, object],
) -> str:
    value = facts.get("successorFamily")
    if value is None and len(snapshot.cycle_candidate_families) == 1:
        return next(iter(snapshot.cycle_candidate_families))
    family = required_identifier(value, "successor_family")
    if family not in snapshot.cycle_candidate_families:
        raise ProgramEventError("successor_family_invalid")
    return family


def _open_p0(
    snapshot: ProgramSnapshot,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    blocker_id = required_identifier(payload.get("blockerId"), "blocker_id")
    required_text(payload.get("reason"), "blocker_reason")
    if blocker_id in snapshot.open_p0_blockers:
        raise ProgramEventError("blocker_id_reused")
    return replace(
        snapshot,
        open_p0_blockers=snapshot.open_p0_blockers | {blocker_id},
    )


def _resolve_p0(
    snapshot: ProgramSnapshot,
    payload: Mapping[str, object],
) -> ProgramSnapshot:
    blocker_id = required_identifier(payload.get("blockerId"), "blocker_id")
    if blocker_id not in snapshot.open_p0_blockers:
        raise ProgramEventError("blocker_not_open")
    return replace(
        snapshot,
        open_p0_blockers=snapshot.open_p0_blockers - {blocker_id},
    )


def _pause(snapshot: ProgramSnapshot) -> ProgramSnapshot:
    if snapshot.paused_by_user:
        raise ProgramEventError("program_already_paused")
    return replace(snapshot, paused_by_user=True)


def _resume(snapshot: ProgramSnapshot) -> ProgramSnapshot:
    if not snapshot.paused_by_user:
        raise ProgramEventError("program_not_paused")
    return replace(snapshot, paused_by_user=False)
