"""Shared read-only support for dormant autonomous-research hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import re
from collections.abc import Mapping
from pathlib import Path


def read_hook_input() -> Mapping[str, object]:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, Mapping) else {}


def write_json(value: Mapping[str, object]) -> None:
    sys.stdout.write(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )


_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def next_action_from_bound_program(
    hook_input: Mapping[str, object] | None = None,
) -> Mapping[str, object] | None:
    program_root_source = os.environ.get("RP001_AUTONOMY_PROGRAM_ROOT")
    if not program_root_source:
        return _next_v2_campaign_action(hook_input or {})
    repository_root = Path(__file__).resolve().parents[2]
    program_root = _resolve(repository_root, program_root_source)
    output_root = _resolve(
        repository_root,
        os.environ.get(
            "RP001_AUTONOMY_PRESET_OUTPUT_ROOT",
            "research/rp-001/autonomy-runs",
        ),
    )
    confirmation_root = _resolve(
        repository_root,
        os.environ.get(
            "RP001_AUTONOMY_CONFIRMATION_RELEASE_ROOT",
            "research-data/releases/RP-001/confirmation",
        ),
    )
    command = [
        sys.executable,
        "-B",
        str(repository_root / "research" / "rp-001" / "autonomous_research.py"),
        "next",
        "--repository-root",
        str(repository_root),
        "--preset-output-root",
        str(output_root),
        "--confirmation-release-root",
        str(confirmation_root),
        "--program-root",
        str(program_root),
    ]
    for value in _live_collection_roots(repository_root):
        command.extend(("--live-collection-root", str(value)))
    environment = dict(os.environ)
    source_root = repository_root / "research" / "rp-001" / "src"
    environment["PYTHONPATH"] = str(source_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    if completed.returncode != 0:
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, Mapping) else None


def has_active_research_binding(value: Mapping[str, object]) -> bool:
    if os.environ.get("RP001_AUTONOMY_PROGRAM_ROOT"):
        return True
    binding = _v2_session_binding(value)
    return binding is not None


def _next_v2_campaign_action(
    value: Mapping[str, object],
) -> Mapping[str, object] | None:
    binding = _v2_session_binding(value)
    if binding is None:
        return None
    repository_root, campaign_id = binding
    source_repository_root = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-B",
        str(
            source_repository_root
            / "research"
            / "rp-001"
            / "quant_autonomous_research.py"
        ),
        "next",
        "--campaign-id",
        campaign_id,
        "--repository-root",
        str(repository_root),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(
        source_repository_root / "research" / "rp-001" / "src"
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    if completed.returncode != 0:
        return None
    try:
        action = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return action if isinstance(action, Mapping) else None


def _v2_session_binding(
    value: Mapping[str, object],
) -> tuple[Path, str] | None:
    session_id = value.get("session_id")
    if not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None:
        return None
    repository_root = Path(
        os.environ.get(
            "QUANT_RESEARCH_REPOSITORY_ROOT",
            str(Path(__file__).resolve().parents[2]),
        )
    ).resolve()
    activation_path = (
        repository_root
        / ".codex"
        / "state"
        / "quant-research"
        / "sessions"
        / f"{session_id}.json"
    )
    if activation_path.is_symlink() or not activation_path.is_file():
        return None
    try:
        activation = json.loads(activation_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return None
    campaign_id = activation.get("campaignId") if isinstance(activation, dict) else None
    if not isinstance(campaign_id, str):
        return None
    return repository_root, campaign_id


def _live_collection_roots(repository_root: Path) -> tuple[Path, ...]:
    source = os.environ.get("RP001_AUTONOMY_LIVE_COLLECTION_ROOTS", "")
    if not source:
        return ()
    return tuple(
        _resolve(repository_root, item)
        for item in source.split(os.pathsep)
        if item
    )


def _resolve(repository_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path
