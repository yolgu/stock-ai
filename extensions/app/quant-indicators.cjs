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
  const volumeProfile = createVolumeProfile(observations.intradayCandles, price);
  const indicators = {
    basicReturn: calculateBasicReturn(
      observations.price,
      observations.dailyCandles,
      marketDataSnapshot.capturedAt
    ),
    vwap: calculateVwap(observations.intradayCandles, price),
    cvd: calculateEstimatedCvd(observations.trades),
    spread: calculateSpreadRisk(observations.orderbook),
    atrStop: calculateAtrStopRisk(observations.dailyCandles, price),
    supplyPressure: calculateSupplyPressure(volumeProfile),
    profitTakingPressure: createUnavailableProfitTakingPressure(),
    riskReward: createUnavailableRiskReward(),
    velocityAcceleration: calculateVelocityAcceleration(
      observations.intradayCandles,
      observations.trades
    ),
    distanceProfile: createUnavailableDistanceProfile(),
    rsiMomentum: calculateRsiMomentum(observations.intradayCandles),
    marketSentimentScore: createUnavailableMarketSentimentScore(),
    intradayTradeScore: createUnavailableIntradayTradeScore()
  };
  indicators.distanceProfile = calculateDistanceProfile(
    observations.intradayCandles,
    observations.dailyCandles,
    price,
    indicators.vwap,
    indicators.atrStop
  );
  indicators.riskReward = calculateRiskReward(
    observations.dailyCandles,
    price,
    indicators.atrStop
  );
  indicators.profitTakingPressure = calculateProfitTakingPressure({
    volumeProfile,
    currentPrice: price,
    vwap: indicators.vwap,
    atrStop: indicators.atrStop,
    spread: indicators.spread,
    trades: observations.trades,
    orderbook: observations.orderbook,
    intradayCandles: observations.intradayCandles
  });
  indicators.marketSentimentScore = calculateMarketSentimentScore(indicators);
  indicators.intradayTradeScore = calculateIntradayTradeScore(
    indicators.marketSentimentScore
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
    signals: selectSignals(indicators, decision.status),
    explanationTraces: createExplanationTraces(observations, indicators)
  };
}

