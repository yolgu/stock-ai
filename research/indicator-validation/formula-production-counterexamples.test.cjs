const assert = require("node:assert/strict");
const test = require("node:test");

const {
  evaluateDuplicateCandleCounterexample,
  evaluateFutureTimestampCounterexample,
  evaluateHiddenFloorCounterexample,
  evaluateInputOrderCounterexample,
  evaluateRiskRewardBranchCounterexample,
  evaluateSplitAdjustmentCounterexample
} = require("./formula-production-counterexamples.cjs");


test("production displayed linear score is not the returned hidden-floor score", () => {
  assert.deepEqual(evaluateHiddenFloorCounterexample(), {
    causeScores: {
      profitBurden: 100,
      realizedSellPressure: 3,
      overheadSupplyPressure: 0,
      liquidityImpactRisk: 56
    },
    displayedLinearScore: 42,
    returnedScore: 65
  });
});

test("a future candle changes a historical production snapshot", () => {
  assert.deepEqual(evaluateFutureTimestampCounterexample(), {
    asOf: "2026-07-06T09:34:00.000Z",
    appendedTimestamp: "2026-07-06T09:36:00.000Z",
    beforeVwap: "101.0000",
    afterVwap: "498.8066"
  });
});

test("reversing the same candles changes the production volume expansion", () => {
  assert.deepEqual(evaluateInputOrderCounterexample(), {
    ascendingVolumeExpansion: 1,
    reversedVolumeExpansion: 0.13
  });
});

test("duplicating one timestamp changes production VWAP", () => {
  assert.deepEqual(evaluateDuplicateCandleCounterexample(), {
    uniqueVwap: "109.0000",
    duplicateVwap: "108.1818"
  });
});

test("split-adjusting price and volume changes the fixed-volume CVD state", () => {
  assert.deepEqual(evaluateSplitAdjustmentCounterexample(), {
    preSplit: { value: "10", label: "체결 중립", severity: "neutral" },
    adjustedSplit: { value: "100", label: "체결 압력 우위", severity: "positive" }
  });
});

test("risk-reward warning and danger branches are unreachable for positive ATR", () => {
  const result = evaluateRiskRewardBranchCounterexample();

  assert.equal(result.ratio, 2);
  assert.equal(result.severity, "positive");
  assert.equal(result.warningReachable, false);
  assert.equal(result.dangerReachable, false);
});
