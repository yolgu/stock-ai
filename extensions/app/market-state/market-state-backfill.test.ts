import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface BackfillProgress {
  jobId: string;
  status: "idle" | "running" | "complete" | "incomplete" | "failed";
  requiredSessions: number;
  completedSessions: number;
  currentInstrumentId: string | null;
  totalInstrumentCount: number;
  completedInstrumentCount: number;
  error: string | null;
}

const { JsonFileStore } = require("../storage.cjs") as {
  JsonFileStore: new (
    filePath: string,
    defaultValue: Record<string, never>
  ) => {
    read(): Promise<Record<string, unknown>>;
    write(value: Record<string, unknown>): Promise<void>;
  };
};
const { MinuteBarRepository } = require("./market-state-repository.cjs") as {
  MinuteBarRepository: new (rootDirectory: string) => object;
};
const { MinuteHistoryBackfill } = require("./market-state-backfill.cjs") as {
  MinuteHistoryBackfill: new (input: {
    minuteRepository: object;
    progressStore: object;
    tossMarketDataClient: {
      fetchCandles(
        symbol: string,
        interval: string,
        accessToken: string,
        count: number,
        before: string | null
      ): Promise<{
        candles: Array<Record<string, string>>;
        nextBefore: string | null;
      }>;
    };
    tossAccessTokenProvider: {
      readAccessToken(occurredAt: string): Promise<string>;
    };
    nowIso(): string;
    requiredSessions: number;
  }) => {
    start(input: {
      instrumentIds: string[];
      occurredAt: string;
    }): Promise<BackfillProgress>;
    readProgress(): Promise<BackfillProgress>;
    waitForIdle(): Promise<void>;
  };
};

const temporaryDirectories: string[] = [];

afterEach(async (): Promise<void> => {
  await Promise.all(
    temporaryDirectories.splice(0).map(
      async (directory: string): Promise<void> => {
        await rm(directory, { recursive: true, force: true });
      }
    )
  );
});

describe("minute history backfill", () => {
  it("returns immediately and follows pagination until only missing sessions are filled", async () => {
    const rootDirectory: string = await createTemporaryDirectory();
    const requestedBefore: Array<string | null> = [];
    const pages: Array<{
      candles: Array<Record<string, string>>;
      nextBefore: string | null;
    }> = [
      {
        candles: createFullSessionCandles("2026-07-31"),
        nextBefore: "cursor-1"
      },
      {
        candles: createFullSessionCandles("2026-07-30"),
        nextBefore: "cursor-2"
      }
    ];
    const backfill = new MinuteHistoryBackfill({
      minuteRepository: new MinuteBarRepository(rootDirectory),
      progressStore: new JsonFileStore(
        path.join(rootDirectory, "backfill-progress.json"),
        {}
      ),
      tossMarketDataClient: {
        fetchCandles: async (
          _symbol: string,
          _interval: string,
          _accessToken: string,
          _count: number,
          before: string | null
        ) => {
          requestedBefore.push(before);

          return pages.shift() ?? { candles: [], nextBefore: null };
        }
      },
      tossAccessTokenProvider: {
        readAccessToken: async (): Promise<string> => "token"
      },
      nowIso: (): string => "2026-07-31T20:05:00.000Z",
      requiredSessions: 2
    });

    const started: BackfillProgress = await backfill.start({
      instrumentIds: ["AAPL"],
      occurredAt: "2026-07-31T20:05:00.000Z"
    });
    expect(started.status).toBe("running");

    await backfill.waitForIdle();
    expect(await backfill.readProgress()).toMatchObject({
      status: "complete",
      requiredSessions: 2,
      completedSessions: 2,
      completedInstrumentCount: 1,
      totalInstrumentCount: 1,
      error: null
    });
    expect(requestedBefore).toEqual([null, "cursor-1"]);

    await backfill.start({
      instrumentIds: ["AAPL"],
      occurredAt: "2026-07-31T20:06:00.000Z"
    });
    await backfill.waitForIdle();
    expect(requestedBefore).toEqual([null, "cursor-1"]);
  });

  it("resumes from the durable cursor after a transient page failure", async () => {
    const rootDirectory: string = await createTemporaryDirectory();
    const requestedBefore: Array<string | null> = [];
    let shouldFailAtCursor: boolean = true;
    const backfill = new MinuteHistoryBackfill({
      minuteRepository: new MinuteBarRepository(rootDirectory),
      progressStore: new JsonFileStore(
        path.join(rootDirectory, "backfill-progress.json"),
        {}
      ),
      tossMarketDataClient: {
        fetchCandles: async (
          _symbol: string,
          _interval: string,
          _accessToken: string,
          _count: number,
          before: string | null
        ): Promise<{
          candles: Array<Record<string, string>>;
          nextBefore: string | null;
        }> => {
          requestedBefore.push(before);

          if (before === null) {
            return {
              candles: createFullSessionCandles("2026-07-31"),
              nextBefore: "cursor-1"
            };
          }

          if (shouldFailAtCursor) {
            const error: Error & { code: string } = Object.assign(
              new Error("temporary provider failure"),
              { code: "market_data_unavailable" }
            );
            throw error;
          }

          return {
            candles: createFullSessionCandles("2026-07-30"),
            nextBefore: "cursor-2"
          };
        }
      },
      tossAccessTokenProvider: {
        readAccessToken: async (): Promise<string> => "token"
      },
      nowIso: (): string => "2026-07-31T20:05:00.000Z",
      requiredSessions: 2
    });

    await backfill.start({
      instrumentIds: ["AAPL"],
      occurredAt: "2026-07-31T20:05:00.000Z"
    });
    await backfill.waitForIdle();
    expect(await backfill.readProgress()).toMatchObject({
      status: "failed",
      completedSessions: 1,
      error: "market_data_unavailable",
      cursorByInstrument: { AAPL: "cursor-1" }
    });

    shouldFailAtCursor = false;
    await backfill.start({
      instrumentIds: ["AAPL"],
      occurredAt: "2026-07-31T20:06:00.000Z"
    });
    await backfill.waitForIdle();

    expect(await backfill.readProgress()).toMatchObject({
      status: "complete",
      completedSessions: 2,
      error: null
    });
    expect(requestedBefore).toEqual([
      null,
      "cursor-1",
      "cursor-1"
    ]);
  });
});

async function createTemporaryDirectory(): Promise<string> {
  const directory: string = await mkdtemp(
    path.join(tmpdir(), "stock-sub-backfill-")
  );
  temporaryDirectories.push(directory);

  return directory;
}

function createFullSessionCandles(
  sessionDate: "2026-07-30" | "2026-07-31"
): Array<Record<string, string>> {
  const day: number = sessionDate === "2026-07-30" ? 30 : 31;

  return Array.from(
    { length: 390 },
    (_value: undefined, minute: number): Record<string, string> => {
      const timestamp: string = new Date(
        Date.UTC(2026, 6, day, 13, 30 + minute)
      ).toISOString();

      return {
        timestamp,
        openPrice: "100",
        highPrice: "101",
        lowPrice: "99",
        closePrice: "100",
        volume: "10",
        currency: "USD"
      };
    }
  );
}
