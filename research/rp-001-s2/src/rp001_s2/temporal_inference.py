"""Chronologically valid synchronized block inference for RP-001-S2."""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from datetime import date
from typing import Protocol

from rp001_s2.evaluation import ContrastInference, MaxTInference


class PredictionLike(Protocol):
    family_id: str
    fold_id: str
    row_id: str
    session_id: str
    outcome: bool
    candidate_probability: float
    baseline_constant_probability: float
    baseline_trend_probability: float


def synchronized_calendar_block_max_t(
    rows: Sequence[PredictionLike],
    *,
    seed: int = 20260711,
    replicates: int = 2000,
    block_length_sessions: int = 20,
    delta: float = 0.005,
) -> MaxTInference:
    """Bootstrap synchronized chronological blocks without crossing OOF folds."""
    values = tuple(rows)
    family_ids = tuple(sorted({row.family_id for row in values}))
    if len(family_ids) != 3 or replicates <= 1 or block_length_sessions <= 0:
        raise ValueError("max_t_input_invalid")
    by_family = {
        family: tuple(row for row in values if row.family_id == family)
        for family in family_ids
    }
    reference_keys = _common_mask_keys(by_family[family_ids[0]])
    reference_baselines = _baseline_probabilities(by_family[family_ids[0]])
    if any(
        _common_mask_keys(by_family[family]) != reference_keys
        for family in family_ids[1:]
    ):
        raise ValueError("max_t_common_mask_mismatch")
    if any(
        _baseline_probabilities(by_family[family]) != reference_baselines
        for family in family_ids[1:]
    ):
        raise ValueError("max_t_baseline_mismatch")
    fold_segments = _chronological_fold_segments(by_family[family_ids[0]])
    if not fold_segments or any(
        len(segment) < block_length_sessions for segment in fold_segments
    ):
        raise ValueError("max_t_insufficient_sessions")
    session_keys = tuple(key for segment in fold_segments for key in segment)
    session_differences: dict[
        tuple[str, str],
        dict[tuple[str, str], tuple[float, ...]],
    ] = {}
    observed: dict[tuple[str, str], float] = {}
    for family in family_ids:
        family_rows = by_family[family]
        for baseline_id in ("B1", "B2"):
            grouped: dict[tuple[str, str], list[float]] = {
                key: [] for key in session_keys
            }
            all_values: list[float] = []
            for row in family_rows:
                baseline = (
                    row.baseline_constant_probability
                    if baseline_id == "B1"
                    else row.baseline_trend_probability
                )
                difference = (
                    (float(row.outcome) - baseline) ** 2
                    - (float(row.outcome) - row.candidate_probability) ** 2
                )
                key = (row.fold_id, row.session_id)
                if key not in grouped:
                    raise ValueError("max_t_common_mask_mismatch")
                grouped[key].append(difference)
                all_values.append(difference)
            contrast_key = (family, baseline_id)
            session_differences[contrast_key] = {
                key: tuple(grouped[key]) for key in session_keys
            }
            observed[contrast_key] = statistics.fmean(all_values)

    generator = random.Random(seed)
    replicate_estimates: dict[tuple[str, str], list[float]] = {
        key: [] for key in observed
    }
    for _replicate in range(replicates):
        sampled_keys = tuple(
            key
            for segment in fold_segments
            for key in _sample_segment(
                segment,
                block_length_sessions=block_length_sessions,
                generator=generator,
            )
        )
        for key, grouped in session_differences.items():
            sampled = [
                value
                for session_key in sampled_keys
                for value in grouped[session_key]
            ]
            replicate_estimates[key].append(statistics.fmean(sampled))
    standard_errors = {
        key: statistics.stdev(estimates)
        for key, estimates in replicate_estimates.items()
    }
    usable = tuple(key for key, error in standard_errors.items() if error > 0.0)
    if not usable:
        critical: float | None = None
    else:
        maxima = tuple(
            max(
                (replicate_estimates[key][index] - observed[key])
                / standard_errors[key]
                for key in usable
            )
            for index in range(replicates)
        )
        critical = _type7_quantile(maxima, 0.95)
    contrasts: list[ContrastInference] = []
    for key in sorted(observed):
        error = standard_errors[key]
        lower = (
            None
            if critical is None or error <= 0.0
            else observed[key] - critical * error
        )
        contrasts.append(
            ContrastInference(
                family_id=key[0],
                baseline_id=key[1],
                brier_improvement=observed[key],
                bootstrap_standard_error=error if error > 0.0 else None,
                simultaneous_lower_bound_95=lower,
                passed_delta_0_005=lower is not None and lower > delta,
            )
        )
    return MaxTInference(
        method=(
            "synchronized_fold_segmented_chronological_moving_session_blocks_"
            "studentized_maxT"
        ),
        seed=seed,
        replicates=replicates,
        block_length_sessions=block_length_sessions,
        simultaneous_critical_value=critical,
        contrasts=tuple(contrasts),
    )


def _common_mask_keys(rows: Sequence[PredictionLike]) -> tuple[tuple[str, str, str, bool], ...]:
    keys = tuple(
        sorted(
            (row.fold_id, row.session_id, row.row_id, row.outcome)
            for row in rows
        )
    )
    if len(keys) != len(set(keys)):
        raise ValueError("max_t_common_mask_mismatch")
    return keys


def _baseline_probabilities(
    rows: Sequence[PredictionLike],
) -> tuple[tuple[str, str, str, bool, float, float], ...]:
    return tuple(
        sorted(
            (
                row.fold_id,
                row.session_id,
                row.row_id,
                row.outcome,
                row.baseline_constant_probability,
                row.baseline_trend_probability,
            )
            for row in rows
        )
    )


def _chronological_fold_segments(
    rows: Sequence[PredictionLike],
) -> tuple[tuple[tuple[str, str], ...], ...]:
    fold_sessions: dict[str, set[str]] = {}
    session_fold: dict[str, str] = {}
    for row in rows:
        previous = session_fold.setdefault(row.session_id, row.fold_id)
        if previous != row.fold_id:
            raise ValueError("max_t_session_fold_mismatch")
        fold_sessions.setdefault(row.fold_id, set()).add(row.session_id)
    try:
        dated_segments = tuple(
            tuple(
                (fold_id, session, date.fromisoformat(session))
                for session in sorted(sessions, key=date.fromisoformat)
            )
            for fold_id, sessions in sorted(
                fold_sessions.items(),
                key=lambda value: min(date.fromisoformat(session) for session in value[1]),
            )
        )
    except ValueError:
        raise ValueError("max_t_session_id_invalid") from None
    for previous, current in zip(dated_segments, dated_segments[1:]):
        if max(value[2] for value in previous) >= min(value[2] for value in current):
            raise ValueError("max_t_fold_order_invalid")
    return tuple(
        tuple((fold_id, session) for fold_id, session, _session_date in segment)
        for segment in dated_segments
    )


def _sample_segment(
    segment: tuple[tuple[str, str], ...],
    *,
    block_length_sessions: int,
    generator: random.Random,
) -> tuple[tuple[str, str], ...]:
    maximum_start = len(segment) - block_length_sessions
    sampled: list[tuple[str, str]] = []
    while len(sampled) < len(segment):
        start = generator.randint(0, maximum_start)
        sampled.extend(segment[start : start + block_length_sessions])
    return tuple(sampled[: len(segment)])


def _type7_quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered or not 0.0 <= probability <= 1.0:
        raise ValueError("quantile_input_invalid")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])
