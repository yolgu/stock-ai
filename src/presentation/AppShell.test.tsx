import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { StockReferenceClient } from "../infrastructure/neutralino/NeutralinoStockReferenceClient";
import type {
  MarketDataSnapshotPayload,
  QuantIndicatorSnapshotPayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";
import { AppShell } from "./AppShell";
import { StartupStateView } from "./StartupStateView";

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
    riskReward: {
      status: "available",
      ratio: 4.5,
      label: "손익비 1.5x 이상",
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
      key: "spread",
      label: "스프레드 정상",
      severity: "positive",
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
    expect(screen.queryByText("194.93")).not.toBeInTheDocument();
    expect(screen.queryByText("195.00")).not.toBeInTheDocument();
    expect(screen.queryByText("100")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(quantIndicatorClient.refreshWatchlist).toHaveBeenCalledWith({
        cardIds: ["card-1"]
      });
    });
    expect(screen.getByText("관망")).toBeVisible();
    expect(screen.getByText("지표 업데이트 09:00:06")).toBeVisible();
    expect(screen.getByText("VWAP 위 안착")).toBeVisible();
    expect(screen.getByText("체결 압력 우위")).toBeVisible();
    expect(screen.getByText("스프레드 정상")).toBeVisible();
    expect(screen.queryByText("101.7500")).not.toBeInTheDocument();
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
});
