"""Secure one-shot execution of sampled Toss trade and orderbook captures."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from urllib.request import build_opener

from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    _Opener,
    _RejectRedirectHandler,
    _authenticate,
    load_credentials,
)
from rp001_s2.toss_forward_archive import (
    ForwardArchiveError,
    FreeBytes,
    ImmutableTossForwardStorage,
    StoredForwardArchive,
    StoredForwardFailureEvidence,
    StoredForwardTradeArchive,
)
from rp001_s2.toss_forward_microstructure import (
    ForwardMicrostructureError,
    SampledOrderbookSnapshot,
    SampledTradeStream,
    StrictTossForwardTransport,
    TossForwardMicrostructureCollector,
)
from rp001_s2.toss_intraday_run import (
    IntradayRunError,
    load_secure_toss_environment,
)


class TossForwardCaptureRunError(ValueError):
    """Sanitized failure from the forward capture execution boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ForwardCaptureStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, repr=False)
class TossForwardCaptureArguments:
    credential_file: Path = field(repr=False)
    storage_root: Path
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.credential_file, Path)
            or not isinstance(self.storage_root, Path)
            or type(self.symbols) is not tuple
            or not self.symbols
        ):
            raise TossForwardCaptureRunError("forward_capture_arguments_invalid")

    def __repr__(self) -> str:
        return (
            "TossForwardCaptureArguments(credential_file=<redacted>, "
            f"storage_root={self.storage_root!r}, symbols={self.symbols!r})"
        )


@dataclass(frozen=True)
class TossForwardSymbolOutcome:
    symbol: str
    status: ForwardCaptureStatus
    stored_archive: StoredForwardArchive | None = None
    failure_evidence: StoredForwardFailureEvidence | None = None
    error_code: str | None = None
    trade_archive: StoredForwardTradeArchive | None = None
    trade_row_count: int = 0
    orderbook_error_code: str | None = None


@dataclass(frozen=True)
class TossForwardCaptureResult:
    outcomes: tuple[TossForwardSymbolOutcome, ...]


def run_toss_forward_capture(
    arguments: TossForwardCaptureArguments,
    *,
    clock: Callable[[], datetime],
    opener: _Opener | None = None,
    request_pacer: Callable[[], None] | None = None,
    free_bytes: FreeBytes | None = None,
) -> TossForwardCaptureResult:
    """Authenticate once, then sample one trade page and one book per symbol."""
    if not isinstance(arguments, TossForwardCaptureArguments) or not callable(clock):
        raise TossForwardCaptureRunError("forward_capture_arguments_invalid")
    effective_opener = opener or build_opener(_RejectRedirectHandler())
    try:
        transport = StrictTossForwardTransport(
            opener=effective_opener,
            allowed_symbols=arguments.symbols,
            request_pacer=request_pacer,
        )
        storage = ImmutableTossForwardStorage(
            arguments.storage_root,
            free_bytes=free_bytes,
        )
    except ReadOnlyBoundaryError as error:
        raise TossForwardCaptureRunError(error.code) from None
    except ForwardArchiveError as error:
        raise TossForwardCaptureRunError(error.code) from None

    environment: dict[str, str] | None = None
    credentials = None
    token = ""
    sensitive_values: tuple[str, ...] = ()
    try:
        try:
            environment = load_secure_toss_environment(
                arguments.credential_file
            )
            credentials = load_credentials(environment)
            sensitive_values = (
                credentials.client_id,
                credentials.client_secret,
            )
            token = _authenticate(effective_opener, credentials, clock)
            sensitive_values = (*sensitive_values, token)
        except (IntradayRunError, ReadOnlyBoundaryError) as error:
            captures = getattr(error, "captures", ())
            return _failed_result_for_all_symbols(
                storage,
                arguments.symbols,
                error.code,
                captures,
                sensitive_values,
            )

        collector = TossForwardMicrostructureCollector(
            transport=transport,
            token_supplier=lambda: token,
            clock=clock,
        )
        outcomes = tuple(
            _capture_symbol(
                storage,
                collector,
                symbol,
                sensitive_values,
            )
            for symbol in arguments.symbols
        )
        return TossForwardCaptureResult(outcomes=outcomes)
    except ForwardArchiveError as error:
        raise TossForwardCaptureRunError(error.code) from None
    finally:
        if environment is not None:
            environment.clear()
        sensitive_values = ()
        token = ""
        credentials = None


