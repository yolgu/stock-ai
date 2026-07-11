"""Full-scope execution boundary for the frozen registered Toss daily plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from rp001_s2.archive_contract import CollectionScope
from rp001_s2.daily_scope_plan import (
    DailyPlanExecutionState,
    TossDailyScopePlan,
    parse_daily_scope_plan,
)
from rp001_s2.toss_daily_canonicalization import (
    canonicalize_toss_daily_collection,
)
from rp001_s2.toss_daily_collection import (
    Canonicalizer,
    CredentialLoader,
    DailyMarketDataPacer,
    SessionFactory,
    TossDailyBatchSummary,
    open_toss_daily_session,
    run_toss_daily_batch,
)
from rp001_s2.toss_intraday_run import load_secure_toss_environment
from rp001_s2.toss_retry_queue import (
    TossRetryQueueError,
    load_verified_toss_retry_queue,
)
from rp001_s2.toss_session_lease import (
    ExclusiveTossSessionLease,
    TossSessionLeaseError,
)


_REGISTERED_48_DEFERRED_PLAN_SHA256 = (
    "6982a5145ef9cb2fc698db1dfe9b371ce003aaa63089fbb2c5905b72a36d47ec"
)
_EXPECTED_INSTRUMENT_COUNT = 48
_EXPECTED_SCOPE_COUNT = 96
_MAX_PLAN_BYTES = 1024 * 1024


class DailySupervisorError(ValueError):
    """Stable, secret-free failure from the daily full-scope boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DailySupervisorArguments:
    plan_path: Path
    credential_file: Path
    archive_root: Path
    ledger_root: Path
    retry_queue_path: Path | None = None


@dataclass(frozen=True)
class DailySupervisorSummary:
    plan_sha256: str
    scope_count: int
    priority_scope_count: int
    terminal_count: int
    missing_scope_count: int
    completed_count: int
    partial_count: int
    data_unavailable_count: int
    failed_count: int
    invalid_count: int
    blocked_storage_capacity_count: int
    resumed_count: int
    total_row_count: int
    total_capture_count: int


@dataclass(frozen=True)
class _VerifiedDailyPlan:
    plan: TossDailyScopePlan
    sha256: str


def build_daily_supervisor_argument_parser() -> argparse.ArgumentParser:
    """Expose only complete-plan and local boundary paths."""
    parser = argparse.ArgumentParser(
        description="Run the frozen registered Toss daily plan in full.",
        allow_abbrev=False,
    )
    parser.add_argument("--plan", dest="plan_path", type=Path, required=True)
    parser.add_argument(
        "--retry-queue",
        dest="retry_queue_path",
        type=Path,
    )
    parser.add_argument(
        "--credential-file",
        dest="credential_file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--archive-root",
        dest="archive_root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--ledger-root",
        dest="ledger_root",
        type=Path,
        required=True,
    )
    return parser


def parse_daily_supervisor_arguments(
    values: list[str] | None = None,
) -> DailySupervisorArguments:
    namespace = build_daily_supervisor_argument_parser().parse_args(values)
    return DailySupervisorArguments(
        plan_path=namespace.plan_path,
        retry_queue_path=namespace.retry_queue_path,
        credential_file=namespace.credential_file,
        archive_root=namespace.archive_root,
        ledger_root=namespace.ledger_root.resolve(),
    )


