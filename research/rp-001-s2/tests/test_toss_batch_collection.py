from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, MutableMapping
from unittest.mock import patch

from rp001.local_evidence import AppendOnlyLocalLedger
from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.archive_storage import CanonicalMinuteBar
from rp001_s2.intraday_measurement import IntradayCandleCollection, MeasuredBar
from rp001_s2.minute_canonicalization import MinuteCanonicalizationError
from rp001_s2.toss_batch_collection import (
    BatchScopeStatus,
    GlobalMarketDataPacer,
    TossBatchCollectionError,
    TossMinuteBatchSummary,
    run_toss_minute_batch,
)
from rp001_s2.toss_intraday_run import IntradayRunError


_AVAILABLE_BYTES = 100 * 1024**3


def _scope(
    symbol: str = "AAPL",
    *,
    sample_role: SampleRole = SampleRole.SEEN,
    minute_offset: int = 0,
) -> CollectionScope:
    start = datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc) + timedelta(
        minutes=minute_offset
    )
    return CollectionScope(
        provider="toss",
        feed="provider_all",
        instrument_id=symbol,
        symbol=symbol,
        interval="1m",
        start_at=start,
        end_at=start + timedelta(minutes=2),
        adjustment_mode="native",
        session_scope="provider_all",
        sample_role=sample_role,
    )


