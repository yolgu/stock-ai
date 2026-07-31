const crypto = require("node:crypto");

const { aggregateCompletedSession } = require("./completed-five-minute-bar.cjs");
const { evaluateMarketStateEndpoint, signalPresentation } = require(
  "./market-state-evaluator.cjs"
);
const {
  addCrossSectionalFeatures,
  calculateBaseFeatureVector
} = require("./market-state-features.cjs");
const {
  evaluateFormula,
  loadFormulaRelease
} = require("./market-state-formula.cjs");
const {
  calculateReferenceMarketPassageByBucket,
  calculateReferenceNormalization,
  calculateReferenceZOneByBucket
} = require("./market-state-normalization.cjs");
const {
  advanceObservedMarketState,
  createInitialObservedMarketState
} = require("./observed-market-state.cjs");

const REQUIRED_PRIOR_SESSIONS = 60;
const FIRST_FORMULA_BUCKET = 6;

/**
 * Application service for ingestion, background preparation, formula evaluation,
 * and renderer read contracts.
 */
class MarketStateApplicationService {
  /**
   * @param {{
   *   watchlistRepository: {list(): Promise<Record<string, *>>},
   *   marketDataSnapshotRepository: {readLatest(cardIds?: string[]): Promise<Array<Record<string, *>>>},
   *   minuteRepository: Record<string, *>,
   *   snapshotRepository: Record<string, *>,
   *   backfill: Record<string, *>
   * }} input
   */
  constructor(input) {
    this.watchlistRepository = input.watchlistRepository;
    this.marketDataSnapshotRepository =
      input.marketDataSnapshotRepository;
    this.minuteRepository = input.minuteRepository;
    this.snapshotRepository = input.snapshotRepository;
    this.backfill = input.backfill;
    /** @type {Promise<void> | null} */
    this.activeCalculation = null;
    /** @type {Record<string, string>} */
    this.calculationErrorsByCardId = {};
  }

  /**
   * @param {{cardIds?: string[]}} payload
   * @param {string} occurredAt
   * @returns {Promise<Record<string, *>>}
   */
  async refresh(payload, occurredAt) {
    const watchlist = await this.watchlistRepository.list();
    const requestedCardIds = Array.isArray(payload.cardIds)
      ? new Set(payload.cardIds)
      : null;
    const cards = watchlist.activeCards.filter(
      (card) =>
        requestedCardIds === null || requestedCardIds.has(card.id)
    );
    await this.ingestLatestWatchlistCandles(cards, occurredAt);
    const release = loadFormulaRelease();
    const supportedCards = cards.filter((card) =>
      release.targetInstrumentIds.includes(normalizeSymbol(card.symbol))
    );
    const backfillProgress = supportedCards.length > 0
      ? await this.backfill.start({
          instrumentIds: collectionPriority(
            supportedCards.map((card) => card.symbol),
            release
          ),
          occurredAt
        })
      : await this.backfill.readProgress();
    this.scheduleCalculation(supportedCards, occurredAt);
    const storedSnapshots =
      await this.snapshotRepository.readLatest(
        cards.map((card) => card.id)
      );
    const storedByCardId = new Map(
      storedSnapshots.map((snapshot) => [snapshot.cardId, snapshot])
    );
    const snapshots = cards.map((card) => {
      const calculationError =
        this.calculationErrorsByCardId[card.id];

      if (calculationError === undefined) {
        const storedSnapshot = storedByCardId.get(card.id);

        if (storedSnapshot !== undefined) {
          return storedSnapshot;
        }
      }

      return createPendingSnapshot({
        card,
        occurredAt,
        release,
        reason: release.targetInstrumentIds.includes(
          normalizeSymbol(card.symbol)
        )
          ? calculationError ||
            "minute_history_collection_in_progress"
          : "symbol_outside_frozen_formula_roster"
      });
    });

    return {
      refreshedAt: occurredAt,
      snapshots,
      backfillProgress
    };
  }

  /**
   * @param {{cardIds?: string[]}} payload
   * @returns {Promise<{snapshots: Array<Record<string, *>>, backfillProgress: Record<string, *>}>}
   */
  async readLatest(payload) {
    return {
      snapshots: await this.snapshotRepository.readLatest(
        Array.isArray(payload.cardIds) ? payload.cardIds : undefined
      ),
      backfillProgress: await this.backfill.readProgress()
    };
  }

