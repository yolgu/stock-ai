const NORMALIZATION_WINDOWS = [1, 3, 4, 5, 6, 9, 12, 24];
const PRICE_PASSAGE_WINDOWS = [3, 4, 5, 6];
const MINIMUM_PRIOR_SESSIONS = 40;
const MAXIMUM_PRIOR_SESSIONS = 60;
const MARKET_BETA_SESSION_COUNT = 20;
const MINIMUM_BETA_PAIRS = 1_000;

/**
 * @typedef {{
 *   instrumentId: string,
 *   sessionDate: string,
 *   bucketIndex: number,
 *   close: number,
 *   volume: number
 * }} NormalizationBar
 */

/**
 * Calculates the reference episode normalization using only strict-prior sessions.
 *
 * @param {{
 *   bars: NormalizationBar[],
 *   marketBars: NormalizationBar[],
 *   priorSessions: Array<{bars: NormalizationBar[], marketBars: NormalizationBar[]}>
 * }} input
 * @returns {Record<string, *>}
 */
function calculateReferenceNormalization(input) {
  const priorSessions = Array.isArray(input.priorSessions)
    ? input.priorSessions.slice(-MAXIMUM_PRIOR_SESSIONS)
    : [];

  if (priorSessions.length < MINIMUM_PRIOR_SESSIONS) {
    return unavailable("forty_prior_sessions_required");
  }

  const bars = indexSessionBars(input.bars);
  const marketBars = indexSessionBars(input.marketBars);
  const endpointBucket = Math.max(...bars.keys());

  if (
    !Number.isInteger(endpointBucket) ||
    !bars.has(endpointBucket) ||
    !marketBars.has(endpointBucket)
  ) {
    return unavailable("synchronized_endpoint_required");
  }

  const beta = estimatePriorMarketBeta(priorSessions);

  if (beta === null) {
    return unavailable("prior_market_beta_unavailable");
  }

  const currentReturns = calculateReturns(bars);
  const currentMarketReturns = calculateReturns(marketBars);
  /** @type {Record<string, number>} */
  const zByWindow = {};
  /** @type {Record<string, number>} */
  const scaleByWindow = {};
  /** @type {Record<string, number>} */
  const relativeVolumeByWindow = {};
  /** @type {Record<string, number>} */
  const efficiencyByWindow = {};

  for (const window of NORMALIZATION_WINDOWS) {
    const statistics = calculateWindowStatistics({
      beta,
      bucket: endpointBucket,
      window,
      currentBars: bars,
      currentReturns,
      currentMarketReturns,
      priorSessions
    });

    if (statistics === null) {
      continue;
    }

    zByWindow[String(window)] = statistics.z;
    scaleByWindow[String(window)] = statistics.scale;
    relativeVolumeByWindow[String(window)] = statistics.relativeVolume;

    if (statistics.efficiency !== null) {
      efficiencyByWindow[String(window)] = statistics.efficiency;
    }
  }

  if (
    !PRICE_PASSAGE_WINDOWS.every(
      (window) => Number.isFinite(zByWindow[String(window)])
    ) ||
    !Number.isFinite(zByWindow["1"]) ||
    !Number.isFinite(relativeVolumeByWindow["1"])
  ) {
    return unavailable("reference_windows_unavailable");
  }

  const passage = classifyPricePassage(zByWindow);
  const passageScale = passage.window === null
    ? null
    : scaleByWindow[String(passage.window)] ?? null;

  return {
    status: "available",
    pricePassage: passage.direction,
    passageWindow: passage.window,
    passageScale,
    zOne: zByWindow["1"],
    relativeVolumeOne: relativeVolumeByWindow["1"],
    zByWindow,
    scaleByWindow,
    relativeVolumeByWindow,
    efficiencyByWindow,
    beta
  };
}

