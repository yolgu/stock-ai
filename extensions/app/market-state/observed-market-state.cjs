const NORMALIZATION_BAR_COUNT = 3;
const EPISODE_HORIZON_BARS = 24;
const FOLLOWUP_CONFIRMATION_SCALE_MULTIPLE = 2;
const RESOLUTION_SCALE_MULTIPLE = 1;
const REIGNITION_MINIMUM_GAP_BARS = 4;
const DIRECTIONAL_MERGE_GAP_BARS = 3;
const TREND_WINDOWS = [6, 9, 12];

/**
 * @typedef {{
 *   state: "BASELINE" | "AFTER_UP" | "AFTER_DOWN" | "UNAVAILABLE",
 *   phase: "BASELINE" | "ACTIVE" | "WATCHER" | "UNAVAILABLE",
 *   stateStartedAt: string,
 *   confirmationBucketIndex: number | null,
 *   episodeScale: number | null,
 *   runningExtreme: number | null,
 *   lastExtremeBucketIndex: number | null,
 *   lastDirectionalEndBucketIndex: number | null,
 *   normalizationBars: number,
 *   broadDownSeen: boolean,
 *   broadContextComplete: boolean
 * }} ObservedStateSnapshot
 */

/**
 * @typedef {{
 *   endpoint: string,
 *   bucketIndex: number,
 *   available: boolean,
 *   close: number,
 *   high: number,
 *   low: number,
 *   pricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE",
 *   passageScale: number | null,
 *   passageWindow: number | null,
 *   zByWindow: Record<string, number>,
 *   scaleByWindow: Record<string, number>,
 *   closeHistory: number[],
 *   marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE",
 *   downsideBreadth: number | null,
 *   zOne: number | null,
 *   relativeVolumeOne: number | null
 * }} ObservedStateEndpoint
 */

/**
 * @param {string} sessionStartedAt
 * @returns {ObservedStateSnapshot}
 */
function createInitialObservedMarketState(sessionStartedAt) {
  if (!Number.isFinite(Date.parse(sessionStartedAt))) {
    throw new Error("observed_state_session_start_invalid");
  }

  return baseline(sessionStartedAt);
}

/**
 * Advances the causal risk state using only information visible at the endpoint.
 *
 * @param {ObservedStateSnapshot} previous
 * @param {ObservedStateEndpoint} endpoint
 * @returns {ObservedStateSnapshot}
 */
function advanceObservedMarketState(previous, endpoint) {
  validateEndpoint(endpoint);

  if (!endpoint.available) {
    return unavailable(endpoint.endpoint);
  }

  if (
    previous.state === "BASELINE" ||
    previous.state === "UNAVAILABLE"
  ) {
    return startBaselineEpisode(endpoint);
  }

  validateOpenEpisode(previous);
  /** @type {ObservedStateSnapshot} */
  const current = {
    ...previous,
    normalizationBars: isNormalized(endpoint)
      ? previous.normalizationBars + 1
      : 0
  };
  const extremeUpdated = updateExtreme(current, endpoint);

  if (current.state === "AFTER_UP" && !extremeUpdated) {
    updateBroadDownContext(current, endpoint);
  }

  /** @type {Set<string>} */
  const candidates = followupCandidates(
    current,
    endpoint,
    extremeUpdated
  );

  if (current.normalizationBars >= NORMALIZATION_BAR_COUNT) {
    candidates.add("NORMALIZATION");
  }

  if (mergeSameDirectionPassage(current, endpoint)) {
    candidates.delete("UP_REIGNITION");
    candidates.delete("RENEWED_DOWN_PASSAGE");
  }

  const cause = selectFollowupCause(current.state, candidates);

  if (cause === "CENSORED") {
    return unavailable(endpoint.endpoint);
  }

  if (cause === "NORMALIZATION" || cause === "OTHER_COMPETING") {
    return baseline(endpoint.endpoint);
  }

  if (cause !== "NONE") {
    return startFollowupEpisode(current, endpoint, cause);
  }

  if (
    current.phase === "ACTIVE" &&
    reverseMove(current, endpoint) >=
      RESOLUTION_SCALE_MULTIPLE * current.episodeScale
  ) {
    return {
      ...current,
      phase: "WATCHER"
    };
  }

  if (
    endpoint.bucketIndex - current.confirmationBucketIndex >=
    EPISODE_HORIZON_BARS
  ) {
    return baseline(endpoint.endpoint);
  }

  return current;
}

/**
 * @param {ObservedStateEndpoint} endpoint
 * @returns {ObservedStateSnapshot}
 */
