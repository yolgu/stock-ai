import type {
  CreateWatchStockCardInput,
  CreateWatchStockCardResult,
  WatchStockCardDto,
  Watchlist
} from "../../domain/watchlist/Watchlist";

export interface WatchlistListDto {
  activeCards: WatchStockCardDto[];
  hiddenCards: WatchStockCardDto[];
  archivedCards: WatchStockCardDto[];
}

export interface WatchlistRepository {
  load(): Promise<Watchlist>;
  save(watchlist: Watchlist): Promise<void>;
}

export class ListWatchStockCards {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async list(): Promise<WatchlistListDto> {
    const watchlist = await this.repository.load();

    return {
      activeCards: watchlist.listActiveCards(),
      hiddenCards: watchlist.listHiddenCards(),
      archivedCards: watchlist.listArchivedCards()
    };
  }
}

export class CreateWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async create(input: CreateWatchStockCardInput): Promise<CreateWatchStockCardResult> {
    const watchlist = await this.repository.load();
    const result = watchlist.createCard(input);

    if (result.type === "created") {
      await this.repository.save(watchlist);
    }

    return result;
  }
}

export class UpdateWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async update(
    cardId: string,
    input: {
      displayName?: string;
      groupId?: string | null;
      tags?: readonly string[];
      memo?: string;
      now: string;
    }
  ): Promise<WatchStockCardDto | undefined> {
    const watchlist = await this.repository.load();
    const card = watchlist.updateCard(cardId, input);

    if (card !== undefined) {
      await this.repository.save(watchlist);
    }

    return card;
  }
}

export class HideWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async hide(cardId: string, now: string): Promise<WatchStockCardDto | undefined> {
    const watchlist = await this.repository.load();
    const card = watchlist.hideCard(cardId, now);

    if (card !== undefined) {
      await this.repository.save(watchlist);
    }

    return card;
  }
}

export class ArchiveWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async archive(cardId: string, now: string): Promise<WatchStockCardDto | undefined> {
    const watchlist = await this.repository.load();
    const card = watchlist.archiveCard(cardId, now);

    if (card !== undefined) {
      await this.repository.save(watchlist);
    }

    return card;
  }
}

export class RestoreWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async restore(cardId: string, now: string): Promise<WatchStockCardDto | undefined> {
    const watchlist = await this.repository.load();
    const card = watchlist.restoreCard(cardId, now);

    if (card !== undefined) {
      await this.repository.save(watchlist);
    }

    return card;
  }
}

export class DeleteWatchStockCard {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async delete(cardId: string): Promise<void> {
    const watchlist = await this.repository.load();
    watchlist.deleteCard(cardId);
    await this.repository.save(watchlist);
  }
}

export class ReorderWatchStockCards {
  public constructor(private readonly repository: WatchlistRepository) {}

  public async reorder(
    orderedCardIds: readonly string[],
    now: string
  ): Promise<WatchStockCardDto[]> {
    const watchlist = await this.repository.load();
    const cards = watchlist.reorderActiveCards(orderedCardIds, now);
    await this.repository.save(watchlist);

    return cards;
  }
}
