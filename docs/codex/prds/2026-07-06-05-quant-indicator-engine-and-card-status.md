# Step 05 PRD: Quant Indicator Engine And Card Status

## Goal

Calculate deterministic day-trading indicators from market snapshots and classify each card into a concise decision-support state.

## User Value

The user sees what matters beside the Toss chart: VWAP condition, CVD pressure, spread risk, ATR-based stop risk, supply pressure, risk/reward status, and current card state.

## Scope

- VWAP, VWAP distance, and VWAP reclaim/loss state.
- CVD and trade imbalance.
- Spread and orderbook imbalance.
- ATR and stop-width risk.
- Volume profile, POC, overhead supply pressure.
- Risk/reward threshold check.
- Data quality and calculation availability.
- Card state classification.

## Non-Goals

- No LLM narrative.
- No news sentiment.
- No backtest metrics.
- No order submission.

## Object-Oriented Design

### Entities

- `QuantIndicatorSnapshot`: deterministic indicator values for a card and timestamp.
- `CardAnalysisState`: current derived state attached to a card.

### Value Objects

- `VwapState`
- `CvdState`
- `SpreadRisk`
- `AtrStopRisk`
- `SupplyPressure`
- `RiskRewardState`
- `DataQualityState`
- `CardDecisionStatus`: `watch`, `confirmationWaiting`, `riskHigh`, `invalidated`, `dataInsufficient`

### Domain Services

- `VwapCalculator`
- `CvdCalculator`
- `SpreadRiskCalculator`
- `AtrCalculator`
- `VolumeProfileCalculator`
- `RiskRewardCalculator`
- `CardStatusClassifier`

### Application Use Cases

- `CalculateQuantIndicatorsForCard`
- `CalculateQuantIndicatorsForWatchlist`
- `ClassifyWatchStockCardStatus`

### Repository

- `QuantIndicatorSnapshotRepository`

## Display Language

The product displays derived states instead of raw Toss-visible values:

- `VWAP 재돌파 필요`
- `체결 압력 둔화`
- `손절 폭 과대`
- `스프레드 정상`
- `매물대 부담`
- `손익비 1.5x 미달`

## Acceptance Criteria

- Every deterministic indicator is reproducible from a stored market data snapshot.
- If required input is missing, the indicator reports `calculationUnavailable` with a reason.
- Card status updates on every polling cycle.
- The UI receives qualitative labels and compact severity, not raw chart replacement data.
- LLM-dependent fields are not updated by this engine.

## Verification

- Calculator tests use fixed market snapshots and expected numeric outputs.
- Status classifier tests cover conflicting indicator combinations.
- Data quality tests cover stale, missing, partial, and estimated inputs.

## Dependencies

- Step 04 market data polling and cache.

