const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const formulaRelease = require("./formula-release.json");

const signalStateIds = [
  "FOMO_LIKE",
  "PANIC_LIKE",
  "PROFIT_TAKING_PROXY",
  "PERSISTENT_RECOVERY",
  "EFFICIENT_UPTREND"
];

/**
 * @returns {Record<string, *>} immutable formula release copy
 */
function loadFormulaRelease() {
  validateFormulaRelease(formulaRelease);

  return structuredClone(formulaRelease);
}

/**
 * @param {Record<string, *>} formula
 * @param {Record<string, number>} featureValues
 * @returns {{rawScore: number, contributions: Array<Record<string, number|string>>}}
 */
function evaluateFormula(formula, featureValues) {
  validateFormulaDimensions(formula);
  const contributions = formula.featureNames.map((featureName, index) => {
    const rawValue = featureValues[featureName];

    if (!Number.isFinite(rawValue)) {
      throw new Error(`formula_feature_unavailable:${featureName}`);
    }

    const mean = formula.featureMeans[index];
    const scale = formula.featureScales[index];
    const coefficient = formula.ridgeCoefficients[index];
    const standardizedValue = (rawValue - mean) / scale;

    return {
      featureName,
      rawValue,
      mean,
      scale,
      standardizedValue,
      coefficient,
      contribution: coefficient * standardizedValue
    };
  });
  const rawScore = contributions.reduce(
    (score, contribution) => score + contribution.contribution,
    formula.intercept
  );

  return { rawScore, contributions };
}

/**
 * NumPy's default linear/type-7 quantile.
 *
 * @param {number[]} scores
 * @param {number} tailShare
 * @returns {number}
 */
function calculateDynamicThreshold(scores, tailShare) {
  const values = validateFiniteScores(scores);

  if (!Number.isFinite(tailShare) || tailShare <= 0 || tailShare >= 1) {
    throw new Error("formula_tail_share_invalid");
  }

  return linearQuantile(values, 1 - tailShare);
}

/**
 * @param {number[]} scores
 * @param {number} value
 * @returns {number}
 */
function calculateEmpiricalPercentile(scores, value) {
  const values = validateFiniteScores(scores);

  if (!Number.isFinite(value)) {
    throw new Error("formula_score_invalid");
  }

  const lowerOrEqualCount = values.filter((score) => score <= value).length;

  return 100 * lowerOrEqualCount / values.length;
}

/**
 * @param {{
 *   formula: {riskState: string, causalGateId: string},
 *   currentRiskState: string,
 *   rawScore: number,
 *   dynamicThreshold: number,
 *   gateValues: Record<string, number>
 * }} input
 * @returns {{status: string, gatePassed: boolean|null}}
 */
function evaluateSignal(input) {
  if (input.currentRiskState !== input.formula.riskState) {
    return { status: "notApplicable", gatePassed: null };
  }

  const gatePassed = evaluateCausalGate(
    input.formula.causalGateId,
    input.gateValues
  );
  const detected =
    gatePassed &&
    Number.isFinite(input.rawScore) &&
    Number.isFinite(input.dynamicThreshold) &&
    input.rawScore >= input.dynamicThreshold;

  return {
    status: detected ? "detected" : "notDetected",
    gatePassed
  };
}

/**
 * @param {{
 *   bucketIndex: number,
 *   detected: boolean,
 *   endpoint: string,
 *   previous: {
 *     currentDetectionStartedAt: string|null,
 *     lastDetectedAt: string|null,
 *     lastNotifiedBucketIndex: number|null
 *   }
 * }} input
 * @returns {{
 *   currentDetectionStartedAt: string|null,
 *   lastDetectedAt: string|null,
 *   lastNotifiedBucketIndex: number|null,
 *   shouldNotify: boolean
 * }}
 */
function advanceDetectionRecord(input) {
  if (!input.detected) {
    return {
      currentDetectionStartedAt: null,
      lastDetectedAt: input.previous.lastDetectedAt,
      lastNotifiedBucketIndex: input.previous.lastNotifiedBucketIndex,
      shouldNotify: false
    };
  }

  const canNotify =
    input.previous.lastNotifiedBucketIndex === null ||
    input.bucketIndex - input.previous.lastNotifiedBucketIndex > 6;

  return {
    currentDetectionStartedAt:
      input.previous.currentDetectionStartedAt || input.endpoint,
    lastDetectedAt: input.endpoint,
    lastNotifiedBucketIndex: canNotify
      ? input.bucketIndex
      : input.previous.lastNotifiedBucketIndex,
    shouldNotify: canNotify
  };
}

