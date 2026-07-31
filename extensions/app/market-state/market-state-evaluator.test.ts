import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

interface FormulaSignalFixture {
  stateId: string;
  riskState: "BASELINE" | "AFTER_UP" | "AFTER_DOWN";
  fixedFormula: {
    featureNames: string[];
    featureMeans: number[];
    featureScales: number[];
    ridgeCoefficients: number[];
    intercept: number;
  };
}

const {
  evaluateFormula,
  loadFormulaRelease
} = require("./market-state-formula.cjs") as {
  evaluateFormula(
    formula: FormulaSignalFixture["fixedFormula"],
    featureValues: Record<string, number>
  ): { rawScore: number };
  loadFormulaRelease(): {
    formulaVersion: string;
    contentSha256: string;
    signals: FormulaSignalFixture[];
  };
};
const { evaluateMarketStateEndpoint } = require(
  "./market-state-evaluator.cjs"
) as {
  evaluateMarketStateEndpoint(input: {
    cardId: string;
    symbol: string;
    sessionDate: string;
    endpoint: string;
    sourceGenerationId: string;
    bucketIndex: number;
    currentRiskState: "BASELINE" | "AFTER_UP" | "AFTER_DOWN";
    featureValues: Record<string, number>;
    gateValues: { pressureMean3: number; relativeVolume: number };
    scoreHistoryBySignal: Record<string, number[]>;
    previousDetectionRecords: Record<string, {
      currentDetectionStartedAt: string | null;
      lastDetectedAt: string | null;
      lastNotifiedBucketIndex: number | null;
    }>;
  }): {
    snapshot: {
      signals: Array<{
        signalId: string;
        displayName: string;
        status: string;
        percentile: number | null;
        currentDetectionStartedAt: string | null;
        lastDetectedAt: string | null;
        trace: { contributions: Array<Record<string, number | string>> } | null;
      }>;
      notifiedSignalIds: string[];
    };
    detectionRecords: Record<string, {
      currentDetectionStartedAt: string | null;
      lastDetectedAt: string | null;
      lastNotifiedBucketIndex: number | null;
    }>;
  };
};

describe("market-state endpoint evaluator", () => {
  it("publishes all five named signals while separating eligibility and notification", () => {
    const release = loadFormulaRelease();
    const featureValues: Record<string, number> = {};

    for (const signal of release.signals) {
      signal.fixedFormula.featureNames.forEach(
        (featureName: string, index: number): void => {
          featureValues[featureName] = signal.fixedFormula.featureMeans[index] ?? 0;
        }
      );
    }

    const scoreHistoryBySignal: Record<string, number[]> = {};

    for (const signal of release.signals) {
      const rawScore: number = evaluateFormula(
        signal.fixedFormula,
        featureValues
      ).rawScore;
      scoreHistoryBySignal[signal.stateId] = [rawScore - 2, rawScore - 1];
    }

    const result = evaluateMarketStateEndpoint({
      cardId: "card-aapl",
      symbol: "AAPL",
      sessionDate: "2026-07-31",
      endpoint: "2026-07-31T14:05:00.000Z",
      sourceGenerationId: "generation-1",
      bucketIndex: 6,
      currentRiskState: "BASELINE",
      featureValues,
      gateValues: {
        pressureMean3: 0.1,
        relativeVolume: 2
      },
      scoreHistoryBySignal,
      previousDetectionRecords: {}
    });

    expect(result.snapshot.signals.map((signal) => signal.displayName)).toEqual([
      "FOMO",
      "패닉",
      "차익실현",
      "회복",
      "상승세"
    ]);
    expect(result.snapshot.signals.map((signal) => signal.status)).toEqual([
      "detected",
      "detected",
      "notApplicable",
      "notApplicable",
      "detected"
    ]);
    expect(result.snapshot.signals[0]?.percentile).toBe(100);
    expect(result.snapshot.signals[2]?.percentile).toBeNull();
    expect(result.snapshot.notifiedSignalIds).toEqual([
      "FOMO_LIKE",
      "PANIC_LIKE",
      "EFFICIENT_UPTREND"
    ]);
    expect(result.snapshot.signals[0]?.trace?.contributions.length).toBe(22);
  });

  it("keeps a high-percentile gated signal as not detected", () => {
    const release = loadFormulaRelease();
    const fomo = release.signals[0];
    const featureValues: Record<string, number> = Object.fromEntries(
      fomo.fixedFormula.featureNames.map(
        (featureName: string, index: number): [string, number] => [
          featureName,
          fomo.fixedFormula.featureMeans[index] ?? 0
        ]
      )
    );
    const rawScore: number = evaluateFormula(
      fomo.fixedFormula,
      featureValues
    ).rawScore;
    const result = evaluateMarketStateEndpoint({
      cardId: "card-aapl",
      symbol: "AAPL",
      sessionDate: "2026-07-31",
      endpoint: "2026-07-31T14:05:00.000Z",
      sourceGenerationId: "generation-1",
      bucketIndex: 6,
      currentRiskState: "BASELINE",
      featureValues,
      gateValues: {
        pressureMean3: -0.1,
        relativeVolume: 2
      },
      scoreHistoryBySignal: {
        FOMO_LIKE: [rawScore - 2, rawScore - 1]
      },
      previousDetectionRecords: {}
    });
    const fomoResult = result.snapshot.signals[0];

    expect(fomoResult?.percentile).toBe(100);
    expect(fomoResult?.status).toBe("notDetected");
    expect(result.snapshot.notifiedSignalIds).not.toContain("FOMO_LIKE");
  });
});
