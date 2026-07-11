from __future__ import annotations

import hashlib
import unittest

from rp001_s2.discovery import ForecastFeatures
from rp001_s2.evaluation import (
    EvaluationExample,
    PredictionRow,
    build_development_folds,
    choose_alarm_threshold,
    run_purged_oof,
    synchronized_block_max_t,
)


def _features(index: int) -> ForecastFeatures:
    value = (index % 17) / 16.0
    return ForecastFeatures(
        z1=2.0 * value - 0.5,
        m3=2.5 * value,
        m5=2.0 * value - 0.2,
        m10=1.8 * value,
        m20=1.2 * value,
        trend_consistency_10=0.4 + 0.6 * value,
        acceleration_3_vs_10=0.7 * value,
        return_curvature=0.8 * value,
        turnover_surprise=2.0 * value,
        return_scale=0.01,
        turnover_scale=0.2,
        as_of_index=index,
        series_id="TEST",
        signal_session_id=f"S{index:04d}",
        source_window_sha256=hashlib.sha256(str(index).encode()).hexdigest(),
    )


class PurgedWalkForwardContractTest(unittest.TestCase):
    def test_folds_have_ten_session_purge_and_embargo(self) -> None:
        folds = build_development_folds(875)

        self.assertGreaterEqual(len(folds), 3)
        for fold in folds:
            self.assertEqual(fold.purge.stop - fold.purge.start, 10)
            self.assertEqual(fold.embargo.stop - fold.embargo.start, 10)
            self.assertEqual(fold.train.stop, fold.purge.start)
            self.assertEqual(fold.purge.stop, fold.validation.start)
            self.assertEqual(fold.validation.stop, fold.embargo.start)
            self.assertLessEqual(fold.embargo.stop, 875)

    def test_oof_compares_all_models_on_identical_rows(self) -> None:
        examples = tuple(
            EvaluationExample(
                row_id=f"A:{index}",
                symbol="A",
                session_index=index,
                session_id=f"S{index:04d}",
                features=_features(index),
                outcome=(index % 17) >= 13,
                onset_offset_sessions=2 if (index % 17) >= 13 else None,
            )
            for index in range(875)
        )

        result = run_purged_oof(examples, session_count=875)

        expected_rows = {
            row.row_id for row in result.predictions if row.family_id == result.family_ids[0]
        }
        for family_id in result.family_ids:
            family_rows = {
                row.row_id for row in result.predictions if row.family_id == family_id
            }
            self.assertEqual(family_rows, expected_rows)
        self.assertTrue(
            all(
                0.0 <= probability <= 1.0
                for row in result.predictions
                for probability in (
                    row.candidate_probability,
                    row.baseline_constant_probability,
                    row.baseline_trend_probability,
                )
            )
        )
        inference = synchronized_block_max_t(
            result.predictions,
            replicates=100,
            block_length_sessions=20,
        )
        self.assertEqual(len(inference.contrasts), 6)
        self.assertTrue(
            all(
                value.simultaneous_lower_bound_95 is not None
                for value in inference.contrasts
            )
        )


class AlarmThresholdContractTest(unittest.TestCase):
    def test_threshold_respects_fpr_cap_and_uses_development_predictions(self) -> None:
        rows = tuple(
            PredictionRow(
                family_id="F",
                fold_id="fold-1" if index < 10 else "fold-2",
                row_id=str(index),
                symbol="A",
                session_id=f"S{index:02d}",
                outcome=index in {8, 9, 18, 19},
                onset_offset_sessions=2 if index in {8, 9, 18, 19} else None,
                candidate_probability=(index % 10) / 10.0,
                baseline_constant_probability=0.2,
                baseline_trend_probability=0.2,
            )
            for index in range(20)
        )

        selection = choose_alarm_threshold(rows)

        self.assertIsNotNone(selection.threshold)
        self.assertLessEqual(selection.false_alarm_rate, 0.10)
        self.assertGreater(selection.recall, 0.0)


if __name__ == "__main__":
    unittest.main()
