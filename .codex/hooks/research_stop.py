"""Request at most one continuation for a verified runnable ActionContract."""

from __future__ import annotations

from research_hook_support import next_action_from_bound_program, read_hook_input, write_json


_NON_RUNNABLE_ACTIONS = frozenset({"WAIT_FOR_DATA_RELEASE", "NONE"})


def main() -> int:
    value = read_hook_input()
    if value.get("hook_event_name") != "Stop" or value.get("stop_hook_active") is True:
        write_json({"continue": True})
        return 0
    action = next_action_from_bound_program()
    if action is None or action.get("actionKind") in _NON_RUNNABLE_ACTIONS:
        write_json({"continue": True})
        return 0
    write_json(
        {
            "decision": "block",
            "reason": (
                "Resume the verified autonomous research ActionContract "
                f"{action.get('actionId')} ({action.get('actionKind')}); do not add planning."
            ),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
