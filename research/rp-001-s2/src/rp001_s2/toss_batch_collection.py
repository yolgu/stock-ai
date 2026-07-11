"""Resumable, append-only execution of frozen Toss minute collection scopes."""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

from rp001.local_evidence import AppendOnlyLocalLedger, LocalLedgerEntry
from rp001.toss_research_collector import RawHttpCapture
from rp001_s2.archive_contract import CollectionScope
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
    ArchiveStorageError,
    CanonicalMinuteBar,
    ImmutableArchiveStorage,
    StoredArchive,
    StoredFailureEvidence,
)
from rp001_s2.intraday_measurement import IntradayCandleCollection
from rp001_s2.minute_canonicalization import (
    MinuteCanonicalizationError,
    canonicalize_toss_collection,
)
from rp001_s2.toss_intraday_run import (
    IntradayRunError,
    load_secure_toss_environment,
    run_toss_minute_shard,
    validate_toss_minute_scope,
)


_TERMINAL_EVENT_TYPE = "toss_minute_scope_terminal"
_DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.0
_STABLE_ERROR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
_INVALID_ARCHIVE_CODES = frozenset(
    {
        "archive_already_exists",
        "archive_input_invalid",
        "acquisition_completion_invalid",
        "canonical_minute_bar_invalid",
        "raw_capture_invalid",
    }
)


