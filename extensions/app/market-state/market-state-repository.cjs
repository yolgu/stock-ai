const crypto = require("node:crypto");
const path = require("node:path");

const { JsonFileStore } = require("../storage.cjs");

const REGULAR_SESSION_MINUTES = 390;
const NEW_YORK_TIME = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23"
});

/**
 * Atomic instrument/session repository for canonical one-minute bars.
 */
class MinuteBarRepository {
  /**
   * @param {string} rootDirectory
   */
  constructor(rootDirectory) {
    this.rootDirectory = rootDirectory;
    this.manifestStore = new JsonFileStore(
      path.join(rootDirectory, "minutes", "manifest.json"),
      {
        schemaVersion: "market-state-minute-manifest.v1",
        instruments: {}
      }
    );
  }

  /**
   * @param {{
   *   instrumentId: string,
   *   receivedAt: string,
   *   sourceRequestId: string,
   *   candles: Array<Record<string, string>>
   * }} input
   * @returns {Promise<{accepted: number, revised: number, ignored: number}>}
   */
  async saveProviderCandles(input) {
    const instrumentId = normalizeInstrumentId(input.instrumentId);
    validateAcquisitionIdentity(input.receivedAt, input.sourceRequestId);
    /** @type {Map<string, Array<Record<string, *>>>} */
    const barsBySession = new Map();
    let ignored = 0;

    for (const candle of Array.isArray(input.candles) ? input.candles : []) {
      const bar = createCanonicalMinuteBar({
        candle,
        instrumentId,
        receivedAt: input.receivedAt,
        sourceRequestId: input.sourceRequestId
      });

      if (bar === null) {
        ignored += 1;
        continue;
      }

      const sessionBars = barsBySession.get(bar.sessionDate) || [];
      sessionBars.push(bar);
      barsBySession.set(bar.sessionDate, sessionBars);
    }

    let accepted = 0;
    let revised = 0;
    /** @type {Array<{sessionDate: string, minuteCount: number}>} */
    const sessionUpdates = [];

    for (const [sessionDate, bars] of barsBySession) {
      const partitionStore = this.createPartitionStore(instrumentId, sessionDate);
      const updatedPartition = await partitionStore.update((partition) => {
        const minutes = Array.isArray(partition.minutes)
          ? partition.minutes
          : [];
        const minuteByBucket = new Map(
          minutes.map((minute) => [minute.minuteBucket, minute])
        );

        for (const bar of bars) {
          const existing = minuteByBucket.get(bar.minuteBucket);

          if (existing === undefined) {
            minuteByBucket.set(bar.minuteBucket, {
              minuteBucket: bar.minuteBucket,
              canonical: bar,
              revisions: [bar]
            });
            accepted += 1;
            continue;
          }

          const revisions = Array.isArray(existing.revisions)
            ? existing.revisions
            : [existing.canonical];
          const isDuplicate = revisions.some(
            (revision) => revision.contentHash === bar.contentHash
          );

          if (isDuplicate) {
            ignored += 1;
            continue;
          }

          const nextRevisions = [...revisions, bar].sort(
            compareProviderRevisions
          );
          minuteByBucket.set(bar.minuteBucket, {
            minuteBucket: bar.minuteBucket,
            canonical: nextRevisions[nextRevisions.length - 1],
            revisions: nextRevisions
          });
          revised += 1;
        }

        return {
          schemaVersion: "market-state-minute-partition.v1",
          instrumentId,
          sessionDate,
          minutes: [...minuteByBucket.values()].sort(
            (left, right) => left.minuteBucket - right.minuteBucket
          )
        };
      });
      sessionUpdates.push({
        sessionDate,
        minuteCount: updatedPartition.minutes.length
      });
    }

    if (sessionUpdates.length > 0) {
      await this.updateManifest(instrumentId, sessionUpdates);
    }

    return { accepted, revised, ignored };
  }

  /**
   * @param {string} instrumentId
   * @param {string} sessionDate
   * @returns {Promise<Array<Record<string, *>>>}
   */
  async readSession(instrumentId, sessionDate) {
    const normalizedInstrumentId = normalizeInstrumentId(instrumentId);
    validateSessionDate(sessionDate);
    const partition = await this
      .createPartitionStore(normalizedInstrumentId, sessionDate)
      .read();

    return (Array.isArray(partition.minutes) ? partition.minutes : [])
      .map((minute) => minute.canonical)
      .filter((bar) => bar !== null && typeof bar === "object")
      .sort((left, right) => left.minuteBucket - right.minuteBucket);
  }

