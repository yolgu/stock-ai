from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib
import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit
import unittest

from rp001.toss_research_collector import (
    CandleCollection,
    CanonicalScalar,
    CollectorError,
    HttpRequest,
    HttpResponse,
    RawHttpCapture,
    TossResearchCollector,
)


MEMORY_BEARER = "unit-" + "test-" + "memory-" + "bearer"
NOW = datetime(2026, 7, 11, 1, 2, 3, tzinfo=timezone.utc)
INITIAL_BEFORE = "2026-07-01T00:00:00Z"


class QueueTransport:
    def __init__(self, responses: Sequence[HttpResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected transport request")
        return self._responses.pop(0)


def fixed_clock() -> datetime:
    return NOW


def valid_metadata(symbol: str = "AAPL") -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": "Apple",
        "englishName": "Apple Inc.",
        "isinCode": "US0378331005",
        "market": "NASDAQ",
        "securityType": "STOCK",
        "isCommonShare": True,
        "status": "ACTIVE",
        "currency": "USD",
        "sharesOutstanding": "15200000000",
    }


def candle(
    timestamp: str,
    *,
    currency: str = "USD",
    close_price: str = "103",
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "openPrice": "100",
        "highPrice": "105",
        "lowPrice": "99",
        "closePrice": close_price,
        "volume": "123456",
        "currency": currency,
    }


def json_response(
    value: object,
    *,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return HttpResponse(
        status=status,
        headers=headers or {"Content-Type": "application/json; charset=utf-8"},
        body=body,
    )


def metadata_response(rows: Sequence[dict[str, object]]) -> HttpResponse:
    return json_response({"result": list(rows)})


def candle_response(
    rows: Sequence[dict[str, object]],
    next_before: str | None = None,
) -> HttpResponse:
    value: dict[str, object] = {"candles": list(rows)}
    if next_before is not None:
        value["nextBefore"] = next_before
    return json_response({"result": value})


def json_unicode_escaped(value: str) -> str:
    return "".join(f"\\u{ord(character):04x}" for character in value)


def collector_for(
    responses: Sequence[HttpResponse],
    token_supplier: Callable[[], str] | None = None,
) -> tuple[TossResearchCollector, QueueTransport]:
    transport = QueueTransport(responses)
    collector = TossResearchCollector(
        transport=transport,
        token_supplier=token_supplier or (lambda: MEMORY_BEARER),
        clock=fixed_clock,
    )
    return collector, transport


def traceback_exposed_strings(error: BaseException) -> tuple[str, ...]:
    exposed: list[str] = []
    pending_errors: list[BaseException] = [error]
    seen_errors: set[int] = set()

    def collect_value(value: object, seen_values: set[int]) -> None:
        if id(value) in seen_values:
            return
        seen_values.add(id(value))
        if isinstance(value, str):
            exposed.append(value)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                collect_value(key, seen_values)
                collect_value(item, seen_values)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                collect_value(item, seen_values)
            return
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            for field in dataclasses.fields(value):
                collect_value(getattr(value, field.name), seen_values)

    while pending_errors:
        current_error = pending_errors.pop()
        if id(current_error) in seen_errors:
            continue
        seen_errors.add(id(current_error))
        traceback = current_error.__traceback__
        while traceback is not None:
            for local_name, local_value in traceback.tb_frame.f_locals.items():
                if local_name != "self":
                    collect_value(local_value, set())
            traceback = traceback.tb_next
        if current_error.__cause__ is not None:
            pending_errors.append(current_error.__cause__)
        if current_error.__context__ is not None:
            pending_errors.append(current_error.__context__)
    return tuple(exposed)


class TossResearchCollectorModuleContractTest(unittest.TestCase):
    def test_research_only_collector_module_exists(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("rp001.toss_research_collector"))

    def test_module_exposes_only_typed_collection_boundary_objects(self) -> None:
        module = importlib.import_module("rp001.toss_research_collector")
        expected_names = {
            "CollectorError",
            "HttpRequest",
            "HttpResponse",
            "RawHttpCapture",
            "CanonicalScalar",
            "StockMetadata",
            "MetadataCollection",
            "CandleRow",
            "CandleCollection",
            "PairedCandleRow",
            "CombinedCandleCollection",
            "TossResearchCollector",
        }

        self.assertEqual(
            set(getattr(module, "__all__", ())),
            expected_names,
        )

    def test_collector_has_no_public_generic_request_or_url_builder(self) -> None:
        public_methods = {
            name
            for name in dir(TossResearchCollector)
            if not name.startswith("_") and callable(getattr(TossResearchCollector, name))
        }

        self.assertEqual(
            public_methods,
            {"collect_metadata", "collect_candles", "collect_adjusted_native"},
        )


class TossResearchCollectorTestCase(unittest.TestCase):
    def collect(self, operation: Callable[[], object]) -> object:
        try:
            return operation()
        except Exception as error:  # noqa: BLE001 - converts unexpected exceptions into RED failures
            self.fail(f"collection unexpectedly failed with {type(error).__name__}: {error}")

    def assert_error_code(self, expected_code: str, operation: Callable[[], object]) -> CollectorError:
        try:
            with self.assertRaises(CollectorError) as raised:
                operation()
        except (TypeError, UnicodeError, OverflowError) as unexpected_error:
            self.fail(
                "collector leaked a raw boundary exception: "
                f"{type(unexpected_error).__name__}"
            )
        self.assertEqual(raised.exception.code, expected_code)
        return raised.exception

    def assert_capture_bodies(
        self,
        error: CollectorError,
        expected_bodies: Sequence[bytes],
    ) -> None:
        captures = getattr(error, "captures", ())
        self.assertIsInstance(captures, tuple)
        self.assertEqual(
            [base64.b64decode(capture.body_base64) for capture in captures],
            list(expected_bodies),
        )


class MetadataCollectionContractTest(TossResearchCollectorTestCase):
    def test_metadata_uses_only_exact_allowed_get_url_and_symbols_query(self) -> None:
        collector, transport = collector_for(
            [metadata_response([valid_metadata("AAPL"), valid_metadata("MSFT")])]
        )

        result = self.collect(lambda: collector.collect_metadata(("AAPL", "MSFT")))

        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(
            request.url,
            "https://openapi.tossinvest.com/api/v1/stocks?symbols=AAPL%2CMSFT",
        )
        self.assertEqual(parse_qs(urlsplit(request.url).query), {"symbols": ["AAPL,MSFT"]})
        self.assertEqual(dict(request.headers)["Authorization"], f"Bearer {MEMORY_BEARER}")

    def test_metadata_capture_preserves_exact_body_hash_and_only_allowlisted_headers(self) -> None:
        response = json_response(
            {"result": [valid_metadata()]},
            headers={
                "Content-Type": "application/json",
                "ETag": '"abc"',
                "X-RateLimit-Remaining": "9",
                "Set-Cookie": "private-cookie",
                "X-Debug": "private-detail",
            },
        )
        collector, _ = collector_for([response])

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))
        capture = result.capture

        self.assertEqual(base64.b64decode(capture.body_base64), response.body)
        self.assertEqual(capture.body_sha256, hashlib.sha256(response.body).hexdigest())
        self.assertEqual(capture.received_at, "2026-07-11T01:02:03Z")
        self.assertEqual(
            dict(capture.headers),
            {
                "content-type": "application/json",
                "etag": '"abc"',
                "x-ratelimit-remaining": "9",
            },
        )
        canonical_keys = set(dataclasses.asdict(capture))
        self.assertTrue({"body_base64", "body_sha256"}.issubset(canonical_keys))
        self.assertTrue(
            {"artifact_sha256", "self_sha256", "record_sha256"}.isdisjoint(canonical_keys)
        )

    def test_content_type_accepts_exact_json_media_type_with_optional_charset_only(self) -> None:
        accepted_values = (
            "application/json",
            "\tApplication/JSON ; charset=utf-8 ",
            'application/json;charset="UTF-8"',
        )
        for content_type in accepted_values:
            with self.subTest(content_type=content_type):
                response = metadata_response([valid_metadata()])
                response = HttpResponse(
                    response.status,
                    {"Content-Type": content_type},
                    response.body,
                )
                collector, _ = collector_for([response])

                result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

                self.assertEqual(result.records[0].symbol, "AAPL")

    def test_content_type_rejects_json_prefix_suffix_and_unregistered_parameters(self) -> None:
        rejected_values = (
            "application/jsonp",
            "application/problem+json",
            "application/json+suffix",
            "text/json",
            "application/json profile=x",
            "application/json; profile=x",
            "application/json; charset=utf-8; profile=x",
            "application/json; charset",
        )
        for content_type in rejected_values:
            with self.subTest(content_type=content_type):
                response = metadata_response([valid_metadata()])
                response = HttpResponse(
                    response.status,
                    {"Content-Type": content_type},
                    response.body,
                )
                collector, _ = collector_for([response])

                error = self.assert_error_code(
                    "INVALID_CONTENT_TYPE",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

                self.assert_capture_bodies(error, [response.body])

    def test_metadata_preserves_numeric_scalar_lexeme_and_type(self) -> None:
        body = (
            b'{"result":[{"symbol":"AAPL","name":"Apple","englishName":"Apple Inc.",'
            b'"isinCode":"US0378331005","market":"NASDAQ","securityType":"STOCK",'
            b'"isCommonShare":true,"status":"ACTIVE","currency":"USD",'
            b'"sharesOutstanding":"015200000000"}]}'
        )
        response = HttpResponse(200, {"Content-Type": "application/json"}, body)
        collector, _ = collector_for([response])

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

        self.assertEqual(
            result.records[0].shares_outstanding,
            CanonicalScalar(kind="json_string", text="015200000000"),
        )

    def test_metadata_rejects_invalid_inputs_before_token_or_transport(self) -> None:
        supplied = 0

        def token_supplier() -> str:
            nonlocal supplied
            supplied += 1
            return MEMORY_BEARER

        invalid_pools: tuple[object, ...] = (
            (),
            "AAPL",
            ("AAPL", "AAPL"),
            ("aapl",),
            ("\ud800",),
            (["AAPL"],),
            ({"symbol": "AAPL"},),
            tuple(f"S{index}" for index in range(201)),
        )
        for invalid_pool in invalid_pools:
            with self.subTest(pool_type=type(invalid_pool).__name__, length=len(invalid_pool)):
                collector, transport = collector_for([], token_supplier)
                self.assert_error_code(
                    "INVALID_INPUT",
                    lambda invalid_pool=invalid_pool: collector.collect_metadata(invalid_pool),
                )
                self.assertEqual(transport.requests, [])
        self.assertEqual(supplied, 0)

    def test_metadata_rejects_invalid_json_shape_and_duplicate_or_unrequested_symbols(self) -> None:
        cases = (
            (HttpResponse(200, {"Content-Type": "application/json"}, b"{"), "INVALID_JSON"),
            (json_response({"stocks": [valid_metadata()]}), "INVALID_METADATA_SHAPE"),
            (json_response({"result": [{"symbol": "AAPL"}]}), "INVALID_METADATA_SHAPE"),
            (metadata_response([valid_metadata("MSFT")]), "UNEXPECTED_METADATA_SYMBOL"),
            (metadata_response([valid_metadata(), valid_metadata()]), "DUPLICATE_METADATA_SYMBOL"),
            (
                json_response({"result": [valid_metadata()], "unexpected": True}),
                "INVALID_METADATA_SHAPE",
            ),
        )
        for response, code in cases:
            with self.subTest(code=code):
                collector, _ = collector_for([response])
                self.assert_error_code(code, lambda: collector.collect_metadata(("AAPL",)))

    def test_metadata_accepts_only_documented_safe_extras_in_raw_and_projects_them_away(self) -> None:
        record = valid_metadata()
        record.update(
            {
                "listDate": "1980-12-12",
                "delistDate": None,
                "leverageFactor": "1",
                "koreanMarketDetail": "NONE",
            }
        )
        response = metadata_response([record])
        collector, _ = collector_for([response])

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

        self.assertEqual(result.records[0].symbol, "AAPL")
        self.assertFalse(hasattr(result.records[0], "list_date"))
        self.assertFalse(hasattr(result.records[0], "leverage_factor"))
        self.assertEqual(base64.b64decode(result.capture.body_base64), response.body)

    def test_metadata_rejects_every_unregistered_field_and_preserves_raw_capture(self) -> None:
        unregistered_fields: tuple[tuple[str, object], ...] = (
            ("volume", "1"),
            ("turnover", "1"),
            ("returnRate", "0.1"),
            ("open", "1"),
            ("high", "1"),
            ("low", "1"),
            ("close", "1"),
            ("closePrice", "1"),
            ("candle", {}),
            ("ohlcv", []),
            ("label", "future"),
            ("outcome", "future"),
            ("performance", "future"),
            ("marketCap", "1"),
            ("sectorCode", "TECH"),
            ("futureUnknownField", "future"),
        )
        for field_name, field_value in unregistered_fields:
            with self.subTest(field=field_name):
                record = valid_metadata()
                record[field_name] = field_value
                response = metadata_response([record])
                collector, _ = collector_for([response])

                error = self.assert_error_code(
                    "UNREGISTERED_METADATA_FIELD",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

                self.assert_capture_bodies(error, [response.body])

    def test_metadata_requires_the_exact_requested_symbol_set(self) -> None:
        response = metadata_response([valid_metadata("AAPL")])
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "MISSING_METADATA_SYMBOLS",
            lambda: collector.collect_metadata(("AAPL", "MSFT")),
        )
        self.assert_capture_bodies(error, [response.body])
        with self.assertRaises(AttributeError):
            error.captures = ()

    def test_shares_outstanding_requires_nonnegative_integer_lexeme_of_at_most_30_digits(self) -> None:
        invalid_values: tuple[object, ...] = (
            "-1",
            "+1",
            "1.0",
            "1e3",
            "NaN",
            "Infinity",
            "",
            "abc",
            "1" * 31,
        )
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                record = valid_metadata()
                record["sharesOutstanding"] = invalid_value
                collector, _ = collector_for([metadata_response([record])])
                self.assert_error_code(
                    "INVALID_METADATA_SHAPE",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

    def test_shares_outstanding_accepts_zero_and_exact_json_integer_lexemes(self) -> None:
        body = (
            b'{"result":[{"symbol":"AAPL","name":"Apple",'
            b'"englishName":"Apple Inc.","isinCode":"US0378331005",'
            b'"market":"NASDAQ","securityType":"STOCK","isCommonShare":true,'
            b'"status":"ACTIVE","currency":"USD","sharesOutstanding":0}]}'
        )
        collector, _ = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, body)]
        )

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

        self.assertEqual(
            result.records[0].shares_outstanding,
            CanonicalScalar("json_number", "0"),
        )


