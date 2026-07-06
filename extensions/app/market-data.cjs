const crypto = require("node:crypto");

const { JsonFileStore } = require("./storage.cjs");

const MARKET_DATA_BASE_URL = "https://openapi.tossinvest.com";
const REGULAR_POLL_DELAY_MS = 15_000;
const CLOSED_POLL_DELAY_MS = 300_000;
const INTRADAY_CANDLE_STALE_MS = 60_000;
const DAILY_CANDLE_STALE_MS = 24 * 60 * 60 * 1000;
const DEFAULT_MAX_SNAPSHOTS = 500;
const DEFAULT_MINIMUM_INTERVAL_BY_GROUP = {
  MARKET_DATA: 125,
  MARKET_DATA_CHART: 250,
  MARKET_INFO: 400
};
const koreanMarkets = new Set(["KOSPI", "KOSDAQ", "KONEX", "KRX"]);

class MarketDataError extends Error {
  constructor(code, message, recoverable, extra = {}) {
    super(message);
    this.name = "MarketDataError";
    this.code = code;
    this.recoverable = recoverable;
    Object.assign(this, extra);
  }
}

class RateLimitAwareTossClient {
  constructor(fetcher, options = {}) {
    this.fetcher = fetcher;
    this.lastRateLimitByGroup = new Map();
    this.nextAvailableAtByGroup = new Map();
    this.requestQueueByGroup = new Map();
    this.nowMs = typeof options.nowMs === "function" ? options.nowMs : Date.now;
    this.sleep = typeof options.sleep === "function"
      ? options.sleep
      : (durationMs) => new Promise((resolve) => {
          setTimeout(resolve, durationMs);
        });
    this.minimumIntervalByGroup = {
      ...DEFAULT_MINIMUM_INTERVAL_BY_GROUP,
      ...(options.minimumIntervalByGroup || {})
    };
  }

  async requestJson(url, init, group) {
    return this.enqueueRequest(group, () => this.performRequest(url, init, group));
  }

  async enqueueRequest(group, request) {
    const previousRequest = this.requestQueueByGroup.get(group) || Promise.resolve();
    const nextRequest = previousRequest
      .catch(() => undefined)
      .then(request);
    this.requestQueueByGroup.set(group, nextRequest.catch(() => undefined));

    return nextRequest;
  }

  async performRequest(url, init, group) {
    await this.waitForGroupAvailability(group);

    let response;

    try {
      response = await this.fetcher(url, init);
    } catch (error) {
      throw new MarketDataError(
        "market_data_unavailable",
        error instanceof Error ? error.message : "Toss market data request failed",
        true
      );
    }

    const rateLimit = readRateLimitHeaders(response);
    this.lastRateLimitByGroup.set(group, rateLimit);

    if (!response.ok) {
      await mapMarketDataFailure(response, rateLimit);
    }

    return response.json().catch(() => ({}));
  }

  async waitForGroupAvailability(group) {
    const now = this.nowMs();
    const nextAvailableAt = this.nextAvailableAtByGroup.get(group) || 0;
    const waitDurationMs = Math.max(nextAvailableAt - now, 0);

    if (waitDurationMs > 0) {
      await this.sleep(waitDurationMs);
    }

    const requestStartedAt = this.nowMs();
    this.nextAvailableAtByGroup.set(
      group,
      requestStartedAt + this.readMinimumInterval(group)
    );
  }

  readMinimumInterval(group) {
    const interval = this.minimumIntervalByGroup[group];

    return typeof interval === "number" && interval > 0 ? interval : 0;
  }

  readRateLimit(group) {
    return this.lastRateLimitByGroup.get(group) || null;
  }
}

class TossMarketDataClient {
  constructor(rateLimitClient) {
    this.rateLimitClient = rateLimitClient;
  }

  async fetchPrices(symbols, accessToken) {
    const result = [];

    for (const chunk of chunkSymbols(symbols, 200)) {
      const query = new URLSearchParams();
      query.set("symbols", chunk.join(","));
      const payload = await this.rateLimitClient.requestJson(
        `${MARKET_DATA_BASE_URL}/api/v1/prices?${query.toString()}`,
        createBearerRequest(accessToken),
        "MARKET_DATA"
      );
      result.push(...readResultArray(payload));
    }

    return result;
  }

