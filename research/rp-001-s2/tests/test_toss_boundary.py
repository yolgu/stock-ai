from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from rp001.toss_research_collector import HttpRequest, HttpResponse
from rp001_s2.sample_design import CANDIDATE_POOL
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    StrictCandleTransport,
    StrictMetadataTransport,
    load_credentials,
    run_metadata_request,
)


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.headers = {"Content-Type": "application/json"}
        self._stream = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


class _Opener:
    def __init__(self, responses: tuple[_Response, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        return self.responses.pop(0)


def _metadata_body() -> bytes:
    records = [
        {
            "symbol": symbol,
            "name": symbol,
            "englishName": symbol,
            "isinCode": f"US{symbol:0<10}"[:12],
            "market": "NYSE",
            "securityType": "STOCK",
            "isCommonShare": True,
            "status": "ACTIVE",
            "currency": "USD",
            "sharesOutstanding": "1000000",
        }
        for symbol in CANDIDATE_POOL
    ]
    return json.dumps({"result": records}, separators=(",", ":")).encode()


class TossCredentialBoundaryTest(unittest.TestCase):
    def test_credentials_require_one_shot_environment_values(self) -> None:
        with self.assertRaisesRegex(ReadOnlyBoundaryError, "credential_environment_invalid"):
            load_credentials({})

    def test_credentials_are_consumed_without_repr_exposure(self) -> None:
        environment = {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "credential",
        }

        credentials = load_credentials(environment)

        self.assertNotIn("identifier", repr(credentials))
        self.assertNotIn("credential", repr(credentials))
        self.assertNotIn("TOSS_CLIENT_ID", environment)
        self.assertNotIn("TOSS_CLIENT_SECRET", environment)


class TossMetadataBoundaryTest(unittest.TestCase):
    def test_transport_rejects_every_non_metadata_endpoint(self) -> None:
        transport = StrictMetadataTransport(
            opener=_Opener(()),
            allowed_symbols=CANDIDATE_POOL,
        )
        request = HttpRequest(
            method="GET",
            url="https://openapi.tossinvest.com/api/v1/orders?symbols=BA",
            headers={"Accept": "application/json", "Authorization": "Bearer token"},
        )

        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            transport(request)

    def test_metadata_run_uses_only_oauth_then_exact_stock_get(self) -> None:
        opener = _Opener(
            (
                _Response(200, b'{"access_token":"ephemeral-token"}'),
                _Response(200, _metadata_body()),
            )
        )
        environment = {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "credential",
        }

        collection = run_metadata_request(
            symbols=CANDIDATE_POOL,
            opener=opener,
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
            environment=environment,
        )

        self.assertEqual(len(collection.records), len(CANDIDATE_POOL))
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(getattr(opener.requests[0], "method"), "POST")
        self.assertEqual(getattr(opener.requests[0], "full_url"), "https://openapi.tossinvest.com/oauth2/token")
        self.assertEqual(getattr(opener.requests[1], "method"), "GET")
        self.assertTrue(
            getattr(opener.requests[1], "full_url").startswith(
                "https://openapi.tossinvest.com/api/v1/stocks?symbols="
            )
        )
        self.assertNotIn("ephemeral-token", repr(opener.requests[1]))

    def test_oauth_rate_limit_preserves_sanitized_failure_lineage(self) -> None:
        opener = _Opener((_Response(429, b'{"error":"rate_limited"}'),))

        with self.assertRaises(ReadOnlyBoundaryError) as raised:
            run_metadata_request(
                symbols=CANDIDATE_POOL,
                opener=opener,
                clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                environment={
                    "TOSS_CLIENT_ID": "identifier",
                    "TOSS_CLIENT_SECRET": "credential",
                },
            )

        self.assertEqual(raised.exception.code, "authentication_http_status")
        self.assertEqual(len(raised.exception.captures), 1)
        capture = raised.exception.captures[0]
        self.assertEqual(capture.method, "POST")
        self.assertEqual(capture.status, 429)
        self.assertEqual(capture.received_at, "2026-07-11T00:00:00Z")
        self.assertEqual(capture.body_base64, "")
        self.assertEqual(len(capture.body_sha256), 64)

    def test_transport_rejects_endpoint_variants(self) -> None:
        transport = StrictMetadataTransport(
            opener=_Opener(()),
            allowed_symbols=CANDIDATE_POOL,
        )
        urls = (
            "https://openapi.tossinvest.com/api/v1/accounts?symbols=BA",
            "https://openapi.tossinvest.com/api/v1/assets?symbols=BA",
            "https://openapi.tossinvest.com/api/v1/candles?symbols=BA",
            "https://evil.example/api/v1/stocks?symbols=BA",
            "http://openapi.tossinvest.com/api/v1/stocks?symbols=BA",
            "https://openapi.tossinvest.com/api/v1/stocks?symbols=BA&extra=1",
        )
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(
                        HttpRequest(
                            method="GET",
                            url=url,
                            headers={
                                "Accept": "application/json",
                                "Authorization": "Bearer token",
                            },
                        )
                    )


class TossCandleBoundaryTest(unittest.TestCase):
    def test_candle_transport_allows_only_frozen_development_symbols(self) -> None:
        opener = _Opener((_Response(200, b"{}"),))
        transport = StrictCandleTransport(
            opener=opener,
            allowed_symbols=("BA", "MRK"),
            request_pacer=lambda: None,
        )
        allowed = HttpRequest(
            method="GET",
            url=(
                "https://openapi.tossinvest.com/api/v1/candles?"
                "symbol=BA&interval=1d&count=200&adjusted=true&"
                "before=2026-07-01T00%3A00%3A00Z"
            ),
            headers={"Accept": "application/json", "Authorization": "Bearer token"},
        )

        response = transport(allowed)

        self.assertEqual(response.status, 200)
        for forbidden_url in (
            allowed.url.replace("symbol=BA", "symbol=LOW"),
            allowed.url.replace("/api/v1/candles", "/api/v1/orders"),
            allowed.url.replace("adjusted=true", "adjusted=maybe"),
        ):
            with self.subTest(url=forbidden_url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(
                        HttpRequest(
                            method="GET",
                            url=forbidden_url,
                            headers={
                                "Accept": "application/json",
                                "Authorization": "Bearer token",
                            },
                        )
                    )


if __name__ == "__main__":
    unittest.main()
