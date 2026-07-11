from __future__ import annotations

import base64
import hashlib
import io
import json
import unittest
from datetime import datetime, timezone

from rp001.toss_research_collector import HttpRequest
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, _RejectRedirectHandler
from rp001_s2.toss_forward_microstructure import (
    MINIMUM_FORWARD_REQUEST_INTERVAL_SECONDS,
    ForwardMicrostructureError,
    StrictTossForwardTransport,
    TossForwardMicrostructureCollector,
    build_live_toss_forward_transport,
)


_TRADE_URL = (
    "https://openapi.tossinvest.com/api/v1/trades?symbol=TSLA&count=50"
)
_BOOK_URL = "https://openapi.tossinvest.com/api/v1/orderbook?symbol=TSLA"


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


def _body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _trade(
    *,
    price: str = "250.100",
    volume: str = "10.500",
    timestamp: str = "2026-07-11T01:00:00.000Z",
    currency: str = "USD",
) -> dict[str, str]:
    return {
        "price": price,
        "volume": volume,
        "timestamp": timestamp,
        "currency": currency,
    }


def _trade_response(rows: list[dict[str, str]]) -> _Response:
    return _Response(_body({"result": rows}))


def _book_response(
    *,
    timestamp: str | None = "2026-07-11T01:00:00.000Z",
    asks: list[dict[str, str]] | None = None,
    bids: list[dict[str, str]] | None = None,
    currency: str = "USD",
) -> _Response:
    return _Response(
        _body(
            {
                "result": {
                    "timestamp": timestamp,
                    "currency": currency,
                    "asks": asks
                    if asks is not None
                    else [
                        {"price": "250.20", "volume": "12.0"},
                        {"price": "250.30", "volume": "15"},
                    ],
                    "bids": bids
                    if bids is not None
                    else [
                        {"price": "250.10", "volume": "9"},
                        {"price": "250.00", "volume": "8.5"},
                    ],
                }
            }
        )
    )


def _request(url: str) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=url,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer ephemeral-token",
        },
    )


def _collector(
    responses: tuple[_Response, ...],
) -> tuple[TossForwardMicrostructureCollector, _QueueOpener, list[str]]:
    opener = _QueueOpener(responses)
    pace_events: list[str] = []
    transport = StrictTossForwardTransport(
        opener=opener,
        allowed_symbols=("TSLA", "000660"),
        request_pacer=lambda: pace_events.append("paced"),
    )
    collector = TossForwardMicrostructureCollector(
        transport=transport,
        token_supplier=lambda: "ephemeral-token",
        clock=lambda: datetime(2026, 7, 11, 1, 0, 1, tzinfo=timezone.utc),
    )
    return collector, opener, pace_events


