import { describe, expect, it } from "vitest";

import {
  APP_RUNTIME_CONTRACT,
  createAppRequest,
  createAppResponse,
  createTossCredentialStatusPayload,
  isAppResponseEnvelope,
  parseAppRequest
} from "./app-runtime-contract";

describe("watchlist and settings IPC contract", () => {
  it("centralizes watchlist and Toss settings event names", () => {
    expect(APP_RUNTIME_CONTRACT.events.watchlistCreateRequest).toBe(
      "watchlist:create:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.stockReferenceVerifyRequest).toBe(
      "stock-reference:verify:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.watchlistCreateVerifiedRequest).toBe(
      "watchlist:create-verified:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.tossCredentialsSaveRequest).toBe(
      "settings:toss-credentials:save"
    );
    expect(APP_RUNTIME_CONTRACT.events.tossConnectionTestRequest).toBe(
      "settings:toss-connection:test"
    );
  });

  it("creates generic request and response envelopes with requestId", () => {
    const request = createAppRequest({
      event: "watchlist:list:request",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z",
      payload: {}
    });
    const response = createAppResponse({
      event: "watchlist:list:response",
      requestId: request.requestId,
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        activeCards: [],
        hiddenCards: [],
        archivedCards: []
      }
    });

    expect(response).toEqual({
      event: "watchlist:list:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        activeCards: [],
        hiddenCards: [],
        archivedCards: []
      }
    });
    expect(isAppResponseEnvelope(response)).toBe(true);
  });

  it("converts a request without requestId into a structured error", () => {
    const parsed = parseAppRequest(
      {
        event: "watchlist:create:request",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: {}
      },
      "2026-07-06T09:00:01.000Z"
    );

    expect(parsed).toEqual({
      ok: false,
      error: {
        event: "app:error",
        requestId: "unavailable",
        occurredAt: "2026-07-06T09:00:01.000Z",
        error: {
          code: "invalid_request",
          message: "request requires requestId",
          recoverable: true
        }
      }
    });
  });

  it("never exposes Toss client secret in credential status payloads", () => {
    const payload = createTossCredentialStatusPayload({
      clientId: "client_fixture_1234567890",
      configured: true,
      lastValidatedAt: "2026-07-06T09:00:00.000Z",
      connectionStatus: "valid"
    });

    expect(payload).toEqual({
      configured: true,
      maskedClientId: "clie…7890",
      lastValidatedAt: "2026-07-06T09:00:00.000Z",
      connectionStatus: "valid"
    });
    expect(JSON.stringify(payload)).not.toContain("secret");
  });

  it("defines stock reference verification envelopes without leaking tokens", () => {
    const response = createAppResponse({
      event: "stock-reference:verify:response",
      requestId: "request-stock-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        verified: [
          {
            symbol: "MU",
            market: "NASDAQ",
            displayName: "MU 마이크론",
            currency: "USD",
            status: "ACTIVE",
            securityType: "STOCK",
            requiresConfirmation: false,
            confirmationReasons: [],
            verifiedAt: "2026-07-06T09:00:01.000Z"
          }
        ],
        rejected: [
          {
            symbol: "ZZZZZZZZZZZZ",
            reason: "stock_not_found",
            message: "종목을 찾을 수 없습니다."
          }
        ]
      }
    });

    expect(isAppResponseEnvelope(response)).toBe(true);
    expect(APP_RUNTIME_CONTRACT.errorCodes).toContain("stock_not_found");
    expect(APP_RUNTIME_CONTRACT.errorCodes).toContain("stock_confirmation_required");
    expect(JSON.stringify(response)).not.toContain("access-token");
    expect(JSON.stringify(response)).not.toContain("clientSecret");
  });

  it("defines market data snapshot envelopes without leaking secrets or tokens", () => {
    const response = createAppResponse({
      event: "market-data:latest-snapshots:response",
      requestId: "request-market-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        snapshots: [
          {
            snapshotId: "snapshot-1",
            cardId: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            capturedAt: "2026-07-06T09:00:01.000Z",
            freshness: "fresh",
            quality: "complete",
            observations: {
              price: {
                symbol: "MU",
                timestamp: "2026-07-06T09:00:00.000Z",
                lastPrice: "194.93",
                currency: "USD"
              },
              trades: [],
              orderbook: null,
              intradayCandles: null,
              dailyCandles: null,
              exchangeRate: null,
              marketSession: {
                country: "US",
                state: "regular",
                source: "calendar"
              }
            },
            adapterErrors: []
          }
        ]
      }
    });

    expect(isAppResponseEnvelope(response)).toBe(true);
    expect(APP_RUNTIME_CONTRACT.events.marketDataRefreshWatchlistRequest).toBe(
      "market-data:refresh-watchlist:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.marketDataLatestSnapshotsResponse).toBe(
      "market-data:latest-snapshots:response"
    );
    expect(APP_RUNTIME_CONTRACT.errorCodes).toContain("market_data_rate_limited");
    expect(JSON.stringify(response)).not.toContain("access_token");
    expect(JSON.stringify(response)).not.toContain("clientSecret");
    expect(JSON.stringify(response)).not.toContain("Bearer ");
  });

  it("defines quant indicator envelopes without leaking raw credentials or access tokens", () => {
    const response = createAppResponse({
      event: "quant-indicators:latest-snapshots:response",
      requestId: "request-quant-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        snapshots: [
          {
            snapshotId: "quant-1",
            sourceMarketDataSnapshotId: "market-1",
            cardId: "card-1",
            market: "NASDAQ",
            symbol: "MU",
            calculatedAt: "2026-07-06T09:00:01.000Z",
            quality: "complete",
            decisionStatus: "watch",
            decisionLabel: "관망",
            nextCheckLabel: "VWAP 위 안착 유지 확인",
            signals: [
              {
                key: "vwap",
                label: "VWAP 위 안착",
                severity: "positive",
                status: "available",
                reason: null
              },
              {
                key: "cvd",
                label: "체결 압력 우위",
                severity: "positive",
                status: "estimated",
                reason: "Toss 체결 데이터에 aggressor side가 없어 tick-rule로 추정합니다."
              }
            ]
          }
        ]
      }
    });

    expect(isAppResponseEnvelope(response)).toBe(true);
    expect(APP_RUNTIME_CONTRACT.events.quantIndicatorsRefreshWatchlistRequest).toBe(
      "quant-indicators:refresh-watchlist:request"
    );
    expect(APP_RUNTIME_CONTRACT.events.quantIndicatorsLatestSnapshotsResponse).toBe(
      "quant-indicators:latest-snapshots:response"
    );
    expect(APP_RUNTIME_CONTRACT.errorCodes).toContain("quant_indicator_unavailable");
    expect(APP_RUNTIME_CONTRACT.errorCodes).toContain("quant_indicator_snapshot_not_found");
    expect(JSON.stringify(response)).not.toContain("access_token");
    expect(JSON.stringify(response)).not.toContain("clientSecret");
    expect(JSON.stringify(response)).not.toContain("Bearer ");
  });
});
