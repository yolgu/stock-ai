"""Secure execution boundary for frozen Toss one-minute collection scopes."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, MutableMapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn
from urllib.request import build_opener

from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.archive_contract import (
    TOSS_PROVIDER_DATE_DAILY_FEED,
    CollectionScope,
    is_supported_toss_minute_scope,
)
from rp001_s2.intraday_boundary import StrictMinuteCandleTransport
from rp001_s2.intraday_measurement import (
    IntradayCandleCollection,
    IntradayMeasurementCollector,
    MeasurementError,
)
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _Opener,
    _RejectRedirectHandler,
    _authenticate,
    load_credentials,
)


_MAX_CREDENTIAL_FILE_BYTES = 64 * 1024
_SHARD_DURATION = timedelta(days=7)


class IntradayRunError(ValueError):
    """Sanitized failure from a Toss intraday acquisition boundary."""

    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


class _DuplicateCredentialKey(ValueError):
    pass


class TossMinuteSession:
    """Reuse one ephemeral Toss token across a bounded minute batch."""

    def __init__(
        self,
        *,
        opener: _Opener,
        token: str,
        clock: Callable[[], datetime],
    ) -> None:
        if not token or any(character in token for character in "\r\n\x00"):
            raise IntradayRunError("session_invalid")
        self._opener = opener
        self._token = token
        self._clock = clock

    def __repr__(self) -> str:
        return "TossMinuteSession(<redacted>)"

    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: Callable[[], None] | None = None,
    ) -> IntradayCandleCollection:
        if not self._token:
            raise IntradayRunError("session_closed")
        adjusted = validate_toss_minute_scope(scope)
        initial_before = _format_utc(_initial_before(scope))
        try:
            transport = StrictMinuteCandleTransport(
                opener=self._opener,
                allowed_symbols=(scope.symbol,),
                earliest_before=_format_utc(scope.start_at),
                initial_before=initial_before,
                request_pacer=request_pacer,
            )
            collector = IntradayMeasurementCollector(
                transport=transport,
                token_supplier=lambda: self._token,
                clock=self._clock,
            )
            return collector.collect_candles(
                symbol=scope.symbol,
                interval="1m",
                adjusted=adjusted,
                start_at=_format_utc(scope.start_at),
                end_at=_format_utc(scope.end_at),
                initial_before=initial_before,
                count=200,
                page_limit=64,
            )
        except (ReadOnlyBoundaryError, MeasurementError) as error:
            raise IntradayRunError(error.code, captures=error.captures) from None

    def close(self) -> None:
        self._token = ""


def load_secure_toss_environment(path: Path) -> dict[str, str]:
    """Read a private regular file into a one-shot credential environment."""
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_size > _MAX_CREDENTIAL_FILE_BYTES
        ):
            raise IntradayRunError("credential_file_invalid")
        source = _read_bounded(descriptor)
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except IntradayRunError:
        raise
    except Exception:
        raise IntradayRunError("credential_file_invalid") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if not isinstance(value, dict):
        raise IntradayRunError("credential_file_invalid")
    client_id = value.get("clientId")
    client_secret = value.get("clientSecret")
    if not _valid_secret(client_id) or not _valid_secret(client_secret):
        raise IntradayRunError("credential_file_invalid")
    return {
        "TOSS_CLIENT_ID": client_id,
        "TOSS_CLIENT_SECRET": client_secret,
    }


def open_toss_minute_session(
    *,
    environment: MutableMapping[str, str],
    clock: Callable[[], datetime],
    opener: _Opener | None = None,
) -> TossMinuteSession:
    """Authenticate once and return a redacted, explicitly closable session."""
    credentials = load_credentials(environment)
    effective_opener = opener or build_opener(_RejectRedirectHandler())
    try:
        token = _authenticate(effective_opener, credentials, clock)
        return TossMinuteSession(
            opener=effective_opener,
            token=token,
            clock=clock,
        )
    except ReadOnlyBoundaryError as error:
        raise IntradayRunError(error.code, captures=error.captures) from None


def seven_day_shards(scope: CollectionScope) -> tuple[CollectionScope, ...]:
    """Partition one frozen acquisition scope without changing its role."""
    cursor = scope.start_at
    shards: list[CollectionScope] = []
    while cursor < scope.end_at:
        shard_end = min(cursor + _SHARD_DURATION, scope.end_at)
        shards.append(replace(scope, start_at=cursor, end_at=shard_end))
        cursor = shard_end
    return tuple(shards)


def run_toss_minute_shard(
    scope: CollectionScope,
    *,
    environment: MutableMapping[str, str],
    clock: Callable[[], datetime],
    opener: _Opener | None = None,
    request_pacer: Callable[[], None] | None = None,
) -> IntradayCandleCollection:
    """Authenticate ephemerally and exhaust one bounded Toss minute shard."""
    validate_toss_minute_scope(scope)
    session = open_toss_minute_session(
        environment=environment,
        clock=clock,
        opener=opener,
    )
    try:
        return session.collect(
            scope,
            request_pacer=request_pacer,
        )
    finally:
        session.close()


def validate_toss_minute_scope(scope: CollectionScope) -> bool:
    """Validate the Toss minute identity before credentials or network access."""
    if not is_supported_toss_minute_scope(scope):
        raise IntradayRunError("scope_not_allowed")
    return scope.adjustment_mode == "adjusted"


def _initial_before(scope: CollectionScope) -> datetime:
    if scope.feed == TOSS_PROVIDER_DATE_DAILY_FEED:
        return scope.end_at - timedelta(minutes=1)
    return scope.end_at


def _read_bounded(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = _MAX_CREDENTIAL_FILE_BYTES + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(remaining, 16 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    source = b"".join(chunks)
    if len(source) > _MAX_CREDENTIAL_FILE_BYTES:
        raise IntradayRunError("credential_file_invalid")
    return source


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateCredentialKey()
        value[key] = item
    return value


def _reject_json_constant(_: str) -> NoReturn:
    raise _DuplicateCredentialKey()


def _valid_secret(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(character in value for character in "\r\n\x00")
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
