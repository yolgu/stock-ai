import { describe, expect, it } from "vitest";

import { AppRuntimeProfile } from "../../domain/runtime/AppRuntimeProfile";
import {
  LoadAppRuntimeProfile,
  type RuntimeProfileRepository
} from "./LoadAppRuntimeProfile";

describe("LoadAppRuntimeProfile", () => {
  it("returns renderer-safe startup capabilities", async () => {
    const repository: RuntimeProfileRepository = {
      load: async (): Promise<AppRuntimeProfile> => AppRuntimeProfile.createDefault()
    };
    const useCase = new LoadAppRuntimeProfile(repository);

    const profile = await useCase.load();

    expect(profile.runtimeMode).toBe("desktop");
    expect(profile.marketDataMode).toBe("notConfigured");
    expect(profile.capabilities.map((capability) => capability.name)).toEqual([
      "watchlist",
      "quantIndicators",
      "llmInsights",
      "orders"
    ]);
    expect(JSON.stringify(profile).toLowerCase()).not.toMatch(
      /secret|token|credential|auth|env|path/
    );
  });
});
