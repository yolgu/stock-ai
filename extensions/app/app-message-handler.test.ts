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

  it("verifies pasted symbols through Toss stock info before creating a card", async () => {
    const fetcher = async (url: string | URL | Request): Promise<Response> => {
      if (String(url).endsWith("/oauth2/token")) {
        return new Response(
          JSON.stringify({
            access_token: "access-token-that-must-not-leak",
            token_type: "Bearer",
            expires_in: 86400
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          result: [
            {
              symbol: "MU",
              name: "마이크론 테크놀로지",
              englishName: "Micron Technology",
              market: "NASDAQ",
              securityType: "STOCK",
              status: "ACTIVE",
              currency: "USD",
              koreanMarketDetail: null
            }
          ]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };
    const handler = createAppMessageHandler({
      storageDirectory: await createStorageDirectory(),
      fetcher
    });

    await handler(
      JSON.stringify({
        event: "settings:toss-credentials:save",
        data: {
          event: "settings:toss-credentials:save",
          requestId: "request-save",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {
            clientId: "client_fixture_1234567890",
            clientSecret: "secret_fixture_super_secret"
          }
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );
    const verified = await handler(
      JSON.stringify({
        event: "stock-reference:verify:request",
        data: {
          event: "stock-reference:verify:request",
          requestId: "request-verify",
          occurredAt: "2026-07-06T09:00:02.000Z",
          payload: {
            rawInput: "NASDAQ:MU, ZZZZZZZZZZZZ"
          }
        }
      }),
      () => "2026-07-06T09:00:03.000Z"
    );
    const created = await handler(
      JSON.stringify({
        event: "watchlist:create-verified:request",
        data: {
          event: "watchlist:create-verified:request",
          requestId: "request-create",
          occurredAt: "2026-07-06T09:00:04.000Z",
          payload: {
            symbol: "MU",
            confirmedRisk: false,
            tags: ["반도체"],
            memo: "검증 카드",
            groupId: null
          }
        }
      }),
      () => "2026-07-06T09:00:05.000Z"
    );

    expect(verified).toEqual({
      event: "stock-reference:verify:response",
      requestId: "request-verify",
      occurredAt: "2026-07-06T09:00:03.000Z",
      payload: {
        verified: [
          expect.objectContaining({
            symbol: "MU",
            market: "NASDAQ",
            displayName: "마이크론 테크놀로지",
            requiresConfirmation: false
          })
        ],
        rejected: [
          {
            symbol: "ZZZZZZZZZZZZ",
            reason: "stock_not_found",
            message: "종목을 찾을 수 없습니다."
          }
        ]
      }
    });
    expect(created).toEqual({
      event: "watchlist:create-verified:response",
      requestId: "request-create",
      occurredAt: "2026-07-06T09:00:05.000Z",
      payload: {
        type: "created",
        card: expect.objectContaining({
          market: "NASDAQ",
          symbol: "MU",
          displayName: "마이크론 테크놀로지"
        }),
        watchlist: expect.objectContaining({
          activeCards: [
            expect.objectContaining({
              symbol: "MU"
            })
          ]
        })
      }
    });
    expect(JSON.stringify(verified)).not.toContain("access-token-that-must-not-leak");
    expect(JSON.stringify(created)).not.toContain("secret_fixture_super_secret");
  });

  it("refreshes market data for active cards without returning secrets", async () => {
    const requestedUrls: string[] = [];
    const fetcher = async (url: string | URL | Request): Promise<Response> => {
      const requestUrl = String(url);
      requestedUrls.push(requestUrl);

      if (requestUrl.endsWith("/oauth2/token")) {
        return new Response(
          JSON.stringify({
            access_token: "access-token-that-must-not-leak",
            token_type: "Bearer",
            expires_in: 86400
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (requestUrl.includes("/api/v1/prices")) {
        return new Response(
          JSON.stringify({
            result: [
              {
                symbol: "MU",
                timestamp: "2026-07-06T09:00:00.000Z",
                lastPrice: "194.93",
                currency: "USD"
              }
            ]
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (requestUrl.includes("/api/v1/trades")) {
        return new Response(
          JSON.stringify({
            result: [
              {
                price: "194.93",
                volume: "10",
                timestamp: "2026-07-06T09:00:00.000Z",
                currency: "USD"
              }
            ]
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (requestUrl.includes("/api/v1/orderbook")) {
        return new Response(
          JSON.stringify({
            result: {
              timestamp: "2026-07-06T09:00:00.000Z",
              currency: "USD",
              asks: [],
              bids: []
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (requestUrl.includes("/api/v1/candles")) {
        return new Response(
          JSON.stringify({
            result: {
              candles: [],
              nextBefore: null
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (requestUrl.includes("/api/v1/exchange-rate")) {
        return new Response(
          JSON.stringify({
            result: {
              baseCurrency: "USD",
              quoteCurrency: "KRW",
              rate: "1380.5",
              midRate: "1375",
              validFrom: "2026-07-06T09:00:00.000Z",
              validUntil: "2026-07-06T09:01:00.000Z"
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          result: {
            today: {
              date: "2026-07-06",
              regularMarket: {
                startTime: "2026-07-06T00:00:00.000Z",
                endTime: "2026-07-06T23:59:59.000Z"
              }
            },
            previousBusinessDay: { date: "2026-07-03" },
            nextBusinessDay: { date: "2026-07-07" }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };
    const handler = createAppMessageHandler({
      storageDirectory: await createStorageDirectory(),
      fetcher
    });

    await handler(
      JSON.stringify({
        event: "settings:toss-credentials:save",
        data: {
          event: "settings:toss-credentials:save",
          requestId: "request-save",
          occurredAt: "2026-07-06T09:00:00.000Z",
          payload: {
            clientId: "client_fixture_1234567890",
            clientSecret: "secret_fixture_super_secret"
          }
        }
      }),
      () => "2026-07-06T09:00:01.000Z"
    );
    await handler(
      JSON.stringify({
        event: "watchlist:create:request",
        data: {
          event: "watchlist:create:request",
          requestId: "request-card",
          occurredAt: "2026-07-06T09:00:02.000Z",
          payload: {
            id: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            displayName: "마이크론 테크놀로지",
            groupId: null,
            tags: [],
            memo: ""
          }
        }
      }),
      () => "2026-07-06T09:00:03.000Z"
    );
    const refreshed = await handler(
      JSON.stringify({
        event: "market-data:refresh-watchlist:request",
        data: {
          event: "market-data:refresh-watchlist:request",
          requestId: "request-market",
          occurredAt: "2026-07-06T09:00:04.000Z",
          payload: {
            visibleCardIds: ["card-1"]
          }
        }
      }),
      () => "2026-07-06T09:00:05.000Z"
    );

    expect(refreshed).toEqual({
      event: "market-data:refresh-watchlist:response",
      requestId: "request-market",
      occurredAt: "2026-07-06T09:00:05.000Z",
      payload: {
        refreshedAt: "2026-07-06T09:00:05.000Z",
        nextPollDelayMs: 15_000,
        snapshots: [
          expect.objectContaining({
            cardId: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            freshness: "fresh",
            quality: "complete",
            observations: expect.objectContaining({
              price: expect.objectContaining({
                lastPrice: "194.93"
              })
            })
          })
        ]
      }
    });
    expect(requestedUrls.some((url) => url.includes("/api/v1/prices"))).toBe(true);
    expect(requestedUrls.some((url) => url.includes("/api/v1/trades?symbol=MU"))).toBe(true);
    expect(JSON.stringify(refreshed)).not.toContain("access-token-that-must-not-leak");
    expect(JSON.stringify(refreshed)).not.toContain("secret_fixture_super_secret");

    const quantRefreshed = await handler(
      JSON.stringify({
        event: "quant-indicators:refresh-watchlist:request",
        data: {
          event: "quant-indicators:refresh-watchlist:request",
          requestId: "request-quant",
          occurredAt: "2026-07-06T09:00:06.000Z",
          payload: {
            cardIds: ["card-1"]
          }
        }
      }),
      () => "2026-07-06T09:00:07.000Z"
    );

    expect(quantRefreshed).toEqual({
      event: "quant-indicators:refresh-watchlist:response",
      requestId: "request-quant",
      occurredAt: "2026-07-06T09:00:07.000Z",
      payload: {
        refreshedAt: "2026-07-06T09:00:07.000Z",
        snapshots: [
          expect.objectContaining({
            cardId: "card-1",
            symbol: "MU",
            sourceMarketDataSnapshotId: expect.any(String),
            decisionStatus: "dataInsufficient",
            decisionLabel: "데이터 부족"
          })
        ]
      }
    });
    expect(JSON.stringify(quantRefreshed)).not.toContain("access-token-that-must-not-leak");
    expect(JSON.stringify(quantRefreshed)).not.toContain("secret_fixture_super_secret");
  });
});
