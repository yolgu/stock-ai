const {
  createQuantIndicatorSnapshot
} = require("../../extensions/app/quant-indicators.cjs");


const AS_OF = "2026-07-06T09:34:00.000Z";
const CALCULATED_AT = "2026-07-06T09:35:00.000Z";


function createCandle(timestamp, close, volume, range = 1) {
  return {
    timestamp,
    openPrice: String(close),
    highPrice: String(close + range),
    lowPrice: String(close - range),
    closePrice: String(close),
    volume: String(volume),
    currency: "USD"
  };
}


function createDailyCandles(lastPrice = 103.5) {
  return Array.from({ length: 15 }, (_value, index) => {
    const close = index === 14 ? lastPrice : 100 + index * 0.25;

    return createCandle(
      `2026-06-${String(20 + index).padStart(2, "0")}T00:00:00.000Z`,
      close,
      10_000,
      0.5
    );
  });
}


function createSnapshot(observations, capturedAt = AS_OF) {
  return createQuantIndicatorSnapshot({
    marketDataSnapshot: {
      snapshotId: "formula-audit-market",
      cardId: "formula-audit-card",
      market: "NASDAQ",
      symbol: "MU",
      capturedAt,
      observations
    },
    calculatedAt: CALCULATED_AT
  });
}


function defaultOrderbook(price = 103.5) {
  return {
    timestamp: AS_OF,
    currency: "USD",
    asks: [{ price: String(price + 0.1), volume: "100" }],
    bids: [{ price: String(price - 0.1), volume: "120" }]
  };
}


function defaultTrades() {
  return [
    { price: "100.00", volume: "10", timestamp: "2026-07-06T09:30:00.000Z", currency: "USD" },
    { price: "101.00", volume: "20", timestamp: "2026-07-06T09:31:00.000Z", currency: "USD" },
    { price: "100.50", volume: "5", timestamp: "2026-07-06T09:32:00.000Z", currency: "USD" },
    { price: "102.00", volume: "30", timestamp: "2026-07-06T09:33:00.000Z", currency: "USD" }
  ];
}


function completeObservations() {
  return {
    price: {
      symbol: "MU",
      timestamp: AS_OF,
      lastPrice: "103.50",
      currency: "USD"
    },
    trades: defaultTrades(),
    orderbook: defaultOrderbook(),
    intradayCandles: {
      candles: [
        createCandle("2026-07-06T09:30:00.000Z", 100, 1000),
        createCandle("2026-07-06T09:31:00.000Z", 102, 2000),
        createCandle("2026-07-06T09:32:00.000Z", 103, 1000)
      ]
    },
    dailyCandles: { candles: createDailyCandles() }
  };
}


function evaluateHiddenFloorCounterexample() {
  const snapshot = createSnapshot(completeObservations());
  const pressure = snapshot.indicators.profitTakingPressure;
  const causeScores = Object.fromEntries(
    Object.entries(pressure.causes).map(([identifier, cause]) => [identifier, cause.score])
  );
  const displayedLinearScore = Math.round(
    0.35 * causeScores.profitBurden
      + 0.30 * causeScores.realizedSellPressure
      + 0.25 * causeScores.overheadSupplyPressure
      + 0.10 * causeScores.liquidityImpactRisk
  );

  return {
    causeScores,
    displayedLinearScore,
    returnedScore: pressure.score
  };
}


function evaluateFutureTimestampCounterexample() {
  const observations = completeObservations();
  const baseCandles = [
    createCandle("2026-07-06T09:30:00.000Z", 100, 1000),
    createCandle("2026-07-06T09:31:00.000Z", 101, 1000),
    createCandle("2026-07-06T09:32:00.000Z", 102, 1000)
  ];
  const appendedTimestamp = "2026-07-06T09:36:00.000Z";
  const before = createSnapshot({
    ...observations,
    intradayCandles: { candles: baseCandles }
  });
  const after = createSnapshot({
    ...observations,
    intradayCandles: {
      candles: [
        ...baseCandles,
        createCandle(appendedTimestamp, 500, 1_000_000)
      ]
    }
  });

  return {
    asOf: AS_OF,
    appendedTimestamp,
    beforeVwap: before.indicators.vwap.value,
    afterVwap: after.indicators.vwap.value
  };
}


