from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.minute_scope_plan import (
    build_toss_minute_scope_plan,
    canonical_minute_plan_bytes,
)
from rp001_s2.minute_supervisor import (
    MinuteSupervisorArguments,
    MinuteSupervisorError,
    build_supervisor_argument_parser,
    run_minute_supervisor,
)


class _RecordingPacer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


class _Session:
    def __init__(self) -> None:
        self.collected: list[CollectionScope] = []
        self.pacer_ids: list[int] = []
        self.closed = False

    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: Callable[[], None],
    ) -> object:
        self.collected.append(scope)
        self.pacer_ids.append(id(request_pacer))
        request_pacer()
        return object()

    def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class _BatchSummary:
    completed_count: int
    partial_count: int = 0
    data_unavailable_count: int = 0
    failed_count: int = 0
    invalid_count: int = 0
    resumed_count: int = 0
    total_row_count: int = 0
    total_capture_count: int = 0


class _BatchRunner:
    def __init__(self) -> None:
        self.session_ids: list[int] = []
        self.pacer_ids: list[int] = []
        self.batches: list[tuple[CollectionScope, ...]] = []

    def __call__(self, scopes: tuple[CollectionScope, ...], **kwargs: object) -> _BatchSummary:
        session = kwargs["shared_session"]
        pacer = kwargs["request_pacer"]
        self.session_ids.append(id(session))
        self.pacer_ids.append(id(pacer))
        self.batches.append(scopes)
        for scope in scopes:
            session.collect(scope)
        return _BatchSummary(completed_count=len(scopes))


