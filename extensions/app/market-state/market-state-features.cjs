const MINIMUM_FEATURE_BUCKET = 6;
const NORMALIZATION_SESSION_COUNT = 40;
const REGULAR_SESSION_LAST_BUCKET = 77;
const MINIMUM_CROSS_SECTION_COUNT = 5;
const REQUIRED_CROSS_SECTION_SHARE = 0.8;

/**
 * @typedef {{
 *   instrumentId: string,
 *   sessionDate: string,
 *   bucketIndex: number,
 *   barStart: string,
 *   barEnd: string,
 *   open: number,
 *   high: number,
 *   low: number,
 *   close: number,
 *   volume: number,
 *   availableAt: string
 * }} FiveMinuteBar
 */

/**
 * @typedef {{
 *   volume: number,
 *   ret1: number
 * }} HistoricalBucketObservation
 */

/**
 * @typedef {{
 *   status: "available",
 *   instrumentId: string,
 *   sessionDate: string,
 *   bucketIndex: number,
 *   endpoint: string,
 *   values: Record<string, number>,
 *   gateValues: {
 *     pressureMean3: number,
 *     relativeVolume: number
 *   }
 * }} AvailableFeatureVector
 */

/**
 * Calculates the frozen causal feature definition at one completed endpoint.
 */
class MarketStateFeatureEngine {
  /**
   * @param {{
   *   bars: FiveMinuteBar[],
   *   marketBars: FiveMinuteBar[],
   *   historicalByBucket: Record<string, HistoricalBucketObservation[]>
   * }} input
   * @returns {AvailableFeatureVector | {status: "unavailable", reason: string}}
   */
  calculateBase(input) {
    const bars = normalizeSessionBars(input.bars);
    const marketBars = normalizeSessionBars(input.marketBars);

    if (bars.length <= MINIMUM_FEATURE_BUCKET) {
      return unavailable("seven_session_bars_required");
    }

    if (!hasSingleSessionIdentity(bars) || !hasSingleSessionIdentity(marketBars)) {
      return unavailable("session_bar_identity_invalid");
    }

    const marketByBucket = new Map(
      marketBars.map((bar) => [bar.bucketIndex, bar])
    );
    /** @type {Array<{bar: FiveMinuteBar, values: Record<string, number>}>} */
    const eligibleRows = [];

    for (
      let position = MINIMUM_FEATURE_BUCKET;
      position < bars.length;
      position += 1
    ) {
      const row = calculateCausalRow({
        bars,
        marketByBucket,
        position,
        historicalByBucket: input.historicalByBucket
      });

      if (row.status === "unavailable") {
        return row;
      }

      eligibleRows.push({
        bar: bars[position],
        values: row.values
      });
    }

    const current = eligibleRows[eligibleRows.length - 1];
    const pressureValues = eligibleRows
      .slice(-6)
      .map((row) => row.values.signed_volume_pressure);
    const pressureMean3 = mean(pressureValues.slice(-3));
    const pressureMean6 = mean(pressureValues);
    const values = {
      ...current.values,
      signed_volume_pressure_mean_3: pressureMean3,
      signed_volume_pressure_mean_6: pressureMean6
    };
    const volatilityScale = Math.max(
      Math.sqrt(3) * values.realized_volatility_6,
      1e-8
    );
    const normalizedMomentum = clamp(
      values.residual_ret_3 / volatilityScale,
      -8,
      8
    );
    values.portable_trend_quality_score = (
      Math.tanh(normalizedMomentum / 2) +
      values.signed_efficiency_6 +
      Math.tanh(pressureMean3)
    ) / 3;

    if (!Object.values(values).every(Number.isFinite)) {
      return unavailable("feature_value_non_finite");
    }

    return {
      status: "available",
      instrumentId: current.bar.instrumentId,
      sessionDate: current.bar.sessionDate,
      bucketIndex: current.bar.bucketIndex,
      endpoint: current.bar.barEnd,
      values,
      gateValues: {
        pressureMean3,
        relativeVolume: values.relative_volume
      }
    };
  }

