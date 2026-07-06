import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { TossCredentialStatusPayload } from "../shared/contracts/app-runtime-contract";
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
      enabled: false,
      reason: "시장 데이터 폴링 단계 이후 활성화"
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

function createWatchlistClient(cards: WatchStockCardDto[] = []) {
  let activeCards = [...cards];

  return {
    list: async () => ({
      activeCards,
      hiddenCards: [],
      archivedCards: []
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
  it("renders an empty watchlist-ready desktop shell", () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        tossSettingsClient={createTossSettingsClient()}
      />
    );

    expect(
      screen.getByRole("heading", { name: "관심종목 분석 대기" })
    ).toBeVisible();
    expect(screen.getByText("토스 차트 옆에서 볼 분석 카드를 준비합니다.")).toBeVisible();
    expect(screen.getByText("watchlist")).toBeVisible();
    expect(screen.getByText("준비됨")).toBeVisible();
    expect(screen.getByText("quantIndicators")).toBeVisible();
    expect(screen.getByText("대기")).toBeVisible();
  });

  it("opens Toss settings and saves masked credential status", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
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

  it("creates a visible analysis card from the add form", async () => {
    render(
      <AppShell
        runtimeProfile={runtimeProfile}
        watchlistClient={createWatchlistClient()}
        tossSettingsClient={createTossSettingsClient()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    fireEvent.change(screen.getByLabelText("시장"), {
      target: { value: "NASDAQ" }
    });
    fireEvent.change(screen.getByLabelText("심볼"), {
      target: { value: "MU" }
    });
    fireEvent.change(screen.getByLabelText("표시 이름"), {
      target: { value: "MU 마이크론" }
    });
    fireEvent.click(screen.getByRole("button", { name: "카드 저장" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "MU 마이크론" })).toBeVisible();
    });
    expect(screen.getByText("NASDAQ · MU")).toBeVisible();
    expect(screen.getByText("VWAP 중심 관찰")).toBeVisible();
  });
});
