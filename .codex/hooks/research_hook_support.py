"""Shared read-only support for dormant autonomous-research hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def next_action_from_bound_program() -> Mapping[str, object] | None:
    program_root_source = os.environ.get("RP001_AUTONOMY_PROGRAM_ROOT")
    if not program_root_source:
        return None
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
