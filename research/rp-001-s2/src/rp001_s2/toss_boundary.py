"""Strict read-only Toss transport for RP-001-S2 research inputs."""

from __future__ import annotations

import json
import hashlib
import os
import time
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from rp001.toss_research_collector import (
    CollectorError,
    CombinedCandleCollection,
    HttpRequest,
    HttpResponse,
    MetadataCollection,
    RawHttpCapture,
    TossResearchCollector,
)


_OAUTH_URL = "https://openapi.tossinvest.com/oauth2/token"
_STOCKS_URL = "https://openapi.tossinvest.com/api/v1/stocks"
_TIMEOUT_SECONDS = 30.0
_AUTH_RESPONSE_LIMIT_BYTES = 1024 * 1024
_METADATA_RESPONSE_LIMIT_BYTES = 2 * 1024 * 1024
_CANDLE_RESPONSE_LIMIT_BYTES = 8 * 1024 * 1024
_MINIMUM_REQUEST_INTERVAL_SECONDS = 0.21


class _Opener(Protocol):
    def open(self, request: Request, timeout: float) -> object:
        """Open one HTTP request."""


class ReadOnlyBoundaryError(ValueError):
    """Sanitized failure at the read-only market-data boundary."""

    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class TossCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)

    def __repr__(self) -> str:
        return "TossCredentials(<redacted>)"


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


