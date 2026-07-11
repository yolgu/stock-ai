const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");

const {
  RateLimitAwareTossClient
} = require("../../extensions/app/market-data.cjs");
const {
  CachedTossAccessTokenProvider
} = require("../../extensions/app/stock-reference.cjs");
const {
  StoredTossCredentialRepository,
  TossOAuthClient
} = require("../../extensions/app/toss-credentials.cjs");
const {
  TOSS_DAILY_CANDLE_REQUEST_SPEC,
  TossDailyCandleArchiveClient
} = require("./toss-daily-client.cjs");

const ARCHIVE_SPEC = "toss-daily-candle-archive/v1";
const ARCHIVE_START_DATE = "1900-01-01";
const ARCHIVE_END_DATE = "2026-07-09";
const ARCHIVE_SYMBOLS = Object.freeze(["TSLA", "NVDA", "MU", "000660"]);
const DEFAULT_OUTPUT_DIRECTORY = path.join(__dirname, "data");
const OPEN_API_SPEC_URL =
  "https://openapi.tossinvest.com/openapi-docs/latest/openapi.json";
const SAFE_ERROR_CODES = new Set([
  "archive_authentication_failed",
  "archive_dependency_initialization_failed",
  "archive_failed",
  "archive_write_failed",
  "candle_pagination_limit_exceeded",
  "invalid_candle_archive",
  "invalid_candle_request",
  "invalid_candle_response",
  "invalid_toss_credentials",
  "market_data_rate_limited",
  "market_data_unavailable",
  "stalled_candle_pagination",
  "toss_connection_failed",
  "toss_daily_candle_request_failed"
]);
const TERMINATION_REASONS = new Set([
  "source_exhausted",
  "start_reached"
]);
const ISO_TIMESTAMP_WITH_ZONE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

class TossDailyArchiveError extends Error {
  constructor(code, message, recoverable, retryAfterSeconds = null) {
    super(message);
    this.name = "TossDailyArchiveError";
    this.code = code;
    this.recoverable = recoverable;

    if (retryAfterSeconds !== null) {
      this.retryAfterSeconds = retryAfterSeconds;
    }
  }
}

/**
 * @param {{
 *   mode?: "dry-run" | "live",
 *   outputDirectory?: string,
 *   credentialFilePath?: string,
 *   dependenciesFactory?: Function,
 *   fetcher?: typeof fetch,
 *   now?: () => string,
 *   rateLimitOptions?: object
 * }} options
 * @returns {Promise<object>}
 */
async function fetchTossDailyArchive(options = {}) {
  const mode = options.mode || "live";
  const outputDirectory = normalizeOutputDirectory(options.outputDirectory);
  const plan = createDryRunPlan(outputDirectory);

  if (mode === "dry-run") {
    return plan;
  }

  if (mode !== "live") {
    throw new TossDailyArchiveError(
      "invalid_candle_request",
      "Toss daily archive mode must be dry-run or live",
      false
    );
  }

  const fetchedAt = readFetchedAt(options.now);
  const dependencies = await createArchiveDependencies(options);
  const accessToken = await readAccessToken(dependencies, fetchedAt);
  const preparedArchives = [];

  for (const symbol of ARCHIVE_SYMBOLS) {
    const archive = await fetchSymbolArchive(
      dependencies.dailyCandleClient,
      symbol,
      accessToken
    );
    preparedArchives.push(prepareSymbolArchive(symbol, archive));
  }

  const manifest = createManifest(fetchedAt, preparedArchives);
  await persistArchive(outputDirectory, preparedArchives, manifest, options.fileSystem);

  return manifest;
}

/**
 * @param {string[]} argv
 * @param {object} options
 * @returns {Promise<number>}
 */
async function runCli(argv = process.argv.slice(2), options = {}) {
  const stdout = options.stdout || process.stdout;
  const stderr = options.stderr || process.stderr;

  try {
    const cliOptions = parseCliArguments(argv);
    const archiveOptions = {
      ...options,
      ...cliOptions
    };
    delete archiveOptions.stdout;
    delete archiveOptions.stderr;
    const result = await fetchTossDailyArchive(archiveOptions);
    stdout.write(serializeJson(result));

    return 0;
  } catch (error) {
    stderr.write(
      "Toss daily archive failed (" + readSafeErrorCode(error) + ")\n"
    );

    return 1;
  }
}

/**
 * @param {string} filePath
 * @param {unknown} value
 * @param {{ fileSystem?: typeof fs }} options
 * @returns {Promise<void>}
 */
