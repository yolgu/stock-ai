"""Best-effort denial of obvious trading and private-account tool requests."""

from __future__ import annotations

import json
import os
import re

from research_hook_support import read_hook_input, write_json


_FORBIDDEN = re.compile(
    r"(?:/(?:api|openapi)/(?:[^/\s\"']+/){0,3}"
    r"(?:orders?|conditional-orders?|accounts?|positions?|assets?)(?:/|\b))"
    r"|(?:\b(?:place|submit|cancel)[ _-]+(?:an?[ _-]+)?"
    r"(?:buy|sell|market|limit)?[ _-]*order\b)"
    r"|(?:\bmcp__[^\s\"']*__(?:place|submit|cancel|get|list)?_?"
    r"(?:orders?|accounts?|positions?|assets?)\b)",
    re.IGNORECASE,
)


def main() -> int:
    value = read_hook_input()
    if (
        value.get("hook_event_name") != "PreToolUse"
        or not os.environ.get("RP001_AUTONOMY_PROGRAM_ROOT")
    ):
        return 0
    searchable = json.dumps(
        {
            "toolName": value.get("tool_name"),
            "toolInput": value.get("tool_input"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if _FORBIDDEN.search(searchable) is None:
        return 0
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "Autonomous research cannot access orders, accounts, positions, or assets."
                ),
            }
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
