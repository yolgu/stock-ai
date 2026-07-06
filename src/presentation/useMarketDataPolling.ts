import { useCallback, useEffect, useState } from "react";

import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type {
  MarketDataSnapshotPayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";

const MARKET_DATA_RETRY_DELAY_MS = 15_000;

export interface UseMarketDataPollingInput {
  activeCards: WatchStockCardDto[];
  credentials: TossCredentialStatusPayload;
}

export interface UseMarketDataPollingResult {
  status: "idle" | "loading" | "ready" | "error";
  snapshotsByCardId: Record<string, MarketDataSnapshotPayload>;
  message: string | null;
  refreshNow(): Promise<void>;
}

export function useMarketDataPolling(
  marketDataClient: MarketDataClient,
  input: UseMarketDataPollingInput
): UseMarketDataPollingResult {
  const [state, setState] = useState<Omit<UseMarketDataPollingResult, "refreshNow">>({
    status: "idle",
    snapshotsByCardId: {},
    message: null
  });
  const cardIdsKey = input.activeCards.map((card) => card.id).join("|");
  const canPoll =
    input.credentials.configured &&
    input.credentials.connectionStatus !== "invalid" &&
    input.activeCards.length > 0;

  const refreshNow = useCallback(async (): Promise<void> => {
    if (!canPoll) {
      setState((current) => ({ ...current, status: "idle" }));
      return;
    }

    try {
      setState((current) => ({ ...current, status: "loading", message: null }));
      const result = await marketDataClient.refreshWatchlist({
        visibleCardIds: input.activeCards.map((card) => card.id)
      });
      setState({
        status: "ready",
        snapshotsByCardId: indexSnapshotsByCardId(result.snapshots),
        message: null
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        status: "error",
        message: error instanceof Error ? error.message : "시장 데이터 수집에 실패했습니다."
      }));
    }
  }, [canPoll, cardIdsKey, input.activeCards, marketDataClient]);

  useEffect(() => {
    if (!canPoll) {
      setState((current) => ({ ...current, status: "idle" }));
      return;
    }

    let isCancelled = false;
    let timeoutId: number | undefined;

    const refreshAndSchedule = async (): Promise<void> => {
      try {
        setState((current) => ({ ...current, status: "loading", message: null }));
        const result = await marketDataClient.refreshWatchlist({
          visibleCardIds: input.activeCards.map((card) => card.id)
        });

        if (isCancelled) {
          return;
        }

        setState({
          status: "ready",
          snapshotsByCardId: indexSnapshotsByCardId(result.snapshots),
          message: null
        });
        timeoutId = window.setTimeout(refreshAndSchedule, result.nextPollDelayMs);
      } catch (error) {
        if (isCancelled) {
          return;
        }

        setState((current) => ({
          ...current,
          status: "error",
          message: error instanceof Error ? error.message : "시장 데이터 수집에 실패했습니다."
        }));
        timeoutId = window.setTimeout(refreshAndSchedule, MARKET_DATA_RETRY_DELAY_MS);
      }
    };

    void refreshAndSchedule();

    return () => {
      isCancelled = true;

      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [canPoll, cardIdsKey, input.activeCards, marketDataClient]);

  return {
    ...state,
    refreshNow
  };
}

function indexSnapshotsByCardId(
  snapshots: MarketDataSnapshotPayload[]
): Record<string, MarketDataSnapshotPayload> {
  return snapshots.reduce<Record<string, MarketDataSnapshotPayload>>((indexed, snapshot) => {
    indexed[snapshot.cardId] = snapshot;

    return indexed;
  }, {});
}