  /**
   * @param {{cardId: string, signalId: string}} payload
   * @returns {Promise<Record<string, *> | null>}
   */
  async readTrace(payload) {
    return this.snapshotRepository.readTrace(
      payload.cardId,
      payload.signalId
    );
  }

  /**
   * @param {{cardId: string, signalId: string, sessionDate: string}} payload
   * @returns {Promise<Record<string, *>>}
   */
  async readHistory(payload) {
    return this.snapshotRepository.readHistory(
      payload.cardId,
      payload.signalId,
      payload.sessionDate
    );
  }

  /**
   * @returns {Promise<void>}
   */
  async waitForIdle() {
    await this.backfill.waitForIdle();

    if (this.activeCalculation !== null) {
      await this.activeCalculation;
    }
  }

  /**
   * @param {Array<Record<string, *>>} cards
   * @param {string} occurredAt
   * @returns {Promise<void>}
   */
  async ingestLatestWatchlistCandles(cards, occurredAt) {
    if (cards.length === 0) {
      return;
    }

    const snapshots =
      await this.marketDataSnapshotRepository.readLatest(
        cards.map((card) => card.id)
      );

    for (const snapshot of snapshots) {
      const page = snapshot.observations &&
        snapshot.observations.intradayCandles;

      if (!page || !Array.isArray(page.candles)) {
        continue;
      }

      await this.minuteRepository.saveProviderCandles({
        instrumentId: snapshot.symbol,
        receivedAt:
          typeof page.fetchedAt === "string"
            ? page.fetchedAt
            : snapshot.capturedAt || occurredAt,
        sourceRequestId: snapshot.snapshotId,
        candles: page.candles
      });
    }
  }

  /**
   * @param {Array<Record<string, *>>} cards
   * @param {string} occurredAt
   * @returns {void}
   */
  scheduleCalculation(cards, occurredAt) {
    if (this.activeCalculation !== null || cards.length === 0) {
      return;
    }

    this.activeCalculation = this.calculateCards(cards, occurredAt)
      .finally(() => {
        this.activeCalculation = null;
      });
  }

  /**
   * @param {Array<Record<string, *>>} cards
   * @param {string} occurredAt
   * @returns {Promise<void>}
   */
  async calculateCards(cards, occurredAt) {
    for (const card of cards) {
      try {
        const evaluation = await calculateCardEvaluation({
          card,
          occurredAt,
          minuteRepository: this.minuteRepository,
          snapshotRepository: this.snapshotRepository
        });

        if (evaluation !== null) {
          await this.snapshotRepository.saveEvaluation(evaluation);
          delete this.calculationErrorsByCardId[card.id];
        }
      } catch (error) {
        this.calculationErrorsByCardId[card.id] =
          error instanceof Error
            ? error.message
            : "market_state_calculation_failed";
      }
    }
  }
}

/**
 * @param {{
 *   card: Record<string, *>,
 *   occurredAt: string,
 *   minuteRepository: Record<string, *>,
 *   snapshotRepository: Record<string, *>
 * }} input
 * @returns {Promise<{snapshot: Record<string, *>, detectionRecords: Record<string, Record<string, *>>} | null>}
 */
