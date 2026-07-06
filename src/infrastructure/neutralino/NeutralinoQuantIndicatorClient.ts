import type {
  QuantIndicatorLatestSnapshotsPayload,
  QuantIndicatorRefreshCardPayload,
  QuantIndicatorRefreshPayload,
  ReadLatestQuantIndicatorSnapshotsPayload,
  RefreshQuantIndicatorsForCardPayload,
  RefreshQuantIndicatorsForWatchlistPayload
} from "../../shared/contracts/app-runtime-contract";
import { APP_RUNTIME_CONTRACT } from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";

export interface QuantIndicatorClient {
  refreshWatchlist(
    input: RefreshQuantIndicatorsForWatchlistPayload
  ): Promise<QuantIndicatorRefreshPayload>;
  refreshCard(
    input: RefreshQuantIndicatorsForCardPayload
  ): Promise<QuantIndicatorRefreshCardPayload>;
  readLatestSnapshots(
    input: ReadLatestQuantIndicatorSnapshotsPayload
  ): Promise<QuantIndicatorLatestSnapshotsPayload>;
}

export class NeutralinoQuantIndicatorClient implements QuantIndicatorClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async refreshWatchlist(
    input: RefreshQuantIndicatorsForWatchlistPayload
  ): Promise<QuantIndicatorRefreshPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsRefreshWatchlistRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsRefreshWatchlistResponse,
      payload: input
    });
  }

  public async refreshCard(
    input: RefreshQuantIndicatorsForCardPayload
  ): Promise<QuantIndicatorRefreshCardPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsRefreshCardRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsRefreshCardResponse,
      payload: input
    });
  }

  public async readLatestSnapshots(
    input: ReadLatestQuantIndicatorSnapshotsPayload
  ): Promise<QuantIndicatorLatestSnapshotsPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsLatestSnapshotsRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.quantIndicatorsLatestSnapshotsResponse,
      payload: input
    });
  }
}
