"""Command-line boundary for the autonomous research controller."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from rp001.autonomy.controller import AutonomousResearchController
from rp001.local_evidence import canonical_json_bytes


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        controller = AutonomousResearchController(
            repository_root=arguments.repository_root.resolve(),
            preset_output_root=arguments.preset_output_root.resolve(),
            live_collection_roots=tuple(
                path.resolve() for path in arguments.live_collection_root
            ),
            confirmation_release_root=arguments.confirmation_release_root.resolve(),
        )
        output = _run(controller, arguments)
    except Exception as error:
        sys.stderr.write(f"INVALID {type(error).__name__}\n")
        return 1
    sys.stdout.write(canonical_json_bytes(output).decode("utf-8") + "\n")
    return 0


def _run(
    controller: AutonomousResearchController,
    arguments: argparse.Namespace,
) -> dict[str, object]:
    command = arguments.command
    if command == "bootstrap":
        snapshot = controller.bootstrap(
            goal_path=arguments.goal,
            program_spec_input_path=arguments.program_spec_input,
            program_root=arguments.program_root,
            occurred_at=arguments.occurred_at,
        )
        return snapshot.to_canonical_dict()
    if command == "bootstrap-goal":
        snapshot = controller.bootstrap_goal(
            goal_path=arguments.goal,
            program_root=arguments.program_root,
            occurred_at=arguments.occurred_at,
        )
        return snapshot.to_canonical_dict()
    if command == "status" or command == "verify":
        status = controller.verify(arguments.program_root)
        body = status.to_canonical_dict()
        if command == "verify":
            body["verified"] = True
        return body
    if command == "next":
        action = controller.next_action(arguments.program_root)
        return action.to_canonical_dict(arguments.repository_root.resolve())
    if command == "register-data-release":
        snapshot = controller.register_data_release(
            arguments.program_root,
            release_id=arguments.release_id,
            role=arguments.role,
            manifest_path=arguments.manifest,
            occurred_at=arguments.occurred_at,
        )
        return snapshot.to_canonical_dict()
    if command == "pause":
        return controller.pause(
            arguments.program_root,
            occurred_at=arguments.occurred_at,
        ).to_canonical_dict()
    if command == "resume":
        return controller.resume(
            arguments.program_root,
            occurred_at=arguments.occurred_at,
        ).to_canonical_dict()
    if command == "open-p0":
        return controller.open_p0(
            arguments.program_root,
            blocker_id=arguments.blocker_id,
            reason=arguments.reason,
            occurred_at=arguments.occurred_at,
        ).to_canonical_dict()
    if command == "validate-result":
        result = controller.validate_result(arguments.program_root, arguments.result)
        return {
            "valid": True,
            "actionId": result.event_payload["actionId"],
            "artifactCount": len(result.artifact_paths),
        }
    if command == "commit-result":
        snapshot = controller.commit_result(
            arguments.program_root,
            arguments.result,
            occurred_at=arguments.occurred_at,
        )
        return snapshot.to_canonical_dict()
    raise ValueError("command_invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autonomous_research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in (
        "bootstrap",
        "bootstrap-goal",
        "status",
        "next",
        "register-data-release",
        "pause",
        "resume",
        "open-p0",
        "validate-result",
        "commit-result",
        "verify",
    ):
        command = subparsers.add_parser(name)
        _common_arguments(
            command,
            program_root_required=(name != "bootstrap-goal"),
        )
        if name in {"bootstrap", "bootstrap-goal"}:
            command.add_argument("--goal", type=Path, required=True)
        if name == "bootstrap":
            command.add_argument("--program-spec-input", type=Path, required=True)
        if name in {"bootstrap", "bootstrap-goal"}:
            command.add_argument("--occurred-at", required=True)
        if name == "register-data-release":
            command.add_argument("--release-id", required=True)
            command.add_argument(
                "--role",
                choices=("development", "confirmation"),
                required=True,
            )
            command.add_argument("--manifest", type=Path, required=True)
            command.add_argument("--occurred-at", required=True)
        if name in {"pause", "resume"}:
            command.add_argument("--occurred-at", required=True)
        if name == "open-p0":
            command.add_argument("--blocker-id", required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--occurred-at", required=True)
        if name in {"validate-result", "commit-result"}:
            command.add_argument("--result", type=Path, required=True)
        if name == "commit-result":
            command.add_argument("--occurred-at", required=True)
    return parser


def _common_arguments(
    parser: argparse.ArgumentParser,
    *,
    program_root_required: bool,
) -> None:
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--preset-output-root", type=Path, required=True)
    parser.add_argument("--confirmation-release-root", type=Path, required=True)
    parser.add_argument("--live-collection-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--program-root",
        type=Path,
        required=program_root_required,
    )
