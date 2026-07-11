from __future__ import annotations

import base64
import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as parquet
import zstandard

import rp001_s2.archive_storage as archive_storage
from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import (
    CollectionScope,
    FormulaState,
    ResearchDataKind,
    ResearchViewAccess,
    SampleRole,
)
from rp001_s2.archive_storage import (
    ArchiveStorageError,
    CanonicalMinuteBar,
    ImmutableArchiveStorage,
)


_AVAILABLE_BYTES = 60 * 1024**3


def _scope() -> CollectionScope:
    return CollectionScope(
        provider="alpaca",
        feed="iex",
        instrument_id="AAPL",
        symbol="AAPL",
        interval="1m",
        start_at=datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 1, 13, 32, tzinfo=timezone.utc),
        adjustment_mode="raw",
        session_scope="provider_all",
        sample_role=SampleRole.SEEN,
    )


def _capture(body: bytes) -> RawHttpCapture:
    return RawHttpCapture(
        endpoint_id="alpaca_historical_minute_bars_v2",
        method="GET",
        sanitized_url=(
            "https://data.alpaca.markets/v2/stocks/AAPL/bars?timeframe=1Min"
        ),
        query=(("timeframe", "1Min"),),
        status=200,
        headers=(("content-type", "application/json"),),
        received_at="2026-07-01T13:33:00Z",
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _bar(raw_body_sha256: str) -> CanonicalMinuteBar:
    return CanonicalMinuteBar(
        provider="alpaca",
        feed="iex",
        instrument_id="AAPL",
        symbol="AAPL",
        source_timestamp="2026-07-01T13:30:00Z",
        event_start_utc="2026-07-01T13:30:00Z",
        bar_end_utc="2026-07-01T13:31:00Z",
        received_at_utc="2026-07-01T13:33:00Z",
        research_available_at_utc="2026-07-01T13:33:00Z",
        session_date="2026-07-01",
        session_type="regular",
        currency="USD",
        adjustment_mode="raw",
        numeric_fidelity="json_number_lexeme",
        quality_status="valid",
        open_price=CanonicalScalar("json_number", "100.10"),
        high_price=CanonicalScalar("json_number", "101.250"),
        low_price=CanonicalScalar("json_number", "99.875"),
        close_price=CanonicalScalar("json_number", "100.625"),
        volume=CanonicalScalar("json_number", "10.500"),
        raw_body_sha256=raw_body_sha256,
        capture_ordinal=0,
        source_row_index=0,
        occurrences=((raw_body_sha256, 0, 0),),
    )


def _completion(row_count: int) -> archive_storage.AcquisitionCompletion:
    if row_count == 0:
        return archive_storage.AcquisitionCompletion(
            requested_start_reached=False,
            completion_reason="data_unavailable",
            terminal_status=archive_storage.AcquisitionTerminalStatus.DATA_UNAVAILABLE,
            analysis_row_count=0,
            audit_row_count=0,
            returned_row_count=0,
        )
    return archive_storage.AcquisitionCompletion(
        requested_start_reached=True,
        completion_reason="provider_terminal",
        terminal_status=archive_storage.AcquisitionTerminalStatus.COMPLETED,
        analysis_row_count=row_count,
        audit_row_count=0,
        returned_row_count=row_count,
    )


def _rewrite_manifest_as_v1(stored: object) -> None:
    manifest_path = getattr(stored, "manifest_path")
    sidecar_path = getattr(stored, "manifest_sha256_path")
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schemaVersion"] = "rp001-s2-immutable-minute-archive.v1"
    manifest.pop("acquisitionCompletion", None)
    for raw_artifact in manifest["rawArtifacts"]:
        for field in ("method", "sanitizedUrl", "query", "responseHeaders"):
            raw_artifact.pop(field, None)
    manifest_bytes = json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    sidecar_path.write_text(
        f"{hashlib.sha256(manifest_bytes).hexdigest()}\n",
        encoding="ascii",
    )


class ImmutableArchiveWriteTest(unittest.TestCase):
    def test_exports_typed_acquisition_completion_contract(self) -> None:
        self.assertTrue(hasattr(archive_storage, "AcquisitionCompletion"))
        self.assertTrue(hasattr(archive_storage, "AcquisitionTerminalStatus"))

    def test_exports_failure_and_invalid_evidence_contract(self) -> None:
        self.assertTrue(
            hasattr(archive_storage.AcquisitionTerminalStatus, "FAILED")
        )
        self.assertTrue(
            hasattr(archive_storage.AcquisitionTerminalStatus, "INVALID")
        )
        self.assertTrue(hasattr(archive_storage, "StoredFailureEvidence"))
        self.assertTrue(
            hasattr(ImmutableArchiveStorage, "write_failure_evidence")
        )
        self.assertTrue(
            hasattr(ImmutableArchiveStorage, "verify_failure_evidence")
        )
        self.assertTrue(
            hasattr(ImmutableArchiveStorage, "load_resumable_completion")
        )

    def test_write_archive_requires_completion_parameter(self) -> None:
        parameter = inspect.signature(
            ImmutableArchiveStorage.write_archive
        ).parameters.get("completion")

        self.assertIsNotNone(parameter)
        self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_v2_manifest_preserves_request_lineage_and_completion(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        cursor_sha256 = "b" * 64
        capture = replace(
            _capture(raw_body),
            method="POST",
            sanitized_url=(
                "https://data.alpaca.markets/v2/stocks/AAPL/bars?"
                f"timeframe=1Min&feed=iex&page_token_sha256={cursor_sha256}"
            ),
            query=(
                ("timeframe", "1Min"),
                ("feed", "iex"),
                ("page_token_sha256", cursor_sha256),
            ),
            headers=(
                ("content-type", "application/json"),
                ("x-ratelimit-remaining", "199"),
            ),
        )
        completion = _completion(1)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture.body_sha256),),
                completion=completion,
            )

            manifest = json.loads(stored.manifest_path.read_bytes())
            self.assertEqual(
                manifest["schemaVersion"],
                "rp001-s2-immutable-minute-archive.v2",
            )
            raw_artifact = manifest["rawArtifacts"][0]
            self.assertEqual(raw_artifact["method"], "POST")
            self.assertEqual(raw_artifact["sanitizedUrl"], capture.sanitized_url)
            self.assertEqual(
                raw_artifact["query"],
                [
                    {"name": "timeframe", "value": "1Min"},
                    {"name": "feed", "value": "iex"},
                    {"name": "page_token_sha256", "value": cursor_sha256},
                ],
            )
            self.assertEqual(
                raw_artifact["responseHeaders"],
                [
                    {"name": "content-type", "value": "application/json"},
                    {"name": "x-ratelimit-remaining", "value": "199"},
                ],
            )
            self.assertEqual(
                manifest["acquisitionCompletion"],
                {
                    "requestedStartReached": True,
                    "completionReason": "provider_terminal",
                    "terminalStatus": "completed",
                    "analysisRowCount": 1,
                    "auditRowCount": 0,
                    "returnedRowCount": 1,
                },
            )
            storage.verify_archive(stored)

    def test_v2_rejects_unsafe_or_inconsistent_sanitized_url(self) -> None:
        raw_body = b'{"bars":[]}'
        safe_query = (
            ("timeframe", "1Min"),
            ("page_token_sha256", "a" * 64),
        )
        unsafe_captures = (
            replace(
                _capture(raw_body),
                sanitized_url=(
                    "http://data.alpaca.markets/v2/stocks/AAPL/bars?"
                    "timeframe=1Min&page_token_sha256=" + "a" * 64
                ),
                query=safe_query,
            ),
            replace(
                _capture(raw_body),
                sanitized_url=(
                    "https://client:secret@data.alpaca.markets/"
                    "v2/stocks/AAPL/bars?timeframe=1Min&"
                    "page_token_sha256=" + "a" * 64
                ),
                query=safe_query,
            ),
            replace(
                _capture(raw_body),
                sanitized_url=(
                    "https://data.alpaca.markets/v2/stocks/AAPL/bars?"
                    "timeframe=1Min&page_token=raw-secret"
                ),
                query=safe_query,
            ),
            replace(
                _capture(raw_body),
                sanitized_url=(
                    "https://data.alpaca.markets/v2/stocks/AAPL/bars?"
                    "timeframe=1Min&page_token_sha256=" + "a" * 64 + "#secret"
                ),
                query=safe_query,
            ),
        )

        for capture in unsafe_captures:
            with self.subTest(sanitized_url=capture.sanitized_url):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    storage = ImmutableArchiveStorage(
                        root,
                        free_bytes=lambda _path: _AVAILABLE_BYTES,
                    )

                    with self.assertRaisesRegex(
                        ArchiveStorageError,
                        "raw_capture_invalid",
                    ):
                        storage.write_archive(
                            scope=_scope(),
                            captures=(capture,),
                            rows=(),
                            completion=_completion(0),
                        )

                    self.assertFalse((root / _scope().acquisition_key).exists())

    def test_completion_rejects_partial_collection_labeled_completed(self) -> None:
        with self.assertRaisesRegex(
            ArchiveStorageError,
            "acquisition_completion_invalid",
        ):
            archive_storage.AcquisitionCompletion(
                requested_start_reached=False,
                completion_reason="provider_terminal_before_start",
                terminal_status=archive_storage.AcquisitionTerminalStatus.COMPLETED,
                analysis_row_count=1,
                audit_row_count=0,
                returned_row_count=1,
            )

    def test_completion_counts_must_match_terminal_status_and_rows(self) -> None:
        invalid_values = (
            {
                "requested_start_reached": True,
                "completion_reason": "provider_terminal",
                "terminal_status": archive_storage.AcquisitionTerminalStatus.COMPLETED,
                "analysis_row_count": 1,
                "audit_row_count": 1,
                "returned_row_count": 1,
            },
            {
                "requested_start_reached": False,
                "completion_reason": "data_unavailable",
                "terminal_status": archive_storage.AcquisitionTerminalStatus.DATA_UNAVAILABLE,
                "analysis_row_count": 1,
                "audit_row_count": 0,
                "returned_row_count": 1,
            },
            {
                "requested_start_reached": True,
                "completion_reason": "provider_terminal_before_start",
                "terminal_status": archive_storage.AcquisitionTerminalStatus.PARTIAL,
                "analysis_row_count": 1,
                "audit_row_count": 0,
                "returned_row_count": 1,
            },
        )
        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaisesRegex(
                    ArchiveStorageError,
                    "acquisition_completion_invalid",
                ):
                    archive_storage.AcquisitionCompletion(**invalid_value)

        partial = archive_storage.AcquisitionCompletion(
            requested_start_reached=False,
            completion_reason="provider_terminal_before_start",
            terminal_status=archive_storage.AcquisitionTerminalStatus.PARTIAL,
            analysis_row_count=1,
            audit_row_count=0,
            returned_row_count=1,
        )
        self.assertEqual(
            partial.terminal_status,
            archive_storage.AcquisitionTerminalStatus.PARTIAL,
        )

    def test_failure_completion_requires_stable_reason_and_zero_counts(self) -> None:
        for terminal_status, completion_reason in (
            (
                archive_storage.AcquisitionTerminalStatus.FAILED,
                "TRANSPORT_ERROR",
            ),
            (
                archive_storage.AcquisitionTerminalStatus.INVALID,
                "CANONICAL_CONTRACT_INVALID",
            ),
            (
                archive_storage.AcquisitionTerminalStatus.FAILED,
                "measurement_failed",
            ),
        ):
            with self.subTest(terminal_status=terminal_status):
                completion = archive_storage.AcquisitionCompletion(
                    requested_start_reached=False,
                    completion_reason=completion_reason,
                    terminal_status=terminal_status,
                    analysis_row_count=0,
                    audit_row_count=0,
                    returned_row_count=0,
                )
                self.assertEqual(completion.terminal_status, terminal_status)

        with self.assertRaisesRegex(
            ArchiveStorageError,
            "acquisition_completion_invalid",
        ):
            archive_storage.AcquisitionCompletion(
                requested_start_reached=False,
                completion_reason="TRANSPORT_ERROR",
                terminal_status=archive_storage.AcquisitionTerminalStatus.FAILED,
                analysis_row_count=1,
                audit_row_count=0,
                returned_row_count=1,
            )

    def test_completion_returned_count_must_match_canonical_rows(self) -> None:
        capture = _capture(b'{"bars":[]}')
        completion = archive_storage.AcquisitionCompletion(
            requested_start_reached=True,
            completion_reason="provider_terminal",
            terminal_status=archive_storage.AcquisitionTerminalStatus.COMPLETED,
            analysis_row_count=2,
            audit_row_count=0,
            returned_row_count=2,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            with self.assertRaisesRegex(
                ArchiveStorageError,
                "acquisition_completion_invalid",
            ):
                storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(),
                    completion=completion,
                )

    def test_writes_lossless_raw_zstandard_and_decimal_parquet_with_lineage(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z","o":100.10}]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture.body_sha256),),
                completion=_completion(1),
            )

            compressed = stored.raw_paths[0].read_bytes()
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(compressed),
                raw_body,
            )
            manifest = json.loads(stored.manifest_path.read_bytes())
            self.assertEqual(
                manifest["rawArtifacts"][0]["uncompressedSha256"],
                hashlib.sha256(raw_body).hexdigest(),
            )
            self.assertEqual(
                manifest["rawArtifacts"][0]["storedSha256"],
                hashlib.sha256(compressed).hexdigest(),
            )
            table = parquet.read_table(stored.canonical_path)
            self.assertEqual(table.column("provider").to_pylist(), ["alpaca"])
            self.assertEqual(table.column("feed").to_pylist(), ["iex"])
            self.assertEqual(table.column("instrument_id").to_pylist(), ["AAPL"])
            self.assertEqual(table.column("symbol").to_pylist(), ["AAPL"])
            self.assertEqual(
                table.column("source_timestamp").to_pylist(),
                ["2026-07-01T13:30:00Z"],
            )
            self.assertEqual(
                table.column("event_start_utc").to_pylist(),
                ["2026-07-01T13:30:00Z"],
            )
            self.assertEqual(
                table.column("bar_end_utc").to_pylist(),
                ["2026-07-01T13:31:00Z"],
            )
            self.assertEqual(
                table.column("received_at_utc").to_pylist(),
                ["2026-07-01T13:33:00Z"],
            )
            self.assertEqual(
                table.column("research_available_at_utc").to_pylist(),
                ["2026-07-01T13:33:00Z"],
            )
            self.assertEqual(table.column("session_date").to_pylist(), ["2026-07-01"])
            self.assertEqual(table.column("session_type").to_pylist(), ["regular"])
            self.assertEqual(table.column("currency").to_pylist(), ["USD"])
            self.assertEqual(table.column("adjustment_mode").to_pylist(), ["raw"])
            self.assertEqual(
                table.column("numeric_fidelity").to_pylist(),
                ["json_number_lexeme"],
            )
            self.assertEqual(table.column("quality_status").to_pylist(), ["valid"])
            self.assertEqual(table.column("open_price").to_pylist(), [Decimal("100.10")])
            self.assertEqual(table.column("high_price").to_pylist(), [Decimal("101.250")])
            self.assertEqual(table.column("low_price").to_pylist(), [Decimal("99.875")])
            self.assertEqual(table.column("close_price").to_pylist(), [Decimal("100.625")])
            self.assertEqual(table.column("volume").to_pylist(), [Decimal("10.500")])
            self.assertEqual(
                table.column("raw_body_sha256").to_pylist(),
                [capture.body_sha256],
            )
            self.assertEqual(table.column("capture_ordinal").to_pylist(), [0])
            self.assertEqual(table.column("source_row_index").to_pylist(), [0])

    def test_alpaca_exponent_numbers_round_trip_as_exact_decimals(self) -> None:
        raw_body = b'{"bars":[{"o":1e2,"h":1.01e2,"l":9.9e1,"c":1.005e2,"v":1.05e1}]}'
        capture = _capture(raw_body)
        bar = replace(
            _bar(capture.body_sha256),
            open_price=CanonicalScalar("json_number", "1e2"),
            high_price=CanonicalScalar("json_number", "1.01e2"),
            low_price=CanonicalScalar("json_number", "9.9e1"),
            close_price=CanonicalScalar("json_number", "1.005e2"),
            volume=CanonicalScalar("json_number", "1.05e1"),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            stored = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            ).write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(bar,),
                completion=_completion(1),
            )

            table = parquet.read_table(stored.canonical_path)

            self.assertEqual(table.column("open_price").to_pylist(), [Decimal("1e2")])
            self.assertEqual(table.column("close_price").to_pylist(), [Decimal("1.005e2")])
            self.assertEqual(table.column("volume").to_pylist(), [Decimal("1.05e1")])

    def test_manifest_is_canonical_with_a_separate_sha256_sidecar(self) -> None:
        raw_body = b'{"bars":[]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(),
                completion=_completion(0),
            )

            manifest_bytes = stored.manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            self.assertEqual(
                manifest_bytes,
                json.dumps(
                    manifest,
                    allow_nan=False,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
            self.assertNotIn("manifestSha256", manifest)
            self.assertEqual(
                stored.manifest_sha256_path.read_text(encoding="ascii"),
                f"{hashlib.sha256(manifest_bytes).hexdigest()}\n",
            )

    def test_identical_inputs_produce_identical_canonical_manifests(self) -> None:
        raw_body = b'{"bars":[]}'
        capture = _capture(raw_body)
        manifests: list[bytes] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temporary_directory:
                stored = ImmutableArchiveStorage(
                    Path(temporary_directory),
                    free_bytes=lambda _path: _AVAILABLE_BYTES,
                ).write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(),
                    completion=_completion(0),
                )
                manifests.append(stored.manifest_path.read_bytes())

        self.assertEqual(manifests[0], manifests[1])

    def test_existing_archive_is_never_overwritten(self) -> None:
        raw_body = b'{"bars":[]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = ImmutableArchiveStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(),
                completion=_completion(0),
            )
            before = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }

            with self.assertRaises(ArchiveStorageError) as raised:
                storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(),
                    completion=_completion(0),
                )

            self.assertEqual(raised.exception.code, "archive_already_exists")
            after = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_capacity_guard_runs_before_every_write_without_deleting_evidence(
        self,
    ) -> None:
        raw_body = b'{"bars":[]}'
        capture = _capture(raw_body)
        threshold = 50 * 1024**3
        for blocked_call in range(6):
            with self.subTest(blocked_call=blocked_call):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    calls: list[Path] = []

                    def free_bytes(path: Path) -> int:
                        calls.append(path)
                        return threshold - 1 if len(calls) - 1 == blocked_call else threshold

                    storage = ImmutableArchiveStorage(root, free_bytes=free_bytes)

                    with self.assertRaises(ArchiveStorageError) as raised:
                        storage.write_archive(
                            scope=_scope(),
                            captures=(capture,),
                            rows=(),
                            completion=_completion(0),
                        )

                    self.assertEqual(
                        raised.exception.code,
                        "blocked_storage_capacity",
                    )
                    self.assertEqual(len(calls), blocked_call + 1)
                    archive_directory = root / _scope().acquisition_key
                    written_files = (
                        tuple(
                            path
                            for path in archive_directory.rglob("*")
                            if path.is_file()
                        )
                        if archive_directory.exists()
                        else ()
                    )
                    self.assertEqual(len(written_files), max(0, blocked_call - 1))


