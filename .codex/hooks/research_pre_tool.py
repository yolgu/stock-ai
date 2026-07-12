"""Best-effort denial of obvious trading and private-account tool requests."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from research_hook_support import (
    has_active_research_binding,
    next_action_from_bound_program,
    read_hook_input,
    write_json,
)


_FORBIDDEN = re.compile(
    r"(?:/(?:api|openapi)/(?:[^/\s\"']+/){0,3}"
    r"(?:orders?|conditional-orders?|accounts?|positions?|assets?)(?:/|\b))"
    r"|(?:\b(?:place|submit|cancel)[ _-]+(?:an?[ _-]+)?"
    r"(?:buy|sell|market|limit)?[ _-]*order\b)"
    r"|(?:\bmcp__[^\s\"']*__(?:place|submit|cancel|get|list)?_?"
    r"(?:orders?|accounts?|positions?|assets?)\b)",
    re.IGNORECASE,
)
_WRITE_TOOLS = frozenset({"write", "edit", "multiedit", "apply_patch"})
_READ_ONLY_COMMANDS = frozenset({"rg", "sed", "head", "tail", "pwd", "ls", "find"})
_SAFE_TOOLS = frozenset(
    {
        "read",
        "glob",
        "grep",
        "websearch",
        "webfetch",
        "get_goal",
        "create_goal",
        "update_goal",
        "todowrite",
    }
)


def main() -> int:
    value = read_hook_input()
    if (
        value.get("hook_event_name") != "PreToolUse"
        or not has_active_research_binding(value)
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
    denial_reason: str | None = None
    if _FORBIDDEN.search(searchable) is not None:
        denial_reason = (
            "Autonomous research cannot access orders, accounts, positions, or assets."
        )
    elif _violates_write_boundary(value):
        denial_reason = "Autonomous research writes are limited to the current ActionContract directory."
    if denial_reason is None:
        return 0
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": denial_reason,
            }
        }
    )
    return 0


def _violates_write_boundary(value: dict[str, object] | object) -> bool:
    if not isinstance(value, dict):
        return True
    tool_name = value.get("tool_name")
    tool_input = value.get("tool_input")
    if not isinstance(tool_input, dict):
        return (
            isinstance(tool_name, str)
            and _normalized_tool_name(tool_name) in _WRITE_TOOLS
        )
    normalized_tool = _normalized_tool_name(tool_name) if isinstance(tool_name, str) else ""
    if normalized_tool in {
        "bash",
        "exec_command",
    }:
        command = tool_input.get("cmd") or tool_input.get("command")
        return not isinstance(command, str) or not _shell_is_allowlisted(command)
    if normalized_tool.startswith("mcp__"):
        return True
    if normalized_tool not in _WRITE_TOOLS:
        return normalized_tool not in _SAFE_TOOLS
    action = next_action_from_bound_program(value)
    if not isinstance(action, dict):
        return True
    allowed_source = action.get("allowedWriteDirectory")
    if not isinstance(allowed_source, str):
        return True
    repository_root = Path(
        os.environ.get(
            "QUANT_RESEARCH_REPOSITORY_ROOT",
            str(Path(__file__).resolve().parents[2]),
        )
    ).resolve()
    allowed = (repository_root / allowed_source).resolve()
    paths: list[str] = []
    for name in ("file_path", "path"):
        candidate = tool_input.get(name)
        if isinstance(candidate, str):
            paths.append(candidate)
    patch = tool_input.get("patch") or tool_input.get("input")
    if isinstance(patch, str):
        paths.extend(
            match.group(1)
            for match in re.finditer(
                r"^\*\*\* (?:Add|Update|Delete) File: (.+)$",
                patch,
                re.MULTILINE,
            )
        )
    if not paths:
        return True
    for source in paths:
        candidate = Path(source)
        resolved = (
            candidate if candidate.is_absolute() else repository_root / candidate
        ).resolve()
        try:
            resolved.relative_to(allowed)
        except ValueError:
            return True
    return False


def _shell_is_allowlisted(command: str) -> bool:
    if re.search(r"[;&|`<>\n]|\$\(", command):
        return False
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    if not arguments:
        return False
    executable = Path(arguments[0]).name
    if executable in _READ_ONLY_COMMANDS:
        if executable == "find" and any(
            value in {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
            for value in arguments[1:]
        ):
            return False
        if executable == "sed" and any(
            value.startswith("-i") for value in arguments[1:]
        ):
            return False
        return True
    if executable == "git" and len(arguments) >= 2:
        return (
            arguments[1] in {"status", "diff", "log", "show", "rev-parse"}
            and not any(
                value == "-o" or value.startswith("--output")
                for value in arguments[2:]
            )
        )
    if executable.startswith("python"):
        scripts = [value for value in arguments[1:] if not value.startswith("-")]
        if not scripts:
            return False
        repository_root = Path(__file__).resolve().parents[2]
        quant_cli = (
            repository_root / "research/rp-001/quant_autonomous_research.py"
        ).resolve()
        program_verifier = (
            repository_root / "research/rp-001/run_program.py"
        ).resolve()
        script = Path(scripts[0]).resolve()
        script_index = arguments.index(scripts[0])
        trailing = arguments[script_index + 1 :]
        if script == quant_cli and trailing:
            return trailing[0] in {
                "status",
                "next",
                "commit-action",
                "register-development-release",
                "register-confirmation-release",
                "record-action-failure",
                "record-program-version-terminal",
            }
        if script == program_verifier:
            return trailing == ["--verify"]
        return False
    return False


def _normalized_tool_name(tool_name: str) -> str:
    return tool_name.rsplit(".", maxsplit=1)[-1].lower()


if __name__ == "__main__":
    raise SystemExit(main())
