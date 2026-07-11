from __future__ import annotations

import base64
import hashlib
import io
import json
import unittest
from datetime import datetime, timezone

from rp001.toss_research_collector import HttpRequest
from rp001_s2.alpaca_boundary import AlpacaCredentialCapability
from rp001_s2.alpaca_daily import (
    AlpacaDailyCollector,
    AlpacaDailyError,
    StrictAlpacaDailyTransport,
    build_live_strict_alpaca_daily_transport,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, _RejectRedirectHandler


_KEY_ID = "fixture-key-id"
_SECRET_KEY = "fixture-secret-key"
_EXPECTED_URL = (
    "https://data.alpaca.markets/v2/stocks/TSLA/bars?"
    "timeframe=1Day&start=2016-01-01T00%3A00%3A00Z&"
    "end=2016-01-03T00%3A00%3A00Z&limit=10000&adjustment=raw&"
    "asof=-&feed=sip&currency=USD&sort=asc"
)


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
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
        "interval": "1d",
        "start_at": datetime(2016, 1, 1, tzinfo=timezone.utc),
        "end_at": datetime(2016, 1, 4, tzinfo=timezone.utc),
        "adjustment_mode": "raw",
        "session_scope": "provider_all",
        "sample_role": SampleRole.SEEN,
    }
    values.update(overrides)
    return CollectionScope(**values)


def _credentials() -> AlpacaCredentialCapability:
    return AlpacaCredentialCapability.consume(
        {
            "APCA_API_KEY_ID": _KEY_ID,
            "APCA_API_SECRET_KEY": _SECRET_KEY,
        }
    )


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


def _transport(
    opener: _QueueOpener,
    scope: CollectionScope | None = None,
) -> StrictAlpacaDailyTransport:
    return StrictAlpacaDailyTransport(
        opener=opener,
        scope=scope or _scope(),
        credentials=_credentials(),
    )


def _collector(
    responses: tuple[_Response, ...],
    *,
    scope: CollectionScope | None = None,
    received_at: datetime = datetime(2016, 1, 10, tzinfo=timezone.utc),
) -> tuple[AlpacaDailyCollector, _QueueOpener, CollectionScope]:
    effective_scope = scope or _scope()
    opener = _QueueOpener(responses)
    transport = _transport(opener, effective_scope)
    return (
        AlpacaDailyCollector(
            transport=transport,
            clock=lambda: received_at,
        ),
        opener,
        effective_scope,
    )


def _request(url: str = _EXPECTED_URL, **header_overrides: str) -> HttpRequest:
    headers = {
        "Accept": "application/json",
        "APCA-API-KEY-ID": _KEY_ID,
        "APCA-API-SECRET-KEY": _SECRET_KEY,
    }
    headers.update(header_overrides)
    return HttpRequest(method="GET", url=url, headers=headers)


class StrictAlpacaDailyBoundaryTest(unittest.TestCase):
    def test_builds_exact_one_day_half_open_request(self) -> None:
        opener = _QueueOpener((_Response(_body([], None)),))
        transport = _transport(opener)

        response = transport.request_page()

        self.assertEqual(response.status, 200)
        self.assertEqual(len(opener.requests), 1)
        outgoing = opener.requests[0]
        self.assertEqual(getattr(outgoing, "method"), "GET")
        self.assertEqual(getattr(outgoing, "full_url"), _EXPECTED_URL)
        self.assertEqual(
            dict(getattr(outgoing, "header_items")()),
            {
                "Accept": "application/json",
                "Apca-api-key-id": _KEY_ID,
                "Apca-api-secret-key": _SECRET_KEY,
            },
        )

    def test_rejects_non_daily_or_non_us_scope_before_open(self) -> None:
        opener = _QueueOpener(())
        invalid_scopes = (
            _scope(provider="toss"),
            _scope(feed="otc"),
            _scope(symbol="000660", instrument_id="000660"),
            _scope(symbol="tsla", instrument_id="tsla"),
            _scope(interval="1m"),
            _scope(adjustment_mode="all"),
            _scope(session_scope="regular"),
            _scope(start_at=datetime(2016, 1, 1, 0, 1, tzinfo=timezone.utc)),
            _scope(end_at=datetime(2016, 1, 1, 12, 0, tzinfo=timezone.utc)),
        )

        for scope in invalid_scopes:
            with self.subTest(scope=scope.to_canonical_body()):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "allowed_scope_invalid"):
                    StrictAlpacaDailyTransport(
                        opener=opener,
                        scope=scope,
                        credentials=_credentials(),
                    )
        self.assertEqual(opener.requests, [])

    def test_rejects_operational_endpoint_origin_query_and_header_variants(self) -> None:
        opener = _QueueOpener(())
        transport = _transport(opener)
        forbidden_urls = (
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/orders"),
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/account"),
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/assets"),
            _EXPECTED_URL.replace("https://", "http://"),
            _EXPECTED_URL.replace("data.alpaca.markets", "evil.example"),
            _EXPECTED_URL.replace("data.alpaca.markets", "data.alpaca.markets:443"),
            _EXPECTED_URL.replace("/TSLA/bars", "/%2e%2e/orders"),
            _EXPECTED_URL.replace("timeframe=1Day", "timeframe=1Min"),
            _EXPECTED_URL.replace("limit=10000", "extra=1&limit=10000"),
            _EXPECTED_URL.replace("currency=USD&sort=asc", "sort=asc&currency=USD"),
            _EXPECTED_URL + "#fragment",
        )

        for url in forbidden_urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(_request(url))
        for request in (
            HttpRequest(method="POST", url=_EXPECTED_URL, headers=_request().headers),
            _request(**{"APCA-API-KEY-ID": "wrong"}),
            _request(**{"APCA-API-SECRET-KEY": "wrong"}),
            _request(Accept="text/plain"),
        ):
            with self.subTest(request=repr(request)):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(request)
        self.assertEqual(opener.requests, [])

    def test_page_token_is_last_and_redirects_are_disabled_for_live_transport(self) -> None:
        opener = _QueueOpener((_Response(_body([], None)),))
        transport = _transport(opener)

        transport.request_page("next/token+=")

        self.assertEqual(
            getattr(opener.requests[0], "full_url"),
            _EXPECTED_URL + "&page_token=next%2Ftoken%2B%3D",
        )
        live = build_live_strict_alpaca_daily_transport(
            scope=_scope(),
            credentials=_credentials(),
        )
        self.assertTrue(
            any(
                isinstance(handler, _RejectRedirectHandler)
                for handler in live._opener.handlers
            )
        )


