from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from rp001_s2.direction_neutral_overheat import (
    CompetitivePathLabel,
    DirectionNeutralObservation,
    LabelHorizon,
    OverheatBurst,
    OverheatEpisode,
    label_competitive_path,
)


_ORIGIN = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _observation(
    ordinal: int,
    *,
    signed_return: float = 0.0,
    low: float = 9.99,
    high: float = 10.01,
) -> DirectionNeutralObservation:
    minute_end = _ORIGIN + timedelta(minutes=ordinal)
    return DirectionNeutralObservation(
        symbol="AAPL",
        session_ordinal=0,
        minute_of_day=ordinal,
        market_minute_ordinal=ordinal,
        minute_end_utc=minute_end,
        available_at_utc=minute_end + timedelta(seconds=1),
        session_id="2020-01-01",
        session_date=date(2020, 1, 1),
        source_window_sha256="a" * 64,
        signed_return=signed_return,
        log_low=low,
        log_high=high,
        log_close=10.0,
        family_scores={"range": 0.0},
    )


def _history() -> tuple[DirectionNeutralObservation, ...]:
    return tuple(
        _observation(
            ordinal,
            signed_return=-0.01 if ordinal % 2 == 0 else 0.01,
        )
        for ordinal in range(40)
    )


def _anchor() -> DirectionNeutralObservation:
    return _observation(100)


def _future(
    *,
    up_at: int | None = None,
    down_at: int | None = None,
    both_at: int | None = None,
) -> tuple[DirectionNeutralObservation, ...]:
    bars: list[DirectionNeutralObservation] = []
    for offset in range(1, 6):
        low = 9.99
        high = 10.01
        if offset == up_at:
            high = 10.08
        if offset == down_at:
            low = 9.92
        if offset == both_at:
            low = 9.92
            high = 10.08
        bars.append(_observation(100 + offset, low=low, high=high))
    return tuple(bars)


def _episode(
    anchor: DirectionNeutralObservation,
    *,
    closed_at: int | None,
    coverage_complete: bool = True,
) -> OverheatEpisode:
    return OverheatEpisode(
        anchor=anchor,
        bursts=(OverheatBurst((anchor.market_minute_ordinal,)),),
        closed_at_market_minute_ordinal=closed_at,
        coverage_complete=coverage_complete,
        right_censored=closed_at is None,
    )


class CompetitivePathLabelTest(unittest.TestCase):
    def test_direction_is_assigned_only_after_direction_neutral_anchor(self) -> None:
        anchor = _anchor()
        cases = (
            (
                _future(up_at=1),
                CompetitivePathLabel.UPSIDE_ACCELERATION,
            ),
            (
                _future(down_at=1),
                CompetitivePathLabel.DOWNSIDE_ACCELERATION,
            ),
            (
                _future(up_at=1, down_at=3),
                CompetitivePathLabel.UP_THEN_DOWN_REVERSAL,
            ),
            (
                _future(down_at=1, up_at=3),
                CompetitivePathLabel.DOWN_THEN_UP_REVERSAL,
            ),
        )

        for future, expected in cases:
            with self.subTest(expected=expected):
                result = label_competitive_path(
                    anchor,
                    _history() + future,
                    _episode(anchor, closed_at=None),
                    LabelHorizon.MINUTES_5,
                )

                self.assertEqual(result.label, expected)
                self.assertEqual(result.horizon, LabelHorizon.MINUTES_5)

    def test_no_passage_is_persistence_or_normalization_from_episode_state(self) -> None:
        anchor = _anchor()
        observations = _history() + _future()

        persistent = label_competitive_path(
            anchor,
            observations,
            _episode(anchor, closed_at=None),
            LabelHorizon.MINUTES_5,
        )
        normalized = label_competitive_path(
            anchor,
            observations,
            _episode(anchor, closed_at=104),
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(
            persistent.label,
            CompetitivePathLabel.VOLATILE_PERSISTENCE,
        )
        self.assertEqual(normalized.label, CompetitivePathLabel.NORMALIZATION)

    def test_same_bar_order_missing_future_and_incomplete_episode_are_unidentified(self) -> None:
        anchor = _anchor()
        cases = (
            (_history() + _future(both_at=1), _episode(anchor, closed_at=None)),
            (_history() + _future()[:-1], _episode(anchor, closed_at=None)),
            (
                _history() + _future(),
                _episode(anchor, closed_at=None, coverage_complete=False),
            ),
        )

        for observations, episode in cases:
            result = label_competitive_path(
                anchor,
                observations,
                episode,
                LabelHorizon.MINUTES_5,
            )

            self.assertEqual(
                result.label,
                CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE,
            )
            self.assertIsNotNone(result.reason)

    def test_future_returns_do_not_change_ex_ante_barriers(self) -> None:
        anchor = _anchor()
        ordinary = label_competitive_path(
            anchor,
            _history() + _future(),
            _episode(anchor, closed_at=None),
            LabelHorizon.MINUTES_5,
        )
        extreme_future = tuple(
            DirectionNeutralObservation(
                **{
                    **bar.__dict__,
                    "signed_return": 100.0 if index % 2 else -100.0,
                }
            )
            for index, bar in enumerate(_future())
        )
        repeated = label_competitive_path(
            anchor,
            _history() + extreme_future,
            _episode(anchor, closed_at=None),
            LabelHorizon.MINUTES_5,
        )

        self.assertEqual(ordinary.lower_barrier, repeated.lower_barrier)
        self.assertEqual(ordinary.upper_barrier, repeated.upper_barrier)


if __name__ == "__main__":
    unittest.main()
