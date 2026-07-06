const { JsonFileStore } = require("./storage.cjs");

const DEFAULT_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

class StockReferenceError extends Error {
  constructor(code, message, recoverable) {
    super(message);
    this.name = "StockReferenceError";
    this.code = code;
    this.recoverable = recoverable;
  }
}

class StoredStockReferenceCache {
  constructor(filePath, options = {}) {
    this.store = new JsonFileStore(filePath, {
      references: []
    });
    this.ttlMs = options.ttlMs || DEFAULT_CACHE_TTL_MS;
  }

  async saveAll(identities) {
    const snapshot = await this.readSnapshot();
    const referencesBySymbol = new Map(
      snapshot.references.map((reference) => [normalizeSymbol(reference.symbol), reference])
    );

    identities.forEach((identity) => {
      referencesBySymbol.set(normalizeSymbol(identity.symbol), { ...identity });
    });

    await this.store.write({
      references: [...referencesBySymbol.values()]
    });
  }

  async readFresh(symbols, now) {
    const snapshot = await this.readSnapshot();
    const nowMs = Date.parse(now);
    const freshReferencesBySymbol = new Map(
      snapshot.references
        .filter((reference) => isFreshReference(reference, nowMs, this.ttlMs))
        .map((reference) => [normalizeSymbol(reference.symbol), reference])
    );
    const hits = [];
    const misses = [];

    symbols.map(normalizeSymbol).forEach((symbol) => {
      const hit = freshReferencesBySymbol.get(symbol);

      if (hit === undefined) {
        misses.push(symbol);
        return;
      }

      hits.push({ ...hit });
    });

    return { hits, misses };
  }

  async readBySymbol(symbol) {
    const snapshot = await this.readSnapshot();
    const normalizedSymbol = normalizeSymbol(symbol);

    return snapshot.references.find(
      (reference) => normalizeSymbol(reference.symbol) === normalizedSymbol
    );
  }

  async readSnapshot() {
    const snapshot = await this.store.read();

    return {
      references: Array.isArray(snapshot.references) ? snapshot.references : []
    };
  }
}

class CachedTossAccessTokenProvider {
  constructor(credentialRepository, oauthClient) {
    this.credentialRepository = credentialRepository;
    this.oauthClient = oauthClient;
    this.cachedToken = null;
  }

  async readAccessToken(now) {
    if (this.cachedToken !== null && Date.parse(now) < this.cachedToken.expiresAtMs) {
      return this.cachedToken.accessToken;
    }

    const credentials = await this.credentialRepository.readCredentials();

    if (typeof credentials.clientId !== "string" || typeof credentials.clientSecret !== "string") {
      throw new StockReferenceError(
        "invalid_toss_credentials",
        "Toss credentials are not configured",
        true
      );
    }

    const token = await this.oauthClient.issueAccessToken(credentials);
    const ttlMs = Math.max((token.expiresIn - 60) * 1000, 1000);
    this.cachedToken = {
      accessToken: token.accessToken,
      expiresAtMs: Date.parse(now) + ttlMs
    };

    return token.accessToken;
  }
}

class TossStockInfoClient {
  constructor(fetcher) {
    this.fetcher = fetcher;
  }

  async fetchStockIdentities(symbols, accessToken, now) {
    const requestedSymbols = uniqueSymbols(symbols);
    const verified = [];
    const rejected = [];

    for (const chunk of chunkSymbols(requestedSymbols, 200)) {
      const chunkResult = await this.fetchChunk(chunk, accessToken, now);
      verified.push(...chunkResult.verified);
      rejected.push(...chunkResult.rejected);
    }

    return { verified, rejected };
  }

