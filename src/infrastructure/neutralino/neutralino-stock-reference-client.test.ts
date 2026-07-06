import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoStockReferenceClient } from "./NeutralinoStockReferenceClient";

describe("NeutralinoStockReferenceClient", () => {
  it("dispatches a typed stock verification request and resolves the matching response", async () => {
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
    const client = new NeutralinoStockReferenceClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-stock-1"
      }
    });

    const result = client.verify({ rawInput: "NASDAQ:MU" });

    expect(dispatches).toEqual([
      {
        eventName: "stock-reference:verify:request",
        data: {
          event: "stock-reference:verify:request",
          requestId: "request-stock-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: { rawInput: "NASDAQ:MU" }
        }
      }
    ]);

    eventListeners.get("stock-reference:verify:response")?.({
      detail: {
        event: "stock-reference:verify:response",
        requestId: "request-stock-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
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
              verifiedAt: "2026-07-06T09:00:01.000Z"
            }
          ],
          rejected: []
        }
      }
    });

    await expect(result).resolves.toMatchObject({
      verified: [
        {
          symbol: "MU",
          market: "NASDAQ",
          requiresConfirmation: false
        }
      ],
      rejected: []
    });
  });

  it("creates a watch card only through the verified creation event", async () => {
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
    const client = new NeutralinoStockReferenceClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-stock-2"
      }
    });

    const result = client.createVerifiedCard({
      symbol: "MU",
      confirmedRisk: false,
      groupId: null,
      tags: ["반도체"],
      memo: ""
    });

    expect(dispatches[0]).toEqual({
      eventName: "watchlist:create-verified:request",
      data: expect.objectContaining({
        event: "watchlist:create-verified:request",
        requestId: "request-stock-2",
        payload: {
          symbol: "MU",
          confirmedRisk: false,
          groupId: null,
          tags: ["반도체"],
          memo: ""
        }
      })
    });
    expect(dispatches[0]?.eventName).not.toBe("watchlist:create:request");

    eventListeners.get("watchlist:create-verified:response")?.({
      detail: {
        event: "watchlist:create-verified:response",
        requestId: "request-stock-2",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          type: "created",
          card: {
            id: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            displayName: "마이크론 테크놀로지",
            groupId: null,
            tags: ["반도체"],
            memo: "",
            sortOrder: 1,
            lifecycleStatus: "active",
            createdAt: "2026-07-06T09:00:01.000Z",
            updatedAt: "2026-07-06T09:00:01.000Z"
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
        symbol: "MU",
        displayName: "마이크론 테크놀로지"
      }
    });
  });
});
