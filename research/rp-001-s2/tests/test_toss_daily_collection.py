from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from rp001.toss_research_collector import (
    CandleCollection,
    CandleRow,
    CanonicalScalar,
    RawHttpCapture,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.daily_archive_storage import CanonicalDailyBar
from rp001_s2.toss_daily_canonicalization import DailyCanonicalizationError
from rp001_s2.toss_daily_collection import (
    DailyBatchScopeStatus,
    DailyMarketDataPacer,
    TossDailyRunError,
    run_toss_daily_batch,
)


_FREE_BYTES = 100 * 1024**3


def _scope(adjustment_mode: str = "native") -> CollectionScope:
    return CollectionScope(
        provider="toss",
        feed="provider_all",
        instrument_id="TSLA",
        symbol="TSLA",
        interval="1d",
        start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        adjustment_mode=adjustment_mode,
        session_scope="provider_all",
        sample_role=SampleRole.SEEN,
    )


def _capture(adjusted: bool, *, status: int = 200) -> RawHttpCapture:
    body = json.dumps(
        {
            "result": {
                "candles": [
                    {
                        "timestamp": "2026-07-01T04:00:00Z",
                        "openPrice": "100",
                        "highPrice": "103",
                        "lowPrice": "99",
                        "closePrice": "102",
                        "volume": "1000",
                        "currency": "USD",
                    }
                ],
                "nextBefore": None,
            }
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return RawHttpCapture(
        endpoint_id="daily_candles_v1",
        method="GET",
        sanitized_url="https://openapi.tossinvest.com/api/v1/candles",
        query=(
            ("symbol", "TSLA"),
            ("interval", "1d"),
            ("count", "200"),
            ("adjusted", str(adjusted).lower()),
            ("before", "2026-07-03T00:00:00Z"),
        ),
        status=status,
        headers=(("content-type", "application/json"),),
        received_at="2026-07-04T00:00:00Z",
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _collection(scope: CollectionScope) -> CandleCollection:
    scalar = lambda value: CanonicalScalar("decimal_string", value)
    return CandleCollection(
        symbol=scope.symbol,
        adjusted=scope.adjustment_mode == "adjusted",
        start=scope.start_at.date(),
        end=scope.end_at.date() - date.resolution,
        session_timezone="America/New_York",
        provider_session_membership="not_documented",
        analysis_rows=(
            CandleRow(
                timestamp="2026-07-01T04:00:00Z",
                open_price=scalar("100"),
                high_price=scalar("103"),
                low_price=scalar("99"),
                close_price=scalar("102"),
                volume=scalar("1000"),
                currency="USD",
            ),
        ),
        audit_only_rows=(),
        captures=(_capture(scope.adjustment_mode == "adjusted"),),
    )


def _canonicalize(
    scope: CollectionScope,
    collection: CandleCollection,
) -> tuple[CanonicalDailyBar, ...]:
    capture = collection.captures[0]
    row = collection.analysis_rows[0]
    return (
        CanonicalDailyBar(
            provider=scope.provider,
            feed=scope.feed,
            instrument_id=scope.instrument_id,
            symbol=scope.symbol,
            source_timestamp=row.timestamp,
            session_date="2026-07-01",
            received_at_utc=capture.received_at,
            research_available_at_utc=capture.received_at,
            session_type=scope.session_scope,
            currency=row.currency,
            adjustment_mode=scope.adjustment_mode,
            numeric_fidelity="decimal_string_lexeme",
            quality_status="verified_provider_response",
            open_price=row.open_price,
            high_price=row.high_price,
            low_price=row.low_price,
            close_price=row.close_price,
            volume=row.volume,
            raw_body_sha256=capture.body_sha256,
            capture_ordinal=0,
            source_row_index=0,
            occurrences=((capture.body_sha256, 0, 0),),
        ),
    )


class _Session:
    def __init__(self) -> None:
        self.collected: list[CollectionScope] = []
        self.closed = False

    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: object,
    ) -> CandleCollection:
        self.collected.append(scope)
        request_pacer()
        return _collection(scope)

    def close(self) -> None:
        self.closed = True


class TossDailyCollectionTest(unittest.TestCase):
    def test_default_pacer_is_exactly_point_one_requests_per_second(self) -> None:
        values = iter((0.0, 0.0, 10.0))
        sleeps: list[float] = []
        pacer = DailyMarketDataPacer(
            monotonic=lambda: next(values),
            sleeper=sleeps.append,
        )

        pacer()
        pacer()

        self.assertEqual(pacer.requests_per_second, 0.1)
        self.assertEqual(sleeps, [10.0])

    def test_two_scopes_share_one_authentication_and_append_terminal_events(self) -> None:
        sessions: list[_Session] = []
        credential_loads: list[Path] = []

        def load(path: Path) -> dict[str, str]:
            credential_loads.append(path)
            return {"first": "value", "second": "value"}

        def open_session(**_arguments: object) -> _Session:
            session = _Session()
            sessions.append(session)
            return session

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "credentials.json"
            credential.write_text("not-read-by-fake", encoding="utf-8")

            summary = run_toss_daily_batch(
                (_scope("native"), _scope("adjusted")),
                credential_file=credential,
                archive_root=root / "archives",
                ledger_root=(root / "ledger").resolve(),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=lambda: None,
                free_bytes=lambda _path: _FREE_BYTES,
                credential_loader=load,
                session_factory=open_session,
                canonicalizer=_canonicalize,
            )

            self.assertEqual(summary.completed_count, 0)
            self.assertEqual(summary.partial_count, 2)
            self.assertEqual(len(credential_loads), 1)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(len(sessions[0].collected), 2)
            self.assertTrue(sessions[0].closed)
            self.assertEqual(
                len(tuple((root / "ledger/events").glob("*.json"))),
                2,
            )
            self.assertEqual(len(tuple((root / "archives").glob("*/manifest.json"))), 2)

    def test_verified_resume_does_not_load_credentials_or_call_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "credentials.json"
            credential.write_text("fixture", encoding="utf-8")
            arguments = {
                "credential_file": credential,
                "archive_root": root / "archives",
                "ledger_root": (root / "ledger").resolve(),
                "clock": lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                "request_pacer": lambda: None,
                "free_bytes": lambda _path: _FREE_BYTES,
                "canonicalizer": _canonicalize,
            }
            run_toss_daily_batch(
                (_scope(),),
                credential_loader=lambda _path: {"one": "value"},
                session_factory=lambda **_arguments: _Session(),
                **arguments,
            )

            resumed = run_toss_daily_batch(
                (_scope(),),
                credential_loader=lambda _path: self.fail("credentials loaded"),
                session_factory=lambda **_arguments: self.fail("session opened"),
                **arguments,
            )

            self.assertEqual(resumed.resumed_count, 1)
            self.assertEqual(resumed.terminals[0].status, DailyBatchScopeStatus.PARTIAL)

    def test_failure_capture_is_archived_and_scope_remains_failed(self) -> None:
        capture = _capture(False, status=500)

        class FailingSession(_Session):
            def collect(
                self,
                scope: CollectionScope,
                *,
                request_pacer: object,
            ) -> CandleCollection:
                del scope, request_pacer
                raise TossDailyRunError("HTTP_STATUS", captures=(capture,))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "credentials.json"
            credential.write_text("fixture", encoding="utf-8")

            summary = run_toss_daily_batch(
                (_scope(),),
                credential_file=credential,
                archive_root=root / "archives",
                ledger_root=(root / "ledger").resolve(),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=lambda: None,
                free_bytes=lambda _path: _FREE_BYTES,
                credential_loader=lambda _path: {"one": "value"},
                session_factory=lambda **_arguments: FailingSession(),
                canonicalizer=_canonicalize,
            )

            self.assertEqual(summary.failed_count, 1)
            evidence = summary.terminals[0].failure_evidence
            self.assertIsNotNone(evidence)
            self.assertTrue(evidence.manifest_path.is_file())

    def test_canonicalization_failure_preserves_every_collected_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "credentials.json"
            credential.write_text("fixture", encoding="utf-8")

            summary = run_toss_daily_batch(
                (_scope(),),
                credential_file=credential,
                archive_root=root / "archives",
                ledger_root=(root / "ledger").resolve(),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=lambda: None,
                free_bytes=lambda _path: _FREE_BYTES,
                credential_loader=lambda _path: {"one": "value"},
                session_factory=lambda **_arguments: _Session(),
                canonicalizer=lambda _scope, _collection: (
                    (_ for _ in ()).throw(
                        DailyCanonicalizationError("conflicting_duplicate")
                    )
                ),
            )

            terminal = summary.terminals[0]
            self.assertEqual(terminal.status, DailyBatchScopeStatus.INVALID)
            self.assertEqual(terminal.capture_count, 1)
            self.assertIsNotNone(terminal.failure_evidence)

    def test_storage_failure_retains_capture_count_even_without_capacity_for_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credential = root / "credentials.json"
            credential.write_text("fixture", encoding="utf-8")

            summary = run_toss_daily_batch(
                (_scope(),),
                credential_file=credential,
                archive_root=root / "archives",
                ledger_root=(root / "ledger").resolve(),
                clock=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
                request_pacer=lambda: None,
                free_bytes=lambda _path: 0,
                credential_loader=lambda _path: {"one": "value"},
                session_factory=lambda **_arguments: _Session(),
                canonicalizer=_canonicalize,
            )

            terminal = summary.terminals[0]
            self.assertEqual(
                terminal.status,
                DailyBatchScopeStatus.BLOCKED_STORAGE_CAPACITY,
            )
            self.assertEqual(terminal.capture_count, 1)


if __name__ == "__main__":
    unittest.main()
