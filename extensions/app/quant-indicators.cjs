const crypto = require("node:crypto");

const { JsonFileStore } = require("./storage.cjs");

const DEFAULT_MAX_SNAPSHOTS = 500;
const ESTIMATED_CVD_REASON =
  "Toss 체결 데이터에 aggressor side가 없어 tick-rule로 추정합니다.";

class QuantIndicatorError extends Error {
  constructor(code, message, recoverable) {
    super(message);
    this.name = "QuantIndicatorError";
    this.code = code;
    this.recoverable = recoverable;
  }
}

class StoredQuantIndicatorSnapshotRepository {
  constructor(filePath, options = {}) {
    this.store = new JsonFileStore(filePath, {
      snapshots: []
    });
    this.maxSnapshots = options.maxSnapshots || DEFAULT_MAX_SNAPSHOTS;
  }

  async saveAll(snapshots) {
    const current = await this.readSnapshot();
    const nextSnapshots = [...current.snapshots, ...snapshots]
      .sort(compareSnapshots)
      .slice(-this.maxSnapshots);

    await this.store.write({
      snapshots: nextSnapshots
    });
  }

  async readLatest(cardIds) {
    const current = await this.readSnapshot();
    const latestByCardId = new Map();

    current.snapshots.forEach((snapshot) => {
      const previous = latestByCardId.get(snapshot.cardId);

      if (previous === undefined || Date.parse(snapshot.calculatedAt) > Date.parse(previous.calculatedAt)) {
        latestByCardId.set(snapshot.cardId, snapshot);
      }
    });

    if (Array.isArray(cardIds) && cardIds.length > 0) {
      return cardIds
        .map((cardId) => latestByCardId.get(cardId))
        .filter((snapshot) => snapshot !== undefined);
    }

    return [...latestByCardId.values()];
  }

  async readSnapshot() {
    const snapshot = await this.store.read();

    return {
      snapshots: Array.isArray(snapshot.snapshots) ? snapshot.snapshots : []
    };
  }
}

async function refreshQuantIndicatorsForWatchlist(context, payload) {
  const cardIds = Array.isArray(payload.cardIds) ? payload.cardIds : [];
  const latestMarketSnapshots = await context.marketDataSnapshotRepository.readLatest(cardIds);
  const snapshots = latestMarketSnapshots.map((marketDataSnapshot) =>
    createQuantIndicatorSnapshot({
      marketDataSnapshot,
      calculatedAt: context.occurredAt
    })
  );

  if (snapshots.length > 0) {
    await context.quantIndicatorSnapshotRepository.saveAll(snapshots);
  }

  return {
    refreshedAt: context.occurredAt,
    snapshots
  };
}

async function refreshQuantIndicatorsForCard(context, payload) {
  const latestMarketSnapshots = await context.marketDataSnapshotRepository.readLatest([
    payload.cardId
  ]);
  const marketDataSnapshot = latestMarketSnapshots[0];

  if (marketDataSnapshot === undefined) {
    throw new QuantIndicatorError(
      "quant_indicator_snapshot_not_found",
      "market data snapshot was not found for quant indicator calculation",
      true
    );
  }

  const snapshot = createQuantIndicatorSnapshot({
    marketDataSnapshot,
    calculatedAt: context.occurredAt
  });
  await context.quantIndicatorSnapshotRepository.saveAll([snapshot]);

  return {
    refreshedAt: context.occurredAt,
    snapshot
  };
}

async function readLatestQuantIndicatorSnapshots(context, payload) {
  return {
    snapshots: await context.quantIndicatorSnapshotRepository.readLatest(
      Array.isArray(payload.cardIds) ? payload.cardIds : undefined
    )
  };
}

function createQuantIndicatorSnapshot(input) {
  const marketDataSnapshot = input.marketDataSnapshot || {};
  const observations = marketDataSnapshot.observations || {};
  const price = readDecimal(observations.price && observations.price.lastPrice);
  const indicators = {
    vwap: calculateVwap(observations.intradayCandles, price),
    cvd: calculateEstimatedCvd(observations.trades),
    spread: calculateSpreadRisk(observations.orderbook),
    atrStop: calculateAtrStopRisk(observations.dailyCandles, price),
    supplyPressure: calculateSupplyPressure(observations.intradayCandles, price),
    riskReward: createUnavailableRiskReward()
  };
  indicators.riskReward = calculateRiskReward(
    observations.dailyCandles,
    price,
    indicators.atrStop
  );
  const decision = classifyCardDecision(indicators);

  return {
    snapshotId: crypto.randomUUID(),
    sourceMarketDataSnapshotId: String(marketDataSnapshot.snapshotId || ""),
    cardId: String(marketDataSnapshot.cardId || ""),
    market: normalizeText(marketDataSnapshot.market),
    symbol: normalizeText(marketDataSnapshot.symbol),
    calculatedAt: input.calculatedAt,
    quality: calculateQuality(indicators),
    decisionStatus: decision.status,
    decisionLabel: decision.label,
    nextCheckLabel: decision.nextCheckLabel,
    indicators,
    signals: selectSignals(indicators, decision.status)
  };
}

