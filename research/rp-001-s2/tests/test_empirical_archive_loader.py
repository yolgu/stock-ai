from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import (
    CollectionScope,
    SampleRole,
    TOSS_PROVIDER_DATE_DAILY_FEED,
)
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
    CanonicalMinuteBar,
    ImmutableArchiveStorage,
)
from rp001_s2.empirical_archive_loader import (
    DailyScopeLedgerStatus,
    EmpiricalArchiveError,
    load_verified_daily_series,
)


_AVAILABLE_BYTES = 60 * 1024**3


def _scope(
    day: int,
    *,
    symbol: str = "AAPL",
    start_minute: int = 0,
    end_minute: int = 3,
    adjustment_mode: str = "native",
    sample_role: SampleRole = SampleRole.SEEN,
) -> CollectionScope:
    start = datetime(2026, 7, day, 13, 30, tzinfo=timezone.utc) + timedelta(
        minutes=start_minute
    )
    return CollectionScope(
        provider="toss",
        feed=TOSS_PROVIDER_DATE_DAILY_FEED,
        instrument_id=symbol,
        symbol=symbol,
        interval="1m",
        start_at=start,
        end_at=datetime(2026, 7, day, 13, 30, tzinfo=timezone.utc)
        + timedelta(minutes=end_minute),
        adjustment_mode=adjustment_mode,
        session_scope="provider_all",
        sample_role=sample_role,
    )