function startBaselineEpisode(endpoint) {
  if (endpoint.pricePassage === "AMBIGUOUS") {
    return baseline(endpoint.endpoint);
  }

  if (
    endpoint.pricePassage === "UP" ||
    endpoint.pricePassage === "DOWN"
  ) {
    return startDirectionalEpisode({
      endpoint,
      state:
        endpoint.pricePassage === "UP"
          ? "AFTER_UP"
          : "AFTER_DOWN",
      scale: requiredPassageScale(endpoint)
    });
  }

  const trendWindow = sustainedUpwardPathWindow(endpoint);

  if (trendWindow === null) {
    return baseline(endpoint.endpoint);
  }

  const trendScale = endpoint.scaleByWindow[String(trendWindow)];

  if (!Number.isFinite(trendScale) || trendScale <= 0) {
    throw new Error("observed_state_trend_scale_invalid");
  }

  return startDirectionalEpisode({
    endpoint,
    state: "AFTER_UP",
    scale: trendScale
  });
}

/**
 * @param {{
 *   endpoint: ObservedStateEndpoint,
 *   state: "AFTER_UP" | "AFTER_DOWN",
 *   scale: number
 * }} input
 * @returns {ObservedStateSnapshot}
 */
function startDirectionalEpisode(input) {
  return {
    state: input.state,
    phase: "ACTIVE",
    stateStartedAt: input.endpoint.endpoint,
    confirmationBucketIndex: input.endpoint.bucketIndex,
    episodeScale: input.scale,
    runningExtreme:
      input.state === "AFTER_UP"
        ? input.endpoint.high
        : input.endpoint.low,
    lastExtremeBucketIndex: input.endpoint.bucketIndex,
    lastDirectionalEndBucketIndex: input.endpoint.bucketIndex,
    normalizationBars: 0,
    broadDownSeen: false,
    broadContextComplete: true
  };
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @param {boolean} extremeUpdated
 * @returns {Set<string>}
 */
function followupCandidates(current, endpoint, extremeUpdated) {
  /** @type {Set<string>} */
  const candidates = new Set();

  if (current.state === "AFTER_UP") {
    const drawdown = reverseMove(current, endpoint);
    const broadDown =
      !extremeUpdated &&
      endpoint.pricePassage === "DOWN" &&
      current.broadDownSeen;
    const requiresBroadClassification =
      endpoint.pricePassage === "DOWN" ||
      drawdown >=
        FOLLOWUP_CONFIRMATION_SCALE_MULTIPLE * current.episodeScale;

    if (
      !extremeUpdated &&
      requiresBroadClassification &&
      !current.broadDownSeen &&
      !current.broadContextComplete
    ) {
      candidates.add("CENSORED");
      return candidates;
    }

    if (broadDown) {
      candidates.add("BROAD_DOWN_PASSAGE");
    }

    if (
      !extremeUpdated &&
      drawdown >=
        FOLLOWUP_CONFIRMATION_SCALE_MULTIPLE * current.episodeScale &&
      !current.broadDownSeen
    ) {
      candidates.add("POST_RALLY_RETRACEMENT");
    }

    if (
      qualifiesReignition(current, endpoint) &&
      endpoint.pricePassage === "UP"
    ) {
      candidates.add("UP_REIGNITION");
    }

    if (
      endpoint.pricePassage === "AMBIGUOUS" ||
      (
        endpoint.pricePassage === "DOWN" &&
        (
          extremeUpdated ||
          (
            !broadDown &&
            drawdown <
              FOLLOWUP_CONFIRMATION_SCALE_MULTIPLE *
                current.episodeScale
          )
        )
      )
    ) {
      candidates.add("OTHER_COMPETING");
    }

    return candidates;
  }

  const rebound = reverseMove(current, endpoint);

  if (
    qualifiesReignition(current, endpoint) &&
    endpoint.pricePassage === "DOWN"
  ) {
    candidates.add("RENEWED_DOWN_PASSAGE");
  }

  if (
    !extremeUpdated &&
    rebound >=
      FOLLOWUP_CONFIRMATION_SCALE_MULTIPLE * current.episodeScale
  ) {
    candidates.add("POST_SELLOFF_RECOVERY");
  }

  if (
    endpoint.pricePassage === "UP" ||
    endpoint.pricePassage === "AMBIGUOUS"
  ) {
    candidates.add("OTHER_COMPETING");
  }

  return candidates;
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @returns {void}
 */
function updateBroadDownContext(current, endpoint) {
  const breadthAvailable = Number.isFinite(endpoint.downsideBreadth);
  const endpointBroadDown =
    (
      breadthAvailable &&
      endpoint.downsideBreadth >= 0.8
    ) ||
    endpoint.marketPricePassage === "DOWN";

  current.broadDownSeen =
    current.broadDownSeen || endpointBroadDown;

  if (
    !endpointBroadDown &&
    (
      !breadthAvailable ||
      endpoint.marketPricePassage === "UNAVAILABLE"
    )
  ) {
    current.broadContextComplete = false;
  }
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @returns {boolean}
 */
function updateExtreme(current, endpoint) {
  if (
    current.state === "AFTER_UP" &&
    endpoint.high > current.runningExtreme
  ) {
    current.runningExtreme = endpoint.high;
    current.lastExtremeBucketIndex = endpoint.bucketIndex;
    current.broadDownSeen = false;
    current.broadContextComplete = true;
    return true;
  }

  if (
    current.state === "AFTER_DOWN" &&
    endpoint.low < current.runningExtreme
  ) {
    current.runningExtreme = endpoint.low;
    current.lastExtremeBucketIndex = endpoint.bucketIndex;
    current.broadDownSeen = false;
    current.broadContextComplete = true;
    return true;
  }

  return false;
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @returns {boolean}
 */
function mergeSameDirectionPassage(current, endpoint) {
  const directionMatches =
    (
      current.state === "AFTER_UP" &&
      endpoint.pricePassage === "UP"
    ) ||
    (
      current.state === "AFTER_DOWN" &&
      endpoint.pricePassage === "DOWN"
    );

  if (!directionMatches || endpoint.passageWindow === null) {
    return false;
  }

  const intervalStart =
    endpoint.bucketIndex - endpoint.passageWindow + 1;
  const overlaps =
    intervalStart <= current.lastDirectionalEndBucketIndex;
  const withinMergeGap =
    endpoint.bucketIndex - current.lastDirectionalEndBucketIndex <=
    DIRECTIONAL_MERGE_GAP_BARS;

  if (!overlaps && !withinMergeGap) {
    return false;
  }

  current.lastDirectionalEndBucketIndex = endpoint.bucketIndex;
  return true;
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @returns {boolean}
 */
function qualifiesReignition(current, endpoint) {
  return (
    endpoint.bucketIndex - current.confirmationBucketIndex >=
    REIGNITION_MINIMUM_GAP_BARS
  );
}

/**
 * @param {"AFTER_UP" | "AFTER_DOWN"} state
 * @param {Set<string>} candidates
 * @returns {string}
 */
function selectFollowupCause(state, candidates) {
  const priority = state === "AFTER_UP"
    ? [
        "CENSORED",
        "BROAD_DOWN_PASSAGE",
        "POST_RALLY_RETRACEMENT",
        "UP_REIGNITION",
        "NORMALIZATION",
        "OTHER_COMPETING"
      ]
    : [
        "CENSORED",
        "RENEWED_DOWN_PASSAGE",
        "POST_SELLOFF_RECOVERY",
        "NORMALIZATION",
        "OTHER_COMPETING"
      ];

  return priority.find((candidate) => candidates.has(candidate)) || "NONE";
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @param {string} cause
 * @returns {ObservedStateSnapshot}
 */
function startFollowupEpisode(current, endpoint, cause) {
  const passageCauses = new Set([
    "BROAD_DOWN_PASSAGE",
    "UP_REIGNITION",
    "RENEWED_DOWN_PASSAGE"
  ]);
  const scale = passageCauses.has(cause)
    ? requiredPassageScale(endpoint)
    : current.episodeScale;
  const state = [
    "BROAD_DOWN_PASSAGE",
    "POST_RALLY_RETRACEMENT",
    "RENEWED_DOWN_PASSAGE"
  ].includes(cause)
    ? "AFTER_DOWN"
    : "AFTER_UP";

  return startDirectionalEpisode({
    endpoint,
    state,
    scale
  });
}

/**
 * @param {ObservedStateEndpoint} endpoint
 * @returns {number | null}
 */
function sustainedUpwardPathWindow(endpoint) {
  const values = TREND_WINDOWS.map(
    (window) => endpoint.zByWindow[String(window)]
  );

  if (
    values.some((value) => !Number.isFinite(value)) ||
    Math.max(...values) < 2 ||
    Math.max(...values) >= 3 ||
    values.some((value) => value <= -3)
  ) {
    return null;
  }

  const qualifyingWindows = TREND_WINDOWS.filter(
    (window) => endpoint.zByWindow[String(window)] >= 2
  );

  if (qualifyingWindows.length === 0) {
    return null;
  }

  const window = Math.max(...qualifyingWindows);
  const scale = endpoint.scaleByWindow[String(window)];
  const closes = endpoint.closeHistory.slice(-window);

  if (
    !Number.isFinite(scale) ||
    scale <= 0 ||
    closes.length !== window ||
    closes.some((close) => !Number.isFinite(close) || close <= 0)
  ) {
    return null;
  }

  let runningPeak = Math.log(closes[0]);
  let adverseExcursion = 0;

  for (const close of closes) {
    const logClose = Math.log(close);
    runningPeak = Math.max(runningPeak, logClose);
    adverseExcursion = Math.max(
      adverseExcursion,
      runningPeak - logClose
    );
  }

  return adverseExcursion < 0.75 * scale
    ? window
    : null;
}

/**
 * @param {ObservedStateSnapshot} current
 * @param {ObservedStateEndpoint} endpoint
 * @returns {number}
 */
function reverseMove(current, endpoint) {
  return current.state === "AFTER_UP"
    ? Math.log(current.runningExtreme) - Math.log(endpoint.close)
    : Math.log(endpoint.close) - Math.log(current.runningExtreme);
}

/**
 * @param {ObservedStateEndpoint} endpoint
 * @returns {boolean}
 */
function isNormalized(endpoint) {
  return Number.isFinite(endpoint.zOne) &&
    Number.isFinite(endpoint.relativeVolumeOne) &&
    Math.abs(endpoint.zOne) < 0.5 &&
    endpoint.relativeVolumeOne < 1.25;
}

/**
 * @param {ObservedStateEndpoint} endpoint
 * @returns {number}
 */
function requiredPassageScale(endpoint) {
  if (
    !Number.isInteger(endpoint.passageWindow) ||
    endpoint.passageWindow <= 0 ||
    !Number.isFinite(endpoint.passageScale) ||
    endpoint.passageScale <= 0
  ) {
    throw new Error("observed_state_passage_scale_invalid");
  }

  return endpoint.passageScale;
}

/**
 * @param {string} endpoint
 * @returns {ObservedStateSnapshot}
 */
function baseline(endpoint) {
  return {
    state: "BASELINE",
    phase: "BASELINE",
    stateStartedAt: endpoint,
    confirmationBucketIndex: null,
    episodeScale: null,
    runningExtreme: null,
    lastExtremeBucketIndex: null,
    lastDirectionalEndBucketIndex: null,
    normalizationBars: 0,
    broadDownSeen: false,
    broadContextComplete: true
  };
}

/**
 * @param {string} endpoint
 * @returns {ObservedStateSnapshot}
 */
function unavailable(endpoint) {
  return {
    state: "UNAVAILABLE",
    phase: "UNAVAILABLE",
    stateStartedAt: endpoint,
    confirmationBucketIndex: null,
    episodeScale: null,
    runningExtreme: null,
    lastExtremeBucketIndex: null,
    lastDirectionalEndBucketIndex: null,
    normalizationBars: 0,
    broadDownSeen: false,
    broadContextComplete: true
  };
}

/**
 * @param {ObservedStateSnapshot} state
 * @returns {void}
 */
function validateOpenEpisode(state) {
  if (
    !["ACTIVE", "WATCHER"].includes(state.phase) ||
    !Number.isInteger(state.confirmationBucketIndex) ||
    !Number.isFinite(state.episodeScale) ||
    state.episodeScale <= 0 ||
    !Number.isFinite(state.runningExtreme) ||
    state.runningExtreme <= 0 ||
    !Number.isInteger(state.lastExtremeBucketIndex) ||
    !Number.isInteger(state.lastDirectionalEndBucketIndex)
  ) {
    throw new Error("observed_state_episode_invalid");
  }
}

/**
 * @param {ObservedStateEndpoint} endpoint
 * @returns {void}
 */
function validateEndpoint(endpoint) {
  if (
    typeof endpoint !== "object" ||
    endpoint === null ||
    !Number.isFinite(Date.parse(endpoint.endpoint)) ||
    !Number.isInteger(endpoint.bucketIndex) ||
    endpoint.bucketIndex < 0 ||
    typeof endpoint.available !== "boolean" ||
    !["UP", "DOWN", "AMBIGUOUS", "NONE"].includes(
      endpoint.pricePassage
    ) ||
    !["UP", "DOWN", "AMBIGUOUS", "NONE", "UNAVAILABLE"].includes(
      endpoint.marketPricePassage
    ) ||
    (
      endpoint.downsideBreadth !== null &&
      (
        !Number.isFinite(endpoint.downsideBreadth) ||
        endpoint.downsideBreadth < 0 ||
        endpoint.downsideBreadth > 1
      )
    ) ||
    !Array.isArray(endpoint.closeHistory) ||
    typeof endpoint.zByWindow !== "object" ||
    endpoint.zByWindow === null ||
    typeof endpoint.scaleByWindow !== "object" ||
    endpoint.scaleByWindow === null ||
    (
      endpoint.available &&
      (
        !Number.isFinite(endpoint.close) ||
        !Number.isFinite(endpoint.high) ||
        !Number.isFinite(endpoint.low) ||
        endpoint.low <= 0 ||
        endpoint.high < endpoint.low ||
        endpoint.close < endpoint.low ||
        endpoint.close > endpoint.high
      )
    )
  ) {
    throw new Error("observed_state_endpoint_invalid");
  }
}

module.exports = {
  advanceObservedMarketState,
  createInitialObservedMarketState
};
