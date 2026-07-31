import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface ProviderCandleFixture {
  timestamp: string;
  openPrice: string;
  highPrice: string;
  lowPrice: string;
  closePrice: string;
  volume: string;
  currency: string;
}

interface CanonicalMinuteBarFixture {
  instrumentId: string;
  sessionDate: string;
  minuteBucket: number;
  barStart: string;
  barEnd: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  receivedAt: string;
  availableAt: string;
  sourceRequestId: string;
  providerRevisionId: string;
  contentHash: string;
}

const {
  MarketStateSnapshotRepository,
  MinuteBarRepository
} = require("./market-state-repository.cjs") as {
  MinuteBarRepository: new (rootDirectory: string) => {
    saveProviderCandles(input: {
      instrumentId: string;
      receivedAt: string;
      sourceRequestId: string;
      candles: ProviderCandleFixture[];
    }): Promise<{ accepted: number; revised: number; ignored: number }>;
    readSession(
      instrumentId: string,
      sessionDate: string
    ): Promise<CanonicalMinuteBarFixture[]>;
    readCoverage(instrumentId: string): Promise<{
      completeSessionDates: string[];
      minuteCount: number;
    }>;
  };
  MarketStateSnapshotRepository: new (filePath: string) => {
    saveEvaluation(input: {
      snapshot: Record<string, unknown>;
      detectionRecords: Record<string, Record<string, unknown>>;
    }): Promise<void>;
    readLatest(cardIds: string[]): Promise<Array<Record<string, unknown>>>;
    readTrace(
      cardId: string,
      signalId: string
    ): Promise<Record<string, unknown> | null>;
    readHistory(
      cardId: string,
      signalId: string,
      sessionDate: string
    ): Promise<{ points: Array<Record<string, unknown>> }>;
    readDetectionRecords(
      cardId: string,
      sessionDate: string
    ): Promise<Record<string, Record<string, unknown>>>;
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

describe("minute bar repository", () => {
  it("stores only regular-session minutes with complete provenance", async () => {
    const repository: InstanceType<typeof MinuteBarRepository> =
      new MinuteBarRepository(await createTemporaryDirectory());

    const result: { accepted: number; revised: number; ignored: number } =
      await repository.saveProviderCandles({
        instrumentId: "AAPL",
        receivedAt: "2026-07-31T13:32:10.000Z",
        sourceRequestId: "request-1",
        candles: [
          createProviderCandle("2026-07-31T13:29:00.000Z", "99"),
          createProviderCandle("2026-07-31T13:30:00.000Z", "100"),
          createProviderCandle("2026-07-31T13:31:00.000Z", "101")
        ]
      });
    const bars: CanonicalMinuteBarFixture[] = await repository.readSession(
      "AAPL",
      "2026-07-31"
    );

    expect(result).toEqual({ accepted: 2, revised: 0, ignored: 1 });
    expect(bars).toHaveLength(2);
    expect(bars[0]).toMatchObject({
      instrumentId: "AAPL",
      sessionDate: "2026-07-31",
      minuteBucket: 0,
      barStart: "2026-07-31T13:30:00.000Z",
      barEnd: "2026-07-31T13:31:00.000Z",
      close: 100,
      receivedAt: "2026-07-31T13:32:10.000Z",
      availableAt: "2026-07-31T13:32:10.000Z",
      sourceRequestId: "request-1"
    });
    expect(bars[0]?.providerRevisionId).toMatch(/^[a-f0-9]{64}$/);
    expect(bars[0]?.contentHash).toMatch(/^[a-f0-9]{64}$/);
  });

  it("replaces a provider revision without duplicating the canonical minute", async () => {
    const rootDirectory: string = await createTemporaryDirectory();
    const repository: InstanceType<typeof MinuteBarRepository> =
      new MinuteBarRepository(rootDirectory);
    const baseInput: {
      instrumentId: string;
      receivedAt: string;
      sourceRequestId: string;
      candles: ProviderCandleFixture[];
    } = {
      instrumentId: "AAPL",
      receivedAt: "2026-07-31T13:32:10.000Z",
      sourceRequestId: "request-1",
      candles: [createProviderCandle("2026-07-31T13:30:00.000Z", "100")]
    };

    await repository.saveProviderCandles(baseInput);
    const revisionResult: { accepted: number; revised: number; ignored: number } =
      await repository.saveProviderCandles({
        ...baseInput,
        receivedAt: "2026-07-31T13:33:00.000Z",
        sourceRequestId: "request-2",
        candles: [createProviderCandle("2026-07-31T13:30:00.000Z", "102")]
      });
    const duplicateResult: { accepted: number; revised: number; ignored: number } =
      await repository.saveProviderCandles({
        ...baseInput,
        receivedAt: "2026-07-31T13:34:00.000Z",
        sourceRequestId: "request-3"
      });
    const bars: CanonicalMinuteBarFixture[] = await repository.readSession(
      "AAPL",
      "2026-07-31"
    );
    const partitionPath: string = path.join(
      rootDirectory,
      "minutes",
      "AAPL",
      "2026-07-31.json"
    );
    const partition: {
      minutes: Array<{ revisions: CanonicalMinuteBarFixture[] }>;
    } = JSON.parse(await readFile(partitionPath, "utf8")) as {
      minutes: Array<{ revisions: CanonicalMinuteBarFixture[] }>;
    };

    expect(revisionResult).toEqual({ accepted: 0, revised: 1, ignored: 0 });
    expect(duplicateResult).toEqual({ accepted: 0, revised: 0, ignored: 1 });
    expect(bars).toHaveLength(1);
    expect(bars[0]?.close).toBe(102);
    expect(partition.minutes[0]?.revisions).toHaveLength(2);
  });

  it("selects the same canonical revision regardless of provider input order", async () => {
    const firstRepository: InstanceType<typeof MinuteBarRepository> =
      new MinuteBarRepository(await createTemporaryDirectory());
    const secondRepository: InstanceType<typeof MinuteBarRepository> =
      new MinuteBarRepository(await createTemporaryDirectory());
    const lowerClose: ProviderCandleFixture = createProviderCandle(
      "2026-07-31T13:30:00.000Z",
      "100"
    );
    const higherClose: ProviderCandleFixture = createProviderCandle(
      "2026-07-31T13:30:00.000Z",
      "102"
    );
    const save = async (
      repository: InstanceType<typeof MinuteBarRepository>,
      candles: ProviderCandleFixture[]
    ): Promise<void> => {
      await repository.saveProviderCandles({
        instrumentId: "AAPL",
        receivedAt: "2026-07-31T13:32:10.000Z",
        sourceRequestId: "request-with-duplicate-revisions",
        candles
      });
    };

    await save(firstRepository, [lowerClose, higherClose]);
    await save(secondRepository, [higherClose, lowerClose]);

    const firstBars: CanonicalMinuteBarFixture[] =
      await firstRepository.readSession("AAPL", "2026-07-31");
    const secondBars: CanonicalMinuteBarFixture[] =
      await secondRepository.readSession("AAPL", "2026-07-31");

    expect(firstBars[0]?.contentHash).toBe(
      secondBars[0]?.contentHash
    );
    expect(firstBars[0]?.close).toBe(secondBars[0]?.close);
  });

  it("marks coverage complete only when all 390 regular minutes exist", async () => {
    const repository: InstanceType<typeof MinuteBarRepository> =
      new MinuteBarRepository(await createTemporaryDirectory());
    const candles: ProviderCandleFixture[] = Array.from(
      { length: 390 },
      (_value: undefined, minute: number): ProviderCandleFixture =>
        createProviderCandle(
          new Date(Date.UTC(2026, 6, 31, 13, 30 + minute)).toISOString(),
          String(100 + minute / 100)
        )
    );

    await repository.saveProviderCandles({
      instrumentId: "AAPL",
      receivedAt: "2026-07-31T20:01:00.000Z",
      sourceRequestId: "full-session",
      candles
    });

    expect(await repository.readCoverage("AAPL")).toEqual({
      completeSessionDates: ["2026-07-31"],
      minuteCount: 390
    });
  });

  it("stores the latest formula trace, session history, and detection memory atomically", async () => {
    const rootDirectory: string = await createTemporaryDirectory();
    const repository: InstanceType<typeof MarketStateSnapshotRepository> =
      new MarketStateSnapshotRepository(
        path.join(rootDirectory, "market-state-snapshots.json")
      );
    const firstSnapshot: Record<string, unknown> = createFormulaSnapshot(
      "2026-07-31T14:05:00.000Z",
      "detected",
      99.8
    );
    const secondSnapshot: Record<string, unknown> = createFormulaSnapshot(
      "2026-07-31T14:10:00.000Z",
      "notDetected",
      87.2
    );

    await repository.saveEvaluation({
      snapshot: firstSnapshot,
      detectionRecords: {
        FOMO_LIKE: {
          currentDetectionStartedAt: "2026-07-31T14:05:00.000Z",
          lastDetectedAt: "2026-07-31T14:05:00.000Z",
          lastNotifiedBucketIndex: 6
        }
      }
    });
    await repository.saveEvaluation({
      snapshot: secondSnapshot,
      detectionRecords: {
        FOMO_LIKE: {
          currentDetectionStartedAt: null,
          lastDetectedAt: "2026-07-31T14:05:00.000Z",
          lastNotifiedBucketIndex: 6
        }
      }
    });

    expect(await repository.readLatest(["card-aapl"])).toEqual([
      secondSnapshot
    ]);
    expect(await repository.readTrace("card-aapl", "FOMO_LIKE")).toMatchObject({
      signalId: "FOMO_LIKE",
      status: "notDetected",
      percentile: 87.2
    });
    expect((await repository.readHistory(
      "card-aapl",
      "FOMO_LIKE",
      "2026-07-31"
    )).points).toHaveLength(2);
    expect(await repository.readDetectionRecords(
      "card-aapl",
      "2026-07-31"
    )).toMatchObject({
      FOMO_LIKE: {
        currentDetectionStartedAt: null,
        lastDetectedAt: "2026-07-31T14:05:00.000Z",
        lastNotifiedBucketIndex: 6
      }
    });
  });
});

async function createTemporaryDirectory(): Promise<string> {
  const directory: string = await mkdtemp(
    path.join(tmpdir(), "stock-sub-market-state-")
  );
  temporaryDirectories.push(directory);

  return directory;
}

function createProviderCandle(
  timestamp: string,
  closePrice: string
): ProviderCandleFixture {
  const close: number = Number(closePrice);

  return {
    timestamp,
    openPrice: String(close - 0.5),
    highPrice: String(close + 1),
    lowPrice: String(close - 1),
    closePrice,
    volume: "100",
    currency: "USD"
  };
}

function createFormulaSnapshot(
  asOf: string,
  status: "detected" | "notDetected",
  percentile: number
): Record<string, unknown> {
  return {
    snapshotId: `snapshot-${asOf}`,
    cardId: "card-aapl",
    symbol: "AAPL",
    sessionDate: "2026-07-31",
    asOf,
    sourceGenerationId: `generation-${asOf}`,
    formulaVersion: "formula-v1",
    formulaContentSha256: "a".repeat(64),
    observedState: "BASELINE",
    observedStateLabel: "방향성 확인 전",
    notifiedSignalIds: [],
    signals: [
      {
        signalId: "FOMO_LIKE",
        displayName: "FOMO",
        status,
        percentile,
        rawScore: 1,
        dynamicThreshold: 0.5,
        trace: {
          intercept: 0,
          contributions: []
        }
      }
    ]
  };
}