  async fetchTrades(symbol, accessToken, count = 50) {
    const query = new URLSearchParams();
    query.set("symbol", normalizeSymbol(symbol));
    query.set("count", String(count));
    const payload = await this.rateLimitClient.requestJson(
      `${MARKET_DATA_BASE_URL}/api/v1/trades?${query.toString()}`,
      createBearerRequest(accessToken),
      "MARKET_DATA"
    );

    return readResultArray(payload);
  }

  async fetchOrderbook(symbol, accessToken) {
    const query = new URLSearchParams();
    query.set("symbol", normalizeSymbol(symbol));
    const payload = await this.rateLimitClient.requestJson(
      `${MARKET_DATA_BASE_URL}/api/v1/orderbook?${query.toString()}`,
      createBearerRequest(accessToken),
      "MARKET_DATA"
    );

    return payload.result || null;
  }

  async fetchCandles(symbol, interval, accessToken, count = 100) {
    const query = new URLSearchParams();
    query.set("symbol", normalizeSymbol(symbol));
    query.set("interval", interval);
    query.set("count", String(count));
    query.set("adjusted", "true");
    const payload = await this.rateLimitClient.requestJson(
      `${MARKET_DATA_BASE_URL}/api/v1/candles?${query.toString()}`,
      createBearerRequest(accessToken),
      "MARKET_DATA_CHART"
    );

    return {
      interval,
      candles: Array.isArray(payload.result && payload.result.candles)
        ? payload.result.candles
        : [],
      nextBefore: typeof (payload.result && payload.result.nextBefore) === "string"
        ? payload.result.nextBefore
        : null
    };
  }
}

class TossMarketInfoClient {
  constructor(rateLimitClient) {
    this.rateLimitClient = rateLimitClient;
  }

  async fetchExchangeRate(baseCurrency, quoteCurrency, accessToken) {
    const query = new URLSearchParams();
    query.set("baseCurrency", baseCurrency);
    query.set("quoteCurrency", quoteCurrency);
    const payload = await this.rateLimitClient.requestJson(
      `${MARKET_DATA_BASE_URL}/api/v1/exchange-rate?${query.toString()}`,
      createBearerRequest(accessToken),
      "MARKET_INFO"
    );

    return payload.result || null;
  }

  async fetchMarketCalendar(country, accessToken) {
    try {
      const payload = await this.rateLimitClient.requestJson(
        `${MARKET_DATA_BASE_URL}/api/v1/market-calendar/${country}`,
        createBearerRequest(accessToken),
        "MARKET_INFO"
      );

      return payload.result || null;
    } catch (error) {
      if (normalizeErrorCode(error) === "market_data_rate_limited") {
        throw error;
      }

      throw new MarketDataError(
        "market_calendar_unavailable",
        error instanceof Error ? error.message : "Toss market calendar request failed",
        true
      );
    }
  }
}

class StoredMarketDataSnapshotRepository {
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

      if (previous === undefined || Date.parse(snapshot.capturedAt) > Date.parse(previous.capturedAt)) {
        latestByCardId.set(snapshot.cardId, snapshot);
      }
    });

    if (Array.isArray(cardIds) && cardIds.length > 0) {
      return cardIds
        .map((cardId) => latestByCardId.get(cardId))
        .filter((snapshot) => snapshot !== undefined)
        .map(markSnapshotFreshness);
    }

    return [...latestByCardId.values()].map(markSnapshotFreshness);
  }

  async readSnapshot() {
    const snapshot = await this.store.read();

    return {
      snapshots: Array.isArray(snapshot.snapshots) ? snapshot.snapshots : []
    };
  }
}

async function refreshMarketDataForWatchlist(context, payload) {
  const watchlist = await context.watchlistRepository.list();
  const cards = prioritizeCards(
    watchlist.activeCards,
    Array.isArray(payload.visibleCardIds) ? payload.visibleCardIds : []
  );
  const snapshots = await refreshCards(context, cards);

  if (snapshots.length > 0) {
    await context.marketDataSnapshotRepository.saveAll(snapshots);
  }

  return {
    refreshedAt: context.occurredAt,
    nextPollDelayMs: chooseNextPollDelay(snapshots),
    snapshots
  };
}

