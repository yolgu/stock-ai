import { describe, expect, it } from "vitest";

import type { RuntimeProfileDto } from "../../domain/runtime/AppRuntimeProfile";
import {
  APP_RUNTIME_CONTRACT,
  createAppError,
  createRuntimeProfileResponse
} from "../../shared/contracts/app-runtime-contract";
import {
  NeutralinoRuntimeProfileClient,
  RuntimeProfileClientError,
  type NeutralinoEventsApi,
  type NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";

class CapturingExtensionsApi implements NeutralinoExtensionsApi {
  public readonly dispatched: Array<{
    extensionId: string;
    eventName: string;
    data: unknown;
  }> = [];

  public async dispatch(
    extensionId: string,
    eventName: string,
    data: unknown
  ): Promise<void> {
    this.dispatched.push({ extensionId, eventName, data });
  }
}

class ManualEventsApi implements NeutralinoEventsApi {
  private readonly listeners = new Map<string, Set<(event: { detail: unknown }) => void>>();

  public async on(
    eventName: string,
    handler: (event: { detail: unknown }) => void
  ): Promise<void> {
    const listeners = this.listeners.get(eventName) ?? new Set();
    listeners.add(handler);
    this.listeners.set(eventName, listeners);
  }

  public async off(
    eventName: string,
    handler: (event: { detail: unknown }) => void
  ): Promise<void> {
    this.listeners.get(eventName)?.delete(handler);
  }

  public emit(eventName: string, detail: unknown): void {
    for (const listener of this.listeners.get(eventName) ?? []) {
      listener({ detail });
    }
  }
}

const readyProfile: RuntimeProfileDto = {
  runtimeMode: "desktop",
  marketDataMode: "notConfigured",
  capabilities: [
    {
      name: "watchlist",
      enabled: true,
      reason: "관심종목 목록 기능 준비됨"
    }
  ]
};

describe("NeutralinoRuntimeProfileClient", () => {
  it("dispatches a typed runtime profile request and resolves the matching response", async () => {
    const extensions = new CapturingExtensionsApi();
    const events = new ManualEventsApi();
    const client = new NeutralinoRuntimeProfileClient({
      extensions,
      events,
      clock: {
        nowIso: (): string => "2026-07-06T09:00:00.000Z",
        nextRequestId: (): string => "request-1"
      },
      timeoutMs: 1000
    });

    const result = client.loadRuntimeProfile();

    expect(extensions.dispatched).toEqual([
      {
        extensionId: "app.stockSub.runtime",
        eventName: "app:runtime-profile:request",
        data: {
          event: "app:runtime-profile:request",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {}
        }
      }
    ]);

    events.emit(
      APP_RUNTIME_CONTRACT.events.runtimeProfileResponse,
      createRuntimeProfileResponse({
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: readyProfile
      })
    );

    await expect(result).resolves.toEqual(readyProfile);
  });

  it("rejects with a typed runtime profile client error from app:error", async () => {
    const extensions = new CapturingExtensionsApi();
    const events = new ManualEventsApi();
    const client = new NeutralinoRuntimeProfileClient({
      extensions,
      events,
      clock: {
        nowIso: (): string => "2026-07-06T09:00:00.000Z",
        nextRequestId: (): string => "request-1"
      },
      timeoutMs: 1000
    });

    const result = client.loadRuntimeProfile();

    events.emit(
      APP_RUNTIME_CONTRACT.events.appError,
      createAppError({
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        code: "extension_unavailable",
        message: "runtime extension is unavailable",
        recoverable: true
      })
    );

    await expect(result).rejects.toEqual(
      new RuntimeProfileClientError(
        "extension_unavailable",
        "runtime extension is unavailable",
        true
      )
    );
  });
});
