import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  advanceDetectionRecord,
  calculateDynamicThreshold,
  calculateEmpiricalPercentile,
  evaluateFormula,
  evaluateSignal,
  loadFormulaRelease
} = require("./market-state-formula.cjs") as {
  advanceDetectionRecord(input: {
    bucketIndex: number;
    detected: boolean;
    endpoint: string;
    previous: {
      currentDetectionStartedAt: string | null;
      lastDetectedAt: string | null;
      lastNotifiedBucketIndex: number | null;
    };
  }): {
    currentDetectionStartedAt: string | null;
    lastDetectedAt: string | null;
    lastNotifiedBucketIndex: number | null;
    shouldNotify: boolean;
  };
  calculateDynamicThreshold(scores: number[], tailShare: number): number;
  calculateEmpiricalPercentile(scores: number[], value: number): number;
  evaluateFormula(
    formula: {
      featureNames: string[];
      featureMeans: number[];
      featureScales: number[];
      ridgeCoefficients: number[];
      intercept: number;
    },
    featureValues: Record<string, number>
  ): {
    rawScore: number;
    contributions: Array<{
      featureName: string;
      standardizedValue: number;
      contribution: number;
    }>;
  };
  evaluateSignal(input: {
    formula: {
      riskState: "BASELINE" | "AFTER_UP" | "AFTER_DOWN";
      causalGateId: string;
    };
    currentRiskState: "BASELINE" | "AFTER_UP" | "AFTER_DOWN";
    rawScore: number;
    dynamicThreshold: number;
    gateValues: Record<string, number>;
  }): { status: string; gatePassed: boolean | null };
  loadFormulaRelease(): {
    contentSha256: string;
    engineVersion: string;
    featureDefinitionVersion: string;
    formulaVersion: string;
    lifecycleDefinitionVersion: string;
    marketProxyId: string;
    signals: Array<{
      stateId: string;
      candidateId: string;
      fixedFormula: {
        causalGateId: string;
        transportTailSafetyFactor: number;
      };
    }>;
    targetInstrumentIds: string[];
  };
};

describe("market-state formula release", () => {
  it("loads exactly the five current formulas and excludes the predecessor uptrend", () => {
    const release = loadFormulaRelease();
    const stateIds = release.signals.map((signal) => signal.stateId);
    const uptrend = release.signals.find(
      (signal) => signal.stateId === "EFFICIENT_UPTREND"
    );

    expect(stateIds).toEqual([
      "FOMO_LIKE",
      "PANIC_LIKE",
      "PROFIT_TAKING_PROXY",
      "PERSISTENT_RECOVERY",
      "EFFICIENT_UPTREND"
    ]);
    expect(uptrend?.candidateId).toBe("PORTABLE_TREND_QUALITY_SCORE");
    expect(uptrend?.fixedFormula.transportTailSafetyFactor).toBe(1);
    expect(uptrend?.fixedFormula.causalGateId).toBe("POSITIVE_RELATIVE_VOLUME");
    expect(release.formulaVersion).toBe(
      "2ce9e3f48c8437f8f3e218ce39028b81f2279f16fe17bc68111682f7c070e842"
    );
    expect(release.featureDefinitionVersion).toBe(
      "rp001.v4-minute-strict-precursor.v1"
    );
    expect(release.lifecycleDefinitionVersion).toBe(
      "rp001.v4-reference-episode.v1"
    );
    expect(release.engineVersion).toBe(
      "stock-sub.market-state-engine.v1"
    );
    expect(release.contentSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(release.targetInstrumentIds).toHaveLength(33);
    expect(release.marketProxyId).toBe("SPY");
  });
});

describe("market-state formula calculation", () => {
  it("returns a reproducible contribution trace whose sum equals eta", () => {
    const result = evaluateFormula(
      {
        featureNames: ["momentum", "pressure"],
        featureMeans: [1, 10],
        featureScales: [2, 5],
        ridgeCoefficients: [0.5, -0.25],
        intercept: 0.1
      },
      {
        momentum: 5,
        pressure: 5
      }
    );

    expect(result.contributions).toEqual([
      {
        featureName: "momentum",
        rawValue: 5,
        mean: 1,
        scale: 2,
        standardizedValue: 2,
        coefficient: 0.5,
        contribution: 1
      },
      {
        featureName: "pressure",
        rawValue: 5,
        mean: 10,
        scale: 5,
        standardizedValue: -1,
        coefficient: -0.25,
        contribution: 0.25
      }
    ]);
    expect(result.rawScore).toBeCloseTo(1.35, 12);
  });

  it("uses NumPy-compatible linear quantiles and an empirical right CDF percentile", () => {
    expect(calculateDynamicThreshold([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 0.25))
      .toBeCloseTo(6.75, 12);
    expect(calculateEmpiricalPercentile([1, 2, 3, 4], 3)).toBe(75);
  });

  it("separates risk-state eligibility, gates, and threshold detection", () => {
    expect(evaluateSignal({
      formula: {
        riskState: "AFTER_UP",
        causalGateId: "NONE"
      },
      currentRiskState: "BASELINE",
      rawScore: 2,
      dynamicThreshold: 1,
      gateValues: {}
    })).toMatchObject({ status: "notApplicable", gatePassed: null });

    expect(evaluateSignal({
      formula: {
        riskState: "BASELINE",
        causalGateId: "POSITIVE_PRESSURE_MEAN_3"
      },
      currentRiskState: "BASELINE",
      rawScore: 2,
      dynamicThreshold: 1,
      gateValues: { pressureMean3: -0.01 }
    })).toMatchObject({ status: "notDetected", gatePassed: false });

    expect(evaluateSignal({
      formula: {
        riskState: "BASELINE",
        causalGateId: "POSITIVE_PRESSURE_MEAN_3"
      },
      currentRiskState: "BASELINE",
      rawScore: 2,
      dynamicThreshold: 1,
      gateValues: { pressureMean3: 0.01 }
    })).toMatchObject({ status: "detected", gatePassed: true });
  });

  it("preserves last detection while suppressing six endpoints and notifying on the seventh", () => {
    const first = advanceDetectionRecord({
      bucketIndex: 100,
      detected: true,
      endpoint: "2026-07-31T14:35:00.000Z",
      previous: {
        currentDetectionStartedAt: null,
        lastDetectedAt: null,
        lastNotifiedBucketIndex: null
      }
    });
    const sixth = advanceDetectionRecord({
      bucketIndex: 106,
      detected: true,
      endpoint: "2026-07-31T15:05:00.000Z",
      previous: first
    });
    const seventh = advanceDetectionRecord({
      bucketIndex: 107,
      detected: true,
      endpoint: "2026-07-31T15:10:00.000Z",
      previous: sixth
    });
    const cleared = advanceDetectionRecord({
      bucketIndex: 108,
      detected: false,
      endpoint: "2026-07-31T15:15:00.000Z",
      previous: seventh
    });

    expect(first.shouldNotify).toBe(true);
    expect(sixth.shouldNotify).toBe(false);
    expect(seventh.shouldNotify).toBe(true);
    expect(cleared.currentDetectionStartedAt).toBeNull();
    expect(cleared.lastDetectedAt).toBe("2026-07-31T15:10:00.000Z");
  });
});
