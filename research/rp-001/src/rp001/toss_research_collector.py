"""Research-only, read-only Toss market-data collection boundary."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Callable, Mapping, NoReturn, Sequence
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from rp001.sensitive_value_policy import find_sensitive_values

__all__ = [
    "CandleCollection",
    "CandleRow",
    "CanonicalScalar",
    "CollectorError",
    "CombinedCandleCollection",
    "HttpRequest",
    "HttpResponse",
    "MetadataCollection",
    "PairedCandleRow",
    "RawHttpCapture",
    "StockMetadata",
    "TossResearchCollector",
]

_STOCKS_ENDPOINT_ID = "stocks_metadata_v1"
_CANDLES_ENDPOINT_ID = "daily_candles_v1"
_ENDPOINT_URLS = MappingProxyType(
    {
        _STOCKS_ENDPOINT_ID: "https://openapi.tossinvest.com/api/v1/stocks",
        _CANDLES_ENDPOINT_ID: "https://openapi.tossinvest.com/api/v1/candles",
    }
)
_MAX_METADATA_SYMBOLS = 200
_MAX_CANDLE_ROWS_PER_PAGE = 200
_CANDLE_PAGE_LIMIT = 20
_SESSION_TIMEZONE_NAME = "America/New_York"
_SESSION_TIMEZONE = ZoneInfo(_SESSION_TIMEZONE_NAME)
_PROVIDER_SESSION_MEMBERSHIP = "not_documented"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.^-]{0,19}$")
_UNSIGNED_DECIMAL_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_UNSIGNED_INTEGER_PATTERN = re.compile(r"^[0-9]+$")
_JSON_CONTENT_TYPE_PATTERN = re.compile(
    r'^[ \t]*application/json[ \t]*(?:;[ \t]*charset[ \t]*=[ \t]*(?:"utf-8"|utf-8)[ \t]*)?$',
    re.IGNORECASE,
)
_ALLOWED_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "etag",
        "last-modified",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_METADATA_FIELDS = frozenset(
    {
        "symbol",
        "name",
        "englishName",
        "isinCode",
        "market",
        "securityType",
        "isCommonShare",
        "status",
        "currency",
        "sharesOutstanding",
    }
)
_DOCUMENTED_SAFE_METADATA_EXTRA_FIELDS = frozenset(
    {
        "listDate",
        "delistDate",
        "leverageFactor",
        "koreanMarketDetail",
    }
)
_CANDLE_FIELDS = frozenset(
    {
        "timestamp",
        "openPrice",
        "highPrice",
        "lowPrice",
        "closePrice",
        "volume",
        "currency",
    }
)


class CollectorError(ValueError):
    """A sanitized collector failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        capture: RawHttpCapture | None = None,
        *,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self._captures = captures + (() if capture is None else (capture,))
        super().__init__(f"{code}: market-data collection failed")

    @property
    def captures(self) -> tuple[RawHttpCapture, ...]:
        return self._captures

    @property
    def capture(self) -> RawHttpCapture | None:
        return self.captures[-1] if self.captures else None

    def with_prior_captures(
        self,
        prior_captures: tuple[RawHttpCapture, ...],
    ) -> CollectorError:
        combined: list[RawHttpCapture] = []
        seen_object_ids: set[int] = set()
        for capture in prior_captures + self.captures:
            if id(capture) in seen_object_ids:
                continue
            seen_object_ids.add(id(capture))
            combined.append(capture)
        return CollectorError(self.code, captures=tuple(combined))


@dataclass(frozen=True, repr=False)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return f"HttpRequest(method={self.method!r}, url={self.url!r}, headers=<redacted>)"


@dataclass(frozen=True, repr=False)
class HttpResponse:
    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)

    def __repr__(self) -> str:
        body_size = len(self.body) if isinstance(self.body, bytes) else "invalid"
        return f"HttpResponse(status={self.status!r}, headers=<redacted>, body=<{body_size} bytes>)"


