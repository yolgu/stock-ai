"""Run the frozen RP-001-S2 Cycle 003 recovery evaluation."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from rp001_s2.cycle003_run import (
    Cycle003RunArguments,
    Cycle003RunError,
    run_cycle003_evaluation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--contract-path", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    try:
        values = parser.parse_args(argv)
        summary = run_cycle003_evaluation(
            Cycle003RunArguments(
                repository_root=values.repository_root,
                contract_path=values.contract_path,
                contract_sha256=values.contract_sha256,
                run_id=values.run_id,
            )
        )
    except (Cycle003RunError, ValueError, SystemExit) as error:
        code = (
            str(error)
            if isinstance(error, (Cycle003RunError, ValueError))
            else "invalid_arguments"
        )
        print(
            json.dumps(
                {"status": "failed", "failureCode": code},
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(dataclasses.asdict(summary), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