class SecurityBoundaryContractTest(TossResearchCollectorTestCase):
    def test_raw_capture_repr_redacts_body_headers_url_and_query_values(self) -> None:
        secret = "fake-secret-that-must-not-render"
        cursor = "raw-page-cursor-that-must-not-render"
        capture = RawHttpCapture(
            endpoint_id="fixture",
            method="GET",
            sanitized_url=f"https://example.test/data?page_token={cursor}",
            query=(("page_token", cursor),),
            status=401,
            headers=(("authorization", secret),),
            received_at="2026-07-11T00:00:00Z",
            body_base64=base64.b64encode(secret.encode("utf-8")).decode("ascii"),
            body_sha256=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
        )

        rendered = repr(capture)

        self.assertNotIn(secret, rendered)
        self.assertNotIn(cursor, rendered)
        self.assertNotIn(capture.body_base64, rendered)
        self.assertIn("body=<redacted>", rendered)

    def test_request_repr_capture_and_http_error_never_expose_token_or_provider_body(self) -> None:
        memory_bearer = "never-" + "print-" + "this-" + "memory-" + "bearer"
        private_body = b'{"message":"provider-private-detail"}'
        collector, transport = collector_for(
            [HttpResponse(503, {"Content-Type": "application/json"}, private_body)],
            token_supplier=lambda: memory_bearer,
        )

        error = self.assert_error_code("HTTP_STATUS", lambda: collector.collect_metadata(("AAPL",)))

        request = transport.requests[0]
        rendered = repr(request) + repr(error) + str(error)
        self.assertNotIn(memory_bearer, rendered)
        self.assertNotIn("provider-private-detail", rendered)
        self.assertNotIn("Authorization", repr(request))

    def test_error_traceback_locals_never_retain_bearer_or_authorization_request(self) -> None:
        memory_bearer = "traceback-" + "opaque-" + "memory-" + "value"
        shape_collector, _ = collector_for(
            [metadata_response([])],
            token_supplier=lambda: memory_bearer,
        )
        transport_collector, _ = collector_for(
            [],
            token_supplier=lambda: memory_bearer,
        )
        http_collector, _ = collector_for(
            [HttpResponse(503, {"Content-Type": "text/plain"}, b"benign failure")],
            token_supplier=lambda: memory_bearer,
        )
        sensitive_body = ('{"echo":"' + memory_bearer + '"}').encode("utf-8")
        sensitive_collector, _ = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, sensitive_body)],
            token_supplier=lambda: memory_bearer,
        )
        cases = (
            ("MISSING_METADATA_SYMBOLS", lambda: shape_collector.collect_metadata(("AAPL",))),
            ("TRANSPORT_ERROR", lambda: transport_collector.collect_metadata(("AAPL",))),
            ("HTTP_STATUS", lambda: http_collector.collect_metadata(("AAPL",))),
            ("SENSITIVE_RESPONSE", lambda: sensitive_collector.collect_metadata(("AAPL",))),
        )
        for expected_code, operation in cases:
            with self.subTest(code=expected_code):
                error = self.assert_error_code(expected_code, operation)
                exposed = traceback_exposed_strings(error)

                self.assertNotIn(memory_bearer, exposed)
                self.assertNotIn(f"Bearer {memory_bearer}", exposed)
                self.assertNotIn("Authorization", exposed)

    def test_token_supplier_failure_is_sanitized_outside_the_credential_frame(self) -> None:
        memory_bearer = "supplier-" + "failure-" + "opaque-" + "memory-" + "value"

        def failing_token_supplier() -> str:
            sensitive_context = {
                "Authorization": f"Bearer {memory_bearer}",
            }
            raise RuntimeError(sensitive_context)

        collector, transport = collector_for(
            [],
            token_supplier=failing_token_supplier,
        )

        error = self.assert_error_code(
            "AUTH_TOKEN_UNAVAILABLE",
            lambda: collector.collect_metadata(("AAPL",)),
        )
        exposed = traceback_exposed_strings(error)

        self.assertEqual(transport.requests, [])
        self.assertNotIn(memory_bearer, exposed)
        self.assertNotIn(f"Bearer {memory_bearer}", exposed)
        self.assertNotIn("Authorization", exposed)

    def test_sensitive_response_body_is_rejected_without_reflection(self) -> None:
        sensitive_value = "ts" + "ck_" + "live_" + "response_should_never_publish"
        body = ('{"accessToken":"' + sensitive_value + '"}').encode("utf-8")
        collector, _ = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, body)]
        )

        error = self.assert_error_code("SENSITIVE_RESPONSE", lambda: collector.collect_metadata(("AAPL",)))

        self.assertNotIn(sensitive_value, str(error) + repr(error))

    def test_response_that_echoes_memory_token_is_rejected(self) -> None:
        memory_bearer = "opaque-" + "unit-" + "test-" + "bearer"
        body = ('{"message":"' + memory_bearer + '"}').encode("utf-8")
        collector, _ = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, body)],
            token_supplier=lambda: memory_bearer,
        )

        error = self.assert_error_code("SENSITIVE_RESPONSE", lambda: collector.collect_metadata(("AAPL",)))

        self.assertNotIn(memory_bearer, str(error) + repr(error))

    def test_sensitive_allowlisted_response_header_is_rejected(self) -> None:
        sensitive_value = "ts" + "sk_" + "live_" + "header_should_never_publish"
        collector, _ = collector_for(
            [
                json_response(
                    [valid_metadata()],
                    headers={"Content-Type": "application/json", "ETag": sensitive_value},
                )
            ]
        )

        self.assert_error_code("SENSITIVE_RESPONSE", lambda: collector.collect_metadata(("AAPL",)))

    def test_shared_sensitive_value_policy_rejects_non_toss_credentials(self) -> None:
        sensitive_value = "AK" + "IA" + ("A" * 16)
        body = ('{"note":"' + sensitive_value + '"}').encode("utf-8")
        collector, _ = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, body)]
        )

        error = self.assert_error_code(
            "SENSITIVE_RESPONSE",
            lambda: collector.collect_metadata(("AAPL",)),
        )

        self.assertEqual(getattr(error, "captures", ()), ())
        self.assertNotIn(sensitive_value, str(error) + repr(error))

    def test_decoded_json_recursively_rejects_escaped_credentials_without_current_capture(self) -> None:
        escaped_sensitive_bodies = (
            b'{"result":{"message":"\\u0042earer abcdefghijklmnopqrstuvwxyz"}}',
            b'{"result":{"\\u0041uthorization":"abcdefghijklmnop"}}',
            b'{"result":{"access\\u0054oken":"abcdefghijklmnop"}}',
            b'{"result":{"value":"\\u0074sck_live_abcdefghijklmnop"}}',
            b'{"result":{"value":"\\u0073k-proj-abcdefghijklmnopqrstuvwxyz"}}',
            b'{"result":{"nested":[{"value":"\\u0042earer abcdefghijklmnop"}]}}',
        )
        for body in escaped_sensitive_bodies:
            with self.subTest(body_sha256=hashlib.sha256(body).hexdigest()):
                collector, _ = collector_for(
                    [HttpResponse(200, {"Content-Type": "application/json"}, body)]
                )

                error = self.assert_error_code(
                    "SENSITIVE_RESPONSE",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

                self.assertEqual(getattr(error, "captures", ()), ())

    def test_decoded_json_rejects_exact_escaped_opaque_memory_bearer_in_value_or_key(self) -> None:
        memory_bearer = "opaque-" + "current-" + "memory-" + "value"
        escaped_bearer = json_unicode_escaped(memory_bearer)
        bodies = (
            (f'{{"result":{{"value":"{escaped_bearer}"}}}}').encode("ascii"),
            (f'{{"result":{{"{escaped_bearer}":"benign"}}}}').encode("ascii"),
        )
        for body in bodies:
            with self.subTest(body_sha256=hashlib.sha256(body).hexdigest()):
                self.assertNotIn(memory_bearer.encode("utf-8"), body)
                collector, _ = collector_for(
                    [HttpResponse(200, {"Content-Type": "application/json"}, body)],
                    token_supplier=lambda: memory_bearer,
                )

                error = self.assert_error_code(
                    "SENSITIVE_RESPONSE",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

                self.assertEqual(getattr(error, "captures", ()), ())

    def test_sensitive_preflight_precedes_status_content_type_and_json_validity(self) -> None:
        memory_bearer = "opaque-" + "preflight-" + "memory-" + "value"
        escaped_bearer = json_unicode_escaped(memory_bearer)
        valid_json_body = (f'{{"result":{{"value":"{escaped_bearer}"}}}}').encode("ascii")
        malformed_json_body = (f'{{"broken":"{escaped_bearer}"').encode("ascii")
        registered_value = "ts" + "ck_" + "live_" + "registered_value"
        malformed_registered_body = (
            "broken:" + json_unicode_escaped(registered_value)
        ).encode("ascii")
        responses = (
            HttpResponse(503, {"Content-Type": "application/json"}, valid_json_body),
            HttpResponse(200, {"Content-Type": "text/plain"}, valid_json_body),
            HttpResponse(200, {"Content-Type": "application/json"}, malformed_json_body),
            HttpResponse(
                503,
                {"Content-Type": "text/plain"},
                malformed_registered_body,
            ),
        )
        for response in responses:
            with self.subTest(status=response.status, body_sha256=hashlib.sha256(response.body).hexdigest()):
                collector, _ = collector_for(
                    [response],
                    token_supplier=lambda: memory_bearer,
                )

                error = self.assert_error_code(
                    "SENSITIVE_RESPONSE",
                    lambda: collector.collect_metadata(("AAPL",)),
                )

                self.assertEqual(getattr(error, "captures", ()), ())

    def test_benign_non_json_http_error_with_surrogate_pair_escape_remains_capturable(self) -> None:
        body = b"gateway unavailable \\ud83d\\ude00"
        response = HttpResponse(503, {"Content-Type": "text/plain"}, body)
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "HTTP_STATUS",
            lambda: collector.collect_metadata(("AAPL",)),
        )

        self.assert_capture_bodies(error, [body])

    def test_escaped_sensitive_later_page_keeps_only_prior_safe_capture(self) -> None:
        first_response = candle_response(
            [candle("2026-06-30T00:00:00Z")],
            next_before="cursor-2",
        )
        sensitive_body = (
            b'{"result":{"candles":[],"note":"\\u0042earer abcdefghijklmnop"}}'
        )
        collector, _ = collector_for(
            [
                first_response,
                HttpResponse(200, {"Content-Type": "application/json"}, sensitive_body),
            ]
        )

        error = self.assert_error_code(
            "SENSITIVE_RESPONSE",
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 6, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            ),
        )

        self.assert_capture_bodies(error, [first_response.body])

    def test_escaped_opaque_bearer_on_later_page_keeps_only_prior_safe_capture(self) -> None:
        memory_bearer = "opaque-" + "later-" + "memory-" + "value"
        first_response = candle_response(
            [candle("2026-06-30T00:00:00Z")],
            next_before="cursor-2",
        )
        escaped_bearer = json_unicode_escaped(memory_bearer)
        sensitive_body = (
            f'{{"result":{{"candles":[],"note":"{escaped_bearer}"}}}}'
        ).encode("ascii")
        collector, _ = collector_for(
            [
                first_response,
                HttpResponse(200, {"Content-Type": "application/json"}, sensitive_body),
            ],
            token_supplier=lambda: memory_bearer,
        )

        error = self.assert_error_code(
            "SENSITIVE_RESPONSE",
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 6, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            ),
        )

        self.assert_capture_bodies(error, [first_response.body])

    def test_lone_surrogate_memory_bearer_is_rejected_before_transport(self) -> None:
        collector, transport = collector_for(
            [],
            token_supplier=lambda: "\ud800",
        )

        error = self.assert_error_code(
            "AUTH_TOKEN_INVALID",
            lambda: collector.collect_metadata(("AAPL",)),
        )

        self.assertEqual(transport.requests, [])
        self.assertNotIn("\ud800", str(error) + repr(error))

    def test_benign_decoded_korean_metadata_remains_publishable_with_exact_raw(self) -> None:
        record = valid_metadata()
        record["name"] = "애플"
        record["koreanMarketDetail"] = "미국 나스닥"
        response = metadata_response([record])
        collector, _ = collector_for([response])

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

        self.assertEqual(result.records[0].name, "애플")
        self.assertEqual(base64.b64decode(result.capture.body_base64), response.body)

    def test_benign_unicode_escaped_korean_slash_and_backslash_preserve_exact_raw(self) -> None:
        record = valid_metadata()
        record["name"] = "애플 / 테스트"
        record["koreanMarketDetail"] = "경로 / 역슬래시 \\"
        body = json.dumps(
            {"result": [record]},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        self.assertIn(b"\\u", body)
        response = HttpResponse(200, {"Content-Type": "application/json"}, body)
        collector, _ = collector_for([response])

        result = self.collect(lambda: collector.collect_metadata(("AAPL",)))

        self.assertEqual(result.records[0].name, "애플 / 테스트")
        self.assertEqual(base64.b64decode(result.capture.body_base64), body)

    def test_decoded_json_lone_surrogate_key_or_value_is_captured_as_invalid_json(self) -> None:
        records: list[dict[str, object]] = []

        name_record = valid_metadata()
        name_record["name"] = "\ud800"
        records.append(name_record)

        safe_extra_record = valid_metadata()
        safe_extra_record["listDate"] = "\ud800"
        records.append(safe_extra_record)

        surrogate_key_record = valid_metadata()
        surrogate_key_record["\ud800"] = "benign"
        records.append(surrogate_key_record)

        for record in records:
            body = json.dumps(
                {"result": [record]},
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
            response = HttpResponse(200, {"Content-Type": "application/json"}, body)
            collector, _ = collector_for([response])

            error = self.assert_error_code(
                "INVALID_JSON",
                lambda: collector.collect_metadata(("AAPL",)),
            )

            self.assert_capture_bodies(error, [body])


class CandleCollectionContractTest(TossResearchCollectorTestCase):
    def test_candles_use_exact_allowed_daily_query_and_preserve_scalar_lexemes(self) -> None:
        body = (
            b'{"result":{"candles":[{"timestamp":"2026-06-30T00:00:00Z",'
            b'"openPrice":123.00,"highPrice":125.00,"lowPrice":"119.00",'
            b'"closePrice":124,"volume":"00123456","currency":"USD"}]}}'
        )
        collector, transport = collector_for(
            [HttpResponse(200, {"Content-Type": "application/json"}, body)]
        )

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 6, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            )
        )

        self.assertEqual(
            transport.requests[0].url,
            "https://openapi.tossinvest.com/api/v1/candles?"
            "symbol=AAPL&interval=1d&count=200&adjusted=true&"
            "before=2026-07-01T00%3A00%3A00Z",
        )
        self.assertEqual(result.analysis_rows[0].open_price, CanonicalScalar("json_number", "123.00"))
        self.assertEqual(result.analysis_rows[0].high_price, CanonicalScalar("json_number", "125.00"))
        self.assertEqual(result.analysis_rows[0].low_price, CanonicalScalar("json_string", "119.00"))
        self.assertEqual(result.analysis_rows[0].volume, CanonicalScalar("json_string", "00123456"))
        self.assertEqual(base64.b64decode(result.captures[0].body_base64), body)
        self.assertEqual(getattr(result, "session_timezone", None), "America/New_York")
        self.assertEqual(
            getattr(result, "provider_session_membership", None),
            "not_documented",
        )

    def test_candle_page_accepts_exactly_200_rows(self) -> None:
        newest = datetime(2026, 6, 30, 16, 0, tzinfo=timezone.utc)
        rows = [
            candle(
                (newest - timedelta(days=index)).isoformat().replace("+00:00", "Z"),
                close_price=str(1000 - index),
            )
            for index in range(200)
        ]
        collector, _ = collector_for([candle_response(rows)])

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL",
                date(2025, 1, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            )
        )

        self.assertEqual(len(result.analysis_rows), 200)

    def test_candle_page_rejects_more_than_200_rows_with_raw_capture(self) -> None:
        newest = datetime(2026, 6, 30, 16, 0, tzinfo=timezone.utc)
        rows = [
            candle(
                (newest - timedelta(days=index)).isoformat().replace("+00:00", "Z"),
                close_price=str(1000 - index),
            )
            for index in range(201)
        ]
        response = candle_response(rows)
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "INVALID_CANDLE_SHAPE",
            lambda: collector.collect_candles(
                "AAPL",
                date(2025, 1, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            ),
        )

        self.assert_capture_bodies(error, [response.body])

    def test_ohlc_requires_finite_strictly_positive_unsigned_decimal_lexemes(self) -> None:
        invalid_values: tuple[object, ...] = (
            "0",
            "0.0",
            "-1",
            "+1",
            "1e3",
            "NaN",
            "Infinity",
            "",
            "abc",
        )
        for field_name in ("openPrice", "highPrice", "lowPrice", "closePrice"):
            for invalid_value in invalid_values:
                with self.subTest(field=field_name, value=invalid_value):
                    row = candle("2026-06-30T00:00:00Z")
                    row[field_name] = invalid_value
                    collector, _ = collector_for([candle_response([row])])
                    self.assert_error_code(
                        "INVALID_CANDLE_SHAPE",
                        lambda: collector.collect_candles(
                            "AAPL",
                            date(2026, 6, 1),
                            date(2026, 6, 30),
                            INITIAL_BEFORE,
                            True,
                        ),
                    )

    def test_volume_requires_nonnegative_unsigned_integer_lexeme(self) -> None:
        for invalid_value in ("-1", "+1", "1.0", "1e3", "NaN", "Infinity", "", "abc"):
            with self.subTest(value=invalid_value):
                row = candle("2026-06-30T00:00:00Z")
                row["volume"] = invalid_value
                collector, _ = collector_for([candle_response([row])])
                self.assert_error_code(
                    "INVALID_CANDLE_SHAPE",
                    lambda: collector.collect_candles(
                        "AAPL",
                        date(2026, 6, 1),
                        date(2026, 6, 30),
                        INITIAL_BEFORE,
                        True,
                    ),
                )

    def test_nonfinite_and_exponent_json_number_lexemes_are_rejected(self) -> None:
        invalid_bodies = (
            b'{"result":{"candles":[{"timestamp":"2026-06-30T00:00:00Z",'
            b'"openPrice":1e3,"highPrice":"105","lowPrice":"99",'
            b'"closePrice":"103","volume":"1","currency":"USD"}]}}',
            b'{"result":{"candles":[{"timestamp":"2026-06-30T00:00:00Z",'
            b'"openPrice":NaN,"highPrice":"105","lowPrice":"99",'
            b'"closePrice":"103","volume":"1","currency":"USD"}]}}',
        )
        expected_codes = ("INVALID_CANDLE_SHAPE", "INVALID_JSON")
        for body, expected_code in zip(invalid_bodies, expected_codes, strict=True):
            with self.subTest(code=expected_code):
                collector, _ = collector_for(
                    [HttpResponse(200, {"Content-Type": "application/json"}, body)]
                )
                self.assert_error_code(
                    expected_code,
                    lambda: collector.collect_candles(
                        "AAPL",
                        date(2026, 6, 1),
                        date(2026, 6, 30),
                        INITIAL_BEFORE,
                        True,
                    ),
                )

    def test_pagination_treats_cursor_as_opaque_and_deduplicates_identical_overlap(self) -> None:
        overlap = candle("2026-06-29T16:00:00Z", close_price="102")
        collector, transport = collector_for(
            [
                candle_response(
                    [candle("2026-06-30T16:00:00Z"), overlap],
                    next_before="opaque/+== cursor",
                ),
                candle_response([overlap, candle("2026-06-28T16:00:00Z", close_price="101")]),
            ]
        )

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 28), date(2026, 6, 30), INITIAL_BEFORE, False
            )
        )

        self.assertEqual(
            [row.timestamp for row in result.analysis_rows],
            [
                "2026-06-28T16:00:00Z",
                "2026-06-29T16:00:00Z",
                "2026-06-30T16:00:00Z",
            ],
        )
        second_query = parse_qs(urlsplit(transport.requests[1].url).query)
        self.assertEqual(second_query["before"], ["opaque/+== cursor"])
        self.assertEqual(second_query["adjusted"], ["false"])

    def test_conflicting_duplicate_timestamp_is_invalid(self) -> None:
        first_response = candle_response(
            [candle("2026-06-30T00:00:00Z", close_price="103")],
            next_before="cursor-2",
        )
        second_response = candle_response(
            [candle("2026-06-30T00:00:00Z", close_price="999")]
        )
        collector, _ = collector_for(
            [first_response, second_response]
        )

        error = self.assert_error_code(
            "CONFLICTING_DUPLICATE",
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True
            ),
        )
        self.assert_capture_bodies(error, [first_response.body, second_response.body])

    def test_different_raw_timestamps_for_same_utc_instant_are_conflicting_duplicates(self) -> None:
        response = candle_response(
            [
                candle("2026-06-30T16:00:00Z"),
                candle("2026-06-30T12:00:00-04:00"),
            ]
        )
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "CONFLICTING_DUPLICATE",
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 6, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            ),
        )

        self.assert_capture_bodies(error, [response.body])

    def test_distinct_instants_in_same_new_york_session_are_conflicting_duplicates(self) -> None:
        response = candle_response(
            [
                candle("2026-06-30T16:00:00Z"),
                candle("2026-06-30T14:00:00Z"),
            ]
        )
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "CONFLICTING_DUPLICATE",
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 6, 1),
                date(2026, 6, 30),
                INITIAL_BEFORE,
                True,
            ),
        )

        self.assert_capture_bodies(error, [response.body])

    def test_repeated_cursor_is_invalid(self) -> None:
        response = candle_response(
            [candle("2026-06-30T00:00:00Z")],
            next_before=INITIAL_BEFORE,
        )
        collector, _ = collector_for([response])

        error = self.assert_error_code(
            "REPEATED_CURSOR",
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True
            ),
        )
        self.assert_capture_bodies(error, [response.body])

    def test_page_with_no_new_unique_row_is_invalid(self) -> None:
        only_row = candle("2026-06-30T00:00:00Z")
        first_response = candle_response([only_row], next_before="cursor-2")
        second_response = candle_response([only_row], next_before="cursor-3")
        collector, _ = collector_for([first_response, second_response])

        error = self.assert_error_code(
            "NO_PAGINATION_PROGRESS",
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True
            ),
        )
        self.assert_capture_bodies(error, [first_response.body, second_response.body])

    def test_fixed_page_limit_rejects_unbounded_provider_cursor_chain(self) -> None:
        responses: list[HttpResponse] = []
        for page_index in range(20):
            day = 30 - page_index
            responses.append(
                candle_response(
                    [candle(f"2026-06-{day:02d}T00:00:00Z", close_price=str(200 - page_index))],
                    next_before=f"cursor-{page_index + 1}",
                )
            )
        collector, transport = collector_for(responses)

        error = self.assert_error_code(
            "PAGE_LIMIT_EXCEEDED",
            lambda: collector.collect_candles(
                "AAPL", date(2020, 1, 1), date(2026, 6, 30), INITIAL_BEFORE, True
            ),
        )
        self.assertEqual(len(transport.requests), 20)
        self.assert_capture_bodies(error, [response.body for response in responses])

    def test_later_page_json_shape_and_http_failures_preserve_every_received_raw_body(self) -> None:
        later_failures = (
            (
                HttpResponse(200, {"Content-Type": "application/json"}, b"not-json"),
                "INVALID_JSON",
            ),
            (json_response({"result": {"wrong": []}}), "INVALID_CANDLE_SHAPE"),
            (
                HttpResponse(
                    503,
                    {"Content-Type": "application/json"},
                    b'{"message":"temporarily unavailable"}',
                ),
                "HTTP_STATUS",
            ),
        )
        for second_response, expected_code in later_failures:
            with self.subTest(code=expected_code):
                first_response = candle_response(
                    [candle("2026-06-30T00:00:00Z")],
                    next_before="cursor-2",
                )
                collector, _ = collector_for([first_response, second_response])

                error = self.assert_error_code(
                    expected_code,
                    lambda: collector.collect_candles(
                        "AAPL",
                        date(2026, 6, 1),
                        date(2026, 6, 30),
                        INITIAL_BEFORE,
                        True,
                    ),
                )

                self.assert_capture_bodies(error, [first_response.body, second_response.body])

    def test_lone_surrogate_next_cursor_is_captured_as_invalid_json_with_prior_lineage(self) -> None:
        first_response = candle_response(
            [candle("2026-06-30T00:00:00Z")],
            next_before="cursor-2",
        )
        second_value = {
            "result": {
                "candles": [candle("2026-06-29T00:00:00Z")],
                "nextBefore": "\ud800",
            }
        }
        second_response = HttpResponse(
            200,
            {"Content-Type": "application/json"},
            json.dumps(second_value, ensure_ascii=True, separators=(",", ":")).encode("ascii"),
        )
        collector, _ = collector_for([first_response, second_response])

        try:
            error = self.assert_error_code(
                "INVALID_JSON",
                lambda: collector.collect_candles(
                    "AAPL",
                    date(2026, 6, 1),
                    date(2026, 6, 30),
                    INITIAL_BEFORE,
                    True,
                ),
            )
        except UnicodeError as unexpected_error:
            self.fail(
                "cursor validation leaked a raw Unicode boundary error: "
                f"{type(unexpected_error).__name__}"
            )

        self.assert_capture_bodies(error, [first_response.body, second_response.body])

    def test_requested_range_and_audit_only_rows_are_strictly_separated(self) -> None:
        collector, transport = collector_for(
            [
                candle_response(
                    [
                        candle("2026-07-01T16:00:00Z"),
                        candle("2026-06-30T16:00:00Z"),
                        candle("2026-06-01T16:00:00Z"),
                    ],
                    next_before="unused-older-cursor",
                )
            ]
        )

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 15), date(2026, 6, 30), INITIAL_BEFORE, True
            )
        )

        self.assertEqual([row.timestamp for row in result.analysis_rows], ["2026-06-30T16:00:00Z"])
        self.assertEqual(
            [row.timestamp for row in result.audit_only_rows],
            ["2026-06-01T16:00:00Z", "2026-07-01T16:00:00Z"],
        )
        self.assertEqual(len(transport.requests), 1)

    def test_session_date_uses_new_york_dst_boundary_from_timestamp_instant(self) -> None:
        collector, _ = collector_for(
            [
                candle_response(
                    [
                        candle("2026-03-08T07:30:00Z"),
                        candle("2026-03-08T04:30:00Z"),
                    ]
                )
            ]
        )

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 3, 7),
                date(2026, 3, 7),
                "2026-03-09T00:00:00Z",
                True,
            )
        )

        self.assertEqual(
            [row.timestamp for row in result.analysis_rows],
            ["2026-03-08T04:30:00Z"],
        )
        self.assertEqual(
            [row.timestamp for row in result.audit_only_rows],
            ["2026-03-08T07:30:00Z"],
        )

    def test_session_date_converts_non_new_york_offset_and_preserves_raw_timestamp(self) -> None:
        raw_timestamp = "2026-06-30T23:30:00-07:00"
        collector, _ = collector_for([candle_response([candle(raw_timestamp)])])

        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL",
                date(2026, 7, 1),
                date(2026, 7, 1),
                "2026-07-02T00:00:00Z",
                True,
            )
        )

        self.assertEqual([row.timestamp for row in result.analysis_rows], [raw_timestamp])

    def test_page_order_must_move_from_newer_to_older_before_start_cutoff(self) -> None:
        collector, _ = collector_for(
            [
                candle_response(
                    [
                        candle("2026-06-01T00:00:00Z"),
                        candle("2026-06-30T00:00:00Z"),
                    ],
                    next_before="cursor-that-must-not-be-silently-skipped",
                )
            ]
        )

        self.assert_error_code(
            "PAGE_ORDER_INVALID",
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 15), date(2026, 6, 30), INITIAL_BEFORE, True
            ),
        )

    def test_cursor_pages_cannot_move_forward_in_time(self) -> None:
        collector, _ = collector_for(
            [
                candle_response(
                    [
                        candle("2026-06-30T00:00:00Z"),
                        candle("2026-06-29T00:00:00Z"),
                    ],
                    next_before="cursor-2",
                ),
                candle_response([candle("2026-07-01T00:00:00Z")]),
            ]
        )

        self.assert_error_code(
            "PAGE_ORDER_INVALID",
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 1), date(2026, 7, 1), INITIAL_BEFORE, True
            ),
        )

    def test_invalid_candle_json_shape_required_fields_and_timestamp_are_rejected(self) -> None:
        invalid_rows = candle("2026-06-30T00:00:00Z")
        del invalid_rows["volume"]
        cases = (
            (HttpResponse(200, {"Content-Type": "application/json"}, b"not-json"), "INVALID_JSON"),
            (json_response([]), "INVALID_CANDLE_SHAPE"),
            (json_response({"result": {"candles": "wrong"}}), "INVALID_CANDLE_SHAPE"),
            (
                json_response({"result": {"candles": []}, "unexpected": True}),
                "INVALID_CANDLE_SHAPE",
            ),
            (
                json_response({"result": {"candles": [], "unexpected": True}}),
                "INVALID_CANDLE_SHAPE",
            ),
            (candle_response([invalid_rows]), "INVALID_CANDLE_SHAPE"),
            (candle_response([candle("not-a-timestamp")]), "INVALID_TIMESTAMP"),
        )
        for response, code in cases:
            with self.subTest(code=code):
                collector, _ = collector_for([response])
                self.assert_error_code(
                    code,
                    lambda: collector.collect_candles(
                        "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True
                    ),
                )

    def test_extreme_timestamp_offsets_are_captured_as_invalid_timestamp(self) -> None:
        extreme_timestamps = (
            "0001-01-01T00:00:00+14:00",
            "9999-12-31T23:59:59-14:00",
        )
        for timestamp in extreme_timestamps:
            with self.subTest(timestamp=timestamp):
                response = candle_response([candle(timestamp)])
                collector, _ = collector_for([response])

                error = self.assert_error_code(
                    "INVALID_TIMESTAMP",
                    lambda: collector.collect_candles(
                        "AAPL",
                        date(2026, 6, 1),
                        date(2026, 6, 30),
                        INITIAL_BEFORE,
                        True,
                    ),
                )

                self.assert_capture_bodies(error, [response.body])

    def test_extreme_initial_before_is_invalid_before_token_or_transport(self) -> None:
        extreme_before_values = (
            "0001-01-01T00:00:00+14:00",
            "9999-12-31T23:59:59-14:00",
        )
        for before in extreme_before_values:
            with self.subTest(before=before):
                collector, transport = collector_for([])

                self.assert_error_code(
                    "INVALID_INPUT",
                    lambda: collector.collect_candles(
                        "AAPL",
                        date(2026, 6, 1),
                        date(2026, 6, 30),
                        before,
                        True,
                    ),
                )

                self.assertEqual(transport.requests, [])

    def test_invalid_candle_inputs_are_rejected_before_token_or_transport(self) -> None:
        invalid_arguments = (
            ("aapl", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True),
            ("\ud800", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True),
            ("AAPL", date(2026, 7, 1), date(2026, 6, 30), INITIAL_BEFORE, True),
            ("AAPL", "2026-06-01", date(2026, 6, 30), INITIAL_BEFORE, True),
            ("AAPL", date(2026, 6, 1), date(2026, 6, 30), "", True),
            ("AAPL", date(2026, 6, 1), date(2026, 6, 30), "\ud800", True),
            ("AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, 1),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                collector, transport = collector_for([])
                self.assert_error_code(
                    "INVALID_INPUT",
                    lambda arguments=arguments: collector.collect_candles(*arguments),
                )
                self.assertEqual(transport.requests, [])


class AdjustedNativeCombinationContractTest(TossResearchCollectorTestCase):
    def test_adjusted_and_native_requested_rows_are_combined_on_exact_timestamp_currency_key(self) -> None:
        timestamp = "2026-06-30T00:00:00Z"
        collector, transport = collector_for(
            [
                candle_response([candle(timestamp, close_price="101")]),
                candle_response([candle(timestamp, close_price="100")]),
            ]
        )

        result = self.collect(
            lambda: collector.collect_adjusted_native(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE
            )
        )

        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].timestamp, timestamp)
        self.assertEqual(result.rows[0].adjusted.close_price.text, "101")
        self.assertEqual(result.rows[0].native.close_price.text, "100")
        self.assertEqual(getattr(result, "session_timezone", None), "America/New_York")
        self.assertEqual(
            getattr(result, "provider_session_membership", None),
            "not_documented",
        )
        self.assertEqual(
            [parse_qs(urlsplit(request.url).query)["adjusted"] for request in transport.requests],
            [["true"], ["false"]],
        )

    def test_adjusted_native_timestamp_set_mismatch_is_invalid_without_imputation(self) -> None:
        adjusted_response = candle_response([candle("2026-06-30T00:00:00Z")])
        native_response = candle_response([candle("2026-06-29T00:00:00Z")])
        collector, _ = collector_for([adjusted_response, native_response])

        error = self.assert_error_code(
            "ADJUSTED_NATIVE_KEY_MISMATCH",
            lambda: collector.collect_adjusted_native(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE
            ),
        )
        self.assert_capture_bodies(error, [adjusted_response.body, native_response.body])

    def test_adjusted_native_currency_set_mismatch_is_invalid_without_reweighting(self) -> None:
        timestamp = "2026-06-30T00:00:00Z"
        collector, _ = collector_for(
            [
                candle_response([candle(timestamp, currency="USD")]),
                candle_response([candle(timestamp, currency="KRW")]),
            ]
        )

        self.assert_error_code(
            "ADJUSTED_NATIVE_KEY_MISMATCH",
            lambda: collector.collect_adjusted_native(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE
            ),
        )

    def test_native_failure_preserves_adjusted_and_native_raw_captures(self) -> None:
        adjusted_response = candle_response([candle("2026-06-30T00:00:00Z")])
        native_response = HttpResponse(
            200,
            {"Content-Type": "application/json"},
            b"not-json",
        )
        collector, _ = collector_for([adjusted_response, native_response])

        error = self.assert_error_code(
            "INVALID_JSON",
            lambda: collector.collect_adjusted_native(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE
            ),
        )

        self.assert_capture_bodies(error, [adjusted_response.body, native_response.body])

    def test_sensitive_native_failure_preserves_only_publishable_adjusted_capture(self) -> None:
        adjusted_response = candle_response([candle("2026-06-30T00:00:00Z")])
        memory_bearer = "private-" + "memory-" + "bearer"
        sensitive_native_response = HttpResponse(
            200,
            {"Content-Type": "application/json"},
            ('{"message":"' + memory_bearer + '"}').encode("utf-8"),
        )
        collector, _ = collector_for(
            [adjusted_response, sensitive_native_response],
            token_supplier=lambda: memory_bearer,
        )

        error = self.assert_error_code(
            "SENSITIVE_RESPONSE",
            lambda: collector.collect_adjusted_native(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE
            ),
        )

        self.assert_capture_bodies(error, [adjusted_response.body])


class ImmutableBoundaryContractTest(TossResearchCollectorTestCase):
    def test_returned_boundary_dataclasses_are_frozen(self) -> None:
        scalar = CanonicalScalar("json_string", "1")
        row = candle("2026-06-30T00:00:00Z")
        collector, _ = collector_for([candle_response([row])])
        result = self.collect(
            lambda: collector.collect_candles(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), INITIAL_BEFORE, True
            )
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            scalar.text = "2"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.symbol = "MSFT"


if __name__ == "__main__":
    unittest.main()
