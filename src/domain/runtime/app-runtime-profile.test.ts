import { describe, expect, it } from "vitest";

import {
  AppRuntimeProfile,
  FeatureCapability,
  type FeatureCapabilityName
} from "./AppRuntimeProfile";

describe("FeatureCapability", () => {
  it("allows known capability names and exposes enabled state", () => {
    const capability = FeatureCapability.enabled("watchlist");

    expect(capability.name()).toBe("watchlist");
    expect(capability.isEnabled()).toBe(true);
    expect(capability.toDto()).toEqual({
      name: "watchlist",
      enabled: true,
      reason: "관심종목 목록 기능 준비됨"
    });
  });

  it("rejects unknown capability names", () => {
    expect(() =>
      FeatureCapability.enabled("marketData" as FeatureCapabilityName)
    ).toThrow("Unknown feature capability: marketData");
  });
});

describe("AppRuntimeProfile", () => {
  it("creates a default desktop profile with watchlist and quant indicators available", () => {
    const profile = AppRuntimeProfile.createDefault();

    expect(profile.isCapabilityEnabled("watchlist")).toBe(true);
    expect(profile.isCapabilityEnabled("quantIndicators")).toBe(true);
    expect(profile.isCapabilityEnabled("llmInsights")).toBe(false);
    expect(profile.isCapabilityEnabled("orders")).toBe(false);
    expect(profile.toDto()).toEqual({
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
    });
  });
});
