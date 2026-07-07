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
            indicators: {
              basicReturn: {
                status: "available",
                currentPrice: "194.9300",
                referencePrice: "190.0000",
                absoluteChange: "4.9300",
                simpleReturnPercent: 2.59,
                logReturnPercent: 2.56,
                currency: "USD",
                referenceLabel: "전일 종가",
                label: "전일 종가 대비 상승",
                severity: "positive",
                unavailableReason: null
              },
              vwap: {
                status: "available",
                value: "191.2400",
                distanceBps: 193,
                label: "VWAP 위 안착",
                severity: "positive",
                unavailableReason: null
              },
              cvd: {
                status: "estimated",
                value: "45",
                confidence: "estimated",
                label: "체결 압력 우위",
                severity: "positive",
                unavailableReason: null
              },
              spread: {
                status: "available",
                spreadBps: 19,
                label: "스프레드 정상",
                severity: "positive",
                unavailableReason: null
              },
              velocityAcceleration: {
                status: "available",
                latestLogReturnPercent: 0.84,
                priceAccelerationPercent: -0.01,
                volumeChangePercent: 0,
                estimatedCvdChange: "5",
                label: "상승 속도 둔화",
                severity: "warning",
                unavailableReason: null
              },
              distanceProfile: {
                status: "available",
                vwapDistanceBps: 193,
                movingAverageDistanceBps: 150,
                atrMultipleFromPreviousClose: 1.25,
                label: "상방 이격 주의",
                severity: "warning",
                unavailableReason: null
              },
              rsiMomentum: {
                status: "available",
                rsi: 64.2,
                momentumPercent: 1.48,
                label: "모멘텀 양호",
                severity: "positive",
                unavailableReason: null
              },
              atrStop: {
                status: "available",
                atr: "1.0000",
                stopDistancePercent: 0.97,
                label: "손절 폭 정상",
                severity: "positive",
                unavailableReason: null
              },
              supplyPressure: {
                status: "available",
                pocPrice: "192.0000",
                overheadRatio: 0.14,
                label: "매물대 부담 낮음",
                severity: "positive",
                unavailableReason: null
              },
              profitTakingPressure: {
                status: "available",
                profitLongRatio: 0.75,
                weightedProfitPressure: 0.02,
                vwapAtrExtension: 1,
                sellFlowPressure: 0,
                askBookPressure: 0,
                volumeExpansion: 0.67,
                score: 42,
                label: "차익실현 압박 경계",
                severity: "warning",
                unavailableReason: null
              },
              riskReward: {
                status: "available",
                ratio: 2,
                label: "손익비 1.5x 이상",
                severity: "positive",
                unavailableReason: null
              },
              marketSentimentScore: {
                status: "available",
                score: 78,
                label: "정량 심리 우호",
                severity: "positive",
                unavailableReason: null
              },
              intradayTradeScore: {
                status: "available",
                conditionStrengthPercent: 94.27,
                label: "조건 충족 강함",
                severity: "positive",
                unavailableReason: null
              }
            },
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
            ],
            explanationTraces: [
              {
                key: "basicReturn",
                title: "기본 수익률",
                source: "현재가와 전일 종가",
                originalFormula: ["단순 수익률 = 현재가 / 기준가 - 1"],
                substitutedFormula: ["단순 수익률 = 194.93 / 190.00 - 1"],
                result: ["단순 수익률 = +2.59%"],
                inputs: [{ label: "현재가", value: "$194.93" }],
                meaning: "가격이 기준 시점보다 얼마나 움직였는지 보는 가장 기본 지표입니다.",
                usage: "손절, 익절, 포지션 크기 판단의 출발점으로 사용합니다.",
                judgment: "현재가는 전일 종가보다 위에 있습니다.",
                caution: "단순 수익률은 여러 구간을 그냥 더하면 누적 수익률과 달라집니다.",
                limitation: null
              },
              {
                key: "cvd",
                title: "CVD 추정",
                source: "최근 체결 내역",
                originalFormula: ["tick-rule CVD = Σ(가격 상승 체결량 - 가격 하락 체결량)"],
                substitutedFormula: ["tick-rule CVD = +20 - 5 + 30"],
                result: ["CVD 추정값 = 45"],
                inputs: [{ label: "체결 방향", value: "tick-rule 추정" }],
                meaning: "최근 체결이 어느 방향으로 기울었는지 참고합니다.",
                usage: "VWAP 재돌파나 이탈 판단에서 체결 압력 회복 여부를 함께 봅니다.",
                judgment: "체결 압력 우위",
                caution: "정확한 매수·매도 주체가 아니라 방향 참고용입니다.",
                limitation: "Toss 체결 데이터에 aggressor side가 없어 tick-rule로 추정합니다."
              },
              {
                key: "intradayTradeScore",
                title: "종합 데이트레이딩 점수",
                source: "정량 심리 점수",
                originalFormula: ["조건 충족 강도 = sigmoid((정량 심리 점수 - 50) / 10) × 100"],
                substitutedFormula: ["조건 충족 강도 = sigmoid((78.00 - 50) / 10) × 100"],
                result: ["조건 충족 강도 = 94.27%"],
                inputs: [{ label: "정량 심리 점수", value: "78.00" }],
                meaning: "여러 정량 조건이 동시에 얼마나 충족됐는지 압축해 보여줍니다.",
                usage: "체크리스트 전체 분위기를 빠르게 비교할 때 사용합니다.",
                judgment: "조건 충족 강함",
                caution: "확률처럼 보이지만 매수 성공률 예측값이 아니라 조건 강도입니다.",
                limitation: null
              },
              {
                key: "profitTakingPressure",
                title: "차익실현 압박 추정",
                source: "당일 1분봉 거래량 분포, VWAP, ATR, 체결 방향 추정, 호가 잔량",
                originalFormula: [
                  "차익실현 압박 점수 = 100 × 가중합(수익권 물량, VWAP/ATR 이격, 매도 체결 압력, 매도호가 압력, 거래량 확장)"
                ],
                substitutedFormula: [
                  "점수 = 100 × (0.30×0.75 + 0.25×1.00 + 0.20×0.00 + 0.15×0.00 + 0.10×0.67)"
                ],
                result: ["차익실현 압박 점수 = 42점"],
                inputs: [{ label: "수익권 물량 비율", value: "0.75" }],
                meaning: "현재가보다 낮은 가격대에 쌓인 당일 거래량과 실제 매도 압력을 함께 보는 내부 추정 지표입니다.",
                usage: "단기 참여자 다수가 수익권이고 매도 압력이 붙는지 확인합니다.",
                judgment: "차익실현 압박 경계",
                caution: "표준 공식명이 아니며 매수·매도 추천으로 해석하지 않습니다.",
                limitation: "표준 공식명이 아니라 앱 내부 추정 지표이며 실제 보유자 원가나 매도 의도를 알 수 없습니다."
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
    expect(JSON.stringify(response)).toContain("profitTakingPressure");
    expect(JSON.stringify(response)).toContain("conditionStrengthPercent");
    expect(JSON.stringify(response)).not.toContain("conditionProbabilityPercent");
    expect(JSON.stringify(response)).not.toContain("access_token");
    expect(JSON.stringify(response)).not.toContain("clientSecret");
    expect(JSON.stringify(response)).not.toContain("Bearer ");
  });
});
