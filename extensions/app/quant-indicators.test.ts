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
  it("calculates deterministic VWAP, estimated CVD, spread, profit taking pressure, ATR, supply pressure, and risk reward", () => {
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
        basicReturn: {
          status: "available",
          currentPrice: "103.5000",
          referencePrice: "103.5000",
          absoluteChange: "0.0000",
          simpleReturnPercent: 0,
          logReturnPercent: 0,
          currency: "USD",
          referenceLabel: "전일 종가",
          label: "전일 종가 대비 보합"
        },
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
          pocPrice: "102.0000",
          overheadRatio: 0,
          label: "매물대 부담 낮음"
        },
        profitTakingPressure: {
          status: "available",
          profitLongRatio: 1,
          weightedProfitPressure: 0.02,
          vwapAtrExtension: 1,
          sellFlowPressure: 0,
          askBookPressure: 0,
          volumeExpansion: 0.38,
          score: 65,
          label: "차익실현 리스크 높음",
          severity: "warning",
          causes: {
            profitBurden: {
              status: "available",
              score: 100,
              label: "수익권 부담 매우 높음",
              severity: "danger",
              reason: "수익권 물량과 VWAP/ATR 이격이 함께 큽니다."
            },
            realizedSellPressure: {
              status: "estimated",
              score: 3,
              label: "실제 매도 압력 낮음",
              severity: "positive",
              reason: "최근 체결 방향과 호가 잔량으로 추정합니다."
            },
            overheadSupplyPressure: {
              status: "available",
              score: 0,
              label: "위쪽 매물 부담 낮음",
              severity: "positive",
              reason: "현재가 위 거래량 부담을 ATR 기준으로 봅니다."
            },
            liquidityImpactRisk: {
              status: "available",
              score: 56,
              label: "체결 환경 위험 경계",
              severity: "warning",
              reason: "스프레드, 호가 깊이, 최근 가격충격으로 추정합니다."
            }
          }
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
    const explanationTraces = snapshot.explanationTraces as Array<Record<string, unknown>>;
    const basicReturnTrace = explanationTraces.find((trace) => trace.key === "basicReturn");
    const cvdTrace = explanationTraces.find((trace) => trace.key === "cvd");
    const profitTakingPressureTrace: Record<string, unknown> | undefined =
      explanationTraces.find(
      (trace) => trace.key === "profitTakingPressure"
    );

    expect(basicReturnTrace).toMatchObject({
      key: "basicReturn",
      originalFormula: expect.arrayContaining(["단순 수익률 = 현재가 / 기준가 - 1"]),
      substitutedFormula: expect.arrayContaining(["단순 수익률 = 103.50 / 103.50 - 1"]),
      result: expect.arrayContaining(["단순 수익률 = 0.00%"])
    });
    expect(cvdTrace).toMatchObject({
      key: "cvd",
      limitation: "Toss 체결 데이터에 aggressor side가 없어 tick-rule로 추정합니다."
    });
    expect(profitTakingPressureTrace).toBeUndefined();
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
        basicReturn: {
          status: "unavailable",
          unavailableReason: "current price and previous close are required"
        },
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
        },
        velocityAcceleration: {
          status: "unavailable",
          unavailableReason: "at least three intraday candles are required"
        },
        distanceProfile: {
          status: "unavailable",
          unavailableReason: "VWAP, ATR, and at least 20 intraday candles are required"
        },
        rsiMomentum: {
          status: "unavailable",
          unavailableReason: "at least 15 intraday candles are required"
        },
        profitTakingPressure: {
          status: "unavailable",
          unavailableReason: "current price, intraday candles, VWAP, and ATR are required"
        },
        marketSentimentScore: {
          status: "unavailable",
          unavailableReason: "deterministic indicator components are required"
        },
        intradayTradeScore: {
          status: "unavailable",
          unavailableReason: "market sentiment score is required"
        }
      }
    });
  });

  it("calculates LLM-free velocity, distance, RSI, sentiment score, and trade score", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createExpandedDeterministicMarketDataSnapshot(),
      calculatedAt: "2026-07-06T09:50:00.000Z"
    });

    expect(snapshot).toMatchObject({
      quality: "complete",
      indicators: {
        velocityAcceleration: {
          status: "available",
          latestLogReturnPercent: 0.84,
          priceAccelerationPercent: -0.01,
          volumeChangePercent: 0,
          estimatedCvdChange: "5",
          label: "상승 속도 둔화",
          severity: "warning"
        },
        distanceProfile: {
          status: "available",
          vwapDistanceBps: 868,
          movingAverageDistanceBps: 868,
          atrMultipleFromPreviousClose: 0,
          label: "상방 이격 과열",
          severity: "warning"
        },
        rsiMomentum: {
          status: "available",
          rsi: 100,
          momentumPercent: 4.29,
          label: "RSI 과열",
          severity: "warning"
        },
        profitTakingPressure: {
          status: "available",
          profitLongRatio: 0.95,
          score: 65,
          label: "차익실현 리스크 높음",
          severity: "warning"
        },
        marketSentimentScore: {
          status: "available",
          score: 85,
          label: "정량 심리 우호",
          severity: "positive"
        },
        intradayTradeScore: {
          status: "available",
          conditionStrengthPercent: 97.07,
          label: "조건 충족 강함",
          severity: "positive"
        }
      }
    });

    const explanationTraces = snapshot.explanationTraces as Array<Record<string, unknown>>;

    expect(explanationTraces.map((trace) => trace.key)).toEqual(
      expect.arrayContaining([
        "velocityAcceleration",
        "distanceProfile",
        "rsiMomentum",
        "marketSentimentScore",
        "intradayTradeScore"
      ])
    );
    expect(explanationTraces.find((trace) => trace.key === "intradayTradeScore")).toMatchObject({
      originalFormula: expect.arrayContaining(["조건 충족 강도 = sigmoid((정량 심리 점수 - 50) / 10) × 100"]),
      result: expect.arrayContaining(["조건 충족 강도 = 97.07%"])
    });
  });

  it("raises the composite score when realized selling pressure confirms large profit burden", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createStrongProfitTakingPressureSnapshot(),
      calculatedAt: "2026-07-06T09:50:00.000Z"
    });

    expect(snapshot).toMatchObject({
      indicators: {
        profitTakingPressure: {
          status: "available",
          score: 75,
          label: "차익실현 리스크 높음",
          severity: "warning",
          causes: {
            profitBurden: {
              score: 100,
              label: "수익권 부담 매우 높음"
            },
            realizedSellPressure: {
              score: 96,
              label: "실제 매도 압력 매우 높음"
            }
          }
        },
        marketSentimentScore: {
          status: "available",
          score: 64,
          label: "정량 심리 중립",
          severity: "neutral"
        }
      }
    });
  });

  it("keeps overhead supply as a cause without turning it into realized profit taking pressure", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createOverheadSupplyWithoutProfitTakingSnapshot(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      indicators: {
        supplyPressure: {
          status: "available",
          overheadRatio: 0.75,
          label: "상단 매물대 근접",
          severity: "danger"
        },
        profitTakingPressure: {
          status: "available",
          profitLongRatio: 0.25,
          score: 65,
          label: "차익실현 리스크 높음",
          severity: "warning",
          causes: {
            profitBurden: {
              score: 19,
              label: "수익권 부담 낮음"
            },
            realizedSellPressure: {
              score: 20,
              label: "실제 매도 압력 낮음"
            },
            overheadSupplyPressure: {
              score: 85,
              label: "위쪽 매물 부담 매우 높음"
            }
          }
        }
      }
    });
  });

  it("keeps a partial score when trade flow and orderbook causes are unavailable", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createProfitTakingPressureWithoutFlowSnapshot(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      indicators: {
        profitTakingPressure: {
          status: "available",
          profitLongRatio: 1,
          vwapAtrExtension: 1,
          sellFlowPressure: 0,
          askBookPressure: 0,
          score: 65,
          label: "차익실현 리스크 높음",
          severity: "warning",
          causes: {
            profitBurden: {
              status: "available",
              score: 100
            },
            realizedSellPressure: {
              status: "unavailable",
              score: null,
              label: "실제 매도 압력 계산 불가"
            },
            liquidityImpactRisk: {
              status: "estimated",
              score: 49,
              label: "체결 환경 위험 경계"
            }
          }
        }
      }
    });
  });

  it("uses the previous daily close when the daily candle contains the current trading date", () => {
    const snapshot = createQuantIndicatorSnapshot({
      marketDataSnapshot: createMarketDataSnapshotWithCurrentSessionDailyCandle(),
      calculatedAt: "2026-07-06T09:35:00.000Z"
    });

    expect(snapshot).toMatchObject({
      indicators: {
        basicReturn: {
          status: "available",
          currentPrice: "103.5000",
          referencePrice: "100.0000",
          absoluteChange: "3.5000",
          simpleReturnPercent: 3.5,
          logReturnPercent: 3.44,
          referenceLabel: "전일 종가"
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

function createMarketDataSnapshotWithCurrentSessionDailyCandle(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      dailyCandles: {
        interval: "1d",
        nextBefore: null,
        candles: [
          createCandle("2026-07-01T00:00:00.000Z", "98", "99", "97", "98.50", "10000"),
          createCandle("2026-07-02T00:00:00.000Z", "99", "100", "98", "99.50", "10000"),
          createCandle("2026-07-03T00:00:00.000Z", "100", "101", "99", "100.00", "10000"),
          createCandle("2026-07-06T00:00:00.000Z", "101", "104", "100", "103.50", "10000")
        ]
      }
    }
  };
}

function createOverheadSupplyWithoutProfitTakingSnapshot(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      price: {
        symbol: "MU",
        timestamp: "2026-07-06T09:34:00.000Z",
        lastPrice: "100.00",
        currency: "USD"
      },
      trades: [
        { price: "100.00", volume: "10", timestamp: "2026-07-06T09:30:00.000Z", currency: "USD" },
        { price: "99.50", volume: "20", timestamp: "2026-07-06T09:31:00.000Z", currency: "USD" },
        { price: "99.00", volume: "15", timestamp: "2026-07-06T09:32:00.000Z", currency: "USD" },
        { price: "99.50", volume: "30", timestamp: "2026-07-06T09:33:00.000Z", currency: "USD" }
      ],
      orderbook: {
        timestamp: "2026-07-06T09:34:00.000Z",
        currency: "USD",
        asks: [{ price: "100.10", volume: "40" }],
        bids: [{ price: "99.90", volume: "160" }]
      },
      intradayCandles: {
        interval: "1m",
        nextBefore: null,
        candles: [
          createCandle("2026-07-06T09:30:00.000Z", "99", "100", "98", "99", "1000"),
          createCandle("2026-07-06T09:31:00.000Z", "101", "102", "100", "101", "1000"),
          createCandle("2026-07-06T09:32:00.000Z", "102", "103", "101", "102", "1000"),
          createCandle("2026-07-06T09:33:00.000Z", "103", "104", "102", "103", "1000")
        ]
      },
      dailyCandles: {
        interval: "1d",
        nextBefore: null,
        candles: createDailyCandles("100.00")
      }
    }
  };
}

function createStrongProfitTakingPressureSnapshot(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      price: {
        symbol: "MU",
        timestamp: "2026-07-06T09:49:00.000Z",
        lastPrice: "120.00",
        currency: "USD"
      },
      trades: [
        { price: "120.00", volume: "10", timestamp: "2026-07-06T09:45:00.000Z", currency: "USD" },
        { price: "119.00", volume: "30", timestamp: "2026-07-06T09:46:00.000Z", currency: "USD" },
        { price: "118.00", volume: "30", timestamp: "2026-07-06T09:47:00.000Z", currency: "USD" },
        { price: "117.50", volume: "30", timestamp: "2026-07-06T09:48:00.000Z", currency: "USD" }
      ],
      orderbook: {
        timestamp: "2026-07-06T09:49:00.000Z",
        currency: "USD",
        asks: [{ price: "120.10", volume: "220" }],
        bids: [{ price: "119.90", volume: "20" }]
      },
      intradayCandles: {
        interval: "1m",
        nextBefore: null,
        candles: Array.from({ length: 20 }, (_value, index) => {
          const close = 100 + index;

          return createCandle(
            `2026-07-06T09:${String(30 + index).padStart(2, "0")}:00.000Z`,
            close.toFixed(2),
            (close + 1).toFixed(2),
            (close - 1).toFixed(2),
            close.toFixed(2),
            "1000"
          );
        })
      },
      dailyCandles: {
        interval: "1d",
        nextBefore: null,
        candles: createDailyCandles("120.00")
      }
    }
  };
}

