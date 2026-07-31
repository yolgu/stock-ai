const crypto = require("node:crypto");

const {
  advanceDetectionRecord,
  calculateDynamicThreshold,
  calculateEmpiricalPercentile,
  evaluateFormula,
  evaluateSignal,
  loadFormulaRelease
} = require("./market-state-formula.cjs");

const signalPresentation = Object.freeze({
  FOMO_LIKE: {
    displayName: "FOMO",
    formationLabel: "추격 매수형 가격 움직임 형성 감지",
    horizonMinutes: 30
  },
  PANIC_LIKE: {
    displayName: "패닉",
    formationLabel: "공포 매도형 가격 움직임 형성 감지",
    horizonMinutes: 30
  },
  PROFIT_TAKING_PROXY: {
    displayName: "차익실현",
    formationLabel: "상승 확인 후 되돌림 조짐",
    horizonMinutes: 30
  },
  PERSISTENT_RECOVERY: {
    displayName: "회복",
    formationLabel: "하락 확인 후 회복 조짐",
    horizonMinutes: 30
  },
  EFFICIENT_UPTREND: {
    displayName: "상승세",
    formationLabel: "역행이 작은 상승 흐름 형성 감지",
    horizonMinutes: 60
  }
});

/**
 * Evaluates all five frozen formulas at one completed five-minute endpoint.
 *
 * @param {{
 *   cardId: string,
 *   symbol: string,
 *   sessionDate: string,
 *   endpoint: string,
 *   sourceGenerationId: string,
 *   bucketIndex: number,
 *   currentRiskState: "BASELINE" | "AFTER_UP" | "AFTER_DOWN",
 *   featureValues: Record<string, number>,
 *   gateValues: {pressureMean3: number, relativeVolume: number},
 *   scoreHistoryBySignal: Record<string, number[]>,
 *   previousDetectionRecords: Record<string, Record<string, *>>
 * }} input
 * @returns {{snapshot: Record<string, *>, detectionRecords: Record<string, Record<string, *>>}}
 */
function evaluateMarketStateEndpoint(input) {
  validateEndpointInput(input);
  const release = loadFormulaRelease();
  /** @type {Array<Record<string, *>>} */
  const signals = [];
  /** @type {Record<string, Record<string, *>>} */
  const detectionRecords = {};
  /** @type {string[]} */
  const notifiedSignalIds = [];

  for (const signalDefinition of release.signals) {
    const signalId = signalDefinition.stateId;
    const presentation = signalPresentation[signalId];
    const previousRecord =
      input.previousDetectionRecords[signalId] ||
      emptyDetectionRecord();
    const isApplicable =
      signalDefinition.riskState === input.currentRiskState;

    if (!isApplicable) {
      const record = advanceDetectionRecord({
        bucketIndex: input.bucketIndex,
        detected: false,
        endpoint: input.endpoint,
        previous: previousRecord
      });
      detectionRecords[signalId] = withoutNotificationFlag(record);
      signals.push({
        signalId,
        displayName: presentation.displayName,
        formationLabel: presentation.formationLabel,
        horizonMinutes: presentation.horizonMinutes,
        status: "notApplicable",
        percentile: null,
        percentileNumerator: null,
        percentileDenominator: null,
        rawScore: null,
        dynamicThreshold: null,
        thresholdDistance: null,
        gate: createGateTrace(
          signalDefinition.fixedFormula.causalGateId,
          input.gateValues,
          null
        ),
        requiredRiskState: signalDefinition.riskState,
        currentRiskState: input.currentRiskState,
        currentDetectionStartedAt: record.currentDetectionStartedAt,
        lastDetectedAt: record.lastDetectedAt,
        trace: null
      });
      continue;
    }

    const scoreHistory = input.scoreHistoryBySignal[signalId];

    if (!Array.isArray(scoreHistory) || scoreHistory.length === 0) {
      const record = advanceDetectionRecord({
        bucketIndex: input.bucketIndex,
        detected: false,
        endpoint: input.endpoint,
        previous: previousRecord
      });
      detectionRecords[signalId] = withoutNotificationFlag(record);
      signals.push(createCollectingSignal({
        signalDefinition,
        presentation,
        currentRiskState: input.currentRiskState,
        record
      }));
      continue;
    }

    let formulaResult;

    try {
      formulaResult = evaluateFormula(
        signalDefinition.fixedFormula,
        input.featureValues
      );
    } catch (error) {
      const record = advanceDetectionRecord({
        bucketIndex: input.bucketIndex,
        detected: false,
        endpoint: input.endpoint,
        previous: previousRecord
      });
      detectionRecords[signalId] = withoutNotificationFlag(record);
      signals.push(createUnavailableSignal({
        signalDefinition,
        presentation,
        currentRiskState: input.currentRiskState,
        record,
        reason:
          error instanceof Error
            ? error.message
            : "formula_feature_unavailable"
      }));
      continue;
    }

    const effectiveTailShare =
      signalDefinition.fixedFormula.calibrationTailShare *
      signalDefinition.fixedFormula.transportTailSafetyFactor;
    const dynamicThreshold = calculateDynamicThreshold(
      scoreHistory,
      effectiveTailShare
    );
    const percentile = calculateEmpiricalPercentile(
      scoreHistory,
      formulaResult.rawScore
    );
    const decision = evaluateSignal({
      formula: {
        riskState: signalDefinition.riskState,
        causalGateId: signalDefinition.fixedFormula.causalGateId
      },
      currentRiskState: input.currentRiskState,
      rawScore: formulaResult.rawScore,
      dynamicThreshold,
      gateValues: input.gateValues
    });
    const detected = decision.status === "detected";
    const record = advanceDetectionRecord({
      bucketIndex: input.bucketIndex,
      detected,
      endpoint: input.endpoint,
      previous: previousRecord
    });
    detectionRecords[signalId] = withoutNotificationFlag(record);

    if (record.shouldNotify) {
      notifiedSignalIds.push(signalId);
    }

    const percentileNumerator = scoreHistory.filter(
      (score) => score <= formulaResult.rawScore
    ).length;
    const gate = createGateTrace(
      signalDefinition.fixedFormula.causalGateId,
      input.gateValues,
      decision.gatePassed
    );
    signals.push({
      signalId,
      displayName: presentation.displayName,
      formationLabel: presentation.formationLabel,
      horizonMinutes: presentation.horizonMinutes,
      status: decision.status,
      percentile,
      percentileNumerator,
      percentileDenominator: scoreHistory.length,
      rawScore: formulaResult.rawScore,
      dynamicThreshold,
      thresholdDistance: formulaResult.rawScore - dynamicThreshold,
      gate,
      requiredRiskState: signalDefinition.riskState,
      currentRiskState: input.currentRiskState,
      currentDetectionStartedAt: record.currentDetectionStartedAt,
      lastDetectedAt: record.lastDetectedAt,
      trace: {
        intercept: signalDefinition.fixedFormula.intercept,
        contributions: formulaResult.contributions,
        effectiveTailShare,
        calibrationTailShare:
          signalDefinition.fixedFormula.calibrationTailShare,
        transportTailSafetyFactor:
          signalDefinition.fixedFormula.transportTailSafetyFactor,
        candidateId: signalDefinition.candidateId,
        cause: signalDefinition.cause,
        phenotypeTag: signalDefinition.phenotypeTag
      }
    });
  }

  return {
    snapshot: {
      snapshotId: crypto.randomUUID(),
      cardId: input.cardId,
      symbol: input.symbol,
      sessionDate: input.sessionDate,
      asOf: input.endpoint,
      bucketIndex: input.bucketIndex,
      sourceGenerationId: input.sourceGenerationId,
      formulaVersion: release.formulaVersion,
      formulaContentSha256: release.contentSha256,
      observedState: input.currentRiskState,
      observedStateLabel: observedStateLabel(input.currentRiskState),
      signals,
      notifiedSignalIds
    },
    detectionRecords
  };
}

