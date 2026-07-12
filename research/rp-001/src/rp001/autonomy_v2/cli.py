"""Internal CLI boundary for Goal continuation turns."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from rp001.autonomy_v2.controller import CampaignController
from rp001.local_evidence import canonical_json_bytes


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        repository_root = arguments.repository_root.resolve(strict=True)
        controller = CampaignController(repository_root)
        if arguments.command == "bootstrap-campaign":
            output = controller.bootstrap(
                arguments.goal,
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        elif arguments.command == "status":
            output = controller.status(
                arguments.campaign_id
            ).snapshot.to_canonical_dict()
        elif arguments.command == "next":
            output = controller.next_action(arguments.campaign_id).to_canonical_dict(
                repository_root
            )
        elif arguments.command == "commit-action":
            output = controller.commit_action(
                arguments.campaign_id,
                result_path=arguments.result,
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        elif arguments.command == "register-development-release":
            output = controller.register_development_release(
                arguments.campaign_id,
                release_id=arguments.release_id,
                manifest_path=arguments.manifest,
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        elif arguments.command == "register-confirmation-release":
            output = controller.register_confirmation_release(
                arguments.campaign_id,
                release_id=arguments.release_id,
                manifest_path=arguments.manifest,
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        elif arguments.command == "record-action-failure":
            output = controller.record_action_failure(
                arguments.campaign_id,
                action_id=arguments.action_id,
                error_code=arguments.error_code,
                input_hashes=tuple(arguments.input_hash),
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        elif arguments.command == "record-program-version-terminal":
            output = controller.record_program_version_terminal(
                arguments.campaign_id,
                occurred_at=arguments.occurred_at,
            ).to_canonical_dict()
        else:
            raise ValueError("command_invalid")
    except Exception as error:
        sys.stderr.write(f"INVALID {type(error).__name__}\n")
        return 1
    sys.stdout.write(canonical_json_bytes(output).decode("utf-8") + "\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant_autonomous_research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-campaign")
    bootstrap.add_argument("--goal", type=Path, required=True)
    bootstrap.add_argument("--occurred-at", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--campaign-id", required=True)
    next_action = subparsers.add_parser("next")
    next_action.add_argument("--campaign-id", required=True)
    commit = subparsers.add_parser("commit-action")
    commit.add_argument("--campaign-id", required=True)
    commit.add_argument("--result", type=Path, required=True)
    commit.add_argument("--occurred-at", required=True)
    register = subparsers.add_parser("register-development-release")
    register.add_argument("--campaign-id", required=True)
    register.add_argument("--release-id", required=True)
    register.add_argument("--manifest", type=Path, required=True)
    register.add_argument("--occurred-at", required=True)
    confirmation = subparsers.add_parser("register-confirmation-release")
    confirmation.add_argument("--campaign-id", required=True)
    confirmation.add_argument("--release-id", required=True)
    confirmation.add_argument("--manifest", type=Path, required=True)
    confirmation.add_argument("--occurred-at", required=True)
    failure = subparsers.add_parser("record-action-failure")
    failure.add_argument("--campaign-id", required=True)
    failure.add_argument("--action-id", required=True)
    failure.add_argument("--error-code", required=True)
    failure.add_argument("--input-hash", action="append", required=True)
    failure.add_argument("--occurred-at", required=True)
    terminal = subparsers.add_parser("record-program-version-terminal")
    terminal.add_argument("--campaign-id", required=True)
    terminal.add_argument("--occurred-at", required=True)
    for command in (
        bootstrap,
        status,
        next_action,
        commit,
        register,
        confirmation,
        failure,
        terminal,
    ):
        command.add_argument("--repository-root", type=Path, required=True)
    return parser


def _mapping(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("mapping_path_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("mapping_invalid")
    if canonical_json_bytes(value) != path.read_bytes():
        raise ValueError("mapping_not_canonical")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
