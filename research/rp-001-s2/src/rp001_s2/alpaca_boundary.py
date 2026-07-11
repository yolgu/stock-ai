"""Strict read-only Alpaca transport for one frozen minute-bar scope."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, build_opener

from rp001.toss_research_collector import HttpRequest, HttpResponse
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _Opener,
    _RejectRedirectHandler,
    _open_http_response,
)


_BASE_URL = "https://data.alpaca.markets"
_RESPONSE_LIMIT_BYTES = 16 * 1024 * 1024
_US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_ALLOWED_FEEDS = frozenset({"sip", "iex"})
_ALLOWED_ADJUSTMENTS = frozenset({"raw", "split"})
_HEADER_NAMES = frozenset(
    {"accept", "apca-api-key-id", "apca-api-secret-key"}
)


@dataclass(frozen=True, repr=False)
class AlpacaCredentialCapability:
    """One-shot credential authority for Alpaca market-data requests."""

    _key_id: str = field(repr=False)
    _secret_key: str = field(repr=False)

    @classmethod
    def consume(
        cls,
        environment: MutableMapping[str, str],
    ) -> AlpacaCredentialCapability:
        key_id = environment.pop("APCA_API_KEY_ID", None)
        secret_key = environment.pop("APCA_API_SECRET_KEY", None)
        try:
            if not _valid_credential(key_id) or not _valid_credential(secret_key):
                raise ReadOnlyBoundaryError("credential_environment_invalid")
            return cls(_key_id=key_id, _secret_key=secret_key)
        finally:
            key_id = None
            secret_key = None

    def __repr__(self) -> str:
        return "AlpacaCredentialCapability(<redacted>)"

    def _authorized_headers(self) -> Mapping[str, str]:
        return {
            "Accept": "application/json",
            "APCA-API-KEY-ID": self._key_id,
            "APCA-API-SECRET-KEY": self._secret_key,
        }

    def authorizes(self, headers: Mapping[str, str]) -> bool:
        if not isinstance(headers, Mapping):
            return False
        header_items: list[tuple[str, str]] = []
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                return False
            header_items.append((name.lower(), value))
        normalized = dict(header_items)
        return (
            len(header_items) == len(normalized)
            and set(normalized) == _HEADER_NAMES
            and normalized.get("accept") == "application/json"
            and normalized.get("apca-api-key-id") == self._key_id
            and normalized.get("apca-api-secret-key") == self._secret_key
        )

    def contains_sensitive(
        self,
        body: bytes,
        additional_values: Sequence[str] = (),
    ) -> bool:
        """Return only whether a body contains credentials or request-bound secrets."""
        return _body_contains_exact_values(
            body,
            (self._key_id, self._secret_key, *tuple(additional_values)),
        )


class StrictAlpacaBarsTransport:
    """Permit only exact single-symbol reads within one frozen Alpaca scope."""

    def __init__(
        self,
        *,
        opener: _Opener,
        scope: CollectionScope,
        credentials: AlpacaCredentialCapability,
    ) -> None:
        if not _valid_scope(scope) or not isinstance(
            credentials, AlpacaCredentialCapability
        ):
            raise ReadOnlyBoundaryError("allowed_scope_invalid")
        self._opener = opener
        self._scope = scope
        self._credentials = credentials

    def request_page(self, page_token: str | None = None) -> HttpResponse:
        """Read one page, with an opaque provider token only on later pages."""
        url = _bars_url(self._scope, page_token)
        request = HttpRequest(
            method="GET",
            url=url,
            headers=self._credentials._authorized_headers(),
        )
        return self(request)

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
            "alpaca_transport_error",
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
        if not _url_has_exact_origin_and_path(parsed, self._scope):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        expected_prefix = _query(self._scope)
        if query == expected_prefix:
            expected_url = _bars_url(self._scope, None)
        elif (
            len(query) == len(expected_prefix) + 1
            and query[:-1] == expected_prefix
            and query[-1][0] == "page_token"
            and _valid_page_token(query[-1][1])
        ):
            expected_url = _bars_url(self._scope, query[-1][1])
        else:
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        if request.url != expected_url or not self._credentials.authorizes(
            request.headers
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")


def build_live_strict_alpaca_transport(
    *,
    scope: CollectionScope,
    credentials: AlpacaCredentialCapability,
) -> StrictAlpacaBarsTransport:
    """Build the live Alpaca transport with redirects disabled."""
    return StrictAlpacaBarsTransport(
        opener=build_opener(_RejectRedirectHandler()),
        scope=scope,
        credentials=credentials,
    )


def _valid_credential(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in "\r\n\x00")
    )


def _valid_scope(scope: object) -> bool:
    if not isinstance(scope, CollectionScope):
        return False
    duration = scope.end_at - scope.start_at
    return (
        scope.provider == "alpaca"
        and scope.feed in _ALLOWED_FEEDS
        and scope.interval == "1m"
        and scope.adjustment_mode in _ALLOWED_ADJUSTMENTS
        and scope.session_scope == "provider_all"
        and scope.instrument_id == scope.symbol
        and _US_SYMBOL.fullmatch(scope.symbol) is not None
        and scope.symbol != "000660"
        and scope.start_at.utcoffset() == timedelta(0)
        and scope.end_at.utcoffset() == timedelta(0)
        and scope.start_at.second == 0
        and scope.start_at.microsecond == 0
        and scope.end_at.second == 0
        and scope.end_at.microsecond == 0
        and duration >= timedelta(minutes=1)
    )


def _bars_url(scope: CollectionScope, page_token: str | None) -> str:
    if page_token is not None and not _valid_page_token(page_token):
        raise ReadOnlyBoundaryError("page_token_invalid")
    query = _query(scope)
    if page_token is not None:
        query.append(("page_token", page_token))
    path = f"/v2/stocks/{scope.symbol}/bars"
    return f"{_BASE_URL}{path}?{urlencode(query)}"


def _query(scope: CollectionScope) -> list[tuple[str, str]]:
    return [
        ("timeframe", "1Min"),
        ("start", _format_utc(scope.start_at)),
        ("end", _format_utc(scope.end_at - timedelta(minutes=1))),
        ("limit", "10000"),
        ("adjustment", scope.adjustment_mode),
        ("asof", "-"),
        ("feed", scope.feed),
        ("currency", "USD"),
        ("sort", "asc"),
    ]


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def _valid_page_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 4096
        and not any(character in value for character in "\r\n\x00")
    )


def _sanitized_capture_url_and_query(
    actual_url: str,
    page_token: str | None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    parsed = urlsplit(actual_url)
    query = list(
        parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    )
    if page_token is not None:
        if not query or query[-1] != ("page_token", page_token):
            raise ReadOnlyBoundaryError("capture_cursor_binding_invalid")
        cursor_sha256 = hashlib.sha256(page_token.encode("utf-8")).hexdigest()
        query[-1] = ("page_token_sha256", cursor_sha256)
    sanitized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(query)}"
    return sanitized_url, tuple(query)


def _page_token_from_url(url: str) -> str | None:
    query = parse_qsl(
        urlsplit(url).query,
        keep_blank_values=True,
        strict_parsing=True,
    )
    return next((value for name, value in query if name == "page_token"), None)


def _body_contains_exact_values(
    body: object,
    sensitive_values: Sequence[str],
) -> bool:
    if not isinstance(body, bytes):
        return True
    values = tuple(
        value
        for value in sensitive_values
        if isinstance(value, str) and value
    )
    if any(value.encode("utf-8") in body for value in values):
        return True
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return False
    pending: list[object] = [decoded]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if any(secret in key for secret in values):
                    return True
                pending.append(value)
            continue
        if isinstance(current, list):
            pending.extend(current)
            continue
        if isinstance(current, str) and any(
            secret in current for secret in values
        ):
            return True
    return False


def _url_has_exact_origin_and_path(
    parsed: object,
    scope: CollectionScope,
) -> bool:
    return (
        getattr(parsed, "scheme", None) == "https"
        and getattr(parsed, "netloc", None) == "data.alpaca.markets"
        and getattr(parsed, "path", None) == f"/v2/stocks/{scope.symbol}/bars"
        and not getattr(parsed, "fragment", None)
        and getattr(parsed, "username", None) is None
        and getattr(parsed, "password", None) is None
    )
