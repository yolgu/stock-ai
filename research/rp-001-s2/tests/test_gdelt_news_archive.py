from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rp001.local_evidence import canonical_json_bytes, sha256_bytes
from rp001_s2.archive_contract import BENCHMARK_SYMBOLS, PRIORITY_SYMBOLS
from rp001_s2.gdelt_news_archive import (
    GdeltArchiveStorage,
    GdeltHttpResponse,
    GdeltNewsScope,
    GdeltQueryEntry,
    GlobalGdeltWorker,
    build_gdelt_query_map,
    build_gdelt_ticker_proxy_map,
)


_UTC = timezone.utc


def _scope_plan_source() -> bytes:
    symbols = tuple(sorted((*PRIORITY_SYMBOLS, *BENCHMARK_SYMBOLS)))
    return canonical_json_bytes(
        {
            "schemaVersion": "test-scope-plan.v1",
            "instruments": [
                {"instrumentId": symbol, "symbol": symbol} for symbol in symbols
            ],
        }
    )


def _directory_source() -> bytes:
    records = [
        {
            "symbol": symbol,
            "securityName": f"Official {symbol} Security Name",
        }
        for symbol in sorted((*PRIORITY_SYMBOLS, *BENCHMARK_SYMBOLS))
        if symbol != "000660"
    ]
    return canonical_json_bytes(
        {"schemaVersion": "test-directory.v1", "records": records}
    )


class _ControlledTime:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.elapsed += seconds

    def utc_now(self) -> datetime:
        return datetime(2026, 7, 11, tzinfo=_UTC) + timedelta(
            seconds=self.elapsed
        )


class _SequenceTransport:
    def __init__(self, responses: tuple[GdeltHttpResponse, ...]) -> None:
        self._responses = list(responses)
        self.started_at: list[float] = []
        self.requests: list[object] = []
        self._time: _ControlledTime | None = None

    def bind_time(self, controlled: _ControlledTime) -> None:
        self._time = controlled

    def __call__(self, request: object) -> GdeltHttpResponse:
        if self._time is None:
            raise AssertionError("time_not_bound")
        self.started_at.append(self._time.monotonic())
        self.requests.append(request)
        return self._responses.pop(0)


class GdeltQueryMapTest(unittest.TestCase):
    def test_freezes_exact_company_name_queries_for_all_frozen_symbols(self) -> None:
        scope_source = _scope_plan_source()
        directory_source = _directory_source()

        query_map = build_gdelt_query_map(
            scope_plan_source=scope_source,
            directory_master_source=directory_source,
            frozen_at="2026-07-11T16:10:00Z",
        )

        self.assertEqual(len(query_map.entries), 48)
        by_symbol = {entry.symbol: entry for entry in query_map.entries}
        self.assertEqual(by_symbol["TSLA"].query, '"Tesla Inc"')
        self.assertEqual(by_symbol["NVDA"].query, '"NVIDIA Corporation"')
        self.assertEqual(by_symbol["AAPL"].query, '"Apple Inc"')
        self.assertEqual(by_symbol["CAT"].query, '"Caterpillar Inc"')
        self.assertEqual(by_symbol["GE"].query, '"GE Aerospace"')
        self.assertEqual(by_symbol["000660"].query, '"SK hynix"')
        self.assertEqual(
            query_map.scope_plan_sha256,
            sha256_bytes(scope_source),
        )
        self.assertEqual(
            query_map.directory_master_sha256,
            sha256_bytes(directory_source),
        )
        canonical = query_map.to_canonical_body()
        self.assertEqual(
            canonical["scopePlan"],
            {
                "path": "scope-plans-v2/toss-minute-scope-plan-9c1841e5c72c6e28d08fc73c24b6dfc1d8e95fcf3d457d40bfe0dd32b36b7ec3.json",
                "sha256": sha256_bytes(scope_source),
            },
        )
        self.assertEqual(
            canonical["queryContract"]["http429BackoffSeconds"],
            [30, 60, 120],
        )
        self.assertEqual(canonical["queryContract"]["maxAttempts"], 4)
        for entry in query_map.entries:
            self.assertTrue(entry.query.startswith('"'))
            self.assertTrue(entry.query.endswith('"'))
            self.assertNotEqual(entry.query, f'"{entry.symbol}"')

    def test_ticker_proxy_is_physically_separate_and_forbids_other_symbols(self) -> None:
        proxy_map = build_gdelt_ticker_proxy_map(
            company_query_map_sha256="a" * 64,
            frozen_at="2026-07-11T16:15:00Z",
        )

        body = proxy_map.to_canonical_body()
        self.assertEqual(body["queryKind"], "ticker_query_proxy")
        self.assertEqual(body["evidenceStatus"], "proxy_only")
        self.assertEqual(body["mixingWithCompanyMeasure"], "forbidden")
        self.assertEqual(body["eligibleSymbols"], ["TSLA", "NVDA", "AAPL"])
        self.assertEqual(
            [entry["gdeltQuery"] for entry in body["entries"]],
            ["TSLA", "NVDA", "AAPL"],
        )
        self.assertNotIn("TSLA", body["fallbackForbiddenSymbols"])
        self.assertIn("CAT", body["fallbackForbiddenSymbols"])
        self.assertEqual(len(body["fallbackForbiddenSymbols"]), 45)


