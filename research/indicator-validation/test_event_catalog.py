import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from event_catalog import (  # noqa: E402
    MarketGroundTruthEvent,
    build_ground_truth_catalog,
    build_phase_catalog,
    build_signal_catalog,
    cluster_market_events,
    match_lead_times,
)


def actual_sessions(count: int = 10) -> pd.DatetimeIndex:
    dates = [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-05",
        "2026-06-08",
        "2026-06-09",
        "2026-06-11",
        "2026-06-12",
        "2026-06-15",
        "2026-06-16",
        "2026-06-17",
        "2026-06-18",
    ]
    return pd.DatetimeIndex(pd.to_datetime(dates[:count], utc=True))


class GroundTruthEpisodeCatalogTest(unittest.TestCase):
    def test_merges_success_origins_through_t_plus_h_without_revising_earliest_target(self) -> None:
        labels = pd.DataFrame(
            {
                "status": [
                    "failure",
                    "success",
                    "success",
                    "failure",
                    "success",
                    "success",
                    "failure",
                    "failure",
                    "failure",
                    "failure",
                ],
                "label": [0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0],
                "firstPassageOffset": [
                    np.nan,
                    3.0,
                    1.0,
                    np.nan,
                    1.0,
                    2.0,
                    np.nan,
                    np.nan,
                    np.nan,
                    np.nan,
                ],
            },
            index=actual_sessions(),
        )

        catalog = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="panicOnset",
            horizon=3,
            label_frame=labels,
        )

        self.assertEqual(len(catalog.episodes), 2)
        first, second = catalog.episodes
        self.assertEqual(first.origin_ordinal, 1)
        self.assertEqual(first.origin_date, "2026-06-02")
        self.assertEqual(first.target_offset, 3)
        self.assertEqual(first.target_ordinal, 4)
        self.assertEqual(first.target_date, "2026-06-08")
        self.assertEqual(first.suppressed_through_ordinal, 4)
        self.assertEqual(
            [(origin.ordinal, origin.date) for origin in first.merged_origins],
            [(2, "2026-06-03"), (4, "2026-06-08")],
        )
        self.assertEqual(
            [
                (origin.target_offset, origin.target_date)
                for origin in first.merged_origins
            ],
            [(1, "2026-06-05"), (1, "2026-06-09")],
        )
        self.assertEqual(second.origin_ordinal, 5)
        self.assertEqual(second.target_ordinal, 7)

    def test_rejects_nonbinary_observed_labels(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["failure", "failure"],
                "label": [0.0, 2.0],
                "firstPassageOffset": [np.nan, np.nan],
            },
            index=actual_sessions(2),
        )

        with self.assertRaisesRegex(ValueError, "binary label"):
            build_ground_truth_catalog(
                symbol="TEST",
                outcome_id="panicOnset",
                horizon=1,
                label_frame=labels,
            )


class MarketEventClusteringTest(unittest.TestCase):
    def test_partitions_clusters_by_outcome_and_horizon_and_never_duplicates_a_symbol(self) -> None:
        events = [
            MarketGroundTruthEvent("A", "panicOnset", 5, "lower", "2026-06-01"),
            MarketGroundTruthEvent("B", "panicOnset", 5, "lower", "2026-06-02"),
            MarketGroundTruthEvent("A", "panicOnset", 5, "lower", "2026-06-02"),
            MarketGroundTruthEvent("C", "panicContinuation", 10, "lower", "2026-06-01"),
        ]

        clusters = cluster_market_events(events)

        member_scopes = [
            [
                (member.event.symbol, member.event.outcome_id, member.event.horizon)
                for member in cluster.members
            ]
            for cluster in clusters
        ]
        self.assertIn(
            [("A", "panicOnset", 5), ("B", "panicOnset", 5)],
            member_scopes,
        )
        self.assertIn([("A", "panicOnset", 5)], member_scopes)
        self.assertIn([("C", "panicContinuation", 10)], member_scopes)
        for cluster in clusters:
            symbols = [member.event.symbol for member in cluster.members]
            self.assertEqual(len(symbols), len(set(symbols)))

    def test_uses_same_direction_one_day_anchor_distance_without_chaining(self) -> None:
        events = [
            MarketGroundTruthEvent("A", "panic", 5, "lower", "2026-06-01"),
            MarketGroundTruthEvent("B", "panic", 5, "lower", "2026-06-02"),
            MarketGroundTruthEvent("C", "panic", 5, "lower", "2026-06-03"),
            MarketGroundTruthEvent("D", "fomo", 5, "upper", "2026-06-01"),
        ]

        clusters = cluster_market_events(events)

        self.assertEqual(len(clusters), 3)
        self.assertEqual(
            [member.event.symbol for member in clusters[0].members],
            ["A", "B"],
        )
        self.assertEqual(
            [member.global_event_weight for member in clusters[0].members],
            [0.5, 0.5],
        )
        self.assertEqual(
            [member.event.symbol for member in clusters[1].members],
            ["D"],
        )
        self.assertEqual(
            [member.event.symbol for member in clusters[2].members],
            ["C"],
        )


class SignalEpisodeCatalogTest(unittest.TestCase):
    def test_discards_cooldown_crossings_and_requires_a_new_crossing(self) -> None:
        alerts = pd.Series(
            [
                False,
                True,
                False,
                True,
                True,
                False,
                True,
                True,
                pd.NA,
                True,
                False,
                True,
            ],
            index=actual_sessions(12),
            dtype="boolean",
        )

        catalog = build_signal_catalog(
            symbol="TEST",
            candidate_id="panic.repaired",
            outcome_id="panicOnset",
            horizon=3,
            alerts=alerts,
        )

        self.assertEqual(
            [(episode.alert_ordinal, episode.alert_date) for episode in catalog.episodes],
            [
                (1, "2026-06-02"),
                (6, "2026-06-11"),
                (11, "2026-06-18"),
            ],
        )
        self.assertEqual(
            [episode.suppressed_through_ordinal for episode in catalog.episodes],
            [4, 9, 14],
        )

    def test_unavailable_alert_resets_crossing_without_consulting_future_labels(self) -> None:
        alerts = pd.Series(
            [False, True, True, pd.NA, True],
            index=actual_sessions(5),
            dtype="boolean",
        )

        catalog = build_signal_catalog(
            symbol="TEST",
            candidate_id="panic.repaired",
            outcome_id="panicOnset",
            horizon=1,
            alerts=alerts,
        )

        self.assertEqual(
            [episode.alert_ordinal for episode in catalog.episodes],
            [1, 4],
        )

    def test_rejects_numeric_threshold_flags_as_nonraw_alerts(self) -> None:
        alerts = pd.Series([0, 1], index=actual_sessions(2))

        with self.assertRaisesRegex(ValueError, "boolean or unavailable"):
            build_signal_catalog(
                symbol="TEST",
                candidate_id="panic.repaired",
                outcome_id="panicOnset",
                horizon=1,
                alerts=alerts,
            )


