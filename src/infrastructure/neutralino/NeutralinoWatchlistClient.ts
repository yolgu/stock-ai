import type { WatchStockCardDto } from "../../domain/watchlist/Watchlist";
import { APP_RUNTIME_CONTRACT } from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";

export interface WatchlistListPayload {
  activeCards: WatchStockCardDto[];
  hiddenCards: WatchStockCardDto[];
  archivedCards: WatchStockCardDto[];
}

export interface CreateWatchCardPayload {
  market: string;
  symbol: string;
  displayName: string;
  groupId: string | null;
  tags: string[];
  memo: string;
}

export type CreateWatchCardResponse =
  | {
      type: "created";
      card: WatchStockCardDto;
      watchlist: WatchlistListPayload;
    }
  | {
      type: "duplicate-card";
      existingCardId: string;
      watchlist: WatchlistListPayload;
    }
  | {
      type: "restore-available";
      archivedCardId: string;
      watchlist: WatchlistListPayload;
    };

export interface WatchlistClient {
  list(): Promise<WatchlistListPayload>;
  create(input: CreateWatchCardPayload): Promise<CreateWatchCardResponse>;
  update(
    cardId: string,
    input: Partial<CreateWatchCardPayload>
  ): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }>;
  hide(cardId: string): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }>;
  archive(cardId: string): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }>;
  restore(cardId: string): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }>;
  delete(cardId: string): Promise<WatchlistListPayload>;
  reorder(orderedCardIds: string[]): Promise<WatchlistListPayload>;
}

export class NeutralinoWatchlistClient implements WatchlistClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async list(): Promise<WatchlistListPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistListRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistListResponse,
      payload: {}
    });
  }

  public async create(input: CreateWatchCardPayload): Promise<CreateWatchCardResponse> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistCreateRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistCreateResponse,
      payload: input
    });
  }

  public async update(
    cardId: string,
    input: Partial<CreateWatchCardPayload>
  ): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistUpdateRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistUpdateResponse,
      payload: {
        cardId,
        ...input
      }
    });
  }

  public async hide(
    cardId: string
  ): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistHideRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistHideResponse,
      payload: { cardId }
    });
  }

  public async archive(
    cardId: string
  ): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistArchiveRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistArchiveResponse,
      payload: { cardId }
    });
  }

  public async restore(
    cardId: string
  ): Promise<{ card: WatchStockCardDto; watchlist: WatchlistListPayload }> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistRestoreRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistRestoreResponse,
      payload: { cardId }
    });
  }

  public async delete(cardId: string): Promise<WatchlistListPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistDeleteRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistDeleteResponse,
      payload: { cardId }
    });
  }

  public async reorder(orderedCardIds: string[]): Promise<WatchlistListPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistReorderRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistReorderResponse,
      payload: { orderedCardIds }
    });
  }
}
