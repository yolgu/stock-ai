const assert = require("node:assert/strict");
const test = require("node:test");

const {
  TossDailyCandleArchiveClient
} = require("./toss-daily-client.cjs");

const ACCESS_TOKEN = "test-access-token-do-not-expose";
const RESPONSE_SECRET = "response-secret-do-not-expose";

function createCandle(timestamp, closePrice) {
  return {
    timestamp,
    openPrice: closePrice,
    highPrice: closePrice,
    lowPrice: closePrice,
    closePrice,
    volume: "100",
    currency: "USD"
  };
}

test("paginates daily candles with the official cursor contract and returns a deduplicated ascending range", async () => {
  const requests = [];
  const pages = [
    {
      result: {
        candles: [
          createCandle("2024-01-06T09:30:00-05:00", "106-out-of-range"),
          createCandle("2024-01-05T09:30:00-05:00", "105"),
          createCandle("2024-01-04T09:30:00-05:00", "104-first")
        ],
        nextBefore: "2024-01-04T09:30:00-05:00"
      }
    },
    {
      result: {
        candles: [
          createCandle("2024-01-04T09:30:00-05:00", "104-duplicate"),
          createCandle("2024-01-03T09:30:00-05:00", "103"),
          createCandle("2024-01-02T09:30:00-05:00", "102"),
          createCandle("2024-01-01T09:30:00-05:00", "101")
        ],
        nextBefore: null
      }
    }
  ];
  const rateLimitClient = {
    requestJson: async (url, init, group) => {
      requests.push({ url, init, group });

      return pages[requests.length - 1];
    }
  };
  const client = new TossDailyCandleArchiveClient(rateLimitClient);

  const candles = await client.fetchRange({
    symbol: "TSLA",
    accessToken: ACCESS_TOKEN,
    startDate: "2024-01-01",
    endDate: "2024-01-05"
  });

  assert.equal(requests.length, 2);
  const firstUrl = new URL(requests[0].url);
  const secondUrl = new URL(requests[1].url);
  assert.equal(firstUrl.origin + firstUrl.pathname, "https://openapi.tossinvest.com/api/v1/candles");
  assert.deepEqual(Object.fromEntries(firstUrl.searchParams), {
    symbol: "TSLA",
    interval: "1d",
    count: "200",
    adjusted: "true"
  });
  assert.equal(firstUrl.searchParams.has("before"), false);
  assert.equal(
    secondUrl.searchParams.get("before"),
    "2024-01-04T09:30:00-05:00"
  );
  assert.equal(requests[0].group, "MARKET_DATA_CHART");
  assert.equal(requests[1].group, "MARKET_DATA_CHART");
  assert.equal(requests.every(({ init }) => init.method === "GET"), true);
  assert.equal(
    new Headers(requests[0].init.headers).get("Authorization"),
    `Bearer ${ACCESS_TOKEN}`
  );
  assert.deepEqual(
    candles.map((candle) => candle.timestamp),
    [
      "2024-01-01T09:30:00-05:00",
      "2024-01-02T09:30:00-05:00",
      "2024-01-03T09:30:00-05:00",
      "2024-01-04T09:30:00-05:00",
      "2024-01-05T09:30:00-05:00"
    ]
  );
  assert.equal(candles[3].closePrice, "104-first");
  assert.equal(
    candles.some((candle) => candle.closePrice === "106-out-of-range"),
    false
  );
  assert.doesNotMatch(JSON.stringify(candles), /Authorization/i);
  assert.equal(JSON.stringify(candles).includes(ACCESS_TOKEN), false);
  assert.equal(requests.every(({ url }) => !url.includes(ACCESS_TOKEN)), true);
});

