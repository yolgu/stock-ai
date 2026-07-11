"""Strict forward-only Toss trade and orderbook snapshot measurement."""

from __future__ import annotations

import base64
import hashlib
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, build_opener

from rp001.toss_research_collector import (
    CanonicalScalar,
    CollectorError,
    HttpRequest,
    HttpResponse,
    RawHttpCapture,
    _parse_json,
    _parse_timestamp,
    _utc_timestamp,
)
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _CANDLE_RESPONSE_LIMIT_BYTES,
    _Opener,
    _RejectRedirectHandler,
    _open_http_response,
)


MINIMUM_FORWARD_REQUEST_INTERVAL_SECONDS = 1.0
_BASE_URL = "https://openapi.tossinvest.com"
_TRADES_PATH = "/api/v1/trades"
_ORDERBOOK_PATH = "/api/v1/orderbook"
_TRADES_ENDPOINT_ID = "sampled_trades_v1"
_ORDERBOOK_ENDPOINT_ID = "sampled_orderbook_v1"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.^-]{0,19}$")
_TRADE_FIELDS = frozenset({"price", "volume", "timestamp", "currency"})
_BOOK_FIELDS = frozenset({"timestamp", "currency", "asks", "bids"})
_BOOK_ENTRY_FIELDS = frozenset({"price", "volume"})
_ALLOWED_CAPTURE_HEADERS = frozenset(
    {
        "content-type",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "retry-after",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)
_MAX_TRADE_POLLS = 10_000

TokenSupplier = Callable[[], str]
Clock = Callable[[], datetime]
RequestPacer = Callable[[], None]
Occurrence = tuple[str, int, int]


class ForwardMicrostructureError(ValueError):
    """Sanitized sampled-microstructure failure with safe captures."""

    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


@dataclass(frozen=True)
class SampledTradeObservation:
    price: CanonicalScalar
    volume: CanonicalScalar
    source_timestamp: str
    normalized_event_at: str
    received_at: str
    currency: str
    source_body_sha256: str
    source_capture_ordinal: int
    source_row_index: int
    source_occurrence: Occurrence
    duplicate_status: str
    ambiguous_occurrences: tuple[Occurrence, ...]


@dataclass(frozen=True)
class SampledTradeStream:
    symbol: str
    observations: tuple[SampledTradeObservation, ...]
    captures: tuple[RawHttpCapture, ...]
    measurement_kind: str = "sampled_trade_stream"
    completeness: str = "not_complete_exchange_tape"
    aggressor_side_status: str = "not_identifiable"
    order_id_status: str = "not_available"
    ofi_status: str = "not_identifiable"


@dataclass(frozen=True)
class SampledOrderbookLevel:
    side: str
    level: int
    price: CanonicalScalar
    volume: CanonicalScalar
    source_body_sha256: str
    source_capture_ordinal: int
    source_row_index: int


@dataclass(frozen=True)
class SampledOrderbookSnapshot:
    symbol: str
    source_timestamp: str | None
    normalized_event_at: str | None
    received_at: str
    currency: str
    asks: tuple[SampledOrderbookLevel, ...]
    bids: tuple[SampledOrderbookLevel, ...]
    source_body_sha256: str
    source_capture_ordinal: int
    source_row_index: int
    capture: RawHttpCapture
    measurement_kind: str = "sampled_orderbook_snapshot"
    completeness: str = "not_complete_exchange_tape"
    aggressor_side_status: str = "not_identifiable"
    order_id_status: str = "not_available"
    ofi_status: str = "not_identifiable"


class _GlobalMinimumIntervalPacer:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._last_request_at: float | None = None

    def __call__(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                remaining = self.interval_seconds - (now - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()


_GLOBAL_FORWARD_PACER = _GlobalMinimumIntervalPacer(
    MINIMUM_FORWARD_REQUEST_INTERVAL_SECONDS
)


class StrictTossForwardTransport:
    """Permit only frozen recent-trade and current-orderbook reads."""

    def __init__(
        self,
        *,
        opener: _Opener,
        allowed_symbols: Sequence[str],
        request_pacer: RequestPacer | None = None,
    ) -> None:
        try:
            if isinstance(allowed_symbols, (str, bytes)):
                raise TypeError
            symbols = tuple(allowed_symbols)
        except TypeError:
            raise ReadOnlyBoundaryError("allowed_scope_invalid") from None
        if (
            not symbols
            or any(not _valid_symbol(symbol) for symbol in symbols)
            or len(symbols) != len(set(symbols))
            or (request_pacer is not None and not callable(request_pacer))
        ):
            raise ReadOnlyBoundaryError("allowed_scope_invalid")
        self._opener = opener
        self._allowed_symbols = frozenset(symbols)
        self._request_pacer = request_pacer or _GLOBAL_FORWARD_PACER

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._validate_request(request)
        self._request_pacer()
        outgoing = Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        return _open_http_response(
            self._opener,
            outgoing,
            _CANDLE_RESPONSE_LIMIT_BYTES,
            "forward_microstructure_transport_error",
        )

    def _validate_request(self, request: HttpRequest) -> None:
        if not isinstance(request, HttpRequest) or request.method != "GET":
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        try:
            parsed = urlsplit(request.url)
            query = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except (TypeError, ValueError):
            raise ReadOnlyBoundaryError("endpoint_not_allowed") from None
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.tossinvest.com"
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or not self._valid_endpoint(parsed.path, query, request.url)
            or not _valid_bearer_headers(request.headers)
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")

    def _valid_endpoint(
        self,
        path: str,
        query: list[tuple[str, str]],
        url: str,
    ) -> bool:
        if path == _TRADES_PATH and len(query) == 2:
            symbol = query[0][1]
            return (
                tuple(name for name, _ in query) == ("symbol", "count")
                and symbol in self._allowed_symbols
                and query[1][1] == "50"
                and url == _trades_url(symbol)
            )
        if path == _ORDERBOOK_PATH and len(query) == 1:
            symbol = query[0][1]
            return (
                query[0][0] == "symbol"
                and symbol in self._allowed_symbols
                and url == _orderbook_url(symbol)
            )
        return False


def build_live_toss_forward_transport(
    *,
    allowed_symbols: Sequence[str],
    request_pacer: RequestPacer | None = None,
) -> StrictTossForwardTransport:
    """Build the forward read-only transport with redirects rejected."""
    return StrictTossForwardTransport(
        opener=build_opener(_RejectRedirectHandler()),
        allowed_symbols=allowed_symbols,
        request_pacer=request_pacer,
    )


class TossForwardMicrostructureCollector:
    """Collect sampled observations without claiming a complete event tape."""

    def __init__(
        self,
        *,
        transport: StrictTossForwardTransport,
        token_supplier: TokenSupplier,
        clock: Clock,
    ) -> None:
        if (
            not isinstance(transport, StrictTossForwardTransport)
            or not callable(token_supplier)
            or not callable(clock)
        ):
            raise ForwardMicrostructureError("INVALID_INPUT")
        self._transport = transport
        self._token_supplier = token_supplier
        self._clock = clock

    def collect_trade_polls(
        self,
        *,
        symbol: str,
        poll_count: int,
    ) -> SampledTradeStream:
        if (
            not _valid_symbol(symbol)
            or type(poll_count) is not int
            or not 1 <= poll_count <= _MAX_TRADE_POLLS
        ):
            raise ForwardMicrostructureError("INVALID_INPUT")
        captures: list[RawHttpCapture] = []
        observations: list[SampledTradeObservation] = []
        try:
            for capture_ordinal in range(poll_count):
                capture, value = self._receive(
                    _TRADES_ENDPOINT_ID,
                    _trades_url(symbol),
                )
                captures.append(capture)
                observations.extend(
                    _parse_trades(value, capture, capture_ordinal)
                )
        except ForwardMicrostructureError as error:
            raise ForwardMicrostructureError(
                error.code,
                _combine_captures(tuple(captures), error.captures),
            ) from None
        return SampledTradeStream(
            symbol=symbol,
            observations=_mark_ambiguous_duplicates(tuple(observations)),
            captures=tuple(captures),
        )

    def poll_orderbook(
        self,
        *,
        symbol: str,
        capture_ordinal: int = 0,
    ) -> SampledOrderbookSnapshot:
        if (
            not _valid_symbol(symbol)
            or type(capture_ordinal) is not int
            or capture_ordinal < 0
        ):
            raise ForwardMicrostructureError("INVALID_INPUT")
        capture, value = self._receive(
            _ORDERBOOK_ENDPOINT_ID,
            _orderbook_url(symbol),
        )
        return _parse_orderbook(value, symbol, capture, capture_ordinal)

    def _receive(
        self,
        endpoint_id: str,
        url: str,
    ) -> tuple[RawHttpCapture, object]:
        token = ""
        try:
            try:
                token = self._token_supplier()
            except Exception:
                raise ForwardMicrostructureError("TOKEN_UNAVAILABLE") from None
            if not _valid_token(token):
                raise ForwardMicrostructureError("TOKEN_UNAVAILABLE")
            response = self._transport(
                HttpRequest(
                    method="GET",
                    url=url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
            )
            capture = _capture(endpoint_id, url, response, self._clock)
            if not 200 <= response.status < 300:
                raise ForwardMicrostructureError("HTTP_STATUS", (capture,))
            content_type = dict(capture.headers).get("content-type", "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise ForwardMicrostructureError(
                    "INVALID_CONTENT_TYPE",
                    (capture,),
                )
            try:
                value = _parse_json(response.body, capture)
            except CollectorError as error:
                raise ForwardMicrostructureError(
                    error.code,
                    error.captures,
                ) from None
            return capture, value
        except ReadOnlyBoundaryError as error:
            raise ForwardMicrostructureError(error.code, error.captures) from None
        finally:
            token = ""


def _parse_trades(
    value: object,
    capture: RawHttpCapture,
    capture_ordinal: int,
) -> tuple[SampledTradeObservation, ...]:
    if (
        not isinstance(value, dict)
        or frozenset(value) != {"result"}
        or not isinstance(value["result"], list)
        or len(value["result"]) > 50
    ):
        raise ForwardMicrostructureError("INVALID_TRADE_SHAPE", (capture,))
    observations: list[SampledTradeObservation] = []
    for row_index, raw in enumerate(value["result"]):
        if not isinstance(raw, dict) or frozenset(raw) != _TRADE_FIELDS:
            raise ForwardMicrostructureError("INVALID_TRADE_SHAPE", (capture,))
        price = _decimal_string(raw["price"], positive=True, capture=capture)
        volume = _decimal_string(raw["volume"], positive=False, capture=capture)
        source_timestamp, normalized_event_at = _event_timestamp(
            raw["timestamp"],
            capture,
            nullable=False,
        )
        currency = _currency(raw["currency"], capture)
        occurrence = (capture.body_sha256, capture_ordinal, row_index)
        observations.append(
            SampledTradeObservation(
                price=price,
                volume=volume,
                source_timestamp=source_timestamp,
                normalized_event_at=normalized_event_at,
                received_at=capture.received_at,
                currency=currency,
                source_body_sha256=capture.body_sha256,
                source_capture_ordinal=capture_ordinal,
                source_row_index=row_index,
                source_occurrence=occurrence,
                duplicate_status="unique_poll_observation",
                ambiguous_occurrences=(occurrence,),
            )
        )
    return tuple(observations)


def _mark_ambiguous_duplicates(
    observations: tuple[SampledTradeObservation, ...],
) -> tuple[SampledTradeObservation, ...]:
    groups: dict[
        tuple[str, str, str, str],
        list[SampledTradeObservation],
    ] = {}
    for observation in observations:
        signature = (
            observation.source_timestamp,
            observation.price.text,
            observation.volume.text,
            observation.currency,
        )
        groups.setdefault(signature, []).append(observation)
    ambiguous: dict[Occurrence, tuple[Occurrence, ...]] = {}
    for group in groups.values():
        if len({item.source_capture_ordinal for item in group}) <= 1:
            continue
        occurrences = tuple(item.source_occurrence for item in group)
        for item in group:
            ambiguous[item.source_occurrence] = occurrences
    return tuple(
        replace(
            observation,
            duplicate_status="ambiguous_cross_poll_duplicate",
            ambiguous_occurrences=ambiguous[observation.source_occurrence],
        )
        if observation.source_occurrence in ambiguous
        else observation
        for observation in observations
    )


def _parse_orderbook(
    value: object,
    symbol: str,
    capture: RawHttpCapture,
    capture_ordinal: int,
) -> SampledOrderbookSnapshot:
    if not isinstance(value, dict) or frozenset(value) != {"result"}:
        raise ForwardMicrostructureError("INVALID_ORDERBOOK_SHAPE", (capture,))
    result = value["result"]
    if (
        not isinstance(result, dict)
        or frozenset(result) != _BOOK_FIELDS
        or not isinstance(result["asks"], list)
        or not isinstance(result["bids"], list)
    ):
        raise ForwardMicrostructureError("INVALID_ORDERBOOK_SHAPE", (capture,))
    source_timestamp, normalized_event_at = _event_timestamp(
        result["timestamp"],
        capture,
        nullable=True,
    )
    currency = _currency(result["currency"], capture)
    asks, ask_values = _levels(
        result["asks"],
        "ask",
        capture,
        capture_ordinal,
        row_offset=0,
    )
    bids, bid_values = _levels(
        result["bids"],
        "bid",
        capture,
        capture_ordinal,
        row_offset=len(asks),
    )
    if any(current <= previous for previous, current in zip(ask_values, ask_values[1:])):
        raise ForwardMicrostructureError("ORDERBOOK_ORDER_INVALID", (capture,))
    if any(current >= previous for previous, current in zip(bid_values, bid_values[1:])):
        raise ForwardMicrostructureError("ORDERBOOK_ORDER_INVALID", (capture,))
    return SampledOrderbookSnapshot(
        symbol=symbol,
        source_timestamp=source_timestamp,
        normalized_event_at=normalized_event_at,
        received_at=capture.received_at,
        currency=currency,
        asks=asks,
        bids=bids,
        source_body_sha256=capture.body_sha256,
        source_capture_ordinal=capture_ordinal,
        source_row_index=0,
        capture=capture,
    )


def _levels(
    values: list[object],
    side: str,
    capture: RawHttpCapture,
    capture_ordinal: int,
    *,
    row_offset: int,
) -> tuple[tuple[SampledOrderbookLevel, ...], tuple[Decimal, ...]]:
    levels: list[SampledOrderbookLevel] = []
    prices: list[Decimal] = []
    for level_index, value in enumerate(values):
        if not isinstance(value, dict) or frozenset(value) != _BOOK_ENTRY_FIELDS:
            raise ForwardMicrostructureError("INVALID_ORDERBOOK_SHAPE", (capture,))
        price, price_value = _decimal_string_value(
            value["price"],
            positive=True,
            capture=capture,
        )
        volume = _decimal_string(value["volume"], positive=False, capture=capture)
        levels.append(
            SampledOrderbookLevel(
                side=side,
                level=level_index,
                price=price,
                volume=volume,
                source_body_sha256=capture.body_sha256,
                source_capture_ordinal=capture_ordinal,
                source_row_index=row_offset + level_index,
            )
        )
        prices.append(price_value)
    return tuple(levels), tuple(prices)


def _event_timestamp(
    value: object,
    capture: RawHttpCapture,
    *,
    nullable: bool,
) -> tuple[str | None, str | None]:
    if value is None and nullable:
        return None, None
    if not isinstance(value, str) or not value:
        raise ForwardMicrostructureError("TIMESTAMP_INVALID", (capture,))
    try:
        event = _parse_timestamp(value, capture)
        received = _parse_timestamp(capture.received_at, capture)
    except CollectorError:
        raise ForwardMicrostructureError("TIMESTAMP_INVALID", (capture,)) from None
    if event > received:
        raise ForwardMicrostructureError("TIMESTAMP_INVALID", (capture,))
    return value, _format_utc(event)


def _decimal_string(
    value: object,
    *,
    positive: bool,
    capture: RawHttpCapture,
) -> CanonicalScalar:
    scalar, _ = _decimal_string_value(value, positive=positive, capture=capture)
    return scalar


def _decimal_string_value(
    value: object,
    *,
    positive: bool,
    capture: RawHttpCapture,
) -> tuple[CanonicalScalar, Decimal]:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ForwardMicrostructureError("DECIMAL_INVALID", (capture,))
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        raise ForwardMicrostructureError("DECIMAL_INVALID", (capture,)) from None
    if (
        not decimal.is_finite()
        or (positive and decimal <= 0)
        or (not positive and decimal < 0)
    ):
        raise ForwardMicrostructureError("DECIMAL_INVALID", (capture,))
    return CanonicalScalar(kind="json_string", text=value), decimal


def _currency(value: object, capture: RawHttpCapture) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise ForwardMicrostructureError("CURRENCY_INVALID", (capture,))
    return value


def _capture(
    endpoint_id: str,
    url: str,
    response: HttpResponse,
    clock: Clock,
) -> RawHttpCapture:
    if (
        not isinstance(response, HttpResponse)
        or type(response.status) is not int
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
    ):
        raise ForwardMicrostructureError("INVALID_HTTP_RESPONSE")
    try:
        received_at = _utc_timestamp(clock)
    except CollectorError:
        raise ForwardMicrostructureError("CLOCK_INVALID") from None
    query = tuple(
        parse_qsl(
            urlsplit(url).query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    )
    return RawHttpCapture(
        endpoint_id=endpoint_id,
        method="GET",
        sanitized_url=url,
        query=query,
        status=response.status,
        headers=_capture_headers(response.headers),
        received_at=received_at,
        body_base64=base64.b64encode(response.body).decode("ascii"),
        body_sha256=hashlib.sha256(response.body).hexdigest(),
    )


def _capture_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    captured: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ForwardMicrostructureError("INVALID_HTTP_RESPONSE")
        normalized_name = name.lower()
        if normalized_name in captured or any(
            character in value for character in "\r\n\x00"
        ):
            raise ForwardMicrostructureError("INVALID_HTTP_RESPONSE")
        if normalized_name in _ALLOWED_CAPTURE_HEADERS:
            captured[normalized_name] = value
    return tuple(sorted(captured.items()))


def _valid_bearer_headers(headers: Mapping[str, str]) -> bool:
    if not isinstance(headers, Mapping):
        return False
    items: list[tuple[str, str]] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            return False
        items.append((name.lower(), value))
    normalized = dict(items)
    authorization = normalized.get("authorization")
    return (
        len(items) == len(normalized)
        and set(normalized) == {"accept", "authorization"}
        and normalized.get("accept") == "application/json"
        and isinstance(authorization, str)
        and authorization.startswith("Bearer ")
        and authorization != "Bearer "
        and not any(character in authorization for character in "\r\n\x00")
    )


def _valid_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in "\r\n\x00")
    )


def _valid_symbol(value: object) -> bool:
    return isinstance(value, str) and _SYMBOL_PATTERN.fullmatch(value) is not None


def _trades_url(symbol: str) -> str:
    return f"{_BASE_URL}{_TRADES_PATH}?{urlencode((('symbol', symbol), ('count', '50')))}"


def _orderbook_url(symbol: str) -> str:
    return f"{_BASE_URL}{_ORDERBOOK_PATH}?{urlencode((('symbol', symbol),))}"


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _combine_captures(
    prior: tuple[RawHttpCapture, ...],
    current: tuple[RawHttpCapture, ...],
) -> tuple[RawHttpCapture, ...]:
    combined = list(prior)
    for capture in current:
        if capture not in combined:
            combined.append(capture)
    return tuple(combined)
