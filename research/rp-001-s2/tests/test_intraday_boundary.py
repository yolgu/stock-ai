from __future__ import annotations

import io
import unittest
from rp001.toss_research_collector import HttpRequest
from rp001_s2.intraday_boundary import (
    StrictMinuteCandleTransport,
    build_live_strict_minute_transport,
)
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, _RejectRedirectHandler


class _Response:
    def __init__(self) -> None:
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self._body = io.BytesIO(b"{}")

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


def _request(url: str) -> HttpRequest:
    return HttpRequest(
        method="GET",
        url=url,
        headers={"Accept": "application/json", "Authorization": "Bearer ephemeral"},
    )


class StrictIntradayBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.opener = _Opener()
        self.transport = StrictMinuteCandleTransport(
            opener=self.opener,
            allowed_symbols=("BA", "PEP"),
            earliest_before="2026-07-10T08:00:00+09:00",
            initial_before="2026-07-11T08:00:00+09:00",
            request_pacer=lambda: None,
        )

    def test_allows_only_frozen_minute_candle_reads(self) -> None:
        candle = _request(
            "https://openapi.tossinvest.com/api/v1/candles?"
            "symbol=BA&interval=1m&count=200&adjusted=false&"
            "before=2026-07-11T08%3A00%3A00%2B09%3A00"
        )

        self.assertEqual(self.transport(candle).status, 200)
        self.assertEqual(len(self.opener.requests), 1)

    def test_rejects_operational_endpoints_and_scope_variants(self) -> None:
        allowed = (
            "https://openapi.tossinvest.com/api/v1/candles?"
            "symbol=BA&interval=1m&count=200&adjusted=false&"
            "before=2026-07-11T08%3A00%3A00%2B09%3A00"
        )
        forbidden = (
            "https://openapi.tossinvest.com/api/v1/orders?symbol=BA",
            "https://openapi.tossinvest.com/api/v1/accounts",
            "https://openapi.tossinvest.com/api/v1/assets",
            "https://openapi.tossinvest.com/api/v1/market-calendar/US?date=2026-07-10",
            allowed.replace("symbol=BA", "symbol=LOW"),
            allowed.replace("interval=1m", "interval=5m"),
            allowed.replace("count=200", "count=100"),
            allowed.replace("before=2026", "extra=1&before=2026"),
            allowed.replace("2026-07-11T08", "2026-07-11T09"),
            "https://openapi.tossinvest.com/api/v1/market-calendar/US?date=2026-07-11",
        )

        for url in forbidden:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    self.transport(_request(url))

    def test_daily_reference_is_outside_this_task_boundary(self) -> None:
        daily = _request(
            "https://openapi.tossinvest.com/api/v1/candles?"
            "symbol=PEP&interval=1d&count=200&adjusted=true&"
            "before=2026-07-11T08%3A00%3A00%2B09%3A00"
        )

        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            self.transport(daily)

    def test_case_insensitive_duplicate_authorization_headers_are_rejected(self) -> None:
        request = HttpRequest(
            method="GET",
            url=(
                "https://openapi.tossinvest.com/api/v1/candles?"
                "symbol=BA&interval=1m&count=200&adjusted=false&"
                "before=2026-07-11T08%3A00%3A00%2B09%3A00"
            ),
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer first",
                "authorization": "Bearer second",
            },
        )

        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            self.transport(request)
        self.assertEqual(self.opener.requests, [])

    def test_live_factory_installs_redirect_rejection(self) -> None:
        transport = build_live_strict_minute_transport(
            allowed_symbols=("BA", "PEP"),
            earliest_before="2026-07-10T08:00:00+09:00",
            initial_before="2026-07-11T08:00:00+09:00",
            request_pacer=lambda: None,
        )

        self.assertTrue(
            any(
                isinstance(handler, _RejectRedirectHandler)
                for handler in transport._opener.handlers
            )
        )


if __name__ == "__main__":
    unittest.main()
