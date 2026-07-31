import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  aggregateCompletedFiveMinuteBar,
  aggregateCompletedSession
} = require("./completed-five-minute-bar.cjs") as {
  aggregateCompletedFiveMinuteBar(
    bars: Array<{
      instrumentId: string;
      sessionDate: string;
      barStart: string;
      barEnd: string;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
      availableAt: string;
      contentHash: string;
    }>
  ): {
    barStart: string;
    barEnd: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    availableAt: string;
    sourceHashes: string[];
  };
  aggregateCompletedSession(
    bars: Array<ReturnType<typeof createMinuteBar> & { minuteBucket: number }>,
    availableBefore: string
  ): Array<{ bucketIndex: number }>;
};

describe("completed five-minute bar", () => {
  it("aggregates exactly five contiguous completed one-minute bars", () => {
    const result = aggregateCompletedFiveMinuteBar(
      Array.from({ length: 5 }, (_unused: unknown, index: number) =>
        createMinuteBar(index)
      )
    );

    expect(result).toMatchObject({
      barStart: "2026-07-31T13:30:00.000Z",
      barEnd: "2026-07-31T13:35:00.000Z",
      open: 100,
      high: 105,
      low: 99,
      close: 104.5,
      volume: 60,
      availableAt: "2026-07-31T13:35:01.000Z",
      sourceHashes: ["hash-0", "hash-1", "hash-2", "hash-3", "hash-4"]
    });
  });

  it("rejects missing or duplicated minute buckets instead of interpolating", () => {
    const missing = [0, 1, 3, 4].map(createMinuteBar);
    const duplicated = [0, 1, 1, 3, 4].map(createMinuteBar);

    expect(() => aggregateCompletedFiveMinuteBar(missing)).toThrow(
      "five_minute_bar_requires_exactly_five_minutes"
    );
    expect(() => aggregateCompletedFiveMinuteBar(duplicated)).toThrow(
      "five_minute_bar_minutes_not_contiguous"
    );
  });

  it("emits only complete buckets whose five source minutes are available", () => {
    const minutes: Array<ReturnType<typeof createMinuteBar> & {
      minuteBucket: number;
    }> = Array.from(
      { length: 10 },
      (_value: undefined, index: number) => ({
        ...createMinuteBar(index),
        minuteBucket: index
      })
    );
    minutes[8] = {
      ...minutes[8],
      availableAt: "2026-07-31T14:00:00.000Z"
    };

    expect(aggregateCompletedSession(
      minutes,
      "2026-07-31T13:59:00.000Z"
    ).map((bar: { bucketIndex: number }): number => bar.bucketIndex)).toEqual([0]);
  });

  it("rejects a future event even when its availability timestamp is malformed", () => {
    const minutes: Array<ReturnType<typeof createMinuteBar> & {
      minuteBucket: number;
    }> = Array.from(
      { length: 5 },
      (_value: undefined, index: number) => ({
        ...createMinuteBar(index),
        minuteBucket: index
      })
    );
    minutes[4] = {
      ...minutes[4],
      barEnd: "2026-07-31T14:05:00.000Z",
      availableAt: "2026-07-31T13:35:00.000Z"
    };

    expect(aggregateCompletedSession(
      minutes,
      "2026-07-31T13:59:00.000Z"
    )).toEqual([]);
  });
});

function createMinuteBar(index: number): {
  instrumentId: string;
  sessionDate: string;
  barStart: string;
  barEnd: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  availableAt: string;
  contentHash: string;
} {
  const minute: number = 30 + index;
  const nextMinute: number = minute + 1;

  return {
    instrumentId: "NVDA",
    sessionDate: "2026-07-31",
    barStart: `2026-07-31T13:${String(minute).padStart(2, "0")}:00.000Z`,
    barEnd: `2026-07-31T13:${String(nextMinute).padStart(2, "0")}:00.000Z`,
    open: 100 + index,
    high: 101 + index,
    low: 99 + index,
    close: 100.5 + index,
    volume: 10 + index,
    availableAt: `2026-07-31T13:${String(nextMinute).padStart(2, "0")}:01.000Z`,
    contentHash: `hash-${index}`
  };
}
