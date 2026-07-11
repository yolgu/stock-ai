from __future__ import annotations

import math
import unittest
from dataclasses import replace

from rp001_s2.direction_neutral_overheat import CompetitivePathLabel
from rp001_s2.overheat_oof import (
    CANDIDATE_MODEL_IDS,
    CLASS_ORDER,
    FAMILY_NAMES,
    MODEL_IDS,
    CompetitivePathExample,
    FamilyThresholdFlags,
    multiclass_brier_score,
    multiclass_log_loss,
    run_competitive_path_development_oof,
    top_class_ece,
)


def _sessions(count: int = 126) -> tuple[str, ...]:
    return tuple(f"session-{index:03d}" for index in range(count))


def _flags(index: int) -> dict[str, FamilyThresholdFlags]:
    result: dict[str, FamilyThresholdFlags] = {}
    for family_index, family in enumerate(FAMILY_NAMES):
        exceeds_p999 = (index + family_index) % 11 == 0
        result[family] = FamilyThresholdFlags(
            exceeds_p99=exceeds_p999 or (index + family_index) % 3 == 0,
            exceeds_p999=exceeds_p999,
        )
    return result


def _examples(
    sessions: tuple[str, ...],
    *,
    censored_indices: frozenset[int] = frozenset({10, 65, 90}),
) -> tuple[CompetitivePathExample, ...]:
    eligible_labels = CLASS_ORDER
    rows: list[CompetitivePathExample] = []
    for index, session_id in enumerate(sessions):
        label = (
            CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE
            if index in censored_indices
            else eligible_labels[index % len(eligible_labels)]
        )
        rows.append(
            CompetitivePathExample(
                row_id=f"row-{index:03d}",
                symbol="AAPL",
                session_id=session_id,
                sample_role="development",
                label=label,
                family_flags=_flags(index),
                signed_return=(-1.0 if index % 2 else 1.0) * (0.001 + index / 100_000),
                intrabar_log_range=0.002 + index / 100_000,
            )
        )
    return tuple(rows)


