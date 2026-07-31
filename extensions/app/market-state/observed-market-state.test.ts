import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface ObservedStateSnapshot {
  state: "BASELINE" | "AFTER_UP" | "AFTER_DOWN" | "UNAVAILABLE";
  phase: "BASELINE" | "ACTIVE" | "WATCHER" | "UNAVAILABLE";
  stateStartedAt: string;
  confirmationBucketIndex: number | null;
  episodeScale: number | null;
  runningExtreme: number | null;
  lastExtremeBucketIndex: number | null;
  lastDirectionalEndBucketIndex: number | null;
  normalizationBars: number;
  broadDownSeen: boolean;
  broadContextComplete: boolean;
}

const {
  advanceObservedMarketState,
  createInitialObservedMarketState
} = require("./observed-market-state.cjs") as {
  advanceObservedMarketState(
    previous: ObservedStateSnapshot,
    endpoint: {
      endpoint: string;
      bucketIndex: number;
      available: boolean;
      close: number;
      high: number;
      low: number;
      pricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
      passageScale: number | null;
      passageWindow: number | null;
      zByWindow: Record<string, number>;
      scaleByWindow: Record<string, number>;
      closeHistory: number[];
      marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE";
      downsideBreadth: number | null;
      zOne: number | null;
      relativeVolumeOne: number | null;
    }
  ): ObservedStateSnapshot;
  createInitialObservedMarketState(sessionStartedAt: string): ObservedStateSnapshot;
};

describe("observed market state", () => {
  it("moves from baseline only after a visible price-passage confirmation", () => {
    const initial: ObservedStateSnapshot = createInitialObservedMarketState(
      "2026-07-31T13:30:00.000Z"
    );
    const quiet: ObservedStateSnapshot = advanceObservedMarketState(
      initial,
      endpoint({ bucketIndex: 5, pricePassage: "NONE" })
    );
    const confirmed: ObservedStateSnapshot = advanceObservedMarketState(
      quiet,
      endpoint({
        bucketIndex: 6,
        pricePassage: "UP",
        passageWindow: 6,
        passageScale: 0.02,
        high: 105,
        close: 104
      })
    );

    expect(quiet.state).toBe("BASELINE");
    expect(confirmed).toMatchObject({
      state: "AFTER_UP",
      phase: "ACTIVE",
      confirmationBucketIndex: 6,
      episodeScale: 0.02,
      runningExtreme: 105,
      normalizationBars: 0
    });
  });

  it("transitions after a confirmed two-scale retracement or recovery", () => {
    const afterUp: ObservedStateSnapshot = {
      state: "AFTER_UP",
      phase: "ACTIVE",
      stateStartedAt: "2026-07-31T14:05:00.000Z",
      confirmationBucketIndex: 6,
      episodeScale: 0.02,
      runningExtreme: 105,
      lastExtremeBucketIndex: 6,
      lastDirectionalEndBucketIndex: 6,
      normalizationBars: 0,
      broadDownSeen: false,
      broadContextComplete: true
    };
    const retraced: ObservedStateSnapshot = advanceObservedMarketState(
      afterUp,
      endpoint({
        bucketIndex: 10,
        close: 100,
        high: 101,
        low: 99,
        pricePassage: "NONE"
      })
    );
    const afterDown: ObservedStateSnapshot = {
      state: "AFTER_DOWN",
      phase: "ACTIVE",
      stateStartedAt: "2026-07-31T14:05:00.000Z",
      confirmationBucketIndex: 6,
      episodeScale: 0.02,
      runningExtreme: 95,
      lastExtremeBucketIndex: 6,
      lastDirectionalEndBucketIndex: 6,
      normalizationBars: 0,
      broadDownSeen: false,
      broadContextComplete: true
    };
    const recovered: ObservedStateSnapshot = advanceObservedMarketState(
      afterDown,
      endpoint({
        bucketIndex: 10,
        close: 100,
        high: 101,
        low: 99,
        pricePassage: "NONE"
      })
    );

    expect(retraced.state).toBe("AFTER_DOWN");
    expect(retraced.runningExtreme).toBe(99);
    expect(recovered.state).toBe("AFTER_UP");
    expect(recovered.runningExtreme).toBe(101);
  });

  it("returns to baseline only after three visible normalization bars", () => {
    let state: ObservedStateSnapshot = {
      state: "AFTER_UP",
      phase: "ACTIVE",
      stateStartedAt: "2026-07-31T14:05:00.000Z",
      confirmationBucketIndex: 6,
      episodeScale: 0.02,
      runningExtreme: 105,
      lastExtremeBucketIndex: 6,
      lastDirectionalEndBucketIndex: 6,
      normalizationBars: 0,
      broadDownSeen: false,
      broadContextComplete: true
    };

    for (let bucketIndex: number = 7; bucketIndex <= 9; bucketIndex += 1) {
      state = advanceObservedMarketState(
        state,
        endpoint({
          bucketIndex,
          close: 104.5,
          high: 104.8,
          low: 104.2,
          zOne: 0.2,
          relativeVolumeOne: 1.1
        })
      );
    }

    expect(state).toMatchObject({
      state: "BASELINE",
      phase: "BASELINE",
      confirmationBucketIndex: null,
      episodeScale: null,
      runningExtreme: null,
      normalizationBars: 0
    });
  });

  it("marks a missing endpoint unavailable without fabricating a transition", () => {
    const initial: ObservedStateSnapshot = createInitialObservedMarketState(
      "2026-07-31T13:30:00.000Z"
    );

    expect(
      advanceObservedMarketState(
        initial,
        endpoint({ available: false })
      )
    ).toMatchObject({
      state: "UNAVAILABLE",
      phase: "UNAVAILABLE"
    });
  });

  it("enters AFTER_UP after the frozen sustained-upward-path confirmation", () => {
    const initial: ObservedStateSnapshot = createInitialObservedMarketState(
      "2026-07-31T13:30:00.000Z"
    );
    const confirmed: ObservedStateSnapshot = advanceObservedMarketState(
      initial,
      endpoint({
        bucketIndex: 12,
        close: 106,
        high: 106.2,
        low: 105.8,
        zByWindow: { "6": 2.2, "9": 1.6, "12": 1.2 },
        scaleByWindow: { "6": 0.02, "9": 0.025, "12": 0.03 },
        closeHistory: [100, 101, 102, 103, 104, 106]
      })
    );

    expect(confirmed).toMatchObject({
      state: "AFTER_UP",
      phase: "ACTIVE",
      confirmationBucketIndex: 12,
      episodeScale: 0.02
    });
  });

  it("keeps the research risk state while a one-scale reverse move is watched", () => {
    const afterUp: ObservedStateSnapshot = activeAfterUp();
    const watcher: ObservedStateSnapshot = advanceObservedMarketState(
      afterUp,
      endpoint({
        bucketIndex: 8,
        close: 102,
        high: 103,
        low: 101.5
      })
    );
    const retraced: ObservedStateSnapshot = advanceObservedMarketState(
      watcher,
      endpoint({
        bucketIndex: 10,
        close: 100,
        high: 101,
        low: 99
      })
    );

    expect(watcher).toMatchObject({
      state: "AFTER_UP",
      phase: "WATCHER"
    });
    expect(retraced).toMatchObject({
      state: "AFTER_DOWN",
      phase: "ACTIVE"
    });
  });

  it("separates a broad downside passage from an idiosyncratic retracement", () => {
    const broadDown: ObservedStateSnapshot = advanceObservedMarketState(
      activeAfterUp(),
      endpoint({
        bucketIndex: 8,
        close: 103.5,
        high: 104,
        low: 103,
        pricePassage: "DOWN",
        passageWindow: 3,
        passageScale: 0.015,
        marketPricePassage: "NONE",
        downsideBreadth: 0.82
      })
    );
    const incompleteContext: ObservedStateSnapshot =
      advanceObservedMarketState(
        activeAfterUp(),
        endpoint({
          bucketIndex: 8,
          close: 103.5,
          high: 104,
          low: 103,
          pricePassage: "DOWN",
          passageWindow: 3,
          passageScale: 0.015,
          marketPricePassage: "NONE",
          downsideBreadth: null
        })
      );

    expect(broadDown).toMatchObject({
      state: "AFTER_DOWN",
      phase: "ACTIVE",
      episodeScale: 0.015
    });
    expect(incompleteContext).toMatchObject({
      state: "UNAVAILABLE",
      phase: "UNAVAILABLE"
    });
  });
});

