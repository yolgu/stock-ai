"""Execute and publish the RP-001-S2 Cycle 002 development screen."""

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
from pathlib import Path

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
)
from rp001_s2.cycle002 import (
    Cycle002Abstention,
    Cycle002Features,
    IneligibleRegimeEndLabel,
    RegimeEndLabel,
    build_cycle002_features,
    hypothetical_avoided_continuation_loss,
    label_upside_regime_end,
)
from rp001_s2.cycle002_evaluation import (
    Cycle002DevelopmentEvaluation,
    Cycle002Example,
    Cycle002PredictionRow,
    run_cycle002_purged_oof,
)
from rp001_s2.cycle_control import decide_development_cycle
from rp001_s2.development_run import _convert_processed
from rp001_s2.evaluation import MaxTInference, brier_score, synchronized_block_max_t


_PROGRAM_ID = "RP-001-S2"
_CYCLE_ID = "RP-001-S2-CYCLE-002"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTRACT_PATH = Path(
    "research/rp-001-s2/contracts/cycle-002-development-contract-v1.json"
)


class Cycle002RunError(ValueError):
    """Sanitized Cycle 002 run failure."""


@dataclass(frozen=True)
class Cycle002RunArguments:
    repository_root: Path
    contract_path: Path
    contract_sha256: str
    run_id: str


@dataclass(frozen=True)
class Cycle002RunSummary:
    run_id: str
    status: str
    input_row_count: int
    eligible_row_count: int
    positive_outcome_count: int
    completed_family_count: int
    passed_family_count: int
    next_state: str
    manifest_sha256: str
    decision_sha256: str
    ledger_sha256: str


