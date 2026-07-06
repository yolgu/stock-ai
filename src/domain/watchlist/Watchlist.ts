export type CardLifecycleStatus = "active" | "hidden" | "archived" | "deleted";

export interface WatchStockCardDto {
  id: string;
  market: string;
  symbol: string;
  displayName: string;
  groupId: string | null;
  tags: string[];
  memo: string;
  sortOrder: number;
  lifecycleStatus: CardLifecycleStatus;
  createdAt: string;
  updatedAt: string;
}

export interface WatchGroupDto {
  id: string;
  name: string;
  sortOrder: number;
}

export interface WatchlistDto {
  cards: WatchStockCardDto[];
  groups: WatchGroupDto[];
}

export interface CreateWatchStockCardInput {
  id: string;
  market: string;
  symbol: string;
  displayName: string;
  groupId?: string | null;
  tags?: readonly string[];
  memo?: string;
  now: string;
}

export type CreateWatchStockCardResult =
  | {
      type: "created";
      card: WatchStockCardDto;
    }
  | {
      type: "duplicate-card";
      existingCardId: string;
    }
  | {
      type: "restore-available";
      archivedCardId: string;
    };

export class WatchStockCard {
  private constructor(private readonly state: WatchStockCardDto) {}

  public static create(input: CreateWatchStockCardInput, sortOrder: number): WatchStockCard {
    const now = input.now;

    return new WatchStockCard({
      id: input.id,
      market: Market.from(input.market).value(),
      symbol: StockSymbol.from(input.symbol).value(),
      displayName: DisplayName.from(input.displayName).value(),
      groupId: input.groupId ?? null,
      tags: WatchTag.listFrom(input.tags ?? []),
      memo: input.memo ?? "",
      sortOrder,
      lifecycleStatus: "active",
      createdAt: now,
      updatedAt: now
    });
  }

  public static fromDto(dto: WatchStockCardDto): WatchStockCard {
    return new WatchStockCard({
      ...dto,
      tags: [...dto.tags]
    });
  }

  public id(): string {
    return this.state.id;
  }

  public market(): string {
    return this.state.market;
  }

  public symbol(): string {
    return this.state.symbol;
  }

  public lifecycleStatus(): CardLifecycleStatus {
    return this.state.lifecycleStatus;
  }

  public hasSameMarketSymbol(market: string, symbol: string): boolean {
    return this.state.market === Market.from(market).value() &&
      this.state.symbol === StockSymbol.from(symbol).value();
  }

  public isActiveAnalysisTarget(): boolean {
    return this.state.lifecycleStatus === "active";
  }

  public isHidden(): boolean {
    return this.state.lifecycleStatus === "hidden";
  }

  public isArchived(): boolean {
    return this.state.lifecycleStatus === "archived";
  }

  public hide(now: string): void {
    this.changeLifecycleStatus("hidden", now);
  }

  public archive(now: string): void {
    this.changeLifecycleStatus("archived", now);
  }

  public restore(now: string): void {
    this.changeLifecycleStatus("active", now);
  }

  public updateDetails(input: {
    displayName?: string;
    groupId?: string | null;
    tags?: readonly string[];
    memo?: string;
    now: string;
  }): void {
    if (input.displayName !== undefined) {
      this.state.displayName = DisplayName.from(input.displayName).value();
    }

    if (input.groupId !== undefined) {
      this.state.groupId = input.groupId;
    }

    if (input.tags !== undefined) {
      this.state.tags = WatchTag.listFrom(input.tags);
    }

    if (input.memo !== undefined) {
      this.state.memo = input.memo;
    }

    this.state.updatedAt = input.now;
  }

  public reorder(sortOrder: number, now: string): void {
    this.state.sortOrder = SortOrder.from(sortOrder).value();
    this.state.updatedAt = now;
  }

  public toDto(): WatchStockCardDto {
    return {
      ...this.state,
      tags: [...this.state.tags]
    };
  }

  private changeLifecycleStatus(lifecycleStatus: CardLifecycleStatus, now: string): void {
    this.state.lifecycleStatus = lifecycleStatus;
    this.state.updatedAt = now;
  }
}

export class Watchlist {
  private constructor(
    private readonly cards: WatchStockCard[],
    private readonly groups: WatchGroupDto[]
  ) {}

  public static empty(): Watchlist {
    return new Watchlist([], []);
  }

  public static fromDto(dto: WatchlistDto): Watchlist {
    return new Watchlist(
      dto.cards.map((card) => WatchStockCard.fromDto(card)),
      dto.groups.map((group) => ({ ...group }))
    );
  }

  public createCard(input: CreateWatchStockCardInput): CreateWatchStockCardResult {
    const existingCard = this.findByMarketSymbol(input.market, input.symbol);

    if (existingCard?.isArchived() === true) {
      return {
        type: "restore-available",
        archivedCardId: existingCard.id()
      };
    }

    if (existingCard !== undefined) {
      return {
        type: "duplicate-card",
        existingCardId: existingCard.id()
      };
    }

    const card = WatchStockCard.create(input, this.nextSortOrder());
    this.cards.push(card);

    return {
      type: "created",
      card: card.toDto()
    };
  }