async function writeJsonAtomically(filePath, value, options = {}) {
  const fileSystem = options.fileSystem || fs;
  const temporaryPath = filePath + "." + process.pid + "." +
    crypto.randomUUID() + ".tmp";

  try {
    await fileSystem.mkdir(path.dirname(filePath), { recursive: true });
    await fileSystem.writeFile(temporaryPath, serializeJson(value), {
      encoding: "utf8",
      mode: 0o600
    });
    await fileSystem.chmod(temporaryPath, 0o600);
    await fileSystem.rename(temporaryPath, filePath);
  } catch {
    try {
      await fileSystem.rm(temporaryPath, { force: true });
    } catch {
      // The original write failure is the actionable boundary error.
    }

    throw new TossDailyArchiveError(
      "archive_write_failed",
      "Toss daily archive file write failed",
      true
    );
  }
}

function createDryRunPlan(outputDirectory) {
  return {
    mode: "dry-run",
    spec: ARCHIVE_SPEC,
    endpoint: TOSS_DAILY_CANDLE_REQUEST_SPEC.endpoint,
    openApiSpecUrl: OPEN_API_SPEC_URL,
    symbols: [...ARCHIVE_SYMBOLS],
    request: createRequestSpec(false),
    output: {
      manifestPath: path.join(outputDirectory, "manifest.json"),
      rawFiles: ARCHIVE_SYMBOLS.map((symbol) => ({
        symbol,
        filePath: path.join(outputDirectory, "raw", symbol + ".json")
      }))
    }
  };
}

function createRequestSpec(includeSymbols) {
  const request = {
    startDate: ARCHIVE_START_DATE,
    endDate: ARCHIVE_END_DATE,
    interval: TOSS_DAILY_CANDLE_REQUEST_SPEC.interval,
    adjusted: TOSS_DAILY_CANDLE_REQUEST_SPEC.adjusted,
    count: TOSS_DAILY_CANDLE_REQUEST_SPEC.count
  };

  return includeSymbols
    ? { symbols: [...ARCHIVE_SYMBOLS], ...request }
    : request;
}

async function createArchiveDependencies(options) {
  const dependenciesFactory = typeof options.dependenciesFactory === "function"
    ? options.dependenciesFactory
    : createLiveDependencies;

  try {
    const dependencies = await dependenciesFactory({
      credentialFilePath: options.credentialFilePath ||
        path.resolve(process.cwd(), ".storage", "toss-credentials.local.json"),
      fetcher: options.fetcher || fetch,
      rateLimitOptions: options.rateLimitOptions || {}
    });

    if (
      !isRecord(dependencies) ||
      !isRecord(dependencies.accessTokenProvider) ||
      typeof dependencies.accessTokenProvider.readAccessToken !== "function" ||
      !isRecord(dependencies.dailyCandleClient) ||
      typeof dependencies.dailyCandleClient.fetchRangeWithMetadata !== "function"
    ) {
      throw new Error("invalid dependencies");
    }

    return dependencies;
  } catch (error) {
    throw createSanitizedBoundaryError(
      error,
      "archive_dependency_initialization_failed",
      "Toss daily archive dependencies could not be initialized"
    );
  }
}

function createLiveDependencies(options) {
  const credentialRepository = new StoredTossCredentialRepository(
    options.credentialFilePath
  );
  const oauthClient = new TossOAuthClient(options.fetcher);
  const accessTokenProvider = new CachedTossAccessTokenProvider(
    credentialRepository,
    oauthClient
  );
  const rateLimitClient = new RateLimitAwareTossClient(
    options.fetcher,
    options.rateLimitOptions
  );

  return {
    accessTokenProvider,
    dailyCandleClient: new TossDailyCandleArchiveClient(rateLimitClient)
  };
}

async function readAccessToken(dependencies, fetchedAt) {
  try {
    const accessToken = await dependencies.accessTokenProvider.readAccessToken(
      fetchedAt
    );

    if (typeof accessToken !== "string" || accessToken.trim() === "") {
      throw new Error("missing access token");
    }

    return accessToken;
  } catch (error) {
    throw createSanitizedBoundaryError(
      error,
      "archive_authentication_failed",
      "Toss daily archive authentication failed"
    );
  }
}

async function fetchSymbolArchive(dailyCandleClient, symbol, accessToken) {
  try {
    return await dailyCandleClient.fetchRangeWithMetadata({
      symbol,
      accessToken,
      startDate: ARCHIVE_START_DATE,
      endDate: ARCHIVE_END_DATE
    });
  } catch (error) {
    throw createSanitizedBoundaryError(
      error,
      "archive_failed",
      "Toss daily archive collection failed for " + symbol
    );
  }
}

