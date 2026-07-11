from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rp001.local_evidence import (
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.archive_contract import BENCHMARK_SYMBOLS, PRIORITY_SYMBOLS
from rp001_s2.gdelt_news_archive import (
    GdeltArchiveStorage,
    GdeltHttpRequest,
    GdeltHttpResponse,
    GdeltNewsScope,
    GdeltQueryEntry,
    GlobalGdeltWorker,
    StrictGdeltTransport,
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


class _ExceptionSequenceTransport:
    def __init__(
        self,
        values: tuple[Exception | GdeltHttpResponse, ...],
    ) -> None:
        self._values = list(values)

    def __call__(self, request: object) -> GdeltHttpResponse:
        value = self._values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class _HttpFixture:
    def __init__(
        self,
        *,
        status: int = 200,
        headers: tuple[tuple[str, str], ...] = (
            ("content-type", "application/json"),
        ),
        body: bytes = b'{"query_details":{},"timeline":[]}',
    ) -> None:
        self.status = status
        self.headers = dict(headers)
        self._body = body

    def read(self, limit: int) -> bytes:
        return self._body[:limit]

    def close(self) -> None:
        pass


class _FixtureOpener:
    def __init__(self, result: _HttpFixture | OSError) -> None:
        self._result = result
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> _HttpFixture:
        self.requests.append((request, timeout))
        if isinstance(self._result, OSError):
            raise self._result
        return self._result


def _strict_request(**changes: str) -> GdeltHttpRequest:
    values = {
        "query": '"Tesla Inc"',
        "mode": "timelinevolraw",
        "format": "json",
        "startdatetime": "20260412000000",
        "enddatetime": "20260711000000",
        "timelinesmooth": "0",
    }
    values.update({key: value for key, value in changes.items() if key in values})
    url = changes.get(
        "url",
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        + urllib.parse.urlencode(values),
    )
    return GdeltHttpRequest(
        method=changes.get("method", "GET"),
        url=url,
        headers=(
            ("Accept", "application/json"),
            ("User-Agent", "RP-001 research collector (zero-cost, read-only)"),
        ),
    )


def _rewrite_canonical_artifact(path: Path, value: object) -> str:
    source = canonical_json_bytes(value)
    artifact_sha256 = sha256_bytes(source)
    path.write_bytes(source)
    Path(f"{path}.sha256").write_text(
        f"{artifact_sha256}\n",
        encoding="ascii",
    )
    return artifact_sha256


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

    def test_converts_arbitrary_transport_exception_and_continues_next_scope(self) -> None:
        controlled = _ControlledTime()
        transport = _ExceptionSequenceTransport(
            (
                RuntimeError("secret-bearing transport failure"),
                GdeltHttpResponse(
                    status=200,
                    headers=(("content-type", "application/json"),),
                    body=b'{"query_details":{},"timeline":[]}',
                ),
            )
        )
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

        self.assertEqual(
            tuple(outcome.terminal_status for outcome in outcomes),
            ("failed", "completed"),
        )
        self.assertEqual(outcomes[0].terminal_reason, "transport_error")
        self.assertEqual(outcomes[0].attempts[0].response.status, 0)
        self.assertNotIn(b"secret-bearing", outcomes[0].attempts[0].response.body)

    def test_rejects_jsonp_media_type_but_accepts_json_with_charset(self) -> None:
        controlled = _ControlledTime()
        transport = _SequenceTransport(
            (
                GdeltHttpResponse(
                    status=200,
                    headers=(("content-type", "application/jsonp"),),
                    body=b'{"query_details":{},"timeline":[]}',
                ),
                GdeltHttpResponse(
                    status=200,
                    headers=(
                        ("content-type", "application/json; charset=utf-8"),
                    ),
                    body=b'{"query_details":{},"timeline":[]}',
                ),
            )
        )
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

        self.assertEqual(
            tuple(outcome.terminal_status for outcome in outcomes),
            ("invalid", "completed"),
        )
        query_map = build_gdelt_query_map(
            scope_plan_source=_scope_plan_source(),
            directory_master_source=_directory_source(),
            frozen_at="2026-07-11T16:10:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            storage = GdeltArchiveStorage(Path(directory).resolve())
            stored = storage.publish_outcome(
                storage.publish_query_map(query_map),
                outcomes[0],
            )
            storage.verify_scope(stored)


class StrictGdeltTransportTest(unittest.TestCase):
    def test_allows_only_exact_frozen_get_request(self) -> None:
        opener = _FixtureOpener(_HttpFixture())
        transport = StrictGdeltTransport(opener=opener)

        response = transport(_strict_request())

        self.assertEqual(response.status, 200)
        self.assertEqual(len(opener.requests), 1)
        invalid_requests = (
            _strict_request(method="POST"),
            _strict_request(
                url="http://api.gdeltproject.org/api/v2/doc/doc?"
                + urllib.parse.urlencode(
                    {
                        "query": '"Tesla Inc"',
                        "mode": "timelinevolraw",
                        "format": "json",
                        "startdatetime": "20260412000000",
                        "enddatetime": "20260711000000",
                        "timelinesmooth": "0",
                    }
                )
            ),
            _strict_request(
                url="https://evil.example/api/v2/doc/doc?"
                + urllib.parse.urlencode(
                    {
                        "query": '"Tesla Inc"',
                        "mode": "timelinevolraw",
                        "format": "json",
                        "startdatetime": "20260412000000",
                        "enddatetime": "20260711000000",
                        "timelinesmooth": "0",
                    }
                )
            ),
            _strict_request(
                url="https://api.gdeltproject.org/api/v2/doc/other?"
                + urllib.parse.urlencode(
                    {
                        "query": '"Tesla Inc"',
                        "mode": "timelinevolraw",
                        "format": "json",
                        "startdatetime": "20260412000000",
                        "enddatetime": "20260711000000",
                        "timelinesmooth": "0",
                    }
                )
            ),
            _strict_request(startdatetime="20260413000000"),
            _strict_request(mode="artlist"),
            _strict_request(query='"unfrozen company"'),
            _strict_request(
                url=_strict_request().url + "&maxrecords=250",
            ),
        )
        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaisesRegex(ValueError, "gdelt_request_not_allowed"):
                    transport(request)
        self.assertEqual(len(opener.requests), 1)

    def test_rejects_redirect_response_without_following_it(self) -> None:
        opener = _FixtureOpener(
            _HttpFixture(
                status=302,
                headers=(("location", "https://evil.example/redirect"),),
                body=b"redirect",
            )
        )

        with self.assertRaisesRegex(ValueError, "gdelt_redirect_rejected"):
            StrictGdeltTransport(opener=opener)(_strict_request())

    def test_converts_oserror_to_safe_raw_failure_response(self) -> None:
        transport = StrictGdeltTransport(
            opener=_FixtureOpener(OSError("secret-bearing local failure"))
        )

        response = transport(_strict_request())

        self.assertEqual(response.status, 0)
        self.assertEqual(
            json.loads(response.body),
            {
                "errorCode": "gdelt_transport_oserror",
                "schemaVersion": "rp001-s2-gdelt-transport-failure.v1",
            },
        )
        self.assertNotIn(b"secret-bearing", response.body)


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

    def test_rejects_semantically_tampered_metadata_even_with_valid_hashes(self) -> None:
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

        mutations = (
            ("method", "POST"),
            ("endpoint", "https://evil.example/api/v2/doc/doc"),
            ("mode", "timelinetone"),
            ("querySha256", "0" * 64),
            ("attempt", 2),
            ("status", 429),
            ("contentType", "text/plain"),
        )
        for field, replacement in mutations:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    storage = GdeltArchiveStorage(root)
                    query_binding = storage.publish_query_map(query_map)
                    stored = storage.publish_outcome(query_binding, outcome)
                    metadata_path = stored.metadata_paths[0]
                    metadata = json.loads(metadata_path.read_bytes())
                    metadata[field] = replacement
                    metadata_sha256 = _rewrite_canonical_artifact(
                        metadata_path,
                        metadata,
                    )
                    manifest = json.loads(stored.manifest_path.read_bytes())
                    manifest["attempts"][0]["metadata"][
                        "sha256"
                    ] = metadata_sha256
                    manifest_sha256 = _rewrite_canonical_artifact(
                        stored.manifest_path,
                        manifest,
                    )

                    with self.assertRaisesRegex(
                        ValueError,
                        "gdelt_archive_verification_failed",
                    ):
                        storage.verify_scope(
                            replace(stored, manifest_sha256=manifest_sha256)
                        )

    def test_persists_oserror_as_failed_terminal_raw_and_metadata(self) -> None:
        query_map = build_gdelt_query_map(
            scope_plan_source=_scope_plan_source(),
            directory_master_source=_directory_source(),
            frozen_at="2026-07-11T16:10:00Z",
        )
        entry = next(value for value in query_map.entries if value.symbol == "TSLA")
        controlled = _ControlledTime()
        outcome = GlobalGdeltWorker(
            transport=StrictGdeltTransport(
                opener=_FixtureOpener(OSError("secret-bearing local failure"))
            ),
            monotonic=controlled.monotonic,
            sleeper=controlled.sleep,
            utc_clock=controlled.utc_now,
        ).collect((GdeltNewsScope.for_entry(entry, "timelinevolraw"),))[0]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage = GdeltArchiveStorage(root)
            stored = storage.publish_outcome(
                storage.publish_query_map(query_map),
                outcome,
            )

            storage.verify_scope(stored)
            manifest = json.loads(stored.manifest_path.read_bytes())
            metadata = json.loads(stored.metadata_paths[0].read_bytes())
            self.assertEqual(
                manifest["terminal"],
                {"status": "failed", "reason": "transport_error"},
            )
            self.assertEqual(metadata["status"], 0)
            self.assertEqual(metadata["contentType"], "application/json")
            self.assertNotIn(b"secret-bearing", stored.raw_body_paths[0].read_bytes())

    def test_recovers_body_only_partial_attempt_as_explicit_invalid_terminal(self) -> None:
        query_map = build_gdelt_query_map(
            scope_plan_source=_scope_plan_source(),
            directory_master_source=_directory_source(),
            frozen_at="2026-07-11T16:10:00Z",
        )
        entry = next(value for value in query_map.entries if value.symbol == "TSLA")
        scope = GdeltNewsScope.for_entry(entry, "timelinevolraw")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage = GdeltArchiveStorage(root)
            query_binding = storage.publish_query_map(query_map)
            scope_body = scope.to_canonical_body(query_binding.artifact_sha256)
            scope_sha256 = sha256_bytes(canonical_json_bytes(scope_body))
            partial_body_path = (
                root
                / "captures"
                / query_binding.artifact_sha256
                / "TSLA"
                / "timelinevolraw"
                / scope_sha256
                / "attempt-001.body.json"
            )
            partial = LocalArtifactStore(root).publish_bytes(
                partial_body_path,
                b'{"query_details":{},"timeline":[]}',
            )

            recovered = storage.recover_partial_scope(
                query_binding,
                scope,
                recovered_at="2026-07-11T16:20:00Z",
            )

            self.assertIsNotNone(recovered)
            assert recovered is not None
            storage.verify_scope(recovered)
            self.assertEqual(partial.path.read_bytes(), b'{"query_details":{},"timeline":[]}')
            manifest = json.loads(recovered.manifest_path.read_bytes())
            self.assertEqual(manifest["terminal"]["status"], "invalid")
            self.assertEqual(
                manifest["terminal"]["reason"],
                "partial_attempt_without_terminal_manifest",
            )

    def test_rejects_deleted_v2_manifest_ordinal_with_valid_rehashed_manifest(self) -> None:
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
            stored = storage.publish_outcome(
                storage.publish_query_map(query_map),
                outcome,
            )
            manifest = json.loads(stored.manifest_path.read_bytes())
            self.assertEqual(
                manifest["schemaVersion"],
                "rp001-s2-gdelt-news-manifest.v2",
            )
            del manifest["attempts"][0]["ordinal"]
            manifest_sha256 = _rewrite_canonical_artifact(
                stored.manifest_path,
                manifest,
            )

            with self.assertRaisesRegex(
                ValueError,
                "gdelt_archive_verification_failed",
            ):
                storage.verify_scope(
                    replace(stored, manifest_sha256=manifest_sha256)
                )

    def test_rejects_deleted_v2_request_url_hash_with_valid_rehashed_chain(self) -> None:
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
            stored = storage.publish_outcome(
                storage.publish_query_map(query_map),
                outcome,
            )
            metadata_path = stored.metadata_paths[0]
            metadata = json.loads(metadata_path.read_bytes())
            del metadata["requestUrlSha256"]
            metadata_sha256 = _rewrite_canonical_artifact(
                metadata_path,
                metadata,
            )
            manifest = json.loads(stored.manifest_path.read_bytes())
            manifest["attempts"][0]["metadata"]["sha256"] = metadata_sha256
            manifest_sha256 = _rewrite_canonical_artifact(
                stored.manifest_path,
                manifest,
            )

            with self.assertRaisesRegex(
                ValueError,
                "gdelt_archive_verification_failed",
            ):
                storage.verify_scope(
                    replace(stored, manifest_sha256=manifest_sha256)
                )

    def test_rejects_impossible_retry_status_sequence_with_valid_hashes(self) -> None:
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
                    status=429,
                    headers=(("content-type", "text/plain"),),
                    body=b"rate limited",
                ),
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
            stored = storage.publish_outcome(
                storage.publish_query_map(query_map),
                outcome,
            )
            first_metadata_path = stored.metadata_paths[0]
            first_metadata = json.loads(first_metadata_path.read_bytes())
            first_metadata["status"] = 500
            first_metadata_sha256 = _rewrite_canonical_artifact(
                first_metadata_path,
                first_metadata,
            )
            manifest = json.loads(stored.manifest_path.read_bytes())
            manifest["attempts"][0]["status"] = 500
            manifest["attempts"][0]["metadata"][
                "sha256"
            ] = first_metadata_sha256
            manifest_sha256 = _rewrite_canonical_artifact(
                stored.manifest_path,
                manifest,
            )

            with self.assertRaisesRegex(
                ValueError,
                "gdelt_archive_verification_failed",
            ):
                storage.verify_scope(
                    replace(stored, manifest_sha256=manifest_sha256)
                )

    def test_seals_sidecar_only_partial_without_repeating_publish_conflict(self) -> None:
        query_map = build_gdelt_query_map(
            scope_plan_source=_scope_plan_source(),
            directory_master_source=_directory_source(),
            frozen_at="2026-07-11T16:10:00Z",
        )
        entry = next(value for value in query_map.entries if value.symbol == "TSLA")
        scope = GdeltNewsScope.for_entry(entry, "timelinevolraw")
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
        ).collect((scope,))[0]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage = GdeltArchiveStorage(root)
            query_binding = storage.publish_query_map(query_map)
            scope_sha256 = sha256_bytes(
                canonical_json_bytes(
                    scope.to_canonical_body(query_binding.artifact_sha256)
                )
            )
            body_path = (
                root
                / "captures"
                / query_binding.artifact_sha256
                / "TSLA"
                / "timelinevolraw"
                / scope_sha256
                / "attempt-001.body.json"
            )
            body_path.parent.mkdir(parents=True)
            declared_sha256 = sha256_bytes(outcome.attempts[0].response.body)
            Path(f"{body_path}.sha256").write_text(
                f"{declared_sha256}\n",
                encoding="ascii",
            )

            recovered = storage.recover_partial_scope(
                query_binding,
                scope,
                recovered_at="2026-07-11T16:20:00Z",
            )

            self.assertIsNotNone(recovered)
            assert recovered is not None
            storage.verify_scope(recovered)
            manifest = json.loads(recovered.manifest_path.read_bytes())
            self.assertEqual(
                manifest["partialArtifacts"][0]["kind"],
                "orphan_body_sidecar",
            )
            self.assertEqual(
                manifest["partialArtifacts"][0]["declaredSha256"],
                declared_sha256,
            )
            self.assertEqual(
                storage.publish_outcome(query_binding, outcome),
                recovered,
            )


if __name__ == "__main__":
    unittest.main()