@dataclass(frozen=True, repr=False)
class RawHttpCapture:
    endpoint_id: str
    method: str
    sanitized_url: str
    query: tuple[tuple[str, str], ...]
    status: int
    headers: tuple[tuple[str, str], ...]
    received_at: str
    body_base64: str
    body_sha256: str

    def __repr__(self) -> str:
        return (
            "RawHttpCapture("
            f"endpoint_id={self.endpoint_id!r}, "
            f"method={self.method!r}, "
            "sanitized_url=<redacted>, "
            "query=<redacted>, "
            f"status={self.status!r}, "
            "headers=<redacted>, "
            f"received_at={self.received_at!r}, "
            "body=<redacted>, "
            f"body_sha256={self.body_sha256!r})"
        )


@dataclass(frozen=True)
class CanonicalScalar:
    """Lossless processed scalar: JSON token kind plus its original lexeme."""

    kind: str
    text: str


@dataclass(frozen=True)
class StockMetadata:
    symbol: str
    name: str
    english_name: str
    isin_code: str
    market: str
    security_type: str
    is_common_share: bool
    status: str
    currency: str
    shares_outstanding: CanonicalScalar


@dataclass(frozen=True)
class MetadataCollection:
    records: tuple[StockMetadata, ...]
    capture: RawHttpCapture


@dataclass(frozen=True)
class CandleRow:
    timestamp: str
    open_price: CanonicalScalar
    high_price: CanonicalScalar
    low_price: CanonicalScalar
    close_price: CanonicalScalar
    volume: CanonicalScalar
    currency: str


@dataclass(frozen=True)
class CandleCollection:
    symbol: str
    adjusted: bool
    start: date
    end: date
    session_timezone: str
    provider_session_membership: str
    analysis_rows: tuple[CandleRow, ...]
    audit_only_rows: tuple[CandleRow, ...]
    captures: tuple[RawHttpCapture, ...]


@dataclass(frozen=True)
class PairedCandleRow:
    timestamp: str
    currency: str
    adjusted: CandleRow
    native: CandleRow


@dataclass(frozen=True)
class CombinedCandleCollection:
    symbol: str
    session_timezone: str
    provider_session_membership: str
    rows: tuple[PairedCandleRow, ...]
    adjusted_collection: CandleCollection
    native_collection: CandleCollection


Transport = Callable[[HttpRequest], HttpResponse]
TokenSupplier = Callable[[], str]
Clock = Callable[[], datetime]


class _JsonNumber(str):
    """Marks an exact JSON numeric lexeme without converting it to binary float."""


class _InvalidJson(ValueError):
    pass


@dataclass(frozen=True)
class _ReceivedJson:
    capture: RawHttpCapture
    value: object


@dataclass(frozen=True)
class _SanitizedHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True)
class _CredentialBoundaryResult:
    error_code: str | None
    response: _SanitizedHttpResponse | None


@dataclass(frozen=True)
class _ParsedCandlePage:
    rows: tuple[CandleRow, ...]
    timestamps: tuple[datetime, ...]
    next_before: str | None


class _PreflightObjectPairs(tuple[tuple[str, object], ...]):
    """Retains every decoded JSON key/value pair for credential preflight."""


