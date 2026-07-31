import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface FiveMinuteBarFixture {
  instrumentId: string;
  sessionDate: string;
  bucketIndex: number;
  barStart: string;
  barEnd: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  availableAt: string;
}

interface HistoricalBucketObservationFixture {
  volume: number;
  ret1: number;
}

interface AvailableFeatureVector {
  status: "available";
  instrumentId: string;
  sessionDate: string;
  bucketIndex: number;
  endpoint: string;
  values: Record<string, number>;
  gateValues: {
    pressureMean3: number;
    relativeVolume: number;
  };
}

interface UnavailableFeatureVector {
  status: "unavailable";
  reason: string;
}

type FeatureVectorResult = AvailableFeatureVector | UnavailableFeatureVector;

const {
  addCrossSectionalFeatures,
  calculateBaseFeatureVector
} = require("./market-state-features.cjs") as {
  addCrossSectionalFeatures(
    featureVectors: AvailableFeatureVector[],
    targetInstrumentIds: string[]
  ): Map<string, AvailableFeatureVector>;
  calculateBaseFeatureVector(input: {
    bars: FiveMinuteBarFixture[];
    marketBars: FiveMinuteBarFixture[];
    historicalByBucket: Record<string, HistoricalBucketObservationFixture[]>;
  }): FeatureVectorResult;
};

describe("market-state feature engine", () => {
  it("reproduces the causal endpoint features from completed five-minute bars", () => {
    const closes: number[] = [100, 101, 100.5, 102, 101.5, 103, 104, 103.5, 105, 107];
    const bars: FiveMinuteBarFixture[] = createBars("AAPL", closes, 200);
    const marketCloses: number[] = [200, 200.5, 201, 201.5, 202, 202.5, 203, 203.5, 204, 204.5];
    const marketBars: FiveMinuteBarFixture[] = createBars("SPY", marketCloses, 1_000);
    const historicalByBucket: Record<string, HistoricalBucketObservationFixture[]> =
      createHistoricalBuckets(10);

    const result: FeatureVectorResult = calculateBaseFeatureVector({
      bars,
      marketBars,
      historicalByBucket
    });

    expect(result.status).toBe("available");
    if (result.status !== "available") {
      return;
    }

    const ret1: number = Math.log(107) - Math.log(105);
    const ret3: number = Math.log(107) - Math.log(104);
    const ret6: number = Math.log(107) - Math.log(102);
    const previousRet3: number = Math.log(104) - Math.log(102);
    const marketRet1: number = Math.log(204.5) - Math.log(204);
    const marketRet3: number = Math.log(204.5) - Math.log(203);

    expect(result.values.ret_1).toBeCloseTo(ret1, 12);
    expect(result.values.ret_3).toBeCloseTo(ret3, 12);
    expect(result.values.ret_6).toBeCloseTo(ret6, 12);
    expect(result.values.acceleration_3).toBeCloseTo(ret3 - previousRet3, 12);
    expect(result.values.market_ret_1).toBeCloseTo(marketRet1, 12);
    expect(result.values.market_ret_3).toBeCloseTo(marketRet3, 12);
    expect(result.values.residual_ret_1).toBeCloseTo(ret1 - marketRet1, 12);
    expect(result.values.relative_volume).toBeCloseTo(2, 12);
    expect(result.values.log_relative_volume).toBeCloseTo(Math.log(2), 12);
    expect(result.values.z_ret_1).toBeCloseTo(ret1 / (1.4826 * 0.01), 12);
    expect(result.values.ret_1_volume_interaction).toBeCloseTo(
      result.values.z_ret_1 * Math.log(2),
      12
    );
    expect(result.values.ret_3_volume_interaction).toBeCloseTo(
      ret3 * Math.log(2),
      12
    );
    expect(result.values.bucket_fraction).toBeCloseTo(9 / 77, 12);
    expect(result.values.bucket_fraction_squared).toBeCloseTo((9 / 77) ** 2, 12);
    expect(result.values.portable_trend_quality_score).toBeCloseTo(
      (
        Math.tanh(
          Math.max(
            -8,
            Math.min(
              8,
              result.values.residual_ret_3 /
                Math.max(Math.sqrt(3) * result.values.realized_volatility_6, 1e-8)
            )
          ) / 2
        ) +
        result.values.signed_efficiency_6 +
        Math.tanh(result.values.signed_volume_pressure_mean_3)
      ) / 3,
      12
    );
    expect(result.gateValues.relativeVolume).toBeCloseTo(2, 12);
    expect(result.gateValues.pressureMean3).toBeCloseTo(
      result.values.signed_volume_pressure_mean_3,
      12
    );
  });

  it("requires forty strict-prior same-bucket observations", () => {
    const bars: FiveMinuteBarFixture[] = createBars(
      "AAPL",
      [100, 101, 102, 103, 104, 105, 106],
      200
    );
    const marketBars: FiveMinuteBarFixture[] = createBars(
      "SPY",
      [200, 201, 202, 203, 204, 205, 206],
      1_000
    );
    const historicalByBucket: Record<string, HistoricalBucketObservationFixture[]> =
      createHistoricalBuckets(7, 39);

    expect(calculateBaseFeatureVector({
      bars,
      marketBars,
      historicalByBucket
    })).toEqual({
      status: "unavailable",
      reason: "forty_prior_bucket_observations_required"
    });
  });

  it("adds panic cross-sectional features only at the frozen-roster coverage boundary", () => {
    const targetInstrumentIds: string[] = Array.from(
      { length: 33 },
      (_value: undefined, index: number): string => `S${String(index).padStart(2, "0")}`
    );
    const coveredVectors: AvailableFeatureVector[] = targetInstrumentIds
      .slice(0, 27)
      .map((instrumentId: string, index: number): AvailableFeatureVector =>
        createCrossSectionVector(instrumentId, index)
      );

    const augmented: Map<string, AvailableFeatureVector> = addCrossSectionalFeatures(
      coveredVectors,
      targetInstrumentIds
    );
    const first: AvailableFeatureVector | undefined = augmented.get("S00");
    const last: AvailableFeatureVector | undefined = augmented.get("S26");

    expect(augmented).toHaveLength(27);
    expect(first?.values.cross_sectional_residual_ret_3_rank).toBeCloseTo(
      1 / 27 - 0.5,
      12
    );
    expect(last?.values.cross_sectional_residual_ret_3_rank).toBeCloseTo(0.5, 12);
    expect(first?.values.cross_sectional_positive_breadth).toBeCloseTo(13 / 27, 12);
    expect(first?.values.cross_sectional_residual_ret_1_dispersion).toBeGreaterThan(0);

    expect(() =>
      addCrossSectionalFeatures(coveredVectors.slice(0, 26), targetInstrumentIds)
    ).toThrow("cross_sectional_coverage_insufficient");
  });
});