  /**
   * @param {string} instrumentId
   * @returns {Promise<{completeSessionDates: string[], minuteCount: number}>}
   */
  async readCoverage(instrumentId) {
    const normalizedInstrumentId = normalizeInstrumentId(instrumentId);
    const manifest = await this.manifestStore.read();
    const instrument = manifest.instruments &&
      manifest.instruments[normalizedInstrumentId];
    const sessions = instrument && instrument.sessions &&
      typeof instrument.sessions === "object"
      ? instrument.sessions
      : {};
    const sessionEntries = Object.entries(sessions);

    return {
      completeSessionDates: sessionEntries
        .filter((entry) => entry[1].minuteCount === REGULAR_SESSION_MINUTES)
        .map((entry) => entry[0])
        .sort(),
      minuteCount: sessionEntries.reduce(
        (total, entry) => total + Number(entry[1].minuteCount || 0),
        0
      )
    };
  }

  /**
   * @param {string} instrumentId
   * @returns {Promise<string[]>}
   */
  async readSessionDates(instrumentId) {
    const normalizedInstrumentId = normalizeInstrumentId(instrumentId);
    const manifest = await this.manifestStore.read();
    const instrument = manifest.instruments &&
      manifest.instruments[normalizedInstrumentId];

    return instrument &&
      instrument.sessions &&
      typeof instrument.sessions === "object"
      ? Object.keys(instrument.sessions).sort()
      : [];
  }

  /**
   * @param {string} instrumentId
   * @param {string} sessionDate
   * @returns {JsonFileStore}
   */
  createPartitionStore(instrumentId, sessionDate) {
    return new JsonFileStore(
      path.join(
        this.rootDirectory,
        "minutes",
        instrumentId,
        `${sessionDate}.json`
      ),
      {
        schemaVersion: "market-state-minute-partition.v1",
        instrumentId,
        sessionDate,
        minutes: []
      }
    );
  }

  /**
   * @param {string} instrumentId
   * @param {Array<{sessionDate: string, minuteCount: number}>} sessionUpdates
   * @returns {Promise<void>}
   */
  async updateManifest(instrumentId, sessionUpdates) {
    await this.manifestStore.update((manifest) => {
      const instruments = manifest.instruments &&
        typeof manifest.instruments === "object"
        ? { ...manifest.instruments }
        : {};
      const currentInstrument = instruments[instrumentId] || { sessions: {} };
      const sessions = currentInstrument.sessions &&
        typeof currentInstrument.sessions === "object"
        ? { ...currentInstrument.sessions }
        : {};

      for (const update of sessionUpdates) {
        sessions[update.sessionDate] = {
          minuteCount: update.minuteCount,
          complete: update.minuteCount === REGULAR_SESSION_MINUTES
        };
      }

      instruments[instrumentId] = { sessions };

      return {
        schemaVersion: "market-state-minute-manifest.v1",
        instruments
      };
    });
  }
}

/**
 * Atomic repository for formula snapshots, traces, session history, and
 * notification memory.
 */
class MarketStateSnapshotRepository {
  /**
   * @param {string} filePath
   */
  constructor(filePath) {
    this.store = new JsonFileStore(filePath, {
      schemaVersion: "market-state-formula-snapshots.v1",
      latestByCardId: {},
      historyByKey: {},
      detectionRecordsBySession: {}
    });
  }

  /**
   * @param {{
   *   snapshot: Record<string, *>,
   *   detectionRecords: Record<string, Record<string, *>>
   * }} input
   * @returns {Promise<void>}
   */
  async saveEvaluation(input) {
    validateFormulaSnapshot(input.snapshot);
    await this.store.update((stored) => {
      const latestByCardId = {
        ...(stored.latestByCardId || {})
      };
      const historyByKey = {
        ...(stored.historyByKey || {})
      };
      const detectionRecordsBySession = {
        ...(stored.detectionRecordsBySession || {})
      };
      latestByCardId[input.snapshot.cardId] = input.snapshot;

      for (const signal of input.snapshot.signals) {
        const historyKey = formulaHistoryKey(
          input.snapshot.cardId,
          input.snapshot.sessionDate,
          signal.signalId
        );
        const previousPoints = Array.isArray(historyByKey[historyKey])
          ? historyByKey[historyKey]
          : [];
        const nextPoint = {
          asOf: input.snapshot.asOf,
          bucketIndex: readBucketIndexFromSnapshot(input.snapshot),
          status: signal.status,
          percentile: signal.percentile,
          rawScore: signal.rawScore,
          dynamicThreshold: signal.dynamicThreshold,
          detected: signal.status === "detected"
        };
        historyByKey[historyKey] = [
          ...previousPoints.filter(
            (point) => point.asOf !== input.snapshot.asOf
          ),
          nextPoint
        ].sort(
          (left, right) =>
            Date.parse(left.asOf) - Date.parse(right.asOf)
        );
      }

      detectionRecordsBySession[
        detectionSessionKey(
          input.snapshot.cardId,
          input.snapshot.sessionDate
        )
      ] = input.detectionRecords;

      return {
        schemaVersion: "market-state-formula-snapshots.v1",
        latestByCardId,
        historyByKey,
        detectionRecordsBySession
      };
    });
  }