test("stops after a page reaches candles older than the inclusive start date", async () => {
  let requestCount = 0;
  const pages = [
    {
      result: {
        candles: [
          createCandle("2024-01-03T00:00:00.000Z", "103"),
          createCandle("2024-01-02T00:00:00.000Z", "102")
        ],
        nextBefore: "2024-01-02T00:00:00.000Z"
      }
    },
    {
      result: {
        candles: [
          createCandle("2024-01-02T00:00:00.000Z", "102-duplicate"),
          createCandle("2024-01-01T00:00:00.000Z", "101"),
          createCandle("2023-12-31T00:00:00.000Z", "100")
        ],
        nextBefore: "2023-12-31T00:00:00.000Z"
      }
    },
    {
      result: {
        candles: [createCandle("2023-12-30T00:00:00.000Z", "99")],
        nextBefore: null
      }
    }
  ];
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      const page = pages[requestCount];
      requestCount += 1;

      return page;
    }
  });

  const candles = await client.fetchRange({
    symbol: "NVDA",
    accessToken: ACCESS_TOKEN,
    startDate: "2024-01-01",
    endDate: "2024-01-03"
  });

  assert.equal(requestCount, 2);
  assert.deepEqual(
    candles.map((candle) => candle.timestamp),
    [
      "2024-01-01T00:00:00.000Z",
      "2024-01-02T00:00:00.000Z",
      "2024-01-03T00:00:00.000Z"
    ]
  );
});

test("redacts downstream authorization details from errors without logging them", async (context) => {
  const consoleError = context.mock.method(console, "error", () => {});
  const consoleLog = context.mock.method(console, "log", () => {});
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      throw Object.assign(
        new Error(`Authorization: Bearer ${ACCESS_TOKEN}`),
        {
          code: "market_data_rate_limited",
          recoverable: true,
          retryAfterSeconds: 2
        }
      );
    }
  });

  await assert.rejects(
    client.fetchRange({
      symbol: "MU",
      accessToken: ACCESS_TOKEN,
      startDate: "2024-01-01",
      endDate: "2024-01-02"
    }),
    (error) => {
      const errorText = String(error);

      assert.doesNotMatch(errorText, /Authorization/i);
      assert.equal(errorText.includes(ACCESS_TOKEN), false);
      assert.equal(error.code, "market_data_rate_limited");
      assert.equal(error.recoverable, true);
      assert.equal(error.retryAfterSeconds, 2);

      return true;
    }
  );
  assert.equal(consoleError.mock.callCount(), 0);
  assert.equal(consoleLog.mock.callCount(), 0);
});

test("rejects stalled pagination when nextBefore repeats before reaching the start date", async () => {
  const repeatedBefore = "2024-01-02T00:00:00.000Z";
  const pages = [
    {
      result: {
        candles: [
          createCandle("2024-01-03T00:00:00.000Z", "103"),
          createCandle(repeatedBefore, "102-first")
        ],
        nextBefore: repeatedBefore
      }
    },
    {
      result: {
        candles: [
          createCandle(repeatedBefore, "102-duplicate"),
          createCandle("2024-01-01T00:00:00.000Z", "101")
        ],
        nextBefore: repeatedBefore
      }
    }
  ];
  let requestCount = 0;
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      const page = pages[requestCount];
      requestCount += 1;

      if (page === undefined) {
        throw new Error("repeated cursor caused an extra request");
      }

      return page;
    }
  });

  await assert.rejects(
    client.fetchRange({
      symbol: "MU",
      accessToken: ACCESS_TOKEN,
      startDate: "2023-12-31",
      endDate: "2024-01-03"
    }),
    (error) => {
      assert.equal(error.code, "stalled_candle_pagination");
      assert.match(String(error), /pagination stalled/i);
      assert.equal(String(error).includes(ACCESS_TOKEN), false);

      return true;
    }
  );

  assert.equal(requestCount, 2);
});

test("rejects malformed candle response schemas without exposing response content", async (context) => {
  const scenarios = [
    {
      name: "missing result",
      payload: { diagnostic: RESPONSE_SECRET }
    },
    {
      name: "malformed result",
      payload: { result: [], diagnostic: RESPONSE_SECRET }
    },
    {
      name: "candles is not an array",
      payload: {
        result: { candles: RESPONSE_SECRET, nextBefore: null }
      }
    },
    {
      name: "nextBefore is missing",
      payload: {
        result: { candles: [], diagnostic: RESPONSE_SECRET }
      }
    },
    {
      name: "nextBefore is neither a string nor null",
      payload: {
        result: { candles: [], nextBefore: { diagnostic: RESPONSE_SECRET } }
      }
    },
    {
      name: "candle timestamp is invalid",
      payload: {
        result: {
          candles: [createCandle("not-a-timestamp", RESPONSE_SECRET)],
          nextBefore: null
        }
      }
    }
  ];

  for (const scenario of scenarios) {
    await context.test(scenario.name, async () => {
      const client = new TossDailyCandleArchiveClient({
        requestJson: async () => scenario.payload
      });

      await assert.rejects(
        client.fetchRange({
          symbol: "TSLA",
          accessToken: ACCESS_TOKEN,
          startDate: "2024-01-01",
          endDate: "2024-01-02"
        }),
        (error) => {
          assert.equal(error.code, "invalid_candle_response");
          assert.match(String(error), /response schema/i);
          assert.equal(String(error).includes(RESPONSE_SECRET), false);
          assert.equal(String(error).includes(ACCESS_TOKEN), false);

          return true;
        }
      );
    });
  }
});

