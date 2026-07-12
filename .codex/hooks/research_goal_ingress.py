"""Capture an explicit QUANT_RESEARCH_GOAL and request Goal activation."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = SOURCE_REPOSITORY_ROOT / "research" / "rp-001" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from research_hook_support import read_hook_input, write_json
from rp001.autonomy_v2.goal_ingress import GoalIngress, GoalIngressError
from rp001.autonomy_v2.controller import CampaignController, CampaignControllerError


def main() -> int:
    value = read_hook_input()
    if value.get("hook_event_name") != "UserPromptSubmit":
        return 0
    prompt = value.get("prompt")
    session_id = value.get("session_id")
    if not isinstance(prompt, str) or not isinstance(session_id, str):
        return 0
    repository_root = Path(
        os.environ.get(
            "QUANT_RESEARCH_REPOSITORY_ROOT",
            str(SOURCE_REPOSITORY_ROOT),
        )
    ).resolve()
    try:
        ingress = GoalIngress(repository_root)
        activation = ingress.capture(
            prompt,
            session_id=session_id,
        )
        if activation is not None:
            CampaignController(repository_root).bootstrap(
                activation.goal_path,
                occurred_at=datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            )
            ingress.mark_bootstrapped(activation)
    except (GoalIngressError, CampaignControllerError):
        if prompt.startswith("[QUANT_RESEARCH_GOAL]"):
            write_json(
                {
                    "decision": "block",
                    "reason": (
                        "The quantitative research Goal failed deterministic "
                        "ingress validation and was not persisted."
                    ),
                }
            )
        return 0
    if activation is None:
        return 0
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "A verified [QUANT_RESEARCH_GOAL] is explicit authorization to "
                    "call create_goal exactly once. Read the exact Goal from "
                    f"{activation.goal_path}; use the body after the marker as the "
                    "create_goal objective and omit token_budget. Campaign bootstrap "
                    f"for {activation.campaign_id} is already committed; run status "
                    "and next without bootstrapping again. Do not ask the user for an extra "
                    "command and do not rewrite the Goal."
                ),
            }
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
