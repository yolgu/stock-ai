"""Execute and publish RP-001-S2 cycle-001 empirical development evidence."""

from __future__ import annotations

import dataclasses
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.discovery import (
    Abstention,
    DailyObservation,
    IneligibleOnsetLabel,
    OnsetLabel,
    build_forecast_features,
    label_upside_regime_onset,
)
from rp001_s2.evaluation import (
    DevelopmentEvaluation,
    EvaluationExample,
    PredictionRow,
    brier_score,
    run_purged_oof,
    synchronized_block_max_t,
)


_PROGRAM_ID = "RP-001-S2"
_CYCLE_ID = "RP-001-S2-CYCLE-001"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTRACT_PATH = Path(
    "research/rp-001-s2/contracts/development-analysis-contract-v1.0.1.json"
)


class DevelopmentRunError(ValueError):
    """Sanitized development-run failure."""


@dataclass(frozen=True)
class DevelopmentRunArguments:
    repository_root: Path
    contract_path: Path
    contract_sha256: str
    run_id: str


@dataclass(frozen=True)
class DevelopmentRunSummary:
    run_id: str
    status: str
    input_row_count: int
    eligible_row_count: int
    completed_family_count: int
    passed_family_count: int
    manifest_sha256: str
    ledger_sha256: str


def run_development_evaluation(
    arguments: DevelopmentRunArguments,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> DevelopmentRunSummary:
    root = arguments.repository_root.absolute()
    contract = _verify_contract(root, arguments)
    if not _RUN_ID.fullmatch(arguments.run_id):
        raise DevelopmentRunError("run_id_invalid")
    processed_path = root / str(contract["processedCandles"]["path"])
    processed = json.loads(processed_path.read_text())
    observations, adjusted_prices, session_count = _convert_processed(processed)
    examples, preparation = _prepare_examples(observations)
    evaluation = run_purged_oof(examples, session_count=session_count)
    inference = synchronized_block_max_t(evaluation.predictions)
    family_metrics = _family_metrics(evaluation, inference)
    economics = _economic_metrics(
        evaluation,
        examples,
        adjusted_prices,
    )
    passed = tuple(
        value["familyId"]
        for value in family_metrics
        if value["developmentGate"] == "pass"
    )
    failure_diagnosis = _failure_diagnosis(family_metrics, economics)
    return _publish(
        arguments,
        contract,
        evaluation,
        inference,
        examples,
        preparation,
        family_metrics,
        economics,
        passed,
        failure_diagnosis,
        root,
        clock,
    )


def _verify_contract(
    root: Path,
    arguments: DevelopmentRunArguments,
) -> Mapping[str, object]:
    if not _SHA256.fullmatch(arguments.contract_sha256):
        raise DevelopmentRunError("contract_sha256_invalid")
    path = arguments.contract_path if arguments.contract_path.is_absolute() else root / arguments.contract_path
    if path.absolute() != root / _CONTRACT_PATH:
        raise DevelopmentRunError("contract_path_not_canonical")
    try:
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
        value = json.loads(source.decode("utf-8"))
    except Exception:
        raise DevelopmentRunError("contract_invalid") from None
    if (
        sha256_bytes(source) != arguments.contract_sha256
        or sidecar != f"{arguments.contract_sha256}\n"
        or not isinstance(value, dict)
        or canonical_json_bytes(value) != source
        or value.get("schemaVersion") != "rp001-s2-development-analysis-contract.v1.0.1"
        or value.get("status") != "analysis_authorized_confirmation_price_unopened"
        or value.get("postPriceChangeClass") != "complete_frozen_maxT_implementation_before_outcome_open"
        or value.get("postResultTuning") is not False
    ):
        raise DevelopmentRunError("contract_invalid")
    bindings = value.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise DevelopmentRunError("contract_invalid")
    for binding in bindings.values():
        _verify_binding(root, binding)
    processed = value.get("processedCandles")
    if not isinstance(processed, dict):
        raise DevelopmentRunError("contract_invalid")
    _verify_binding(root, processed)
    if not _has_freeze_event(root, arguments.contract_sha256):
        raise DevelopmentRunError("freeze_event_invalid")
    return value


def _verify_binding(root: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise DevelopmentRunError("binding_invalid")
    relative = value.get("path")
    expected = value.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise DevelopmentRunError("binding_invalid")
    try:
        path = root / relative
        path.relative_to(root)
        if sha256_bytes(path.read_bytes()) != expected:
            raise DevelopmentRunError("binding_invalid")
        sidecar = Path(f"{path}.sha256")
        if sidecar.exists() and sidecar.read_text(encoding="ascii") != f"{expected}\n":
            raise DevelopmentRunError("binding_invalid")
    except (OSError, ValueError, UnicodeError):
        raise DevelopmentRunError("binding_invalid") from None


def _has_freeze_event(root: Path, contract_sha256: str) -> bool:
    events = root / "research/rp-001-s2/local-ledgers/program/events"
    for path in sorted(events.glob("*.json")):
        event = json.loads(path.read_text())
        if (
            event.get("eventType") == "rp001_s2_development_analysis_frozen"
            and event.get("payload", {}).get("contract")
            == {"path": _CONTRACT_PATH.as_posix(), "sha256": contract_sha256}
        ):
            return True
    return False


def _convert_processed(
    value: Mapping[str, object],
) -> tuple[
    dict[str, tuple[DailyObservation, ...]],
    dict[str, tuple[float, ...]],
    int,
]:
    symbols = value.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 6:
        raise DevelopmentRunError("processed_schema_invalid")
    observations: dict[str, tuple[DailyObservation, ...]] = {}
    adjusted_prices: dict[str, tuple[float, ...]] = {}
    expected_calendar: tuple[str, ...] | None = None
    for item in symbols:
        if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
            raise DevelopmentRunError("processed_schema_invalid")
        symbol = item["symbol"]
        rows = item.get("analysisRows")
        if not isinstance(rows, list):
            raise DevelopmentRunError("processed_schema_invalid")
        converted: list[DailyObservation] = []
        prices: list[float] = []
        for row in rows:
            if not isinstance(row, dict):
                raise DevelopmentRunError("processed_schema_invalid")
            adjusted = row.get("adjusted")
            native = row.get("native")
            if not isinstance(adjusted, dict) or not isinstance(native, dict):
                raise DevelopmentRunError("processed_schema_invalid")
            adjusted_close = _number(adjusted.get("closePrice"), positive=True)
            native_close = _number(native.get("closePrice"), positive=True)
            native_volume = _number(native.get("volume"), positive=True)
            session = row.get("sessionDate")
            currency = row.get("currency")
            if not isinstance(session, str) or not isinstance(currency, str):
                raise DevelopmentRunError("processed_schema_invalid")
            converted.append(
                DailyObservation(
                    adjusted_close=adjusted_close,
                    native_close=native_close,
                    native_volume=native_volume,
                    currency=currency,
                    series_id=symbol,
                    session_id=session,
                    available_as_of_signal=True,
                )
            )
            prices.append(adjusted_close)
        calendar = tuple(row.session_id or "" for row in converted)
        if expected_calendar is None:
            expected_calendar = calendar
        elif calendar != expected_calendar:
            raise DevelopmentRunError("common_calendar_mismatch")
        observations[symbol] = tuple(converted)
        adjusted_prices[symbol] = tuple(prices)
    if expected_calendar is None or len(expected_calendar) < 607:
        raise DevelopmentRunError("insufficient_sessions")
    return observations, adjusted_prices, len(expected_calendar)


def _number(value: object, *, positive: bool) -> float:
    if not isinstance(value, dict) or value.get("kind") != "json_string" or not isinstance(value.get("text"), str):
        raise DevelopmentRunError("numeric_schema_invalid")
    try:
        decimal = Decimal(value["text"])
        result = float(decimal)
    except (InvalidOperation, OverflowError, ValueError):
        raise DevelopmentRunError("numeric_schema_invalid") from None
    if not decimal.is_finite() or not math.isfinite(result) or (positive and result <= 0.0):
        raise DevelopmentRunError("numeric_schema_invalid")
    return result


def _prepare_examples(
    observations: Mapping[str, tuple[DailyObservation, ...]],
) -> tuple[tuple[EvaluationExample, ...], dict[str, object]]:
    examples: list[EvaluationExample] = []
    abstentions: Counter[str] = Counter()
    ineligible: Counter[str] = Counter()
    for symbol, rows in observations.items():
        for index in range(len(rows)):
            features = build_forecast_features(rows, index)
            if isinstance(features, Abstention):
                abstentions[features.reason.value] += 1
                continue
            label = label_upside_regime_onset(rows, index, features)
            if isinstance(label, IneligibleOnsetLabel):
                ineligible[label.reason] += 1
                continue
            assert isinstance(label, OnsetLabel)
            examples.append(
                EvaluationExample(
                    row_id=f"{symbol}:{rows[index].session_id}",
                    symbol=symbol,
                    session_index=index,
                    session_id=str(rows[index].session_id),
                    features=features,
                    outcome=label.outcome,
                    onset_offset_sessions=label.onset_offset_sessions,
                )
            )
    return tuple(examples), {
        "inputRowCount": sum(len(rows) for rows in observations.values()),
        "eligibleRowCount": len(examples),
        "positiveOutcomeCount": sum(row.outcome for row in examples),
        "featureAbstentions": dict(sorted(abstentions.items())),
        "labelIneligible": dict(sorted(ineligible.items())),
    }


def _family_metrics(
    evaluation: DevelopmentEvaluation,
    inference: object,
) -> tuple[dict[str, object], ...]:
    contrasts = dataclasses.asdict(inference)["contrasts"]
    results: list[dict[str, object]] = []
    thresholds = {value.family_id: value.alarm_threshold for value in evaluation.frozen_models}
    for family in evaluation.family_ids:
        rows = tuple(row for row in evaluation.predictions if row.family_id == family)
        outcomes = tuple(row.outcome for row in rows)
        candidate = tuple(row.candidate_probability for row in rows)
        b1 = tuple(row.baseline_constant_probability for row in rows)
        b2 = tuple(row.baseline_trend_probability for row in rows)
        threshold = thresholds[family]
        classification = _classification(rows, threshold)
        family_contrasts = tuple(value for value in contrasts if value["family_id"] == family)
        passed = len(family_contrasts) == 2 and all(value["passed_delta_0_005"] for value in family_contrasts)
        results.append(
            {
                "familyId": family,
                "rowCount": len(rows),
                "candidateBrier": brier_score(outcomes, candidate),
                "baselineB1Brier": brier_score(outcomes, b1),
                "baselineB2Brier": brier_score(outcomes, b2),
                "candidateLogLoss": _log_loss(outcomes, candidate),
                "baselineB1LogLoss": _log_loss(outcomes, b1),
                "baselineB2LogLoss": _log_loss(outcomes, b2),
                "candidateCalibrationEce10": _ece(outcomes, candidate),
                "alarmThreshold": threshold,
                "classification": classification,
                "contrasts": family_contrasts,
                "developmentGate": "pass" if passed else "fail",
            }
        )
    return tuple(results)


def _classification(rows: Sequence[PredictionRow], threshold: float | None) -> dict[str, object]:
    if threshold is None:
        return {"alarmCount": 0, "recall": None, "falseAlarmRate": None, "precision": None, "missRate": None, "meanOnsetLeadSessions": None}
    alarms = tuple(row for row in rows if row.candidate_probability >= threshold)
    positives = tuple(row for row in rows if row.outcome)
    negatives = tuple(row for row in rows if not row.outcome)
    true_positive = tuple(row for row in alarms if row.outcome)
    false_positive = tuple(row for row in alarms if not row.outcome)
    return {
        "alarmCount": len(alarms),
        "recall": len(true_positive) / len(positives) if positives else None,
        "falseAlarmRate": len(false_positive) / len(negatives) if negatives else None,
        "precision": len(true_positive) / len(alarms) if alarms else None,
        "missRate": 1.0 - len(true_positive) / len(positives) if positives else None,
        "meanOnsetLeadSessions": statistics.fmean(
            row.onset_offset_sessions for row in true_positive if row.onset_offset_sessions is not None
        ) if true_positive else None,
    }


def _economic_metrics(
    evaluation: DevelopmentEvaluation,
    examples: Sequence[EvaluationExample],
    adjusted_prices: Mapping[str, tuple[float, ...]],
) -> tuple[dict[str, object], ...]:
    index_by_row = {row.row_id: row.session_index for row in examples}
    thresholds = {value.family_id: value.alarm_threshold for value in evaluation.frozen_models}
    results: list[dict[str, object]] = []
    for family in evaluation.family_ids:
        threshold = thresholds[family]
        family_rows = tuple(row for row in evaluation.predictions if row.family_id == family)
        alarms = () if threshold is None else tuple(row for row in family_rows if row.candidate_probability >= threshold)
        selected: list[tuple[str, int, float]] = []
        last_exit: dict[str, int] = {}
        for row in sorted(alarms, key=lambda value: (value.symbol, index_by_row[value.row_id])):
            index = index_by_row[row.row_id]
            if index <= last_exit.get(row.symbol, -1) or index + 10 >= len(adjusted_prices[row.symbol]):
                continue
            gross = adjusted_prices[row.symbol][index + 10] / adjusted_prices[row.symbol][index + 1] - 1.0
            selected.append((row.symbol, index, gross))
            last_exit[row.symbol] = index + 10
        scenarios = tuple(
            _scenario_metrics(selected, cost_bps)
            for cost_bps in (100.0, 300.0)
        )
        results.append({"familyId": family, "hypotheticalOnly": True, "scenarios": scenarios})
    return tuple(results)


def _scenario_metrics(
    trades: Sequence[tuple[str, int, float]],
    cost_bps: float,
) -> dict[str, object]:
    if not trades:
        return {"costBps": cost_bps, "tradeCount": 0, "meanNetReturn": None, "cumulativeNetReturn": None, "maximumDrawdown": None, "VaR95": None, "CVaR95": None, "status": "not_estimable_zero_trades"}
    returns = [gross - cost_bps / 10_000.0 for _symbol, _index, gross in trades]
    equity = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity / peak - 1.0)
    tail: dict[str, object]
    if len(returns) < 20:
        tail = {"VaR95": None, "CVaR95": None, "tailStatus": "not_estimable_fewer_than_20_trades"}
    else:
        fifth = _quantile(returns, 0.05)
        tail_values = tuple(value for value in returns if value <= fifth)
        tail = {"VaR95": -fifth, "CVaR95": -statistics.fmean(tail_values), "tailStatus": "estimated"}
    return {
        "costBps": cost_bps,
        "tradeCount": len(returns),
        "turnoverRoundTrips": len(returns),
        "meanNetReturn": statistics.fmean(returns),
        "cumulativeNetReturn": equity - 1.0,
        "maximumDrawdown": maximum_drawdown,
        **tail,
        "status": "estimated",
    }


def _failure_diagnosis(
    family_metrics: Sequence[Mapping[str, object]],
    economics: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    economic_by_family = {str(value["familyId"]): value for value in economics}
    diagnoses: list[dict[str, object]] = []
    for value in family_metrics:
        family = str(value["familyId"])
        reasons: list[str] = []
        candidate = float(value["candidateBrier"])
        best = min(float(value["baselineB1Brier"]), float(value["baselineB2Brier"]))
        if candidate >= best:
            reasons.append("discrimination_not_better_than_best_baseline")
        elif best - candidate <= 0.005:
            reasons.append("brier_improvement_below_delta")
        if value["developmentGate"] != "pass":
            reasons.append("simultaneous_uncertainty_gate_failed")
        classification = value["classification"]
        if isinstance(classification, dict) and classification.get("alarmCount") == 0:
            reasons.append("threshold_zero_alarm")
        stress = economic_by_family[family]["scenarios"][1]
        if stress["status"] == "estimated" and stress["meanNetReturn"] <= 0.0:
            reasons.append("stress_cost_net_utility_nonpositive")
        diagnoses.append({"familyId": family, "status": "pass" if not reasons else "fail", "reasons": reasons})
    return tuple(diagnoses)


def _publish(
    arguments: DevelopmentRunArguments,
    contract: Mapping[str, object],
    evaluation: DevelopmentEvaluation,
    inference: object,
    examples: Sequence[EvaluationExample],
    preparation: Mapping[str, object],
    family_metrics: Sequence[Mapping[str, object]],
    economics: Sequence[Mapping[str, object]],
    passed: tuple[str, ...],
    failure_diagnosis: Sequence[Mapping[str, object]],
    root: Path,
    clock: Callable[[], datetime],
) -> DevelopmentRunSummary:
    timestamp = _timestamp(clock)
    run_directory = root / "research/rp-001-s2/evaluation-runs" / arguments.run_id
    store = LocalArtifactStore(root)
    result = store.publish_json(
        run_directory / "result.json",
        {
            "schemaVersion": "rp001-s2-development-result.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "completed",
            "createdAt": timestamp,
            "sampleRole": "seen_development_after_price_open",
            "estimand": "upside_price_regime_onset_by_5_persistent_at_10",
            "preparation": dict(preparation),
            "validation": {
                "folds": [dataclasses.asdict(value) for value in evaluation.folds],
                "sameEligibleRowMask": True,
                "predictionRowCountPerFamily": len(evaluation.predictions) // 3,
                "foldSelectedL2": [list(value) for value in evaluation.fold_selected_l2],
            },
            "familyMetrics": list(family_metrics),
            "maxTInference": dataclasses.asdict(inference),
            "economics": list(economics),
            "failureDiagnosis": list(failure_diagnosis),
            "passedFamilies": list(passed),
            "confirmationAuthorized": bool(passed),
            "confirmationPriceVolumeOpened": False,
            "operationalDisposition": "NoTrade/no integration",
            "ordersAccountsAssetsAccessed": False,
        },
    )
    models = store.publish_json(
        run_directory / "development-models.json",
        {
            "schemaVersion": "rp001-s2-development-models.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "development_fit_not_confirmation_freeze",
            "models": [
                {
                    "familyId": value.family_id,
                    "selectedL2Penalty": value.selected_l2_penalty,
                    "intercept": value.model.intercept,
                    "nonnegativeWeights": list(value.model.nonnegative_weights),
                    "alarmThreshold": value.alarm_threshold,
                }
                for value in evaluation.frozen_models
            ],
            "baselineConstantProbability": evaluation.baseline_constant_probability,
            "baselineDirectionalCounts": [list(value) for value in evaluation.baseline_directional_counts],
            "confirmationFreezeAllowedFamilies": list(passed),
        },
    )
    trial = store.publish_json(
        run_directory / "trial.json",
        {
            "schemaVersion": "rp001-s2-development-trial.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "seed": 20260711,
            "candidateFamilyCount": 3,
            "completedFamilyCount": 3,
            "failedFamilyCount": 3 - len(passed),
            "invalidFamilyCount": 0,
            "allAttemptsDisclosed": True,
            "foldSelectedL2": [list(value) for value in evaluation.fold_selected_l2],
            "failureDiagnosis": list(failure_diagnosis),
            "postResultTuning": False,
        },
    )
    manifest = store.publish_json(
        run_directory / "manifest.json",
        {
            "schemaVersion": "rp001-s2-development-evaluation-manifest.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "status": "completed",
            "createdAt": timestamp,
            "contractSha256": arguments.contract_sha256,
            "inputProcessedCandles": contract["processedCandles"],
            "artifacts": [_binding(value, root) for value in (result, models, trial)],
        },
    )
    event = AppendOnlyLocalLedger(
        root / "research/rp-001-s2/local-ledgers/program"
    ).append(
        "rp001_s2_development_evaluation_completed",
        {
            "runId": arguments.run_id,
            "passedFamilies": list(passed),
            "manifest": _binding(manifest, root),
            "confirmationPriceVolumeOpened": False,
            "operationalDisposition": "NoTrade/no integration",
        },
        timestamp,
    )
    return DevelopmentRunSummary(
        run_id=arguments.run_id,
        status="completed",
        input_row_count=int(preparation["inputRowCount"]),
        eligible_row_count=int(preparation["eligibleRowCount"]),
        completed_family_count=3,
        passed_family_count=len(passed),
        manifest_sha256=manifest.artifact_sha256,
        ledger_sha256=event.record_sha256,
    )


def _log_loss(outcomes: Sequence[bool], probabilities: Sequence[float]) -> float:
    return statistics.fmean(
        -(
            float(outcome) * math.log(min(max(probability, 1e-15), 1.0 - 1e-15))
            + (1.0 - float(outcome)) * math.log(1.0 - min(max(probability, 1e-15), 1.0 - 1e-15))
        )
        for outcome, probability in zip(outcomes, probabilities, strict=True)
    )


def _ece(outcomes: Sequence[bool], probabilities: Sequence[float]) -> float:
    total = len(outcomes)
    result = 0.0
    for index in range(10):
        lower = index / 10.0
        upper = (index + 1) / 10.0
        members = tuple(
            (outcome, probability)
            for outcome, probability in zip(outcomes, probabilities, strict=True)
            if (
                (lower <= probability <= upper)
                if index == 9
                else (lower <= probability < upper)
            )
        )
        if members:
            result += len(members) / total * abs(
                statistics.fmean(probability for _outcome, probability in members)
                - statistics.fmean(float(outcome) for outcome, _probability in members)
            )
    return result


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _binding(value: LocalArtifactBinding, root: Path) -> dict[str, str]:
    path = value.path.relative_to(root) if value.path.is_absolute() else value.path
    return {"path": path.as_posix(), "sha256": value.artifact_sha256}


def _timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DevelopmentRunError("clock_invalid")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