  /**
   * @param {AvailableFeatureVector[]} featureVectors
   * @param {string[]} targetInstrumentIds
   * @returns {Map<string, AvailableFeatureVector>}
   */
  addCrossSection(featureVectors, targetInstrumentIds) {
    validateTargetRoster(targetInstrumentIds);
    const roster = new Set(targetInstrumentIds);
    const vectors = featureVectors.filter(
      (vector) => roster.has(vector.instrumentId)
    );
    const requiredCount = Math.max(
      MINIMUM_CROSS_SECTION_COUNT,
      Math.ceil(targetInstrumentIds.length * REQUIRED_CROSS_SECTION_SHARE)
    );

    if (
      vectors.length < requiredCount ||
      new Set(vectors.map((vector) => vector.instrumentId)).size !== vectors.length
    ) {
      throw new Error("cross_sectional_coverage_insufficient");
    }

    validateCommonEndpoint(vectors);
    const breadth = mean(
      vectors.map((vector) => vector.values.residual_ret_1 > 0 ? 1 : 0)
    );
    const meanPressure = mean(
      vectors.map((vector) => vector.values.signed_volume_pressure)
    );
    const residualRet1Dispersion = populationStandardDeviation(
      vectors.map((vector) => vector.values.residual_ret_1)
    );
    const residualRet3Ranks = percentileRanks(
      vectors,
      (vector) => vector.values.residual_ret_3
    );
    const efficiencyRanks = percentileRanks(
      vectors,
      (vector) => vector.values.signed_efficiency_6
    );
    const pressureRanks = percentileRanks(
      vectors,
      (vector) => vector.values.signed_volume_pressure_mean_3
    );
    /** @type {Map<string, AvailableFeatureVector>} */
    const augmented = new Map();

    for (const vector of vectors) {
      const residualRet3Rank = residualRet3Ranks.get(vector.instrumentId);
      const efficiencyRank = efficiencyRanks.get(vector.instrumentId);
      const pressureRank = pressureRanks.get(vector.instrumentId);

      if (
        residualRet3Rank === undefined ||
        efficiencyRank === undefined ||
        pressureRank === undefined
      ) {
        throw new Error("cross_sectional_rank_unavailable");
      }

      augmented.set(vector.instrumentId, {
        ...vector,
        values: {
          ...vector.values,
          cross_sectional_positive_breadth: breadth,
          cross_sectional_mean_volume_pressure: meanPressure,
          cross_sectional_residual_ret_3_rank: residualRet3Rank,
          cross_sectional_residual_ret_1_dispersion: residualRet1Dispersion,
          cross_sectional_signed_efficiency_6_rank: efficiencyRank,
          cross_sectional_pressure_mean_3_rank: pressureRank,
          trend_quality_persistent_score:
            residualRet3Rank + efficiencyRank + pressureRank
        }
      });
    }

    return augmented;
  }
}

/**
 * @param {{
 *   bars: FiveMinuteBar[],
 *   marketBars: FiveMinuteBar[],
 *   historicalByBucket: Record<string, HistoricalBucketObservation[]>
 * }} input
 * @returns {AvailableFeatureVector | {status: "unavailable", reason: string}}
 */
function calculateBaseFeatureVector(input) {
  return new MarketStateFeatureEngine().calculateBase(input);
}

/**
 * @param {AvailableFeatureVector[]} featureVectors
 * @param {string[]} targetInstrumentIds
 * @returns {Map<string, AvailableFeatureVector>}
 */
function addCrossSectionalFeatures(featureVectors, targetInstrumentIds) {
  return new MarketStateFeatureEngine().addCrossSection(
    featureVectors,
    targetInstrumentIds
  );
}

/**
 * @param {{
 *   bars: FiveMinuteBar[],
 *   marketByBucket: Map<number, FiveMinuteBar>,
 *   position: number,
 *   historicalByBucket: Record<string, HistoricalBucketObservation[]>
 * }} input
 * @returns {{status: "available", values: Record<string, number>} | {status: "unavailable", reason: string}}
 */