function prepareSymbolArchive(symbol, archive) {
  validateArchiveMetadata(archive);
  const candles = validateAndCanonicalizeCandles(symbol, archive.candles);
  const rawText = serializeJson(candles);
  const rawFile = path.posix.join("raw", symbol + ".json");

  return {
    rawText,
    rawFile,
    entry: {
      symbol,
      currency: candles[0].currency,
      adjusted: TOSS_DAILY_CANDLE_REQUEST_SPEC.adjusted,
      rows: candles.length,
      start: candles[0].timestamp,
      end: candles[candles.length - 1].timestamp,
      pages: archive.pages,
      rawRows: archive.rawRows,
      duplicates: archive.duplicates,
      termination: archive.termination,
      candleCanonicalSha256: sha256Utf8(canonicalize(candles)),
      rawFileSha256: sha256Utf8(rawText),
      rawFile,
      quality: {
        ascending: true,
        unique: true,
        strictOhlcv: true,
        cutoffCompliant: true
      }
    }
  };
}

function validateArchiveMetadata(archive) {
  if (
    !isRecord(archive) ||
    !Array.isArray(archive.candles) ||
    !Number.isInteger(archive.pages) ||
    archive.pages < 1 ||
    !Number.isInteger(archive.rawRows) ||
    archive.rawRows < archive.candles.length ||
    !Number.isInteger(archive.duplicates) ||
    archive.duplicates < 0 ||
    archive.rawRows < archive.candles.length + archive.duplicates ||
    !TERMINATION_REASONS.has(archive.termination)
  ) {
    throw createInvalidArchiveError();
  }
}

function validateAndCanonicalizeCandles(symbol, values) {
  if (values.length === 0) {
    throw createInvalidArchiveError();
  }

  const candles = values.map(readCanonicalCandle);
  const currency = candles[0].currency;
  const seenTradingDates = new Set();
  let previousTimestampMs = null;

  for (const candle of candles) {
    const timestampMs = Date.parse(candle.timestamp);
    const dateKey = candle.timestamp.slice(0, 10);

    if (
      dateKey < ARCHIVE_START_DATE ||
      dateKey > ARCHIVE_END_DATE ||
      (previousTimestampMs !== null && timestampMs <= previousTimestampMs) ||
      seenTradingDates.has(dateKey) ||
      candle.currency !== currency
    ) {
      throw createInvalidArchiveError();
    }

    validateOhlcBounds(candle);
    seenTradingDates.add(dateKey);
    previousTimestampMs = timestampMs;
  }

  if (typeof symbol !== "string" || symbol.trim() === "") {
    throw createInvalidArchiveError();
  }

  return candles;
}

function readCanonicalCandle(value) {
  if (!isRecord(value)) {
    throw createInvalidArchiveError();
  }

  const timestamp = readTimestamp(value.timestamp);
  const openPrice = readDecimalText(value.openPrice, false);
  const highPrice = readDecimalText(value.highPrice, false);
  const lowPrice = readDecimalText(value.lowPrice, false);
  const closePrice = readDecimalText(value.closePrice, false);
  const volume = readDecimalText(value.volume, true);
  const currency = readCurrency(value.currency);

  return {
    timestamp,
    openPrice,
    highPrice,
    lowPrice,
    closePrice,
    volume,
    currency
  };
}

function readTimestamp(value) {
  if (
    typeof value !== "string" ||
    !ISO_TIMESTAMP_WITH_ZONE.test(value) ||
    !Number.isFinite(Date.parse(value)) ||
    !isValidDateKey(value.slice(0, 10))
  ) {
    throw createInvalidArchiveError();
  }

  return value;
}

function readDecimalText(value, allowZero) {
  if (
    typeof value !== "string" ||
    value === "" ||
    value.trim() !== value ||
    !Number.isFinite(Number(value)) ||
    (allowZero ? Number(value) < 0 : Number(value) <= 0)
  ) {
    throw createInvalidArchiveError();
  }

  return value;
}

function readCurrency(value) {
  if (typeof value !== "string" || !/^[A-Z]{3}$/.test(value)) {
    throw createInvalidArchiveError();
  }

  return value;
}

function validateOhlcBounds(candle) {
  const open = Number(candle.openPrice);
  const high = Number(candle.highPrice);
  const low = Number(candle.lowPrice);
  const close = Number(candle.closePrice);

  if (
    high < Math.max(open, low, close) ||
    low > Math.min(open, high, close)
  ) {
    throw createInvalidArchiveError();
  }
}