/**
 * Calculates the strict-prior residual-return z score for every visible
 * one-bar endpoint. The series is the market-row input used by the frozen
 * broad-downside classifier.
 *
 * @param {{
 *   bars: NormalizationBar[],
 *   marketBars: NormalizationBar[],
 *   priorSessions: Array<{bars: NormalizationBar[], marketBars: NormalizationBar[]}>
 * }} input
 * @returns {Map<number, number>}
 */
function calculateReferenceZOneByBucket(input) {
  const priorSessions = Array.isArray(input.priorSessions)
    ? input.priorSessions.slice(-MAXIMUM_PRIOR_SESSIONS)
    : [];
  /** @type {Map<number, number>} */
  const zOneByBucket = new Map();

  if (priorSessions.length < MINIMUM_PRIOR_SESSIONS) {
    return zOneByBucket;
  }

  const beta = estimatePriorMarketBeta(priorSessions);

  if (beta === null) {
    return zOneByBucket;
  }

  const currentReturns = calculateReturns(indexSessionBars(input.bars));
  const currentMarketReturns = calculateReturns(
    indexSessionBars(input.marketBars)
  );
  const priorReturnPairs = priorSessions.map((session) => ({
    stockReturns: calculateReturns(indexSessionBars(session.bars)),
    marketReturns: calculateReturns(indexSessionBars(session.marketBars))
  }));

  for (const [bucket, stockReturn] of currentReturns) {
    const marketReturn = currentMarketReturns.get(bucket);

    if (marketReturn === undefined) {
      continue;
    }

    const historicalResiduals = priorReturnPairs.flatMap((pair) => {
      const priorStockReturn = pair.stockReturns.get(bucket);
      const priorMarketReturn = pair.marketReturns.get(bucket);

      return priorStockReturn === undefined ||
        priorMarketReturn === undefined
        ? []
        : [priorStockReturn - beta * priorMarketReturn];
    });
    const baseline = robustBaseline(historicalResiduals);

    if (baseline === null) {
      continue;
    }

    zOneByBucket.set(
      bucket,
      (
        stockReturn -
        beta * marketReturn -
        baseline.center
      ) / baseline.scale
    );
  }

  return zOneByBucket;
}

/**
 * Calculates strict-prior SPY price-passage classifications without stock
 * residualization.
 *
 * @param {{
 *   marketBars: NormalizationBar[],
 *   priorSessions: Array<{bars: NormalizationBar[], marketBars: NormalizationBar[]}>
 * }} input
 * @returns {Map<number, {direction: "UP" | "DOWN" | "AMBIGUOUS" | "NONE", window: number | null}>}
 */
function calculateReferenceMarketPassageByBucket(input) {
  const priorSessions = Array.isArray(input.priorSessions)
    ? input.priorSessions.slice(-MAXIMUM_PRIOR_SESSIONS)
    : [];
  /** @type {Map<number, {direction: "UP" | "DOWN" | "AMBIGUOUS" | "NONE", window: number | null}>} */
  const passageByBucket = new Map();

  if (priorSessions.length < MINIMUM_PRIOR_SESSIONS) {
    return passageByBucket;
  }

  const currentReturns = calculateReturns(
    indexSessionBars(input.marketBars)
  );
  const priorMarketReturns = priorSessions.map((session) =>
    calculateReturns(indexSessionBars(session.marketBars))
  );

  for (const bucket of currentReturns.keys()) {
    /** @type {Record<string, number>} */
    const zByWindow = {};

    for (const window of PRICE_PASSAGE_WINDOWS) {
      const buckets = Array.from(
        { length: window },
        (_value, index) => bucket - window + 1 + index
      );

      if (
        buckets[0] < 1 ||
        buckets.some((candidate) => !currentReturns.has(candidate))
      ) {
        continue;
      }

      const historicalSums = priorMarketReturns.flatMap((returns) => {
        if (buckets.some((candidate) => !returns.has(candidate))) {
          return [];
        }

        return [
          buckets.reduce(
            (total, candidate) => total + returns.get(candidate),
            0
          )
        ];
      });
      const baseline = robustBaseline(historicalSums);

      if (baseline === null) {
        continue;
      }

      const currentSum = buckets.reduce(
        (total, candidate) => total + currentReturns.get(candidate),
        0
      );
      zByWindow[String(window)] =
        (currentSum - baseline.center) / baseline.scale;
    }

    if (
      PRICE_PASSAGE_WINDOWS.every(
        (window) => Number.isFinite(zByWindow[String(window)])
      )
    ) {
      passageByBucket.set(
        bucket,
        classifyPricePassage(zByWindow)
      );
    }
  }

  return passageByBucket;
}