class LeadTimeMatcherTest(unittest.TestCase):
    def test_matches_earliest_forward_target_within_h_actual_sessions(self) -> None:
        labels = pd.DataFrame(
            {
                "status": [
                    "failure",
                    "success",
                    "failure",
                    "failure",
                    "failure",
                    "success",
                    "failure",
                    "failure",
                    "failure",
                    "failure",
                    "failure",
                    "failure",
                ],
                "label": [0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "firstPassageOffset": [
                    np.nan,
                    3.0,
                    np.nan,
                    np.nan,
                    np.nan,
                    2.0,
                    np.nan,
                    np.nan,
                    np.nan,
                    np.nan,
                    np.nan,
                    np.nan,
                ],
            },
            index=actual_sessions(12),
        )
        alerts = pd.Series(
            [False, False, True, False, False, False, True, False, False, False, True, False],
            index=actual_sessions(12),
            dtype="boolean",
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="panicOnset",
            horizon=3,
            label_frame=labels,
        )
        signals = build_signal_catalog(
            symbol="TEST",
            candidate_id="panic.repaired",
            outcome_id="panicOnset",
            horizon=3,
            alerts=alerts,
        )

        matches = match_lead_times(signals, ground_truth)

        self.assertEqual(
            [match.status for match in matches],
            ["matched", "matched", "lead_time_unavailable"],
        )
        self.assertEqual(
            [match.lead_time_sessions for match in matches],
            [2, 1, None],
        )
        self.assertEqual(
            [match.target_date for match in matches],
            ["2026-06-08", "2026-06-12", None],
        )
        self.assertEqual(
            [match.origin_date for match in matches],
            ["2026-06-02", "2026-06-09", None],
        )

    def test_does_not_match_a_target_before_the_alert(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["success", "failure", "failure", "failure", "failure"],
                "label": [1.0, 0.0, 0.0, 0.0, 0.0],
                "firstPassageOffset": [1.0, np.nan, np.nan, np.nan, np.nan],
            },
            index=actual_sessions(5),
        )
        alerts = pd.Series(
            [False, False, True, False, False],
            index=actual_sessions(5),
            dtype="boolean",
        )

        matches = match_lead_times(
            build_signal_catalog(
                "TEST",
                "panic.repaired",
                "panicOnset",
                3,
                alerts,
            ),
            build_ground_truth_catalog(
                "TEST",
                "panicOnset",
                3,
                labels,
            ),
        )

        self.assertEqual(matches[0].status, "lead_time_unavailable")
        self.assertIsNone(matches[0].lead_time_sessions)

    def test_includes_a_target_exactly_h_sessions_after_the_alert(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["success", "failure", "failure", "failure"],
                "label": [1.0, 0.0, 0.0, 0.0],
                "firstPassageOffset": [3.0, np.nan, np.nan, np.nan],
            },
            index=actual_sessions(4),
        )
        alerts = pd.Series(
            [True, False, False, False],
            index=actual_sessions(4),
            dtype="boolean",
        )

        matches = match_lead_times(
            build_signal_catalog("TEST", "panic.repaired", "panicOnset", 3, alerts),
            build_ground_truth_catalog("TEST", "panicOnset", 3, labels),
        )

        self.assertEqual(matches[0].status, "matched")
        self.assertEqual(matches[0].lead_time_sessions, 3)

    def test_rejects_scope_and_actual_session_axis_mismatches(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["success", "failure", "failure", "failure"],
                "label": [1.0, 0.0, 0.0, 0.0],
                "firstPassageOffset": [1.0, np.nan, np.nan, np.nan],
            },
            index=actual_sessions(4),
        )
        ground_truth = build_ground_truth_catalog(
            "TEST",
            "panicOnset",
            1,
            labels,
        )
        alert_values = [True, False, False, False]

        with self.assertRaisesRegex(ValueError, "scopes must match"):
            match_lead_times(
                build_signal_catalog(
                    "TEST",
                    "panic.repaired",
                    "fomoContinuation",
                    1,
                    pd.Series(alert_values, index=actual_sessions(4)),
                ),
                ground_truth,
            )
        with self.assertRaisesRegex(ValueError, "actual-session axes must match"):
            match_lead_times(
                build_signal_catalog(
                    "TEST",
                    "panic.repaired",
                    "panicOnset",
                    1,
                    pd.Series(alert_values, index=actual_sessions(5)[1:]),
                ),
                ground_truth,
            )