async function refreshMarketDataForCard(context, payload) {
  const watchlist = await context.watchlistRepository.list();
  const card = watchlist.activeCards.find((activeCard) => activeCard.id === payload.cardId);

  if (card === undefined) {
    throw new MarketDataError(
      "market_data_snapshot_not_found",
      "watch card was not found for market data refresh",
      true
    );
  }

  const snapshots = await refreshCards(context, [card]);

  if (snapshots.length > 0) {
    await context.marketDataSnapshotRepository.saveAll(snapshots);
  }

  return {
    refreshedAt: context.occurredAt,
    nextPollDelayMs: chooseNextPollDelay(snapshots),
    snapshot: snapshots[0]
  };
}

async function readLatestMarketDataSnapshots(context, payload) {
  return {
    snapshots: await context.marketDataSnapshotRepository.readLatest(
      Array.isArray(payload.cardIds) ? payload.cardIds : undefined
    )
  };
}

async function refreshCards(context, cards) {
  if (cards.length === 0) {
    return [];
  }

  const accessToken = await context.tossAccessTokenProvider.readAccessToken(context.occurredAt);
  const latestSnapshots = await context.marketDataSnapshotRepository.readLatest(
    cards.map((card) => card.id)
  );
  const latestByCardId = new Map(latestSnapshots.map((snapshot) => [snapshot.cardId, snapshot]));
  const priceResult = await fetchPriceMap(context, cards, accessToken);
  const marketSessions = await fetchMarketSessions(context, cards, accessToken);
  const exchangeRateResult = await fetchUsdExchangeRateIfNeeded(context, cards, accessToken);
  const snapshots = [];

  for (const card of cards) {
    const adapterErrors = [...priceResult.errors];
    const previousSnapshot = latestByCardId.get(card.id);
    const trades = await collectObservation(adapterErrors, "trades", () =>
      context.tossMarketDataClient.fetchTrades(card.symbol, accessToken)
    );
    const orderbook = await collectObservation(adapterErrors, "orderbook", () =>
      context.tossMarketDataClient.fetchOrderbook(card.symbol, accessToken)
    );
    const intradayCandles = shouldRefreshCandles(
      previousSnapshot,
      context.occurredAt,
      "intraday"
    )
      ? await collectObservation(adapterErrors, "intradayCandles", () =>
          context.tossMarketDataClient.fetchCandles(card.symbol, "1m", accessToken, 100)
        )
      : previousSnapshot.observations.intradayCandles;
    const dailyCandles = shouldRefreshCandles(previousSnapshot, context.occurredAt, "daily")
      ? await collectObservation(adapterErrors, "dailyCandles", () =>
          context.tossMarketDataClient.fetchCandles(card.symbol, "1d", accessToken, 100)
        )
      : previousSnapshot.observations.dailyCandles;
    const country = resolveMarketCountry(card.market);
    const marketSession = marketSessions.sessionByCountry.get(country) || {
      country,
      state: "closed",
      source: "fallback"
    };
    const sessionError = marketSessions.errorsByCountry.get(country);

    if (sessionError !== undefined) {
      adapterErrors.push(sessionError);
    }

    if (country === "US" && exchangeRateResult.error !== null) {
      adapterErrors.push(exchangeRateResult.error);
    }

    snapshots.push(
      createMarketDataSnapshot({
        card,
        capturedAt: context.occurredAt,
        price: priceResult.pricesBySymbol.get(normalizeSymbol(card.symbol)) || null,
        trades: Array.isArray(trades) ? trades : [],
        orderbook,
        intradayCandles,
        dailyCandles,
        exchangeRate: country === "US" ? exchangeRateResult.exchangeRate : null,
        marketSession,
        adapterErrors
      })
    );
  }

  return snapshots;
}

async function fetchPriceMap(context, cards, accessToken) {
  try {
    const prices = await context.tossMarketDataClient.fetchPrices(
      cards.map((card) => card.symbol),
      accessToken
    );

    return {
      pricesBySymbol: new Map(
        prices.map((price) => [normalizeSymbol(price.symbol), normalizePrice(price)])
      ),
      errors: []
    };
  } catch (error) {
    return {
      pricesBySymbol: new Map(),
      errors: [createAdapterError("prices", error)]
    };
  }
}