function calculateCausalRow(input) {
  const bar = input.bars[input.position];
  const marketBar = input.marketByBucket.get(bar.bucketIndex);
  const marketPrevious = input.marketByBucket.get(bar.bucketIndex - 1);
  const marketPreviousThree = input.marketByBucket.get(bar.bucketIndex - 3);

  if (
    marketBar === undefined ||
    marketPrevious === undefined ||
    marketPreviousThree === undefined
  ) {
    return unavailable("matching_market_bars_required");
  }

  const history = readNormalizationHistory(
    input.historicalByBucket[String(bar.bucketIndex)]
  );

  if (history === null) {
    return unavailable("forty_prior_bucket_observations_required");
  }

  const logCloses = input.bars.map((candidate) => Math.log(candidate.close));
  const ret1Values = [];

  for (
    let position = input.position - 5;
    position <= input.position;
    position += 1
  ) {
    ret1Values.push(logCloses[position] - logCloses[position - 1]);
  }

  const ret1 = ret1Values[ret1Values.length - 1];
  const ret3 = logCloses[input.position] - logCloses[input.position - 3];
  const ret6 = logCloses[input.position] - logCloses[input.position - 6];
  const previousRet3 =
    logCloses[input.position - 3] - logCloses[input.position - 6];
  const absolutePath = ret1Values.reduce(
    (total, value) => total + Math.abs(value),
    0
  );

  if (absolutePath <= 0) {
    return unavailable("signed_efficiency_path_unavailable");
  }

  const expectedVolume = median(history.map((value) => value.volume));
  const historicalReturnScale = median(
    history.map((value) => Math.abs(value.ret1))
  );

  if (expectedVolume <= 0) {
    return unavailable("historical_volume_invalid");
  }

  const relativeVolumeUnclipped = bar.volume / expectedVolume;
  const logRelativeVolume = Math.log(relativeVolumeUnclipped);
  const relativeVolume = clamp(Math.exp(logRelativeVolume), 1e-6, 100);
  const priceRange = bar.high - bar.low;
  const closeLocation = priceRange === 0
    ? 0
    : (2 * bar.close - bar.high - bar.low) / priceRange;
  const marketRet1 = Math.log(marketBar.close) - Math.log(marketPrevious.close);
  const marketRet3 =
    Math.log(marketBar.close) - Math.log(marketPreviousThree.close);
  const residualRet1 = ret1 - marketRet1;
  const residualRet3 = ret3 - marketRet3;
  const rangeFraction = priceRange / bar.close;
  const signedVolumePressure =
    closeLocation * Math.log1p(relativeVolume);
  const squareRootRelativeVolume = Math.sqrt(relativeVolume);
  const bucketFraction = bar.bucketIndex / REGULAR_SESSION_LAST_BUCKET;
  const robustReturnScale =
    1.4826 * Math.max(historicalReturnScale, 1e-8);
  const zRet1 = ret1 / robustReturnScale;
  const window12 = logCloses.slice(
    Math.max(0, input.position - 11),
    input.position + 1
  );
  const window24 = logCloses.slice(
    Math.max(0, input.position - 23),
    input.position + 1
  );
  const values = {
    ret_1: ret1,
    z_ret_1: zRet1,
    ret_3: ret3,
    ret_6: ret6,
    acceleration_3: ret3 - previousRet3,
    signed_efficiency_6: ret6 / absolutePath,
    realized_volatility_6: populationStandardDeviation(ret1Values),
    range_fraction: rangeFraction,
    market_ret_1: marketRet1,
    market_ret_3: marketRet3,
    residual_ret_1: residualRet1,
    residual_ret_3: residualRet3,
    rally_12: logCloses[input.position] - Math.min(...window12),
    selloff_12: logCloses[input.position] - Math.max(...window12),
    rally_24: logCloses[input.position] - Math.min(...window24),
    selloff_24: logCloses[input.position] - Math.max(...window24),
    bucket_fraction: bucketFraction,
    bucket_fraction_squared: bucketFraction ** 2,
    log_relative_volume: logRelativeVolume,
    volume_excess_125: Math.max(logRelativeVolume - Math.log(1.25), 0),
    volume_excess_150: Math.max(logRelativeVolume - Math.log(1.5), 0),
    ret_1_volume_interaction: zRet1 * logRelativeVolume,
    ret_3_volume_interaction: ret3 * logRelativeVolume,
    close_location_value: closeLocation,
    relative_volume: relativeVolume,
    signed_volume_pressure: signedVolumePressure,
    signed_price_impact: residualRet1 / squareRootRelativeVolume,
    directional_liquidity_stress:
      closeLocation * rangeFraction / squareRootRelativeVolume
  };

  if (!Object.values(values).every(Number.isFinite)) {
    return unavailable("feature_value_non_finite");
  }

  return { status: "available", values };
}

/**
 * @param {FiveMinuteBar[]} bars
 * @returns {FiveMinuteBar[]}
 */