class TossResearchCollector:
    """Collects only stock metadata and daily candle research inputs."""

    def __init__(
        self,
        transport: Transport,
        token_supplier: TokenSupplier,
        clock: Clock,
    ) -> None:
        if not callable(transport) or not callable(token_supplier) or not callable(clock):
            raise CollectorError("INVALID_INPUT")
        self._transport = transport
        self._token_supplier = token_supplier
        self._clock = clock

    def collect_metadata(self, symbols: Sequence[str]) -> MetadataCollection:
        validated_symbols = _validate_symbols(symbols)
        query = (("symbols", ",".join(validated_symbols)),)
        received = self._receive_json(_STOCKS_ENDPOINT_ID, query)
        records = _parse_metadata(received.value, frozenset(validated_symbols), received.capture)
        return MetadataCollection(records=records, capture=received.capture)

    def collect_candles(
        self,
        symbol: str,
        start: date,
        end: date,
        before: str,
        adjusted: bool,
    ) -> CandleCollection:
        _validate_candle_request(symbol, start, end, before, adjusted)
        rows_by_timestamp: dict[str, CandleRow] = {}
        timestamps_by_text: dict[str, datetime] = {}
        timestamp_text_by_instant: dict[datetime, str] = {}
        timestamp_text_by_session: dict[date, str] = {}
        captures: list[RawHttpCapture] = []
        seen_cursors = {before}
        cursor = before
        previous_page_oldest: datetime | None = None

        for page_number in range(1, _CANDLE_PAGE_LIMIT + 1):
            try:
                received = self._receive_candle_page(symbol, adjusted, cursor)
                page = _parse_candle_page(received.value, received.capture)
                previous_page_oldest = _validate_page_order(
                    page,
                    previous_page_oldest,
                    received.capture,
                )
                captures.append(received.capture)
                new_row_count = _merge_candle_page(
                    page,
                    rows_by_timestamp,
                    timestamps_by_text,
                    timestamp_text_by_instant,
                    timestamp_text_by_session,
                    received.capture,
                )
                if new_row_count == 0:
                    raise CollectorError("NO_PAGINATION_PROGRESS", received.capture)

                next_before = page.next_before
                if next_before is not None and next_before in seen_cursors:
                    raise CollectorError("REPEATED_CURSOR", received.capture)

                crossed_requested_start = any(
                    _session_date(timestamp) < start for timestamp in page.timestamps
                )
                if next_before is None or crossed_requested_start:
                    break
                if page_number == _CANDLE_PAGE_LIMIT:
                    raise CollectorError("PAGE_LIMIT_EXCEEDED", received.capture)

                seen_cursors.add(next_before)
                cursor = next_before
            except CollectorError as error:
                raise error.with_prior_captures(tuple(captures)) from None

        ordered_rows = tuple(
            rows_by_timestamp[timestamp_text]
            for timestamp_text in sorted(
                rows_by_timestamp,
                key=lambda value: (timestamps_by_text[value], value),
            )
        )
        analysis_rows, audit_only_rows = _partition_by_requested_range(
            ordered_rows,
            timestamps_by_text,
            start,
            end,
        )
        return CandleCollection(
            symbol=symbol,
            adjusted=adjusted,
            start=start,
            end=end,
            session_timezone=_SESSION_TIMEZONE_NAME,
            provider_session_membership=_PROVIDER_SESSION_MEMBERSHIP,
            analysis_rows=analysis_rows,
            audit_only_rows=audit_only_rows,
            captures=tuple(captures),
        )

    def collect_adjusted_native(
        self,
        symbol: str,
        start: date,
        end: date,
        before: str,
    ) -> CombinedCandleCollection:
        adjusted_collection = self.collect_candles(symbol, start, end, before, True)
        try:
            native_collection = self.collect_candles(symbol, start, end, before, False)
        except CollectorError as error:
            raise error.with_prior_captures(adjusted_collection.captures) from None
        adjusted_by_key = {
            (row.timestamp, row.currency): row for row in adjusted_collection.analysis_rows
        }
        native_by_key = {(row.timestamp, row.currency): row for row in native_collection.analysis_rows}
        if adjusted_by_key.keys() != native_by_key.keys():
            raise CollectorError(
                "ADJUSTED_NATIVE_KEY_MISMATCH",
                captures=adjusted_collection.captures + native_collection.captures,
            )

        paired_rows = tuple(
            PairedCandleRow(
                timestamp=timestamp,
                currency=currency,
                adjusted=adjusted_by_key[(timestamp, currency)],
                native=native_by_key[(timestamp, currency)],
            )
            for timestamp, currency in sorted(
                adjusted_by_key,
                key=lambda key: (_parse_timestamp(key[0]), key[0], key[1]),
            )
        )
        return CombinedCandleCollection(
            symbol=symbol,
            session_timezone=_SESSION_TIMEZONE_NAME,
            provider_session_membership=_PROVIDER_SESSION_MEMBERSHIP,
            rows=paired_rows,
            adjusted_collection=adjusted_collection,
            native_collection=native_collection,
        )

    def _receive_candle_page(
        self,
        symbol: str,
        adjusted: bool,
        before: str,
    ) -> _ReceivedJson:
        query = (
            ("symbol", symbol),
            ("interval", "1d"),
            ("count", "200"),
            ("adjusted", "true" if adjusted else "false"),
            ("before", before),
        )
        return self._receive_json(_CANDLES_ENDPOINT_ID, query)

    def _receive_json(
        self,
        endpoint_id: str,
        query: tuple[tuple[str, str], ...],
    ) -> _ReceivedJson:
        endpoint_url = _ENDPOINT_URLS.get(endpoint_id)
        if endpoint_url is None:
            raise CollectorError("ENDPOINT_NOT_ALLOWED")
        url = f"{endpoint_url}?{urlencode(query)}"
        boundary_result = _send_allowed_get_no_raise(
            self._transport,
            self._token_supplier,
            url,
        )
        if boundary_result.error_code is not None:
            raise CollectorError(boundary_result.error_code)
        response = boundary_result.response
        if response is None:
            raise CollectorError("INVALID_HTTP_RESPONSE")
        capture = _make_capture(
            endpoint_id,
            url,
            query,
            response,
            self._clock,
        )
        if response.status < 200 or response.status >= 300:
            raise CollectorError("HTTP_STATUS", capture)
        content_type = dict(response.headers).get("content-type", "")
        if _JSON_CONTENT_TYPE_PATTERN.fullmatch(content_type) is None:
            raise CollectorError("INVALID_CONTENT_TYPE", capture)
        value = _parse_json(response.body, capture)
        return _ReceivedJson(capture=capture, value=value)


