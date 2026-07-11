from __future__ import annotations

import io
import unittest
from datetime import datetime, timezone
from typing import cast

from rp001.toss_research_collector import HttpRequest
from rp001_s2.alpaca_boundary import (
    AlpacaCredentialCapability,
    StrictAlpacaBarsTransport,
    build_live_strict_alpaca_transport,
)
from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, _RejectRedirectHandler


_KEY_ID = "test-key-id"
_SECRET_KEY = "test-secret-key"
_EXPECTED_URL = (
    "https://data.alpaca.markets/v2/stocks/TSLA/bars?"
    "timeframe=1Min&start=2026-06-01T13%3A30%3A00Z&"
    "end=2026-07-01T19%3A59%3A00Z&limit=10000&adjustment=raw&"
    "asof=-&feed=sip&currency=USD&sort=asc"
)


class _Response:
    def __init__(
        self,
        body: bytes = b'{"bars":[],"symbol":"TSLA","next_page_token":null}',
    ) -> None:
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class _Opener:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        return _Response()


def _scope(**overrides: object) -> CollectionScope:
    values: dict[str, object] = {
        "provider": "alpaca",
        "feed": "sip",
        "instrument_id": "TSLA",
        "symbol": "TSLA",
        "interval": "1m",
        "start_at": datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
        "end_at": datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc),
        "adjustment_mode": "raw",
        "session_scope": "provider_all",
        "sample_role": SampleRole.SEEN,
    }
    values.update(overrides)
    return CollectionScope(**values)


def _capability() -> AlpacaCredentialCapability:
    return AlpacaCredentialCapability.consume(
        {
            "APCA_API_KEY_ID": _KEY_ID,
            "APCA_API_SECRET_KEY": _SECRET_KEY,
        }
    )


def _request(url: str = _EXPECTED_URL, **header_overrides: str) -> HttpRequest:
    headers = {
        "Accept": "application/json",
        "APCA-API-KEY-ID": _KEY_ID,
        "APCA-API-SECRET-KEY": _SECRET_KEY,
    }
    headers.update(header_overrides)
    return HttpRequest(method="GET", url=url, headers=headers)


class AlpacaCredentialCapabilityTest(unittest.TestCase):
    def test_factory_consumes_both_environment_values_and_redacts_repr(self) -> None:
        environment = {
            "APCA_API_KEY_ID": _KEY_ID,
            "APCA_API_SECRET_KEY": _SECRET_KEY,
            "UNRELATED": "preserved",
        }

        capability = AlpacaCredentialCapability.consume(environment)

        self.assertEqual(environment, {"UNRELATED": "preserved"})
        self.assertNotIn(_KEY_ID, repr(capability))
        self.assertNotIn(_SECRET_KEY, repr(capability))
        self.assertEqual(repr(capability), "AlpacaCredentialCapability(<redacted>)")

    def test_factory_rejects_invalid_credentials_after_consuming_both(self) -> None:
        for environment in (
            {},
            {"APCA_API_KEY_ID": _KEY_ID},
            {"APCA_API_SECRET_KEY": _SECRET_KEY},
            {
                "APCA_API_KEY_ID": _KEY_ID,
                "APCA_API_SECRET_KEY": "bad\nsecret",
            },
        ):
            with self.subTest(environment_keys=tuple(environment)):
                with self.assertRaisesRegex(
                    ReadOnlyBoundaryError,
                    "credential_environment_invalid",
                ):
                    AlpacaCredentialCapability.consume(environment)
                self.assertNotIn("APCA_API_KEY_ID", environment)
                self.assertNotIn("APCA_API_SECRET_KEY", environment)


class StrictAlpacaBarsTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.opener = _Opener()
        self.transport = StrictAlpacaBarsTransport(
            opener=self.opener,
            scope=_scope(),
            credentials=_capability(),
        )

    def test_builds_exact_single_symbol_half_open_minute_request(self) -> None:
        response = self.transport.request_page()

        self.assertEqual(response.status, 200)
        self.assertEqual(len(self.opener.requests), 1)
        outgoing = self.opener.requests[0]
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
        self.assertNotIn(_KEY_ID, repr(outgoing))
        self.assertNotIn(_SECRET_KEY, repr(outgoing))

    def test_places_opaque_page_token_last_with_canonical_encoding(self) -> None:
        self.transport.request_page("next/token+=")

        outgoing = self.opener.requests[0]
        self.assertEqual(
            getattr(outgoing, "full_url"),
            _EXPECTED_URL + "&page_token=next%2Ftoken%2B%3D",
        )

    def test_rejects_scope_outside_frozen_alpaca_minute_contract_before_open(self) -> None:
        forbidden_scopes = (
            _scope(provider="toss"),
            _scope(feed="otc"),
            _scope(symbol="000660", instrument_id="000660"),
            _scope(symbol="tsla", instrument_id="tsla"),
            _scope(symbol="../TSLA", instrument_id="../TSLA"),
            _scope(interval="1d"),
            _scope(adjustment_mode="all"),
            _scope(session_scope="regular"),
            _scope(start_at=datetime(2026, 6, 1, 13, 30, 1, tzinfo=timezone.utc)),
            _scope(end_at=datetime(2026, 6, 1, 13, 30, 30, tzinfo=timezone.utc)),
        )

        for scope in forbidden_scopes:
            with self.subTest(scope=scope.to_canonical_body()):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "allowed_scope_invalid"):
                    StrictAlpacaBarsTransport(
                        opener=self.opener,
                        scope=scope,
                        credentials=_capability(),
                    )
        self.assertEqual(self.opener.requests, [])

    def test_rejects_order_account_asset_and_all_url_variants_before_open(self) -> None:
        forbidden_urls = (
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/orders"),
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/account"),
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/assets"),
            _EXPECTED_URL.replace("https://", "http://"),
            _EXPECTED_URL.replace("data.alpaca.markets", "evil.example"),
            _EXPECTED_URL.replace("data.alpaca.markets", "data.alpaca.markets:443"),
            _EXPECTED_URL.replace("/v2/stocks/TSLA/bars", "/v2/stocks/%2e%2e/orders"),
            _EXPECTED_URL.replace("timeframe=1Min", "extra=1&timeframe=1Min"),
            _EXPECTED_URL.replace("limit=10000", "limit=9999"),
            _EXPECTED_URL.replace("feed=sip", "feed=iex"),
            _EXPECTED_URL.replace("sort=asc", "sort=desc"),
            _EXPECTED_URL + "#fragment",
        )

        for url in forbidden_urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    self.transport(_request(url))
        self.assertEqual(self.opener.requests, [])

    def test_rejects_noncanonical_query_order_and_wrong_credentials(self) -> None:
        reordered = _EXPECTED_URL.replace(
            "currency=USD&sort=asc",
            "sort=asc&currency=USD",
        )
        requests = (
            _request(reordered),
            HttpRequest(
                method="POST",
                url=_EXPECTED_URL,
                headers=_request().headers,
            ),
            HttpRequest(
                method="GET",
                url=_EXPECTED_URL,
                headers={
                    **_request().headers,
                    "accept": "application/json",
                },
            ),
            _request(**{"APCA-API-KEY-ID": "wrong"}),
            _request(**{"APCA-API-SECRET-KEY": "wrong"}),
            _request(Accept="text/plain"),
        )

        for request in requests:
            with self.subTest(request=repr(request)):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    self.transport(request)
        self.assertEqual(self.opener.requests, [])

    def test_malformed_header_mapping_fails_closed_before_open(self) -> None:
        malformed_headers = cast(
            dict[str, str],
            {1: "application/json"},
        )

        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            self.transport(
                HttpRequest(
                    method="GET",
                    url=_EXPECTED_URL,
                    headers=malformed_headers,
                )
            )

        self.assertEqual(self.opener.requests, [])

    def test_empty_or_control_character_page_token_is_rejected_before_open(self) -> None:
        for page_token in ("", "bad\nvalue", "bad\x00value"):
            with self.subTest(page_token=repr(page_token)):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "page_token_invalid"):
                    self.transport.request_page(page_token)
        self.assertEqual(self.opener.requests, [])

    def test_network_failure_is_sanitized_without_request_or_credentials(self) -> None:
        class _FailingOpener:
            def open(self, request: object, timeout: float) -> object:
                del request, timeout
                raise OSError(_SECRET_KEY)

        transport = StrictAlpacaBarsTransport(
            opener=_FailingOpener(),
            scope=_scope(),
            credentials=_capability(),
        )

        with self.assertRaises(ReadOnlyBoundaryError) as raised:
            transport.request_page()

        rendered = repr(raised.exception) + str(raised.exception)
        self.assertEqual(raised.exception.code, "alpaca_transport_error")
        self.assertNotIn(_KEY_ID, rendered)
        self.assertNotIn(_SECRET_KEY, rendered)

    def test_live_factory_installs_redirect_rejection(self) -> None:
        transport = build_live_strict_alpaca_transport(
            scope=_scope(),
            credentials=_capability(),
        )

        self.assertTrue(
            any(
                isinstance(handler, _RejectRedirectHandler)
                for handler in transport._opener.handlers
            )
        )


if __name__ == "__main__":
    unittest.main()