function createBars(
  instrumentId: string,
  closes: number[],
  volume: number
): FiveMinuteBarFixture[] {
  return closes.map(
    (close: number, bucketIndex: number): FiveMinuteBarFixture => {
      const startMinute: number = 30 + bucketIndex * 5;
      const barStart: Date = new Date(Date.UTC(2026, 6, 31, 13, startMinute));
      const barEnd: Date = new Date(barStart.getTime() + 5 * 60_000);

      return {
        instrumentId,
        sessionDate: "2026-07-31",
        bucketIndex,
        barStart: barStart.toISOString(),
        barEnd: barEnd.toISOString(),
        open: close - 0.5,
        high: close + 1,
        low: close - 1,
        close,
        volume,
        availableAt: barEnd.toISOString()
      };
    }
  );
}

function createHistoricalBuckets(
  bucketCount: number,
  observationCount: number = 40
): Record<string, HistoricalBucketObservationFixture[]> {
  const historicalByBucket: Record<string, HistoricalBucketObservationFixture[]> = {};

  for (let bucketIndex: number = 0; bucketIndex < bucketCount; bucketIndex += 1) {
    historicalByBucket[String(bucketIndex)] = Array.from(
      { length: observationCount },
      (): HistoricalBucketObservationFixture => ({
        volume: 100,
        ret1: 0.01
      })
    );
  }

  return historicalByBucket;
}

function createCrossSectionVector(
  instrumentId: string,
  index: number
): AvailableFeatureVector {
  const signedValue: number = index - 13;

  return {
    status: "available",
    instrumentId,
    sessionDate: "2026-07-31",
    bucketIndex: 9,
    endpoint: "2026-07-31T14:20:00.000Z",
    values: {
      residual_ret_1: signedValue,
      residual_ret_3: index,
      signed_efficiency_6: index,
      signed_volume_pressure: index / 10,
      signed_volume_pressure_mean_3: index
    },
    gateValues: {
      pressureMean3: index,
      relativeVolume: 2
    }
  };
}