class TossBatchCollectionError(ValueError):
    """Stable rejection of an invalid batch execution boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BatchScopeStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    DATA_UNAVAILABLE = "data_unavailable"
    FAILED = "failed"
    INVALID = "invalid"
    BLOCKED_STORAGE_CAPACITY = "blocked_storage_capacity"


class CredentialLoader(Protocol):
    def __call__(self, path: Path) -> MutableMapping[str, str]:
        """Load a one-shot credential environment from a private file path."""


class TossShardRunner(Protocol):
    def __call__(
        self,
        scope: CollectionScope,
        *,
        environment: MutableMapping[str, str],
        clock: Callable[[], datetime],
        request_pacer: Callable[[], None],
    ) -> IntradayCandleCollection:
        """Collect one frozen Toss minute scope."""


class TossCanonicalizer(Protocol):
    def __call__(
        self,
        scope: CollectionScope,
        collection: IntradayCandleCollection,
    ) -> tuple[CanonicalMinuteBar, ...]:
        """Convert one collection into immutable canonical rows."""


class GlobalMarketDataPacer:
    """Serialize market-data calls behind one batch-wide minimum interval."""

    def __init__(
        self,
        minimum_interval_seconds: float = _DEFAULT_MINIMUM_INTERVAL_SECONDS,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            isinstance(minimum_interval_seconds, bool)
            or not isinstance(minimum_interval_seconds, (int, float))
            or minimum_interval_seconds < _DEFAULT_MINIMUM_INTERVAL_SECONDS
        ):
            raise TossBatchCollectionError("market_data_interval_invalid")
        self._minimum_interval_seconds = float(minimum_interval_seconds)
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    @property
    def minimum_interval_seconds(self) -> float:
        return self._minimum_interval_seconds

    def __call__(self) -> None:
        with self._lock:
            now = self._monotonic()
            if self._last_request_at is None:
                self._last_request_at = now
                return
            remaining = self._minimum_interval_seconds - (
                now - self._last_request_at
            )
            if remaining > 0:
                self._sleeper(remaining)
                now = self._monotonic()
            self._last_request_at = now


@dataclass(frozen=True)
class TossMinuteScopeTerminal:
    scope_index: int
    acquisition_key: str
    status: BatchScopeStatus
    error_code: str | None
    row_count: int
    capture_count: int
    manifest_path: Path | None
    manifest_sha256_path: Path | None
    acquisition_completion: AcquisitionCompletion | None
    resumed_from_verified_archive: bool
    event_path: Path
    event_sha256_path: Path
    event_sha256: str
    failure_evidence: StoredFailureEvidence | None
    failure_evidence_error_code: str | None
    safe_captures: tuple[RawHttpCapture, ...] = field(repr=False)

    @property
    def requested_start_reached(self) -> bool | None:
        if self.acquisition_completion is None:
            return None
        return self.acquisition_completion.requested_start_reached

    @property
    def completion_reason(self) -> str | None:
        if self.acquisition_completion is None:
            return None
        return self.acquisition_completion.completion_reason

    @property
    def failure_evidence_manifest_path(self) -> Path | None:
        if self.failure_evidence is None:
            return None
        return self.failure_evidence.manifest_path

    @property
    def failure_evidence_manifest_sha256_path(self) -> Path | None:
        if self.failure_evidence is None:
            return None
        return self.failure_evidence.manifest_sha256_path


@dataclass(frozen=True)
class TossMinuteBatchSummary:
    terminals: tuple[TossMinuteScopeTerminal, ...]
    manifest_paths: tuple[Path, ...]
    failure_evidence_manifest_paths: tuple[Path, ...]
    total_row_count: int
    total_capture_count: int

    @property
    def completed_count(self) -> int:
        return self._status_count(BatchScopeStatus.COMPLETED)

    @property
    def data_unavailable_count(self) -> int:
        return self._status_count(BatchScopeStatus.DATA_UNAVAILABLE)

    @property
    def partial_count(self) -> int:
        return self._status_count(BatchScopeStatus.PARTIAL)

    @property
    def failed_count(self) -> int:
        return self._status_count(BatchScopeStatus.FAILED)

    @property
    def invalid_count(self) -> int:
        return self._status_count(BatchScopeStatus.INVALID)

    @property
    def blocked_storage_capacity_count(self) -> int:
        return self._status_count(BatchScopeStatus.BLOCKED_STORAGE_CAPACITY)

    @property
    def resumed_count(self) -> int:
        return sum(
            terminal.resumed_from_verified_archive for terminal in self.terminals
        )

    def _status_count(self, status: BatchScopeStatus) -> int:
        return sum(terminal.status is status for terminal in self.terminals)


@dataclass(frozen=True)
class _ScopeOutcome:
    acquisition_key: str
    status: BatchScopeStatus
    error_code: str | None = None
    row_count: int = 0
    capture_count: int = 0
    capture_sha256s: tuple[str, ...] = ()
    safe_captures: tuple[RawHttpCapture, ...] = field(default=(), repr=False)
    stored_archive: StoredArchive | None = None
    acquisition_completion: AcquisitionCompletion | None = None
    failure_evidence: StoredFailureEvidence | None = None
    failure_evidence_error_code: str | None = None
    resumed_from_verified_archive: bool = False


@dataclass(frozen=True)
class _VerifiedArchive:
    stored_archive: StoredArchive
    row_count: int
    capture_count: int
    capture_sha256s: tuple[str, ...]
    acquisition_completion: AcquisitionCompletion | None


def run_toss_minute_batch(
    scopes: tuple[CollectionScope, ...],
    *,
    credential_file: Path,
    archive_root: Path,
    ledger_root: Path,
    clock: Callable[[], datetime],
    request_pacer: Callable[[], None] | None = None,
    free_bytes: Callable[[Path], int] | None = None,
    credential_loader: CredentialLoader = load_secure_toss_environment,
    shard_runner: TossShardRunner = run_toss_minute_shard,
    canonicalizer: TossCanonicalizer = canonicalize_toss_collection,
) -> TossMinuteBatchSummary:
    """Execute every scope in order and append one terminal event per scope."""
    _validate_batch_input(scopes, credential_file, archive_root, ledger_root)
    storage = ImmutableArchiveStorage(archive_root, free_bytes=free_bytes)
    ledger = AppendOnlyLocalLedger(ledger_root.resolve())
    effective_pacer = (
        request_pacer if request_pacer is not None else GlobalMarketDataPacer()
    )
    terminals: list[TossMinuteScopeTerminal] = []

    with ledger.transaction() as ledger_transaction:
        for scope_index, scope in enumerate(scopes):
            outcome = _resume_or_collect(
                scope=scope,
                credential_file=credential_file,
                archive_root=archive_root,
                storage=storage,
                clock=clock,
                request_pacer=effective_pacer,
                credential_loader=credential_loader,
                shard_runner=shard_runner,
                canonicalizer=canonicalizer,
            )
            entry = ledger_transaction.append(
                _TERMINAL_EVENT_TYPE,
                _terminal_payload(scope_index, scope, outcome),
                _format_utc(clock()),
            )
            terminals.append(_terminal(scope_index, outcome, entry))

    terminal_tuple = tuple(terminals)
    return TossMinuteBatchSummary(
        terminals=terminal_tuple,
        manifest_paths=tuple(
            terminal.manifest_path
            for terminal in terminal_tuple
            if terminal.manifest_path is not None
        ),
        failure_evidence_manifest_paths=tuple(
            terminal.failure_evidence_manifest_path
            for terminal in terminal_tuple
            if terminal.failure_evidence_manifest_path is not None
        ),
        total_row_count=sum(terminal.row_count for terminal in terminal_tuple),
        total_capture_count=sum(
            terminal.capture_count for terminal in terminal_tuple
        ),
    )


def _validate_batch_input(
    scopes: object,
    credential_file: object,
    archive_root: object,
    ledger_root: object,
) -> None:
    if type(scopes) is not tuple or any(
        not isinstance(scope, CollectionScope) for scope in scopes
    ):
        raise TossBatchCollectionError("scopes_must_be_frozen_tuple")
    if (
        not isinstance(credential_file, Path)
        or not isinstance(archive_root, Path)
        or not isinstance(ledger_root, Path)
    ):
        raise TossBatchCollectionError("batch_path_invalid")
    if not ledger_root.is_absolute():
        raise TossBatchCollectionError("ledger_root_must_be_absolute")


def _resume_or_collect(
    *,
    scope: CollectionScope,
    credential_file: Path,
    archive_root: Path,
    storage: ImmutableArchiveStorage,
    clock: Callable[[], datetime],
    request_pacer: Callable[[], None],
    credential_loader: CredentialLoader,
    shard_runner: TossShardRunner,
    canonicalizer: TossCanonicalizer,
) -> _ScopeOutcome:
    try:
        validate_toss_minute_scope(scope)
    except IntradayRunError as error:
        return _invalid_outcome(storage, scope, error.code)

    verified = _verified_existing_archive(scope, archive_root, storage)
    if verified is not None:
        status = _collection_status(verified.acquisition_completion)
        return _ScopeOutcome(
            acquisition_key=scope.acquisition_key,
            status=status,
            row_count=verified.row_count,
            capture_count=verified.capture_count,
            capture_sha256s=verified.capture_sha256s,
            stored_archive=verified.stored_archive,
            acquisition_completion=verified.acquisition_completion,
            resumed_from_verified_archive=True,
        )

    return _collect_and_store(
        scope=scope,
        credential_file=credential_file,
        storage=storage,
        clock=clock,
        request_pacer=request_pacer,
        credential_loader=credential_loader,
        shard_runner=shard_runner,
        canonicalizer=canonicalizer,
    )


def _collect_and_store(
    *,
    scope: CollectionScope,
    credential_file: Path,
    storage: ImmutableArchiveStorage,
    clock: Callable[[], datetime],
    request_pacer: Callable[[], None],
    credential_loader: CredentialLoader,
    shard_runner: TossShardRunner,
    canonicalizer: TossCanonicalizer,
) -> _ScopeOutcome:
    safe_captures: tuple[RawHttpCapture, ...] = ()
    completion: AcquisitionCompletion | None = None
    row_count = 0
    environment: MutableMapping[str, str] | None = None
    try:
        environment = credential_loader(credential_file)
        collection = shard_runner(
            scope,
            environment=environment,
            clock=clock,
            request_pacer=request_pacer,
        )
        safe_captures = _safe_capture_tuple(collection.captures)
        rows = canonicalizer(scope, collection)
        row_count = len(rows)
        completion = _acquisition_completion(collection, row_count)
        stored = storage.write_archive(
            scope=scope,
            captures=safe_captures,
            rows=rows,
            completion=completion,
        )
        return _ScopeOutcome(
            acquisition_key=scope.acquisition_key,
            status=_collection_status(completion),
            row_count=row_count,
            capture_count=len(safe_captures),
            capture_sha256s=tuple(
                capture.body_sha256 for capture in safe_captures
            ),
            safe_captures=safe_captures,
            stored_archive=stored,
            acquisition_completion=completion,
        )
    except IntradayRunError as error:
        captures = _safe_capture_tuple(error.captures)
        return _failed_outcome(storage, scope, error.code, captures)
    except MinuteCanonicalizationError as error:
        return _invalid_outcome(storage, scope, error.code, safe_captures)
    except ArchiveStorageError as error:
        return _archive_failure_outcome(
            storage,
            scope,
            error.code,
            safe_captures,
            row_count=row_count,
        )
    except Exception:
        return _failed_outcome(
            storage,
            scope,
            "unexpected_failure",
            safe_captures,
        )
    finally:
        if environment is not None:
            environment.clear()


def _verified_existing_archive(
    scope: CollectionScope,
    archive_root: Path,
    storage: ImmutableArchiveStorage,
) -> _VerifiedArchive | None:
    stored = _stored_archive(scope, archive_root)
    if not stored.archive_directory.exists():
        return None
    try:
        completion = storage.load_resumable_completion(stored)
        manifest = json.loads(stored.manifest_path.read_bytes())
        canonical = manifest["canonicalArtifact"]
        raw_artifacts = manifest["rawArtifacts"]
        return _VerifiedArchive(
            stored_archive=stored,
            row_count=canonical["rowCount"],
            capture_count=len(raw_artifacts),
            capture_sha256s=tuple(
                artifact["uncompressedSha256"] for artifact in raw_artifacts
            ),
            acquisition_completion=completion,
        )
    except (ArchiveStorageError, KeyError, TypeError, ValueError):
        return None


def _stored_archive(
    scope: CollectionScope,
    archive_root: Path,
) -> StoredArchive:
    archive_directory = archive_root / scope.acquisition_key
    return StoredArchive(
        acquisition_key=scope.acquisition_key,
        archive_directory=archive_directory,
        raw_paths=tuple(sorted((archive_directory / "raw").glob("*.json.zst"))),
        canonical_path=archive_directory / "canonical/minute-bars.parquet",
        occurrence_path=(
            archive_directory / "canonical/minute-bar-occurrences.parquet"
        ),
        manifest_path=archive_directory / "manifest.json",
        manifest_sha256_path=archive_directory / "manifest.json.sha256",
    )


def _acquisition_completion(
    collection: IntradayCandleCollection,
    returned_row_count: int,
) -> AcquisitionCompletion:
    if returned_row_count == 0:
        terminal_status = AcquisitionTerminalStatus.DATA_UNAVAILABLE
    elif not collection.requested_start_reached:
        terminal_status = AcquisitionTerminalStatus.PARTIAL
    else:
        terminal_status = AcquisitionTerminalStatus.COMPLETED
    return AcquisitionCompletion(
        requested_start_reached=collection.requested_start_reached,
        completion_reason=collection.completion_reason,
        terminal_status=terminal_status,
        analysis_row_count=len(collection.analysis_rows),
        audit_row_count=len(collection.audit_only_rows),
        returned_row_count=returned_row_count,
    )


def _collection_status(
    completion: AcquisitionCompletion | None,
) -> BatchScopeStatus:
    if completion is None:
        return BatchScopeStatus.DATA_UNAVAILABLE
    if completion.terminal_status is AcquisitionTerminalStatus.PARTIAL:
        return BatchScopeStatus.PARTIAL
    if completion.terminal_status is AcquisitionTerminalStatus.COMPLETED:
        return BatchScopeStatus.COMPLETED
    return BatchScopeStatus.DATA_UNAVAILABLE


def _safe_capture_tuple(value: object) -> tuple[RawHttpCapture, ...]:
    if type(value) is not tuple or any(
        not isinstance(capture, RawHttpCapture) for capture in value
    ):
        return ()
    return value


def _invalid_outcome(
    storage: ImmutableArchiveStorage,
    scope: CollectionScope,
    error_code: str,
    captures: tuple[RawHttpCapture, ...] = (),
) -> _ScopeOutcome:
    return _persisted_error_outcome(
        storage,
        scope,
        BatchScopeStatus.INVALID,
        error_code,
        captures,
    )


def _failed_outcome(
    storage: ImmutableArchiveStorage,
    scope: CollectionScope,
    error_code: str,
    captures: tuple[RawHttpCapture, ...] = (),
) -> _ScopeOutcome:
    return _persisted_error_outcome(
        storage,
        scope,
        BatchScopeStatus.FAILED,
        error_code,
        captures,
    )


def _archive_failure_outcome(
    storage: ImmutableArchiveStorage,
    scope: CollectionScope,
    error_code: str,
    captures: tuple[RawHttpCapture, ...],
    *,
    row_count: int,
) -> _ScopeOutcome:
    if error_code == "blocked_storage_capacity":
        return _error_outcome(
            scope,
            BatchScopeStatus.BLOCKED_STORAGE_CAPACITY,
            error_code,
            captures,
            row_count=row_count,
        )
    status = (
        BatchScopeStatus.INVALID
        if error_code in _INVALID_ARCHIVE_CODES
        else BatchScopeStatus.FAILED
    )
    return _persisted_error_outcome(
        storage,
        scope,
        status,
        error_code,
        captures,
        row_count=row_count,
    )


def _persisted_error_outcome(
    storage: ImmutableArchiveStorage,
    scope: CollectionScope,
    status: BatchScopeStatus,
    error_code: str,
    captures: tuple[RawHttpCapture, ...],
    *,
    row_count: int = 0,
) -> _ScopeOutcome:
    safe_error_code = _safe_error_code(error_code)
    completion = _failure_completion(status, safe_error_code)
    evidence: StoredFailureEvidence | None = None
    evidence_error_code: str | None = None
    if captures:
        try:
            evidence = storage.write_failure_evidence(
                scope=scope,
                captures=captures,
                completion=completion,
            )
        except ArchiveStorageError as error:
            evidence_error_code = _safe_error_code(error.code)
    return _error_outcome(
        scope,
        status,
        safe_error_code,
        captures,
        row_count=row_count,
        completion=completion,
        failure_evidence=evidence,
        failure_evidence_error_code=evidence_error_code,
    )


def _failure_completion(
    status: BatchScopeStatus,
    error_code: str,
) -> AcquisitionCompletion:
    terminal_status = (
        AcquisitionTerminalStatus.INVALID
        if status is BatchScopeStatus.INVALID
        else AcquisitionTerminalStatus.FAILED
    )
    return AcquisitionCompletion(
        requested_start_reached=False,
        completion_reason=error_code,
        terminal_status=terminal_status,
        analysis_row_count=0,
        audit_row_count=0,
        returned_row_count=0,
    )


def _safe_error_code(value: object) -> str:
    if type(value) is str and _STABLE_ERROR_CODE.fullmatch(value) is not None:
        return value
    return "unexpected_failure"


def _error_outcome(
    scope: CollectionScope,
    status: BatchScopeStatus,
    error_code: str,
    captures: tuple[RawHttpCapture, ...],
    *,
    row_count: int = 0,
    completion: AcquisitionCompletion | None = None,
    failure_evidence: StoredFailureEvidence | None = None,
    failure_evidence_error_code: str | None = None,
) -> _ScopeOutcome:
    return _ScopeOutcome(
        acquisition_key=scope.acquisition_key,
        status=status,
        error_code=error_code,
        row_count=row_count,
        capture_count=len(captures),
        capture_sha256s=tuple(capture.body_sha256 for capture in captures),
        safe_captures=captures,
        acquisition_completion=completion,
        failure_evidence=failure_evidence,
        failure_evidence_error_code=failure_evidence_error_code,
    )


def _terminal_payload(
    scope_index: int,
    scope: CollectionScope,
    outcome: _ScopeOutcome,
) -> dict[str, object]:
    stored = outcome.stored_archive
    completion = outcome.acquisition_completion
    failure_evidence = outcome.failure_evidence
    return {
        "acquisitionKey": outcome.acquisition_key,
        "captureCount": outcome.capture_count,
        "captureSha256s": list(outcome.capture_sha256s),
        "completionReason": (
            completion.completion_reason if completion is not None else None
        ),
        "acquisitionTerminalStatus": (
            completion.terminal_status.value if completion is not None else None
        ),
        "analysisRowCount": (
            completion.analysis_row_count if completion is not None else None
        ),
        "auditRowCount": (
            completion.audit_row_count if completion is not None else None
        ),
        "errorCode": outcome.error_code,
        "failureEvidenceDigest": (
            failure_evidence.evidence_digest
            if failure_evidence is not None
            else None
        ),
        "failureEvidenceErrorCode": outcome.failure_evidence_error_code,
        "failureEvidenceManifestPath": _failure_evidence_relative_path(
            failure_evidence
        ),
        "failureEvidenceManifestSha256Path": (
            f"{_failure_evidence_relative_path(failure_evidence)}.sha256"
            if failure_evidence is not None
            else None
        ),
        "manifestPath": _manifest_relative_path(stored),
        "requestedStartReached": (
            completion.requested_start_reached if completion is not None else None
        ),
        "resumedFromVerifiedArchive": outcome.resumed_from_verified_archive,
        "rowCount": outcome.row_count,
        "returnedRowCount": (
            completion.returned_row_count if completion is not None else None
        ),
        "scope": scope.to_canonical_body(),
        "scopeIndex": scope_index,
        "status": outcome.status.value,
    }


def _manifest_relative_path(stored: StoredArchive | None) -> str | None:
    if stored is None:
        return None
    return f"{stored.acquisition_key}/manifest.json"


def _failure_evidence_relative_path(
    stored: StoredFailureEvidence | None,
) -> str | None:
    if stored is None:
        return None
    return (
        f"failure-evidence/{stored.acquisition_key}/"
        f"{stored.evidence_digest}/manifest.json"
    )


def _terminal(
    scope_index: int,
    outcome: _ScopeOutcome,
    entry: LocalLedgerEntry,
) -> TossMinuteScopeTerminal:
    stored = outcome.stored_archive
    return TossMinuteScopeTerminal(
        scope_index=scope_index,
        acquisition_key=outcome.acquisition_key,
        status=outcome.status,
        error_code=outcome.error_code,
        row_count=outcome.row_count,
        capture_count=outcome.capture_count,
        safe_captures=outcome.safe_captures,
        manifest_path=stored.manifest_path if stored is not None else None,
        manifest_sha256_path=(
            stored.manifest_sha256_path if stored is not None else None
        ),
        acquisition_completion=outcome.acquisition_completion,
        resumed_from_verified_archive=outcome.resumed_from_verified_archive,
        event_path=entry.path,
        event_sha256_path=entry.sidecar_path,
        event_sha256=entry.record_sha256,
        failure_evidence=outcome.failure_evidence,
        failure_evidence_error_code=outcome.failure_evidence_error_code,
    )


def _format_utc(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise TossBatchCollectionError("clock_must_return_utc")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
