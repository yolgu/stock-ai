import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(RESEARCH_DIRECTORY))

from research_pipeline import (  # noqa: E402
    CandidateTrialEvaluator,
    ResearchProtocol,
    ResearchWindowBuilder,
    SpecialOutcomeDefinition,
    TossCandleArchive,
    select_prediction_episode_starts,
)
from validation import (  # noqa: E402
    BarrierDefinition,
    CandidateDefinition,
    OutcomeDefinition,
)


def make_market(count: int = 520, start: str = "2019-01-02") -> pd.DataFrame:
    index = pd.date_range(start, periods=count, freq="B", tz="UTC")
    increments = 0.001 + 0.008 * np.sin(np.arange(count) / 5.0)
    close = 100.0 * np.exp(np.cumsum(increments))
    open_price = close * (1.0 - 0.001 * np.cos(np.arange(count)))
    high = np.maximum(open_price, close) * 1.01
    low = np.minimum(open_price, close) * 0.99
    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000_000.0 + 10_000.0 * (np.arange(count) % 17),
        },
        index=index,
    )


class ResearchProtocolTest(unittest.TestCase):
    def test_loads_all_preregistered_daily_candidates_without_exact_flow_substitution(self) -> None:
        protocol = ResearchProtocol.from_file(
            RESEARCH_DIRECTORY / "preregistration.json"
        )

        self.assertEqual(len(protocol.candidate_registry.candidates), 19)
        self.assertEqual(protocol.horizons, (1, 3, 5, 10))
        self.assertEqual(protocol.data_cutoff, "2026-07-09")
        self.assertNotIn(
            "panic.earlyRiskExactFlow",
            [candidate.identifier for candidate in protocol.candidate_registry.candidates],
        )
        self.assertEqual(protocol.calibration_bin_count, 5)
        self.assertIn("reliefConfirmed", protocol.outcome_definitions)
        relief_original = next(
            candidate
            for candidate in protocol.candidate_registry.candidates
            if candidate.identifier == "relief.originalProxy"
        )
        self.assertEqual(
            relief_original.horizons_for_outcome("fakeRelief"),
            (5, 10),
        )
        self.assertEqual(len(protocol.hypotheses), 130)
        self.assertEqual(
            protocol.hypotheses[0].identifier,
            "fomo.baseline.breakout20::fomoContinuation@1",
        )
        self.assertEqual(
            protocol.hypotheses[-1].identifier,
            "relief.persistenceGated::reliefConfirmed@5",
        )
        self.assertEqual(protocol.minimum_event_count, 30)
        self.assertEqual(protocol.anchor_dates["TSLA:primary"], "2020-07-23")
        self.assertEqual(protocol.anchor_dates["NVDA:primary"], "2023-05-25")
        self.assertEqual(protocol.anchor_dates["TSLA:sensitivity"], "2020-08-12")
        self.assertEqual(len(protocol.primary_holm_hypotheses), 4)
        self.assertEqual(protocol.significance_alpha, 0.05)
        self.assertEqual(protocol.four_month_start_date, "2026-03-10")
        self.assertEqual(protocol.four_month_end_date, "2026-07-09")
        self.assertEqual(
            protocol.candidate_complexity["panic.deduplicated"],
            (5, 0),
        )


