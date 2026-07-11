"""Collect the frozen RP-001 Toss daily-candle research sample."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import re
import stat
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import NoReturn, Protocol, TextIO, cast
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request
from zoneinfo import ZoneInfo

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerEntry,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values
from rp001.toss_research_collector import (
    CandleRow,
    CollectorError,
    CombinedCandleCollection,
    HttpRequest,
    HttpResponse,
    RawHttpCapture,
    TossResearchCollector,
)


def _load_metadata_boundary() -> tuple[ModuleType, str, str]:
    path = Path(__file__).resolve().with_name("collect_toss_metadata.py")
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    name = f"_rp001_candle_metadata_boundary_{digest}"
    source = _read_attested_boundary_source(path)
    source_sha256 = hashlib.sha256(source).hexdigest()
    specification = importlib.util.spec_from_loader(
        name,
        loader=None,
        origin=str(path),
    )
    if specification is None:
        raise RuntimeError("metadata boundary is unavailable")
    module = importlib.util.module_from_spec(specification)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        code = compile(
            source,
            str(path),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module, name, source_sha256


def _read_attested_boundary_source(path: Path) -> bytes:
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("boundary source is not regular")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        attached = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(attached.st_mode)
            or (opened.st_dev, opened.st_ino) != (attached.st_dev, attached.st_ino)
        ):
            raise OSError("boundary source attachment changed")
        return b"".join(chunks)
    except OSError:
        raise RuntimeError("metadata boundary is unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


(
    BOUNDARY,
    BOUNDARY_MODULE_NAME,
    BOUNDARY_EXECUTED_SOURCE_SHA256,
) = _load_metadata_boundary()

_OAUTH_URL = "https://openapi.tossinvest.com/oauth2/token"
_PROGRAM_ID = "RP-001"
_GOAL_VERSION = "1.2-COMPACT"
_SELECTED_SYMBOLS = ("AMZN", "CAT", "XOM", "AAPL", "AMD", "COST")
_START_DATE = date(2023, 1, 3)
_END_DATE = date(2026, 6, 30)
_INITIAL_BEFORE = "2026-07-01T00:00:00Z"
_SESSION_TIMEZONE = "America/New_York"
_INTERVAL = "1d"
_COUNT = "200"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CANONICAL_LEDGER_RELATIVE_PATH = Path(
    "research/rp-001/local-ledgers/interim-program"
)
_PREDECESSOR_CONTRACT_RELATIVE_PATH = Path(
    "research/rp-001/contracts/toss-read-only-source-contract-v1.2.json"
)
_PREDECESSOR_CONTRACT_SHA256 = (
    "082a43ad0bdf74d582896743f711bce6e22b18cdc21dbfa897c3d75bda9444a8"
)
_SOURCE_CONTRACT_RELATIVE_PATH = Path(
    "research/rp-001/contracts/toss-read-only-source-contract-v1.3.json"
)
_SAMPLE_FREEZE_RELATIVE_PATH = Path(
    "research/rp-001/contracts/selected-sample-freeze-v1.json"
)
_SAMPLE_FREEZE_SHA256 = (
    "aaf7a9442e2f7c17cd7321200b80ab5405ca35e49eafe79a35d953edf42b3ecb"
)
_MERC_FREEZE_RELATIVE_PATH = Path(
    "research/rp-001/contracts/st-beh-interim-merc-v1.json"
)
_MERC_FREEZE_SHA256 = (
    "efa61aa526a4887128c7d78916c23645bda43091b726973f99be9793f65a1ae3"
)
_FREEZE_LEDGER_EVENT_RELATIVE_PATH = Path(
    "research/rp-001/local-ledgers/interim-program/events/000013.json"
)
_FREEZE_LEDGER_EVENT_SHA256 = (
    "62e6fe366ede7ee49b7536caf33f46586feaa99a780185ea1bef807fb131ffd0"
)
_FREEZE_LEDGER_EVENT_OCCURRED_AT = "2026-07-11T00:28:08Z"
_TIMEOUT_SECONDS = 30.0
_OAUTH_RESPONSE_LIMIT_BYTES = 1024 * 1024
_CANDLE_RESPONSE_LIMIT_BYTES = 8 * 1024 * 1024
_MINIMUM_REQUEST_INTERVAL_SECONDS = 0.21


class UrlOpener(Protocol):
    def open(self, request: Request, timeout: float) -> object:
        """Open one HTTP request."""


class CandleRunError(ValueError):
    """Sanitized candle-run failure with a stable machine code."""

    def __init__(
        self,
        code: str,
        artifact_hashes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.code = code
        self.artifact_hashes = artifact_hashes
        super().__init__(f"{code}: read-only daily-candle research run failed")


@dataclass(frozen=True)
class CandleRunArguments:
    repository_root: Path
    credentials_path: Path
    predecessor_contract_path: Path
    predecessor_contract_sha256: str
    source_contract_path: Path
    source_contract_sha256: str
    sample_freeze_path: Path
    sample_freeze_sha256: str
    merc_freeze_path: Path
    merc_freeze_sha256: str
    freeze_ledger_event_path: Path
    freeze_ledger_event_sha256: str
    runner_source_path: Path
    runner_source_sha256: str
    runner_test_path: Path
    runner_test_sha256: str
    boundary_source_path: Path
    boundary_source_sha256: str
    boundary_test_path: Path
    boundary_test_sha256: str
    collector_source_path: Path
    collector_source_sha256: str
    collector_test_path: Path
    collector_test_sha256: str
    local_evidence_source_path: Path
    local_evidence_source_sha256: str
    local_evidence_test_path: Path
    local_evidence_test_sha256: str
    sensitive_policy_source_path: Path
    sensitive_policy_source_sha256: str
    sensitive_policy_test_path: Path
    sensitive_policy_test_sha256: str
    output_directory: Path
    ledger_directory: Path
    run_id: str


@dataclass(frozen=True)
class CandleRunSummary:
    run_id: str
    status: str
    symbol_count: int
    analysis_row_count: int
    capture_count: int
    artifact_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _VerifiedFile:
    role: str
    relative_path: str
    sha256: str

    def to_lineage_body(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.relative_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _VerifiedInputs:
    predecessor_contract: Mapping[str, object]
    source_contract: Mapping[str, object]
    sample_freeze: Mapping[str, object]
    merc_freeze: Mapping[str, object]
    freeze_ledger_event: Mapping[str, object]
    files: tuple[_VerifiedFile, ...]


@dataclass(frozen=True)
class _TerminalFailure:
    code: str
    stage: str
    request_attempted: bool
    response_received: bool | str
    price_volume_opened: bool | str
    sensitive_raw_omitted: bool
    raw_response_omitted: bool
    captures: tuple[RawHttpCapture, ...]


@dataclass(frozen=True)
class _AcquisitionOutcome:
    collections: tuple[CombinedCandleCollection, ...] | None
    failure: _TerminalFailure | None


class _MinimumIntervalPacer:
    def __init__(
        self,
        interval_seconds: float = _MINIMUM_REQUEST_INTERVAL_SECONDS,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    def __call__(self) -> None:
        while True:
            now = self._monotonic()
            if self._last_request_at is None:
                self._last_request_at = now
                return
            remaining = self._interval_seconds - (now - self._last_request_at)
            if remaining <= 1e-9:
                self._last_request_at = now
                return
            self._sleeper(remaining)


class CandleTransport:
    """Exact GET-only transport for the frozen candle endpoint."""

    def __init__(
        self,
        opener: UrlOpener,
        timeout_seconds: float,
        allowed_symbols: Sequence[str],
        request_pacer: Callable[[], None],
        namespace_verifier: Callable[[], None],
    ) -> None:
        if not callable(getattr(opener, "open", None)):
            raise CandleRunError("TRANSPORT_CONFIGURATION_INVALID")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise CandleRunError("TRANSPORT_CONFIGURATION_INVALID")
        if tuple(allowed_symbols) != _SELECTED_SYMBOLS:
            raise CandleRunError("TRANSPORT_CONFIGURATION_INVALID")
        if not callable(request_pacer) or not callable(namespace_verifier):
            raise CandleRunError("TRANSPORT_CONFIGURATION_INVALID")
        self._opener = opener
        self._timeout_seconds = float(timeout_seconds)
        self._allowed_symbols = frozenset(allowed_symbols)
        self._request_pacer = request_pacer
        self._namespace_verifier = namespace_verifier
        self.request_count = 0
        self.response_count = 0
        self.response_complete_count = 0
        self.failure_code: str | None = None

    def __call__(self, request: HttpRequest) -> HttpResponse:
        failure_code: str | None = None
        try:
            return self._send(request)
        except CandleRunError as error:
            failure_code = error.code
        except BaseException as error:
            if isinstance(
                error,
                cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")),
            ):
                failure_code = error.code
            elif isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                failure_code = "RUN_INTERRUPTED"
            else:
                failure_code = "CANDLE_TRANSPORT_ERROR"
        self.failure_code = failure_code or "CANDLE_TRANSPORT_ERROR"
        del request
        raise CandleRunError(self.failure_code)

    def _send(self, request: HttpRequest) -> HttpResponse:
        _require_allowed_candle_request(request, self._allowed_symbols)
        outgoing = Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        try:
            self._namespace_verifier()
            self._request_pacer()
            self._namespace_verifier()
        except CandleRunError:
            raise
        except cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")) as error:
            raise CandleRunError(error.code) from None
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            raise CandleRunError("REQUEST_PACING_FAILED") from None
        self.request_count += 1
        try:
            received = self._opener.open(
                outgoing,
                timeout=self._timeout_seconds,
            )
            self._namespace_verifier()
        except HTTPError as error:
            self.response_count += 1
            response = _boundary_http_error_response(
                error,
                "CANDLE_TRANSPORT_ERROR",
                _CANDLE_RESPONSE_LIMIT_BYTES,
                "CANDLE_RESPONSE_TOO_LARGE",
            )
            self.response_complete_count += 1
            self._namespace_verifier()
            return response
        except cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")) as error:
            raise CandleRunError(error.code) from None
        except CandleRunError:
            raise
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            raise CandleRunError("CANDLE_TRANSPORT_ERROR") from None
        self.response_count += 1
        response = _boundary_url_response(
            received,
            "CANDLE_TRANSPORT_ERROR",
            _CANDLE_RESPONSE_LIMIT_BYTES,
            "CANDLE_RESPONSE_TOO_LARGE",
        )
        self.response_complete_count += 1
        self._namespace_verifier()
        return response


ArtifactStoreFactory = Callable[[], LocalArtifactStore]
LedgerFactory = Callable[[Path], object]
Clock = Callable[[], datetime]


def run_daily_candle_collection(
    arguments: CandleRunArguments,
    *,
    opener: UrlOpener | None = None,
    clock: Clock | None = None,
    request_pacer: Callable[[], None] | None = None,
    artifact_store_factory: ArtifactStoreFactory = LocalArtifactStore,
    ledger_factory: LedgerFactory = AppendOnlyLocalLedger,
) -> CandleRunSummary:
    """Verify every frozen input, collect candles, and commit one terminal event."""
    failure_code: str | None = None
    failure_hashes: tuple[tuple[str, str], ...] = ()
    try:
        return _run_daily_candle_collection_once(
            arguments,
            opener=opener,
            clock=clock,
            request_pacer=request_pacer,
            artifact_store_factory=artifact_store_factory,
            ledger_factory=ledger_factory,
        )
    except CandleRunError as error:
        failure_code = error.code
        failure_hashes = error.artifact_hashes
    except cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")) as error:
        failure_code = error.code
        failure_hashes = error.artifact_hashes
    except BaseException as error:
        failure_code = (
            "RUN_INTERRUPTED"
            if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit))
            else "INTERNAL_RUN_ERROR"
        )
    del opener
    raise CandleRunError(failure_code or "INTERNAL_RUN_ERROR", failure_hashes)


def _run_daily_candle_collection_once(
    arguments: CandleRunArguments,
    *,
    opener: UrlOpener | None,
    clock: Clock | None,
    request_pacer: Callable[[], None] | None,
    artifact_store_factory: ArtifactStoreFactory,
    ledger_factory: LedgerFactory,
) -> CandleRunSummary:
    effective_clock = clock or getattr(BOUNDARY, "_system_clock")
    effective_opener = opener or getattr(BOUNDARY, "_build_redirect_rejecting_opener")()
    effective_pacer = request_pacer or _MinimumIntervalPacer()
    repository = getattr(BOUNDARY, "_require_repository_root")(
        arguments.repository_root
    )
    output = None
    pinned_ledger = None
    trust_anchor_lock_acquired = False
    repository_lock_acquired = False
    try:
        run_paths = _build_run_paths(arguments, repository)
        ledger_directory = getattr(BOUNDARY, "_resolve_repository_namespace_path")(
            repository,
            arguments.ledger_directory,
            "LEDGER_PATH_INVALID",
        )
        _require_canonical_ledger_directory(ledger_directory, repository.path)
        getattr(BOUNDARY, "_acquire_exclusive_lock")(
            repository.parent_descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        trust_anchor_lock_acquired = True
        repository.verify()
        getattr(BOUNDARY, "_acquire_exclusive_lock")(
            repository.descriptor,
            "LEDGER_LOCK_UNAVAILABLE",
        )
        repository_lock_acquired = True
        repository.verify()
        output = getattr(BOUNDARY, "_pin_repository_directory")(
            repository,
            run_paths.output_root,
            create=True,
            error_code="OUTPUT_PATH_INVALID",
        )
        pinned_ledger = getattr(BOUNDARY, "_pin_repository_directory")(
            repository,
            ledger_directory,
            create=True,
            error_code="LEDGER_PATH_INVALID",
        )
        with getattr(BOUNDARY, "_exclusive_output_run_lock")(
            repository,
            output,
            arguments.run_id,
        ) as locked_output:
            getattr(BOUNDARY, "_require_output_run_absent")(
                output,
                arguments.run_id,
            )
            with getattr(BOUNDARY, "_exclusive_ledger_lock")(
                repository,
                pinned_ledger,
            ) as locked_ledger:
                with getattr(BOUNDARY, "_pinned_namespace_guard")(
                    output,
                    pinned_ledger,
                    locked_output=locked_output,
                    locked_ledger=locked_ledger,
                ) as guard:
                    verified = _verify_frozen_inputs(arguments, repository)
                    guard.verify()
                    credential = None
                    delegate_store = (
                        None
                        if artifact_store_factory is LocalArtifactStore
                        else artifact_store_factory()
                    )
                    store = getattr(BOUNDARY, "_TransactionalArtifactStore")(
                        guard,
                        run_paths,
                        delegate_store,
                    )
                    delegate_ledger = (
                        None
                        if ledger_factory is AppendOnlyLocalLedger
                        else ledger_factory(ledger_directory)
                    )
                    ledger = getattr(BOUNDARY, "_TransactionalLedger")(
                        guard,
                        ledger_directory,
                        delegate_ledger,
                    )
                    try:
                        store.require_run_absent()
                        credential = getattr(BOUNDARY, "_open_credential_capability")(
                            repository,
                            arguments.credentials_path,
                        )
                        store.claim_run_directory()
                        ledger.claim_events_directory()
                        guard.verify()
                        acquisition = _acquire_candles_no_raise(
                            credential,
                            effective_opener,
                            effective_clock,
                            effective_pacer,
                            guard.verify,
                        )
                        guard.verify()
                        if acquisition.failure is not None:
                            hashes = _publish_terminal_failure(
                                arguments=arguments,
                                repository_root=repository.path,
                                verified=verified,
                                run_paths=run_paths,
                                failure=acquisition.failure,
                                store=store,
                                ledger=ledger,
                                clock=effective_clock,
                            )
                            raise CandleRunError(
                                acquisition.failure.code,
                                hashes,
                            )
                        if acquisition.collections is None:
                            raise CandleRunError("INTERNAL_RUN_ERROR")
                        return _publish_success(
                            arguments=arguments,
                            repository_root=repository.path,
                            verified=verified,
                            run_paths=run_paths,
                            collections=acquisition.collections,
                            store=store,
                            ledger=ledger,
                            clock=effective_clock,
                        )
                    except BaseException as caught:
                        try:
                            store.remove_run_directory_if_empty()
                        except BaseException:
                            pass
                        if isinstance(caught, LocalEvidenceError):
                            raise CandleRunError(
                                "EVIDENCE_PUBLICATION_FAILED"
                            ) from None
                        raise
                    finally:
                        if credential is not None:
                            credential.close()
                        ledger.close()
                        store.close()
    finally:
        if pinned_ledger is not None:
            os.close(pinned_ledger.descriptor)
        if output is not None:
            os.close(output.descriptor)
        if repository_lock_acquired:
            getattr(BOUNDARY, "_release_exclusive_lock")(
                repository.descriptor,
                "LEDGER_LOCK_UNAVAILABLE",
            )
        if trust_anchor_lock_acquired:
            getattr(BOUNDARY, "_release_exclusive_lock")(
                repository.parent_descriptor,
                "LEDGER_LOCK_UNAVAILABLE",
            )
        getattr(BOUNDARY, "_close_repository_capability")(repository)


def _acquire_candles_no_raise(
    credential: object,
    opener: UrlOpener,
    clock: Clock,
    request_pacer: Callable[[], None],
    namespace_verifier: Callable[[], None],
) -> _AcquisitionOutcome:
    stage = "credential"
    request_attempted = False
    response_received = False
    transport: CandleTransport | None = None
    completed_captures: list[RawHttpCapture] = []
    ephemeral = ""
    try:
        credentials = getattr(BOUNDARY, "_load_credentials")(credential)
        stage = "auth"
        form = urlencode(
            (
                ("grant_type", "client_credentials"),
                ("client_id", credentials.client_identifier),
                ("client_secret", credentials.private_credential),
            )
        ).encode("ascii")
        request = Request(
            _OAUTH_URL,
            data=form,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        request_attempted = True
        try:
            namespace_verifier()
            received = opener.open(request, timeout=_TIMEOUT_SECONDS)
            namespace_verifier()
        except HTTPError as error:
            response_received = True
            auth_response = _boundary_http_error_response(
                error,
                "AUTH_TRANSPORT_ERROR",
                _OAUTH_RESPONSE_LIMIT_BYTES,
                "AUTH_RESPONSE_TOO_LARGE",
            )
        else:
            response_received = True
            auth_response = _boundary_url_response(
                received,
                "AUTH_TRANSPORT_ERROR",
                _OAUTH_RESPONSE_LIMIT_BYTES,
                "AUTH_RESPONSE_TOO_LARGE",
            )
            namespace_verifier()
        if not 200 <= auth_response.status < 300:
            raise CandleRunError("AUTH_HTTP_STATUS")
        ephemeral = _ephemeral_token(auth_response.body)

        stage = "candles"
        request_attempted = False
        response_received = False
        transport = CandleTransport(
            opener=opener,
            timeout_seconds=_TIMEOUT_SECONDS,
            allowed_symbols=_SELECTED_SYMBOLS,
            request_pacer=request_pacer,
            namespace_verifier=namespace_verifier,
        )
        collector = TossResearchCollector(
            transport=transport,
            token_supplier=lambda: ephemeral,
            clock=clock,
        )
        collections: list[CombinedCandleCollection] = []
        for symbol in _SELECTED_SYMBOLS:
            try:
                collection = collector.collect_adjusted_native(
                    symbol,
                    _START_DATE,
                    _END_DATE,
                    _INITIAL_BEFORE,
                )
                _require_complete_frozen_range(collection)
            except CollectorError as error:
                raise error.with_prior_captures(tuple(completed_captures)) from None
            collections.append(collection)
            completed_captures.extend(_collection_captures(collection))
        return _AcquisitionOutcome(tuple(collections), None)
    except BaseException as caught:
        if isinstance(caught, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            code = "RUN_INTERRUPTED"
        elif isinstance(caught, CollectorError):
            code = caught.code
        elif isinstance(caught, CandleRunError):
            code = caught.code
        elif isinstance(caught, cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError"))):
            code = caught.code
        elif stage == "credential":
            code = "CREDENTIAL_FILE_INVALID"
        elif stage == "auth":
            code = "AUTH_TRANSPORT_ERROR"
        else:
            code = "CANDLE_TRANSPORT_ERROR"
        captures = (
            _unique_captures(caught.captures)
            if isinstance(caught, CollectorError)
            else tuple(completed_captures)
        )
        if stage == "candles" and transport is not None:
            request_attempted = transport.request_count > 0
            response_received = transport.response_count > 0
            if transport.failure_code is not None:
                code = transport.failure_code
        if stage != "candles":
            price_volume_opened: bool | str = False
        elif captures or (transport and transport.response_complete_count > 0):
            price_volume_opened = True
        elif response_received:
            price_volume_opened = "unknown"
        else:
            price_volume_opened = False
        failure = _TerminalFailure(
            code=code,
            stage=stage,
            request_attempted=request_attempted,
            response_received=response_received,
            price_volume_opened=price_volume_opened,
            sensitive_raw_omitted=code == "SENSITIVE_RESPONSE",
            raw_response_omitted=bool(response_received and not captures),
            captures=captures,
        )
        return _AcquisitionOutcome(None, failure)
    finally:
        ephemeral = ""


def _require_complete_frozen_range(
    collection: CombinedCandleCollection,
) -> None:
    start_session = _START_DATE.isoformat()
    adjusted_sessions = {
        _session_date(row.timestamp)
        for row in collection.adjusted_collection.analysis_rows
    }
    native_sessions = {
        _session_date(row.timestamp)
        for row in collection.native_collection.analysis_rows
    }
    if start_session not in adjusted_sessions or start_session not in native_sessions:
        raise CollectorError(
            "CANDLE_RANGE_INCOMPLETE",
            captures=_collection_captures(collection),
        )


def _ephemeral_token(source: bytes) -> str:
    try:
        payload = json.loads(source.decode("utf-8"))
    except Exception:
        raise CandleRunError("AUTH_RESPONSE_INVALID") from None
    if not isinstance(payload, dict):
        raise CandleRunError("AUTH_RESPONSE_INVALID")
    ephemeral_bearer = payload.get("access_token")
    if (
        not isinstance(ephemeral_bearer, str)
        or not ephemeral_bearer
        or any(character in ephemeral_bearer for character in "\r\n\x00")
    ):
        raise CandleRunError("AUTH_RESPONSE_INVALID")
    return ephemeral_bearer


def _publish_success(
    *,
    arguments: CandleRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    run_paths: object,
    collections: tuple[CombinedCandleCollection, ...],
    store: object,
    ledger: object,
    clock: Clock,
) -> CandleRunSummary:
    published: list[LocalArtifactBinding] = []
    ledger_entry: LocalLedgerEntry | None = None
    try:
        store.require_terminal_namespace(success=True)
        raw = _publish(
            store,
            run_paths.raw,
            _raw_body(arguments.run_id, collections),
            published,
        )
        processed = _publish(
            store,
            run_paths.processed,
            _processed_body(
                arguments.run_id,
                collections,
                raw,
                repository_root,
            ),
            published,
        )
        scope = _publish(
            store,
            run_paths.selection,
            _scope_body(arguments, verified),
            published,
        )
        exposure = _publish(
            store,
            run_paths.exposure,
            _exposure_body(
                arguments.run_id,
                collections,
                raw,
                processed,
                repository_root,
                clock,
            ),
            published,
        )
        prior = (raw, processed, scope, exposure)
        manifest = _publish(
            store,
            run_paths.manifest,
            _manifest_body(
                arguments,
                verified,
                collections,
                prior,
                repository_root,
                clock,
            ),
            published,
        )
        bindings = prior + (manifest,)
        if store.terminal_artifact_mismatches(bindings):
            raise CandleRunError("EVIDENCE_INTEGRITY_LOST")
        ledger_entry = ledger.append(
            event_type="toss_daily_candle_collection_succeeded",
            payload={
                "runId": arguments.run_id,
                "sampleRole": "unseen_historical_confirmation",
                "symbols": list(_SELECTED_SYMBOLS),
                "analysisRowCount": _analysis_row_count(collections),
                "captureCount": len(_all_captures(collections)),
                "manifest": _binding_body(manifest, repository_root),
                "operationalDisposition": "NoTrade/no integration",
            },
            occurred_at=_safe_timestamp(clock),
        )
        mismatches = store.terminal_artifact_mismatches(bindings)
        if mismatches:
            _raise_committed_invalidated(
                arguments,
                "success",
                ledger_entry,
                mismatches,
                ledger,
                clock,
            )
        artifact_hashes = tuple(
            (path.name.removesuffix(".json"), binding.artifact_sha256)
            for path, binding in zip(
                (
                    run_paths.raw,
                    run_paths.processed,
                    run_paths.selection,
                    run_paths.exposure,
                    run_paths.manifest,
                ),
                bindings,
                strict=True,
            )
        ) + (("ledgerEvent", ledger_entry.record_sha256),)
        return CandleRunSummary(
            run_id=arguments.run_id,
            status="succeeded",
            symbol_count=len(collections),
            analysis_row_count=_analysis_row_count(collections),
            capture_count=len(_all_captures(collections)),
            artifact_hashes=artifact_hashes,
        )
    except BaseException as caught:
        if ledger_entry is not None:
            if isinstance(caught, CandleRunError) and caught.code == "EVIDENCE_INTEGRITY_LOST":
                raise
            _raise_committed_invalidated(
                arguments,
                "success",
                ledger_entry,
                (("run", "post_commit_processing_error"),),
                ledger,
                clock,
            )
        code = _error_code(caught, "evidence")
    try:
        getattr(BOUNDARY, "_rollback_bindings")(store, published)
    except BaseException as error:
        if _is_boundary_error(error, "NAMESPACE_IDENTITY_CHANGED"):
            raise CandleRunError("NAMESPACE_IDENTITY_CHANGED") from None
        raise CandleRunError("EVIDENCE_ROLLBACK_FAILED") from None
    failure = _TerminalFailure(
        code=code,
        stage="evidence",
        request_attempted=True,
        response_received=True,
        price_volume_opened=True,
        sensitive_raw_omitted=False,
        raw_response_omitted=False,
        captures=_all_captures(collections),
    )
    hashes = _publish_terminal_failure(
        arguments=arguments,
        repository_root=repository_root,
        verified=verified,
        run_paths=run_paths,
        failure=failure,
        store=store,
        ledger=ledger,
        clock=clock,
    )
    raise CandleRunError(code, hashes)


def _publish_terminal_failure(
    *,
    arguments: CandleRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    run_paths: object,
    failure: _TerminalFailure,
    store: object,
    ledger: object,
    clock: Clock,
) -> tuple[tuple[str, str], ...]:
    store.require_terminal_namespace(success=False)
    source_lineage = [value.to_lineage_body() for value in verified.files]
    published: list[LocalArtifactBinding] = []
    failure_binding = _publish(
        store,
        run_paths.failure,
        {
            "schemaVersion": "rp001-toss-daily-candle-failure.v1",
            "programId": _PROGRAM_ID,
            "goalVersion": _GOAL_VERSION,
            "runId": arguments.run_id,
            "status": "failed",
            "errorCode": failure.code,
            "stage": failure.stage,
            "sampleRole": "unseen_historical_confirmation",
            "requestAttempted": failure.request_attempted,
            "responseReceived": failure.response_received,
            "metadataPreviouslyOpened": True,
            "priceVolumeOpened": failure.price_volume_opened,
            "outcomesPerformanceOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "sensitiveRawOmitted": failure.sensitive_raw_omitted,
            "rawResponseOmitted": failure.raw_response_omitted,
            "failedAt": _safe_timestamp(clock),
            "operationalDisposition": "NoTrade/no integration",
            "sourceLineage": source_lineage,
            "captures": [_capture_body(value) for value in failure.captures],
        },
        published,
    )
    if store.terminal_artifact_mismatches((failure_binding,)):
        _rollback_quietly(store, published)
        raise CandleRunError("EVIDENCE_INTEGRITY_LOST")
    try:
        entry = ledger.append(
            event_type="toss_daily_candle_collection_failed",
            payload={
                "runId": arguments.run_id,
                "sampleRole": "unseen_historical_confirmation",
                "errorCode": failure.code,
                "stage": failure.stage,
                "sourceLineage": source_lineage,
                "failureArtifact": _binding_body(
                    failure_binding,
                    repository_root,
                ),
                "operationalDisposition": "NoTrade/no integration",
            },
            occurred_at=_safe_timestamp(clock),
        )
    except BaseException as caught:
        if _is_boundary_error(caught, "LEDGER_COMMIT_MISMATCH"):
            raise CandleRunError("LEDGER_COMMIT_MISMATCH") from None
        _rollback_quietly(store, published)
        raise CandleRunError("EVIDENCE_PUBLICATION_FAILED") from None
    mismatches = store.terminal_artifact_mismatches((failure_binding,))
    if mismatches:
        _raise_committed_invalidated(
            arguments,
            "failure",
            entry,
            mismatches,
            ledger,
            clock,
        )
    return (
        ("failure", failure_binding.artifact_sha256),
        ("ledgerEvent", entry.record_sha256),
    )


def _raise_committed_invalidated(
    arguments: CandleRunArguments,
    terminal_type: str,
    terminal_entry: LocalLedgerEntry,
    mismatches: Sequence[tuple[str, str]],
    ledger: object,
    clock: Clock,
) -> NoReturn:
    terminal_role = (
        "ledgerSuccessEvent" if terminal_type == "success" else "ledgerFailureEvent"
    )
    payload: dict[str, object] = {
        "runId": arguments.run_id,
        "terminalEventType": terminal_type,
        "invalidatedTerminalEventSha256": terminal_entry.record_sha256,
        "mismatches": [
            {"role": role, "category": category}
            for role, category in mismatches
        ],
    }
    try:
        invalidation = ledger.append(
            event_type="toss_daily_candle_collection_invalidated",
            payload=payload,
            occurred_at=_safe_timestamp(clock),
        )
    except BaseException:
        raise CandleRunError(
            "EVIDENCE_INTEGRITY_LOST",
            ((terminal_role, terminal_entry.record_sha256),),
        ) from None
    raise CandleRunError(
        "EVIDENCE_INTEGRITY_LOST",
        (
            (terminal_role, terminal_entry.record_sha256),
            ("ledgerInvalidationEvent", invalidation.record_sha256),
        ),
    )


def _build_run_paths(arguments: CandleRunArguments, repository: object) -> object:
    if _RUN_ID_PATTERN.fullmatch(arguments.run_id) is None:
        raise CandleRunError("RUN_ID_INVALID")
    output_root = getattr(BOUNDARY, "_resolve_repository_namespace_path")(
        repository,
        arguments.output_directory,
        "OUTPUT_PATH_INVALID",
    )
    if output_root != repository.path / Path("research/rp-001/candle-runs"):
        raise CandleRunError("OUTPUT_PATH_INVALID")
    run_directory = output_root / arguments.run_id
    return getattr(BOUNDARY, "_RunPaths")(
        raw=run_directory / "raw-candles.json",
        processed=run_directory / "processed-candles.json",
        selection=run_directory / "candle-scope.json",
        exposure=run_directory / "candle-exposure.json",
        manifest=run_directory / "manifest.json",
        failure=run_directory / "failure.json",
    )


def _require_canonical_ledger_directory(path: Path, repository_root: Path) -> None:
    if path != repository_root / _CANONICAL_LEDGER_RELATIVE_PATH:
        raise CandleRunError("LEDGER_PATH_INVALID")


def _verify_frozen_inputs(
    arguments: CandleRunArguments,
    repository: object,
) -> _VerifiedInputs:
    declared = (
        ("predecessor_contract", arguments.predecessor_contract_path, arguments.predecessor_contract_sha256, True),
        ("source_contract", arguments.source_contract_path, arguments.source_contract_sha256, True),
        ("sample_freeze", arguments.sample_freeze_path, arguments.sample_freeze_sha256, True),
        ("merc_freeze", arguments.merc_freeze_path, arguments.merc_freeze_sha256, True),
        ("freeze_ledger_event", arguments.freeze_ledger_event_path, arguments.freeze_ledger_event_sha256, True),
        ("runner_source", arguments.runner_source_path, arguments.runner_source_sha256, False),
        ("runner_test", arguments.runner_test_path, arguments.runner_test_sha256, False),
        ("boundary_source", arguments.boundary_source_path, arguments.boundary_source_sha256, False),
        ("boundary_test", arguments.boundary_test_path, arguments.boundary_test_sha256, False),
        ("collector_source", arguments.collector_source_path, arguments.collector_source_sha256, False),
        ("collector_test", arguments.collector_test_path, arguments.collector_test_sha256, False),
        ("local_evidence_source", arguments.local_evidence_source_path, arguments.local_evidence_source_sha256, False),
        ("local_evidence_test", arguments.local_evidence_test_path, arguments.local_evidence_test_sha256, False),
        ("sensitive_policy_source", arguments.sensitive_policy_source_path, arguments.sensitive_policy_source_sha256, False),
        ("sensitive_policy_test", arguments.sensitive_policy_test_path, arguments.sensitive_policy_test_sha256, False),
    )
    files: list[_VerifiedFile] = []
    objects: dict[str, Mapping[str, object]] = {}
    for role, declared_path, expected_sha256, canonical in declared:
        if _SHA256_PATTERN.fullmatch(expected_sha256) is None:
            raise CandleRunError("INPUT_HASH_INVALID")
        relative = getattr(BOUNDARY, "_repository_input_relative_argument")(
            repository,
            declared_path,
            "INPUT_PATH_INVALID",
        )
        exact_provenance = {
            "predecessor_contract": (
                _PREDECESSOR_CONTRACT_RELATIVE_PATH,
                _PREDECESSOR_CONTRACT_SHA256,
            ),
            "sample_freeze": (
                _SAMPLE_FREEZE_RELATIVE_PATH,
                _SAMPLE_FREEZE_SHA256,
            ),
            "merc_freeze": (
                _MERC_FREEZE_RELATIVE_PATH,
                _MERC_FREEZE_SHA256,
            ),
            "freeze_ledger_event": (
                _FREEZE_LEDGER_EVENT_RELATIVE_PATH,
                _FREEZE_LEDGER_EVENT_SHA256,
            ),
        }.get(role)
        source = getattr(BOUNDARY, "_read_repository_regular_file")(
            repository,
            relative,
            "FROZEN_INPUT_INVALID",
        )
        actual = sha256_bytes(source)
        if actual != expected_sha256:
            raise CandleRunError("INPUT_HASH_MISMATCH")
        if role == "source_contract" and relative != _SOURCE_CONTRACT_RELATIVE_PATH:
            raise CandleRunError("SOURCE_CONTRACT_INVALID")
        if exact_provenance is not None and (
            relative != exact_provenance[0]
            or expected_sha256 != exact_provenance[1]
        ):
            raise CandleRunError("FROZEN_PROVENANCE_MISMATCH")
        if canonical:
            _require_sidecar(repository, relative, expected_sha256)
            objects[role] = _load_canonical_object(source)
        files.append(_VerifiedFile(role, relative.as_posix(), actual))
    verified_files = tuple(files)
    _validate_execution_sources(verified_files, repository)
    _validate_sample_freeze(objects["sample_freeze"])
    _validate_merc_freeze(objects["merc_freeze"], arguments, repository)
    _validate_freeze_ledger_event(
        objects["freeze_ledger_event"],
        arguments,
        repository,
    )
    _validate_source_contract(objects["source_contract"], arguments, repository)
    return _VerifiedInputs(
        predecessor_contract=objects["predecessor_contract"],
        source_contract=objects["source_contract"],
        sample_freeze=objects["sample_freeze"],
        merc_freeze=objects["merc_freeze"],
        freeze_ledger_event=objects["freeze_ledger_event"],
        files=verified_files,
    )


def _validate_execution_sources(
    files: tuple[_VerifiedFile, ...],
    repository: object,
) -> None:
    by_role = {value.role: value for value in files}
    actual = {
        "runner_source": _execution_source_path(__file__, repository),
        "boundary_source": _execution_source_path(
            cast(str, getattr(BOUNDARY, "__file__")),
            repository,
        ),
        "collector_source": _object_source_path(TossResearchCollector, repository),
        "local_evidence_source": _object_source_path(LocalArtifactStore, repository),
        "sensitive_policy_source": _object_source_path(find_sensitive_values, repository),
    }
    for role, relative in actual.items():
        if by_role.get(role) is None or by_role[role].relative_path != relative.as_posix():
            raise CandleRunError("EXECUTION_SOURCE_MISMATCH")
        source = getattr(BOUNDARY, "_read_repository_regular_file")(
            repository,
            relative,
            "EXECUTION_SOURCE_MISMATCH",
        )
        if sha256_bytes(source) != by_role[role].sha256:
            raise CandleRunError("EXECUTION_SOURCE_MISMATCH")
    if (
        by_role["boundary_source"].sha256
        != BOUNDARY_EXECUTED_SOURCE_SHA256
    ):
        raise CandleRunError("EXECUTION_SOURCE_MISMATCH")


def _execution_source_path(source: str, repository: object) -> Path:
    try:
        return Path(source).resolve(strict=True).relative_to(repository.path)
    except (OSError, RuntimeError, ValueError):
        raise CandleRunError("EXECUTION_SOURCE_MISMATCH") from None


def _object_source_path(value: object, repository: object) -> Path:
    try:
        source = inspect.getsourcefile(value)
    except (OSError, TypeError):
        source = None
    if source is None:
        raise CandleRunError("EXECUTION_SOURCE_MISMATCH")
    return _execution_source_path(source, repository)


def _validate_sample_freeze(value: Mapping[str, object]) -> None:
    selection = value.get("selection")
    selected = (
        selection.get("selectedSymbols")
        if isinstance(selection, dict)
        else value.get("selectedSymbols")
    )
    period = value.get("period")
    if (
        value.get("programId") != _PROGRAM_ID
        or value.get("goalVersion") != _GOAL_VERSION
        or value.get("usageScope") != "research_only"
        or value.get("operationalDisposition")
        not in {"NoTrade/no integration", "no_trade_no_integration"}
        or selected != list(_SELECTED_SYMBOLS)
        or not isinstance(period, dict)
        or period.get("startDate") != _START_DATE.isoformat()
        or period.get("endDate") != _END_DATE.isoformat()
        or period.get("inclusive") is not True
        or period.get("interval") != _INTERVAL
        or period.get("timezone") != _SESSION_TIMEZONE
    ):
        raise CandleRunError("SAMPLE_FREEZE_INVALID")


def _validate_merc_freeze(
    value: Mapping[str, object],
    arguments: CandleRunArguments,
    repository: object,
) -> None:
    schema = value.get("schemaVersion")
    if schema == "rp001-candle-merc-freeze.v1":
        sample_binding = value.get("sampleBinding")
        data_scope = None
        status_valid = value.get("status") == "merc_frozen_before_price_volume_open"
        unopened = value.get("priceVolumeOpened") is False
    elif schema == "rp001-st-beh-interim-merc.v1":
        bindings = value.get("bindings")
        sample_binding = (
            bindings.get("selectedSampleFreeze")
            if isinstance(bindings, dict)
            else None
        )
        data_scope = value.get("dataScope")
        status_valid = value.get("status") == "predata_rules_frozen_candle_inputs_pending"
        unopened = True
    else:
        raise CandleRunError("MERC_FREEZE_INVALID")
    expected_sample_path = _relative_argument(arguments.sample_freeze_path, repository)
    if (
        value.get("programId") != _PROGRAM_ID
        or value.get("goalVersion") != _GOAL_VERSION
        or value.get("operationalDisposition") != "NoTrade/no integration"
        or not status_valid
        or not unopened
        or sample_binding
        != {"path": expected_sample_path, "sha256": arguments.sample_freeze_sha256}
    ):
        raise CandleRunError("MERC_FREEZE_INVALID")
    if data_scope is not None and data_scope != {
        "additionalSymbolsHorizonsThresholds": "forbidden",
        "endDate": _END_DATE.isoformat(),
        "interval": _INTERVAL,
        "sampleRole": "unseen_historical_confirmation",
        "startDate": _START_DATE.isoformat(),
        "symbols": list(_SELECTED_SYMBOLS),
        "timezone": _SESSION_TIMEZONE,
    }:
        raise CandleRunError("MERC_FREEZE_INVALID")


def _validate_freeze_ledger_event(
    value: Mapping[str, object],
    arguments: CandleRunArguments,
    repository: object,
) -> None:
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise CandleRunError("FREEZE_LEDGER_EVENT_INVALID")
    sample_binding = payload.get("selectedSampleFreeze")
    merc_binding = payload.get("interimMerc")
    pre_candle = payload.get("preCandleState")
    if (
        value.get("schemaVersion") != "rp001-local-ledger-entry.v1"
        or value.get("eventType")
        != "rp001_selected_sample_and_st_beh_interim_merc_frozen"
        or value.get("occurredAt") != _FREEZE_LEDGER_EVENT_OCCURRED_AT
        or value.get("sequence") != 13
        or payload.get("programId") != _PROGRAM_ID
        or sample_binding
        != _artifact_binding(
            arguments.sample_freeze_path,
            arguments.sample_freeze_sha256,
            repository,
        )
        or merc_binding
        != _artifact_binding(
            arguments.merc_freeze_path,
            arguments.merc_freeze_sha256,
            repository,
        )
        or not isinstance(pre_candle, dict)
        or pre_candle.get("candleRequests") != 0
        or pre_candle.get("priceVolumeOutcomePerformanceOpened") is not False
    ):
        raise CandleRunError("FREEZE_LEDGER_EVENT_INVALID")
    previous_sha256 = value.get("previousRecordSha256")
    if (
        not isinstance(previous_sha256, str)
        or _SHA256_PATTERN.fullmatch(previous_sha256) is None
    ):
        raise CandleRunError("FREEZE_LEDGER_EVENT_INVALID")


def _validate_source_contract(
    value: Mapping[str, object],
    arguments: CandleRunArguments,
    repository: object,
) -> None:
    expected_top_level_keys = frozenset(
        {
            "schemaVersion",
            "status",
            "programId",
            "goalVersion",
            "decisionScope",
            "operationalDisposition",
            "finalizedAt",
            "supersedes",
            "allowedRequests",
            "candleScope",
            "requestPacing",
            "completeness",
            "outputRoot",
            "credentialBoundary",
            "exposureState",
            "forbiddenRequests",
            "canonicalLedgerPath",
            "bindings",
            "qualityEvidence",
        }
    )
    expected_allowed = [
        {"method": "POST", "path": "/oauth2/token", "purpose": "ephemeral_authentication_only"},
        {
            "method": "GET",
            "path": "/api/v1/candles",
            "purpose": "frozen_daily_price_volume_collection",
            "parameters": ["symbol", "interval=1d", "count=200", "adjusted", "before"],
        },
    ]
    scope = {
        "symbols": list(_SELECTED_SYMBOLS),
        "startDate": _START_DATE.isoformat(),
        "endDate": _END_DATE.isoformat(),
        "interval": _INTERVAL,
        "timezone": _SESSION_TIMEZONE,
        "count": 200,
        "initialBefore": _INITIAL_BEFORE,
        "adjustedModes": [True, False],
        "paginationCursor": "opaque_before",
        "requestOrder": "symbol_then_adjusted_true_then_false_sequential",
    }
    if (
        frozenset(value) != expected_top_level_keys
        or value.get("schemaVersion") != "rp001-toss-read-only-source-contract.v1.3"
        or value.get("status") != "read_only_daily_candle_runner_authorized"
        or value.get("programId") != _PROGRAM_ID
        or value.get("goalVersion") != _GOAL_VERSION
        or value.get("decisionScope") != "research_only"
        or value.get("operationalDisposition") != "NoTrade/no integration"
        or not _finalized_after_freeze_event(value.get("finalizedAt"))
        or value.get("allowedRequests") != expected_allowed
        or value.get("candleScope") != scope
        or value.get("requestPacing")
        != {
            "minimumIntervalSeconds": 0.21,
            "method": "monotonic_sleep_loop",
        }
        or value.get("completeness")
        != {
            "requireFrozenStartSession": True,
            "terminalCursorBeforeStart": "data_unavailable",
        }
        or value.get("outputRoot") != "research/rp-001/candle-runs"
        or value.get("canonicalLedgerPath") != _CANONICAL_LEDGER_RELATIVE_PATH.as_posix()
        or value.get("qualityEvidence")
        != {
            "candleRunnerTestsPassed": 20,
            "candleRunnerTestsTotal": 20,
            "candleDependencyRegressionTestsPassed": 229,
            "candleDependencyRegressionTestsTotal": 229,
            "programRegressionTestsPassed": 399,
            "programRegressionTestsTotal": 399,
            "criticalFindings": 0,
            "importantFindings": 0,
            "minorFindings": 0,
            "finalReviewVerdict": "APPROVE",
            "reviewVerdicts": {
                "runner": "APPROVE_C0_I0_M0",
                "metadataBoundary": "APPROVE_C0_I0_M0",
                "collector": "APPROVE_C0_I0_M0",
                "localEvidence": "APPROVE_C0_I0_M0",
                "sensitiveValuePolicy": "APPROVE_C0_I0_M0",
            },
            "reviewScope": [
                "parent_fd_trust_anchor_active_lifecycle",
                "metadata_boundary_executed_byte_attestation",
                "rate_paced_complete_daily_range",
                "post_return_external_cas_deferred",
            ],
        }
    ):
        raise CandleRunError("SOURCE_CONTRACT_INVALID")
    credential = value.get("credentialBoundary")
    exposure = value.get("exposureState")
    forbidden = value.get("forbiddenRequests")
    if (
        credential
        != {
            "pathClass": "repository_dot_storage_0600_pinned_regular_file",
            "tokenLifecycle": "ephemeral_credential_frame_only",
            "oauthResponsePersistence": "forbidden",
        }
        or exposure
        != {
            "metadataPreviouslyOpened": True,
            "priceVolumeOpened": False,
            "outcomesPerformanceOpened": False,
            "ordersAccountsAssetsAccessed": False,
        }
        or forbidden
        != {
            "families": ["order", "account", "asset"],
            "otherMarketEndpoints": ["stocks", "prices", "trades", "orderbook"],
            "operatingAppIntegration": True,
        }
    ):
        raise CandleRunError("SOURCE_CONTRACT_INVALID")
    bindings = value.get("bindings")
    if not isinstance(bindings, dict):
        raise CandleRunError("SOURCE_CONTRACT_INVALID")
    expected_bindings = {
        "predecessorContract": _artifact_binding(arguments.predecessor_contract_path, arguments.predecessor_contract_sha256, repository),
        "sampleFreeze": _artifact_binding(arguments.sample_freeze_path, arguments.sample_freeze_sha256, repository),
        "mercFreeze": _artifact_binding(arguments.merc_freeze_path, arguments.merc_freeze_sha256, repository),
        "freezeLedgerEvent": _artifact_binding(arguments.freeze_ledger_event_path, arguments.freeze_ledger_event_sha256, repository),
        "runner": _source_binding(arguments.runner_source_path, arguments.runner_source_sha256, arguments.runner_test_path, arguments.runner_test_sha256, repository),
        "metadataBoundary": _source_binding(arguments.boundary_source_path, arguments.boundary_source_sha256, arguments.boundary_test_path, arguments.boundary_test_sha256, repository),
        "collector": _source_binding(arguments.collector_source_path, arguments.collector_source_sha256, arguments.collector_test_path, arguments.collector_test_sha256, repository),
        "localEvidence": _source_binding(arguments.local_evidence_source_path, arguments.local_evidence_source_sha256, arguments.local_evidence_test_path, arguments.local_evidence_test_sha256, repository),
        "sensitiveValuePolicy": _source_binding(arguments.sensitive_policy_source_path, arguments.sensitive_policy_source_sha256, arguments.sensitive_policy_test_path, arguments.sensitive_policy_test_sha256, repository),
    }
    if bindings != expected_bindings:
        raise CandleRunError("SOURCE_CONTRACT_INVALID")
    expected_supersedes = {
        **_artifact_binding(
            arguments.predecessor_contract_path,
            arguments.predecessor_contract_sha256,
            repository,
        ),
        "reason": "authorize_frozen_daily_candle_collection_only",
    }
    if value.get("supersedes") != expected_supersedes:
        raise CandleRunError("SOURCE_CONTRACT_INVALID")


def _finalized_after_freeze_event(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        finalized = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        freeze_event = datetime.strptime(
            _FREEZE_LEDGER_EVENT_OCCURRED_AT,
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return finalized > freeze_event


def _artifact_binding(path: Path, sha256: str, repository: object) -> dict[str, object]:
    return {"path": _relative_argument(path, repository), "sha256": sha256}


def _source_binding(
    source_path: Path,
    source_sha256: str,
    test_path: Path,
    test_sha256: str,
    repository: object,
) -> dict[str, object]:
    return {
        "sourcePath": _relative_argument(source_path, repository),
        "sourceSha256": source_sha256,
        "testPath": _relative_argument(test_path, repository),
        "testSha256": test_sha256,
    }


def _relative_argument(path: Path, repository: object) -> str:
    return getattr(BOUNDARY, "_repository_input_relative_argument")(
        repository,
        path,
        "INPUT_PATH_INVALID",
    ).as_posix()


def _require_sidecar(repository: object, relative: Path, sha256: str) -> None:
    source = getattr(BOUNDARY, "_read_repository_regular_file")(
        repository,
        relative.with_name(f"{relative.name}.sha256"),
        "FROZEN_INPUT_INVALID",
    )
    if source != f"{sha256}\n".encode("ascii"):
        raise CandleRunError("FROZEN_INPUT_INVALID")


def _load_canonical_object(source: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(source.decode("utf-8"))
    except Exception:
        raise CandleRunError("FROZEN_INPUT_INVALID") from None
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise CandleRunError("FROZEN_INPUT_INVALID")
    return MappingProxyType(value)


def _require_allowed_candle_request(
    request: HttpRequest,
    allowed_symbols: frozenset[str],
) -> None:
    if not isinstance(request, HttpRequest) or request.method != "GET":
        raise CandleRunError("ENDPOINT_NOT_ALLOWED")
    try:
        parsed = urlsplit(request.url)
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise CandleRunError("ENDPOINT_NOT_ALLOWED") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != "openapi.tossinvest.com"
        or parsed.path != "/api/v1/candles"
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or len(query) != 5
        or tuple(name for name, _ in query)
        != ("symbol", "interval", "count", "adjusted", "before")
        or query[0][1] not in allowed_symbols
        or query[1][1] != _INTERVAL
        or query[2][1] != _COUNT
        or query[3][1] not in {"true", "false"}
        or not _valid_cursor(query[4][1])
    ):
        raise CandleRunError("ENDPOINT_NOT_ALLOWED")
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
        raise CandleRunError("ENDPOINT_NOT_ALLOWED")


def _valid_cursor(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 2048
        and not any(character in value for character in "\r\n\x00")
    )


def _boundary_url_response(
    value: object,
    error_code: str,
    limit: int,
    oversized_code: str,
) -> HttpResponse:
    try:
        return getattr(BOUNDARY, "_url_response")(
            value,
            error_code,
            limit,
            oversized_code,
        )
    except cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")) as error:
        raise CandleRunError(error.code) from None


def _boundary_http_error_response(
    value: HTTPError,
    error_code: str,
    limit: int,
    oversized_code: str,
) -> HttpResponse:
    try:
        return getattr(BOUNDARY, "_http_error_response")(
            value,
            error_code,
            limit,
            oversized_code,
        )
    except cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")) as error:
        raise CandleRunError(error.code) from None


def _all_captures(
    collections: Sequence[CombinedCandleCollection],
) -> tuple[RawHttpCapture, ...]:
    return tuple(
        capture
        for collection in collections
        for capture in _collection_captures(collection)
    )


def _collection_captures(
    collection: CombinedCandleCollection,
) -> tuple[RawHttpCapture, ...]:
    return (
        collection.adjusted_collection.captures
        + collection.native_collection.captures
    )


def _unique_captures(
    captures: Sequence[RawHttpCapture],
) -> tuple[RawHttpCapture, ...]:
    result: list[RawHttpCapture] = []
    seen: set[int] = set()
    for capture in captures:
        if id(capture) not in seen:
            seen.add(id(capture))
            result.append(capture)
    return tuple(result)


def _analysis_row_count(collections: Sequence[CombinedCandleCollection]) -> int:
    return sum(len(collection.rows) for collection in collections)


def _raw_body(
    run_id: str,
    collections: Sequence[CombinedCandleCollection],
) -> dict[str, object]:
    captures = _all_captures(collections)
    return {
        "schemaVersion": "rp001-toss-daily-candle-raw.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "sampleRole": "unseen_historical_confirmation",
        "captureCount": len(captures),
        "captures": [_capture_body(value) for value in captures],
    }


def _capture_body(capture: RawHttpCapture) -> dict[str, object]:
    return {
        "endpointId": capture.endpoint_id,
        "method": capture.method,
        "sanitizedUrl": capture.sanitized_url,
        "query": [
            {"name": name, "value": value} for name, value in capture.query
        ],
        "status": capture.status,
        "headers": [
            {"name": name, "value": value} for name, value in capture.headers
        ],
        "receivedAt": capture.received_at,
        "bodyBase64": capture.body_base64,
        "bodySha256": capture.body_sha256,
    }


def _processed_body(
    run_id: str,
    collections: Sequence[CombinedCandleCollection],
    raw_binding: LocalArtifactBinding,
    repository_root: Path,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-toss-daily-candle-processed.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "sampleRole": "unseen_historical_confirmation",
        "interval": _INTERVAL,
        "timezone": _SESSION_TIMEZONE,
        "requestedRange": {
            "startDate": _START_DATE.isoformat(),
            "endDate": _END_DATE.isoformat(),
            "inclusive": True,
        },
        "availability": {
            "signalTiming": "official_daily_close_usable_next_session",
            "providerSessionMembership": collections[0].provider_session_membership,
        },
        "rawArtifact": _binding_body(raw_binding, repository_root),
        "symbols": [_processed_symbol_body(value) for value in collections],
    }


def _processed_symbol_body(
    collection: CombinedCandleCollection,
) -> dict[str, object]:
    return {
        "symbol": collection.symbol,
        "analysisRows": [_paired_row_body(value) for value in collection.rows],
        "auditOnlyRows": {
            "adjusted": [
                _candle_row_body(value)
                for value in collection.adjusted_collection.audit_only_rows
            ],
            "native": [
                _candle_row_body(value)
                for value in collection.native_collection.audit_only_rows
            ],
        },
    }


def _paired_row_body(value: object) -> dict[str, object]:
    return {
        "sessionDate": _session_date(value.timestamp),
        "timestamp": value.timestamp,
        "currency": value.currency,
        "adjusted": _price_volume_body(value.adjusted),
        "native": _price_volume_body(value.native),
    }


def _candle_row_body(value: CandleRow) -> dict[str, object]:
    body = {
        "sessionDate": _session_date(value.timestamp),
        "timestamp": value.timestamp,
        "currency": value.currency,
    }
    body.update(_price_volume_body(value))
    return body


def _price_volume_body(value: CandleRow) -> dict[str, object]:
    return {
        "openPrice": _scalar_body(value.open_price),
        "highPrice": _scalar_body(value.high_price),
        "lowPrice": _scalar_body(value.low_price),
        "closePrice": _scalar_body(value.close_price),
        "volume": _scalar_body(value.volume),
    }


def _scalar_body(value: object) -> dict[str, object]:
    return {"kind": value.kind, "text": value.text}


def _session_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(ZoneInfo(_SESSION_TIMEZONE)).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        raise CandleRunError("INVALID_TIMESTAMP") from None


def _scope_body(
    arguments: CandleRunArguments,
    verified: _VerifiedInputs,
) -> dict[str, object]:
    by_role = {value.role: value.to_lineage_body() for value in verified.files}
    return {
        "schemaVersion": "rp001-toss-daily-candle-scope.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": arguments.run_id,
        "status": "frozen_scope_executed_without_reselection",
        "symbols": list(_SELECTED_SYMBOLS),
        "startDate": _START_DATE.isoformat(),
        "endDate": _END_DATE.isoformat(),
        "interval": _INTERVAL,
        "timezone": _SESSION_TIMEZONE,
        "count": 200,
        "initialBefore": _INITIAL_BEFORE,
        "adjustedModes": [True, False],
        "sampleRole": "unseen_historical_confirmation",
        "sampleFreeze": by_role["sample_freeze"],
        "mercFreeze": by_role["merc_freeze"],
        "freezeLedgerEvent": by_role["freeze_ledger_event"],
        "sourceContract": by_role["source_contract"],
        "operationalDisposition": "NoTrade/no integration",
    }


def _exposure_body(
    run_id: str,
    collections: Sequence[CombinedCandleCollection],
    raw: LocalArtifactBinding,
    processed: LocalArtifactBinding,
    repository_root: Path,
    clock: Clock,
) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-toss-daily-candle-exposure.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": run_id,
        "status": "price_volume_opened",
        "metadataPreviouslyOpened": True,
        "priceVolumeOpened": True,
        "outcomesPerformanceOpened": False,
        "ordersAccountsAssetsAccessed": False,
        "symbolCount": len(collections),
        "analysisRowCount": _analysis_row_count(collections),
        "captureCount": len(_all_captures(collections)),
        "openedAt": _safe_timestamp(clock),
        "rawArtifact": _binding_body(raw, repository_root),
        "processedArtifact": _binding_body(processed, repository_root),
        "operationalDisposition": "NoTrade/no integration",
    }


def _manifest_body(
    arguments: CandleRunArguments,
    verified: _VerifiedInputs,
    collections: Sequence[CombinedCandleCollection],
    bindings: Sequence[LocalArtifactBinding],
    repository_root: Path,
    clock: Clock,
) -> dict[str, object]:
    roles = ("raw_candles", "processed_candles", "candle_scope", "candle_exposure")
    return {
        "schemaVersion": "rp001-toss-daily-candle-manifest.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "runId": arguments.run_id,
        "status": "research_only_collection_complete",
        "createdAt": _safe_timestamp(clock),
        "sampleRole": "unseen_historical_confirmation",
        "symbols": list(_SELECTED_SYMBOLS),
        "analysisRowCount": _analysis_row_count(collections),
        "captureCount": len(_all_captures(collections)),
        "sourceLineage": [value.to_lineage_body() for value in verified.files],
        "artifacts": [
            {"role": role, **_binding_body(binding, repository_root)}
            for role, binding in zip(roles, bindings, strict=True)
        ],
        "exposureState": {
            "metadataPreviouslyOpened": True,
            "priceVolumeOpened": True,
            "outcomesPerformanceOpened": False,
            "ordersAccountsAssetsAccessed": False,
        },
        "operationalDisposition": "NoTrade/no integration",
    }


def _publish(
    store: object,
    path: Path,
    body: Mapping[str, object],
    published: list[LocalArtifactBinding],
) -> LocalArtifactBinding:
    binding = store.publish_json(path, body)
    published.append(binding)
    return binding


def _binding_body(
    binding: LocalArtifactBinding,
    repository_root: Path,
) -> dict[str, object]:
    try:
        relative = binding.path.relative_to(repository_root).as_posix()
    except ValueError:
        raise CandleRunError("INPUT_PATH_INVALID") from None
    return {"path": relative, "sha256": binding.artifact_sha256}


def _rollback_quietly(
    store: object,
    bindings: Sequence[LocalArtifactBinding],
) -> None:
    try:
        getattr(BOUNDARY, "_rollback_bindings")(store, bindings)
        store.remove_run_directory_if_empty()
    except BaseException:
        return


def _error_code(caught: BaseException, stage: str) -> str:
    if isinstance(caught, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return "RUN_INTERRUPTED"
    if isinstance(caught, CandleRunError):
        return caught.code
    if isinstance(caught, cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError"))):
        return caught.code
    if isinstance(caught, LocalEvidenceError):
        return "EVIDENCE_PUBLICATION_FAILED"
    return "INTERNAL_RUN_ERROR" if stage == "evidence" else "CANDLE_TRANSPORT_ERROR"


def _is_boundary_error(value: BaseException, code: str) -> bool:
    return isinstance(
        value,
        cast(type[BaseException], getattr(BOUNDARY, "MetadataRunError")),
    ) and getattr(value, "code", None) == code


def _safe_timestamp(clock: Clock) -> str:
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("timezone required")
        normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    except BaseException:
        normalized = datetime.now(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise CandleRunError("INVALID_ARGUMENTS")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(
        description="Collect the frozen Toss daily-candle research sample.",
    )
    path_options = (
        "repository-root", "credentials-path", "predecessor-contract-path",
        "source-contract-path", "sample-freeze-path", "merc-freeze-path",
        "freeze-ledger-event-path",
        "runner-source-path", "runner-test-path", "boundary-source-path",
        "boundary-test-path", "collector-source-path", "collector-test-path",
        "local-evidence-source-path", "local-evidence-test-path",
        "sensitive-policy-source-path", "sensitive-policy-test-path",
        "output-directory", "ledger-directory",
    )
    for option in path_options:
        parser.add_argument(f"--{option}", required=True, type=Path)
    hash_options = (
        "predecessor-contract-sha256", "source-contract-sha256",
        "sample-freeze-sha256", "merc-freeze-sha256", "runner-source-sha256",
        "freeze-ledger-event-sha256",
        "runner-test-sha256", "boundary-source-sha256", "boundary-test-sha256",
        "collector-source-sha256", "collector-test-sha256",
        "local-evidence-source-sha256", "local-evidence-test-sha256",
        "sensitive-policy-source-sha256", "sensitive-policy-test-sha256",
    )
    for option in hash_options:
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--run-id", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    opener: UrlOpener | None = None,
    clock: Clock | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    parsed_run_id = "unavailable"
    try:
        namespace = build_argument_parser().parse_args(argv)
        arguments = CandleRunArguments(**vars(namespace))
        parsed_run_id = arguments.run_id
        summary = run_daily_candle_collection(
            arguments,
            opener=opener,
            clock=clock,
        )
    except CandleRunError as error:
        _write_summary(
            output_stream,
            CandleRunSummary(
                run_id=parsed_run_id if _RUN_ID_PATTERN.fullmatch(parsed_run_id) else "unavailable",
                status="failed",
                symbol_count=0,
                analysis_row_count=0,
                capture_count=0,
                artifact_hashes=error.artifact_hashes,
            ),
        )
        error_stream.write(f"{error.code}\n")
        return 1
    _write_summary(output_stream, summary)
    return 0


def _write_summary(stream: TextIO, summary: CandleRunSummary) -> None:
    stream.write(
        canonical_json_bytes(
            {
                "runId": summary.run_id,
                "status": summary.status,
                "symbolCount": summary.symbol_count,
                "analysisRowCount": summary.analysis_row_count,
                "captureCount": summary.capture_count,
                "artifactHashes": dict(summary.artifact_hashes),
            }
        ).decode("utf-8")
        + "\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