def run_daily_supervisor(
    arguments: DailySupervisorArguments,
    *,
    expected_plan_sha256: str = _REGISTERED_48_DEFERRED_PLAN_SHA256,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    request_pacer: Callable[[], None] | None = None,
    free_bytes: Callable[[Path], int] | None = None,
    credential_loader: CredentialLoader = load_secure_toss_environment,
    session_factory: SessionFactory = open_toss_daily_session,
    canonicalizer: Canonicalizer = canonicalize_toss_daily_collection,
    batch_runner: Callable[..., TossDailyBatchSummary] = run_toss_daily_batch,
    output: TextIO = sys.stdout,
) -> DailySupervisorSummary:
    """Verify the full plan first, then execute all 96 scopes exactly once."""
    _validate_arguments(arguments, expected_plan_sha256)
    verified_plan = _load_verified_plan(
        arguments.plan_path,
        expected_plan_sha256,
    )
    priority_scopes = _load_priority_scopes(
        verified_plan.plan,
        arguments.retry_queue_path,
    )
    scopes = _ordered_scopes(verified_plan.plan, priority_scopes)
    try:
        lease = ExclusiveTossSessionLease.acquire(arguments.credential_file)
    except TossSessionLeaseError as error:
        raise DailySupervisorError(error.code) from None
    try:
        pacer = (
            request_pacer
            if request_pacer is not None
            else DailyMarketDataPacer(requests_per_second=4.0)
        )
        try:
            batch_summary = batch_runner(
                scopes,
                credential_file=arguments.credential_file,
                archive_root=arguments.archive_root,
                ledger_root=arguments.ledger_root,
                clock=clock,
                request_pacer=pacer,
                free_bytes=free_bytes,
                credential_loader=credential_loader,
                session_factory=session_factory,
                canonicalizer=canonicalizer,
            )
        except Exception:
            raise DailySupervisorError("daily_batch_execution_failed") from None
        summary = _verified_summary(
            verified_plan,
            priority_scopes,
            scopes,
            batch_summary,
        )
        output.write(_canonical_json(_summary_body(summary)) + "\n")
        output.flush()
        return summary
    finally:
        lease.close()


def main(values: list[str] | None = None) -> int:
    arguments = parse_daily_supervisor_arguments(values)
    try:
        run_daily_supervisor(arguments)
    except DailySupervisorError as error:
        sys.stderr.write(
            _canonical_json(
                {
                    "eventType": "toss_daily_supervisor_failed",
                    "errorCode": error.code,
                }
            )
            + "\n"
        )
        return 1
    return 0


def _validate_arguments(
    arguments: object,
    expected_plan_sha256: object,
) -> None:
    if not isinstance(arguments, DailySupervisorArguments):
        raise DailySupervisorError("daily_supervisor_arguments_invalid")
    if any(
        not isinstance(path, Path)
        for path in (
            arguments.plan_path,
            arguments.credential_file,
            arguments.archive_root,
            arguments.ledger_root,
        )
    ):
        raise DailySupervisorError("daily_supervisor_arguments_invalid")
    if (
        not arguments.ledger_root.is_absolute()
        or (
            arguments.retry_queue_path is not None
            and not isinstance(arguments.retry_queue_path, Path)
        )
        or not _is_sha256(expected_plan_sha256)
    ):
        raise DailySupervisorError("daily_supervisor_arguments_invalid")


def _load_verified_plan(
    path: Path,
    expected_plan_sha256: str,
) -> _VerifiedDailyPlan:
    sidecar_path = Path(f"{path}.sha256")
    try:
        if path.is_symlink() or sidecar_path.is_symlink():
            raise ValueError
        source = path.read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        if (
            not source
            or len(source) > _MAX_PLAN_BYTES
            or digest != expected_plan_sha256
            or sidecar_path.read_bytes() != f"{digest}\n".encode("ascii")
            or path.read_bytes() != source
        ):
            raise ValueError
        plan = parse_daily_scope_plan(source)
        if (
            plan.execution_state
            is not DailyPlanExecutionState.DEFERRED_UNTIL_MINUTE_COLLECTION_TERMINAL
            or plan.instrument_count != _EXPECTED_INSTRUMENT_COUNT
            or plan.scope_count != _EXPECTED_SCOPE_COUNT
        ):
            raise ValueError
        return _VerifiedDailyPlan(plan=plan, sha256=digest)
    except (OSError, ValueError):
        raise DailySupervisorError("daily_plan_verification_failed") from None