async function fetchMarketSessions(context, cards, accessToken) {
  const countries = new Set(cards.map((card) => resolveMarketCountry(card.market)));
  const sessionByCountry = new Map();
  const errorsByCountry = new Map();

  for (const country of countries) {
    try {
      const calendar = await context.tossMarketInfoClient.fetchMarketCalendar(country, accessToken);
      sessionByCountry.set(country, mapCalendarToMarketSession(country, calendar, context.occurredAt));
    } catch (error) {
      sessionByCountry.set(country, {
        country,
        state: "closed",
        source: "fallback"
      });
      errorsByCountry.set(country, createAdapterError("marketCalendar", error));
    }
  }

  return { sessionByCountry, errorsByCountry };
}

async function fetchUsdExchangeRateIfNeeded(context, cards, accessToken) {
  const hasUsCard = cards.some((card) => resolveMarketCountry(card.market) === "US");

  if (!hasUsCard) {
    return { exchangeRate: null, error: null };
  }

  try {
    const exchangeRate = await context.tossMarketInfoClient.fetchExchangeRate(
      "USD",
      "KRW",
      accessToken
    );

    return {
      exchangeRate: normalizeExchangeRate(exchangeRate),
      error: null
    };
  } catch (error) {
    return {
      exchangeRate: null,
      error: createAdapterError("exchangeRate", error)
    };
  }
}

async function collectObservation(adapterErrors, endpoint, fetchObservation) {
  try {
    return await fetchObservation();
  } catch (error) {
    adapterErrors.push(createAdapterError(endpoint, error));
    return null;
  }
}

function createMarketDataSnapshot(input) {
  const adapterErrors = Array.isArray(input.adapterErrors) ? input.adapterErrors : [];

  return {
    snapshotId: crypto.randomUUID(),
    cardId: input.card.id,
    market: normalizeMarket(input.card.market),
    symbol: normalizeSymbol(input.card.symbol),
    capturedAt: input.capturedAt,
    freshness: "fresh",
    quality: decideQuality(input.price, adapterErrors),
    observations: {
      price: input.price === null ? null : normalizePrice(input.price),
      trades: Array.isArray(input.trades) ? input.trades.map(normalizeTrade) : [],
      orderbook: input.orderbook === null ? null : normalizeOrderbook(input.orderbook),
      intradayCandles: normalizeCandlePage(input.intradayCandles, "1m"),
      dailyCandles: normalizeCandlePage(input.dailyCandles, "1d"),
      exchangeRate: input.exchangeRate === null ? null : normalizeExchangeRate(input.exchangeRate),
      marketSession: input.marketSession || null
    },
    adapterErrors
  };
}

function decideQuality(price, adapterErrors) {
  if (adapterErrors.length === 0) {
    return "complete";
  }

  return price === null ? "degraded" : "partial";
}

function shouldRefreshCandles(previousSnapshot, now, candleType) {
  if (previousSnapshot === undefined) {
    return true;
  }

  const previousCandlePage = candleType === "intraday"
    ? previousSnapshot.observations.intradayCandles
    : previousSnapshot.observations.dailyCandles;

  if (previousCandlePage === null || previousCandlePage === undefined) {
    return true;
  }

  const capturedAtMs = Date.parse(previousSnapshot.capturedAt);
  const staleMs = candleType === "intraday" ? INTRADAY_CANDLE_STALE_MS : DAILY_CANDLE_STALE_MS;

  return !Number.isFinite(capturedAtMs) || Date.parse(now) - capturedAtMs >= staleMs;
}

function mapCalendarToMarketSession(country, calendar, now) {
  const today = calendar && calendar.today;

  if (today === null || today === undefined) {
    return { country, state: "closed", source: "fallback" };
  }

  const sessionMap = country === "KR"
    ? today.integrated
    : {
        preMarket: today.preMarket || today.dayMarket,
        regularMarket: today.regularMarket,
        afterMarket: today.afterMarket
      };

  if (sessionMap === null || sessionMap === undefined) {
    return { country, state: "holiday", source: "calendar" };
  }

  if (isWithinSession(now, sessionMap.regularMarket)) {
    return { country, state: "regular", source: "calendar" };
  }

  if (isWithinSession(now, sessionMap.preMarket)) {
    return { country, state: "pre", source: "calendar" };
  }

  if (isWithinSession(now, sessionMap.afterMarket)) {
    return { country, state: "after", source: "calendar" };
  }

  return { country, state: "closed", source: "calendar" };
}