async function calculateCardEvaluation(input) {
  const symbol = normalizeSymbol(input.card.symbol);
  const sessionDates = await input.minuteRepository.readSessionDates(symbol);
  const marketSessionDates =
    await input.minuteRepository.readSessionDates("SPY");
  const commonSessionDates = intersection(
    sessionDates,
    marketSessionDates
  );

  if (commonSessionDates.length === 0) {
    return null;
  }

  const currentSessionDate =
    commonSessionDates[commonSessionDates.length - 1];
  const targetCoverage =
    await input.minuteRepository.readCoverage(symbol);
  const marketCoverage =
    await input.minuteRepository.readCoverage("SPY");
  const priorCompleteDates = intersection(
    targetCoverage.completeSessionDates,
    marketCoverage.completeSessionDates
  )
    .filter((sessionDate) => sessionDate < currentSessionDate)
    .slice(-REQUIRED_PRIOR_SESSIONS);

  if (priorCompleteDates.length < REQUIRED_PRIOR_SESSIONS) {
    return null;
  }

  const orderedDates = [...priorCompleteDates, currentSessionDate];
  const targetSessions = await loadFiveMinuteSessions(
    input.minuteRepository,
    symbol,
    orderedDates,
    input.occurredAt
  );
  const marketSessions = await loadFiveMinuteSessions(
    input.minuteRepository,
    "SPY",
    orderedDates,
    input.occurredAt
  );
  const release = loadFormulaRelease();
  const frozenRosterContext = await calculateFrozenRosterContext({
    minuteRepository: input.minuteRepository,
    occurredAt: input.occurredAt,
    targetSymbol: symbol,
    currentSessionDate,
    release,
    priorDates: priorCompleteDates,
    targetSessions,
    marketSessions
  });

  if (frozenRosterContext === null) {
    return null;
  }

  const current = frozenRosterContext.currentRow;
  const previousDetectionRecords =
    await input.snapshotRepository.readDetectionRecords(
      input.card.id,
      currentSessionDate
    );
  const generationSources = [
    ...current.bar.sourceHashes,
    ...current.marketBar.sourceHashes,
    ...frozenRosterContext.sourceHashes
  ];
  const sourceGenerationId = sha256(
    generationSources.sort().join("|")
  );

  return evaluateMarketStateEndpoint({
    cardId: input.card.id,
    symbol,
    sessionDate: currentSessionDate,
    endpoint: current.bar.barEnd,
    sourceGenerationId,
    bucketIndex: current.bar.bucketIndex,
    currentRiskState: current.observedState,
    featureValues: frozenRosterContext.featureVector.values,
    gateValues: frozenRosterContext.featureVector.gateValues,
    scoreHistoryBySignal:
      frozenRosterContext.scoreHistoryBySignal,
    previousDetectionRecords
  });
}

/**
 * @param {{
 *   minuteRepository: Record<string, *>,
 *   occurredAt: string,
 *   targetSymbol: string,
 *   currentSessionDate: string,
 *   release: Record<string, *>,
 *   priorDates: string[],
 *   targetSessions: Map<string, Array<Record<string, *>>>,
 *   marketSessions: Map<string, Array<Record<string, *>>>
 * }} input
 * @returns {Promise<{currentRow: Record<string, *>, featureVector: Record<string, *>, scoreHistoryBySignal: Record<string, number[]>, sourceHashes: string[]} | null>}
 */
