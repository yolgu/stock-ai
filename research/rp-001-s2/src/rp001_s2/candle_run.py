"""Collect and publish one frozen RP-001-S2 daily-candle development sample."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001.toss_research_collector import (
    CanonicalScalar,
    CombinedCandleCollection,
    PairedCandleRow,
    RawHttpCapture,
)
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, run_candle_request


_PROGRAM_ID = "RP-001-S2"
_CYCLE_ID = "RP-001-S2-CYCLE-001"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SESSION_TIMEZONE = ZoneInfo("America/New_York")
_CONTRACT_RELATIVE_PATH = Path(
    "research/rp-001-s2/contracts/development-candle-contract-v1.json"
)
_START_DATE = date(2023, 1, 3)
_END_DATE = date(2026, 6, 30)
_INITIAL_BEFORE = "2026-07-01T00:00:00Z"


class CandleRunError(ValueError):
    """Sanitized terminal candle-run failure."""


@dataclass(frozen=True)
class CandleRunArguments:
    repository_root: Path
    contract_path: Path
    contract_sha256: str
    run_id: str


@dataclass(frozen=True)
class CandleRunSummary:
    run_id: str
    status: str
    symbol_count: int
    analysis_row_count: int
    capture_count: int
    manifest_sha256: str
    ledger_sha256: str


def run_development_candle_collection(
    arguments: CandleRunArguments,
    *,
    opener: object | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    environment: MutableMapping[str, str] | None = None,
    request_pacer: Callable[[], None] | None = None,
) -> CandleRunSummary:
    root = arguments.repository_root.absolute()
    contract = _verify_contract(root, arguments)
    symbols = tuple(str(value) for value in contract["developmentSymbols"])
    if not _RUN_ID.fullmatch(arguments.run_id):
        raise CandleRunError("run_id_invalid")
    run_directory = root / "research/rp-001-s2/candle-runs" / arguments.run_id
    ledger_directory = root / "research/rp-001-s2/local-ledgers/program"
    store = LocalArtifactStore(root)
    try:
        collections = run_candle_request(
            symbols=symbols,
            start_date=_START_DATE,
            end_date=_END_DATE,
            initial_before=_INITIAL_BEFORE,
            opener=opener,
            clock=clock,
            environment=environment,
            request_pacer=request_pacer,
        )
        _validate_complete_common_calendar(collections, symbols)
        return _publish_success(
            arguments,
            contract,
            collections,
            run_directory,
            store,
            AppendOnlyLocalLedger(ledger_directory),
            clock,
        )
    except Exception as error:
        captures = error.captures if isinstance(error, ReadOnlyBoundaryError) else ()
        code = (
            error.code
            if isinstance(error, ReadOnlyBoundaryError)
            else str(error) if isinstance(error, CandleRunError) else "candle_run_failed"
        )
        _publish_failure(
            arguments,
            code,
            captures,
            run_directory,
            store,
            AppendOnlyLocalLedger(ledger_directory),
            clock,
        )
        raise CandleRunError(code) from None


def _verify_contract(
    root: Path,
    arguments: CandleRunArguments,
) -> Mapping[str, object]:
    if not _SHA256.fullmatch(arguments.contract_sha256):
        raise CandleRunError("contract_sha256_invalid")
    path = arguments.contract_path if arguments.contract_path.is_absolute() else root / arguments.contract_path
    if path.absolute() != root / _CONTRACT_RELATIVE_PATH:
        raise CandleRunError("contract_path_not_canonical")
    try:
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
        value = json.loads(source.decode("utf-8"))
    except Exception:
        raise CandleRunError("contract_invalid") from None
    if (
        sha256_bytes(source) != arguments.contract_sha256
        or sidecar != f"{arguments.contract_sha256}\n"
        or not isinstance(value, dict)
        or canonical_json_bytes(value) != source
    ):
        raise CandleRunError("contract_invalid")
    expected_period = {
        "startDate": _START_DATE.isoformat(),
        "endDate": _END_DATE.isoformat(),
        "inclusive": True,
        "interval": "1d",
        "timezone": "America/New_York",
        "initialBefore": _INITIAL_BEFORE,
    }
    if (
        value.get("schemaVersion") != "rp001-s2-development-candle-contract.v1"
        or value.get("programId") != _PROGRAM_ID
        or value.get("cycleId") != _CYCLE_ID
        or value.get("status") != "development_candles_authorized_confirmation_price_unopened"
        or value.get("sampleRole") != "seen_development_after_price_open"
        or value.get("period") != expected_period
        or value.get("ordersAccountsAssetsAllowed") is not False
        or value.get("allowedRequests")
        != [
            {"method": "POST", "path": "/oauth2/token"},
            {"method": "GET", "path": "/api/v1/candles"},
        ]
    ):
        raise CandleRunError("contract_invalid")
    development = value.get("developmentSymbols")
    confirmation = value.get("confirmationSymbols")
    if (
        not isinstance(development, list)
        or len(development) != 6
        or len(set(development)) != 6
        or not isinstance(confirmation, list)
        or len(confirmation) != 6
        or set(development) & set(confirmation)
    ):
        raise CandleRunError("contract_invalid")
    bindings = value.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise CandleRunError("contract_invalid")
    for binding in bindings.values():
        _verify_binding(root, binding)
    if not _has_freeze_event(root, arguments.contract_sha256):
        raise CandleRunError("freeze_event_invalid")
    return value


def _verify_binding(root: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise CandleRunError("contract_binding_invalid")
    path_value = value.get("path")
    expected = value.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise CandleRunError("contract_binding_invalid")
    try:
        path = root / path_value
        path.relative_to(root)
        if sha256_bytes(path.read_bytes()) != expected:
            raise CandleRunError("contract_binding_invalid")
        sidecar = Path(f"{path}.sha256")
        if sidecar.exists() and sidecar.read_text(encoding="ascii") != f"{expected}\n":
            raise CandleRunError("contract_binding_invalid")
    except (OSError, ValueError, UnicodeError):
        raise CandleRunError("contract_binding_invalid") from None


def _has_freeze_event(root: Path, contract_sha256: str) -> bool:
    events = root / "research/rp-001-s2/local-ledgers/program/events"
    for path in sorted(events.glob("*.json")):
        try:
            source = path.read_bytes()
            if Path(f"{path}.sha256").read_text(encoding="ascii") != f"{sha256_bytes(source)}\n":
                return False
            event = json.loads(source.decode("utf-8"))
        except Exception:
            return False
        if (
            isinstance(event, dict)
            and event.get("eventType") == "rp001_s2_development_candle_scope_frozen"
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("contract")
            == {"path": _CONTRACT_RELATIVE_PATH.as_posix(), "sha256": contract_sha256}
        ):
            return True
    return False


def _validate_complete_common_calendar(
    collections: Sequence[CombinedCandleCollection],
    symbols: tuple[str, ...],
) -> None:
    if tuple(value.symbol for value in collections) != symbols:
        raise CandleRunError("symbol_order_mismatch")
    expected: tuple[str, ...] | None = None
    for value in collections:
        calendar = tuple(_session_date(row.timestamp) for row in value.rows)
        if (
            len(calendar) < 607
            or not calendar
            or calendar[0] != _START_DATE.isoformat()
            or calendar[-1] != _END_DATE.isoformat()
            or len(set(calendar)) != len(calendar)
        ):
            raise CandleRunError("incomplete_candle_range")
        if expected is None:
            expected = calendar
        elif calendar != expected:
            raise CandleRunError("common_calendar_mismatch")


def _publish_success(
    arguments: CandleRunArguments,
    contract: Mapping[str, object],
    collections: tuple[CombinedCandleCollection, ...],
    run_directory: Path,
    store: LocalArtifactStore,
    ledger: AppendOnlyLocalLedger,
    clock: Callable[[], datetime],
) -> CandleRunSummary:
    timestamp = _timestamp(clock)
    captures = tuple(
        capture
        for value in collections
        for capture in (
            value.adjusted_collection.captures + value.native_collection.captures
        )
    )
    raw = store.publish_json(
        run_directory / "raw-candles.json",
        {
            "schemaVersion": "rp001-s2-toss-candles-raw.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "sampleRole": contract["sampleRole"],
            "captures": [_capture_body(value, include_body=True) for value in captures],
        },
    )
    processed = store.publish_json(
        run_directory / "processed-candles.json",
        {
            "schemaVersion": "rp001-s2-toss-candles-processed.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "sampleRole": contract["sampleRole"],
            "period": contract["period"],
            "signalTiming": "official_daily_close_usable_next_session",
            "featurePriceMode": "native_unadjusted",
            "labelPriceMode": "adjusted_future_only",
            "providerRevisionAndPublication": "not_documented",
            "rawArtifact": _binding(raw, arguments.repository_root),
            "symbols": [_processed_symbol(value) for value in collections],
        },
    )
    exposure = store.publish_json(
        run_directory / "exposure.json",
        {
            "schemaVersion": "rp001-s2-candle-exposure.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "createdAt": timestamp,
            "sampleRole": contract["sampleRole"],
            "developmentPriceVolumeOpened": True,
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "symbols": contract["developmentSymbols"],
        },
    )
    prior = (raw, processed, exposure)
    row_count = sum(len(value.rows) for value in collections)
    manifest = store.publish_json(
        run_directory / "manifest.json",
        {
            "schemaVersion": "rp001-s2-candle-manifest.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "development_candles_complete",
            "createdAt": timestamp,
            "symbolCount": len(collections),
            "analysisRowCount": row_count,
            "captureCount": len(captures),
            "contractSha256": arguments.contract_sha256,
            "artifacts": [_binding(value, arguments.repository_root) for value in prior],
        },
    )
    event = ledger.append(
        "rp001_s2_development_candles_succeeded",
        {
            "runId": arguments.run_id,
            "analysisRowCount": row_count,
            "manifest": _binding(manifest, arguments.repository_root),
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAccessed": False,
        },
        timestamp,
    )
    return CandleRunSummary(
        run_id=arguments.run_id,
        status="succeeded",
        symbol_count=len(collections),
        analysis_row_count=row_count,
        capture_count=len(captures),
        manifest_sha256=manifest.artifact_sha256,
        ledger_sha256=event.record_sha256,
    )


def _publish_failure(
    arguments: CandleRunArguments,
    code: str,
    captures: tuple[RawHttpCapture, ...],
    run_directory: Path,
    store: LocalArtifactStore,
    ledger: AppendOnlyLocalLedger,
    clock: Callable[[], datetime],
) -> None:
    timestamp = _timestamp(clock)
    capture_binding: LocalArtifactBinding | None = None
    if captures:
        capture_binding = store.publish_json(
            run_directory / "failure-captures.json",
            {
                "schemaVersion": "rp001-s2-candle-failure-captures.v1",
                "programId": _PROGRAM_ID,
                "cycleId": _CYCLE_ID,
                "runId": arguments.run_id,
                "captures": [
                    _capture_body(value, include_body=code != "SENSITIVE_RESPONSE")
                    for value in captures
                ],
            },
        )
    failure = store.publish_json(
        run_directory / "failure.json",
        {
            "schemaVersion": "rp001-s2-candle-failure.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "failed",
            "failureCode": code,
            "createdAt": timestamp,
            "failureCaptures": _binding(capture_binding, arguments.repository_root) if capture_binding else None,
            "ordersAccountsAssetsAccessed": False,
        },
    )
    ledger.append(
        "rp001_s2_development_candles_failed",
        {
            "runId": arguments.run_id,
            "failureCode": code,
            "failure": _binding(failure, arguments.repository_root),
            "confirmationPriceVolumeOpened": False,
            "ordersAccountsAssetsAccessed": False,
        },
        timestamp,
    )


def _processed_symbol(value: CombinedCandleCollection) -> dict[str, object]:
    return {
        "symbol": value.symbol,
        "providerSessionMembership": value.provider_session_membership,
        "analysisRows": [_paired_row(row) for row in value.rows],
        "auditOnlyRows": {
            "adjusted": [_candle_row(row) for row in value.adjusted_collection.audit_only_rows],
            "native": [_candle_row(row) for row in value.native_collection.audit_only_rows],
        },
    }


def _paired_row(value: PairedCandleRow) -> dict[str, object]:
    return {
        "sessionDate": _session_date(value.timestamp),
        "timestamp": value.timestamp,
        "currency": value.currency,
        "adjusted": _price_volume(value.adjusted.open_price, value.adjusted.high_price, value.adjusted.low_price, value.adjusted.close_price, value.adjusted.volume),
        "native": _price_volume(value.native.open_price, value.native.high_price, value.native.low_price, value.native.close_price, value.native.volume),
    }


def _candle_row(value: object) -> dict[str, object]:
    return {
        "sessionDate": _session_date(value.timestamp),
        "timestamp": value.timestamp,
        "currency": value.currency,
        **_price_volume(value.open_price, value.high_price, value.low_price, value.close_price, value.volume),
    }


def _price_volume(
    open_price: CanonicalScalar,
    high_price: CanonicalScalar,
    low_price: CanonicalScalar,
    close_price: CanonicalScalar,
    volume: CanonicalScalar,
) -> dict[str, object]:
    return {
        "openPrice": _scalar(open_price),
        "highPrice": _scalar(high_price),
        "lowPrice": _scalar(low_price),
        "closePrice": _scalar(close_price),
        "volume": _scalar(volume),
    }


def _scalar(value: CanonicalScalar) -> dict[str, str]:
    return {"kind": value.kind, "text": value.text}


def _capture_body(value: RawHttpCapture, *, include_body: bool) -> dict[str, object]:
    body: dict[str, object] = {
        "endpointId": value.endpoint_id,
        "method": value.method,
        "sanitizedUrl": value.sanitized_url,
        "query": [{"name": name, "value": item} for name, item in value.query],
        "status": value.status,
        "headers": [{"name": name, "value": item} for name, item in value.headers],
        "receivedAt": value.received_at,
        "bodySha256": value.body_sha256,
        "rawBodyPersisted": bool(include_body and value.body_base64),
    }
    if include_body and value.body_base64:
        body["bodyBase64"] = value.body_base64
    return body


def _session_date(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp)
    if parsed.tzinfo is None:
        raise CandleRunError("timestamp_timezone_missing")
    return parsed.astimezone(_SESSION_TIMEZONE).date().isoformat()


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root.absolute()) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


def _timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CandleRunError("clock_invalid")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