function isWithinSession(now, session) {
  if (session === null || session === undefined) {
    return false;
  }

  const nowMs = Date.parse(now);
  const startMs = Date.parse(session.startTime);
  const endMs = Date.parse(session.endTime);

  return Number.isFinite(nowMs) &&
    Number.isFinite(startMs) &&
    Number.isFinite(endMs) &&
    nowMs >= startMs &&
    nowMs <= endMs;
}

function chooseNextPollDelay(snapshots) {
  const allClosed = snapshots.length > 0 &&
    snapshots.every((snapshot) => {
      const state = snapshot.observations.marketSession &&
        snapshot.observations.marketSession.state;

      return state === "closed" || state === "holiday";
    });
  const baseDelayMs = allClosed ? CLOSED_POLL_DELAY_MS : REGULAR_POLL_DELAY_MS;
  const retryAfterDelayMs = readMaxRetryAfterDelayMs(snapshots);

  return Math.max(baseDelayMs, retryAfterDelayMs);
}

function readRateLimitHeaders(response) {
  return {
    limit: readNumberHeader(response.headers, "X-RateLimit-Limit"),
    remaining: readNumberHeader(response.headers, "X-RateLimit-Remaining"),
    resetSeconds: readNumberHeader(response.headers, "X-RateLimit-Reset"),
    retryAfterSeconds: readNumberHeader(response.headers, "Retry-After")
  };
}

async function mapMarketDataFailure(response, rateLimit) {
  let payload = {};

  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (response.status === 401) {
    throw new MarketDataError(
      "invalid_toss_credentials",
      "Toss access token is invalid",
      true
    );
  }

  if (response.status === 429) {
    throw new MarketDataError(
      "market_data_rate_limited",
      readTossErrorMessage(payload) || "Toss market data rate limit exceeded",
      true,
      { retryAfterSeconds: rateLimit.retryAfterSeconds }
    );
  }

  throw new MarketDataError(
    "market_data_unavailable",
    readTossErrorMessage(payload) || "Toss market data request failed",
    true
  );
}

