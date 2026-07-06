const crypto = require("node:crypto");
const path = require("node:path");

const contract = require("../../contracts/app-runtime-contract.json");
const { StoredWatchlistRepository } = require("./storage.cjs");
const {
  StoredTossCredentialRepository,
  TossOAuthClient
} = require("./toss-credentials.cjs");
const {
  CachedTossAccessTokenProvider,
  StoredStockReferenceCache,
  TossStockInfoClient,
  createVerifiedWatchCard,
  verifyStockReferences
} = require("./stock-reference.cjs");
const {
  RateLimitAwareTossClient,
  StoredMarketDataSnapshotRepository,
  TossMarketDataClient,
  TossMarketInfoClient,
  readLatestMarketDataSnapshots,
  refreshMarketDataForCard,
  refreshMarketDataForWatchlist
} = require("./market-data.cjs");
const {
  StoredQuantIndicatorSnapshotRepository,
  readLatestQuantIndicatorSnapshots,
  refreshQuantIndicatorsForCard,
  refreshQuantIndicatorsForWatchlist
} = require("./quant-indicators.cjs");

function createDefaultRuntimeProfilePayload() {
  return {
    runtimeMode: "desktop",
    marketDataMode: "notConfigured",
    capabilities: [
      {
        name: "watchlist",
        enabled: true,
        reason: "관심종목 목록 기능 준비됨"
      },
      {
        name: "quantIndicators",
        enabled: true,
        reason: "정량 지표 계산 준비됨"
      },
      {
        name: "llmInsights",
        enabled: false,
        reason: "수동 AI 분석 단계 이후 활성화"
      },
      {
        name: "orders",
        enabled: false,
        reason: "주문 연동 단계 이후 활성화"
      }
    ]
  };
}

function createAppError(requestId, occurredAt, code, message, recoverable) {
  return {
    event: contract.events.appError,
    requestId,
    occurredAt,
    error: {
      code,
      message,
      recoverable
    }
  };
}

function parseRuntimeProfileRequest(data, occurredAt) {
  if (data === null || typeof data !== "object") {
    return {
      ok: false,
      error: createAppError(
        "unavailable",
        occurredAt,
        "invalid_request",
        "runtime profile request requires requestId",
        true
      )
    };
  }

  if (typeof data.requestId !== "string" || data.requestId.trim() === "") {
    return {
      ok: false,
      error: createAppError(
        "unavailable",
        occurredAt,
        "invalid_request",
        "runtime profile request requires requestId",
        true
      )
    };
  }

  return {
    ok: true,
    requestId: data.requestId
  };
}

function handleRuntimeProfileMessage(rawMessage, nowIso) {
  const message = JSON.parse(rawMessage);

  if (message.event !== contract.events.runtimeProfileRequest) {
    return undefined;
  }

  const occurredAt = nowIso();
  const parsed = parseRuntimeProfileRequest(message.data, occurredAt);

  if (!parsed.ok) {
    return parsed.error;
  }

  return {
    event: contract.events.runtimeProfileResponse,
    requestId: parsed.requestId,
    occurredAt,
    payload: createDefaultRuntimeProfilePayload()
  };
}

function createAppMessageHandler(options = {}) {
  const storageDirectory = options.storageDirectory || path.resolve(process.cwd(), ".storage");
  const watchlistRepository = new StoredWatchlistRepository(
    path.join(storageDirectory, "watchlist.local.json")
  );
  const tossCredentialRepository = new StoredTossCredentialRepository(
    path.join(storageDirectory, "toss-credentials.local.json")
  );
  const stockReferenceCache = new StoredStockReferenceCache(
    path.join(storageDirectory, "stock-reference-cache.local.json")
  );
  const marketDataSnapshotRepository = new StoredMarketDataSnapshotRepository(
    path.join(storageDirectory, "market-data-cache.local.json")
  );
  const quantIndicatorSnapshotRepository = new StoredQuantIndicatorSnapshotRepository(
    path.join(storageDirectory, "quant-indicator-cache.local.json")
  );
  const tossOAuthClient = new TossOAuthClient(options.fetcher || fetch);
  const tossAccessTokenProvider = new CachedTossAccessTokenProvider(
    tossCredentialRepository,
    tossOAuthClient
  );
  const tossStockInfoClient = new TossStockInfoClient(options.fetcher || fetch);
  const rateLimitAwareTossClient = new RateLimitAwareTossClient(options.fetcher || fetch);
  const tossMarketDataClient = new TossMarketDataClient(rateLimitAwareTossClient);
  const tossMarketInfoClient = new TossMarketInfoClient(rateLimitAwareTossClient);

  return async function handleAppMessage(rawMessage, nowIso) {
    const runtimeResponse = handleRuntimeProfileMessage(rawMessage, nowIso);

    if (runtimeResponse !== undefined) {
      return runtimeResponse;
    }

    const message = JSON.parse(rawMessage);
    const occurredAt = nowIso();
    const request = parseAppRequestData(message.data, occurredAt);

    if (!request.ok) {
      return request.error;
    }

    try {
      return await handleAppRequest({
        event: message.event,
        requestId: request.requestId,
        payload: request.payload,
        occurredAt,
        watchlistRepository,
        tossCredentialRepository,
        tossOAuthClient,
        stockReferenceCache,
        tossAccessTokenProvider,
        tossStockInfoClient,
        marketDataSnapshotRepository,
        quantIndicatorSnapshotRepository,
        tossMarketDataClient,
        tossMarketInfoClient
      });
    } catch (error) {
      return createAppError(
        request.requestId,
        occurredAt,
        normalizeErrorCode(error),
        error instanceof Error ? error.message : "extension request failed",
        error && typeof error.recoverable === "boolean" ? error.recoverable : true
      );
    }
  };
}

