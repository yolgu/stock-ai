import {
  APP_RUNTIME_CONTRACT,
  createAppRequest,
  isAppErrorEnvelope,
  isAppResponseEnvelope,
  type AppRequestEvent,
  type AppResponseEvent
} from "../../shared/contracts/app-runtime-contract";
import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi,
  RuntimeProfileClientClock
} from "./NeutralinoRuntimeProfileClient";
import { RuntimeProfileClientError } from "./NeutralinoRuntimeProfileClient";

export interface NeutralinoAppRequestClientOptions {
  extensions: NeutralinoExtensionsApi;
  events: NeutralinoEventsApi;
  clock?: RuntimeProfileClientClock;
  timeoutMs?: number;
}

export interface SendAppRequestInput<
  RequestEvent extends AppRequestEvent,
  ResponseEvent extends AppResponseEvent,
  RequestPayload
> {
  requestEvent: RequestEvent;
  responseEvent: ResponseEvent;
  payload: RequestPayload;
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

export class NeutralinoAppRequestClient {
  private readonly clock: RuntimeProfileClientClock;
  private readonly timeoutMs: number;

  public constructor(private readonly options: NeutralinoAppRequestClientOptions) {
    this.clock = options.clock ?? defaultClock;
    this.timeoutMs = options.timeoutMs ?? 5000;
  }

  public async send<
    RequestEvent extends AppRequestEvent,
    ResponseEvent extends AppResponseEvent,
    RequestPayload,
    ResponsePayload
  >(
    input: SendAppRequestInput<RequestEvent, ResponseEvent, RequestPayload>
  ): Promise<ResponsePayload> {
    const request = createAppRequest({
      event: input.requestEvent,
      requestId: this.clock.nextRequestId(),
      occurredAt: this.clock.nowIso(),
      payload: input.payload
    });
    const response = this.waitForResponse<ResponsePayload>(
      request.requestId,
      input.responseEvent
    );

    try {
      await this.options.extensions.dispatch(
        APP_RUNTIME_CONTRACT.extensionId,
        request.event,
        request
      );
    } catch (error) {
      throw new RuntimeProfileClientError(
        "extension_unavailable",
        error instanceof Error ? error.message : "extension is unavailable",
        true
      );
    }

    return response;
  }

  private async waitForResponse<ResponsePayload>(
    requestId: string,
    responseEvent: AppResponseEvent
  ): Promise<ResponsePayload> {
    return new Promise<ResponsePayload>((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        void detachListeners();
        reject(
          new RuntimeProfileClientError(
            "extension_unavailable",
            "extension response timed out",
            true
          )
        );
      }, this.timeoutMs);

      const handleResponse = (event: { detail: unknown }): void => {
        if (
          isAppResponseEnvelope(event.detail) &&
          event.detail.event === responseEvent &&
          event.detail.requestId === requestId
        ) {
          window.clearTimeout(timeoutId);
          void detachListeners();
          resolve(event.detail.payload as ResponsePayload);
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
        await this.options.events.off(responseEvent, handleResponse);
        await this.options.events.off(APP_RUNTIME_CONTRACT.events.appError, handleError);
      };

      void this.options.events.on(responseEvent, handleResponse);
      void this.options.events.on(APP_RUNTIME_CONTRACT.events.appError, handleError);
    });
  }
}
