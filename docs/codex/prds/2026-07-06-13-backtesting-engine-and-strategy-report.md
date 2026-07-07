# Step 13 PRD: Backtesting Engine And Strategy Report

## Goal

Evaluate watch-card conditions against historical data so the product can distinguish deterministic evidence from untested heuristics.

## User Value

The user sees whether a condition such as `VWAP reclaim + CVD recovery + spread normal` has historical support, sample size, drawdown, and risk/reward characteristics.

## Scope

- Backtest rule definitions based on deterministic indicators.
- Historical candle and derived indicator reconstruction.
- Strategy result metrics.
- Per-card backtest report.
- LLM-ready summary input for Step 12 manual insight refresh.

## Non-Goals

- No promise of future profit.
- No high-frequency tick-perfect simulator in MVP.
- No automatic strategy optimization by LLM.
- No order execution.

## Object-Oriented Design

### Entities

- `BacktestStrategy`: named deterministic condition set.
- `BacktestRun`: one execution against a symbol, time range, and strategy.
- `BacktestReport`: immutable result summary.

### Value Objects

- `BacktestTimeRange`
- `EntryCondition`
- `ExitCondition`
- `InvalidationCondition`
- `BacktestSampleSize`
- `WinRate`
- `AverageRiskReward`
- `MaxDrawdown`

### Domain Services

- `StrategyConditionEvaluator`
- `BacktestSimulator`
- `BacktestMetricCalculator`
- `BacktestReliabilityClassifier`

### Application Use Cases

- `RunBacktestForCard`
- `ListBacktestReportsForCard`
- `AttachBacktestSummaryToInsightSnapshot`

### Repository

- `BacktestReportRepository`

## Acceptance Criteria

- User can run a backtest for a card using a deterministic strategy template.
- Report includes sample size, win rate, average gain/loss, max drawdown, average risk/reward, and reliability label.
- If historical data is insufficient, report says insufficient sample instead of producing a misleading score.
- Backtest report can be attached to a manual AI insight snapshot.
- Backtest does not trigger automatic orders.

## Verification

- Simulator tests use fixed candles and expected trades.
- Metric tests validate win rate, drawdown, and risk/reward calculation.
- Reliability tests classify insufficient, weak, moderate, and strong sample evidence.

## Dependencies

- Step 05 quant indicator engine.
- Step 12 insight snapshot structure for optional summary attachment.
