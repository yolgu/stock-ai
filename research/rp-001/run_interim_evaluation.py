"""Execute the frozen RP-001 research-only interim evaluation."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from rp001 import interim_candidates as candidate_api
from rp001.interim_candidates import (
    Abstention,
    AbstentionReason,
    BinomialTrainingCount,
    BlockedValidationPlan,
    CandidateHeadId,
    CandidateRawScores,
    CensoredFutureLabels,
    CensoringReason,
    DailyPriceVolumeObservation,
    FixedValidationPlan,
    FutureContinuationLabels,
    OutcomeId,
    PointInTimeFeatureSet,
    Probability,
    build_fixed_validation_plan,
    build_price_volume_features,
    candidate_probability,
    constant_baseline_probability,
    directional_shock_baseline_probability,
    label_future_continuation,
    score_candidate_heads,
)
from rp001.interim_evaluation import (
    CandidateSelectionContext,
    CommonEvaluationKey,
    CommonEvaluationRow,
    CostScenario,
    HypotheticalTrade,
    ShortExecutionEvidence,
    TradeDirection,
    evaluate_common_forecasts,
    evaluate_hypothetical_trades,
)
from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    canonical_json_bytes,
)


Clock = Callable[[], datetime]


class LocalLedger(Protocol):
    def append(
        self,
        event_type: str,
        payload: Mapping[str, object],
        occurred_at: str,
    ) -> object:
        """Append one terminal event."""


LedgerFactory = Callable[[Path], LocalLedger]

_PROGRAM_ID = "RP-001"
_GOAL_VERSION = "1.2-COMPACT"
_USAGE_SCOPE = "research_only"
_OPERATIONAL_DISPOSITION = "NoTrade/no integration"
_SAMPLE_ROLE = "unseen_historical_confirmation"
_EXPECTED_SYMBOLS = ("AMZN", "CAT", "XOM", "AAPL", "AMD", "COST")
_START_DATE = "2023-01-03"
_END_DATE = "2026-06-30"
_INTERVAL = "1d"
_TIMEZONE = "America/New_York"
_EXPECTED_SAMPLE_SHA256 = (
    "aaf7a9442e2f7c17cd7321200b80ab5405ca35e49eafe79a35d953edf42b3ecb"
)
_EXPECTED_MERC_SHA256 = (
    "efa61aa526a4887128c7d78916c23645bda43091b726973f99be9793f65a1ae3"
)
_PRICE_FIELDS = ("openPrice", "highPrice", "lowPrice", "closePrice")
_CANDLE_FIELDS = frozenset((*_PRICE_FIELDS, "volume"))
_SCALAR_FIELDS = frozenset(("kind", "text"))
_UNSIGNED_DECIMAL = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_UNSIGNED_INTEGER = re.compile(r"^[0-9]+$")
_JSON_UNSIGNED_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_JSON_UNSIGNED_INTEGER = re.compile(r"^(?:0|[1-9][0-9]*)$")
_SESSION_TIMEZONE = ZoneInfo(_TIMEZONE)
_HEAD_OUTCOMES = {
    CandidateHeadId.SF: OutcomeId.UPSIDE_CONTINUATION,
    CandidateHeadId.SP: OutcomeId.DOWNSIDE_CONTINUATION,
    CandidateHeadId.ST: OutcomeId.DOWNSIDE_CONTINUATION,
    CandidateHeadId.SR: OutcomeId.UPSIDE_CONTINUATION,
}
_HEAD_SCORE_FIELDS = {
    CandidateHeadId.SF: "sf",
    CandidateHeadId.SP: "sp",
    CandidateHeadId.ST: "st",
    CandidateHeadId.SR: "sr",
}
_SUCCESS_ARTIFACT_ROLES = ("result", "trial", "manifest")


class InterimEvaluationRunError(ValueError):
    """Sanitized terminal failure with a stable machine code."""

    def __init__(
        self,
        code: str,
        stage: str = "execution",
        invalid_row_count: int = 0,
    ) -> None:
        self.code = code
        self.stage = stage
        self.invalid_row_count = invalid_row_count
        super().__init__(f"{code}: interim evaluation failed")


@dataclass(frozen=True)
class InterimEvaluationRunArguments:
    repository_root: Path
    processed_candles_path: Path
    processed_candles_sha256: str
    sample_freeze_path: Path
    sample_freeze_sha256: str
    merc_freeze_path: Path
    merc_freeze_sha256: str
    output_directory: Path
    ledger_directory: Path
    run_id: str


@dataclass(frozen=True)
class InterimEvaluationRunSummary:
    run_id: str
    status: str
    symbol_count: int
    session_count: int
    evaluation_count: int
    artifact_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _VerifiedInputs:
    processed: Mapping[str, object]
    sample: Mapping[str, object]
    merc: Mapping[str, object]
    raw_path: Path
    raw_sha256: str


@dataclass(frozen=True)
class _PreparedPoint:
    feature: PointInTimeFeatureSet | None
    scores: CandidateRawScores | None
    labels: FutureContinuationLabels | None


@dataclass(frozen=True)
class _PreparedSeries:
    symbol: str
    observations: tuple[DailyPriceVolumeObservation, ...]
    timestamps: tuple[datetime, ...]
    points: tuple[_PreparedPoint, ...]


@dataclass(frozen=True)
class _ValidatedCandle:
    close: float
    volume: float


@dataclass(frozen=True)
class _PreparedDataset:
    series: tuple[_PreparedSeries, ...]
    validation_plan: FixedValidationPlan
    counts: Mapping[str, object]
    source_window_manifest_sha256: str


@dataclass(frozen=True)
class _FoldSpecification:
    fold_id: str
    phase: str
    train_start: int
    train_stop: int
    evaluation_start: int
    evaluation_stop: int


@dataclass(frozen=True)
class _TrainingMapping:
    mapping_id: str
    outcome_count: BinomialTrainingCount
    directional_counts: tuple[BinomialTrainingCount, ...]
    candidate_counts: tuple[BinomialTrainingCount, ...]


@dataclass(frozen=True)
class _EvaluationBundle:
    head_id: CandidateHeadId
    outcome_id: OutcomeId
    fold: _FoldSpecification
    rows: tuple[CommonEvaluationRow, ...]
    body: Mapping[str, object]


def run_interim_evaluation(
    arguments: InterimEvaluationRunArguments,
    *,
    clock: Clock | None = None,
    ledger_factory: LedgerFactory = AppendOnlyLocalLedger,
) -> InterimEvaluationRunSummary:
    effective_clock = clock or _system_clock
    try:
        return _run_interim_evaluation_once(
            arguments, effective_clock, ledger_factory
        )
    except InterimEvaluationRunError as error:
        _publish_failure_without_masking(
            arguments, error, effective_clock, ledger_factory
        )
        raise
    except Exception:
        error = InterimEvaluationRunError("INTERNAL_EVALUATION_ERROR")
        _publish_failure_without_masking(
            arguments, error, effective_clock, ledger_factory
        )
        raise error from None


def _run_interim_evaluation_once(
    arguments: InterimEvaluationRunArguments,
    clock: Clock,
    ledger_factory: LedgerFactory,
) -> InterimEvaluationRunSummary:
    repository_root = _repository_root(arguments.repository_root)
    run_directory = _run_directory(arguments, repository_root)
    if run_directory.exists():
        raise InterimEvaluationRunError(
            "OUTPUT_ALREADY_EXISTS", "input_validation"
        )
    evaluation_instant = _clock_instant(clock)
    timestamp = _format_timestamp(evaluation_instant)
    verified = _verify_inputs(arguments, repository_root)
    series = _convert_processed_candles(
        verified.processed, evaluation_instant
    )
    prepared = _prepare_dataset(series)
    bundles, mapping_abstentions = _evaluate_frozen_heads(prepared)
    economics = _evaluate_economics(
        bundles,
        prepared.series,
        verified.merc,
    )
    counts = dict(prepared.counts)
    counts["probabilityMappingAbstentions"] = {
        reason.value: mapping_abstentions.get(reason.value, 0)
        for reason in AbstentionReason
    }
    counts["commonMaskRowCount"] = sum(len(bundle.rows) for bundle in bundles)
    counts["invalidRowCount"] = 0
    counts["failureCount"] = 0
    result = _result_body(
        arguments,
        verified,
        prepared,
        bundles,
        economics,
        counts,
        timestamp,
    )
    trial = _trial_body(
        arguments,
        verified,
        prepared,
        bundles,
        counts,
        timestamp,
    )
    bindings = _publish_success_artifacts(
        arguments,
        repository_root,
        verified,
        result,
        trial,
        timestamp,
    )
    _append_success_event_or_rollback(
        arguments=arguments,
        repository_root=repository_root,
        prepared=prepared,
        bundles=bundles,
        bindings=bindings,
        timestamp=timestamp,
        ledger_factory=ledger_factory,
    )
    return InterimEvaluationRunSummary(
        run_id=arguments.run_id,
        status="succeeded",
        symbol_count=len(prepared.series),
        session_count=len(prepared.series[0].observations),
        evaluation_count=len(bundles),
        artifact_hashes=tuple(
            (role, binding.artifact_sha256) for role, binding in bindings
        ),
    )


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(clock: Clock) -> str:
    return _format_timestamp(_clock_instant(clock))


def _clock_instant(clock: Clock) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InterimEvaluationRunError("CLOCK_INVALID", "evidence")
    return value.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _repository_root(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise InterimEvaluationRunError(
            "REPOSITORY_PATH_INVALID", "input_validation"
        ) from error
    if not resolved.is_dir():
        raise InterimEvaluationRunError(
            "REPOSITORY_PATH_INVALID", "input_validation"
        )
    return resolved


def _resolve_relative(root: Path, path: Path, code: str) -> Path:
    if path.is_absolute():
        raise InterimEvaluationRunError(code, "input_validation")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise InterimEvaluationRunError(code, "input_validation") from error
    return resolved


def _run_directory(
    arguments: InterimEvaluationRunArguments,
    repository_root: Path,
) -> Path:
    if (
        not isinstance(arguments.run_id, str)
        or not arguments.run_id.strip()
        or "/" in arguments.run_id
        or "\\" in arguments.run_id
    ):
        raise InterimEvaluationRunError("RUN_ID_INVALID", "input_validation")
    output_root = _resolve_relative(
        repository_root,
        arguments.output_directory,
        "OUTPUT_PATH_INVALID",
    )
    return output_root / arguments.run_id


def _sha256(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def _load_bound_json(
    repository_root: Path,
    relative_path: Path,
    expected_sha256: str,
) -> tuple[Mapping[str, object], Path]:
    path = _resolve_relative(
        repository_root, relative_path, "INPUT_PATH_INVALID"
    )
    try:
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise InterimEvaluationRunError(
            "INPUT_FILE_INVALID", "input_validation"
        ) from error
    actual_sha256 = _sha256(source)
    if actual_sha256 != expected_sha256 or sidecar != f"{actual_sha256}\n":
        raise InterimEvaluationRunError(
            "INPUT_HASH_MISMATCH", "input_validation"
        )
    try:
        value = json.loads(source)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InterimEvaluationRunError(
            "INPUT_JSON_INVALID", "input_validation"
        ) from error
    if not isinstance(value, Mapping) or canonical_json_bytes(value) != source:
        raise InterimEvaluationRunError(
            "INPUT_CANONICAL_JSON_REQUIRED", "input_validation"
        )
    return value, path


def _verify_inputs(
    arguments: InterimEvaluationRunArguments,
    repository_root: Path,
) -> _VerifiedInputs:
    if (
        arguments.sample_freeze_sha256 != _EXPECTED_SAMPLE_SHA256
        or arguments.merc_freeze_sha256 != _EXPECTED_MERC_SHA256
    ):
        raise InterimEvaluationRunError(
            "INPUT_HASH_MISMATCH", "input_validation"
        )
    processed, _processed_path = _load_bound_json(
        repository_root,
        arguments.processed_candles_path,
        arguments.processed_candles_sha256,
    )
    sample, _sample_path = _load_bound_json(
        repository_root,
        arguments.sample_freeze_path,
        arguments.sample_freeze_sha256,
    )
    merc, _merc_path = _load_bound_json(
        repository_root,
        arguments.merc_freeze_path,
        arguments.merc_freeze_sha256,
    )
    _verify_declared_bindings(repository_root, sample)
    _verify_declared_bindings(repository_root, merc)
    _validate_frozen_scope(sample, merc)
    _validate_processed_scope(processed)
    raw = _mapping(processed.get("rawArtifact"), "DATA_SCHEMA_INVALID")
    raw_path_value = raw.get("path")
    raw_sha256 = raw.get("sha256")
    if not isinstance(raw_path_value, str) or not isinstance(raw_sha256, str):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    raw_path = _verify_declared_file(
        repository_root, raw_path_value, raw_sha256
    )
    return _VerifiedInputs(
        processed=processed,
        sample=sample,
        merc=merc,
        raw_path=raw_path,
        raw_sha256=raw_sha256,
    )


def _verify_declared_bindings(root: Path, value: object) -> None:
    if isinstance(value, Mapping):
        path = value.get("path")
        sha256 = value.get("sha256")
        if isinstance(path, str) and isinstance(sha256, str):
            _verify_declared_file(root, path, sha256)
        source_path = value.get("sourcePath")
        source_sha256 = value.get("sourceSha256")
        if isinstance(source_path, str) and isinstance(source_sha256, str):
            _verify_declared_file(root, source_path, source_sha256)
        test_path = value.get("testPath")
        test_sha256 = value.get("testSha256")
        if isinstance(test_path, str) and isinstance(test_sha256, str):
            _verify_declared_file(root, test_path, test_sha256)
        for nested in value.values():
            _verify_declared_bindings(root, nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _verify_declared_bindings(root, nested)


def _verify_declared_file(root: Path, path_value: str, sha256: str) -> Path:
    path = _resolve_relative(root, Path(path_value), "INPUT_PATH_INVALID")
    try:
        actual = _sha256(path.read_bytes())
    except OSError as error:
        raise InterimEvaluationRunError(
            "INPUT_FILE_INVALID", "input_validation"
        ) from error
    if actual != sha256:
        raise InterimEvaluationRunError(
            "INPUT_HASH_MISMATCH", "input_validation"
        )
    return path


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InterimEvaluationRunError(code, "input_validation", 1)
    return value


def _validate_frozen_scope(
    sample: Mapping[str, object], merc: Mapping[str, object]
) -> None:
    selection = _mapping(sample.get("selection"), "FROZEN_CONTRACT_INVALID")
    period = _mapping(sample.get("period"), "FROZEN_CONTRACT_INVALID")
    data_scope = _mapping(merc.get("dataScope"), "FROZEN_CONTRACT_INVALID")
    validation = _mapping(merc.get("validation"), "FROZEN_CONTRACT_INVALID")
    evaluation = _mapping(merc.get("evaluation"), "FROZEN_CONTRACT_INVALID")
    bootstrap = _mapping(evaluation.get("bootstrap"), "FROZEN_CONTRACT_INVALID")
    multiple = _mapping(
        evaluation.get("multipleComparisons"), "FROZEN_CONTRACT_INVALID"
    )
    expected_period = {
        "startDate": _START_DATE,
        "endDate": _END_DATE,
        "inclusive": True,
        "interval": _INTERVAL,
        "timezone": _TIMEZONE,
    }
    if (
        sample.get("programId") != _PROGRAM_ID
        or sample.get("goalVersion") != _GOAL_VERSION
        or sample.get("usageScope") != _USAGE_SCOPE
        or sample.get("operationalDisposition") != _OPERATIONAL_DISPOSITION
        or selection.get("selectedSymbols") != list(_EXPECTED_SYMBOLS)
        or selection.get("selectedCount") != 6
        or selection.get("sampleRole") != _SAMPLE_ROLE
        or dict(period) != expected_period
        or merc.get("programId") != _PROGRAM_ID
        or merc.get("goalVersion") != _GOAL_VERSION
        or merc.get("usageScope") != _USAGE_SCOPE
        or merc.get("operationalDisposition") != _OPERATIONAL_DISPOSITION
        or data_scope.get("symbols") != list(_EXPECTED_SYMBOLS)
        or data_scope.get("sampleRole") != _SAMPLE_ROLE
        or data_scope.get("startDate") != _START_DATE
        or data_scope.get("endDate") != _END_DATE
        or data_scope.get("interval") != _INTERVAL
        or data_scope.get("timezone") != _TIMEZONE
        or validation.get("minimumSessions") != 607
        or validation.get("minimumTrainingSessions") != 252
        or validation.get("validationSessions") != 63
        or validation.get("purgeSessions") != 10
        or validation.get("embargoSessions") != 10
        or validation.get("terminalHoldoutSessions") != 126
        or validation.get("minimumOofFolds") != 3
        or evaluation.get("alarmThreshold") != 0.5
        or evaluation.get("primaryDelta") != 0.005
        or bootstrap.get("seed") != 20260710
        or bootstrap.get("blockLengthSessions") != 20
        or bootstrap.get("replicates") != 2000
        or multiple.get("familySize") != 4
        or multiple.get("selectionContext")
        != "selected_from_multiple_candidates"
    ):
        raise InterimEvaluationRunError(
            "FROZEN_CONTRACT_INVALID", "input_validation"
        )
    selected_binding = _mapping(
        _mapping(merc.get("bindings"), "FROZEN_CONTRACT_INVALID").get(
            "selectedSampleFreeze"
        ),
        "FROZEN_CONTRACT_INVALID",
    )
    if selected_binding.get("sha256") != _EXPECTED_SAMPLE_SHA256:
        raise InterimEvaluationRunError(
            "FROZEN_CONTRACT_INVALID", "input_validation"
        )


def _validate_processed_scope(processed: Mapping[str, object]) -> None:
    requested = _mapping(processed.get("requestedRange"), "DATA_SCHEMA_INVALID")
    availability = _mapping(processed.get("availability"), "DATA_SCHEMA_INVALID")
    symbols = processed.get("symbols")
    if not isinstance(symbols, list):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    observed_symbols = [
        item.get("symbol") if isinstance(item, Mapping) else None
        for item in symbols
    ]
    if (
        processed.get("schemaVersion")
        != "rp001-toss-daily-candle-processed.v1"
        or processed.get("programId") != _PROGRAM_ID
        or processed.get("goalVersion") != _GOAL_VERSION
        or processed.get("sampleRole") != _SAMPLE_ROLE
        or processed.get("interval") != _INTERVAL
        or processed.get("timezone") != _TIMEZONE
        or requested
        != {
            "startDate": _START_DATE,
            "endDate": _END_DATE,
            "inclusive": True,
        }
        or availability.get("signalTiming")
        != "official_daily_close_usable_next_session"
        or availability.get("providerSessionMembership") != "not_documented"
        or observed_symbols != list(_EXPECTED_SYMBOLS)
    ):
        raise InterimEvaluationRunError(
            "DATA_SCOPE_MISMATCH", "input_validation"
        )


def _lossless_number(value: object, *, is_volume: bool) -> float:
    scalar = _mapping(value, "DATA_SCHEMA_INVALID")
    if frozenset(scalar) != _SCALAR_FIELDS:
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    kind = scalar.get("kind")
    text = scalar.get("text")
    if kind not in {"json_number", "json_string"} or not isinstance(
        text, str
    ):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    string_pattern = _UNSIGNED_INTEGER if is_volume else _UNSIGNED_DECIMAL
    json_pattern = (
        _JSON_UNSIGNED_INTEGER if is_volume else _JSON_UNSIGNED_DECIMAL
    )
    pattern = json_pattern if kind == "json_number" else string_pattern
    if pattern.fullmatch(text) is None or (
        not is_volume
        and not any(character not in {"0", "."} for character in text)
    ):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    try:
        decimal = Decimal(text)
        number = float(decimal)
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        ) from error
    if (
        not decimal.is_finite()
        or not math.isfinite(number)
        or (not is_volume and number <= 0.0)
        or (is_volume and number < 0.0)
    ):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    return number


def _validated_candle(value: object) -> _ValidatedCandle:
    candle = _mapping(value, "DATA_SCHEMA_INVALID")
    if frozenset(candle) != _CANDLE_FIELDS:
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    prices = {
        field: _lossless_number(candle[field], is_volume=False)
        for field in _PRICE_FIELDS
    }
    volume = _lossless_number(candle["volume"], is_volume=True)
    return _ValidatedCandle(close=prices["closePrice"], volume=volume)


def _validated_observation_timestamp(
    value: str,
    session_date: date,
    evaluation_instant: datetime,
) -> datetime:
    try:
        if value != value.strip():
            raise ValueError("timestamp whitespace is forbidden")
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        instant = parsed.astimezone(timezone.utc)
        derived_session_date = instant.astimezone(_SESSION_TIMEZONE).date()
    except (TypeError, ValueError, OverflowError, OSError) as error:
        raise InterimEvaluationRunError(
            "POINT_IN_TIME_AVAILABILITY_INVALID", "input_validation", 1
        ) from error
    if derived_session_date != session_date or instant > evaluation_instant:
        raise InterimEvaluationRunError(
            "POINT_IN_TIME_AVAILABILITY_INVALID", "input_validation", 1
        )
    return instant


def _convert_processed_candles(
    processed: Mapping[str, object],
    evaluation_instant: datetime,
) -> tuple[_PreparedSeries, ...]:
    raw_symbols = processed.get("symbols")
    if not isinstance(raw_symbols, list):
        raise InterimEvaluationRunError(
            "DATA_SCHEMA_INVALID", "input_validation", 1
        )
    series_values: list[_PreparedSeries] = []
    expected_calendar: tuple[str, ...] | None = None
    for raw_symbol in raw_symbols:
        symbol_value = _mapping(raw_symbol, "DATA_SCHEMA_INVALID")
        symbol = symbol_value.get("symbol")
        rows = symbol_value.get("analysisRows")
        if not isinstance(symbol, str) or not isinstance(rows, list):
            raise InterimEvaluationRunError(
                "DATA_SCHEMA_INVALID", "input_validation", 1
            )
        observations: list[DailyPriceVolumeObservation] = []
        timestamps: list[datetime] = []
        prior_date: date | None = None
        prior_timestamp: datetime | None = None
        for raw_row in rows:
            row = _mapping(raw_row, "DATA_SCHEMA_INVALID")
            session_id = row.get("sessionDate")
            timestamp = row.get("timestamp")
            currency = row.get("currency")
            if (
                not isinstance(session_id, str)
                or not isinstance(timestamp, str)
                or not timestamp.strip()
                or not isinstance(currency, str)
                or not currency.strip()
            ):
                raise InterimEvaluationRunError(
                    "DATA_SCHEMA_INVALID", "input_validation", 1
                )
            try:
                session_date = date.fromisoformat(session_id)
            except ValueError as error:
                raise InterimEvaluationRunError(
                    "DATA_SCHEMA_INVALID", "input_validation", 1
                ) from error
            if prior_date is not None and session_date <= prior_date:
                raise InterimEvaluationRunError(
                    "DATA_SCHEMA_INVALID", "input_validation", 1
                )
            observed_at = _validated_observation_timestamp(
                timestamp, session_date, evaluation_instant
            )
            if prior_timestamp is not None and observed_at <= prior_timestamp:
                raise InterimEvaluationRunError(
                    "POINT_IN_TIME_AVAILABILITY_INVALID",
                    "input_validation",
                    1,
                )
            prior_date = session_date
            prior_timestamp = observed_at
            adjusted = _validated_candle(row.get("adjusted"))
            native = _validated_candle(row.get("native"))
            observations.append(
                DailyPriceVolumeObservation(
                    adjusted_close=adjusted.close,
                    native_close=native.close,
                    native_volume=native.volume,
                    currency=currency,
                    series_id=symbol,
                    session_id=session_id,
                    available_as_of_signal=(observed_at <= evaluation_instant),
                )
            )
            timestamps.append(observed_at)
        calendar = tuple(str(row.session_id) for row in observations)
        if (
            len(observations) < 607
            or not calendar
            or calendar[0] != _START_DATE
            or calendar[-1] != _END_DATE
        ):
            raise InterimEvaluationRunError(
                "INSUFFICIENT_OR_INEXACT_SESSIONS", "input_validation"
            )
        if expected_calendar is None:
            expected_calendar = calendar
        elif calendar != expected_calendar:
            raise InterimEvaluationRunError(
                "COMMON_SESSION_CALENDAR_MISMATCH", "input_validation"
            )
        series_values.append(
            _PreparedSeries(
                symbol=symbol,
                observations=tuple(observations),
                timestamps=tuple(timestamps),
                points=(),
            )
        )
    return tuple(series_values)


def _zero_counts(values: Sequence[Enum]) -> dict[str, int]:
    return {str(value.value): 0 for value in values}


def _prepare_dataset(series: tuple[_PreparedSeries, ...]) -> _PreparedDataset:
    feature_abstentions = Counter(_zero_counts(tuple(AbstentionReason)))
    score_abstentions = Counter(_zero_counts(tuple(AbstentionReason)))
    label_censoring = Counter(_zero_counts(tuple(CensoringReason)))
    source_windows: list[dict[str, object]] = []
    prepared_series: list[_PreparedSeries] = []
    feature_count = 0
    label_count = 0
    source_window_check_count = 0
    source_window_mismatch_count = 0
    feature_availability_check_count = 0
    feature_availability_violation_count = 0
    future_label_row_check_count = 0
    for value in series:
        points: list[_PreparedPoint] = []
        for index in range(len(value.observations)):
            feature = build_price_volume_features(value.observations, index)
            if isinstance(feature, Abstention):
                feature_abstentions[feature.reason.value] += 1
                points.append(_PreparedPoint(None, None, None))
                continue
            feature_count += 1
            signal_timestamp = value.timestamps[index]
            feature_timestamps = value.timestamps[index - 21 : index + 1]
            feature_availability_check_count += len(feature_timestamps)
            if any(
                observed_at > signal_timestamp
                for observed_at in feature_timestamps
            ):
                feature_availability_violation_count += 1
                raise InterimEvaluationRunError(
                    "POINT_IN_TIME_AVAILABILITY_INVALID", "evaluation"
                )
            source_windows.append(
                {
                    "seriesId": value.symbol,
                    "sessionId": feature.signal_session_id,
                    "asOfIndex": feature.as_of_index,
                    "sourceWindowSha256": feature.source_window_sha256,
                }
            )
            scores = score_candidate_heads(feature)
            if isinstance(scores, Abstention):
                score_abstentions[scores.reason.value] += 1
                points.append(_PreparedPoint(feature, None, None))
                continue
            labels = label_future_continuation(
                value.observations, index, feature
            )
            source_window_check_count += 1
            future_label_timestamps = value.timestamps[index + 1 : index + 11]
            if len(future_label_timestamps) == 10:
                future_label_row_check_count += len(future_label_timestamps)
                if any(
                    observed_at <= signal_timestamp
                    for observed_at in future_label_timestamps
                ):
                    raise InterimEvaluationRunError(
                        "POINT_IN_TIME_AVAILABILITY_INVALID", "evaluation"
                    )
            if isinstance(labels, CensoredFutureLabels):
                label_censoring[labels.reason.value] += 1
                if labels.reason is CensoringReason.SOURCE_WINDOW_MISMATCH:
                    source_window_mismatch_count += 1
                points.append(_PreparedPoint(feature, scores, None))
                continue
            label_count += 1
            points.append(_PreparedPoint(feature, scores, labels))
        prepared_series.append(
            _PreparedSeries(
                symbol=value.symbol,
                observations=value.observations,
                timestamps=value.timestamps,
                points=tuple(points),
            )
        )
    session_count = len(series[0].observations)
    validation_plan = build_fixed_validation_plan(session_count)
    if isinstance(validation_plan, BlockedValidationPlan):
        raise InterimEvaluationRunError(
            "INSUFFICIENT_OOF_FOLDS", "evaluation"
        )
    source_window_manifest_sha256 = _sha256(
        canonical_json_bytes(source_windows)
    )
    return _PreparedDataset(
        series=tuple(prepared_series),
        validation_plan=validation_plan,
        counts={
            "inputAnalysisRows": sum(
                len(value.observations) for value in series
            ),
            "convertedObservationCount": sum(
                len(value.observations) for value in series
            ),
            "featureEligibleCount": feature_count,
            "labelEligibleCount": label_count,
            "featureAbstentions": dict(feature_abstentions),
            "scoreAbstentions": dict(score_abstentions),
            "labelCensoring": dict(label_censoring),
            "sourceWindowCheckCount": source_window_check_count,
            "sourceWindowMismatchCount": source_window_mismatch_count,
            "featureAvailabilityCheckCount": (
                feature_availability_check_count
            ),
            "featureAvailabilityViolationCount": (
                feature_availability_violation_count
            ),
            "futureLabelRowCheckCount": future_label_row_check_count,
        },
        source_window_manifest_sha256=source_window_manifest_sha256,
    )


def _fold_specifications(plan: FixedValidationPlan) -> tuple[_FoldSpecification, ...]:
    development = tuple(
        _FoldSpecification(
            fold_id=f"development_{fold.ordinal:02d}",
            phase="development_oof",
            train_start=fold.train.start,
            train_stop=fold.train.stop,
            evaluation_start=fold.validation.start,
            evaluation_stop=fold.validation.stop,
        )
        for fold in plan.folds
    )
    terminal = _FoldSpecification(
        fold_id="terminal_holdout",
        phase="terminal_holdout",
        train_start=plan.terminal_mapping_fit_source.start,
        train_stop=plan.terminal_mapping_fit_source.stop,
        evaluation_start=plan.terminal_holdout.start,
        evaluation_stop=plan.terminal_holdout.stop,
    )
    return development + (terminal,)


def _outcome(labels: FutureContinuationLabels, outcome_id: OutcomeId) -> bool:
    if outcome_id is OutcomeId.UPSIDE_CONTINUATION:
        return labels.upside_continuation
    return labels.downside_continuation


def _score(scores: CandidateRawScores, head_id: CandidateHeadId) -> float:
    return float(getattr(scores, _HEAD_SCORE_FIELDS[head_id]))


def _training_mapping(
    dataset: _PreparedDataset,
    fold: _FoldSpecification,
    head_id: CandidateHeadId,
    outcome_id: OutcomeId,
) -> _TrainingMapping:
    outcomes = [0, 0]
    directional = [[0, 0] for _ in range(5)]
    candidate = [[0, 0] for _ in range(5)]
    for series in dataset.series:
        for point in series.points[fold.train_start : fold.train_stop]:
            if point.feature is None or point.scores is None or point.labels is None:
                continue
            outcome = _outcome(point.labels, outcome_id)
            outcomes[1] += 1
            outcomes[0] += int(outcome)
            directional_input = point.feature.vector.z1
            if outcome_id is OutcomeId.DOWNSIDE_CONTINUATION:
                directional_input = -directional_input
            directional_index = candidate_api._closed_bin_index(
                directional_input,
                candidate_api._DIRECTIONAL_BIN_EDGES,
            )
            candidate_index = candidate_api._closed_bin_index(
                _score(point.scores, head_id),
                candidate_api._CANDIDATE_BIN_EDGES,
            )
            directional[directional_index][1] += 1
            directional[directional_index][0] += int(outcome)
            candidate[candidate_index][1] += 1
            candidate[candidate_index][0] += int(outcome)
    outcome_count = BinomialTrainingCount(outcomes[0], outcomes[1])
    directional_counts = tuple(
        BinomialTrainingCount(successes, trials)
        for successes, trials in directional
    )
    candidate_counts = tuple(
        BinomialTrainingCount(successes, trials)
        for successes, trials in candidate
    )
    mapping_body = {
        "headId": head_id.value,
        "outcomeId": outcome_id.value,
        "foldId": fold.fold_id,
        "train": [fold.train_start, fold.train_stop],
        "outcomeCount": dataclasses.asdict(outcome_count),
        "directionalCounts": [dataclasses.asdict(value) for value in directional_counts],
        "candidateCounts": [dataclasses.asdict(value) for value in candidate_counts],
    }
    return _TrainingMapping(
        mapping_id=_sha256(canonical_json_bytes(mapping_body)),
        outcome_count=outcome_count,
        directional_counts=directional_counts,
        candidate_counts=candidate_counts,
    )


def _probability_value(
    value: Probability | Abstention,
    abstentions: Counter[str],
) -> float | None:
    if isinstance(value, Abstention):
        abstentions[value.reason.value] += 1
        return None
    return value.value


def _evaluate_frozen_heads(
    dataset: _PreparedDataset,
) -> tuple[tuple[_EvaluationBundle, ...], Counter[str]]:
    bundles: list[_EvaluationBundle] = []
    mapping_abstentions: Counter[str] = Counter()
    for fold in _fold_specifications(dataset.validation_plan):
        for head_id, outcome_id in _HEAD_OUTCOMES.items():
            mapping = _training_mapping(
                dataset, fold, head_id, outcome_id
            )
            evaluation_key = CommonEvaluationKey(
                outcome_id=outcome_id.value,
                fold_id=fold.fold_id,
                sample_role=_SAMPLE_ROLE,
                training_mapping_id=mapping.mapping_id,
            )
            rows: list[CommonEvaluationRow] = []
            for series in dataset.series:
                for index in range(
                    fold.evaluation_start, fold.evaluation_stop
                ):
                    point = series.points[index]
                    if (
                        point.feature is None
                        or point.scores is None
                        or point.labels is None
                    ):
                        continue
                    candidate_value = _probability_value(
                        candidate_probability(
                            _score(point.scores, head_id),
                            mapping.candidate_counts,
                        ),
                        mapping_abstentions,
                    )
                    b1_value = _probability_value(
                        constant_baseline_probability(mapping.outcome_count),
                        mapping_abstentions,
                    )
                    b2_value = _probability_value(
                        directional_shock_baseline_probability(
                            outcome_id,
                            point.feature.vector.z1,
                            mapping.directional_counts,
                        ),
                        mapping_abstentions,
                    )
                    if None in (candidate_value, b1_value, b2_value):
                        continue
                    session_id = str(
                        series.observations[index].session_id
                    )
                    rows.append(
                        CommonEvaluationRow(
                            evaluation_key=evaluation_key,
                            row_id=(
                                f"{head_id.value}:{fold.fold_id}:"
                                f"{series.symbol}:{session_id}"
                            ),
                            series_id=series.symbol,
                            session_id=session_id,
                            time_index=index,
                            global_session_index=index,
                            outcome=_outcome(point.labels, outcome_id),
                            candidate_probability=float(candidate_value),
                            b1_probability=float(b1_value),
                            b2_probability=float(b2_value),
                        )
                    )
            if not rows:
                raise InterimEvaluationRunError(
                    "NO_COMMON_EVALUATION_ROWS", "evaluation"
                )
            common_rows = tuple(rows)
            evaluation = evaluate_common_forecasts(
                common_rows,
                CandidateSelectionContext.SELECTED_FROM_MULTIPLE_CANDIDATES,
            )
            body = {
                "headId": head_id.value,
                "outcomeId": outcome_id.value,
                "foldId": fold.fold_id,
                "phase": fold.phase,
                "selectionContext": (
                    CandidateSelectionContext.SELECTED_FROM_MULTIPLE_CANDIDATES.value
                ),
                "evaluationKey": _json_value(evaluation_key),
                "trainingWindow": [fold.train_start, fold.train_stop],
                "evaluationWindow": [
                    fold.evaluation_start,
                    fold.evaluation_stop,
                ],
                "commonMaskRowCount": len(common_rows),
                "commonMaskSha256": _sha256(
                    canonical_json_bytes([row.row_id for row in common_rows])
                ),
                "metrics": {
                    "candidate": _json_value(evaluation.candidate),
                    "b1": _json_value(evaluation.b1),
                    "b2": _json_value(evaluation.b2),
                    "comparison": _json_value(evaluation.comparison),
                    "temporalIdentification": _json_value(
                        evaluation.temporal_identification
                    ),
                    "calibrationBinCount": len(
                        evaluation.candidate.calibration.bins
                    ),
                },
                "bootstrap": _json_value(evaluation.bootstrap),
            }
            bundles.append(
                _EvaluationBundle(
                    head_id=head_id,
                    outcome_id=outcome_id,
                    fold=fold,
                    rows=common_rows,
                    body=body,
                )
            )
    return tuple(bundles), mapping_abstentions


def _cost_scenarios(merc: Mapping[str, object]) -> tuple[tuple[str, CostScenario], ...]:
    cost_contract = _mapping(merc.get("costContract"), "FROZEN_CONTRACT_INVALID")
    values = cost_contract.get("scenarios")
    if not isinstance(values, list) or len(values) != 2:
        raise InterimEvaluationRunError(
            "FROZEN_CONTRACT_INVALID", "evaluation"
        )
    scenarios: list[tuple[str, CostScenario]] = []
    for value in values:
        scenario = _mapping(value, "FROZEN_CONTRACT_INVALID")
        components = _mapping(
            scenario.get("components"), "FROZEN_CONTRACT_INVALID"
        )
        try:
            cost = CostScenario(
                fees_bps=float(components["fees_bps"]),
                fx_bps=float(components["fx_bps"]),
                slippage_bps=float(components["slippage_bps"]),
                market_impact_bps=float(components["market_impact_bps"]),
                tax_bps=float(components["tax_bps"]),
                borrow_hedge_bps=float(components["borrow_hedge_bps"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise InterimEvaluationRunError(
                "FROZEN_CONTRACT_INVALID", "evaluation"
            ) from error
        if cost.total_bps != float(scenario.get("expectedTotalBps", -1.0)):
            raise InterimEvaluationRunError(
                "FROZEN_CONTRACT_INVALID", "evaluation"
            )
        scenario_id = scenario.get("scenarioId")
        if not isinstance(scenario_id, str):
            raise InterimEvaluationRunError(
                "FROZEN_CONTRACT_INVALID", "evaluation"
            )
        scenarios.append((scenario_id, cost))
    return tuple(scenarios)


def _candidate_trades(
    bundles: Sequence[_EvaluationBundle],
    series_values: Sequence[_PreparedSeries],
) -> tuple[tuple[CandidateHeadId, HypotheticalTrade], int]:
    series_by_symbol = {value.symbol: value for value in series_values}
    candidates: list[tuple[CandidateHeadId, HypotheticalTrade]] = []
    for bundle in bundles:
        direction = (
            TradeDirection.LONG
            if bundle.outcome_id is OutcomeId.UPSIDE_CONTINUATION
            else TradeDirection.DOWNSIDE_SHORT
        )
        for row in bundle.rows:
            if row.candidate_probability < 0.5:
                continue
            series = series_by_symbol[row.series_id]
            entry_index = row.time_index + 1
            exit_index = row.time_index + 10
            if exit_index >= len(series.observations):
                continue
            entry_close = float(
                series.observations[entry_index].adjusted_close
            )
            exit_close = float(series.observations[exit_index].adjusted_close)
            gross_return = (
                exit_close / entry_close - 1.0
                if direction is TradeDirection.LONG
                else 1.0 - exit_close / entry_close
            )
            candidates.append(
                (
                    bundle.head_id,
                    HypotheticalTrade(
                        series_id=row.series_id,
                        entry_session_id=str(
                            series.observations[entry_index].session_id
                        ),
                        exit_session_id=str(
                            series.observations[exit_index].session_id
                        ),
                        entry_index=entry_index,
                        exit_index=exit_index,
                        gross_simple_return=gross_return,
                        direction=direction,
                    ),
                )
            )
    accepted: list[tuple[CandidateHeadId, HypotheticalTrade]] = []
    last_exit: dict[tuple[CandidateHeadId, str], int] = {}
    suppressed = 0
    for head_id, trade in sorted(
        candidates,
        key=lambda pair: (
            pair[0].value,
            pair[1].series_id,
            pair[1].entry_index,
            pair[1].exit_index,
        ),
    ):
        key = (head_id, trade.series_id)
        if trade.entry_index <= last_exit.get(key, -1):
            suppressed += 1
            continue
        accepted.append((head_id, trade))
        last_exit[key] = trade.exit_index
    return tuple(accepted), suppressed


def _evaluate_economics(
    bundles: Sequence[_EvaluationBundle],
    series_values: Sequence[_PreparedSeries],
    merc: Mapping[str, object],
) -> Mapping[str, object]:
    trades, overlap_suppressed = _candidate_trades(bundles, series_values)
    grouped: dict[tuple[str, str], list[HypotheticalTrade]] = defaultdict(list)
    for head_id, trade in trades:
        grouped[(head_id.value, trade.series_id)].append(trade)
    scenario_bodies: list[dict[str, object]] = []
    for scenario_id, scenario in _cost_scenarios(merc):
        head_series_results: list[dict[str, object]] = []
        for (head_id, series_id), values in sorted(grouped.items()):
            evaluation = evaluate_hypothetical_trades(
                values,
                scenario,
                short_execution_evidence=ShortExecutionEvidence.NOT_AVAILABLE,
                minimum_tail_observations=20,
            )
            head_series_results.append(
                {
                    "headId": head_id,
                    "seriesId": series_id,
                    "evaluation": _json_value(evaluation),
                }
            )
        scenario_bodies.append(
            {
                "scenarioId": scenario_id,
                "components": _json_value(scenario),
                "totalBps": scenario.total_bps,
                "headSeriesResults": head_series_results,
            }
        )
    return {
        "costScenarios": scenario_bodies,
        "minimumTailObservations": 20,
        "acceptedHypotheticalTradeCount": len(trades),
        "overlapSuppressedTradeCount": overlap_suppressed,
        "overlapPolicy": (
            "one_position_at_a_time_per_series_closed_intervals"
        ),
        "downsideShortEconomics": (
            "not_identifiable_without_borrow_and_execution_data"
        ),
        "multiSymbolPortfolioEconomics": (
            "not_identifiable_without_portfolio_weights_and_common_calendar"
        ),
    }


def _camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            _camel_case(field.name): _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(nested) for nested in value]
    return value


def _result_body(
    arguments: InterimEvaluationRunArguments,
    verified: _VerifiedInputs,
    prepared: _PreparedDataset,
    bundles: Sequence[_EvaluationBundle],
    economics: Mapping[str, object],
    counts: Mapping[str, object],
    timestamp: str,
) -> Mapping[str, object]:
    plan = prepared.validation_plan
    return {
        "schemaVersion": "rp001-interim-evaluation-result.v1",
        "programId": _PROGRAM_ID,
        "goalVersion": _GOAL_VERSION,
        "studyId": "ST-BEH-001",
        "runId": arguments.run_id,
        "status": "completed",
        "createdAt": timestamp,
        "usageScope": _USAGE_SCOPE,
        "operationalDisposition": _OPERATIONAL_DISPOSITION,
        "sampleRole": _SAMPLE_ROLE,
        "symbols": list(_EXPECTED_SYMBOLS),
        "period": {
            "startDate": _START_DATE,
            "endDate": _END_DATE,
            "interval": _INTERVAL,
            "timezone": _TIMEZONE,
        },
        "estimand": {
            "estimandId": "onset_forecast",
            "primaryHorizonSessions": 10,
            "secondaryHorizons": [],
        },
        "validation": {
            "minimumTrainingSessions": 252,
            "validationSessions": 63,
            "purgeSessions": 10,
            "embargoSessions": 10,
            "terminalHoldoutSessions": 126,
            "minimumOofFolds": 3,
            "developmentFoldCount": len(plan.folds),
            "terminalMappingFitCount": plan.terminal_mapping_fit_count,
            "evaluationCount": len(bundles),
            "sameEligibleRowMaskRequired": True,
        },
        "evaluations": [dict(bundle.body) for bundle in bundles],
        "multipleComparisons": {
            "candidateFamilySize": 4,
            "selectionContext": "selected_from_multiple_candidates",
            "supportWithoutSeparateFamilywiseAdjustment": False,
            "unadjusted95PercentIntervals": "descriptive_only",
        },
        "economics": dict(economics),
        "counts": dict(counts),
        "leakageEvidence": {
            "rowOrderFeatureWindowIntegrity": "verified",
            "featureWindowIndexBoundary": "indices_at_or_before_t_only",
            "futureRowsUsage": "labels_only",
            "sourceVintagePointInTime": "not_identifiable",
            "providerPublicationTimestamp": "not_documented",
            "providerRevisionPolicy": "not_documented",
            "confirmatoryAdoptionPointInTimeGate": "not_identifiable",
            "metricsEvidenceClass": "research_only_price_volume_proxy",
            "sourceWindowCheckCount": counts["sourceWindowCheckCount"],
            "sourceWindowMismatchCount": counts["sourceWindowMismatchCount"],
            "featureAvailabilityCheckCount": counts[
                "featureAvailabilityCheckCount"
            ],
            "featureAvailabilityViolationCount": counts[
                "featureAvailabilityViolationCount"
            ],
            "futureLabelRowCheckCount": counts[
                "futureLabelRowCheckCount"
            ],
            "futureLabelRowsExcludedFromFeatures": True,
            "providerSessionMembership": "not_documented",
            "declaredSignalTiming": (
                "official_daily_close_usable_next_session"
            ),
            "sourceWindowManifestSha256": (
                prepared.source_window_manifest_sha256
            ),
        },
        "identificationLimits": dict(
            _mapping(
                verified.merc.get("identificationLimits"),
                "FROZEN_CONTRACT_INVALID",
            )
        ),
        "postResultTuning": "forbidden_not_performed",
    }


def _input_bindings(
    arguments: InterimEvaluationRunArguments,
    verified: _VerifiedInputs,
) -> Mapping[str, object]:
    return {
        "processedCandles": {
            "path": arguments.processed_candles_path.as_posix(),
            "sha256": arguments.processed_candles_sha256,
        },
        "rawCandles": {
            "path": verified.raw_path.relative_to(
                arguments.repository_root.resolve()
            ).as_posix(),
            "sha256": verified.raw_sha256,
        },
        "selectedSampleFreeze": {
            "path": arguments.sample_freeze_path.as_posix(),
            "sha256": arguments.sample_freeze_sha256,
        },
        "mercFreeze": {
            "path": arguments.merc_freeze_path.as_posix(),
            "sha256": arguments.merc_freeze_sha256,
        },
    }


def _trial_body(
    arguments: InterimEvaluationRunArguments,
    verified: _VerifiedInputs,
    prepared: _PreparedDataset,
    bundles: Sequence[_EvaluationBundle],
    counts: Mapping[str, object],
    timestamp: str,
) -> Mapping[str, object]:
    return {
        "schemaVersion": "rp001-interim-evaluation-trial.v1",
        "programId": _PROGRAM_ID,
        "studyId": "ST-BEH-001",
        "protocolId": "SP-003-PV10-v1",
        "protocolVersion": "1.0.1",
        "runId": arguments.run_id,
        "status": "completed",
        "completedAt": timestamp,
        "frozenInputs": dict(_input_bindings(arguments, verified)),
        "symbols": list(_EXPECTED_SYMBOLS),
        "sessionCount": len(prepared.series[0].observations),
        "headIds": [value.value for value in _HEAD_OUTCOMES],
        "evaluationCount": len(bundles),
        "counts": dict(counts),
        "usageScope": _USAGE_SCOPE,
        "operationalDisposition": _OPERATIONAL_DISPOSITION,
        "postResultTuning": "forbidden_not_performed",
    }


def _publish_success_artifacts(
    arguments: InterimEvaluationRunArguments,
    repository_root: Path,
    verified: _VerifiedInputs,
    result: Mapping[str, object],
    trial: Mapping[str, object],
    timestamp: str,
) -> tuple[tuple[str, LocalArtifactBinding], ...]:
    run_directory = _run_directory(arguments, repository_root)
    store = LocalArtifactStore(repository_root)
    published: list[LocalArtifactBinding] = []
    try:
        result_binding = store.publish_json(
            run_directory / "result.json", result
        )
        published.append(result_binding)
        trial_binding = store.publish_json(run_directory / "trial.json", trial)
        published.append(trial_binding)
        manifest = {
            "schemaVersion": "rp001-interim-evaluation-manifest.v1",
            "programId": _PROGRAM_ID,
            "runId": arguments.run_id,
            "status": "succeeded",
            "createdAt": timestamp,
            "usageScope": _USAGE_SCOPE,
            "operationalDisposition": _OPERATIONAL_DISPOSITION,
            "frozenInputs": dict(_input_bindings(arguments, verified)),
            "publishedArtifactCount": 2,
            "publishedArtifacts": [
                {
                    "role": role,
                    "path": binding.path.relative_to(repository_root).as_posix(),
                    "sha256": binding.artifact_sha256,
                }
                for role, binding in (
                    ("result", result_binding),
                    ("trial", trial_binding),
                )
            ],
            "postResultTuning": "forbidden_not_performed",
        }
        manifest_binding = store.publish_json(
            run_directory / "manifest.json", manifest
        )
        published.append(manifest_binding)
    except (LocalEvidenceError, OSError):
        for binding in reversed(published):
            try:
                store.rollback_publication(binding)
            except LocalEvidenceError:
                pass
        raise InterimEvaluationRunError(
            "EVIDENCE_PUBLICATION_FAILED", "evidence"
        ) from None
    return (
        ("result", result_binding),
        ("trial", trial_binding),
        ("manifest", manifest_binding),
    )


def _append_success_event_or_rollback(
    *,
    arguments: InterimEvaluationRunArguments,
    repository_root: Path,
    prepared: _PreparedDataset,
    bundles: Sequence[_EvaluationBundle],
    bindings: tuple[tuple[str, LocalArtifactBinding], ...],
    timestamp: str,
    ledger_factory: LedgerFactory,
) -> None:
    ledger_directory = _resolve_relative(
        repository_root,
        arguments.ledger_directory,
        "LEDGER_PATH_INVALID",
    )
    try:
        ledger_factory(ledger_directory).append(
            "rp001_interim_evaluation_completed",
            {
                "runId": arguments.run_id,
                "status": "succeeded",
                "symbolCount": len(prepared.series),
                "sessionCount": len(prepared.series[0].observations),
                "evaluationCount": len(bundles),
                "processedCandlesSha256": (
                    arguments.processed_candles_sha256
                ),
                "selectedSampleFreezeSha256": (
                    arguments.sample_freeze_sha256
                ),
                "mercFreezeSha256": arguments.merc_freeze_sha256,
                "artifacts": [
                    {
                        "role": role,
                        "path": binding.path.relative_to(
                            repository_root
                        ).as_posix(),
                        "sha256": binding.artifact_sha256,
                    }
                    for role, binding in bindings
                ],
                "usageScope": _USAGE_SCOPE,
                "operationalDisposition": _OPERATIONAL_DISPOSITION,
            },
            timestamp,
        )
    except Exception:
        _rollback_success_artifacts(bindings, repository_root)
        raise InterimEvaluationRunError(
            "LEDGER_APPEND_FAILED", "evidence"
        ) from None


def _rollback_success_artifacts(
    bindings: Sequence[tuple[str, LocalArtifactBinding]],
    repository_root: Path,
) -> None:
    store = LocalArtifactStore(repository_root)
    rollback_failed = False
    for _role, binding in reversed(tuple(bindings)):
        try:
            store.rollback_publication(binding)
        except LocalEvidenceError:
            rollback_failed = True
    if rollback_failed:
        raise InterimEvaluationRunError(
            "EVIDENCE_ROLLBACK_FAILED", "evidence"
        )


def _publish_failure_without_masking(
    arguments: InterimEvaluationRunArguments,
    error: InterimEvaluationRunError,
    clock: Clock,
    ledger_factory: LedgerFactory,
) -> None:
    try:
        root = _repository_root(arguments.repository_root)
        run_directory = _run_directory(arguments, root)
        retained_roles = _retained_success_artifact_roles(run_directory)
        if error.code == "EVIDENCE_ROLLBACK_FAILED" and retained_roles:
            _publish_terminal_invalidation(
                arguments=arguments,
                root=root,
                run_directory=run_directory,
                error=error,
                invalidated_at=_timestamp(clock),
                retained_roles=retained_roles,
                ledger_factory=ledger_factory,
            )
            return
        store = LocalArtifactStore(root)
        failure = {
            "schemaVersion": "rp001-interim-evaluation-failure.v1",
            "programId": _PROGRAM_ID,
            "runId": arguments.run_id,
            "status": "failed",
            "errorCode": error.code,
            "stage": error.stage,
            "failedAt": _timestamp(clock),
            "counts": {
                "failureCount": 1,
                "invalidRowCount": error.invalid_row_count,
            },
            "frozenInputs": {
                "processedCandles": {
                    "path": arguments.processed_candles_path.as_posix(),
                    "sha256": arguments.processed_candles_sha256,
                },
                "selectedSampleFreeze": {
                    "path": arguments.sample_freeze_path.as_posix(),
                    "sha256": arguments.sample_freeze_sha256,
                },
                "mercFreeze": {
                    "path": arguments.merc_freeze_path.as_posix(),
                    "sha256": arguments.merc_freeze_sha256,
                },
            },
            "usageScope": _USAGE_SCOPE,
            "operationalDisposition": _OPERATIONAL_DISPOSITION,
            "postResultTuning": "forbidden_not_performed",
        }
        binding = store.publish_json(run_directory / "failure.json", failure)
        ledger = ledger_factory(
            _resolve_relative(
                root, arguments.ledger_directory, "LEDGER_PATH_INVALID"
            )
        )
        ledger.append(
            "rp001_interim_evaluation_failed",
            {
                "runId": arguments.run_id,
                "status": "failed",
                "errorCode": error.code,
                "failureArtifact": {
                    "path": binding.path.relative_to(root).as_posix(),
                    "sha256": binding.artifact_sha256,
                },
                "usageScope": _USAGE_SCOPE,
                "operationalDisposition": _OPERATIONAL_DISPOSITION,
            },
            _timestamp(clock),
        )
    except Exception:
        return


def _retained_success_artifact_roles(
    run_directory: Path,
) -> tuple[str, ...]:
    return tuple(
        role
        for role in _SUCCESS_ARTIFACT_ROLES
        if _path_is_occupied(run_directory / f"{role}.json")
        or _path_is_occupied(run_directory / f"{role}.json.sha256")
    )


def _path_is_occupied(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _publish_terminal_invalidation(
    *,
    arguments: InterimEvaluationRunArguments,
    root: Path,
    run_directory: Path,
    error: InterimEvaluationRunError,
    invalidated_at: str,
    retained_roles: Sequence[str],
    ledger_factory: LedgerFactory,
) -> None:
    marker = {
        "schemaVersion": "rp001-interim-evaluation-invalidation.v1",
        "programId": _PROGRAM_ID,
        "runId": arguments.run_id,
        "status": "invalidated",
        "errorCode": error.code,
        "stage": error.stage,
        "invalidatedAt": invalidated_at,
        "terminalAuthority": (
            "terminal_invalidation_supersedes_success_artifacts"
        ),
        "retainedSuccessArtifactsAuthoritative": False,
        "invalidatedArtifactRoles": list(retained_roles),
        "failureArtifactPublished": False,
        "usageScope": _USAGE_SCOPE,
        "operationalDisposition": _OPERATIONAL_DISPOSITION,
        "postResultTuning": "forbidden_not_performed",
    }
    binding = LocalArtifactStore(root).publish_json(
        run_directory / "terminal-invalidation.json", marker
    )
    try:
        ledger_factory(
            _resolve_relative(
                root, arguments.ledger_directory, "LEDGER_PATH_INVALID"
            )
        ).append(
            "rp001_interim_evaluation_invalidated",
            {
                "runId": arguments.run_id,
                "status": "invalidated",
                "errorCode": error.code,
                "terminalAuthorityArtifact": {
                    "path": binding.path.relative_to(root).as_posix(),
                    "sha256": binding.artifact_sha256,
                },
                "retainedSuccessArtifactsAuthoritative": False,
                "invalidatedArtifactRoles": list(retained_roles),
                "usageScope": _USAGE_SCOPE,
                "operationalDisposition": _OPERATIONAL_DISPOSITION,
            },
            invalidated_at,
        )
    except Exception:
        return