async function calculateFrozenRosterContext(input) {
  const instruments = input.release.targetInstrumentIds;
  const priorDates = input.priorDates.slice(
    -REQUIRED_PRIOR_SESSIONS
  );

  if (priorDates.length < REQUIRED_PRIOR_SESSIONS) {
    return null;
  }

  const orderedDates = [...priorDates, input.currentSessionDate];
  const marketSessions = input.marketSessions;
  /** @type {Map<string, Map<string, Array<Record<string, *>>>>} */
  const sessionsByInstrument = new Map();

  for (const instrumentId of instruments) {
    sessionsByInstrument.set(
      instrumentId,
      instrumentId === input.targetSymbol
        ? input.targetSessions
        : await loadFiveMinuteSessions(
            input.minuteRepository,
            instrumentId,
            orderedDates,
            input.occurredAt
          )
    );
  }

  const panicFormula = input.release.signals.find(
    (signal) => signal.stateId === "PANIC_LIKE"
  );

  if (panicFormula === undefined) {
    throw new Error("panic_formula_missing");
  }

  /** @type {Record<string, number[]>} */
  const scoreHistoryBySignal = Object.fromEntries(
    input.release.signals.map((signal) => [signal.stateId, []])
  );

  for (
    let sessionIndex = 40;
    sessionIndex < REQUIRED_PRIOR_SESSIONS;
    sessionIndex += 1
  ) {
    const sessionDate = orderedDates[sessionIndex];
    const targetSessions = sessionsByInstrument.get(input.targetSymbol);

    if (targetSessions === undefined) {
      return null;
    }

    const contexts = createCrossSectionContexts({
      instruments,
      sessionDate,
      priorDates: orderedDates.slice(0, sessionIndex),
      sessionsByInstrument,
      marketSessions
    });
    const targetContext = contexts.find(
      (context) => context.instrumentId === input.targetSymbol
    );

    if (targetContext === undefined) {
      return null;
    }

    const marketContextByBucket =
      createReferenceMarketContextByBucket(
        contexts,
        instruments
      );
    const targetRows = calculateSessionRows({
      bars: targetContext.bars,
      marketBars: targetContext.marketBars,
      priorSessions: targetContext.priorSessions,
      marketContextByBucket
    });
    appendEligibleScores(
      scoreHistoryBySignal,
      targetRows,
      input.release
    );
    const riskStateByBucket = new Map(
      targetRows.map((row) => [
        row.bar.bucketIndex,
        row.observedState
      ])
    );
    const endpointCount = targetContext
      ? targetContext.bars.length
      : 0;

    for (
      let position = FIRST_FORMULA_BUCKET;
      position < endpointCount;
      position += 1
    ) {
      const vectors = calculateCrossSectionVectors(
        contexts,
        position
      );

      if (vectors.length < Math.ceil(instruments.length * 0.8)) {
        continue;
      }

      let augmented;

      try {
        augmented = addCrossSectionalFeatures(vectors, instruments);
      } catch {
        continue;
      }

      const target = augmented.get(input.targetSymbol);
      const bucketIndex =
        targetContext.bars[position].bucketIndex;

      if (
        target === undefined ||
        riskStateByBucket.get(bucketIndex) !== panicFormula.riskState
      ) {
        continue;
      }

      scoreHistoryBySignal.PANIC_LIKE.push(
        evaluateFormula(
          panicFormula.fixedFormula,
          target.values
        ).rawScore
      );
    }
  }

  const currentContexts = createCrossSectionContexts({
    instruments,
    sessionDate: input.currentSessionDate,
    priorDates,
    sessionsByInstrument,
    marketSessions
  });
  const currentTargetContext = currentContexts.find(
    (context) => context.instrumentId === input.targetSymbol
  );
  const currentEndpointCount = currentTargetContext
    ? currentTargetContext.bars.length
    : 0;

  if (currentEndpointCount <= FIRST_FORMULA_BUCKET) {
    return null;
  }

  const currentMarketContextByBucket =
    createReferenceMarketContextByBucket(
      currentContexts,
      instruments
    );
  const currentRows = calculateSessionRows({
    bars: currentTargetContext.bars,
    marketBars: currentTargetContext.marketBars,
    priorSessions: currentTargetContext.priorSessions,
    marketContextByBucket: currentMarketContextByBucket
  });
  const currentRow = currentRows[currentRows.length - 1];

  if (
    currentRow === undefined ||
    currentRow.observedState === "UNAVAILABLE"
  ) {
    return null;
  }

  const currentPosition = currentTargetContext.bars.findIndex(
    (bar) => bar.bucketIndex === currentRow.bar.bucketIndex
  );

  if (currentPosition < FIRST_FORMULA_BUCKET) {
    return null;
  }

  const currentVectors = calculateCrossSectionVectors(
    currentContexts,
    currentPosition
  );

  if (
    currentVectors.length < Math.ceil(instruments.length * 0.8)
  ) {
    return null;
  }

  const currentAugmented = addCrossSectionalFeatures(
    currentVectors,
    instruments
  );
  const featureVector = currentAugmented.get(input.targetSymbol);

  if (featureVector === undefined) {
    return null;
  }

  const sourceHashes = currentContexts.flatMap((context) => {
    const bar = context.bars[currentPosition];

    return bar && Array.isArray(bar.sourceHashes)
      ? bar.sourceHashes
      : [];
  });

  return {
    currentRow,
    featureVector,
    scoreHistoryBySignal,
    sourceHashes
  };
}

/**
 * @param {{
 *   instruments: string[],
 *   sessionDate: string,
 *   priorDates: string[],
 *   sessionsByInstrument: Map<string, Map<string, Array<Record<string, *>>>>,
 *   marketSessions: Map<string, Array<Record<string, *>>>
 * }} input
 * @returns {Array<Record<string, *>>}
 */
