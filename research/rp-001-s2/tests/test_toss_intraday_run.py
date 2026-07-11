from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from rp001_s2.archive_contract import CollectionScope, SampleRole
from rp001_s2.toss_intraday_run import (
    IntradayRunError,
    RefreshingTokenSupplier,
    load_secure_toss_environment,
    open_toss_minute_session,
    run_toss_minute_shard,
    seven_day_shards,
)


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self.headers = {"Content-Type": "application/json"}
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


class _ProviderDateOpener:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.pages_by_before = self._build_pages_by_before(rows)
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> _Response:
        del timeout
        self.requests.append(request)
        if len(self.requests) == 1:
            return _Response(b'{"access_token":"ephemeral-token"}')
        full_url = getattr(request, "full_url")
        before = parse_qs(urlsplit(full_url).query)["before"][0]
        rows, next_before = self.pages_by_before.get(before, ([], None))
        return _Response(
            json.dumps(
                {"result": {"candles": rows, "nextBefore": next_before}},
                separators=(",", ":"),
            ).encode("utf-8")
        )

    @staticmethod
    def _build_pages_by_before(
        rows: list[dict[str, str]],
    ) -> dict[str, tuple[list[dict[str, str]], str | None]]:
        pages: dict[str, tuple[list[dict[str, str]], str | None]] = {}
        cursor = "2026-07-09T23:59:00Z"
        start = 0
        while start < len(rows):
            page = rows[start : start + 200]
            end = start + len(page)
            next_before = page[-1]["timestamp"] if end < len(rows) else None
            pages[cursor] = (page, next_before)
            if next_before is None:
                break
            cursor = next_before
            start = end - 1
        return pages


def _scope(
    *,
    start_at: datetime = datetime(2026, 7, 1, tzinfo=timezone.utc),
    end_at: datetime = datetime(2026, 7, 15, tzinfo=timezone.utc),
    sample_role: SampleRole = SampleRole.SEEN,
) -> CollectionScope:
    return CollectionScope(
        provider="toss",
        feed="provider_all",
        instrument_id="AAPL",
        symbol="AAPL",
        interval="1m",
        start_at=start_at,
        end_at=end_at,
        adjustment_mode="native",
        session_scope="provider_all",
        sample_role=sample_role,
    )


