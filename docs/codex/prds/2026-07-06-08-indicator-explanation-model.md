# Step 08 PRD: Indicator Explanation Model

## Goal

Make each deterministic indicator explainable through a structured, reproducible trace.

## User Value

The user can understand what each indicator means, which values were used, what formula was applied, and why the current result produced its label.

## Scope

- Explanation trace model.
- Original formula.
- Current substituted formula.
- Calculation result.
- Input list.
- Meaning.
- Usage.
- Judgment.
- Caution.
- Limitation.
- Supported keys: basic return, VWAP, CVD estimate, spread, ATR stop, supply pressure, risk/reward.

## Non-Goals

- No LLM-generated explanation.
- No news sentiment explanation.
- No backtest explanation.
- No order recommendation.

## Object-Oriented Design

### Payload

- `QuantIndicatorExplanationTracePayload`

### Trace Keys

- `basicReturn`
- `vwap`
- `cvd`
- `spread`
- `atrStop`
- `supplyPressure`
- `riskReward`

### Source Of Truth

- The extension creates traces from the same deterministic calculation result that creates the quant snapshot.
- The renderer displays traces and does not recalculate formulas.

## Explanation Rules

- `originalFormula` keeps the generic formula.
- `substitutedFormula` inserts the selected card's current values.
- `result` shows the computed value and label.
- `inputs` lists only values already allowed in the quant payload.
- `limitation` is required for estimated indicators.
- CVD must identify that Toss trades do not include aggressor side and that the value is tick-rule based.

## Acceptance Criteria

- Every supported indicator has an explanation trace when a quant snapshot exists.
- Unavailable indicators still produce a trace explaining missing inputs.
- CVD trace always marks the value as estimated.
- Response and cache payloads do not include Toss secrets, access tokens, or bearer tokens.

## Verification

- Extension tests validate trace shape and formula/result strings.
- Contract tests validate `explanationTraces` is part of the quant snapshot payload.
- Secret-scanning verification checks response and storage payloads.

## Dependencies

- Step 05 quant indicator engine.
- Step 07 market context and basic returns.