def _format_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _capture(scope: CollectionScope, *, status: int = 200) -> RawHttpCapture:
    body = json.dumps(
        {"symbol": scope.symbol, "status": status},
        separators=(",", ":"),
    ).encode("utf-8")
    received_at = _format_utc(scope.start_at + timedelta(seconds=90))
    return RawHttpCapture(
        endpoint_id="minute_bars",
        method="GET",
        sanitized_url=(
            "https://openapi.tossinvest.com/api/v1/candles?"
            f"symbol={scope.symbol}"
        ),
        query=(("symbol", scope.symbol),),
        status=status,
        headers=(("content-type", "application/json"),),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _collection(
    scope: CollectionScope,
    capture: RawHttpCapture,
) -> IntradayCandleCollection:
    event_start = _format_utc(scope.start_at)
    bar_end = _format_utc(scope.start_at + timedelta(minutes=1))
    occurrence = (capture.body_sha256, 0, 0)
    measured = MeasuredBar(
        timestamp=event_start,
        normalized_instant=event_start,
        bar_end=bar_end,
        available_at=capture.received_at,
        open_price=CanonicalScalar("json_string", "100.0"),
        high_price=CanonicalScalar("json_string", "101.0"),
        low_price=CanonicalScalar("json_string", "99.0"),
        close_price=CanonicalScalar("json_string", "100.5"),
        volume=CanonicalScalar("json_string", "10.0"),
        currency="USD",
        source_body_sha256=capture.body_sha256,
        source_capture_ordinal=0,
        source_row_index=0,
        provider_order=0,
        occurrences=(occurrence,),
    )
    return IntradayCandleCollection(
        symbol=scope.symbol,
        interval="1m",
        adjusted=False,
        start_at=_format_utc(scope.start_at),
        end_at=_format_utc(scope.end_at),
        analysis_rows=(measured,),
        audit_only_rows=(),
        captures=(capture,),
        inclusive_overlap_count=0,
        requested_start_reached=True,
        completion_reason="provider_terminal",
    )


def _bar(scope: CollectionScope, capture: RawHttpCapture) -> CanonicalMinuteBar:
    event_start = _format_utc(scope.start_at)
    bar_end = _format_utc(scope.start_at + timedelta(minutes=1))
    occurrence = (capture.body_sha256, 0, 0)
    return CanonicalMinuteBar(
        provider=scope.provider,
        feed=scope.feed,
        instrument_id=scope.instrument_id,
        symbol=scope.symbol,
        source_timestamp=event_start,
        event_start_utc=event_start,
        bar_end_utc=bar_end,
        received_at_utc=capture.received_at,
        research_available_at_utc=capture.received_at,
        session_date=scope.start_at.date().isoformat(),
        session_type="provider_all_unclassified",
        currency="USD",
        adjustment_mode=scope.adjustment_mode,
        numeric_fidelity="decimal_string_lexeme",
        quality_status="verified_completed",
        open_price=CanonicalScalar("json_string", "100.0"),
        high_price=CanonicalScalar("json_string", "101.0"),
        low_price=CanonicalScalar("json_string", "99.0"),
        close_price=CanonicalScalar("json_string", "100.5"),
        volume=CanonicalScalar("json_string", "10.0"),
        raw_body_sha256=capture.body_sha256,
        capture_ordinal=0,
        source_row_index=0,
        occurrences=(occurrence,),
    )


class _RecordingPacer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


class _Dependencies:
    def __init__(
        self,
        *,
        failed_symbols: frozenset[str] = frozenset(),
        invalid_symbols: frozenset[str] = frozenset(),
        partial_symbols: frozenset[str] = frozenset(),
        unavailable_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self.failed_symbols = failed_symbols
        self.invalid_symbols = invalid_symbols
        self.partial_symbols = partial_symbols
        self.unavailable_symbols = unavailable_symbols
        self.credential_paths: list[Path] = []
        self.shard_symbols: list[str] = []
        self.pacer_ids: list[int] = []
        self.failure_captures: dict[str, RawHttpCapture] = {}
        self.session_open_count = 0
        self.session_close_count = 0

    def load_credentials(self, path: Path) -> dict[str, str]:
        self.credential_paths.append(path)
        return {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "private-value",
        }

    def open_session(
        self,
        *,
        environment: MutableMapping[str, str],
        clock: Callable[[], datetime],
    ) -> _Dependencies:
        del clock
        self.assert_ephemeral_environment(environment)
        environment.clear()
        self.session_open_count += 1
        return self

    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: Callable[[], None],
    ) -> IntradayCandleCollection:
        self.shard_symbols.append(scope.symbol)
        self.pacer_ids.append(id(request_pacer))
        request_pacer()
        capture = _capture(scope)
        if scope.symbol in self.failed_symbols:
            self.failure_captures[scope.symbol] = capture
            raise IntradayRunError("measurement_failed", captures=(capture,))
        collection = _collection(scope, capture)
        if scope.symbol in self.unavailable_symbols:
            return replace(
                collection,
                analysis_rows=(),
                requested_start_reached=False,
                completion_reason="empty_provider_terminal",
            )
        if scope.symbol in self.partial_symbols:
            return replace(
                collection,
                requested_start_reached=False,
                completion_reason="provider_terminal_before_start",
            )
        return collection

    def close(self) -> None:
        self.session_close_count += 1

    def canonicalize(
        self,
        scope: CollectionScope,
        collection: IntradayCandleCollection,
    ) -> tuple[CanonicalMinuteBar, ...]:
        if scope.symbol in self.invalid_symbols:
            raise MinuteCanonicalizationError("COLLECTION_SCOPE_MISMATCH")
        if scope.symbol in self.unavailable_symbols:
            return ()
        return (_bar(scope, collection.captures[0]),)

    def assert_ephemeral_environment(
        self,
        environment: MutableMapping[str, str],
    ) -> None:
        if environment != {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "private-value",
        }:
            raise AssertionError("unexpected credential environment")


def _run(
    root: Path,
    scopes: tuple[CollectionScope, ...],
    dependencies: _Dependencies,
    *,
    pacer: Callable[[], None] | None = None,
    free_bytes: Callable[[Path], int] = lambda _path: _AVAILABLE_BYTES,
) -> TossMinuteBatchSummary:
    archive_root = root / "archives"
    archive_root.mkdir(exist_ok=True)
    credential_path = root / "toss-credentials.local.json"
    return run_toss_minute_batch(
        scopes,
        credential_file=credential_path,
        archive_root=archive_root,
        ledger_root=root / "private-ledger",
        clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        request_pacer=pacer or _RecordingPacer(),
        free_bytes=free_bytes,
        credential_loader=dependencies.load_credentials,
        session_factory=dependencies.open_session,
        canonicalizer=dependencies.canonicalize,
    )


class TossMinuteBatchResumeTest(unittest.TestCase):
    def test_batch_uses_one_linear_ledger_transaction(self) -> None:
        scopes = tuple(
            _scope(symbol, minute_offset=index * 10)
            for index, symbol in enumerate(("AAPL", "MSFT", "NVDA"))
        )
        dependencies = _Dependencies()
        original_validate = AppendOnlyLocalLedger._validate_existing_entries
        validation_count = 0

        def count_validation(
            ledger: AppendOnlyLocalLedger,
            events_identity: object,
        ) -> tuple[int, str | None]:
            nonlocal validation_count
            validation_count += 1
            return original_validate(ledger, events_identity)

        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch.object(
                AppendOnlyLocalLedger,
                "_validate_existing_entries",
                new=count_validation,
            ),
        ):
            summary = _run(Path(temporary_directory), scopes, dependencies)

        self.assertEqual(3, summary.completed_count)
        self.assertEqual(2, validation_count)

    def test_verified_resume_reads_neither_network_nor_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = _scope()
            first_dependencies = _Dependencies()
            first = _run(root, (scope,), first_dependencies)
            resumed_dependencies = _Dependencies()

            resumed = _run(root, (scope,), resumed_dependencies)

            self.assertEqual(first.completed_count, 1)
            self.assertEqual(resumed.completed_count, 1)
            self.assertEqual(resumed.resumed_count, 1)
            self.assertEqual(resumed_dependencies.credential_paths, [])
            self.assertEqual(resumed_dependencies.shard_symbols, [])
            self.assertEqual(resumed_dependencies.session_open_count, 0)
            self.assertEqual(resumed_dependencies.session_close_count, 0)
            self.assertTrue(resumed.terminals[0].resumed_from_verified_archive)
            self.assertEqual(resumed.terminals[0].row_count, 1)
            self.assertEqual(resumed.terminals[0].capture_count, 1)

    def test_v1_archive_without_completion_is_not_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = _scope()
            first = _run(root, (scope,), _Dependencies())
            manifest_path = first.terminals[0].manifest_path
            manifest_sha256_path = first.terminals[0].manifest_sha256_path
            self.assertIsNotNone(manifest_path)
            self.assertIsNotNone(manifest_sha256_path)
            assert manifest_path is not None
            assert manifest_sha256_path is not None
            manifest = json.loads(manifest_path.read_bytes())
            manifest["schemaVersion"] = "rp001-s2-immutable-minute-archive.v1"
            manifest.pop("acquisitionCompletion")
            for artifact in manifest["rawArtifacts"]:
                artifact.pop("method")
                artifact.pop("sanitizedUrl")
                artifact.pop("query")
                artifact.pop("responseHeaders")
            source = json.dumps(
                manifest,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            manifest_path.write_bytes(source)
            manifest_sha256_path.write_text(
                f"{hashlib.sha256(source).hexdigest()}\n",
                encoding="ascii",
            )
            dependencies = _Dependencies()

            resumed = _run(root, (scope,), dependencies)

        self.assertEqual(dependencies.shard_symbols, ["AAPL"])
        self.assertEqual(len(dependencies.credential_paths), 1)
        self.assertFalse(resumed.terminals[0].resumed_from_verified_archive)
        self.assertEqual(resumed.terminals[0].status, BatchScopeStatus.INVALID)

    def test_seen_and_unseen_scopes_follow_identical_execution(self) -> None:
        snapshots: list[tuple[object, ...]] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            for index, role in enumerate(
                (
                    SampleRole.SEEN,
                    SampleRole.UNSEEN,
                    SampleRole.CONFIRMATION,
                )
            ):
                root = parent / str(index)
                root.mkdir()
                dependencies = _Dependencies()
                pacer = _RecordingPacer()

                summary = _run(
                    root,
                    (_scope(sample_role=role),),
                    dependencies,
                    pacer=pacer,
                )

                snapshots.append(
                    (
                        summary.terminals[0].status,
                        summary.total_row_count,
                        summary.total_capture_count,
                        len(summary.manifest_paths),
                        len(dependencies.credential_paths),
                        tuple(dependencies.shard_symbols),
                        pacer.calls,
                    )
                )

        self.assertEqual(len(set(snapshots)), 1)

    def test_batch_rejects_non_frozen_scope_sequence_before_side_effects(self) -> None:
        dependencies = _Dependencies()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive_root = root / "archives"
            archive_root.mkdir()

            with self.assertRaisesRegex(
                TossBatchCollectionError,
                "scopes_must_be_frozen_tuple",
            ):
                run_toss_minute_batch(
                    [_scope()],  # type: ignore[arg-type]
                    credential_file=root / "toss-credentials.local.json",
                    archive_root=archive_root,
                    ledger_root=root / "private-ledger",
                    clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                    credential_loader=dependencies.load_credentials,
                    session_factory=dependencies.open_session,
                    canonicalizer=dependencies.canonicalize,
                )

        self.assertEqual(dependencies.credential_paths, [])
        self.assertEqual(dependencies.shard_symbols, [])

    def test_failure_preserves_captures_and_continues_next_scope(self) -> None:
        scopes = (_scope("AAPL"), _scope("MSFT", minute_offset=10))
        dependencies = _Dependencies(failed_symbols=frozenset({"AAPL"}))
        pacer = _RecordingPacer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            summary = _run(
                root,
                scopes,
                dependencies,
                pacer=pacer,
            )
            failure_manifest_path = (
                summary.terminals[0].failure_evidence_manifest_path
            )
            self.assertIsNotNone(failure_manifest_path)
            assert failure_manifest_path is not None
            failure_manifest = json.loads(failure_manifest_path.read_bytes())

        self.assertEqual(
            tuple(terminal.status for terminal in summary.terminals),
            (BatchScopeStatus.FAILED, BatchScopeStatus.COMPLETED),
        )
        self.assertEqual(dependencies.shard_symbols, ["AAPL", "MSFT"])
        self.assertEqual(len(dependencies.credential_paths), 1)
        self.assertEqual(dependencies.session_open_count, 1)
        self.assertEqual(dependencies.session_close_count, 1)
        self.assertEqual(len(set(dependencies.pacer_ids)), 1)
        self.assertEqual(pacer.calls, 2)
        self.assertEqual(
            summary.terminals[0].safe_captures,
            (dependencies.failure_captures["AAPL"],),
        )
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(summary.completed_count, 1)
        self.assertEqual(
            failure_manifest["acquisitionCompletion"]["terminalStatus"],
            "failed",
        )
        self.assertEqual(
            failure_manifest["acquisitionCompletion"]["completionReason"],
            "measurement_failed",
        )
        self.assertEqual(len(failure_manifest["rawArtifacts"]), 1)
        self.assertEqual(failure_manifest["canonicalArtifact"]["rowCount"], 0)

    def test_invalid_capture_is_persisted_without_blocking_later_success(self) -> None:
        scope = _scope("AAPL")
        invalid_dependencies = _Dependencies(
            invalid_symbols=frozenset({"AAPL"}),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid = _run(root, (scope,), invalid_dependencies)
            terminal = invalid.terminals[0]
            failure_manifest_path = terminal.failure_evidence_manifest_path
            self.assertIsNotNone(failure_manifest_path)
            assert failure_manifest_path is not None
            preserved_source = failure_manifest_path.read_bytes()

            success_dependencies = _Dependencies()
            success = _run(root, (scope,), success_dependencies)

            self.assertEqual(terminal.status, BatchScopeStatus.INVALID)
            self.assertEqual(
                json.loads(preserved_source)["acquisitionCompletion"][
                    "terminalStatus"
                ],
                "invalid",
            )
            self.assertEqual(success.completed_count, 1)
            self.assertFalse(success.terminals[0].resumed_from_verified_archive)
            self.assertEqual(success_dependencies.shard_symbols, ["AAPL"])
            self.assertEqual(failure_manifest_path.read_bytes(), preserved_source)

    def test_data_unavailable_and_invalid_scope_are_terminal(self) -> None:
        unavailable = _scope("EMPTY")
        invalid = replace(_scope("AAPL", minute_offset=10), provider="alpaca")
        dependencies = _Dependencies(
            unavailable_symbols=frozenset({"EMPTY"}),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            summary = _run(
                Path(temporary_directory),
                (unavailable, invalid),
                dependencies,
            )

        self.assertEqual(
            tuple(terminal.status for terminal in summary.terminals),
            (BatchScopeStatus.DATA_UNAVAILABLE, BatchScopeStatus.INVALID),
        )
        self.assertEqual(dependencies.shard_symbols, ["EMPTY"])
        self.assertEqual(summary.data_unavailable_count, 1)
        self.assertEqual(summary.invalid_count, 1)
        self.assertTrue(summary.terminals[0].manifest_path is not None)

    def test_partial_provider_terminal_is_not_counted_as_completed(self) -> None:
        partial = _scope("AAPL")
        dependencies = _Dependencies(partial_symbols=frozenset({"AAPL"}))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            summary = _run(root, (partial,), dependencies)
            event = json.loads(summary.terminals[0].event_path.read_bytes())
            manifest_path = summary.terminals[0].manifest_path
            self.assertIsNotNone(manifest_path)
            assert manifest_path is not None
            manifest = json.loads(manifest_path.read_bytes())

            resumed_dependencies = _Dependencies()
            resumed = _run(root, (partial,), resumed_dependencies)

        terminal = summary.terminals[0]
        self.assertEqual(terminal.status, BatchScopeStatus.PARTIAL)
        self.assertEqual(terminal.row_count, 1)
        self.assertFalse(terminal.requested_start_reached)
        self.assertEqual(
            terminal.completion_reason,
            "provider_terminal_before_start",
        )
        self.assertEqual(summary.completed_count, 0)
        self.assertEqual(summary.partial_count, 1)
        self.assertFalse(event["payload"]["requestedStartReached"])
        self.assertEqual(
            event["payload"]["completionReason"],
            "provider_terminal_before_start",
        )
        self.assertEqual(event["payload"]["acquisitionTerminalStatus"], "partial")
        self.assertEqual(event["payload"]["analysisRowCount"], 1)
        self.assertEqual(event["payload"]["auditRowCount"], 0)
        self.assertEqual(event["payload"]["returnedRowCount"], 1)
        self.assertEqual(
            manifest["acquisitionCompletion"]["terminalStatus"],
            "partial",
        )
        self.assertEqual(resumed.completed_count, 0)
        self.assertEqual(resumed.partial_count, 1)
        self.assertEqual(resumed_dependencies.credential_paths, [])
        self.assertEqual(resumed_dependencies.shard_symbols, [])
        self.assertFalse(resumed.terminals[0].requested_start_reached)
        self.assertEqual(
            resumed.terminals[0].completion_reason,
            "provider_terminal_before_start",
        )


class TossMinuteBatchEvidenceTest(unittest.TestCase):
    def test_terminal_ledger_is_canonical_sidecar_bound_and_hash_chained(self) -> None:
        scopes = (_scope("AAPL"), _scope("MSFT", minute_offset=10))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            summary = _run(root, scopes, _Dependencies())
            event_paths = sorted((root / "private-ledger/events").glob("*.json"))

            self.assertEqual(len(event_paths), 2)
            previous_sha256: str | None = None
            for sequence, event_path in enumerate(event_paths, start=1):
                source = event_path.read_bytes()
                event = json.loads(source)
                actual_sha256 = hashlib.sha256(source).hexdigest()
                self.assertEqual(
                    source,
                    json.dumps(
                        event,
                        allow_nan=False,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                )
                self.assertEqual(event["sequence"], sequence)
                self.assertEqual(event["previousRecordSha256"], previous_sha256)
                self.assertEqual(
                    Path(f"{event_path}.sha256").read_text(encoding="ascii"),
                    f"{actual_sha256}\n",
                )
                self.assertEqual(
                    event["payload"]["acquisitionKey"],
                    scopes[sequence - 1].acquisition_key,
                )
                previous_sha256 = actual_sha256
            expected_event_hashes = tuple(
                Path(f"{path}.sha256").read_text(encoding="ascii").strip()
                for path in event_paths
            )

        self.assertEqual(
            tuple(terminal.event_sha256 for terminal in summary.terminals),
            expected_event_hashes,
        )
        self.assertNotIn("private-value", repr(summary))

    def test_tampered_archive_is_not_skipped_or_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = _scope()
            first = _run(root, (scope,), _Dependencies())
            manifest_path = first.terminals[0].manifest_path
            self.assertIsNotNone(manifest_path)
            assert manifest_path is not None
            manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
            tampered = manifest_path.read_bytes()
            dependencies = _Dependencies()

            resumed = _run(root, (scope,), dependencies)

            self.assertEqual(dependencies.shard_symbols, ["AAPL"])
            self.assertEqual(len(dependencies.credential_paths), 1)
            self.assertEqual(resumed.terminals[0].status, BatchScopeStatus.INVALID)
            self.assertFalse(resumed.terminals[0].resumed_from_verified_archive)
            self.assertEqual(manifest_path.read_bytes(), tampered)
            self.assertIsNotNone(
                resumed.terminals[0].failure_evidence_manifest_path
            )

    def test_storage_capacity_block_is_terminal_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scope = _scope()
            summary = _run(
                root,
                (scope,),
                _Dependencies(),
                free_bytes=lambda _path: 0,
            )

            terminal = summary.terminals[0]
            self.assertEqual(
                terminal.status,
                BatchScopeStatus.BLOCKED_STORAGE_CAPACITY,
            )
            self.assertEqual(summary.blocked_storage_capacity_count, 1)
            self.assertIsNone(terminal.manifest_path)
            self.assertFalse((root / "archives" / scope.acquisition_key).exists())
            self.assertTrue(terminal.event_path.is_file())
            self.assertEqual(terminal.capture_count, 1)
            self.assertEqual(len(terminal.safe_captures), 1)
            self.assertIsNone(terminal.failure_evidence_manifest_path)


class GlobalMarketDataPacerTest(unittest.TestCase):
    def test_default_paces_four_requests_per_second(self) -> None:
        moments = iter((0.0, 0.1, 0.25, 0.35, 0.5, 0.6, 0.75))
        sleeps: list[float] = []
        pacer = GlobalMarketDataPacer(
            monotonic=lambda: next(moments),
            sleeper=sleeps.append,
        )

        pacer()
        pacer()
        pacer()
        pacer()

        self.assertEqual(0.25, pacer.minimum_interval_seconds)
        self.assertEqual(3, len(sleeps))
        for duration in sleeps:
            self.assertAlmostEqual(0.15, duration)

    def test_interval_cannot_cross_transport_safety_floor(self) -> None:
        with self.assertRaisesRegex(
            TossBatchCollectionError,
            "market_data_interval_invalid",
        ):
            GlobalMarketDataPacer(0.209)

        self.assertEqual(0.25, GlobalMarketDataPacer(0.25).minimum_interval_seconds)


if __name__ == "__main__":
    unittest.main()
