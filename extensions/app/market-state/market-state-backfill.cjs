const crypto = require("node:crypto");

const DEFAULT_REQUIRED_SESSIONS = 60;
const MAXIMUM_PAGES_PER_RUN = 250;

/**
 * Background coordinator that fills only missing historical minute coverage.
 */
class MinuteHistoryBackfill {
  /**
   * @param {{
   *   minuteRepository: {
   *     readCoverage(instrumentId: string): Promise<{completeSessionDates: string[]}>,
   *     saveProviderCandles(input: Record<string, *>): Promise<Record<string, number>>
   *   },
   *   progressStore: {
   *     read(): Promise<Record<string, *>>,
   *     write(value: Record<string, *>): Promise<void>
   *   },
   *   tossMarketDataClient: {
   *     fetchCandles(
   *       symbol: string,
   *       interval: string,
   *       accessToken: string,
   *       count: number,
   *       before: string | null
   *     ): Promise<{candles: Array<Record<string, string>>, nextBefore: string | null}>
   *   },
   *   tossAccessTokenProvider: {
   *     readAccessToken(occurredAt: string): Promise<string>
   *   },
   *   nowIso: () => string,
   *   requiredSessions?: number
   * }} input
   */
  constructor(input) {
    this.minuteRepository = input.minuteRepository;
    this.progressStore = input.progressStore;
    this.tossMarketDataClient = input.tossMarketDataClient;
    this.tossAccessTokenProvider = input.tossAccessTokenProvider;
    this.nowIso = input.nowIso;
    this.requiredSessions =
      input.requiredSessions || DEFAULT_REQUIRED_SESSIONS;
    /** @type {Promise<void> | null} */
    this.activePromise = null;
  }

  /**
   * @param {{instrumentIds: string[], occurredAt: string}} input
   * @returns {Promise<Record<string, *>>}
   */
  async start(input) {
    if (this.activePromise !== null) {
      return this.readProgress();
    }

    const instrumentIds = uniqueInstrumentIds(input.instrumentIds);
    const coverage = await this.readCoverageByInstrument(instrumentIds);
    const completeInstrumentCount = instrumentIds.filter(
      (instrumentId) =>
        coverage[instrumentId] >= this.requiredSessions
    ).length;

    if (completeInstrumentCount === instrumentIds.length) {
      const completed = createProgress({
        jobId: crypto.randomUUID(),
        status: "complete",
        instrumentIds,
        coverage,
        requiredSessions: this.requiredSessions,
        currentInstrumentId: null,
        cursorByInstrument: {},
        error: null
      });
      await this.progressStore.write(completed);

      return completed;
    }

    const previous = await this.readProgress();
    const running = createProgress({
      jobId: crypto.randomUUID(),
      status: "running",
      instrumentIds,
      coverage,
      requiredSessions: this.requiredSessions,
      currentInstrumentId: firstIncompleteInstrument(
        instrumentIds,
        coverage,
        this.requiredSessions
      ),
      cursorByInstrument:
        ["running", "incomplete", "failed"].includes(previous.status) &&
        typeof previous.cursorByInstrument === "object"
          ? previous.cursorByInstrument
          : {},
      error: null
    });
    await this.progressStore.write(running);
    this.activePromise = this.run(
      instrumentIds,
      input.occurredAt,
      running
    ).finally(() => {
      this.activePromise = null;
    });

    return running;
  }

  /**
   * @returns {Promise<Record<string, *>>}
   */
  async readProgress() {
    const stored = await this.progressStore.read();

    if (
      typeof stored.jobId !== "string" ||
      typeof stored.status !== "string"
    ) {
      return {
        jobId: "not-started",
        status: "idle",
        requiredSessions: 0,
        completedSessions: 0,
        currentInstrumentId: null,
        totalInstrumentCount: 0,
        completedInstrumentCount: 0,
        cursorByInstrument: {},
        error: null
      };
    }

    return stored;
  }

  /**
   * @returns {Promise<void>}
   */
  async waitForIdle() {
    if (this.activePromise !== null) {
      await this.activePromise;
    }
  }