  /**
   * @param {string[] | undefined} cardIds
   * @returns {Promise<Array<Record<string, *>>>}
   */
  async readLatest(cardIds) {
    const stored = await this.store.read();
    const latestByCardId = stored.latestByCardId || {};

    if (Array.isArray(cardIds) && cardIds.length > 0) {
      return cardIds
        .map((cardId) => latestByCardId[cardId])
        .filter((snapshot) => snapshot !== undefined);
    }

    return Object.values(latestByCardId);
  }

  /**
   * @param {string} cardId
   * @param {string} signalId
   * @returns {Promise<Record<string, *> | null>}
   */
  async readTrace(cardId, signalId) {
    const snapshots = await this.readLatest([cardId]);
    const snapshot = snapshots[0];

    if (snapshot === undefined || !Array.isArray(snapshot.signals)) {
      return null;
    }

    const signal = snapshot.signals.find(
      (candidate) => candidate.signalId === signalId
    );

    if (signal === undefined) {
      return null;
    }

    return {
      ...signal,
      cardId: snapshot.cardId,
      symbol: snapshot.symbol,
      sessionDate: snapshot.sessionDate,
      asOf: snapshot.asOf,
      sourceGenerationId: snapshot.sourceGenerationId,
      formulaVersion: snapshot.formulaVersion,
      formulaContentSha256: snapshot.formulaContentSha256,
      observedState: snapshot.observedState,
      observedStateLabel: snapshot.observedStateLabel
    };
  }

  /**
   * @param {string} cardId
   * @param {string} signalId
   * @param {string} sessionDate
   * @returns {Promise<{cardId: string, signalId: string, sessionDate: string, points: Array<Record<string, *>>}>}
   */
  async readHistory(cardId, signalId, sessionDate) {
    const stored = await this.store.read();
    const historyKey = formulaHistoryKey(
      cardId,
      sessionDate,
      signalId
    );
    const points = stored.historyByKey &&
      Array.isArray(stored.historyByKey[historyKey])
      ? stored.historyByKey[historyKey]
      : [];

    return {
      cardId,
      signalId,
      sessionDate,
      points
    };
  }

  /**
   * @param {string} cardId
   * @param {string} sessionDate
   * @returns {Promise<Record<string, Record<string, *>>>}
   */
  async readDetectionRecords(cardId, sessionDate) {
    const stored = await this.store.read();
    const records = stored.detectionRecordsBySession &&
      stored.detectionRecordsBySession[
        detectionSessionKey(cardId, sessionDate)
      ];

    return records && typeof records === "object"
      ? records
      : {};
  }
}

/**
 * @param {{
 *   candle: Record<string, string>,
 *   instrumentId: string,
 *   receivedAt: string,
 *   sourceRequestId: string
 * }} input
 * @returns {Record<string, *> | null}
 */
function createCanonicalMinuteBar(input) {
  const barStartMs = Date.parse(input.candle.timestamp);
  const receivedAtMs = Date.parse(input.receivedAt);

  if (!Number.isFinite(barStartMs) || !Number.isFinite(receivedAtMs)) {
    return null;
  }

  const sessionCoordinate = readUsRegularSessionCoordinate(
    new Date(barStartMs)
  );

  if (sessionCoordinate === null) {
    return null;
  }

  const open = Number(input.candle.openPrice);
  const high = Number(input.candle.highPrice);
  const low = Number(input.candle.lowPrice);
  const close = Number(input.candle.closePrice);
  const volume = Number(input.candle.volume);

  if (
    ![open, high, low, close, volume].every(Number.isFinite) ||
    low <= 0 ||
    high < low ||
    open < low ||
    open > high ||
    close < low ||
    close > high ||
    volume < 0
  ) {
    return null;
  }

  const barStart = new Date(barStartMs).toISOString();
  const barEndMs = barStartMs + 60_000;
  const content = {
    instrumentId: input.instrumentId,
    sessionDate: sessionCoordinate.sessionDate,
    minuteBucket: sessionCoordinate.minuteBucket,
    barStart,
    barEnd: new Date(barEndMs).toISOString(),
    open,
    high,
    low,
    close,
    volume
  };
  const contentHash = sha256(canonicalJson(content));

  return {
    ...content,
    providerEventTime: barStart,
    receivedAt: new Date(receivedAtMs).toISOString(),
    availableAt: new Date(Math.max(barEndMs, receivedAtMs)).toISOString(),
    sourceRequestId: input.sourceRequestId,
    providerRevisionId: contentHash,
    contentHash
  };
}