def _capture(
    *,
    symbol: str,
    received_at: str,
    body: bytes,
) -> RawHttpCapture:
    query = (("symbol", symbol), ("interval", "1m"))
    return RawHttpCapture(
        endpoint_id="toss_intraday_candles_v1",
        method="GET",
        sanitized_url=(
            "https://openapi.tossinvest.com/api/v1/candles"
            f"?symbol={symbol}&interval=1m"
        ),
        query=query,
        status=200,
        headers=(("content-type", "application/json"),),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _bar(
    *,
    scope: CollectionScope,
    minute: int,
    close: str,
    capture: RawHttpCapture,
    source_row_index: int,
    occurrences: tuple[tuple[str, int, int], ...] | None = None,
) -> CanonicalMinuteBar:
    event_start = scope.start_at.replace(hour=13, minute=30) + timedelta(
        minutes=minute
    )
    open_price = str(float(close) - 0.1)
    high_price = str(float(close) + 0.2)
    low_price = str(float(close) - 0.2)
    primary = (capture.body_sha256, 0, source_row_index)
    return CanonicalMinuteBar(
        provider=scope.provider,
        feed=scope.feed,
        instrument_id=scope.instrument_id,
        symbol=scope.symbol,
        source_timestamp=event_start.isoformat().replace("+00:00", "Z"),
        event_start_utc=event_start.isoformat().replace("+00:00", "Z"),
        bar_end_utc=(event_start + timedelta(minutes=1))
        .isoformat()
        .replace("+00:00", "Z"),
        received_at_utc=capture.received_at,
        research_available_at_utc=capture.received_at,
        session_date=event_start.date().isoformat(),
        session_type="regular",
        currency="USD",
        adjustment_mode=scope.adjustment_mode,
        numeric_fidelity="decimal_string_lexeme",
        quality_status="verified_completed",
        open_price=CanonicalScalar("json_string", open_price),
        high_price=CanonicalScalar("json_string", high_price),
        low_price=CanonicalScalar("json_string", low_price),
        close_price=CanonicalScalar("json_string", close),
        volume=CanonicalScalar("json_string", str(100 + source_row_index)),
        raw_body_sha256=capture.body_sha256,
        capture_ordinal=0,
        source_row_index=source_row_index,
        occurrences=occurrences or (primary,),
    )


def _write_archive(
    root: Path,
    scope: CollectionScope,
    *,
    minutes_and_closes: tuple[tuple[int, str], ...],
    terminal_status: AcquisitionTerminalStatus = AcquisitionTerminalStatus.COMPLETED,
    overlapping_first_row: bool = False,
) -> object:
    received_at = (
        scope.end_at + timedelta(minutes=5)
    ).isoformat().replace("+00:00", "Z")
    capture = _capture(
        symbol=scope.symbol,
        received_at=received_at,
        body=json.dumps(minutes_and_closes).encode("utf-8"),
    )
    captures = (capture,)
    overlap_capture: RawHttpCapture | None = None
    if overlapping_first_row:
        overlap_capture = _capture(
            symbol=scope.symbol,
            received_at=received_at,
            body=json.dumps({"overlap": minutes_and_closes[0]}).encode("utf-8"),
        )
        captures += (overlap_capture,)
    rows: list[CanonicalMinuteBar] = []
    for index, (minute, close) in enumerate(minutes_and_closes):
        occurrences = None
        if index == 0 and overlap_capture is not None:
            occurrences = (
                (capture.body_sha256, 0, index),
                (overlap_capture.body_sha256, 1, 0),
            )
        rows.append(
            _bar(
                scope=scope,
                minute=minute,
                close=close,
                capture=capture,
                source_row_index=index,
                occurrences=occurrences,
            )
        )
    completed = terminal_status is AcquisitionTerminalStatus.COMPLETED
    data_unavailable = (
        terminal_status is AcquisitionTerminalStatus.DATA_UNAVAILABLE
    )
    completion = AcquisitionCompletion(
        requested_start_reached=completed,
        completion_reason=(
            "provider_terminal"
            if completed
            else "data_unavailable"
            if data_unavailable
            else "provider_terminal_before_start"
        ),
        terminal_status=terminal_status,
        analysis_row_count=len(rows),
        audit_row_count=0,
        returned_row_count=len(rows),
    )
    return ImmutableArchiveStorage(
        root,
        free_bytes=lambda _path: _AVAILABLE_BYTES,
    ).write_archive(
        scope=scope,
        captures=captures,
        rows=tuple(rows),
        completion=completion,
    )


def _rewrite_as_v1(stored: object) -> None:
    manifest_path = getattr(stored, "manifest_path")
    sidecar_path = getattr(stored, "manifest_sha256_path")
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schemaVersion"] = "rp001-s2-immutable-minute-archive.v1"
    manifest.pop("acquisitionCompletion")
    for artifact in manifest["rawArtifacts"]:
        for field in ("method", "sanitizedUrl", "query", "responseHeaders"):
            artifact.pop(field)
    body = json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_path.write_bytes(body)
    sidecar_path.write_text(
        f"{hashlib.sha256(body).hexdigest()}\n",
        encoding="ascii",
    )


class VerifiedDailySeriesLoaderTest(unittest.TestCase):
    def test_reconstructs_primary_and_occurrence_lineage_without_filling_gap(
        self,
    ) -> None:
        scope = _scope(1)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            stored = _write_archive(
                root,
                scope,
                minutes_and_closes=((0, "100.1"), (2, "100.3")),
                overlapping_first_row=True,
            )
            occurrence_table = __import__("pyarrow.parquet").parquet.read_table(
                stored.occurrence_path
            )
            self.assertEqual(occurrence_table.num_rows, 3)

            result = load_verified_daily_series(root=root, scopes=(scope,))

        self.assertEqual(
            tuple(bar.event_start_utc for bar in result.bars),
            ("2026-07-01T13:30:00Z", "2026-07-01T13:32:00Z"),
        )
        self.assertEqual(len(result.bars[0].occurrences), 2)
        self.assertEqual(
            result.bars[0].occurrences[0],
            (result.bars[0].raw_body_sha256, 0, 0),
        )
        self.assertEqual(result.bars[0].occurrences[1][1:], (1, 0))
        self.assertNotEqual(
            result.bars[0].occurrences[0][0],
            result.bars[0].occurrences[1][0],
        )
        self.assertEqual(result.ledger[0].status, DailyScopeLedgerStatus.LOADED)

    def test_loads_partial_rows_and_keeps_missing_and_unavailable_in_ledger(
        self,
    ) -> None:
        complete_scope = _scope(1)
        missing_scope = _scope(2)
        partial_scope = _scope(3)
        unavailable_scope = _scope(4)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_archive(
                root,
                complete_scope,
                minutes_and_closes=((0, "100.1"),),
            )
            _write_archive(
                root,
                partial_scope,
                minutes_and_closes=((0, "100.3"),),
                terminal_status=AcquisitionTerminalStatus.PARTIAL,
            )
            _write_archive(
                root,
                unavailable_scope,
                minutes_and_closes=(),
                terminal_status=AcquisitionTerminalStatus.DATA_UNAVAILABLE,
            )

            result = load_verified_daily_series(
                root=root,
                scopes=(
                    complete_scope,
                    missing_scope,
                    partial_scope,
                    unavailable_scope,
                ),
            )

        self.assertEqual(len(result.bars), 2)
        self.assertEqual(
            tuple(entry.status for entry in result.ledger),
            (
                DailyScopeLedgerStatus.LOADED,
                DailyScopeLedgerStatus.MISSING,
                DailyScopeLedgerStatus.PARTIAL_LOADED,
                DailyScopeLedgerStatus.NON_RESUMABLE,
            ),
        )
        self.assertEqual(
            result.ledger[2].reason,
            "partial:provider_terminal_before_start",
        )
        self.assertEqual(
            result.ledger[3].reason,
            "data_unavailable:data_unavailable",
        )
        self.assertIsNotNone(result.ledger[2].manifest_sha256)

    def test_rejects_confirmation_scope_before_archive_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(EmpiricalArchiveError) as raised:
                load_verified_daily_series(
                    root=Path(temporary_directory),
                    scopes=(_scope(1, sample_role=SampleRole.CONFIRMATION),),
                )

        self.assertEqual(raised.exception.code, "confirmation_archive_sealed")

    def test_rejects_stored_confirmation_role_without_opening_canonical_file(
        self,
    ) -> None:
        stored_scope = _scope(1, sample_role=SampleRole.CONFIRMATION)
        requested_scope = replace(stored_scope, sample_role=SampleRole.SEEN)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            stored = _write_archive(
                root,
                stored_scope,
                minutes_and_closes=((0, "100.1"),),
            )
            stored.canonical_path.write_bytes(b"intentionally unreadable")

            with self.assertRaises(EmpiricalArchiveError) as raised:
                load_verified_daily_series(root=root, scopes=(requested_scope,))

        self.assertEqual(raised.exception.code, "confirmation_archive_sealed")

    def test_rejects_v1_tamper_and_failure_evidence(self) -> None:
        with self.subTest("v1"):
            scope = _scope(1)
            with tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                stored = _write_archive(
                    root,
                    scope,
                    minutes_and_closes=((0, "100.1"),),
                )
                _rewrite_as_v1(stored)
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(root=root, scopes=(scope,))
            self.assertEqual(raised.exception.code, "v2_archive_required")

        with self.subTest("tamper"):
            scope = _scope(1)
            with tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                stored = _write_archive(
                    root,
                    scope,
                    minutes_and_closes=((0, "100.1"),),
                )
                stored.canonical_path.write_bytes(
                    stored.canonical_path.read_bytes() + b"tamper"
                )
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(root=root, scopes=(scope,))
            self.assertEqual(raised.exception.code, "archive_verification_failed")

        with self.subTest("failure"):
            scope = _scope(1)
            with tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                capture = _capture(
                    symbol=scope.symbol,
                    received_at="2026-07-01T14:00:00Z",
                    body=b'{"error":"provider"}',
                )
                ImmutableArchiveStorage(
                    root,
                    free_bytes=lambda _path: _AVAILABLE_BYTES,
                ).write_failure_evidence(
                    scope=scope,
                    captures=(capture,),
                    completion=AcquisitionCompletion(
                        requested_start_reached=False,
                        completion_reason="provider_failed",
                        terminal_status=AcquisitionTerminalStatus.FAILED,
                        analysis_row_count=0,
                        audit_row_count=0,
                        returned_row_count=0,
                    ),
                )
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(root=root, scopes=(scope,))
            self.assertEqual(raised.exception.code, "scope_failure_evidence_present")

    def test_rejects_mixed_series_identity_and_conflicting_duplicates(self) -> None:
        with self.subTest("mixed-symbol"):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(
                        root=Path(temporary_directory),
                        scopes=(_scope(1), _scope(2, symbol="MSFT")),
                    )
            self.assertEqual(raised.exception.code, "daily_series_scope_mismatch")

        with self.subTest("mixed-adjustment"):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(
                        root=Path(temporary_directory),
                        scopes=(
                            _scope(1),
                            _scope(2, adjustment_mode="adjusted"),
                        ),
                    )
            self.assertEqual(raised.exception.code, "daily_series_scope_mismatch")

        with self.subTest("conflicting-overlap"):
            first = _scope(1, start_minute=0, end_minute=3)
            second = _scope(1, start_minute=0, end_minute=2)
            with tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                _write_archive(
                    root,
                    first,
                    minutes_and_closes=((0, "100.1"),),
                )
                _write_archive(
                    root,
                    second,
                    minutes_and_closes=((0, "101.1"),),
                )
                with self.assertRaises(EmpiricalArchiveError) as raised:
                    load_verified_daily_series(
                        root=root,
                        scopes=(first, second),
                    )
            self.assertEqual(raised.exception.code, "conflicting_minute_duplicate")

    def test_identical_cross_archive_overlap_is_one_bar_not_a_synthetic_row(self) -> None:
        first = _scope(1, start_minute=0, end_minute=3)
        second = _scope(1, start_minute=0, end_minute=2)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_archive(
                root,
                first,
                minutes_and_closes=((0, "100.1"),),
            )
            _write_archive(
                root,
                second,
                minutes_and_closes=((0, "100.1"),),
            )

            result = load_verified_daily_series(
                root=root,
                scopes=(first, second),
            )
            reordered = load_verified_daily_series(
                root=root,
                scopes=(second, first),
            )

        self.assertEqual(len(result.bars), 1)
        self.assertEqual(result.bars[0].event_start_utc, "2026-07-01T13:30:00Z")
        self.assertEqual(
            tuple(entry.status for entry in result.ledger),
            (DailyScopeLedgerStatus.LOADED, DailyScopeLedgerStatus.LOADED),
        )
        self.assertEqual(
            result.source_evidence_sha256,
            reordered.source_evidence_sha256,
        )


if __name__ == "__main__":
    unittest.main()
