from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid_denominator = denominator.where(denominator != 0.0)
    return numerator / valid_denominator


def _clip_unit(values: pd.Series) -> pd.Series:
    return values.clip(lower=0.0, upper=1.0)


def past_only_midrank_percentile(
    values: pd.Series,
    minimum_sessions: int = 60,
    maximum_sessions: int = 252,
) -> pd.Series:
    """Return a causal midrank percentile against prior finite observations."""
    if minimum_sessions <= 0 or maximum_sessions < minimum_sessions:
        raise ValueError("Invalid percentile reference window")

    numeric_values = pd.to_numeric(values, errors="coerce").astype(float)
    result = pd.Series(np.nan, index=numeric_values.index, dtype=float)

    for position, current_value in enumerate(numeric_values.to_numpy()):
        if not np.isfinite(current_value):
            continue

        window_start = max(0, position - maximum_sessions)
        prior_values = numeric_values.iloc[window_start:position].to_numpy()
        prior_values = prior_values[np.isfinite(prior_values)]
        if len(prior_values) < minimum_sessions:
            continue

        count_less = int(np.count_nonzero(prior_values < current_value))
        count_equal = int(np.count_nonzero(prior_values == current_value))
        result.iloc[position] = (
            count_less + 0.5 * count_equal
        ) / len(prior_values)

    return result