async function handleAppRequest(context) {
  if (context.event === contract.events.watchlistListRequest) {
    return createAppResponse(
      contract.events.watchlistListResponse,
      context.requestId,
      context.occurredAt,
      await context.watchlistRepository.list()
    );
  }

  if (context.event === contract.events.watchlistCreateRequest) {
    return createAppResponse(
      contract.events.watchlistCreateResponse,
      context.requestId,
      context.occurredAt,
      await context.watchlistRepository.create(context.payload, context.occurredAt)
    );
  }

  if (context.event === contract.events.watchlistUpdateRequest) {
    const result = await context.watchlistRepository.update(
      context.payload.cardId,
      context.payload,
      context.occurredAt
    );

    return createWatchCardResultOrError(
      result,
      contract.events.watchlistUpdateResponse,
      context.requestId,
      context.occurredAt
    );
  }

  if (context.event === contract.events.watchlistHideRequest) {
    const result = await context.watchlistRepository.hide(
      context.payload.cardId,
      context.occurredAt
    );

    return createWatchCardResultOrError(
      result,
      contract.events.watchlistHideResponse,
      context.requestId,
      context.occurredAt
    );
  }

  if (context.event === contract.events.watchlistArchiveRequest) {
    const result = await context.watchlistRepository.archive(
      context.payload.cardId,
      context.occurredAt
    );

    return createWatchCardResultOrError(
      result,
      contract.events.watchlistArchiveResponse,
      context.requestId,
      context.occurredAt
    );
  }

  if (context.event === contract.events.watchlistRestoreRequest) {
    const result = await context.watchlistRepository.restore(
      context.payload.cardId,
      context.occurredAt
    );

    return createWatchCardResultOrError(
      result,
      contract.events.watchlistRestoreResponse,
      context.requestId,
      context.occurredAt
    );
  }

  if (context.event === contract.events.watchlistDeleteRequest) {
    return createAppResponse(
      contract.events.watchlistDeleteResponse,
      context.requestId,
      context.occurredAt,
      await context.watchlistRepository.delete(context.payload.cardId)
    );
  }

  if (context.event === contract.events.watchlistReorderRequest) {
    return createAppResponse(
      contract.events.watchlistReorderResponse,
      context.requestId,
      context.occurredAt,
      await context.watchlistRepository.reorder(
        Array.isArray(context.payload.orderedCardIds)
          ? context.payload.orderedCardIds
          : [],
        context.occurredAt
      )
    );
  }

  if (context.event === contract.events.stockReferenceVerifyRequest) {
    return createAppResponse(
      contract.events.stockReferenceVerifyResponse,
      context.requestId,
      context.occurredAt,
      await verifyStockReferences(context, context.payload.rawInput)
    );
  }

  if (context.event === contract.events.watchlistCreateVerifiedRequest) {
    return createAppResponse(
      contract.events.watchlistCreateVerifiedResponse,
      context.requestId,
      context.occurredAt,
      await createVerifiedWatchCard(context)
    );
  }

  if (context.event === contract.events.marketDataRefreshWatchlistRequest) {
    return createAppResponse(
      contract.events.marketDataRefreshWatchlistResponse,
      context.requestId,
      context.occurredAt,
      await refreshMarketDataForWatchlist(context, context.payload)
    );
  }

  if (context.event === contract.events.marketDataRefreshCardRequest) {
    return createAppResponse(
      contract.events.marketDataRefreshCardResponse,
      context.requestId,
      context.occurredAt,
      await refreshMarketDataForCard(context, context.payload)
    );
  }

  if (context.event === contract.events.marketDataLatestSnapshotsRequest) {
    return createAppResponse(
      contract.events.marketDataLatestSnapshotsResponse,
      context.requestId,
      context.occurredAt,
      await readLatestMarketDataSnapshots(context, context.payload)
    );
  }

  if (context.event === contract.events.quantIndicatorsRefreshWatchlistRequest) {
    return createAppResponse(
      contract.events.quantIndicatorsRefreshWatchlistResponse,
      context.requestId,
      context.occurredAt,
      await refreshQuantIndicatorsForWatchlist(context, context.payload)
    );
  }

  if (context.event === contract.events.quantIndicatorsRefreshCardRequest) {
    return createAppResponse(
      contract.events.quantIndicatorsRefreshCardResponse,
      context.requestId,
      context.occurredAt,
      await refreshQuantIndicatorsForCard(context, context.payload)
    );
  }

  if (context.event === contract.events.quantIndicatorsLatestSnapshotsRequest) {
    return createAppResponse(
      contract.events.quantIndicatorsLatestSnapshotsResponse,
      context.requestId,
      context.occurredAt,
      await readLatestQuantIndicatorSnapshots(context, context.payload)
    );
  }

  if (context.event === contract.events.tossCredentialsReadStatusRequest) {
    return createAppResponse(
      contract.events.tossCredentialsReadStatusResponse,
      context.requestId,
      context.occurredAt,
      await context.tossCredentialRepository.readStatus()
    );
  }

  if (context.event === contract.events.tossCredentialsSaveRequest) {
    return createAppResponse(
      contract.events.tossCredentialsSaveResponse,
      context.requestId,
      context.occurredAt,
      await context.tossCredentialRepository.save(context.payload, context.occurredAt)
    );
  }

  if (context.event === contract.events.tossCredentialsDeleteRequest) {
    return createAppResponse(
      contract.events.tossCredentialsDeleteResponse,
      context.requestId,
      context.occurredAt,
      await context.tossCredentialRepository.delete()
    );
  }

  if (context.event === contract.events.tossConnectionTestRequest) {
    return createAppResponse(
      contract.events.tossConnectionTestResponse,
      context.requestId,
      context.occurredAt,
      await testTossConnection(context)
    );
  }

  return undefined;
}

