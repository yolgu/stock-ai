from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pyarrow.parquet as parquet
import zstandard

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.toss_forward_microstructure import (
    SampledOrderbookLevel,
    SampledOrderbookSnapshot,
    SampledTradeObservation,
    SampledTradeStream,
)


_AVAILABLE_BYTES = 100 * 1024**3
_TRADE_URL = (
    "https://openapi.tossinvest.com/api/v1/trades?symbol=TSLA&count=50"
)
_ORDERBOOK_URL = (
    "https://openapi.tossinvest.com/api/v1/orderbook?symbol=TSLA"
)


def _capture(
    *,
    endpoint_id: str,
    url: str,
    query: tuple[tuple[str, str], ...],
    body: bytes,
    received_at: str,
    status: int = 200,
) -> RawHttpCapture:
    return RawHttpCapture(
        endpoint_id=endpoint_id,
        method="GET",
        sanitized_url=url,
        query=query,
        status=status,
        headers=(
            ("content-type", "application/json"),
            ("retry-after", "1"),
        ),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _success_evidence() -> tuple[SampledTradeStream, SampledOrderbookSnapshot]:
    trade_body = (
        b'{"result":[{"price":"250.100","volume":"10.500",'
        b'"timestamp":"2026-07-11T01:00:00.000Z","currency":"USD"}]}'
    )
    orderbook_body = (
        b'{"result":{"timestamp":"2026-07-11T01:00:00.000Z",'
        b'"currency":"USD","asks":[{"price":"250.20","volume":"12.0"}],'
        b'"bids":[{"price":"250.10","volume":"9"}]}}'
    )
    trade_capture = _capture(
        endpoint_id="sampled_trades_v1",
        url=_TRADE_URL,
        query=(("symbol", "TSLA"), ("count", "50")),
        body=trade_body,
        received_at="2026-07-11T01:00:01Z",
    )
    orderbook_capture = _capture(
        endpoint_id="sampled_orderbook_v1",
        url=_ORDERBOOK_URL,
        query=(("symbol", "TSLA"),),
        body=orderbook_body,
        received_at="2026-07-11T01:00:02Z",
    )
    occurrence = (trade_capture.body_sha256, 0, 0)
    trade_stream = SampledTradeStream(
        symbol="TSLA",
        observations=(
            SampledTradeObservation(
                price=CanonicalScalar(kind="json_string", text="250.100"),
                volume=CanonicalScalar(kind="json_string", text="10.500"),
                source_timestamp="2026-07-11T01:00:00.000Z",
                normalized_event_at="2026-07-11T01:00:00Z",
                received_at=trade_capture.received_at,
                currency="USD",
                source_body_sha256=trade_capture.body_sha256,
                source_capture_ordinal=0,
                source_row_index=0,
                source_occurrence=occurrence,
                duplicate_status="unique_poll_observation",
                ambiguous_occurrences=(occurrence,),
            ),
        ),
        captures=(trade_capture,),
    )
    orderbook_snapshot = SampledOrderbookSnapshot(
        symbol="TSLA",
        source_timestamp="2026-07-11T01:00:00.000Z",
        normalized_event_at="2026-07-11T01:00:00Z",
        received_at=orderbook_capture.received_at,
        currency="USD",
        asks=(
            SampledOrderbookLevel(
                side="ask",
                level=0,
                price=CanonicalScalar(kind="json_string", text="250.20"),
                volume=CanonicalScalar(kind="json_string", text="12.0"),
                source_body_sha256=orderbook_capture.body_sha256,
                source_capture_ordinal=1,
                source_row_index=0,
            ),
        ),
        bids=(
            SampledOrderbookLevel(
                side="bid",
                level=0,
                price=CanonicalScalar(kind="json_string", text="250.10"),
                volume=CanonicalScalar(kind="json_string", text="9"),
                source_body_sha256=orderbook_capture.body_sha256,
                source_capture_ordinal=1,
                source_row_index=1,
            ),
        ),
        source_body_sha256=orderbook_capture.body_sha256,
        source_capture_ordinal=1,
        source_row_index=0,
        capture=orderbook_capture,
    )
    return trade_stream, orderbook_snapshot


def _private_root(path: Path) -> None:
    os.chmod(path, 0o700)


class TossForwardArchiveContractTest(unittest.TestCase):
    def test_exports_immutable_forward_archive_contract(self) -> None:
        try:
            archive = importlib.import_module("rp001_s2.toss_forward_archive")
        except ModuleNotFoundError:
            archive = None

        self.assertIsNotNone(archive)
        self.assertTrue(hasattr(archive, "ImmutableTossForwardStorage"))
        self.assertTrue(hasattr(archive, "ForwardArchiveError"))
        self.assertTrue(hasattr(archive, "StoredForwardArchive"))
        self.assertTrue(hasattr(archive, "StoredForwardFailureEvidence"))

    def test_writes_exact_raw_canonical_parquet_and_idempotent_manifest(self) -> None:
        from rp001_s2.toss_forward_archive import ImmutableTossForwardStorage

        trade_stream, orderbook_snapshot = _success_evidence()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _private_root(root)
            storage = ImmutableTossForwardStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_archive(
                trade_stream=trade_stream,
                orderbook_snapshot=orderbook_snapshot,
            )
            before = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }
            repeated = storage.write_archive(
                trade_stream=trade_stream,
                orderbook_snapshot=orderbook_snapshot,
            )

            self.assertEqual(repeated, stored)
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.raw_paths[0].read_bytes()
                ),
                base64.b64decode(trade_stream.captures[0].body_base64),
            )
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.raw_paths[1].read_bytes()
                ),
                base64.b64decode(orderbook_snapshot.capture.body_base64),
            )
            trade_rows = parquet.read_table(stored.trades_path).to_pylist()
            self.assertEqual(trade_rows[0]["price_lexeme"], "250.100")
            self.assertEqual(trade_rows[0]["volume_lexeme"], "10.500")
            self.assertEqual(
                trade_rows[0]["completeness"],
                "not_complete_exchange_tape",
            )
            orderbook_rows = parquet.read_table(
                stored.orderbook_path
            ).to_pylist()
            self.assertEqual(
                [(row["side"], row["price_lexeme"]) for row in orderbook_rows],
                [("ask", "250.20"), ("bid", "250.10")],
            )
            self.assertTrue(
                all(
                    row["completeness"] == "not_complete_exchange_tape"
                    for row in orderbook_rows
                )
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
            identity = {
                "schemaVersion": "rp001-s2-toss-forward-archive.v1",
                "identityDomain": "rp001_s2.toss_forward_archive",
                "symbol": "TSLA",
                "captures": [
                    {
                        "endpointId": capture.endpoint_id,
                        "receivedAt": capture.received_at,
                        "bodySha256": capture.body_sha256,
                    }
                    for capture in (
                        trade_stream.captures[0],
                        orderbook_snapshot.capture,
                    )
                ],
            }
            expected_identity = hashlib.sha256(
                json.dumps(
                    identity,
                    allow_nan=False,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(stored.content_identity, expected_identity)
            self.assertEqual(manifest["contentIdentity"], expected_identity)
            self.assertEqual(
                manifest["claims"]["tradeStream"]["measurementKind"],
                "sampled_trade_stream",
            )
            self.assertEqual(
                manifest["claims"]["orderbookSnapshot"]["ofiStatus"],
                "not_identifiable",
            )
            self.assertEqual(
                stored.manifest_sha256_path.read_text(encoding="ascii"),
                f"{hashlib.sha256(manifest_bytes).hexdigest()}\n",
            )
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o600
                    for path in stored.archive_directory.rglob("*")
                    if path.is_file()
                )
            )
            after = {
                path.relative_to(stored.archive_directory): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in stored.archive_directory.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            storage.verify_archive(stored)

    def test_rejects_same_identity_conflict_and_detects_tampering(self) -> None:
        from rp001_s2.toss_forward_archive import (
            ForwardArchiveError,
            ImmutableTossForwardStorage,
        )

        trade_stream, orderbook_snapshot = _success_evidence()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _private_root(root)
            storage = ImmutableTossForwardStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )
            stored = storage.write_archive(
                trade_stream=trade_stream,
                orderbook_snapshot=orderbook_snapshot,
            )
            conflicting_capture = replace(
                trade_stream.captures[0],
                headers=(("content-type", "application/json"),),
            )

            with self.assertRaisesRegex(
                ForwardArchiveError,
                "forward_archive_conflict",
            ):
                storage.write_archive(
                    trade_stream=replace(
                        trade_stream,
                        captures=(conflicting_capture,),
                    ),
                    orderbook_snapshot=orderbook_snapshot,
                )

            stored.raw_paths[0].write_bytes(b"tampered")
            with self.assertRaisesRegex(
                ForwardArchiveError,
                "forward_archive_verification_failed",
            ):
                storage.verify_archive(stored)

    def test_rejects_canonical_rows_not_reconstructed_from_exact_raw(self) -> None:
        from rp001_s2.toss_forward_archive import (
            ForwardArchiveError,
            ImmutableTossForwardStorage,
        )

        trade_stream, orderbook_snapshot = _success_evidence()
        fabricated = replace(
            trade_stream,
            observations=(
                replace(
                    trade_stream.observations[0],
                    price=CanonicalScalar(kind="json_string", text="999.00"),
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _private_root(root)
            storage = ImmutableTossForwardStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            with self.assertRaisesRegex(
                ForwardArchiveError,
                "forward_archive_input_invalid",
            ):
                storage.write_archive(
                    trade_stream=fabricated,
                    orderbook_snapshot=orderbook_snapshot,
                )

            self.assertFalse((root / "success").exists())

    def test_failure_evidence_distinguishes_exact_and_auth_redacted_captures(
        self,
    ) -> None:
        from rp001_s2.toss_forward_archive import (
            ForwardArchiveError,
            ImmutableTossForwardStorage,
        )

        redacted_body = b'{"message":"invalid client"}'
        auth_capture = RawHttpCapture(
            endpoint_id="oauth_client_credentials_v1",
            method="POST",
            sanitized_url="https://openapi.tossinvest.com/oauth2/token",
            query=(),
            status=401,
            headers=(("content-type", "application/json"),),
            received_at="2026-07-11T01:00:00Z",
            body_base64="",
            body_sha256=hashlib.sha256(redacted_body).hexdigest(),
        )
        market_body = b'{"message":"temporarily unavailable"}'
        market_capture = _capture(
            endpoint_id="sampled_trades_v1",
            url=_TRADE_URL,
            query=(("symbol", "TSLA"), ("count", "50")),
            body=market_body,
            received_at="2026-07-11T01:00:01Z",
            status=503,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _private_root(root)
            storage = ImmutableTossForwardStorage(
                root,
                free_bytes=lambda _path: _AVAILABLE_BYTES,
            )

            stored = storage.write_failure_evidence(
                symbol="TSLA",
                error_code="HTTP_STATUS",
                captures=(auth_capture, market_capture),
            )
            before = stored.manifest_path.read_bytes()
            repeated = storage.write_failure_evidence(
                symbol="TSLA",
                error_code="HTTP_STATUS",
                captures=(auth_capture, market_capture),
            )

            self.assertEqual(repeated, stored)
            self.assertEqual(
                stored.evidence_directory,
                root
                / "failure-evidence"
                / "TSLA"
                / stored.evidence_digest,
            )
            manifest = json.loads(before)
            evidence = manifest["captureEvidence"]
            self.assertEqual(
                [item["rawAvailability"] for item in evidence],
                ["redacted_at_auth_boundary", "exact"],
            )
            self.assertNotIn("path", evidence[0])
            self.assertEqual(evidence[0]["bodySha256"], auth_capture.body_sha256)
            self.assertEqual(evidence[0]["status"], 401)
            self.assertEqual(
                evidence[0]["responseHeaders"],
                [{"name": "content-type", "value": "application/json"}],
            )
            self.assertEqual(
                zstandard.ZstdDecompressor().decompress(
                    stored.raw_paths[0].read_bytes()
                ),
                market_body,
            )
            self.assertFalse(
                any(
                    path.suffix == ".parquet"
                    for path in stored.evidence_directory.rglob("*")
                )
            )
            storage.verify_failure_evidence(stored)

            stored.raw_paths[0].write_bytes(b"tampered")
            with self.assertRaisesRegex(
                ForwardArchiveError,
                "forward_failure_evidence_verification_failed",
            ):
                storage.verify_failure_evidence(stored)


if __name__ == "__main__":
    unittest.main()
