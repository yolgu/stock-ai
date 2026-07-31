import { describe, expect, it } from "vitest";

import {
  APP_RUNTIME_CONTRACT,
  createAppError,
  createRuntimeProfileRequest,
  createRuntimeProfileResponse,
  isMarketStateHistoryPayload,
  isMarketStateRefreshPayload,
  isMarketStateTraceResponsePayload,
  parseRuntimeProfileRequest
} from "./app-runtime-contract";

describe("app runtime IPC contract", () => {
  it("creates a runtime profile request envelope", () => {
    const request = createRuntimeProfileRequest({
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z"
    });

    expect(request).toEqual({
      event: "app:runtime-profile:request",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:00.000Z",
      payload: {}
    });
    expect(APP_RUNTIME_CONTRACT.extensionId).toBe("app.stockSub.runtime");
  });

  it("creates a runtime profile response envelope", () => {
    const response = createRuntimeProfileResponse({
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        runtimeMode: "desktop",
        marketDataMode: "notConfigured",
        capabilities: []
      }
    });

    expect(response).toEqual({
      event: "app:runtime-profile:response",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:01.000Z",
      payload: {
        runtimeMode: "desktop",
        marketDataMode: "notConfigured",
        capabilities: []
      }
    });
  });

  it("converts a request without requestId into a structured error", () => {
    const parsed = parseRuntimeProfileRequest(
      {
        event: "app:runtime-profile:request",
        occurredAt: "2026-07-06T09:00:00.000Z",
        payload: {}
      },
      "2026-07-06T09:00:02.000Z"
    );

    expect(parsed).toEqual({
      ok: false,
      error: {
        event: "app:error",
        requestId: "unavailable",
        occurredAt: "2026-07-06T09:00:02.000Z",
        error: {
          code: "invalid_request",
          message: "runtime profile request requires requestId",
          recoverable: true
        }
      }
    });
  });

  it("creates a typed app error envelope", () => {
    expect(
      createAppError({
        requestId: "request-1",
        occurredAt: "2026-07-06T09:00:03.000Z",
        code: "extension_unavailable",
        message: "runtime extension is unavailable",
        recoverable: true
      })
    ).toEqual({
      event: "app:error",
      requestId: "request-1",
      occurredAt: "2026-07-06T09:00:03.000Z",
      error: {
        code: "extension_unavailable",
        message: "runtime extension is unavailable",
        recoverable: true
      }
    });
  });

  it("rejects market-state payloads with the wrong signal set, hash, or status", () => {
    const validPayload: Record<string, unknown> = {
      refreshedAt: "2026-07-31T14:05:01.000Z",
      snapshots: [
        {
          snapshotId: "snapshot-1",
          cardId: "card-1",
          symbol: "AAPL",
          sessionDate: "2026-07-31",
          asOf: "2026-07-31T14:05:00.000Z",
          bucketIndex: 6,
          sourceGenerationId: "generation-1",
          formulaVersion: "a".repeat(64),
          formulaContentSha256: "b".repeat(64),
          observedState: "BASELINE",
          observedStateLabel: "방향성 확인 전",
          notifiedSignalIds: [],
          signals: [
            "FOMO_LIKE",
            "PANIC_LIKE",
            "PROFIT_TAKING_PROXY",
            "PERSISTENT_RECOVERY",
            "EFFICIENT_UPTREND"
          ].map((signalId: string) => ({
            signalId,
            displayName: signalId,
            formationLabel: signalId,
            horizonMinutes: 30,
            status: "notDetected",
            percentile: 50,
            percentileNumerator: 1,
            percentileDenominator: 2,
            rawScore: 0,
            dynamicThreshold: 1,
            thresholdDistance: -1,
            gate: null,
            requiredRiskState: "BASELINE",
            currentRiskState: "BASELINE",
            currentDetectionStartedAt: null,
            lastDetectedAt: null,
            trace: null
          }))
        }
      ],
      backfillProgress: {
        jobId: "job-1",
        status: "running",
        requiredSessions: 60,
        completedSessions: 20,
        currentInstrumentId: "AAPL",
        totalInstrumentCount: 34,
        completedInstrumentCount: 1,
        error: null
      }
    };

    expect(isMarketStateRefreshPayload(validPayload)).toBe(true);
    expect(isMarketStateRefreshPayload({
      ...validPayload,
      snapshots: [{
        ...(validPayload.snapshots as Array<Record<string, unknown>>)[0],
        signals: (
          (validPayload.snapshots as Array<Record<string, unknown>>)[0]
            ?.signals as unknown[]
        ).slice(0, 4)
      }]
    })).toBe(false);
    expect(isMarketStateRefreshPayload({
      ...validPayload,
      snapshots: [{
        ...(validPayload.snapshots as Array<Record<string, unknown>>)[0],
        formulaContentSha256: "invalid"
      }]
    })).toBe(false);
    expect(isMarketStateRefreshPayload({
      ...validPayload,
      snapshots: [{
        ...(validPayload.snapshots as Array<Record<string, unknown>>)[0],
        signals: (
          (validPayload.snapshots as Array<Record<string, unknown>>)[0]
            ?.signals as Array<Record<string, unknown>>
        ).map((signal: Record<string, unknown>, index: number) => ({
          ...signal,
          status: index === 0 ? "resolved" : signal.status
        }))
      }]
    })).toBe(false);
    expect(isMarketStateRefreshPayload({
      ...validPayload,
      snapshots: [{
        ...(validPayload.snapshots as Array<Record<string, unknown>>)[0],
        signals: (
          (validPayload.snapshots as Array<Record<string, unknown>>)[0]
            ?.signals as Array<Record<string, unknown>>
        ).map((signal: Record<string, unknown>, index: number) => ({
          ...signal,
          trace: index === 0 ? {} : signal.trace
        }))
      }]
    })).toBe(false);
  });

  it("validates formula trace and history payloads before renderer use", () => {
    const formulaTrace: Record<string, unknown> = {
      intercept: -0.5,
      contributions: [
        {
          featureName: "ret_6",
          rawValue: 0.02,
          mean: 0,
          scale: 0.01,
          standardizedValue: 2,
          coefficient: 0.4,
          contribution: 0.8
        }
      ],
      effectiveTailShare: 0.01,
      calibrationTailShare: 0.0125,
      transportTailSafetyFactor: 0.8,
      candidateId: "VOLUME_AUGMENTED",
      cause: "UP_PRICE_PASSAGE",
      phenotypeTag: "up_chase_phenotype"
    };
    const trace: Record<string, unknown> = {
      signalId: "FOMO_LIKE",
      displayName: "FOMO",
      formationLabel: "추격 매수형 가격 움직임 형성 감지",
      horizonMinutes: 30,
      status: "detected",
      percentile: 99.5,
      percentileNumerator: 995,
      percentileDenominator: 1_000,
      rawScore: 1.4,
      dynamicThreshold: 1.2,
      thresholdDistance: 0.2,
      gate: {
        gateId: "POSITIVE_PRESSURE_MEAN_3",
        label: "최근 3개 봉의 거래량 압력",
        value: 0.3,
        operator: ">",
        threshold: 0,
        passed: true
      },
      requiredRiskState: "BASELINE",
      currentRiskState: "BASELINE",
      currentDetectionStartedAt: "2026-07-31T14:00:00.000Z",
      lastDetectedAt: "2026-07-31T14:05:00.000Z",
      trace: formulaTrace,
      cardId: "card-1",
      symbol: "MU",
      sessionDate: "2026-07-31",
      asOf: "2026-07-31T14:05:00.000Z",
      sourceGenerationId: "generation-1",
      formulaVersion: "a".repeat(64),
      formulaContentSha256: "b".repeat(64),
      observedState: "BASELINE",
      observedStateLabel: "방향성 확인 전"
    };
    const history: Record<string, unknown> = {
      cardId: "card-1",
      signalId: "FOMO_LIKE",
      sessionDate: "2026-07-31",
      points: [
        {
          asOf: "2026-07-31T14:05:00.000Z",
          bucketIndex: 6,
          status: "detected",
          percentile: 99.5,
          rawScore: 1.4,
          dynamicThreshold: 1.2,
          detected: true
        }
      ]
    };

    expect(isMarketStateTraceResponsePayload({ trace })).toBe(true);
    expect(isMarketStateTraceResponsePayload({
      trace: {
        ...trace,
        trace: {
          ...formulaTrace,
          contributions: [{ featureName: "ret_6" }]
        }
      }
    })).toBe(false);
    expect(isMarketStateHistoryPayload(history)).toBe(true);
    expect(isMarketStateHistoryPayload({
      ...history,
      points: [
        {
          ...(history.points as Array<Record<string, unknown>>)[0],
          percentile: 101
        }
      ]
    })).toBe(false);
  });
});