test("rejects a blank symbol before making a request", async () => {
  let requestCount = 0;
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      requestCount += 1;

      return { result: { candles: [], nextBefore: null } };
    }
  });

  await assert.rejects(
    client.fetchRange({
      symbol: "   ",
      accessToken: ACCESS_TOKEN,
      startDate: "2024-01-01",
      endDate: "2024-01-02"
    }),
    (error) => {
      assert.equal(error.code, "invalid_candle_request");
      assert.match(String(error), /symbol is required/i);

      return true;
    }
  );
  assert.equal(requestCount, 0);
});

test("rejects a blank access token before making a request", async () => {
  let requestCount = 0;
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      requestCount += 1;

      return { result: { candles: [], nextBefore: null } };
    }
  });

  await assert.rejects(
    client.fetchRange({
      symbol: "TSLA",
      accessToken: "   ",
      startDate: "2024-01-01",
      endDate: "2024-01-02"
    }),
    (error) => {
      assert.equal(error.code, "invalid_candle_request");
      assert.match(String(error), /access token is required/i);

      return true;
    }
  );
  assert.equal(requestCount, 0);
});

test("fails safely when pagination exceeds a bounded page count", async () => {
  let requestCount = 0;
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      requestCount += 1;

      return {
        result: {
          candles: [],
          nextBefore: new Date(Date.UTC(2024, 0, 2, 0, 0, 0, requestCount)).toISOString()
        }
      };
    }
  });

  await assert.rejects(
    client.fetchRange({
      symbol: "000660",
      accessToken: ACCESS_TOKEN,
      startDate: "1900-01-01",
      endDate: "2100-01-01"
    }),
    /pagination exceeded the safety limit/i
  );
  assert.ok(requestCount > 1);
  assert.ok(requestCount <= 1_000);
});

test("reports archive pagination metadata without changing fetchRange compatibility", async () => {
  const pages = [
    {
      result: {
        candles: [
          createCandle("2024-01-06T00:00:00.000Z", "106"),
          createCandle("2024-01-05T00:00:00.000Z", "105"),
          createCandle("2024-01-04T00:00:00.000Z", "104-first")
        ],
        nextBefore: "2024-01-04T00:00:00.000Z"
      }
    },
    {
      result: {
        candles: [
          createCandle("2024-01-04T00:00:00.000Z", "104-duplicate"),
          createCandle("2024-01-03T00:00:00.000Z", "103"),
          createCandle("2024-01-02T00:00:00.000Z", "102"),
          createCandle("2024-01-01T00:00:00.000Z", "101")
        ],
        nextBefore: null
      }
    }
  ];
  let requestCount = 0;
  const client = new TossDailyCandleArchiveClient({
    requestJson: async () => {
      const page = pages[requestCount];
      requestCount += 1;

      return page;
    }
  });

  const archive = await client.fetchRangeWithMetadata({
    symbol: "TSLA",
    accessToken: ACCESS_TOKEN,
    startDate: "2024-01-01",
    endDate: "2024-01-05"
  });

  assert.deepEqual(
    archive.candles.map(({ timestamp }) => timestamp),
    [
      "2024-01-01T00:00:00.000Z",
      "2024-01-02T00:00:00.000Z",
      "2024-01-03T00:00:00.000Z",
      "2024-01-04T00:00:00.000Z",
      "2024-01-05T00:00:00.000Z"
    ]
  );
  assert.deepEqual(
    {
      pages: archive.pages,
      rawRows: archive.rawRows,
      duplicates: archive.duplicates,
      termination: archive.termination
    },
    {
      pages: 2,
      rawRows: 7,
      duplicates: 1,
      termination: "source_exhausted"
    }
  );
});
