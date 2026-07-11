from __future__ import annotations

import dataclasses
import random
import statistics
import unittest
from datetime import date, timedelta

from rp001_s2.evaluation import PredictionRow
from rp001_s2.temporal_inference import synchronized_calendar_block_max_t


def _rows(session_order: tuple[int, ...]) -> tuple[PredictionRow, ...]:
    start = date(2025, 1, 1)
    values: list[PredictionRow] = []
    for family_index, family in enumerate(("F1", "F2", "F3")):
        for session_index in session_order:
            session = (start + timedelta(days=session_index)).isoformat()
            for symbol_index, symbol in enumerate(("A", "B")):
                outcome = (session_index + symbol_index) % 5 == 0
                values.append(
                    PredictionRow(
                        family_id=family,
                        fold_id="fold-1" if session_index < 30 else "fold-2",
                        row_id=f"{symbol}:{session}",
                        symbol=symbol,
                        session_id=session,
                        outcome=outcome,
                        onset_offset_sessions=2 if outcome else None,
                        candidate_probability=min(
                            0.95,
                            0.12 + 0.02 * family_index + 0.5 * float(outcome),
                        ),
                        baseline_constant_probability=0.2,
                        baseline_trend_probability=0.18 + 0.02 * (session_index % 3),
                    )
                )
    return tuple(values)


class CalendarBlockMaxTContractTest(unittest.TestCase):
    def test_inference_is_invariant_to_symbol_or_session_first_encounter_order(self) -> None:
        chronological = tuple(range(60))
        nonchronological = tuple(range(30, 60)) + tuple(range(30))

        expected = synchronized_calendar_block_max_t(
            _rows(chronological),
            replicates=100,
            block_length_sessions=10,
        )
        actual = synchronized_calendar_block_max_t(
            _rows(nonchronological),
            replicates=100,
            block_length_sessions=10,
        )

        self.assertEqual(dataclasses.asdict(expected), dataclasses.asdict(actual))

    def test_lower_bound_uses_bootstrap_minus_observed_upper_tail(self) -> None:
        rows = _rows(tuple(range(60)))

        result = synchronized_calendar_block_max_t(
            rows,
            replicates=200,
            block_length_sessions=10,
        )

        self.assertAlmostEqual(
            _reference_upper_tail_critical(rows, replicates=200, block_length=10),
            float(result.simultaneous_critical_value),
            places=14,
        )

    def test_common_mask_mismatch_is_rejected_before_bootstrap(self) -> None:
        rows = list(_rows(tuple(range(60))))
        rows.pop()

        with self.assertRaisesRegex(ValueError, "max_t_common_mask_mismatch"):
            synchronized_calendar_block_max_t(
                tuple(rows),
                replicates=100,
                block_length_sessions=10,
            )

    def test_family_specific_baseline_probabilities_are_rejected(self) -> None:
        rows = list(_rows(tuple(range(60))))
        last = rows[-1]
        rows[-1] = dataclasses.replace(
            last,
            baseline_constant_probability=last.baseline_constant_probability + 0.01,
        )

        with self.assertRaisesRegex(ValueError, "max_t_baseline_mismatch"):
            synchronized_calendar_block_max_t(
                tuple(rows),
                replicates=100,
                block_length_sessions=10,
            )

    def test_interleaving_fold_date_ranges_are_rejected(self) -> None:
        rows = tuple(
            dataclasses.replace(
                row,
                fold_id="fold-even" if date.fromisoformat(row.session_id).day % 2 == 0 else "fold-odd",
            )
            for row in _rows(tuple(range(60)))
        )

        with self.assertRaisesRegex(ValueError, "max_t_fold_order_invalid"):
            synchronized_calendar_block_max_t(
                rows,
                replicates=100,
                block_length_sessions=10,
            )


def _reference_upper_tail_critical(
    rows: tuple[PredictionRow, ...],
    *,
    replicates: int,
    block_length: int,
) -> float:
    families = tuple(sorted({row.family_id for row in rows}))
    reference = tuple(row for row in rows if row.family_id == families[0])
    folds = tuple(sorted({row.fold_id for row in reference}))
    segments = tuple(
        tuple(
            sorted(
                {row.session_id for row in reference if row.fold_id == fold},
            )
        )
        for fold in folds
    )
    grouped: dict[tuple[str, str], dict[tuple[str, str], tuple[float, ...]]] = {}
    observed: dict[tuple[str, str], float] = {}
    for family in families:
        family_rows = tuple(row for row in rows if row.family_id == family)
        for baseline_id in ("B1", "B2"):
            values: dict[tuple[str, str], list[float]] = {
                (fold, session): [] for fold, segment in zip(folds, segments, strict=True) for session in segment
            }
            all_differences: list[float] = []
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
                values[(row.fold_id, row.session_id)].append(difference)
                all_differences.append(difference)
            key = (family, baseline_id)
            grouped[key] = {name: tuple(items) for name, items in values.items()}
            observed[key] = statistics.fmean(all_differences)
    generator = random.Random(20260711)
    estimates = {key: [] for key in observed}
    for _ in range(replicates):
        sampled: list[tuple[str, str]] = []
        for fold, segment in zip(folds, segments, strict=True):
            segment_sample: list[str] = []
            while len(segment_sample) < len(segment):
                start = generator.randint(0, len(segment) - block_length)
                segment_sample.extend(segment[start : start + block_length])
            sampled.extend((fold, session) for session in segment_sample[: len(segment)])
        for key, values in grouped.items():
            estimates[key].append(
                statistics.fmean(
                    value for session in sampled for value in values[session]
                )
            )
    errors = {key: statistics.stdev(values) for key, values in estimates.items()}
    usable = tuple(key for key, error in errors.items() if error > 0.0)
    maxima = tuple(
        max(
            (estimates[key][index] - observed[key]) / errors[key]
            for key in usable
        )
        for index in range(replicates)
    )
    return _type7(maxima, 0.95)


def _type7(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


if __name__ == "__main__":
    unittest.main()
