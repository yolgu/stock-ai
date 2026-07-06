import type { RuntimeProfileDto } from "../../domain/runtime/AppRuntimeProfile";
import {
  APP_RUNTIME_CONTRACT,
  createRuntimeProfileRequest,
  isAppErrorEnvelope,
  isRuntimeProfileResponseEnvelope
} from "../../shared/contracts/app-runtime-contract";

export interface NeutralinoExtensionsApi {
  dispatch(extensionId: string, eventName: string, data: unknown): Promise<unknown>;
}

export interface NeutralinoEventsApi {
  on(eventName: string, handler: (event: { detail: unknown }) => void): Promise<unknown>;
  off(eventName: string, handler: (event: { detail: unknown }) => void): Promise<unknown>;
}

export interface RuntimeProfileClient {
  loadRuntimeProfile(): Promise<RuntimeProfileDto>;
}

export interface RuntimeProfileClientClock {
  nowIso(): string;
  nextRequestId(): string;
}

export interface NeutralinoRuntimeProfileClientOptions {
  extensions: NeutralinoExtensionsApi;
  events: NeutralinoEventsApi;
  clock?: RuntimeProfileClientClock;
  timeoutMs?: number;
}

export class RuntimeProfileClientError extends Error {
  public constructor(
    public readonly code: string,
    message: string,
    public readonly recoverable: boolean
  ) {
    super(message);
    this.name = "RuntimeProfileClientError";
  }
}

const defaultClock: RuntimeProfileClientClock = {
  nowIso: (): string => new Date().toISOString(),
  nextRequestId: (): string => {
    if (globalThis.crypto?.randomUUID !== undefined) {
      return globalThis.crypto.randomUUID();
    }

    return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
};

export class NeutralinoRuntimeProfileClient implements RuntimeProfileClient {
  private readonly clock: RuntimeProfileClientClock;
  private readonly timeoutMs: number;

  public constructor(private readonly options: NeutralinoRuntimeProfileClientOptions) {
    this.clock = options.clock ?? defaultClock;
    this.timeoutMs = options.timeoutMs ?? 5000;
  }

  public async loadRuntimeProfile(): Promise<RuntimeProfileDto> {
    const request = createRuntimeProfileRequest({
      requestId: this.clock.nextRequestId(),
      occurredAt: this.clock.nowIso()
    });
    const response = this.waitForRuntimeProfileResponse(request.requestId);

    try {
      await this.options.extensions.dispatch(
        APP_RUNTIME_CONTRACT.extensionId,
        request.event,
        request
      );
    } catch (error) {
      throw new RuntimeProfileClientError(
        "extension_unavailable",
        error instanceof Error ? error.message : "runtime extension is unavailable",
        true
      );
    }

    return response;
  }

  private async waitForRuntimeProfileResponse(requestId: string): Promise<RuntimeProfileDto> {
    return new Promise<RuntimeProfileDto>((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        void detachListeners();
        reject(
          new RuntimeProfileClientError(
            "runtime_profile_unavailable",
            "runtime profile response timed out",
            true
          )
        );
      }, this.timeoutMs);

      const handleResponse = (event: { detail: unknown }): void => {
        if (
          isRuntimeProfileResponseEnvelope(event.detail) &&
          event.detail.requestId === requestId
        ) {
          window.clearTimeout(timeoutId);
          void detachListeners();
          resolve(event.detail.payload);
        }
      };

      const handleError = (event: { detail: unknown }): void => {
        if (isAppErrorEnvelope(event.detail) && event.detail.requestId === requestId) {
          window.clearTimeout(timeoutId);
          void detachListeners();
          reject(
            new RuntimeProfileClientError(
              event.detail.error.code,
              event.detail.error.message,
              event.detail.error.recoverable
            )
          );
        }
      };

      const detachListeners = async (): Promise<void> => {
        await this.options.events.off(
          APP_RUNTIME_CONTRACT.events.runtimeProfileResponse,
          handleResponse
        );
        await this.options.events.off(APP_RUNTIME_CONTRACT.events.appError, handleError);
      };

      void this.options.events.on(
        APP_RUNTIME_CONTRACT.events.runtimeProfileResponse,
        handleResponse
      );
      void this.options.events.on(APP_RUNTIME_CONTRACT.events.appError, handleError);
    });
  }
}
