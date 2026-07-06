import contractSpec from "../../../contracts/app-runtime-contract.json";

export type FeatureCapabilityName =
  | "watchlist"
  | "quantIndicators"
  | "llmInsights"
  | "orders";

export type RuntimeMode = "desktop";

export type MarketDataMode = "notConfigured";

export interface FeatureCapabilityDto {
  name: FeatureCapabilityName;
  enabled: boolean;
  reason: string;
}

export interface RuntimeProfileDto {
  runtimeMode: RuntimeMode;
  marketDataMode: MarketDataMode;
  capabilities: FeatureCapabilityDto[];
}

const defaultCapabilityReasons: Record<FeatureCapabilityName, string> = {
  watchlist: "관심종목 목록 기능 준비됨",
  quantIndicators: "정량 지표 계산 준비됨",
  llmInsights: "수동 AI 분석 단계 이후 활성화",
  orders: "주문 연동 단계 이후 활성화"
};

export class FeatureCapability {
  private constructor(
    private readonly capabilityName: FeatureCapabilityName,
    private readonly enabledState: boolean,
    private readonly reasonText: string
  ) {}

  public static enabled(
    capabilityName: FeatureCapabilityName,
    reasonText = defaultCapabilityReasons[capabilityName]
  ): FeatureCapability {
    FeatureCapability.assertKnownCapability(capabilityName);

    return new FeatureCapability(capabilityName, true, reasonText);
  }

  public static disabled(
    capabilityName: FeatureCapabilityName,
    reasonText = defaultCapabilityReasons[capabilityName]
  ): FeatureCapability {
    FeatureCapability.assertKnownCapability(capabilityName);

    return new FeatureCapability(capabilityName, false, reasonText);
  }

  public name(): FeatureCapabilityName {
    return this.capabilityName;
  }

  public isEnabled(): boolean {
    return this.enabledState;
  }

  public toDto(): FeatureCapabilityDto {
    return {
      name: this.capabilityName,
      enabled: this.enabledState,
      reason: this.reasonText
    };
  }

  private static assertKnownCapability(capabilityName: FeatureCapabilityName): void {
    if (!contractSpec.capabilities.includes(capabilityName)) {
      throw new Error(`Unknown feature capability: ${capabilityName}`);
    }
  }
}

export class AppRuntimeProfile {
  private constructor(
    private readonly runtimeMode: RuntimeMode,
    private readonly marketDataMode: MarketDataMode,
    private readonly capabilities: FeatureCapability[]
  ) {}

  public static createDefault(): AppRuntimeProfile {
    return new AppRuntimeProfile("desktop", "notConfigured", [
      FeatureCapability.enabled("watchlist"),
      FeatureCapability.enabled("quantIndicators"),
      FeatureCapability.disabled("llmInsights"),
      FeatureCapability.disabled("orders")
    ]);
  }

  public isCapabilityEnabled(capabilityName: FeatureCapabilityName): boolean {
    return this.capabilities.some(
      (capability) => capability.name() === capabilityName && capability.isEnabled()
    );
  }

  public toDto(): RuntimeProfileDto {
    return {
      runtimeMode: this.runtimeMode,
      marketDataMode: this.marketDataMode,
      capabilities: this.capabilities.map((capability) => capability.toDto())
    };
  }
}
