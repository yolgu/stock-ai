from __future__ import annotations

import math
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Mapping

from rp001_s2.direction_neutral_overheat import (
    DirectionNeutralObservation,
    LabelHorizon,
    PassageLabel,
    ScreenState,
    ScreeningResult,
    group_episodes,
    label_first_passage,
    screen_observation,
)


_FAMILIES: tuple[str, ...] = ("return", "range", "turnover")
_SOURCE_WINDOW_SHA256 = "a" * 64
_UTC_ORIGIN = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _observation(
    session_ordinal: int,
    *,
    symbol: str = "AAPL",
    minute_of_day: int = 600,
    market_minute_ordinal: int | None = None,
    signed_return: float = 0.0,
    log_low: float = 9.99,
    log_high: float = 10.01,
    log_close: float = 10.0,
    family_scores: Mapping[str, float | None] | None = None,
    minute_end_utc: datetime | None = None,
    available_at_utc: datetime | None = None,
    session_id: str | None = None,
    session_date: date | None = None,
    source_window_sha256: str = _SOURCE_WINDOW_SHA256,
) -> DirectionNeutralObservation:
    resolved_market_minute_ordinal = (
        session_ordinal * 1_000 + minute_of_day
        if market_minute_ordinal is None
        else market_minute_ordinal
    )
    resolved_minute_end = (
        _UTC_ORIGIN + timedelta(minutes=resolved_market_minute_ordinal)
        if minute_end_utc is None
        else minute_end_utc
    )
    resolved_session_date = (
        date(2020, 1, 1) + timedelta(days=session_ordinal)
        if session_date is None
        else session_date
    )
    return DirectionNeutralObservation(
        symbol=symbol,
        session_ordinal=session_ordinal,
        minute_of_day=minute_of_day,
        market_minute_ordinal=resolved_market_minute_ordinal,
        minute_end_utc=resolved_minute_end,
        available_at_utc=(
            resolved_minute_end + timedelta(seconds=3)
            if available_at_utc is None
            else available_at_utc
        ),
        session_id=(
            resolved_session_date.isoformat() if session_id is None else session_id
        ),
        session_date=resolved_session_date,
        source_window_sha256=source_window_sha256,
        signed_return=signed_return,
        log_low=log_low,
        log_high=log_high,
        log_close=log_close,
        family_scores=(
            {family: 0.0 for family in _FAMILIES}
            if family_scores is None
            else family_scores
        ),
    )


def _sixty_session_history() -> tuple[DirectionNeutralObservation, ...]:
    return tuple(
        _observation(
            40 + index,
            family_scores={family: float(index) for family in _FAMILIES},
        )
        for index in range(60)
    )


def _decision(
    market_minute_ordinal: int,
    state: ScreenState,
    *,
    symbol: str = "AAPL",
    session_ordinal: int | None = None,
    minute_of_day: int | None = None,
) -> ScreeningResult:
    return ScreeningResult(
        observation=_observation(
            (
                market_minute_ordinal // 390
                if session_ordinal is None
                else session_ordinal
            ),
            symbol=symbol,
            minute_of_day=(
                market_minute_ordinal % 390
                if minute_of_day is None
                else minute_of_day
            ),
            market_minute_ordinal=market_minute_ordinal,
        ),
        state=state,
        family_screens=(),
    )


def _sigma_history(
    count: int = 40,
    *,
    zero_variation: bool = False,
) -> tuple[DirectionNeutralObservation, ...]:
    return tuple(
        _observation(
            index,
            market_minute_ordinal=index,
            signed_return=(
                0.0 if zero_variation else (-0.01 if index % 2 == 0 else 0.01)
            ),
        )
        for index in range(count)
    )


def _anchor(
    *,
    log_low: float = 9.99,
    log_high: float = 10.01,
) -> DirectionNeutralObservation:
    return _observation(
        40,
        market_minute_ordinal=100,
        minute_of_day=600,
        log_low=log_low,
        log_high=log_high,
        log_close=10.0,
    )