def _provider_date_rows() -> list[dict[str, str]]:
    retained_minutes = tuple(range(1439, 101, -1)) + (1,)
    return [
        {
            "timestamp": (
                datetime(2026, 7, 9, tzinfo=timezone.utc)
                .replace(hour=minute // 60, minute=minute % 60)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
            "openPrice": "100",
            "highPrice": "103",
            "lowPrice": "99",
            "closePrice": "102",
            "volume": "10.500",
            "currency": "USD",
        }
        for minute in retained_minutes
    ]


class TossIntradayRunTest(unittest.TestCase):
    def test_single_session_refreshes_its_token_before_expiry(self) -> None:
        first_candle = {
            "timestamp": "2026-07-10T13:30:00Z",
            "openPrice": "100",
            "highPrice": "103",
            "lowPrice": "99",
            "closePrice": "102",
            "volume": "10",
            "currency": "USD",
        }
        second_candle = {**first_candle, "timestamp": "2026-07-10T13:40:00Z"}
        opener = _QueueOpener(
            (
                _Response(b'{"access_token":"first-token"}'),
                _Response(json.dumps({"result": {"candles": [first_candle], "nextBefore": None}}).encode()),
                _Response(b'{"access_token":"second-token"}'),
                _Response(json.dumps({"result": {"candles": [second_candle], "nextBefore": None}}).encode()),
            )
        )
        moments = iter((0.0, 0.0, 301.0, 301.0))
        first_scope = replace(
            _scope(
                start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
                end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
            ),
            instrument_id="stable-instrument-id",
        )
        second_scope = replace(
            first_scope,
            start_at=datetime(2026, 7, 10, 13, 40, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, 13, 42, tzinfo=timezone.utc),
        )

        session = open_toss_minute_session(
            environment={
                "TOSS_CLIENT_ID": "identifier",
                "TOSS_CLIENT_SECRET": "private-value",
            },
            opener=opener,
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
            token_monotonic=lambda: next(moments),
        )
        session.collect(first_scope, request_pacer=lambda: None)
        session.collect(second_scope, request_pacer=lambda: None)
        session.close()

        self.assertEqual(
            [getattr(request, "method") for request in opener.requests],
            ["POST", "GET", "POST", "GET"],
        )

    def test_refreshing_token_supplier_closes_without_secret_repr(self) -> None:
        moments = iter((0.0, 299.0, 300.0, 300.0))
        supplier = RefreshingTokenSupplier(
            initial_token="first-token",
            refresh=lambda: "second-token",
            monotonic=lambda: next(moments),
        )

        self.assertEqual(supplier(), "first-token")
        self.assertEqual(supplier(), "second-token")
        supplier.close()

        with self.assertRaisesRegex(IntradayRunError, "session_closed"):
            supplier()
        self.assertNotIn("first-token", repr(supplier))
        self.assertNotIn("second-token", repr(supplier))

    def test_authenticated_session_reuses_one_token_until_closed(self) -> None:
        first_candle = {
            "timestamp": "2026-07-10T13:30:00Z",
            "openPrice": "100",
            "highPrice": "103",
            "lowPrice": "99",
            "closePrice": "102",
            "volume": "10",
            "currency": "USD",
        }
        second_candle = {
            **first_candle,
            "timestamp": "2026-07-10T13:40:00Z",
        }
        opener = _QueueOpener(
            (
                _Response(b'{"access_token":"ephemeral-token"}'),
                _Response(
                    json.dumps(
                        {"result": {"candles": [first_candle], "nextBefore": None}},
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
                _Response(
                    json.dumps(
                        {"result": {"candles": [second_candle], "nextBefore": None}},
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
            )
        )
        environment = {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "private-value",
        }
        first_scope = replace(
            _scope(
                start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
                end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
            ),
            instrument_id="stable-instrument-id",
        )
        second_scope = replace(
            first_scope,
            start_at=datetime(2026, 7, 10, 13, 40, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, 13, 42, tzinfo=timezone.utc),
        )

        session = open_toss_minute_session(
            environment=environment,
            opener=opener,
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )
        first = session.collect(first_scope, request_pacer=lambda: None)
        second = session.collect(second_scope, request_pacer=lambda: None)
        session.close()

        self.assertEqual(environment, {})
        self.assertEqual(len(first.analysis_rows), 1)
        self.assertEqual(len(second.analysis_rows), 1)
        self.assertEqual(
            [getattr(request, "method") for request in opener.requests],
            ["POST", "GET", "GET"],
        )
        with self.assertRaisesRegex(IntradayRunError, "session_closed"):
            session.collect(second_scope, request_pacer=lambda: None)
        self.assertNotIn("ephemeral-token", repr(session))

    def test_provider_date_daily_scope_queries_2359_and_preserves_1339_rows(self) -> None:
        scope = CollectionScope(
            provider="toss",
            feed="provider_date_daily_v2",
            instrument_id="stable-aapl-id",
            symbol="AAPL",
            interval="1m",
            start_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            adjustment_mode="native",
            session_scope="provider_all",
            sample_role=SampleRole.SEEN,
        )
        opener = _ProviderDateOpener(_provider_date_rows())

        result = run_toss_minute_shard(
            scope,
            environment={
                "TOSS_CLIENT_ID": "identifier",
                "TOSS_CLIENT_SECRET": "private-value",
            },
            opener=opener,
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
            request_pacer=lambda: None,
        )

        self.assertEqual(len(result.analysis_rows), 1_339)
        self.assertEqual(result.analysis_rows[0].normalized_instant, "2026-07-09T00:01:00Z")
        self.assertEqual(result.analysis_rows[-1].normalized_instant, "2026-07-09T23:59:00Z")
        self.assertEqual(len(result.captures), 7)
        self.assertTrue(all(len(page[0]) <= 200 for page in opener.pages_by_before.values()))
        candle_url = getattr(opener.requests[1], "full_url")
        self.assertEqual(
            parse_qs(urlsplit(candle_url).query)["before"],
            ["2026-07-09T23:59:00Z"],
        )
        self.assertNotEqual(
            scope.acquisition_key,
            replace(scope, feed="provider_all").acquisition_key,
        )

    def test_provider_date_daily_scope_rejects_non_daily_or_off_grid_windows(self) -> None:
        valid = CollectionScope(
            provider="toss",
            feed="provider_date_daily_v2",
            instrument_id="stable-aapl-id",
            symbol="AAPL",
            interval="1m",
            start_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            adjustment_mode="native",
            session_scope="provider_all",
            sample_role=SampleRole.SEEN,
        )
        invalid_scopes = (
            replace(valid, end_at=datetime(2026, 7, 10, 0, 1, tzinfo=timezone.utc)),
            replace(
                valid,
                start_at=datetime(2026, 7, 9, 23, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 7, 10, 0, 30, tzinfo=timezone.utc),
            ),
            replace(
                valid,
                start_at=datetime(2026, 7, 9, 0, 0, 1, tzinfo=timezone.utc),
            ),
        )
        opener = _QueueOpener(())

        for invalid in invalid_scopes:
            with self.subTest(scope=invalid):
                with self.assertRaisesRegex(IntradayRunError, "scope_not_allowed"):
                    run_toss_minute_shard(
                        invalid,
                        environment={
                            "TOSS_CLIENT_ID": "identifier",
                            "TOSS_CLIENT_SECRET": "private-value",
                        },
                        opener=opener,
                        clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                        request_pacer=lambda: None,
                    )

        self.assertEqual(opener.requests, [])

    def test_secure_file_is_consumed_into_one_shot_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "toss-credentials.local.json"
            path.write_text(
                json.dumps(
                    {
                        "clientId": "identifier",
                        "clientSecret": "private-value",
                        "metadata": {"purpose": "research"},
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)

            environment = load_secure_toss_environment(path)

        self.assertEqual(environment.pop("TOSS_CLIENT_ID"), "identifier")
        self.assertEqual(environment.pop("TOSS_CLIENT_SECRET"), "private-value")
        self.assertEqual(environment, {})

    def test_secure_file_rejects_symlink_and_permissive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text(
                '{"clientId":"identifier","clientSecret":"private-value"}',
                encoding="utf-8",
            )
            target.chmod(0o644)
            link = root / "link.json"
            link.symlink_to(target)

            with self.assertRaisesRegex(IntradayRunError, "credential_file_invalid"):
                load_secure_toss_environment(target)
            with self.assertRaisesRegex(IntradayRunError, "credential_file_invalid"):
                load_secure_toss_environment(link)

    def test_seven_day_shards_cover_scope_without_gaps_or_role_filtering(self) -> None:
        seen = seven_day_shards(_scope(sample_role=SampleRole.SEEN))
        unseen = seven_day_shards(_scope(sample_role=SampleRole.UNSEEN))

        self.assertEqual(
            [(item.start_at, item.end_at) for item in seen],
            [(item.start_at, item.end_at) for item in unseen],
        )
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0].start_at, _scope().start_at)
        self.assertEqual(seen[0].end_at, seen[1].start_at)
        self.assertEqual(seen[-1].end_at, _scope().end_at)
        self.assertTrue(
            all((item.end_at - item.start_at).days <= 7 for item in seen)
        )

    def test_live_shard_path_authenticates_then_calls_only_minute_candles(self) -> None:
        candle = {
            "timestamp": "2026-07-10T13:30:00Z",
            "openPrice": "100",
            "highPrice": "103",
            "lowPrice": "99",
            "closePrice": "102",
            "volume": "10.500",
            "currency": "USD",
        }
        opener = _QueueOpener(
            (
                _Response(b'{"access_token":"ephemeral-token"}'),
                _Response(
                    json.dumps(
                        {"result": {"candles": [candle], "nextBefore": None}},
                        separators=(",", ":"),
                    ).encode("utf-8")
                ),
            )
        )
        environment = {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "private-value",
        }
        shard = _scope(
            start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
        )
        shard = replace(shard, instrument_id="stable-instrument-id")

        result = run_toss_minute_shard(
            shard,
            environment=environment,
            opener=opener,
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
            request_pacer=lambda: None,
        )

        self.assertEqual(environment, {})
        self.assertEqual(len(result.analysis_rows), 1)
        self.assertEqual(result.analysis_rows[0].volume.text, "10.500")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(getattr(opener.requests[0], "method"), "POST")
        self.assertEqual(getattr(opener.requests[1], "method"), "GET")
        self.assertEqual(
            getattr(opener.requests[1], "full_url").split("?", 1)[0],
            "https://openapi.tossinvest.com/api/v1/candles",
        )
        self.assertNotIn("private-value", repr(result))

    def test_non_toss_or_non_minute_scope_is_rejected_before_network(self) -> None:
        opener = _QueueOpener(())
        invalid = CollectionScope(
            provider="alpaca",
            feed="iex",
            instrument_id="AAPL",
            symbol="AAPL",
            interval="1m",
            start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
            adjustment_mode="native",
            session_scope="provider_all",
            sample_role=SampleRole.SEEN,
        )

        with self.assertRaisesRegex(IntradayRunError, "scope_not_allowed"):
            run_toss_minute_shard(
                invalid,
                environment={
                    "TOSS_CLIENT_ID": "identifier",
                    "TOSS_CLIENT_SECRET": "private-value",
                },
                opener=opener,
                clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                request_pacer=lambda: None,
            )

        self.assertEqual(opener.requests, [])

    def test_measurement_failure_preserves_safe_raw_captures(self) -> None:
        opener = _QueueOpener(
            (
                _Response(b'{"access_token":"ephemeral-token"}'),
                _Response(b'{"error":"temporarily unavailable"}', status=503),
            )
        )
        environment = {
            "TOSS_CLIENT_ID": "identifier",
            "TOSS_CLIENT_SECRET": "private-value",
        }
        shard = _scope(
            start_at=datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 10, 13, 32, tzinfo=timezone.utc),
        )

        with self.assertRaises(IntradayRunError) as raised:
            run_toss_minute_shard(
                shard,
                environment=environment,
                opener=opener,
                clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
                request_pacer=lambda: None,
            )

        self.assertEqual(raised.exception.code, "HTTP_STATUS")
        self.assertEqual(len(raised.exception.captures), 1)
        self.assertEqual(raised.exception.captures[0].status, 503)
        self.assertNotIn("ephemeral-token", repr(raised.exception.captures))


if __name__ == "__main__":
    unittest.main()
