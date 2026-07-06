import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoQuantIndicatorClient } from "./NeutralinoQuantIndicatorClient";

describe("NeutralinoQuantIndicatorClient", () => {
  it("dispatches a typed quant refresh request and resolves matching snapshots", async () => {
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
    const client = new NeutralinoQuantIndicatorClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-quant-1"
      }
    });

    const result = client.refreshWatchlist({ cardIds: ["card-1"] });

    expect(dispatches[0]).toEqual({
      eventName: "quant-indicators:refresh-watchlist:request",
      data: {
        event: "quant-indicators:refresh-watchlist:request",
        requestId: "request-quant-1",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: { cardIds: ["card-1"] }
      }
    });

    eventListeners.get("quant-indicators:refresh-watchlist:response")?.({
      detail: {
        event: "quant-indicators:refresh-watchlist:response",
        requestId: "request-quant-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          refreshedAt: "2026-07-06T09:00:01.000Z",
          snapshots: []
        }
      }
    });

    await expect(result).resolves.toEqual({
      refreshedAt: "2026-07-06T09:00:01.000Z",
      snapshots: []
    });
  });
});