  public updateCard(
    cardId: string,
    input: {
      displayName?: string;
      groupId?: string | null;
      tags?: readonly string[];
      memo?: string;
      now: string;
    }
  ): WatchStockCardDto | undefined {
    const card = this.findById(cardId);

    if (card === undefined) {
      return undefined;
    }

    card.updateDetails(input);

    return card.toDto();
  }

  public hideCard(cardId: string, now: string): WatchStockCardDto | undefined {
    const card = this.findById(cardId);

    if (card === undefined) {
      return undefined;
    }

    card.hide(now);

    return card.toDto();
  }

  public archiveCard(cardId: string, now: string): WatchStockCardDto | undefined {
    const card = this.findById(cardId);

    if (card === undefined) {
      return undefined;
    }

    card.archive(now);

    return card.toDto();
  }

  public restoreCard(cardId: string, now: string): WatchStockCardDto | undefined {
    const card = this.findById(cardId);

    if (card === undefined) {
      return undefined;
    }

    card.restore(now);

    return card.toDto();
  }

  public deleteCard(cardId: string): void {
    const cardIndex = this.cards.findIndex((card) => card.id() === cardId);

    if (cardIndex >= 0) {
      this.cards.splice(cardIndex, 1);
    }
  }

  public reorderActiveCards(orderedCardIds: readonly string[], now: string): WatchStockCardDto[] {
    const activeCardsById = new Map(
      this.cards
        .filter((card) => card.isActiveAnalysisTarget())
        .map((card) => [card.id(), card])
    );

    orderedCardIds.forEach((cardId, index) => {
      activeCardsById.get(cardId)?.reorder(index + 1, now);
    });

    return this.listActiveCards();
  }

  public listActiveCards(): WatchStockCardDto[] {
    return this.cards
      .filter((card) => card.isActiveAnalysisTarget())
      .map((card) => card.toDto())
      .sort(compareBySortOrder);
  }

  public listHiddenCards(): WatchStockCardDto[] {
    return this.cards
      .filter((card) => card.isHidden())
      .map((card) => card.toDto())
      .sort(compareBySortOrder);
  }

  public listArchivedCards(): WatchStockCardDto[] {
    return this.cards
      .filter((card) => card.isArchived())
      .map((card) => card.toDto())
      .sort(compareBySortOrder);
  }

  public toDto(): WatchlistDto {
    return {
      cards: this.cards.map((card) => card.toDto()),
      groups: this.groups.map((group) => ({ ...group }))
    };
  }

  private findById(cardId: string): WatchStockCard | undefined {
    return this.cards.find((card) => card.id() === cardId);
  }

  private findByMarketSymbol(market: string, symbol: string): WatchStockCard | undefined {
    return this.cards.find((card) => card.hasSameMarketSymbol(market, symbol));
  }

  private nextSortOrder(): number {
    return this.cards.reduce(
      (maxSortOrder, card) => Math.max(maxSortOrder, card.toDto().sortOrder),
      0
    ) + 1;
  }
}

class Market {
  private constructor(private readonly marketValue: string) {}

  public static from(value: string): Market {
    const market = value.trim().toUpperCase();

    if (market === "") {
      throw new Error("Market is required");
    }

    return new Market(market);
  }

  public value(): string {
    return this.marketValue;
  }
}

class StockSymbol {
  private constructor(private readonly symbolValue: string) {}

  public static from(value: string): StockSymbol {
    const symbol = value.trim().toUpperCase();

    if (!/^[A-Z0-9.-]+$/.test(symbol)) {
      throw new Error("Stock symbol supports letters, numbers, '.', and '-' only");
    }

    return new StockSymbol(symbol);
  }

  public value(): string {
    return this.symbolValue;
  }
}

class DisplayName {
  private constructor(private readonly displayNameValue: string) {}

  public static from(value: string): DisplayName {
    const displayName = value.trim();

    if (displayName === "") {
      throw new Error("Display name is required");
    }

    return new DisplayName(displayName);
  }

  public value(): string {
    return this.displayNameValue;
  }
}

class WatchTag {
  public static listFrom(values: readonly string[]): string[] {
    return values
      .map((value) => value.trim())
      .filter((value) => value !== "");
  }
}

class SortOrder {
  private constructor(private readonly sortOrderValue: number) {}

  public static from(value: number): SortOrder {
    if (!Number.isInteger(value) || value < 1) {
      throw new Error("Sort order must be a positive integer");
    }

    return new SortOrder(value);
  }

  public value(): number {
    return this.sortOrderValue;
  }
}

function compareBySortOrder(left: WatchStockCardDto, right: WatchStockCardDto): number {
  return left.sortOrder - right.sortOrder;
}