function calculateVwap(candlePage, currentPrice) {
  const candles = readCandles(candlePage);

  if (candles.length === 0) {
    return unavailableIndicator("intraday candles are required", "VWAP 계산 불가");
  }

  let volumeSum = 0;
  let weightedPriceSum = 0;

  candles.forEach((candle) => {
    const high = readDecimal(candle.highPrice);
    const low = readDecimal(candle.lowPrice);
    const close = readDecimal(candle.closePrice);
    const volume = readDecimal(candle.volume);

    if ([high, low, close, volume].every(Number.isFinite) && volume > 0) {
      const typicalPrice = (high + low + close) / 3;
      weightedPriceSum += typicalPrice * volume;
      volumeSum += volume;
    }
  });

  if (volumeSum <= 0 || !Number.isFinite(currentPrice)) {
    return unavailableIndicator("price and candle volume are required", "VWAP 계산 불가");
  }

  const value = weightedPriceSum / volumeSum;
  const distanceBps = Math.round(((currentPrice - value) / value) * 10_000);

  if (distanceBps >= 0) {
    return availableVwap(value, distanceBps, "VWAP 위 안착", "positive");
  }

  if (distanceBps > -80) {
    return availableVwap(value, distanceBps, "VWAP 재돌파 필요", "warning");
  }

  return availableVwap(value, distanceBps, "VWAP 이탈", "danger");
}

function calculateEstimatedCvd(trades) {
  if (!Array.isArray(trades) || trades.length < 2) {
    return {
      status: "unavailable",
      value: null,
      confidence: "unavailable",
      label: "체결 압력 계산 불가",
      severity: "unavailable",
      unavailableReason: "at least two trades are required"
    };
  }

  const orderedTrades = [...trades].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
  let cumulativeDelta = 0;

  for (let index = 1; index < orderedTrades.length; index += 1) {
    const previousPrice = readDecimal(orderedTrades[index - 1].price);
    const currentPrice = readDecimal(orderedTrades[index].price);
    const volume = readDecimal(orderedTrades[index].volume);

    if (!Number.isFinite(previousPrice) || !Number.isFinite(currentPrice) || !Number.isFinite(volume)) {
      continue;
    }

    if (currentPrice > previousPrice) {
      cumulativeDelta += volume;
    } else if (currentPrice < previousPrice) {
      cumulativeDelta -= volume;
    }
  }

  if (cumulativeDelta >= 20) {
    return estimatedCvd(cumulativeDelta, "체결 압력 우위", "positive");
  }

  if (cumulativeDelta <= -20) {
    return estimatedCvd(cumulativeDelta, "체결 압력 둔화", "danger");
  }

  return estimatedCvd(cumulativeDelta, "체결 중립", "neutral");
}

function calculateSpreadRisk(orderbook) {
  const bestAsk = orderbook && Array.isArray(orderbook.asks) ? orderbook.asks[0] : undefined;
  const bestBid = orderbook && Array.isArray(orderbook.bids) ? orderbook.bids[0] : undefined;
  const askPrice = readDecimal(bestAsk && bestAsk.price);
  const bidPrice = readDecimal(bestBid && bestBid.price);

  if (!Number.isFinite(askPrice) || !Number.isFinite(bidPrice) || askPrice <= bidPrice) {
    return {
      status: "unavailable",
      spreadBps: null,
      label: "스프레드 계산 불가",
      severity: "unavailable",
      unavailableReason: "orderbook asks and bids are required"
    };
  }

  const midpoint = (askPrice + bidPrice) / 2;
  const spreadBps = Math.round(((askPrice - bidPrice) / midpoint) * 10_000);

  if (spreadBps <= 30) {
    return availableSpread(spreadBps, "스프레드 정상", "positive");
  }

  if (spreadBps <= 70) {
    return availableSpread(spreadBps, "스프레드 확대", "warning");
  }

  return availableSpread(spreadBps, "스프레드 위험", "danger");
}

