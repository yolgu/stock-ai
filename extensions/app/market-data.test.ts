import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  RateLimitAwareTossClient,
  MarketDataError,
  StoredMarketDataSnapshotRepository,
  TossMarketDataClient,
  canonicalizeMinuteCandles,
  createMarketDataSnapshot,
  refreshMarketDataForWatchlist
} = require("./market-data.cjs") as {
  MarketDataError: new (
    code: string,
    message: string,
    recoverable: boolean,
    extra?: Record<string, unknown>
  ) => Error & {
    code: string;
    recoverable: boolean;
    retryAfterSeconds?: number;
  };
  RateLimitAwareTossClient: new (
    fetcher: typeof fetch,
    options?: {
      nowMs?: () => number;
      sleep?: (durationMs: number) => Promise<void>;
      minimumIntervalByGroup?: Record<string, number>;
    }
  ) => {
    requestJson(url: string, init: RequestInit, group: string): Promise<unknown>;
  };
  StoredMarketDataSnapshotRepository: new (
    filePath: string,
    options?: { maxSnapshots?: number }
  ) => {
    saveAll(snapshots: unknown[]): Promise<void>;
    readLatest(cardIds?: string[]): Promise<unknown[]>;
  };
  TossMarketDataClient: new (rateLimitClient: {
    requestJson(url: string, init: RequestInit, group: string): Promise<unknown>;
  }) => {
    fetchPrices(symbols: string[], accessToken: string): Promise<unknown[]>;
    fetchTrades(symbol: string, accessToken: string): Promise<unknown[]>;
    fetchOrderbook(symbol: string, accessToken: string): Promise<unknown>;
    fetchCandles(
      symbol: string,
      interval: "1m" | "1d",
      accessToken: string,
      count?: number,
      before?: string | null
    ): Promise<unknown>;
  };
  canonicalizeMinuteCandles(
    candles: Array<Record<string, unknown>>,
    completedBefore: string
  ): Array<Record<string, unknown>>;
  createMarketDataSnapshot(input: {
    card: { id: string; market: string; symbol: string };
    capturedAt: string;
    price: unknown | null;
    trades: unknown[];
    orderbook: unknown | null;
    intradayCandles: unknown | null;
    dailyCandles: unknown | null;
    exchangeRate: unknown | null;
    marketSession: unknown | null;
    adapterErrors: unknown[];
  }): unknown;
  refreshMarketDataForWatchlist(
    context: Record<string, unknown>,
    payload: Record<string, unknown>
  ): Promise<{
    refreshedAt: string;
    nextPollDelayMs: number;
    snapshots: Array<{
      adapterErrors: unknown[];
      observations?: {
        intradayCandles?: {
          fetchedAt?: string;
          candles: Array<Record<string, unknown>>;
        };
        marketSession?: {
          country: string;
          state: string;
          source: string;
        };
      };
    }>;
  }>;
};

let tempDirectory: string | undefined;

async function createTempPath(fileName: string): Promise<string> {
  tempDirectory = await mkdtemp(join(tmpdir(), "market-data-"));

  return join(tempDirectory, fileName);
}

afterEach(async () => {
  if (tempDirectory !== undefined) {
    await rm(tempDirectory, { recursive: true, force: true });
    tempDirectory = undefined;
  }
});

