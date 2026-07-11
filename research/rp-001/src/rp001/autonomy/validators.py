"""Deterministic validators for model-produced autonomous research results."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from rp001.autonomy.security_boundary import (
    ResearchFilesystemBoundary,
    SecurityBoundaryError,
)
from rp001.local_evidence import canonical_json_bytes, sha256_bytes
from rp001.sensitive_value_policy import find_sensitive_values


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "actionId",
        "actionKind",
        "fromState",
        "toState",
        "status",
        "artifactBindings",
        "facts",
    }
)
_BINDING_FIELDS = frozenset({"path", "sha256"})
_TEXT_SUFFIXES = frozenset(
    {".csv", ".json", ".jsonl", ".md", ".py", ".sql", ".toml", ".tsv", ".txt", ".yaml", ".yml"}
)


class ActionResultValidationError(ValueError):
    """Raised when an action result cannot become research evidence."""


class ActionContractLike(Protocol):
    action_id: str
    current_state: str
    allowed_write_directory: Path

    @property
    def kind_value(self) -> str: ...


@dataclass(frozen=True)
class ValidatedActionResult:
    event_payload: dict[str, object]
    artifact_paths: tuple[Path, ...]


def validate_action_result_mapping(
    value: Mapping[str, object],
    *,
    action: ActionContractLike,
    repository_root: Path,
    boundary: ResearchFilesystemBoundary,
    committed_action_ids: frozenset[str],
) -> ValidatedActionResult:
    """Validate identity, transition inputs, artifact hashes, and write scope."""
    if set(value) != _RESULT_FIELDS:
        raise ActionResultValidationError("action_result_fields_invalid")
    serialized_result = canonical_json_bytes(value).decode("utf-8")
    if find_sensitive_values(serialized_result):
        raise ActionResultValidationError("action_result_sensitive_value")
    action_id = _text(value.get("actionId"), "action_id_invalid")
    if action_id in committed_action_ids:
        raise ActionResultValidationError("action_id_reused")
    if action_id != action.action_id:
        raise ActionResultValidationError("action_result_stale")
    if value.get("actionKind") != action.kind_value:
        raise ActionResultValidationError("action_kind_mismatch")
    if value.get("fromState") != action.current_state:
        raise ActionResultValidationError("action_state_mismatch")
    if value.get("schemaVersion") != "rp001-autonomous-action-result.v1":
        raise ActionResultValidationError("action_result_schema_invalid")
    if value.get("status") not in {"succeeded", "failed", "invalid"}:
        raise ActionResultValidationError("action_result_status_invalid")
    to_state = _text(value.get("toState"), "action_to_state_invalid")
    facts = value.get("facts")
    if not isinstance(facts, Mapping):
        raise ActionResultValidationError("action_facts_invalid")
    artifact_paths = _artifact_bindings(
        value.get("artifactBindings"),
        action=action,
        repository_root=repository_root,
        boundary=boundary,
    )
    return ValidatedActionResult(
        event_payload={
            "actionId": action_id,
            "actionKind": action.kind_value,
            "fromState": action.current_state,
            "toState": to_state,
            "status": value["status"],
            "artifactBindings": [
                {
                    "path": path.relative_to(repository_root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
                for path in artifact_paths
            ],
            "facts": dict(facts),
        },
        artifact_paths=artifact_paths,
    )


def _artifact_bindings(
    value: object,
    *,
    action: ActionContractLike,
    repository_root: Path,
    boundary: ResearchFilesystemBoundary,
) -> tuple[Path, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
    ):
        raise ActionResultValidationError("artifact_bindings_invalid")
    paths: list[Path] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _BINDING_FIELDS:
            raise ActionResultValidationError("artifact_binding_invalid")
        relative = _text(item.get("path"), "artifact_path_invalid")
        expected = _text(item.get("sha256"), "artifact_hash_invalid")
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or ".." in parsed.parts or _SHA256.fullmatch(expected) is None:
            raise ActionResultValidationError("artifact_binding_invalid")
        candidate = repository_root / parsed
        try:
            candidate = boundary.require_write_path(candidate)
            candidate.relative_to(action.allowed_write_directory)
        except (SecurityBoundaryError, ValueError):
            raise ActionResultValidationError("artifact_path_denied") from None
        if candidate.is_symlink() or not candidate.is_file():
            raise ActionResultValidationError("artifact_unavailable")
        source = candidate.read_bytes()
        sidecar = Path(f"{candidate}.sha256")
        if (
            sha256_bytes(source) != expected
            or not sidecar.is_file()
            or sidecar.is_symlink()
            or sidecar.read_bytes() != f"{expected}\n".encode("ascii")
        ):
            raise ActionResultValidationError("artifact_hash_mismatch")
        decoded = _decoded_for_secret_scan(candidate, source)
        if find_sensitive_values(decoded):
            raise ActionResultValidationError("artifact_sensitive_value")
        paths.append(candidate)
    if len(set(paths)) != len(paths):
        raise ActionResultValidationError("artifact_binding_duplicate")
    return tuple(paths)


def _decoded_for_secret_scan(path: Path, source: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        try:
            decoded = source.decode("utf-8")
        except UnicodeDecodeError:
            raise ActionResultValidationError("artifact_encoding_invalid") from None
        if suffix == ".json":
            try:
                value = json.loads(decoded)
                canonical = canonical_json_bytes(value)
            except (json.JSONDecodeError, RecursionError, ValueError):
                raise ActionResultValidationError(
                    "artifact_canonical_json_invalid"
                ) from None
            if canonical != source:
                raise ActionResultValidationError("artifact_canonical_json_invalid")
        return decoded
    return source.decode("utf-8", errors="ignore")


def _text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActionResultValidationError(error)
    return value