class TossCandleArchiveTest(unittest.TestCase):
    def test_reads_strict_decimal_text_candles_as_an_ascending_market_frame(self) -> None:
        candles = [
            {
                "timestamp": "2026-07-08T09:00:00+09:00",
                "openPrice": "100",
                "highPrice": "110",
                "lowPrice": "90",
                "closePrice": "105",
                "volume": "1000",
                "currency": "KRW",
            },
            {
                "timestamp": "2026-07-09T09:00:00+09:00",
                "openPrice": "105",
                "highPrice": "115",
                "lowPrice": "100",
                "closePrice": "110",
                "volume": "2000",
                "currency": "KRW",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "000660.json"
            file_path.write_text(json.dumps(candles), encoding="utf-8")

            archive = TossCandleArchive.from_file("000660", file_path)

        self.assertEqual(archive.symbol, "000660")
        self.assertEqual(archive.currency, "KRW")
        self.assertEqual(archive.market.index.strftime("%Y-%m-%d").tolist(), ["2026-07-08", "2026-07-09"])
        self.assertEqual(archive.market["close"].tolist(), [105.0, 110.0])

    def test_rejects_duplicate_trading_dates(self) -> None:
        duplicate = {
            "timestamp": "2026-07-09T09:00:00+09:00",
            "openPrice": "100",
            "highPrice": "110",
            "lowPrice": "90",
            "closePrice": "105",
            "volume": "1000",
            "currency": "KRW",
        }
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "duplicate.json"
            file_path.write_text(json.dumps([duplicate, duplicate]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unique trading dates"):
                TossCandleArchive.from_file("000660", file_path)


class ResearchWindowBuilderTest(unittest.TestCase):
    def test_anchored_window_contains_exactly_360_actual_sessions(self) -> None:
        market = make_market(800, start="2018-01-02")
        anchor_date = market.index[300].strftime("%Y-%m-%d")

        window = ResearchWindowBuilder().anchored(
            symbol="TSLA",
            market=market,
            anchor_date=anchor_date,
            sessions=360,
        )

        self.assertEqual(window.analysis_start, 300)
        self.assertEqual(window.analysis_end, 660)
        self.assertEqual(len(window.analysis_market), 360)
        self.assertEqual(window.analysis_market.index[0], market.index[300])

    def test_current_window_uses_last_120_completed_sessions(self) -> None:
        market = make_market(300)

        window = ResearchWindowBuilder().latest(
            symbol="MU",
            market=market,
            sessions=120,
        )

        self.assertEqual(window.analysis_start, 180)
        self.assertEqual(window.analysis_end, 300)
        self.assertEqual(len(window.analysis_market), 120)


class CandidateTrialEvaluatorTest(unittest.TestCase):
    def test_episode_cooldown_uses_actual_sessions_and_unavailable_scores_reset_crossing(self) -> None:
        records = [
            {"date": "2026-07-01", "alert": True},
            {"date": "2026-07-02", "alert": False},
            {"date": "2026-07-03", "alert": True},
        ]

        starts = select_prediction_episode_starts(records, horizon=1)

        self.assertEqual(starts.tolist(), ["2026-07-01", "2026-07-03"])

    def test_episode_crossing_recomputes_the_previous_score_at_the_current_fold_threshold(self) -> None:
        records = [
            {
                "date": "2026-07-01",
                "score": 82.0,
                "alertThreshold": 80.0,
                "causalEligibility": True,
                "alert": True,
            },
            {
                "date": "2026-07-02",
                "score": 85.0,
                "alertThreshold": 80.0,
                "causalEligibility": True,
                "alert": True,
            },
            {
                "date": "2026-07-03",
                "score": 95.0,
                "alertThreshold": 90.0,
                "causalEligibility": True,
                "alert": True,
            },
        ]

        starts = select_prediction_episode_starts(records, horizon=1)

        self.assertEqual(starts.tolist(), ["2026-07-01", "2026-07-03"])

    def test_lower_fold_threshold_does_not_create_a_false_crossing(self) -> None:
        records = [
            {
                "date": "2026-07-01",
                "score": 85.0,
                "alertThreshold": 90.0,
                "causalEligibility": True,
                "alert": False,
            },
            {
                "date": "2026-07-02",
                "score": 85.0,
                "alertThreshold": 80.0,
                "causalEligibility": True,
                "alert": True,
            },
        ]

        starts = select_prediction_episode_starts(records, horizon=1)

        self.assertEqual(starts.tolist(), [])

    def test_raw_alert_does_not_use_the_future_outcome_availability(self) -> None:
        market = make_market(520)
        for position, multiplier in zip(
            range(len(market) - 5, len(market)),
            (2.0, 3.0, 4.0, 5.0, 6.0),
            strict=True,
        ):
            market.iloc[position, 0:4] *= multiplier
        candidate = CandidateDefinition(
            identifier="fomo.baseline.test",
            family="fomo",
            kind="baseline",
            formula="momentum5",
            weights=None,
            primary_outcome="fomoContinuation",
            outcome_ids=("fomoContinuation",),
            applicable_horizons=(5,),
        )
        outcome = OutcomeDefinition(
            identifier="fomoContinuation",
            barrier=BarrierDefinition("upper", 0.5, "lower", 0.3),
            applicable_horizons=(5,),
        )

        result = CandidateTrialEvaluator(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
            bootstrap_repetitions=10,
        ).evaluate(
            symbol="TEST",
            market=market,
            analysis_start=280,
            analysis_sessions=240,
            block_sessions=120,
            candidate=candidate,
            outcome=outcome,
            horizon=5,
        )

        last_prediction = result["predictions"][-1]
        self.assertEqual(last_prediction["status"], "right_censored_excluded")
        self.assertGreaterEqual(
            last_prediction["score"],
            last_prediction["alertThreshold"],
        )
        self.assertTrue(last_prediction["alert"])

    def test_produces_past_only_probabilities_and_jeffreys_alert_distribution(self) -> None:
        market = make_market(520)
        candidate = CandidateDefinition(
            identifier="panic.baseline.test",
            family="panic",
            kind="baseline",
            formula="downMoveImpulse",
            weights=None,
            primary_outcome="panicContinuation",
            outcome_ids=("panicContinuation",),
            applicable_horizons=(5,),
        )
        outcome = OutcomeDefinition(
            identifier="panicContinuation",
            barrier=BarrierDefinition("lower", 0.75, "upper", 0.5),
            applicable_horizons=(5,),
        )

        result = CandidateTrialEvaluator(
            percentile_minimum_sessions=20,
            percentile_maximum_sessions=60,
            calibration_bin_count=5,
            bootstrap_repetitions=50,
        ).evaluate(
            symbol="TEST",
            market=market,
            analysis_start=280,
            analysis_sessions=240,
            block_sessions=120,
            candidate=candidate,
            outcome=outcome,
            horizon=5,
        )

        self.assertEqual(result["candidateId"], candidate.identifier)
        self.assertEqual(result["horizon"], 5)
        self.assertEqual(len(result["folds"]), 2)
        self.assertEqual(sum(fold["testSessions"] for fold in result["folds"]), 240)
        self.assertTrue(0.0 <= result["posterior"]["mean"] <= 1.0)
        self.assertEqual(
            result["alerts"]["successes"] + result["alerts"]["failures"],
            result["alerts"]["observed"],
        )
        self.assertFalse(math.isnan(result["metrics"]["brierScore"]))
        self.assertEqual(result["pairedBrierBootstrap"]["foldCount"], 2)
        observed_daily_alerts = sum(
            1
            for prediction in result["predictions"]
            if prediction["label"] is not None and prediction["alert"]
        )
        self.assertEqual(
            result["metrics"]["truePositive"]
            + result["metrics"]["falsePositive"],
            observed_daily_alerts,
        )
        self.assertEqual(
            [prediction["status"] for prediction in result["predictions"][-5:]],
            ["right_censored_excluded"] * 5,
        )
        for prediction in result["predictions"]:
            self.assertLess(prediction["trainingEnd"], prediction["date"])
            self.assertEqual(
                prediction["alert"],
                prediction["score"] is not None
                and prediction["score"] >= prediction["alertThreshold"],
            )

    def test_rejects_a_horizon_excluded_for_the_requested_outcome(self) -> None:
        market = make_market(520)
        candidate = CandidateDefinition(
            identifier="relief.persistence.test",
            family="relief",
            kind="repaired",
            formula="reliefPersistence",
            weights=None,
            primary_outcome="reliefConfirmed",
            outcome_ids=("reliefConfirmed", "fakeRelief"),
            applicable_horizons=(3, 5, 10),
            outcome_applicable_horizons={
                "reliefConfirmed": (3, 5, 10),
                "fakeRelief": (5, 10),
            },
        )
        outcome = SpecialOutcomeDefinition(
            identifier="fakeRelief",
            applicable_horizons=(5, 10),
        )

        with self.assertRaisesRegex(
            ValueError,
            "Candidate is not applicable to the requested outcome and horizon",
        ):
            CandidateTrialEvaluator(
                percentile_minimum_sessions=20,
                percentile_maximum_sessions=60,
                bootstrap_repetitions=10,
            ).evaluate(
                symbol="TEST",
                market=market,
                analysis_start=280,
                analysis_sessions=240,
                block_sessions=120,
                candidate=candidate,
                outcome=outcome,
                horizon=3,
            )


if __name__ == "__main__":
    unittest.main()