describe("TossMarketDataClient", () => {
  it("requests price batches and per-symbol market observations without account headers", async () => {
    const requests: Array<{ url: string; headers: Headers }> = [];
    const rateLimitClient = {
      requestJson: async (url: string, init: RequestInit): Promise<unknown> => {
        requests.push({ url, headers: new Headers(init.headers) });

        if (url.includes("/prices")) {
          return { result: [{ symbol: "MU", lastPrice: "194.93", currency: "USD" }] };
        }

        if (url.includes("/trades")) {
          return { result: [{ price: "194.93", volume: "10", timestamp: "2026-07-06T09:00:00Z", currency: "USD" }] };
        }

        if (url.includes("/orderbook")) {
          return { result: { currency: "USD", asks: [], bids: [] } };
        }

        return { result: { candles: [], nextBefore: null } };
      }
    };
    const client = new TossMarketDataClient(rateLimitClient);

    await client.fetchPrices(["MU", "AAPL"], "access-token-that-must-not-leak");
    await client.fetchTrades("MU", "access-token-that-must-not-leak");
    await client.fetchOrderbook("MU", "access-token-that-must-not-leak");
    await client.fetchCandles(
      "MU",
      "1m",
      "access-token-that-must-not-leak",
      100,
      "2026-07-01T00:00:00.000Z"
    );

    expect(requests.map((request) => request.url)).toEqual([
      "https://openapi.tossinvest.com/api/v1/prices?symbols=MU%2CAAPL",
      "https://openapi.tossinvest.com/api/v1/trades?symbol=MU&count=50",
      "https://openapi.tossinvest.com/api/v1/orderbook?symbol=MU",
      "https://openapi.tossinvest.com/api/v1/candles?symbol=MU&interval=1m&count=100&adjusted=true&before=2026-07-01T00%3A00%3A00.000Z"
    ]);
    expect(requests.every((request) => request.headers.get("Authorization") === "Bearer access-token-that-must-not-leak")).toBe(true);
    expect(requests.some((request) => request.headers.has("X-Tossinvest-Account"))).toBe(false);
  });

  it("maps Toss 429 responses to a recoverable market data rate limit error", async () => {
    const fetcher = async (): Promise<Response> =>
      new Response(JSON.stringify({ error: { code: "rate-limit-exceeded" } }), {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": "2",
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": "1"
        }
      });
    const client = new RateLimitAwareTossClient(fetcher);

    await expect(
      client.requestJson("https://openapi.tossinvest.com/api/v1/prices?symbols=MU", {}, "MARKET_DATA")
    ).rejects.toMatchObject({
      code: "market_data_rate_limited",
      recoverable: true,
      retryAfterSeconds: 2
    });
  });

  it("paces requests in the same rate-limit group", async () => {
    let virtualTimeMs = 0;
    const requestTimes: number[] = [];
    const fetcher = async (): Promise<Response> => {
      requestTimes.push(virtualTimeMs);

      return new Response(JSON.stringify({ result: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    };
    const client = new RateLimitAwareTossClient(fetcher, {
      nowMs: () => virtualTimeMs,
      sleep: async (durationMs: number): Promise<void> => {
        virtualTimeMs += durationMs;
      },
      minimumIntervalByGroup: {
        MARKET_DATA: 125
      }
    });

    await client.requestJson("https://openapi.tossinvest.com/api/v1/trades?symbol=MU", {}, "MARKET_DATA");
    await client.requestJson("https://openapi.tossinvest.com/api/v1/orderbook?symbol=MU", {}, "MARKET_DATA");

    expect(requestTimes).toEqual([0, 125]);
  });
});

describe("refreshMarketDataForWatchlist", () => {
  it("refreshes intraday candles from their fetchedAt instead of the newer snapshot capturedAt", async () => {
    const fetchedIntervals: string[] = [];
    const context = {
      occurredAt: "2026-07-06T09:01:00.000Z",
      watchlistRepository: {
        list: async () => ({
          activeCards: [{ id: "card-1", market: "NASDAQ", symbol: "MU" }]
        })
      },
      tossAccessTokenProvider: {
        readAccessToken: async () => "access-token-that-must-not-leak"
      },
      marketDataSnapshotRepository: {
        readLatest: async () => [{
          snapshotId: "snapshot-previous",
          cardId: "card-1",
          market: "NASDAQ",
          symbol: "MU",
          capturedAt: "2026-07-06T09:00:45.000Z",
          freshness: "fresh",
          quality: "complete",
          observations: {
            price: null,
            trades: [],
            orderbook: null,
            intradayCandles: {
              interval: "1m",
              fetchedAt: "2026-07-06T09:00:00.000Z",
              candles: [],
              nextBefore: null
            },
            dailyCandles: {
              interval: "1d",
              fetchedAt: "2026-07-06T09:00:45.000Z",
              candles: [],
              nextBefore: null
            },
            exchangeRate: null,
            marketSession: null
          },
          adapterErrors: []
        }],
        saveAll: async (): Promise<void> => {}
      },
      tossMarketDataClient: {
        fetchPrices: async () => [],
        fetchTrades: async () => [],
        fetchOrderbook: async () => null,
        fetchCandles: async (_symbol: string, interval: "1m" | "1d") => {
          fetchedIntervals.push(interval);

          return { interval, candles: [], nextBefore: null };
        }
      },
      tossMarketInfoClient: {
        fetchMarketCalendar: async () => ({
          today: {
            regularMarket: {
              startTime: "2026-07-06T00:00:00.000Z",
              endTime: "2026-07-06T23:59:59.000Z"
            }
          }
        }),
        fetchExchangeRate: async () => null
      }
    };

    const result = await refreshMarketDataForWatchlist(context, {
      visibleCardIds: ["card-1"]
    });

    expect(fetchedIntervals).toEqual(["1m"]);
    expect(result.snapshots[0]?.observations?.intradayCandles?.fetchedAt).toBe(
      "2026-07-06T09:01:00.000Z"
    );
  });

  it("keeps US day-market polling at 15 seconds when pre-market exists later on the same Korean calendar day", async () => {
    const context = {
      occurredAt: "2026-07-07T03:30:00.000Z",
      watchlistRepository: {
        list: async () => ({
          activeCards: [
            {
              id: "card-1",
              market: "NASDAQ",
              symbol: "MU"
            }
          ]
        })
      },
      tossAccessTokenProvider: {
        readAccessToken: async () => "access-token-that-must-not-leak"
      },
      marketDataSnapshotRepository: {
        readLatest: async () => [],
        saveAll: async (): Promise<void> => {}
      },
      tossMarketDataClient: {
        fetchPrices: async () => [
          {
            symbol: "MU",
            lastPrice: "194.93",
            currency: "USD",
            timestamp: "2026-07-07T12:30:00.000+09:00"
          }
        ],
        fetchTrades: async () => [],
        fetchOrderbook: async () => null,
        fetchCandles: async (_symbol: string, interval: "1m" | "1d") => ({
          interval,
          candles: [],
          nextBefore: null
        })
      },
      tossMarketInfoClient: {
        fetchMarketCalendar: async () => ({
          today: {
            date: "2026-07-07",
            dayMarket: {
              startTime: "2026-07-07T09:00:00.000+09:00",
              endTime: "2026-07-07T17:00:00.000+09:00"
            },
            preMarket: {
              startTime: "2026-07-07T17:00:00.000+09:00",
              endTime: "2026-07-07T22:30:00.000+09:00"
            },
            regularMarket: {
              startTime: "2026-07-07T22:30:00.000+09:00",
              endTime: "2026-07-08T05:00:00.000+09:00"
            },
            afterMarket: {
              startTime: "2026-07-08T05:00:00.000+09:00",
              endTime: "2026-07-08T08:50:00.000+09:00"
            }
          }
        }),
        fetchExchangeRate: async () => null
      }
    };

    const result = await refreshMarketDataForWatchlist(context, {
      visibleCardIds: ["card-1"]
    });

    expect(result.nextPollDelayMs).toBe(15_000);
    expect(result.snapshots[0]?.observations?.marketSession).toEqual({
      country: "US",
      state: "pre",
      source: "calendar"
    });
  });

  it("keeps US regular-session polling at 15 seconds when the session is on the previous Korean calendar day", async () => {
    const savedSnapshots: unknown[] = [];
    const context = {
      occurredAt: "2026-07-06T16:13:00.000Z",
      watchlistRepository: {
        list: async () => ({
          activeCards: [
            {
              id: "card-1",
              market: "NASDAQ",
              symbol: "MU"
            }
          ]
        })
      },
      tossAccessTokenProvider: {
        readAccessToken: async () => "access-token-that-must-not-leak"
      },
      marketDataSnapshotRepository: {
        readLatest: async () => [],
        saveAll: async (snapshots: unknown[]): Promise<void> => {
          savedSnapshots.push(...snapshots);
        }
      },
      tossMarketDataClient: {
        fetchPrices: async () => [
          {
            symbol: "MU",
            lastPrice: "194.93",
            currency: "USD",
            timestamp: "2026-07-07T01:13:00.000+09:00"
          }
        ],
        fetchTrades: async () => [],
        fetchOrderbook: async () => null,
        fetchCandles: async (_symbol: string, interval: "1m" | "1d") => ({
          interval,
          candles: [],
          nextBefore: null
        })
      },
      tossMarketInfoClient: {
        fetchMarketCalendar: async () => ({
          today: {
            date: "2026-07-07",
            regularMarket: {
              startTime: "2026-07-07T22:30:00.000+09:00",
              endTime: "2026-07-08T05:00:00.000+09:00"
            }
          },
          previousBusinessDay: {
            date: "2026-07-06",
            regularMarket: {
              startTime: "2026-07-06T22:30:00.000+09:00",
              endTime: "2026-07-07T05:00:00.000+09:00"
            }
          }
        }),
        fetchExchangeRate: async () => null
      }
    };

    const result = await refreshMarketDataForWatchlist(context, {
      visibleCardIds: ["card-1"]
    });

    expect(result.nextPollDelayMs).toBe(15_000);
    expect(result.snapshots[0]?.observations?.marketSession).toEqual({
      country: "US",
      state: "regular",
      source: "calendar"
    });
    expect(savedSnapshots).toHaveLength(1);
  });

  it("uses rate-limit retry-after errors to delay the next polling cycle", async () => {
    const savedSnapshots: unknown[] = [];
    const rateLimitedError = new MarketDataError(
      "market_data_rate_limited",
      "Toss market data rate limit exceeded",
      true,
      { retryAfterSeconds: 60 }
    );
    const context = {
      occurredAt: "2026-07-06T09:00:00.000Z",
      watchlistRepository: {
        list: async () => ({
          activeCards: [
            {
              id: "card-1",
              market: "NASDAQ",
              symbol: "MU"
            }
          ]
        })
      },
      tossAccessTokenProvider: {
        readAccessToken: async () => "access-token-that-must-not-leak"
      },
      marketDataSnapshotRepository: {
        readLatest: async () => [],
        saveAll: async (snapshots: unknown[]): Promise<void> => {
          savedSnapshots.push(...snapshots);
        }
      },
      tossMarketDataClient: {
        fetchPrices: async () => {
          throw rateLimitedError;
        },
        fetchTrades: async () => [],
        fetchOrderbook: async () => null,
        fetchCandles: async (_symbol: string, interval: "1m" | "1d") => ({
          interval,
          candles: [],
          nextBefore: null
        })
      },
      tossMarketInfoClient: {
        fetchMarketCalendar: async () => ({
          today: {
            date: "2026-07-06",
            regularMarket: {
              startTime: "2026-07-06T00:00:00.000Z",
              endTime: "2026-07-06T23:59:59.000Z"
            }
          }
        }),
        fetchExchangeRate: async () => null
      }
    };

    const result = await refreshMarketDataForWatchlist(context, {
      visibleCardIds: ["card-1"]
    });

    expect(result.nextPollDelayMs).toBeGreaterThanOrEqual(60_000);
    expect(result.snapshots[0]?.adapterErrors).toContainEqual(
      expect.objectContaining({
        endpoint: "prices",
        code: "market_data_rate_limited",
        retryAfterSeconds: 60
      })
    );
    expect(savedSnapshots).toHaveLength(1);
  });
});

describe("StoredMarketDataSnapshotRepository", () => {
  it("stores latest snapshots with owner-only permissions and without secrets", async () => {
    const filePath = await createTempPath("market-data-cache.json");
    const repository = new StoredMarketDataSnapshotRepository(filePath);
    const snapshot = createMarketDataSnapshot({
      card: { id: "card-1", market: "NASDAQ", symbol: "MU" },
      capturedAt: "2026-07-06T09:00:00.000Z",
      price: { symbol: "MU", lastPrice: "194.93", currency: "USD", timestamp: null },
      trades: [],
      orderbook: null,
      intradayCandles: null,
      dailyCandles: null,
      exchangeRate: null,
      marketSession: { country: "US", state: "regular", source: "calendar" },
      adapterErrors: []
    });

    await repository.saveAll([snapshot]);

    expect(await repository.readLatest(["card-1"])).toEqual([
      expect.objectContaining({
        cardId: "card-1",
        symbol: "MU",
        quality: "complete",
        observations: expect.objectContaining({
          price: expect.objectContaining({
            lastPrice: "194.93"
          })
        })
      })
    ]);
    expect((await stat(filePath)).mode & 0o777).toBe(0o600);
    const savedText = await readFile(filePath, "utf8");
    expect(savedText).not.toContain("access_token");
    expect(savedText).not.toContain("clientSecret");
    expect(savedText).not.toContain("Bearer ");
  });
});

describe("createMarketDataSnapshot", () => {
  it("sorts and deduplicates minute candles while excluding incomplete and future minutes", () => {
    const candles = canonicalizeMinuteCandles(
      [
        createRawCandle("2026-07-06T09:02:00.000Z", "102"),
        createRawCandle("2026-07-06T09:00:00.000Z", "100"),
        createRawCandle("2026-07-06T09:01:10.000Z", "101-old"),
        createRawCandle("2026-07-06T09:03:00.000Z", "103"),
        createRawCandle("2026-07-06T09:01:40.000Z", "101-new")
      ],
      "2026-07-06T09:02:00.000Z"
    );

    expect(candles.map((candle) => candle.timestamp)).toEqual([
      "2026-07-06T09:00:00.000Z",
      "2026-07-06T09:01:40.000Z"
    ]);
    expect(candles[1]?.closePrice).toBe("101-new");
  });

  it("degrades quality when observations include adapter errors", () => {
    const partialSnapshot = createMarketDataSnapshot({
      card: { id: "card-1", market: "NASDAQ", symbol: "MU" },
      capturedAt: "2026-07-06T09:00:00.000Z",
      price: { symbol: "MU", lastPrice: "194.93", currency: "USD", timestamp: null },
      trades: [],
      orderbook: null,
      intradayCandles: null,
      dailyCandles: null,
      exchangeRate: null,
      marketSession: null,
      adapterErrors: [
        {
          endpoint: "trades",
          code: "market_data_unavailable",
          message: "failed",
          recoverable: true
        }
      ]
    });
    const degradedSnapshot = createMarketDataSnapshot({
      card: { id: "card-1", market: "NASDAQ", symbol: "MU" },
      capturedAt: "2026-07-06T09:00:00.000Z",
      price: null,
      trades: [],
      orderbook: null,
      intradayCandles: null,
      dailyCandles: null,
      exchangeRate: null,
      marketSession: null,
      adapterErrors: [
        {
          endpoint: "prices",
          code: "market_data_unavailable",
          message: "failed",
          recoverable: true
        }
      ]
    });

    expect(partialSnapshot).toEqual(
      expect.objectContaining({
        quality: "partial"
      })
    );
    expect(degradedSnapshot).toEqual(
      expect.objectContaining({
        quality: "degraded"
      })
    );
  });
});

function createRawCandle(timestamp: string, closePrice: string): Record<string, unknown> {
  return {
    timestamp,
    openPrice: closePrice,
    highPrice: closePrice,
    lowPrice: closePrice,
    closePrice,
    volume: "1",
    currency: "USD"
  };
}
