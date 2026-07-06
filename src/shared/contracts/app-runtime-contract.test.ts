import { describe, expect, it } from "vitest";

import {
  APP_RUNTIME_CONTRACT,
  createAppError,
  createRuntimeProfileRequest,
  createRuntimeProfileResponse,
  parseRuntimeProfileRequest
} from "./app-runtime-contract";

describe("app runtime IPC contract", () => {
  it("creates a runtime profile request envelope", () => {
    const request = createRuntimeProfileRequest({
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z"
    });

    expect(request).toEqual({
      event: "app:runtime-profile:request",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z",
      payload: {}
    });
    expect(APP_RUNTIME_CONTRACT.extensionId).toBe("app.stockSub.runtime");
  });

  it("creates a runtime profile response envelope", () => {
    const response = createRuntimeProfileResponse({
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        runtimeMode: "desktop",
        marketDataMode: "notConfigured",
        capabilities: []
      }
    });

    expect(response).toEqual({
      event: "app:runtime-profile:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        runtimeMode: "desktop",
        marketDataMode: "notConfigured",
        capabilities: []
      }
    });
  });

  it("converts a request without requestId into a structured error", () => {
    const parsed = parseRuntimeProfileRequest(
      {
        event: "app:runtime-profile:request",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: {}
      },
      "2026-07-06T09:00:02.000Z"
    );

    expect(parsed).toEqual({
      ok: false,
      error: {
        event: "app:error",
        requestId: "unavailable",
        occurredAt: "2026-07-06T09:00:02.000Z",
        error: {
          code: "invalid_request",
          message: "runtime profile request requires requestId",
          recoverable: true
        }
      }
    });
  });

  it("creates a typed app error envelope", () => {
    expect(
      createAppError({
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:03.000Z",
        code: "extension_unavailable",
        message: "runtime extension is unavailable",
        recoverable: true
      })
    ).toEqual({
      event: "app:error",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:03.000Z",
      error: {
        code: "extension_unavailable",
        message: "runtime extension is unavailable",
        recoverable: true
      }
    });
  });
});