def run_cycle002_evaluation(
    arguments: Cycle002RunArguments,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Cycle002RunSummary:
    """Verify the freeze, run the exposed development OOF, and publish evidence."""
    root = arguments.repository_root.absolute()
    contract = _verify_contract(root, arguments)
    if not _RUN_ID.fullmatch(arguments.run_id):
        raise Cycle002RunError("run_id_invalid")
    processed_path = root / str(contract["processedCandles"]["path"])
    processed = json.loads(processed_path.read_text(encoding="utf-8"))
    observations, adjusted_prices, session_count = _convert_processed(processed)
    examples, preparation = _prepare_examples(observations)
    evaluation = run_cycle002_purged_oof(examples, session_count=session_count)
    inference = synchronized_block_max_t(evaluation.predictions)  # type: ignore[arg-type]
    family_metrics = _family_metrics(evaluation, inference)
    economics = _economic_metrics(evaluation, examples, adjusted_prices)
    passed = tuple(
        str(value["familyId"])
        for value in family_metrics
        if value["developmentGate"] == "pass"
    )
    diagnoses = _failure_diagnosis(family_metrics)
    return _publish(
        arguments,
        contract,
        evaluation,
        inference,
        preparation,
        family_metrics,
        economics,
        passed,
        diagnoses,
        root,
        clock,
    )


def _verify_contract(
    root: Path,
    arguments: Cycle002RunArguments,
) -> Mapping[str, object]:
    if not _SHA256.fullmatch(arguments.contract_sha256):
        raise Cycle002RunError("contract_sha256_invalid")
    path = (
        arguments.contract_path
        if arguments.contract_path.is_absolute()
        else root / arguments.contract_path
    )
    if path.absolute() != root / _CONTRACT_PATH:
        raise Cycle002RunError("contract_path_not_canonical")
    try:
        source = path.read_bytes()
        sidecar = Path(f"{path}.sha256").read_text(encoding="ascii")
        value = json.loads(source.decode("utf-8"))
    except Exception:
        raise Cycle002RunError("contract_invalid") from None
    if (
        sha256_bytes(source) != arguments.contract_sha256
        or sidecar != f"{arguments.contract_sha256}\n"
        or not isinstance(value, dict)
        or canonical_json_bytes(value) != source
        or value.get("schemaVersion")
        != "rp001-s2-cycle-002-development-contract.v1"
        or value.get("cycleId") != _CYCLE_ID
        or value.get("status")
        != "development_authorized_confirmation_price_unopened"
        or value.get("previousCycleResultInformedDesign") is not True
        or value.get("confirmationPriceVolumeOpened") is not False
    ):
        raise Cycle002RunError("contract_invalid")
    bindings = value.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise Cycle002RunError("contract_invalid")
    for binding in bindings.values():
        _verify_binding(root, binding)
    processed = value.get("processedCandles")
    if not isinstance(processed, dict):
        raise Cycle002RunError("contract_invalid")
    _verify_binding(root, processed)
    if not _has_freeze_event(root, arguments.contract_sha256):
        raise Cycle002RunError("freeze_event_invalid")
    return value


def _verify_binding(root: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise Cycle002RunError("binding_invalid")
    relative = value.get("path")
    expected = value.get("sha256")
    if (
        not isinstance(relative, str)
        or not isinstance(expected, str)
        or not _SHA256.fullmatch(expected)
    ):
        raise Cycle002RunError("binding_invalid")
    try:
        path = root / relative
        path.relative_to(root)
        if sha256_bytes(path.read_bytes()) != expected:
            raise Cycle002RunError("binding_invalid")
        sidecar = Path(f"{path}.sha256")
        if sidecar.exists() and sidecar.read_text(encoding="ascii") != f"{expected}\n":
            raise Cycle002RunError("binding_invalid")
    except (OSError, ValueError, UnicodeError):
        raise Cycle002RunError("binding_invalid") from None


def _has_freeze_event(root: Path, contract_sha256: str) -> bool:
    events = root / "research/rp-001-s2/local-ledgers/program/events"
    expected = {"path": _CONTRACT_PATH.as_posix(), "sha256": contract_sha256}
    for path in sorted(events.glob("*.json")):
        event = json.loads(path.read_text(encoding="utf-8"))
        if (
            event.get("eventType") == "rp001_s2_cycle_002_development_frozen"
            and event.get("payload", {}).get("contract") == expected
        ):
            return True
    return False


def _prepare_examples(
    observations: Mapping[str, tuple[object, ...]],
) -> tuple[tuple[Cycle002Example, ...], dict[str, object]]:
    examples: list[Cycle002Example] = []
    abstentions: Counter[str] = Counter()
    ineligible: Counter[str] = Counter()
    for symbol, untyped_rows in observations.items():
        rows = untyped_rows
        for index in range(len(rows)):
            features = build_cycle002_features(rows, index)  # type: ignore[arg-type]
            if isinstance(features, Cycle002Abstention):
                abstentions[features.reason] += 1
                continue
            assert isinstance(features, Cycle002Features)
            label = label_upside_regime_end(rows, index, features)  # type: ignore[arg-type]
            if isinstance(label, IneligibleRegimeEndLabel):
                ineligible[label.reason] += 1
                continue
            assert isinstance(label, RegimeEndLabel)
            session_id = str(features.base.signal_session_id)
            examples.append(
                Cycle002Example(
                    row_id=f"{symbol}:{session_id}",
                    symbol=symbol,
                    session_index=index,
                    session_id=session_id,
                    features=features,
                    outcome=label.outcome,
                    end_offset_sessions=label.end_offset_sessions,
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
    evaluation: Cycle002DevelopmentEvaluation,
    inference: MaxTInference,
) -> tuple[dict[str, object], ...]:
    contrasts = dataclasses.asdict(inference)["contrasts"]
    thresholds = {
        value.family_id: value.alarm_threshold for value in evaluation.frozen_models
    }
    results: list[dict[str, object]] = []
    for family in evaluation.family_ids:
        rows = tuple(row for row in evaluation.predictions if row.family_id == family)
        outcomes = tuple(row.outcome for row in rows)
        candidate = tuple(row.candidate_probability for row in rows)
        baseline_b1 = tuple(row.baseline_constant_probability for row in rows)
        baseline_b2 = tuple(row.baseline_trend_probability for row in rows)
        family_contrasts = tuple(
            value for value in contrasts if value["family_id"] == family
        )
        passed = len(family_contrasts) == 2 and all(
            value["passed_delta_0_005"] for value in family_contrasts
        )
        results.append(
            {
                "familyId": family,
                "rowCount": len(rows),
                "candidateBrier": brier_score(outcomes, candidate),
                "baselineB1Brier": brier_score(outcomes, baseline_b1),
                "baselineB2Brier": brier_score(outcomes, baseline_b2),
                "candidateLogLoss": _log_loss(outcomes, candidate),
                "baselineB1LogLoss": _log_loss(outcomes, baseline_b1),
                "baselineB2LogLoss": _log_loss(outcomes, baseline_b2),
                "candidateCalibrationEce10": _ece(outcomes, candidate),
                "alarmThreshold": thresholds[family],
                "classification": _classification(rows, thresholds[family]),
                "contrasts": family_contrasts,
                "developmentGate": "pass" if passed else "fail",
            }
        )
    return tuple(results)


def _classification(
    rows: Sequence[Cycle002PredictionRow],
    threshold: float | None,
) -> dict[str, object]:
    if threshold is None:
        return {
            "alarmCount": 0,
            "recall": None,
            "falseAlarmRate": None,
            "precision": None,
            "missRate": None,
            "meanEndLeadSessions": None,
        }
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
        "meanEndLeadSessions": (
            statistics.fmean(
                row.end_offset_sessions
                for row in true_positive
                if row.end_offset_sessions is not None
            )
            if true_positive
            else None
        ),
    }


def _economic_metrics(
    evaluation: Cycle002DevelopmentEvaluation,
    examples: Sequence[Cycle002Example],
    adjusted_prices: Mapping[str, tuple[float, ...]],
) -> tuple[dict[str, object], ...]:
    index_by_row = {row.row_id: row.session_index for row in examples}
    thresholds = {
        value.family_id: value.alarm_threshold for value in evaluation.frozen_models
    }
    results: list[dict[str, object]] = []
    for family in evaluation.family_ids:
        threshold = thresholds[family]
        rows = tuple(row for row in evaluation.predictions if row.family_id == family)
        alarms = (
            ()
            if threshold is None
            else tuple(row for row in rows if row.candidate_probability >= threshold)
        )
        events: list[tuple[float, float]] = []
        last_horizon: dict[str, int] = {}
        for row in sorted(alarms, key=lambda value: (value.symbol, index_by_row[value.row_id])):
            index = index_by_row[row.row_id]
            if index <= last_horizon.get(row.symbol, -1) or index + 10 >= len(
                adjusted_prices[row.symbol]
            ):
                continue
            events.append(
                (
                    adjusted_prices[row.symbol][index + 1],
                    adjusted_prices[row.symbol][index + 10],
                )
            )
            last_horizon[row.symbol] = index + 10
        results.append(
            {
                "familyId": family,
                "researchOnly": True,
                "actionProxy": "hypothetical_long_exit_at_next_close",
                "benefitDefinition": "negative_next_close_to_session10_long_return_minus_cost",
                "portfolioMetricsStatus": "not_identifiable_no_capital_allocation",
                "formalG8Status": "not_evaluated_action_execution_impact_contract_absent",
                "scenarios": [
                    _economic_scenario(events, cost_bps) for cost_bps in (100.0, 300.0)
                ],
            }
        )
    return tuple(results)


def _economic_scenario(
    events: Sequence[tuple[float, float]],
    cost_bps: float,
) -> dict[str, object]:
    benefits = tuple(
        hypothetical_avoided_continuation_loss(
            next_close,
            horizon_close,
            cost_bps=cost_bps,
        )
        for next_close, horizon_close in events
    )
    if not benefits:
        return {
            "costBps": cost_bps,
            "eventCount": 0,
            "meanNetAvoidedLoss": None,
            "lossVaR95": None,
            "lossCVaR95": None,
            "status": "not_estimable_zero_events",
        }
    if len(benefits) < 20:
        tail = {
            "lossVaR95": None,
            "lossCVaR95": None,
            "tailStatus": "not_estimable_fewer_than_20_events",
        }
    else:
        fifth = _quantile(benefits, 0.05)
        tail_values = tuple(value for value in benefits if value <= fifth)
        tail = {
            "lossVaR95": max(0.0, -fifth),
            "lossCVaR95": max(0.0, -statistics.fmean(tail_values)),
            "tailStatus": "estimated",
        }
    return {
        "costBps": cost_bps,
        "eventCount": len(benefits),
        "meanNetAvoidedLoss": statistics.fmean(benefits),
        **tail,
        "status": "estimated_research_only",
    }


def _failure_diagnosis(
    family_metrics: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    diagnoses: list[dict[str, object]] = []
    for value in family_metrics:
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
        diagnoses.append(
            {
                "familyId": value["familyId"],
                "status": "pass" if value["developmentGate"] == "pass" else "fail",
                "reasons": reasons,
            }
        )
    return tuple(diagnoses)


def _publish(
    arguments: Cycle002RunArguments,
    contract: Mapping[str, object],
    evaluation: Cycle002DevelopmentEvaluation,
    inference: MaxTInference,
    preparation: Mapping[str, object],
    family_metrics: Sequence[Mapping[str, object]],
    economics: Sequence[Mapping[str, object]],
    passed: tuple[str, ...],
    diagnoses: Sequence[Mapping[str, object]],
    root: Path,
    clock: Callable[[], datetime],
) -> Cycle002RunSummary:
    timestamp = _timestamp(clock)
    run_directory = root / "research/rp-001-s2/evaluation-runs" / arguments.run_id
    store = LocalArtifactStore(root)
    result_body: dict[str, object] = {
        "schemaVersion": "rp001-s2-cycle-002-development-result.v1",
        "programId": _PROGRAM_ID,
        "cycleId": _CYCLE_ID,
        "runId": arguments.run_id,
        "status": "completed",
        "createdAt": timestamp,
        "sampleRole": "seen_development_reused_for_internal_discovery",
        "estimand": "upside_price_regime_end_by_5_nonpositive_at_10",
        "claimLevel": "price_volume_regime_proxy_only",
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
        "formalG8Status": "not_evaluated_action_execution_impact_contract_absent",
        "failureDiagnosis": list(diagnoses),
        "passedFamilies": list(passed),
        "confirmationAuthorized": bool(passed),
        "confirmationPriceVolumeOpened": False,
        "operationalDisposition": "NoTrade/no integration",
        "ordersAccountsAssetsAccessed": False,
    }
    result = store.publish_json(run_directory / "result.json", result_body)
    models = store.publish_json(
        run_directory / "development-models.json",
        {
            "schemaVersion": "rp001-s2-cycle-002-development-models.v1",
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
            "baselineDirectionalCounts": [
                list(value) for value in evaluation.baseline_directional_counts
            ],
            "confirmationFreezeAllowedFamilies": list(passed),
        },
    )
    trial = store.publish_json(
        run_directory / "trial.json",
        {
            "schemaVersion": "rp001-s2-cycle-002-development-trial.v1",
            "programId": _PROGRAM_ID,
            "cycleId": _CYCLE_ID,
            "runId": arguments.run_id,
            "seed": 20260711,
            "candidateFamilyCount": 3,
            "completedFamilyCount": 3,
            "failedFamilyCount": 3 - len(passed),
            "invalidFamilyCount": 0,
            "allAttemptsDisclosed": True,
            "previousCycleResultInformedDesign": True,
            "foldSelectedL2": [list(value) for value in evaluation.fold_selected_l2],
            "failureDiagnosis": list(diagnoses),
            "postCycle002ResultTuning": False,
        },
    )
    manifest = store.publish_json(
        run_directory / "manifest.json",
        {
            "schemaVersion": "rp001-s2-cycle-002-evaluation-manifest.v1",
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
    ledger = AppendOnlyLocalLedger(root / "research/rp-001-s2/local-ledgers/program")
    ledger.append(
        "rp001_s2_cycle_002_development_evaluation_completed",
        {
            "runId": arguments.run_id,
            "passedFamilies": list(passed),
            "manifest": _binding(manifest, root),
            "confirmationPriceVolumeOpened": False,
            "operationalDisposition": "NoTrade/no integration",
        },
        timestamp,
    )
    decision = decide_development_cycle(result_body)
    decision_artifact = store.publish_json(
        root / "research/rp-001-s2/cycle-decisions/cycle-002-decision.json",
        {
            "schemaVersion": "rp001-s2-cycle-decision.v1",
            "programId": _PROGRAM_ID,
            "recordedAt": timestamp,
            **decision,
            "nextCycleId": (
                "RP-001-S2-CYCLE-003" if decision["nextState"] == "NEXT_CYCLE" else None
            ),
            "evidence": {
                "developmentResult": _binding(result, root),
                "developmentManifest": _binding(manifest, root),
            },
        },
    )
    transition = ledger.append(
        "rp001_s2_cycle_002_state_transition",
        {
            "cycleId": _CYCLE_ID,
            "cycleStatus": decision["cycleStatus"],
            "nextState": decision["nextState"],
            "nextCycleId": (
                "RP-001-S2-CYCLE-003" if decision["nextState"] == "NEXT_CYCLE" else None
            ),
            "programTerminal": False,
            "confirmationPriceVolumeOpened": False,
            "decision": _binding(decision_artifact, root),
        },
        timestamp,
    )
    return Cycle002RunSummary(
        run_id=arguments.run_id,
        status="completed",
        input_row_count=int(preparation["inputRowCount"]),
        eligible_row_count=int(preparation["eligibleRowCount"]),
        positive_outcome_count=int(preparation["positiveOutcomeCount"]),
        completed_family_count=3,
        passed_family_count=len(passed),
        next_state=str(decision["nextState"]),
        manifest_sha256=manifest.artifact_sha256,
        decision_sha256=decision_artifact.artifact_sha256,
        ledger_sha256=transition.record_sha256,
    )


def _log_loss(outcomes: Sequence[bool], probabilities: Sequence[float]) -> float:
    return statistics.fmean(
        -(
            float(outcome) * math.log(min(max(probability, 1e-15), 1.0 - 1e-15))
            + (1.0 - float(outcome))
            * math.log(1.0 - min(max(probability, 1e-15), 1.0 - 1e-15))
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
                lower <= probability <= upper
                if index == 9
                else lower <= probability < upper
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
        raise Cycle002RunError("clock_invalid")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
