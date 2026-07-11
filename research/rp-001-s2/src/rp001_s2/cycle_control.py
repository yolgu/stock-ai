"""Minimal executable state transitions for RP-001-S2 discovery cycles."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def decide_development_cycle(result: Mapping[str, object]) -> dict[str, object]:
    """Convert one completed development screen into the next permitted state."""
    cycle_id = _required_text(result, "cycleId")
    run_id = _required_text(result, "runId")
    passed_families = _text_sequence(result.get("passedFamilies"))
    family_metrics = _mapping_sequence(result.get("familyMetrics"))
    failure_diagnoses = _mapping_sequence(result.get("failureDiagnosis"))
    confirmation_authorized = result.get("confirmationAuthorized")
    confirmation_opened = result.get("confirmationPriceVolumeOpened")
    if (
        type(confirmation_authorized) is not bool
        or confirmation_authorized != bool(passed_families)
        or confirmation_opened is not False
        or not family_metrics
        or len(family_metrics) != len(failure_diagnoses)
    ):
        raise ValueError("development_result_inconsistent")

    metric_by_family = _unique_by_family(family_metrics)
    diagnosis_by_family = _unique_by_family(failure_diagnoses)
    if set(metric_by_family) != set(diagnosis_by_family):
        raise ValueError("development_result_inconsistent")
    passed_set = set(passed_families)
    if not passed_set <= set(metric_by_family):
        raise ValueError("development_result_inconsistent")

    candidate_decisions: list[dict[str, object]] = []
    for metric in family_metrics:
        family_id = _required_text(metric, "familyId")
        diagnosis = diagnosis_by_family[family_id]
        gate_passed = metric.get("developmentGate") == "pass"
        diagnosis_passed = diagnosis.get("status") == "pass"
        if gate_passed != diagnosis_passed or gate_passed != (family_id in passed_set):
            raise ValueError("development_result_inconsistent")
        candidate_decisions.append(
            {
                "familyId": family_id,
                "claimLevel": "price_volume_regime_proxy_only",
                "disposition": _candidate_disposition(metric, gate_passed),
                "reasons": list(_text_sequence(diagnosis.get("reasons"))),
            }
        )

    screen_passed = bool(passed_families)
    return {
        "cycleId": cycle_id,
        "developmentRunId": run_id,
        "cycleStatus": "DevelopmentScreenPassed" if screen_passed else "CycleTerminal",
        "nextState": "FREEZE_CONFIRMATION" if screen_passed else "NEXT_CYCLE",
        "programTerminal": False,
        "confirmationAuthorized": screen_passed,
        "confirmationPriceVolumeOpened": False,
        "candidateDecisions": candidate_decisions,
        "operationalDisposition": "NoTrade/no integration",
        "ordersAccountsAssetsAccessed": False,
    }


def _candidate_disposition(metric: Mapping[str, object], gate_passed: bool) -> str:
    if gate_passed:
        return "retain_for_confirmation_freeze"
    candidate = _finite_number(metric.get("candidateBrier"))
    baseline_b1 = _finite_number(metric.get("baselineB1Brier"))
    baseline_b2 = _finite_number(metric.get("baselineB2Brier"))
    if candidate >= min(baseline_b1, baseline_b2):
        return "reject_current_version"
    return "repair_as_new_formula_version"


def _unique_by_family(
    values: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for value in values:
        family_id = _required_text(value, "familyId")
        if family_id in indexed:
            raise ValueError("development_result_inconsistent")
        indexed[family_id] = value
    return indexed


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError("development_result_inconsistent")
    return result


def _text_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("development_result_inconsistent")
    return tuple(value)


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("development_result_inconsistent")
    return tuple(value)


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("development_result_inconsistent")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("development_result_inconsistent")
    return result
