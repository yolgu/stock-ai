const crypto = require("node:crypto");

/**
 * @param {Array<{
 *   instrumentId: string,
 *   sessionDate: string,
 *   barStart: string,
 *   barEnd: string,
 *   open: number,
 *   high: number,
 *   low: number,
 *   close: number,
 *   volume: number,
 *   availableAt: string,
 *   contentHash: string
 * }>} minuteBars
 * @returns {Record<string, *>}
 */
function aggregateCompletedFiveMinuteBar(minuteBars) {
  if (!Array.isArray(minuteBars) || minuteBars.length !== 5) {
    throw new Error("five_minute_bar_requires_exactly_five_minutes");
  }

  const bars = [...minuteBars].sort(
    (left, right) => Date.parse(left.barStart) - Date.parse(right.barStart)
  );
  validateCommonIdentity(bars);
  validateContiguousMinutes(bars);

  const sourceHashes = bars.map((bar) => bar.contentHash);
  const barEnd = bars[4].barEnd;

  return {
    instrumentId: bars[0].instrumentId,
    sessionDate: bars[0].sessionDate,
    barStart: bars[0].barStart,
    barEnd,
    open: bars[0].open,
    high: Math.max(...bars.map((bar) => bar.high)),
    low: Math.min(...bars.map((bar) => bar.low)),
    close: bars[4].close,
    volume: bars.reduce((total, bar) => total + bar.volume, 0),
    availableAt: bars
      .map((bar) => bar.availableAt)
      .sort((left, right) => Date.parse(right) - Date.parse(left))[0],
    sourceHashes,
    sourceHash: crypto
      .createHash("sha256")
      .update(sourceHashes.join("|"))
      .digest("hex")
  };
}

/**
 * @param {Array<Record<string, *>>} minuteBars
 * @param {string} availableBefore
 * @returns {Array<Record<string, *>>}
 */
function aggregateCompletedSession(minuteBars, availableBefore) {
  const availableBeforeMs = Date.parse(availableBefore);

  if (!Array.isArray(minuteBars) || !Number.isFinite(availableBeforeMs)) {
    throw new Error("five_minute_session_input_invalid");
  }

  /** @type {Map<number, Array<Record<string, *>>>} */
  const barsByBucket = new Map();

  for (const minuteBar of minuteBars) {
    const barEndMs = Date.parse(minuteBar.barEnd);
    const availableAtMs = Date.parse(minuteBar.availableAt);

    if (
      !Number.isInteger(minuteBar.minuteBucket) ||
      minuteBar.minuteBucket < 0 ||
      !Number.isFinite(barEndMs) ||
      barEndMs > availableBeforeMs ||
      !Number.isFinite(availableAtMs) ||
      availableAtMs > availableBeforeMs
    ) {
      continue;
    }

    const bucketIndex = Math.floor(minuteBar.minuteBucket / 5);
    const bucketBars = barsByBucket.get(bucketIndex) || [];
    bucketBars.push(minuteBar);
    barsByBucket.set(bucketIndex, bucketBars);
  }

  /** @type {Array<Record<string, *>>} */
  const completedBars = [];

  for (const [bucketIndex, unsortedBars] of barsByBucket) {
    const bucketBars = [...unsortedBars].sort(
      (left, right) => left.minuteBucket - right.minuteBucket
    );

    if (
      bucketBars.length !== 5 ||
      !bucketBars.every(
        (bar, index) => bar.minuteBucket === bucketIndex * 5 + index
      )
    ) {
      continue;
    }

    completedBars.push({
      ...aggregateCompletedFiveMinuteBar(bucketBars),
      bucketIndex
    });
  }

  return completedBars.sort(
    (left, right) => left.bucketIndex - right.bucketIndex
  );
}

function validateCommonIdentity(bars) {
  const first = bars[0];
  const identityMatches = bars.every(
    (bar) =>
      bar.instrumentId === first.instrumentId &&
      bar.sessionDate === first.sessionDate
  );

  if (!identityMatches) {
    throw new Error("five_minute_bar_identity_mismatch");
  }
}

function validateContiguousMinutes(bars) {
  for (let index = 0; index < bars.length; index += 1) {
    const bar = bars[index];
    const startMs = Date.parse(bar.barStart);
    const endMs = Date.parse(bar.barEnd);
    const nextStartMs = index < bars.length - 1
      ? Date.parse(bars[index + 1].barStart)
      : endMs;

    if (
      !Number.isFinite(startMs) ||
      !Number.isFinite(endMs) ||
      endMs - startMs !== 60_000 ||
      nextStartMs !== endMs
    ) {
      throw new Error("five_minute_bar_minutes_not_contiguous");
    }
  }
}

module.exports = {
  aggregateCompletedFiveMinuteBar,
  aggregateCompletedSession
};
