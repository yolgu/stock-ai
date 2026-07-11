"""Immutable local evidence for formal direction-neutral empirical runs."""

from __future__ import annotations

import json
import math
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerAppendError,
    LocalLedgerEntry,
    canonical_json_bytes,
    decode_canonical_local_ledger_record,
    require_trusted_directory_root,
    sha256_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values
from rp001_s2.direction_neutral_overheat import (
    CompetitivePathResult,
    DirectionNeutralObservation,
    LabelHorizon,
    ScreenState,
    ScreeningResult,
)
from rp001_s2.empirical_pipeline import (
    DirectionNeutralEmpiricalResult,
    EpisodeCompetitivePath,
    ExcludedEpisode,
)
from rp001_s2.overheat_features import FeatureMarket, FeatureSession
from rp001_s2.overheat_oof import (
    CompetitivePathDevelopmentOOF,
    CompetitivePathExample,
    DevelopmentFold,
    ExcludedOOFRow,
    OOFMetrics,
    OOFProbabilityRow,
    SessionInterval,
)


_PROTOCOL_SCHEMA = "rp001-s2-empirical-run-protocol.v1"
_EPISODE_CATALOG_SCHEMA = "rp001-s2-empirical-episode-catalog.v1"
_OOF_SCHEMA = "rp001-s2-empirical-oof-evidence.v1"
_TRIAL_SCHEMA = "rp001-s2-empirical-trial.v1"
_MANIFEST_SCHEMA = "rp001-s2-empirical-run-manifest.v1"
_FAILURE_SCHEMA = "rp001-s2-empirical-run-failure.v1"
_FROZEN_EVENT = "rp001_s2_empirical_protocol_frozen"
_COMPLETED_EVENT = "rp001_s2_empirical_run_completed"
_FAILED_EVENT = "rp001_s2_empirical_run_failed"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{2,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PROTOCOL_KEYS = frozenset(
    {
        "schemaVersion",
        "usageScope",
        "runId",
        "frozenAt",
        "sampleRole",
        "symbols",
        "adjustmentMode",
        "featureMarket",
        "horizon",
        "frozenSessionAxis",
        "acquisitionKeys",
        "codeRevision",
        "sourceBindings",
    }
)
_PROTOCOL_FORBIDDEN_KEY_TERMS = (
    "result",
    "metric",
    "label",
    "outcome",
    "prediction",
    "probability",
)


class EmpiricalRunEvidenceError(ValueError):
    """Stable refusal at the immutable empirical-evidence boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CanonicalJsonBinding:
    relative_path: str
    sha256: str


@dataclass(frozen=True)
class EmpiricalRunProtocol:
    run_id: str
    frozen_at: datetime
    sample_role: str
    target_symbol: str
    benchmark_symbol: str
    adjustment_mode: str
    market: FeatureMarket
    horizon: LabelHorizon
    frozen_sessions: tuple[FeatureSession, ...]
    target_acquisition_keys: tuple[str, ...]
    benchmark_acquisition_keys: tuple[str, ...]
    code_revision: str
    source_scope_plan: CanonicalJsonBinding
    session_calendar: CanonicalJsonBinding


@dataclass(frozen=True)
class FrozenEmpiricalProtocol:
    run_id: str
    protocol_path: Path
    protocol_sha256: str


@dataclass(frozen=True)
class CompletedEmpiricalRunSummary:
    run_id: str
    status: str
    candidate_minute_count: int
    episode_count: int
    structural_exclusion_count: int
    oof_probability_row_count: int
    oof_excluded_row_count: int
    protocol_sha256: str
    episode_catalog_sha256: str
    oof_sha256: str
    trial_sha256: str
    manifest_sha256: str
    ledger_sha256: str


@dataclass(frozen=True)
class FailedEmpiricalRunSummary:
    run_id: str
    status: str
    protocol_sha256: str
    failure_sha256: str
    ledger_sha256: str


@dataclass(frozen=True)
class VerifiedEmpiricalRun:
    run_id: str
    status: str
    protocol_sha256: str
    terminal_sha256: str
    ledger_sha256: str


@dataclass(frozen=True)
class _StoredLedgerRecord:
    body: Mapping[str, object]
    sha256: str


def freeze_empirical_run_protocol(
    *,
    trusted_root: Path,
    protocol: EmpiricalRunProtocol,
) -> FrozenEmpiricalProtocol:
    """Freeze inputs before formal computation and append the freeze event."""
    root = _require_trusted_root(trusted_root)
    protocol_body = _validate_protocol(root, protocol)
    _require_publishable_body(protocol_body)
    relative_path = _protocol_relative_path(protocol.run_id)
    path = root / relative_path
    store = LocalArtifactStore(root)
    ledger = AppendOnlyLocalLedger(root / "ledger")
    published: LocalArtifactBinding | None = None
    event: LocalLedgerEntry | None = None
    try:
        with ledger.transaction() as transaction:
            state = transaction.validate()
            events = _read_ledger_records(root, state.sequence)
            if _events_for_run(events, protocol.run_id):
                raise EmpiricalRunEvidenceError("run_id_already_exists")
            published = store.publish_json(path, protocol_body)
            event = transaction.append(
                _FROZEN_EVENT,
                {
                    "runId": protocol.run_id,
                    "protocol": _binding_body(relative_path, published.artifact_sha256),
                },
                _format_utc(protocol.frozen_at),
            )
    except EmpiricalRunEvidenceError:
        if event is not None:
            raise EmpiricalRunEvidenceError("freeze_event_commit_uncertain") from None
        _rollback_if_uncommitted(store, published)
        raise
    except LocalLedgerAppendError as error:
        if not error.event_published:
            _rollback_if_uncommitted(store, published)
        raise EmpiricalRunEvidenceError("freeze_event_commit_uncertain") from None
    except LocalEvidenceError as error:
        if event is not None:
            raise EmpiricalRunEvidenceError("freeze_event_commit_uncertain") from None
        _rollback_if_uncommitted(store, published)
        raise _publication_error(error) from None
    if published is None:
        raise EmpiricalRunEvidenceError("protocol_publication_failed")
    return FrozenEmpiricalProtocol(
        run_id=protocol.run_id,
        protocol_path=path,
        protocol_sha256=published.artifact_sha256,
    )


def publish_completed_empirical_run(
    *,
    trusted_root: Path,
    protocol: FrozenEmpiricalProtocol,
    result: DirectionNeutralEmpiricalResult,
    oof: CompetitivePathDevelopmentOOF,
    completed_at: datetime,
) -> CompletedEmpiricalRunSummary:
    """Publish complete empirical evidence and one completed terminal event."""
    root = _require_trusted_root(trusted_root)
    _require_utc(completed_at)
    protocol_body = _load_frozen_protocol(root, protocol)
    _require_terminal_not_before_freeze(protocol_body, completed_at)
    _validate_completed_inputs(protocol_body, result, oof)
    protocol_binding = _binding_body(
        _protocol_relative_path(protocol.run_id),
        protocol.protocol_sha256,
    )
    episode_body = _episode_catalog_body(
        protocol.run_id,
        protocol_binding,
        result,
    )
    oof_body = _oof_body(protocol.run_id, protocol_binding, oof)
    trial_body = _trial_body(
        protocol.run_id,
        protocol_binding,
        result,
        oof,
    )
    for body in (episode_body, oof_body, trial_body):
        _require_publishable_body(body)

    run_directory = Path("runs") / protocol.run_id
    store = LocalArtifactStore(root)
    ledger = AppendOnlyLocalLedger(root / "ledger")
    publications: list[LocalArtifactBinding] = []
    event: LocalLedgerEntry | None = None
    try:
        with ledger.transaction() as transaction:
            state = transaction.validate()
            events = _read_ledger_records(root, state.sequence)
            _require_open_frozen_run(events, protocol, protocol_body)
            episode = _publish(
                store,
                root / run_directory / "episode-catalog.json",
                episode_body,
                publications,
            )
            oof_binding = _publish(
                store,
                root / run_directory / "oof.json",
                oof_body,
                publications,
            )
            trial = _publish(
                store,
                root / run_directory / "trial.json",
                trial_body,
                publications,
            )
            manifest_body = {
                "schemaVersion": _MANIFEST_SCHEMA,
                "runId": protocol.run_id,
                "status": "completed",
                "completedAt": _format_utc(completed_at),
                "protocol": protocol_binding,
                "artifacts": {
                    "episodeCatalog": _relative_binding(root, episode),
                    "oof": _relative_binding(root, oof_binding),
                    "trial": _relative_binding(root, trial),
                },
            }
            _require_publishable_body(manifest_body)
            manifest = _publish(
                store,
                root / run_directory / "manifest.json",
                manifest_body,
                publications,
            )
            event = transaction.append(
                _COMPLETED_EVENT,
                {
                    "runId": protocol.run_id,
                    "protocol": protocol_binding,
                    "manifest": _relative_binding(root, manifest),
                },
                _format_utc(completed_at),
            )
    except EmpiricalRunEvidenceError:
        if event is not None:
            raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
        _rollback_publications(store, publications)
        raise
    except LocalLedgerAppendError as error:
        if not error.event_published:
            _rollback_publications(store, publications)
        raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
    except LocalEvidenceError as error:
        if event is not None:
            raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
        _rollback_publications(store, publications)
        raise _publication_error(error) from None

    return CompletedEmpiricalRunSummary(
        run_id=protocol.run_id,
        status="completed",
        candidate_minute_count=sum(
            screening.state is ScreenState.CANDIDATE
            for screening in result.screening_results
        ),
        episode_count=len(result.episode_results),
        structural_exclusion_count=len(result.excluded_episodes),
        oof_probability_row_count=len(oof.predictions),
        oof_excluded_row_count=len(oof.excluded_rows),
        protocol_sha256=protocol.protocol_sha256,
        episode_catalog_sha256=episode.artifact_sha256,
        oof_sha256=oof_binding.artifact_sha256,
        trial_sha256=trial.artifact_sha256,
        manifest_sha256=manifest.artifact_sha256,
        ledger_sha256=event.record_sha256,
    )


def publish_failed_empirical_run(
    *,
    trusted_root: Path,
    protocol: FrozenEmpiricalProtocol,
    error_code: str,
    failed_at: datetime,
) -> FailedEmpiricalRunSummary:
    """Publish a sanitized failed terminal without fabricating result artifacts."""
    root = _require_trusted_root(trusted_root)
    _require_utc(failed_at)
    if type(error_code) is not str or _ERROR_CODE.fullmatch(error_code) is None:
        raise EmpiricalRunEvidenceError("error_code_invalid")
    if find_sensitive_values(error_code):
        raise EmpiricalRunEvidenceError("sensitive_value_refused")
    protocol_body = _load_frozen_protocol(root, protocol)
    _require_terminal_not_before_freeze(protocol_body, failed_at)
    protocol_binding = _binding_body(
        _protocol_relative_path(protocol.run_id),
        protocol.protocol_sha256,
    )
    failure_body = {
        "schemaVersion": _FAILURE_SCHEMA,
        "runId": protocol.run_id,
        "status": "failed",
        "failedAt": _format_utc(failed_at),
        "errorCode": error_code,
        "protocol": protocol_binding,
    }
    _require_publishable_body(failure_body)
    store = LocalArtifactStore(root)
    ledger = AppendOnlyLocalLedger(root / "ledger")
    failure: LocalArtifactBinding | None = None
    event: LocalLedgerEntry | None = None
    try:
        with ledger.transaction() as transaction:
            state = transaction.validate()
            events = _read_ledger_records(root, state.sequence)
            _require_open_frozen_run(events, protocol, protocol_body)
            failure = store.publish_json(
                root / "runs" / protocol.run_id / "failure.json",
                failure_body,
            )
            event = transaction.append(
                _FAILED_EVENT,
                {
                    "runId": protocol.run_id,
                    "protocol": protocol_binding,
                    "failure": _relative_binding(root, failure),
                },
                _format_utc(failed_at),
            )
    except EmpiricalRunEvidenceError:
        if event is not None:
            raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
        _rollback_if_uncommitted(store, failure)
        raise
    except LocalLedgerAppendError as error:
        if not error.event_published:
            _rollback_if_uncommitted(store, failure)
        raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
    except LocalEvidenceError as error:
        if event is not None:
            raise EmpiricalRunEvidenceError("terminal_event_commit_uncertain") from None
        _rollback_if_uncommitted(store, failure)
        raise _publication_error(error) from None
    if failure is None:
        raise EmpiricalRunEvidenceError("failure_publication_failed")
    return FailedEmpiricalRunSummary(
        run_id=protocol.run_id,
        status="failed",
        protocol_sha256=protocol.protocol_sha256,
        failure_sha256=failure.artifact_sha256,
        ledger_sha256=event.record_sha256,
    )


def verify_empirical_run(
    *,
    trusted_root: Path,
    run_id: str,
) -> VerifiedEmpiricalRun:
    """Re-read and verify one immutable completed or failed empirical run."""
    try:
        root = _require_trusted_root(trusted_root)
        _require_run_id(run_id)
        protocol_relative = _protocol_relative_path(run_id)
        protocol_body, protocol_sha256 = _read_json_artifact(
            root,
            protocol_relative,
        )
        parsed_protocol = _protocol_from_body(protocol_body)
        if parsed_protocol.run_id != run_id:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        regenerated = _validate_protocol(root, parsed_protocol)
        if regenerated != protocol_body:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")

        events = _read_validated_ledger_records(root)
        run_events = _events_for_run(events, run_id)
        if len(run_events) != 2:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        protocol_binding = _binding_body(protocol_relative, protocol_sha256)
        _verify_freeze_event(
            run_events[0],
            run_id,
            protocol_binding,
            _format_utc(parsed_protocol.frozen_at),
        )
        terminal = run_events[1]
        event_type = terminal.body.get("eventType")
        if event_type == _COMPLETED_EVENT:
            terminal_sha256 = _verify_completed_run(
                root,
                run_id,
                protocol_binding,
                protocol_body,
                terminal,
            )
            status = "completed"
        elif event_type == _FAILED_EVENT:
            terminal_sha256 = _verify_failed_run(
                root,
                run_id,
                protocol_binding,
                terminal,
            )
            status = "failed"
        else:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        return VerifiedEmpiricalRun(
            run_id=run_id,
            status=status,
            protocol_sha256=protocol_sha256,
            terminal_sha256=terminal_sha256,
            ledger_sha256=terminal.sha256,
        )
    except EmpiricalRunEvidenceError as error:
        if error.code in {"trusted_root_invalid", "run_id_invalid"}:
            raise
        raise EmpiricalRunEvidenceError("evidence_verification_failed") from None
    except (LocalEvidenceError, OSError, TypeError, ValueError):
        raise EmpiricalRunEvidenceError("evidence_verification_failed") from None


def _validate_protocol(
    root: Path,
    protocol: EmpiricalRunProtocol,
) -> dict[str, object]:
    if not isinstance(protocol, EmpiricalRunProtocol):
        raise EmpiricalRunEvidenceError("protocol_invalid")
    _require_run_id(protocol.run_id)
    _require_utc(protocol.frozen_at)
    if protocol.sample_role != "exposed_development":
        raise EmpiricalRunEvidenceError("sample_role_invalid")
    for value in (
        protocol.target_symbol,
        protocol.benchmark_symbol,
        protocol.adjustment_mode,
        protocol.code_revision,
    ):
        if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
            raise EmpiricalRunEvidenceError("protocol_identity_invalid")
    if protocol.target_symbol == protocol.benchmark_symbol:
        raise EmpiricalRunEvidenceError("protocol_symbol_invalid")
    if not isinstance(protocol.market, FeatureMarket):
        raise EmpiricalRunEvidenceError("feature_market_invalid")
    if not isinstance(protocol.horizon, LabelHorizon):
        raise EmpiricalRunEvidenceError("label_horizon_invalid")
    sessions = protocol.frozen_sessions
    if type(sessions) is not tuple or not sessions or any(
        not isinstance(session, FeatureSession) for session in sessions
    ):
        raise EmpiricalRunEvidenceError("frozen_session_axis_invalid")
    session_dates = tuple(session.session_date for session in sessions)
    if any(
        current <= previous
        for previous, current in zip(session_dates, session_dates[1:])
    ):
        raise EmpiricalRunEvidenceError("frozen_session_axis_invalid")
    acquisition_keys = (
        protocol.target_acquisition_keys + protocol.benchmark_acquisition_keys
    )
    if (
        type(protocol.target_acquisition_keys) is not tuple
        or type(protocol.benchmark_acquisition_keys) is not tuple
        or not protocol.target_acquisition_keys
        or not protocol.benchmark_acquisition_keys
        or any(_SHA256.fullmatch(value) is None for value in acquisition_keys)
    ):
        raise EmpiricalRunEvidenceError("acquisition_keys_mismatch")
    if len(acquisition_keys) != len(set(acquisition_keys)):
        raise EmpiricalRunEvidenceError("acquisition_keys_duplicate")
    scope_plan = _read_bound_json(root, protocol.source_scope_plan)
    _validate_scope_plan_semantics(scope_plan, protocol)
    planned_keys = scope_plan.get("scopeAcquisitionKeys")
    if (
        not isinstance(planned_keys, list)
        or any(type(value) is not str for value in planned_keys)
        or len(planned_keys) != len(set(planned_keys))
        or set(planned_keys) != set(acquisition_keys)
    ):
        raise EmpiricalRunEvidenceError("acquisition_keys_mismatch")
    calendar = _read_bound_json(root, protocol.session_calendar)
    expected_sessions = [_feature_session_body(session) for session in sessions]
    if (
        type(calendar.get("schemaVersion")) is not str
        or not calendar.get("schemaVersion")
        or calendar.get("featureMarket") != protocol.market.value
        or calendar.get("sessions") != expected_sessions
    ):
        raise EmpiricalRunEvidenceError("session_calendar_mismatch")

    body = _protocol_body(protocol)
    if _contains_protocol_outcome_key(body):
        raise EmpiricalRunEvidenceError("protocol_contains_outcome_field")
    return body


def _validate_scope_plan_semantics(
    scope_plan: Mapping[str, object],
    protocol: EmpiricalRunProtocol,
) -> None:
    instruments = scope_plan.get("instruments")
    adjustment_modes = scope_plan.get("adjustmentModes")
    if (
        type(scope_plan.get("schemaVersion")) is not str
        or not scope_plan.get("schemaVersion")
        or scope_plan.get("sampleRole") != "exposed_development"
        or not isinstance(instruments, list)
        or not isinstance(adjustment_modes, list)
        or adjustment_modes != [protocol.adjustment_mode]
    ):
        raise EmpiricalRunEvidenceError("scope_plan_semantic_mismatch")
    identities: list[tuple[str, str]] = []
    for value in instruments:
        if (
            not isinstance(value, dict)
            or type(value.get("instrumentId")) is not str
            or type(value.get("symbol")) is not str
        ):
            raise EmpiricalRunEvidenceError("scope_plan_semantic_mismatch")
        identities.append((value["instrumentId"], value["symbol"]))
    symbols = tuple(value[1] for value in identities)
    if (
        len(identities) != 2
        or len(set(identities)) != 2
        or set(symbols) != {protocol.target_symbol, protocol.benchmark_symbol}
    ):
        raise EmpiricalRunEvidenceError("scope_plan_semantic_mismatch")


def _protocol_body(protocol: EmpiricalRunProtocol) -> dict[str, object]:
    return {
        "schemaVersion": _PROTOCOL_SCHEMA,
        "usageScope": "research_only",
        "runId": protocol.run_id,
        "frozenAt": _format_utc(protocol.frozen_at),
        "sampleRole": protocol.sample_role,
        "symbols": {
            "target": protocol.target_symbol,
            "benchmark": protocol.benchmark_symbol,
        },
        "adjustmentMode": protocol.adjustment_mode,
        "featureMarket": protocol.market.value,
        "horizon": protocol.horizon.value,
        "frozenSessionAxis": [
            _feature_session_body(session) for session in protocol.frozen_sessions
        ],
        "acquisitionKeys": {
            "target": list(protocol.target_acquisition_keys),
            "benchmark": list(protocol.benchmark_acquisition_keys),
        },
        "codeRevision": protocol.code_revision,
        "sourceBindings": {
            "scopePlan": _canonical_binding_body(protocol.source_scope_plan),
            "sessionCalendar": _canonical_binding_body(protocol.session_calendar),
        },
    }


def _protocol_from_body(body: Mapping[str, object]) -> EmpiricalRunProtocol:
    if set(body) != _PROTOCOL_KEYS:
        raise EmpiricalRunEvidenceError("protocol_invalid")
    if (
        body.get("schemaVersion") != _PROTOCOL_SCHEMA
        or body.get("usageScope") != "research_only"
        or body.get("sampleRole") != "exposed_development"
    ):
        raise EmpiricalRunEvidenceError("protocol_invalid")
    symbols = body.get("symbols")
    keys = body.get("acquisitionKeys")
    sources = body.get("sourceBindings")
    sessions = body.get("frozenSessionAxis")
    if (
        not isinstance(symbols, dict)
        or set(symbols) != {"target", "benchmark"}
        or not isinstance(keys, dict)
        or set(keys) != {"target", "benchmark"}
        or not isinstance(sources, dict)
        or set(sources) != {"scopePlan", "sessionCalendar"}
        or not isinstance(sessions, list)
    ):
        raise EmpiricalRunEvidenceError("protocol_invalid")
    try:
        return EmpiricalRunProtocol(
            run_id=_required_string(body.get("runId")),
            frozen_at=_parse_utc(_required_string(body.get("frozenAt"))),
            sample_role=_required_string(body.get("sampleRole")),
            target_symbol=_required_string(symbols.get("target")),
            benchmark_symbol=_required_string(symbols.get("benchmark")),
            adjustment_mode=_required_string(body.get("adjustmentMode")),
            market=FeatureMarket(_required_string(body.get("featureMarket"))),
            horizon=LabelHorizon(_required_string(body.get("horizon"))),
            frozen_sessions=tuple(_feature_session_from_body(value) for value in sessions),
            target_acquisition_keys=_string_tuple(keys.get("target")),
            benchmark_acquisition_keys=_string_tuple(keys.get("benchmark")),
            code_revision=_required_string(body.get("codeRevision")),
            source_scope_plan=_canonical_binding_from_body(sources.get("scopePlan")),
            session_calendar=_canonical_binding_from_body(
                sources.get("sessionCalendar")
            ),
        )
    except (TypeError, ValueError):
        raise EmpiricalRunEvidenceError("protocol_invalid") from None


def _validate_completed_inputs(
    protocol_body: Mapping[str, object],
    result: DirectionNeutralEmpiricalResult,
    oof: CompetitivePathDevelopmentOOF,
) -> None:
    if not isinstance(result, DirectionNeutralEmpiricalResult):
        raise EmpiricalRunEvidenceError("empirical_result_invalid")
    if not isinstance(oof, CompetitivePathDevelopmentOOF):
        raise EmpiricalRunEvidenceError("oof_invalid")
    protocol = _protocol_from_body(protocol_body)
    if result.horizon is not protocol.horizon or oof.horizon is not protocol.horizon:
        raise EmpiricalRunEvidenceError("empirical_horizon_mismatch")
    if (
        result.target_series.symbol != protocol.target_symbol
        or result.feature_dataset.symbol != protocol.target_symbol
        or result.benchmark_series.symbol != protocol.benchmark_symbol
        or result.feature_dataset.benchmark_symbol != protocol.benchmark_symbol
    ):
        raise EmpiricalRunEvidenceError("empirical_symbol_mismatch")
    if (
        result.target_series.adjustment_mode != protocol.adjustment_mode
        or result.benchmark_series.adjustment_mode != protocol.adjustment_mode
    ):
        raise EmpiricalRunEvidenceError("adjustment_mode_mismatch")
    if result.feature_dataset.market is not protocol.market:
        raise EmpiricalRunEvidenceError("feature_market_mismatch")
    _validate_result_acquisition_keys(protocol, result)
    result_sessions = tuple(
        entry.session for entry in result.session_coverage.entries
    )
    expected_axis = tuple(
        session.session_date.isoformat() for session in protocol.frozen_sessions
    )
    if result_sessions != protocol.frozen_sessions or oof.frozen_session_axis != expected_axis:
        raise EmpiricalRunEvidenceError("frozen_session_axis_mismatch")
    if not _is_sha256(result.source_evidence_sha256):
        raise EmpiricalRunEvidenceError("empirical_result_evidence_missing")
    _validate_result_rows(protocol, result, expected_axis)
    _validate_oof_rows(protocol, result, oof, expected_axis)
    expected_upstream = _ordered_exclusions(
        result.oof_upstream_exclusions,
        expected_axis,
    )
    actual_upstream = _ordered_exclusions(
        tuple(
            row
            for row in oof.excluded_rows
            if row.reason != "censored_or_not_identifiable"
        ),
        expected_axis,
    )
    if actual_upstream != expected_upstream:
        raise EmpiricalRunEvidenceError("oof_upstream_exclusions_mismatch")


def _validate_result_acquisition_keys(
    protocol: EmpiricalRunProtocol,
    result: DirectionNeutralEmpiricalResult,
) -> None:
    target = tuple(entry.acquisition_key for entry in result.target_series.ledger)
    benchmark = tuple(
        entry.acquisition_key for entry in result.benchmark_series.ledger
    )
    if (
        len(target) != len(set(target))
        or len(benchmark) != len(set(benchmark))
        or set(target) != set(protocol.target_acquisition_keys)
        or set(benchmark) != set(protocol.benchmark_acquisition_keys)
        or any(
            entry.symbol != protocol.target_symbol
            for entry in result.target_series.ledger
        )
        or any(
            entry.symbol != protocol.benchmark_symbol
            for entry in result.benchmark_series.ledger
        )
    ):
        raise EmpiricalRunEvidenceError("result_acquisition_keys_mismatch")


def _validate_result_rows(
    protocol: EmpiricalRunProtocol,
    result: DirectionNeutralEmpiricalResult,
    axis: tuple[str, ...],
) -> None:
    if tuple(value.episode for value in result.episode_results) != result.episodes:
        raise EmpiricalRunEvidenceError("episode_catalog_mismatch")
    screenings = tuple(result.screening_results)
    observations = tuple(value.observation for value in screenings)
    examples = tuple(
        value.example
        for value in result.episode_results
        if value.example is not None
    )
    structural_sources = {
        value.source_evidence_sha256 for value in result.excluded_episodes
    }
    excluded_episode_sources = {
        value.source_evidence_sha256
        for value in result.episode_results
        if value.example is None
    }
    if (
        observations != result.feature_dataset.observations
        or examples != result.examples
        or structural_sources != excluded_episode_sources
        or any(
            value.screening not in screenings
            or value.episode.anchor != value.screening.observation
            for value in result.episode_results
        )
    ):
        raise EmpiricalRunEvidenceError("empirical_result_internal_mismatch")
    if any(
        not isinstance(value, ScreeningResult)
        or value.observation.symbol != protocol.target_symbol
        or value.observation.session_id not in axis
        for value in screenings
    ):
        raise EmpiricalRunEvidenceError("screening_result_mismatch")
    if any(
        not isinstance(value, EpisodeCompetitivePath)
        or value.label.horizon is not protocol.horizon
        or value.episode.anchor.symbol != protocol.target_symbol
        or value.episode.anchor.session_id not in axis
        or not _is_sha256(value.source_evidence_sha256)
        for value in result.episode_results
    ):
        raise EmpiricalRunEvidenceError("episode_result_mismatch")
    if any(
        not isinstance(value, CompetitivePathExample)
        or value.horizon is not protocol.horizon
        or value.symbol != protocol.target_symbol
        or value.session_id not in axis
        for value in result.examples
    ):
        raise EmpiricalRunEvidenceError("episode_example_mismatch")
    if any(
        not isinstance(value, ExcludedEpisode)
        or value.horizon is not protocol.horizon
        or value.symbol != protocol.target_symbol
        or value.session_id not in axis
        or not _is_sha256(value.source_evidence_sha256)
        for value in result.excluded_episodes
    ):
        raise EmpiricalRunEvidenceError("structural_exclusion_mismatch")


def _validate_oof_rows(
    protocol: EmpiricalRunProtocol,
    result: DirectionNeutralEmpiricalResult,
    oof: CompetitivePathDevelopmentOOF,
    axis: tuple[str, ...],
) -> None:
    if not _is_sha256(oof.input_dataset_sha256) or not _is_sha256(
        oof.row_mask_sha256
    ):
        raise EmpiricalRunEvidenceError("oof_input_mask_evidence_missing")
    if (
        not oof.class_order
        or len(oof.class_order) != len(set(oof.class_order))
        or not oof.model_ids
        or len(oof.model_ids) != len(set(oof.model_ids))
        or not set(oof.candidate_model_ids).issubset(oof.model_ids)
        or not oof.folds
        or not oof.common_validation_row_ids
        or not oof.predictions
        or not oof.metrics
    ):
        raise EmpiricalRunEvidenceError("oof_evidence_incomplete")
    if len(oof.common_validation_row_ids) != len(set(oof.common_validation_row_ids)):
        raise EmpiricalRunEvidenceError("oof_common_rows_invalid")
    fold_ids = tuple(fold.fold_id for fold in oof.folds)
    if len(fold_ids) != len(set(fold_ids)):
        raise EmpiricalRunEvidenceError("oof_fold_invalid")
    examples_by_id = {value.row_id: value for value in result.examples}
    if (
        len(examples_by_id) != len(result.examples)
        or any(row_id not in examples_by_id for row_id in oof.common_validation_row_ids)
    ):
        raise EmpiricalRunEvidenceError("oof_result_lineage_mismatch")
    for row in oof.predictions:
        example = examples_by_id.get(row.row_id)
        if (
            not isinstance(row, OOFProbabilityRow)
            or row.model_id not in oof.model_ids
            or row.fold_id not in fold_ids
            or row.symbol != protocol.target_symbol
            or row.session_id not in axis
            or row.row_id not in oof.common_validation_row_ids
            or not _is_sha256(row.source_evidence_sha256)
            or len(row.probabilities) != len(oof.class_order)
            or any(not _is_finite_probability(value) for value in row.probabilities)
            or not math.isclose(sum(row.probabilities), 1.0, abs_tol=1e-12)
        ):
            raise EmpiricalRunEvidenceError("oof_probability_row_invalid")
        if (
            example is None
            or row.symbol != example.symbol
            or row.session_id != example.session_id
            or row.label is not example.label
            or row.source_evidence_sha256 != example.source_evidence_sha256
        ):
            raise EmpiricalRunEvidenceError("oof_result_lineage_mismatch")
    expected_rows = oof.common_validation_row_ids
    for model_id in oof.model_ids:
        model_rows = tuple(
            row.row_id for row in oof.predictions if row.model_id == model_id
        )
        if model_rows != expected_rows:
            raise EmpiricalRunEvidenceError("oof_common_rows_invalid")
    if tuple(metric.model_id for metric in oof.metrics) != oof.model_ids or any(
        not isinstance(metric, OOFMetrics)
        or metric.row_count != len(expected_rows)
        or any(
            not _is_finite_number(value)
            for value in (
                metric.multiclass_brier,
                metric.log_loss,
                metric.top_class_ece,
            )
        )
        for metric in oof.metrics
    ):
        raise EmpiricalRunEvidenceError("oof_metrics_invalid")
    excluded_ids = tuple(row.row_id for row in oof.excluded_rows)
    if len(excluded_ids) != len(set(excluded_ids)) or set(excluded_ids) & set(
        expected_rows
    ):
        raise EmpiricalRunEvidenceError("oof_excluded_rows_invalid")
    if any(
        not isinstance(row, ExcludedOOFRow)
        or row.horizon is not protocol.horizon
        or row.symbol != protocol.target_symbol
        or row.session_id not in axis
        for row in oof.excluded_rows
    ):
        raise EmpiricalRunEvidenceError("oof_excluded_rows_invalid")
    for row in oof.excluded_rows:
        if row.reason != "censored_or_not_identifiable":
            continue
        example = examples_by_id.get(row.row_id)
        if (
            example is None
            or row.symbol != example.symbol
            or row.session_id != example.session_id
            or row.label is not example.label
            or row.source_evidence_sha256 != example.source_evidence_sha256
        ):
            raise EmpiricalRunEvidenceError("oof_result_lineage_mismatch")


def _episode_catalog_body(
    run_id: str,
    protocol_binding: Mapping[str, object],
    result: DirectionNeutralEmpiricalResult,
) -> dict[str, object]:
    state_counts = Counter(value.state.value for value in result.screening_results)
    return {
        "schemaVersion": _EPISODE_CATALOG_SCHEMA,
        "runId": run_id,
        "protocol": dict(protocol_binding),
        "stateCounts": {
            state.value: state_counts[state.value] for state in ScreenState
        },
        "candidateMinutes": [
            _candidate_minute_body(value)
            for value in result.screening_results
            if value.state is ScreenState.CANDIDATE
        ],
        "episodes": [
            _episode_result_body(value, result.excluded_episodes)
            for value in result.episode_results
        ],
        "structuralExclusions": [
            _excluded_episode_body(value) for value in result.excluded_episodes
        ],
        "sourceEvidenceSha256": result.source_evidence_sha256,
    }


def _candidate_minute_body(value: ScreeningResult) -> dict[str, object]:
    observation = value.observation
    return {
        **_observation_identity_body(observation),
        "state": value.state.value,
        "familyThresholds": [
            {
                "family": screen.family,
                "observationCount": screen.observation_count,
                "score": screen.score,
                "p99": screen.p99,
                "p999": screen.p999,
                "exceedsP99": screen.exceeds_p99,
                "exceedsP999": screen.exceeds_p999,
            }
            for screen in value.family_screens
        ],
    }


def _episode_result_body(
    value: EpisodeCompetitivePath,
    exclusions: Sequence[ExcludedEpisode],
) -> dict[str, object]:
    row_id = (
        value.example.row_id
        if value.example is not None
        else next(
            (
                exclusion.row_id
                for exclusion in exclusions
                if exclusion.source_evidence_sha256 == value.source_evidence_sha256
            ),
            None,
        )
    )
    return {
        "rowId": row_id,
        "anchor": _observation_identity_body(value.episode.anchor),
        "bursts": [
            {
                "candidateMarketMinuteOrdinals": list(
                    burst.candidate_market_minute_ordinals
                )
            }
            for burst in value.episode.bursts
        ],
        "closedAtMarketMinuteOrdinal": value.episode.closed_at_market_minute_ordinal,
        "coverageComplete": value.episode.coverage_complete,
        "rightCensored": value.episode.right_censored,
        "label": _competitive_label_body(value.label),
        "example": (
            None if value.example is None else _example_body(value.example)
        ),
        "sourceEvidenceSha256": value.source_evidence_sha256,
    }


def _competitive_label_body(value: CompetitivePathResult) -> dict[str, object]:
    return {
        "horizon": value.horizon.value,
        "label": value.label.value,
        "reason": value.reason,
        "sigma": value.sigma,
        "lowerBarrier": value.lower_barrier,
        "upperBarrier": value.upper_barrier,
        "firstPassageMarketMinuteOrdinal": value.first_passage_market_minute_ordinal,
        "secondPassageMarketMinuteOrdinal": value.second_passage_market_minute_ordinal,
        "horizonEndMarketMinuteOrdinal": value.horizon_end_market_minute_ordinal,
    }


def _example_body(value: CompetitivePathExample) -> dict[str, object]:
    return {
        "rowId": value.row_id,
        "symbol": value.symbol,
        "sessionId": value.session_id,
        "sampleRole": value.sample_role,
        "horizon": value.horizon.value,
        "label": value.label.value,
        "familyFlags": {
            family: {
                "exceedsP99": flags.exceeds_p99,
                "exceedsP999": flags.exceeds_p999,
            }
            for family, flags in value.family_flags.items()
        },
        "signedReturn": value.signed_return,
        "intrabarLogRange": value.intrabar_log_range,
        "sourceEvidenceSha256": value.source_evidence_sha256,
    }


def _excluded_episode_body(value: ExcludedEpisode) -> dict[str, object]:
    return {
        "rowId": value.row_id,
        "symbol": value.symbol,
        "sessionId": value.session_id,
        "horizon": value.horizon.value,
        "label": value.label.value,
        "reason": value.reason.value,
        "sourceEvidenceSha256": value.source_evidence_sha256,
    }


def _observation_identity_body(
    value: DirectionNeutralObservation,
) -> dict[str, object]:
    return {
        "symbol": value.symbol,
        "sessionId": value.session_id,
        "sessionDate": value.session_date.isoformat(),
        "sessionOrdinal": value.session_ordinal,
        "minuteOfDay": value.minute_of_day,
        "marketMinuteOrdinal": value.market_minute_ordinal,
        "minuteEndUtc": _format_utc(value.minute_end_utc),
        "availableAtUtc": _format_utc(value.available_at_utc),
        "sourceWindowSha256": value.source_window_sha256,
        "signedReturn": value.signed_return,
        "logLow": value.log_low,
        "logHigh": value.log_high,
        "logClose": value.log_close,
        "familyScores": dict(value.family_scores),
    }


def _oof_body(
    run_id: str,
    protocol_binding: Mapping[str, object],
    oof: CompetitivePathDevelopmentOOF,
) -> dict[str, object]:
    return {
        "schemaVersion": _OOF_SCHEMA,
        "runId": run_id,
        "protocol": dict(protocol_binding),
        "horizon": oof.horizon.value,
        "classes": [value.value for value in oof.class_order],
        "modelIds": list(oof.model_ids),
        "candidateModelIds": list(oof.candidate_model_ids),
        "frozenSessionAxis": list(oof.frozen_session_axis),
        "folds": [_fold_body(value) for value in oof.folds],
        "excludedRows": [_excluded_oof_body(value) for value in oof.excluded_rows],
        "commonValidationRowIds": list(oof.common_validation_row_ids),
        "rowMaskSha256": oof.row_mask_sha256,
        "inputDatasetSha256": oof.input_dataset_sha256,
        "probabilityRows": [
            _probability_row_body(value) for value in oof.predictions
        ],
        "metrics": [_metrics_body(value) for value in oof.metrics],
        "hyperparameters": {
            "seed": oof.hyperparameters.seed,
            "softmaxInitialization": oof.hyperparameters.softmax_initialization,
            "randomness": oof.hyperparameters.randomness,
            "b2Shrinkage": oof.hyperparameters.b2_shrinkage,
            "softmaxIterations": oof.hyperparameters.softmax_iterations,
            "softmaxLearningRate": oof.hyperparameters.softmax_learning_rate,
            "softmaxL2": oof.hyperparameters.softmax_l2,
            "eceBins": oof.hyperparameters.ece_bins,
        },
    }


def _fold_body(value: DevelopmentFold) -> dict[str, object]:
    return {
        "foldId": value.fold_id,
        "train": _interval_body(value.train),
        "purge": _interval_body(value.purge),
        "validation": _interval_body(value.validation),
        "embargo": _interval_body(value.embargo),
    }


def _interval_body(value: SessionInterval) -> dict[str, int]:
    return {"start": value.start, "stop": value.stop}


def _excluded_oof_body(value: ExcludedOOFRow) -> dict[str, object]:
    return {
        "rowId": value.row_id,
        "symbol": value.symbol,
        "sessionId": value.session_id,
        "horizon": value.horizon.value,
        "label": value.label.value,
        "reason": value.reason,
        "sourceEvidenceSha256": value.source_evidence_sha256,
    }


def _probability_row_body(value: OOFProbabilityRow) -> dict[str, object]:
    return {
        "modelId": value.model_id,
        "foldId": value.fold_id,
        "rowId": value.row_id,
        "symbol": value.symbol,
        "sessionId": value.session_id,
        "label": value.label.value,
        "sourceEvidenceSha256": value.source_evidence_sha256,
        "probabilities": list(value.probabilities),
    }


def _metrics_body(value: OOFMetrics) -> dict[str, object]:
    return {
        "modelId": value.model_id,
        "rowCount": value.row_count,
        "multiclassBrier": value.multiclass_brier,
        "logLoss": value.log_loss,
        "topClassEce": value.top_class_ece,
    }


def _trial_body(
    run_id: str,
    protocol_binding: Mapping[str, object],
    result: DirectionNeutralEmpiricalResult,
    oof: CompetitivePathDevelopmentOOF,
) -> dict[str, object]:
    metrics = {value.model_id: value for value in oof.metrics}
    probability_counts = Counter(value.model_id for value in oof.predictions)
    return {
        "schemaVersion": _TRIAL_SCHEMA,
        "runId": run_id,
        "protocol": dict(protocol_binding),
        "status": "completed_development_oof",
        "counts": {
            "candidateMinutes": sum(
                value.state is ScreenState.CANDIDATE
                for value in result.screening_results
            ),
            "episodes": len(result.episode_results),
            "structuralExclusions": len(result.excluded_episodes),
            "oofExcludedRows": len(oof.excluded_rows),
            "oofProbabilityRows": len(oof.predictions),
            "attempts": len(oof.model_ids),
        },
        "attempts": [
            {
                "modelId": model_id,
                "role": (
                    "candidate"
                    if model_id in oof.candidate_model_ids
                    else "baseline"
                ),
                "status": "completed",
                "probabilityRowCount": probability_counts[model_id],
                "metrics": _metrics_body(metrics[model_id]),
            }
            for model_id in oof.model_ids
        ],
        "postResultTuning": False,
        "confirmationOpened": False,
        "externalAccessCounts": {"orders": 0, "accounts": 0, "assets": 0},
        "costGate": "not_evaluated",
    }


def _load_frozen_protocol(
    root: Path,
    frozen: FrozenEmpiricalProtocol,
) -> Mapping[str, object]:
    if not isinstance(frozen, FrozenEmpiricalProtocol):
        raise EmpiricalRunEvidenceError("protocol_binding_invalid")
    _require_run_id(frozen.run_id)
    expected_relative = _protocol_relative_path(frozen.run_id)
    expected_path = root / expected_relative
    if (
        frozen.protocol_path != expected_path
        or not _is_sha256(frozen.protocol_sha256)
    ):
        raise EmpiricalRunEvidenceError("protocol_binding_invalid")
    body, actual_sha256 = _read_json_artifact(
        root,
        expected_relative,
        expected_sha256=frozen.protocol_sha256,
    )
    if actual_sha256 != frozen.protocol_sha256:
        raise EmpiricalRunEvidenceError("protocol_binding_invalid")
    parsed = _protocol_from_body(body)
    regenerated = _validate_protocol(root, parsed)
    if parsed.run_id != frozen.run_id or regenerated != body:
        raise EmpiricalRunEvidenceError("protocol_binding_invalid")
    return body


def _require_terminal_not_before_freeze(
    protocol_body: Mapping[str, object],
    terminal_at: datetime,
) -> None:
    frozen_at = _parse_utc(_required_string(protocol_body.get("frozenAt")))
    if terminal_at < frozen_at:
        raise EmpiricalRunEvidenceError("terminal_timestamp_before_freeze")


def _require_open_frozen_run(
    events: Sequence[_StoredLedgerRecord],
    protocol: FrozenEmpiricalProtocol,
    protocol_body: Mapping[str, object],
) -> None:
    run_events = _events_for_run(events, protocol.run_id)
    if len(run_events) != 1:
        raise EmpiricalRunEvidenceError(
            "run_already_terminal" if len(run_events) > 1 else "freeze_event_missing"
        )
    binding = _binding_body(
        _protocol_relative_path(protocol.run_id),
        protocol.protocol_sha256,
    )
    _verify_freeze_event(
        run_events[0],
        protocol.run_id,
        binding,
        _required_string(protocol_body.get("frozenAt")),
    )


def _verify_freeze_event(
    event: _StoredLedgerRecord,
    run_id: str,
    protocol_binding: Mapping[str, object],
    frozen_at: str,
) -> None:
    payload = event.body.get("payload")
    if (
        event.body.get("eventType") != _FROZEN_EVENT
        or event.body.get("occurredAt") != frozen_at
        or not isinstance(payload, dict)
        or payload != {"runId": run_id, "protocol": dict(protocol_binding)}
    ):
        raise EmpiricalRunEvidenceError("freeze_event_invalid")


def _verify_completed_run(
    root: Path,
    run_id: str,
    protocol_binding: Mapping[str, object],
    protocol_body: Mapping[str, object],
    terminal: _StoredLedgerRecord,
) -> str:
    expected_names = {
        "protocol.json",
        "protocol.json.sha256",
        "episode-catalog.json",
        "episode-catalog.json.sha256",
        "oof.json",
        "oof.json.sha256",
        "trial.json",
        "trial.json.sha256",
        "manifest.json",
        "manifest.json.sha256",
    }
    _require_run_inventory(root, run_id, expected_names)
    manifest_relative = f"runs/{run_id}/manifest.json"
    manifest_body, manifest_sha256 = _read_json_artifact(root, manifest_relative)
    payload = terminal.body.get("payload")
    if (
        not isinstance(payload, dict)
        or payload
        != {
            "runId": run_id,
            "protocol": dict(protocol_binding),
            "manifest": _binding_body(manifest_relative, manifest_sha256),
        }
        or set(manifest_body)
        != {
            "schemaVersion",
            "runId",
            "status",
            "completedAt",
            "protocol",
            "artifacts",
        }
        or manifest_body.get("schemaVersion") != _MANIFEST_SCHEMA
        or manifest_body.get("runId") != run_id
        or manifest_body.get("status") != "completed"
        or terminal.body.get("occurredAt") != manifest_body.get("completedAt")
        or manifest_body.get("protocol") != protocol_binding
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    _parse_utc(_required_string(manifest_body.get("completedAt")))
    artifacts = manifest_body.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "episodeCatalog",
        "oof",
        "trial",
    }:
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    bodies: dict[str, Mapping[str, object]] = {}
    for key, filename in (
        ("episodeCatalog", "episode-catalog.json"),
        ("oof", "oof.json"),
        ("trial", "trial.json"),
    ):
        relative = f"runs/{run_id}/{filename}"
        binding = artifacts.get(key)
        expected_sha256 = _sha_from_binding(binding, relative)
        body, actual_sha256 = _read_json_artifact(
            root,
            relative,
            expected_sha256=expected_sha256,
        )
        if actual_sha256 != expected_sha256:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        bodies[key] = body
    _verify_completed_bodies(
        run_id,
        protocol_binding,
        protocol_body,
        bodies,
    )
    return manifest_sha256


def _verify_completed_bodies(
    run_id: str,
    protocol_binding: Mapping[str, object],
    protocol_body: Mapping[str, object],
    bodies: Mapping[str, Mapping[str, object]],
) -> None:
    catalog = bodies["episodeCatalog"]
    oof = bodies["oof"]
    trial = bodies["trial"]
    if (
        catalog.get("schemaVersion") != _EPISODE_CATALOG_SCHEMA
        or oof.get("schemaVersion") != _OOF_SCHEMA
        or trial.get("schemaVersion") != _TRIAL_SCHEMA
        or any(body.get("runId") != run_id for body in bodies.values())
        or any(body.get("protocol") != protocol_binding for body in bodies.values())
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    protocol = _protocol_from_body(protocol_body)
    expected_axis = [
        session.session_date.isoformat() for session in protocol.frozen_sessions
    ]
    if (
        oof.get("horizon") != protocol.horizon.value
        or oof.get("frozenSessionAxis") != expected_axis
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    candidates = catalog.get("candidateMinutes")
    episodes = catalog.get("episodes")
    structural = catalog.get("structuralExclusions")
    excluded = oof.get("excludedRows")
    probabilities = oof.get("probabilityRows")
    model_ids = oof.get("modelIds")
    attempts = trial.get("attempts")
    counts = trial.get("counts")
    if not all(
        isinstance(value, list)
        for value in (
            candidates,
            episodes,
            structural,
            excluded,
            probabilities,
            model_ids,
            attempts,
        )
    ) or not isinstance(counts, dict):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    expected_counts = {
        "candidateMinutes": len(candidates),
        "episodes": len(episodes),
        "structuralExclusions": len(structural),
        "oofExcludedRows": len(excluded),
        "oofProbabilityRows": len(probabilities),
        "attempts": len(model_ids),
    }
    if (
        counts != expected_counts
        or trial.get("status") != "completed_development_oof"
        or trial.get("postResultTuning") is not False
        or trial.get("confirmationOpened") is not False
        or trial.get("externalAccessCounts")
        != {"orders": 0, "accounts": 0, "assets": 0}
        or trial.get("costGate") != "not_evaluated"
        or [value.get("modelId") for value in attempts if isinstance(value, dict)]
        != model_ids
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    _verify_catalog_oof_lineage(
        protocol,
        episodes,
        structural,
        excluded,
        probabilities,
    )


def _verify_catalog_oof_lineage(
    protocol: EmpiricalRunProtocol,
    episodes: list[object],
    structural: list[object],
    excluded: list[object],
    probabilities: list[object],
) -> None:
    examples: dict[str, Mapping[str, object]] = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        example = episode.get("example")
        if example is None:
            continue
        if not isinstance(example, dict) or type(example.get("rowId")) is not str:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        row_id = str(example["rowId"])
        if row_id in examples:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        examples[row_id] = example
    structural_by_id = _rows_by_id(structural)
    axis = {
        session.session_date.isoformat() for session in protocol.frozen_sessions
    }
    for row in probabilities:
        example = _matching_example(row, examples)
        if not _same_oof_lineage(row, example, protocol, axis):
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
    for row in excluded:
        if not isinstance(row, dict):
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        if row.get("reason") == "censored_or_not_identifiable":
            source = _matching_example(row, examples)
        else:
            source = structural_by_id.get(str(row.get("rowId")))
            if source is None:
                raise EmpiricalRunEvidenceError("evidence_verification_failed")
        if not _same_oof_lineage(row, source, protocol, axis):
            raise EmpiricalRunEvidenceError("evidence_verification_failed")


def _rows_by_id(values: list[object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for value in values:
        if not isinstance(value, dict) or type(value.get("rowId")) is not str:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        row_id = str(value["rowId"])
        if row_id in result:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        result[row_id] = value
    return result


def _matching_example(
    row: object,
    examples: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object]:
    if not isinstance(row, dict) or type(row.get("rowId")) is not str:
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    example = examples.get(str(row["rowId"]))
    if example is None:
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    return example


def _same_oof_lineage(
    row: object,
    source: Mapping[str, object],
    protocol: EmpiricalRunProtocol,
    axis: set[str],
) -> bool:
    return (
        isinstance(row, dict)
        and row.get("symbol") == source.get("symbol") == protocol.target_symbol
        and row.get("sessionId") == source.get("sessionId")
        and row.get("sessionId") in axis
        and row.get("horizon", protocol.horizon.value) == protocol.horizon.value
        and row.get("label") == source.get("label")
        and row.get("sourceEvidenceSha256")
        == source.get("sourceEvidenceSha256")
    )


def _verify_failed_run(
    root: Path,
    run_id: str,
    protocol_binding: Mapping[str, object],
    terminal: _StoredLedgerRecord,
) -> str:
    _require_run_inventory(
        root,
        run_id,
        {
            "protocol.json",
            "protocol.json.sha256",
            "failure.json",
            "failure.json.sha256",
        },
    )
    failure_relative = f"runs/{run_id}/failure.json"
    failure, failure_sha256 = _read_json_artifact(root, failure_relative)
    payload = terminal.body.get("payload")
    if (
        not isinstance(payload, dict)
        or payload
        != {
            "runId": run_id,
            "protocol": dict(protocol_binding),
            "failure": _binding_body(failure_relative, failure_sha256),
        }
        or set(failure)
        != {"schemaVersion", "runId", "status", "failedAt", "errorCode", "protocol"}
        or failure.get("schemaVersion") != _FAILURE_SCHEMA
        or failure.get("runId") != run_id
        or failure.get("status") != "failed"
        or terminal.body.get("occurredAt") != failure.get("failedAt")
        or failure.get("protocol") != protocol_binding
        or type(failure.get("errorCode")) is not str
        or _ERROR_CODE.fullmatch(str(failure.get("errorCode"))) is None
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    _parse_utc(_required_string(failure.get("failedAt")))
    return failure_sha256


def _read_bound_json(
    root: Path,
    binding: CanonicalJsonBinding,
) -> Mapping[str, object]:
    try:
        if not isinstance(binding, CanonicalJsonBinding) or not _is_sha256(
            binding.sha256
        ):
            raise EmpiricalRunEvidenceError("source_binding_invalid")
        body, actual_sha256 = _read_json_artifact(
            root,
            binding.relative_path,
            expected_sha256=binding.sha256,
        )
        if actual_sha256 != binding.sha256:
            raise EmpiricalRunEvidenceError("source_binding_invalid")
        return body
    except EmpiricalRunEvidenceError:
        raise EmpiricalRunEvidenceError("source_binding_invalid") from None
    except (LocalEvidenceError, OSError, ValueError):
        raise EmpiricalRunEvidenceError("source_binding_invalid") from None


def _read_json_artifact(
    root: Path,
    relative_path: str,
    *,
    expected_sha256: str | None = None,
) -> tuple[Mapping[str, object], str]:
    source = _read_regular_relative(root, relative_path)
    sidecar = _read_regular_relative(root, f"{relative_path}.sha256")
    actual_sha256 = sha256_bytes(source)
    if (
        expected_sha256 is not None
        and actual_sha256 != expected_sha256
        or sidecar != f"{actual_sha256}\n".encode("ascii")
    ):
        raise EmpiricalRunEvidenceError("artifact_hash_mismatch")
    body = _decode_canonical_object(source)
    if find_sensitive_values(source.decode("utf-8")):
        raise EmpiricalRunEvidenceError("sensitive_value_refused")
    return body, actual_sha256


def _read_regular_relative(root: Path, relative_path: str) -> bytes:
    parts = _relative_parts(relative_path)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(root, directory_flags)
    try:
        for component in parts[:-1]:
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], file_flags, dir_fd=directory)
        try:
            before = os.fstat(descriptor)
            attached = os.stat(
                parts[-1],
                dir_fd=directory,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(attached.st_mode)
                or (before.st_dev, before.st_ino)
                != (attached.st_dev, attached.st_ino)
            ):
                raise EmpiricalRunEvidenceError("regular_file_required")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                source = stream.read()
            after = os.fstat(descriptor)
            reattached = os.stat(
                parts[-1],
                dir_fd=directory,
                follow_symlinks=False,
            )
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or after.st_size != len(source)
                or not stat.S_ISREG(reattached.st_mode)
                or (after.st_dev, after.st_ino)
                != (reattached.st_dev, reattached.st_ino)
            ):
                raise EmpiricalRunEvidenceError("artifact_changed_during_read")
            return source
        finally:
            os.close(descriptor)
    except OSError:
        raise EmpiricalRunEvidenceError("regular_file_required") from None
    finally:
        os.close(directory)


def _read_validated_ledger_records(
    root: Path,
) -> tuple[_StoredLedgerRecord, ...]:
    _relative_parts("ledger/events")
    _list_regular_directory(root, "ledger/events")
    try:
        with AppendOnlyLocalLedger(root / "ledger").transaction() as transaction:
            state = transaction.validate()
            records = _read_ledger_records(root, state.sequence)
            _validate_ledger_record_chain(records)
            if transaction.validate() != state:
                raise EmpiricalRunEvidenceError("evidence_verification_failed")
            transaction.verify()
            return records
    except (EmpiricalRunEvidenceError, LocalEvidenceError):
        raise EmpiricalRunEvidenceError("evidence_verification_failed") from None


def _validate_ledger_record_chain(
    records: Sequence[_StoredLedgerRecord],
) -> None:
    previous_sha256: str | None = None
    for sequence, record in enumerate(records, start=1):
        decoded = decode_canonical_local_ledger_record(
            canonical_json_bytes(record.body),
            expected_sequence=sequence,
            expected_previous_sha256=previous_sha256,
        )
        if decoded != record.body:
            raise EmpiricalRunEvidenceError("evidence_verification_failed")
        previous_sha256 = record.sha256


def _read_ledger_records(
    root: Path,
    count: int,
) -> tuple[_StoredLedgerRecord, ...]:
    records: list[_StoredLedgerRecord] = []
    for sequence in range(1, count + 1):
        body, record_sha256 = _read_json_artifact(
            root,
            f"ledger/events/{sequence:06d}.json",
        )
        records.append(_StoredLedgerRecord(body=body, sha256=record_sha256))
    return tuple(records)


def _events_for_run(
    events: Sequence[_StoredLedgerRecord],
    run_id: str,
) -> tuple[_StoredLedgerRecord, ...]:
    return tuple(
        event
        for event in events
        if isinstance(event.body.get("payload"), dict)
        and event.body["payload"].get("runId") == run_id
    )


def _require_run_inventory(
    root: Path,
    run_id: str,
    expected_names: set[str],
) -> None:
    actual = set(_list_regular_directory(root, f"runs/{run_id}"))
    if actual != expected_names:
        raise EmpiricalRunEvidenceError("evidence_verification_failed")


def _list_regular_directory(root: Path, relative_path: str) -> tuple[str, ...]:
    parts = _relative_parts(relative_path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(root, flags)
    try:
        for component in parts:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        names = tuple(os.listdir(descriptor))
        for name in names:
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise EmpiricalRunEvidenceError("regular_file_required")
        return names
    except OSError:
        raise EmpiricalRunEvidenceError("regular_file_required") from None
    finally:
        os.close(descriptor)


def _decode_canonical_object(source: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError, ValueError):
        raise EmpiricalRunEvidenceError("canonical_json_invalid") from None
    if not isinstance(value, dict) or canonical_json_bytes(value) != source:
        raise EmpiricalRunEvidenceError("canonical_json_invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite_json_constant:{value}")


def _relative_parts(value: object) -> tuple[str, ...]:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise EmpiricalRunEvidenceError("relative_path_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise EmpiricalRunEvidenceError("relative_path_invalid")
    return path.parts


def _require_trusted_root(value: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise EmpiricalRunEvidenceError("trusted_root_invalid")
    try:
        return require_trusted_directory_root(value)
    except LocalEvidenceError:
        raise EmpiricalRunEvidenceError("trusted_root_invalid") from None


def _require_run_id(run_id: object) -> None:
    if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
        raise EmpiricalRunEvidenceError("run_id_invalid")


def _require_utc(value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise EmpiricalRunEvidenceError("timestamp_not_utc")


def _format_utc(value: datetime) -> str:
    _require_utc(value)
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EmpiricalRunEvidenceError("timestamp_not_utc") from None
    _require_utc(parsed)
    if _format_utc(parsed) != value:
        raise EmpiricalRunEvidenceError("timestamp_not_utc")
    return parsed


def _feature_session_body(value: FeatureSession) -> dict[str, object]:
    return {
        "sessionDate": value.session_date.isoformat(),
        "regularMinutes": value.regular_minutes,
    }


def _feature_session_from_body(value: object) -> FeatureSession:
    if not isinstance(value, dict) or set(value) != {
        "sessionDate",
        "regularMinutes",
    }:
        raise ValueError("feature_session_invalid")
    session_date = datetime.strptime(
        _required_string(value.get("sessionDate")),
        "%Y-%m-%d",
    ).date()
    regular_minutes = value.get("regularMinutes")
    if type(regular_minutes) is not int:
        raise ValueError("feature_session_invalid")
    return FeatureSession(session_date, regular_minutes)


def _canonical_binding_body(value: CanonicalJsonBinding) -> dict[str, str]:
    if not isinstance(value, CanonicalJsonBinding) or not _is_sha256(value.sha256):
        raise EmpiricalRunEvidenceError("source_binding_invalid")
    _relative_parts(value.relative_path)
    return {"path": value.relative_path, "sha256": value.sha256}


def _canonical_binding_from_body(value: object) -> CanonicalJsonBinding:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("binding_invalid")
    return CanonicalJsonBinding(
        relative_path=_required_string(value.get("path")),
        sha256=_required_string(value.get("sha256")),
    )


def _binding_body(relative_path: str, sha256: str) -> dict[str, str]:
    _relative_parts(relative_path)
    if not _is_sha256(sha256):
        raise EmpiricalRunEvidenceError("binding_invalid")
    return {"path": relative_path, "sha256": sha256}


def _relative_binding(
    root: Path,
    value: LocalArtifactBinding,
) -> dict[str, str]:
    try:
        relative = value.path.relative_to(root).as_posix()
    except ValueError:
        raise EmpiricalRunEvidenceError("binding_invalid") from None
    return _binding_body(relative, value.artifact_sha256)


def _sha_from_binding(value: object, expected_path: str) -> str:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "sha256"}
        or value.get("path") != expected_path
        or not _is_sha256(value.get("sha256"))
    ):
        raise EmpiricalRunEvidenceError("evidence_verification_failed")
    return str(value["sha256"])


def _protocol_relative_path(run_id: str) -> str:
    _require_run_id(run_id)
    return f"runs/{run_id}/protocol.json"


def _contains_protocol_outcome_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            any(term in str(key).lower() for term in _PROTOCOL_FORBIDDEN_KEY_TERMS)
            or _contains_protocol_outcome_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_protocol_outcome_key(item) for item in value)
    return False


def _require_publishable_body(value: Mapping[str, object]) -> None:
    try:
        source = canonical_json_bytes(value)
    except LocalEvidenceError:
        raise EmpiricalRunEvidenceError("evidence_payload_invalid") from None
    if find_sensitive_values(source.decode("utf-8")):
        raise EmpiricalRunEvidenceError("sensitive_value_refused")


def _publish(
    store: LocalArtifactStore,
    path: Path,
    value: Mapping[str, object],
    publications: list[LocalArtifactBinding],
) -> LocalArtifactBinding:
    binding = store.publish_json(path, value)
    publications.append(binding)
    return binding


def _rollback_if_uncommitted(
    store: LocalArtifactStore,
    binding: LocalArtifactBinding | None,
) -> None:
    if binding is None:
        return
    try:
        store.rollback_publication(binding)
    except LocalEvidenceError:
        raise EmpiricalRunEvidenceError("publication_rollback_failed") from None


def _rollback_publications(
    store: LocalArtifactStore,
    publications: Sequence[LocalArtifactBinding],
) -> None:
    for binding in reversed(publications):
        _rollback_if_uncommitted(store, binding)


def _publication_error(error: LocalEvidenceError) -> EmpiricalRunEvidenceError:
    if "sensitive values" in str(error):
        return EmpiricalRunEvidenceError("sensitive_value_refused")
    if "already exists" in str(error):
        return EmpiricalRunEvidenceError("artifact_destination_exists")
    return EmpiricalRunEvidenceError("evidence_publication_failed")


def _ordered_exclusions(
    values: Sequence[ExcludedOOFRow],
    axis: tuple[str, ...],
) -> tuple[ExcludedOOFRow, ...]:
    positions = {session_id: index for index, session_id in enumerate(axis)}
    try:
        return tuple(
            sorted(values, key=lambda row: (positions[row.session_id], row.row_id))
        )
    except KeyError:
        raise EmpiricalRunEvidenceError("oof_upstream_exclusions_mismatch") from None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _is_finite_probability(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= float(value) <= 1.0


def _required_string(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("string_required")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise ValueError("string_list_required")
    return tuple(value)
