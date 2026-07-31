import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoMarketStateClient } from "./NeutralinoMarketStateClient";

describe("NeutralinoMarketStateClient", () => {
  it("dispatches the market-state refresh and validates the response boundary", async () => {
    const eventListeners: Map<
      string,
      (event: { detail: unknown }) => void
    > = new Map();
    const dispatches: Array<{ eventName: string; data: unknown }> = [];
    const extensions: NeutralinoExtensionsApi = {
      dispatch: async (
        _extensionId: string,
        eventName: string,
        data: unknown
      ): Promise<unknown> => {
        dispatches.push({ eventName, data });
        return undefined;
      }
    };
    const events: NeutralinoEventsApi = {
      on: async (
        eventName: string,
        handler: (event: { detail: unknown }) => void
      ): Promise<unknown> => {
        eventListeners.set(eventName, handler);
        return undefined;
      },
      off: async (eventName: string): Promise<unknown> => {
        eventListeners.delete(eventName);
        return undefined;
      }
    };
    const client: NeutralinoMarketStateClient =
      new NeutralinoMarketStateClient({
        extensions,
        events,
        clock: {
          nowIso: (): string => "2026-07-31T14:05:00.000Z",
          nextRequestId: (): string => "request-market-state-1"
        }
      });

    const result = client.refreshWatchlist({ cardIds: ["card-1"] });

    expect(dispatches[0]).toMatchObject({
      eventName: "market-state:refresh-watchlist:request",
      data: {
        event: "market-state:refresh-watchlist:request",
        requestId: "request-market-state-1",
        payload: { cardIds: ["card-1"] }
      }
    });
    eventListeners.get("market-state:refresh-watchlist:response")?.({
      detail: {
        event: "market-state:refresh-watchlist:response",
        requestId: "request-market-state-1",
        occurredAt: "2026-07-31T14:05:01.000Z",
        payload: {
          refreshedAt: "2026-07-31T14:05:01.000Z",
          snapshots: [],
          backfillProgress: {
            jobId: "job-1",
            status: "running",
            requiredSessions: 60,
            completedSessions: 1,
            currentInstrumentId: "AAPL",
            totalInstrumentCount: 34,
            completedInstrumentCount: 0,
            error: null
          }
        }
      }
    });

    await expect(result).resolves.toMatchObject({
      snapshots: [],
      backfillProgress: { status: "running" }
    });
  });

  it("rejects an unvalidated market-state payload", async () => {
    const eventListeners: Map<
      string,
      (event: { detail: unknown }) => void
    > = new Map();
    const client: NeutralinoMarketStateClient =
      new NeutralinoMarketStateClient({
        extensions: {
          dispatch: async (): Promise<unknown> => undefined
        },
        events: {
          on: async (
            eventName: string,
            handler: (event: { detail: unknown }) => void
          ): Promise<unknown> => {
            eventListeners.set(eventName, handler);
            return undefined;
          },
          off: async (eventName: string): Promise<unknown> => {
            eventListeners.delete(eventName);
            return undefined;
          }
        },
        clock: {
          nowIso: (): string => "2026-07-31T14:05:00.000Z",
          nextRequestId: (): string => "request-market-state-invalid"
        }
      });
    const result = client.refreshWatchlist({ cardIds: ["card-1"] });

    eventListeners.get("market-state:refresh-watchlist:response")?.({
      detail: {
        event: "market-state:refresh-watchlist:response",
        requestId: "request-market-state-invalid",
        occurredAt: "2026-07-31T14:05:01.000Z",
        payload: {
          refreshedAt: "invalid",
          snapshots: [],
          backfillProgress: {}
        }
      }
    });

    await expect(result).rejects.toMatchObject({
      code: "market_state_calculation_failed"
    });

    const traceResult = client.readTrace({
      cardId: "card-1",
      signalId: "FOMO_LIKE"
    });
    eventListeners.get("market-state:trace:response")?.({
      detail: {
        event: "market-state:trace:response",
        requestId: "request-market-state-invalid",
        occurredAt: "2026-07-31T14:05:02.000Z",
        payload: { trace: {} }
      }
    });
    await expect(traceResult).rejects.toMatchObject({
      code: "market_state_calculation_failed"
    });

    const historyResult = client.readHistory({
      cardId: "card-1",
      signalId: "FOMO_LIKE",
      sessionDate: "2026-07-31"
    });
    eventListeners.get("market-state:history:response")?.({
      detail: {
        event: "market-state:history:response",
        requestId: "request-market-state-invalid",
        occurredAt: "2026-07-31T14:05:03.000Z",
        payload: {
          cardId: "card-1",
          signalId: "FOMO_LIKE",
          sessionDate: "2026-07-31",
          points: [{ percentile: 101 }]
        }
      }
    });
    await expect(historyResult).rejects.toMatchObject({
      code: "market_state_calculation_failed"
    });
  });
});
