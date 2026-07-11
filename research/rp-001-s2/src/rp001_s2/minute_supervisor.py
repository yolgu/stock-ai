"""Persistent execution of a verified, frozen Toss minute plan."""

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
from rp001_s2.minute_canonicalization import canonicalize_toss_collection
from rp001_s2.minute_scope_plan import (
    TossMinuteScopePlan,
    parse_toss_minute_scope_plan,
)
from rp001_s2.toss_batch_collection import (
    CredentialLoader,
    GlobalMarketDataPacer,
    PersistentTossMinuteSession,
    TossCanonicalizer,
    TossSessionFactory,
    TossMinuteBatchSummary,
    run_toss_minute_batch,
)
from rp001_s2.toss_intraday_run import (
    load_secure_toss_environment,
    open_toss_minute_session,
)
from rp001_s2.toss_retry_queue import (
    TossRetryQueueError,
    load_verified_toss_retry_queue,
)
from rp001_s2.toss_session_lease import (
    ExclusiveTossSessionLease,
    TossSessionLeaseError,
)


_MAX_PLAN_BYTES = 64 * 1024 * 1024
_DEFAULT_BATCH_SIZE = 256
_MAX_BATCH_SIZE = 4096


class MinuteSupervisorError(ValueError):
    """Stable, secret-free failure from the supervisor boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MinuteSupervisorArguments:
    plan_path: Path
    credential_file: Path
    archive_root: Path
    ledger_root: Path
    retry_queue_path: Path | None = None
    batch_size: int = _DEFAULT_BATCH_SIZE


@dataclass(frozen=True)
class MinuteSupervisorSummary:
    scope_count: int
    priority_scope_count: int
    batch_count: int
    completed_count: int
    partial_count: int
    data_unavailable_count: int
    failed_count: int
    invalid_count: int
    blocked_storage_capacity_count: int
    resumed_count: int
    total_row_count: int
    total_capture_count: int


def build_supervisor_argument_parser() -> argparse.ArgumentParser:
    """Expose paths and bounded execution settings, never credential values."""
    parser = argparse.ArgumentParser(
        description="Resume a verified frozen Toss minute plan.",
        allow_abbrev=False,
    )
    parser.add_argument("--plan", dest="plan_path", type=Path, required=True)
    parser.add_argument(
        "--credential-file",
        dest="credential_file",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--retry-queue",
        dest="retry_queue_path",
        type=Path,
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
    parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
    )
    return parser


def parse_supervisor_arguments(
    values: list[str] | None = None,
) -> MinuteSupervisorArguments:
    """Translate CLI values into the typed supervisor boundary."""
    namespace = build_supervisor_argument_parser().parse_args(values)
    return MinuteSupervisorArguments(
        plan_path=namespace.plan_path,
        credential_file=namespace.credential_file,
        archive_root=namespace.archive_root,
        ledger_root=namespace.ledger_root.resolve(),
        retry_queue_path=namespace.retry_queue_path,
        batch_size=namespace.batch_size,
    )


def run_minute_supervisor(
    arguments: MinuteSupervisorArguments,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    request_pacer: Callable[[], None] | None = None,
    free_bytes: Callable[[Path], int] | None = None,
    credential_loader: CredentialLoader = load_secure_toss_environment,
    session_factory: TossSessionFactory = open_toss_minute_session,
    canonicalizer: TossCanonicalizer = canonicalize_toss_collection,
    batch_runner: Callable[..., TossMinuteBatchSummary] = run_toss_minute_batch,
    output: TextIO = sys.stdout,
) -> MinuteSupervisorSummary:
    """Verify first, then reuse one lazy session and pacer across all batches."""
    _validate_arguments(arguments)
    plan = _load_verified_plan(arguments.plan_path)
    priority_scopes = _load_priority_scopes(plan, arguments.retry_queue_path)
    try:
        lease = ExclusiveTossSessionLease.acquire(arguments.credential_file)
    except TossSessionLeaseError as error:
        raise MinuteSupervisorError(error.code) from None
    summaries: list[TossMinuteBatchSummary] = []
    batches = _ordered_batches(plan, arguments.batch_size, priority_scopes)
    try:
        pacer = (
            request_pacer
            if request_pacer is not None
            else GlobalMarketDataPacer()
        )
        session = PersistentTossMinuteSession(
            credential_file=arguments.credential_file,
            credential_loader=credential_loader,
            session_factory=session_factory,
            clock=clock,
            request_pacer=pacer,
        )
        try:
            executed_scope_count = 0
            for batch_index, scopes in enumerate(batches):
                try:
                    summary = batch_runner(
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
                        shared_session=session,
                    )
                except Exception:
                    raise MinuteSupervisorError(
                        "batch_execution_failed"
                    ) from None
                summaries.append(summary)
                _write_batch_progress(
                    output,
                    batch_index=batch_index,
                    scope_start_index=executed_scope_count,
                    scope_count=len(scopes),
                    priority_batch=(batch_index == 0 and bool(priority_scopes)),
                    summary=summary,
                )
                executed_scope_count += len(scopes)
        finally:
            session.close()
    finally:
        lease.close()

    return _aggregate_summary(
        plan.scope_count,
        len(priority_scopes),
        summaries,
    )


def main(values: list[str] | None = None) -> int:
    """Run the path-only CLI and emit only stable, secret-free JSON."""
    arguments = parse_supervisor_arguments(values)
    try:
        summary = run_minute_supervisor(arguments)
    except MinuteSupervisorError as error:
        sys.stderr.write(
            _canonical_json(
                {
                    "eventType": "toss_minute_supervisor_failed",
                    "errorCode": error.code,
                }
            )
            + "\n"
        )
        return 1
    sys.stdout.write(
        _canonical_json(
            {
                "eventType": "toss_minute_supervisor_terminal",
                "scopeCount": summary.scope_count,
                "priorityScopeCount": summary.priority_scope_count,
                "batchCount": summary.batch_count,
                "completedCount": summary.completed_count,
                "partialCount": summary.partial_count,
                "dataUnavailableCount": summary.data_unavailable_count,
                "failedCount": summary.failed_count,
                "invalidCount": summary.invalid_count,
                "blockedStorageCapacityCount": (
                    summary.blocked_storage_capacity_count
                ),
                "resumedCount": summary.resumed_count,
                "totalRowCount": summary.total_row_count,
                "totalCaptureCount": summary.total_capture_count,
            }
        )
        + "\n"
    )
    return 0


def _validate_arguments(arguments: object) -> None:
    if not isinstance(arguments, MinuteSupervisorArguments):
        raise MinuteSupervisorError("supervisor_arguments_invalid")
    if any(
        not isinstance(path, Path)
        for path in (
            arguments.plan_path,
            arguments.credential_file,
            arguments.archive_root,
            arguments.ledger_root,
        )
    ):
        raise MinuteSupervisorError("supervisor_arguments_invalid")
    if arguments.retry_queue_path is not None and not isinstance(
        arguments.retry_queue_path,
        Path,
    ):
        raise MinuteSupervisorError("supervisor_arguments_invalid")
    if not arguments.ledger_root.is_absolute():
        raise MinuteSupervisorError("supervisor_arguments_invalid")
    if (
        isinstance(arguments.batch_size, bool)
        or not isinstance(arguments.batch_size, int)
        or not 1 <= arguments.batch_size <= _MAX_BATCH_SIZE
    ):
        raise MinuteSupervisorError("supervisor_arguments_invalid")


def _load_verified_plan(path: Path) -> TossMinuteScopePlan:
    sidecar_path = Path(f"{path}.sha256")
    try:
        if path.is_symlink() or sidecar_path.is_symlink():
            raise ValueError
        source = path.read_bytes()
        if not source or len(source) > _MAX_PLAN_BYTES:
            raise ValueError
        expected_sidecar = f"{hashlib.sha256(source).hexdigest()}\n".encode(
            "ascii"
        )
        if sidecar_path.read_bytes() != expected_sidecar:
            raise ValueError
        if path.read_bytes() != source:
            raise ValueError
        return parse_toss_minute_scope_plan(source)
    except (OSError, ValueError):
        raise MinuteSupervisorError("plan_verification_failed") from None


def _load_priority_scopes(
    plan: TossMinuteScopePlan,
    retry_queue_path: Path | None,
) -> tuple[CollectionScope, ...]:
    if retry_queue_path is None:
        return ()
    try:
        queue = load_verified_toss_retry_queue(retry_queue_path)
    except TossRetryQueueError:
        raise MinuteSupervisorError("retry_queue_verification_failed") from None
    scope_by_key = {scope.acquisition_key: scope for scope in plan.scopes}
    minute_keys = queue.minute_acquisition_keys
    if len(minute_keys) > _MAX_BATCH_SIZE:
        raise MinuteSupervisorError("retry_queue_verification_failed")
    try:
        return tuple(scope_by_key[key] for key in minute_keys)
    except KeyError:
        raise MinuteSupervisorError("retry_queue_verification_failed") from None


def _ordered_batches(
    plan: TossMinuteScopePlan,
    batch_size: int,
    priority_scopes: tuple[CollectionScope, ...],
) -> tuple[tuple[CollectionScope, ...], ...]:
    priority_keys = {scope.acquisition_key for scope in priority_scopes}
    remaining = tuple(
        scope for scope in plan.scopes if scope.acquisition_key not in priority_keys
    )
    batches = tuple(
        remaining[index : index + batch_size]
        for index in range(0, len(remaining), batch_size)
    )
    if not priority_scopes:
        return batches
    return (priority_scopes, *batches)


def _write_batch_progress(
    output: TextIO,
    *,
    batch_index: int,
    scope_start_index: int,
    scope_count: int,
    priority_batch: bool,
    summary: object,
) -> None:
    body = {
        "batchIndex": batch_index,
        "scopeStartIndex": scope_start_index,
        "scopeEndExclusive": scope_start_index + scope_count,
        "scopeCount": scope_count,
        "priorityBatch": priority_batch,
        "completedCount": _summary_count(summary, "completed_count"),
        "partialCount": _summary_count(summary, "partial_count"),
        "dataUnavailableCount": _summary_count(
            summary,
            "data_unavailable_count",
        ),
        "failedCount": _summary_count(summary, "failed_count"),
        "invalidCount": _summary_count(summary, "invalid_count"),
        "blockedStorageCapacityCount": _summary_count(
            summary,
            "blocked_storage_capacity_count",
        ),
        "resumedCount": _summary_count(summary, "resumed_count"),
        "totalRowCount": _summary_count(summary, "total_row_count"),
        "totalCaptureCount": _summary_count(summary, "total_capture_count"),
    }
    output.write(_canonical_json(body) + "\n")
    output.flush()


def _aggregate_summary(
    scope_count: int,
    priority_scope_count: int,
    summaries: list[TossMinuteBatchSummary],
) -> MinuteSupervisorSummary:
    return MinuteSupervisorSummary(
        scope_count=scope_count,
        priority_scope_count=priority_scope_count,
        batch_count=len(summaries),
        completed_count=_sum_field(summaries, "completed_count"),
        partial_count=_sum_field(summaries, "partial_count"),
        data_unavailable_count=_sum_field(
            summaries,
            "data_unavailable_count",
        ),
        failed_count=_sum_field(summaries, "failed_count"),
        invalid_count=_sum_field(summaries, "invalid_count"),
        blocked_storage_capacity_count=_sum_field(
            summaries,
            "blocked_storage_capacity_count",
        ),
        resumed_count=_sum_field(summaries, "resumed_count"),
        total_row_count=_sum_field(summaries, "total_row_count"),
        total_capture_count=_sum_field(summaries, "total_capture_count"),
    )


def _sum_field(summaries: list[object], name: str) -> int:
    return sum(_summary_count(summary, name) for summary in summaries)


def _summary_count(summary: object, name: str) -> int:
    value = getattr(summary, name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MinuteSupervisorError("batch_summary_invalid")
    return value


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
