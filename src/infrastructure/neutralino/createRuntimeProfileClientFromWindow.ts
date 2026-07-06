import type { RuntimeProfileDto } from "../../domain/runtime/AppRuntimeProfile";
import type { TossCredentialStatusPayload } from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoRuntimeProfileClient,
  RuntimeProfileClientError,
  type NeutralinoEventsApi,
  type NeutralinoExtensionsApi,
  type RuntimeProfileClient
} from "./NeutralinoRuntimeProfileClient";
import {
  NeutralinoMarketDataClient,
  type MarketDataClient
} from "./NeutralinoMarketDataClient";
import {
  NeutralinoQuantIndicatorClient,
  type QuantIndicatorClient
} from "./NeutralinoQuantIndicatorClient";
import {
  NeutralinoTossSettingsClient,
  type SaveTossCredentialsInput,
  type TossSettingsClient
} from "./NeutralinoTossSettingsClient";
import {
  NeutralinoWatchlistClient,
  type CreateWatchCardPayload,
  type CreateWatchCardResponse,
  type WatchlistClient,
  type WatchlistListPayload
} from "./NeutralinoWatchlistClient";
import {
  NeutralinoStockReferenceClient,
  type CreateVerifiedWatchCardResponse,
  type StockReferenceClient,
  type VerifyStockReferencePayload
} from "./NeutralinoStockReferenceClient";
import type {
  CreateVerifiedWatchCardPayload,
  StockReferenceVerificationPayload
} from "../../shared/contracts/app-runtime-contract";

export interface NeutralinoRuntimeApi {
  extensions: NeutralinoExtensionsApi;
  events: NeutralinoEventsApi;
}

interface NeutralinoWindow {
  Neutralino?: NeutralinoRuntimeApi;
}

class MissingNeutralinoRuntimeProfileClient implements RuntimeProfileClient {
  public async loadRuntimeProfile(): Promise<RuntimeProfileDto> {
    throw new RuntimeProfileClientError(
      "extension_unavailable",
      "Neutralino runtime is unavailable",
      true
    );
  }
}

class MissingNeutralinoWatchlistClient implements WatchlistClient {
  public async list(): Promise<WatchlistListPayload> {
    throw createMissingRuntimeError();
  }

  public async create(_input: CreateWatchCardPayload): Promise<CreateWatchCardResponse> {
    throw createMissingRuntimeError();
  }

  public async update(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async hide(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async archive(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async restore(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async delete(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async reorder(): Promise<never> {
    throw createMissingRuntimeError();
  }
}

class MissingNeutralinoStockReferenceClient implements StockReferenceClient {
  public async verify(
    _input: VerifyStockReferencePayload
  ): Promise<StockReferenceVerificationPayload> {
    throw createMissingRuntimeError();
  }

  public async createVerifiedCard(
    _input: CreateVerifiedWatchCardPayload
  ): Promise<CreateVerifiedWatchCardResponse> {
    throw createMissingRuntimeError();
  }
}

class MissingNeutralinoMarketDataClient implements MarketDataClient {
  public async refreshWatchlist(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async refreshCard(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async readLatestSnapshots(): Promise<never> {
    throw createMissingRuntimeError();
  }
}

class MissingNeutralinoQuantIndicatorClient implements QuantIndicatorClient {
  public async refreshWatchlist(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async refreshCard(): Promise<never> {
    throw createMissingRuntimeError();
  }

  public async readLatestSnapshots(): Promise<never> {
    throw createMissingRuntimeError();
  }
}

class MissingNeutralinoTossSettingsClient implements TossSettingsClient {
  public async readStatus(): Promise<TossCredentialStatusPayload> {
    throw createMissingRuntimeError();
  }

  public async saveCredentials(
    _input: SaveTossCredentialsInput
  ): Promise<TossCredentialStatusPayload> {
    throw createMissingRuntimeError();
  }

  public async deleteCredentials(): Promise<TossCredentialStatusPayload> {
    throw createMissingRuntimeError();
  }

  public async testConnection(): Promise<TossCredentialStatusPayload> {
    throw createMissingRuntimeError();
  }
}

export function createRuntimeProfileClientFromWindow(
  targetWindow: NeutralinoWindow = window as NeutralinoWindow
): RuntimeProfileClient {
  return createRuntimeProfileClientFromNeutralinoApi(targetWindow.Neutralino);
}

export function createRuntimeProfileClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): RuntimeProfileClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoRuntimeProfileClient();
  }

  return new NeutralinoRuntimeProfileClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

export function createWatchlistClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): WatchlistClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoWatchlistClient();
  }

  return new NeutralinoWatchlistClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

export function createTossSettingsClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): TossSettingsClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoTossSettingsClient();
  }

  return new NeutralinoTossSettingsClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

export function createStockReferenceClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): StockReferenceClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoStockReferenceClient();
  }

  return new NeutralinoStockReferenceClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

export function createMarketDataClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): MarketDataClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoMarketDataClient();
  }

  return new NeutralinoMarketDataClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

export function createQuantIndicatorClientFromNeutralinoApi(
  neutralinoApi: NeutralinoRuntimeApi | undefined
): QuantIndicatorClient {
  if (neutralinoApi === undefined) {
    return new MissingNeutralinoQuantIndicatorClient();
  }

  return new NeutralinoQuantIndicatorClient({
    extensions: neutralinoApi.extensions,
    events: neutralinoApi.events
  });
}

function createMissingRuntimeError(): RuntimeProfileClientError {
  return new RuntimeProfileClientError(
    "extension_unavailable",
    "Neutralino runtime is unavailable",
    true
  );
}