  /**
   * @param {string[]} instrumentIds
   * @param {string} occurredAt
   * @param {Record<string, *>} initialProgress
   * @returns {Promise<void>}
   */
  async run(instrumentIds, occurredAt, initialProgress) {
    const cursorByInstrument = {
      ...initialProgress.cursorByInstrument
    };

    try {
      const accessToken =
        await this.tossAccessTokenProvider.readAccessToken(occurredAt);
      let exhausted = false;

      for (const instrumentId of instrumentIds) {
        let coverage = await this.minuteRepository.readCoverage(instrumentId);

        if (
          coverage.completeSessionDates.length >= this.requiredSessions
        ) {
          continue;
        }

        let before =
          typeof cursorByInstrument[instrumentId] === "string"
            ? cursorByInstrument[instrumentId]
            : null;

        for (
          let pageNumber = 0;
          pageNumber < MAXIMUM_PAGES_PER_RUN;
          pageNumber += 1
        ) {
          await this.writeRunningProgress(
            instrumentIds,
            instrumentId,
            cursorByInstrument
          );
          const page = await this.tossMarketDataClient.fetchCandles(
            instrumentId,
            "1m",
            accessToken,
            100,
            before
          );
          const candles = Array.isArray(page.candles)
            ? page.candles
            : [];

          if (candles.length === 0) {
            exhausted = true;
            break;
          }

          await this.minuteRepository.saveProviderCandles({
            instrumentId,
            receivedAt: this.nowIso(),
            sourceRequestId: crypto.randomUUID(),
            candles
          });
          coverage = await this.minuteRepository.readCoverage(instrumentId);

          if (
            coverage.completeSessionDates.length >= this.requiredSessions
          ) {
            delete cursorByInstrument[instrumentId];
            break;
          }

          const nextBefore =
            typeof page.nextBefore === "string" &&
            page.nextBefore !== before
              ? page.nextBefore
              : null;

          if (nextBefore === null) {
            exhausted = true;
            break;
          }

          before = nextBefore;
          cursorByInstrument[instrumentId] = nextBefore;
        }
      }

      const coverage =
        await this.readCoverageByInstrument(instrumentIds);
      const complete = instrumentIds.every(
        (instrumentId) =>
          coverage[instrumentId] >= this.requiredSessions
      );
      await this.progressStore.write(
        createProgress({
          jobId: initialProgress.jobId,
          status: complete ? "complete" : "incomplete",
          instrumentIds,
          coverage,
          requiredSessions: this.requiredSessions,
          currentInstrumentId: null,
          cursorByInstrument,
          error: complete
            ? null
            : exhausted
              ? "provider_history_exhausted"
              : "page_budget_reached"
        })
      );
    } catch (error) {
      const coverage =
        await this.readCoverageByInstrument(instrumentIds);
      await this.progressStore.write(
        createProgress({
          jobId: initialProgress.jobId,
          status: "failed",
          instrumentIds,
          coverage,
          requiredSessions: this.requiredSessions,
          currentInstrumentId: null,
          cursorByInstrument,
          error:
            error &&
            typeof error === "object" &&
            typeof error.code === "string"
              ? error.code
              : error instanceof Error
                ? error.message
              : "minute_backfill_failed"
        })
      );
    }
  }

  /**
   * @param {string[]} instrumentIds
   * @param {string} currentInstrumentId
   * @param {Record<string, string>} cursorByInstrument
   * @returns {Promise<void>}
   */
  async writeRunningProgress(
    instrumentIds,
    currentInstrumentId,
    cursorByInstrument
  ) {
    const current = await this.readProgress();
    const coverage =
      await this.readCoverageByInstrument(instrumentIds);
    await this.progressStore.write(
      createProgress({
        jobId: current.jobId,
        status: "running",
        instrumentIds,
        coverage,
        requiredSessions: this.requiredSessions,
        currentInstrumentId,
        cursorByInstrument,
        error: null
      })
    );
  }

  /**
   * @param {string[]} instrumentIds
   * @returns {Promise<Record<string, number>>}
   */
  async readCoverageByInstrument(instrumentIds) {
    /** @type {Record<string, number>} */
    const coverage = {};

    for (const instrumentId of instrumentIds) {
      const value = await this.minuteRepository.readCoverage(instrumentId);
      coverage[instrumentId] = value.completeSessionDates.length;
    }

    return coverage;
  }
}

/**
 * @param {{
 *   jobId: string,
 *   status: string,
 *   instrumentIds: string[],
 *   coverage: Record<string, number>,
 *   requiredSessions: number,
 *   currentInstrumentId: string | null,
 *   cursorByInstrument: Record<string, string>,
 *   error: string | null
 * }} input
 * @returns {Record<string, *>}
 */
function createProgress(input) {
  const completedSessions = input.instrumentIds.reduce(
    (total, instrumentId) =>
      total +
      Math.min(
        input.requiredSessions,
        input.coverage[instrumentId] || 0
      ),
    0
  );

  return {
    jobId: input.jobId,
    status: input.status,
    requiredSessions:
      input.requiredSessions * input.instrumentIds.length,
    completedSessions,
    currentInstrumentId: input.currentInstrumentId,
    totalInstrumentCount: input.instrumentIds.length,
    completedInstrumentCount: input.instrumentIds.filter(
      (instrumentId) =>
        (input.coverage[instrumentId] || 0) >= input.requiredSessions
    ).length,
    cursorByInstrument: { ...input.cursorByInstrument },
    error: input.error
  };
}

/**
 * @param {string[]} instrumentIds
 * @param {Record<string, number>} coverage
 * @param {number} requiredSessions
 * @returns {string | null}
 */
function firstIncompleteInstrument(
  instrumentIds,
  coverage,
  requiredSessions
) {
  return instrumentIds.find(
    (instrumentId) =>
      (coverage[instrumentId] || 0) < requiredSessions
  ) || null;
}

/**
 * @param {string[]} values
 * @returns {string[]}
 */
function uniqueInstrumentIds(values) {
  return [...new Set(
    (Array.isArray(values) ? values : [])
      .map((value) => String(value || "").trim().toUpperCase())
      .filter((value) => /^[A-Z0-9._-]{1,16}$/.test(value))
  )];
}

module.exports = {
  MinuteHistoryBackfill
};
