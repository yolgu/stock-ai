import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  createDefaultRuntimeProfilePayload,
  handleRuntimeProfileMessage
} = require("./main.cjs") as {
  createDefaultRuntimeProfilePayload: () => unknown;
  handleRuntimeProfileMessage: (
    rawMessage: string,
    nowIso: () => string
  ) => unknown | undefined;
};

describe("runtime profile extension responder", () => {
  it("returns a success response for a valid runtime profile request", () => {
    const response = handleRuntimeProfileMessage(
      JSON.stringify({
        event: "app:runtime-profile:request",
        data: {
          event: "app:runtime-profile:request",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {}
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );

    expect(response).toEqual({
      event: "app:runtime-profile:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: createDefaultRuntimeProfilePayload()
    });
  });

  it("returns a structured error for a missing requestId", () => {
    const response = handleRuntimeProfileMessage(
      JSON.stringify({
        event: "app:runtime-profile:request",
        data: {
          event: "app:runtime-profile:request",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {}
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );

    expect(response).toEqual({
      event: "app:error",
      requestId: "unavailable",
      occurredAt: "2026-07-06T09:00:01.000Z",
      error: {
        code: "invalid_request",
        message: "runtime profile request requires requestId",
        recoverable: true
      }
    });
  });
});