function createCrossSectionContexts(input) {
  return input.instruments.map((instrumentId) => {
    const sessions = input.sessionsByInstrument.get(instrumentId);
    const priorSessions = sessions
      ? createPriorSessionInputs(
          input.priorDates,
          sessions,
          input.marketSessions
        )
      : [];

    return {
      instrumentId,
      bars: sessions && sessions.get(input.sessionDate) || [],
      marketBars: input.marketSessions.get(input.sessionDate) || [],
      priorSessions,
      historicalByBucket: createHistoricalBucketObservations(
        priorSessions
      )
    };
  });
}

/**
 * Builds the fixed-roster market context used by the research reference
 * episode rules at every completed endpoint.
 *
 * @param {Array<Record<string, *>>} contexts
 * @param {string[]} targetInstrumentIds
 * @returns {Map<number, {marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE", downsideBreadth: number | null}>}
 */
function createReferenceMarketContextByBucket(
  contexts,
  targetInstrumentIds
) {
  const requiredMemberCount = Math.ceil(
    targetInstrumentIds.length * 0.8
  );
  /** @type {Map<string, Map<number, number>>} */
  const zOneByInstrument = new Map();

  for (const context of contexts) {
    zOneByInstrument.set(
      context.instrumentId,
      calculateReferenceZOneByBucket({
        bars: context.bars,
        marketBars: context.marketBars,
        priorSessions: context.priorSessions
      })
    );
  }

  const referenceContext = contexts.find(
    (context) =>
      context.marketBars.length > 0 &&
      context.priorSessions.length >= 40
  );
  const marketPassageByBucket = referenceContext === undefined
    ? new Map()
    : calculateReferenceMarketPassageByBucket({
        marketBars: referenceContext.marketBars,
        priorSessions: referenceContext.priorSessions
      });
  const bucketIndices = new Set(
    contexts.flatMap((context) =>
      context.bars.map((bar) => bar.bucketIndex)
    )
  );
  /** @type {Map<number, {marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE", downsideBreadth: number | null}>} */
  const marketContextByBucket = new Map();

  for (const bucketIndex of bucketIndices) {
    const availableZOne = targetInstrumentIds.flatMap(
      (instrumentId) => {
        const value = zOneByInstrument
          .get(instrumentId)
          ?.get(bucketIndex);

        return Number.isFinite(value) ? [value] : [];
      }
    );
    const downsideBreadth =
      availableZOne.length >= requiredMemberCount
        ? availableZOne.filter((value) => value <= -1).length /
          availableZOne.length
        : null;
    const marketPassage = marketPassageByBucket.get(bucketIndex);

    marketContextByBucket.set(bucketIndex, {
      marketPricePassage:
        marketPassage?.direction || "UNAVAILABLE",
      downsideBreadth
    });
  }

  return marketContextByBucket;
}

/**
 * @param {Array<Record<string, *>>} contexts
 * @param {number} position
 * @returns {Array<Record<string, *>>}
 */
function calculateCrossSectionVectors(contexts, position) {
  /** @type {Array<Record<string, *>>} */
  const vectors = [];

  for (const context of contexts) {
    if (
      context.bars.length <= position ||
      context.marketBars.length <= position
    ) {
      continue;
    }

    const vector = calculateBaseFeatureVector({
      bars: context.bars.slice(0, position + 1),
      marketBars: context.marketBars.slice(0, position + 1),
      historicalByBucket: context.historicalByBucket
    });

    if (vector.status === "available") {
      vectors.push(vector);
    }
  }

  return vectors;
}

/**
 * @param {{
 *   bars: Array<Record<string, *>>,
 *   marketBars: Array<Record<string, *>>,
 *   priorSessions: Array<{bars: Array<Record<string, *>>, marketBars: Array<Record<string, *>>}>,
 *   marketContextByBucket?: Map<number, {marketPricePassage: "UP" | "DOWN" | "AMBIGUOUS" | "NONE" | "UNAVAILABLE", downsideBreadth: number | null}>
 * }} input
 * @returns {Array<Record<string, *>>}
 */