def _future_bar(
    offset: int,
    *,
    session_ordinal: int = 40,
    minute_of_day: int | None = None,
    signed_return: float = 0.0,
    log_low: float = 9.99,
    log_high: float = 10.01,
) -> DirectionNeutralObservation:
    return _observation(
        session_ordinal,
        minute_of_day=600 + offset if minute_of_day is None else minute_of_day,
        market_minute_ordinal=100 + offset,
        signed_return=signed_return,
        log_low=log_low,
        log_high=log_high,
        log_close=10.0,
    )


class DirectionNeutralScreeningTest(unittest.TestCase):
    def test_observation_preserves_frozen_temporal_and_lineage_contract(self) -> None:
        observation = _observation(40, market_minute_ordinal=100)

        self.assertEqual(observation.minute_end_utc, _UTC_ORIGIN + timedelta(minutes=100))
        self.assertEqual(
            observation.available_at_utc,
            observation.minute_end_utc + timedelta(seconds=3),
        )
        self.assertEqual(observation.session_id, "2020-02-10")
        self.assertEqual(observation.session_date, date(2020, 2, 10))
        self.assertEqual(observation.source_window_sha256, _SOURCE_WINDOW_SHA256)

    def test_target_availability_is_signal_time_and_late_history_is_excluded(
        self,
    ) -> None:
        history = tuple(
            _observation(
                60 + index,
                family_scores={family: float(index) for family in _FAMILIES},
            )
            for index in range(40)
        )
        target = _observation(
            100,
            family_scores={family: 1_000.0 for family in _FAMILIES},
        )
        self.assertEqual(
            screen_observation(target, history).state,
            ScreenState.CANDIDATE,
        )

        late_history = replace(
            history[0],
            available_at_utc=target.available_at_utc + timedelta(microseconds=1),
        )
        result = screen_observation(target, (late_history,) + history[1:])
        self.assertEqual(result.state, ScreenState.UNKNOWN)
        self.assertTrue(
            all(screen.observation_count == 39 for screen in result.family_screens)
        )

        with self.assertRaisesRegex(ValueError, "observation_timestamp_invalid"):
            replace(
                target,
                available_at_utc=target.minute_end_utc - timedelta(microseconds=1),
            )

    def test_type7_thresholds_are_strict_at_p99_and_p999(self) -> None:
        history = _sixty_session_history()
        target = _observation(
            100,
            family_scores={
                "return": 58.41,
                "range": 58.941,
                "turnover": 0.0,
            },
        )

        result = screen_observation(target, history)
        by_family = {screen.family: screen for screen in result.family_screens}

        self.assertEqual(result.state, ScreenState.INACTIVE)
        self.assertAlmostEqual(by_family["return"].p99, 58.41, places=12)
        self.assertAlmostEqual(by_family["range"].p999, 58.941, places=12)
        self.assertFalse(by_family["return"].exceeds_p99)
        self.assertTrue(by_family["range"].exceeds_p99)
        self.assertFalse(by_family["range"].exceeds_p999)

    def test_two_p99_families_or_one_p999_family_selects_candidate(self) -> None:
        history = _sixty_session_history()
        two_p99 = _observation(
            100,
            family_scores={
                "return": 58.42,
                "range": 58.42,
                "turnover": 0.0,
            },
        )
        one_p999 = replace(
            two_p99,
            family_scores={
                "return": 58.95,
                "range": 0.0,
                "turnover": 0.0,
            },
        )

        self.assertEqual(
            screen_observation(two_p99, history).state,
            ScreenState.CANDIDATE,
        )
        self.assertEqual(
            screen_observation(one_p999, history).state,
            ScreenState.CANDIDATE,
        )

    def test_missing_families_remain_unknown_and_are_not_reweighted(self) -> None:
        history = tuple(
            _observation(
                60 + index,
                family_scores={family: float(index) for family in _FAMILIES},
            )
            for index in range(40)
        )
        one_p99 = _observation(
            100,
            family_scores={
                "return": 38.7,
                "range": None,
                "turnover": None,
            },
        )

        unknown = screen_observation(one_p99, history)
        by_family = {screen.family: screen for screen in unknown.family_screens}

        self.assertEqual(unknown.state, ScreenState.UNKNOWN)
        self.assertTrue(by_family["return"].exceeds_p99)
        self.assertFalse(by_family["return"].exceeds_p999)
        self.assertFalse(by_family["range"].available)
        self.assertIsNone(by_family["range"].score)

        one_p999 = replace(
            one_p99,
            family_scores={
                "return": 39.0,
                "range": None,
                "turnover": None,
            },
        )
        self.assertEqual(
            screen_observation(one_p999, history).state,
            ScreenState.CANDIDATE,
        )

    def test_omitted_family_key_is_unknown_instead_of_a_zero_score(self) -> None:
        history = tuple(
            _observation(
                60 + index,
                family_scores={family: float(index) for family in _FAMILIES},
            )
            for index in range(40)
        )
        target = _observation(
            100,
            family_scores={"return": 38.7, "range": 0.0},
        )

        result = screen_observation(target, history)
        by_family = {screen.family: screen for screen in result.family_screens}

        self.assertEqual(result.state, ScreenState.UNKNOWN)
        self.assertEqual(set(by_family), set(_FAMILIES))
        self.assertIsNone(by_family["turnover"].score)
        self.assertFalse(by_family["turnover"].available)

    def test_only_prior_sixty_sessions_at_the_same_minute_are_used(self) -> None:
        history = _sixty_session_history()
        target = _observation(
            100,
            family_scores={family: 0.0 for family in _FAMILIES},
        )
        late_revision = replace(
            history[-1],
            available_at_utc=target.available_at_utc + timedelta(seconds=1),
            family_scores={family: 1_000.0 for family in _FAMILIES},
        )
        irrelevant = (
            _observation(
                39,
                family_scores={family: 1_000.0 for family in _FAMILIES},
            ),
            _observation(
                99,
                minute_of_day=601,
                family_scores={family: 1_000.0 for family in _FAMILIES},
            ),
            _observation(
                100,
                family_scores={family: 1_000.0 for family in _FAMILIES},
            ),
            _observation(
                101,
                family_scores={family: 1_000.0 for family in _FAMILIES},
            ),
            late_revision,
        )

        baseline = screen_observation(target, history)
        with_irrelevant_rows = screen_observation(target, history + irrelevant)

        self.assertEqual(with_irrelevant_rows.state, baseline.state)
        self.assertEqual(with_irrelevant_rows.family_screens, baseline.family_screens)
        self.assertTrue(
            all(screen.observation_count == 60 for screen in baseline.family_screens)
        )

    def test_fewer_than_forty_family_observations_is_unknown(self) -> None:
        history = tuple(
            _observation(
                61 + index,
                family_scores={family: float(index) for family in _FAMILIES},
            )
            for index in range(39)
        )
        target = _observation(
            100,
            family_scores={family: 1_000.0 for family in _FAMILIES},
        )

        result = screen_observation(target, history)

        self.assertEqual(result.state, ScreenState.UNKNOWN)
        self.assertTrue(
            all(not screen.available for screen in result.family_screens)
        )

    def test_signed_direction_and_reflected_log_prices_do_not_change_selection(
        self,
    ) -> None:
        history = _sixty_session_history()
        positive = _observation(
            100,
            signed_return=0.04,
            log_low=10.00,
            log_close=10.02,
            log_high=10.05,
            family_scores={
                "return": 58.42,
                "range": 58.42,
                "turnover": 0.0,
            },
        )
        reflected = replace(
            positive,
            signed_return=-positive.signed_return,
            log_low=20.0 - positive.log_high,
            log_close=20.0 - positive.log_close,
            log_high=20.0 - positive.log_low,
        )

        positive_result = screen_observation(positive, history)
        reflected_result = screen_observation(reflected, history)

        self.assertEqual(positive_result.state, ScreenState.CANDIDATE)
        self.assertEqual(reflected_result.state, positive_result.state)
        self.assertEqual(
            reflected_result.family_screens,
            positive_result.family_screens,
        )


