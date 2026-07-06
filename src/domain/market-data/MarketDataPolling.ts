import type { WatchStockCardDto } from "../watchlist/Watchlist";

export type MarketDataPollingSession = "pre" | "regular" | "after" | "closed" | "holiday";
export type MarketDataPollingCountry = "KR" | "US";

export interface MarketDataPollingWatchlist {
  activeCards: WatchStockCardDto[];
  hiddenCards: WatchStockCardDto[];
  archivedCards: WatchStockCardDto[];
}

export interface CreateMarketDataPollingPlanInput {
  watchlist: MarketDataPollingWatchlist;
  visibleCardIds: readonly string[];
  marketSession: MarketDataPollingSession;
}

const regularSessionDelayMs = 15_000;
const closedSessionDelayMs = 300_000;
const koreanMarkets = new Set(["KOSPI", "KOSDAQ", "KONEX", "KRX"]);

export class MarketDataPollingPlan {
  private constructor(
    private readonly prioritizedCards: WatchStockCardDto[],
    private readonly pollingSession: MarketDataPollingSession
  ) {}

  public static create(input: CreateMarketDataPollingPlanInput): MarketDataPollingPlan {
    const visibleCardIdSet = new Set(input.visibleCardIds);
    const sortedCards = [...input.watchlist.activeCards].sort((left, right) => {
      const leftVisibleIndex = input.visibleCardIds.indexOf(left.id);
      const rightVisibleIndex = input.visibleCardIds.indexOf(right.id);
      const leftIsVisible = visibleCardIdSet.has(left.id);
      const rightIsVisible = visibleCardIdSet.has(right.id);

      if (leftIsVisible && rightIsVisible) {
        return leftVisibleIndex - rightVisibleIndex;
      }

      if (leftIsVisible) {
        return -1;
      }

      if (rightIsVisible) {
        return 1;
      }

      return left.sortOrder - right.sortOrder;
    });

    return new MarketDataPollingPlan(sortedCards, input.marketSession);
  }

  public cardsToPoll(): WatchStockCardDto[] {
    return this.prioritizedCards.map((card) => ({ ...card, tags: [...card.tags] }));
  }

  public symbolsForPriceBatch(): string[] {
    return this.prioritizedCards.map((card) => card.symbol);
  }

  public marketCountries(): MarketDataPollingCountry[] {
    const countries = new Set<MarketDataPollingCountry>();

    this.prioritizedCards.forEach((card) => {
      countries.add(resolveMarketCountry(card.market));
    });

    return [...countries];
  }

  public nextPollDelayMs(): number {
    if (this.pollingSession === "closed" || this.pollingSession === "holiday") {
      return closedSessionDelayMs;
    }

    return regularSessionDelayMs;
  }
}

export function resolveMarketCountry(market: string): MarketDataPollingCountry {
  return koreanMarkets.has(market.trim().toUpperCase()) ? "KR" : "US";
}