class PhaseCatalogTest(unittest.TestCase):
    def test_prodrome_preserves_pre_anchor_actual_sessions_for_an_early_origin(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["success", "failure", "failure"],
                "label": [1.0, 0.0, 0.0],
                "firstPassageOffset": [1.0, np.nan, np.nan],
            },
            index=actual_sessions(3),
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="panicOnset",
            horizon=1,
            label_frame=labels,
        )
        prior_dates = (
            "2026-05-22",
            "2026-05-26",
            "2026-05-27",
            "2026-05-28",
            "2026-05-29",
        )

        phase = build_phase_catalog(
            ground_truth,
            labels,
            prior_session_dates=prior_dates,
        ).episodes[0]

        self.assertEqual(phase.origin_date, "2026-06-01")
        self.assertEqual(phase.prodrome_dates, prior_dates)

    def test_records_only_mechanically_identifiable_confirmed_relief_phases(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["failure"] * 5 + ["success"] + ["failure"] * 6,
                "label": [0.0] * 5 + [1.0] + [0.0] * 6,
                "firstPassageOffset": [np.nan] * 5 + [2.0] + [np.nan] * 6,
                "confirmationOffset": [np.nan] * 5 + [4.0] + [np.nan] * 6,
                "terminalOffset": [np.nan] * 5 + [4.0] + [np.nan] * 6,
            },
            index=actual_sessions(12),
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="reliefConfirmed",
            horizon=5,
            label_frame=labels,
        )

        phase = build_phase_catalog(ground_truth, labels).episodes[0]

        self.assertEqual(
            phase.prodrome_dates,
            (
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
                "2026-06-05",
                "2026-06-08",
            ),
        )
        self.assertEqual(phase.start_date, "2026-06-09")
        self.assertEqual(phase.full_target_date, "2026-06-12")
        self.assertEqual(phase.extreme_date, "2026-06-12")
        self.assertEqual(phase.extreme_offset, 2)
        self.assertEqual(phase.confirmation_date, "2026-06-16")
        self.assertEqual(phase.end_offset, 4)
        self.assertEqual(phase.end_date, "2026-06-16")
        self.assertEqual(phase.end_reason, "confirmation")
        self.assertIsNone(phase.fake_relief_date)
        self.assertEqual(
            [
                (item.phase, item.status, item.reason)
                for item in phase.phase_not_identifiable
            ],
            [
                ("early", "phase_not_identifiable", "half_barrier_rule_unspecified"),
                ("middle", "phase_not_identifiable", "half_barrier_rule_unspecified"),
                ("firstRebound", "phase_not_identifiable", "rebound_rule_unspecified"),
            ],
        )

    def test_fake_relief_uses_break_date_as_target_but_preserves_rebound_full_target(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["failure", "failure", "success"] + ["failure"] * 7,
                "label": [0.0, 0.0, 1.0] + [0.0] * 7,
                "firstPassageOffset": [np.nan, np.nan, 2.0] + [np.nan] * 7,
                "confirmationOffset": [np.nan] * 10,
                "terminalOffset": [np.nan, np.nan, 5.0] + [np.nan] * 7,
            },
            index=actual_sessions(10),
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="fakeRelief",
            horizon=5,
            label_frame=labels,
        )

        phase = build_phase_catalog(ground_truth, labels).episodes[0]

        self.assertEqual(ground_truth.episodes[0].target_offset, 5)
        self.assertEqual(ground_truth.episodes[0].target_date, "2026-06-12")
        self.assertEqual(phase.prodrome_dates, ("2026-06-01", "2026-06-02"))
        self.assertEqual(phase.start_date, "2026-06-03")
        self.assertEqual(phase.full_target_date, "2026-06-08")
        self.assertEqual(phase.extreme_date, "2026-06-08")
        self.assertIsNone(phase.confirmation_date)
        self.assertEqual(phase.fake_relief_date, "2026-06-12")
        self.assertEqual(phase.end_offset, 5)
        self.assertEqual(phase.end_date, "2026-06-12")
        self.assertEqual(phase.end_reason, "vertical_barrier")

    def test_confirmed_relief_success_requires_a_confirmation_offset(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["failure", "success", "failure", "failure"],
                "label": [0.0, 1.0, 0.0, 0.0],
                "firstPassageOffset": [np.nan, 1.0, np.nan, np.nan],
                "confirmationOffset": [np.nan] * 4,
            },
            index=actual_sessions(4),
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="reliefConfirmed",
            horizon=2,
            label_frame=labels,
        )

        with self.assertRaisesRegex(ValueError, "confirmationOffset"):
            build_phase_catalog(ground_truth, labels)

    def test_rejects_a_phase_frame_that_no_longer_matches_the_ground_truth_origin(self) -> None:
        labels = pd.DataFrame(
            {
                "status": ["failure", "success", "failure", "failure"],
                "label": [0.0, 1.0, 0.0, 0.0],
                "firstPassageOffset": [np.nan, 1.0, np.nan, np.nan],
            },
            index=actual_sessions(4),
        )
        ground_truth = build_ground_truth_catalog(
            symbol="TEST",
            outcome_id="panicOnset",
            horizon=2,
            label_frame=labels,
        )
        changed_labels = labels.copy()
        changed_labels.loc[changed_labels.index[1], "firstPassageOffset"] = 2.0

        with self.assertRaisesRegex(ValueError, "match its ground truth"):
            build_phase_catalog(ground_truth, changed_labels)


if __name__ == "__main__":
    unittest.main()
