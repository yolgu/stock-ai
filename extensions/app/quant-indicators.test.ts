import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  StoredQuantIndicatorSnapshotRepository,
  createQuantIndicatorSnapshot
} = require("./quant-indicators.cjs") as {
  StoredQuantIndicatorSnapshotRepository: new (
    filePath: string,
    options?: { maxSnapshots?: number }
  ) => {
    saveAll(snapshots: unknown[]): Promise<void>;
    readLatest(cardIds?: string[]): Promise<unknown[]>;
  };
  createQuantIndicatorSnapshot(input: {
    marketDataSnapshot: Record<string, unknown>;
    calculatedAt: string;
  }): Record<string, unknown>;
};

let tempDirectory: string | undefined;

async function createTempPath(fileName: string): Promise<string> {
  tempDirectory = await mkdtemp(join(tmpdir(), "quant-indicators-"));

  return join(tempDirectory, fileName);
}

afterEach(async () => {
  if (tempDirectory !== undefined) {
    await rm(tempDirectory, { recursive: true, force: true });
    tempDirectory = undefined;
  }
});

describe("createQuantIndicatorSnapshot", () => {
  it("calculates deterministic VWAP, estimated CVD, spread, ATR, supply pressure, and risk reward", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createCompleteMarketDataSnapshot(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      sourceMarketDataSnapshotId: "market-1",
      cardId: "card-1",
      market: "NASDAQ",
      symbol: "MU",
      quality: "complete",
      decisionStatus: "watch",
      decisionLabel: "관망",
      indicators: {
        vwap: {
          status: "available",
          value: "101.7500",
          distanceBps: 172,
          label: "VWAP 위 안착"
        },
        cvd: {
          status: "estimated",
          value: "45",
          confidence: "estimated",
          label: "체결 압력 우위"
        },
        spread: {
          status: "available",
          spreadBps: 19,
          label: "스프레드 정상"
        },
        atrStop: {
          status: "available",
          atr: "1.0000",
          stopDistancePercent: 0.97,
          label: "손절 폭 정상"
        },
        supplyPressure: {
          status: "available",
          label: "매물대 부담 낮음"
        },
        riskReward: {
          status: "available",
          ratio: 2,
          label: "손익비 1.5x 이상"
        }
      }
    });
    expect(snapshot.signals).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: "vwap", label: "VWAP 위 안착" }),
        expect.objectContaining({ key: "cvd", status: "estimated" }),
        expect.objectContaining({ key: "spread", label: "스프레드 정상" })
      ])
    );
  });

  it("reports unavailable calculations when required market observations are missing", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: {
        ...createCompleteMarketDataSnapshot(),
        observations: {
          price: null,
          trades: [],
          orderbook: null,
          intradayCandles: null,
          dailyCandles: null,
          exchangeRate: null,
          marketSession: null
        }
      },
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      quality: "unavailable",
      decisionStatus: "dataInsufficient",
      decisionLabel: "데이터 부족",
      indicators: {
        vwap: {
          status: "unavailable",
          unavailableReason: "intraday candles are required"
        },
        cvd: {
          status: "unavailable",
          unavailableReason: "at least two trades are required"
        },
        spread: {
          status: "unavailable",
          unavailableReason: "orderbook asks and bids are required"
        },
        atrStop: {
          status: "unavailable",
          unavailableReason: "at least 15 daily candles are required"
        }
      }
    });
  });

  it("classifies a VWAP loss with weakening estimated CVD as invalidated", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createInvalidatedMarketDataSnapshot(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      decisionStatus: "invalidated",
      decisionLabel: "무효화",
      nextCheckLabel: "시나리오 무효, 손절 우선"
    });
  });
});