def _write_plan(root: Path) -> Path:
    plan = build_toss_minute_scope_plan(
        instruments=(("US-AAPL", "AAPL"), ("US-MSFT", "MSFT")),
        start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        instrument_master_sha256="a" * 64,
        sample_role=SampleRole.SEEN,
    )
    source = canonical_minute_plan_bytes(plan)
    path = root / "plan.json"
    path.write_bytes(source)
    Path(f"{path}.sha256").write_text(
        f"{hashlib.sha256(source).hexdigest()}\n",
        encoding="ascii",
    )
    return path


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_retry_queue(
    root: Path,
    *,
    minute_scopes: tuple[CollectionScope, ...],
    out_of_plan: bool = False,
) -> Path:
    items: list[dict[str, object]] = []
    for index, scope in enumerate(minute_scopes):
        acquisition_key = (
            "f" * 64 if out_of_plan and index == 0 else scope.acquisition_key
        )
        event = {
            "eventType": "toss_minute_scope_terminal",
            "payload": {
                "acquisitionKey": acquisition_key,
                "scope": scope.to_canonical_body(),
            },
        }
        if out_of_plan and index == 0:
            event["payload"]["scope"] = {
                **scope.to_canonical_body(),
                "instrumentId": "outside-plan",
            }
        event_source = _canonical_json_bytes(event)
        event_path = root / f"minute-event-{index}.json"
        event_path.write_bytes(event_source)
        items.append(
            {
                "acquisitionKey": acquisition_key,
                "adjustmentMode": scope.adjustment_mode,
                "endAt": scope.end_at.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "interval": "1m",
                "provider": "toss",
                "reason": "concurrent_oauth_invalidated_active_token",
                "retryState": "ready_after_next_minute_batch_reauthentication",
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
                "groupId": "minute-retry",
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


class MinuteSupervisorTest(unittest.TestCase):
    def test_verified_retry_scopes_run_first_once_then_the_whole_plan(self) -> None:
        sessions: list[_Session] = []
        batch_runner = _BatchRunner()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _write_plan(root)
            plan = build_toss_minute_scope_plan(
                instruments=(("US-AAPL", "AAPL"), ("US-MSFT", "MSFT")),
                start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
                instrument_master_sha256="a" * 64,
                sample_role=SampleRole.SEEN,
            )
            priority_scopes = (plan.scopes[2], plan.scopes[5])
            retry_queue_path = _write_retry_queue(
                root,
                minute_scopes=priority_scopes,
            )
            credential_path = root / "credentials.json"
            credential_path.write_text("fixture", encoding="utf-8")

            summary = run_minute_supervisor(
                MinuteSupervisorArguments(
                    plan_path=plan_path,
                    retry_queue_path=retry_queue_path,
                    credential_file=credential_path,
                    archive_root=root / "archives",
                    ledger_root=(root / "ledger").resolve(),
                    batch_size=3,
                ),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=_RecordingPacer(),
                credential_loader=lambda _path: {
                    "TOSS_CLIENT_ID": "identifier",
                    "TOSS_CLIENT_SECRET": "private-value",
                },
                session_factory=lambda **_kwargs: (
                    sessions.append(_Session()) or sessions[-1]
                ),
                batch_runner=batch_runner,
                output=io.StringIO(),
            )

        flattened = tuple(scope for batch in batch_runner.batches for scope in batch)
        self.assertEqual(batch_runner.batches[0], priority_scopes)
        self.assertEqual(len(flattened), plan.scope_count)
        self.assertEqual(
            len({scope.acquisition_key for scope in flattened}),
            plan.scope_count,
        )
        self.assertEqual(summary.priority_scope_count, 2)
        self.assertEqual(summary.scope_count, plan.scope_count)

    def test_retry_queue_tamper_is_rejected_before_credentials(self) -> None:
        for fault in ("queue_sidecar", "source_event", "outside_plan"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan_path = _write_plan(root)
                plan = build_toss_minute_scope_plan(
                    instruments=(("US-AAPL", "AAPL"), ("US-MSFT", "MSFT")),
                    start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                    end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
                    instrument_master_sha256="a" * 64,
                    sample_role=SampleRole.SEEN,
                )
                retry_queue_path = _write_retry_queue(
                    root,
                    minute_scopes=(plan.scopes[0],),
                    out_of_plan=fault == "outside_plan",
                )
                if fault == "queue_sidecar":
                    retry_queue_path.write_bytes(
                        retry_queue_path.read_bytes() + b"tampered"
                    )
                elif fault == "source_event":
                    (root / "minute-event-0.json").write_bytes(b"tampered")

                with self.assertRaisesRegex(
                    MinuteSupervisorError,
                    "retry_queue_verification_failed",
                ):
                    run_minute_supervisor(
                        MinuteSupervisorArguments(
                            plan_path=plan_path,
                            retry_queue_path=retry_queue_path,
                            credential_file=root / "credentials.json",
                            archive_root=root / "archives",
                            ledger_root=(root / "ledger").resolve(),
                            batch_size=3,
                        ),
                        credential_loader=lambda _path: self.fail(
                            "credentials loaded"
                        ),
                        batch_runner=_BatchRunner(),
                        output=io.StringIO(),
                    )

    def test_same_credential_file_cannot_open_a_second_supervisor(self) -> None:
        sessions: list[_Session] = []
        batch_runner = _BatchRunner()
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _write_plan(root)
            credential_path = root / "credentials.json"
            credential_path.write_text("fixture", encoding="utf-8")
            arguments = MinuteSupervisorArguments(
                plan_path=plan_path,
                credential_file=credential_path,
                archive_root=root / "archives",
                ledger_root=(root / "ledger").resolve(),
                batch_size=8,
            )
            probed = False

            def probe_singleton(
                scopes: tuple[CollectionScope, ...],
                **kwargs: object,
            ) -> _BatchSummary:
                nonlocal probed
                if not probed:
                    probed = True
                    with self.assertRaisesRegex(
                        MinuteSupervisorError,
                        "session_already_active",
                    ):
                        run_minute_supervisor(
                            arguments,
                            credential_loader=lambda _path: self.fail(
                                "second supervisor loaded credentials"
                            ),
                            batch_runner=lambda *_args, **_kwargs: self.fail(
                                "second supervisor ran a batch"
                            ),
                            output=io.StringIO(),
                        )
                return batch_runner(scopes, **kwargs)

            summary = run_minute_supervisor(
                arguments,
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=_RecordingPacer(),
                credential_loader=lambda _path: {
                    "TOSS_CLIENT_ID": "identifier",
                    "TOSS_CLIENT_SECRET": "private-value",
                },
                session_factory=lambda **_kwargs: (
                    sessions.append(_Session()) or sessions[-1]
                ),
                batch_runner=probe_singleton,
                output=output,
            )

        self.assertTrue(probed)
        self.assertEqual(summary.completed_count, 8)
        self.assertEqual(len(sessions), 1)

    def test_one_lazy_session_and_one_pacer_span_every_bounded_batch(self) -> None:
        sessions: list[_Session] = []
        credential_loads: list[Path] = []
        batch_runner = _BatchRunner()
        pacer = _RecordingPacer()
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _write_plan(root)
            credential_path = root / "credentials.json"
            credential_path.write_text("fixture", encoding="utf-8")

            summary = run_minute_supervisor(
                MinuteSupervisorArguments(
                    plan_path=plan_path,
                    credential_file=credential_path,
                    archive_root=root / "archives",
                    ledger_root=(root / "ledger").resolve(),
                    batch_size=3,
                ),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=pacer,
                credential_loader=lambda path: (
                    credential_loads.append(path)
                    or {
                        "TOSS_CLIENT_ID": "identifier",
                        "TOSS_CLIENT_SECRET": "private-value",
                    }
                ),
                session_factory=lambda **_kwargs: sessions.append(_Session()) or sessions[-1],
                batch_runner=batch_runner,
                output=output,
            )

        self.assertEqual(summary.scope_count, 8)
        self.assertEqual(summary.batch_count, 3)
        self.assertEqual(summary.completed_count, 8)
        self.assertEqual(len(credential_loads), 1)
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].closed)
        self.assertEqual(len(set(batch_runner.session_ids)), 1)
        self.assertEqual(len(set(batch_runner.pacer_ids)), 1)
        self.assertEqual(pacer.calls, 8)
        rendered = output.getvalue()
        self.assertEqual(len(rendered.splitlines()), 3)
        self.assertNotIn("private-value", rendered)
        self.assertNotIn("identifier", rendered)

    def test_plan_or_sidecar_tamper_fails_before_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = _write_plan(root)
            plan_path.write_bytes(plan_path.read_bytes() + b"tampered")

            with self.assertRaisesRegex(
                MinuteSupervisorError,
                "plan_verification_failed",
            ):
                run_minute_supervisor(
                    MinuteSupervisorArguments(
                        plan_path=plan_path,
                        credential_file=root / "credentials.json",
                        archive_root=root / "archives",
                        ledger_root=(root / "ledger").resolve(),
                        batch_size=2,
                    ),
                    clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                    credential_loader=lambda _path: self.fail("credentials loaded"),
                    batch_runner=_BatchRunner(),
                    output=io.StringIO(),
                )

    def test_cli_exposes_only_a_credential_file_not_secret_or_token_arguments(self) -> None:
        destinations = {
            action.dest for action in build_supervisor_argument_parser()._actions
        }

        self.assertIn("credential_file", destinations)
        self.assertIn("retry_queue_path", destinations)
        self.assertTrue(
            destinations.isdisjoint(
                {
                    "symbol",
                    "start_at",
                    "end_at",
                    "client_id",
                    "client_secret",
                    "token",
                    "access_token",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