function normalizeSessionBars(bars) {
  if (!Array.isArray(bars)) {
    return [];
  }

  return [...bars].sort(
    (left, right) => left.bucketIndex - right.bucketIndex
  );
}

/**
 * @param {FiveMinuteBar[]} bars
 * @returns {boolean}
 */
function hasSingleSessionIdentity(bars) {
  if (bars.length === 0) {
    return false;
  }

  const first = bars[0];

  return bars.every(
    (bar, index) =>
      bar.instrumentId === first.instrumentId &&
      bar.sessionDate === first.sessionDate &&
      bar.bucketIndex === index &&
      Number.isFinite(bar.close) &&
      bar.close > 0 &&
      Number.isFinite(bar.high) &&
      Number.isFinite(bar.low) &&
      Number.isFinite(bar.volume)
  );
}

/**
 * @param {HistoricalBucketObservation[] | undefined} history
 * @returns {HistoricalBucketObservation[] | null}
 */
function readNormalizationHistory(history) {
  if (!Array.isArray(history) || history.length < NORMALIZATION_SESSION_COUNT) {
    return null;
  }

  const selected = history.slice(-NORMALIZATION_SESSION_COUNT);

  if (
    selected.some(
      (observation) =>
        !Number.isFinite(observation.volume) ||
        observation.volume <= 0 ||
        !Number.isFinite(observation.ret1)
    )
  ) {
    return null;
  }

  return selected;
}

/**
 * @param {AvailableFeatureVector[]} vectors
 * @returns {void}
 */
function validateCommonEndpoint(vectors) {
  const first = vectors[0];
  const allMatch = vectors.every(
    (vector) =>
      vector.sessionDate === first.sessionDate &&
      vector.bucketIndex === first.bucketIndex &&
      vector.endpoint === first.endpoint
  );

  if (!allMatch) {
    throw new Error("cross_sectional_endpoint_mismatch");
  }
}

/**
 * @param {string[]} targetInstrumentIds
 * @returns {void}
 */
function validateTargetRoster(targetInstrumentIds) {
  if (
    !Array.isArray(targetInstrumentIds) ||
    targetInstrumentIds.length < 10 ||
    new Set(targetInstrumentIds).size !== targetInstrumentIds.length
  ) {
    throw new Error("cross_sectional_roster_invalid");
  }
}

/**
 * @template T
 * @param {T[]} values
 * @param {(value: T) => number} readValue
 * @returns {Map<string, number>}
 */
function percentileRanks(values, readValue) {
  const ordered = values
    .map((value) => ({
      instrumentId: /** @type {AvailableFeatureVector} */ (value).instrumentId,
      value: readValue(value)
    }))
    .sort((left, right) => left.value - right.value);
  /** @type {Map<string, number>} */
  const ranks = new Map();
  let start = 0;

  while (start < ordered.length) {
    let end = start;

    while (
      end + 1 < ordered.length &&
      ordered[end + 1].value === ordered[start].value
    ) {
      end += 1;
    }

    const averageOneBasedRank = ((start + 1) + (end + 1)) / 2;
    const percentileRank = averageOneBasedRank / ordered.length - 0.5;

    for (let index = start; index <= end; index += 1) {
      ranks.set(ordered[index].instrumentId, percentileRank);
    }

    start = end + 1;
  }

  return ranks;
}

/**
 * @param {number[]} values
 * @returns {number}
 */
function mean(values) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

/**
 * @param {number[]} values
 * @returns {number}
 */
function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  const middle = Math.floor(ordered.length / 2);

  return ordered.length % 2 === 0
    ? (ordered[middle - 1] + ordered[middle]) / 2
    : ordered[middle];
}

/**
 * @param {number[]} values
 * @returns {number}
 */
function populationStandardDeviation(values) {
  const center = mean(values);
  const variance = mean(values.map((value) => (value - center) ** 2));

  return Math.sqrt(variance);
}

/**
 * @param {number} value
 * @param {number} minimum
 * @param {number} maximum
 * @returns {number}
 */
function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

/**
 * @param {string} reason
 * @returns {{status: "unavailable", reason: string}}
 */
function unavailable(reason) {
  return { status: "unavailable", reason };
}

module.exports = {
  MarketStateFeatureEngine,
  addCrossSectionalFeatures,
  calculateBaseFeatureVector
};
