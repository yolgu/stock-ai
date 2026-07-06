import {
  APP_RUNTIME_CONTRACT,
  type TossCredentialStatusPayload
} from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoAppRequestClient,
  type NeutralinoAppRequestClientOptions
} from "./NeutralinoAppRequestClient";

export interface SaveTossCredentialsInput {
  clientId: string;
  clientSecret: string;
}

export interface TossSettingsClient {
  readStatus(): Promise<TossCredentialStatusPayload>;
  saveCredentials(input: SaveTossCredentialsInput): Promise<TossCredentialStatusPayload>;
  deleteCredentials(): Promise<TossCredentialStatusPayload>;
  testConnection(): Promise<TossCredentialStatusPayload>;
}

export class NeutralinoTossSettingsClient implements TossSettingsClient {
  private readonly requestClient: NeutralinoAppRequestClient;

  public constructor(options: NeutralinoAppRequestClientOptions) {
    this.requestClient = new NeutralinoAppRequestClient(options);
  }

  public async readStatus(): Promise<TossCredentialStatusPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsReadStatusRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsReadStatusResponse,
      payload: {}
    });
  }

  public async saveCredentials(
    input: SaveTossCredentialsInput
  ): Promise<TossCredentialStatusPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsSaveRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsSaveResponse,
      payload: input
    });
  }

  public async deleteCredentials(): Promise<TossCredentialStatusPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsDeleteRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.tossCredentialsDeleteResponse,
      payload: {}
    });
  }

  public async testConnection(): Promise<TossCredentialStatusPayload> {
    return this.requestClient.send({
      requestEvent: APP_RUNTIME_CONTRACT.events.tossConnectionTestRequest,
      responseEvent: APP_RUNTIME_CONTRACT.events.tossConnectionTestResponse,
      payload: {}
    });
  }
}