def _capture_symbol(
    storage: ImmutableTossForwardStorage,
    collector: TossForwardMicrostructureCollector,
    symbol: str,
    sensitive_values: tuple[str, ...],
) -> TossForwardSymbolOutcome:
    safe_captures: tuple[RawHttpCapture, ...] = ()
    trade_stream: SampledTradeStream | None = None
    trade_archive: StoredForwardTradeArchive | None = None
    orderbook_snapshot: SampledOrderbookSnapshot | None = None
    trade_error_code: str | None = None
    orderbook_error_code: str | None = None
    orderbook_failure_captures: tuple[RawHttpCapture, ...] = ()
    try:
        trade_stream = collector.collect_trade_polls(
            symbol=symbol,
            poll_count=1,
        )
        safe_captures = _require_safe_captures(
            trade_stream.captures,
            sensitive_values,
            prior=(),
        )
        trade_archive = storage.write_trade_archive(trade_stream)
    except _SensitiveResponseMaterial:
        if trade_archive is not None and trade_stream is not None:
            return _partial_outcome(
                storage,
                symbol,
                trade_archive,
                len(trade_stream.observations),
                "sensitive_response_material",
                (),
            )
        return _failure_outcome(
            storage,
            symbol,
            "sensitive_response_material",
            (),
        )
    except ForwardMicrostructureError as error:
        trade_error_code = error.code
        try:
            safe_captures = _require_safe_captures(
                _combine_captures(safe_captures, error.captures),
                sensitive_values,
                prior=(),
            )
        except _SensitiveResponseMaterial:
            return _failure_outcome(
                storage,
                symbol,
                "sensitive_response_material",
                (),
            )

    try:
        orderbook_snapshot = collector.poll_orderbook(
            symbol=symbol,
            capture_ordinal=len(safe_captures),
        )
        safe_captures = _require_safe_captures(
            (orderbook_snapshot.capture,),
            sensitive_values,
            prior=safe_captures,
        )
    except _SensitiveResponseMaterial:
        if trade_archive is not None and trade_stream is not None:
            return _partial_outcome(
                storage,
                symbol,
                trade_archive,
                len(trade_stream.observations),
                "sensitive_response_material",
                (),
            )
        return _failure_outcome(
            storage,
            symbol,
            "sensitive_response_material",
            (),
        )
    except ForwardMicrostructureError as error:
        orderbook_error_code = error.code
        if trade_archive is not None and trade_stream is not None:
            try:
                orderbook_failure_captures = _require_safe_captures(
                    error.captures,
                    sensitive_values,
                    prior=(),
                )
            except _SensitiveResponseMaterial:
                return _partial_outcome(
                    storage,
                    symbol,
                    trade_archive,
                    len(trade_stream.observations),
                    "sensitive_response_material",
                    (),
                )
        else:
            try:
                safe_captures = _require_safe_captures(
                    _combine_captures(safe_captures, error.captures),
                    sensitive_values,
                    prior=(),
                )
            except _SensitiveResponseMaterial:
                return _failure_outcome(
                    storage,
                    symbol,
                    "sensitive_response_material",
                    (),
                )

    if trade_error_code is not None:
        return _failure_outcome(
            storage,
            symbol,
            trade_error_code,
            safe_captures,
        )
    if orderbook_error_code is not None:
        if trade_stream is None or trade_archive is None:
            return _failure_outcome(
                storage,
                symbol,
                "forward_capture_incomplete",
                safe_captures,
            )
        return _partial_outcome(
            storage,
            symbol,
            trade_archive,
            len(trade_stream.observations),
            orderbook_error_code,
            orderbook_failure_captures,
        )
    if (
        trade_stream is None
        or trade_archive is None
        or orderbook_snapshot is None
    ):
        return _failure_outcome(
            storage,
            symbol,
            "forward_capture_incomplete",
            safe_captures,
        )
    stored = storage.write_archive(
        trade_stream=trade_stream,
        orderbook_snapshot=orderbook_snapshot,
    )
    return TossForwardSymbolOutcome(
        symbol=symbol,
        status=ForwardCaptureStatus.COMPLETED,
        stored_archive=stored,
        trade_archive=trade_archive,
        trade_row_count=len(trade_stream.observations),
    )


