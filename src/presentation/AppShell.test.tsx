import {
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type { MarketStateClient } from "../infrastructure/neutralino/NeutralinoMarketStateClient";
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { StockReferenceClient } from "../infrastructure/neutralino/NeutralinoStockReferenceClient";
import type {
  MarketDataSnapshotPayload,
  MarketStateFormulaSnapshotPayload,
  MarketStateHistoryPayload,
  MarketStateLatestSnapshotsPayload,
  MarketStateRefreshPayload,
  MarketStateSignalId,
  MarketStateSignalPayload,
  MarketStateTracePayload,
  MarketStateTraceResponsePayload,
  QuantIndicatorSnapshotPayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";
import { AppShell } from "./AppShell";
import { StartupStateView } from "./StartupStateView";
import { useQuantIndicators } from "./useQuantIndicators";

const runtimeProfile: RuntimeProfileDto = {
  runtimeMode: "desktop",
  marketDataMode: "notConfigured",
  capabilities: [
    {
      name: "watchlist",
      enabled: true,
      reason: "관심종목 목록 기능 준비됨"
    },
    {
      name: "quantIndicators",
      enabled: true,
      reason: "정량 지표 계산 준비됨"
    }
  ]
};

const emptyWatchlist = {
  activeCards: [],
  hiddenCards: [],
  archivedCards: []
};

const sampleCard: WatchStockCardDto = {
  id: "card-1",
  market: "NASDAQ",
  symbol: "MU",
  displayName: "MU 마이크론",
  groupId: null,
  tags: ["반도체"],
  memo: "VWAP 중심 관찰",
  sortOrder: 1,
  lifecycleStatus: "active",
  createdAt: "2026-07-06T09:00:00.000Z",
  updatedAt: "2026-07-06T09:00:00.000Z"
};

const riskCard: WatchStockCardDto = {
  id: "card-2",
  market: "NASDAQ",
  symbol: "AMD",
  displayName: "AMD",
  groupId: "AI",
  tags: ["AI"],
  memo: "손익비 재확인",
  sortOrder: 2,
  lifecycleStatus: "active",
  createdAt: "2026-07-06T09:00:00.000Z",
  updatedAt: "2026-07-06T09:00:00.000Z"
};

const sampleActiveCards = [sampleCard];

const marketStateSignalIds: readonly MarketStateSignalId[] = [
  "FOMO_LIKE",
  "PANIC_LIKE",
  "PROFIT_TAKING_PROXY",
  "PERSISTENT_RECOVERY",
  "EFFICIENT_UPTREND"
];

const marketStateSignalNames: Record<MarketStateSignalId, string> = {
  FOMO_LIKE: "FOMO",
  PANIC_LIKE: "패닉",
  PROFIT_TAKING_PROXY: "차익실현",
  PERSISTENT_RECOVERY: "회복",
  EFFICIENT_UPTREND: "상승세"
};

const sampleMarketStateSignals: MarketStateSignalPayload[] =
  marketStateSignalIds.map(
    (
      signalId: MarketStateSignalId,
      index: number
    ): MarketStateSignalPayload => ({
      signalId,
      displayName: marketStateSignalNames[signalId],
      formationLabel: `${marketStateSignalNames[signalId]} 형성`,
      horizonMinutes: 30,
      status: index === 0 ? "detected" : "notDetected",
      percentile: 93.4 - index * 8,
      percentileNumerator: 934 - index * 80,
      percentileDenominator: 1_000,
      rawScore: 1.32 - index * 0.15,
      dynamicThreshold: 1.1,
      thresholdDistance: 0.22 - index * 0.15,
      gate:
        signalId === "FOMO_LIKE"
          ? {
              gateId: "POSITIVE_PRESSURE_MEAN_3",
              label: "최근 3개 봉 매수 압력",
              value: 0.42,
              operator: ">",
              threshold: 0,
              passed: true
            }
          : null,
      requiredRiskState: "BASELINE",
      currentRiskState: "BASELINE",
      currentDetectionStartedAt:
        signalId === "FOMO_LIKE"
          ? "2026-07-31T14:00:00.000Z"
          : null,
      lastDetectedAt:
        signalId === "FOMO_LIKE"
          ? "2026-07-31T14:00:00.000Z"
          : null,
      trace:
        signalId === "FOMO_LIKE"
          ? {
              intercept: -0.18,
              contributions: [
                {
                  featureName: "ret_6",
                  rawValue: 0.021,
                  mean: 0.001,
                  scale: 0.01,
                  standardizedValue: 2,
                  coefficient: 0.75,
                  contribution: 1.5
                },
                {
                  featureName: "relative_volume",
                  rawValue: 1.8,
                  mean: 1,
                  scale: 0.4,
                  standardizedValue: 2,
                  coefficient: 0.31,
                  contribution: 0.62
                }
              ],
              effectiveTailShare: 0.08,
              calibrationTailShare: 0.1,
              transportTailSafetyFactor: 0.8,
              candidateId: "fomo-v3",
              cause: "fast-upside-demand",
              phenotypeTag: "fomo-like"
            }
          : null
    })
  );

const sampleMarketStateSnapshot: MarketStateFormulaSnapshotPayload = {
  snapshotId: "market-state-1",
  cardId: "card-1",
  symbol: "MU",
  sessionDate: "2026-07-31",
  asOf: "2026-07-31T14:05:00.000Z",
  bucketIndex: 6,
  sourceGenerationId: "generation-1",
  formulaVersion: "a".repeat(64),
  formulaContentSha256: "b".repeat(64),
  observedState: "BASELINE",
  observedStateLabel: "방향성 확인 전",
  signals: sampleMarketStateSignals,
  notifiedSignalIds: ["FOMO_LIKE"]
};

const sampleMarketStateTrace: MarketStateTracePayload = {
  ...sampleMarketStateSignals[0],
  cardId: "card-1",
  symbol: "MU",
  sessionDate: "2026-07-31",
  asOf: "2026-07-31T14:05:00.000Z",
  sourceGenerationId: "generation-1",
  formulaVersion: "a".repeat(64),
  formulaContentSha256: "b".repeat(64),
  observedState: "BASELINE",
  observedStateLabel: "방향성 확인 전"
};

const sampleMarketStateHistory: MarketStateHistoryPayload = {
  cardId: "card-1",
  signalId: "FOMO_LIKE",
  sessionDate: "2026-07-31",
  points: Array.from(
    { length: 13 },
    (_: unknown, index: number) => ({
      asOf: `2026-07-31T14:${String(index * 5).padStart(2, "0")}:00.000Z`,
      bucketIndex: index,
      status: index >= 11 ? "detected" : "notDetected",
      percentile: 45 + index * 4,
      rawScore: 0.2 + index * 0.1,
      dynamicThreshold: 1.1,
      detected: index >= 11
    })
  )
};

const sampleMarketDataSnapshot: MarketDataSnapshotPayload = {
  snapshotId: "snapshot-1",
  cardId: "card-1",
  market: "NASDAQ",
  symbol: "MU",
  capturedAt: "2026-07-06T09:00:05.000Z",
  freshness: "fresh",
  quality: "complete",
  observations: {
    price: {
      symbol: "MU",
      timestamp: "2026-07-06T09:00:00.000Z",
      lastPrice: "194.93",
      currency: "USD"
    },
    trades: [
      {
        price: "194.93",
        volume: "10",
        timestamp: "2026-07-06T09:00:00.000Z",
        currency: "USD"
      }
    ],
    orderbook: {
      timestamp: "2026-07-06T09:00:00.000Z",
      currency: "USD",
      asks: [{ price: "195.00", volume: "100" }],
      bids: [{ price: "194.90", volume: "120" }]
    },
    intradayCandles: null,
    dailyCandles: null,
    exchangeRate: null,
    marketSession: {
      country: "US",
      state: "regular",
      source: "calendar"
    }
  },
  adapterErrors: []
};

const sampleQuantIndicatorSnapshot: QuantIndicatorSnapshotPayload = {
  snapshotId: "quant-1",
  sourceMarketDataSnapshotId: "snapshot-1",
  cardId: "card-1",
  market: "NASDAQ",
  symbol: "MU",
  calculatedAt: "2026-07-06T09:00:06.000Z",
  quality: "complete",
  decisionStatus: "watch",
  decisionLabel: "관망",
  nextCheckLabel: "VWAP 위 안착 유지 확인",
  indicators: {
    basicReturn: {
      status: "available",
      currentPrice: "194.93",
      referencePrice: "190.00",
      absoluteChange: "4.9300",
      simpleReturnPercent: 2.59,
      logReturnPercent: 2.56,
      currency: "USD",
      referenceLabel: "전일 종가",
      label: "전일 종가 대비 상승",
      severity: "positive",
      unavailableReason: null
    },
    vwap: {
      status: "available",
      value: "101.7500",
      distanceBps: 172,
      label: "VWAP 위 안착",
      severity: "positive",
      unavailableReason: null
    },
    cvd: {
      status: "estimated",
      value: "45",
      confidence: "estimated",
      label: "체결 압력 우위",
      severity: "positive",
      unavailableReason: null
    },
    spread: {
      status: "available",
      spreadBps: 19,
      label: "스프레드 정상",
      severity: "positive",
      unavailableReason: null
    },
    atrStop: {
      status: "available",
      atr: "1.0000",
      stopDistancePercent: 0.97,
      label: "손절 폭 정상",
      severity: "positive",
      unavailableReason: null
    },
    supplyPressure: {
      status: "available",
      pocPrice: "102.0000",
      overheadRatio: 0,
      label: "매물대 부담 낮음",
      severity: "positive",
      unavailableReason: null
    },
    profitTakingPressure: {
      status: "available",
      profitLongRatio: 0.75,
      weightedProfitPressure: 0.02,
      vwapAtrExtension: 1,
      sellFlowPressure: 0,
      askBookPressure: 0,
      volumeExpansion: 0.67,
      score: 42,
      causes: {
        profitBurden: {
          status: "available",
          score: 74,
          label: "수익권 부담 높음",
          severity: "warning",
          reason: "수익권 물량과 VWAP/ATR 이격이 함께 큽니다."
        },
        realizedSellPressure: {
          status: "estimated",
          score: 18,
          label: "실제 매도 압력 낮음",
          severity: "positive",
          reason: "최근 체결 방향과 호가 잔량으로 추정합니다."
        },
        overheadSupplyPressure: {
          status: "available",
          score: 31,
          label: "위쪽 매물 부담 보통",
          severity: "neutral",
          reason: "현재가 위 거래량 부담을 ATR 기준으로 봅니다."
        },
        liquidityImpactRisk: {
          status: "available",
          score: 45,
          label: "체결 환경 위험 경계",
          severity: "warning",
          reason: "스프레드, 호가 깊이, 최근 가격충격으로 추정합니다."
        }
      },
      label: "차익실현 리스크 경계",
      severity: "warning",
      unavailableReason: null
    },
    riskReward: {
      status: "available",
      ratio: 4.5,
      label: "손익비 1.5x 이상",
      severity: "positive",
      unavailableReason: null
    },
    velocityAcceleration: {
      status: "available",
      latestLogReturnPercent: 0.84,
      priceAccelerationPercent: -0.01,
      volumeChangePercent: 0,
      estimatedCvdChange: "5",
      label: "상승 속도 둔화",
      severity: "warning",
      unavailableReason: null
    },
    distanceProfile: {
      status: "available",
      vwapDistanceBps: 172,
      movingAverageDistanceBps: 96,
      atrMultipleFromPreviousClose: 0.8,
      label: "상방 이격",
      severity: "positive",
      unavailableReason: null
    },
    rsiMomentum: {
      status: "available",
      rsi: 58.25,
      momentumPercent: 1.2,
      label: "모멘텀 양호",
      severity: "positive",
      unavailableReason: null
    },
    marketSentimentScore: {
      status: "available",
      score: 82,
      label: "정량 심리 우호",
      severity: "positive",
      unavailableReason: null
    },
    intradayTradeScore: {
      status: "available",
      conditionStrengthPercent: 96.08,
      label: "조건 충족 강함",
      severity: "positive",
      unavailableReason: null
    }
  },
  signals: [
    {
      key: "vwap",
      label: "VWAP 위 안착",
      severity: "positive",
      status: "available",
      reason: null
    },
    {
      key: "cvd",
      label: "체결 압력 우위",
      severity: "positive",
      status: "estimated",
      reason: "Toss 체결 데이터에 aggressor side가 없어 tick-rule로 추정합니다."
    },
    {
      key: "profitTakingPressure",
      label: "차익실현 리스크 경계",
      severity: "warning",
      status: "available",
      reason: null
    }
  ],
  explanationTraces: [
    {
      key: "basicReturn",
      title: "기본 수익률",
      source: "현재가와 전일 종가",
      originalFormula: [
        "단순 수익률 = 현재가 / 기준가 - 1",
        "로그 수익률 = ln(현재가 / 기준가)"
      ],
      substitutedFormula: [
        "단순 수익률 = 194.93 / 190.00 - 1",
        "로그 수익률 = ln(194.93 / 190.00)"
      ],
      result: ["단순 수익률 = +2.59%", "로그 수익률 = +2.56%"],
      inputs: [
        { label: "현재가", value: "$194.93" },
        { label: "기준가", value: "$190.00" }
      ],
      meaning: "가격이 기준 시점보다 얼마나 움직였는지 보는 가장 기본 지표입니다.",
      usage: "손절, 익절, 포지션 크기 판단의 출발점으로 사용합니다.",
      judgment: "현재가는 전일 종가보다 위에 있습니다.",
      caution: "단순 수익률은 여러 구간을 그냥 더하면 누적 수익률과 달라집니다.",
      limitation: null
    },
    {
      key: "cvd",
      title: "CVD 추정",
      source: "최근 체결 내역",
      originalFormula: ["tick-rule CVD = Σ(가격 상승 체결량 - 가격 하락 체결량)"],
      substitutedFormula: ["tick-rule CVD = +20 - 5 + 30"],
      result: ["CVD 추정값 = 45"],
      inputs: [{ label: "체결 방향", value: "tick-rule 추정" }],
      meaning: "최근 체결이 어느 방향으로 기울었는지 참고합니다.",
      usage: "VWAP 재돌파나 이탈 판단에서 체결 압력 회복 여부를 함께 봅니다.",
      judgment: "체결 압력 우위",
      caution: "정확한 매수·매도 주체가 아니라 방향 참고용입니다.",
      limitation: "Toss 체결 데이터에 aggressor side가 없어 tick-rule 기반 추정값입니다."
    },
    {
      key: "velocityAcceleration",
      title: "속도/가속도",
      source: "최근 1분봉 종가와 거래량",
      originalFormula: ["가격 속도 = ln(현재 종가 / 직전 종가) × 100"],
      substitutedFormula: ["가격 속도 = ln(119.00 / 118.00) × 100"],
      result: ["가격 속도 = +0.84%"],
      inputs: [{ label: "최근 종가", value: "119.00" }],
      meaning: "가격 변화가 빨라지는지 느려지는지 확인합니다.",
      usage: "단기 추세가 유지되는지 확인할 때 봅니다.",
      judgment: "상승 속도 둔화",
      caution: "짧은 구간의 속도는 노이즈가 큽니다.",
      limitation: null
    },
    {
      key: "profitTakingPressure",
      title: "차익실현 리스크",
      source: "당일 1분봉 거래량 분포, VWAP, ATR, 체결 방향 추정, 호가 잔량",
      originalFormula: [
        "차익실현 리스크 = 0.35×수익권 부담 + 0.30×실제 매도 압력 + 0.25×위쪽 매물 부담 + 0.10×체결 환경 위험"
      ],
      substitutedFormula: [
        "점수 = 0.35×74 + 0.30×18 + 0.25×31 + 0.10×45"
      ],
      result: [
        "차익실현 리스크 = 42점",
        "수익권 부담 = 74점",
        "실제 매도 압력 = 18점",
        "위쪽 매물 부담 = 31점",
        "체결 환경 위험 = 45점"
      ],
      inputs: [
        { label: "수익권 물량 비율", value: "0.75" },
        { label: "VWAP/ATR 이격", value: "1.00" }
      ],
      meaning: "수익권 물량, 실제 매도 압력, 위쪽 매물 부담, 체결 환경을 나눠 보는 내부 추정 지표입니다.",
      usage: "점수 하나보다 어떤 원인이 리스크를 키우는지 확인합니다.",
      judgment: "차익실현 리스크 경계",
      caution: "표준 공식명이 아니며 매수·매도 추천으로 해석하지 않습니다.",
      limitation: "표준 공식명이 아니라 앱 내부 추정 지표이며 실제 보유자 원가나 매도 의도를 알 수 없습니다."
    }
  ]
};

const riskQuantIndicatorSnapshot: QuantIndicatorSnapshotPayload = {
  ...sampleQuantIndicatorSnapshot,
  snapshotId: "quant-2",
  sourceMarketDataSnapshotId: "snapshot-2",
  cardId: "card-2",
  symbol: "AMD",
  decisionStatus: "riskHigh",
  decisionLabel: "리스크 높음",
  nextCheckLabel: "손절 폭과 매물대 부담 재확인",
  indicators: {
    ...sampleQuantIndicatorSnapshot.indicators,
    spread: {
      status: "available",
      spreadBps: 88,
      label: "스프레드 위험",
      severity: "danger",
      unavailableReason: null
    },
    riskReward: {
      status: "available",
      ratio: 0.8,
      label: "손익비 1.5x 미달",
      severity: "danger",
      unavailableReason: null
    }
  },
  signals: [
    {
      key: "spread",
      label: "스프레드 위험",
      severity: "danger",
      status: "available",
      reason: null
    },
    {
      key: "riskReward",
      label: "손익비 1.5x 미달",
      severity: "danger",
      status: "available",
      reason: null
    }
  ]
};

function createWatchlistClient(
  cards: WatchStockCardDto[] = [],
  hiddenCards: WatchStockCardDto[] = [],
  archivedCards: WatchStockCardDto[] = []
) {
  let activeCards = [...cards];

  return {
    list: async () => ({
      activeCards,
      hiddenCards,
      archivedCards
    }),
    create: async () => {
      activeCards = [sampleCard];

      return {
        type: "created" as const,
        card: sampleCard,
        watchlist: {
          activeCards,
          hiddenCards: [],
          archivedCards: []
        }
      };
    },
    update: async () => ({ card: sampleCard, watchlist: emptyWatchlist }),
    hide: async () => ({ card: sampleCard, watchlist: emptyWatchlist }),
    archive: async () => ({ card: sampleCard, watchlist: emptyWatchlist }),
    restore: async () => ({ card: sampleCard, watchlist: emptyWatchlist }),
    delete: async () => emptyWatchlist,
    reorder: async () => emptyWatchlist
  };
}

function createMarketDataClient(
  overrides: Partial<MarketDataClient> = {}
): MarketDataClient {
  return {
    refreshWatchlist:
      overrides.refreshWatchlist ??
      vi.fn(async () => ({
        refreshedAt: "2026-07-06T09:00:05.000Z",
        nextPollDelayMs: 15_000,
        snapshots: [sampleMarketDataSnapshot]
      })),
    refreshCard:
      overrides.refreshCard ??
      vi.fn(async () => ({
        refreshedAt: "2026-07-06T09:00:05.000Z",
        nextPollDelayMs: 15_000,
        snapshot: sampleMarketDataSnapshot
      })),
    readLatestSnapshots:
      overrides.readLatestSnapshots ??
      vi.fn(async () => ({
        snapshots: [sampleMarketDataSnapshot]
      }))
  };
}

function createMarketStateClient(
  overrides: Partial<MarketStateClient> = {}
): MarketStateClient {
  return {
    refreshWatchlist:
      overrides.refreshWatchlist ??
      vi.fn(
        async (): Promise<MarketStateRefreshPayload> => ({
          refreshedAt: "2026-07-31T14:05:01.000Z",
          snapshots: [sampleMarketStateSnapshot],
          backfillProgress: {
            jobId: "market-state-backfill-1",
            status: "complete",
            requiredSessions: 60,
            completedSessions: 60,
            currentInstrumentId: null,
            totalInstrumentCount: 34,
            completedInstrumentCount: 34,
            error: null
          }
        })
      ),
    readLatestSnapshots:
      overrides.readLatestSnapshots ??
      vi.fn(
        async (): Promise<MarketStateLatestSnapshotsPayload> => ({
          snapshots: [sampleMarketStateSnapshot],
          backfillProgress: {
            jobId: "market-state-backfill-1",
            status: "complete",
            requiredSessions: 60,
            completedSessions: 60,
            currentInstrumentId: null,
            totalInstrumentCount: 34,
            completedInstrumentCount: 34,
            error: null
          }
        })
      ),
    readTrace:
      overrides.readTrace ??
      vi.fn(
        async (): Promise<MarketStateTraceResponsePayload> => ({
          trace: sampleMarketStateTrace
        })
      ),
    readHistory:
      overrides.readHistory ??
      vi.fn(
        async (): Promise<MarketStateHistoryPayload> =>
          sampleMarketStateHistory
      )
  };
}

function createQuantIndicatorClient(
  overrides: Partial<QuantIndicatorClient> = {}
): QuantIndicatorClient {
  return {
    refreshWatchlist:
      overrides.refreshWatchlist ??
      vi.fn(async () => ({
        refreshedAt: "2026-07-06T09:00:06.000Z",
        snapshots: [sampleQuantIndicatorSnapshot]
      })),
    refreshCard:
      overrides.refreshCard ??
      vi.fn(async () => ({
        refreshedAt: "2026-07-06T09:00:06.000Z",
        snapshot: sampleQuantIndicatorSnapshot
      })),
    readLatestSnapshots:
      overrides.readLatestSnapshots ??
      vi.fn(async () => ({
        snapshots: [sampleQuantIndicatorSnapshot]
      }))
  };
}

function createStockReferenceClient(
  overrides: Partial<StockReferenceClient> = {}
): StockReferenceClient {
  const verify =
    overrides.verify ??
    vi.fn(async ({ rawInput }) => {
      if (rawInput.includes("ZZZZ")) {
        return {
          verified: [],
          rejected: [
            {
              symbol: "ZZZZZZZZZZZZ",
              reason: "stock_not_found" as const,
              message: "종목을 찾을 수 없습니다."
            }
          ]
        };
      }

      return {
        verified: [
          {
            symbol: "MU",
            market: "NASDAQ",
            displayName: "마이크론 테크놀로지",
            englishName: "Micron Technology",
            currency: "USD",
            status: "ACTIVE",
            securityType: "STOCK",
            requiresConfirmation: false,
            confirmationReasons: [],
            verifiedAt: "2026-07-06T09:00:00.000Z"
          }
        ],
        rejected: []
      };
    });
  const createVerifiedCard =
    overrides.createVerifiedCard ??
    vi.fn(async () => ({
      type: "created" as const,
      card: {
        ...sampleCard,
        displayName: "마이크론 테크놀로지",
        memo: "검증 카드"
      },
      watchlist: {
        activeCards: [
          {
            ...sampleCard,
            displayName: "마이크론 테크놀로지",
            memo: "검증 카드"
          }
        ],
        hiddenCards: [],
        archivedCards: []
      }
    }));

  return {
    verify,
    createVerifiedCard
  };
}

function createTossSettingsClient(status?: TossCredentialStatusPayload) {
  let currentStatus =
    status ?? {
      configured: false,
      maskedClientId: null,
      lastValidatedAt: null,
      connectionStatus: "notConfigured" as const
    };

  return {
    readStatus: async () => currentStatus,
    saveCredentials: async () => {
      currentStatus = {
        configured: true,
        maskedClientId: "clie…7890",
        lastValidatedAt: null,
        connectionStatus: "saved"
      };

      return currentStatus;
    },
    deleteCredentials: async () => {
      currentStatus = {
        configured: false,
        maskedClientId: null,
        lastValidatedAt: null,
        connectionStatus: "notConfigured"
      };

      return currentStatus;
    },
    testConnection: async () => {
      currentStatus = {
        configured: true,
        maskedClientId: "clie…7890",
        lastValidatedAt: "2026-07-06T09:00:00.000Z",
        connectionStatus: "valid"
      };

      return currentStatus;
    }
  };
}

function QuantIndicatorStateHarness({
  quantIndicatorClient,
  credentials
}: {
  quantIndicatorClient: QuantIndicatorClient;
  credentials: TossCredentialStatusPayload;
}) {
  const quantIndicators = useQuantIndicators(quantIndicatorClient, {
    activeCards: sampleActiveCards,
    credentials,
    marketDataStatus: "ready"
  });
  const score =
    quantIndicators.snapshotsByCardId["card-1"]?.indicators.profitTakingPressure.score ?? "--";

  return (
    <section aria-label="정량 지표 테스트 하네스">
      <p>{quantIndicators.status}</p>
      <p>{score}</p>
      <button type="button" onClick={() => void quantIndicators.refreshNow()}>
        정량 지표 다시 계산
      </button>
    </section>
  );
}

describe("StartupStateView", () => {
  it("shows the loading state while the runtime profile is requested", () => {
    render(<StartupStateView state={{ status: "loading" }} />);

    expect(screen.getByText("런타임 확인 중")).toBeVisible();
    expect(screen.getByText("앱 확장과 안전한 통신 경계를 준비하고 있습니다.")).toBeVisible();
  });

  it("shows a recoverable extension error state", () => {
    render(
      <StartupStateView
        state={{
          status: "error",
          message: "runtime extension is unavailable",
          recoverable: true
        }}
      />
    );

    expect(screen.getByText("시작할 수 없습니다")).toBeVisible();
    expect(screen.getByText("runtime extension is unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeVisible();
  });
});

describe("AppShell", () => {
  const validTossCredentialStatus: TossCredentialStatusPayload = {
    configured: true,
    maskedClientId: "clie…7890",
    lastValidatedAt: "2026-07-06T09:00:00.000Z",
    connectionStatus: "valid"
  };

  it("renders an empty watchlist-ready desktop shell", () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient()}
      />
    );

    expect(
      screen.getByRole("heading", { name: "관심종목 분석 대기" })
    ).toBeVisible();
    expect(screen.getByText("토스 차트 옆에서 볼 분석 카드를 준비합니다.")).toBeVisible();
    expect(screen.getByText("watchlist")).toBeVisible();
    expect(screen.getByText("quantIndicators")).toBeVisible();
    expect(screen.getAllByText("준비됨")).toHaveLength(2);
    expect(screen.queryByText("대기")).not.toBeInTheDocument();
  });

  it("opens Toss settings and saves masked credential status", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "설정" }));
    fireEvent.change(screen.getByLabelText("Toss API Key"), {
      target: { value: "client_fixture_1234567890" }
    });
    fireEvent.change(screen.getByLabelText("Toss Secret Key"), {
      target: { value: "secret_fixture_super_secret" }
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(screen.getByText("clie…7890")).toBeVisible();
    });
    expect(screen.queryByText("secret_fixture_super_secret")).not.toBeInTheDocument();
  });

  it("renders a compact single-ticker add form", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    await waitFor(() => {
      expect(screen.getByLabelText("시장")).toHaveValue("NASDAQ");
    });

    expect(screen.getByLabelText("티커")).toBeVisible();
    expect(screen.getByRole("button", { name: "추가" })).toBeVisible();
    expect(screen.queryByLabelText("심볼 붙여넣기")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "심볼 검증" })).not.toBeInTheDocument();
  });

  it("creates a visible analysis card from one ticker", async () => {
    const stockReferenceClient = createStockReferenceClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={stockReferenceClient}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "추가" })).toBeEnabled();
    });
    fireEvent.change(screen.getByLabelText("티커"), {
      target: { value: "MU" }
    });
    fireEvent.change(screen.getByLabelText("태그"), {
      target: { value: "반도체" }
    });
    fireEvent.change(screen.getByLabelText("메모"), {
      target: { value: "검증 카드" }
    });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      expect(stockReferenceClient.verify).toHaveBeenCalledWith({ rawInput: "MU" });
    });
    expect(stockReferenceClient.createVerifiedCard).toHaveBeenCalledWith({
      symbol: "MU",
      confirmedRisk: false,
      groupId: null,
      tags: ["반도체"],
      memo: "검증 카드"
    });
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "마이크론 테크놀로지" })).toBeVisible();
    });
    expect(screen.getByText("NASDAQ · MU")).toBeVisible();
    expect(screen.getByText("검증 카드")).toBeVisible();
  });

  it("shows rejected stock symbols without a card creation action", async () => {
    const stockReferenceClient = createStockReferenceClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={stockReferenceClient}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "추가" })).toBeEnabled();
    });
    fireEvent.change(screen.getByLabelText("티커"), {
      target: { value: "ZZZZZZZZZZZZ" }
    });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      expect(screen.getByText("종목을 찾을 수 없습니다.")).toBeVisible();
    });
    expect(stockReferenceClient.createVerifiedCard).not.toHaveBeenCalled();
  });

  it("asks for confirmation when the selected market differs from Toss stock info", async () => {
    const stockReferenceClient = createStockReferenceClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        stockReferenceClient={stockReferenceClient}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    await waitFor(() => {
      expect(screen.getByLabelText("시장")).toBeVisible();
    });
    fireEvent.change(screen.getByLabelText("시장"), {
      target: { value: "NYSE" }
    });
    fireEvent.change(screen.getByLabelText("티커"), {
      target: { value: "MU" }
    });
    fireEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      expect(screen.getByText("MU는 NASDAQ 종목입니다.")).toBeVisible();
    });
    expect(stockReferenceClient.createVerifiedCard).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "NASDAQ으로 추가" }));

    await waitFor(() => {
      expect(stockReferenceClient.createVerifiedCard).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: "MU",
          confirmedRisk: false
        })
      );
    });
  });

  it("polls market data for active cards and renders only freshness status", async () => {
    const marketDataClient = createMarketDataClient();
    const quantIndicatorClient = createQuantIndicatorClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={marketDataClient}
        quantIndicatorClient={quantIndicatorClient}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(marketDataClient.refreshWatchlist).toHaveBeenCalledWith({
        visibleCardIds: ["card-1"]
      });
    });
    expect(screen.getByText("업데이트 09:00:05")).toBeVisible();
    expect(screen.getAllByText("$194.93")[0]).toBeVisible();
    expect(screen.queryByText("195.00")).not.toBeInTheDocument();
    expect(screen.queryByText("100")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(quantIndicatorClient.refreshWatchlist).toHaveBeenCalledWith({
        cardIds: ["card-1"]
      });
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
    });
    expect(screen.getAllByText("+$4.93")[0]).toBeVisible();
    expect(screen.getAllByText("+2.59%")[0]).toBeVisible();
    expect(screen.getAllByText("관망").some((element) => element.tagName === "SPAN")).toBe(true);
    expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
    expect(screen.getByText("VWAP 위 안착 ($101.75)")).toBeVisible();
    expect(screen.getByText("체결 압력 우위 (45)")).toBeVisible();
    expect(
      screen.queryByText("차익실현 리스크 경계 (42점)")
    ).not.toBeInTheDocument();
    expect(screen.queryByText("101.7500")).not.toBeInTheDocument();
  });

  it("shows all five market-state signals while the first calculation is collecting", async () => {
    let resolveQuantRefresh: (
      value: Awaited<ReturnType<QuantIndicatorClient["refreshWatchlist"]>>
    ) => void = () => undefined;
    const pendingQuantRefresh = new Promise<
      Awaited<ReturnType<QuantIndicatorClient["refreshWatchlist"]>>
    >((resolve) => {
      resolveQuantRefresh = resolve;
    });
    const quantIndicatorClient = createQuantIndicatorClient({
      refreshWatchlist: vi.fn(() => pendingQuantRefresh)
    });

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={quantIndicatorClient}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(quantIndicatorClient.refreshWatchlist).toHaveBeenCalledWith({
        cardIds: ["card-1"]
      });
    });

    expect(screen.getByText("계산 중")).toBeVisible();
    const signalRegion: HTMLElement = screen.getByRole("region", {
      name: "MU 심리·시장 신호"
    });
    expect(within(signalRegion).getAllByRole("button")).toHaveLength(5);
    expect(
      within(signalRegion).getByRole("button", {
        name: "FOMO — 수집 중 상세"
      })
    ).toBeVisible();
    expect(
      within(signalRegion).getByRole("button", {
        name: "패닉 — 수집 중 상세"
      })
    ).toBeVisible();
    expect(
      within(signalRegion).getByRole("button", {
        name: "차익실현 — 수집 중 상세"
      })
    ).toBeVisible();
    expect(
      within(signalRegion).getByRole("button", {
        name: "회복 — 수집 중 상세"
      })
    ).toBeVisible();
    expect(
      within(signalRegion).getByRole("button", {
        name: "상승세 — 수집 중 상세"
      })
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));
    expect(
      within(
        screen.getByRole("tablist", { name: "시장상태 신호 선택" })
      ).getAllByRole("tab")
    ).toHaveLength(5);

    resolveQuantRefresh({
      refreshedAt: "2026-07-06T09:00:06.000Z",
      snapshots: [sampleQuantIndicatorSnapshot]
    });

    await waitFor(() => {
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
    });
  });

  it("keeps the previous quant snapshot when a later refresh fails", async () => {
    let rejectSecondRefresh: (reason?: unknown) => void = () => undefined;
    const secondRefresh = new Promise<
      Awaited<ReturnType<QuantIndicatorClient["refreshWatchlist"]>>
    >((_, reject) => {
      rejectSecondRefresh = reject;
    });
    const quantIndicatorClient = createQuantIndicatorClient({
      refreshWatchlist: vi.fn()
        .mockResolvedValueOnce({
          refreshedAt: "2026-07-06T09:00:06.000Z",
          snapshots: [sampleQuantIndicatorSnapshot]
        })
        .mockReturnValueOnce(secondRefresh)
    });

    render(
      <QuantIndicatorStateHarness
        quantIndicatorClient={quantIndicatorClient}
        credentials={validTossCredentialStatus}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("ready")).toBeVisible();
      expect(screen.getByText("42")).toBeVisible();
    });

    fireEvent.click(screen.getByRole("button", { name: "정량 지표 다시 계산" }));
    expect(screen.getByText("refreshing")).toBeVisible();

    rejectSecondRefresh(new Error("정량 지표 계산 지연"));
    await waitFor(() => {
      expect(screen.getByText("failedRefresh")).toBeVisible();
      expect(screen.getByText("42")).toBeVisible();
    });
  });

  it("does not add value parentheses when a signal has no calculated final value", async () => {
    const unavailableVwapSnapshot: QuantIndicatorSnapshotPayload = {
      ...sampleQuantIndicatorSnapshot,
      indicators: {
        ...sampleQuantIndicatorSnapshot.indicators,
        vwap: {
          status: "unavailable",
          value: null,
          distanceBps: null,
          label: "VWAP 계산 불가",
          severity: "unavailable",
          unavailableReason: "1분봉이 부족합니다."
        }
      },
      signals: [
        {
          key: "vwap",
          label: "VWAP 계산 불가",
          severity: "unavailable",
          status: "unavailable",
          reason: "1분봉이 부족합니다."
        }
      ]
    };

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient({
          refreshWatchlist: vi.fn(async () => ({
            refreshedAt: "2026-07-06T09:00:06.000Z",
            snapshots: [unavailableVwapSnapshot]
          }))
        })}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("VWAP 계산 불가")).toBeVisible();
    });
    expect(screen.queryByText("VWAP 계산 불가 ()")).not.toBeInTheDocument();
    expect(screen.queryByText(/VWAP 계산 불가 \(.+\)/)).not.toBeInTheDocument();
  });

  it("does not start market data polling when Toss credentials are not configured", async () => {
    const marketDataClient = createMarketDataClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={marketDataClient}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient()}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "MU 마이크론" })).toBeVisible();
    });
    expect(marketDataClient.refreshWatchlist).not.toHaveBeenCalled();
  });

  it("filters the dashboard by quant status and lightweight card group", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([
          { ...sampleCard, groupId: "반도체" },
          riskCard
        ])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient({
          refreshWatchlist: vi.fn(async () => ({
            refreshedAt: "2026-07-06T09:00:06.000Z",
            snapshots: [
              { ...sampleQuantIndicatorSnapshot, cardId: "card-1" },
              riskQuantIndicatorSnapshot
            ]
          }))
        })}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "MU 마이크론" })).toBeVisible();
      expect(screen.getByRole("heading", { name: "AMD" })).toBeVisible();
      expect(screen.getByText("손익비 1.5x 미달 (0.80x)")).toBeVisible();
    });

    fireEvent.click(screen.getByRole("button", { name: "리스크 높음" }));

    expect(screen.queryByRole("heading", { name: "MU 마이크론" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AMD" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "반도체" }));

    expect(screen.getByRole("heading", { name: "MU 마이크론" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "AMD" })).not.toBeInTheDocument();
  });

  it("opens a right detail panel with checklist, conditional zones, data quality, and stale AI placeholder", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "MU 마이크론" })).toBeVisible();
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));

    expect(screen.getByRole("complementary", { name: "MU 상세 분석" })).toBeVisible();
    expect(screen.getByText("진입 전 체크")).toBeVisible();
    expect(screen.getByText("조건부 구간")).toBeVisible();
    expect(screen.getByText("데이터 품질")).toBeVisible();
    expect(screen.getAllByText("$194.93")[0]).toBeVisible();
    expect(screen.getAllByText("+$4.93")[0]).toBeVisible();
    expect(screen.getAllByText("+2.59%")[0]).toBeVisible();
    expect(screen.getAllByText("VWAP 위 안착 ($101.75)")).toHaveLength(2);
    expect(screen.getAllByText("체결 압력 우위 (45)")).toHaveLength(2);
    expect(screen.getByText("스프레드 정상 (19bp)")).toBeVisible();
    expect(screen.getByText("상승 속도 둔화 (+0.84%)")).toBeVisible();
    expect(screen.getByText("상방 이격 (172bp)")).toBeVisible();
    expect(screen.getByText("모멘텀 양호 (58.25)")).toBeVisible();
    expect(screen.getByText("손절 폭 정상 (0.97%)")).toBeVisible();
    expect(screen.queryByText("매물대 부담 낮음 (0.00)")).not.toBeInTheDocument();
    expect(screen.queryByText("차익실현 리스크 경계 (42점)")).not.toBeInTheDocument();
    expect(
      within(
        screen.getByRole("tablist", { name: "시장상태 신호 선택" })
      ).getAllByRole("tab")
    ).toHaveLength(5);
    expect(
      screen.getByRole("tab", { name: "차익실현—수집 중" })
    ).toBeVisible();
    expect(screen.getByText("손익비 1.5x 이상 (4.50x)")).toBeVisible();
    expect(screen.getByText("정량 심리 우호 (82점)")).toBeVisible();
    expect(screen.getByText("조건 충족 강함 (96.08%)")).toBeVisible();
    expect(screen.getByText("AI 분석 대기")).toBeVisible();
    expect(screen.getByRole("button", { name: "AI 분석은 Step 12에서 활성화" })).toBeDisabled();
  });

  it("opens beginner explanations only by clicking a help button", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
      expect(screen.getByRole("button", { name: "MU 마이크론 상세 보기" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));

    expect(screen.queryByRole("tab", { name: "초보자 설명" })).not.toBeInTheDocument();
    expect(screen.queryByText("지표 로드맵")).not.toBeInTheDocument();
    expect(screen.queryByText("원래 공식")).not.toBeInTheDocument();

    const helpButton = screen.getByRole("button", { name: "CVD 초보자 설명 보기" });
    fireEvent.mouseEnter(helpButton);

    expect(screen.queryByRole("tooltip", { name: "CVD 추정 설명" })).not.toBeInTheDocument();

    fireEvent.focus(helpButton);

    expect(screen.queryByRole("tooltip", { name: "CVD 추정 설명" })).not.toBeInTheDocument();

    fireEvent.click(helpButton);

    const helperPopup = screen.getByRole("tooltip", { name: "CVD 추정 설명" });
    expect(helperPopup).toBeVisible();
    expect(helperPopup).toHaveClass("indicator-explanation-popover--centered");
    expect(screen.getByText("원래 공식")).toBeVisible();
    expect(screen.getByText("tick-rule CVD = Σ(가격 상승 체결량 - 가격 하락 체결량)")).toBeVisible();
    expect(screen.getByText("현재 값 대입")).toBeVisible();
    expect(screen.getByText("tick-rule CVD = +20 - 5 + 30")).toBeVisible();
    expect(screen.getByText("Toss 체결 데이터에 aggressor side가 없어 tick-rule 기반 추정값입니다.")).toBeVisible();

    fireEvent.click(helpButton);

    expect(screen.queryByRole("tooltip", { name: "CVD 추정 설명" })).not.toBeInTheDocument();
  });

  it("shows the research formula trace, lineage, history, and interpretation limits", async () => {
    const marketStateClient: MarketStateClient =
      createMarketStateClient();

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        marketStateClient={marketStateClient}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
      expect(
        screen.getByRole("button", {
          name: "FOMO 93.4 감지 상세"
        })
      ).toBeVisible();
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "FOMO 93.4 감지 상세"
      })
    );

    await waitFor(() => {
      expect(screen.getByText("93.4000 / 100")).toBeVisible();
    });
    expect(screen.getByText("934 / 1000")).toBeVisible();
    expect(screen.getByText("원점수 η")).toBeVisible();
    expect(screen.getByText("동적 임계값 τ")).toBeVisible();
    expect(screen.getByText("임계 대비 η−τ")).toBeVisible();
    expect(
      screen.getByText(/최근 3개 봉 매수 압력/)
    ).toHaveTextContent("0.420000 > 0 · 통과");
    expect(screen.getByText("점수를 크게 움직인 요인")).toBeVisible();
    expect(screen.getAllByText("ret_6")).toHaveLength(2);
    expect(
      screen.getByText("전체 수식과 2개 입력 보기")
    ).toBeVisible();
    expect(screen.getByText("당일 전체 변화 보기")).toBeVisible();
    expect(
      screen.getByText(
        /투자자 심리, 사건 발생확률 또는 매수·매도 권고를 직접 뜻하지 않으며/
      )
    ).toBeVisible();
  });

  it("switches clicked help popovers and closes the active one with Escape", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
      expect(screen.getByRole("button", { name: "MU 마이크론 상세 보기" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));

    const helpButton = screen.getByRole("button", { name: "CVD 초보자 설명 보기" });
    fireEvent.click(helpButton);

    expect(screen.getByRole("tooltip", { name: "CVD 추정 설명" })).toBeVisible();

    const velocityHelpButton = screen.getByRole("button", { name: "속도/가속도 초보자 설명 보기" });
    fireEvent.click(velocityHelpButton);

    expect(screen.queryByRole("tooltip", { name: "CVD 추정 설명" })).not.toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: "속도/가속도 설명" })).toBeVisible();

    fireEvent.keyDown(velocityHelpButton, { key: "Escape" });

    expect(screen.queryByRole("tooltip", { name: "속도/가속도 설명" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "MU 상세 분석" })).toBeVisible();
  });

  it("closes the active helper popup when clicking outside it", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient([sampleCard])}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
      expect(screen.getByRole("button", { name: "MU 마이크론 상세 보기" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));

    fireEvent.click(screen.getByRole("button", { name: "CVD 초보자 설명 보기" }));

    expect(screen.getByRole("tooltip", { name: "CVD 추정 설명" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "지표 설명 닫기" }));

    expect(screen.queryByRole("tooltip", { name: "CVD 추정 설명" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "MU 상세 분석" })).toBeVisible();
  });

  it("updates memo, tags, and lightweight group from the detail panel", async () => {
    const update = vi.fn(async () => ({
      card: {
        ...sampleCard,
        groupId: "반도체",
        tags: ["반도체", "관찰"],
        memo: "상세에서 수정"
      },
      watchlist: {
        activeCards: [
          {
            ...sampleCard,
            groupId: "반도체",
            tags: ["반도체", "관찰"],
            memo: "상세에서 수정"
          }
        ],
        hiddenCards: [],
        archivedCards: []
      }
    }));
    const watchlistClient = {
      ...createWatchlistClient([sampleCard]),
      update
    };

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={watchlistClient}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "MU 마이크론 상세 보기" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "MU 마이크론 상세 보기" }));
    fireEvent.change(screen.getByLabelText("상세 메모"), {
      target: { value: "상세에서 수정" }
    });
    fireEvent.change(screen.getByLabelText("상세 태그"), {
      target: { value: "반도체, 관찰" }
    });
    fireEvent.change(screen.getByLabelText("상세 그룹"), {
      target: { value: "반도체" }
    });
    fireEvent.click(screen.getByRole("button", { name: "카드 저장" }));

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith("card-1", {
        memo: "상세에서 수정",
        tags: ["반도체", "관찰"],
        groupId: "반도체"
      });
    });
  });

  it("reorders cards with keyboard-friendly up and down card actions", async () => {
    const reorder = vi.fn(async () => ({
      activeCards: [riskCard, sampleCard],
      hiddenCards: [],
      archivedCards: []
    }));
    const watchlistClient = {
      ...createWatchlistClient([sampleCard, riskCard]),
      reorder
    };

    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={watchlistClient}
        stockReferenceClient={createStockReferenceClient()}
        marketDataClient={createMarketDataClient()}
        quantIndicatorClient={createQuantIndicatorClient()}
        tossSettingsClient={createTossSettingsClient(validTossCredentialStatus)}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "AMD 위로 이동" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "AMD 위로 이동" }));

    await waitFor(() => {
      expect(reorder).toHaveBeenCalledWith(["card-2", "card-1"]);
    });
  });
});
