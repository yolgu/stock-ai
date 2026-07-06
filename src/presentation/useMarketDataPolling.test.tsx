import { act, cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type {
  MarketDataSnapshotPayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";
import { useMarketDataPolling } from "./useMarketDataPolling";

const activeCard: WatchStockCardDto = {
  id: "card-1",
  market: "NASDAQ",
  symbol: "MU",
  displayName: "마이크론 테크놀로지",
  groupId: null,
  tags: [],
  memo: "",
  sortOrder: 1,
  lifecycleStatus: "active",
  createdAt: "2026-07-06T09:00:00.000Z",
  updatedAt: "2026-07-06T09:00:00.000Z"
};

const validCredentials: TossCredentialStatusPayload = {
  configured: true,
  maskedClientId: "clie...7890",
  lastValidatedAt: "2026-07-06T09:00:00.000Z",
  connectionStatus: "valid"
};

const activeCards = [activeCard];

const marketDataSnapshot: MarketDataSnapshotPayload = {
  snapshotId: "snapshot-1",
  cardId: "card-1",
  market: "NASDAQ",
  symbol: "MU",
  capturedAt: "2026-07-06T09:00:05.000Z",
  freshness: "fresh",
  quality: "complete",
  observations: {
    price: null,
    trades: [],
    orderbook: null,
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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useMarketDataPolling", () => {
  it("keeps scheduled polling alive after a transient refresh failure", async () => {
    const refreshWatchlist = vi
      .fn<MarketDataClient["refreshWatchlist"]>()
      .mockRejectedValueOnce(new Error("temporary Toss outage"))
      .mockResolvedValueOnce({
        refreshedAt: "2026-07-06T09:00:20.000Z",
        nextPollDelayMs: 15_000,
        snapshots: [marketDataSnapshot]
      });
    const client: MarketDataClient = {
      refreshWatchlist,
      refreshCard: vi.fn<MarketDataClient["refreshCard"]>(),
      readLatestSnapshots: vi.fn<MarketDataClient["readLatestSnapshots"]>()
    };

    render(<PollingHarness client={client} />);
    const scheduledTimeouts: Array<{
      handler: () => void;
      delayMs: number;
    }> = [];
    vi.spyOn(window, "setTimeout").mockImplementation(
      (handler, timeout, ...args): ReturnType<typeof window.setTimeout> => {
        if (typeof handler === "function") {
          scheduledTimeouts.push({
            handler: () => handler(...args),
            delayMs: typeof timeout === "number" ? timeout : 0
          });
        }

        return scheduledTimeouts.length as unknown as ReturnType<typeof window.setTimeout>;
      }
    );
    vi.spyOn(window, "clearTimeout").mockImplementation(() => undefined);

    await act(async () => {
      await Promise.resolve();
    });

    expect(refreshWatchlist).toHaveBeenCalledTimes(1);
    expect(screen.getByText("error")).toBeVisible();
    expect(scheduledTimeouts).toContainEqual(
      expect.objectContaining({
        delayMs: 15_000
      })
    );
    const retryTimeout = scheduledTimeouts.find((timeout) => timeout.delayMs === 15_000);

    await act(async () => {
      retryTimeout?.handler();
    });

    expect(refreshWatchlist).toHaveBeenCalledTimes(2);
    expect(screen.getByText("ready")).toBeVisible();
  });
});

function PollingHarness({ client }: { client: MarketDataClient }): ReactElement {
  const polling = useMarketDataPolling(client, {
    activeCards,
    credentials: validCredentials
  });

  return (
    <div>
      <span>{polling.status}</span>
      <span>{Object.keys(polling.snapshotsByCardId).join(",")}</span>
    </div>
  );
}