@dataclass(frozen=True)
class CompositeScoreDefinition:
    identifier: str
    weights: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Composite identifier is required")
        if not self.weights:
            raise ValueError("Composite weights are required")
        if any(not np.isfinite(weight) or weight < 0.0 for weight in self.weights.values()):
            raise ValueError("Composite weights must be finite and non-negative")
        if not math.isclose(
            sum(self.weights.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("Composite weights must sum to one")

    def score(self, features: pd.DataFrame) -> pd.Series:
        missing_columns = set(self.weights) - set(features.columns)
        if missing_columns:
            raise KeyError(f"Missing composite components: {sorted(missing_columns)}")

        components = features.loc[:, list(self.weights)].astype(float)
        finite = components.notna().all(axis=1)
        available_values = components.where(finite).stack()
        if not available_values.empty and not available_values.between(0.0, 1.0).all():
            raise ValueError("Composite components must be in the unit interval")

        weighted = components.mul(pd.Series(self.weights), axis="columns")
        return 100.0 * weighted.sum(axis=1, min_count=len(self.weights))


class DailyFeatureEngine:
    MODEL_FEATURE_NAMES = (
        "returnImpulse",
        "returnAccel",
        "volumeSurprise",
        "rangeChase",
        "vwapPersistenceProxy",
        "pullbackHold",
        "downMoveImpulse",
        "vwapDownPressure",
        "breakdownCascade",
        "liquidityProxy",
        "profitBreadth",
        "profitGainMass",
        "vwapExtension",
        "momentum5",
        "volume20",
        "breakout20",
        "drawdown3",
        "lowBreak20",
        "runup20",
        "single_session_rebound",
        "two_session_persistence_and_no_new_low",
        "rebound",
        "persistence",
        "noNewLow",
    )
    VOLUME_DEPENDENT_FEATURES = frozenset(
        {
            "volumeSurprise",
            "volume20",
            "vwap20",
            "vwapPersistenceProxy",
            "vwapDownPressure",
            "liquidityProxy",
            "profitBreadth",
            "profitGainMass",
            "vwapExtension",
        }
    )

    def __init__(
        self,
        percentile_minimum_sessions: int = 60,
        percentile_maximum_sessions: int = 252,
    ) -> None:
        if percentile_minimum_sessions <= 0:
            raise ValueError("Percentile minimum sessions must be positive")
        if percentile_maximum_sessions < percentile_minimum_sessions:
            raise ValueError("Percentile maximum must not be smaller than minimum")
        self.percentile_minimum_sessions = percentile_minimum_sessions
        self.percentile_maximum_sessions = percentile_maximum_sessions

    def compute(self, candles: pd.DataFrame) -> pd.DataFrame:
        market = self._validated_market_frame(candles)
        features = pd.DataFrame(index=market.index)
        close = market["close"]
        high = market["high"]
        low = market["low"]
        volume = market["volume"]

        log_return = np.log(close / close.shift(1))
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1).where(previous_close.notna())
        atr14 = true_range.rolling(14, min_periods=14).mean()
        rv20 = log_return.shift(1).rolling(20, min_periods=20).std(ddof=0)
        high_previous_20 = high.shift(1).rolling(20, min_periods=20).max()
        low_previous_20 = low.shift(1).rolling(20, min_periods=20).min()
        median_volume_previous_20 = volume.shift(1).rolling(20, min_periods=20).median()

        features["atr14"] = atr14
        features["rv20"] = rv20
        features["highPrev20"] = high_previous_20
        features["lowPrev20"] = low_previous_20
        features["logReturn"] = log_return

        return_impulse_raw = _safe_divide(
            np.log(close / close.shift(5)).clip(lower=0.0),
            rv20 * math.sqrt(5.0),
        )
        return_acceleration_raw = _safe_divide(
            (log_return - log_return.shift(1).rolling(5, min_periods=5).mean()).clip(
                lower=0.0
            ),
            rv20,
        )
        volume_surprise_raw = _safe_divide(volume, median_volume_previous_20)

        features["returnImpulse"] = self._percentile(return_impulse_raw)
        features["returnAccel"] = self._percentile(return_acceleration_raw)
        features["volumeSurprise"] = self._percentile(volume_surprise_raw)

        range_position = _safe_divide(
            close - low_previous_20,
            high_previous_20 - low_previous_20,
        )
        high_break = _safe_divide(close - high_previous_20, atr14)
        features["rangeChase"] = (
            0.6 * _clip_unit(range_position) + 0.4 * _clip_unit(high_break)
        )

        typical_price = (high + low + close) / 3.0
        vwap20 = _safe_divide(
            (typical_price * volume).rolling(20, min_periods=20).sum(),
            volume.rolling(20, min_periods=20).sum(),
        )
        above_vwap_volume = volume.where(
            typical_price > vwap20,
            0.0,
        ).where(vwap20.notna())
        below_vwap_volume = volume.where(
            typical_price < vwap20,
            0.0,
        ).where(vwap20.notna())
        rolling_volume_5 = volume.rolling(5, min_periods=5).sum()
        features["typicalPrice"] = typical_price
        features["vwap20"] = vwap20
        features["vwapPersistenceProxy"] = _clip_unit(
            _safe_divide(
                above_vwap_volume.rolling(5, min_periods=5).sum(),
                rolling_volume_5,
            )
        )
        features["pullbackHold"] = 1.0 - _clip_unit(
            _safe_divide(high_previous_20 - close, atr14)
        )

        down_move_raw = _safe_divide(
            (-np.log(close / close.shift(3))).clip(lower=0.0),
            rv20 * math.sqrt(3.0),
        )
        features["downMoveImpulse"] = self._percentile(down_move_raw)
        features["vwapDownPressure"] = (
            0.5 * _clip_unit(_safe_divide(vwap20 - close, atr14))
            + 0.5
            * _clip_unit(
                _safe_divide(
                    below_vwap_volume.rolling(5, min_periods=5).sum(),
                    rolling_volume_5,
                )
            )
        )

        new_low = (low < low_previous_20).astype(float).where(low_previous_20.notna())
        new_low_count_5 = new_low.rolling(5, min_periods=5).sum()
        features["newLowCount5"] = new_low_count_5
        features["breakdownCascade"] = (
            0.6 * _clip_unit(_safe_divide(low_previous_20 - close, atr14))
            + 0.4 * self._percentile(new_low_count_5)
        )

        liquidity_raw = _safe_divide(log_return.abs(), close * volume)
        features["liquidityProxy"] = self._percentile(liquidity_raw)

        features["profitBreadth"] = self._profit_breadth(
            close,
            typical_price,
            volume,
        )
        features["profitGainMass"] = self._profit_gain_mass(
            close,
            typical_price,
            volume,
            atr14,
        )
        features["vwapExtension"] = _clip_unit(_safe_divide(close - vwap20, atr14))

        features["momentum5"] = self._percentile(np.log(close / close.shift(5)))
        features["volume20"] = features["volumeSurprise"]
        features["breakout20"] = _clip_unit(_safe_divide(close - high_previous_20, atr14))
        features["drawdown3"] = features["downMoveImpulse"]
        features["lowBreak20"] = _clip_unit(_safe_divide(low_previous_20 - close, atr14))
        runup_numerator = close / close.shift(20) - 1.0
        runup_denominator = 2.0 * atr14 / close
        features["runup20"] = _clip_unit(_safe_divide(runup_numerator, runup_denominator))

        lower_wick = _safe_divide(close - low, high - low)
        recent_low = low.rolling(5, min_periods=5).min()
        rebound = _clip_unit(_safe_divide(close - recent_low, atr14))
        single_rebound = 0.5 * _clip_unit(lower_wick) + 0.5 * rebound
        persistence = (
            (close > close.shift(1)) & (close.shift(1) > close.shift(2))
        ).astype(float).where(close.shift(2).notna())
        no_new_low = (low >= low.shift(1)).astype(float).where(low.shift(1).notna())
        gate = persistence * no_new_low
        features["single_session_rebound"] = single_rebound
        features["two_session_persistence_and_no_new_low"] = single_rebound * gate
        features["rebound"] = rebound
        features["persistence"] = persistence
        features["noNewLow"] = no_new_low

        zero_signal_volume = volume == 0.0
        features.loc[
            zero_signal_volume,
            list(self.VOLUME_DEPENDENT_FEATURES),
        ] = np.nan

        return features

    def _percentile(self, values: pd.Series) -> pd.Series:
        return past_only_midrank_percentile(
            values,
            minimum_sessions=self.percentile_minimum_sessions,
            maximum_sessions=self.percentile_maximum_sessions,
        )

    @staticmethod
    def _validated_market_frame(candles: pd.DataFrame) -> pd.DataFrame:
        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = set(required_columns) - set(candles.columns)
        if missing_columns:
            raise ValueError(f"Missing candle columns: {sorted(missing_columns)}")
        if not candles.index.is_monotonic_increasing or candles.index.has_duplicates:
            raise ValueError("Candle index must be unique and ascending")

        market = candles.loc[:, required_columns].apply(pd.to_numeric, errors="raise")
        if not np.isfinite(market.to_numpy()).all():
            raise ValueError("Candles must contain finite numbers")
        if (market[["open", "high", "low", "close"]] <= 0.0).any().any():
            raise ValueError("Candle prices must be positive")
        if (market["volume"] < 0.0).any():
            raise ValueError("Candle volume must be non-negative")
        if (market["high"] < market[["open", "close", "low"]].max(axis=1)).any():
            raise ValueError("Candle high violates OHLC ordering")
        if (market["low"] > market[["open", "close", "high"]].min(axis=1)).any():
            raise ValueError("Candle low violates OHLC ordering")
        return market.astype(float)

    @staticmethod
    def _profit_breadth(
        close: pd.Series,
        typical_price: pd.Series,
        volume: pd.Series,
    ) -> pd.Series:
        result = pd.Series(np.nan, index=close.index, dtype=float)
        for position in range(119, len(close)):
            window_price = typical_price.iloc[position - 119 : position + 1]
            window_volume = volume.iloc[position - 119 : position + 1]
            denominator = window_volume.sum()
            if denominator > 0.0:
                result.iloc[position] = window_volume.where(
                    window_price < close.iloc[position],
                    0.0,
                ).sum() / denominator
        return _clip_unit(result)

    @staticmethod
    def _profit_gain_mass(
        close: pd.Series,
        typical_price: pd.Series,
        volume: pd.Series,
        atr14: pd.Series,
    ) -> pd.Series:
        result = pd.Series(np.nan, index=close.index, dtype=float)
        for position in range(119, len(close)):
            current_atr = atr14.iloc[position]
            window_price = typical_price.iloc[position - 119 : position + 1]
            window_volume = volume.iloc[position - 119 : position + 1]
            denominator = window_volume.sum() * current_atr
            if denominator > 0.0 and np.isfinite(denominator):
                gains = (close.iloc[position] - window_price).clip(lower=0.0)
                result.iloc[position] = (window_volume * gains).sum() / denominator
        return _clip_unit(result)


@dataclass(frozen=True)
class CandidateDefinition:
    identifier: str
    family: str
    kind: str
    formula: str | None
    weights: Mapping[str, float] | None
    primary_outcome: str
    outcome_ids: tuple[str, ...]
    applicable_horizons: tuple[int, ...]
    outcome_applicable_horizons: Mapping[str, tuple[int, ...]] | None = None

    def __post_init__(self) -> None:
        if not self.identifier or not self.family:
            raise ValueError("Candidate identifier and family are required")
        if self.weights is None and self.formula is None:
            raise ValueError("Candidate requires either a formula or weights")
        if self.weights is not None and self.formula is not None:
            raise ValueError("Candidate cannot combine a formula and weights")
        if not self.outcome_ids or self.primary_outcome not in self.outcome_ids:
            raise ValueError("Candidate primary outcome must be registered")
        if not self.applicable_horizons or any(
            horizon <= 0 for horizon in self.applicable_horizons
        ):
            raise ValueError("Candidate horizons must be positive")
        if self.outcome_applicable_horizons is not None:
            unknown_outcomes = set(self.outcome_applicable_horizons) - set(
                self.outcome_ids
            )
            if unknown_outcomes:
                raise ValueError("Outcome horizon map contains an unknown outcome")

    def horizons_for_outcome(self, outcome_id: str) -> tuple[int, ...]:
        if outcome_id not in self.outcome_ids:
            return ()
        if (
            self.outcome_applicable_horizons is not None
            and outcome_id in self.outcome_applicable_horizons
        ):
            mapped = self.outcome_applicable_horizons[outcome_id]
            return tuple(
                horizon for horizon in self.applicable_horizons if horizon in mapped
            )
        return self.applicable_horizons


class CandidateRegistry:
    def __init__(self, candidates: Sequence[CandidateDefinition]) -> None:
        identifiers = [candidate.identifier for candidate in candidates]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Candidate identifiers must be unique")
        self._candidates = tuple(candidates)

    @property
    def candidates(self) -> tuple[CandidateDefinition, ...]:
        return self._candidates

    def score_all(self, features: pd.DataFrame) -> pd.DataFrame:
        scores = pd.DataFrame(index=features.index)
        for candidate in self._candidates:
            if candidate.weights is not None:
                score = CompositeScoreDefinition(
                    candidate.identifier,
                    candidate.weights,
                ).score(features)
            else:
                assert candidate.formula is not None
                if candidate.formula not in features:
                    raise KeyError(
                        f"Missing candidate formula feature: {candidate.formula}"
                    )
                component = pd.to_numeric(features[candidate.formula], errors="coerce")
                available = component.dropna()
                if not available.empty and not available.between(0.0, 1.0).all():
                    raise ValueError(
                        f"Candidate formula {candidate.formula} is outside the unit interval"
                    )
                score = 100.0 * component
            scores[candidate.identifier] = score
        return scores


@dataclass(frozen=True)
class BarrierDefinition:
    target_direction: str
    target_atr_multiple: float
    opposite_direction: str
    opposite_atr_multiple: float

    def __post_init__(self) -> None:
        valid_directions = {"upper", "lower"}
        if self.target_direction not in valid_directions:
            raise ValueError("Invalid target direction")
        if self.opposite_direction not in valid_directions:
            raise ValueError("Invalid opposite direction")
        if self.target_direction == self.opposite_direction:
            raise ValueError("Barrier directions must be opposite")
        if self.target_atr_multiple <= 0.0 or self.opposite_atr_multiple <= 0.0:
            raise ValueError("ATR barrier multiples must be positive")


@dataclass(frozen=True)
class BarrierOutcome:
    status: str
    first_passage_offset: int | None

    @property
    def observed_label(self) -> float | None:
        if self.status == "success":
            return 1.0
        if self.status == "failure":
            return 0.0
        return None


class BarrierOutcomeEvaluator:
    def evaluate(
        self,
        signal_close: float,
        signal_atr: float,
        future_candles: pd.DataFrame,
        definition: BarrierDefinition,
        requested_horizon: int,
    ) -> BarrierOutcome:
        if requested_horizon <= 0:
            raise ValueError("Requested horizon must be positive")
        if not np.isfinite(signal_close) or not np.isfinite(signal_atr) or signal_atr <= 0.0:
            return BarrierOutcome("unavailable_excluded", None)
        if not {"high", "low"}.issubset(future_candles.columns):
            raise ValueError("Future candles require high and low")

        observed = future_candles.iloc[:requested_horizon]
        if len(observed) < requested_horizon:
            return BarrierOutcome("right_censored_excluded", None)
        target_barrier = self._barrier_price(
            signal_close,
            signal_atr,
            definition.target_direction,
            definition.target_atr_multiple,
        )
        opposite_barrier = self._barrier_price(
            signal_close,
            signal_atr,
            definition.opposite_direction,
            definition.opposite_atr_multiple,
        )

        for offset, (_, candle) in enumerate(observed.iterrows(), start=1):
            target_hit = self._is_hit(candle, definition.target_direction, target_barrier)
            opposite_hit = self._is_hit(candle, definition.opposite_direction, opposite_barrier)
            if target_hit and opposite_hit:
                return BarrierOutcome("ambiguous_excluded", offset)
            if target_hit:
                return BarrierOutcome("success", offset)
            if opposite_hit:
                return BarrierOutcome("failure", offset)

        return BarrierOutcome("failure", None)

    @staticmethod
    def _barrier_price(
        signal_close: float,
        signal_atr: float,
        direction: str,
        multiple: float,
    ) -> float:
        signed_distance = signal_atr * multiple
        return signal_close + signed_distance if direction == "upper" else signal_close - signed_distance

    @staticmethod
    def _is_hit(candle: pd.Series, direction: str, barrier: float) -> bool:
        if direction == "upper":
            return float(candle["high"]) >= barrier
        return float(candle["low"]) <= barrier


@dataclass(frozen=True)
class OutcomeDefinition:
    identifier: str
    barrier: BarrierDefinition
    applicable_horizons: tuple[int, ...] = (1, 3, 5, 10)

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("Outcome identifier is required")
        if not self.applicable_horizons:
            raise ValueError("Outcome requires at least one horizon")


class OutcomeLabelEngine:
    def __init__(self, definitions: Mapping[str, OutcomeDefinition]) -> None:
        if set(definitions) != {
            definition.identifier for definition in definitions.values()
        }:
            raise ValueError("Outcome mapping keys must match identifiers")
        self._definitions = dict(definitions)
        self._evaluator = BarrierOutcomeEvaluator()

    def label(
        self,
        candles: pd.DataFrame,
        atr: pd.Series,
        outcome_id: str,
        horizon: int,
        eligibility: pd.Series | None = None,
    ) -> pd.DataFrame:
        if outcome_id not in self._definitions:
            raise KeyError(f"Unknown outcome definition: {outcome_id}")
        definition = self._definitions[outcome_id]
        if horizon not in definition.applicable_horizons:
            raise ValueError(f"Outcome {outcome_id} is not applicable at horizon {horizon}")
        if not candles.index.equals(atr.index):
            raise ValueError("ATR index must match candles")
        if eligibility is not None and not candles.index.equals(eligibility.index):
            raise ValueError("Eligibility index must match candles")

        records: list[dict[str, object]] = []
        for position, index in enumerate(candles.index):
            eligibility_status = (
                "eligible"
                if eligibility is None
                else _read_eligibility_status(eligibility.loc[index])
            )
            if eligibility_status == "unavailable":
                outcome = BarrierOutcome("unavailable_excluded", None)
            elif eligibility_status == "ineligible":
                outcome = BarrierOutcome("ineligible_excluded", None)
            else:
                future = candles.iloc[position + 1 : position + 1 + horizon]
                outcome = self._evaluator.evaluate(
                    signal_close=float(candles.iloc[position]["close"]),
                    signal_atr=float(atr.iloc[position]),
                    future_candles=future,
                    definition=definition.barrier,
                    requested_horizon=horizon,
                )
            records.append(
                {
                    "status": outcome.status,
                    "label": outcome.observed_label,
                    "firstPassageOffset": outcome.first_passage_offset,
                }
            )
        return pd.DataFrame(records, index=candles.index)


class ReliefOutcomeLabelEngine:
    CONFIRMED_HORIZONS = (3, 5, 10)
    FAKE_RELIEF_HORIZONS = (5, 10)

    def label(
        self,
        candles: pd.DataFrame,
        atr: pd.Series,
        outcome_id: str,
        horizon: int,
        eligibility: pd.Series,
    ) -> pd.DataFrame:
        if outcome_id not in {"reliefConfirmed", "fakeRelief"}:
            raise ValueError("Unsupported relief outcome")
        applicable_horizons = (
            self.CONFIRMED_HORIZONS
            if outcome_id == "reliefConfirmed"
            else self.FAKE_RELIEF_HORIZONS
        )
        if horizon not in applicable_horizons:
            raise ValueError("Relief outcome is not applicable at this horizon")
        if not candles.index.equals(atr.index) or not candles.index.equals(eligibility.index):
            raise ValueError("Relief inputs must share the candle index")

        records: list[dict[str, object]] = []
        for position, index in enumerate(candles.index):
            eligibility_status = _read_eligibility_status(eligibility.loc[index])
            if eligibility_status == "unavailable":
                records.append(self._record("unavailable_excluded"))
                continue
            if position < 5 or eligibility_status == "ineligible":
                records.append(self._record("ineligible_excluded"))
                continue
            signal_close = float(candles.iloc[position]["close"])
            signal_atr = float(atr.iloc[position])
            if not np.isfinite(signal_atr) or signal_atr <= 0.0:
                records.append(self._record("unavailable_excluded"))
                continue

            episode_low = float(candles["low"].iloc[position - 5 : position + 1].min())
            selloff_reference_high = float(
                candles["close"].iloc[position - 5 : position].max()
            )
            midpoint_recovery = episode_low + 0.5 * (
                selloff_reference_high - episode_low
            )
            future = candles.iloc[position + 1 : position + 1 + horizon]
            if len(future) < horizon:
                record = self._record("right_censored_excluded")
            elif outcome_id == "reliefConfirmed":
                record = self._confirmed_relief(
                    signal_close,
                    signal_atr,
                    future,
                    horizon,
                    episode_low,
                    midpoint_recovery,
                )
            else:
                record = self._fake_relief(
                    signal_close,
                    signal_atr,
                    future,
                    horizon,
                    episode_low,
                    midpoint_recovery,
                )
            record["episodeLow"] = episode_low
            record["midpointRecovery"] = midpoint_recovery
            records.append(record)
        return pd.DataFrame(records, index=candles.index)

    def _confirmed_relief(
        self,
        signal_close: float,
        signal_atr: float,
        future: pd.DataFrame,
        horizon: int,
        episode_low: float,
        midpoint_recovery: float,
    ) -> dict[str, object]:
        base_deadline = horizon - 2
        passage_status, passage_offset = self._first_rebound_passage(
            signal_close,
            signal_atr,
            future.iloc[:base_deadline],
        )
        if passage_status == "ambiguous_excluded":
            return self._record(passage_status, first_passage_offset=passage_offset)
        if passage_status == "opposite_first":
            return self._record("failure", first_passage_offset=passage_offset)
        if passage_status == "no_passage":
            status = "failure" if len(future) >= base_deadline else "right_censored_excluded"
            return self._record(status)

        assert passage_offset is not None
        confirmation_end = passage_offset + 2
        available_confirmation = future.iloc[
            passage_offset:min(confirmation_end, len(future))
        ]
        for confirmation_index, (_, candle) in enumerate(
            available_confirmation.iterrows(),
            start=passage_offset + 1,
        ):
            if (
                float(candle["low"]) < episode_low
                or float(candle["close"]) < midpoint_recovery
            ):
                return self._record(
                    "failure",
                    first_passage_offset=passage_offset,
                    terminal_offset=confirmation_index,
                )
        if len(future) < confirmation_end:
            return self._record(
                "right_censored_excluded",
                first_passage_offset=passage_offset,
            )
        return self._record(
            "success",
            first_passage_offset=passage_offset,
            confirmation_offset=confirmation_end,
            terminal_offset=confirmation_end,
        )

    def _fake_relief(
        self,
        signal_close: float,
        signal_atr: float,
        future: pd.DataFrame,
        horizon: int,
        episode_low: float,
        midpoint_recovery: float,
    ) -> dict[str, object]:
        base_deadline = horizon - 3
        passage_status, passage_offset = self._first_rebound_passage(
            signal_close,
            signal_atr,
            future.iloc[:base_deadline],
        )
        if passage_status == "ambiguous_excluded":
            return self._record(passage_status, first_passage_offset=passage_offset)
        if passage_status == "opposite_first":
            return self._record("failure", first_passage_offset=passage_offset)
        if passage_status == "no_passage":
            status = "failure" if len(future) >= base_deadline else "right_censored_excluded"
            return self._record(status)

        assert passage_offset is not None
        post_rebound_end = passage_offset + 3
        if len(future) < post_rebound_end:
            return self._record(
                "right_censored_excluded",
                first_passage_offset=passage_offset,
            )
        confirmation_streak = 0
        for offset in range(passage_offset + 1, min(len(future), post_rebound_end) + 1):
            candle = future.iloc[offset - 1]
            if float(candle["low"]) < episode_low:
                return self._record(
                    "success",
                    first_passage_offset=passage_offset,
                    terminal_offset=offset,
                )
            if (
                float(candle["low"]) >= episode_low
                and float(candle["close"]) >= midpoint_recovery
            ):
                confirmation_streak += 1
            else:
                confirmation_streak = 0
            if confirmation_streak == 2:
                return self._record(
                    "failure",
                    first_passage_offset=passage_offset,
                    confirmation_offset=offset,
                    terminal_offset=offset,
                )

        return self._record(
            "failure",
            first_passage_offset=passage_offset,
            terminal_offset=post_rebound_end,
        )

    @staticmethod
    def _first_rebound_passage(
        signal_close: float,
        signal_atr: float,
        future: pd.DataFrame,
    ) -> tuple[str, int | None]:
        target = signal_close + 0.75 * signal_atr
        opposite = signal_close - 0.5 * signal_atr
        for offset, (_, candle) in enumerate(future.iterrows(), start=1):
            target_hit = float(candle["high"]) >= target
            opposite_hit = float(candle["low"]) <= opposite
            if target_hit and opposite_hit:
                return "ambiguous_excluded", offset
            if target_hit:
                return "target_first", offset
            if opposite_hit:
                return "opposite_first", offset
        return "no_passage", None

    @staticmethod
    def _record(
        status: str,
        first_passage_offset: int | None = None,
        confirmation_offset: int | None = None,
        terminal_offset: int | None = None,
    ) -> dict[str, object]:
        label: float | None
        if status == "success":
            label = 1.0
        elif status == "failure":
            label = 0.0
        else:
            label = None
        return {
            "status": status,
            "label": label,
            "firstPassageOffset": first_passage_offset,
            "confirmationOffset": confirmation_offset,
            "terminalOffset": terminal_offset,
            "episodeLow": None,
            "midpointRecovery": None,
        }


class EventEpisodeCatalog:
    def select_starts(self, signals: pd.Series, horizon: int) -> pd.Index:
        if horizon <= 0:
            raise ValueError("Episode horizon must be positive")
        starts: list[object] = []
        blocked_through_position = -1
        previous_signal = False
        for position, (index, signal) in enumerate(signals.fillna(False).items()):
            current_signal = bool(signal)
            is_upward_crossing = current_signal and not previous_signal
            if is_upward_crossing and position > blocked_through_position:
                starts.append(index)
                blocked_through_position = position + horizon
            previous_signal = current_signal
        return pd.Index(starts)


def _read_eligibility_status(value: object | None) -> str:
    if value is None:
        return "unavailable"
    try:
        if bool(pd.isna(value)):
            return "unavailable"
    except (TypeError, ValueError):
        return "unavailable"
    return "eligible" if bool(value) else "ineligible"


@dataclass(frozen=True)
class WalkForwardFold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_end: int
    excluded_training_ranges: tuple[tuple[int, int], ...] = ()

    @property
    def training_positions(self) -> tuple[int, ...]:
        return tuple(
            position
            for position in range(self.train_start, self.train_end)
            if not any(
                start <= position < end
                for start, end in self.excluded_training_ranges
            )
        )

    @property
    def train_size(self) -> int:
        return len(self.training_positions)

    @property
    def test_size(self) -> int:
        return self.test_end - self.test_start


class WalkForwardSplitter:
    def __init__(
        self,
        block_sessions: int = 120,
        purge_sessions: int = 10,
        embargo_sessions: int = 10,
    ) -> None:
        if block_sessions <= 0:
            raise ValueError("Block sessions must be positive")
        if purge_sessions < 0 or embargo_sessions < 0:
            raise ValueError("Purge and embargo must be non-negative")
        self.block_sessions = block_sessions
        self.purge_sessions = purge_sessions
        self.embargo_sessions = embargo_sessions

    def split(
        self,
        total_sessions: int,
        analysis_start: int,
        block_count: int,
    ) -> list[WalkForwardFold]:
        if analysis_start <= self.purge_sessions:
            raise ValueError("Insufficient pre-analysis training history")
        required_end = analysis_start + block_count * self.block_sessions
        if block_count <= 0 or required_end > total_sessions:
            raise ValueError("Analysis blocks exceed available sessions")

        folds: list[WalkForwardFold] = []
        prior_embargo_ranges: list[tuple[int, int]] = []
        for block_index in range(block_count):
            test_start = analysis_start + block_index * self.block_sessions
            test_end = test_start + self.block_sessions
            train_end = test_start - self.purge_sessions
            excluded_training_ranges = tuple(
                (max(0, start), min(train_end, end))
                for start, end in prior_embargo_ranges
                if start < train_end and end > 0
            )
            embargo_end = min(test_end + self.embargo_sessions, total_sessions)
            folds.append(
                WalkForwardFold(
                    train_start=0,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    embargo_end=embargo_end,
                    excluded_training_ranges=excluded_training_ranges,
                )
            )
            if embargo_end > test_end:
                prior_embargo_ranges.append((test_end, embargo_end))
        return folds


@dataclass(frozen=True)
class PosteriorSummary:
    mean: float
    median: float
    lower: float
    upper: float


class JeffreysPosterior:
    def __init__(self, successes: int, failures: int) -> None:
        if successes < 0 or failures < 0:
            raise ValueError("Success and failure counts must be non-negative")
        self.successes = successes
        self.failures = failures
        self.alpha = successes + 0.5
        self.beta = failures + 0.5

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def summary(self, credibility: float = 0.95) -> PosteriorSummary:
        if not 0.0 < credibility < 1.0:
            raise ValueError("Credibility must be between zero and one")
        tail = (1.0 - credibility) / 2.0
        return PosteriorSummary(
            mean=self.mean,
            median=_beta_quantile(0.5, self.alpha, self.beta),
            lower=_beta_quantile(tail, self.alpha, self.beta),
            upper=_beta_quantile(1.0 - tail, self.alpha, self.beta),
        )


def _continued_fraction_beta(a: float, b: float, x: float) -> float:
    maximum_iterations = 300
    epsilon = 3.0e-14
    minimum = np.finfo(float).tiny / epsilon
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < minimum:
        d = minimum
    d = 1.0 / d
    result = d

    for iteration in range(1, maximum_iterations + 1):
        even_step = 2 * iteration
        coefficient = iteration * (b - iteration) * x / (
            (qam + even_step) * (a + even_step)
        )
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        result *= d * c

        coefficient = -(a + iteration) * (qab + iteration) * x / (
            (a + even_step) * (qap + even_step)
        )
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            return result

    raise ArithmeticError("Beta continued fraction did not converge")


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _continued_fraction_beta(a, b, x) / a
    return 1.0 - front * _continued_fraction_beta(b, a, 1.0 - x) / b


def _beta_quantile(probability: float, a: float, b: float) -> float:
    if probability <= 0.0:
        return 0.0
    if probability >= 1.0:
        return 1.0
    lower = 0.0
    upper = 1.0
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if _regularized_incomplete_beta(midpoint, a, b) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _midranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    position = 0
    while position < len(values):
        end = position + 1
        while end < len(values) and values[order[end]] == values[order[position]]:
            end += 1
        rank = (position + 1 + end) / 2.0
        ranks[order[position:end]] = rank
        position = end
    return ranks


def binary_metrics(
    labels: Sequence[float] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
    sample_weights: Sequence[float] | np.ndarray | None = None,
    predicted_classes: Sequence[bool] | np.ndarray | None = None,
) -> dict[str, float | int | None]:
    observed = np.asarray(labels, dtype=float)
    predicted_probability = np.asarray(probabilities, dtype=float)
    weights = (
        np.ones(len(observed), dtype=float)
        if sample_weights is None
        else np.asarray(sample_weights, dtype=float)
    )
    raw_predicted_classes = (
        None
        if predicted_classes is None
        else np.asarray(predicted_classes, dtype=object)
    )
    if not (
        len(observed)
        == len(predicted_probability)
        == len(weights)
        == (
            len(observed)
            if raw_predicted_classes is None
            else len(raw_predicted_classes)
        )
    ):
        raise ValueError("Binary metric inputs must have equal lengths")
    if raw_predicted_classes is not None and not all(
        isinstance(value, (bool, np.bool_)) for value in raw_predicted_classes
    ):
        raise ValueError("Predicted classes must be boolean")
    finite = (
        np.isfinite(observed)
        & np.isfinite(predicted_probability)
        & np.isfinite(weights)
    )
    observed = observed[finite]
    predicted_probability = predicted_probability[finite]
    weights = weights[finite]
    registered_predicted_class = (
        None
        if raw_predicted_classes is None
        else raw_predicted_classes.astype(bool)[finite]
    )
    if len(observed) == 0:
        raise ValueError("At least one observed probability is required")
    if not np.isin(observed, [0.0, 1.0]).all():
        raise ValueError("Binary labels must be zero or one")
    if ((predicted_probability < 0.0) | (predicted_probability > 1.0)).any():
        raise ValueError("Probabilities must be in the unit interval")
    if (weights < 0.0).any() or weights.sum() <= 0.0:
        raise ValueError("Sample weights must be non-negative with positive total")

    predicted_class = (
        predicted_probability >= threshold
        if registered_predicted_class is None
        else registered_predicted_class
    )
    positive = observed == 1.0
    negative = ~positive
    true_positive = float(weights[predicted_class & positive].sum())
    true_negative = float(weights[~predicted_class & negative].sum())
    false_positive = float(weights[predicted_class & negative].sum())
    false_negative = float(weights[~predicted_class & positive].sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    mcc_denominator = math.sqrt(
        (true_positive + false_positive)
        * (true_positive + false_negative)
        * (true_negative + false_positive)
        * (true_negative + false_negative)
    )
    mcc = (
        (true_positive * true_negative - false_positive * false_negative) / mcc_denominator
        if mcc_denominator
        else 0.0
    )

    positive_count = int(np.count_nonzero(positive))
    negative_count = int(np.count_nonzero(negative))
    roc_auc: float | None = None
    pr_auc: float | None = None
    positive_weight = float(weights[positive].sum())
    negative_weight = float(weights[negative].sum())
    if positive_weight > 0.0 and negative_weight > 0.0:
        roc_auc = _weighted_roc_auc(
            observed,
            predicted_probability,
            weights,
        )
    if positive_weight > 0.0:
        pr_auc = _weighted_average_precision(
            observed,
            predicted_probability,
            weights,
        )

    clipped_probability = np.clip(predicted_probability, 1.0e-15, 1.0 - 1.0e-15)
    log_loss = -float(
        np.average(
            observed * np.log(clipped_probability)
            + (1.0 - observed) * np.log(1.0 - clipped_probability),
            weights=weights,
        )
    )

    return {
        "observations": int(len(observed)),
        "successes": positive_count,
        "failures": negative_count,
        "totalWeight": float(weights.sum()),
        "brierScore": float(
            np.average((predicted_probability - observed) ** 2, weights=weights)
        ),
        "logLoss": log_loss,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mcc": mcc,
        "rocAuc": roc_auc,
        "prAuc": pr_auc,
        "truePositive": true_positive,
        "trueNegative": true_negative,
        "falsePositive": false_positive,
        "falseNegative": false_negative,
    }


def _weighted_roc_auc(
    labels: np.ndarray,
    probabilities: np.ndarray,
    weights: np.ndarray,
) -> float:
    order = np.argsort(probabilities, kind="mergesort")
    ordered_probabilities = probabilities[order]
    ordered_labels = labels[order]
    ordered_weights = weights[order]
    total_positive = float(ordered_weights[ordered_labels == 1.0].sum())
    total_negative = float(ordered_weights[ordered_labels == 0.0].sum())
    concordance = 0.0
    negative_weight_below = 0.0
    position = 0
    while position < len(order):
        end = position + 1
        while (
            end < len(order)
            and ordered_probabilities[end] == ordered_probabilities[position]
        ):
            end += 1
        group_labels = ordered_labels[position:end]
        group_weights = ordered_weights[position:end]
        group_positive = float(group_weights[group_labels == 1.0].sum())
        group_negative = float(group_weights[group_labels == 0.0].sum())
        concordance += group_positive * (
            negative_weight_below + 0.5 * group_negative
        )
        negative_weight_below += group_negative
        position = end
    return concordance / (total_positive * total_negative)


def _weighted_average_precision(
    labels: np.ndarray,
    probabilities: np.ndarray,
    weights: np.ndarray,
) -> float:
    order = np.argsort(-probabilities, kind="mergesort")
    ordered_probabilities = probabilities[order]
    ordered_labels = labels[order]
    ordered_weights = weights[order]
    total_positive = float(ordered_weights[ordered_labels == 1.0].sum())
    cumulative_positive = 0.0
    cumulative_weight = 0.0
    average_precision = 0.0
    position = 0
    while position < len(order):
        end = position + 1
        while (
            end < len(order)
            and ordered_probabilities[end] == ordered_probabilities[position]
        ):
            end += 1
        group_labels = ordered_labels[position:end]
        group_weights = ordered_weights[position:end]
        group_positive = float(group_weights[group_labels == 1.0].sum())
        cumulative_positive += group_positive
        cumulative_weight += float(group_weights.sum())
        precision = cumulative_positive / cumulative_weight
        average_precision += (group_positive / total_positive) * precision
        position = end
    return average_precision


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if ((values < 0.0) | (values > 1.0) | ~np.isfinite(values)).any():
        raise ValueError("P-values must be finite and in the unit interval")
    if len(values) == 0:
        return []

    order = np.argsort(values, kind="mergesort")
    ranked = values[order]
    adjusted_ranked = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted_ranked = np.minimum.accumulate(adjusted_ranked[::-1])[::-1]
    adjusted_ranked = np.minimum(adjusted_ranked, 1.0)
    adjusted = np.empty(len(values), dtype=float)
    adjusted[order] = adjusted_ranked
    return adjusted.tolist()


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if ((values < 0.0) | (values > 1.0) | ~np.isfinite(values)).any():
        raise ValueError("P-values must be finite and in the unit interval")
    if len(values) == 0:
        return []

    order = np.argsort(values, kind="mergesort")
    ranked = values[order]
    multipliers = np.arange(len(values), 0, -1)
    adjusted_ranked = np.maximum.accumulate(ranked * multipliers)
    adjusted_ranked = np.minimum(adjusted_ranked, 1.0)
    adjusted = np.empty(len(values), dtype=float)
    adjusted[order] = adjusted_ranked
    return adjusted.tolist()


def beta_binomial_predictive(
    successes: int,
    failures: int,
    future_events: int,
) -> list[float]:
    if successes < 0 or failures < 0 or future_events < 0:
        raise ValueError("Event counts must be non-negative")
    alpha = successes + 0.5
    beta = failures + 0.5
    log_prior_beta = (
        math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)
    )
    probabilities: list[float] = []
    for future_successes in range(future_events + 1):
        future_failures = future_events - future_successes
        log_combination = (
            math.lgamma(future_events + 1)
            - math.lgamma(future_successes + 1)
            - math.lgamma(future_failures + 1)
        )
        log_posterior_beta = (
            math.lgamma(alpha + future_successes)
            + math.lgamma(beta + future_failures)
            - math.lgamma(alpha + beta + future_events)
        )
        probabilities.append(
            math.exp(log_combination + log_posterior_beta - log_prior_beta)
        )
    total = sum(probabilities)
    return [probability / total for probability in probabilities]


def _expected_fold_order(
    observed_fold_ids: Sequence[object],
    expected_fold_ids: Sequence[object] | None,
) -> list[object]:
    if expected_fold_ids is None:
        return list(observed_fold_ids)
    ordered = list(expected_fold_ids)
    if len(ordered) != len(set(ordered)):
        raise ValueError("Expected fold identifiers must be unique")
    unexpected = [fold_id for fold_id in observed_fold_ids if fold_id not in ordered]
    if unexpected:
        raise ValueError("Observed fold identifier is not registered")
    return ordered


def _registered_fold_ordinals(ordered_fold_ids: Sequence[object]) -> list[int]:
    if all(isinstance(fold_id, (int, np.integer)) for fold_id in ordered_fold_ids):
        numeric = [int(fold_id) for fold_id in ordered_fold_ids]
        offset = 0 if 0 in numeric else 1
        ordinals = [fold_id - offset for fold_id in numeric]
        if all(ordinal >= 0 for ordinal in ordinals):
            return ordinals
    return list(range(len(ordered_fold_ids)))


def paired_brier_bootstrap(
    labels: Sequence[float] | np.ndarray,
    baseline_probabilities: Sequence[float] | np.ndarray,
    candidate_probabilities: Sequence[float] | np.ndarray,
    sample_weights: Sequence[float] | np.ndarray | None = None,
    fold_ids: Sequence[object] | np.ndarray | None = None,
    expected_fold_ids: Sequence[object] | None = None,
    block_lengths: Sequence[int] = (5, 10, 20),
    repetitions: int = 2_000,
    seed: int = 20260710,
    seed_resolver: Callable[[int, int], int] | None = None,
) -> dict[str, object]:
    observed = np.asarray(labels, dtype=float)
    baseline = np.asarray(baseline_probabilities, dtype=float)
    candidate = np.asarray(candidate_probabilities, dtype=float)
    weights = (
        np.ones(len(observed), dtype=float)
        if sample_weights is None
        else np.asarray(sample_weights, dtype=float)
    )
    folds = (
        np.zeros(len(observed), dtype=int)
        if fold_ids is None
        else np.asarray(fold_ids, dtype=object)
    )
    if not (
        len(observed)
        == len(baseline)
        == len(candidate)
        == len(weights)
        == len(folds)
    ):
        raise ValueError("Paired Brier inputs must have equal lengths")
    finite = (
        np.isfinite(observed)
        & np.isfinite(baseline)
        & np.isfinite(candidate)
        & np.isfinite(weights)
    )
    observed = observed[finite]
    baseline = baseline[finite]
    candidate = candidate[finite]
    weights = weights[finite]
    folds = folds[finite]
    if len(observed) == 0:
        raise ValueError("Paired Brier bootstrap requires observations")
    if not np.isin(observed, [0.0, 1.0]).all():
        raise ValueError("Paired Brier labels must be binary")
    if (
        ((baseline < 0.0) | (baseline > 1.0)).any()
        or ((candidate < 0.0) | (candidate > 1.0)).any()
    ):
        raise ValueError("Paired Brier probabilities must be in the unit interval")
    if (weights <= 0.0).any():
        raise ValueError("Paired Brier weights require a positive total")

    observation_differences = (baseline - observed) ** 2 - (candidate - observed) ** 2
    block_summaries: list[dict[str, float | int]] = []
    observed_fold_ids = list(dict.fromkeys(folds.tolist()))
    ordered_fold_ids = _expected_fold_order(observed_fold_ids, expected_fold_ids)
    fold_positions = [np.flatnonzero(folds == fold_id) for fold_id in ordered_fold_ids]
    empty_fold_ids = [
        fold_id
        for fold_id, positions in zip(ordered_fold_ids, fold_positions, strict=True)
        if len(positions) == 0
    ]
    if empty_fold_ids:
        return {
            "status": "bootstrap_unavailable",
            "reason": "empty_expected_fold",
            "emptyFoldIds": empty_fold_ids,
            "foldCount": len(ordered_fold_ids),
        }
    fold_ordinals = _registered_fold_ordinals(ordered_fold_ids)
    for offset, block_length in enumerate(block_lengths):
        fold_samples = [
            positions[
                MovingBlockBootstrap(
                    block_length=block_length,
                    repetitions=repetitions,
                    seed=(
                        seed_resolver(block_length, fold_ordinals[fold_position])
                        if seed_resolver is not None
                        else seed + offset * 10_007 + fold_ordinals[fold_position]
                    ),
                ).resample_indices(len(positions))
            ]
            for fold_position, positions in enumerate(fold_positions)
        ]
        if not fold_samples:
            continue
        indices = np.concatenate(fold_samples, axis=1)
        resampled_weights = weights[indices]
        bootstrap_means = (
            (observation_differences[indices] * resampled_weights).sum(axis=1)
            / resampled_weights.sum(axis=1)
        )
        block_summaries.append(
            {
                "blockLength": int(block_length),
                "lower": percentile_order_statistic(bootstrap_means, 0.025),
                "upper": percentile_order_statistic(bootstrap_means, 0.975),
                "oneSidedPValue": float(
                    (1 + np.count_nonzero(bootstrap_means <= 0.0))
                    / (repetitions + 1)
                ),
            }
        )
    if not block_summaries:
        raise ValueError("No bootstrap block length fits the observed sample")

    return {
        "status": "available",
        "observations": int(len(observed)),
        "foldCount": len(ordered_fold_ids),
        "brierDifference": float(
            np.average(observation_differences, weights=weights)
        ),
        "conservativeLower": min(
            float(summary["lower"]) for summary in block_summaries
        ),
        "conservativeUpper": max(
            float(summary["upper"]) for summary in block_summaries
        ),
        "oneSidedPValue": max(
            float(summary["oneSidedPValue"]) for summary in block_summaries
        ),
        "byBlockLength": block_summaries,
    }


def circular_shift_placebo(
    labels: Sequence[float] | np.ndarray,
    baseline_probabilities: Sequence[float] | np.ndarray,
    candidate_probabilities: Sequence[float] | np.ndarray,
    fold_ids: Sequence[object] | np.ndarray,
    horizon: int,
    repetitions: int,
    seed_resolver: Callable[[int], int],
    expected_fold_ids: Sequence[object] | None = None,
    sample_weights: Sequence[float] | np.ndarray | None = None,
) -> dict[str, object]:
    if horizon <= 0 or repetitions <= 0:
        raise ValueError("Placebo horizon and repetitions must be positive")
    observed = np.asarray(labels, dtype=float)
    baseline = np.asarray(baseline_probabilities, dtype=float)
    candidate = np.asarray(candidate_probabilities, dtype=float)
    folds = np.asarray(fold_ids, dtype=object)
    weights = (
        np.ones(len(observed), dtype=float)
        if sample_weights is None
        else np.asarray(sample_weights, dtype=float)
    )
    if not (
        len(observed)
        == len(baseline)
        == len(candidate)
        == len(folds)
        == len(weights)
    ):
        raise ValueError("Placebo inputs must have equal lengths")
    finite = (
        np.isfinite(observed)
        & np.isfinite(baseline)
        & np.isfinite(candidate)
        & np.isfinite(weights)
    )
    observed = observed[finite]
    baseline = baseline[finite]
    candidate = candidate[finite]
    folds = folds[finite]
    weights = weights[finite]
    if len(observed) == 0:
        raise ValueError("Placebo requires paired observations")
    if not np.isin(observed, [0.0, 1.0]).all():
        raise ValueError("Placebo labels must be binary")
    if (
        ((baseline < 0.0) | (baseline > 1.0)).any()
        or ((candidate < 0.0) | (candidate > 1.0)).any()
        or (weights <= 0.0).any()
    ):
        raise ValueError("Placebo probabilities and weights are outside their domain")

    observed_fold_ids = list(dict.fromkeys(folds.tolist()))
    ordered_fold_ids = _expected_fold_order(observed_fold_ids, expected_fold_ids)
    fold_positions = [np.flatnonzero(folds == fold_id) for fold_id in ordered_fold_ids]
    empty_fold_ids = [
        fold_id
        for fold_id, positions in zip(ordered_fold_ids, fold_positions, strict=True)
        if len(positions) == 0
    ]
    if empty_fold_ids:
        return {
            "status": "placebo_unavailable",
            "reason": "empty_expected_fold",
            "emptyFoldIds": empty_fold_ids,
        }
    allowed_offset_ranges = [
        (horizon + 1, len(positions) - horizon - 1)
        for positions in fold_positions
    ]
    if any(lower > upper for lower, upper in allowed_offset_ranges):
        return {"status": "placebo_unavailable"}

    fold_ordinals = _registered_fold_ordinals(ordered_fold_ids)
    generators = [XorShift32(seed_resolver(ordinal)) for ordinal in fold_ordinals]
    placebo_statistics = np.empty(repetitions, dtype=float)
    for repetition in range(repetitions):
        shifted_labels = observed.copy()
        for fold_ordinal, positions in enumerate(fold_positions):
            lower, upper = allowed_offset_ranges[fold_ordinal]
            offset_count = upper - lower + 1
            offset = lower + math.floor(
                generators[fold_ordinal].uniform() * offset_count
            )
            shifted_labels[positions] = np.roll(observed[positions], -offset)
        loss_difference = (
            (baseline - shifted_labels) ** 2
            - (candidate - shifted_labels) ** 2
        )
        placebo_statistics[repetition] = float(
            np.average(loss_difference, weights=weights)
        )

    observed_difference = float(
        np.average(
            (baseline - observed) ** 2 - (candidate - observed) ** 2,
            weights=weights,
        )
    )
    return {
        "status": "available",
        "repetitions": repetitions,
        "observedBrierDifference": observed_difference,
        "lower95": percentile_order_statistic(placebo_statistics, 0.025),
        "median": percentile_order_statistic(placebo_statistics, 0.5),
        "upper95": percentile_order_statistic(placebo_statistics, 0.975),
        "observedRankFraction": float(
            (1 + np.count_nonzero(placebo_statistics <= observed_difference))
            / (repetitions + 1)
        ),
        "upperTailPValue": float(
            (1 + np.count_nonzero(placebo_statistics >= observed_difference))
            / (repetitions + 1)
        ),
        "allowedOffsetsByFold": [
            [int(lower), int(upper)]
            for lower, upper in allowed_offset_ranges
        ],
    }


def percentile_order_statistic(
    values: Sequence[float] | np.ndarray,
    quantile: float,
) -> float:
    samples = np.asarray(values, dtype=float)
    samples = samples[np.isfinite(samples)]
    if len(samples) == 0:
        raise ValueError("Order statistic requires a finite sample")
    if not 0.0 < quantile <= 1.0:
        raise ValueError("Order statistic quantile must be in (0, 1]")
    ordered = np.sort(samples)
    one_based_index = math.ceil(quantile * len(ordered))
    return float(ordered[one_based_index - 1])


@dataclass(frozen=True)
class FittedProbabilityCalibrator:
    bin_edges: tuple[float, ...]
    bin_probabilities: tuple[float, ...]
    alert_threshold: float

    def predict(self, scores: pd.Series) -> pd.Series:
        numeric_scores = pd.to_numeric(scores, errors="coerce").astype(float)
        predictions = pd.Series(np.nan, index=numeric_scores.index, dtype=float)
        bin_edges = np.asarray(self.bin_edges, dtype=float)
        probabilities = np.asarray(self.bin_probabilities, dtype=float)
        for position, score in enumerate(numeric_scores.to_numpy()):
            if not np.isfinite(score):
                continue
            bin_index = int(np.searchsorted(bin_edges, score, side="left"))
            predictions.iloc[position] = probabilities[bin_index]
        return predictions


class CausalProbabilityCalibrator:
    def __init__(
        self,
        bin_count: int = 5,
        alert_quantile: float = 0.8,
        minimum_valid_pairs: int = 30,
    ) -> None:
        if bin_count < 2:
            raise ValueError("Probability calibration requires at least two bins")
        if not 0.0 < alert_quantile < 1.0:
            raise ValueError("Alert quantile must be between zero and one")
        if minimum_valid_pairs < bin_count:
            raise ValueError("Minimum valid pairs must cover every calibration bin")
        self.bin_count = bin_count
        self.alert_quantile = alert_quantile
        self.minimum_valid_pairs = minimum_valid_pairs

    def fit(
        self,
        scores: pd.Series,
        labels: pd.Series,
    ) -> FittedProbabilityCalibrator:
        if not scores.index.equals(labels.index):
            raise ValueError("Training score and label indexes must match")
        training = pd.DataFrame(
            {
                "score": pd.to_numeric(scores, errors="coerce"),
                "label": pd.to_numeric(labels, errors="coerce"),
            }
        ).replace([np.inf, -np.inf], np.nan).dropna()
        if len(training) < self.minimum_valid_pairs:
            raise ValueError(
                "Calibration requires at least "
                f"{self.minimum_valid_pairs} valid training pairs"
            )
        if not training["label"].isin([0.0, 1.0]).all():
            raise ValueError("Calibration labels must be binary")

        sorted_scores = np.sort(training["score"].to_numpy())
        requested_edges = [
            sorted_scores[math.ceil(bin_index * len(sorted_scores) / self.bin_count) - 1]
            for bin_index in range(1, self.bin_count)
        ]
        maximum_score = float(sorted_scores[-1])
        edges = np.asarray(
            sorted({float(edge) for edge in requested_edges if edge < maximum_score}),
            dtype=float,
        )
        bin_indexes = np.searchsorted(
            edges,
            training["score"].to_numpy(),
            side="left",
        )
        observed_probabilities: list[float] = []
        observed_weights: list[int] = []
        for bin_index in range(len(edges) + 1):
            bin_labels = training.loc[bin_indexes == bin_index, "label"]
            successes = int(bin_labels.sum())
            count = len(bin_labels)
            observed_probabilities.append((successes + 0.5) / (count + 1.0))
            observed_weights.append(max(count, 1))

        monotone_probabilities = _pooled_adjacent_violators(
            observed_probabilities,
            observed_weights,
        )
        return FittedProbabilityCalibrator(
            bin_edges=tuple(float(edge) for edge in edges),
            bin_probabilities=tuple(monotone_probabilities),
            alert_threshold=float(
                sorted_scores[
                    math.ceil(self.alert_quantile * len(sorted_scores)) - 1
                ]
            ),
        )


def _pooled_adjacent_violators(
    values: Sequence[float],
    weights: Sequence[int],
) -> list[float]:
    blocks: list[dict[str, float | int]] = []
    for value, weight in zip(values, weights, strict=True):
        blocks.append(
            {
                "value": float(value),
                "weight": int(weight),
                "count": 1,
            }
        )
        while len(blocks) >= 2 and blocks[-2]["value"] > blocks[-1]["value"]:
            right = blocks.pop()
            left = blocks.pop()
            combined_weight = int(left["weight"]) + int(right["weight"])
            combined_value = (
                float(left["value"]) * int(left["weight"])
                + float(right["value"]) * int(right["weight"])
            ) / combined_weight
            blocks.append(
                {
                    "value": combined_value,
                    "weight": combined_weight,
                    "count": int(left["count"]) + int(right["count"]),
                }
            )

    result: list[float] = []
    for block in blocks:
        result.extend([float(block["value"])] * int(block["count"]))
    return result


UINT32_MODULUS = 2**32
XORSHIFT32_ZERO_SEED_REPLACEMENT = 1_831_565_813


class XorShift32:
    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int):
            raise TypeError("XorShift32 seed must be an integer")
        normalized_seed = seed % UINT32_MODULUS
        self._state = (
            XORSHIFT32_ZERO_SEED_REPLACEMENT
            if normalized_seed == 0
            else normalized_seed
        )

    def next_uint32(self) -> int:
        value = self._state
        value ^= (value << 13) % UINT32_MODULUS
        value %= UINT32_MODULUS
        value ^= value >> 17
        value %= UINT32_MODULUS
        value ^= (value << 5) % UINT32_MODULUS
        value %= UINT32_MODULUS
        self._state = value
        return value

    def uniform(self) -> float:
        return self.next_uint32() / UINT32_MODULUS