class GlobalGdeltWorkerTest(unittest.TestCase):
    def test_serializes_successful_scopes_at_ten_second_start_interval(self) -> None:
        controlled = _ControlledTime()
        response = GdeltHttpResponse(
            status=200,
            headers=(("content-type", "application/json"),),
            body=b'{"query_details":{},"timeline":[]}',
        )
        transport = _SequenceTransport((response, response))
        transport.bind_time(controlled)
        worker = GlobalGdeltWorker(
            transport=transport,
            monotonic=controlled.monotonic,
            sleeper=controlled.sleep,
            utc_clock=controlled.utc_now,
        )
        entry = GdeltQueryEntry(
            instrument_id="TSLA",
            symbol="TSLA",
            canonical_company_name="Tesla Inc",
            query='"Tesla Inc"',
            source_kind="official_nasdaq_trader_directory",
            source_name="Tesla, Inc. - Common Stock",
            source_path="instrument-master.json",
        )

        outcomes = worker.collect(
            (
                GdeltNewsScope.for_entry(entry, "timelinevolraw"),
                GdeltNewsScope.for_entry(entry, "timelinetone"),
            )
        )

        self.assertEqual(transport.started_at, [0.0, 10.0])
        self.assertEqual(
            tuple(outcome.terminal_status for outcome in outcomes),
            ("completed", "completed"),
        )
        self.assertEqual(controlled.sleeps, [10.0])

    def test_preserves_four_429_attempts_then_marks_provider_rate_limited(self) -> None:
        controlled = _ControlledTime()
        response = GdeltHttpResponse(
            status=429,
            headers=(("content-type", "text/plain"),),
            body=b"Please limit requests to one every 5 seconds.",
        )
        transport = _SequenceTransport((response, response, response, response))
        transport.bind_time(controlled)
        worker = GlobalGdeltWorker(
            transport=transport,
            monotonic=controlled.monotonic,
            sleeper=controlled.sleep,
            utc_clock=controlled.utc_now,
        )
        entry = GdeltQueryEntry(
            instrument_id="TSLA",
            symbol="TSLA",
            canonical_company_name="Tesla Inc",
            query='"Tesla Inc"',
            source_kind="official_nasdaq_trader_directory",
            source_name="Tesla, Inc. - Common Stock",
            source_path="instrument-master.json",
        )

        outcome = worker.collect(
            (GdeltNewsScope.for_entry(entry, "timelinevolraw"),)
        )[0]

        self.assertEqual(outcome.terminal_status, "provider_rate_limited")
        self.assertEqual(len(outcome.attempts), 4)
        self.assertEqual(transport.started_at, [0.0, 30.0, 90.0, 210.0])
        self.assertEqual(controlled.sleeps, [30.0, 60.0, 120.0])


class GdeltArchiveStorageTest(unittest.TestCase):
    def test_publishes_and_verifies_raw_attempts_manifest_and_sidecars(self) -> None:
        query_map = build_gdelt_query_map(
            scope_plan_source=_scope_plan_source(),
            directory_master_source=_directory_source(),
            frozen_at="2026-07-11T16:10:00Z",
        )
        entry = next(value for value in query_map.entries if value.symbol == "TSLA")
        controlled = _ControlledTime()
        transport = _SequenceTransport(
            (
                GdeltHttpResponse(
                    status=200,
                    headers=(("content-type", "application/json"),),
                    body=b'{"query_details":{},"timeline":[]}',
                ),
            )
        )
        transport.bind_time(controlled)
        outcome = GlobalGdeltWorker(
            transport=transport,
            monotonic=controlled.monotonic,
            sleeper=controlled.sleep,
            utc_clock=controlled.utc_now,
        ).collect((GdeltNewsScope.for_entry(entry, "timelinevolraw"),))[0]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage = GdeltArchiveStorage(root)
            query_binding = storage.publish_query_map(query_map)
            stored = storage.publish_outcome(query_binding, outcome)

            storage.verify_scope(stored)
            self.assertEqual(
                query_binding.sidecar_path.read_text(encoding="ascii"),
                f"{query_binding.artifact_sha256}\n",
            )
            self.assertEqual(
                stored.manifest_sha256_path.read_text(encoding="ascii"),
                f"{stored.manifest_sha256}\n",
            )
            self.assertEqual(len(stored.raw_body_paths), 1)
            self.assertEqual(len(stored.metadata_paths), 1)
            for path in (*stored.raw_body_paths, *stored.metadata_paths):
                self.assertTrue(Path(f"{path}.sha256").is_file())

            resumed = storage.publish_outcome(query_binding, outcome)
            self.assertEqual(resumed, stored)
            stored.raw_body_paths[0].write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "gdelt_archive_verification_failed"):
                storage.verify_scope(stored)


if __name__ == "__main__":
    unittest.main()
