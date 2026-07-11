"""Application service for Goal-driven autonomous research execution."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from rp001.autonomy.goal_contract import (
    GoalContractError,
    compile_goal_document,
    compile_program_spec,
)
from rp001.autonomy.model import ProgramSnapshot, ProgramSpec, ResearchState
from rp001.autonomy.policy import NextAction, NextActionKind, decide_next_action
from rp001.autonomy.reducer import replay_program_events
from rp001.autonomy.security_boundary import (
    ResearchFilesystemBoundary,
    SecurityBoundaryError,
)
from rp001.autonomy.validators import (
    ActionResultValidationError,
    ValidatedActionResult,
    validate_action_result_mapping,
)
from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerAppendError,
    LocalLedgerState,
    LocalLedgerTransaction,
    canonical_json_bytes,
    decode_canonical_local_ledger_record,
    sha256_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values


_OCCURRED_AT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AutonomousResearchError(ValueError):
    """Base error for the autonomous research application boundary."""


class ActionResultError(AutonomousResearchError):
    """Raised when a proposed action result is stale or invalid."""


@dataclass(frozen=True)
class ControllerStatus:
    spec: ProgramSpec
    snapshot: ProgramSnapshot
    ledger_state: LocalLedgerState

    def to_canonical_dict(self) -> dict[str, object]:
        body = self.snapshot.to_canonical_dict()
        body.update(
            {
                "ledgerSequence": self.ledger_state.sequence,
                "ledgerTailSha256": self.ledger_state.record_sha256,
            }
        )
        return body


@dataclass(frozen=True)
class ActionContract:
    action_id: str
    program_id: str
    program_version: str
    kind: NextActionKind
    current_state: str
    reason: str
    allowed_write_directory: Path
    input_bindings: tuple[dict[str, str], ...]
    required_validators: tuple[str, ...]
    data_request: dict[str, object] | None
    maximum_steps_per_activation: int
    ledger_tail_sha256: str | None

    @property
    def kind_value(self) -> str:
        return self.kind.value

    def to_canonical_dict(self, repository_root: Path) -> dict[str, object]:
        return {
            "schemaVersion": "rp001-autonomous-action-contract.v1",
            "actionId": self.action_id,
            "programId": self.program_id,
            "programVersion": self.program_version,
            "actionKind": self.kind.value,
            "currentState": self.current_state,
            "reason": self.reason,
            "inputBindings": [dict(value) for value in self.input_bindings],
            "allowedWritePaths": [
                self.allowed_write_directory.relative_to(repository_root).as_posix()
            ],
            "requiredValidators": list(self.required_validators),
            "successEventType": "autonomy_action_committed",
            "failureEventType": "autonomy_action_committed",
            "dataRequest": (
                dict(self.data_request) if self.data_request is not None else None
            ),
            "resourceBudget": {
                "maximumStepsPerActivation": self.maximum_steps_per_activation
            },
            "ledgerTailSha256": self.ledger_tail_sha256,
        }


class AutonomousResearchController:
    def __init__(
        self,
        *,
        repository_root: Path,
        preset_output_root: Path,
        live_collection_roots: tuple[Path, ...],
        confirmation_release_root: Path,
    ) -> None:
        if not repository_root.is_absolute():
            raise AutonomousResearchError("repository_root_invalid")
        self._repository_root = repository_root
        self._boundary = ResearchFilesystemBoundary(
            repository_root=repository_root,
            preset_output_root=preset_output_root,
            live_collection_roots=live_collection_roots,
            confirmation_release_root=confirmation_release_root,
        )
        self._store = LocalArtifactStore(repository_root)

    def bootstrap(
        self,
        *,
        goal_path: Path,
        program_spec_input_path: Path,
        program_root: Path,
        occurred_at: str,
    ) -> ProgramSnapshot:
        """Publish immutable Goal/spec bindings and the first ledger event."""
        _require_occurred_at(occurred_at)
        program_root = self._require_program_root(program_root)
        goal_source = _read_regular_bytes(goal_path, "goal_source_invalid")
        spec_source = _read_regular_bytes(
            program_spec_input_path,
            "program_spec_input_invalid",
        )
        spec_value = _canonical_mapping(spec_source, "program_spec_input_invalid")
        try:
            spec = compile_program_spec(goal_source, spec_value)
        except GoalContractError as error:
            raise AutonomousResearchError(str(error)) from None
        return self._publish_program(
            program_root=program_root,
            goal_source=goal_source,
            spec=spec,
            occurred_at=occurred_at,
        )

    def bootstrap_goal(
        self,
        *,
        goal_path: Path,
        program_root: Path | None,
        occurred_at: str,
    ) -> ProgramSnapshot:
        """Bootstrap or resume directly from one unchanged complete Goal."""
        _require_occurred_at(occurred_at)
        goal_source = _read_regular_bytes(goal_path, "goal_source_invalid")
        try:
            spec = compile_goal_document(goal_source)
        except GoalContractError as error:
            raise AutonomousResearchError(str(error)) from None
        selected_root = program_root or (
            self._boundary.preset_output_root / spec.program_id
        )
        selected_root = self._require_program_root(selected_root)
        if selected_root.name != spec.program_id:
            raise AutonomousResearchError("program_root_identity_invalid")
        if selected_root.exists():
            status = self.status(selected_root)
            if status.spec != spec:
                raise AutonomousResearchError("program_goal_binding_invalid")
            return status.snapshot
        return self._publish_program(
            program_root=selected_root,
            goal_source=goal_source,
            spec=spec,
            occurred_at=occurred_at,
        )

    def _publish_program(
        self,
        *,
        program_root: Path,
        goal_source: bytes,
        spec: ProgramSpec,
        occurred_at: str,
    ) -> ProgramSnapshot:
        if program_root.name != spec.program_id:
            raise AutonomousResearchError("program_root_identity_invalid")
        try:
            goal_text = goal_source.decode("utf-8")
        except UnicodeDecodeError:
            raise AutonomousResearchError("goal_source_invalid") from None
        if find_sensitive_values(goal_text):
            raise AutonomousResearchError("goal_sensitive_value")
        spec_source = canonical_json_bytes(spec.to_canonical_dict())
        if find_sensitive_values(spec_source.decode("utf-8")):
            raise AutonomousResearchError("program_spec_sensitive_value")
        published: list[LocalArtifactBinding] = []
        try:
            goal_binding = self._store.publish_bytes(
                program_root / "goal-source.md",
                goal_source,
            )
            published.append(goal_binding)
            spec_binding = self._store.publish_json(
                program_root / "program-spec.json",
                spec.to_canonical_dict(),
            )
            published.append(spec_binding)
            ledger = self._ledger(program_root)
            ledger.require_empty()
            ledger.append(
                "autonomy_program_bootstrapped",
                {
                    "programId": spec.program_id,
                    "programSpecSha256": spec_binding.artifact_sha256,
                    "goal": _binding(goal_binding, self._repository_root),
                    "programSpec": _binding(spec_binding, self._repository_root),
                },
                occurred_at,
            )
        except BaseException as error:
            event_published = (
                isinstance(error, LocalLedgerAppendError)
                and error.event_published
            )
            if not event_published:
                for binding in reversed(published):
                    try:
                        self._store.rollback_publication(binding)
                    except LocalEvidenceError:
                        pass
            raise
        return self.status(program_root).snapshot

    def status(self, program_root: Path) -> ControllerStatus:
        """Replay verified evidence and return current state without writing."""
        program_root = self._require_program_root(program_root)
        spec = self._load_spec(program_root)
        ledger = self._ledger(program_root)
        with ledger.transaction() as transaction:
            events, ledger_state = self._read_events_locked(program_root, transaction)
            try:
                snapshot = replay_program_events(spec, events)
            except ValueError as error:
                raise AutonomousResearchError(str(error)) from None
            self._verify_committed_bindings(events, snapshot)
        return ControllerStatus(spec, snapshot, ledger_state)

    def next_action(self, program_root: Path) -> ActionContract:
        """Return a deterministic, read-only action contract."""
        status = self.status(program_root)
        decision = decide_next_action(status.spec, status.snapshot)
        return self._action_contract(program_root, status, decision)

    def register_data_release(
        self,
        program_root: Path,
        *,
        release_id: str,
        role: str,
        manifest_path: Path,
        occurred_at: str,
    ) -> ProgramSnapshot:
        """Bind a user-supplied manifest by hash without modifying it."""
        _require_occurred_at(occurred_at)
        if role not in {"development", "confirmation"}:
            raise AutonomousResearchError("release_role_invalid")
        program_root = self._require_program_root(program_root)
        ledger = self._ledger(program_root)
        spec = self._load_spec(program_root)
        with ledger.transaction() as transaction:
            events, _ledger_state = self._read_events_locked(program_root, transaction)
            try:
                snapshot = replay_program_events(spec, events)
            except ValueError as error:
                raise AutonomousResearchError(str(error)) from None
            self._verify_committed_bindings(events, snapshot)
            if snapshot.state is not ResearchState.AWAITING_DATA_RELEASE:
                raise AutonomousResearchError("state_transition_invalid")
            if role == "confirmation":
                try:
                    self._boundary.require_confirmation_release(
                        manifest_path,
                        snapshot,
                    )
                except SecurityBoundaryError as error:
                    raise AutonomousResearchError(str(error)) from None
                if snapshot.frozen_formula_version_sha256 is None:
                    raise AutonomousResearchError(
                        "confirmation_formula_binding_missing"
                    )
            elif snapshot.confirmation_frozen:
                raise AutonomousResearchError("release_role_invalid")
            manifest_source = _read_regular_bytes(
                manifest_path,
                "release_manifest_invalid",
            )
            _canonical_mapping(manifest_source, "release_manifest_invalid")
            if find_sensitive_values(manifest_source.decode("utf-8")):
                raise AutonomousResearchError("release_manifest_sensitive_value")
            try:
                relative_manifest = manifest_path.resolve(strict=True).relative_to(
                    self._repository_root
                )
            except (OSError, ValueError):
                raise AutonomousResearchError(
                    "release_manifest_path_invalid"
                ) from None
            payload: dict[str, object] = {
                "releaseId": release_id,
                "role": role,
                "manifestPath": relative_manifest.as_posix(),
                "manifestSha256": sha256_bytes(manifest_source),
            }
            if role == "confirmation":
                payload["formulaVersionSha256"] = (
                    snapshot.frozen_formula_version_sha256
                )
            event = {
                "eventType": "autonomy_data_release_registered",
                "payload": payload,
            }
            try:
                replay_program_events(spec, (*events, event))
            except ValueError as error:
                raise AutonomousResearchError(str(error)) from None
            transaction.append(event["eventType"], event["payload"], occurred_at)
        return self.status(program_root).snapshot

    def validate_result(
        self,
        program_root: Path,
        result_path: Path,
    ) -> ValidatedActionResult:
        """Validate a result against the current action without committing it."""
        status = self.status(program_root)
        action = self._action_contract(
            program_root,
            status,
            decide_next_action(status.spec, status.snapshot),
        )
        result = self._validate_result_mapping(result_path, action, status.snapshot)
        event = {"eventType": "autonomy_action_committed", "payload": result.event_payload}
        try:
            replay_program_events(status.spec, (*self._events(program_root), event))
        except ValueError as error:
            raise ActionResultError(str(error)) from None
        return result

    def commit_result(
        self,
        program_root: Path,
        result_path: Path,
        *,
        occurred_at: str,
    ) -> ProgramSnapshot:
        """Atomically validate current state and append one action result."""
        _require_occurred_at(occurred_at)
        program_root = self._require_program_root(program_root)
        spec = self._load_spec(program_root)
        ledger = self._ledger(program_root)
        with ledger.transaction() as transaction:
            events, ledger_state = self._read_events_locked(program_root, transaction)
            snapshot = replay_program_events(spec, events)
            self._verify_committed_bindings(events, snapshot)
            status = ControllerStatus(spec, snapshot, ledger_state)
            action = self._action_contract(
                program_root,
                status,
                decide_next_action(spec, snapshot),
            )
            result = self._validate_result_mapping(result_path, action, snapshot)
            event = {
                "eventType": "autonomy_action_committed",
                "payload": result.event_payload,
            }
            try:
                replay_program_events(spec, (*events, event))
            except ValueError as error:
                raise ActionResultError(str(error)) from None
            transaction.append(event["eventType"], event["payload"], occurred_at)
        return self.status(program_root).snapshot

    def verify(self, program_root: Path) -> ControllerStatus:
        return self.status(program_root)

    def pause(self, program_root: Path, *, occurred_at: str) -> ProgramSnapshot:
        return self._append_program_event(
            program_root,
            event_type="autonomy_user_paused",
            payload={},
            occurred_at=occurred_at,
        )

    def resume(self, program_root: Path, *, occurred_at: str) -> ProgramSnapshot:
        return self._append_program_event(
            program_root,
            event_type="autonomy_user_resumed",
            payload={},
            occurred_at=occurred_at,
        )

    def open_p0(
        self,
        program_root: Path,
        *,
        blocker_id: str,
        reason: str,
        occurred_at: str,
    ) -> ProgramSnapshot:
        if not reason or find_sensitive_values(reason):
            raise AutonomousResearchError("blocker_reason_invalid")
        return self._append_program_event(
            program_root,
            event_type="autonomy_p0_opened",
            payload={"blockerId": blocker_id, "reason": reason},
            occurred_at=occurred_at,
        )

    def _append_program_event(
        self,
        program_root: Path,
        *,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> ProgramSnapshot:
        _require_occurred_at(occurred_at)
        program_root = self._require_program_root(program_root)
        spec = self._load_spec(program_root)
        ledger = self._ledger(program_root)
        event = {"eventType": event_type, "payload": dict(payload)}
        with ledger.transaction() as transaction:
            events, _state = self._read_events_locked(program_root, transaction)
            try:
                snapshot = replay_program_events(spec, events)
            except ValueError as error:
                raise AutonomousResearchError(str(error)) from None
            self._verify_committed_bindings(events, snapshot)
            try:
                replay_program_events(spec, (*events, event))
            except ValueError as error:
                raise AutonomousResearchError(str(error)) from None
            transaction.append(event_type, event["payload"], occurred_at)
        return self.status(program_root).snapshot

    def _validate_result_mapping(
        self,
        result_path: Path,
        action: ActionContract,
        snapshot: ProgramSnapshot,
    ) -> ValidatedActionResult:
        source = _read_regular_bytes(result_path, "action_result_invalid")
        value = _canonical_mapping(source, "action_result_invalid")
        try:
            return validate_action_result_mapping(
                value,
                action=action,
                repository_root=self._repository_root,
                boundary=self._boundary,
                committed_action_ids=snapshot.committed_action_ids,
            )
        except ActionResultValidationError as error:
            raise ActionResultError(str(error)) from None

    def _load_spec(self, program_root: Path) -> ProgramSpec:
        goal_path = program_root / "goal-source.md"
        spec_path = program_root / "program-spec.json"
        goal_source = _read_bound_bytes(goal_path, "goal_binding_invalid")
        spec_source = _read_bound_bytes(spec_path, "program_spec_binding_invalid")
        spec_value = _canonical_mapping(spec_source, "program_spec_binding_invalid")
        try:
            return compile_program_spec(goal_source, spec_value)
        except GoalContractError as error:
            raise AutonomousResearchError(str(error)) from None

    def _events(self, program_root: Path) -> tuple[Mapping[str, object], ...]:
        ledger = self._ledger(program_root)
        with ledger.transaction() as transaction:
            events, _state = self._read_events_locked(program_root, transaction)
            return events

    def _read_events_locked(
        self,
        program_root: Path,
        transaction: LocalLedgerTransaction,
    ) -> tuple[tuple[Mapping[str, object], ...], LocalLedgerState]:
        try:
            state = transaction.validate()
        except LocalEvidenceError as error:
            raise AutonomousResearchError(str(error)) from None
        events_directory = program_root / "ledger" / "events"
        previous: str | None = None
        events: list[Mapping[str, object]] = []
        for sequence in range(1, state.sequence + 1):
            path = events_directory / f"{sequence:06d}.json"
            source = _read_regular_bytes(path, "ledger_event_invalid")
            sidecar = _read_regular_bytes(
                Path(f"{path}.sha256"),
                "ledger_sidecar_invalid",
            )
            digest = sha256_bytes(source)
            if sidecar != f"{digest}\n".encode("ascii"):
                raise AutonomousResearchError("ledger_sidecar_invalid")
            try:
                record = decode_canonical_local_ledger_record(
                    source,
                    expected_sequence=sequence,
                    expected_previous_sha256=previous,
                )
            except LocalEvidenceError as error:
                raise AutonomousResearchError(str(error)) from None
            events.append(record)
            previous = digest
        if previous != state.record_sha256:
            raise AutonomousResearchError("ledger_tail_invalid")
        try:
            transaction.verify()
        except LocalEvidenceError as error:
            raise AutonomousResearchError(str(error)) from None
        return tuple(events), state

    def _verify_committed_bindings(
        self,
        events: Sequence[Mapping[str, object]],
        snapshot: ProgramSnapshot,
    ) -> None:
        for event in events:
            if event.get("eventType") != "autonomy_action_committed":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                raise AutonomousResearchError("committed_artifact_binding_invalid")
            bindings = payload.get("artifactBindings")
            if (
                not isinstance(bindings, Sequence)
                or isinstance(bindings, (str, bytes))
                or not bindings
            ):
                raise AutonomousResearchError("committed_artifact_binding_invalid")
            for binding in bindings:
                self._verify_committed_artifact(binding)
        for release in snapshot.release_bindings:
            manifest = self._repository_root / release.manifest_path
            source = _read_regular_bytes(
                manifest,
                "release_manifest_unavailable",
            )
            if sha256_bytes(source) != release.manifest_sha256:
                raise AutonomousResearchError("release_manifest_hash_mismatch")

    def _verify_committed_artifact(self, value: object) -> None:
        if not isinstance(value, Mapping):
            raise AutonomousResearchError("committed_artifact_binding_invalid")
        relative = value.get("path")
        expected = value.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise AutonomousResearchError("committed_artifact_binding_invalid")
        parsed = PurePosixPath(relative)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or _SHA256.fullmatch(expected) is None
        ):
            raise AutonomousResearchError("committed_artifact_binding_invalid")
        try:
            artifact = self._boundary.require_write_path(
                self._repository_root / parsed
            )
        except SecurityBoundaryError as error:
            raise AutonomousResearchError(str(error)) from None
        source = _read_regular_bytes(
            artifact,
            "committed_artifact_unavailable",
        )
        sidecar = _read_regular_bytes(
            Path(f"{artifact}.sha256"),
            "committed_artifact_sidecar_invalid",
        )
        if (
            sha256_bytes(source) != expected
            or sidecar != f"{expected}\n".encode("ascii")
        ):
            raise AutonomousResearchError("committed_artifact_hash_mismatch")

    def _action_contract(
        self,
        program_root: Path,
        status: ControllerStatus,
        decision: NextAction,
    ) -> ActionContract:
        identity = {
            "programId": status.spec.program_id,
            "programSpecSha256": status.snapshot.program_spec_sha256,
            "ledgerTailSha256": status.ledger_state.record_sha256,
            "state": status.snapshot.state.value,
            "actionKind": decision.kind.value,
        }
        action_id = sha256_bytes(canonical_json_bytes(identity))[:32]
        allowed = program_root / "artifacts" / action_id
        return ActionContract(
            action_id=action_id,
            program_id=status.spec.program_id,
            program_version=status.snapshot.program_spec_sha256 or "",
            kind=decision.kind,
            current_state=status.snapshot.state.value,
            reason=decision.reason,
            allowed_write_directory=allowed,
            input_bindings=self._input_bindings(program_root, status, decision),
            required_validators=(
                "action_identity",
                "state_transition_replay",
                "write_boundary",
                "artifact_sha256_sidecar",
                "sensitive_value_scan",
            ),
            data_request=self._data_request(status, decision, action_id),
            maximum_steps_per_activation=(
                status.spec.search_budget.maximum_steps_per_activation
            ),
            ledger_tail_sha256=status.ledger_state.record_sha256,
        )

    def _data_request(
        self,
        status: ControllerStatus,
        decision: NextAction,
        action_id: str,
    ) -> dict[str, object] | None:
        if decision.kind is not NextActionKind.WAIT_FOR_DATA_RELEASE:
            return None
        if status.snapshot.confirmation_frozen:
            role = "confirmation"
            try:
                manifest_directory = self._boundary.confirmation_release_root.relative_to(
                    self._repository_root
                ).as_posix()
            except ValueError:
                manifest_directory = str(self._boundary.confirmation_release_root)
        else:
            role = "development"
            manifest_directory = status.spec.data_release_directory
        request: dict[str, object] = {
            "requestId": f"DATA-{action_id}",
            "role": role,
            "manifestDirectory": manifest_directory,
            "manifestFormat": "canonical-json",
            "maximumUses": 1,
        }
        if role == "confirmation":
            if status.snapshot.frozen_formula_version_sha256 is None:
                raise AutonomousResearchError(
                    "confirmation_formula_binding_missing"
                )
            request["formulaVersionSha256"] = (
                status.snapshot.frozen_formula_version_sha256
            )
        return request

    def _input_bindings(
        self,
        program_root: Path,
        status: ControllerStatus,
        decision: NextAction,
    ) -> tuple[dict[str, str], ...]:
        bindings = [
            self._artifact_input("goal", program_root / "goal-source.md"),
            self._artifact_input("program-spec", program_root / "program-spec.json"),
        ]
        role = (
            "confirmation"
            if decision.kind is NextActionKind.RUN_CONFIRMATION_ONCE
            else "development"
        )
        releases = [
            value for value in status.snapshot.release_bindings if value.role == role
        ]
        if releases:
            release = releases[-1]
            manifest = self._repository_root / release.manifest_path
            source = _read_regular_bytes(manifest, "release_manifest_unavailable")
            if sha256_bytes(source) != release.manifest_sha256:
                raise AutonomousResearchError("release_manifest_hash_mismatch")
            bindings.append(
                {
                    "bindingId": release.release_id,
                    "bindingKind": f"{role}-release-manifest",
                    "path": release.manifest_path,
                    "sha256": release.manifest_sha256,
                }
            )
        return tuple(bindings)

    def _artifact_input(self, binding_id: str, path: Path) -> dict[str, str]:
        source = _read_bound_bytes(path, "program_binding_invalid")
        return {
            "bindingId": binding_id,
            "bindingKind": "frozen-program-artifact",
            "path": path.relative_to(self._repository_root).as_posix(),
            "sha256": sha256_bytes(source),
        }

    def _require_program_root(self, program_root: Path) -> Path:
        try:
            return self._boundary.require_write_path(program_root)
        except ValueError as error:
            raise AutonomousResearchError(str(error)) from None

    @staticmethod
    def _ledger(program_root: Path) -> AppendOnlyLocalLedger:
        return AppendOnlyLocalLedger(program_root / "ledger")


def _canonical_mapping(source: bytes, error: str) -> Mapping[str, object]:
    try:
        value = json.loads(source.decode("utf-8"))
        canonical = canonical_json_bytes(value)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        LocalEvidenceError,
        RecursionError,
    ):
        raise AutonomousResearchError(error) from None
    if not isinstance(value, Mapping) or canonical != source:
        raise AutonomousResearchError(error)
    return value


def _read_regular_bytes(path: Path, error: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise AutonomousResearchError(error)
        return path.read_bytes()
    except OSError:
        raise AutonomousResearchError(error) from None


def _read_bound_bytes(path: Path, error: str) -> bytes:
    source = _read_regular_bytes(path, error)
    sidecar = _read_regular_bytes(Path(f"{path}.sha256"), error)
    if sidecar != f"{sha256_bytes(source)}\n".encode("ascii"):
        raise AutonomousResearchError(error)
    return source


def _binding(
    value: LocalArtifactBinding,
    repository_root: Path,
) -> dict[str, str]:
    return {
        "path": value.path.relative_to(repository_root).as_posix(),
        "sha256": value.artifact_sha256,
    }


def _require_occurred_at(value: str) -> None:
    if _OCCURRED_AT.fullmatch(value) is None:
        raise AutonomousResearchError("occurred_at_invalid")