function validateFormulaRelease(release) {
  const releaseBody = { ...release };
  delete releaseBody.contentSha256;
  const expectedContentSha256 = sha256(canonicalJson(releaseBody));

  if (
    release.contentSha256 !== expectedContentSha256 ||
    release.formulaVersion !==
      "2ce9e3f48c8437f8f3e218ce39028b81f2279f16fe17bc68111682f7c070e842" ||
    release.featureDefinitionVersion !==
      "rp001.v4-minute-strict-precursor.v1" ||
    release.lifecycleDefinitionVersion !==
      "rp001.v4-reference-episode.v1" ||
    release.engineVersion !== "stock-sub.market-state-engine.v1" ||
    release.marketProxyId !== "SPY" ||
    !Array.isArray(release.targetInstrumentIds) ||
    release.targetInstrumentIds.length !== 33 ||
    !Array.isArray(release.sourceBindings) ||
    release.sourceBindings.length !== 13 ||
    release.sourceBindings.some(
      (binding) =>
        typeof binding.role !== "string" ||
        typeof binding.path !== "string" ||
        !/^[a-f0-9]{64}$/.test(binding.sha256)
    ) ||
    !Array.isArray(release.signals) ||
    release.signals.map((signal) => signal.stateId).join("|") !==
      signalStateIds.join("|")
  ) {
    throw new Error("formula_release_invalid");
  }

  for (const signal of release.signals) {
    validateFormulaDimensions(signal.fixedFormula);
  }

  validateEngineSourceBindings(release.sourceBindings);
}

function validateFormulaDimensions(formula) {
  const size = Array.isArray(formula.featureNames)
    ? formula.featureNames.length
    : 0;

  if (
    size === 0 ||
    !Array.isArray(formula.featureMeans) ||
    !Array.isArray(formula.featureScales) ||
    !Array.isArray(formula.ridgeCoefficients) ||
    formula.featureMeans.length !== size ||
    formula.featureScales.length !== size ||
    formula.ridgeCoefficients.length !== size ||
    !Number.isFinite(formula.intercept) ||
    formula.featureScales.some((scale) => !Number.isFinite(scale) || scale <= 0)
  ) {
    throw new Error("formula_dimensions_invalid");
  }
}

function validateEngineSourceBindings(sourceBindings) {
  const engineBindings = sourceBindings.filter(
    (binding) => binding.role === "engine"
  );

  if (engineBindings.length !== 7) {
    throw new Error("formula_engine_bindings_invalid");
  }

  for (const binding of engineBindings) {
    const sourcePath = path.join(
      __dirname,
      path.basename(binding.path)
    );
    const actualSha256 = sha256(fs.readFileSync(sourcePath));

    if (actualSha256 !== binding.sha256) {
      throw new Error(
        `formula_engine_source_mismatch:${path.basename(binding.path)}`
      );
    }
  }
}

function evaluateCausalGate(gateId, gateValues) {
  if (gateId === "NONE") {
    return true;
  }

  if (gateId === "POSITIVE_PRESSURE_MEAN_3") {
    return Number.isFinite(gateValues.pressureMean3) &&
      gateValues.pressureMean3 > 0;
  }

  if (gateId === "POSITIVE_RELATIVE_VOLUME") {
    return Number.isFinite(gateValues.relativeVolume) &&
      gateValues.relativeVolume > 1;
  }

  throw new Error(`formula_gate_unsupported:${gateId}`);
}

function validateFiniteScores(scores) {
  if (
    !Array.isArray(scores) ||
    scores.length === 0 ||
    scores.some((score) => !Number.isFinite(score))
  ) {
    throw new Error("formula_score_history_invalid");
  }

  return [...scores].sort((left, right) => left - right);
}

function linearQuantile(sortedValues, probability) {
  const fractionalIndex = (sortedValues.length - 1) * probability;
  const lowerIndex = Math.floor(fractionalIndex);
  const upperIndex = Math.ceil(fractionalIndex);
  const interpolationWeight = fractionalIndex - lowerIndex;

  return sortedValues[lowerIndex] +
    interpolationWeight *
      (sortedValues[upperIndex] - sortedValues[lowerIndex]);
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }

  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }

  return JSON.stringify(value);
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

module.exports = {
  advanceDetectionRecord,
  calculateDynamicThreshold,
  calculateEmpiricalPercentile,
  evaluateFormula,
  evaluateSignal,
  loadFormulaRelease
};
