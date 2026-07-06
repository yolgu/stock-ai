import { describe, expect, it } from "vitest";

import { Watchlist } from "./Watchlist";

const firstCardInput = {
  id: "card-1",
  market: "NASDAQ",
  symbol: "mu",
  displayName: "MU 마이크론",
  groupId: "semis",
  tags: ["반도체", "미국"],
  memo: "VWAP 중심 관찰",
  now: "2026-07-06T09:00:00.000Z"
} as const;

describe("Watchlist", () => {
  it("creates a watch stock card with normalized market and symbol", () => {
    const watchlist = Watchlist.empty();

    const result = watchlist.createCard(firstCardInput);

    expect(result.type).toBe("created");
    expect(watchlist.listActiveCards()).toEqual([
      {
        id: "card-1",
        market: "NASDAQ",
        symbol: "MU",
        displayName: "MU 마이크론",
        groupId: "semis",
        tags: ["반도체", "미국"],
        memo: "VWAP 중심 관찰",
        sortOrder: 1,
        lifecycleStatus: "active",
        createdAt: "2026-07-06T09:00:00.000Z",
        updatedAt: "2026-07-06T09:00:00.000Z"
      }
    ]);
  });

  it("prevents creating a second active card for the same market and symbol", () => {
    const watchlist = Watchlist.empty();
    watchlist.createCard(firstCardInput);

    const result = watchlist.createCard({
      ...firstCardInput,
      id: "card-2",
      displayName: "Micron Technology",
      now: "2026-07-06T09:01:00.000Z"
    });

    expect(result).toEqual({
      type: "duplicate-card",
      existingCardId: "card-1"
    });
    expect(watchlist.listActiveCards()).toHaveLength(1);
  });

  it("offers restoration instead of creating a second card when the match is archived", () => {
    const watchlist = Watchlist.empty();
    watchlist.createCard(firstCardInput);
    watchlist.archiveCard("card-1", "2026-07-06T09:02:00.000Z");

    const result = watchlist.createCard({
      ...firstCardInput,
      id: "card-2",
      now: "2026-07-06T09:03:00.000Z"
    });

    expect(result).toEqual({
      type: "restore-available",
      archivedCardId: "card-1"
    });
    expect(watchlist.listActiveCards()).toEqual([]);
    expect(watchlist.listArchivedCards()).toHaveLength(1);
  });

  it("excludes hidden and archived cards from the active analysis list", () => {
    const watchlist = Watchlist.empty();
    watchlist.createCard(firstCardInput);
    watchlist.createCard({
      ...firstCardInput,
      id: "card-2",
      market: "NYSE",
      symbol: "IBM",
      displayName: "IBM",
      now: "2026-07-06T09:01:00.000Z"
    });
    watchlist.createCard({
      ...firstCardInput,
      id: "card-3",
      market: "KOSPI",
      symbol: "005930",
      displayName: "삼성전자",
      now: "2026-07-06T09:02:00.000Z"
    });

    watchlist.hideCard("card-2", "2026-07-06T09:03:00.000Z");
    watchlist.archiveCard("card-3", "2026-07-06T09:04:00.000Z");

    expect(watchlist.listActiveCards().map((card) => card.id)).toEqual(["card-1"]);
    expect(watchlist.listHiddenCards().map((card) => card.id)).toEqual(["card-2"]);
    expect(watchlist.listArchivedCards().map((card) => card.id)).toEqual(["card-3"]);
  });

  it("persists stable sort order when active cards are reordered", () => {
    const watchlist = Watchlist.empty();
    watchlist.createCard(firstCardInput);
    watchlist.createCard({
      ...firstCardInput,
      id: "card-2",
      market: "NYSE",
      symbol: "IBM",
      displayName: "IBM",
      now: "2026-07-06T09:01:00.000Z"
    });

    watchlist.reorderActiveCards(["card-2", "card-1"], "2026-07-06T09:02:00.000Z");

    expect(
      watchlist.listActiveCards().map((card) => ({
        id: card.id,
        sortOrder: card.sortOrder
      }))
    ).toEqual([
      { id: "card-2", sortOrder: 1 },
      { id: "card-1", sortOrder: 2 }
    ]);
  });

  it("removes a deleted card from list output", () => {
    const watchlist = Watchlist.empty();
    watchlist.createCard(firstCardInput);

    watchlist.deleteCard("card-1");

    expect(watchlist.toDto().cards).toEqual([]);
  });
});
