import { describe, expect, it } from "vitest";

import type { RuntimeProfileDto } from "../../domain/runtime/AppRuntimeProfile";
import {
  APP_RUNTIME_CONTRACT,
  createRuntimeProfileResponse,
  isRuntimeProfileResponseEnvelope,
  type RuntimeProfileRequestEnvelope
} from "../../shared/contracts/app-runtime-contract";
import { createRuntimeProfileClientFromNeutralinoApi } from "./createRuntimeProfileClientFromWindow";

describe("createRuntimeProfileClientFromNeutralinoApi", () => {
  it("uses the Neutralino module API without relying on a window global", async () => {
    const dispatched: Array<{
      extensionId: string;
      eventName: string;
      data: unknown;
    }> = [];
    const eventListeners = new Map<string, (event: { detail: unknown }) => void>();
    const client = createRuntimeProfileClientFromNeutralinoApi({
      extensions: {
        dispatch: async (extensionId, eventName, data): Promise<void> => {
          dispatched.push({ extensionId, eventName, data });
        }
      },
      events: {
        on: async (eventName, handler): Promise<void> => {
          eventListeners.set(eventName, handler);
        },
        off: async (eventName): Promise<void> => {
          eventListeners.delete(eventName);
        }
      }
    });

    const loadPromise = client.loadRuntimeProfile();

    expect(dispatched[0]?.extensionId).toBe(APP_RUNTIME_CONTRACT.extensionId);
    expect(dispatched[0]?.eventName).toBe(
      APP_RUNTIME_CONTRACT.events.runtimeProfileRequest
    );
    const request = dispatched[0]?.data as RuntimeProfileRequestEnvelope;
    const profile: RuntimeProfileDto = {
      runtimeMode: "desktop",
      marketDataMode: "notConfigured",
      capabilities: []
    };
    eventListeners.get(APP_RUNTIME_CONTRACT.events.runtimeProfileResponse)?.({
      detail: createRuntimeProfileResponse({
        requestId: request.requestId,
        occurredAt: "2026-07-06T20:03:00.000Z",
        payload: profile
      })
    });

    await expect(loadPromise).resolves.toEqual(profile);
    expect(
      isRuntimeProfileResponseEnvelope(
        createRuntimeProfileResponse({
          requestId: request.requestId,
          occurredAt: "2026-07-06T20:03:00.000Z",
          payload: profile
        })
      )
    ).toBe(true);
  });
});
