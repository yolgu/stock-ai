"""Strict read-only Alpaca daily-bar boundary and lossless collector."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from rp001.toss_research_collector import (
    CanonicalScalar,
    CollectorError,
    HttpRequest,
    HttpResponse,
    RawHttpCapture,
    _canonical_scalar,
    _parse_json,
    _parse_timestamp,
    _utc_timestamp,
)
from rp001_s2.alpaca_boundary import (
    AlpacaCredentialCapability,
    _US_SYMBOL,
    _page_token_from_url,
    _sanitized_capture_url_and_query,
)
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _Opener,
    _RejectRedirectHandler,
    _open_http_response,
)


_BASE_URL = "https://data.alpaca.markets"
_ENDPOINT_ID = "alpaca_stock_daily_bars_v2"
_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024
_ALLOWED_FEEDS = frozenset({"sip", "iex"})
_ALLOWED_ADJUSTMENTS = frozenset({"raw", "split"})
_REQUIRED_RESPONSE_FIELDS = frozenset(
    {"bars", "symbol", "next_page_token"}
)
_OPTIONAL_RESPONSE_FIELDS = frozenset({"currency"})
_BAR_FIELDS = frozenset({"t", "o", "h", "l", "c", "v", "n", "vw"})
_MAX_ROWS_PER_PAGE = 10_000
_MAX_PAGE_COUNT = 64
_MAX_PAGE_TOKEN_LENGTH = 4096
_NEW_YORK = ZoneInfo("America/New_York")
_ALLOWED_CAPTURE_HEADERS = frozenset(
    {
        "content-type",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)

Clock = Callable[[], datetime]


class AlpacaDailyError(ValueError):
    """Sanitized daily-boundary failure with safe raw captures."""

    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


@dataclass(frozen=True)
class AlpacaDailyBar:
    source_timestamp: str
    normalized_instant: str
    bar_end: str
    available_at: str
    open_price: CanonicalScalar
    high_price: CanonicalScalar
    low_price: CanonicalScalar
    close_price: CanonicalScalar
    volume: CanonicalScalar
    trade_count: CanonicalScalar
    vwap: CanonicalScalar
    currency: str
    source_body_sha256: str
    source_capture_ordinal: int
    source_row_index: int
    provider_order: int
    occurrences: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class AlpacaDailyCollection:
    scope: CollectionScope
    rows: tuple[AlpacaDailyBar, ...]
    captures: tuple[RawHttpCapture, ...]
    overlap_count: int
    completion_reason: str


@dataclass(frozen=True)
class _ParsedPage:
    rows: tuple[AlpacaDailyBar, ...]
    instants: tuple[datetime, ...]
    next_page_token: str | None


class StrictAlpacaDailyTransport:
    """Permit only one frozen single-symbol Alpaca daily-bar scope."""

    def __init__(
        self,
        *,
        opener: _Opener,
        scope: CollectionScope,
        credentials: AlpacaCredentialCapability,
    ) -> None:
        if not _valid_daily_scope(scope) or not isinstance(
            credentials,
            AlpacaCredentialCapability,
        ):
            raise ReadOnlyBoundaryError("allowed_scope_invalid")
        self._opener = opener
        self._scope = scope
        self._credentials = credentials

    def request_page(self, page_token: str | None = None) -> HttpResponse:
        url = _daily_url(self._scope, page_token)
        return self(
            HttpRequest(
                method="GET",
                url=url,
                headers=self._credentials._authorized_headers(),
            )
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._validate_request(request)
        outgoing = Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        response = _open_http_response(
            self._opener,
            outgoing,
            _RESPONSE_LIMIT_BYTES,
            "alpaca_daily_transport_error",
        )
        page_token = _page_token_from_url(request.url)
        additional_values = (
            ()
            if page_token is None or 200 <= response.status < 300
            else (page_token,)
        )
        if self._credentials.contains_sensitive(response.body, additional_values):
            raise ReadOnlyBoundaryError("sensitive_response_body")
        return response

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
        if not _exact_origin_and_path(parsed, self._scope):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        expected_prefix = _daily_query(self._scope)
        if query == expected_prefix:
            expected_url = _daily_url(self._scope, None)
        elif (
            len(query) == len(expected_prefix) + 1
            and query[:-1] == expected_prefix
            and query[-1][0] == "page_token"
            and _valid_page_token(query[-1][1])
        ):
            expected_url = _daily_url(self._scope, query[-1][1])
        else:
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        if request.url != expected_url or not self._credentials.authorizes(
            request.headers
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")


def build_live_strict_alpaca_daily_transport(
    *,
    scope: CollectionScope,
    credentials: AlpacaCredentialCapability,
) -> StrictAlpacaDailyTransport:
    """Build the daily read-only transport with redirects disabled."""
    return StrictAlpacaDailyTransport(
        opener=build_opener(_RejectRedirectHandler()),
        scope=scope,
        credentials=credentials,
    )


class AlpacaDailyCollector:
    """Exhaust one daily scope without SIP-to-IEX fallback or row sampling."""

    def __init__(
        self,
        *,
        transport: StrictAlpacaDailyTransport,
        clock: Clock,
    ) -> None:
        transport_scope = getattr(transport, "_scope", None)
        if (
            not isinstance(transport, StrictAlpacaDailyTransport)
            or not _valid_daily_scope(transport_scope)
            or not callable(clock)
        ):
            raise AlpacaDailyError("INVALID_INPUT")
        self._transport = transport
        self._clock = clock
        self._acquisition_identity = (
            transport_scope.canonical_acquisition_json_bytes()
        )

    def collect(
        self,
        *,
        scope: CollectionScope,
        page_limit: int,
    ) -> AlpacaDailyCollection:
        if (
            not _valid_daily_scope(scope)
            or type(page_limit) is not int
            or not 1 <= page_limit <= _MAX_PAGE_COUNT
        ):
            raise AlpacaDailyError("INVALID_INPUT")
        if scope.canonical_acquisition_json_bytes() != self._acquisition_identity:
            raise AlpacaDailyError("COLLECTION_SCOPE_MISMATCH")

        captures: list[RawHttpCapture] = []
        rows_by_instant: dict[datetime, AlpacaDailyBar] = {}
        seen_page_tokens: set[str] = set()
        requested_page_token: str | None = None
        previous_page_last: datetime | None = None
        overlap_count = 0
        provider_order = 0

        try:
            for page_ordinal in range(page_limit):
                response = self._request_page(requested_page_token)
                capture = _capture_response(
                    scope,
                    requested_page_token,
                    response,
                    self._clock,
                )
                captures.append(capture)
                _require_success(response, capture)
                page = _parse_page(
                    response.body,
                    scope,
                    capture,
                    page_ordinal,
                    provider_order,
                )
                provider_order += len(page.rows)
                previous_page_last = _validate_page_order(
                    page,
                    previous_page_last,
                    capture,
                )
                if not page.rows:
                    if page.next_page_token is not None:
                        raise AlpacaDailyError(
                            "NO_PAGINATION_PROGRESS",
                            (capture,),
                        )
                    completion_reason = (
                        "data_unavailable"
                        if not rows_by_instant
                        else "provider_terminal"
                    )
                    return _collection(
                        scope,
                        rows_by_instant,
                        captures,
                        overlap_count,
                        completion_reason,
                    )
                new_count, new_overlaps = _merge_page(
                    page,
                    rows_by_instant,
                    capture,
                )
                overlap_count += new_overlaps
                if new_count == 0:
                    raise AlpacaDailyError(
                        "NO_PAGINATION_PROGRESS",
                        (capture,),
                    )
                if page.next_page_token is None:
                    return _collection(
                        scope,
                        rows_by_instant,
                        captures,
                        overlap_count,
                        "provider_terminal",
                    )
                if page.next_page_token in seen_page_tokens:
                    raise AlpacaDailyError(
                        "REPEATED_PAGE_TOKEN",
                        (capture,),
                    )
                if page_ordinal + 1 == page_limit:
                    raise AlpacaDailyError(
                        "PAGE_LIMIT_EXCEEDED",
                        (capture,),
                    )
                seen_page_tokens.add(page.next_page_token)
                requested_page_token = page.next_page_token
        except AlpacaDailyError as error:
            raise AlpacaDailyError(
                error.code,
                _combine_captures(tuple(captures), error.captures),
            ) from None
        except CollectorError as error:
            raise AlpacaDailyError(
                error.code,
                _combine_captures(tuple(captures), error.captures),
            ) from None
        except ReadOnlyBoundaryError as error:
            raise AlpacaDailyError(
                error.code,
                _combine_captures(tuple(captures), error.captures),
            ) from None

        raise AlpacaDailyError("COLLECTION_INCOMPLETE", tuple(captures))

    def _request_page(self, page_token: str | None) -> HttpResponse:
        try:
            response = self._transport.request_page(page_token)
        except ReadOnlyBoundaryError:
            raise
        except Exception:
            raise AlpacaDailyError("TRANSPORT_ERROR") from None
        if not isinstance(response, HttpResponse):
            raise AlpacaDailyError("INVALID_HTTP_RESPONSE")
        return response


def _valid_daily_scope(scope: object) -> bool:
    if not isinstance(scope, CollectionScope):
        return False
    duration = scope.end_at - scope.start_at
    return (
        scope.provider == "alpaca"
        and scope.feed in _ALLOWED_FEEDS
        and scope.interval == "1d"
        and scope.adjustment_mode in _ALLOWED_ADJUSTMENTS
        and scope.session_scope == "provider_all"
        and scope.instrument_id == scope.symbol
        and _US_SYMBOL.fullmatch(scope.symbol) is not None
        and scope.symbol != "000660"
        and _is_utc_midnight(scope.start_at)
        and _is_utc_midnight(scope.end_at)
        and duration >= timedelta(days=1)
    )


def _daily_url(scope: CollectionScope, page_token: str | None) -> str:
    if page_token is not None and not _valid_page_token(page_token):
        raise ReadOnlyBoundaryError("page_token_invalid")
    query = _daily_query(scope)
    if page_token is not None:
        query.append(("page_token", page_token))
    return (
        f"{_BASE_URL}/v2/stocks/{scope.symbol}/bars?"
        f"{urlencode(query)}"
    )


def _daily_query(scope: CollectionScope) -> list[tuple[str, str]]:
    first_session_midnight = _new_york_midnight_utc(scope.start_at.date())
    last_session_date = scope.end_at.date() - timedelta(days=1)
    last_session_midnight = _new_york_midnight_utc(last_session_date)
    return [
        ("timeframe", "1Day"),
        ("start", _format_utc(first_session_midnight)),
        ("end", _format_utc(last_session_midnight)),
        ("limit", "10000"),
        ("adjustment", scope.adjustment_mode),
        ("asof", "-"),
        ("feed", scope.feed),
        ("currency", "USD"),
        ("sort", "asc"),
    ]


def _exact_origin_and_path(parsed: object, scope: CollectionScope) -> bool:
    return (
        getattr(parsed, "scheme", None) == "https"
        and getattr(parsed, "netloc", None) == "data.alpaca.markets"
        and getattr(parsed, "path", None) == f"/v2/stocks/{scope.symbol}/bars"
        and not getattr(parsed, "fragment", None)
        and getattr(parsed, "username", None) is None
        and getattr(parsed, "password", None) is None
    )


def _capture_response(
    scope: CollectionScope,
    requested_page_token: str | None,
    response: HttpResponse,
    clock: Clock,
) -> RawHttpCapture:
    if (
        type(response.status) is not int
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
    ):
        raise AlpacaDailyError("INVALID_HTTP_RESPONSE")
    try:
        received_at = _utc_timestamp(clock)
    except CollectorError:
        raise AlpacaDailyError("CLOCK_INVALID") from None
    actual_url = _daily_url(scope, requested_page_token)
    url, query = _sanitized_capture_url_and_query(
        actual_url,
        requested_page_token,
    )
    headers = _capture_headers(response.headers)
    return RawHttpCapture(
        endpoint_id=_ENDPOINT_ID,
        method="GET",
        sanitized_url=url,
        query=query,
        status=response.status,
        headers=headers,
        received_at=received_at,
        body_base64=base64.b64encode(response.body).decode("ascii"),
        body_sha256=hashlib.sha256(response.body).hexdigest(),
    )


def _capture_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    captured: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise AlpacaDailyError("INVALID_HTTP_RESPONSE")
        normalized_name = name.lower()
        if normalized_name in captured:
            raise AlpacaDailyError("INVALID_HTTP_RESPONSE")
        if any(character in value for character in "\r\n\x00"):
            raise AlpacaDailyError("INVALID_HTTP_RESPONSE")
        if normalized_name in _ALLOWED_CAPTURE_HEADERS:
            captured[normalized_name] = value
    return tuple(sorted(captured.items()))


def _require_success(response: HttpResponse, capture: RawHttpCapture) -> None:
    if response.status in {401, 403}:
        raise AlpacaDailyError("SCOPE_ACCESS_DENIED", (capture,))
    if not 200 <= response.status < 300:
        raise AlpacaDailyError("HTTP_STATUS", (capture,))
    content_type = dict(capture.headers).get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise AlpacaDailyError("INVALID_CONTENT_TYPE", (capture,))


def _parse_page(
    body: bytes,
    scope: CollectionScope,
    capture: RawHttpCapture,
    capture_ordinal: int,
    provider_order_offset: int,
) -> _ParsedPage:
    try:
        value = _parse_json(body, capture)
    except CollectorError as error:
        raise AlpacaDailyError(error.code, error.captures) from None
    if not isinstance(value, dict):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    fields = frozenset(value)
    if (
        not _REQUIRED_RESPONSE_FIELDS.issubset(fields)
        or not fields.issubset(_REQUIRED_RESPONSE_FIELDS | _OPTIONAL_RESPONSE_FIELDS)
        or not isinstance(value["bars"], list)
        or len(value["bars"]) > _MAX_ROWS_PER_PAGE
        or not isinstance(value["symbol"], str)
    ):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    if value["symbol"] != scope.symbol:
        raise AlpacaDailyError("RESPONSE_SCOPE_MISMATCH", (capture,))
    currency = value.get("currency", "USD")
    if not isinstance(currency, str):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    if currency != "USD":
        raise AlpacaDailyError("RESPONSE_SCOPE_MISMATCH", (capture,))
    next_page_token = value["next_page_token"]
    if next_page_token is not None and not _valid_page_token(next_page_token):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))

    rows: list[AlpacaDailyBar] = []
    instants: list[datetime] = []
    for row_index, raw_row in enumerate(value["bars"]):
        row, instant = _parse_row(
            raw_row,
            scope,
            currency,
            capture,
            capture_ordinal,
            row_index,
            provider_order_offset + row_index,
        )
        rows.append(row)
        instants.append(instant)
    return _ParsedPage(tuple(rows), tuple(instants), next_page_token)


def _parse_row(
    value: object,
    scope: CollectionScope,
    currency: str,
    capture: RawHttpCapture,
    capture_ordinal: int,
    source_row_index: int,
    provider_order: int,
) -> tuple[AlpacaDailyBar, datetime]:
    if not isinstance(value, dict) or frozenset(value) != _BAR_FIELDS:
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    source_timestamp = value["t"]
    if not isinstance(source_timestamp, str):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    instant, session_date, bar_end_instant = _new_york_session(
        source_timestamp,
        capture,
    )
    numeric_fields = {
        name: _numeric_scalar(value[name], capture)
        for name in ("o", "h", "l", "c", "v", "n", "vw")
    }
    open_price = numeric_fields["o"]
    high_price = numeric_fields["h"]
    low_price = numeric_fields["l"]
    close_price = numeric_fields["c"]
    volume = numeric_fields["v"]
    trade_count = numeric_fields["n"]
    vwap = numeric_fields["vw"]
    if not _valid_bar_values(
        open_price[1],
        high_price[1],
        low_price[1],
        close_price[1],
        volume[1],
        trade_count[1],
        vwap[1],
    ):
        raise AlpacaDailyError("BAR_INVARIANT", (capture,))
    if not scope.start_at.date() <= session_date < scope.end_at.date():
        raise AlpacaDailyError("BAR_OUTSIDE_SCOPE", (capture,))
    try:
        received_at = _parse_timestamp(capture.received_at, capture)
    except CollectorError:
        raise AlpacaDailyError("CLOCK_INVALID", (capture,)) from None
    if received_at < bar_end_instant:
        raise AlpacaDailyError("BAR_NOT_COMPLETED", (capture,))

    occurrence = (capture.body_sha256, capture_ordinal, source_row_index)
    return (
        AlpacaDailyBar(
            source_timestamp=source_timestamp,
            normalized_instant=_format_utc(instant),
            bar_end=_format_utc(bar_end_instant),
            available_at=capture.received_at,
            open_price=open_price[0],
            high_price=high_price[0],
            low_price=low_price[0],
            close_price=close_price[0],
            volume=volume[0],
            trade_count=trade_count[0],
            vwap=vwap[0],
            currency=currency,
            source_body_sha256=capture.body_sha256,
            source_capture_ordinal=capture_ordinal,
            source_row_index=source_row_index,
            provider_order=provider_order,
            occurrences=(occurrence,),
        ),
        instant,
    )


def _new_york_session(
    value: object,
    capture: RawHttpCapture,
) -> tuple[datetime, date, datetime]:
    if not isinstance(value, str):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    try:
        instant = _parse_timestamp(value, capture)
        local = instant.astimezone(_NEW_YORK)
        if local.time().replace(tzinfo=None) != datetime_time(0, 0):
            raise ValueError
        session_date = local.date()
        expected = _new_york_midnight_utc(session_date)
        if instant != expected:
            raise ValueError
        bar_end = _new_york_midnight_utc(session_date + timedelta(days=1))
        return instant, session_date, bar_end
    except (CollectorError, ValueError, TypeError, OverflowError, OSError):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,)) from None


def _new_york_midnight_utc(session_date: date) -> datetime:
    return datetime.combine(
        session_date,
        datetime_time(0, 0),
        tzinfo=_NEW_YORK,
    ).astimezone(timezone.utc)


def _numeric_scalar(
    value: object,
    capture: RawHttpCapture,
) -> tuple[CanonicalScalar, Decimal]:
    try:
        scalar = _canonical_scalar(value)
        if scalar.kind != "json_number":
            raise CollectorError("INVALID_SCALAR")
        decimal = Decimal(scalar.text)
    except (CollectorError, InvalidOperation):
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,)) from None
    if not decimal.is_finite():
        raise AlpacaDailyError("INVALID_RESPONSE_SHAPE", (capture,))
    return scalar, decimal


def _valid_bar_values(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    trade_count: Decimal,
    vwap: Decimal,
) -> bool:
    return (
        low_price > 0
        and low_price <= open_price <= high_price
        and low_price <= close_price <= high_price
        and volume >= 0
        and trade_count >= 0
        and trade_count == trade_count.to_integral_value()
        and vwap > 0
    )


def _validate_page_order(
    page: _ParsedPage,
    previous_page_last: datetime | None,
    capture: RawHttpCapture,
) -> datetime | None:
    if not page.instants:
        return previous_page_last
    if any(
        current <= previous
        for previous, current in zip(page.instants, page.instants[1:], strict=False)
    ):
        raise AlpacaDailyError("PAGE_ORDER_INVALID", (capture,))
    if previous_page_last is not None and page.instants[0] < previous_page_last:
        raise AlpacaDailyError("PAGE_ORDER_INVALID", (capture,))
    return page.instants[-1]


def _merge_page(
    page: _ParsedPage,
    rows_by_instant: dict[datetime, AlpacaDailyBar],
    capture: RawHttpCapture,
) -> tuple[int, int]:
    new_count = 0
    overlap_count = 0
    for row, instant in zip(page.rows, page.instants, strict=True):
        existing = rows_by_instant.get(instant)
        if existing is None:
            rows_by_instant[instant] = row
            new_count += 1
            continue
        if not _same_observation(existing, row):
            raise AlpacaDailyError("CONFLICTING_DUPLICATE", (capture,))
        rows_by_instant[instant] = _append_occurrence(existing, row)
        overlap_count += 1
    return new_count, overlap_count


def _same_observation(left: AlpacaDailyBar, right: AlpacaDailyBar) -> bool:
    return (
        left.source_timestamp == right.source_timestamp
        and left.normalized_instant == right.normalized_instant
        and left.open_price == right.open_price
        and left.high_price == right.high_price
        and left.low_price == right.low_price
        and left.close_price == right.close_price
        and left.volume == right.volume
        and left.trade_count == right.trade_count
        and left.vwap == right.vwap
        and left.currency == right.currency
    )


def _append_occurrence(
    existing: AlpacaDailyBar,
    duplicate: AlpacaDailyBar,
) -> AlpacaDailyBar:
    return AlpacaDailyBar(
        source_timestamp=existing.source_timestamp,
        normalized_instant=existing.normalized_instant,
        bar_end=existing.bar_end,
        available_at=existing.available_at,
        open_price=existing.open_price,
        high_price=existing.high_price,
        low_price=existing.low_price,
        close_price=existing.close_price,
        volume=existing.volume,
        trade_count=existing.trade_count,
        vwap=existing.vwap,
        currency=existing.currency,
        source_body_sha256=existing.source_body_sha256,
        source_capture_ordinal=existing.source_capture_ordinal,
        source_row_index=existing.source_row_index,
        provider_order=existing.provider_order,
        occurrences=existing.occurrences + duplicate.occurrences,
    )


def _valid_page_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= _MAX_PAGE_TOKEN_LENGTH
        and not any(character in value for character in "\r\n\x00")
    )


def _is_utc_midnight(value: datetime) -> bool:
    return (
        value.utcoffset() == timedelta(0)
        and value.hour == 0
        and value.minute == 0
        and value.second == 0
        and value.microsecond == 0
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def _collection(
    scope: CollectionScope,
    rows_by_instant: dict[datetime, AlpacaDailyBar],
    captures: list[RawHttpCapture],
    overlap_count: int,
    completion_reason: str,
) -> AlpacaDailyCollection:
    return AlpacaDailyCollection(
        scope=scope,
        rows=tuple(
            rows_by_instant[instant] for instant in sorted(rows_by_instant)
        ),
        captures=tuple(captures),
        overlap_count=overlap_count,
        completion_reason=completion_reason,
    )


def _combine_captures(
    prior: tuple[RawHttpCapture, ...],
    current: tuple[RawHttpCapture, ...],
) -> tuple[RawHttpCapture, ...]:
    combined = list(prior)
    for capture in current:
        if capture not in combined:
            combined.append(capture)
    return tuple(combined)