class StrictTossForwardBoundaryTest(unittest.TestCase):
    def test_allowed_symbols_must_be_a_unique_frozen_symbol_sequence(self) -> None:
        for allowed_symbols in (
            (),
            "TSLA",
            (None,),
            (["TSLA"],),
            ("bad\nsymbol",),
            ("TSLA", "TSLA"),
        ):
            with self.subTest(allowed_symbols=allowed_symbols):
                with self.assertRaisesRegex(
                    ReadOnlyBoundaryError,
                    "allowed_scope_invalid",
                ):
                    StrictTossForwardTransport(
                        opener=_QueueOpener(()),
                        allowed_symbols=allowed_symbols,
                        request_pacer=lambda: None,
                    )

    def test_allows_only_exact_trade_and_orderbook_reads_with_one_global_pacer(self) -> None:
        opener = _QueueOpener(
            (
                _Response(b'{"result":[]}'),
                _Response(
                    b'{"result":{"timestamp":null,"currency":"USD",'
                    b'"asks":[],"bids":[]}}'
                ),
            )
        )
        pace_events: list[str] = []
        transport = StrictTossForwardTransport(
            opener=opener,
            allowed_symbols=("TSLA",),
            request_pacer=lambda: pace_events.append("paced"),
        )

        transport(_request(_TRADE_URL))
        transport(_request(_BOOK_URL))

        self.assertEqual(pace_events, ["paced", "paced"])
        self.assertEqual(
            [getattr(request, "full_url") for request in opener.requests],
            [_TRADE_URL, _BOOK_URL],
        )
        self.assertTrue(MINIMUM_FORWARD_REQUEST_INTERVAL_SECONDS >= 1.0)

    def test_rejects_operational_endpoint_origin_query_symbol_and_header_variants(self) -> None:
        opener = _QueueOpener(())
        transport = StrictTossForwardTransport(
            opener=opener,
            allowed_symbols=("TSLA",),
            request_pacer=lambda: None,
        )
        forbidden_urls = (
            _TRADE_URL.replace("/trades", "/orders"),
            _TRADE_URL.replace("/trades", "/accounts"),
            _TRADE_URL.replace("/trades", "/assets"),
            _TRADE_URL.replace("https://", "http://"),
            _TRADE_URL.replace("openapi.tossinvest.com", "evil.example"),
            _TRADE_URL.replace(
                "openapi.tossinvest.com",
                "openapi.tossinvest.com:443",
            ),
            _TRADE_URL.replace("/trades", "/%2e%2e/orders"),
            _TRADE_URL.replace("count=50", "count=49"),
            _TRADE_URL.replace("symbol=TSLA", "symbol=AAPL"),
            _TRADE_URL + "&extra=1",
            _BOOK_URL + "&count=50",
        )
        for url in forbidden_urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(_request(url))
        invalid_requests = (
            HttpRequest(method="POST", url=_TRADE_URL, headers=_request(_TRADE_URL).headers),
            HttpRequest(
                method="GET",
                url=_TRADE_URL,
                headers={
                    "Accept": "application/json",
                    "Authorization": "Bearer first",
                    "authorization": "Bearer second",
                },
            ),
            HttpRequest(
                method="GET",
                url=_TRADE_URL,
                headers={"Accept": "text/plain", "Authorization": "Bearer token"},
            ),
        )
        for request in invalid_requests:
            with self.subTest(request=repr(request)):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(request)
        self.assertEqual(opener.requests, [])

    def test_live_factory_rejects_redirects(self) -> None:
        transport = build_live_toss_forward_transport(
            allowed_symbols=("TSLA",),
        )

        self.assertTrue(
            any(
                isinstance(handler, _RejectRedirectHandler)
                for handler in transport._opener.handlers
            )
        )


class TossSampledTradeStreamTest(unittest.TestCase):
    def test_preserves_decimal_strings_raw_capture_lineage_and_claim_limits(self) -> None:
        raw_body = _body({"result": [_trade()]})
        collector, opener, pace_events = _collector((_Response(raw_body),))

        stream = collector.collect_trade_polls(symbol="TSLA", poll_count=1)

        self.assertEqual(stream.measurement_kind, "sampled_trade_stream")
        self.assertEqual(stream.completeness, "not_complete_exchange_tape")
        self.assertEqual(stream.aggressor_side_status, "not_identifiable")
        self.assertEqual(stream.order_id_status, "not_available")
        self.assertEqual(stream.ofi_status, "not_identifiable")
        self.assertEqual(len(stream.observations), 1)
        observation = stream.observations[0]
        self.assertEqual(observation.price.text, "250.100")
        self.assertEqual(observation.volume.text, "10.500")
        self.assertEqual(observation.source_capture_ordinal, 0)
        self.assertEqual(observation.source_row_index, 0)
        self.assertEqual(observation.duplicate_status, "unique_poll_observation")
        capture = stream.captures[0]
        self.assertEqual(base64.b64decode(capture.body_base64), raw_body)
        self.assertEqual(capture.body_sha256, hashlib.sha256(raw_body).hexdigest())
        self.assertEqual(capture.received_at, "2026-07-11T01:00:01Z")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(pace_events, ["paced"])

    def test_repeated_cross_poll_trade_is_not_deduplicated_and_stays_ambiguous(self) -> None:
        first = _trade_response([_trade()])
        second = _trade_response([_trade()])
        collector, _, _ = _collector((first, second))

        stream = collector.collect_trade_polls(symbol="TSLA", poll_count=2)

        self.assertEqual(len(stream.observations), 2)
        self.assertEqual(
            {item.duplicate_status for item in stream.observations},
            {"ambiguous_cross_poll_duplicate"},
        )
        expected_occurrences = tuple(
            item.source_occurrence for item in stream.observations
        )
        self.assertEqual(
            stream.observations[0].ambiguous_occurrences,
            expected_occurrences,
        )
        self.assertEqual(
            stream.observations[1].ambiguous_occurrences,
            expected_occurrences,
        )
        self.assertNotEqual(
            stream.observations[0].source_occurrence,
            stream.observations[1].source_occurrence,
        )

    def test_trade_response_shape_limit_values_and_timestamp_fail_closed(self) -> None:
        valid = _trade()
        invalid_values = (
            {"trades": [valid]},
            {"result": [{key: value for key, value in valid.items() if key != "price"}]},
            {"result": [{**valid, "extra": "x"}]},
            {"result": [valid] * 51},
            {"result": [_trade(price="0")]},
            {"result": [_trade(volume="-1")]},
            {"result": [_trade(timestamp="not-a-time")]},
            {"result": [_trade(timestamp="2026-07-11T01:00:02Z")]},
        )
        for value in invalid_values:
            with self.subTest(keys=tuple(value)):
                collector, _, _ = _collector((_Response(_body(value)),))
                with self.assertRaises(ForwardMicrostructureError):
                    collector.collect_trade_polls(symbol="TSLA", poll_count=1)