function createBearerRequest(accessToken) {
  return {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`
    }
  };
}

function createAdapterError(endpoint, error) {
  const adapterError = {
    endpoint,
    code: normalizeErrorCode(error),
    message: error instanceof Error ? error.message : "market data request failed",
    recoverable: error && typeof error.recoverable === "boolean" ? error.recoverable : true
  };

  if (error && typeof error.retryAfterSeconds === "number") {
    adapterError.retryAfterSeconds = error.retryAfterSeconds;
  }

  return adapterError;
}

function readMaxRetryAfterDelayMs(snapshots) {
  return snapshots.reduce((maxDelayMs, snapshot) => {
    const adapterErrors = Array.isArray(snapshot.adapterErrors)
      ? snapshot.adapterErrors
      : [];
    const snapshotDelayMs = adapterErrors.reduce((snapshotMaxDelayMs, adapterError) => {
      const retryAfterSeconds = adapterError.retryAfterSeconds;

      if (typeof retryAfterSeconds !== "number" || retryAfterSeconds <= 0) {
        return snapshotMaxDelayMs;
      }

      return Math.max(snapshotMaxDelayMs, retryAfterSeconds * 1000);
    }, 0);

    return Math.max(maxDelayMs, snapshotDelayMs);
  }, 0);
}

function normalizePrice(price) {
  return {
    symbol: normalizeSymbol(price.symbol),
    timestamp: typeof price.timestamp === "string" ? price.timestamp : null,
    lastPrice: String(price.lastPrice ?? ""),
    currency: normalizeText(price.currency)
  };
}

function normalizeTrade(trade) {
  return {
    price: String(trade.price ?? ""),
    volume: String(trade.volume ?? ""),
    timestamp: String(trade.timestamp ?? ""),
    currency: normalizeText(trade.currency)
  };
}

function normalizeOrderbook(orderbook) {
  return {
    timestamp: typeof orderbook.timestamp === "string" ? orderbook.timestamp : null,
    currency: normalizeText(orderbook.currency),
    asks: normalizeOrderbookEntries(orderbook.asks),
    bids: normalizeOrderbookEntries(orderbook.bids)
  };
}

function normalizeOrderbookEntries(entries) {
  if (!Array.isArray(entries)) {
    return [];
  }

  return entries.map((entry) => ({
    price: String(entry.price ?? ""),
    volume: String(entry.volume ?? "")
  }));
}

function normalizeCandlePage(candlePage, interval) {
  if (candlePage === null || candlePage === undefined) {
    return null;
  }

  return {
    interval,
    candles: Array.isArray(candlePage.candles) ? candlePage.candles.map(normalizeCandle) : [],
    nextBefore: typeof candlePage.nextBefore === "string" ? candlePage.nextBefore : null
  };
}

function normalizeCandle(candle) {
  return {
    timestamp: String(candle.timestamp ?? ""),
    openPrice: String(candle.openPrice ?? ""),
    highPrice: String(candle.highPrice ?? ""),
    lowPrice: String(candle.lowPrice ?? ""),
    closePrice: String(candle.closePrice ?? ""),
    volume: String(candle.volume ?? ""),
    currency: normalizeText(candle.currency)
  };
}

function normalizeExchangeRate(exchangeRate) {
  if (exchangeRate === null || exchangeRate === undefined) {
    return null;
  }

  return {
    baseCurrency: normalizeText(exchangeRate.baseCurrency),
    quoteCurrency: normalizeText(exchangeRate.quoteCurrency),
    rate: String(exchangeRate.rate ?? ""),
    midRate: String(exchangeRate.midRate ?? ""),
    validFrom: String(exchangeRate.validFrom ?? ""),
    validUntil: String(exchangeRate.validUntil ?? "")
  };
}

function markSnapshotFreshness(snapshot) {
  const capturedAtMs = Date.parse(snapshot.capturedAt);
  const nowMs = Date.now();
  const freshness = Number.isFinite(capturedAtMs) && nowMs - capturedAtMs <= INTRADAY_CANDLE_STALE_MS
    ? "fresh"
    : "stale";

  return {
    ...snapshot,
    freshness
  };
}

function prioritizeCards(cards, visibleCardIds) {
  const visibleCardIdSet = new Set(visibleCardIds);

  return [...cards].sort((left, right) => {
    const leftVisibleIndex = visibleCardIds.indexOf(left.id);
    const rightVisibleIndex = visibleCardIds.indexOf(right.id);

    if (visibleCardIdSet.has(left.id) && visibleCardIdSet.has(right.id)) {
      return leftVisibleIndex - rightVisibleIndex;
    }

    if (visibleCardIdSet.has(left.id)) {
      return -1;
    }

    if (visibleCardIdSet.has(right.id)) {
      return 1;
    }

    return left.sortOrder - right.sortOrder;
  });
}

function resolveMarketCountry(market) {
  return koreanMarkets.has(normalizeMarket(market)) ? "KR" : "US";
}

function chunkSymbols(symbols, chunkSize) {
  const chunks = [];

  for (let index = 0; index < symbols.length; index += chunkSize) {
    chunks.push(symbols.slice(index, index + chunkSize).map(normalizeSymbol));
  }

  return chunks;
}

function readResultArray(payload) {
  return Array.isArray(payload.result) ? payload.result : [];
}

function readNumberHeader(headers, name) {
  const value = Number(headers.get(name));

  return Number.isFinite(value) ? value : null;
}

function readTossErrorMessage(payload) {
  return payload &&
    payload.error &&
    typeof payload.error.message === "string"
    ? payload.error.message
    : null;
}

function normalizeErrorCode(error) {
  return error && typeof error.code === "string"
    ? error.code
    : "market_data_unavailable";
}

function normalizeMarket(value) {
  return String(value ?? "").trim().toUpperCase();
}

function normalizeSymbol(value) {
  return String(value ?? "").trim().toUpperCase();
}

function normalizeText(value) {
  return String(value ?? "").trim().toUpperCase();
}

function compareSnapshots(left, right) {
  return Date.parse(left.capturedAt) - Date.parse(right.capturedAt);
}

module.exports = {
  MarketDataError,
  RateLimitAwareTossClient,
  StoredMarketDataSnapshotRepository,
  TossMarketDataClient,
  TossMarketInfoClient,
  createMarketDataSnapshot,
  readLatestMarketDataSnapshots,
  refreshMarketDataForCard,
  refreshMarketDataForWatchlist,
  resolveMarketCountry
};