def registered_random_seed(
    base_seed: int,
    candidate_ordinal: int,
    outcome_ordinal: int,
    horizon: int,
    block_length: int,
    fold_ordinal: int,
    purpose_ordinal: int,
) -> int:
    ordinals = (candidate_ordinal, outcome_ordinal, fold_ordinal, purpose_ordinal)
    if not isinstance(base_seed, int) or any(
        not isinstance(value, int) or value < 0 for value in ordinals
    ):
        raise ValueError("Registered randomness requires non-negative integer ordinals")
    if not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("Registered randomness requires a positive horizon")
    if not isinstance(block_length, int) or block_length < 0:
        raise ValueError("Registered randomness requires a non-negative block length")
    return (
        base_seed
        + 1_000_003 * (candidate_ordinal + 1)
        + 10_007 * (outcome_ordinal + 1)
        + 1_009 * horizon
        + 101 * block_length
        + 17 * (fold_ordinal + 1)
        + 65_537 * purpose_ordinal
    ) % UINT32_MODULUS


class MovingBlockBootstrap:
    def __init__(self, block_length: int, repetitions: int, seed: int) -> None:
        if block_length <= 0 or repetitions <= 0:
            raise ValueError("Bootstrap block length and repetitions must be positive")
        self.block_length = block_length
        self.repetitions = repetitions
        self.seed = seed

    def resample_indices(self, sample_size: int) -> np.ndarray:
        if sample_size <= 0:
            raise ValueError("Bootstrap sample size must be positive")
        effective_block_length = min(self.block_length, sample_size)
        generator = XorShift32(self.seed)
        block_count = math.ceil(sample_size / effective_block_length)
        maximum_start = sample_size - effective_block_length
        samples = np.empty((self.repetitions, sample_size), dtype=int)
        offsets = np.arange(effective_block_length)

        for repetition in range(self.repetitions):
            starts = np.asarray(
                [
                    math.floor(generator.uniform() * (maximum_start + 1))
                    for _ in range(block_count)
                ],
                dtype=int,
            )
            indices = (starts[:, None] + offsets[None, :]).reshape(-1)
            samples[repetition] = indices[:sample_size]
        return samples
