const DAILY_CANDLES_ENDPOINT = "https://openapi.tossinvest.com/api/v1/candles";
const DAILY_CANDLE_INTERVAL = "1d";
const DAILY_CANDLE_PAGE_SIZE = 200;
const MAX_PAGE_COUNT = 1_000;
const RATE_LIMIT_GROUP = "MARKET_DATA_CHART";
const SAFE_DOWNSTREAM_ERROR_CODES = new Set([
  "invalid_toss_credentials",
  "market_data_rate_limited",
  "market_data_unavailable"
]);
const TOSS_DAILY_CANDLE_REQUEST_SPEC = Object.freeze({
  endpoint: DAILY_CANDLES_ENDPOINT,
  interval: DAILY_CANDLE_INTERVAL,
  count: DAILY_CANDLE_PAGE_SIZE,
  adjusted: true
});

class TossDailyCandleArchiveError extends Error {
  constructor(code, message, recoverable, retryAfterSeconds) {
    super(message);
    this.name = "TossDailyCandleArchiveError";
    this.code = code;
    this.recoverable = recoverable;

    if (retryAfterSeconds !== null) {
      this.retryAfterSeconds = retryAfterSeconds;
    }
  }
}

class TossDailyCandleArchiveClient {
  /**
   * @param {{ requestJson(url: string, init: object, group: string): Promise<unknown> }} rateLimitClient
   */
  constructor(rateLimitClient) {
    this.rateLimitClient = rateLimitClient;
  }

  /**
   * @param {{ symbol: string, accessToken: string, startDate: string, endDate: string }} input
   * @returns {Promise<Array<{ timestamp: string }>>}
   */
  async fetchRange(input) {
    const archive = await this.fetchRangeWithMetadata(input);

    return archive.candles;
  }

  /**
   * @param {{ symbol: string, accessToken: string, startDate: string, endDate: string }} input
   * @returns {Promise<{
   *   candles: Array<{ timestamp: string }>,
   *   pages: number,
   *   rawRows: number,
   *   duplicates: number,
   *   termination: "source_exhausted" | "start_reached"
   * }>}
   */
  async fetchRangeWithMetadata({ symbol, accessToken, startDate, endDate }) {
    const validatedSymbol = requireNonBlankText(symbol, "symbol");
    const validatedAccessToken = requireNonBlankText(accessToken, "access token");
    const dateRange = createInclusiveDateRange(startDate, endDate);
    const candlesByTimestamp = new Map();
    const seenRawTimestamps = new Set();
    const seenBeforeCursors = new Set();
    let pages = 0;
    let rawRows = 0;
    let duplicates = 0;
    let before = null;

    for (let pageCount = 0; pageCount < MAX_PAGE_COUNT; pageCount += 1) {
      const page = await this.#fetchPage(validatedSymbol, validatedAccessToken, before);
      pages += 1;
      rawRows += page.candles.length;
      duplicates += countDuplicateTimestamps(page.candles, seenRawTimestamps);
      const reachedBeforeStart = collectCandlesInRange(
        candlesByTimestamp,
        page.candles,
        dateRange
      );

      if (page.nextBefore === null) {
        return createArchiveResult(
          candlesByTimestamp,
          pages,
          rawRows,
          duplicates,
          "source_exhausted"
        );
      }

      if (
        reachedBeforeStart ||
        isBeforeStartDate(page.nextBefore, dateRange.start)
      ) {
        return createArchiveResult(
          candlesByTimestamp,
          pages,
          rawRows,
          duplicates,
          "start_reached"
        );
      }

      if (seenBeforeCursors.has(page.nextBefore)) {
        throw new TossDailyCandleArchiveError(
          "stalled_candle_pagination",
          "Toss daily candle pagination stalled before reaching the start date",
          true,
          null
        );
      }

      seenBeforeCursors.add(page.nextBefore);
      before = page.nextBefore;
    }

    throw new TossDailyCandleArchiveError(
      "candle_pagination_limit_exceeded",
      "Toss daily candle pagination exceeded the safety limit",
      true,
      null
    );
  }

  async #fetchPage(symbol, accessToken, before) {
    const query = createDailyCandleQuery(symbol, before);
    let payload;

    try {
      payload = await this.rateLimitClient.requestJson(
        `${DAILY_CANDLES_ENDPOINT}?${query.toString()}`,
        createBearerRequest(accessToken),
        RATE_LIMIT_GROUP
      );
    } catch (error) {
      throw createSanitizedRequestError(error);
    }

    return readCandlePage(payload);
  }
}

