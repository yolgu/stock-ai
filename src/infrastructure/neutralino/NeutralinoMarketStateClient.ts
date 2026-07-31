import {
  APP_RUNTIME_CONTRACT,
  isMarketStateHistoryPayload,
  isMarketStateLatestSnapshotsPayload,
  isMarketStateRefreshPayload,
  isMarketStateTraceResponsePayload,
  type MarketStateHistoryPayload,
  type MarketStateLatestSnapshotsPayload,
  type MarketStateRefreshPayload,
  type MarketStateTraceResponsePayload,
  type ReadLatestMarketStateSnapshotsPayload,
  type ReadMarketStateHistoryPayload,
  type ReadMarketStateTracePayload,
  type RefreshMarketStateForWatchlistPayload
} from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";
import { RuntimeProfileClientError } from "./NeutralinoRuntimeProfileClient";

export interface MarketStateClient {
  refreshWatchlist(
    input: RefreshMarketStateForWatchlistPayload
  ): Promise<MarketStateRefreshPayload>;
  readLatestSnapshots(
    input: ReadLatestMarketStateSnapshotsPayload
  ): Promise<MarketStateLatestSnapshotsPayload>;
  readTrace(
    input: ReadMarketStateTracePayload
  ): Promise<MarketStateTraceResponsePayload>;
  readHistory(
    input: ReadMarketStateHistoryPayload
  ): Promise<MarketStateHistoryPayload>;
}

export class NeutralinoMarketStateClient implements MarketStateClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async refreshWatchlist(
    input: RefreshMarketStateForWatchlistPayload
  ): Promise<MarketStateRefreshPayload> {
    const payload: unknown = await this.requestClient.send({
      requestEvent:
        APP_RUNTIME_CONTRACT.events.marketStateRefreshWatchlistRequest,
      responseEvent:
        APP_RUNTIME_CONTRACT.events.marketStateRefreshWatchlistResponse,
      payload: input
    });

    if (!isMarketStateRefreshPayload(payload)) {
      throw invalidMarketStatePayload();
    }

    return payload;
  }

  public async readLatestSnapshots(
    input: ReadLatestMarketStateSnapshotsPayload
  ): Promise<MarketStateLatestSnapshotsPayload> {
    const payload: unknown = await this.requestClient.send({
      requestEvent:
        APP_RUNTIME_CONTRACT.events.marketStateLatestSnapshotsRequest,
      responseEvent:
        APP_RUNTIME_CONTRACT.events.marketStateLatestSnapshotsResponse,
      payload: input
    });

    if (!isMarketStateLatestSnapshotsPayload(payload)) {
      throw invalidMarketStatePayload();
    }

    return payload;
  }

  public async readTrace(
    input: ReadMarketStateTracePayload
  ): Promise<MarketStateTraceResponsePayload> {
    const payload: unknown = await this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.marketStateTraceRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.marketStateTraceResponse,
      payload: input
    });

    if (!isMarketStateTraceResponsePayload(payload)) {
      throw invalidMarketStatePayload();
    }

    return payload;
  }

  public async readHistory(
    input: ReadMarketStateHistoryPayload
  ): Promise<MarketStateHistoryPayload> {
    const payload: unknown = await this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.marketStateHistoryRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.marketStateHistoryResponse,
      payload: input
    });

    if (!isMarketStateHistoryPayload(payload)) {
      throw invalidMarketStatePayload();
    }

    return payload;
  }
}

function invalidMarketStatePayload(): RuntimeProfileClientError {
  return new RuntimeProfileClientError(
    "market_state_calculation_failed",
    "market-state response failed runtime validation",
    true
  );
}
