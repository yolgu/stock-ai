import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface NormalizationBar {
  instrumentId: string;
  sessionDate: string;
  bucketIndex: number;
  close: number;
  volume: number;
}

interface PriorSession {
  bars: NormalizationBar[];
  marketBars: NormalizationBar[];
}

const {
  calculateReferenceMarketPassageByBucket,
  calculateReferenceNormalization,
  calculateReferenceZOneByBucket
} = require(
  "./market-state-normalization.cjs"
) as {
  calculateReferenceMarketPassageByBucket(input: {
    marketBars: NormalizationBar[];
    priorSessions: PriorSession[];
  }): Map<number, {
    direction: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
    window: number | null;
  }>;
  calculateReferenceNormalization(input: {
    bars: NormalizationBar[];
    marketBars: NormalizationBar[];
    priorSessions: PriorSession[];
  }): {
    status: "available" | "unavailable";
    reason?: string;
    pricePassage?: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
    passageScale?: number | null;
    zOne?: number;
    relativeVolumeOne?: number;
    zByWindow?: Record<string, number>;
  };
  calculateReferenceZOneByBucket(input: {
    bars: NormalizationBar[];
    marketBars: NormalizationBar[];
    priorSessions: PriorSession[];
  }): Map<number, number>;
};

describe("reference price-path normalization", () => {
  it("uses strict-prior sessions to confirm an upward price passage", () => {
    const priorSessions: PriorSession[] = Array.from(
      { length: 40 },
      (_value: undefined, sessionIndex: number): PriorSession => ({
        bars: createSession(
          `2026-05-${String(sessionIndex + 1).padStart(2, "0")}`,
          100,
          0.0002 + sessionIndex * 0.00001,
          "AAPL"
        ),
        marketBars: createSession(
          `2026-05-${String(sessionIndex + 1).padStart(2, "0")}`,
          200,
          0.0001 + sessionIndex * 0.000002,
          "SPY"
        )
      })
    );
    const result = calculateReferenceNormalization({
      bars: createSession("2026-07-31", 100, 0.02, "AAPL"),
      marketBars: createSession("2026-07-31", 200, 0.0001, "SPY"),
      priorSessions
    });

    expect(result.status).toBe("available");
    expect(result.pricePassage).toBe("UP");
    expect(result.passageScale).toBeGreaterThan(0);
    expect(result.zByWindow?.["3"]).toBeGreaterThanOrEqual(3);
    expect(result.zByWindow?.["6"]).toBeGreaterThanOrEqual(3);
  });

  it("does not calculate with fewer than forty complete prior sessions", () => {
    const priorSessions: PriorSession[] = Array.from(
      { length: 39 },
      (_value: undefined, index: number): PriorSession => ({
        bars: createSession(`2026-04-${index + 1}`, 100, 0.001, "AAPL"),
        marketBars: createSession(`2026-04-${index + 1}`, 200, 0.0005, "SPY")
      })
    );

    expect(calculateReferenceNormalization({
      bars: createSession("2026-07-31", 100, 0.01, "AAPL"),
      marketBars: createSession("2026-07-31", 200, 0.001, "SPY"),
      priorSessions
    })).toEqual({
      status: "unavailable",
      reason: "forty_prior_sessions_required"
    });
  });

  it("derives the frozen market passage and residual z-one series by endpoint", () => {
    const priorSessions: PriorSession[] = Array.from(
      { length: 40 },
      (_value: undefined, sessionIndex: number): PriorSession => ({
        bars: createSession(
          `2026-05-${String(sessionIndex + 1).padStart(2, "0")}`,
          100,
          0.0002 + sessionIndex * 0.00001,
          "AAPL"
        ),
        marketBars: createSession(
          `2026-05-${String(sessionIndex + 1).padStart(2, "0")}`,
          200,
          0.0001 + sessionIndex * 0.000002,
          "SPY"
        )
      })
    );
    const marketBars: NormalizationBar[] = createSession(
      "2026-07-31",
      200,
      -0.02,
      "SPY"
    );
    const zOneByBucket: Map<number, number> =
      calculateReferenceZOneByBucket({
        bars: createSession("2026-07-31", 100, -0.2, "AAPL"),
        marketBars,
        priorSessions
      });
    const marketPassageByBucket: Map<
      number,
      {
        direction: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
        window: number | null;
      }
    > = calculateReferenceMarketPassageByBucket({
      marketBars,
      priorSessions
    });

    expect(zOneByBucket.get(77)).toBeLessThan(-1);
    expect(marketPassageByBucket.get(77)).toEqual({
      direction: "DOWN",
      window: 6
    });
  });
});

function createSession(
  sessionDate: string,
  initialClose: number,
  logReturn: number,
  instrumentId: string
): NormalizationBar[] {
  return Array.from(
    { length: 78 },
    (_value: undefined, bucketIndex: number): NormalizationBar => ({
      instrumentId,
      sessionDate,
      bucketIndex,
      close: initialClose * Math.exp(logReturn * bucketIndex),
      volume: 100 + bucketIndex
    })
  );
}