function calculateBasicReturn(priceObservation, candlePage, capturedAt) {
  const currentPrice = readDecimal(priceObservation && priceObservation.lastPrice);
  const referencePrice = readPreviousClose(priceObservation, candlePage, capturedAt);
  const currency = normalizeText(priceObservation && priceObservation.currency);

  if (!Number.isFinite(currentPrice) || !Number.isFinite(referencePrice) || referencePrice <= 0) {
    return unavailableBasicReturn(currency);
  }

  const absoluteChange = currentPrice - referencePrice;
  const simpleReturnPercent = roundTo((absoluteChange / referencePrice) * 100, 2);
  const logReturnPercent = roundTo(Math.log(currentPrice / referencePrice) * 100, 2);

  if (simpleReturnPercent > 0) {
    return availableBasicReturn(
      currentPrice,
      referencePrice,
      absoluteChange,
      simpleReturnPercent,
      logReturnPercent,
      currency,
      "전일 종가 대비 상승",
      "positive"
    );
  }

  if (simpleReturnPercent < 0) {
    return availableBasicReturn(
      currentPrice,
      referencePrice,
      absoluteChange,
      simpleReturnPercent,
      logReturnPercent,
      currency,
      "전일 종가 대비 하락",
      "danger"
    );
  }

  return availableBasicReturn(
    currentPrice,
    referencePrice,
    absoluteChange,
    simpleReturnPercent,
    logReturnPercent,
    currency,
    "전일 종가 대비 보합",
    "neutral"
  );
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

function calculateSupplyPressure(volumeProfile) {
  if (volumeProfile.status !== "available") {
    return {
      status: "unavailable",
      pocPrice: null,
      overheadRatio: null,
      label: "매물대 계산 불가",
      severity: "unavailable",
      unavailableReason: volumeProfile.unavailableReason
    };
  }

  const overheadRatio = volumeProfile.overheadRatio;

  if (overheadRatio <= 0.2) {
    return availableSupplyPressure(volumeProfile.pocPrice, overheadRatio, "매물대 부담 낮음", "positive");
  }

  if (overheadRatio <= 0.45) {
    return availableSupplyPressure(volumeProfile.pocPrice, overheadRatio, "매물대 부담", "warning");
  }

  return availableSupplyPressure(volumeProfile.pocPrice, overheadRatio, "상단 매물대 근접", "danger");
}

function calculateProfitTakingPressure(input) {
  const atr = readDecimal(input.atrStop && input.atrStop.atr);
  const vwap = readDecimal(input.vwap && input.vwap.value);

  if (
    input.volumeProfile.status !== "available" ||
    !Number.isFinite(input.currentPrice) ||
    input.vwap.status !== "available" ||
    input.atrStop.status !== "available" ||
    !Number.isFinite(vwap) ||
    !Number.isFinite(atr) ||
    atr <= 0
  ) {
    return createUnavailableProfitTakingPressure();
  }

  const profitLongRatio = input.volumeProfile.profitLongRatio;
  const weightedProfitPressure = input.volumeProfile.weightedProfitPressure;
  const vwapAtrExtension = clip((Math.max(input.currentPrice - vwap, 0) / atr), 0, 1);
  const hasTradeFlow = hasDirectionalTradeFlow(input.trades);
  const hasOrderbookPressure = hasOrderbookDepth(input.orderbook);
  const sellFlowPressure = hasTradeFlow ? calculateSellFlowPressure(input.trades) : 0;
  const askBookPressure = hasOrderbookPressure ? calculateAskBookPressure(input.orderbook) : 0;
  const volumeExpansion = input.volumeProfile.volumeExpansion;
  const causes = {
    profitBurden: calculateProfitBurdenCause(input.volumeProfile, atr, vwapAtrExtension),
    realizedSellPressure: calculateRealizedSellPressureCause(input.trades, input.orderbook),
    overheadSupplyPressure: calculateOverheadSupplyPressureCause(input.volumeProfile, atr),
    liquidityImpactRisk: calculateLiquidityImpactRiskCause(
      input.orderbook,
      input.intradayCandles,
      input.spread
    )
  };
  const score = calculateProfitTakingRiskScore(causes);
  const level = classifyRiskScore(score);

  return availableProfitTakingPressure(
    profitLongRatio,
    weightedProfitPressure,
    vwapAtrExtension,
    sellFlowPressure,
    askBookPressure,
    volumeExpansion,
    score,
    `차익실현 리스크 ${level.labelSuffix}`,
    level.severity,
    causes
  );
}

function calculateProfitBurdenCause(volumeProfile, atr, vwapAtrExtension) {
  const profitGainMass = clip(volumeProfile.profitGainPriceDistance / atr, 0, 1);
  const score = Math.round(
    100 * (
      0.45 * volumeProfile.profitLongRatio +
      0.35 * profitGainMass +
      0.20 * vwapAtrExtension
    )
  );

  return availableProfitTakingCause(
    score,
    "수익권 부담",
    "수익권 물량과 VWAP/ATR 이격이 함께 큽니다."
  );
}

function calculateRealizedSellPressureCause(trades, orderbook) {
  const tradeFlow = calculateDirectionalTradeFlow(trades);
  const hasTradeFlow = tradeFlow.totalVolume > 0;
  const hasOrderbookPressure = hasOrderbookDepth(orderbook);

  if (!hasTradeFlow && !hasOrderbookPressure) {
    return unavailableProfitTakingCause(
      "실제 매도 압력",
      "recent trades or orderbook depth are required"
    );
  }

  const components = [
    { value: hasTradeFlow ? tradeFlow.sellFlowPressure : null, weight: 0.45 },
    { value: hasTradeFlow ? tradeFlow.aggressiveSellRatio : null, weight: 0.30 },
    { value: hasOrderbookPressure ? calculateAskBookPressure(orderbook) : null, weight: 0.25 }
  ];
  const score = calculateWeightedComponentScore(components);

  return availableProfitTakingCause(
    score,
    "실제 매도 압력",
    "최근 체결 방향과 호가 잔량으로 추정합니다.",
    "estimated"
  );
}

function calculateOverheadSupplyPressureCause(volumeProfile, atr) {
  const overheadLossMass = clip(volumeProfile.overheadLossPriceDistance / atr, 0, 1);
  const score = Math.round(
    100 * (
      0.60 * volumeProfile.overheadRatio +
      0.40 * overheadLossMass
    )
  );

  return availableProfitTakingCause(
    score,
    "위쪽 매물 부담",
    "현재가 위 거래량 부담을 ATR 기준으로 봅니다."
  );
}

function calculateLiquidityImpactRiskCause(orderbook, candlePage, spread) {
  const components = [
    { value: calculateSpreadRiskComponent(spread), weight: 0.45 },
    { value: calculateDepthThinness(orderbook, candlePage), weight: 0.35 },
    { value: calculatePriceImpactRisk(candlePage), weight: 0.20 }
  ];
  const hasAnyComponent = components.some((component) => component.value !== null);

  if (!hasAnyComponent) {
    return unavailableProfitTakingCause(
      "체결 환경 위험",
      "spread, orderbook depth, or intraday candles are required"
    );
  }

  const hasAllComponents = components.every((component) => component.value !== null);
  const score = calculateWeightedComponentScore(components);

  return availableProfitTakingCause(
    score,
    "체결 환경 위험",
    "스프레드, 호가 깊이, 최근 가격충격으로 추정합니다.",
    hasAllComponents ? "available" : "estimated"
  );
}

function calculateProfitTakingRiskScore(causes) {
  const baseScore = Math.round(
    0.35 * readCauseScore(causes.profitBurden) +
    0.30 * readCauseScore(causes.realizedSellPressure) +
    0.25 * readCauseScore(causes.overheadSupplyPressure) +
    0.10 * readCauseScore(causes.liquidityImpactRisk)
  );
  const confirmedSellingScore = (
    readCauseScore(causes.realizedSellPressure) >= 70 &&
    readCauseScore(causes.profitBurden) >= 55
  )
    ? Math.max(baseScore, 75)
    : baseScore;
  const highSingleCauseScore = Object.values(causes).some((cause) =>
    typeof cause.score === "number" && cause.score >= 85
  )
    ? Math.max(confirmedSellingScore, 65)
    : confirmedSellingScore;

  return clip(highSingleCauseScore, 0, 100);
}

function createVolumeProfile(candlePage, currentPrice) {
  const candles = readCandles(candlePage);

  if (candles.length === 0 || !Number.isFinite(currentPrice)) {
    return unavailableVolumeProfile("intraday candles and price are required");
  }

  const binsByPrice = new Map();
  const candleVolumes = [];

  candles.forEach((candle) => {
    const high = readDecimal(candle.highPrice);
    const low = readDecimal(candle.lowPrice);
    const close = readDecimal(candle.closePrice);
    const volume = readDecimal(candle.volume);

    if (![high, low, close, volume].every(Number.isFinite) || volume <= 0) {
      return;
    }

    const typicalPrice = (high + low + close) / 3;
    const binPrice = roundTo(typicalPrice, 2);
    const previousVolume = binsByPrice.get(binPrice) || 0;

    binsByPrice.set(binPrice, previousVolume + volume);
    candleVolumes.push(volume);
  });

  const bins = [...binsByPrice.entries()].map(([price, volume]) => ({ price, volume }));
  const totalVolume = sum(bins.map((bin) => bin.volume));

  if (bins.length === 0 || totalVolume <= 0) {
    return unavailableVolumeProfile("valid candle volume is required");
  }

  const pocBin = bins.reduce((currentPoc, bin) =>
    bin.volume > currentPoc.volume ? bin : currentPoc
  );
  const overheadVolume = sum(bins.filter((bin) => bin.price > currentPrice).map((bin) => bin.volume));
  const profitLongVolume = sum(bins.filter((bin) => bin.price < currentPrice).map((bin) => bin.volume));
  const weightedProfitSum = sum(
    bins.map((bin) => bin.volume * Math.max((currentPrice - bin.price) / bin.price, 0))
  );
  const profitGainDistanceSum = sum(
    bins.map((bin) => bin.volume * Math.max(currentPrice - bin.price, 0))
  );
  const overheadLossDistanceSum = sum(
    bins.map((bin) => bin.volume * Math.max(bin.price - currentPrice, 0))
  );
  const latestVolume = candleVolumes[candleVolumes.length - 1];
  const averageVolume = average(candleVolumes);

  return {
    status: "available",
    pocPrice: pocBin.price,
    overheadRatio: roundTo(overheadVolume / totalVolume, 2),
    profitLongRatio: roundTo(profitLongVolume / totalVolume, 2),
    weightedProfitPressure: roundTo(weightedProfitSum / totalVolume, 2),
    profitGainPriceDistance: profitGainDistanceSum / totalVolume,
    overheadLossPriceDistance: overheadLossDistanceSum / totalVolume,
    volumeExpansion: roundTo(clip((latestVolume / averageVolume) / 2, 0, 1), 2),
    unavailableReason: null
  };
}

function unavailableVolumeProfile(reason) {
  return {
    status: "unavailable",
    pocPrice: null,
    overheadRatio: null,
    profitLongRatio: null,
    weightedProfitPressure: null,
    profitGainPriceDistance: null,
    overheadLossPriceDistance: null,
    volumeExpansion: null,
    unavailableReason: reason
  };
}

function calculateSellFlowPressure(trades) {
  return calculateDirectionalTradeFlow(trades).sellFlowPressure;
}

function calculateDirectionalTradeFlow(trades) {
  if (!Array.isArray(trades) || trades.length < 2) {
    return {
      buyVolume: 0,
      sellVolume: 0,
      totalVolume: 0,
      sellFlowPressure: 0,
      aggressiveSellRatio: 0
    };
  }

  const orderedTrades = [...trades].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
  let buyVolume = 0;
  let sellVolume = 0;

  for (let index = 1; index < orderedTrades.length; index += 1) {
    const previousPrice = readDecimal(orderedTrades[index - 1].price);
    const currentPrice = readDecimal(orderedTrades[index].price);
    const volume = readDecimal(orderedTrades[index].volume);

    if (!Number.isFinite(previousPrice) || !Number.isFinite(currentPrice) || !Number.isFinite(volume)) {
      continue;
    }

    if (currentPrice > previousPrice) {
      buyVolume += volume;
    } else if (currentPrice < previousPrice) {
      sellVolume += volume;
    }
  }

  const totalVolume = buyVolume + sellVolume;

  if (totalVolume <= 0) {
    return {
      buyVolume,
      sellVolume,
      totalVolume: 0,
      sellFlowPressure: 0,
      aggressiveSellRatio: 0
    };
  }

  return {
    buyVolume,
    sellVolume,
    totalVolume,
    sellFlowPressure: roundTo(clip((sellVolume - buyVolume) / totalVolume, 0, 1), 2),
    aggressiveSellRatio: roundTo(sellVolume / totalVolume, 2)
  };
}

function hasDirectionalTradeFlow(trades) {
  if (!Array.isArray(trades) || trades.length < 2) {
    return false;
  }

  const orderedTrades = [...trades].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );

  for (let index = 1; index < orderedTrades.length; index += 1) {
    const previousPrice = readDecimal(orderedTrades[index - 1].price);
    const currentPrice = readDecimal(orderedTrades[index].price);
    const volume = readDecimal(orderedTrades[index].volume);

    if (
      Number.isFinite(previousPrice) &&
      Number.isFinite(currentPrice) &&
      Number.isFinite(volume) &&
      volume > 0 &&
      currentPrice !== previousPrice
    ) {
      return true;
    }
  }

  return false;
}

