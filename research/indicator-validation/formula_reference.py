from __future__ import annotations

import math
from collections.abc import Mapping


def _strict_weighted_score(
    components: Mapping[str, float],
    weights: Mapping[str, float],
) -> float:
    if set(components) != set(weights):
        raise ValueError("Reference components must exactly match registered weights")
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Reference weights must sum to one")
    for identifier, value in components.items():
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"Reference component is outside [0,1]: {identifier}")
    return round(100.0 * sum(components[key] * weights[key] for key in weights), 10)


def documented_chart_fomo(
    *,
    return_impulse: float,
    return_acceleration: float,
    volume_surprise: float,
    range_chase: float,
    vwap_persistence: float,
    pullback_hold: float,
) -> float:
    return _strict_weighted_score(
        {
            "returnImpulse": return_impulse,
            "returnAccel": return_acceleration,
            "volumeSurprise": volume_surprise,
            "rangeChase": range_chase,
            "vwapPersistenceProxy": vwap_persistence,
            "pullbackHold": pullback_hold,
        },
        {
            "returnImpulse": 0.24,
            "returnAccel": 0.16,
            "volumeSurprise": 0.22,
            "rangeChase": 0.16,
            "vwapPersistenceProxy": 0.14,
            "pullbackHold": 0.08,
        },
    )


def documented_chart_panic(
    *,
    down_move_impulse: float,
    volume_surprise: float,
    vwap_down_pressure: float,
    breakdown_cascade: float,
    liquidity_proxy: float,
) -> float:
    return _strict_weighted_score(
        {
            "downMoveImpulse": down_move_impulse,
            "volumeSurprise": volume_surprise,
            "vwapDownPressure": vwap_down_pressure,
            "breakdownCascade": breakdown_cascade,
            "liquidityProxy": liquidity_proxy,
        },
        {
            "downMoveImpulse": 0.30,
            "volumeSurprise": 0.25,
            "vwapDownPressure": 0.20,
            "breakdownCascade": 0.15,
            "liquidityProxy": 0.10,
        },
    )


def documented_potential_ptp(
    *,
    profit_breadth: float,
    profit_gain_mass: float,
    vwap_extension: float,
) -> float:
    return _strict_weighted_score(
        {
            "profitBreadth": profit_breadth,
            "profitGainMass": profit_gain_mass,
            "vwapExtension": vwap_extension,
        },
        {
            "profitBreadth": 0.45,
            "profitGainMass": 0.35,
            "vwapExtension": 0.20,
        },
    )


def production_profit_taking_linear(causes: Mapping[str, float]) -> float:
    required = {
        "profitBurden": 0.35,
        "realizedSellPressure": 0.30,
        "overheadSupplyPressure": 0.25,
        "liquidityImpactRisk": 0.10,
    }
    if set(causes) != set(required):
        raise ValueError("Production cause set is incomplete")
    return float(round(sum(causes[key] * required[key] for key in required)))


def production_profit_taking_actual(causes: Mapping[str, float]) -> float:
    score = production_profit_taking_linear(causes)
    if causes["realizedSellPressure"] >= 70.0 and causes["profitBurden"] >= 55.0:
        score = max(score, 75.0)
    if any(value >= 85.0 for value in causes.values()):
        score = max(score, 65.0)
    return min(max(score, 0.0), 100.0)