function calculateAtrStopRisk(candlePage, currentPrice) {
  const candles = readCandles(candlePage);

  if (candles.length < 15) {
    return {
      status: "unavailable",
      atr: null,
      stopDistancePercent: null,
      label: "손절 폭 계산 불가",
      severity: "unavailable",
      unavailableReason: "at least 15 daily candles are required"
    };
  }

  const trueRanges = [];

  for (let index = 1; index < candles.length; index += 1) {
    const high = readDecimal(candles[index].highPrice);
    const low = readDecimal(candles[index].lowPrice);
    const previousClose = readDecimal(candles[index - 1].closePrice);

    if ([high, low, previousClose].every(Number.isFinite)) {
      trueRanges.push(Math.max(high - low, Math.abs(high - previousClose), Math.abs(low - previousClose)));
    }
  }

  const recentTrueRanges = trueRanges.slice(-14);

  if (recentTrueRanges.length < 14 || !Number.isFinite(currentPrice) || currentPrice <= 0) {
    return {
      status: "unavailable",
      atr: null,
      stopDistancePercent: null,
      label: "손절 폭 계산 불가",
      severity: "unavailable",
      unavailableReason: "valid daily ranges and price are required"
    };
  }

  const atr = average(recentTrueRanges);
  const stopDistancePercent = roundTo((atr / currentPrice) * 100, 2);

  if (stopDistancePercent <= 2) {
    return availableAtrStop(atr, stopDistancePercent, "손절 폭 정상", "positive");
  }

  if (stopDistancePercent <= 4) {
    return availableAtrStop(atr, stopDistancePercent, "손절 폭 주의", "warning");
  }

  return availableAtrStop(atr, stopDistancePercent, "손절 폭 과대", "danger");
}

function calculateSupplyPressure(candlePage, currentPrice) {
  const candles = readCandles(candlePage);

  if (candles.length === 0 || !Number.isFinite(currentPrice)) {
    return {
      status: "unavailable",
      pocPrice: null,
      overheadRatio: null,
      label: "매물대 계산 불가",
      severity: "unavailable",
      unavailableReason: "intraday candles and price are required"
    };
  }

  let totalVolume = 0;
  let overheadVolume = 0;
  let pocPrice = null;
  let pocVolume = -Infinity;

  candles.forEach((candle) => {
    const high = readDecimal(candle.highPrice);
    const low = readDecimal(candle.lowPrice);
    const close = readDecimal(candle.closePrice);
    const volume = readDecimal(candle.volume);

    if (![high, low, close, volume].every(Number.isFinite) || volume <= 0) {
      return;
    }

    const typicalPrice = (high + low + close) / 3;
    totalVolume += volume;

    if (typicalPrice > currentPrice) {
      overheadVolume += volume;
    }

    if (volume > pocVolume) {
      pocVolume = volume;
      pocPrice = typicalPrice;
    }
  });

  if (totalVolume <= 0 || pocPrice === null) {
    return {
      status: "unavailable",
      pocPrice: null,
      overheadRatio: null,
      label: "매물대 계산 불가",
      severity: "unavailable",
      unavailableReason: "valid candle volume is required"
    };
  }

  const overheadRatio = roundTo(overheadVolume / totalVolume, 2);

  if (overheadRatio <= 0.2) {
    return availableSupplyPressure(pocPrice, overheadRatio, "매물대 부담 낮음", "positive");
  }

  if (overheadRatio <= 0.45) {
    return availableSupplyPressure(pocPrice, overheadRatio, "매물대 부담", "warning");
  }

  return availableSupplyPressure(pocPrice, overheadRatio, "상단 매물대 근접", "danger");
}

function calculateRiskReward(candlePage, currentPrice, atrStop) {
  const candles = readCandles(candlePage);

  if (
    candles.length === 0 ||
    !Number.isFinite(currentPrice) ||
    atrStop.status !== "available" ||
    atrStop.atr === null
  ) {
    return createUnavailableRiskReward();
  }

  const atr = readDecimal(atrStop.atr);
  const priorHigh = Math.max(...candles.map((candle) => readDecimal(candle.highPrice)).filter(Number.isFinite));
  const targetPrice = Math.max(priorHigh, currentPrice + atr * 2);
  const ratio = atr > 0 ? roundTo((targetPrice - currentPrice) / atr, 2) : null;

  if (ratio === null || !Number.isFinite(ratio)) {
    return createUnavailableRiskReward();
  }

  if (ratio >= 1.5) {
    return availableRiskReward(ratio, "손익비 1.5x 이상", "positive");
  }

  if (ratio >= 1) {
    return availableRiskReward(ratio, "손익비 주의", "warning");
  }

  return availableRiskReward(ratio, "손익비 1.5x 미달", "danger");
}

