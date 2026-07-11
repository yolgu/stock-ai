const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  fetchTossDailyArchive,
  runCli,
  writeJsonAtomically
} = require("./fetch-toss-daily.cjs");

const ARCHIVE_SPEC = "toss-daily-candle-archive/v1";
const CANDLES_ENDPOINT = "https://openapi.tossinvest.com/api/v1/candles";
const CUTOFF = "2026-07-09";
const FETCHED_AT = "2026-07-10T00:00:00.000Z";
const OPEN_API_SPEC_URL =
  "https://openapi.tossinvest.com/openapi-docs/latest/openapi.json";
const SYMBOLS = ["TSLA", "NVDA", "MU", "000660"];

function createCandle(timestamp, currency = "USD", overrides = {}) {
  return {
    timestamp,
    openPrice: "100",
    highPrice: "110",
    lowPrice: "90",
    closePrice: "105",
    volume: "1000",
    currency,
    ...overrides
  };
}

async function createTempDirectory(context, prefix) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  context.after(async () => {
    await fs.rm(directory, { recursive: true, force: true });
  });

  return directory;
}

function createDryRunPlan(outputDirectory) {
  return {
    mode: "dry-run",
    spec: ARCHIVE_SPEC,
    endpoint: CANDLES_ENDPOINT,
    openApiSpecUrl: OPEN_API_SPEC_URL,
    symbols: SYMBOLS,
    request: {
      startDate: "1900-01-01",
      endDate: CUTOFF,
      interval: "1d",
      adjusted: true,
      count: 200
    },
    output: {
      manifestPath: path.join(outputDirectory, "manifest.json"),
      rawFiles: SYMBOLS.map((symbol) => ({
        symbol,
        filePath: path.join(outputDirectory, "raw", symbol + ".json")
      }))
    }
  };
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }

  if (value !== null && typeof value === "object") {
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

test("dry-run returns a deterministic safe plan without touching credentials, tokens, files, or network", async () => {
  let dependencyFactoryCalls = 0;
  let fetchCalls = 0;
  const outputDirectory = "/safe/output/data";
  const options = {
    mode: "dry-run",
    outputDirectory,
    credentialFilePath: "/must-not-be-read/toss-credentials.local.json",
    dependenciesFactory: () => {
      dependencyFactoryCalls += 1;
      throw new Error("credential boundary must stay closed");
    },
    fetcher: async () => {
      fetchCalls += 1;
      throw new Error("network boundary must stay closed");
    }
  };

  const firstPlan = await fetchTossDailyArchive(options);
  const secondPlan = await fetchTossDailyArchive(options);

  assert.deepEqual(firstPlan, createDryRunPlan(outputDirectory));
  assert.deepEqual(secondPlan, firstPlan);
  assert.equal(dependencyFactoryCalls, 0);
  assert.equal(fetchCalls, 0);
  assert.doesNotMatch(
    JSON.stringify(firstPlan),
    /credential|secret|token|authorization|bearer/i
  );
});

test("CLI prints the dry-run path plan as stable JSON", async () => {
  let stdout = "";
  let stderr = "";
  let dependencyFactoryCalls = 0;
  const outputDirectory = "/safe/output/data";

  const exitCode = await runCli(
    ["--dry-run", "--output-directory", outputDirectory],
    {
      stdout: { write: (chunk) => { stdout += String(chunk); } },
      stderr: { write: (chunk) => { stderr += String(chunk); } },
      dependenciesFactory: () => {
        dependencyFactoryCalls += 1;
        throw new Error("live dependencies must not be constructed");
      }
    }
  );

  assert.equal(exitCode, 0);
  assert.equal(stderr, "");
  assert.equal(
    stdout,
    JSON.stringify(createDryRunPlan(outputDirectory), null, 2) + "\n"
  );
  assert.equal(dependencyFactoryCalls, 0);
});

test("CLI accepts an explicit live mode without exposing the access token", async (context) => {
  const outputDirectory = await createTempDirectory(context, "toss-daily-cli-live-");
  const accessToken = "fixture-cli-token-must-not-leak";
  let stdout = "";
  let stderr = "";

  const exitCode = await runCli(
    ["--live", "--output-directory", outputDirectory],
    {
      stdout: { write: (chunk) => { stdout += String(chunk); } },
      stderr: { write: (chunk) => { stderr += String(chunk); } },
      now: () => FETCHED_AT,
      dependenciesFactory: async () => ({
        accessTokenProvider: {
          readAccessToken: async () => accessToken
        },
        dailyCandleClient: {
          fetchRangeWithMetadata: async ({ symbol }) => ({
            candles: [
              createCandle(
                "2026-07-09T00:00:00.000Z",
                symbol === "000660" ? "KRW" : "USD"
              )
            ],
            pages: 1,
            rawRows: 1,
            duplicates: 0,
            termination: "source_exhausted"
          })
        }
      })
    }
  );

  assert.equal(exitCode, 0);
  assert.equal(stderr, "");
  assert.equal(stdout.includes(accessToken), false);
  assert.equal(JSON.parse(stdout).archives.length, 4);
});

test("CLI rejects an output-directory flag without a path before constructing live dependencies", async () => {
  let stdout = "";
  let stderr = "";
  let dependencyFactoryCalls = 0;

  const exitCode = await runCli(
    ["--dry-run", "--output-directory"],
    {
      stdout: { write: (chunk) => { stdout += String(chunk); } },
      stderr: { write: (chunk) => { stderr += String(chunk); } },
      dependenciesFactory: () => {
        dependencyFactoryCalls += 1;
        throw new Error("live dependencies must not be constructed");
      }
    }
  );

  assert.equal(exitCode, 1);
  assert.equal(stdout, "");
  assert.match(stderr, /invalid_candle_request/);
  assert.equal(dependencyFactoryCalls, 0);
});

test("live archive reuses the credential, OAuth, and rate-limit boundaries once and fetches symbols sequentially", async (context) => {
  const tempDirectory = await createTempDirectory(context, "toss-daily-live-");
  const credentialFilePath = path.join(
    tempDirectory,
    ".storage",
    "toss-credentials.local.json"
  );
  const outputDirectory = path.join(tempDirectory, "archive");
  const clientId = "fixture-client-id-must-not-leak";
  const clientSecret = "fixture-client-secret-must-not-leak";
  const accessToken = "fixture-access-token-must-not-leak";
  let oauthCalls = 0;
  let activeCandleRequests = 0;
  let maximumActiveCandleRequests = 0;
  const requestedSymbols = [];
  const authorizationHeaders = [];

  await fs.mkdir(path.dirname(credentialFilePath), { recursive: true });
  await fs.writeFile(
    credentialFilePath,
    JSON.stringify({
      clientId,
      clientSecret,
      savedAt: FETCHED_AT,
      lastValidatedAt: null,
      connectionStatus: "saved"
    }),
    "utf8"
  );

  const fetcher = async (url, init = {}) => {
    if (String(url) === "https://openapi.tossinvest.com/oauth2/token") {
      oauthCalls += 1;
      assert.equal(init.method, "POST");
      const tokenBody = new URLSearchParams(init.body);
      assert.equal(tokenBody.get("client_id"), clientId);
      assert.equal(tokenBody.get("client_secret"), clientSecret);

      return new Response(
        JSON.stringify({ access_token: accessToken, expires_in: 3600 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    const requestUrl = new URL(String(url));
    const symbol = requestUrl.searchParams.get("symbol");
    requestedSymbols.push(symbol);
    authorizationHeaders.push(new Headers(init.headers).get("Authorization"));
    activeCandleRequests += 1;
    maximumActiveCandleRequests = Math.max(
      maximumActiveCandleRequests,
      activeCandleRequests
    );
    await new Promise((resolve) => setImmediate(resolve));
    activeCandleRequests -= 1;

    assert.equal(requestUrl.origin + requestUrl.pathname, CANDLES_ENDPOINT);
    assert.deepEqual(Object.fromEntries(requestUrl.searchParams), {
      symbol,
      interval: "1d",
      count: "200",
      adjusted: "true"
    });

    const currency = symbol === "000660" ? "KRW" : "USD";

    return new Response(
      JSON.stringify({
        result: {
          candles: [createCandle("2026-07-09T00:00:00.000Z", currency)],
          nextBefore: null
        }
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const manifest = await fetchTossDailyArchive({
    mode: "live",
    outputDirectory,
    credentialFilePath,
    fetcher,
    now: () => FETCHED_AT,
    rateLimitOptions: {
      minimumIntervalByGroup: {
        MARKET_DATA_CHART: 0
      }
    }
  });

  assert.equal(oauthCalls, 1);
  assert.deepEqual(requestedSymbols, SYMBOLS);
  assert.equal(maximumActiveCandleRequests, 1);
  assert.deepEqual(
    authorizationHeaders,
    SYMBOLS.map(() => "Bearer " + accessToken)
  );
  assert.equal(manifest.spec, ARCHIVE_SPEC);
  assert.equal(manifest.endpoint, CANDLES_ENDPOINT);
  assert.equal(manifest.openApiSpecUrl, OPEN_API_SPEC_URL);
  assert.equal(manifest.fetchedAt, FETCHED_AT);
  assert.deepEqual(manifest.request, {
    symbols: SYMBOLS,
    startDate: "1900-01-01",
    endDate: CUTOFF,
    interval: "1d",
    adjusted: true,
    count: 200
  });
  assert.equal(manifest.archives.length, SYMBOLS.length);

  const persistedTexts = [];
  for (const entry of manifest.archives) {
    const rawPath = path.join(outputDirectory, entry.rawFile);
    const rawText = await fs.readFile(rawPath, "utf8");
    const candles = JSON.parse(rawText);
    persistedTexts.push(rawText);
    assert.deepEqual(candles, [
      createCandle(
        "2026-07-09T00:00:00.000Z",
        entry.symbol === "000660" ? "KRW" : "USD"
      )
    ]);
    assert.deepEqual(entry, {
      symbol: entry.symbol,
      currency: entry.symbol === "000660" ? "KRW" : "USD",
      adjusted: true,
      rows: 1,
      start: "2026-07-09T00:00:00.000Z",
      end: "2026-07-09T00:00:00.000Z",
      pages: 1,
      rawRows: 1,
      duplicates: 0,
      termination: "source_exhausted",
      candleCanonicalSha256: sha256Utf8(canonicalize(candles)),
      rawFileSha256: sha256Utf8(rawText),
      rawFile: path.join("raw", entry.symbol + ".json"),
      quality: {
        ascending: true,
        unique: true,
        strictOhlcv: true,
        cutoffCompliant: true
      }
    });
  }

  const manifestText = await fs.readFile(
    path.join(outputDirectory, "manifest.json"),
    "utf8"
  );
  assert.deepEqual(JSON.parse(manifestText), manifest);
  const persistedOutput = [manifestText, ...persistedTexts].join("\n");
  for (const secret of [clientId, clientSecret, accessToken]) {
    assert.equal(persistedOutput.includes(secret), false);
    assert.equal(JSON.stringify(manifest).includes(secret), false);
  }
  assert.doesNotMatch(persistedOutput, /authorization|bearer/i);
  assert.equal(
    (await fs.readdir(path.join(outputDirectory, "raw")))
      .some((fileName) => fileName.endsWith(".tmp")),
    false
  );
});

test("live archive rejects malformed, non-ascending, duplicate, or cutoff-violating OHLCV before writing files", async (context) => {
  const validFirst = createCandle("2026-07-08T00:00:00.000Z");
  const validSecond = createCandle("2026-07-09T00:00:00.000Z");
  const scenarios = [
    {
      name: "empty archive",
      candles: []
    },
    {
      name: "missing OHLCV field",
      candles: [{ ...validFirst, volume: undefined }]
    },
    {
      name: "non-string OHLCV field",
      candles: [{ ...validFirst, openPrice: 100 }]
    },
    {
      name: "inconsistent OHLC bounds",
      candles: [{ ...validFirst, highPrice: "80" }]
    },
    {
      name: "timestamp without timezone",
      candles: [createCandle("2026-07-08T00:00:00")]
    },
    {
      name: "mixed currencies",
      candles: [validFirst, createCandle("2026-07-09T00:00:00.000Z", "KRW")]
    },
    {
      name: "duplicate daily timestamp",
      candles: [validFirst, validFirst]
    },
    {
      name: "descending timestamps",
      candles: [validSecond, validFirst]
    },
    {
      name: "candle after cutoff",
      candles: [createCandle("2026-07-10T00:00:00.000Z")]
    }
  ];

  for (const scenario of scenarios) {
    await context.test(scenario.name, async (scenarioContext) => {
      const tempDirectory = await createTempDirectory(
        scenarioContext,
        "toss-daily-invalid-"
      );
      const outputDirectory = path.join(tempDirectory, "archive");
      const archive = {
        candles: scenario.candles,
        pages: 1,
        rawRows: scenario.candles.length,
        duplicates: 0,
        termination: "source_exhausted"
      };

      await assert.rejects(
        fetchTossDailyArchive({
          mode: "live",
          outputDirectory,
          now: () => FETCHED_AT,
          dependenciesFactory: () => ({
            accessTokenProvider: {
              readAccessToken: async () => "invalid-fixture-token-must-not-leak"
            },
            dailyCandleClient: {
              fetchRangeWithMetadata: async () => archive
            }
          })
        }),
        (error) => {
          assert.equal(error.code, "invalid_candle_archive");
          assert.doesNotMatch(String(error), /invalid-fixture-token/i);

          return true;
        }
      );
      await assert.rejects(fs.stat(outputDirectory), { code: "ENOENT" });
    });
  }
});

test("live archive validates pagination metadata before persisting it", async (context) => {
  const tempDirectory = await createTempDirectory(context, "toss-daily-metadata-");

  await assert.rejects(
    fetchTossDailyArchive({
      mode: "live",
      outputDirectory: path.join(tempDirectory, "archive"),
      now: () => FETCHED_AT,
      dependenciesFactory: () => ({
        accessTokenProvider: {
          readAccessToken: async () => "metadata-fixture-token-must-not-leak"
        },
        dailyCandleClient: {
          fetchRangeWithMetadata: async () => ({
            candles: [createCandle("2026-07-09T00:00:00.000Z")],
            pages: 0,
            rawRows: 0,
            duplicates: -1,
            termination: "unknown"
          })
        }
      })
    }),
    (error) => {
      assert.equal(error.code, "invalid_candle_archive");
      assert.doesNotMatch(String(error), /metadata-fixture-token/i);

      return true;
    }
  );
});

test("live and CLI errors never expose credential or token details", async () => {
  const secret = "credential-and-token-secret-must-not-leak";
  const options = {
    mode: "live",
    dependenciesFactory: () => ({
      accessTokenProvider: {
        readAccessToken: async () => {
          throw new Error("Authorization: Bearer " + secret);
        }
      },
      dailyCandleClient: {
        fetchRangeWithMetadata: async () => {
          throw new Error("must not fetch candles");
        }
      }
    })
  };

  await assert.rejects(
    fetchTossDailyArchive(options),
    (error) => {
      assert.equal(error.code, "archive_authentication_failed");
      assert.equal(String(error).includes(secret), false);
      assert.doesNotMatch(String(error), /authorization|bearer/i);

      return true;
    }
  );

  let stdout = "";
  let stderr = "";
  const exitCode = await runCli([], {
    ...options,
    stdout: { write: (chunk) => { stdout += String(chunk); } },
    stderr: { write: (chunk) => { stderr += String(chunk); } }
  });

  assert.equal(exitCode, 1);
  assert.equal(stdout, "");
  assert.equal(stderr.includes(secret), false);
  assert.doesNotMatch(stderr, /authorization|bearer/i);
  assert.match(stderr, /archive_authentication_failed/);
});

test("atomic JSON writes keep the previous target and remove temporary files when rename fails", async (context) => {
  const tempDirectory = await createTempDirectory(context, "toss-daily-atomic-");
  const filePath = path.join(tempDirectory, "manifest.json");
  const secret = "rename-error-secret-must-not-leak";
  await fs.writeFile(filePath, "{\"version\":\"old\"}\n", "utf8");

  await assert.rejects(
    writeJsonAtomically(
      filePath,
      { version: "new" },
      {
        fileSystem: {
          mkdir: fs.mkdir,
          writeFile: fs.writeFile,
          chmod: fs.chmod,
          rename: async () => {
            throw new Error(secret);
          },
          rm: fs.rm
        }
      }
    ),
    (error) => {
      assert.equal(error.code, "archive_write_failed");
      assert.equal(String(error).includes(secret), false);

      return true;
    }
  );

  assert.equal(await fs.readFile(filePath, "utf8"), "{\"version\":\"old\"}\n");
  assert.deepEqual(await fs.readdir(tempDirectory), ["manifest.json"]);
});
