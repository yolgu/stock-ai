import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const { StoredStockReferenceCache, TossStockInfoClient } = require("./stock-reference.cjs") as {
  StoredStockReferenceCache: new (
    filePath: string,
    options?: { ttlMs?: number }
  ) => {
    saveAll(identities: unknown[]): Promise<void>;
    readFresh(
      symbols: string[],
      now: string
    ): Promise<{
      hits: unknown[];
      misses: string[];
    }>;
  };
  TossStockInfoClient: new (fetcher: typeof fetch) => {
    fetchStockIdentities(
      symbols: string[],
      accessToken: string,
      now: string
    ): Promise<{
      verified: unknown[];
      rejected: unknown[];
    }>;
  };
};

let tempDirectory: string | undefined;

async function createTempPath(fileName: string): Promise<string> {
  tempDirectory = await mkdtemp(join(tmpdir(), "stock-reference-"));

  return join(tempDirectory, fileName);
}

afterEach(async () => {
  if (tempDirectory !== undefined) {
    await rm(tempDirectory, { recursive: true, force: true });
    tempDirectory = undefined;
  }
});

describe("stock reference cache", () => {
  it("stores only verified stock references with owner-only permissions", async () => {
    const filePath = await createTempPath("stock-reference-cache.json");
    const cache = new StoredStockReferenceCache(filePath);

    await cache.saveAll([
      {
        symbol: "MU",
        market: "NASDAQ",
        displayName: "마이크론 테크놀로지",
        englishName: "Micron Technology",
        currency: "USD",
        status: "ACTIVE",
        securityType: "STOCK",
        tradingSuspended: false,
        liquidationTrading: false,
        verifiedAt: "2026-07-06T09:00:00.000Z"
      }
    ]);

    expect(await cache.readFresh(["MU"], "2026-07-06T10:00:00.000Z")).toEqual({
      hits: [
        expect.objectContaining({
          symbol: "MU",
          market: "NASDAQ",
          currency: "USD"
        })
      ],
      misses: []
    });
    expect((await stat(filePath)).mode & 0o777).toBe(0o600);
    const savedText = await readFile(filePath, "utf8");
    expect(savedText).not.toContain("access_token");
    expect(savedText).not.toContain("clientSecret");
    expect(savedText).not.toContain("Bearer ");
  });
});

describe("TossStockInfoClient", () => {
  it("requests stock info with an OAuth bearer token and maps empty results to rejected symbols", async () => {
    const requests: Array<{ url: string; headers: Headers }> = [];
    const fetcher = async (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
      requests.push({
        url: String(url),
        headers: new Headers(init?.headers)
      });

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
    const client = new TossStockInfoClient(fetcher);

    const result = await client.fetchStockIdentities(
      ["MU", "ZZZZZZZZZZZZ"],
      "access-token-that-must-not-leak",
      "2026-07-06T09:00:00.000Z"
    );

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe(
      "https://openapi.tossinvest.com/api/v1/stocks?symbols=MU%2CZZZZZZZZZZZZ"
    );
    expect(requests[0]?.headers.get("Authorization")).toBe(
      "Bearer access-token-that-must-not-leak"
    );
    expect(requests[0]?.headers.has("X-Tossinvest-Account")).toBe(false);
    expect(result).toEqual({
      verified: [
        expect.objectContaining({
          symbol: "MU",
          market: "NASDAQ",
          displayName: "마이크론 테크놀로지",
          currency: "USD",
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
    });
    expect(JSON.stringify(result)).not.toContain("access-token-that-must-not-leak");
  });

  it("maps Toss stock rate limits to a recoverable app error", async () => {
    const fetcher = async (): Promise<Response> =>
      new Response(
        JSON.stringify({
          error: {
            code: "rate-limit-exceeded",
            message: "Too many requests"
          }
        }),
        { status: 429, headers: { "Content-Type": "application/json" } }
      );
    const client = new TossStockInfoClient(fetcher);

    await expect(
      client.fetchStockIdentities(["MU"], "access-token", "2026-07-06T09:00:00.000Z")
    ).rejects.toMatchObject({
      code: "toss_rate_limited",
      recoverable: true
    });
  });
});
