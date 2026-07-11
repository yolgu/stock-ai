from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as parquet
import zstandard

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
        sanitized_url="https://data.alpaca.markets/v2/stocks/AAPL/bars",
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


class ImmutableArchiveWriteTest(unittest.TestCase):
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
                )


if __name__ == "__main__":
    unittest.main()
