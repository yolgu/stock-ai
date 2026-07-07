# Step 10 PRD: LLM-Free Deterministic Indicator Expansion

## Goal

Expand the deterministic quant engine with indicators that can be calculated from the existing Toss market snapshot without news, LLM output, peer benchmarks, or order data.

## User Value

The user gets a richer intraday checklist before introducing LLM interpretation, and every new value remains reproducible from stored market snapshots.

## Scope

- Velocity and acceleration indicators.
- Distance profile indicators.
- RSI and momentum indicators.
- Deterministic intraday sentiment score.
- Deterministic intraday trade-condition score.
- Explanation traces for every new indicator.
- Detail checklist rows and help popovers for every new indicator.

## Non-Goals

- No news sentiment.
- No relative strength against indexes, sectors, or peers.
- No LLM-generated scoring.
- No buy, sell, or order recommendation.

## Object-Oriented Design

### Domain Services

- `VelocityAccelerationCalculator`
- `DistanceProfileCalculator`
- `RsiMomentumCalculator`
- `DeterministicSentimentScoreCalculator`
- `IntradayTradeScoreCalculator`

### Value Objects

- `LogReturnVelocity`
- `PriceAcceleration`
- `DistanceBasisPoint`
- `RsiValue`
- `DeterministicScore`
- `ConditionProbability`

### Extension Boundary

- `QuantIndicatorsPayload` adds five deterministic payload sections:
  - `velocityAcceleration`
  - `distanceProfile`
  - `rsiMomentum`
  - `marketSentimentScore`
  - `intradayTradeScore`
- `explanationTraces` adds matching trace entries.

## Indicator Definitions

- `velocityAcceleration`: latest log return, price acceleration, volume change, and estimated CVD change.
- `distanceProfile`: VWAP distance, MA20 distance, and ATR-based distance from the reference close.
- `rsiMomentum`: 14-period RSI and recent momentum.
- `marketSentimentScore`: normalized 0-100 deterministic score from VWAP, CVD, spread, volatility, supply pressure, and risk/reward conditions.
- `intradayTradeScore`: sigmoid transformation of the deterministic score, shown as condition-strength probability.

## Acceptance Criteria

- Each new indicator returns `status`, core values, `label`, `severity`, and `unavailableReason`.
- Insufficient data returns `unavailable` for that indicator without failing the whole snapshot.
- New explanation traces include original formula, substituted formula, result, and limitation when applicable.
- Checklist rows follow this order:
  1. Basic return
  2. VWAP
  3. CVD estimate
  4. Spread
  5. Velocity and acceleration
  6. Distance profile
  7. RSI and momentum
  8. ATR and stop distance
  9. Supply pressure
  10. Risk/reward
  11. Intraday deterministic sentiment score
  12. Intraday trade-condition score
- Cards still show only two or three core signals.

## Verification

- Quant tests validate deterministic calculations against fixed fixtures.
- Quant tests validate unavailable states for insufficient input.
- Contract tests validate the new payload shape and secret-free responses.
- Renderer tests validate new checklist rows and popover explanations.
- Manual Neutralino smoke check validates the new rows in the desktop shell.

## Dependencies

- Step 04 market data polling and cache.
- Step 05 quant indicator engine and card status.
- Step 08 indicator explanation model.
- Step 09 beginner explanation popover UI.
