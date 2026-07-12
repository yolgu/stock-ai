"""Deterministic ingress for an explicit natural-language research Goal."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from rp001.sensitive_value_policy import find_sensitive_values


QUANT_RESEARCH_GOAL_MARKER = "[QUANT_RESEARCH_GOAL]"
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class GoalIngressError(ValueError):
    """Raised when an explicit Goal cannot be safely activated."""


@dataclass(frozen=True)
class GoalActivation:
    campaign_id: str
    goal_sha256: str
    goal_path: Path
    activation_path: Path
    session_id: str


class GoalIngress:
    def __init__(self, repository_root: Path) -> None:
        if not repository_root.is_absolute():
            raise GoalIngressError("repository_root_invalid")
        self._repository_root = repository_root

    def capture(
        self,
        prompt: str,
        *,
        session_id: str,
    ) -> GoalActivation | None:
        """Preserve a marked Goal exactly and bind it to one session."""
        if not prompt.startswith(f"{QUANT_RESEARCH_GOAL_MARKER}\n"):
            return None
        if _SESSION_ID.fullmatch(session_id) is None:
            raise GoalIngressError("session_id_invalid")
        body = prompt[len(QUANT_RESEARCH_GOAL_MARKER) :].strip()
        if not body:
            raise GoalIngressError("goal_body_invalid")
        if find_sensitive_values(prompt):
            raise GoalIngressError("goal_sensitive_value")
        source = prompt.encode("utf-8")
        digest = hashlib.sha256(source).hexdigest()
        campaign_id = f"QR-CAMPAIGN-{digest[:20].upper()}"
        state_root = self._repository_root / ".codex" / "state" / "quant-research"
        goal_path = state_root / "goals" / digest / "goal-source.md"
        activation_path = state_root / "sessions" / f"{session_id}.json"
        self._require_compatible_binding(activation_path, digest)
        self._publish_once(goal_path, source)
        activation = {
            "schemaVersion": "quant-research-goal-activation.v1",
            "campaignId": campaign_id,
            "goalSha256": digest,
            "goalPath": goal_path.relative_to(self._repository_root).as_posix(),
            "sessionId": session_id,
            "status": "pending_goal_activation",
        }
        if not activation_path.exists():
            self._publish_once(
                activation_path,
                json.dumps(
                    activation,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
            )
        return GoalActivation(
            campaign_id=campaign_id,
            goal_sha256=digest,
            goal_path=goal_path,
            activation_path=activation_path,
            session_id=session_id,
        )

    def mark_bootstrapped(self, activation: GoalActivation) -> None:
        """Atomically expose a session only after its campaign ledger exists."""
        try:
            value = json.loads(activation.activation_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeError):
            raise GoalIngressError("active_goal_conflict") from None
        if (
            not isinstance(value, dict)
            or value.get("campaignId") != activation.campaign_id
            or value.get("goalSha256") != activation.goal_sha256
        ):
            raise GoalIngressError("active_goal_conflict")
        value["status"] = "campaign_bootstrapped"
        source = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        temporary = activation.activation_path.with_suffix(".tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(source)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, activation.activation_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _publish_once(path: Path, source: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != source:
                raise GoalIngressError("goal_state_conflict")
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(source)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _require_compatible_binding(path: Path, digest: str) -> None:
        if not path.exists():
            return
        if path.is_symlink() or not path.is_file():
            raise GoalIngressError("active_goal_conflict")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeError):
            raise GoalIngressError("active_goal_conflict") from None
        if not isinstance(value, dict) or value.get("goalSha256") != digest:
            raise GoalIngressError("active_goal_conflict")