def _validate_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise CollectorError("INVALID_INPUT")
    values = tuple(symbols)
    if not values or len(values) > _MAX_METADATA_SYMBOLS:
        raise CollectorError("INVALID_INPUT")
    if any(not _is_valid_symbol(value) for value in values):
        raise CollectorError("INVALID_INPUT")
    if len(set(values)) != len(values):
        raise CollectorError("INVALID_INPUT")
    return values


def _validate_candle_request(
    symbol: str,
    start: date,
    end: date,
    before: str,
    adjusted: bool,
) -> None:
    if not _is_valid_symbol(symbol):
        raise CollectorError("INVALID_INPUT")
    if type(start) is not date or type(end) is not date or start > end:
        raise CollectorError("INVALID_INPUT")
    if not _is_valid_cursor(before) or type(adjusted) is not bool:
        raise CollectorError("INVALID_INPUT")
    try:
        _parse_timestamp(before)
    except CollectorError:
        raise CollectorError("INVALID_INPUT") from None


def _is_valid_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and _is_utf8_encodable(value)
        and _SYMBOL_PATTERN.fullmatch(value) is not None
    )


def _is_valid_cursor(value: object) -> bool:
    return (
        isinstance(value, str)
        and _is_utf8_encodable(value)
        and 0 < len(value) <= 2048
        and "\r" not in value
        and "\n" not in value
        and "\x00" not in value
    )


def _is_utf8_encodable(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _send_allowed_get_no_raise(
    transport: Transport,
    token_supplier: TokenSupplier,
    url: str,
) -> _CredentialBoundaryResult:
    """Completes all credential-bearing work without propagating an exception."""

    try:
        return _send_allowed_get_in_credential_scope(
            transport,
            token_supplier,
            url,
        )
    except Exception:
        return _CredentialBoundaryResult("TRANSPORT_ERROR", None)


def _send_allowed_get_in_credential_scope(
    transport: Transport,
    token_supplier: TokenSupplier,
    url: str,
) -> _CredentialBoundaryResult:
    """Owns ephemeral credentials; callers must use the no-raise wrapper."""

    try:
        ephemeral_bearer = token_supplier()
    except Exception:
        return _CredentialBoundaryResult("AUTH_TOKEN_UNAVAILABLE", None)
    if not _is_valid_bearer(ephemeral_bearer):
        return _CredentialBoundaryResult("AUTH_TOKEN_INVALID", None)

    request = HttpRequest(
        method="GET",
        url=url,
        headers=MappingProxyType(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {ephemeral_bearer}",
            }
        ),
    )
    try:
        response = transport(request)
    except Exception:
        return _CredentialBoundaryResult("TRANSPORT_ERROR", None)

    try:
        if _response_contains_sensitive_material(response, ephemeral_bearer):
            return _CredentialBoundaryResult("SENSITIVE_RESPONSE", None)
        if not _is_valid_http_response(response):
            return _CredentialBoundaryResult("INVALID_HTTP_RESPONSE", None)
        sanitized_headers = _sanitize_headers_no_raise(response.headers)
        if sanitized_headers is None:
            return _CredentialBoundaryResult("INVALID_HTTP_RESPONSE", None)
        sanitized_response = _SanitizedHttpResponse(
            status=response.status,
            headers=sanitized_headers,
            body=bytes(response.body),
        )
        return _CredentialBoundaryResult(None, sanitized_response)
    except Exception:
        return _CredentialBoundaryResult("SENSITIVE_RESPONSE", None)