async function testTossConnection(context) {
  const credentials = await context.tossCredentialRepository.readCredentials();

  if (typeof credentials.clientId !== "string" || typeof credentials.clientSecret !== "string") {
    throw createPlainError(
      "invalid_toss_credentials",
      "Toss credentials are not configured",
      true
    );
  }

  try {
    await context.tossOAuthClient.testConnection(credentials);
  } catch (error) {
    if (normalizeErrorCode(error) === "invalid_toss_credentials") {
      await context.tossCredentialRepository.markInvalid();
    }

    throw error;
  }

  return context.tossCredentialRepository.markValidated(context.occurredAt);
}

function createWatchCardResultOrError(result, responseEvent, requestId, occurredAt) {
  if (result === undefined) {
    return createAppError(
      requestId,
      occurredAt,
      "watch_card_not_found",
      "watch card was not found",
      true
    );
  }

  return createAppResponse(responseEvent, requestId, occurredAt, result);
}

function createAppResponse(event, requestId, occurredAt, payload) {
  return {
    event,
    requestId,
    occurredAt,
    payload
  };
}

function parseAppRequestData(data, occurredAt) {
  if (data === null || typeof data !== "object") {
    return {
      ok: false,
      error: createAppError(
        "unavailable",
        occurredAt,
        "invalid_request",
        "request requires requestId",
        true
      )
    };
  }

  if (typeof data.requestId !== "string" || data.requestId.trim() === "") {
    return {
      ok: false,
      error: createAppError(
        "unavailable",
        occurredAt,
        "invalid_request",
        "request requires requestId",
        true
      )
    };
  }

  return {
    ok: true,
    requestId: data.requestId,
    payload: data.payload || {}
  };
}

function normalizeErrorCode(error) {
  if (error && typeof error.code === "string" && contract.errorCodes.includes(error.code)) {
    return error.code;
  }

  return "invalid_request";
}

function createPlainError(code, message, recoverable) {
  const error = new Error(message);
  error.code = code;
  error.recoverable = recoverable;

  return error;
}

function createNativeMessage(method, accessToken, data) {
  return JSON.stringify({
    id: crypto.randomUUID(),
    method,
    accessToken,
    data
  });
}

function broadcastEnvelope(socket, auth, envelope) {
  socket.send(
    createNativeMessage("app.broadcast", auth.nlToken, {
      event: envelope.event,
      data: envelope
    })
  );
}

function startExtension() {
  const handleAppMessage = createAppMessageHandler();

  process.stdin.once("data", (chunk) => {
    const auth = JSON.parse(chunk.toString());
    const socket = new WebSocket(
      `ws://localhost:${auth.nlPort}?extensionId=${auth.nlExtensionId}&connectToken=${auth.nlConnectToken}`
    );

    socket.addEventListener("message", (event) => {
      void handleAppMessage(event.data, () => new Date().toISOString()).then((envelope) => {
        if (envelope !== undefined) {
          broadcastEnvelope(socket, auth, envelope);
        }
      });
    });

    socket.addEventListener("close", () => {
      process.exit(0);
    });
  });
}

if (require.main === module) {
  startExtension();
}

module.exports = {
  createAppMessageHandler,
  createDefaultRuntimeProfilePayload,
  handleRuntimeProfileMessage,
  parseRuntimeProfileRequest
};