/**
 * @param {Date} timestamp
 * @returns {{sessionDate: string, minuteBucket: number} | null}
 */
function readUsRegularSessionCoordinate(timestamp) {
  const parts = Object.fromEntries(
    NEW_YORK_TIME
      .formatToParts(timestamp)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  );
  const hour = Number(parts.hour);
  const minute = Number(parts.minute);
  const minuteOfDay = hour * 60 + minute;
  const minuteBucket = minuteOfDay - (9 * 60 + 30);

  if (
    !Number.isInteger(minuteBucket) ||
    minuteBucket < 0 ||
    minuteBucket >= REGULAR_SESSION_MINUTES
  ) {
    return null;
  }

  return {
    sessionDate: `${parts.year}-${parts.month}-${parts.day}`,
    minuteBucket
  };
}

/**
 * @param {Record<string, *>} left
 * @param {Record<string, *>} right
 * @returns {number}
 */
function compareProviderRevisions(left, right) {
  const receivedDifference =
    Date.parse(left.receivedAt) - Date.parse(right.receivedAt);

  if (receivedDifference !== 0) {
    return receivedDifference;
  }

  return String(left.contentHash).localeCompare(
    String(right.contentHash)
  );
}

/**
 * @param {string} value
 * @returns {string}
 */
function normalizeInstrumentId(value) {
  const instrumentId = String(value || "").trim().toUpperCase();

  if (!/^[A-Z0-9._-]{1,16}$/.test(instrumentId)) {
    throw new Error("minute_instrument_id_invalid");
  }

  return instrumentId;
}

/**
 * @param {string} receivedAt
 * @param {string} sourceRequestId
 * @returns {void}
 */
function validateAcquisitionIdentity(receivedAt, sourceRequestId) {
  if (
    !Number.isFinite(Date.parse(receivedAt)) ||
    typeof sourceRequestId !== "string" ||
    sourceRequestId.trim() === ""
  ) {
    throw new Error("minute_acquisition_identity_invalid");
  }
}

/**
 * @param {string} sessionDate
 * @returns {void}
 */
function validateSessionDate(sessionDate) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(sessionDate)) {
    throw new Error("minute_session_date_invalid");
  }
}

/**
 * @param {Record<string, *>} snapshot
 * @returns {void}
 */
function validateFormulaSnapshot(snapshot) {
  if (
    typeof snapshot !== "object" ||
    snapshot === null ||
    typeof snapshot.cardId !== "string" ||
    snapshot.cardId === "" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(snapshot.sessionDate) ||
    !Number.isFinite(Date.parse(snapshot.asOf)) ||
    !Array.isArray(snapshot.signals)
  ) {
    throw new Error("market_state_snapshot_invalid");
  }
}

/**
 * @param {Record<string, *>} snapshot
 * @returns {number | null}
 */
function readBucketIndexFromSnapshot(snapshot) {
  return Number.isInteger(snapshot.bucketIndex)
    ? snapshot.bucketIndex
    : null;
}

/**
 * @param {string} cardId
 * @param {string} sessionDate
 * @param {string} signalId
 * @returns {string}
 */
function formulaHistoryKey(cardId, sessionDate, signalId) {
  return JSON.stringify([cardId, sessionDate, signalId]);
}

/**
 * @param {string} cardId
 * @param {string} sessionDate
 * @returns {string}
 */
function detectionSessionKey(cardId, sessionDate) {
  return JSON.stringify([cardId, sessionDate]);
}

/**
 * @param {string} value
 * @returns {string}
 */
function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

/**
 * @param {*} value
 * @returns {string}
 */
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

module.exports = {
  MarketStateSnapshotRepository,
  MinuteBarRepository,
  createCanonicalMinuteBar,
  readUsRegularSessionCoordinate
};
