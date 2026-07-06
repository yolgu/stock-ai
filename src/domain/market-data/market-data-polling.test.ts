import { describe, expect, it } from "vitest";

import type { WatchStockCardDto } from "../watchlist/Watchlist";
import { MarketDataPollingPlan } from "./MarketDataPolling";

const baseCard: WatchStockCardDto = {
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

describe("MarketDataPollingPlan", () => {
  it("includes only active cards and prioritizes visible cards", () => {
    const plan = MarketDataPollingPlan.create({
      watchlist: {
        activeCards: [
          { ...baseCard, id: "card-1", symbol: "MU", sortOrder: 1 },
          { ...baseCard, id: "card-2", symbol: "AAPL", sortOrder: 2 },
          { ...baseCard, id: "card-3", symbol: "MSFT", sortOrder: 3 }
        ],
        hiddenCards: [{ ...baseCard, id: "hidden-1", symbol: "NVDA", lifecycleStatus: "hidden" }],
        archivedCards: [
          { ...baseCard, id: "archived-1", symbol: "AMD", lifecycleStatus: "archived" }
        ]
      },
      visibleCardIds: ["card-3", "card-1"],
      marketSession: "regular"
    });

    expect(plan.cardsToPoll().map((card) => card.id)).toEqual(["card-3", "card-1", "card-2"]);
    expect(plan.symbolsForPriceBatch()).toEqual(["MSFT", "MU", "AAPL"]);
  });

  it("maps Korean and US markets to the matching calendar country", () => {
    const plan = MarketDataPollingPlan.create({
      watchlist: {
        activeCards: [
          { ...baseCard, id: "card-kr", market: "KOSPI", symbol: "005930" },
          { ...baseCard, id: "card-us", market: "NYSE", symbol: "IBM" }
        ],
        hiddenCards: [],
        archivedCards: []
      },
      visibleCardIds: [],
      marketSession: "regular"
    });

    expect(plan.marketCountries()).toEqual(["KR", "US"]);
  });

  it("uses a slower polling delay when the market is closed or on holiday", () => {
    const closedPlan = MarketDataPollingPlan.create({
      watchlist: { activeCards: [baseCard], hiddenCards: [], archivedCards: [] },
      visibleCardIds: [],
      marketSession: "closed"
    });
    const holidayPlan = MarketDataPollingPlan.create({
      watchlist: { activeCards: [baseCard], hiddenCards: [], archivedCards: [] },
      visibleCardIds: [],
      marketSession: "holiday"
    });

    expect(closedPlan.nextPollDelayMs()).toBeGreaterThanOrEqual(300_000);
    expect(holidayPlan.nextPollDelayMs()).toBeGreaterThanOrEqual(300_000);
  });
});