describe("StoredQuantIndicatorSnapshotRepository", () => {
  it("stores latest quant snapshots with owner-only permissions and without secrets", async () => {
    const filePath = await createTempPath("quant-indicator-cache.json");
    const repository = new StoredQuantIndicatorSnapshotRepository(filePath);
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createCompleteMarketDataSnapshot(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    await repository.saveAll([snapshot]);

    expect(await repository.readLatest(["card-1"])).toEqual([
      expect.objectContaining({
        cardId: "card-1",
        symbol: "MU",
        decisionStatus: "watch",
        sourceMarketDataSnapshotId: "market-1"
      })
    ]);
    expect((await stat(filePath)).mode & 0o777).toBe(0o600);
    const savedText = await readFile(filePath, "utf8");
    expect(savedText).not.toContain("access_token");
    expect(savedText).not.toContain("clientSecret");
    expect(savedText).not.toContain("Bearer ");
  });
});

function createCompleteMarketDataSnapshot(): Record<string, unknown> {
  return {
    snapshotId: "market-1",
    cardId: "card-1",
    market: "NASDAQ",
    symbol: "MU",
    capturedAt: "2026-07-06T09:34:00.000Z",
    freshness: "fresh",
    quality: "complete",
    observations: {
      price: {
        symbol: "MU",
        timestamp: "2026-07-06T09:34:00.000Z",
        lastPrice: "103.50",
        currency: "USD"
      },
      trades: [
        { price: "100.00", volume: "10", timestamp: "2026-07-06T09:30:00.000Z", currency: "USD" },
        { price: "101.00", volume: "20", timestamp: "2026-07-06T09:31:00.000Z", currency: "USD" },
        { price: "100.50", volume: "5", timestamp: "2026-07-06T09:32:00.000Z", currency: "USD" },
        { price: "102.00", volume: "30", timestamp: "2026-07-06T09:33:00.000Z", currency: "USD" }
      ],
      orderbook: {
        timestamp: "2026-07-06T09:34:00.000Z",
        currency: "USD",
        asks: [{ price: "103.60", volume: "100" }],
        bids: [{ price: "103.40", volume: "120" }]
      },
      intradayCandles: {
        interval: "1m",
        nextBefore: null,
        candles: [
          createCandle("2026-07-06T09:30:00.000Z", "100", "101", "99", "100", "1000"),
          createCandle("2026-07-06T09:31:00.000Z", "102", "103", "101", "102", "2000"),
          createCandle("2026-07-06T09:32:00.000Z", "103", "104", "102", "103", "1000")
        ]
      },
      dailyCandles: {
        interval: "1d",
        nextBefore: null,
        candles: createDailyCandles("103.50")
      },
      exchangeRate: null,
      marketSession: {
        country: "US",
        state: "regular",
        source: "calendar"
      }
    },
    adapterErrors: []
  };
}

function createInvalidatedMarketDataSnapshot(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      price: {
        symbol: "MU",
        timestamp: "2026-07-06T09:34:00.000Z",
        lastPrice: "99.00",
        currency: "USD"
      },
      trades: [
        { price: "102.00", volume: "10", timestamp: "2026-07-06T09:30:00.000Z", currency: "USD" },
        { price: "101.00", volume: "20", timestamp: "2026-07-06T09:31:00.000Z", currency: "USD" },
        { price: "100.50", volume: "15", timestamp: "2026-07-06T09:32:00.000Z", currency: "USD" },
        { price: "99.00", volume: "30", timestamp: "2026-07-06T09:33:00.000Z", currency: "USD" }
      ]
    }
  };
}

function createCandle(
  timestamp: string,
  openPrice: string,
  highPrice: string,
  lowPrice: string,
  closePrice: string,
  volume: string
): Record<string, string> {
  return {
    timestamp,
    openPrice,
    highPrice,
    lowPrice,
    closePrice,
    volume,
    currency: "USD"
  };
}

function createDailyCandles(currentPrice: string): Array<Record<string, string>> {
  return Array.from({ length: 15 }, (_value, index) => {
    const close = index === 14 ? Number(currentPrice) : 100 + index * 0.25;

    return createCandle(
      `2026-06-${String(20 + index).padStart(2, "0")}T00:00:00.000Z`,
      close.toFixed(2),
      (close + 0.5).toFixed(2),
      (close - 0.5).toFixed(2),
      close.toFixed(2),
      "10000"
    );
  });
}
