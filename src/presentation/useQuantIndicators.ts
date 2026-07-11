import { useCallback, useEffect, useState } from "react";

import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type {
  QuantIndicatorSnapshotPayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";

export interface UseQuantIndicatorsInput {
  activeCards: WatchStockCardDto[];
  credentials: TossCredentialStatusPayload;
  marketDataStatus: "idle" | "loading" | "ready" | "error";
}

export type QuantIndicatorLoadStatus =
  | "idle"
  | "emptyLoading"
  | "refreshing"
  | "ready"
  | "error"
  | "failedRefresh";

export interface UseQuantIndicatorsResult {
  status: QuantIndicatorLoadStatus;
  snapshotsByCardId: Record<string, QuantIndicatorSnapshotPayload>;
  message: string | null;
  refreshNow(): Promise<void>;
}

export function useQuantIndicators(
  quantIndicatorClient: QuantIndicatorClient,
  input: UseQuantIndicatorsInput
): UseQuantIndicatorsResult {
  const [state, setState] = useState<Omit<UseQuantIndicatorsResult, "refreshNow">>({
    status: "idle",
    snapshotsByCardId: {},
    message: null
  });
  const cardIdsKey = input.activeCards.map((card) => card.id).join("|");
  const canCalculate =
    input.credentials.configured &&
    input.credentials.connectionStatus !== "invalid" &&
    input.marketDataStatus === "ready" &&
    input.activeCards.length > 0;

  const refreshNow = useCallback(async (): Promise<void> => {
    if (!canCalculate) {
      setState((current) => ({ ...current, status: "idle" }));
      return;
    }

    try {
      setState((current) => ({
        ...current,
        status: hasSnapshots(current.snapshotsByCardId) ? "refreshing" : "emptyLoading",
        message: null
      }));
      const result = await quantIndicatorClient.refreshWatchlist({
        cardIds: input.activeCards.map((card) => card.id)
      });
      setState({
        status: "ready",
        snapshotsByCardId: indexSnapshotsByCardId(result.snapshots),
        message: null
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        status: hasSnapshots(current.snapshotsByCardId) ? "failedRefresh" : "error",
        message: error instanceof Error ? error.message : "정량 지표 계산에 실패했습니다."
      }));
    }
  }, [canCalculate, cardIdsKey, input.activeCards, quantIndicatorClient]);

  useEffect(() => {
    void refreshNow();
  }, [refreshNow]);

  return {
    ...state,
    refreshNow
  };
}

function hasSnapshots(
  snapshotsByCardId: Record<string, QuantIndicatorSnapshotPayload>
): boolean {
  return Object.keys(snapshotsByCardId).length > 0;
}

function indexSnapshotsByCardId(
  snapshots: QuantIndicatorSnapshotPayload[]
): Record<string, QuantIndicatorSnapshotPayload> {
  return snapshots.reduce<Record<string, QuantIndicatorSnapshotPayload>>((indexed, snapshot) => {
    indexed[snapshot.cardId] = snapshot;

    return indexed;
  }, {});
}