/**
 * @param {Array<{bars: NormalizationBar[], marketBars: NormalizationBar[]}>} priorSessions
 * @returns {number | null}
 */
function estimatePriorMarketBeta(priorSessions) {
  const selected = priorSessions.slice(-MARKET_BETA_SESSION_COUNT);
  /** @type {Array<[number, number]>} */
  const pairs = [];

  for (const session of selected) {
    const stockReturns = calculateReturns(indexSessionBars(session.bars));
    const marketReturns = calculateReturns(indexSessionBars(session.marketBars));

    for (const [bucket, stockReturn] of stockReturns) {
      const marketReturn = marketReturns.get(bucket);

      if (marketReturn !== undefined) {
        pairs.push([marketReturn, stockReturn]);
      }
    }
  }

  if (pairs.length < MINIMUM_BETA_PAIRS) {
    return null;
  }

  const denominator = pairs.reduce(
    (total, pair) => total + pair[0] * pair[0],
    0
  );

  if (denominator <= 0) {
    return null;
  }

  return pairs.reduce(
    (total, pair) => total + pair[0] * pair[1],
    0
  ) / denominator;
}

/**
 * @param {{
 *   beta: number,
 *   bucket: number,
 *   window: number,
 *   currentBars: Map<number, NormalizationBar>,
 *   currentReturns: Map<number, number>,
 *   currentMarketReturns: Map<number, number>,
 *   priorSessions: Array<{bars: NormalizationBar[], marketBars: NormalizationBar[]}>
 * }} input
 * @returns {{z: number, scale: number, relativeVolume: number, efficiency: number | null} | null}
 */
function calculateWindowStatistics(input) {
  const windowBuckets = Array.from(
    { length: input.window },
    (_value, index) => input.bucket - input.window + 1 + index
  );

  if (
    windowBuckets[0] < 1 ||
    windowBuckets.some(
      (bucket) =>
        !input.currentReturns.has(bucket) ||
        !input.currentMarketReturns.has(bucket) ||
        !input.currentBars.has(bucket)
    )
  ) {
    return null;
  }

  /** @type {number[]} */
  const historicalResiduals = [];
  /** @type {number[]} */
  const historicalVolumes = [];

  for (const session of input.priorSessions) {
    const bars = indexSessionBars(session.bars);
    const stockReturns = calculateReturns(bars);
    const marketReturns = calculateReturns(indexSessionBars(session.marketBars));

    if (
      windowBuckets.some(
        (bucket) =>
          !stockReturns.has(bucket) ||
          !marketReturns.has(bucket) ||
          !bars.has(bucket)
      )
    ) {
      continue;
    }

    historicalResiduals.push(
      windowBuckets.reduce(
        (total, bucket) =>
          total +
          stockReturns.get(bucket) -
          input.beta * marketReturns.get(bucket),
        0
      )
    );
    historicalVolumes.push(
      windowBuckets.reduce(
        (total, bucket) => total + bars.get(bucket).volume,
        0
      )
    );
  }

  const baseline = robustBaseline(historicalResiduals);

  if (
    baseline === null ||
    historicalVolumes.length < MINIMUM_PRIOR_SESSIONS
  ) {
    return null;
  }

  const expectedVolume = median(historicalVolumes);

  if (expectedVolume <= 0) {
    return null;
  }

  const currentEpsilon = windowBuckets.map(
    (bucket) =>
      input.currentReturns.get(bucket) -
      input.beta * input.currentMarketReturns.get(bucket)
  );
  const currentResidual = currentEpsilon.reduce(
    (total, value) => total + value,
    0
  );
  const absoluteResidual = currentEpsilon.reduce(
    (total, value) => total + Math.abs(value),
    0
  );
  const currentVolume = windowBuckets.reduce(
    (total, bucket) => total + input.currentBars.get(bucket).volume,
    0
  );

  return {
    z: (currentResidual - baseline.center) / baseline.scale,
    scale: baseline.scale,
    relativeVolume: currentVolume / expectedVolume,
    efficiency:
      absoluteResidual > 0
        ? Math.abs(currentResidual) / absoluteResidual
        : null
  };
}