class TossSampledOrderbookTest(unittest.TestCase):
    def test_preserves_ordered_decimal_levels_nullable_timestamp_and_claim_limits(self) -> None:
        collector, _, _ = _collector((_book_response(timestamp=None),))

        snapshot = collector.poll_orderbook(symbol="TSLA", capture_ordinal=7)

        self.assertEqual(snapshot.measurement_kind, "sampled_orderbook_snapshot")
        self.assertEqual(snapshot.completeness, "not_complete_exchange_tape")
        self.assertEqual(snapshot.order_id_status, "not_available")
        self.assertEqual(snapshot.ofi_status, "not_identifiable")
        self.assertIsNone(snapshot.source_timestamp)
        self.assertIsNone(snapshot.normalized_event_at)
        self.assertEqual(snapshot.received_at, "2026-07-11T01:00:01Z")
        self.assertEqual(snapshot.source_capture_ordinal, 7)
        self.assertEqual(snapshot.source_row_index, 0)
        self.assertEqual(snapshot.source_body_sha256, snapshot.capture.body_sha256)
        self.assertEqual(
            [level.price.text for level in snapshot.asks],
            ["250.20", "250.30"],
        )
        self.assertEqual(
            [level.price.text for level in snapshot.bids],
            ["250.10", "250.00"],
        )
        self.assertEqual(snapshot.asks[0].source_capture_ordinal, 7)
        self.assertEqual(snapshot.asks[0].source_row_index, 0)
        self.assertEqual(snapshot.bids[0].source_row_index, 2)

    def test_book_schema_decimal_timestamp_and_side_order_fail_closed(self) -> None:
        invalid_results = (
            {"currency": "USD", "asks": [], "bids": []},
            {
                "timestamp": None,
                "currency": "USD",
                "asks": [{"price": "250", "volume": "1", "extra": "x"}],
                "bids": [],
            },
            {
                "timestamp": None,
                "currency": "USD",
                "asks": [
                    {"price": "250.30", "volume": "1"},
                    {"price": "250.20", "volume": "1"},
                ],
                "bids": [],
            },
            {
                "timestamp": None,
                "currency": "USD",
                "asks": [],
                "bids": [
                    {"price": "250.00", "volume": "1"},
                    {"price": "250.10", "volume": "1"},
                ],
            },
            {
                "timestamp": None,
                "currency": "USD",
                "asks": [{"price": "0", "volume": "1"}],
                "bids": [],
            },
            {
                "timestamp": "future",
                "currency": "USD",
                "asks": [],
                "bids": [],
            },
        )
        for result in invalid_results:
            with self.subTest(result=result):
                collector, _, _ = _collector(
                    (_Response(_body({"result": result})),)
                )
                with self.assertRaises(ForwardMicrostructureError):
                    collector.poll_orderbook(symbol="TSLA")

    def test_http_failure_preserves_raw_capture(self) -> None:
        collector, _, _ = _collector(
            (_Response(b'{"error":"rate_limited"}', status=429),)
        )

        with self.assertRaises(ForwardMicrostructureError) as raised:
            collector.poll_orderbook(symbol="TSLA")

        self.assertEqual(raised.exception.code, "HTTP_STATUS")
        self.assertEqual(len(raised.exception.captures), 1)


if __name__ == "__main__":
    unittest.main()
