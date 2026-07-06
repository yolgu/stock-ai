import { useMemo, type ReactElement } from "react";

import {
  createRuntimeProfileClientFromWindow,
  createTossSettingsClientFromNeutralinoApi,
  createWatchlistClientFromNeutralinoApi
} from "./infrastructure/neutralino/createRuntimeProfileClientFromWindow";
import type { RuntimeProfileClient } from "./infrastructure/neutralino/NeutralinoRuntimeProfileClient";
import type { TossSettingsClient } from "./infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "./infrastructure/neutralino/NeutralinoWatchlistClient";
import { AppShell } from "./presentation/AppShell";
import { StartupStateView } from "./presentation/StartupStateView";
import { useRuntimeProfile } from "./presentation/useRuntimeProfile";

export interface AppProps {
  runtimeProfileClient?: RuntimeProfileClient;
  watchlistClient?: WatchlistClient;
  tossSettingsClient?: TossSettingsClient;
}

export function App({
  runtimeProfileClient,
  watchlistClient,
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
  const runtimeProfileState = useRuntimeProfile(client);

  if (runtimeProfileState.status === "ready") {
    return (
      <AppShell
        runtimeProfile={runtimeProfileState.runtimeProfile}
        watchlistClient={activeWatchlistClient}
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