function evaluateInputOrderCounterexample() {
  const observations = completeObservations();
  const candles = [
    createCandle("2026-07-06T09:30:00.000Z", 100, 100),
    createCandle("2026-07-06T09:31:00.000Z", 101, 200),
    createCandle("2026-07-06T09:32:00.000Z", 102, 900)
  ];
  const ascending = createSnapshot({
    ...observations,
    intradayCandles: { candles }
  });
  const reversed = createSnapshot({
    ...observations,
    intradayCandles: { candles: [...candles].reverse() }
  });

  return {
    ascendingVolumeExpansion: ascending.indicators.profitTakingPressure.volumeExpansion,
    reversedVolumeExpansion: reversed.indicators.profitTakingPressure.volumeExpansion
  };
}


function evaluateDuplicateCandleCounterexample() {
  const observations = completeObservations();
  const first = createCandle("2026-07-06T09:30:00.000Z", 100, 100);
  const candles = [
    first,
    createCandle("2026-07-06T09:31:00.000Z", 110, 900)
  ];
  const unique = createSnapshot({
    ...observations,
    price: { ...observations.price, lastPrice: "111" },
    orderbook: defaultOrderbook(111),
    intradayCandles: { candles }
  });
  const duplicate = createSnapshot({
    ...observations,
    price: { ...observations.price, lastPrice: "111" },
    orderbook: defaultOrderbook(111),
    intradayCandles: { candles: [...candles, first] }
  });

  return {
    uniqueVwap: unique.indicators.vwap.value,
    duplicateVwap: duplicate.indicators.vwap.value
  };
}


function splitAdjustedCandle(candle, ratio) {
  return {
    ...candle,
    openPrice: String(Number(candle.openPrice) / ratio),
    highPrice: String(Number(candle.highPrice) / ratio),
    lowPrice: String(Number(candle.lowPrice) / ratio),
    closePrice: String(Number(candle.closePrice) / ratio),
    volume: String(Number(candle.volume) * ratio)
  };
}


function evaluateSplitAdjustmentCounterexample() {
  const ratio = 10;
  const candles = [
    createCandle("2026-07-06T09:30:00.000Z", 100, 1000),
    createCandle("2026-07-06T09:31:00.000Z", 101, 1000)
  ];
  const observations = {
    ...completeObservations(),
    trades: [
      { price: "100", volume: "1", timestamp: "2026-07-06T09:30:00.000Z" },
      { price: "101", volume: "10", timestamp: "2026-07-06T09:31:00.000Z" }
    ],
    intradayCandles: { candles }
  };
  const adjusted = {
    ...observations,
    price: {
      ...observations.price,
      lastPrice: String(Number(observations.price.lastPrice) / ratio)
    },
    trades: observations.trades.map((trade) => ({
      ...trade,
      price: String(Number(trade.price) / ratio),
      volume: String(Number(trade.volume) * ratio)
    })),
    orderbook: {
      ...observations.orderbook,
      asks: observations.orderbook.asks.map((entry) => ({
        price: String(Number(entry.price) / ratio),
        volume: String(Number(entry.volume) * ratio)
      })),
      bids: observations.orderbook.bids.map((entry) => ({
        price: String(Number(entry.price) / ratio),
        volume: String(Number(entry.volume) * ratio)
      }))
    },
    intradayCandles: {
      candles: observations.intradayCandles.candles.map((candle) =>
        splitAdjustedCandle(candle, ratio)
      )
    },
    dailyCandles: {
      candles: observations.dailyCandles.candles.map((candle) =>
        splitAdjustedCandle(candle, ratio)
      )
    }
  };
  const preSplit = createSnapshot(observations).indicators.cvd;
  const adjustedSplit = createSnapshot(adjusted).indicators.cvd;

  return {
    preSplit: {
      value: preSplit.value,
      label: preSplit.label,
      severity: preSplit.severity
    },
    adjustedSplit: {
      value: adjustedSplit.value,
      label: adjustedSplit.label,
      severity: adjustedSplit.severity
    }
  };
}


function evaluateRiskRewardBranchCounterexample() {
  const indicator = createSnapshot(completeObservations()).indicators.riskReward;

  return {
    ratio: indicator.ratio,
    severity: indicator.severity,
    warningReachable: indicator.ratio < 1.5 && indicator.ratio >= 1,
    dangerReachable: indicator.ratio < 1
  };
}


module.exports = {
  evaluateDuplicateCandleCounterexample,
  evaluateFutureTimestampCounterexample,
  evaluateHiddenFloorCounterexample,
  evaluateInputOrderCounterexample,
  evaluateRiskRewardBranchCounterexample,
  evaluateSplitAdjustmentCounterexample
};