function calculateSessionRows(input) {
  if (
    input.bars.length <= FIRST_FORMULA_BUCKET ||
    input.marketBars.length <= FIRST_FORMULA_BUCKET ||
    input.priorSessions.length < 40
  ) {
    return [];
  }

  const historicalByBucket =
    createHistoricalBucketObservations(input.priorSessions);
  const marketPassageByBucket =
    calculateReferenceMarketPassageByBucket({
      marketBars: input.marketBars,
      priorSessions: input.priorSessions
    });
  let observedState = createInitialObservedMarketState(
    input.bars[0].barStart
  );
  /** @type {Array<Record<string, *>>} */
  const rows = [];

  for (
    let position = FIRST_FORMULA_BUCKET;
    position < input.bars.length;
    position += 1
  ) {
    const bars = input.bars.slice(0, position + 1);
    const currentBar = bars[bars.length - 1];
    const marketBars = input.marketBars.filter(
      (bar) => bar.bucketIndex <= currentBar.bucketIndex
    );
    const featureVector = calculateBaseFeatureVector({
      bars,
      marketBars,
      historicalByBucket
    });

    if (featureVector.status !== "available") {
      continue;
    }

    const normalization = calculateReferenceNormalization({
      bars,
      marketBars,
      priorSessions: input.priorSessions
    });
    const marketContext = input.marketContextByBucket?.get(
      currentBar.bucketIndex
    );
    const marketPassage = marketPassageByBucket.get(
      currentBar.bucketIndex
    );
    observedState = advanceObservedMarketState(
      observedState,
      normalization.status === "available"
        ? {
            endpoint: currentBar.barEnd,
            bucketIndex: currentBar.bucketIndex,
            available: true,
            close: currentBar.close,
            high: currentBar.high,
            low: currentBar.low,
            pricePassage: normalization.pricePassage,
            passageScale: normalization.passageScale,
            passageWindow: normalization.passageWindow,
            zByWindow: normalization.zByWindow,
            scaleByWindow: normalization.scaleByWindow,
            closeHistory: bars.map((bar) => bar.close),
            marketPricePassage:
              marketContext?.marketPricePassage ||
              marketPassage?.direction ||
              "UNAVAILABLE",
            downsideBreadth:
              marketContext?.downsideBreadth ?? null,
            zOne: normalization.zOne,
            relativeVolumeOne: normalization.relativeVolumeOne
          }
        : {
            endpoint: currentBar.barEnd,
            bucketIndex: currentBar.bucketIndex,
            available: false,
            close: currentBar.close,
            high: currentBar.high,
            low: currentBar.low,
            pricePassage: "NONE",
            passageScale: null,
            passageWindow: null,
            zByWindow: {},
            scaleByWindow: {},
            closeHistory: bars.map((bar) => bar.close),
            marketPricePassage:
              marketContext?.marketPricePassage ||
              marketPassage?.direction ||
              "UNAVAILABLE",
            downsideBreadth:
              marketContext?.downsideBreadth ?? null,
            zOne: null,
            relativeVolumeOne: null
          }
    );
    rows.push({
      bar: currentBar,
      marketBar: marketBars[marketBars.length - 1],
      featureVector,
      observedState: observedState.state
    });
  }

  return rows;
}

/**
 * @param {Record<string, number[]>} scoreHistoryBySignal
 * @param {Array<Record<string, *>>} rows
 * @param {Record<string, *>} release
 * @returns {void}
 */
function appendEligibleScores(scoreHistoryBySignal, rows, release) {
  for (const row of rows) {
    if (row.observedState === "UNAVAILABLE") {
      continue;
    }

    for (const signal of release.signals) {
      if (
        signal.stateId === "PANIC_LIKE" ||
        signal.riskState !== row.observedState
      ) {
        continue;
      }

      try {
        scoreHistoryBySignal[signal.stateId].push(
          evaluateFormula(
            signal.fixedFormula,
            row.featureVector.values
          ).rawScore
        );
      } catch {
        continue;
      }
    }
  }
}

/**
 * @param {Array<{bars: Array<Record<string, *>>, marketBars: Array<Record<string, *>>}>} priorSessions
 * @returns {Record<string, Array<{volume: number, ret1: number}>>}
 */
function createHistoricalBucketObservations(priorSessions) {
  const selected = priorSessions.slice(-40);
  /** @type {Record<string, Array<{volume: number, ret1: number}>>} */
  const byBucket = {};

  for (const session of selected) {
    const marketByBucket = new Map(
      session.marketBars.map((bar) => [bar.bucketIndex, bar])
    );

    for (let position = 1; position < session.bars.length; position += 1) {
      const bar = session.bars[position];
      const previous = session.bars[position - 1];

      if (
        bar.bucketIndex !== previous.bucketIndex + 1 ||
        !marketByBucket.has(bar.bucketIndex)
      ) {
        continue;
      }

      const key = String(bar.bucketIndex);
      const observations = byBucket[key] || [];
      observations.push({
        volume: bar.volume,
        ret1: Math.log(bar.close) - Math.log(previous.close)
      });
      byBucket[key] = observations;
    }
  }

  return byBucket;
}