/**
 * @param {Record<string, *>} input
 * @returns {Record<string, *>}
 */
function createCollectingSignal(input) {
  return {
    signalId: input.signalDefinition.stateId,
    displayName: input.presentation.displayName,
    formationLabel: input.presentation.formationLabel,
    horizonMinutes: input.presentation.horizonMinutes,
    status: "collecting",
    unavailableReason: "trailing_twenty_session_scores_required",
    percentile: null,
    percentileNumerator: null,
    percentileDenominator: null,
    rawScore: null,
    dynamicThreshold: null,
    thresholdDistance: null,
    gate: null,
    requiredRiskState: input.signalDefinition.riskState,
    currentRiskState: input.currentRiskState,
    currentDetectionStartedAt: input.record.currentDetectionStartedAt,
    lastDetectedAt: input.record.lastDetectedAt,
    trace: null
  };
}

/**
 * @param {Record<string, *>} input
 * @returns {Record<string, *>}
 */
function createUnavailableSignal(input) {
  return {
    ...createCollectingSignal(input),
    status: "unavailable",
    unavailableReason: input.reason
  };
}

/**
 * @param {string} gateId
 * @param {Record<string, number>} gateValues
 * @param {boolean | null} passed
 * @returns {Record<string, *> | null}
 */
function createGateTrace(gateId, gateValues, passed) {
  if (gateId === "NONE") {
    return null;
  }

  if (gateId === "POSITIVE_PRESSURE_MEAN_3") {
    return {
      gateId,
      label: "최근 3개 봉의 거래량 압력",
      value: gateValues.pressureMean3,
      operator: ">",
      threshold: 0,
      passed
    };
  }

  if (gateId === "POSITIVE_RELATIVE_VOLUME") {
    return {
      gateId,
      label: "동일 시각 과거 중앙값 대비 거래량",
      value: gateValues.relativeVolume,
      operator: ">",
      threshold: 1,
      passed
    };
  }

  throw new Error(`formula_gate_unsupported:${gateId}`);
}

/**
 * @returns {Record<string, *>}
 */
function emptyDetectionRecord() {
  return {
    currentDetectionStartedAt: null,
    lastDetectedAt: null,
    lastNotifiedBucketIndex: null
  };
}

/**
 * @param {Record<string, *>} record
 * @returns {Record<string, *>}
 */
function withoutNotificationFlag(record) {
  const output = { ...record };
  delete output.shouldNotify;

  return output;
}

/**
 * @param {string} state
 * @returns {string}
 */
function observedStateLabel(state) {
  if (state === "AFTER_UP") {
    return "상승 확인 후";
  }

  if (state === "AFTER_DOWN") {
    return "하락 확인 후";
  }

  return "방향성 확인 전";
}

/**
 * @param {Record<string, *>} input
 * @returns {void}
 */
function validateEndpointInput(input) {
  if (
    typeof input.cardId !== "string" ||
    input.cardId === "" ||
    typeof input.symbol !== "string" ||
    input.symbol === "" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(input.sessionDate) ||
    !Number.isFinite(Date.parse(input.endpoint)) ||
    typeof input.sourceGenerationId !== "string" ||
    input.sourceGenerationId === "" ||
    !Number.isInteger(input.bucketIndex) ||
    !["BASELINE", "AFTER_UP", "AFTER_DOWN"].includes(
      input.currentRiskState
    )
  ) {
    throw new Error("market_state_endpoint_invalid");
  }
}

module.exports = {
  evaluateMarketStateEndpoint,
  signalPresentation
};
