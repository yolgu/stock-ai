"""Resume-safe execution of frozen Toss whole-period daily scopes."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol
from urllib.request import build_opener

import pyarrow.parquet as parquet

from rp001.local_evidence import AppendOnlyLocalLedger
from rp001.toss_research_collector import (
    CandleCollection,
    CollectorError,
    RawHttpCapture,
    TossResearchCollector,
)
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
)
from rp001_s2.daily_archive_storage import (
    CanonicalDailyBar,
    DailyArchiveStorageError,
    ImmutableDailyArchiveStorage,
    StoredDailyArchive,
    StoredDailyFailureEvidence,
)
from rp001_s2.toss_boundary import (
    ReadOnlyBoundaryError,
    StrictCandleTransport,
    _Opener,
    _RejectRedirectHandler,
    _authenticate,
    load_credentials,
)
from rp001_s2.toss_daily_canonicalization import (
    DailyCanonicalizationError,
    canonicalize_toss_daily_collection,
)
from rp001_s2.toss_intraday_run import load_secure_toss_environment


_TERMINAL_EVENT_TYPE = "toss_daily_scope_terminal"
_DEFAULT_REQUESTS_PER_SECOND = 0.1
_MAX_REQUESTS_PER_SECOND = 4.0


class TossDailyRunError(ValueError):
    def __init__(
        self,
        code: str,
        captures: tuple[RawHttpCapture, ...] = (),
    ) -> None:
        self.code = code
        self.captures = captures
        super().__init__(code)


class DailyBatchScopeStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    DATA_UNAVAILABLE = "data_unavailable"
    FAILED = "failed"
    INVALID = "invalid"
    BLOCKED_STORAGE_CAPACITY = "blocked_storage_capacity"


class DailyMarketDataPacer:
    def __init__(
        self,
        requests_per_second: float = _DEFAULT_REQUESTS_PER_SECOND,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            isinstance(requests_per_second, bool)
            or not isinstance(requests_per_second, (int, float))
            or not math.isfinite(requests_per_second)
            or not 0 < requests_per_second <= _MAX_REQUESTS_PER_SECOND
        ):
            raise TossDailyRunError("daily_rate_invalid")
        self._requests_per_second = float(requests_per_second)
        self._interval_seconds = 1.0 / self._requests_per_second
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    @property
    def requests_per_second(self) -> float:
        return self._requests_per_second

    def __call__(self) -> None:
        with self._lock:
            now = self._monotonic()
            if self._last_request_at is None:
                self._last_request_at = now
                return
            remaining = self._interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)
                now = self._monotonic()
            self._last_request_at = now


class TossDailySession:
    def __init__(
        self,
        *,
        opener: _Opener,
        token: str,
        clock: Callable[[], datetime],
    ) -> None:
        if not token or any(character in token for character in "\r\n\x00"):
            raise TossDailyRunError("session_invalid")
        self._opener = opener
        self._token = token
        self._clock = clock

    def __repr__(self) -> str:
        return "TossDailySession(<redacted>)"

    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: Callable[[], None],
    ) -> CandleCollection:
        _validate_scope(scope)
        if not self._token:
            raise TossDailyRunError("session_closed")
        try:
            collector = TossResearchCollector(
                transport=StrictCandleTransport(
                    opener=self._opener,
                    allowed_symbols=(scope.symbol,),
                    request_pacer=request_pacer,
                ),
                token_supplier=lambda: self._token,
                clock=self._clock,
            )
            return collector.collect_candles(
                symbol=scope.symbol,
                start=scope.start_at.date(),
                end=scope.end_at.date() - timedelta(days=1),
                before=_format_utc(scope.end_at),
                adjusted=scope.adjustment_mode == "adjusted",
            )
        except CollectorError as error:
            raise TossDailyRunError(error.code, error.captures) from None
        except ReadOnlyBoundaryError as error:
            raise TossDailyRunError(error.code, error.captures) from None

    def close(self) -> None:
        self._token = ""


def open_toss_daily_session(
    *,
    environment: MutableMapping[str, str],
    clock: Callable[[], datetime],
    opener: _Opener | None = None,
) -> TossDailySession:
    credentials = load_credentials(environment)
    effective_opener = opener or build_opener(_RejectRedirectHandler())
    try:
        token = _authenticate(effective_opener, credentials, clock)
        return TossDailySession(
            opener=effective_opener,
            token=token,
            clock=clock,
        )
    except ReadOnlyBoundaryError as error:
        raise TossDailyRunError(error.code, error.captures) from None


class CredentialLoader(Protocol):
    def __call__(self, path: Path) -> MutableMapping[str, str]: ...


class Session(Protocol):
    def collect(
        self,
        scope: CollectionScope,
        *,
        request_pacer: Callable[[], None],
    ) -> CandleCollection: ...

    def close(self) -> None: ...


class SessionFactory(Protocol):
    def __call__(
        self,
        *,
        environment: MutableMapping[str, str],
        clock: Callable[[], datetime],
    ) -> Session: ...


Canonicalizer = Callable[
    [CollectionScope, CandleCollection],
    tuple[CanonicalDailyBar, ...],
]


@dataclass(frozen=True)
class TossDailyScopeTerminal:
    scope_index: int
    acquisition_key: str
    status: DailyBatchScopeStatus
    error_code: str | None
    row_count: int
    capture_count: int
    resumed_from_verified_archive: bool
    archive: StoredDailyArchive | None
    failure_evidence: StoredDailyFailureEvidence | None


@dataclass(frozen=True)
class TossDailyBatchSummary:
    terminals: tuple[TossDailyScopeTerminal, ...]

    @property
    def completed_count(self) -> int:
        return self._count(DailyBatchScopeStatus.COMPLETED)

    @property
    def partial_count(self) -> int:
        return self._count(DailyBatchScopeStatus.PARTIAL)

    @property
    def data_unavailable_count(self) -> int:
        return self._count(DailyBatchScopeStatus.DATA_UNAVAILABLE)

    @property
    def failed_count(self) -> int:
        return self._count(DailyBatchScopeStatus.FAILED)

    @property
    def invalid_count(self) -> int:
        return self._count(DailyBatchScopeStatus.INVALID)

    @property
    def resumed_count(self) -> int:
        return sum(value.resumed_from_verified_archive for value in self.terminals)

    @property
    def total_row_count(self) -> int:
        return sum(value.row_count for value in self.terminals)

    def _count(self, status: DailyBatchScopeStatus) -> int:
        return sum(value.status is status for value in self.terminals)


class _LazySession:
    def __init__(
        self,
        *,
        credential_file: Path,
        credential_loader: CredentialLoader,
        session_factory: SessionFactory,
        clock: Callable[[], datetime],
    ) -> None:
        self._credential_file = credential_file
        self._credential_loader = credential_loader
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._failure: TossDailyRunError | None = None

    def collect(
        self,
        scope: CollectionScope,
        request_pacer: Callable[[], None],
    ) -> CandleCollection:
        if self._session is None:
            if self._failure is not None:
                raise TossDailyRunError(
                    self._failure.code,
                    self._failure.captures,
                )
            environment = self._credential_loader(self._credential_file)
            try:
                self._session = self._session_factory(
                    environment=environment,
                    clock=self._clock,
                )
            except TossDailyRunError as error:
                self._failure = error
                raise
            except Exception:
                self._failure = TossDailyRunError("session_open_failed")
                raise self._failure from None
            finally:
                environment.clear()
        return self._session.collect(scope, request_pacer=request_pacer)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._failure = None


def run_toss_daily_batch(
    scopes: tuple[CollectionScope, ...],
    *,
    credential_file: Path,
    archive_root: Path,
    ledger_root: Path,
    clock: Callable[[], datetime],
    request_pacer: Callable[[], None] | None = None,
    free_bytes: Callable[[Path], int] | None = None,
    credential_loader: CredentialLoader = load_secure_toss_environment,
    session_factory: SessionFactory = open_toss_daily_session,
    canonicalizer: Canonicalizer = canonicalize_toss_daily_collection,
) -> TossDailyBatchSummary:
    if (
        type(scopes) is not tuple
        or not scopes
        or not isinstance(credential_file, Path)
        or not isinstance(archive_root, Path)
        or not isinstance(ledger_root, Path)
        or not ledger_root.is_absolute()
        or not callable(clock)
    ):
        raise TossDailyRunError("batch_input_invalid")
    storage = ImmutableDailyArchiveStorage(archive_root, free_bytes=free_bytes)
    ledger = AppendOnlyLocalLedger(ledger_root)
    pacer = request_pacer or DailyMarketDataPacer()
    session = _LazySession(
        credential_file=credential_file,
        credential_loader=credential_loader,
        session_factory=session_factory,
        clock=clock,
    )
    terminals: list[TossDailyScopeTerminal] = []
    try:
        with ledger.transaction() as transaction:
            for scope_index, scope in enumerate(scopes):
                terminal = _resume_or_collect(
                    scope_index,
                    scope,
                    storage,
                    session,
                    pacer,
                    canonicalizer,
                )
                transaction.append(
                    _TERMINAL_EVENT_TYPE,
                    _terminal_payload(scope, terminal),
                    _format_utc(clock()),
                )
                terminals.append(terminal)
    finally:
        session.close()
    return TossDailyBatchSummary(tuple(terminals))


def _resume_or_collect(
    scope_index: int,
    scope: CollectionScope,
    storage: ImmutableDailyArchiveStorage,
    session: _LazySession,
    pacer: Callable[[], None],
    canonicalizer: Canonicalizer,
) -> TossDailyScopeTerminal:
    try:
        _validate_scope(scope)
        existing = storage.find_verified_archive(scope)
        if existing is not None:
            manifest = _read_manifest(existing)
            completion = manifest["acquisitionCompletion"]
            return TossDailyScopeTerminal(
                scope_index=scope_index,
                acquisition_key=scope.acquisition_key,
                status=DailyBatchScopeStatus(completion["terminalStatus"]),
                error_code=None,
                row_count=parquet.read_metadata(existing.canonical_path).num_rows,
                capture_count=len(existing.raw_paths),
                resumed_from_verified_archive=True,
                archive=existing,
                failure_evidence=None,
            )
        collection = session.collect(scope, pacer)
        rows = canonicalizer(scope, collection)
        completion = _completion(scope, collection, rows)
        archive = storage.write_archive(
            scope=scope,
            captures=collection.captures,
            rows=rows,
            completion=completion,
        )
        return TossDailyScopeTerminal(
            scope_index=scope_index,
            acquisition_key=scope.acquisition_key,
            status=DailyBatchScopeStatus(completion.terminal_status.value),
            error_code=None,
            row_count=len(rows),
            capture_count=len(collection.captures),
            resumed_from_verified_archive=False,
            archive=archive,
            failure_evidence=None,
        )
    except TossDailyRunError as error:
        return _failure_terminal(scope_index, scope, storage, error.code, error.captures)
    except DailyCanonicalizationError as error:
        return _failure_terminal(
            scope_index,
            scope,
            storage,
            error.code,
            (),
            status=DailyBatchScopeStatus.INVALID,
        )
    except DailyArchiveStorageError as error:
        status = (
            DailyBatchScopeStatus.BLOCKED_STORAGE_CAPACITY
            if error.code == "blocked_storage_capacity"
            else DailyBatchScopeStatus.INVALID
        )
        return _failure_terminal(
            scope_index,
            scope,
            storage,
            error.code,
            (),
            status=status,
        )
    except Exception:
        return _failure_terminal(
            scope_index,
            scope,
            storage,
            "unexpected_failure",
            (),
        )


def _failure_terminal(
    scope_index: int,
    scope: CollectionScope,
    storage: ImmutableDailyArchiveStorage,
    code: str,
    captures: tuple[RawHttpCapture, ...],
    *,
    status: DailyBatchScopeStatus = DailyBatchScopeStatus.FAILED,
) -> TossDailyScopeTerminal:
    evidence: StoredDailyFailureEvidence | None = None
    if captures:
        try:
            evidence = storage.write_failure_evidence(
                scope=scope,
                captures=captures,
                error_code=code,
            )
        except DailyArchiveStorageError:
            evidence = None
    return TossDailyScopeTerminal(
        scope_index=scope_index,
        acquisition_key=scope.acquisition_key,
        status=status,
        error_code=code,
        row_count=0,
        capture_count=len(captures),
        resumed_from_verified_archive=False,
        archive=None,
        failure_evidence=evidence,
    )


def _completion(
    scope: CollectionScope,
    collection: CandleCollection,
    rows: tuple[CanonicalDailyBar, ...],
) -> AcquisitionCompletion:
    reached = any(
        _session_date(row.timestamp) < scope.start_at.date()
        for row in collection.audit_only_rows
    )
    if rows and reached:
        status = AcquisitionTerminalStatus.COMPLETED
        reason = "requested_start_reached"
    elif rows:
        status = AcquisitionTerminalStatus.PARTIAL
        reason = "provider_terminal_before_start"
    else:
        status = AcquisitionTerminalStatus.DATA_UNAVAILABLE
        reason = "data_unavailable"
    return AcquisitionCompletion(
        requested_start_reached=reached,
        completion_reason=reason,
        terminal_status=status,
        analysis_row_count=len(rows),
        audit_row_count=0,
        returned_row_count=len(rows),
    )


def _validate_scope(scope: object) -> None:
    if (
        not isinstance(scope, CollectionScope)
        or scope.provider != "toss"
        or scope.feed != "provider_all"
        or scope.interval != "1d"
        or scope.adjustment_mode not in {"native", "adjusted"}
        or scope.session_scope != "provider_all"
        or scope.start_at.hour
        or scope.start_at.minute
        or scope.start_at.second
        or scope.start_at.microsecond
        or scope.end_at.hour
        or scope.end_at.minute
        or scope.end_at.second
        or scope.end_at.microsecond
    ):
        raise TossDailyRunError("scope_not_allowed")


def _terminal_payload(
    scope: CollectionScope,
    terminal: TossDailyScopeTerminal,
) -> dict[str, object]:
    return {
        "scopeIndex": terminal.scope_index,
        "acquisitionKey": terminal.acquisition_key,
        "scope": scope.to_canonical_body(),
        "status": terminal.status.value,
        "errorCode": terminal.error_code,
        "rowCount": terminal.row_count,
        "captureCount": terminal.capture_count,
        "resumedFromVerifiedArchive": terminal.resumed_from_verified_archive,
        "manifestPath": (
            str(terminal.archive.manifest_path) if terminal.archive else None
        ),
        "failureEvidenceManifestPath": (
            str(terminal.failure_evidence.manifest_path)
            if terminal.failure_evidence
            else None
        ),
        "ordersAccountsAssetsAccessed": False,
    }


def _read_manifest(stored: StoredDailyArchive) -> dict[str, object]:
    import json

    value = json.loads(stored.manifest_path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise TossDailyRunError("archive_manifest_invalid")
    return value


def _session_date(value: str):
    from zoneinfo import ZoneInfo

    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    return parsed.astimezone(ZoneInfo("America/New_York")).date()


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )
