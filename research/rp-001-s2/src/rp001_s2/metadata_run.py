"""Application service for one RP-001-S2 metadata-only run."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001.toss_research_collector import MetadataCollection, RawHttpCapture

from rp001_s2.sample_design import CANDIDATE_POOL, SampleSelection, select_samples
from rp001_s2.toss_boundary import ReadOnlyBoundaryError, run_metadata_request


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PROGRAM_ID = "RP-001-S2"
_CYCLE_ID = "RP-001-S2-CYCLE-001"
_CANONICAL_CONTRACT_RELATIVE_PATH = Path(
    "research/rp-001-s2/contracts/read-only-source-contract-v1.json"
)
_FREEZE_EVENT_RELATIVE_PATH = Path(
    "research/rp-001-s2/local-ledgers/program/events/000001.json"
)
_IMPLEMENTATION_BINDING_KEYS = frozenset(
    {
        "formulaSource",
        "formulaTests",
        "sampleSource",
        "sampleTests",
        "tossBoundarySource",
        "tossBoundaryTests",
        "metadataRunSource",
        "metadataRunTests",
        "metadataCli",
        "evaluationSource",
        "evaluationTests",
        "collectorSource",
        "collectorTests",
        "sensitivePolicySource",
        "sensitivePolicyTests",
        "localEvidenceSource",
        "localEvidenceTests",
    }
)


class MetadataRunError(ValueError):
    """Sanitized terminal metadata-run failure."""


@dataclass(frozen=True)
class MetadataRunArguments:
    repository_root: Path
    contract_path: Path
    contract_sha256: str
    run_id: str


@dataclass(frozen=True)
class MetadataRunSummary:
    run_id: str
    status: str
    record_count: int
    development_symbols: tuple[str, ...]
    confirmation_symbols: tuple[str, ...]
    manifest_sha256: str
    ledger_sha256: str


def run_metadata_collection(
    arguments: MetadataRunArguments,
    *,
    opener: object | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    environment: MutableMapping[str, str] | None = None,
) -> MetadataRunSummary:
    """Verify a frozen contract, collect metadata, and publish append-only evidence."""
    root = arguments.repository_root.absolute()
    contract = _verify_contract(root, arguments)
    _validate_run_id(arguments.run_id)
    run_directory = root / "research/rp-001-s2/metadata-runs" / arguments.run_id
    ledger_directory = root / "research/rp-001-s2/local-ledgers/program"
    store = LocalArtifactStore(root)
    store.ensure_directory(ledger_directory.parent)
    ledger = AppendOnlyLocalLedger(ledger_directory)
    try:
        collection = run_metadata_request(
            symbols=CANDIDATE_POOL,
            opener=opener,
            clock=clock,
            environment=environment,
        )
        selection = select_samples(_metadata_payloads(collection))
        return _publish_success(
            arguments,
            contract,
            collection,
            selection,
            run_directory,
            store,
            ledger,
            clock,
        )
    except Exception as error:
        captures = (
            error.captures
            if isinstance(error, ReadOnlyBoundaryError)
            else ()
        )
        if isinstance(error, MetadataRunError):
            code = str(error)
        elif isinstance(error, ReadOnlyBoundaryError):
            code = str(error)
        else:
            code = getattr(error, "code", "metadata_run_failed")
        _publish_failure(
            arguments,
            code,
            captures,
            run_directory,
            store,
            ledger,
            clock,
        )
        raise MetadataRunError(code) from None


def _verify_contract(
    root: Path,
    arguments: MetadataRunArguments,
) -> Mapping[str, object]:
    if not _SHA256.fullmatch(arguments.contract_sha256):
        raise MetadataRunError("contract_sha256_invalid")
    path = arguments.contract_path
    if not path.is_absolute():
        path = root / path
    if path.absolute() != (root / _CANONICAL_CONTRACT_RELATIVE_PATH):
        raise MetadataRunError("contract_path_not_canonical")
    try:
        path.relative_to(root)
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
    except (OSError, ValueError, UnicodeError):
        raise MetadataRunError("contract_unavailable") from None
    if (
        sha256_bytes(source) != arguments.contract_sha256
        or sidecar != f"{arguments.contract_sha256}\n"
    ):
        raise MetadataRunError("contract_hash_mismatch")
    try:
        value = json.loads(source.decode("utf-8"))
    except Exception:
        raise MetadataRunError("contract_invalid") from None
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise MetadataRunError("contract_invalid")
    allowed = value.get("allowedRequests")
    if (
        value.get("schemaVersion") != "rp001-s2-read-only-source-contract.v1"
        or value.get("programId") != _PROGRAM_ID
        or value.get("cycleId") != _CYCLE_ID
        or value.get("status") != "metadata_only_authorized_price_unopened"
        or value.get("candidatePool") != list(CANDIDATE_POOL)
        or value.get("ordersAccountsAssetsAllowed") is not False
        or allowed
        != [
            {"method": "POST", "path": "/oauth2/token"},
            {"method": "GET", "path": "/api/v1/stocks"},
        ]
    ):
        raise MetadataRunError("contract_invalid")
    if value.get("credentialBoundary") != {
        "input": "one_shot_process_environment",
        "variableNames": ["TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"],
        "consumeImmediately": True,
        "commandLineValues": "forbidden",
        "persistenceInArtifactsLogsOrManifest": "forbidden",
        "oauthTokenPersistence": "forbidden",
    }:
        raise MetadataRunError("contract_invalid")
    for key in ("merc", "metadataSampleDesign"):
        _verify_declared_binding(root, value.get(key))
    bindings = value.get("implementationBindings")
    if not isinstance(bindings, dict) or frozenset(bindings) != _IMPLEMENTATION_BINDING_KEYS:
        raise MetadataRunError("contract_invalid")
    for binding in bindings.values():
        _verify_declared_binding(root, binding)
    _verify_freeze_event(root, arguments.contract_sha256)
    return value


def _verify_freeze_event(root: Path, contract_sha256: str) -> None:
    path = root / _FREEZE_EVENT_RELATIVE_PATH
    try:
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        raise MetadataRunError("freeze_event_unavailable") from None
    event_sha256 = sha256_bytes(source)
    if sidecar != f"{event_sha256}\n":
        raise MetadataRunError("freeze_event_invalid")
    try:
        event = json.loads(source.decode("utf-8"))
    except Exception:
        raise MetadataRunError("freeze_event_invalid") from None
    if not isinstance(event, dict) or canonical_json_bytes(event) != source:
        raise MetadataRunError("freeze_event_invalid")
    payload = event.get("payload")
    if (
        event.get("sequence") != 1
        or event.get("previousRecordSha256") is not None
        or event.get("eventType") != "rp001_s2_cycle_001_merc_frozen"
        or not isinstance(payload, dict)
        or payload.get("readOnlySourceContract")
        != {
            "path": _CANONICAL_CONTRACT_RELATIVE_PATH.as_posix(),
            "sha256": contract_sha256,
        }
        or payload.get("priceVolumeOpened") is not False
        or payload.get("ordersAccountsAssetsAllowed") is not False
    ):
        raise MetadataRunError("freeze_event_invalid")


def _verify_declared_binding(root: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise MetadataRunError("contract_binding_invalid")
    path_value = value.get("path")
    expected = value.get("sha256")
    if not isinstance(path_value, str) or not _SHA256.fullmatch(str(expected)):
        raise MetadataRunError("contract_binding_invalid")
    path = root / path_value
    try:
        path.relative_to(root)
        actual = sha256_bytes(path.read_bytes())
        sidecar = Path(f"{path}.sha256")
        if sidecar.exists() and sidecar.read_text(encoding="ascii") != f"{expected}\n":
            raise MetadataRunError("contract_binding_invalid")
    except (OSError, ValueError, UnicodeError):
        raise MetadataRunError("contract_binding_invalid") from None
    if actual != expected:
        raise MetadataRunError("contract_binding_invalid")


def _publish_success(
    arguments: MetadataRunArguments,
    contract: Mapping[str, object],
    collection: MetadataCollection,
    selection: SampleSelection,
    run_directory: Path,
    store: LocalArtifactStore,
    ledger: AppendOnlyLocalLedger,
    clock: Callable[[], datetime],
) -> MetadataRunSummary:
    created_at = _timestamp(clock)
    raw = store.publish_json(
        run_directory / "raw-metadata.json",
        _raw_body(arguments.run_id, collection.capture),
    )
    processed = store.publish_json(
        run_directory / "processed-metadata.json",
        _processed_body(arguments.run_id, collection, raw, arguments.repository_root),
    )
    selection_binding = store.publish_json(
        run_directory / "sample-selection.json",
        {
            "schemaVersion": "rp001-s2-sample-selection.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            **selection.to_canonical_body(),
        },
    )
    exposure = store.publish_json(
        run_directory / "metadata-exposure.json",
        {
            "schemaVersion": "rp001-s2-metadata-exposure.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "createdAt": created_at,
            "metadataOpened": True,
            "priceVolumeOpened": False,
            "outcomesPerformanceOpened": False,
            "ordersAccountsAssetsAccessed": False,
            "symbols": list(CANDIDATE_POOL),
        },
    )
    prior = (raw, processed, selection_binding, exposure)
    manifest = store.publish_json(
        run_directory / "manifest.json",
        {
            "schemaVersion": "rp001-s2-metadata-manifest.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "metadata_only_complete_price_unopened",
            "createdAt": created_at,
            "recordCount": len(collection.records),
            "developmentSymbols": list(selection.development_symbols),
            "confirmationSymbols": list(selection.confirmation_symbols),
            "contractSha256": arguments.contract_sha256,
            "contractStatus": contract["status"],
            "artifacts": [_binding_body(value, arguments.repository_root) for value in prior],
        },
    )
    event = ledger.append(
        "rp001_s2_metadata_collection_succeeded",
        {
            "runId": arguments.run_id,
            "recordCount": len(collection.records),
            "developmentSymbols": list(selection.development_symbols),
            "confirmationSymbols": list(selection.confirmation_symbols),
            "manifest": _binding_body(manifest, arguments.repository_root),
            "ordersAccountsAssetsAccessed": False,
        },
        created_at,
    )
    return MetadataRunSummary(
        run_id=arguments.run_id,
        status="succeeded",
        record_count=len(collection.records),
        development_symbols=selection.development_symbols,
        confirmation_symbols=selection.confirmation_symbols,
        manifest_sha256=manifest.artifact_sha256,
        ledger_sha256=event.record_sha256,
    )


def _publish_failure(
    arguments: MetadataRunArguments,
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
        include_body = code != "SENSITIVE_RESPONSE"
        capture_binding = store.publish_json(
            run_directory / "failure-captures.json",
            {
                "schemaVersion": "rp001-s2-metadata-failure-captures.v1",
                "programId": _PROGRAM_ID,
                "cycleId": _CYCLE_ID,
                "runId": arguments.run_id,
                "captureCount": len(captures),
                "rawBodiesOmittedForSensitiveFailure": not include_body,
                "captures": [
                    _capture_body(value, include_body=include_body)
                    for value in captures
                ],
            },
        )
    failure = store.publish_json(
        run_directory / "failure.json",
        {
            "schemaVersion": "rp001-s2-metadata-failure.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "failed",
            "failureCode": code,
            "createdAt": timestamp,
            "ordersAccountsAssetsAccessed": False,
            "credentialsPersisted": False,
            "failureCaptures": (
                _binding_body(capture_binding, arguments.repository_root)
                if capture_binding is not None
                else None
            ),
        },
    )
    ledger.append(
        "rp001_s2_metadata_collection_failed",
        {
            "runId": arguments.run_id,
            "failureCode": code,
            "failure": _binding_body(failure, arguments.repository_root),
            "failureCaptures": (
                _binding_body(capture_binding, arguments.repository_root)
                if capture_binding is not None
                else None
            ),
            "ordersAccountsAssetsAccessed": False,
        },
        timestamp,
    )


def _metadata_payloads(collection: MetadataCollection) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "symbol": value.symbol,
            "name": value.name,
            "englishName": value.english_name,
            "isinCode": value.isin_code,
            "market": value.market,
            "securityType": value.security_type,
            "isCommonShare": value.is_common_share,
            "status": value.status,
            "currency": value.currency,
            "sharesOutstanding": value.shares_outstanding.text,
        }
        for value in collection.records
    )


def _raw_body(run_id: str, capture: RawHttpCapture) -> dict[str, object]:
    return {
        "schemaVersion": "rp001-s2-toss-metadata-raw.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "runId": run_id,
        "sampleRole": "metadata_only",
        "capture": {
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
        },
    }


def _capture_body(
    capture: RawHttpCapture,
    *,
    include_body: bool,
) -> dict[str, object]:
    body: dict[str, object] = {
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
        "bodySha256": capture.body_sha256,
    }
    if include_body and capture.body_base64:
        body["bodyBase64"] = capture.body_base64
    body["rawBodyPersisted"] = bool(include_body and capture.body_base64)
    return body


def _processed_body(
    run_id: str,
    collection: MetadataCollection,
    raw: LocalArtifactBinding,
    root: Path,
) -> dict[str, object]:
    raw_path = raw.path.relative_to(root.absolute()) if raw.path.is_absolute() else raw.path
    return {
        "schemaVersion": "rp001-s2-toss-metadata-processed.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "runId": run_id,
        "sampleRole": "metadata_only",
        "rawArtifact": {
            "path": raw_path.as_posix(),
            "sha256": raw.artifact_sha256,
        },
        "recordCount": len(collection.records),
        "records": list(_metadata_payloads(collection)),
    }


def _binding_body(binding: LocalArtifactBinding, root: Path) -> dict[str, object]:
    path = binding.path
    if path.is_absolute():
        path = path.relative_to(root.absolute())
    return {"path": path.as_posix(), "sha256": binding.artifact_sha256}


def _timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MetadataRunError("clock_invalid")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID.fullmatch(run_id):
        raise MetadataRunError("run_id_invalid")
