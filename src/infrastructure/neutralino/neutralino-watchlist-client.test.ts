import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoWatchlistClient } from "./NeutralinoWatchlistClient";

describe("NeutralinoWatchlistClient", () => {
  it("dispatches a typed list request and resolves the matching response", async () => {
    const eventListeners = new Map<string, (event: { detail: unknown }) => void>();
    const dispatches: Array<{ extensionId: string; eventName: string; data: unknown }> = [];
    const extensions: NeutralinoExtensionsApi = {
      dispatch: async (extensionId, eventName, data): Promise<unknown> => {
        dispatches.push({ extensionId, eventName, data });
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
    const client = new NeutralinoWatchlistClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-1"
      }
    });

    const result = client.list();

    expect(dispatches).toEqual([
      {
        extensionId: "app.stockSub.runtime",
        eventName: "watchlist:list:request",
        data: {
          event: "watchlist:list:request",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {}
        }
      }
    ]);

    eventListeners.get("watchlist:list:response")?.({
      detail: {
        event: "watchlist:list:response",
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          activeCards: [],
          hiddenCards: [],
          archivedCards: []
        }
      }
    });

    await expect(result).resolves.toEqual({
      activeCards: [],
      hiddenCards: [],
      archivedCards: []
    });
  });

  it("creates a watch card through the extension boundary", async () => {
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
    const client = new NeutralinoWatchlistClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-2"
      }
    });

    const result = client.create({
      market: "NASDAQ",
      symbol: "MU",
      displayName: "MU 마이크론",
      groupId: null,
      tags: ["반도체"],
      memo: ""
    });

    expect(dispatches[0]).toEqual({
      eventName: "watchlist:create:request",
      data: expect.objectContaining({
        event: "watchlist:create:request",
        requestId: "request-2",
        payload: expect.objectContaining({
          market: "NASDAQ",
          symbol: "MU",
          displayName: "MU 마이크론"
        })
      })
    });

    eventListeners.get("watchlist:create:response")?.({
      detail: {
        event: "watchlist:create:response",
        requestId: "request-2",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          type: "created",
          card: {
            id: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            displayName: "MU 마이크론",
            groupId: null,
            tags: ["반도체"],
            memo: "",
            sortOrder: 1,
            lifecycleStatus: "active",
            createdAt: "2026-07-06T09:00:00.000Z",
            updatedAt: "2026-07-06T09:00:00.000Z"
          },
          watchlist: {
            activeCards: [],
            hiddenCards: [],
            archivedCards: []
          }
        }
      }
    });

    await expect(result).resolves.toMatchObject({
      type: "created",
      card: {
        id: "card-1",
        symbol: "MU"
      }
    });
  });
});