  async fetchChunk(symbols, accessToken, now) {
    const query = new URLSearchParams();
    query.set("symbols", symbols.join(","));
    let response;

    try {
      response = await this.fetcher(
        `https://openapi.tossinvest.com/api/v1/stocks?${query.toString()}`,
        {
          method: "GET",
          headers: {
            Authorization: `Bearer ${accessToken}`
          }
        }
      );
    } catch (error) {
      throw new StockReferenceError(
        "stock_reference_unavailable",
        error instanceof Error ? error.message : "Toss stock reference request failed",
        true
      );
    }

    if (!response.ok) {
      await mapStockInfoFailure(response);
    }

    const payload = await response.json().catch(() => ({}));
    const stockInfos = Array.isArray(payload.result) ? payload.result : [];
    const stockInfoBySymbol = new Map(
      stockInfos.map((stockInfo) => [normalizeSymbol(stockInfo.symbol), stockInfo])
    );
    const verified = [];
    const rejected = [];

    symbols.forEach((symbol) => {
      const stockInfo = stockInfoBySymbol.get(symbol);

      if (stockInfo === undefined) {
        rejected.push(createStockNotFound(symbol));
        return;
      }

      verified.push(mapStockInfoToVerifiedIdentity(stockInfo, now));
    });

    return { verified, rejected };
  }
}

function parseSymbolInput(rawInput) {
  const segments = String(rawInput ?? "")
    .split(/[,;\n]+/)
    .map((segment) => segment.trim())
    .filter((segment) => segment !== "");
  const seenSymbols = new Set();
  const symbols = [];
  const rejected = [];

  segments.forEach((segment) => {
    const candidates = parseSegment(segment);

    if (candidates.length === 0) {
      rejected.push({
        symbol: segment,
        reason: "invalid_request",
        message: "심볼을 찾을 수 없습니다."
      });
      return;
    }

    candidates.forEach((symbol) => {
      if (!seenSymbols.has(symbol)) {
        symbols.push(symbol);
        seenSymbols.add(symbol);
      }
    });
  });

  return { symbols, rejected };
}

function mapStockInfoToVerifiedIdentity(stockInfo, now) {
  const status = normalizeText(stockInfo.status);
  const koreanMarketDetail = stockInfo.koreanMarketDetail || null;
  const liquidationTrading = Boolean(koreanMarketDetail && koreanMarketDetail.liquidationTrading);
  const tradingSuspended = Boolean(
    koreanMarketDetail &&
      (koreanMarketDetail.krxTradingSuspended || koreanMarketDetail.nxtTradingSuspended)
  );
  const confirmationReasons = createConfirmationReasons({
    status,
    liquidationTrading,
    tradingSuspended
  });

  return {
    symbol: normalizeSymbol(stockInfo.symbol),
    market: normalizeText(stockInfo.market),
    displayName: String(stockInfo.name || stockInfo.symbol).trim(),
    englishName: String(stockInfo.englishName || "").trim(),
    currency: normalizeText(stockInfo.currency),
    status,
    securityType: normalizeText(stockInfo.securityType),
    tradingSuspended,
    liquidationTrading,
    requiresConfirmation: confirmationReasons.length > 0,
    confirmationReasons,
    verifiedAt: now
  };
}

async function verifyStockReferences(context, rawInput) {
  const parsed = parseSymbolInput(rawInput);

  if (parsed.symbols.length === 0) {
    return {
      verified: [],
      rejected: parsed.rejected
    };
  }

  const cached = await context.stockReferenceCache.readFresh(parsed.symbols, context.occurredAt);
  const accessToken = cached.misses.length > 0
    ? await context.tossAccessTokenProvider.readAccessToken(context.occurredAt)
    : null;
  const fetched = accessToken === null
    ? { verified: [], rejected: [] }
    : await context.tossStockInfoClient.fetchStockIdentities(
        cached.misses,
        accessToken,
        context.occurredAt
      );

  if (fetched.verified.length > 0) {
    await context.stockReferenceCache.saveAll(fetched.verified);
  }

  return {
    verified: [...cached.hits, ...fetched.verified],
    rejected: [...parsed.rejected, ...fetched.rejected]
  };
}

