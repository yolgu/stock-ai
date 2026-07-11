from __future__ import annotations

import base64
import hashlib
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.alpaca_measurement import (
    AlpacaMeasuredMinuteBar,
    AlpacaMinuteCollection,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.intraday_measurement import IntradayCandleCollection, MeasuredBar
from rp001_s2.minute_canonicalization import (
    MinuteCanonicalizationError,
    canonicalize_alpaca_collection,
    canonicalize_toss_collection,
)


def _scope(
    *,
    provider: str = "toss",
    feed: str = "provider_all",
    symbol: str = "AAPL",
    start_at: datetime = datetime(2026, 7, 1, 0, 29, tzinfo=timezone.utc),
    end_at: datetime = datetime(2026, 7, 1, 0, 32, tzinfo=timezone.utc),
    adjustment_mode: str = "native",
) -> CollectionScope:
    return CollectionScope(
        provider=provider,
        feed=feed,
        instrument_id=symbol,
        symbol=symbol,
        interval="1m",
        start_at=start_at,
        end_at=end_at,
        adjustment_mode=adjustment_mode,
        session_scope="provider_all",
        sample_role=SampleRole.SEEN,
    )


def _capture(body: bytes, received_at: str) -> RawHttpCapture:
    return RawHttpCapture(
        endpoint_id="minute_bars",
        method="GET",
        sanitized_url="https://market-data.example/minute-bars",
        query=(),
        status=200,
        headers=(("content-type", "application/json"),),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _toss_row(
    *,
    source_timestamp: str,
    normalized_instant: str,
    bar_end: str,
    capture: RawHttpCapture,
    source_row_index: int,
    currency: str = "USD",
) -> MeasuredBar:
    occurrence = (capture.body_sha256, 0, source_row_index)
    return MeasuredBar(
        timestamp=source_timestamp,
        normalized_instant=normalized_instant,
        bar_end=bar_end,
        available_at=capture.received_at,
        open_price=CanonicalScalar("json_string", "100.10"),
        high_price=CanonicalScalar("json_string", "101.250"),
        low_price=CanonicalScalar("json_string", "99.875"),
        close_price=CanonicalScalar("json_string", "100.625"),
        volume=CanonicalScalar("json_string", "10.500"),
        currency=currency,
        source_body_sha256=capture.body_sha256,
        source_capture_ordinal=0,
        source_row_index=source_row_index,
        provider_order=source_row_index,
        occurrences=(occurrence,),
    )


def _toss_collection() -> tuple[CollectionScope, IntradayCandleCollection]:
    scope = _scope()
    capture = _capture(b'{"provider":"toss"}', "2026-07-01T00:31:30Z")
    verified = _toss_row(
        source_timestamp="2026-07-01T09:30:00+09:00",
        normalized_instant="2026-07-01T00:30:00Z",
        bar_end="2026-07-01T00:31:00Z",
        capture=capture,
        source_row_index=1,
    )
    out_of_scope = _toss_row(
        source_timestamp="2026-07-01T00:28:00Z",
        normalized_instant="2026-07-01T00:28:00Z",
        bar_end="2026-07-01T00:29:00Z",
        capture=capture,
        source_row_index=0,
    )
    partial = _toss_row(
        source_timestamp="2026-07-01T00:31:00Z",
        normalized_instant="2026-07-01T00:31:00Z",
        bar_end="2026-07-01T00:32:00Z",
        capture=capture,
        source_row_index=2,
    )
    collection = IntradayCandleCollection(
        symbol="AAPL",
        interval="1m",
        adjusted=False,
        start_at="2026-07-01T00:29:00Z",
        end_at="2026-07-01T00:32:00Z",
        analysis_rows=(verified,),
        audit_only_rows=(out_of_scope, partial),
        captures=(capture,),
        inclusive_overlap_count=0,
        requested_start_reached=True,
        completion_reason="start_boundary_reached",
    )
    return scope, collection


def _alpaca_collection() -> AlpacaMinuteCollection:
    scope = _scope(
        provider="alpaca",
        feed="sip",
        symbol="TSLA",
        start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
        adjustment_mode="raw",
    )
    first = _capture(b'{"page":1}', "2026-07-10T13:31:00Z")
    second = _capture(b'{"page":2}', "2026-07-10T13:31:30Z")
    occurrences = (
        (first.body_sha256, 0, 0),
        (second.body_sha256, 1, 0),
    )
    row = AlpacaMeasuredMinuteBar(
        source_timestamp="2026-07-10T13:30:00Z",
        normalized_instant="2026-07-10T13:30:00Z",
        bar_end="2026-07-10T13:31:00Z",
        available_at=first.received_at,
        open_price=CanonicalScalar("json_number", "1e2"),
        high_price=CanonicalScalar("json_number", "1.01e2"),
        low_price=CanonicalScalar("json_number", "9.9e1"),
        close_price=CanonicalScalar("json_number", "1.005e2"),
        volume=CanonicalScalar("json_number", "1.05e1"),
        trade_count=CanonicalScalar("json_number", "20"),
        vwap=CanonicalScalar("json_number", "1.001e2"),
        currency="USD",
        source_body_sha256=first.body_sha256,
        source_capture_ordinal=0,
        source_row_index=0,
        provider_order=0,
        occurrences=occurrences,
    )
    return AlpacaMinuteCollection(
        scope=scope,
        rows=(row,),
        captures=(first, second),
        overlap_count=1,
        completion_reason="provider_terminal",
    )


class MinuteCanonicalizationTest(unittest.TestCase):
    def test_toss_preserves_analysis_and_distinct_audit_quality_rows(self) -> None:
        scope, collection = _toss_collection()

        bars = canonicalize_toss_collection(scope, collection)

        self.assertEqual(
            tuple(bar.event_start_utc for bar in bars),
            (
                "2026-07-01T00:28:00Z",
                "2026-07-01T00:30:00Z",
                "2026-07-01T00:31:00Z",
            ),
        )
        self.assertEqual(
            tuple(bar.quality_status for bar in bars),
            ("audit_out_of_scope", "verified_completed", "audit_partial"),
        )
        verified = bars[1]
        self.assertEqual(verified.source_timestamp, "2026-07-01T09:30:00+09:00")
        self.assertEqual(verified.provider, "toss")
        self.assertEqual(verified.feed, "provider_all")
        self.assertEqual(verified.instrument_id, "AAPL")
        self.assertEqual(verified.adjustment_mode, "native")
        self.assertEqual(verified.numeric_fidelity, "decimal_string_lexeme")
        self.assertEqual(verified.session_type, "provider_all_unclassified")
        self.assertEqual(verified.session_date, "2026-06-30")
        self.assertEqual(verified.volume.text, "10.500")
        self.assertEqual(verified.received_at_utc, "2026-07-01T00:31:30Z")
        self.assertEqual(bars[2].research_available_at_utc, "2026-07-01T00:32:00Z")

    def test_alpaca_preserves_exponents_scope_and_every_overlap_occurrence(self) -> None:
        collection = _alpaca_collection()

        bars = canonicalize_alpaca_collection(collection)

        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar.provider, "alpaca")
        self.assertEqual(bar.feed, "sip")
        self.assertEqual(bar.adjustment_mode, "raw")
        self.assertEqual(bar.numeric_fidelity, "json_number_lexeme")
        self.assertEqual(bar.quality_status, "verified_completed")
        self.assertEqual(bar.session_date, "2026-07-10")
        self.assertEqual(bar.open_price.text, "1e2")
        self.assertEqual(bar.volume.text, "1.05e1")
        self.assertEqual(bar.occurrences, collection.rows[0].occurrences)

    def test_krw_session_date_uses_asia_seoul(self) -> None:
        scope, collection = _toss_collection()
        krw = replace(
            collection.analysis_rows[0],
            currency="KRW",
            timestamp="2026-07-01T00:30:00Z",
        )
        collection = replace(
            collection,
            analysis_rows=(krw,),
            audit_only_rows=(),
        )

        bars = canonicalize_toss_collection(scope, collection)

        self.assertEqual(bars[0].session_date, "2026-07-01")

    def test_rejects_scope_currency_duplicate_and_lineage_mismatches(self) -> None:
        scope, collection = _toss_collection()
        duplicate = replace(
            collection.analysis_rows[0],
            source_row_index=3,
            provider_order=3,
            occurrences=((collection.captures[0].body_sha256, 0, 3),),
        )
        invalid_cases = (
            (replace(scope, symbol="MSFT", instrument_id="MSFT"), collection),
            (replace(scope, feed="iex"), collection),
            (
                scope,
                replace(
                    collection,
                    analysis_rows=(
                        replace(collection.analysis_rows[0], currency="EUR"),
                    ),
                    audit_only_rows=(),
                ),
            ),
            (
                scope,
                replace(
                    collection,
                    analysis_rows=(collection.analysis_rows[0], duplicate),
                    audit_only_rows=(),
                ),
            ),
            (
                scope,
                replace(
                    collection,
                    analysis_rows=(collection.audit_only_rows[1],),
                    audit_only_rows=(),
                ),
            ),
            (
                scope,
                replace(
                    collection,
                    analysis_rows=(
                        replace(
                            collection.analysis_rows[0],
                            source_capture_ordinal=3,
                            occurrences=(("0" * 64, 3, 0),),
                        ),
                    ),
                ),
            ),
            (
                scope,
                replace(collection, adjusted=True),
            ),
        )
        for invalid_scope, invalid_collection in invalid_cases:
            with self.subTest(
                invalid_scope=invalid_scope,
                invalid_collection=invalid_collection,
            ):
                with self.assertRaises(MinuteCanonicalizationError):
                    canonicalize_toss_collection(
                        invalid_scope,
                        invalid_collection,
                    )

        alpaca = _alpaca_collection()
        with self.assertRaises(MinuteCanonicalizationError):
            canonicalize_alpaca_collection(
                replace(
                    alpaca,
                    scope=replace(alpaca.scope, feed="otc"),
                )
            )

    def test_rejects_values_outside_the_canonical_numeric_contract(self) -> None:
        scope, collection = _toss_collection()
        invalid_row = replace(
            collection.analysis_rows[0],
            open_price=CanonicalScalar("json_number", "100"),
        )

        with self.assertRaises(MinuteCanonicalizationError):
            canonicalize_toss_collection(
                scope,
                replace(collection, analysis_rows=(invalid_row,)),
            )


if __name__ == "__main__":
    unittest.main()