function classifyCardDecision(indicators) {
  if (Object.values(indicators).some((indicator) => indicator.status === "unavailable")) {
    return {
      status: "dataInsufficient",
      label: "데이터 부족",
      nextCheckLabel: "시장 데이터 수집 후 재계산"
    };
  }

  if (indicators.vwap.severity === "danger" && indicators.cvd.severity === "danger") {
    return {
      status: "invalidated",
      label: "무효화",
      nextCheckLabel: "시나리오 무효, 손절 우선"
    };
  }

  if (
    indicators.spread.severity === "danger" ||
    indicators.atrStop.severity === "danger" ||
    indicators.supplyPressure.severity === "danger" ||
    indicators.riskReward.severity === "danger"
  ) {
    return {
      status: "riskHigh",
      label: "리스크 높음",
      nextCheckLabel: "손절 폭과 매물대 부담 재확인"
    };
  }

  if (
    indicators.vwap.severity === "warning" ||
    indicators.cvd.severity === "warning" ||
    indicators.spread.severity === "warning" ||
    indicators.atrStop.severity === "warning" ||
    indicators.supplyPressure.severity === "warning" ||
    indicators.riskReward.severity === "warning"
  ) {
    return {
      status: "confirmationWaiting",
      label: "확인 대기",
      nextCheckLabel: "VWAP 재돌파와 체결 압력 회복 확인"
    };
  }

  return {
    status: "watch",
    label: "관망",
    nextCheckLabel: "VWAP 위 안착 유지 확인"
  };
}

function calculateQuality(indicators) {
  const values = Object.values(indicators);
  const unavailableCount = values.filter((indicator) => indicator.status === "unavailable").length;

  if (unavailableCount === values.length) {
    return "unavailable";
  }

  return unavailableCount > 0 ? "partial" : "complete";
}

function selectSignals(indicators, decisionStatus) {
  if (decisionStatus === "dataInsufficient") {
    return Object.entries(indicators)
      .filter(([, indicator]) => indicator.status === "unavailable")
      .slice(0, 3)
      .map(([key, indicator]) => toSignal(key, indicator));
  }

  const priority = ["vwap", "cvd", "spread", "atrStop", "supplyPressure", "riskReward"];

  return priority.map((key) => toSignal(key, indicators[key])).slice(0, 3);
}

function toSignal(key, indicator) {
  return {
    key,
    label: indicator.label,
    severity: indicator.severity,
    status: indicator.status,
    reason: key === "cvd" && indicator.status === "estimated"
      ? ESTIMATED_CVD_REASON
      : indicator.unavailableReason || null
  };
}

function unavailableIndicator(reason, label) {
  return {
    status: "unavailable",
    value: null,
    distanceBps: null,
    label,
    severity: "unavailable",
    unavailableReason: reason
  };
}

function availableVwap(value, distanceBps, label, severity) {
  return {
    status: "available",
    value: formatDecimal(value),
    distanceBps,
    label,
    severity,
    unavailableReason: null
  };
}

function estimatedCvd(value, label, severity) {
  return {
    status: "estimated",
    value: String(roundTo(value, 4)).replace(/\.0+$/, ""),
    confidence: "estimated",
    label,
    severity,
    unavailableReason: null
  };
}

function availableSpread(spreadBps, label, severity) {
  return {
    status: "available",
    spreadBps,
    label,
    severity,
    unavailableReason: null
  };
}

function availableAtrStop(atr, stopDistancePercent, label, severity) {
  return {
    status: "available",
    atr: formatDecimal(atr),
    stopDistancePercent,
    label,
    severity,
    unavailableReason: null
  };
}

function availableSupplyPressure(pocPrice, overheadRatio, label, severity) {
  return {
    status: "available",
    pocPrice: formatDecimal(pocPrice),
    overheadRatio,
    label,
    severity,
    unavailableReason: null
  };
}

function createUnavailableRiskReward() {
  return {
    status: "unavailable",
    ratio: null,
    label: "손익비 계산 불가",
    severity: "unavailable",
    unavailableReason: "price, ATR, and target reference are required"
  };
}

function availableRiskReward(ratio, label, severity) {
  return {
    status: "available",
    ratio,
    label,
    severity,
    unavailableReason: null
  };
}

function readCandles(candlePage) {
  return candlePage && Array.isArray(candlePage.candles) ? candlePage.candles : [];
}

function readDecimal(value) {
  const decimal = Number(value);

  return Number.isFinite(decimal) ? decimal : Number.NaN;
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function roundTo(value, digits) {
  const factor = 10 ** digits;

  return Math.round(value * factor) / factor;
}

function formatDecimal(value) {
  return value.toFixed(4);
}

function normalizeText(value) {
  return String(value ?? "").trim().toUpperCase();
}

function compareSnapshots(left, right) {
  return Date.parse(left.calculatedAt) - Date.parse(right.calculatedAt);
}

module.exports = {
  QuantIndicatorError,
  StoredQuantIndicatorSnapshotRepository,
  createQuantIndicatorSnapshot,
  readLatestQuantIndicatorSnapshots,
  refreshQuantIndicatorsForCard,
  refreshQuantIndicatorsForWatchlist
};