function calculateAskBookPressure(orderbook) {
  const depth = readOrderbookDepth(orderbook);

  if (depth.totalVolume <= 0) {
    return 0;
  }

  return roundTo(clip((depth.askVolume - depth.bidVolume) / depth.totalVolume, 0, 1), 2);
}

function hasOrderbookDepth(orderbook) {
  return readOrderbookDepth(orderbook).totalVolume > 0;
}

function readOrderbookDepth(orderbook) {
  const asks = orderbook && Array.isArray(orderbook.asks) ? orderbook.asks : [];
  const bids = orderbook && Array.isArray(orderbook.bids) ? orderbook.bids : [];
  const askVolume = sum(asks.map((ask) => readDecimal(ask.volume)).filter(Number.isFinite));
  const bidVolume = sum(bids.map((bid) => readDecimal(bid.volume)).filter(Number.isFinite));

  return {
    askVolume,
    bidVolume,
    totalVolume: askVolume + bidVolume
  };
}

function calculateSpreadRiskComponent(spread) {
  if (!spread || spread.status !== "available" || !Number.isFinite(spread.spreadBps)) {
    return null;
  }

  return clip(spread.spreadBps / 50, 0, 1);
}

function calculateDepthThinness(orderbook, candlePage) {
  const orderbookNotional = calculateOrderbookNotional(orderbook);
  const averageMinuteDollarVolume = calculateAverageMinuteDollarVolume(candlePage);

  if (orderbookNotional <= 0 || averageMinuteDollarVolume <= 0) {
    return null;
  }

  return clip(1 - clip(orderbookNotional / averageMinuteDollarVolume, 0, 1), 0, 1);
}

function calculateOrderbookNotional(orderbook) {
  const asks = orderbook && Array.isArray(orderbook.asks) ? orderbook.asks : [];
  const bids = orderbook && Array.isArray(orderbook.bids) ? orderbook.bids : [];
  const entries = [...asks, ...bids];

  return sum(entries.map((entry) => {
    const price = readDecimal(entry.price);
    const volume = readDecimal(entry.volume);

    return Number.isFinite(price) && Number.isFinite(volume) && price > 0 && volume > 0
      ? price * volume
      : 0;
  }));
}

function calculateAverageMinuteDollarVolume(candlePage) {
  const candles = readOrderedCandles(candlePage);
  const recentDollarVolumes = candles.slice(-20).map((candle) => {
    const close = readDecimal(candle.closePrice);
    const volume = readDecimal(candle.volume);

    return Number.isFinite(close) && Number.isFinite(volume) && close > 0 && volume > 0
      ? close * volume
      : 0;
  }).filter((value) => value > 0);

  return recentDollarVolumes.length === 0 ? 0 : average(recentDollarVolumes);
}

function calculatePriceImpactRisk(candlePage) {
  const candles = readOrderedCandles(candlePage);
  const impacts = [];

  for (let index = 1; index < candles.length; index += 1) {
    const previousClose = readDecimal(candles[index - 1].closePrice);
    const close = readDecimal(candles[index].closePrice);
    const volume = readDecimal(candles[index].volume);

    if (
      Number.isFinite(previousClose) &&
      Number.isFinite(close) &&
      Number.isFinite(volume) &&
      previousClose > 0 &&
      close > 0 &&
      volume > 0
    ) {
      impacts.push(Math.abs(Math.log(close / previousClose)) / (close * volume));
    }
  }

  if (impacts.length < 2) {
    return null;
  }

  const latestImpact = impacts[impacts.length - 1];
  const medianImpact = median(impacts.slice(0, -1));

  if (!Number.isFinite(medianImpact) || medianImpact <= 0) {
    return 0;
  }

  return clip((latestImpact / medianImpact) / 2, 0, 1);
}

function calculateWeightedComponentScore(components) {
  const availableComponents = components.filter((component) =>
    typeof component.value === "number" && Number.isFinite(component.value)
  );
  const totalWeight = sum(availableComponents.map((component) => component.weight));

  if (totalWeight <= 0) {
    return null;
  }

  return Math.round(
    100 *
    sum(availableComponents.map((component) => component.value * component.weight)) /
    totalWeight
  );
}

