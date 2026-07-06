import { describe, expect, it } from "vitest";

import {
  APP_RUNTIME_CONTRACT,
  createAppRequest,
  createAppResponse,
  createTossCredentialStatusPayload,
  isAppResponseEnvelope,
  parseAppRequest
} from "./app-runtime-contract";

describe("watchlist and settings IPC contract", () => {
  it("centralizes watchlist and Toss settings event names", () => {
    expect(APP_RUNTIME_CONTRACT.events.watchlistCreateRequest).toBe(
      "watchlist:create:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.tossCredentialsSaveRequest).toBe(
      "settings:toss-credentials:save"
    );
    expect(APP_RUNTIME_CONTRACT.events.tossConnectionTestRequest).toBe(
      "settings:toss-connection:test"
    );
  });

  it("creates generic request and response envelopes with requestId", () => {
    const request = createAppRequest({
      event: "watchlist:list:request",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z",
      payload: {}
    });
    const response = createAppResponse({
      event: "watchlist:list:response",
      requestId: request.requestId,
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        activeCards: [],
        hiddenCards: [],
        archivedCards: []
      }
    });

    expect(response).toEqual({
      event: "watchlist:list:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        activeCards: [],
        hiddenCards: [],
        archivedCards: []
      }
    });
    expect(isAppResponseEnvelope(response)).toBe(true);
  });

  it("converts a request without requestId into a structured error", () => {
    const parsed = parseAppRequest(
      {
        event: "watchlist:create:request",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: {}
      },
      "2026-07-06T09:00:01.000Z"
    );

    expect(parsed).toEqual({
      ok: false,
      error: {
        event: "app:error",
        requestId: "unavailable",
        occurredAt: "2026-07-06T09:00:01.000Z",
        error: {
          code: "invalid_request",
          message: "request requires requestId",
          recoverable: true
        }
      }
    });
  });

  it("never exposes Toss client secret in credential status payloads", () => {
    const payload = createTossCredentialStatusPayload({
      clientId: "client_fixture_1234567890",
      configured: true,
      lastValidatedAt: "2026-07-06T09:00:00.000Z",
      connectionStatus: "valid"
    });

    expect(payload).toEqual({
      configured: true,
      maskedClientId: "clie…7890",
      lastValidatedAt: "2026-07-06T09:00:00.000Z",
      connectionStatus: "valid"
    });
    expect(JSON.stringify(payload)).not.toContain("secret");
  });
});