function endpoint(
  overrides: Partial<{
    endpoint: string;
    bucketIndex: number;
    available: boolean;
    close: number;
    high: number;
    low: number;
    pricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
    passageScale: number | null;
    passageWindow: number | null;
    zByWindow: Record<string, number>;
    scaleByWindow: Record<string, number>;
    closeHistory: number[];
    marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE";
    downsideBreadth: number | null;
    zOne: number | null;
    relativeVolumeOne: number | null;
  }> = {}
): {
  endpoint: string;
  bucketIndex: number;
  available: boolean;
  close: number;
  high: number;
  low: number;
  pricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE";
  passageScale: number | null;
  passageWindow: number | null;
  zByWindow: Record<string, number>;
  scaleByWindow: Record<string, number>;
  closeHistory: number[];
  marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE";
  downsideBreadth: number | null;
  zOne: number | null;
  relativeVolumeOne: number | null;
} {
  return {
    endpoint: "2026-07-31T14:05:00.000Z",
    bucketIndex: 6,
    available: true,
    close: 100,
    high: 101,
    low: 99,
    pricePassage: "NONE",
    passageScale: null,
    passageWindow: null,
    zByWindow: {},
    scaleByWindow: {},
    closeHistory: [100],
    marketPricePassage: "NONE",
    downsideBreadth: 0,
    zOne: 1,
    relativeVolumeOne: 2,
    ...overrides
  };
}

function activeAfterUp(): ObservedStateSnapshot {
  return {
    state: "AFTER_UP",
    phase: "ACTIVE",
    stateStartedAt: "2026-07-31T14:05:00.000Z",
    confirmationBucketIndex: 6,
    episodeScale: 0.02,
    runningExtreme: 105,
    lastExtremeBucketIndex: 6,
    lastDirectionalEndBucketIndex: 6,
    normalizationBars: 0,
    broadDownSeen: false,
    broadContextComplete: true
  };
}
