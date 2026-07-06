import type {
  MarketDataLatestSnapshotsPayload,
  MarketDataRefreshCardPayload,
  MarketDataRefreshPayload,
  ReadLatestMarketDataSnapshotsPayload,
  RefreshMarketDataForCardPayload,
  RefreshMarketDataForWatchlistPayload
} from "../../shared/contracts/app-runtime-contract";
import { APP_RUNTIME_CONTRACT } from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";

export interface MarketDataClient {
  refreshWatchlist(
    input: RefreshMarketDataForWatchlistPayload
  ): Promise<MarketDataRefreshPayload>;
  refreshCard(input: RefreshMarketDataForCardPayload): Promise<MarketDataRefreshCardPayload>;
  readLatestSnapshots(
    input: ReadLatestMarketDataSnapshotsPayload
  ): Promise<MarketDataLatestSnapshotsPayload>;
}

export class NeutralinoMarketDataClient implements MarketDataClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async refreshWatchlist(
    input: RefreshMarketDataForWatchlistPayload
  ): Promise<MarketDataRefreshPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.marketDataRefreshWatchlistRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.marketDataRefreshWatchlistResponse,
      payload: input
    });
  }

  public async refreshCard(
    input: RefreshMarketDataForCardPayload
  ): Promise<MarketDataRefreshCardPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.marketDataRefreshCardRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.marketDataRefreshCardResponse,
      payload: input
    });
  }

  public async readLatestSnapshots(
    input: ReadLatestMarketDataSnapshotsPayload
  ): Promise<MarketDataLatestSnapshotsPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.marketDataLatestSnapshotsRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.marketDataLatestSnapshotsResponse,
      payload: input
    });
  }
}
