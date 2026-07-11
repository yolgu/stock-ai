from __future__ import annotations

import base64
import hashlib
import io
import json
import unittest
from datetime import datetime, timezone

from rp001_s2.alpaca_boundary import (
    AlpacaCredentialCapability,
    StrictAlpacaBarsTransport,
)
from rp001_s2.alpaca_measurement import (
    AlpacaMeasurementError,
    AlpacaMinuteMeasurementCollector,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self.headers = {
            "Content-Type": content_type,
            "X-Request-ID": "request-id",
        }
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class _QueueOpener:
    def __init__(self, responses: tuple[_Response, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        return self.responses.pop(0)


def _scope(**overrides: object) -> CollectionScope:
    values: dict[str, object] = {
        "provider": "alpaca",
        "feed": "sip",
        "instrument_id": "TSLA",
        "symbol": "TSLA",
        "interval": "1m",
        "start_at": datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
        "end_at": datetime(2026, 7, 10, 13, 35, tzinfo=timezone.utc),
        "adjustment_mode": "raw",
        "session_scope": "provider_all",
        "sample_role": SampleRole.SEEN,
    }
    values.update(overrides)
    return CollectionScope(**values)


def _bar(
    timestamp: str,
    *,
    open_price: int | float = 100,
    high_price: int | float = 103,
    low_price: int | float = 99,
    close_price: int | float = 102,
    volume: int | float = 1000,
    trade_count: int | float = 20,
    vwap: int | float = 101,
) -> dict[str, object]:
    return {
        "t": timestamp,
        "o": open_price,
        "h": high_price,
        "l": low_price,
        "c": close_price,
        "v": volume,
        "n": trade_count,
        "vw": vwap,
    }


def _body(
    bars: list[dict[str, object]],
    next_page_token: str | None,
    *,
    symbol: str = "TSLA",
    currency: object = "USD",
    include_currency: bool = True,
) -> bytes:
    value: dict[str, object] = {
        "bars": bars,
        "symbol": symbol,
        "next_page_token": next_page_token,
    }
    if include_currency:
        value["currency"] = currency
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _collector(
    responses: tuple[_Response, ...],
    *,
    scope: CollectionScope | None = None,
    received_at: datetime = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc),
) -> tuple[AlpacaMinuteMeasurementCollector, _QueueOpener, CollectionScope]:
    effective_scope = scope or _scope()
    opener = _QueueOpener(responses)
    credentials = AlpacaCredentialCapability.consume(
        {
            "APCA_API_KEY_ID": "fixture-key-id",
            "APCA_API_SECRET_KEY": "fixture-secret-key",
        }
    )
    transport = StrictAlpacaBarsTransport(
        opener=opener,
        scope=effective_scope,
        credentials=credentials,
    )
    return (
        AlpacaMinuteMeasurementCollector(
            transport=transport,
            clock=lambda: received_at,
        ),
        opener,
        effective_scope,
    )


class AlpacaMinuteMeasurementContractTest(unittest.TestCase):
    def test_preserves_numeric_lexemes_raw_body_and_row_lineage(self) -> None:
        raw_body = (
            b'{"bars":[{"t":"2026-07-10T13:30:00Z",'
            b'"o":1.000e2,"h":1.03E+2,"l":9.9e1,"c":1.02e2,'
            b'"v":1e3,"n":2E1,"vw":1.01e2}],"symbol":"TSLA",'
            b'"currency":"USD","next_page_token":null}'
        )
        collector, opener, scope = _collector((_Response(raw_body),))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(result.completion_reason, "provider_terminal")
        self.assertEqual(len(result.rows), 1)
        row = result.rows[0]
        self.assertEqual(row.open_price.text, "1.000e2")
        self.assertEqual(row.high_price.text, "1.03E+2")
        self.assertEqual(row.low_price.text, "9.9e1")
        self.assertEqual(row.close_price.text, "1.02e2")
        self.assertEqual(row.volume.text, "1e3")
        self.assertEqual(row.trade_count.text, "2E1")
        self.assertEqual(row.vwap.text, "1.01e2")
        self.assertEqual(row.source_capture_ordinal, 0)
        self.assertEqual(row.source_row_index, 0)
        self.assertEqual(row.source_body_sha256, hashlib.sha256(raw_body).hexdigest())
        self.assertEqual(row.available_at, "2026-07-10T14:00:00Z")
        self.assertEqual(row.bar_end, "2026-07-10T13:31:00Z")
        self.assertEqual(len(row.occurrences), 1)
        capture = result.captures[0]
        self.assertEqual(base64.b64decode(capture.body_base64), raw_body)
        self.assertEqual(capture.body_sha256, hashlib.sha256(raw_body).hexdigest())
        self.assertEqual(capture.received_at, "2026-07-10T14:00:00Z")
        self.assertEqual(capture.headers, (("content-type", "application/json"),))
        self.assertEqual(len(opener.requests), 1)

    def test_short_page_with_token_continues_until_null_terminal(self) -> None:
        first = _Response(
            _body([_bar("2026-07-10T13:30:00Z")], "next/token")
        )
        second = _Response(
            _body([_bar("2026-07-10T13:31:00Z")], None)
        )
        collector, opener, scope = _collector((first, second))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len(result.captures), 2)
        self.assertEqual(len(opener.requests), 2)
        self.assertTrue(
            getattr(opener.requests[1], "full_url").endswith(
                "&page_token=next%2Ftoken"
            )
        )
        cursor_sha256 = hashlib.sha256(b"next/token").hexdigest()
        self.assertNotIn("next/token", result.captures[1].sanitized_url)
        self.assertNotIn("next/token", repr(result.captures[0]))
        self.assertEqual(
            result.captures[1].query[-1],
            ("page_token_sha256", cursor_sha256),
        )
        self.assertIn(cursor_sha256, result.captures[1].sanitized_url)

    def test_credential_echoing_error_is_rejected_without_capture_or_body_leak(self) -> None:
        secret = "fixture-secret-key"
        collector, _, scope = _collector(
            (
                _Response(
                    ('{"message":"' + secret + '"}').encode("utf-8"),
                    status=401,
                ),
            )
        )

        with self.assertRaises(AlpacaMeasurementError) as raised:
            collector.collect(scope=scope, page_limit=4)

        self.assertEqual(raised.exception.captures, ())
        self.assertNotIn(secret, repr(raised.exception) + str(raised.exception))

    def test_empty_null_is_explicit_data_unavailable(self) -> None:
        collector, _, scope = _collector((_Response(_body([], None)),))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(result.rows, ())
        self.assertEqual(result.completion_reason, "data_unavailable")
        self.assertEqual(len(result.captures), 1)

    def test_empty_page_with_token_is_invalid(self) -> None:
        collector, _, scope = _collector((_Response(_body([], "next")),))

        with self.assertRaisesRegex(
            AlpacaMeasurementError,
            "NO_PAGINATION_PROGRESS",
        ):
            collector.collect(scope=scope, page_limit=4)

    def test_response_and_row_shapes_are_exact(self) -> None:
        valid_bar = _bar("2026-07-10T13:30:00Z")
        invalid_values: list[dict[str, object]] = [
            {"bars": [valid_bar], "symbol": "TSLA"},
            {
                "bars": [valid_bar],
                "symbol": "TSLA",
                "next_page_token": None,
                "extra": 1,
            },
            {
                "bars": [{key: value for key, value in valid_bar.items() if key != "vw"}],
                "symbol": "TSLA",
                "next_page_token": None,
            },
            {
                "bars": [{**valid_bar, "extra": 1}],
                "symbol": "TSLA",
                "next_page_token": None,
            },
        ]

        for value in invalid_values:
            with self.subTest(keys=tuple(value)):
                body = json.dumps(value, separators=(",", ":")).encode("utf-8")
                collector, _, scope = _collector((_Response(body),))
                with self.assertRaisesRegex(
                    AlpacaMeasurementError,
                    "INVALID_RESPONSE_SHAPE",
                ):
                    collector.collect(scope=scope, page_limit=4)

    def test_wrong_symbol_or_currency_is_invalid_and_absent_currency_means_usd(self) -> None:
        for body in (
            _body([_bar("2026-07-10T13:30:00Z")], None, symbol="AAPL"),
            _body(
                [_bar("2026-07-10T13:30:00Z")],
                None,
                currency="EUR",
            ),
        ):
            with self.subTest(body=body):
                collector, _, scope = _collector((_Response(body),))
                with self.assertRaisesRegex(
                    AlpacaMeasurementError,
                    "RESPONSE_SCOPE_MISMATCH",
                ):
                    collector.collect(scope=scope, page_limit=4)

        absent = _body(
            [_bar("2026-07-10T13:30:00Z")],
            None,
            include_currency=False,
        )
        collector, _, scope = _collector((_Response(absent),))
        result = collector.collect(scope=scope, page_limit=4)
        self.assertEqual(result.rows[0].currency, "USD")

    def test_more_than_ten_thousand_rows_is_invalid(self) -> None:
        repeated = [_bar("2026-07-10T13:30:00Z")] * 10_001
        collector, _, scope = _collector((_Response(_body(repeated, None)),))

        with self.assertRaisesRegex(
            AlpacaMeasurementError,
            "INVALID_RESPONSE_SHAPE",
        ):
            collector.collect(scope=scope, page_limit=4)

    def test_page_timestamps_must_be_strictly_ascending_and_unique(self) -> None:
        invalid_pages = (
            [
                _bar("2026-07-10T13:31:00Z"),
                _bar("2026-07-10T13:30:00Z"),
            ],
            [
                _bar("2026-07-10T13:30:00Z"),
                _bar("2026-07-10T13:30:00Z"),
            ],
        )

        for bars in invalid_pages:
            with self.subTest(bars=bars):
                collector, _, scope = _collector((_Response(_body(bars, None)),))
                with self.assertRaisesRegex(
                    AlpacaMeasurementError,
                    "PAGE_ORDER_INVALID",
                ):
                    collector.collect(scope=scope, page_limit=4)

    def test_identical_boundary_overlap_merges_occurrences(self) -> None:
        first = _Response(
            _body(
                [
                    _bar("2026-07-10T13:30:00Z"),
                    _bar("2026-07-10T13:31:00Z"),
                ],
                "next",
            )
        )
        second = _Response(
            _body(
                [
                    _bar("2026-07-10T13:31:00Z"),
                    _bar("2026-07-10T13:32:00Z"),
                ],
                None,
            )
        )
        collector, _, scope = _collector((first, second))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.overlap_count, 1)
        self.assertEqual(len(result.rows[1].occurrences), 2)
        self.assertEqual(result.rows[1].occurrences[0][1:], (0, 1))
        self.assertEqual(result.rows[1].occurrences[1][1:], (1, 0))

    def test_conflicting_boundary_overlap_is_invalid(self) -> None:
        first = _Response(
            _body([_bar("2026-07-10T13:30:00Z")], "next")
        )
        second = _Response(
            _body(
                [_bar("2026-07-10T13:30:00Z", close_price=101)],
                None,
            )
        )
        collector, _, scope = _collector((first, second))

        with self.assertRaisesRegex(
            AlpacaMeasurementError,
            "CONFLICTING_DUPLICATE",
        ):
            collector.collect(scope=scope, page_limit=4)

    def test_page_cannot_move_backward_across_page_boundary(self) -> None:
        first = _Response(
            _body(
                [
                    _bar("2026-07-10T13:30:00Z"),
                    _bar("2026-07-10T13:31:00Z"),
                ],
                "next",
            )
        )
        second = _Response(
            _body(
                [
                    _bar("2026-07-10T13:30:00Z"),
                    _bar("2026-07-10T13:32:00Z"),
                ],
                None,
            )
        )
        collector, _, scope = _collector((first, second))

        with self.assertRaisesRegex(
            AlpacaMeasurementError,
            "PAGE_ORDER_INVALID",
        ):
            collector.collect(scope=scope, page_limit=4)

    def test_repeated_token_no_progress_and_page_cap_are_invalid(self) -> None:
        cases = (
            (
                (
                    _Response(_body([_bar("2026-07-10T13:30:00Z")], "same")),
                    _Response(_body([_bar("2026-07-10T13:31:00Z")], "same")),
                ),
                4,
                "REPEATED_PAGE_TOKEN",
            ),
            (
                (
                    _Response(_body([_bar("2026-07-10T13:30:00Z")], "next-1")),
                    _Response(_body([_bar("2026-07-10T13:30:00Z")], "next-2")),
                ),
                4,
                "NO_PAGINATION_PROGRESS",
            ),
            (
                (_Response(_body([_bar("2026-07-10T13:30:00Z")], "next")),),
                1,
                "PAGE_LIMIT_EXCEEDED",
            ),
        )

        for responses, page_limit, error_code in cases:
            with self.subTest(error_code=error_code):
                collector, _, scope = _collector(responses)
                with self.assertRaisesRegex(AlpacaMeasurementError, error_code):
                    collector.collect(scope=scope, page_limit=page_limit)

    def test_rows_must_stay_inside_half_open_scope_and_be_completed(self) -> None:
        invalid_cases = (
            (
                "2026-07-10T13:29:00Z",
                datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc),
                "BAR_OUTSIDE_SCOPE",
            ),
            (
                "2026-07-10T13:35:00Z",
                datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc),
                "BAR_OUTSIDE_SCOPE",
            ),
            (
                "2026-07-10T13:30:00Z",
                datetime(2026, 7, 10, 13, 30, 30, tzinfo=timezone.utc),
                "BAR_NOT_COMPLETED",
            ),
        )

        for timestamp, received_at, error_code in invalid_cases:
            with self.subTest(timestamp=timestamp, error_code=error_code):
                collector, _, scope = _collector(
                    (_Response(_body([_bar(timestamp)], None)),),
                    received_at=received_at,
                )
                with self.assertRaisesRegex(AlpacaMeasurementError, error_code):
                    collector.collect(scope=scope, page_limit=4)

    def test_ohlc_volume_trade_count_and_vwap_invariants_are_enforced(self) -> None:
        invalid_bars = (
            _bar("2026-07-10T13:30:00Z", low_price=101, open_price=100),
            _bar("2026-07-10T13:30:00Z", volume=-1),
            _bar("2026-07-10T13:30:00Z", trade_count=-1),
            _bar("2026-07-10T13:30:00Z", trade_count=1.5),
            _bar("2026-07-10T13:30:00Z", vwap=-1),
        )

        for bar in invalid_bars:
            with self.subTest(bar=bar):
                collector, _, scope = _collector(
                    (_Response(_body([bar], None)),)
                )
                with self.assertRaisesRegex(
                    AlpacaMeasurementError,
                    "BAR_INVARIANT",
                ):
                    collector.collect(scope=scope, page_limit=4)

    def test_non_json_http_failures_preserve_capture(self) -> None:
        cases = (
            (_Response(b'{"error":"denied"}', status=403), "HTTP_STATUS"),
            (
                _Response(
                    _body([_bar("2026-07-10T13:30:00Z")], None),
                    content_type="text/plain",
                ),
                "INVALID_CONTENT_TYPE",
            ),
        )

        for response, error_code in cases:
            with self.subTest(error_code=error_code):
                collector, _, scope = _collector((response,))
                with self.assertRaises(AlpacaMeasurementError) as raised:
                    collector.collect(scope=scope, page_limit=4)
                self.assertEqual(raised.exception.code, error_code)
                self.assertEqual(len(raised.exception.captures), 1)

    def test_feed_and_adjustment_scopes_remain_separate(self) -> None:
        collections = []
        for feed, adjustment in (
            ("sip", "raw"),
            ("iex", "raw"),
            ("sip", "split"),
        ):
            scope = _scope(feed=feed, adjustment_mode=adjustment)
            collector, _, _ = _collector(
                (
                    _Response(
                        _body([_bar("2026-07-10T13:30:00Z")], None)
                    ),
                ),
                scope=scope,
            )
            collections.append(collector.collect(scope=scope, page_limit=4))

        self.assertEqual(len({item.scope.acquisition_key for item in collections}), 3)
        self.assertTrue(all(len(item.rows) == 1 for item in collections))
        self.assertTrue(all(item.overlap_count == 0 for item in collections))

    def test_transport_scope_cannot_be_relabelled_at_collection_time(self) -> None:
        collector, opener, _ = _collector(
            (
                _Response(
                    _body([_bar("2026-07-10T13:30:00Z")], None)
                ),
            )
        )

        with self.assertRaisesRegex(
            AlpacaMeasurementError,
            "COLLECTION_SCOPE_MISMATCH",
        ):
            collector.collect(scope=_scope(feed="iex"), page_limit=4)

        self.assertEqual(opener.requests, [])


if __name__ == "__main__":
    unittest.main()