function isValidDateKey(value) {
  const parsedDateMs = Date.parse(value + "T00:00:00.000Z");

  return Number.isFinite(parsedDateMs) &&
    new Date(parsedDateMs).toISOString().slice(0, 10) === value;
}

function createManifest(fetchedAt, preparedArchives) {
  return {
    spec: ARCHIVE_SPEC,
    endpoint: TOSS_DAILY_CANDLE_REQUEST_SPEC.endpoint,
    openApiSpecUrl: OPEN_API_SPEC_URL,
    fetchedAt,
    request: createRequestSpec(true),
    archives: preparedArchives.map(({ entry }) => entry)
  };
}

async function persistArchive(
  outputDirectory,
  preparedArchives,
  manifest,
  fileSystem
) {
  for (const archive of preparedArchives) {
    await writeJsonAtomically(
      path.join(outputDirectory, archive.rawFile),
      JSON.parse(archive.rawText),
      { fileSystem }
    );
  }

  await writeJsonAtomically(
    path.join(outputDirectory, "manifest.json"),
    manifest,
    { fileSystem }
  );
}

function parseCliArguments(argv) {
  let mode = "live";
  let outputDirectory;

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];

    if (argument === "--dry-run") {
      mode = "dry-run";
      continue;
    }

    if (argument === "--live") {
      mode = "live";
      continue;
    }

    if (argument === "--output-directory") {
      const nextArgument = argv[index + 1];

      if (
        typeof nextArgument !== "string" ||
        nextArgument.trim() === "" ||
        nextArgument.startsWith("--")
      ) {
        throw new TossDailyArchiveError(
          "invalid_candle_request",
          "Toss daily archive output directory is required",
          false
        );
      }

      outputDirectory = nextArgument;
      index += 1;
      continue;
    }

    if (argument.startsWith("--output-directory=")) {
      outputDirectory = argument.slice("--output-directory=".length);
      continue;
    }

    throw new TossDailyArchiveError(
      "invalid_candle_request",
      "Unsupported Toss daily archive argument",
      false
    );
  }

  return outputDirectory === undefined
    ? { mode }
    : { mode, outputDirectory };
}

function normalizeOutputDirectory(value) {
  if (value === undefined) {
    return DEFAULT_OUTPUT_DIRECTORY;
  }

  if (typeof value !== "string" || value.trim() === "") {
    throw new TossDailyArchiveError(
      "invalid_candle_request",
      "Toss daily archive output directory is required",
      false
    );
  }

  return path.resolve(value);
}

function readFetchedAt(now) {
  const value = typeof now === "function"
    ? now()
    : new Date().toISOString();

  if (
    typeof value !== "string" ||
    !ISO_TIMESTAMP_WITH_ZONE.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new TossDailyArchiveError(
      "invalid_candle_request",
      "Toss daily archive fetchedAt must be an ISO timestamp",
      false
    );
  }

  return value;
}

function createInvalidArchiveError() {
  return new TossDailyArchiveError(
    "invalid_candle_archive",
    "Toss daily archive failed strict OHLCV validation",
    false
  );
}

function createSanitizedBoundaryError(error, fallbackCode, message) {
  const details = isRecord(error) ? error : {};
  const code = SAFE_ERROR_CODES.has(details.code)
    ? details.code
    : fallbackCode;
  const recoverable = typeof details.recoverable === "boolean"
    ? details.recoverable
    : true;
  const retryAfterSeconds = Number.isFinite(details.retryAfterSeconds) &&
    details.retryAfterSeconds >= 0
    ? details.retryAfterSeconds
    : null;

  return new TossDailyArchiveError(
    code,
    message,
    recoverable,
    retryAfterSeconds
  );
}

function readSafeErrorCode(error) {
  return isRecord(error) && SAFE_ERROR_CODES.has(error.code)
    ? error.code
    : "archive_failed";
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }

  if (isRecord(value)) {
    return "{" + Object.keys(value)
      .sort()
      .map((key) => JSON.stringify(key) + ":" + canonicalize(value[key]))
      .join(",") + "}";
  }

  return JSON.stringify(value);
}

function sha256Utf8(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function serializeJson(value) {
  return JSON.stringify(value, null, 2) + "\n";
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

if (require.main === module) {
  runCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}

module.exports = {
  TossDailyArchiveError,
  fetchTossDailyArchive,
  runCli,
  writeJsonAtomically
};
