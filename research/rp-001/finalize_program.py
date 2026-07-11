from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import NoReturn, Protocol, TextIO, cast

# Verification is read-only, including Python's module cache behavior.
sys.dont_write_bytecode = True

from rp001.local_evidence import canonical_json_bytes
from rp001.program_completion import (
    PUBLIC_COMPLETION_ERROR_CODES,
    ProgramCompletionError,
    ProgramCompletionService,
)


class CompletionSummary(Protocol):
    def to_canonical_dict(self) -> Mapping[str, object]: ...


class CompletionService(Protocol):
    def finalize(self, completed_at: str) -> CompletionSummary: ...

    def verify(self) -> CompletionSummary: ...


CompletionServiceFactory = Callable[[Path], CompletionService]


class FinalizeProgramCliError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise FinalizeProgramCliError("INVALID_ARGUMENTS")


def default_repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(
        description="Finalize or verify the RP-001 completion package.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--finalize", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--completed-at")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=default_repository_root(),
    )
    return parser


def _default_service_factory(repository_root: Path) -> CompletionService:
    return ProgramCompletionService(repository_root)


def _require_valid_mode_arguments(arguments: argparse.Namespace) -> None:
    if arguments.finalize and arguments.completed_at is None:
        raise FinalizeProgramCliError("INVALID_ARGUMENTS")
    if arguments.verify and arguments.completed_at is not None:
        raise FinalizeProgramCliError("INVALID_ARGUMENTS")


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: CompletionServiceFactory | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        arguments = build_argument_parser().parse_args(argv)
        _require_valid_mode_arguments(arguments)
        factory = service_factory or _default_service_factory
        service = factory(arguments.repository_root)
        if arguments.finalize:
            summary = service.finalize(cast(str, arguments.completed_at))
        else:
            summary = service.verify()
        output_stream.write(
            canonical_json_bytes(summary.to_canonical_dict()).decode("utf-8")
            + "\n"
        )
        return 0
    except FinalizeProgramCliError as error:
        error_stream.write(f"INVALID {error.code}\n")
        return 1
    except ProgramCompletionError as error:
        code = (
            error.code
            if error.code in PUBLIC_COMPLETION_ERROR_CODES
            else "INTERNAL_COMPLETION_ERROR"
        )
        error_stream.write(f"INVALID {code}\n")
        return 1
    except Exception:
        error_stream.write("INVALID INTERNAL_COMPLETION_ERROR\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
