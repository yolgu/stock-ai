"""Add verified autonomous state context only for an explicitly bound program."""

from __future__ import annotations

from research_hook_support import next_action_from_bound_program, read_hook_input, write_json


def main() -> int:
    value = read_hook_input()
    if value.get("hook_event_name") != "SessionStart":
        return 0
    action = next_action_from_bound_program(value)
    if action is None:
        return 0
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "Autonomous research is explicitly bound. Replay status, then obey "
                    f"ActionContract {action.get('actionId')} ({action.get('actionKind')})."
                ),
            }
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
