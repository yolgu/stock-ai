import {
  useCallback,
  useEffect,
  useRef,
  useState
} from "react";

import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketStateClient } from "../infrastructure/neutralino/NeutralinoMarketStateClient";
import type {
  MarketStateBackfillProgressPayload,
  MarketStateFormulaSnapshotPayload,
  MarketStateHistoryPayload,
  MarketStateSignalId,
  MarketStateTracePayload,
  TossCredentialStatusPayload
} from "../shared/contracts/app-runtime-contract";

export type MarketStateLoadStatus =
  | "idle"
  | "loading"
  | "ready"
  | "error";

export interface UseMarketStateInput {
  activeCards: WatchStockCardDto[];
  credentials: TossCredentialStatusPayload;
  marketDataStatus: "idle" | "loading" | "ready" | "error";
  marketDataGenerationKey: string;
}

export interface UseMarketStateResult {
  status: MarketStateLoadStatus;
  snapshotsByCardId: Record<string, MarketStateFormulaSnapshotPayload>;
  backfillProgress: MarketStateBackfillProgressPayload;
  announcement: string | null;
  highlightedCardIds: ReadonlySet<string>;
  selectedTrace: MarketStateTracePayload | null;
  selectedHistory: MarketStateHistoryPayload | null;
  refreshNow(): Promise<void>;
  loadSignalDetail(
    cardId: string,
    signalId: MarketStateSignalId,
    sessionDate: string
  ): Promise<void>;
}

interface MarketStateViewState {
  status: MarketStateLoadStatus;
  snapshotsByCardId: Record<string, MarketStateFormulaSnapshotPayload>;
  backfillProgress: MarketStateBackfillProgressPayload;
  announcement: string | null;
  highlightedCardIds: ReadonlySet<string>;
  selectedTrace: MarketStateTracePayload | null;
  selectedHistory: MarketStateHistoryPayload | null;
}

const idleBackfillProgress: MarketStateBackfillProgressPayload = {
  jobId: "not-started",
  status: "idle",
  requiredSessions: 0,
  completedSessions: 0,
  currentInstrumentId: null,
  totalInstrumentCount: 0,
  completedInstrumentCount: 0,
  error: null
};

export function useMarketState(
  client: MarketStateClient,
  input: UseMarketStateInput
): UseMarketStateResult {
  const [state, setState] = useState<MarketStateViewState>({
    status: "idle",
    snapshotsByCardId: {},
    backfillProgress: idleBackfillProgress,
    announcement: null,
    highlightedCardIds: new Set<string>(),
    selectedTrace: null,
    selectedHistory: null
  });
  const announcedNotificationsRef = useRef<Set<string>>(new Set<string>());
  const cardIdsKey: string = input.activeCards
    .map((card: WatchStockCardDto): string => card.id)
    .join("|");
  const canCalculate: boolean =
    input.credentials.configured &&
    input.credentials.connectionStatus !== "invalid" &&
    input.marketDataStatus === "ready" &&
    input.activeCards.length > 0;

  const refreshNow = useCallback(async (): Promise<void> => {
    if (!canCalculate) {
      setState((current: MarketStateViewState): MarketStateViewState => ({
        ...current,
        status: "idle"
      }));
      return;
    }

    setState((current: MarketStateViewState): MarketStateViewState => ({
      ...current,
      status:
        Object.keys(current.snapshotsByCardId).length > 0
          ? "ready"
          : "loading"
    }));

    try {
      const result = await client.refreshWatchlist({
        cardIds: input.activeCards.map(
          (card: WatchStockCardDto): string => card.id
        )
      });
      const snapshotsByCardId: Record<
        string,
        MarketStateFormulaSnapshotPayload
      > = Object.fromEntries(
        result.snapshots.map(
          (
            snapshot: MarketStateFormulaSnapshotPayload
          ): [string, MarketStateFormulaSnapshotPayload] => [
            snapshot.cardId,
            snapshot
          ]
        )
      );
      const newNotifications: Array<{
        cardId: string;
        displayName: string;
      }> = [];

      for (const snapshot of result.snapshots) {
        for (const signalId of snapshot.notifiedSignalIds) {
          const notificationKey: string =
            `${snapshot.snapshotId}:${signalId}`;

          if (!announcedNotificationsRef.current.has(notificationKey)) {
            announcedNotificationsRef.current.add(notificationKey);
            const signal = snapshot.signals.find(
              (candidate): boolean =>
                candidate.signalId === signalId
            );
            newNotifications.push({
              cardId: snapshot.cardId,
              displayName: signal?.displayName ?? signalId
            });
          }
        }
      }

      const highlightedCardIds: ReadonlySet<string> = new Set(
        newNotifications.map(
          (notification): string => notification.cardId
        )
      );
      const announcement: string | null =
        newNotifications.length === 0
          ? null
          : newNotifications
              .map(
                (notification): string => {
                  const card = input.activeCards.find(
                    (candidate: WatchStockCardDto): boolean =>
                      candidate.id === notification.cardId
                  );

                  return `${card?.displayName ?? notification.cardId} ${notification.displayName} 감지`;
                }
              )
              .join(", ");
      setState(
        (current: MarketStateViewState): MarketStateViewState => ({
          ...current,
          status: "ready",
          snapshotsByCardId,
          backfillProgress: result.backfillProgress,
          announcement,
          highlightedCardIds
        })
      );
    } catch {
      setState((current: MarketStateViewState): MarketStateViewState => ({
        ...current,
        status: "error"
      }));
    }
  }, [canCalculate, client, input.activeCards]);

  useEffect((): void => {
    void refreshNow();
  }, [cardIdsKey, input.marketDataGenerationKey, refreshNow]);

  useEffect((): (() => void) | undefined => {
    if (state.highlightedCardIds.size === 0) {
      return undefined;
    }

    const timeoutId: number = window.setTimeout((): void => {
      setState((current: MarketStateViewState): MarketStateViewState => ({
        ...current,
        highlightedCardIds: new Set<string>(),
        announcement: null
      }));
    }, 3_000);

    return (): void => window.clearTimeout(timeoutId);
  }, [state.highlightedCardIds]);

  useEffect((): (() => void) | undefined => {
    if (state.backfillProgress.status !== "running") {
      return undefined;
    }

    const timeoutId: number = window.setTimeout((): void => {
      void refreshNow();
    }, 15_000);

    return (): void => window.clearTimeout(timeoutId);
  }, [refreshNow, state.backfillProgress.status]);

  const loadSignalDetail = useCallback(
    async (
      cardId: string,
      signalId: MarketStateSignalId,
      sessionDate: string
    ): Promise<void> => {
      const [traceResult, historyResult] = await Promise.all([
        client.readTrace({ cardId, signalId }),
        client.readHistory({ cardId, signalId, sessionDate })
      ]);
      setState((current: MarketStateViewState): MarketStateViewState => ({
        ...current,
        selectedTrace: traceResult.trace,
        selectedHistory: historyResult
      }));
    },
    [client]
  );

  return {
    ...state,
    refreshNow,
    loadSignalDetail
  };
}