class OverheatEpisodeGroupingTest(unittest.TestCase):
    def test_mixed_symbols_are_rejected_instead_of_combined(self) -> None:
        decisions = (
            _decision(0, ScreenState.CANDIDATE, symbol="AAPL"),
            _decision(1, ScreenState.CANDIDATE, symbol="MSFT"),
        )

        with self.assertRaisesRegex(ValueError, "episode_symbol_mismatch"):
            group_episodes(decisions)

    def test_gap_30_stays_in_burst_gap_31_starts_burst_and_gap_61_starts_episode(
        self,
    ) -> None:
        decisions = (
            _decision(0, ScreenState.CANDIDATE),
            *(_decision(value, ScreenState.INACTIVE) for value in range(1, 30)),
            _decision(30, ScreenState.CANDIDATE),
            *(_decision(value, ScreenState.INACTIVE) for value in range(31, 61)),
            _decision(61, ScreenState.CANDIDATE),
            *(_decision(value, ScreenState.INACTIVE) for value in range(62, 122)),
            _decision(122, ScreenState.CANDIDATE),
        )

        episodes = group_episodes(decisions)

        self.assertEqual(len(episodes), 2)
        self.assertEqual(
            episodes[0].bursts[0].candidate_market_minute_ordinals,
            (0, 30),
        )
        self.assertEqual(
            episodes[0].bursts[1].candidate_market_minute_ordinals,
            (61,),
        )
        self.assertEqual(episodes[0].closed_at_market_minute_ordinal, 121)
        self.assertFalse(episodes[0].right_censored)
        self.assertEqual(
            episodes[1].bursts[0].candidate_market_minute_ordinals,
            (122,),
        )
        self.assertTrue(episodes[1].right_censored)

    def test_unknown_breaks_inactive_run_and_marks_incomplete_coverage(self) -> None:
        first_59_after_unknown = (
            _decision(0, ScreenState.CANDIDATE),
            *(_decision(value, ScreenState.INACTIVE) for value in range(1, 31)),
            _decision(31, ScreenState.UNKNOWN),
            *(_decision(value, ScreenState.INACTIVE) for value in range(32, 91)),
        )

        open_episode = group_episodes(first_59_after_unknown)[0]
        closed_episode = group_episodes(
            first_59_after_unknown + (_decision(91, ScreenState.INACTIVE),)
        )[0]

        self.assertFalse(open_episode.coverage_complete)
        self.assertTrue(open_episode.right_censored)
        self.assertIsNone(open_episode.closed_at_market_minute_ordinal)
        self.assertFalse(closed_episode.coverage_complete)
        self.assertFalse(closed_episode.right_censored)
        self.assertEqual(closed_episode.closed_at_market_minute_ordinal, 91)

    def test_unobserved_market_minute_is_unknown_not_inactive(self) -> None:
        decisions = (
            _decision(0, ScreenState.CANDIDATE),
            _decision(1, ScreenState.INACTIVE),
            *(_decision(value, ScreenState.INACTIVE) for value in range(3, 62)),
        )

        episode = group_episodes(decisions)[0]

        self.assertFalse(episode.coverage_complete)
        self.assertTrue(episode.right_censored)
        self.assertIsNone(episode.closed_at_market_minute_ordinal)

    def test_overnight_and_weekend_session_jump_does_not_advance_inactivity(
        self,
    ) -> None:
        decisions = (
            _decision(
                0,
                ScreenState.CANDIDATE,
                session_ordinal=10,
                minute_of_day=600,
            ),
            *(
                _decision(
                    value,
                    ScreenState.INACTIVE,
                    session_ordinal=10,
                    minute_of_day=600 + value,
                )
                for value in range(1, 30)
            ),
            _decision(
                30,
                ScreenState.CANDIDATE,
                session_ordinal=13,
                minute_of_day=600,
            ),
        )

        episode = group_episodes(decisions)[0]

        self.assertEqual(len(episode.bursts), 1)
        self.assertEqual(
            episode.bursts[0].candidate_market_minute_ordinals,
            (0, 30),
        )
        self.assertTrue(episode.coverage_complete)
        self.assertTrue(episode.right_censored)

    def test_inactive_and_unknown_rows_before_first_candidate_create_no_episode(
        self,
    ) -> None:
        decisions = (
            _decision(0, ScreenState.UNKNOWN),
            _decision(1, ScreenState.INACTIVE),
        )

        self.assertEqual(group_episodes(decisions), ())


