import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoMarketDataClient } from "./NeutralinoMarketDataClient";

describe("NeutralinoMarketDataClient", () => {
  it("dispatches a typed watchlist refresh request and resolves matching snapshots", async () => {
    const eventListeners = new Map<string, (event: { detail: unknown }) => void>();
    const dispatches: Array<{ eventName: string; data: unknown }> = [];
    const extensions: NeutralinoExtensionsApi = {
      dispatch: async (_extensionId, eventName, data): Promise<unknown> => {
        dispatches.push({ eventName, data });
        return undefined;
      }
    };
    const events: NeutralinoEventsApi = {
      on: async (eventName, handler): Promise<unknown> => {
        eventListeners.set(eventName, handler);
        return undefined;
      },
      off: async (eventName): Promise<unknown> => {
        eventListeners.delete(eventName);
        return undefined;
      }
    };
    const client = new NeutralinoMarketDataClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-market-1"
      }
    });

    const result = client.refreshWatchlist({ visibleCardIds: ["card-1"] });

    expect(dispatches[0]).toEqual({
      eventName: "market-data:refresh-watchlist:request",
      data: {
        event: "market-data:refresh-watchlist:request",
        requestId: "request-market-1",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: { visibleCardIds: ["card-1"] }
      }
    });

    eventListeners.get("market-data:refresh-watchlist:response")?.({
      detail: {
        event: "market-data:refresh-watchlist:response",
        requestId: "request-market-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          refreshedAt: "2026-07-06T09:00:01.000Z",
          nextPollDelayMs: 15_000,
          snapshots: []
        }
      }
    });

    await expect(result).resolves.toEqual({
      refreshedAt: "2026-07-06T09:00:01.000Z",
      nextPollDelayMs: 15_000,
      snapshots: []
    });
  });
});