function createDailyCandleQuery(symbol, before) {
  const query = new URLSearchParams();
  query.set("symbol", symbol);
  query.set("interval", DAILY_CANDLE_INTERVAL);
  query.set("count", String(DAILY_CANDLE_PAGE_SIZE));
  query.set("adjusted", "true");

  if (before !== null) {
    query.set("before", before);
  }

  return query;
}

function createBearerRequest(accessToken) {
  return {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`
    }
  };
}

function readCandlePage(payload) {
  if (!isRecord(payload) || !isRecord(payload.result)) {
    throw createInvalidResponseError();
  }

  const result = payload.result;

  if (
    !Array.isArray(result.candles) ||
    (result.nextBefore !== null && typeof result.nextBefore !== "string") ||
    !result.candles.every(isTimestampedCandle)
  ) {
    throw createInvalidResponseError();
  }

  return {
    candles: result.candles,
    nextBefore: result.nextBefore
  };
}

function collectCandlesInRange(candlesByTimestamp, candles, dateRange) {
  let reachedBeforeStart = false;

  for (const candle of candles) {
    const dateKey = readIsoDateKey(candle.timestamp);

    if (dateKey < dateRange.start) {
      reachedBeforeStart = true;
      continue;
    }

    if (dateKey > dateRange.end || candlesByTimestamp.has(candle.timestamp)) {
      continue;
    }

    candlesByTimestamp.set(candle.timestamp, candle);
  }

  return reachedBeforeStart;
}

function countDuplicateTimestamps(candles, seenTimestamps) {
  let duplicates = 0;

  for (const candle of candles) {
    if (seenTimestamps.has(candle.timestamp)) {
      duplicates += 1;
      continue;
    }

    seenTimestamps.add(candle.timestamp);
  }

  return duplicates;
}

function createArchiveResult(
  candlesByTimestamp,
  pages,
  rawRows,
  duplicates,
  termination
) {
  return {
    candles: sortCandlesByTimestamp(candlesByTimestamp.values()),
    pages,
    rawRows,
    duplicates,
    termination
  };
}

function createInclusiveDateRange(startDate, endDate) {
  const start = readIsoDateKey(startDate);
  const end = readIsoDateKey(endDate);

  if (start === null || end === null || start > end) {
    throw new TossDailyCandleArchiveError(
      "invalid_candle_request",
      "Invalid daily candle date range",
      false,
      null
    );
  }

  return { start, end };
}

function isBeforeStartDate(timestamp, startDate) {
  const dateKey = readIsoDateKey(timestamp);

  return dateKey !== null && dateKey < startDate;
}

function isTimestampedCandle(value) {
  return isRecord(value) && readIsoDateKey(value.timestamp) !== null;
}

function readIsoDateKey(value) {
  if (typeof value !== "string") {
    return null;
  }

  const match = /^(\d{4}-\d{2}-\d{2})(?:$|T)/.exec(value);

  if (match === null) {
    return null;
  }

  const dateKey = match[1];
  const parsedDateMs = Date.parse(`${dateKey}T00:00:00.000Z`);

  if (!Number.isFinite(parsedDateMs) || !Number.isFinite(Date.parse(value))) {
    return null;
  }

  return new Date(parsedDateMs).toISOString().slice(0, 10) === dateKey
    ? dateKey
    : null;
}

function sortCandlesByTimestamp(candles) {
  return [...candles].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)
  );
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireNonBlankText(value, fieldName) {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }

  throw new TossDailyCandleArchiveError(
    "invalid_candle_request",
    `Toss daily candle ${fieldName} is required`,
    false,
    null
  );
}

function createInvalidResponseError() {
  return new TossDailyCandleArchiveError(
    "invalid_candle_response",
    "Invalid Toss daily candle response schema",
    true,
    null
  );
}

function createSanitizedRequestError(error) {
  const errorDetails = isRecord(error) ? error : {};
  const code = SAFE_DOWNSTREAM_ERROR_CODES.has(errorDetails.code)
    ? errorDetails.code
    : "toss_daily_candle_request_failed";
  const recoverable = typeof errorDetails.recoverable === "boolean"
    ? errorDetails.recoverable
    : true;
  const retryAfterSeconds = Number.isFinite(errorDetails.retryAfterSeconds) &&
    errorDetails.retryAfterSeconds >= 0
    ? errorDetails.retryAfterSeconds
    : null;

  return new TossDailyCandleArchiveError(
    code,
    "Toss daily candle request failed",
    recoverable,
    retryAfterSeconds
  );
}

module.exports = {
  TOSS_DAILY_CANDLE_REQUEST_SPEC,
  TossDailyCandleArchiveClient
};