function readCauseScore(cause) {
  return typeof cause.score === "number" && Number.isFinite(cause.score) ? cause.score : 0;
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

function calculateVelocityAcceleration(candlePage, trades) {
  const candles = readOrderedCandles(candlePage);

  if (candles.length < 3) {
    return createUnavailableVelocityAcceleration();
  }

  const latest = candles[candles.length - 1];
  const previous = candles[candles.length - 2];
  const beforePrevious = candles[candles.length - 3];
  const latestClose = readDecimal(latest.closePrice);
  const previousClose = readDecimal(previous.closePrice);
  const beforePreviousClose = readDecimal(beforePrevious.closePrice);
  const latestVolume = readDecimal(latest.volume);
  const previousVolume = readDecimal(previous.volume);

  if (
    ![latestClose, previousClose, beforePreviousClose, latestVolume, previousVolume].every(Number.isFinite) ||
    latestClose <= 0 ||
    previousClose <= 0 ||
    beforePreviousClose <= 0 ||
    previousVolume <= 0
  ) {
    return createUnavailableVelocityAcceleration();
  }

  const latestLogReturnPercent = roundTo(Math.log(latestClose / previousClose) * 100, 2);
  const previousLogReturnPercent = roundTo(Math.log(previousClose / beforePreviousClose) * 100, 2);
  const priceAccelerationPercent = roundTo(latestLogReturnPercent - previousLogReturnPercent, 2);
  const volumeChangePercent = roundTo(((latestVolume - previousVolume) / previousVolume) * 100, 2);
  const estimatedCvdChange = calculateEstimatedCvdChange(trades);

  if (latestLogReturnPercent > 0 && priceAccelerationPercent >= 0) {
    return availableVelocityAcceleration(
      latestLogReturnPercent,
      priceAccelerationPercent,
      volumeChangePercent,
      estimatedCvdChange,
      "상승 가속",
      "positive"
    );
  }

  if (latestLogReturnPercent > 0) {
    return availableVelocityAcceleration(
      latestLogReturnPercent,
      priceAccelerationPercent,
      volumeChangePercent,
      estimatedCvdChange,
      "상승 속도 둔화",
      "warning"
    );
  }

  if (latestLogReturnPercent < 0 && priceAccelerationPercent < 0) {
    return availableVelocityAcceleration(
      latestLogReturnPercent,
      priceAccelerationPercent,
      volumeChangePercent,
      estimatedCvdChange,
      "하락 가속",
      "danger"
    );
  }

  if (latestLogReturnPercent < 0) {
    return availableVelocityAcceleration(
      latestLogReturnPercent,
      priceAccelerationPercent,
      volumeChangePercent,
      estimatedCvdChange,
      "하락 속도 둔화",
      "warning"
    );
  }

  return availableVelocityAcceleration(
    latestLogReturnPercent,
    priceAccelerationPercent,
    volumeChangePercent,
    estimatedCvdChange,
    "속도 중립",
    "neutral"
  );
}

function calculateDistanceProfile(candlePage, dailyCandlePage, currentPrice, vwap, atrStop) {
  const candles = readOrderedCandles(candlePage);
  const previousClose = readPreviousClose(null, dailyCandlePage, null);
  const atr = readDecimal(atrStop.atr);

  if (
    candles.length < 20 ||
    !Number.isFinite(currentPrice) ||
    currentPrice <= 0 ||
    vwap.status !== "available" ||
    atrStop.status !== "available" ||
    !Number.isFinite(previousClose) ||
    !Number.isFinite(atr) ||
    atr <= 0
  ) {
    return createUnavailableDistanceProfile();
  }

  const recentCloses = candles
    .slice(-20)
    .map((candle) => readDecimal(candle.closePrice))
    .filter(Number.isFinite);

  if (recentCloses.length < 20) {
    return createUnavailableDistanceProfile();
  }

  const movingAverage = average(recentCloses);
  const movingAverageDistanceBps = Math.round(((currentPrice - movingAverage) / movingAverage) * 10_000);
  const atrMultipleFromPreviousClose = roundTo((currentPrice - previousClose) / atr, 2);
  const vwapDistanceBps = vwap.distanceBps;

  if (vwapDistanceBps >= 500 || movingAverageDistanceBps >= 500) {
    return availableDistanceProfile(
      vwapDistanceBps,
      movingAverageDistanceBps,
      atrMultipleFromPreviousClose,
      "상방 이격 과열",
      "warning"
    );
  }

  if (vwapDistanceBps <= -500 || movingAverageDistanceBps <= -500) {
    return availableDistanceProfile(
      vwapDistanceBps,
      movingAverageDistanceBps,
      atrMultipleFromPreviousClose,
      "하방 이격 과대",
      "danger"
    );
  }

  if (vwapDistanceBps >= 0 && movingAverageDistanceBps >= 0) {
    return availableDistanceProfile(
      vwapDistanceBps,
      movingAverageDistanceBps,
      atrMultipleFromPreviousClose,
      "상방 이격",
      "positive"
    );
  }

  if (vwapDistanceBps < 0 && movingAverageDistanceBps < 0) {
    return availableDistanceProfile(
      vwapDistanceBps,
      movingAverageDistanceBps,
      atrMultipleFromPreviousClose,
      "하방 이격",
      "danger"
    );
  }

  return availableDistanceProfile(
    vwapDistanceBps,
    movingAverageDistanceBps,
    atrMultipleFromPreviousClose,
    "이격 중립",
    "neutral"
  );
}

function calculateRsiMomentum(candlePage) {
  const candles = readOrderedCandles(candlePage);

  if (candles.length < 15) {
    return createUnavailableRsiMomentum();
  }

  const closes = candles
    .slice(-15)
    .map((candle) => readDecimal(candle.closePrice));

  if (closes.some((close) => !Number.isFinite(close) || close <= 0)) {
    return createUnavailableRsiMomentum();
  }

  let gainSum = 0;
  let lossSum = 0;

  for (let index = 1; index < closes.length; index += 1) {
    const delta = closes[index] - closes[index - 1];

    if (delta >= 0) {
      gainSum += delta;
    } else {
      lossSum += Math.abs(delta);
    }
  }

  const averageGain = gainSum / 14;
  const averageLoss = lossSum / 14;
  const rsi = averageLoss === 0
    ? 100
    : roundTo(100 - 100 / (1 + averageGain / averageLoss), 2);
  const momentumBase = closes[closes.length - 6] || closes[0];
  const momentumPercent = roundTo(Math.log(closes[closes.length - 1] / momentumBase) * 100, 2);

  if (rsi >= 70) {
    return availableRsiMomentum(rsi, momentumPercent, "RSI 과열", "warning");
  }

  if (rsi <= 30) {
    return availableRsiMomentum(rsi, momentumPercent, "RSI 약세", "danger");
  }

  if (momentumPercent > 0 && rsi >= 50) {
    return availableRsiMomentum(rsi, momentumPercent, "모멘텀 양호", "positive");
  }

  if (momentumPercent < 0) {
    return availableRsiMomentum(rsi, momentumPercent, "모멘텀 둔화", "danger");
  }

  return availableRsiMomentum(rsi, momentumPercent, "모멘텀 중립", "neutral");
}

function calculateMarketSentimentScore(indicators) {
  const availableComponents = [
    indicators.vwap,
    indicators.cvd,
    indicators.spread,
    indicators.atrStop,
    indicators.supplyPressure,
    indicators.riskReward,
    indicators.velocityAcceleration,
    indicators.distanceProfile,
    indicators.rsiMomentum
  ].filter((indicator) => indicator.status !== "unavailable");
  const scoreComponents = availableComponents.map((indicator) => scoreSeverity(indicator.severity));

  if (scoreComponents.length === 0) {
    return createUnavailableMarketSentimentScore();
  }

  const dangerCount = availableComponents.filter((indicator) => indicator.severity === "danger").length;
  const averagedScore = Math.round(average(scoreComponents));
  const score = dangerCount > 0 ? Math.min(averagedScore, 64) : averagedScore;

  if (score >= 70) {
    return availableMarketSentimentScore(score, "정량 심리 우호", "positive");
  }

  if (score >= 45) {
    return availableMarketSentimentScore(score, "정량 심리 중립", "neutral");
  }

  return availableMarketSentimentScore(score, "정량 심리 취약", "danger");
}

function calculateIntradayTradeScore(marketSentimentScore) {
  if (marketSentimentScore.status !== "available" || marketSentimentScore.score === null) {
    return createUnavailableIntradayTradeScore();
  }

  const conditionStrengthPercent = roundTo(
    sigmoid((marketSentimentScore.score - 50) / 10) * 100,
    2
  );

  if (conditionStrengthPercent >= 70) {
    return availableIntradayTradeScore(
      conditionStrengthPercent,
      "조건 충족 강함",
      "positive"
    );
  }

  if (conditionStrengthPercent >= 45) {
    return availableIntradayTradeScore(
      conditionStrengthPercent,
      "조건 일부 충족",
      "neutral"
    );
  }

  return availableIntradayTradeScore(
    conditionStrengthPercent,
    "조건 취약",
    "danger"
  );
}

function classifyCardDecision(indicators) {
  const decisionIndicators = [
    indicators.vwap,
    indicators.cvd,
    indicators.spread,
    indicators.atrStop,
    indicators.supplyPressure,
    indicators.riskReward
  ];

  if (decisionIndicators.some((indicator) => indicator.status === "unavailable")) {
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
  const values = [
    indicators.vwap,
    indicators.cvd,
    indicators.spread,
    indicators.atrStop,
    indicators.supplyPressure,
    indicators.riskReward
  ];
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

  const priority = [
    "vwap",
    "cvd",
    "spread",
    "atrStop",
    "supplyPressure",
    "riskReward"
  ];

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

function unavailableBasicReturn(currency) {
  return {
    status: "unavailable",
    currentPrice: null,
    referencePrice: null,
    absoluteChange: null,
    simpleReturnPercent: null,
    logReturnPercent: null,
    currency,
    referenceLabel: "전일 종가",
    label: "기본 수익률 계산 불가",
    severity: "unavailable",
    unavailableReason: "current price and previous close are required"
  };
}

function availableBasicReturn(
  currentPrice,
  referencePrice,
  absoluteChange,
  simpleReturnPercent,
  logReturnPercent,
  currency,
  label,
  severity
) {
  return {
    status: "available",
    currentPrice: formatDecimal(currentPrice),
    referencePrice: formatDecimal(referencePrice),
    absoluteChange: formatDecimal(absoluteChange),
    simpleReturnPercent,
    logReturnPercent,
    currency,
    referenceLabel: "전일 종가",
    label,
    severity,
    unavailableReason: null
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

function createUnavailableProfitTakingCauses() {
  return {
    profitBurden: unavailableProfitTakingCause(
      "수익권 부담",
      "current price, intraday candles, VWAP, and ATR are required"
    ),
    realizedSellPressure: unavailableProfitTakingCause(
      "실제 매도 압력",
      "recent trades or orderbook depth are required"
    ),
    overheadSupplyPressure: unavailableProfitTakingCause(
      "위쪽 매물 부담",
      "intraday volume profile and ATR are required"
    ),
    liquidityImpactRisk: unavailableProfitTakingCause(
      "체결 환경 위험",
      "spread, orderbook depth, or intraday candles are required"
    )
  };
}

function unavailableProfitTakingCause(name, reason) {
  return {
    status: "unavailable",
    score: null,
    label: `${name} 계산 불가`,
    severity: "unavailable",
    reason
  };
}

function availableProfitTakingCause(score, name, reason, status = "available") {
  const level = classifyRiskScore(score);

  return {
    status,
    score,
    label: `${name} ${level.labelSuffix}`,
    severity: level.severity,
    reason
  };
}

function classifyRiskScore(score) {
  if (score >= 80) {
    return { labelSuffix: "매우 높음", severity: "danger" };
  }

  if (score >= 65) {
    return { labelSuffix: "높음", severity: "warning" };
  }

  if (score >= 45) {
    return { labelSuffix: "경계", severity: "warning" };
  }

  if (score >= 25) {
    return { labelSuffix: "보통", severity: "neutral" };
  }

  return { labelSuffix: "낮음", severity: "positive" };
}

function createUnavailableProfitTakingPressure() {
  return {
    status: "unavailable",
    profitLongRatio: null,
    weightedProfitPressure: null,
    vwapAtrExtension: null,
    sellFlowPressure: null,
    askBookPressure: null,
    volumeExpansion: null,
    score: null,
    causes: createUnavailableProfitTakingCauses(),
    label: "차익실현 리스크 계산 불가",
    severity: "unavailable",
    unavailableReason: "current price, intraday candles, VWAP, and ATR are required"
  };
}

function availableProfitTakingPressure(
  profitLongRatio,
  weightedProfitPressure,
  vwapAtrExtension,
  sellFlowPressure,
  askBookPressure,
  volumeExpansion,
  score,
  label,
  severity,
  causes
) {
  return {
    status: "available",
    profitLongRatio,
    weightedProfitPressure,
    vwapAtrExtension: roundTo(vwapAtrExtension, 2),
    sellFlowPressure,
    askBookPressure,
    volumeExpansion,
    score,
    causes,
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

function createUnavailableVelocityAcceleration() {
  return {
    status: "unavailable",
    latestLogReturnPercent: null,
    priceAccelerationPercent: null,
    volumeChangePercent: null,
    estimatedCvdChange: null,
    label: "속도 계산 불가",
    severity: "unavailable",
    unavailableReason: "at least three intraday candles are required"
  };
}

function availableVelocityAcceleration(
  latestLogReturnPercent,
  priceAccelerationPercent,
  volumeChangePercent,
  estimatedCvdChange,
  label,
  severity
) {
  return {
    status: "available",
    latestLogReturnPercent,
    priceAccelerationPercent,
    volumeChangePercent,
    estimatedCvdChange: estimatedCvdChange === null ? null : formatPlainNumber(estimatedCvdChange),
    label,
    severity,
    unavailableReason: null
  };
}

function createUnavailableDistanceProfile() {
  return {
    status: "unavailable",
    vwapDistanceBps: null,
    movingAverageDistanceBps: null,
    atrMultipleFromPreviousClose: null,
    label: "이격도 계산 불가",
    severity: "unavailable",
    unavailableReason: "VWAP, ATR, and at least 20 intraday candles are required"
  };
}

function availableDistanceProfile(
  vwapDistanceBps,
  movingAverageDistanceBps,
  atrMultipleFromPreviousClose,
  label,
  severity
) {
  return {
    status: "available",
    vwapDistanceBps,
    movingAverageDistanceBps,
    atrMultipleFromPreviousClose,
    label,
    severity,
    unavailableReason: null
  };
}

function createUnavailableRsiMomentum() {
  return {
    status: "unavailable",
    rsi: null,
    momentumPercent: null,
    label: "RSI 계산 불가",
    severity: "unavailable",
    unavailableReason: "at least 15 intraday candles are required"
  };
}

function availableRsiMomentum(rsi, momentumPercent, label, severity) {
  return {
    status: "available",
    rsi,
    momentumPercent,
    label,
    severity,
    unavailableReason: null
  };
}

function createUnavailableMarketSentimentScore() {
  return {
    status: "unavailable",
    score: null,
    label: "정량 심리 계산 불가",
    severity: "unavailable",
    unavailableReason: "deterministic indicator components are required"
  };
}

function availableMarketSentimentScore(score, label, severity) {
  return {
    status: "available",
    score,
    label,
    severity,
    unavailableReason: null
  };
}

function createUnavailableIntradayTradeScore() {
  return {
    status: "unavailable",
    conditionStrengthPercent: null,
    label: "조건 충족 강도 계산 불가",
    severity: "unavailable",
    unavailableReason: "market sentiment score is required"
  };
}

function availableIntradayTradeScore(conditionStrengthPercent, label, severity) {
  return {
    status: "available",
    conditionStrengthPercent,
    label,
    severity,
    unavailableReason: null
  };
}

function createExplanationTraces(observations, indicators) {
  return [
    createBasicReturnTrace(indicators.basicReturn),
    createVwapTrace(observations.intradayCandles, indicators.vwap),
    createCvdTrace(observations.trades, indicators.cvd),
    createSpreadTrace(observations.orderbook, indicators.spread),
    createVelocityAccelerationTrace(indicators.velocityAcceleration),
    createDistanceProfileTrace(indicators.distanceProfile),
    createRsiMomentumTrace(indicators.rsiMomentum),
    createAtrStopTrace(indicators.atrStop),
    createSupplyPressureTrace(indicators.supplyPressure),
    createRiskRewardTrace(indicators.riskReward),
    createMarketSentimentScoreTrace(indicators.marketSentimentScore),
    createIntradayTradeScoreTrace(indicators.intradayTradeScore)
  ];
}

function createBasicReturnTrace(indicator) {
  return {
    key: "basicReturn",
    title: "기본 수익률",
    source: "현재가와 전일 종가",
    originalFormula: [
      "단순 수익률 = 현재가 / 기준가 - 1",
      "로그 수익률 = ln(현재가 / 기준가)"
    ],
    substitutedFormula: indicator.status === "available"
      ? [
          `단순 수익률 = ${formatCompactDecimal(indicator.currentPrice)} / ${formatCompactDecimal(indicator.referencePrice)} - 1`,
          `로그 수익률 = ln(${formatCompactDecimal(indicator.currentPrice)} / ${formatCompactDecimal(indicator.referencePrice)})`
        ]
      : ["현재가 또는 전일 종가가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [
          `단순 수익률 = ${formatSignedPercent(indicator.simpleReturnPercent)}`,
          `로그 수익률 = ${formatSignedPercent(indicator.logReturnPercent)}`
        ]
      : ["기본 수익률 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "현재가", value: formatCurrencyValue(indicator.currentPrice, indicator.currency) },
          { label: "기준가", value: formatCurrencyValue(indicator.referencePrice, indicator.currency) }
        ]
      : [],
    meaning: "가격이 기준 시점보다 얼마나 움직였는지 보는 가장 기본 지표입니다.",
    usage: "손절, 익절, 포지션 크기 판단의 출발점으로 사용합니다.",
    judgment: indicator.label,
    caution: "단순 수익률은 여러 구간을 그냥 더하면 누적 수익률과 달라집니다.",
    limitation: null
  };
}

function createVwapTrace(candlePage, indicator) {
  const formulaInputs = readVwapFormulaInputs(candlePage);

  return {
    key: "vwap",
    title: "VWAP",
    source: "당일 1분봉 가격과 거래량",
    originalFormula: [
      "VWAP = Σ(대표가격 × 거래량) / Σ거래량",
      "대표가격 = (고가 + 저가 + 종가) / 3"
    ],
    substitutedFormula: indicator.status === "available"
      ? [`VWAP = ${formatCompactDecimal(formulaInputs.weightedPriceSum)} / ${formatCompactDecimal(formulaInputs.volumeSum)}`]
      : ["1분봉 가격 또는 거래량이 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`VWAP = ${formatCompactDecimal(indicator.value)}`, `현재가와 거리 = ${indicator.distanceBps}bp`]
      : ["VWAP 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "가격×거래량 합", value: formatCompactDecimal(formulaInputs.weightedPriceSum) },
          { label: "거래량 합", value: formatCompactDecimal(formulaInputs.volumeSum) }
        ]
      : [],
    meaning: "당일 거래량이 많이 실린 평균 가격선입니다.",
    usage: "현재가가 당일 참여자 평균 가격 위에 있는지 확인합니다.",
    judgment: indicator.label,
    caution: "VWAP 단독으로 진입 신호를 확정하지 않고 체결 압력과 스프레드를 함께 봅니다.",
    limitation: null
  };
}

function createCvdTrace(trades, indicator) {
  const formulaInputs = readCvdFormulaInputs(trades);

  return {
    key: "cvd",
    title: "CVD 추정",
    source: "최근 체결 내역",
    originalFormula: ["tick-rule CVD = Σ(가격 상승 체결량 - 가격 하락 체결량)"],
    substitutedFormula: indicator.status === "estimated"
      ? [`tick-rule CVD = ${formulaInputs.expression}`]
      : ["최근 체결이 부족해 대입할 수 없습니다."],
    result: indicator.status === "estimated"
      ? [`CVD 추정값 = ${indicator.value}`]
      : ["체결 압력 계산 불가"],
    inputs: indicator.status === "estimated"
      ? [{ label: "체결 방향", value: "tick-rule 추정" }]
      : [],
    meaning: "최근 체결이 어느 방향으로 기울었는지 참고합니다.",
    usage: "VWAP 재돌파나 이탈 판단에서 체결 압력 회복 여부를 함께 봅니다.",
    judgment: indicator.label,
    caution: "정확한 매수·매도 주체가 아니라 방향 참고용입니다.",
    limitation: ESTIMATED_CVD_REASON
  };
}

function createSpreadTrace(orderbook, indicator) {
  const bestAsk = orderbook && Array.isArray(orderbook.asks) ? orderbook.asks[0] : undefined;
  const bestBid = orderbook && Array.isArray(orderbook.bids) ? orderbook.bids[0] : undefined;

  return {
    key: "spread",
    title: "스프레드",
    source: "최우선 매도호가와 최우선 매수호가",
    originalFormula: ["스프레드(bp) = (매도호가 - 매수호가) / 중간가격 × 10,000"],
    substitutedFormula: indicator.status === "available"
      ? [`스프레드 = (${bestAsk.price} - ${bestBid.price}) / 중간가격 × 10,000`]
      : ["최우선 매도/매수호가가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`스프레드 = ${indicator.spreadBps}bp`]
      : ["스프레드 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "매도호가", value: String(bestAsk.price) },
          { label: "매수호가", value: String(bestBid.price) }
        ]
      : [],
    meaning: "지금 바로 사고팔 때 발생할 수 있는 가격 간격입니다.",
    usage: "스프레드가 넓으면 짧은 매매에서 비용과 미끄러짐 위험이 커집니다.",
    judgment: indicator.label,
    caution: "호가 한 시점만으로 유동성 전체를 단정하지 않습니다.",
    limitation: null
  };
}

function createVelocityAccelerationTrace(indicator) {
  return {
    key: "velocityAcceleration",
    title: "속도/가속도",
    source: "최근 1분봉 종가, 거래량, 체결 흐름",
    originalFormula: [
      "가격 속도 = ln(현재 종가 / 직전 종가) × 100",
      "가격 가속도 = 현재 가격 속도 - 직전 가격 속도"
    ],
    substitutedFormula: indicator.status === "available"
      ? [
          `가격 속도 = ${formatSignedPercent(indicator.latestLogReturnPercent)}`,
          `가격 가속도 = ${formatSignedPercent(indicator.priceAccelerationPercent)}`
        ]
      : ["최근 1분봉이 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [
          `거래량 변화율 = ${formatSignedPercent(indicator.volumeChangePercent)}`,
          `추정 CVD 변화 = ${indicator.estimatedCvdChange ?? "--"}`
        ]
      : ["속도/가속도 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "가격 속도", value: formatSignedPercent(indicator.latestLogReturnPercent) },
          { label: "가격 가속도", value: formatSignedPercent(indicator.priceAccelerationPercent) }
        ]
      : [],
    meaning: "가격과 거래량 변화가 빨라지는지 느려지는지 보는 지표입니다.",
    usage: "단기 추세가 이어지는지, 힘이 빠지는지 확인할 때 참고합니다.",
    judgment: indicator.label,
    caution: "짧은 구간의 속도와 가속도는 노이즈가 커서 단독 판단에 쓰지 않습니다.",
    limitation: "1분봉 기반 단기 추정값입니다."
  };
}

function createDistanceProfileTrace(indicator) {
  return {
    key: "distanceProfile",
    title: "이격도",
    source: "VWAP, 20개 1분봉 평균, ATR",
    originalFormula: [
      "VWAP 이격(bp) = (현재가 - VWAP) / VWAP × 10,000",
      "MA20 이격(bp) = (현재가 - MA20) / MA20 × 10,000",
      "ATR 위치 = (현재가 - 전일 종가) / ATR"
    ],
    substitutedFormula: indicator.status === "available"
      ? [
          `VWAP 이격 = ${indicator.vwapDistanceBps}bp`,
          `MA20 이격 = ${indicator.movingAverageDistanceBps}bp`
        ]
      : ["VWAP, ATR 또는 20개 1분봉이 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`ATR 위치 = ${indicator.atrMultipleFromPreviousClose}x`]
      : ["이격도 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "VWAP 이격", value: `${indicator.vwapDistanceBps}bp` },
          { label: "MA20 이격", value: `${indicator.movingAverageDistanceBps}bp` }
        ]
      : [],
    meaning: "현재 가격이 평균 가격선과 변동성 기준에서 얼마나 떨어져 있는지 봅니다.",
    usage: "추격 매수 위험이나 하방 이탈 위험을 점검합니다.",
    judgment: indicator.label,
    caution: "강한 추세에서는 이격이 오래 유지될 수 있습니다.",
    limitation: null
  };
}

function createRsiMomentumTrace(indicator) {
  return {
    key: "rsiMomentum",
    title: "RSI/모멘텀",
    source: "최근 15개 1분봉 종가",
    originalFormula: [
      "RSI = 100 - 100 / (1 + 평균상승폭 / 평균하락폭)",
      "모멘텀 = ln(현재 종가 / N분 전 종가) × 100"
    ],
    substitutedFormula: indicator.status === "available"
      ? [`RSI = ${indicator.rsi}`, `모멘텀 = ${formatSignedPercent(indicator.momentumPercent)}`]
      : ["최근 1분봉 종가가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [indicator.label]
      : ["RSI/모멘텀 계산 불가"],
    inputs: indicator.status === "available"
      ? [
          { label: "RSI", value: String(indicator.rsi) },
          { label: "모멘텀", value: formatSignedPercent(indicator.momentumPercent) }
        ]
      : [],
    meaning: "최근 상승과 하락의 균형, 그리고 단기 방향성을 함께 봅니다.",
    usage: "가격이 너무 과열됐는지 또는 힘이 유지되는지 확인합니다.",
    judgment: indicator.label,
    caution: "RSI 과열은 즉시 하락 신호가 아니라 추격 위험 경고에 가깝습니다.",
    limitation: null
  };
}

function createAtrStopTrace(indicator) {
  return {
    key: "atrStop",
    title: "ATR/손절 폭",
    source: "최근 14개 일봉 True Range",
    originalFormula: ["TR = max(고가-저가, |고가-전일종가|, |저가-전일종가|)", "ATR = 최근 14개 TR 평균"],
    substitutedFormula: indicator.status === "available"
      ? [`ATR = 최근 14개 True Range 평균 = ${indicator.atr}`]
      : ["일봉 범위가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`현재가 대비 손절 폭 = ${formatSignedPercent(indicator.stopDistancePercent).replace("+", "")}`]
      : ["손절 폭 계산 불가"],
    inputs: indicator.status === "available"
      ? [{ label: "ATR", value: String(indicator.atr) }]
      : [],
    meaning: "최근 가격이 평균적으로 얼마나 크게 움직였는지 보는 변동성 지표입니다.",
    usage: "손절 폭이 너무 넓어지는지 확인합니다.",
    judgment: indicator.label,
    caution: "ATR은 방향을 말하지 않고 변동성 크기만 말합니다.",
    limitation: null
  };
}

function createSupplyPressureTrace(indicator) {
  return {
    key: "supplyPressure",
    title: "매물대",
    source: "당일 1분봉 거래량 분포",
    originalFormula: ["상단 매물 비율 = 현재가 위 대표가격 거래량 / 전체 거래량"],
    substitutedFormula: indicator.status === "available"
      ? [`상단 매물 비율 = ${indicator.overheadRatio}`]
      : ["1분봉 거래량이 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`POC = ${formatCompactDecimal(indicator.pocPrice)}`, `상단 매물 비율 = ${indicator.overheadRatio}`]
      : ["매물대 계산 불가"],
    inputs: indicator.status === "available"
      ? [{ label: "POC", value: formatCompactDecimal(indicator.pocPrice) }]
      : [],
    meaning: "거래량이 많이 쌓인 가격대를 참고해 위쪽 부담을 봅니다.",
    usage: "상단 매물 부담이 크면 단기 상승 여지가 제한될 수 있습니다.",
    judgment: indicator.label,
    caution: "1분봉 volume bucket 기반 추정이며 실제 주문 대기 물량과 다릅니다.",
    limitation: "실제 매물대가 아니라 1분봉 거래량 분포로 추정한 참고값입니다."
  };
}

function createRiskRewardTrace(indicator) {
  return {
    key: "riskReward",
    title: "손익비",
    source: "현재가, ATR 손절 기준, 직전 고점 목표 기준",
    originalFormula: ["손익비 = 기대 이익 폭 / 예상 손실 폭"],
    substitutedFormula: indicator.status === "available"
      ? [`손익비 = ${indicator.ratio}`]
      : ["목표가 또는 손절 기준이 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`손익비 = ${indicator.ratio}x`]
      : ["손익비 계산 불가"],
    inputs: indicator.status === "available"
      ? [{ label: "손익비", value: `${indicator.ratio}x` }]
      : [],
    meaning: "잃을 수 있는 폭 대비 기대할 수 있는 폭을 비교합니다.",
    usage: "단기 매매에서 손실 대비 보상이 충분한지 확인합니다.",
    judgment: indicator.label,
    caution: "목표와 손절 기준은 기본 휴리스틱이며 실제 주문 기준은 별도 확인이 필요합니다.",
    limitation: null
  };
}

function createMarketSentimentScoreTrace(indicator) {
  return {
    key: "marketSentimentScore",
    title: "장중 정량 심리 점수",
    source: "VWAP, CVD, 스프레드, 변동성, 매물대, 손익비, 모멘텀",
    originalFormula: ["정량 심리 점수 = 각 deterministic 지표 점수의 평균"],
    substitutedFormula: indicator.status === "available"
      ? [`정량 심리 점수 = ${indicator.score}`]
      : ["가용 deterministic 지표가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`점수 = ${indicator.score}/100`]
      : ["정량 심리 점수 계산 불가"],
    inputs: indicator.status === "available"
      ? [{ label: "점수", value: `${indicator.score}/100` }]
      : [],
    meaning: "뉴스 감성이 아니라 장중 수급과 리스크 지표를 정규화한 점수입니다.",
    usage: "여러 지표가 같은 방향을 가리키는지 빠르게 확인합니다.",
    judgment: indicator.label,
    caution: "점수는 확률이나 추천이 아니라 조건 정렬 정도입니다.",
    limitation: "LLM이나 뉴스 감성을 포함하지 않는 순수 정량 점수입니다."
  };
}

function createIntradayTradeScoreTrace(indicator) {
  return {
    key: "intradayTradeScore",
    title: "종합 데이트레이딩 점수",
    source: "장중 정량 심리 점수의 sigmoid 변환",
    originalFormula: ["조건 충족 강도 = sigmoid((정량 심리 점수 - 50) / 10) × 100"],
    substitutedFormula: indicator.status === "available"
      ? [`조건 충족 강도 = ${indicator.conditionStrengthPercent}%`]
      : ["정량 심리 점수가 부족해 대입할 수 없습니다."],
    result: indicator.status === "available"
      ? [`조건 충족 강도 = ${indicator.conditionStrengthPercent}%`]
      : ["종합 데이트레이딩 점수 계산 불가"],
    inputs: indicator.status === "available"
      ? [{ label: "조건 충족 강도", value: `${indicator.conditionStrengthPercent}%` }]
      : [],
    meaning: "여러 정량 조건이 얼마나 강하게 맞물렸는지 보는 참고 점수입니다.",
    usage: "관망, 확인 대기, 리스크 높음 상태를 더 세밀하게 읽을 때 참고합니다.",
    judgment: indicator.label,
    caution: "실제 승률이 아니며 매수·매도 지시로 해석하면 안 됩니다.",
    limitation: "백테스트 확률이 아니라 deterministic 점수의 수학적 변환입니다."
  };
}

function readPreviousClose(priceObservation, candlePage, capturedAt) {
  const currentDate = readDateKey(
    (priceObservation && priceObservation.timestamp) || capturedAt
  );
  const candles = readCandles(candlePage)
    .map((candle, index) => ({
      close: readDecimal(candle.closePrice),
      dateKey: readDateKey(candle.timestamp),
      index,
      timestampMs: Date.parse(candle.timestamp)
    }))
    .filter((candle) => Number.isFinite(candle.close) && candle.dateKey !== null)
    .sort(compareCandlesByTime);

  if (candles.length === 0) {
    return Number.NaN;
  }

  if (currentDate !== null) {
    const currentIndex = candles.findIndex((candle) => candle.dateKey === currentDate);

    if (currentIndex > 0) {
      return candles[currentIndex - 1].close;
    }

    const previousCandles = candles.filter((candle) => candle.dateKey < currentDate);

    if (previousCandles.length > 0) {
      return previousCandles[previousCandles.length - 1].close;
    }

    return Number.NaN;
  }

  return candles[candles.length - 1].close;
}

function compareCandlesByTime(left, right) {
  const leftTime = Number.isFinite(left.timestampMs) ? left.timestampMs : null;
  const rightTime = Number.isFinite(right.timestampMs) ? right.timestampMs : null;

  if (leftTime !== null && rightTime !== null && leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  return left.index - right.index;
}

function readDateKey(timestamp) {
  if (typeof timestamp !== "string") {
    return null;
  }

  const match = timestamp.match(/^(\d{4}-\d{2}-\d{2})/);

  return match ? match[1] : null;
}

function readVwapFormulaInputs(candlePage) {
  let volumeSum = 0;
  let weightedPriceSum = 0;

  readCandles(candlePage).forEach((candle) => {
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

  return { weightedPriceSum, volumeSum };
}

function readCvdFormulaInputs(trades) {
  if (!Array.isArray(trades) || trades.length < 2) {
    return { expression: "체결 부족" };
  }

  const orderedTrades = [...trades].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
  const deltas = [];

  for (let index = 1; index < orderedTrades.length; index += 1) {
    const previousPrice = readDecimal(orderedTrades[index - 1].price);
    const currentPrice = readDecimal(orderedTrades[index].price);
    const volume = readDecimal(orderedTrades[index].volume);

    if (!Number.isFinite(previousPrice) || !Number.isFinite(currentPrice) || !Number.isFinite(volume)) {
      continue;
    }

    if (currentPrice > previousPrice) {
      deltas.push(`+${formatCompactDecimal(volume)}`);
    } else if (currentPrice < previousPrice) {
      deltas.push(`-${formatCompactDecimal(volume)}`);
    }
  }

  return { expression: deltas.length > 0 ? deltas.join(" ") : "0" };
}

function calculateEstimatedCvdChange(trades) {
  if (!Array.isArray(trades) || trades.length < 3) {
    return null;
  }

  const orderedTrades = [...trades].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
  const deltas = [];

  for (let index = 1; index < orderedTrades.length; index += 1) {
    const previousPrice = readDecimal(orderedTrades[index - 1].price);
    const currentPrice = readDecimal(orderedTrades[index].price);
    const volume = readDecimal(orderedTrades[index].volume);

    if (!Number.isFinite(previousPrice) || !Number.isFinite(currentPrice) || !Number.isFinite(volume)) {
      continue;
    }

    if (currentPrice > previousPrice) {
      deltas.push(volume);
    } else if (currentPrice < previousPrice) {
      deltas.push(-volume);
    } else {
      deltas.push(0);
    }
  }

  if (deltas.length < 2) {
    return null;
  }

  const splitIndex = Math.max(1, Math.floor(deltas.length / 2));
  const previousCvd = sum(deltas.slice(0, splitIndex));
  const latestCvd = sum(deltas.slice(splitIndex));

  return roundTo(latestCvd - previousCvd, 4);
}

function readOrderedCandles(candlePage) {
  return [...readCandles(candlePage)].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
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

function median(values) {
  if (values.length === 0) {
    return Number.NaN;
  }

  const sortedValues = [...values].sort((left, right) => left - right);
  const middleIndex = Math.floor(sortedValues.length / 2);

  return sortedValues.length % 2 === 0
    ? (sortedValues[middleIndex - 1] + sortedValues[middleIndex]) / 2
    : sortedValues[middleIndex];
}

function sum(values) {
  return values.reduce((total, value) => total + value, 0);
}

function roundTo(value, digits) {
  const factor = 10 ** digits;

  return Math.round(value * factor) / factor;
}

function clip(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function sigmoid(value) {
  return 1 / (1 + Math.exp(-value));
}

function scoreSeverity(severity) {
  if (severity === "positive") {
    return 100;
  }

  if (severity === "neutral") {
    return 65;
  }

  if (severity === "warning") {
    return 55;
  }

  if (severity === "danger") {
    return 15;
  }

  return 0;
}

function formatDecimal(value) {
  return value.toFixed(4);
}

function formatCompactDecimal(value) {
  const decimal = readDecimal(value);

  if (!Number.isFinite(decimal)) {
    return String(value ?? "");
  }

  return decimal.toFixed(2);
}

function formatPlainNumber(value) {
  const decimal = readDecimal(value);

  if (!Number.isFinite(decimal)) {
    return null;
  }

  return String(roundTo(decimal, 4)).replace(/\.0+$/, "");
}

function formatSignedPercent(value) {
  const decimal = readDecimal(value);

  if (!Number.isFinite(decimal)) {
    return "--";
  }

  const sign = decimal > 0 ? "+" : "";

  return `${sign}${decimal.toFixed(2)}%`;
}

function formatCurrencyValue(value, currency) {
  const decimal = readDecimal(value);

  if (!Number.isFinite(decimal)) {
    return "--";
  }

  if (currency === "USD") {
    return `$${decimal.toFixed(2)}`;
  }

  if (currency === "KRW") {
    return `${Math.round(decimal).toLocaleString("ko-KR")}원`;
  }

  return `${currency} ${decimal.toFixed(2)}`.trim();
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
