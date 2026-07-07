# Step 07 PRD: Market Context And Basic Returns

## Goal

Show the minimal price coordinate needed to understand each watch card's deterministic judgment.

## User Value

The user can see when the data was captured and what price move the indicators are interpreting, while still using Toss for full charts, orderbook, and volume tables.

## Scope

- Current price.
- Absolute change.
- Simple return percentage.
- Log return percentage.
- Market data timestamp.
- Quant indicator timestamp.
- Previous close as the default reference price.
- Card and detail-panel display for the price coordinate.

## Non-Goals

- No in-app candlestick chart.
- No raw orderbook table.
- No raw volume table.
- No configurable benchmark selection yet.
- No LLM explanation.

## Object-Oriented Design

### Domain Concept

- `BasicReturn`: explains how current price moved against a reference price.

### Quant Payload

- `basicReturn.currentPrice`
- `basicReturn.referencePrice`
- `basicReturn.absoluteChange`
- `basicReturn.simpleReturnPercent`
- `basicReturn.logReturnPercent`
- `basicReturn.currency`
- `basicReturn.referenceLabel`
- `basicReturn.status`

### Presentation View Model

- `MarketContextViewModel`

## Calculation Rules

- The default reference is previous daily close.
- If the daily candle list contains the current trading date, use the previous daily candle close.
- If the daily candle list does not contain the current trading date, use the latest completed daily candle close before the price timestamp.
- If current price, reference price, or positive reference price is unavailable, return `unavailable`.
- Simple return uses `currentPrice / referencePrice - 1`.
- Log return uses `ln(currentPrice / referencePrice)`.

## UI Behavior

- Watch cards show current price, change, percent change, market-data time, and quant-update time.
- Detail view repeats the same price coordinate near the top.
- Price coordinate is allowed even though raw charts, raw volume, and orderbook tables remain hidden.
- Positive and negative move coloring follows the existing dark Toss-like design token system.

## Acceptance Criteria

- A card with a valid market snapshot and daily candles shows current price, change, percent change, and data time.
- A missing reference price shows a recoverable unavailable state.
- The UI does not show raw orderbook prices, raw volume lists, or candle charts.
- Basic return values are deterministic and reproducible from the cached market snapshot.

## Verification

- Quant tests validate previous-close selection and simple/log return math.
- Renderer tests validate card and detail price coordinate display.
- Renderer tests validate raw volume, orderbook, and chart data remain hidden.

## Dependencies

- Step 04 market data polling and cache.
- Step 05 quant indicator engine.
