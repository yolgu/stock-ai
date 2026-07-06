import { describe, expect, it } from "vitest";

import type {
  NeutralinoEventsApi,
  NeutralinoExtensionsApi
} from "./NeutralinoRuntimeProfileClient";
import { NeutralinoTossSettingsClient } from "./NeutralinoTossSettingsClient";

describe("NeutralinoTossSettingsClient", () => {
  it("saves credentials and resolves only masked credential status", async () => {
    const eventListeners = new Map<string, (event: { detail: unknown }) => void>();
    const dispatches: Array<{ eventName: string; data: unknown }> = [];
    const extensions: NeutralinoExtensionsApi = {
      dispatch: async (_extensionId, eventName, data): Promise<unknown> => {
        dispatches.push({ eventName, data });
        return undefined;
      }
    };
    const events: NeutralinoEventsApi = {
      on: async (eventName, handler): Promise<unknown> => {
        eventListeners.set(eventName, handler);
        return undefined;
      },
      off: async (eventName): Promise<unknown> => {
        eventListeners.delete(eventName);
        return undefined;
      }
    };
    const client = new NeutralinoTossSettingsClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-1"
      }
    });

    const result = client.saveCredentials({
      clientId: "client_fixture_1234567890",
      clientSecret: "secret_fixture_super_secret"
    });

    expect(dispatches).toEqual([
      {
        eventName: "settings:toss-credentials:save",
        data: {
          event: "settings:toss-credentials:save",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {
            clientId: "client_fixture_1234567890",
            clientSecret: "secret_fixture_super_secret"
          }
        }
      }
    ]);

    eventListeners.get("settings:toss-credentials:save:response")?.({
      detail: {
        event: "settings:toss-credentials:save:response",
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          configured: true,
          maskedClientId: "clie…7890",
          lastValidatedAt: null,
          connectionStatus: "saved"
        }
      }
    });

    await expect(result).resolves.toEqual({
      configured: true,
      maskedClientId: "clie…7890",
      lastValidatedAt: null,
      connectionStatus: "saved"
    });
  });

  it("runs a Toss connection test through the extension boundary", async () => {
    const eventListeners = new Map<string, (event: { detail: unknown }) => void>();
    const dispatches: Array<{ eventName: string; data: unknown }> = [];
    const extensions: NeutralinoExtensionsApi = {
      dispatch: async (_extensionId, eventName, data): Promise<unknown> => {
        dispatches.push({ eventName, data });
        return undefined;
      }
    };
    const events: NeutralinoEventsApi = {
      on: async (eventName, handler): Promise<unknown> => {
        eventListeners.set(eventName, handler);
        return undefined;
      },
      off: async (eventName): Promise<unknown> => {
        eventListeners.delete(eventName);
        return undefined;
      }
    };
    const client = new NeutralinoTossSettingsClient({
      extensions,
      events,
      clock: {
        nowIso: () => "2026-07-06T09:00:00.000Z",
        nextRequestId: () => "request-2"
      }
    });

    const result = client.testConnection();

    expect(dispatches[0]).toEqual({
      eventName: "settings:toss-connection:test",
      data: {
        event: "settings:toss-connection:test",
        requestId: "request-2",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: {}
      }
    });

    eventListeners.get("settings:toss-connection:test:response")?.({
      detail: {
        event: "settings:toss-connection:test:response",
        requestId: "request-2",
        occurredAt: "2026-07-06T09:00:01.000Z",
        payload: {
          configured: true,
          maskedClientId: "clie…7890",
          lastValidatedAt: "2026-07-06T09:00:01.000Z",
          connectionStatus: "valid"
        }
      }
    });

    await expect(result).resolves.toMatchObject({
      connectionStatus: "valid"
    });
  });
});