def _is_valid_bearer(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and _is_utf8_encodable(value)
        and "\r" not in value
        and "\n" not in value
        and "\x00" not in value
    )


def _is_valid_http_response(response: object) -> bool:
    return (
        isinstance(response, HttpResponse)
        and type(response.status) is int
        and 100 <= response.status <= 599
        and isinstance(response.headers, Mapping)
        and isinstance(response.body, bytes)
    )


def _sanitize_headers_no_raise(
    headers: Mapping[object, object],
) -> tuple[tuple[str, str], ...] | None:
    sanitized: dict[str, str] = {}
    try:
        header_items = tuple(headers.items())
    except Exception:
        return None
    for name, value in header_items:
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or not _is_utf8_encodable(name)
            or not _is_utf8_encodable(value)
        ):
            return None
        normalized_name = name.lower()
        if normalized_name not in _ALLOWED_RESPONSE_HEADERS:
            continue
        if normalized_name in sanitized and sanitized[normalized_name] != value:
            return None
        sanitized[normalized_name] = value
    return tuple(sorted(sanitized.items()))


def _response_contains_sensitive_material(
    response: object,
    ephemeral_bearer: str,
) -> bool:
    if not isinstance(response, HttpResponse):
        return False
    if isinstance(response.body, bytes) and _body_contains_sensitive_material(
        response.body,
        ephemeral_bearer,
    ):
        return True
    if not isinstance(response.headers, Mapping):
        return False
    try:
        header_items = tuple(response.headers.items())
    except Exception:
        return True
    for name, value in header_items:
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        lexical_name = _decode_json_escapes_lexically(name)
        lexical_value = _decode_json_escapes_lexically(value)
        if any(
            ephemeral_bearer in candidate
            for candidate in (name, value, lexical_name, lexical_value)
        ):
            return True
        assignment = f"{_normalize_sensitive_identifier(lexical_name)}: {lexical_value}"
        if any(
            _contains_sensitive_material_no_raise(candidate)
            for candidate in (lexical_name, lexical_value, assignment)
        ):
            return True
    return False


def _body_contains_sensitive_material(body: bytes, ephemeral_bearer: str) -> bool:
    bearer_bytes = ephemeral_bearer.encode("utf-8")
    if bearer_bytes in body:
        return True
    body_text = body.decode("utf-8", errors="ignore")
    lexical_text = _decode_json_escapes_lexically(body_text)
    if ephemeral_bearer in body_text or ephemeral_bearer in lexical_text:
        return True
    if _contains_sensitive_material_no_raise(body_text):
        return True
    if _contains_sensitive_material_no_raise(lexical_text):
        return True
    try:
        decoded = json.loads(body_text, object_pairs_hook=_PreflightObjectPairs)
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        return False
    return _decoded_json_contains_sensitive_material(decoded, ephemeral_bearer)


def _decoded_json_contains_sensitive_material(
    value: object,
    ephemeral_bearer: str,
) -> bool:
    pending: list[object] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, _PreflightObjectPairs):
            for key, item in current:
                if ephemeral_bearer in key:
                    return True
                if _contains_sensitive_material_no_raise(key):
                    return True
                if isinstance(item, str):
                    if ephemeral_bearer in item:
                        return True
                    assignment = f"{_normalize_sensitive_identifier(key)}: {item}"
                    if _contains_sensitive_material_no_raise(assignment):
                        return True
                pending.append(item)
            continue
        if isinstance(current, list):
            pending.extend(current)
            continue
        if isinstance(current, str):
            if ephemeral_bearer in current:
                return True
            if _contains_sensitive_material_no_raise(current):
                return True
    return False