class ArchiveVerificationTest(unittest.TestCase):
    def test_failure_evidence_is_separate_append_only_and_idempotent(self) -> None:
        first = replace(
            _capture(b'{"page":1,"bars":[]}'),
            status=500,
            headers=(
                ("content-type", "application/json"),
                ("x-ratelimit-remaining", "0"),
            ),
        )
        second = replace(
            _capture(b'{"page":2,"bars":[]}'),
            sanitized_url=(
                "https://data.alpaca.markets/v2/stocks/AAPL/bars?page_token=next"
            ),
            query=(("page_token", "next"),),
        )
        failed = archive_storage.AcquisitionCompletion(
            requested_start_reached=False,
            completion_reason="TRANSPORT_ERROR",
            terminal_status=archive_storage.AcquisitionTerminalStatus.FAILED,
            analysis_row_count=0,
            audit_row_count=0,
            returned_row_count=0,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = ImmutableArchiveStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_failure_evidence(
                scope=_scope(),
                captures=(first, second),
                completion=failed,
            )
            before = {
                path.relative_to(stored.evidence_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.evidence_directory.rglob("*")
                if path.is_file()
            }
            repeated = storage.write_failure_evidence(
                scope=_scope(),
                captures=(first, second),
                completion=failed,
            )

            self.assertEqual(repeated, stored)
            self.assertEqual(
                stored.evidence_directory,
                root
                / "failure-evidence"
                / _scope().acquisition_key
                / stored.evidence_digest,
            )
            self.assertFalse((root / _scope().acquisition_key).exists())
            manifest = json.loads(stored.manifest_path.read_bytes())
            self.assertEqual(
                manifest["schemaVersion"],
                "rp001-s2-immutable-minute-failure-evidence.v1",
            )
            self.assertEqual(manifest["evidenceDigest"], stored.evidence_digest)
            self.assertEqual(
                manifest["acquisitionCompletion"]["terminalStatus"],
                "failed",
            )
            self.assertEqual(len(manifest["rawArtifacts"]), 2)
            self.assertEqual(parquet.read_table(stored.canonical_path).num_rows, 0)
            self.assertEqual(parquet.read_table(stored.occurrence_path).num_rows, 0)
            after = {
                path.relative_to(stored.evidence_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.evidence_directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            storage.verify_failure_evidence(stored)

            invalid = archive_storage.AcquisitionCompletion(
                requested_start_reached=False,
                completion_reason="CANONICAL_CONTRACT_INVALID",
                terminal_status=archive_storage.AcquisitionTerminalStatus.INVALID,
                analysis_row_count=0,
                audit_row_count=0,
                returned_row_count=0,
            )
            distinct = storage.write_failure_evidence(
                scope=_scope(),
                captures=(first, second),
                completion=invalid,
            )
            self.assertNotEqual(distinct.evidence_digest, stored.evidence_digest)
            storage.verify_failure_evidence(distinct)

    def test_only_v2_success_archive_has_resumable_completion(self) -> None:
        capture = _capture(b'{"bars":[]}')
        completion = _completion(0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(),
                completion=completion,
            )

            self.assertEqual(
                storage.load_resumable_completion(stored),
                completion,
            )
            _rewrite_manifest_as_v1(stored)
            storage.verify_archive(stored)
            with self.assertRaisesRegex(
                ArchiveStorageError,
                "archive_not_resumable",
            ):
                storage.load_resumable_completion(stored)

    def test_success_archive_rejects_failure_terminal_status(self) -> None:
        capture = _capture(b'{"bars":[]}')
        failed = archive_storage.AcquisitionCompletion(
            requested_start_reached=False,
            completion_reason="TRANSPORT_ERROR",
            terminal_status=archive_storage.AcquisitionTerminalStatus.FAILED,
            analysis_row_count=0,
            audit_row_count=0,
            returned_row_count=0,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            with self.assertRaisesRegex(
                ArchiveStorageError,
                "acquisition_completion_invalid",
            ):
                storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(),
                    completion=failed,
                )

    def test_v1_manifest_fixture_remains_verifiable(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture.body_sha256),),
                completion=_completion(1),
            )
            _rewrite_manifest_as_v1(stored)

            storage.verify_archive(stored)

    def test_detects_raw_canonical_and_manifest_modification(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        for artifact_name in ("raw", "canonical", "occurrence", "manifest"):
            with self.subTest(artifact_name=artifact_name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    capture = _capture(raw_body)
                    storage = ImmutableArchiveStorage(
                        Path(temporary_directory),
                        free_bytes=lambda _path: _AVAILABLE_BYTES,
                    )
                    stored = storage.write_archive(
                        scope=_scope(),
                        captures=(capture,),
                        rows=(_bar(capture.body_sha256),),
                        completion=_completion(1),
                    )
                    storage.verify_archive(stored)
                    artifact_path = {
                        "raw": stored.raw_paths[0],
                        "canonical": stored.canonical_path,
                        "occurrence": stored.occurrence_path,
                        "manifest": stored.manifest_path,
                    }[artifact_name]
                    source = artifact_path.read_bytes()
                    artifact_path.write_bytes(source[:-1] + bytes((source[-1] ^ 1,)))

                    with self.assertRaises(ArchiveStorageError) as raised:
                        storage.verify_archive(stored)

                    self.assertEqual(
                        raised.exception.code,
                        "archive_verification_failed",
                    )


class ArchiveResearchViewTest(unittest.TestCase):
    def test_duckdb_bar_view_preserves_decimals_and_lineage(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture.body_sha256),),
                completion=_completion(1),
            )
            access = ResearchViewAccess(
                sample_role=SampleRole.SEEN,
                formula_state=FormulaState.DISCOVERY,
            )

            with storage.open_views(stored, access) as views:
                rows = views.query(ResearchDataKind.BAR_VALUES)

            self.assertEqual(rows[0][0:4], ("alpaca", "iex", "AAPL", "AAPL"))
            self.assertEqual(rows[0][4], "2026-07-01T13:30:00Z")
            self.assertEqual(rows[0][15], Decimal("100.10"))
            self.assertEqual(rows[0][19], Decimal("10.500"))
            self.assertEqual(rows[0][20], capture.body_sha256)
            self.assertEqual(rows[0][21:], (0, 0))

    def test_identical_overlap_keeps_one_bar_and_every_raw_occurrence(self) -> None:
        first_body = b'{"page":1,"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        second_body = b'{"page":2,"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        first_capture = _capture(first_body)
        second_capture = _capture(second_body)
        bar = replace(
            _bar(first_capture.body_sha256),
            occurrences=(
                (first_capture.body_sha256, 0, 0),
                (second_capture.body_sha256, 1, 0),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(first_capture, second_capture),
                rows=(bar,),
                completion=_completion(1),
            )
            access = ResearchViewAccess(
                sample_role=SampleRole.SEEN,
                formula_state=FormulaState.DISCOVERY,
            )

            with storage.open_views(stored, access) as views:
                bars = views.query(ResearchDataKind.BAR_VALUES)
                occurrences = views.query_bar_occurrences()
                raw_row_count = views.query(
                    ResearchDataKind.RAW_ARCHIVE_ROW_COUNT
                )

            self.assertEqual(len(bars), 1)
            self.assertEqual(raw_row_count, ((2,),))
            self.assertEqual(
                occurrences,
                (
                    (
                        "2026-07-01T13:30:00Z",
                        first_capture.body_sha256,
                        0,
                        0,
                        0,
                    ),
                    (
                        "2026-07-01T13:30:00Z",
                        second_capture.body_sha256,
                        1,
                        0,
                        1,
                    ),
                ),
            )
            self.assertEqual(parquet.read_table(stored.canonical_path).num_rows, 1)
            self.assertEqual(parquet.read_table(stored.occurrence_path).num_rows, 2)
            storage.verify_archive(stored)

    def test_sealed_confirmation_exposes_only_raw_metadata_hash_and_count(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        capture = _capture(raw_body)
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture.body_sha256),),
                completion=_completion(1),
            )
            sealed = ResearchViewAccess(
                sample_role=SampleRole.CONFIRMATION,
                formula_state=FormulaState.DISCOVERY,
            )

            with storage.open_views(stored, sealed) as views:
                self.assertEqual(
                    views.query(ResearchDataKind.RAW_ARCHIVE_METADATA)[0][0],
                    0,
                )
                self.assertEqual(
                    views.query(ResearchDataKind.RAW_ARCHIVE_HASH)[0][1],
                    capture.body_sha256,
                )
                self.assertEqual(
                    views.query(ResearchDataKind.RAW_ARCHIVE_ROW_COUNT),
                    ((1,),),
                )
                for data_kind in (
                    ResearchDataKind.BAR_VALUES,
                    ResearchDataKind.FEATURES,
                    ResearchDataKind.LABELS,
                ):
                    with self.subTest(data_kind=data_kind):
                        with self.assertRaisesRegex(
                            PermissionError,
                            "confirmation_research_view_sealed",
                        ):
                            views.query(data_kind)


class CanonicalMinuteBarValidationTest(unittest.TestCase):
    def test_rejects_scope_time_ohlcv_identifier_and_lineage_violations(self) -> None:
        raw_body = b'{"bars":[{"t":"2026-07-01T13:30:00Z"}]}'
        capture = _capture(raw_body)
        valid = _bar(capture.body_sha256)
        toss_decimal_string = replace(
            valid,
            provider="toss",
            feed="historical_candles",
            numeric_fidelity="decimal_string_lexeme",
            open_price=CanonicalScalar("json_string", "100.10"),
            high_price=CanonicalScalar("json_string", "101.250"),
            low_price=CanonicalScalar("json_string", "99.875"),
            close_price=CanonicalScalar("json_string", "100.625"),
            volume=CanonicalScalar("json_string", "10.500"),
        )
        self.assertEqual(toss_decimal_string.volume.text, "10.500")
        with self.assertRaises(ArchiveStorageError):
            replace(
                toss_decimal_string,
                volume=CanonicalScalar("json_string", "1.05e1"),
            )
        invalid_local_values = (
            {"event_start_utc": "2026-07-01T13:30:01Z"},
            {"bar_end_utc": "2026-07-01T13:32:00Z"},
            {"research_available_at_utc": "2026-07-01T13:30:30Z"},
            {"session_type": " regular"},
            {"low_price": CanonicalScalar("json_number", "101")},
            {"volume": CanonicalScalar("json_number", "-1")},
        )
        for invalid_values in invalid_local_values:
            with self.subTest(invalid_values=invalid_values):
                with self.assertRaises(ArchiveStorageError):
                    replace(valid, **invalid_values)

        invalid_archive_bars = (
            replace(valid, provider="other"),
            replace(
                valid,
                raw_body_sha256="0" * 64,
                occurrences=(("0" * 64, 0, 0),),
            ),
        )
        for invalid_bar in invalid_archive_bars:
            with self.subTest(invalid_bar=invalid_bar):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    storage = ImmutableArchiveStorage(
                        Path(temporary_directory),
                        free_bytes=lambda _path: _AVAILABLE_BYTES,
                    )

                    with self.assertRaises(ArchiveStorageError):
                        storage.write_archive(
                            scope=_scope(),
                            captures=(capture,),
                            rows=(invalid_bar,),
                            completion=_completion(1),
                        )

        earlier = replace(
            valid,
            source_timestamp="2026-07-01T13:29:00Z",
            event_start_utc="2026-07-01T13:29:00Z",
            bar_end_utc="2026-07-01T13:30:00Z",
            source_row_index=1,
            occurrences=((capture.body_sha256, 0, 1),),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            with self.assertRaises(ArchiveStorageError):
                storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(valid, earlier),
                    completion=_completion(2),
                )

        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = ImmutableArchiveStorage(
                Path(temporary_directory),
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            with self.assertRaises(ArchiveStorageError):
                storage.write_archive(
                    scope=replace(_scope(), interval="1d"),
                    captures=(capture,),
                    rows=(valid,),
                    completion=_completion(1),
                )


if __name__ == "__main__":
    unittest.main()