class StrictMetadataTransport:
    """Allow only one exact GET request for the frozen metadata pool."""

    def __init__(
        self,
        *,
        opener: _Opener,
        allowed_symbols: Sequence[str],
    ) -> None:
        self._opener = opener
        self._allowed_symbols = tuple(allowed_symbols)
        if not self._allowed_symbols or len(set(self._allowed_symbols)) != len(
            self._allowed_symbols
        ):
            raise ReadOnlyBoundaryError("allowed_symbols_invalid")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._validate_request(request)
        outgoing = Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        return _open_http_response(
            self._opener,
            outgoing,
            _METADATA_RESPONSE_LIMIT_BYTES,
            "metadata_transport_error",
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
        except ValueError:
            raise ReadOnlyBoundaryError("endpoint_not_allowed") from None
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.tossinvest.com"
            or parsed.path != "/api/v1/stocks"
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or query != [("symbols", ",".join(self._allowed_symbols))]
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        headers = {name.lower(): value for name, value in request.headers.items()}
        authorization = headers.get("authorization")
        if (
            set(headers) != {"accept", "authorization"}
            or headers.get("accept") != "application/json"
            or not isinstance(authorization, str)
            or not authorization.startswith("Bearer ")
            or authorization == "Bearer "
            or any(character in authorization for character in "\r\n\x00")
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")


class StrictCandleTransport:
    """Allow only frozen daily-candle GET requests for one sample role."""

    def __init__(
        self,
        *,
        opener: _Opener,
        allowed_symbols: Sequence[str],
        request_pacer: Callable[[], None] | None = None,
    ) -> None:
        self._opener = opener
        self._allowed_symbols = frozenset(allowed_symbols)
        self._request_pacer = request_pacer or _MinimumIntervalPacer()
        if not self._allowed_symbols:
            raise ReadOnlyBoundaryError("allowed_symbols_invalid")

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
            "candle_transport_error",
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
        except ValueError:
            raise ReadOnlyBoundaryError("endpoint_not_allowed") from None
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.tossinvest.com"
            or parsed.path != "/api/v1/candles"
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or len(query) != 5
            or tuple(name for name, _value in query)
            != ("symbol", "interval", "count", "adjusted", "before")
            or query[0][1] not in self._allowed_symbols
            or query[1][1] != "1d"
            or query[2][1] != "200"
            or query[3][1] not in {"true", "false"}
            or not query[4][1]
            or len(query[4][1]) > 2048
            or any(character in query[4][1] for character in "\r\n\x00")
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")
        headers = {name.lower(): value for name, value in request.headers.items()}
        authorization = headers.get("authorization")
        if (
            set(headers) != {"accept", "authorization"}
            or headers.get("accept") != "application/json"
            or not isinstance(authorization, str)
            or not authorization.startswith("Bearer ")
            or authorization == "Bearer "
            or any(character in authorization for character in "\r\n\x00")
        ):
            raise ReadOnlyBoundaryError("endpoint_not_allowed")


class _MinimumIntervalPacer:
    def __init__(self) -> None:
        self._last_request_at: float | None = None

    def __call__(self) -> None:
        while True:
            now = time.monotonic()
            if self._last_request_at is None:
                self._last_request_at = now
                return
            remaining = _MINIMUM_REQUEST_INTERVAL_SECONDS - (
                now - self._last_request_at
            )
            if remaining <= 1e-9:
                self._last_request_at = now
                return
            time.sleep(remaining)


def load_credentials(
    environment: MutableMapping[str, str],
) -> TossCredentials:
    """Consume credentials from the one-shot process environment."""
    client_id = environment.pop("TOSS_CLIENT_ID", None)
    client_secret = environment.pop("TOSS_CLIENT_SECRET", None)
    try:
        if (
            not isinstance(client_id, str)
            or not client_id
            or not isinstance(client_secret, str)
            or not client_secret
            or any(character in client_id for character in "\r\n\x00")
            or any(character in client_secret for character in "\r\n\x00")
        ):
            raise ReadOnlyBoundaryError("credential_environment_invalid")
        return TossCredentials(client_id=client_id, client_secret=client_secret)
    finally:
        client_id = None
        client_secret = None


def run_metadata_request(
    *,
    symbols: Sequence[str],
    opener: _Opener | None = None,
    clock: Callable[[], datetime],
    environment: MutableMapping[str, str] | None = None,
) -> MetadataCollection:
    """Authenticate ephemerally and perform exactly one stock-metadata GET."""
    credentials = load_credentials(environment if environment is not None else os.environ)
    effective_opener = opener or build_opener(_RejectRedirectHandler())
    ephemeral_token = ""
    try:
        ephemeral_token = _authenticate(effective_opener, credentials, clock)
        transport = StrictMetadataTransport(
            opener=effective_opener,
            allowed_symbols=symbols,
        )
        collector = TossResearchCollector(
            transport=transport,
            token_supplier=lambda: ephemeral_token,
            clock=clock,
        )
        return collector.collect_metadata(tuple(symbols))
    except ReadOnlyBoundaryError:
        raise
    except CollectorError as error:
        raise ReadOnlyBoundaryError(error.code, error.captures) from None
    except Exception as error:
        code = getattr(error, "code", "metadata_collection_failed")
        raise ReadOnlyBoundaryError(str(code)) from None
    finally:
        ephemeral_token = ""


def run_candle_request(
    *,
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    initial_before: str,
    opener: _Opener | None = None,
    clock: Callable[[], datetime],
    environment: MutableMapping[str, str] | None = None,
    request_pacer: Callable[[], None] | None = None,
) -> tuple[CombinedCandleCollection, ...]:
    """Collect adjusted and native daily candles for one frozen symbol set."""
    credentials = load_credentials(environment if environment is not None else os.environ)
    effective_opener = opener or build_opener(_RejectRedirectHandler())
    ephemeral_token = ""
    try:
        ephemeral_token = _authenticate(effective_opener, credentials, clock)
        transport = StrictCandleTransport(
            opener=effective_opener,
            allowed_symbols=symbols,
            request_pacer=request_pacer,
        )
        collector = TossResearchCollector(
            transport=transport,
            token_supplier=lambda: ephemeral_token,
            clock=clock,
        )
        return tuple(
            collector.collect_adjusted_native(
                symbol,
                start_date,
                end_date,
                initial_before,
            )
            for symbol in symbols
        )
    except ReadOnlyBoundaryError:
        raise
    except CollectorError as error:
        raise ReadOnlyBoundaryError(error.code, error.captures) from None
    except Exception as error:
        code = getattr(error, "code", "candle_collection_failed")
        raise ReadOnlyBoundaryError(str(code)) from None
    finally:
        ephemeral_token = ""


def _authenticate(
    opener: _Opener,
    credentials: TossCredentials,
    clock: Callable[[], datetime],
) -> str:
    body = urlencode(
        (
            ("grant_type", "client_credentials"),
            ("client_id", credentials.client_id),
            ("client_secret", credentials.client_secret),
        )
    ).encode("ascii")
    request = Request(
        _OAUTH_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    response = _open_http_response(
        opener,
        request,
        _AUTH_RESPONSE_LIMIT_BYTES,
        "authentication_transport_error",
    )
    if not 200 <= response.status < 300:
        raise ReadOnlyBoundaryError(
            "authentication_http_status",
            (_oauth_failure_capture(response, clock),),
        )
    try:
        value = json.loads(response.body.decode("utf-8"))
    except Exception:
        raise ReadOnlyBoundaryError(
            "authentication_response_invalid",
            (_oauth_failure_capture(response, clock),),
        ) from None
    token = value.get("access_token") if isinstance(value, dict) else None
    if (
        not isinstance(token, str)
        or not token
        or any(character in token for character in "\r\n\x00")
    ):
        raise ReadOnlyBoundaryError(
            "authentication_response_invalid",
            (_oauth_failure_capture(response, clock),),
        )
    return token


def _oauth_failure_capture(
    response: HttpResponse,
    clock: Callable[[], datetime],
) -> RawHttpCapture:
    received = clock()
    if not isinstance(received, datetime) or received.tzinfo is None:
        raise ReadOnlyBoundaryError("clock_invalid")
    timestamp = received.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    allowed_headers = {
        "content-type",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
    headers = tuple(
        sorted(
            (name.lower(), value)
            for name, value in response.headers.items()
            if name.lower() in allowed_headers
            and isinstance(value, str)
            and not any(character in value for character in "\r\n\x00")
        )
    )
    return RawHttpCapture(
        endpoint_id="oauth_client_credentials_v1",
        method="POST",
        sanitized_url=_OAUTH_URL,
        query=(),
        status=response.status,
        headers=headers,
        received_at=timestamp,
        body_base64="",
        body_sha256=hashlib.sha256(response.body).hexdigest(),
    )


def _open_http_response(
    opener: _Opener,
    request: Request,
    limit: int,
    error_code: str,
) -> HttpResponse:
    try:
        received = opener.open(request, timeout=_TIMEOUT_SECONDS)
    except HTTPError as error:
        received = error
    except Exception:
        raise ReadOnlyBoundaryError(error_code) from None
    try:
        status = getattr(received, "status", getattr(received, "code", None))
        headers_value = getattr(received, "headers", None)
        if not isinstance(status, int) or headers_value is None:
            raise ReadOnlyBoundaryError(error_code)
        headers = dict(headers_value.items())
        body = _read_stream_limited(received, limit, error_code)
        return HttpResponse(status=status, headers=headers, body=body)
    finally:
        close = getattr(received, "close", None)
        if callable(close):
            close()


def _read_stream_limited(stream: object, limit: int, error_code: str) -> bytes:
    read = getattr(stream, "read", None)
    if not callable(read):
        raise ReadOnlyBoundaryError(error_code)
    try:
        source = read(limit + 1)
    except Exception:
        raise ReadOnlyBoundaryError(error_code) from None
    if not isinstance(source, bytes) or len(source) > limit:
        raise ReadOnlyBoundaryError(f"{error_code}_response_too_large")
    return source