class CompetitivePathDevelopmentOOFTest(unittest.TestCase):
    def test_uses_exact_expanding_purged_walk_forward_session_contract(self) -> None:
        sessions = _sessions()

        result = run_competitive_path_development_oof(
            _examples(sessions),
            frozen_session_axis=sessions,
        )

        self.assertEqual(len(result.folds), 3)
        self.assertEqual(
            tuple(
                (
                    (fold.train.start, fold.train.stop),
                    (fold.purge.start, fold.purge.stop),
                    (fold.validation.start, fold.validation.stop),
                    (fold.embargo.start, fold.embargo.stop),
                )
                for fold in result.folds
            ),
            (
                ((0, 60), (60, 61), (61, 81), (81, 82)),
                ((0, 82), (82, 83), (83, 103), (103, 104)),
                ((0, 104), (104, 105), (105, 125), (125, 126)),
            ),
        )
        self.assertEqual(result.class_order, CLASS_ORDER)
        self.assertEqual(result.model_ids, MODEL_IDS)
        self.assertEqual(result.candidate_model_ids, CANDIDATE_MODEL_IDS)

    def test_excludes_and_records_unidentified_rows_on_one_common_mask(self) -> None:
        sessions = _sessions()

        result = run_competitive_path_development_oof(
            _examples(sessions),
            frozen_session_axis=sessions,
        )

        self.assertEqual(
            tuple(row.row_id for row in result.excluded_rows),
            ("row-010", "row-065", "row-090"),
        )
        self.assertTrue(
            all(
                row.reason == "censored_or_not_identifiable"
                for row in result.excluded_rows
            )
        )
        self.assertEqual(len(result.common_validation_row_ids), 58)
        self.assertNotIn("row-065", result.common_validation_row_ids)
        self.assertNotIn("row-090", result.common_validation_row_ids)

        identities_by_model = {
            model_id: tuple(
                (row.fold_id, row.row_id)
                for row in result.predictions
                if row.model_id == model_id
            )
            for model_id in MODEL_IDS
        }
        reference = identities_by_model[MODEL_IDS[0]]
        self.assertTrue(
            all(identities == reference for identities in identities_by_model.values())
        )
        self.assertEqual(len(reference), 58)

    def test_probabilities_and_multiclass_metrics_are_complete_and_finite(self) -> None:
        sessions = _sessions()

        result = run_competitive_path_development_oof(
            _examples(sessions),
            frozen_session_axis=sessions,
        )

        self.assertEqual(len(result.predictions), len(MODEL_IDS) * 58)
        for row in result.predictions:
            with self.subTest(model_id=row.model_id, row_id=row.row_id):
                self.assertEqual(len(row.probabilities), len(CLASS_ORDER))
                self.assertTrue(all(0.0 < value < 1.0 for value in row.probabilities))
                self.assertAlmostEqual(sum(row.probabilities), 1.0, places=12)
        self.assertEqual(tuple(metric.model_id for metric in result.metrics), MODEL_IDS)
        for metric in result.metrics:
            self.assertEqual(metric.row_count, 58)
            self.assertTrue(math.isfinite(metric.multiclass_brier))
            self.assertTrue(math.isfinite(metric.log_loss))
            self.assertTrue(math.isfinite(metric.top_class_ece))
            self.assertGreaterEqual(metric.multiclass_brier, 0.0)
            self.assertGreaterEqual(metric.log_loss, 0.0)
            self.assertTrue(0.0 <= metric.top_class_ece <= 1.0)
        self.assertFalse(hasattr(result, "threshold"))

    def test_c3_validation_values_do_not_refit_scaling_or_change_peer_prediction(self) -> None:
        sessions = _sessions()
        examples = _examples(sessions)
        original = run_competitive_path_development_oof(
            examples,
            frozen_session_axis=sessions,
        )
        changed_row = replace(
            examples[70],
            signed_return=900.0,
            intrabar_log_range=800.0,
        )
        repeated = run_competitive_path_development_oof(
            examples[:70] + (changed_row,) + examples[71:],
            frozen_session_axis=sessions,
        )

        original_peer = next(
            row
            for row in original.predictions
            if row.model_id == "c3_flags_signed_return_range"
            and row.row_id == "row-071"
        )
        repeated_peer = next(
            row
            for row in repeated.predictions
            if row.model_id == "c3_flags_signed_return_range"
            and row.row_id == "row-071"
        )
        original_changed = next(
            row
            for row in original.predictions
            if row.model_id == "c3_flags_signed_return_range"
            and row.row_id == "row-070"
        )
        repeated_changed = next(
            row
            for row in repeated.predictions
            if row.model_id == "c3_flags_signed_return_range"
            and row.row_id == "row-070"
        )
        self.assertEqual(original_peer.probabilities, repeated_peer.probabilities)
        self.assertNotEqual(original_changed.probabilities, repeated_changed.probabilities)

    def test_result_is_deterministic_under_input_order_reversal(self) -> None:
        sessions = _sessions()
        examples = _examples(sessions)

        forward = run_competitive_path_development_oof(
            examples,
            frozen_session_axis=sessions,
        )
        reversed_input = run_competitive_path_development_oof(
            tuple(reversed(examples)),
            frozen_session_axis=sessions,
        )

        self.assertEqual(forward, reversed_input)

    def test_rejects_confirmation_access_invalid_flags_and_insufficient_folds(self) -> None:
        sessions = _sessions()
        examples = _examples(sessions)
        with self.assertRaisesRegex(ValueError, "development_sample_role_required"):
            replace(examples[0], sample_role="sealed_confirmation")
        with self.assertRaisesRegex(ValueError, "family_flags_invalid"):
            FamilyThresholdFlags(exceeds_p99=False, exceeds_p999=True)
        with self.assertRaisesRegex(ValueError, "insufficient_development_folds"):
            short_axis = _sessions(125)
            run_competitive_path_development_oof(
                _examples(short_axis, censored_indices=frozenset()),
                frozen_session_axis=short_axis,
            )


class MulticlassMetricTest(unittest.TestCase):
    def test_perfect_probabilities_have_zero_metrics(self) -> None:
        labels = (
            CompetitivePathLabel.UPSIDE_ACCELERATION,
            CompetitivePathLabel.DOWNSIDE_ACCELERATION,
        )
        probabilities = (
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
        )

        self.assertEqual(
            multiclass_brier_score(labels, probabilities, CLASS_ORDER),
            0.0,
        )
        self.assertEqual(
            multiclass_log_loss(labels, probabilities, CLASS_ORDER),
            0.0,
        )
        self.assertEqual(top_class_ece(labels, probabilities, CLASS_ORDER), 0.0)


if __name__ == "__main__":
    unittest.main()
