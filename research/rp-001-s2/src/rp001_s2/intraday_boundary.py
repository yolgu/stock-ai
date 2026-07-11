"""Strict network boundary for the frozen RP-001-S2 intraday probe."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, build_opener

from rp001.toss_research_collector import HttpRequest, HttpResponse
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _CANDLE_RESPONSE_LIMIT_BYTES,
    _MinimumIntervalPacer,
    _Opener,
    _RejectRedirectHandler,
    _open_http_response,
)


class StrictMinuteCandleTransport:
    """Permit only frozen, bounded 1m candle reads."""

    def __init__(
        self,
        *,
        opener: _Opener,
        allowed_symbols: Sequence[str],
        earliest_before: str,
        initial_before: str,
        request_pacer: Callable[[], None] | None = None,
    ) -> None:
        self._opener = opener
        self._symbols = frozenset(allowed_symbols)
        self._earliest = _instant(earliest_before)
        self._latest = _instant(initial_before)
        self._pacer = request_pacer or _MinimumIntervalPacer()
        if not self._symbols or self._earliest > self._latest:
            raise ReadOnlyBoundaryError("allowed_scope_invalid")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._validate(request)
        self._pacer()
        outgoing = Request(request.url, headers=dict(request.headers), method="GET")
        return _open_http_response(
            self._opener,
            outgoing,
            _CANDLE_RESPONSE_LIMIT_BYTES,
            "intraday_transport_error",
        )

    def _validate(self, request: HttpRequest) -> None:
        if not isinstance(request, HttpRequest) or request.method != "GET":
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        try:
            parsed = urlsplit(request.url)
            query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise ReadOnlyBoundaryError("endpoint_not_allowed") from None
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.tossinvest.com"
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        allowed = parsed.path == "/api/v1/candles" and self._valid_candle_query(query)
        if not allowed:
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        header_items = [(name.lower(), value) for name, value in request.headers.items()]
        headers = dict(header_items)
        authorization = headers.get("authorization")
        if (
            len(header_items) != len(headers)
            or set(headers) != {"accept", "authorization"}
            or headers.get("accept") != "application/json"
            or not isinstance(authorization, str)
            or not authorization.startswith("Bearer ")
            or authorization == "Bearer "
            or any(character in authorization for character in "\r\n\x00")
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")

    def _valid_candle_query(self, query: list[tuple[str, str]]) -> bool:
        if (
            len(query) != 5
            or tuple(name for name, _ in query)
            != ("symbol", "interval", "count", "adjusted", "before")
            or query[0][1] not in self._symbols
            or query[1][1] != "1m"
            or query[2][1] != "200"
            or query[3][1] not in {"true", "false"}
        ):
            return False
        try:
            before = _instant(query[4][1])
        except ReadOnlyBoundaryError:
            return False
        return self._earliest <= before <= self._latest


def build_live_strict_minute_transport(
    *,
    allowed_symbols: Sequence[str],
    earliest_before: str,
    initial_before: str,
    request_pacer: Callable[[], None] | None = None,
) -> StrictMinuteCandleTransport:
    """Build the only live transport path with redirects rejected."""
    return StrictMinuteCandleTransport(
        opener=build_opener(_RejectRedirectHandler()),
        allowed_symbols=allowed_symbols,
        earliest_before=earliest_before,
        initial_before=initial_before,
        request_pacer=request_pacer,
    )


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        raise ReadOnlyBoundaryError("allowed_scope_invalid") from None
