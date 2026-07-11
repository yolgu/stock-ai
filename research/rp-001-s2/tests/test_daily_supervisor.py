from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.daily_scope_plan import (
    DailyPlanExecutionState,
    build_toss_daily_scope_plan,
    canonical_daily_plan_bytes,
)
from rp001_s2.daily_supervisor import (
    DailySupervisorArguments,
    DailySupervisorError,
    build_daily_supervisor_argument_parser,
    run_daily_supervisor,
)


class _RecordingPacer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


@dataclass(frozen=True)
class _Terminal:
    acquisition_key: str


@dataclass(frozen=True)
class _Summary:
    terminals: tuple[_Terminal, ...]
    completed_count: int
    partial_count: int = 0
    data_unavailable_count: int = 0
    failed_count: int = 0
    invalid_count: int = 0
    blocked_storage_capacity_count: int = 0
    resumed_count: int = 0
    total_row_count: int = 0
    total_capture_count: int = 0


class _Runner:
    def __init__(self, *, omit_last_terminal: bool = False) -> None:
        self.omit_last_terminal = omit_last_terminal
        self.scopes: tuple[CollectionScope, ...] = ()
        self.pacer_ids: list[int] = []

    def __call__(
        self,
        scopes: tuple[CollectionScope, ...],
        **kwargs: object,
    ) -> _Summary:
        self.scopes = scopes
        pacer = kwargs["request_pacer"]
        for _scope in scopes:
            self.pacer_ids.append(id(pacer))
            pacer()
        terminals = tuple(_Terminal(scope.acquisition_key) for scope in scopes)
        if self.omit_last_terminal:
            terminals = terminals[:-1]
        return _Summary(
            terminals=terminals,
            completed_count=len(terminals),
        )


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _build_plan(instrument_count: int = 48):
    return build_toss_daily_scope_plan(
        instruments=tuple(
            (f"ID-{index:02d}", f"S{index:02d}")
            for index in range(instrument_count)
        ),
        start_at=datetime(2016, 1, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
        instrument_master_sha256="a" * 64,
        sample_role=SampleRole.SEEN,
        execution_state=(
            DailyPlanExecutionState.DEFERRED_UNTIL_MINUTE_COLLECTION_TERMINAL
        ),
    )


def _write_plan(root: Path, instrument_count: int = 48) -> tuple[Path, str]:
    source = canonical_daily_plan_bytes(_build_plan(instrument_count))
    digest = hashlib.sha256(source).hexdigest()
    path = root / "daily-plan.json"
    path.write_bytes(source)
    Path(f"{path}.sha256").write_text(f"{digest}\n", encoding="ascii")
    return path, digest


def _write_retry_queue(
    root: Path,
    scopes: tuple[CollectionScope, ...],
) -> Path:
    items: list[dict[str, object]] = []
    for index, scope in enumerate(scopes):
        event = {
            "eventType": "toss_daily_scope_terminal",
            "payload": {
                "acquisitionKey": scope.acquisition_key,
                "scope": scope.to_canonical_body(),
            },
        }
        event_source = _canonical_json_bytes(event)
        event_path = root / f"daily-event-{index}.json"
        event_path.write_bytes(event_source)
        items.append(
            {
                "acquisitionKey": scope.acquisition_key,
                "adjustmentMode": scope.adjustment_mode,
                "endAt": scope.end_at.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "failureEvidenceManifestPath": str(root / "failure.json"),
                "interval": "1d",
                "provider": "toss",
                "reason": "separate_oauth_conflicts_with_active_minute_session",
                "retryState": "deferred_until_shared_token_boundary_or_minute_terminal",
                "sourceEventPath": str(event_path),
                "sourceEventSha256": hashlib.sha256(event_source).hexdigest(),
                "startAt": scope.start_at.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "symbol": scope.symbol,
            }
        )
    queue = {
        "createdAt": "2026-07-12T00:00:00Z",
        "groups": [
            {
                "groupId": "daily-retry",
                "itemCount": len(items),
                "items": items,
            }
        ],
        "itemCount": len(items),
        "ordersAccountsAssetsAccessed": False,
        "schemaVersion": "rp001-s2-toss-retry-queue.v1",
        "status": "open",
    }
    source = _canonical_json_bytes(queue)
    path = root / "retry-queue.json"
    path.write_bytes(source)
    Path(f"{path}.sha256").write_text(
        f"{hashlib.sha256(source).hexdigest()}\n",
        encoding="ascii",
    )
    return path


class DailySupervisorTest(unittest.TestCase):
    def test_runs_exactly_96_scopes_with_daily_retries_first_once(self) -> None:
        runner = _Runner()
        pacer = _RecordingPacer()
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path, plan_sha256 = _write_plan(root)
            plan = _build_plan()
            priority = (plan.scopes[4], plan.scopes[1])
            retry_queue_path = _write_retry_queue(root, priority)
            credential_file = root / "credentials.json"
            credential_file.write_text("fixture", encoding="utf-8")

            summary = run_daily_supervisor(
                DailySupervisorArguments(
                    plan_path=plan_path,
                    retry_queue_path=retry_queue_path,
                    credential_file=credential_file,
                    archive_root=root / "archives",
                    ledger_root=(root / "ledger").resolve(),
                ),
                expected_plan_sha256=plan_sha256,
                request_pacer=pacer,
                batch_runner=runner,
                output=output,
            )

        self.assertEqual(runner.scopes[:2], priority)
        self.assertEqual(len(runner.scopes), 96)
        self.assertEqual(
            len({scope.acquisition_key for scope in runner.scopes}),
            96,
        )
        self.assertEqual(len(set(runner.pacer_ids)), 1)
        self.assertEqual(pacer.calls, 96)
        self.assertEqual(summary.plan_sha256, plan_sha256)
        self.assertEqual(summary.scope_count, 96)
        self.assertEqual(summary.priority_scope_count, 2)
        self.assertEqual(summary.missing_scope_count, 0)
        self.assertEqual(summary.completed_count, 96)
        self.assertNotIn("credentials.json", output.getvalue())

    def test_plan_contract_and_terminal_coverage_fail_closed(self) -> None:
        for fault in ("tampered", "not_48_instruments", "missing_terminal"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan_path, plan_sha256 = _write_plan(
                    root,
                    instrument_count=47 if fault == "not_48_instruments" else 48,
                )
                if fault == "tampered":
                    plan_path.write_bytes(plan_path.read_bytes() + b"tampered")
                runner = _Runner(omit_last_terminal=fault == "missing_terminal")

                with self.assertRaisesRegex(
                    DailySupervisorError,
                    (
                        "daily_terminal_coverage_failed"
                        if fault == "missing_terminal"
                        else "daily_plan_verification_failed"
                    ),
                ):
                    run_daily_supervisor(
                        DailySupervisorArguments(
                            plan_path=plan_path,
                            credential_file=root / "credentials.json",
                            archive_root=root / "archives",
                            ledger_root=(root / "ledger").resolve(),
                        ),
                        expected_plan_sha256=plan_sha256,
                        credential_loader=lambda _path: self.fail(
                            "credentials loaded before plan verification"
                        ),
                        batch_runner=runner,
                        request_pacer=_RecordingPacer(),
                        output=io.StringIO(),
                    )

    def test_cli_has_no_partial_scope_or_secret_arguments(self) -> None:
        destinations = {
            action.dest for action in build_daily_supervisor_argument_parser()._actions
        }

        self.assertTrue(
            {
                "plan_path",
                "retry_queue_path",
                "credential_file",
                "archive_root",
                "ledger_root",
            }.issubset(destinations)
        )
        self.assertTrue(
            destinations.isdisjoint(
                {
                    "symbol",
                    "start_at",
                    "end_at",
                    "scope",
                    "client_id",
                    "client_secret",
                    "token",
                    "access_token",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
