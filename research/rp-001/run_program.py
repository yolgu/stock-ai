from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from rp001.program_contract import ProgramContractError, ProgramContractValidator


def default_program_directory() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "meta-research"
        / "objects"
        / "programs"
        / "RP-001-quantitative-market-behavior"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the RP-001 program contract.")
    parser.add_argument("--verify-foundation", action="store_true", required=True)
    parser.add_argument(
        "--program-directory",
        type=Path,
        default=default_program_directory(),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        report = ProgramContractValidator(
            arguments.program_directory
        ).validate_foundation()
    except ProgramContractError as error:
        print(f"INVALID {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            report.to_canonical_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
