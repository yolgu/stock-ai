import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface RefreshResult {
  snapshots: Array<{
    cardId: string;
    observedState: string;
    staleMarker?: boolean;
    signals: Array<{
      status: string;
      unavailableReason?: string;
    }>;
  }>;
}

interface MarketStateService {
  activeCalculation: Promise<void> | null;
  calculationErrorsByCardId: Record<string, string>;
  refresh(
    payload: { cardIds?: string[] },
    occurredAt: string
  ): Promise<RefreshResult>;
}

const { MarketStateApplicationService } = require(
  "./market-state-service.cjs"
) as {
  MarketStateApplicationService: new (input: {
    watchlistRepository: {
      list(): Promise<{
        activeCards: Array<{
          id: string;
          symbol: string;
        }>;
      }>;
    };
    marketDataSnapshotRepository: {
      readLatest(cardIds?: string[]): Promise<Array<Record<string, never>>>;
    };
    minuteRepository: Record<string, never>;
    snapshotRepository: {
      readLatest(
        cardIds?: string[]
      ): Promise<Array<Record<string, boolean | string>>>;
    };
    backfill: {
      start(input: {
        instrumentIds: string[];
        occurredAt: string;
      }): Promise<{ status: string }>;
      readProgress(): Promise<{ status: string }>;
    };
  }) => MarketStateService;
};

describe("market-state application service", () => {
  it("does not present a stored snapshot as current after calculation failure", async () => {
    const service: MarketStateService =
      new MarketStateApplicationService({
        watchlistRepository: {
          async list(): Promise<{
            activeCards: Array<{ id: string; symbol: string }>;
          }> {
            return {
              activeCards: [{ id: "card-aapl", symbol: "AAPL" }]
            };
          }
        },
        marketDataSnapshotRepository: {
          async readLatest(): Promise<Array<Record<string, never>>> {
            return [];
          }
        },
        minuteRepository: {},
        snapshotRepository: {
          async readLatest(): Promise<
            Array<Record<string, boolean | string>>
          > {
            return [{
              cardId: "card-aapl",
              staleMarker: true
            }];
          }
        },
        backfill: {
          async start(): Promise<{ status: string }> {
            return { status: "idle" };
          },
          async readProgress(): Promise<{ status: string }> {
            return { status: "idle" };
          }
        }
      });
    service.activeCalculation = Promise.resolve();
    service.calculationErrorsByCardId = {
      "card-aapl": "normalization_failed"
    };

    const result: RefreshResult = await service.refresh(
      {},
      "2026-07-31T14:35:00.000Z"
    );

    expect(result.snapshots[0]).toMatchObject({
      cardId: "card-aapl",
      observedState: "UNAVAILABLE"
    });
    expect(result.snapshots[0].staleMarker).toBeUndefined();
    expect(
      result.snapshots[0].signals.every(
        (signal: {
          status: string;
          unavailableReason?: string;
        }): boolean =>
          signal.status === "unavailable" &&
          signal.unavailableReason === "normalization_failed"
      )
    ).toBe(true);
  });
});