/**
 * @param {Record<string, number>} zByWindow
 * @returns {{direction: "UP" | "DOWN" | "AMBIGUOUS" | "NONE", window: number | null}}
 */
function classifyPricePassage(zByWindow) {
  const positive = PRICE_PASSAGE_WINDOWS.filter(
    (window) => zByWindow[String(window)] >= 3
  );
  const negative = PRICE_PASSAGE_WINDOWS.filter(
    (window) => zByWindow[String(window)] <= -3
  );

  if (positive.length > 0 && negative.length > 0) {
    return {
      direction: "AMBIGUOUS",
      window: Math.max(...positive, ...negative)
    };
  }

  if (positive.length > 0) {
    return { direction: "UP", window: Math.max(...positive) };
  }

  if (negative.length > 0) {
    return { direction: "DOWN", window: Math.max(...negative) };
  }

  return { direction: "NONE", window: null };
}

/**
 * @param {NormalizationBar[]} bars
 * @returns {Map<number, NormalizationBar>}
 */
function indexSessionBars(bars) {
  return new Map(
    (Array.isArray(bars) ? bars : [])
      .filter(
        (bar) =>
          Number.isInteger(bar.bucketIndex) &&
          bar.bucketIndex >= 0 &&
          Number.isFinite(bar.close) &&
          bar.close > 0 &&
          Number.isFinite(bar.volume) &&
          bar.volume >= 0
      )
      .map((bar) => [bar.bucketIndex, bar])
  );
}

/**
 * @param {Map<number, NormalizationBar>} bars
 * @returns {Map<number, number>}
 */
function calculateReturns(bars) {
  /** @type {Map<number, number>} */
  const returns = new Map();

  for (const [bucket, bar] of bars) {
    const previous = bars.get(bucket - 1);

    if (previous !== undefined) {
      returns.set(bucket, Math.log(bar.close) - Math.log(previous.close));
    }
  }

  return returns;
}

/**
 * @param {number[]} values
 * @returns {{center: number, scale: number} | null}
 */
function robustBaseline(values) {
  if (
    values.length < MINIMUM_PRIOR_SESSIONS ||
    values.some((value) => !Number.isFinite(value))
  ) {
    return null;
  }

  const center = median(values);
  const mad = median(values.map((value) => Math.abs(value - center)));
  let scale = 1.4826 * mad;

  if (scale === 0) {
    const variance = values.reduce(
      (total, value) => total + (value - center) ** 2,
      0
    ) / (values.length - 1);
    scale = Math.sqrt(variance);
  }

  if (!Number.isFinite(scale) || scale <= 0) {
    return null;
  }

  return { center, scale };
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
 * @param {string} reason
 * @returns {{status: "unavailable", reason: string}}
 */
function unavailable(reason) {
  return { status: "unavailable", reason };
}

module.exports = {
  calculateReferenceMarketPassageByBucket,
  calculateReferenceNormalization,
  calculateReferenceZOneByBucket,
  classifyPricePassage,
  estimatePriorMarketBeta,
  robustBaseline
};
