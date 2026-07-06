import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const { createAppMessageHandler } = require("./main.cjs") as {
  createAppMessageHandler: (options: {
    storageDirectory: string;
    fetcher?: typeof fetch;
  }) => (rawMessage: string, nowIso: () => string) => Promise<unknown | undefined>;
};

let tempDirectory: string | undefined;

async function createStorageDirectory(): Promise<string> {
  tempDirectory = await mkdtemp(join(tmpdir(), "stock-sub-handler-"));

  return tempDirectory;
}

afterEach(async () => {
  if (tempDirectory !== undefined) {
    await rm(tempDirectory, { recursive: true, force: true });
    tempDirectory = undefined;
  }
});

describe("app extension message handler", () => {
  it("handles watchlist create and list events through JSON persistence", async () => {
    const handler = createAppMessageHandler({
      storageDirectory: await createStorageDirectory()
    });

    const created = await handler(
      JSON.stringify({
        event: "watchlist:create:request",
        data: {
          event: "watchlist:create:request",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {
            id: "card-1",
            market: "NASDAQ",
            symbol: "mu",
            displayName: "MU 마이크론",
            groupId: null,
            tags: ["반도체"],
            memo: ""
          }
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );
    const listed = await handler(
      JSON.stringify({
        event: "watchlist:list:request",
        data: {
          event: "watchlist:list:request",
          requestId: "request-2",
          occurredAt: "2026-07-06T09:00:02.000Z",
          payload: {}
        }
      }),
      () => "2026-07-06T09:00:03.000Z"
    );

    expect(created).toEqual({
      event: "watchlist:create:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: expect.objectContaining({
        type: "created",
        card: expect.objectContaining({
          id: "card-1",
          symbol: "MU"
        })
      })
    });
    expect(listed).toEqual({
      event: "watchlist:list:response",
      requestId: "request-2",
      occurredAt: "2026-07-06T09:00:03.000Z",
      payload: {
        activeCards: [
          expect.objectContaining({
            id: "card-1",
            symbol: "MU"
          })
        ],
        hiddenCards: [],
        archivedCards: []
      }
    });
  });

  it("handles Toss credential save and connection test without returning secrets", async () => {
    const fetcher = async (): Promise<Response> =>
      new Response(
        JSON.stringify({
          access_token: "access-token-that-must-not-leak",
          token_type: "Bearer",
          expires_in: 86400
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    const handler = createAppMessageHandler({
      storageDirectory: await createStorageDirectory(),
      fetcher
    });

    const saved = await handler(
      JSON.stringify({
        event: "settings:toss-credentials:save",
        data: {
          event: "settings:toss-credentials:save",
          requestId: "request-1",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {
            clientId: "client_fixture_1234567890",
            clientSecret: "secret_fixture_super_secret"
          }
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );
    const tested = await handler(
      JSON.stringify({
        event: "settings:toss-connection:test",
        data: {
          event: "settings:toss-connection:test",
          requestId: "request-2",
          occurredAt: "2026-07-06T09:00:02.000Z",
          payload: {}
        }
      }),
      () => "2026-07-06T09:00:03.000Z"
    );

    expect(JSON.stringify(saved)).not.toContain("super_secret");
    expect(JSON.stringify(tested)).not.toContain("access-token-that-must-not-leak");
    expect(saved).toEqual({
      event: "settings:toss-credentials:save:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        configured: true,
        maskedClientId: "clie…7890",
        lastValidatedAt: null,
        connectionStatus: "saved"
      }
    });
    expect(tested).toEqual({
      event: "settings:toss-connection:test:response",
      requestId: "request-2",
      occurredAt: "2026-07-06T09:00:03.000Z",
      payload: {
        configured: true,
        maskedClientId: "clie…7890",
        lastValidatedAt: "2026-07-06T09:00:03.000Z",
        connectionStatus: "valid"
      }
    });
  });
});
