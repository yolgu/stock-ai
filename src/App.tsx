import { useMemo, type ReactElement } from "react";

import {
  createMarketDataClientFromNeutralinoApi,
  createMarketStateClientFromNeutralinoApi,
  createQuantIndicatorClientFromNeutralinoApi,
  createRuntimeProfileClientFromWindow,
  createStockReferenceClientFromNeutralinoApi,
  createTossSettingsClientFromNeutralinoApi,
  createWatchlistClientFromNeutralinoApi
} from "./infrastructure/neutralino/createRuntimeProfileClientFromWindow";
import type { MarketDataClient } from "./infrastructure/neutralino/NeutralinoMarketDataClient";
import type { MarketStateClient } from "./infrastructure/neutralino/NeutralinoMarketStateClient";
import type { QuantIndicatorClient } from "./infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { RuntimeProfileClient } from "./infrastructure/neutralino/NeutralinoRuntimeProfileClient";
import type { StockReferenceClient } from "./infrastructure/neutralino/NeutralinoStockReferenceClient";
import type { TossSettingsClient } from "./infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "./infrastructure/neutralino/NeutralinoWatchlistClient";
import { AppShell } from "./presentation/AppShell";
import { StartupStateView } from "./presentation/StartupStateView";
import { useRuntimeProfile } from "./presentation/useRuntimeProfile";

export interface AppProps {
  runtimeProfileClient?: RuntimeProfileClient;
  watchlistClient?: WatchlistClient;
  stockReferenceClient?: StockReferenceClient;
  marketDataClient?: MarketDataClient;
  marketStateClient?: MarketStateClient;
  quantIndicatorClient?: QuantIndicatorClient;
  tossSettingsClient?: TossSettingsClient;
}

export function App({
  runtimeProfileClient,
  watchlistClient,
  stockReferenceClient,
  marketDataClient,
  marketStateClient,
  quantIndicatorClient,
  tossSettingsClient
}: AppProps): ReactElement {
  const client = useMemo(
    () => runtimeProfileClient ?? createRuntimeProfileClientFromWindow(),
    [runtimeProfileClient]
  );
  const neutralinoWindowApi =
    typeof window !== "undefined"
      ? (window as typeof window & {
          Neutralino?: Parameters<typeof createWatchlistClientFromNeutralinoApi>[0];
        }).Neutralino
      : undefined;
  const activeWatchlistClient = useMemo(
    () => watchlistClient ?? createWatchlistClientFromNeutralinoApi(neutralinoWindowApi),
    [neutralinoWindowApi, watchlistClient]
  );
  const activeTossSettingsClient = useMemo(
    () => tossSettingsClient ?? createTossSettingsClientFromNeutralinoApi(neutralinoWindowApi),
    [neutralinoWindowApi, tossSettingsClient]
  );
  const activeStockReferenceClient = useMemo(
    () => stockReferenceClient ?? createStockReferenceClientFromNeutralinoApi(neutralinoWindowApi),
    [neutralinoWindowApi, stockReferenceClient]
  );
  const activeMarketDataClient = useMemo(
    () => marketDataClient ?? createMarketDataClientFromNeutralinoApi(neutralinoWindowApi),
    [marketDataClient, neutralinoWindowApi]
  );
  const activeQuantIndicatorClient = useMemo(
    () =>
      quantIndicatorClient ?? createQuantIndicatorClientFromNeutralinoApi(neutralinoWindowApi),
    [neutralinoWindowApi, quantIndicatorClient]
  );
  const activeMarketStateClient = useMemo(
    () =>
      marketStateClient ??
      createMarketStateClientFromNeutralinoApi(neutralinoWindowApi),
    [marketStateClient, neutralinoWindowApi]
  );
  const runtimeProfileState = useRuntimeProfile(client);

  if (runtimeProfileState.status === "ready") {
    return (
      <AppShell
        runtimeProfile={runtimeProfileState.runtimeProfile}
        watchlistClient={activeWatchlistClient}
        stockReferenceClient={activeStockReferenceClient}
        marketDataClient={activeMarketDataClient}
        marketStateClient={activeMarketStateClient}
        quantIndicatorClient={activeQuantIndicatorClient}
        tossSettingsClient={activeTossSettingsClient}
      />
    );
  }

  return (
    <main className="app-background">
      <StartupStateView
        state={runtimeProfileState}
        onRetry={() => globalThis.location.reload()}
      />
    </main>
  );
}