/**
 * @param {string[]} dates
 * @param {Map<string, Array<Record<string, *>>>} targetSessions
 * @param {Map<string, Array<Record<string, *>>>} marketSessions
 * @returns {Array<{bars: Array<Record<string, *>>, marketBars: Array<Record<string, *>>}>}
 */
function createPriorSessionInputs(
  dates,
  targetSessions,
  marketSessions
) {
  return dates
    .map((sessionDate) => ({
      bars: targetSessions.get(sessionDate) || [],
      marketBars: marketSessions.get(sessionDate) || []
    }))
    .filter(
      (session) =>
        session.bars.length === 78 &&
        session.marketBars.length === 78
    );
}

/**
 * @param {Record<string, *>} minuteRepository
 * @param {string} instrumentId
 * @param {string[]} dates
 * @param {string} occurredAt
 * @returns {Promise<Map<string, Array<Record<string, *>>>>}
 */
async function loadFiveMinuteSessions(
  minuteRepository,
  instrumentId,
  dates,
  occurredAt
) {
  /** @type {Map<string, Array<Record<string, *>>>} */
  const sessions = new Map();

  for (const sessionDate of dates) {
    const minutes = await minuteRepository.readSession(
      instrumentId,
      sessionDate
    );
    sessions.set(
      sessionDate,
      aggregateCompletedSession(minutes, occurredAt)
    );
  }

  return sessions;
}

/**
 * @param {{card: Record<string, *>, occurredAt: string, release: Record<string, *>, reason: string}} input
 * @returns {Record<string, *>}
 */
function createPendingSnapshot(input) {
  const collecting =
    input.reason === "minute_history_collection_in_progress";

  return {
    snapshotId: `pending:${input.card.id}`,
    cardId: input.card.id,
    symbol: normalizeSymbol(input.card.symbol),
    sessionDate: "",
    asOf: input.occurredAt,
    bucketIndex: null,
    sourceGenerationId: "pending",
    formulaVersion: input.release.formulaVersion,
    formulaContentSha256: input.release.contentSha256,
    observedState: "UNAVAILABLE",
    observedStateLabel: "데이터 부족",
    notifiedSignalIds: [],
    signals: input.release.signals.map((signal) => ({
      signalId: signal.stateId,
      displayName: signalPresentation[signal.stateId].displayName,
      formationLabel:
        signalPresentation[signal.stateId].formationLabel,
      horizonMinutes:
        signalPresentation[signal.stateId].horizonMinutes,
      status: collecting ? "collecting" : "unavailable",
      unavailableReason: input.reason,
      percentile: null,
      percentileNumerator: null,
      percentileDenominator: null,
      rawScore: null,
      dynamicThreshold: null,
      thresholdDistance: null,
      gate: null,
      requiredRiskState: signal.riskState,
      currentRiskState: "UNAVAILABLE",
      currentDetectionStartedAt: null,
      lastDetectedAt: null,
      trace: null
    }))
  };
}

/**
 * @param {string[]} preferredSymbols
 * @param {Record<string, *>} release
 * @returns {string[]}
 */
function collectionPriority(preferredSymbols, release) {
  return [...new Set([
    ...preferredSymbols.map(normalizeSymbol),
    release.marketProxyId,
    ...release.targetInstrumentIds
  ])];
}

/**
 * @param {string[]} left
 * @param {string[]} right
 * @returns {string[]}
 */
function intersection(left, right) {
  const rightSet = new Set(right);

  return left.filter((value) => rightSet.has(value)).sort();
}

/**
 * @param {string} value
 * @returns {string}
 */
function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase();
}

/**
 * @param {string} value
 * @returns {string}
 */
function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

module.exports = {
  MarketStateApplicationService,
  calculateCardEvaluation,
  calculateSessionRows,
  createPendingSnapshot
};
