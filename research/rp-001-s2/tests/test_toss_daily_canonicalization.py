from __future__ import annotations

import base64
import hashlib
import json
import unittest
from datetime import date, datetime, timezone

from rp001.toss_research_collector import (
    CandleCollection,
    CandleRow,
    CanonicalScalar,
    RawHttpCapture,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.toss_daily_canonicalization import (
    DailyCanonicalizationError,
    canonicalize_toss_daily_collection,
)


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


def _raw_row(close_price: str = "102") -> dict[str, str]:
    return {
        "timestamp": "2026-07-01T04:00:00Z",
        "openPrice": "100",
        "highPrice": "103",
        "lowPrice": "99",
        "closePrice": close_price,
        "volume": "1000",
        "currency": "USD",
    }


def _capture(row: dict[str, str], ordinal: int) -> RawHttpCapture:
    body = json.dumps(
        {"result": {"candles": [row], "nextBefore": None}},
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
            ("adjusted", "false"),
            ("before", f"cursor-{ordinal}"),
        ),
        status=200,
        headers=(("content-type", "application/json"),),
        received_at=f"2026-07-0{ordinal + 3}T00:00:00Z",
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )


def _row() -> CandleRow:
    scalar = lambda value: CanonicalScalar("decimal_string", value)
    return CandleRow(
        timestamp="2026-07-01T04:00:00Z",
        open_price=scalar("100"),
        high_price=scalar("103"),
        low_price=scalar("99"),
        close_price=scalar("102"),
        volume=scalar("1000"),
        currency="USD",
    )


def _collection(captures: tuple[RawHttpCapture, ...]) -> CandleCollection:
    return CandleCollection(
        symbol="TSLA",
        adjusted=False,
        start=date(2026, 7, 1),
        end=date(2026, 7, 2),
        session_timezone="America/New_York",
        provider_session_membership="not_documented",
        analysis_rows=(_row(),),
        audit_only_rows=(),
        captures=captures,
    )


class TossDailyCanonicalizationTest(unittest.TestCase):
    def test_retains_raw_body_row_lineage_and_duplicate_occurrences(self) -> None:
        captures = (_capture(_raw_row(), 0), _capture(_raw_row(), 1))

        rows = canonicalize_toss_daily_collection(
            _scope(),
            _collection(captures),
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.session_date, "2026-07-01")
        self.assertEqual(row.raw_body_sha256, captures[0].body_sha256)
        self.assertEqual(row.capture_ordinal, 0)
        self.assertEqual(row.source_row_index, 0)
        self.assertEqual(
            row.occurrences,
            (
                (captures[0].body_sha256, 0, 0),
                (captures[1].body_sha256, 1, 0),
            ),
        )
        self.assertEqual(row.close_price.text, "102")
        self.assertEqual(row.numeric_fidelity, "decimal_string_lexeme")

    def test_conflicting_raw_duplicate_is_invalid(self) -> None:
        captures = (
            _capture(_raw_row(), 0),
            _capture(_raw_row(close_price="101"), 1),
        )

        with self.assertRaisesRegex(
            DailyCanonicalizationError,
            "conflicting_duplicate",
        ):
            canonicalize_toss_daily_collection(
                _scope(),
                _collection(captures),
            )

    def test_scope_adjustment_must_match_collection(self) -> None:
        collection = _collection((_capture(_raw_row(), 0),))
        adjusted_scope = CollectionScope(
            **{
                **_scope().__dict__,
                "adjustment_mode": "adjusted",
            }
        )

        with self.assertRaisesRegex(
            DailyCanonicalizationError,
            "scope_mismatch",
        ):
            canonicalize_toss_daily_collection(adjusted_scope, collection)

    def test_korean_daily_timestamp_uses_provider_local_session_date(self) -> None:
        raw = {
            **_raw_row(),
            "timestamp": "2026-07-01T00:00:00+09:00",
            "currency": "KRW",
        }
        capture = _capture(raw, 0)
        scalar = lambda value: CanonicalScalar("decimal_string", value)
        collection = CandleCollection(
            symbol="000660",
            adjusted=False,
            start=date(2026, 7, 1),
            end=date(2026, 7, 2),
            session_timezone="Asia/Seoul",
            provider_session_membership="not_documented",
            analysis_rows=(
                CandleRow(
                    timestamp=raw["timestamp"],
                    open_price=scalar("100"),
                    high_price=scalar("103"),
                    low_price=scalar("99"),
                    close_price=scalar("102"),
                    volume=scalar("1000"),
                    currency="KRW",
                ),
            ),
            audit_only_rows=(),
            captures=(capture,),
        )
        scope = CollectionScope(
            provider="toss",
            feed="provider_all",
            instrument_id="000660",
            symbol="000660",
            interval="1d",
            start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            adjustment_mode="native",
            session_scope="provider_all",
            sample_role=SampleRole.SEEN,
        )

        rows = canonicalize_toss_daily_collection(scope, collection)

        self.assertEqual(rows[0].session_date, "2026-07-01")


if __name__ == "__main__":
    unittest.main()