function createProfitTakingPressureWithoutFlowSnapshot(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      trades: [],
      orderbook: null
    }
  };
}

function createExpandedDeterministicMarketDataSnapshot(): Record<string, unknown> {
  const snapshot = createCompleteMarketDataSnapshot();

  return {
    ...snapshot,
    capturedAt: "2026-07-06T09:50:00.000Z",
    observations: {
      ...(snapshot.observations as Record<string, unknown>),
      price: {
        symbol: "MU",
        timestamp: "2026-07-06T09:49:00.000Z",
        lastPrice: "119.00",
        currency: "USD"
      },
      trades: [
        { price: "116.00", volume: "10", timestamp: "2026-07-06T09:45:00.000Z", currency: "USD" },
        { price: "117.00", volume: "20", timestamp: "2026-07-06T09:46:00.000Z", currency: "USD" },
        { price: "116.50", volume: "5", timestamp: "2026-07-06T09:47:00.000Z", currency: "USD" },
        { price: "118.00", volume: "30", timestamp: "2026-07-06T09:48:00.000Z", currency: "USD" }
      ],
      orderbook: {
        timestamp: "2026-07-06T09:49:00.000Z",
        currency: "USD",
        asks: [{ price: "119.10", volume: "100" }],
        bids: [{ price: "118.90", volume: "120" }]
      },
      intradayCandles: {
        interval: "1m",
        nextBefore: null,
        candles: Array.from({ length: 20 }, (_value, index) => {
          const close = 100 + index;

          return createCandle(
            `2026-07-06T09:${String(30 + index).padStart(2, "0")}:00.000Z`,
            close.toFixed(2),
            (close + 1).toFixed(2),
            (close - 1).toFixed(2),
            close.toFixed(2),
            "1000"
          );
        })
      },
      dailyCandles: {
        interval: "1d",
        nextBefore: null,
        candles: createDailyCandles("119.00")
      }
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