class FirstPassageLabelTest(unittest.TestCase):
    def test_first_up_down_and_same_minute_passages_are_distinct(self) -> None:
        history = _sigma_history()
        anchor = _anchor()
        neutral_future = tuple(_future_bar(offset) for offset in range(1, 6))
        up_future = (
            replace(neutral_future[0], log_high=10.08),
            *neutral_future[1:],
        )
        down_future = (
            replace(neutral_future[0], log_low=9.92),
            replace(neutral_future[1], log_high=10.08),
            *neutral_future[2:],
        )
        both_future = (
            replace(neutral_future[0], log_low=9.92, log_high=10.08),
            *neutral_future[1:],
        )

        up = label_first_passage(
            anchor,
            history + up_future,
            LabelHorizon.MINUTES_5,
        )
        down = label_first_passage(
            anchor,
            history + down_future,
            LabelHorizon.MINUTES_5,
        )
        both = label_first_passage(
            anchor,
            history + both_future,
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(up.label, PassageLabel.UP_FIRST)
        self.assertEqual(down.label, PassageLabel.DOWN_FIRST)
        self.assertEqual(both.label, PassageLabel.BOTH_SAME_MINUTE)
        self.assertEqual(up.passage_market_minute_ordinal, 101)
        self.assertEqual(down.passage_market_minute_ordinal, 101)
        self.assertEqual(both.passage_market_minute_ordinal, 101)

    def test_anchor_bar_is_not_part_of_the_future_label_window(self) -> None:
        anchor = _anchor(log_low=9.0, log_high=11.0)
        future = tuple(_future_bar(offset) for offset in range(1, 6))

        result = label_first_passage(
            anchor,
            _sigma_history() + future,
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(result.label, PassageLabel.NO_PASSAGE)

    def test_sigma_is_ex_ante_robust_and_ignores_future_returns(self) -> None:
        future = tuple(
            _future_bar(
                offset,
                signed_return=100.0 if offset % 2 else -100.0,
            )
            for offset in range(1, 6)
        )

        result = label_first_passage(
            _anchor(),
            _sigma_history() + future,
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(result.label, PassageLabel.NO_PASSAGE)
        expected_sigma = 0.014826 * math.sqrt(5.0)
        self.assertAlmostEqual(result.sigma, expected_sigma, places=12)
        self.assertAlmostEqual(
            result.upper_barrier,
            10.0 + 2.0 * expected_sigma,
            places=12,
        )
        self.assertAlmostEqual(
            result.lower_barrier,
            10.0 - 2.0 * expected_sigma,
            places=12,
        )

    def test_each_horizon_has_an_explicit_sqrt_market_minute_sigma(self) -> None:
        cases = (
            (
                LabelHorizon.MINUTES_5,
                5,
                tuple(_future_bar(offset) for offset in range(1, 6)),
            ),
            (
                LabelHorizon.MINUTES_30,
                30,
                tuple(_future_bar(offset) for offset in range(1, 31)),
            ),
            (
                LabelHorizon.MINUTES_120,
                120,
                tuple(_future_bar(offset) for offset in range(1, 121)),
            ),
            (
                LabelHorizon.SESSION_1,
                390,
                (
                    *(_future_bar(offset) for offset in range(1, 5)),
                    _future_bar(5, session_ordinal=41, minute_of_day=599),
                    _future_bar(6, session_ordinal=41, minute_of_day=600),
                ),
            ),
        )
        for horizon, market_minutes, future in cases:
            with self.subTest(horizon=horizon):
                result = label_first_passage(
                    _anchor(),
                    _sigma_history() + future,
                    horizon,
                )
                expected_sigma = 0.014826 * math.sqrt(float(market_minutes))

                self.assertEqual(
                    result.sigma_horizon_market_minutes,
                    market_minutes,
                )
                self.assertAlmostEqual(result.sigma, expected_sigma, places=12)
                self.assertAlmostEqual(
                    result.upper_barrier,
                    10.0 + 2.0 * expected_sigma,
                    places=12,
                )

    def test_sigma_requires_forty_pre_anchor_values_and_positive_mad(self) -> None:
        future = tuple(_future_bar(offset) for offset in range(1, 6))

        insufficient = label_first_passage(
            _anchor(),
            _sigma_history(39) + future,
            LabelHorizon.MINUTES_5,
        )
        zero_variation = label_first_passage(
            _anchor(),
            _sigma_history(zero_variation=True) + future,
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(insufficient.label, PassageLabel.SIGMA_NOT_ESTIMABLE)
        self.assertEqual(zero_variation.label, PassageLabel.SIGMA_NOT_ESTIMABLE)
        self.assertIsNone(insufficient.sigma)
        self.assertIsNone(zero_variation.sigma)

    def test_minute_horizons_require_complete_market_minute_coverage(self) -> None:
        cases = (
            (LabelHorizon.MINUTES_5, 5),
            (LabelHorizon.MINUTES_30, 30),
            (LabelHorizon.MINUTES_120, 120),
        )
        for horizon, minute_count in cases:
            with self.subTest(horizon=horizon):
                complete = tuple(
                    _future_bar(offset) for offset in range(1, minute_count + 1)
                )
                incomplete = complete[:-1]

                self.assertEqual(
                    label_first_passage(
                        _anchor(),
                        _sigma_history() + complete,
                        horizon,
                    ).label,
                    PassageLabel.NO_PASSAGE,
                )
                self.assertEqual(
                    label_first_passage(
                        _anchor(),
                        _sigma_history() + incomplete,
                        horizon,
                    ).label,
                    PassageLabel.CENSORED,
                )

    def test_missing_internal_market_minute_is_censored(self) -> None:
        future = tuple(_future_bar(offset) for offset in (1, 3, 4, 5))

        result = label_first_passage(
            _anchor(),
            _sigma_history() + future,
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(result.label, PassageLabel.CENSORED)

    def test_one_session_horizon_ends_at_same_minute_next_session(self) -> None:
        future_before_endpoint = (
            *(_future_bar(offset) for offset in range(1, 5)),
            _future_bar(5, session_ordinal=41, minute_of_day=599),
        )
        endpoint = _future_bar(
            6,
            session_ordinal=41,
            minute_of_day=600,
            log_high=10.7,
        )

        completed = label_first_passage(
            _anchor(),
            _sigma_history() + future_before_endpoint + (endpoint,),
            LabelHorizon.SESSION_1,
        )
        censored = label_first_passage(
            _anchor(),
            _sigma_history() + future_before_endpoint,
            LabelHorizon.SESSION_1,
        )

        self.assertEqual(completed.label, PassageLabel.UP_FIRST)
        self.assertEqual(completed.passage_market_minute_ordinal, 106)
        self.assertEqual(censored.label, PassageLabel.CENSORED)


if __name__ == "__main__":
    unittest.main()