def _load_priority_scopes(
    plan: TossDailyScopePlan,
    retry_queue_path: Path | None,
) -> tuple[CollectionScope, ...]:
    if retry_queue_path is None:
        return ()
    try:
        queue = load_verified_toss_retry_queue(retry_queue_path)
        scope_by_key = {scope.acquisition_key: scope for scope in plan.scopes}
        return tuple(scope_by_key[key] for key in queue.daily_acquisition_keys)
    except (KeyError, TossRetryQueueError):
        raise DailySupervisorError("retry_queue_verification_failed") from None


def _ordered_scopes(
    plan: TossDailyScopePlan,
    priority_scopes: tuple[CollectionScope, ...],
) -> tuple[CollectionScope, ...]:
    priority_keys = {scope.acquisition_key for scope in priority_scopes}
    return (
        *priority_scopes,
        *(
            scope
            for scope in plan.scopes
            if scope.acquisition_key not in priority_keys
        ),
    )


def _verified_summary(
    verified_plan: _VerifiedDailyPlan,
    priority_scopes: tuple[CollectionScope, ...],
    executed_scopes: tuple[CollectionScope, ...],
    batch_summary: object,
) -> DailySupervisorSummary:
    terminals = getattr(batch_summary, "terminals", None)
    if not isinstance(terminals, tuple):
        raise DailySupervisorError("daily_terminal_coverage_failed")
    expected_keys = tuple(scope.acquisition_key for scope in executed_scopes)
    actual_keys = tuple(
        getattr(terminal, "acquisition_key", None) for terminal in terminals
    )
    if (
        len(expected_keys) != _EXPECTED_SCOPE_COUNT
        or len(set(expected_keys)) != _EXPECTED_SCOPE_COUNT
        or actual_keys != expected_keys
    ):
        raise DailySupervisorError("daily_terminal_coverage_failed")
    counts = {
        name: _summary_count(batch_summary, name)
        for name in (
            "completed_count",
            "partial_count",
            "data_unavailable_count",
            "failed_count",
            "invalid_count",
            "blocked_storage_capacity_count",
        )
    }
    if sum(counts.values()) != _EXPECTED_SCOPE_COUNT:
        raise DailySupervisorError("daily_terminal_coverage_failed")
    return DailySupervisorSummary(
        plan_sha256=verified_plan.sha256,
        scope_count=_EXPECTED_SCOPE_COUNT,
        priority_scope_count=len(priority_scopes),
        terminal_count=len(terminals),
        missing_scope_count=0,
        completed_count=counts["completed_count"],
        partial_count=counts["partial_count"],
        data_unavailable_count=counts["data_unavailable_count"],
        failed_count=counts["failed_count"],
        invalid_count=counts["invalid_count"],
        blocked_storage_capacity_count=counts[
            "blocked_storage_capacity_count"
        ],
        resumed_count=_summary_count(batch_summary, "resumed_count"),
        total_row_count=_summary_count(batch_summary, "total_row_count"),
        total_capture_count=_summary_count(
            batch_summary,
            "total_capture_count",
        ),
    )


def _summary_body(summary: DailySupervisorSummary) -> dict[str, object]:
    return {
        "eventType": "toss_daily_supervisor_terminal",
        "planSha256": summary.plan_sha256,
        "scopeCount": summary.scope_count,
        "priorityScopeCount": summary.priority_scope_count,
        "terminalCount": summary.terminal_count,
        "missingScopeCount": summary.missing_scope_count,
        "completedCount": summary.completed_count,
        "partialCount": summary.partial_count,
        "dataUnavailableCount": summary.data_unavailable_count,
        "failedCount": summary.failed_count,
        "invalidCount": summary.invalid_count,
        "blockedStorageCapacityCount": summary.blocked_storage_capacity_count,
        "resumedCount": summary.resumed_count,
        "totalRowCount": summary.total_row_count,
        "totalCaptureCount": summary.total_capture_count,
    }


def _summary_count(summary: object, name: str) -> int:
    value = getattr(summary, name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DailySupervisorError("daily_terminal_coverage_failed")
    return value


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