async function createVerifiedWatchCard(context) {
  const symbol = normalizeSymbol(context.payload.symbol);
  let identity = await context.stockReferenceCache.readBySymbol(symbol);

  if (identity === undefined) {
    const verified = await verifyStockReferences(context, symbol);
    identity = verified.verified.find(
      (reference) => normalizeSymbol(reference.symbol) === symbol
    );
  }

  if (identity === undefined) {
    throw new StockReferenceError(
      "stock_verification_required",
      "Stock must be verified before creating a card",
      true
    );
  }

  if (identity.requiresConfirmation === true && context.payload.confirmedRisk !== true) {
    throw new StockReferenceError(
      "stock_confirmation_required",
      "Stock requires confirmation before creating a card",
      true
    );
  }

  return context.watchlistRepository.create(
    {
      market: identity.market,
      symbol: identity.symbol,
      displayName: identity.displayName,
      groupId: typeof context.payload.groupId === "string" ? context.payload.groupId : null,
      tags: Array.isArray(context.payload.tags) ? context.payload.tags : [],
      memo: typeof context.payload.memo === "string" ? context.payload.memo : ""
    },
    context.occurredAt
  );
}

function parseSegment(segment) {
  const prefixed = segment.match(/^([A-Za-z_]+)\s*:\s*([A-Za-z0-9.-]+)$/);

  if (prefixed && prefixed[2]) {
    return [normalizeSymbol(prefixed[2])];
  }

  const suffixed = segment.match(/^([A-Za-z0-9-]+)\.([A-Za-z]{2,})$/);

  if (suffixed && suffixed[1]) {
    return [normalizeSymbol(suffixed[1])];
  }

  const matches = [
    ...(segment.match(/\b\d{6}\b/g) || []),
    ...(segment.match(/\b[A-Za-z][A-Za-z0-9.-]{0,31}\b/g) || [])
  ];

  return matches.map(normalizeSymbol);
}

function uniqueSymbols(symbols) {
  const seenSymbols = new Set();
  const unique = [];

  symbols.map(normalizeSymbol).forEach((symbol) => {
    if (!seenSymbols.has(symbol)) {
      unique.push(symbol);
      seenSymbols.add(symbol);
    }
  });

  return unique;
}

function chunkSymbols(symbols, chunkSize) {
  const chunks = [];

  for (let index = 0; index < symbols.length; index += chunkSize) {
    chunks.push(symbols.slice(index, index + chunkSize));
  }

  return chunks;
}

function createConfirmationReasons(input) {
  const reasons = [];

  if (input.status === "DELISTED") {
    reasons.push("delisted");
  } else if (input.status !== "ACTIVE") {
    reasons.push("inactive");
  }

  if (input.liquidationTrading) {
    reasons.push("liquidation_trading");
  }

  if (input.tradingSuspended) {
    reasons.push("trading_suspended");
  }

  return reasons;
}

function isFreshReference(reference, nowMs, ttlMs) {
  const verifiedAtMs = Date.parse(reference.verifiedAt);

  return Number.isFinite(verifiedAtMs) && nowMs - verifiedAtMs <= ttlMs;
}

async function mapStockInfoFailure(response) {
  let payload = {};

  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (response.status === 401 || payload.error && payload.error.code === "invalid-token") {
    throw new StockReferenceError(
      "invalid_toss_credentials",
      "Toss access token is invalid",
      true
    );
  }

  if (response.status === 429) {
    throw new StockReferenceError(
      "toss_rate_limited",
      "Toss stock reference rate limit exceeded",
      true
    );
  }

  throw new StockReferenceError(
    "stock_reference_unavailable",
    "Toss stock reference request failed",
    true
  );
}

function createStockNotFound(symbol) {
  return {
    symbol,
    reason: "stock_not_found",
    message: "종목을 찾을 수 없습니다."
  };
}

function normalizeSymbol(value) {
  return String(value ?? "").trim().toUpperCase();
}

function normalizeText(value) {
  return String(value ?? "").trim().toUpperCase();
}

module.exports = {
  CachedTossAccessTokenProvider,
  StockReferenceError,
  StoredStockReferenceCache,
  TossStockInfoClient,
  createVerifiedWatchCard,
  mapStockInfoToVerifiedIdentity,
  parseSymbolInput,
  verifyStockReferences
};