def _contains_sensitive_material_no_raise(value: str) -> bool:
    try:
        if find_sensitive_values(value):
            return True
        normalized_identifiers = _normalize_sensitive_identifier(value)
        return bool(find_sensitive_values(normalized_identifiers))
    except UnicodeError:
        return False
    except Exception:
        return True


def _normalize_sensitive_identifier(value: str) -> str:
    camel_case_expanded = _CAMEL_CASE_BOUNDARY.sub(" ", value)
    return re.sub(r"[_-]+", " ", camel_case_expanded)


def _decode_json_escapes_lexically(value: str) -> str:
    decoded: list[str] = []
    index = 0
    simple_escapes = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while index < len(value):
        if value[index] != "\\" or index + 1 >= len(value):
            decoded.append(value[index])
            index += 1
            continue
        escape_type = value[index + 1]
        if escape_type in simple_escapes:
            decoded.append(simple_escapes[escape_type])
            index += 2
            continue
        code_unit = _json_unicode_escape_code_unit(value, index)
        if code_unit is None:
            decoded.append(value[index])
            index += 1
            continue
        next_code_unit = _json_unicode_escape_code_unit(value, index + 6)
        if (
            0xD800 <= code_unit <= 0xDBFF
            and next_code_unit is not None
            and 0xDC00 <= next_code_unit <= 0xDFFF
        ):
            scalar = 0x10000 + ((code_unit - 0xD800) << 10) + (next_code_unit - 0xDC00)
            decoded.append(chr(scalar))
            index += 12
            continue
        decoded.append(chr(code_unit))
        index += 6
    return "".join(decoded)


def _json_unicode_escape_code_unit(value: str, index: int) -> int | None:
    if index + 6 > len(value) or value[index : index + 2] != "\\u":
        return None
    digits = value[index + 2 : index + 6]
    if len(digits) != 4 or any(
        character not in "0123456789abcdefABCDEF" for character in digits
    ):
        return None
    return int(digits, 16)


def _make_capture(
    endpoint_id: str,
    url: str,
    query: tuple[tuple[str, str], ...],
    response: _SanitizedHttpResponse,
    clock: Clock,
) -> RawHttpCapture:
    received_at = _utc_timestamp(clock)
    return RawHttpCapture(
        endpoint_id=endpoint_id,
        method="GET",
        sanitized_url=url,
        query=query,
        status=response.status,
        headers=response.headers,
        received_at=received_at,
        body_base64=base64.b64encode(response.body).decode("ascii"),
        body_sha256=hashlib.sha256(response.body).hexdigest(),
    )


def _utc_timestamp(clock: Clock) -> str:
    try:
        value = clock()
    except Exception:
        raise CollectorError("CLOCK_INVALID") from None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CollectorError("CLOCK_INVALID")
    try:
        normalized = value.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise CollectorError("CLOCK_INVALID") from None
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_json(body: bytes, capture: RawHttpCapture) -> object:
    try:
        text = body.decode("utf-8")
        value = json.loads(
            text,
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
        _validate_decoded_json_utf8(value)
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, _InvalidJson, RecursionError):
        raise CollectorError("INVALID_JSON", capture) from None


def _reject_json_constant(_: str) -> NoReturn:
    raise _InvalidJson()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _InvalidJson()
        value[key] = item
    return value


def _validate_decoded_json_utf8(value: object) -> None:
    pending: list[object] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if not _is_utf8_encodable(key):
                    raise _InvalidJson()
                pending.append(item)
            continue
        if isinstance(current, list):
            pending.extend(current)
            continue
        if isinstance(current, str) and not _is_utf8_encodable(current):
            raise _InvalidJson()


def _parse_metadata(
    value: object,
    requested_symbols: frozenset[str],
    capture: RawHttpCapture,
) -> tuple[StockMetadata, ...]:
    if not isinstance(value, dict) or frozenset(value) != {"result"}:
        raise CollectorError("INVALID_METADATA_SHAPE", capture)
    raw_records = value["result"]
    if not isinstance(raw_records, list):
        raise CollectorError("INVALID_METADATA_SHAPE", capture)
    records: list[StockMetadata] = []
    seen_symbols: set[str] = set()
    for item in raw_records:
        record = _parse_metadata_record(item, capture)
        if record.symbol not in requested_symbols:
            raise CollectorError("UNEXPECTED_METADATA_SYMBOL", capture)
        if record.symbol in seen_symbols:
            raise CollectorError("DUPLICATE_METADATA_SYMBOL", capture)
        seen_symbols.add(record.symbol)
        records.append(record)
    if seen_symbols != requested_symbols:
        raise CollectorError("MISSING_METADATA_SYMBOLS", capture)
    return tuple(records)


