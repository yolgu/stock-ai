import type {
  CreateVerifiedWatchCardPayload,
  StockReferenceVerificationPayload
} from "../../shared/contracts/app-runtime-contract";
import { APP_RUNTIME_CONTRACT } from "../../shared/contracts/app-runtime-contract";
import type { CreateWatchCardResponse } from "./NeutralinoWatchlistClient";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";

export interface VerifyStockReferencePayload {
  rawInput: string;
}

export type CreateVerifiedWatchCardResponse = CreateWatchCardResponse;

export interface StockReferenceClient {
  verify(input: VerifyStockReferencePayload): Promise<StockReferenceVerificationPayload>;
  createVerifiedCard(
    input: CreateVerifiedWatchCardPayload
  ): Promise<CreateVerifiedWatchCardResponse>;
}

export class NeutralinoStockReferenceClient implements StockReferenceClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async verify(
    input: VerifyStockReferencePayload
  ): Promise<StockReferenceVerificationPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.stockReferenceVerifyRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.stockReferenceVerifyResponse,
      payload: input
    });
  }

  public async createVerifiedCard(
    input: CreateVerifiedWatchCardPayload
  ): Promise<CreateVerifiedWatchCardResponse> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.watchlistCreateVerifiedRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.watchlistCreateVerifiedResponse,
      payload: input
    });
  }
}
