import { describe, expect, it } from "vitest";

import { Watchlist } from "../../domain/watchlist/Watchlist";
import {
  ArchiveWatchStockCard,
  CreateWatchStockCard,
  ListWatchStockCards,
  ReorderWatchStockCards,
  RestoreWatchStockCard,
  type WatchlistRepository
} from "./WatchlistUseCases";

class InMemoryWatchlistRepository implements WatchlistRepository {
  private watchlist = Watchlist.empty();

  public async load(): Promise<Watchlist> {
    return this.watchlist;
  }

  public async save(watchlist: Watchlist): Promise<void> {
    this.watchlist = watchlist;
  }
}

describe("watchlist use cases", () => {
  it("creates, archives, restores, and reorders cards through the repository boundary", async () => {
    const repository = new InMemoryWatchlistRepository();
    const createCard = new CreateWatchStockCard(repository);
    const archiveCard = new ArchiveWatchStockCard(repository);
    const restoreCard = new RestoreWatchStockCard(repository);
    const reorderCards = new ReorderWatchStockCards(repository);
    const listCards = new ListWatchStockCards(repository);

    await createCard.create({
      id: "card-1",
      market: "NASDAQ",
      symbol: "MU",
      displayName: "MU 마이크론",
      groupId: null,
      tags: ["반도체"],
      memo: "",
      now: "2026-07-06T09:00:00.000Z"
    });
    await createCard.create({
      id: "card-2",
      market: "NYSE",
      symbol: "IBM",
      displayName: "IBM",
      groupId: null,
      tags: [],
      memo: "",
      now: "2026-07-06T09:01:00.000Z"
    });

    await archiveCard.archive("card-1", "2026-07-06T09:02:00.000Z");
    expect((await listCards.list()).activeCards.map((card) => card.id)).toEqual(["card-2"]);

    await restoreCard.restore("card-1", "2026-07-06T09:03:00.000Z");
    await reorderCards.reorder(["card-1", "card-2"], "2026-07-06T09:04:00.000Z");

    expect((await listCards.list()).activeCards.map((card) => card.id)).toEqual([
      "card-1",
      "card-2"
    ]);
  });
});