def _parse_metadata_record(value: object, capture: RawHttpCapture) -> StockMetadata:
    if not isinstance(value, dict) or not _METADATA_FIELDS.issubset(value):
        raise CollectorError("INVALID_METADATA_SHAPE", capture)
    unregistered_fields = frozenset(value).difference(
        _METADATA_FIELDS | _DOCUMENTED_SAFE_METADATA_EXTRA_FIELDS
    )
    if unregistered_fields:
        raise CollectorError("UNREGISTERED_METADATA_FIELD", capture)
    string_fields = (
        "symbol",
        "name",
        "englishName",
        "isinCode",
        "market",
        "securityType",
        "status",
        "currency",
    )
    if any(not isinstance(value[field], str) or not value[field] for field in string_fields):
        raise CollectorError("INVALID_METADATA_SHAPE", capture)
    if type(value["isCommonShare"]) is not bool:
        raise CollectorError("INVALID_METADATA_SHAPE", capture)
    try:
        shares_outstanding = _nonnegative_integer_scalar(
            value["sharesOutstanding"],
            max_length=30,
        )
    except CollectorError:
        raise CollectorError("INVALID_METADATA_SHAPE", capture) from None
    return StockMetadata(
        symbol=value["symbol"],
        name=value["name"],
        english_name=value["englishName"],
        isin_code=value["isinCode"],
        market=value["market"],
        security_type=value["securityType"],
        is_common_share=value["isCommonShare"],
        status=value["status"],
        currency=value["currency"],
        shares_outstanding=shares_outstanding,
    )


def _parse_candle_page(value: object, capture: RawHttpCapture) -> _ParsedCandlePage:
    if not isinstance(value, dict) or frozenset(value) != {"result"}:
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    result = value["result"]
    if not isinstance(result, dict):
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    if "candles" not in result or not frozenset(result).issubset({"candles", "nextBefore"}):
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    raw_rows = result["candles"]
    if not isinstance(raw_rows, list) or len(raw_rows) > _MAX_CANDLE_ROWS_PER_PAGE:
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    rows: list[CandleRow] = []
    timestamps: list[datetime] = []
    for raw_row in raw_rows:
        row, timestamp = _parse_candle_row(raw_row, capture)
        rows.append(row)
        timestamps.append(timestamp)
    next_before_value = result.get("nextBefore")
    if next_before_value is not None and not _is_valid_cursor(next_before_value):
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    return _ParsedCandlePage(
        rows=tuple(rows),
        timestamps=tuple(timestamps),
        next_before=next_before_value,
    )


def _parse_candle_row(
    value: object,
    capture: RawHttpCapture,
) -> tuple[CandleRow, datetime]:
    if not isinstance(value, dict) or frozenset(value) != _CANDLE_FIELDS:
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    timestamp_text = value["timestamp"]
    currency = value["currency"]
    if not isinstance(timestamp_text, str) or not isinstance(currency, str) or not currency:
        raise CollectorError("INVALID_CANDLE_SHAPE", capture)
    timestamp = _parse_timestamp(timestamp_text, capture)
    try:
        row = CandleRow(
            timestamp=timestamp_text,
            open_price=_positive_decimal_scalar(value["openPrice"]),
            high_price=_positive_decimal_scalar(value["highPrice"]),
            low_price=_positive_decimal_scalar(value["lowPrice"]),
            close_price=_positive_decimal_scalar(value["closePrice"]),
            volume=_nonnegative_integer_scalar(value["volume"]),
            currency=currency,
        )
    except CollectorError:
        raise CollectorError("INVALID_CANDLE_SHAPE", capture) from None
    return row, timestamp


def _canonical_scalar(value: object) -> CanonicalScalar:
    if isinstance(value, _JsonNumber):
        return CanonicalScalar(kind="json_number", text=str(value))
    if isinstance(value, str):
        return CanonicalScalar(kind="json_string", text=value)
    raise CollectorError("INVALID_SCALAR")