class AlpacaDailyCollectionTest(unittest.TestCase):
    def test_preserves_numeric_lexemes_raw_body_and_daily_lineage(self) -> None:
        raw_body = (
            b'{"bars":[{"t":"2016-01-01T00:00:00Z",'
            b'"o":1e2,"h":1.03E2,"l":9.9e1,"c":1.02e2,'
            b'"v":1e3,"n":2E1,"vw":1.01e2}],"symbol":"TSLA",'
            b'"currency":"USD","next_page_token":null}'
        )
        collector, opener, scope = _collector((_Response(raw_body),))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(result.completion_reason, "provider_terminal")
        self.assertEqual(len(result.rows), 1)
        row = result.rows[0]
        self.assertEqual(row.source_timestamp, "2016-01-01T00:00:00Z")
        self.assertEqual(row.bar_end, "2016-01-02T00:00:00Z")
        self.assertEqual(row.open_price.text, "1e2")
        self.assertEqual(row.high_price.text, "1.03E2")
        self.assertEqual(row.volume.text, "1e3")
        self.assertEqual(row.source_capture_ordinal, 0)
        self.assertEqual(row.source_row_index, 0)
        self.assertEqual(row.available_at, "2016-01-10T00:00:00Z")
        capture = result.captures[0]
        self.assertEqual(base64.b64decode(capture.body_base64), raw_body)
        self.assertEqual(capture.body_sha256, hashlib.sha256(raw_body).hexdigest())
        self.assertEqual(row.source_body_sha256, capture.body_sha256)
        self.assertEqual(len(opener.requests), 1)

    def test_short_page_with_token_continues_and_overlap_merges(self) -> None:
        first = _Response(
            _body(
                [
                    _bar("2016-01-01T00:00:00Z"),
                    _bar("2016-01-02T00:00:00Z"),
                ],
                "next",
            )
        )
        second = _Response(
            _body(
                [
                    _bar("2016-01-02T00:00:00Z"),
                    _bar("2016-01-03T00:00:00Z"),
                ],
                None,
            )
        )
        collector, opener, scope = _collector((first, second))

        result = collector.collect(scope=scope, page_limit=4)

        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.overlap_count, 1)
        self.assertEqual(len(result.rows[1].occurrences), 2)
        self.assertEqual(len(opener.requests), 2)

    def test_conflicting_overlap_or_nonascending_page_is_invalid(self) -> None:
        cases = (
            (
                _Response(_body([_bar("2016-01-01T00:00:00Z")], "next")),
                _Response(
                    _body(
                        [_bar("2016-01-01T00:00:00Z", close_price=101)],
                        None,
                    )
                ),
                "CONFLICTING_DUPLICATE",
            ),
            (
                _Response(
                    _body(
                        [
                            _bar("2016-01-02T00:00:00Z"),
                            _bar("2016-01-01T00:00:00Z"),
                        ],
                        None,
                    )
                ),
                None,
                "PAGE_ORDER_INVALID",
            ),
        )

        for first, second, error_code in cases:
            responses = (first,) if second is None else (first, second)
            collector, _, scope = _collector(responses)
            with self.subTest(error_code=error_code):
                with self.assertRaisesRegex(AlpacaDailyError, error_code):
                    collector.collect(scope=scope, page_limit=4)

    def test_empty_terminal_and_invalid_pagination_states_are_explicit(self) -> None:
        collector, _, scope = _collector((_Response(_body([], None)),))
        result = collector.collect(scope=scope, page_limit=4)
        self.assertEqual(result.rows, ())
        self.assertEqual(result.completion_reason, "data_unavailable")

        invalid_cases = (
            (
                (_Response(_body([], "next")),),
                4,
                "NO_PAGINATION_PROGRESS",
            ),
            (
                (
                    _Response(_body([_bar("2016-01-01T00:00:00Z")], "same")),
                    _Response(_body([_bar("2016-01-02T00:00:00Z")], "same")),
                ),
                4,
                "REPEATED_PAGE_TOKEN",
            ),
            (
                (_Response(_body([_bar("2016-01-01T00:00:00Z")], "next")),),
                1,
                "PAGE_LIMIT_EXCEEDED",
            ),
        )
        for responses, page_limit, error_code in invalid_cases:
            with self.subTest(error_code=error_code):
                collector, _, scope = _collector(responses)
                with self.assertRaisesRegex(AlpacaDailyError, error_code):
                    collector.collect(scope=scope, page_limit=page_limit)

    def test_response_and_bar_shapes_symbol_currency_and_limit_are_exact(self) -> None:
        valid_bar = _bar("2016-01-01T00:00:00Z")
        invalid_values: tuple[tuple[object, str], ...] = (
            ({"bars": [valid_bar], "symbol": "TSLA"}, "INVALID_RESPONSE_SHAPE"),
            (
                {
                    "bars": [valid_bar],
                    "symbol": "TSLA",
                    "next_page_token": None,
                    "extra": 1,
                },
                "INVALID_RESPONSE_SHAPE",
            ),
            (
                {
                    "bars": [{key: value for key, value in valid_bar.items() if key != "n"}],
                    "symbol": "TSLA",
                    "next_page_token": None,
                },
                "INVALID_RESPONSE_SHAPE",
            ),
            (
                json.loads(_body([valid_bar], None, symbol="AAPL")),
                "RESPONSE_SCOPE_MISMATCH",
            ),
            (
                json.loads(_body([valid_bar], None, currency="EUR")),
                "RESPONSE_SCOPE_MISMATCH",
            ),
            (
                json.loads(_body([valid_bar] * 10_001, None)),
                "INVALID_RESPONSE_SHAPE",
            ),
        )

        for value, error_code in invalid_values:
            with self.subTest(error_code=error_code):
                raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
                collector, _, scope = _collector((_Response(raw),))
                with self.assertRaisesRegex(AlpacaDailyError, error_code):
                    collector.collect(scope=scope, page_limit=4)

    def test_bar_timestamp_scope_completion_and_value_invariants(self) -> None:
        invalid_cases = (
            (
                _bar("2016-01-01T00:01:00Z"),
                datetime(2016, 1, 10, tzinfo=timezone.utc),
                "INVALID_RESPONSE_SHAPE",
            ),
            (
                _bar("2015-12-31T00:00:00Z"),
                datetime(2016, 1, 10, tzinfo=timezone.utc),
                "BAR_OUTSIDE_SCOPE",
            ),
            (
                _bar("2016-01-01T00:00:00Z"),
                datetime(2016, 1, 1, 12, 0, tzinfo=timezone.utc),
                "BAR_NOT_COMPLETED",
            ),
            (
                _bar("2016-01-01T00:00:00Z", low_price=101, open_price=100),
                datetime(2016, 1, 10, tzinfo=timezone.utc),
                "BAR_INVARIANT",
            ),
            (
                _bar("2016-01-01T00:00:00Z", volume=-1),
                datetime(2016, 1, 10, tzinfo=timezone.utc),
                "BAR_INVARIANT",
            ),
            (
                _bar("2016-01-01T00:00:00Z", trade_count=1.5),
                datetime(2016, 1, 10, tzinfo=timezone.utc),
                "BAR_INVARIANT",
            ),
        )

        for bar, received_at, error_code in invalid_cases:
            with self.subTest(error_code=error_code):
                collector, _, scope = _collector(
                    (_Response(_body([bar], None)),),
                    received_at=received_at,
                )
                with self.assertRaisesRegex(AlpacaDailyError, error_code):
                    collector.collect(scope=scope, page_limit=4)

    def test_sip_entitlement_denial_is_one_scope_failure_without_iex_fallback(self) -> None:
        response = _Response(
            b'{"message":"subscription does not permit querying SIP"}',
            status=403,
        )
        collector, opener, scope = _collector((response,))

        with self.assertRaises(AlpacaDailyError) as raised:
            collector.collect(scope=scope, page_limit=4)

        self.assertEqual(raised.exception.code, "SCOPE_ACCESS_DENIED")
        self.assertEqual(len(raised.exception.captures), 1)
        self.assertEqual(len(opener.requests), 1)
        self.assertIn("feed=sip", getattr(opener.requests[0], "full_url"))
        self.assertNotIn("feed=iex", getattr(opener.requests[0], "full_url"))

    def test_collection_scope_cannot_relabel_feed_or_adjustment(self) -> None:
        collector, opener, _ = _collector(
            (_Response(_body([_bar("2016-01-01T00:00:00Z")], None)),)
        )

        with self.assertRaisesRegex(AlpacaDailyError, "COLLECTION_SCOPE_MISMATCH"):
            collector.collect(scope=_scope(feed="iex"), page_limit=4)

        self.assertEqual(opener.requests, [])


if __name__ == "__main__":
    unittest.main()
