from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from rp001.toss_research_collector import HttpRequest, HttpResponse
from rp001_s2.intraday_measurement import (
    IntradayMeasurementCollector,
    MeasurementError,
)


class _QueueTransport:
    def __init__(self, responses: tuple[HttpResponse, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _response(value: object) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps(value, separators=(",", ":")).encode("utf-8"),
    )


def _candle(
    timestamp: str,
    *,
    open_price: str = "100",
    high_price: str = "103",
    low_price: str = "99",
    close_price: str = "102",
    volume: str = "10",
) -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "openPrice": open_price,
        "highPrice": high_price,
        "lowPrice": low_price,
        "closePrice": close_price,
        "volume": volume,
        "currency": "USD",
    }


def _candle_page(
    rows: list[dict[str, str]],
    next_before: str | None,
) -> HttpResponse:
    return _response({"result": {"candles": rows, "nextBefore": next_before}})


class IntradayPaginationContractTest(unittest.TestCase):
    def test_initial_before_inside_scope_keeps_analysis_end_at_scope_end(self) -> None:
        transport = _QueueTransport(
            (
                _candle_page(
                    [
                        _candle("2026-07-09T23:59:00Z"),
                        _candle("2026-07-09T00:01:00Z"),
                    ],
                    None,
                ),
            )
        )
        collector = IntradayMeasurementCollector(
            transport=transport,
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="AAPL",
            interval="1m",
            adjusted=False,
            start_at="2026-07-09T00:00:00Z",
            end_at="2026-07-10T00:00:00Z",
            initial_before="2026-07-09T23:59:00Z",
            count=200,
            page_limit=4,
        )

        self.assertEqual(len(result.analysis_rows), 2)
        self.assertEqual(result.analysis_rows[-1].bar_end, "2026-07-10T00:00:00Z")
        self.assertIn("before=2026-07-09T23%3A59%3A00Z", transport.requests[0].url)

    def test_distinct_minutes_in_one_session_are_preserved_with_raw_lineage(self) -> None:
        first = _candle_page(
            [
                _candle("2026-07-10T22:31:00+09:00"),
                _candle("2026-07-10T22:30:00+09:00", close_price="101"),
            ],
            "2026-07-10T22:30:00+09:00",
        )
        second = _candle_page(
            [
                _candle("2026-07-10T22:30:00+09:00", close_price="101"),
                _candle("2026-07-10T22:29:00+09:00", close_price="100"),
            ],
            None,
        )
        transport = _QueueTransport((first, second))
        collector = IntradayMeasurementCollector(
            transport=transport,
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="BA",
            interval="1m",
            adjusted=False,
            start_at="2026-07-10T22:29:00+09:00",
            end_at="2026-07-10T22:32:00+09:00",
            initial_before="2026-07-10T22:32:00+09:00",
            count=200,
            page_limit=4,
        )

        self.assertEqual(
            [row.timestamp for row in result.analysis_rows],
            [
                "2026-07-10T22:29:00+09:00",
                "2026-07-10T22:30:00+09:00",
                "2026-07-10T22:31:00+09:00",
            ],
        )
        self.assertEqual(result.inclusive_overlap_count, 1)
        self.assertTrue(result.requested_start_reached)
        self.assertEqual(result.completion_reason, "start_boundary_reached")
        self.assertEqual(len(result.captures), 2)
        self.assertEqual(result.analysis_rows[1].source_body_sha256, result.captures[0].body_sha256)
        self.assertEqual(result.analysis_rows[1].source_row_index, 1)
        self.assertEqual(len(result.analysis_rows[1].occurrences), 2)
        self.assertEqual(result.analysis_rows[1].occurrences[1][0], result.captures[1].body_sha256)
        self.assertIn("before=2026-07-10T22%3A30%3A00%2B09%3A00", transport.requests[1].url)

    def test_inclusive_overlap_with_changed_values_is_invalid(self) -> None:
        transport = _QueueTransport(
            (
                _candle_page(
                    [_candle("2026-07-10T22:30:00+09:00")],
                    "2026-07-10T22:30:00+09:00",
                ),
                _candle_page(
                    [_candle("2026-07-10T22:30:00+09:00", close_price="101")],
                    None,
                ),
            )
        )
        collector = IntradayMeasurementCollector(
            transport=transport,
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "CONFLICTING_DUPLICATE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_later_transport_failure_preserves_prior_safe_capture(self) -> None:
        transport = _QueueTransport(
            (
                _candle_page(
                    [_candle("2026-07-10T22:30:00+09:00")],
                    "2026-07-10T22:30:00+09:00",
                ),
            )
        )
        collector = IntradayMeasurementCollector(
            transport=transport,
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaises(MeasurementError) as raised:
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:00:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

        self.assertEqual(raised.exception.code, "TRANSPORT_ERROR")
        self.assertEqual(len(raised.exception.captures), 1)
        self.assertEqual(
            raised.exception.captures[0].query[-1],
            ("before", "2026-07-10T22:32:00+09:00"),
        )

    def test_empty_terminal_page_is_preserved_as_observed_unavailability(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport((_candle_page([], None),)),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="BA",
            interval="1m",
            adjusted=False,
            start_at="2026-07-10T09:00:00+09:00",
            end_at="2026-07-11T07:00:00+09:00",
            initial_before="2026-07-11T07:00:00+09:00",
            count=200,
            page_limit=4,
        )

        self.assertEqual(result.analysis_rows, ())
        self.assertEqual(len(result.captures), 1)
        self.assertFalse(result.requested_start_reached)
        self.assertEqual(result.completion_reason, "empty_provider_terminal")

    def test_provider_terminal_before_requested_start_is_explicitly_partial(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:30:00+09:00")], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="BA",
            interval="1m",
            adjusted=False,
            start_at="2026-07-10T22:00:00+09:00",
            end_at="2026-07-10T22:32:00+09:00",
            initial_before="2026-07-10T22:32:00+09:00",
            count=200,
            page_limit=4,
        )

        self.assertFalse(result.requested_start_reached)
        self.assertEqual(result.completion_reason, "provider_terminal_before_start")

    def test_ohlc_relationship_violation_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:30:00+09:00", low_price="101", open_price="100")], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "OHLC_INVARIANT"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_decimal_volume_is_preserved_losslessly(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (
                    _candle_page(
                        [_candle("2026-07-10T22:30:00+09:00", volume="10.500")],
                        None,
                    ),
                )
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="BA",
            interval="1m",
            adjusted=False,
            start_at="2026-07-10T22:29:00+09:00",
            end_at="2026-07-10T22:32:00+09:00",
            initial_before="2026-07-10T22:32:00+09:00",
            count=200,
            page_limit=4,
        )

        self.assertEqual(result.analysis_rows[0].volume.text, "10.500")

    def test_negative_decimal_volume_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (
                    _candle_page(
                        [_candle("2026-07-10T22:30:00+09:00", volume="-0.1")],
                        None,
                    ),
                )
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "INVALID_CANDLE_SHAPE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_same_instant_with_a_different_offset_representation_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (
                    _candle_page(
                        [_candle("2026-07-10T22:30:00+09:00")],
                        "2026-07-10T13:30:00Z",
                    ),
                    _candle_page([_candle("2026-07-10T13:30:00Z")], None),
                )
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "CONFLICTING_DUPLICATE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_empty_nonterminal_page_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([], "2026-07-10T22:30:00+09:00"),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "NO_PAGINATION_PROGRESS"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_repeated_cursor_is_invalid(self) -> None:
        initial = "2026-07-10T22:32:00+09:00"
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:30:00+09:00")], initial),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "REPEATED_CURSOR"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before=initial,
                count=200,
                page_limit=4,
            )

    def test_duplicate_in_one_page_is_invalid_even_when_values_match(self) -> None:
        timestamp = "2026-07-10T22:30:00+09:00"
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle(timestamp), _candle(timestamp)], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "DUPLICATE_WITHIN_PAGE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_response_after_requested_before_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:33:00+09:00")], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "CANDLE_AFTER_BEFORE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_off_minute_grid_timestamp_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:30:01+09:00")], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "INVALID_CANDLE_SHAPE"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:29:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=4,
            )

    def test_forming_bar_is_kept_for_audit_but_not_analysis(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (_candle_page([_candle("2026-07-10T22:30:00+09:00")], None),)
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 10, 13, 30, 30, tzinfo=timezone.utc),
        )

        result = collector.collect_candles(
            symbol="BA",
            interval="1m",
            adjusted=False,
            start_at="2026-07-10T22:29:00+09:00",
            end_at="2026-07-10T22:32:00+09:00",
            initial_before="2026-07-10T22:32:00+09:00",
            count=200,
            page_limit=4,
        )

        self.assertEqual(result.analysis_rows, ())
        self.assertEqual(len(result.audit_only_rows), 1)
        self.assertEqual(result.audit_only_rows[0].bar_end, "2026-07-10T13:31:00Z")
        self.assertEqual(result.audit_only_rows[0].available_at, "2026-07-10T13:30:30Z")

    def test_page_limit_before_start_boundary_is_invalid(self) -> None:
        collector = IntradayMeasurementCollector(
            transport=_QueueTransport(
                (
                    _candle_page(
                        [_candle("2026-07-10T22:30:00+09:00")],
                        "2026-07-10T22:30:00+09:00",
                    ),
                )
            ),
            token_supplier=lambda: "ephemeral",
            clock=lambda: datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(MeasurementError, "PAGE_LIMIT_EXCEEDED"):
            collector.collect_candles(
                symbol="BA",
                interval="1m",
                adjusted=False,
                start_at="2026-07-10T22:00:00+09:00",
                end_at="2026-07-10T22:32:00+09:00",
                initial_before="2026-07-10T22:32:00+09:00",
                count=200,
                page_limit=1,
            )


if __name__ == "__main__":
    unittest.main()
