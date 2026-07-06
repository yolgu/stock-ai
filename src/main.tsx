import { events, extensions, init } from "@neutralinojs/lib";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import {
  createMarketDataClientFromNeutralinoApi,
  createQuantIndicatorClientFromNeutralinoApi,
  createRuntimeProfileClientFromNeutralinoApi,
  createStockReferenceClientFromNeutralinoApi,
  createTossSettingsClientFromNeutralinoApi,
  createWatchlistClientFromNeutralinoApi
} from "./infrastructure/neutralino/createRuntimeProfileClientFromWindow";
import "./styles.css";

try {
  init();
} catch {
  // Renderer-only Vite runs do not have Neutralino globals.
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App
      runtimeProfileClient={createRuntimeProfileClientFromNeutralinoApi({
        extensions,
        events
      })}
      watchlistClient={createWatchlistClientFromNeutralinoApi({
        extensions,
        events
      })}
      stockReferenceClient={createStockReferenceClientFromNeutralinoApi({
        extensions,
        events
      })}
      marketDataClient={createMarketDataClientFromNeutralinoApi({
        extensions,
        events
      })}
      quantIndicatorClient={createQuantIndicatorClientFromNeutralinoApi({
        extensions,
        events
      })}
      tossSettingsClient={createTossSettingsClientFromNeutralinoApi({
        extensions,
        events
      })}
    />
  </StrictMode>
);
