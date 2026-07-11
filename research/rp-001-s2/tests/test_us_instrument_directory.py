from __future__ import annotations

import hashlib
import io
import unittest
from datetime import datetime, timezone

from rp001.toss_research_collector import HttpRequest
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, _RejectRedirectHandler
from rp001_s2.us_instrument_directory import (
    InstrumentEligibility,
    StrictNasdaqDirectoryTransport,
    build_live_nasdaq_directory_transport,
    collect_us_instrument_directory,
    parse_us_instrument_directory,
)


_NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\r\n"
    "AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N\r\n"
    "QQQ|Invesco QQQ Trust, Series 1 ETF|G|N|N|100|Y|N\r\n"
    "TEST|Test Common Stock|S|Y|N|100|N|N\r\n"
    "WARRW|Example Corp. - Warrant|S|N|N|100|N|N\r\n"
    "File Creation Time: 0711202621:00|||||||\r\n"
).encode("utf-8")

_OTHER = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\r\n"
    "TSLA|Tesla, Inc. - Common Stock|N|TSLA|N|100|N|TSLA\r\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\r\n"
    "PREFP|Example Corp. Preferred Stock|N|PREFP|N|100|N|PREFP\r\n"
    "File Creation Time: 0711202621:00|||||||\r\n"
).encode("utf-8")


class _Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = {"Content-Type": "text/plain; charset=utf-8"}
        self._body = io.BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class _Opener:
    def __init__(self, responses: tuple[_Response, ...] = ()) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else _Response(b"")


class UsInstrumentDirectoryTest(unittest.TestCase):
    def test_preserves_all_rows_and_builds_direction_agnostic_eligible_universe(self) -> None:
        directory = parse_us_instrument_directory(_NASDAQ, _OTHER)

        self.assertEqual(len(directory.records), 7)
        self.assertEqual(
            directory.eligible_symbols,
            ("AAPL", "QQQ", "SPY", "TSLA"),
        )
        by_symbol = {record.symbol: record for record in directory.records}
        self.assertEqual(
            by_symbol["AAPL"].eligibility,
            InstrumentEligibility.COMMON_STOCK,
        )
        self.assertEqual(by_symbol["QQQ"].eligibility, InstrumentEligibility.ETF)
        self.assertEqual(
            by_symbol["TEST"].eligibility,
            InstrumentEligibility.EXCLUDED_TEST_ISSUE,
        )
        self.assertEqual(
            by_symbol["WARRW"].eligibility,
            InstrumentEligibility.EXCLUDED_NON_COMMON,
        )
        self.assertEqual(
            by_symbol["PREFP"].eligibility,
            InstrumentEligibility.EXCLUDED_NON_COMMON,
        )
        self.assertEqual(directory.etf_asset_class_status, "not_identifiable_from_directory")
        self.assertEqual(directory.nasdaq_file_created_at, "0711202621:00")
        self.assertEqual(directory.other_file_created_at, "0711202621:00")

    def test_header_footer_duplicate_and_malformed_utf8_fail_closed(self) -> None:
        invalid_pairs = (
            (_NASDAQ.replace(b"Symbol|", b"Ticker|", 1), _OTHER),
            (_NASDAQ.replace(b"File Creation Time:", b"Created:"), _OTHER),
            (_NASDAQ, _OTHER.replace(b"TSLA|", b"AAPL|", 1)),
            (_NASDAQ + b"\xff", _OTHER),
        )

        for nasdaq, other in invalid_pairs:
            with self.subTest(nasdaq_sha=hashlib.sha256(nasdaq).hexdigest()):
                with self.assertRaisesRegex(ValueError, "instrument_directory_invalid"):
                    parse_us_instrument_directory(nasdaq, other)

    def test_live_collection_preserves_exact_raw_body_hash_and_received_time(self) -> None:
        opener = _Opener((_Response(_NASDAQ), _Response(_OTHER)))
        transport = StrictNasdaqDirectoryTransport(opener=opener)

        collected = collect_us_instrument_directory(
            transport=transport,
            clock=lambda: datetime(2026, 7, 11, 7, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(collected.captures), 2)
        self.assertEqual(collected.captures[0].body_sha256, hashlib.sha256(_NASDAQ).hexdigest())
        self.assertEqual(collected.captures[1].body_sha256, hashlib.sha256(_OTHER).hexdigest())
        self.assertEqual(collected.captures[0].received_at, "2026-07-11T07:00:00Z")
        self.assertEqual(collected.directory.eligible_symbols, ("AAPL", "QQQ", "SPY", "TSLA"))

    def test_transport_rejects_non_directory_hosts_paths_methods_and_headers(self) -> None:
        opener = _Opener()
        transport = StrictNasdaqDirectoryTransport(opener=opener)
        valid = (
            "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
            "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
        )

        for url in valid:
            self.assertEqual(
                transport(HttpRequest("GET", url, {"Accept": "text/plain"})).status,
                200,
            )
        forbidden = (
            valid[0].replace("https://", "http://"),
            valid[0].replace("www.nasdaqtrader.com", "evil.example"),
            valid[0].replace("www.nasdaqtrader.com", "www.nasdaqtrader.com:443"),
            valid[0].replace("nasdaqlisted.txt", "%2e%2e/orders"),
            valid[0] + "?extra=1",
            "https://www.nasdaqtrader.com/api/v1/orders",
        )
        for url in forbidden:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
                    transport(HttpRequest("GET", url, {"Accept": "text/plain"}))
        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            transport(HttpRequest("POST", valid[0], {"Accept": "text/plain"}))
        with self.assertRaisesRegex(ReadOnlyBoundaryError, "endpoint_not_allowed"):
            transport(HttpRequest("GET", valid[0], {"Accept": "application/json"}))

    def test_live_factory_rejects_redirects(self) -> None:
        transport = build_live_nasdaq_directory_transport()

        self.assertTrue(
            any(
                isinstance(handler, _RejectRedirectHandler)
                for handler in transport._opener.handlers
            )
        )


if __name__ == "__main__":
    unittest.main()