def _positive_decimal_scalar(value: object) -> CanonicalScalar:
    scalar = _canonical_scalar(value)
    if _UNSIGNED_DECIMAL_PATTERN.fullmatch(scalar.text) is None:
        raise CollectorError("INVALID_SCALAR")
    if not any(character != "0" and character != "." for character in scalar.text):
        raise CollectorError("INVALID_SCALAR")
    return scalar


def _nonnegative_integer_scalar(
    value: object,
    max_length: int | None = None,
) -> CanonicalScalar:
    scalar = _canonical_scalar(value)
    if _UNSIGNED_INTEGER_PATTERN.fullmatch(scalar.text) is None:
        raise CollectorError("INVALID_SCALAR")
    if max_length is not None and len(scalar.text) > max_length:
        raise CollectorError("INVALID_SCALAR")
    return scalar


def _parse_timestamp(
    value: str,
    capture: RawHttpCapture | None = None,
) -> datetime:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        normalized = parsed.astimezone(timezone.utc)
        normalized.astimezone(_SESSION_TIMEZONE)
        return normalized
    except (TypeError, ValueError, OverflowError, OSError):
        raise CollectorError("INVALID_TIMESTAMP", capture) from None


def _merge_candle_page(
    page: _ParsedCandlePage,
    rows_by_timestamp: dict[str, CandleRow],
    timestamps_by_text: dict[str, datetime],
    timestamp_text_by_instant: dict[datetime, str],
    timestamp_text_by_session: dict[date, str],
    capture: RawHttpCapture,
) -> int:
    new_row_count = 0
    for row, timestamp in zip(page.rows, page.timestamps, strict=True):
        instant_timestamp_text = timestamp_text_by_instant.get(timestamp)
        if instant_timestamp_text is not None and instant_timestamp_text != row.timestamp:
            raise CollectorError("CONFLICTING_DUPLICATE", capture)
        session = _session_date(timestamp)
        session_timestamp_text = timestamp_text_by_session.get(session)
        if session_timestamp_text is not None and session_timestamp_text != row.timestamp:
            raise CollectorError("CONFLICTING_DUPLICATE", capture)
        existing = rows_by_timestamp.get(row.timestamp)
        if existing is None:
            rows_by_timestamp[row.timestamp] = row
            timestamps_by_text[row.timestamp] = timestamp
            timestamp_text_by_instant[timestamp] = row.timestamp
            timestamp_text_by_session[session] = row.timestamp
            new_row_count += 1
            continue
        if existing != row:
            raise CollectorError("CONFLICTING_DUPLICATE", capture)
    return new_row_count


def _validate_page_order(
    page: _ParsedCandlePage,
    previous_page_oldest: datetime | None,
    capture: RawHttpCapture,
) -> datetime | None:
    if not page.timestamps:
        return previous_page_oldest
    if any(
        older_timestamp > newer_timestamp
        for newer_timestamp, older_timestamp in zip(
            page.timestamps,
            page.timestamps[1:],
            strict=False,
        )
    ):
        raise CollectorError("PAGE_ORDER_INVALID", capture)
    current_page_newest = page.timestamps[0]
    if previous_page_oldest is not None and current_page_newest > previous_page_oldest:
        raise CollectorError("PAGE_ORDER_INVALID", capture)
    return page.timestamps[-1]


def _partition_by_requested_range(
    ordered_rows: tuple[CandleRow, ...],
    timestamps_by_text: Mapping[str, datetime],
    start: date,
    end: date,
) -> tuple[tuple[CandleRow, ...], tuple[CandleRow, ...]]:
    analysis_rows: list[CandleRow] = []
    audit_only_rows: list[CandleRow] = []
    for row in ordered_rows:
        row_date = _session_date(timestamps_by_text[row.timestamp])
        if start <= row_date <= end:
            analysis_rows.append(row)
        else:
            audit_only_rows.append(row)
    return tuple(analysis_rows), tuple(audit_only_rows)


def _session_date(timestamp: datetime) -> date:
    return timestamp.astimezone(_SESSION_TIMEZONE).date()