def _failed_result_for_all_symbols(
    storage: ImmutableTossForwardStorage,
    symbols: tuple[str, ...],
    error_code: str,
    captures: object,
    sensitive_values: tuple[str, ...],
) -> TossForwardCaptureResult:
    safe_captures = (
        captures
        if type(captures) is tuple
        and all(isinstance(capture, RawHttpCapture) for capture in captures)
        else ()
    )
    try:
        safe_captures = _require_safe_captures(
            safe_captures,
            sensitive_values,
            prior=(),
        )
    except _SensitiveResponseMaterial:
        safe_captures = ()
        error_code = "sensitive_response_material"
    return TossForwardCaptureResult(
        outcomes=tuple(
            _failure_outcome(
                storage,
                symbol,
                error_code,
                safe_captures,
            )
            for symbol in symbols
        )
    )


def _failure_outcome(
    storage: ImmutableTossForwardStorage,
    symbol: str,
    error_code: str,
    captures: tuple[RawHttpCapture, ...],
) -> TossForwardSymbolOutcome:
    failure_evidence = storage.write_failure_evidence(
        symbol=symbol,
        error_code=error_code,
        captures=captures,
    )
    return TossForwardSymbolOutcome(
        symbol=symbol,
        status=ForwardCaptureStatus.FAILED,
        failure_evidence=failure_evidence,
        error_code=error_code,
    )


def _partial_outcome(
    storage: ImmutableTossForwardStorage,
    symbol: str,
    trade_archive: StoredForwardTradeArchive,
    trade_row_count: int,
    orderbook_error_code: str,
    captures: tuple[RawHttpCapture, ...],
) -> TossForwardSymbolOutcome:
    failure_evidence = storage.write_failure_evidence(
        symbol=symbol,
        error_code=orderbook_error_code,
        captures=captures,
    )
    return TossForwardSymbolOutcome(
        symbol=symbol,
        status=ForwardCaptureStatus.PARTIAL,
        trade_archive=trade_archive,
        failure_evidence=failure_evidence,
        error_code=orderbook_error_code,
        trade_row_count=trade_row_count,
        orderbook_error_code=orderbook_error_code,
    )


class _SensitiveResponseMaterial(ValueError):
    def __init__(self, safe_captures: tuple[RawHttpCapture, ...]) -> None:
        self.safe_captures = safe_captures
        super().__init__("sensitive_response_material")


def _require_safe_captures(
    captures: tuple[RawHttpCapture, ...],
    sensitive_values: tuple[str, ...],
    *,
    prior: tuple[RawHttpCapture, ...],
) -> tuple[RawHttpCapture, ...]:
    safe = list(prior)
    for capture in captures:
        if _capture_contains_sensitive_material(capture, sensitive_values):
            raise _SensitiveResponseMaterial(tuple(safe))
        if capture not in safe:
            safe.append(capture)
    return tuple(safe)


def _capture_contains_sensitive_material(
    capture: RawHttpCapture,
    sensitive_values: tuple[str, ...],
) -> bool:
    values = tuple(value for value in sensitive_values if value)
    if not values:
        return False
    metadata = (
        capture.endpoint_id,
        capture.method,
        capture.sanitized_url,
        capture.received_at,
        *(name for name, _value in capture.query),
        *(value for _name, value in capture.query),
        *(name for name, _value in capture.headers),
        *(value for _name, value in capture.headers),
    )
    if any(secret in value for secret in values for value in metadata):
        return True
    if (
        capture.endpoint_id == "oauth_client_credentials_v1"
        and capture.body_base64 == ""
    ):
        return False
    try:
        body = base64.b64decode(capture.body_base64, validate=True)
    except (TypeError, ValueError):
        return True
    if hashlib.sha256(body).hexdigest() != capture.body_sha256:
        return True
    if any(secret.encode("utf-8") in body for secret in values):
        return True
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return False
    return _json_contains_sensitive_material(decoded, values)


def _json_contains_sensitive_material(
    value: object,
    sensitive_values: tuple[str, ...],
) -> bool:
    if isinstance(value, str):
        return any(secret in value for secret in sensitive_values)
    if isinstance(value, list):
        return any(
            _json_contains_sensitive_material(item, sensitive_values)
            for item in value
        )
    if isinstance(value, dict):
        return any(
            _json_contains_sensitive_material(key, sensitive_values)
            or _json_contains_sensitive_material(item, sensitive_values)
            for key, item in value.items()
        )
    return False


def _combine_captures(
    prior: tuple[RawHttpCapture, ...],
    current: tuple[RawHttpCapture, ...],
) -> tuple[RawHttpCapture, ...]:
    combined = list(prior)
    for capture in current:
        if capture not in combined:
            combined.append(capture)
    return tuple(combined)
