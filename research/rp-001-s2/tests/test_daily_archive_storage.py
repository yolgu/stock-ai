from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as parquet
import zstandard

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
)
from rp001_s2.daily_archive_storage import (
    CanonicalDailyBar,
    DailyArchiveStorageError,
    ImmutableDailyArchiveStorage,
)


_FREE_BYTES = 100 * 1024**3


def _scope() -> CollectionScope:
    return CollectionScope(
        provider="toss",
        feed="provider_all",
        instrument_id="TSLA",
        symbol="TSLA",
        interval="1d",
        start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        adjustment_mode="native",
        session_scope="provider_all",
        sample_role=SampleRole.SEEN,
    )


def _capture() -> tuple[RawHttpCapture, bytes]:
    raw_row = {
        "timestamp": "2026-07-01T04:00:00Z",
        "openPrice": "100",
        "highPrice": "103",
        "lowPrice": "99",
        "closePrice": "102",
        "volume": "1000",
        "currency": "USD",
    }
    body = json.dumps(
        {"result": {"candles": [raw_row], "nextBefore": None}},
        separators=(",", ":"),
    ).encode("utf-8")
    capture = RawHttpCapture(
        endpoint_id="daily_candles_v1",
        method="GET",
        sanitized_url="https://openapi.tossinvest.com/api/v1/candles",
        query=(
            ("symbol", "TSLA"),
            ("interval", "1d"),
            ("count", "200"),
            ("adjusted", "false"),
            ("before", "cursor"),
        ),
        status=200,
        headers=(("content-type", "application/json"),),
        received_at="2026-07-03T00:00:00Z",
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    return capture, body


def _bar(capture: RawHttpCapture) -> CanonicalDailyBar:
    scalar = lambda value: CanonicalScalar("decimal_string", value)
    return CanonicalDailyBar(
        provider="toss",
        feed="provider_all",
        instrument_id="TSLA",
        symbol="TSLA",
        source_timestamp="2026-07-01T04:00:00Z",
        session_date="2026-07-01",
        received_at_utc="2026-07-03T00:00:00Z",
        research_available_at_utc="2026-07-03T00:00:00Z",
        session_type="provider_all",
        currency="USD",
        adjustment_mode="native",
        numeric_fidelity="decimal_string_lexeme",
        quality_status="verified_provider_response",
        open_price=scalar("100"),
        high_price=scalar("103"),
        low_price=scalar("99"),
        close_price=scalar("102"),
        volume=scalar("1000"),
        raw_body_sha256=capture.body_sha256,
        capture_ordinal=0,
        source_row_index=0,
        occurrences=((capture.body_sha256, 0, 0),),
    )


def _completion() -> AcquisitionCompletion:
    return AcquisitionCompletion(
        requested_start_reached=True,
        completion_reason="requested_start_reached",
        terminal_status=AcquisitionTerminalStatus.COMPLETED,
        analysis_row_count=1,
        audit_row_count=0,
        returned_row_count=1,
    )


class ImmutableDailyArchiveStorageTest(unittest.TestCase):
    def test_writes_raw_zstd_parquet_manifest_and_verifies_lineage(self) -> None:
        capture, raw_body = _capture()
        with tempfile.TemporaryDirectory() as directory:
            storage = ImmutableDailyArchiveStorage(
                Path(directory),
                free_bytes=lambda _path: _FREE_BYTES,
            )

            stored = storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture),),
                completion=_completion(),
            )
            storage.verify_archive(stored)

            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.raw_paths[0].read_bytes()
                ),
                raw_body,
            )
            table = parquet.read_table(stored.canonical_path)
            self.assertEqual(table.num_rows, 1)
            self.assertEqual(table.column("source_row_index").to_pylist(), [0])
            manifest_source = stored.manifest_path.read_bytes()
            self.assertEqual(
                stored.manifest_sha256_path.read_text(encoding="ascii"),
                f"{hashlib.sha256(manifest_source).hexdigest()}\n",
            )

    def test_existing_archive_is_never_overwritten(self) -> None:
        capture, _ = _capture()
        with tempfile.TemporaryDirectory() as directory:
            storage = ImmutableDailyArchiveStorage(
                Path(directory),
                free_bytes=lambda _path: _FREE_BYTES,
            )
            storage.write_archive(
                scope=_scope(),
                captures=(capture,),
                rows=(_bar(capture),),
                completion=_completion(),
            )

            with self.assertRaisesRegex(
                DailyArchiveStorageError,
                "archive_already_exists",
            ):
                storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(_bar(capture),),
                    completion=_completion(),
                )

    def test_tampered_raw_or_manifest_fails_verification(self) -> None:
        capture, _ = _capture()
        for target in ("raw", "manifest"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                storage = ImmutableDailyArchiveStorage(
                    Path(directory),
                    free_bytes=lambda _path: _FREE_BYTES,
                )
                stored = storage.write_archive(
                    scope=_scope(),
                    captures=(capture,),
                    rows=(_bar(capture),),
                    completion=_completion(),
                )
                path = (
                    stored.raw_paths[0]
                    if target == "raw"
                    else stored.manifest_path
                )
                path.write_bytes(path.read_bytes() + b"tampered")

                with self.assertRaisesRegex(
                    DailyArchiveStorageError,
                    "archive_verification_failed",
                ):
                    storage.verify_archive(stored)

    def test_failure_evidence_preserves_safe_raw_capture_idempotently(self) -> None:
        capture, raw_body = _capture()
        with tempfile.TemporaryDirectory() as directory:
            storage = ImmutableDailyArchiveStorage(
                Path(directory),
                free_bytes=lambda _path: _FREE_BYTES,
            )

            first = storage.write_failure_evidence(
                scope=_scope(),
                captures=(capture,),
                error_code="HTTP_STATUS",
            )
            second = storage.write_failure_evidence(
                scope=_scope(),
                captures=(capture,),
                error_code="HTTP_STATUS",
            )

            self.assertEqual(first, second)
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    first.raw_paths[0].read_bytes()
                ),
                raw_body,
            )
            storage.verify_failure_evidence(first)


if __name__ == "__main__":
    unittest.main()
