import { useCallback, useEffect, useState } from "react";

import type {
  CreateWatchCardPayload,
  WatchlistClient,
  WatchlistListPayload
} from "../infrastructure/neutralino/NeutralinoWatchlistClient";

export interface WatchlistViewState {
  status: "ready" | "loading" | "error";
  watchlist: WatchlistListPayload;
  message: string | null;
}

export interface UseWatchlistResult extends WatchlistViewState {
  refresh(): Promise<void>;
  createCard(input: CreateWatchCardPayload): Promise<void>;
  hideCard(cardId: string): Promise<void>;
  archiveCard(cardId: string): Promise<void>;
  restoreCard(cardId: string): Promise<void>;
  deleteCard(cardId: string): Promise<void>;
}

const emptyWatchlist: WatchlistListPayload = {
  activeCards: [],
  hiddenCards: [],
  archivedCards: []
};

export function useWatchlist(watchlistClient: WatchlistClient): UseWatchlistResult {
  const [state, setState] = useState<WatchlistViewState>({
    status: "ready",
    watchlist: emptyWatchlist,
    message: null
  });

  const showError = useCallback((error: unknown): void => {
    setState((current) => ({
      ...current,
      status: "error",
      message: error instanceof Error ? error.message : "관심종목 요청에 실패했습니다."
    }));
  }, []);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const watchlist = await watchlistClient.list();
      setState({
        status: "ready",
        watchlist,
        message: null
      });
    } catch (error) {
      showError(error);
    }
  }, [showError, watchlistClient]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createCard = useCallback(
    async (input: CreateWatchCardPayload): Promise<void> => {
      try {
        const result = await watchlistClient.create(input);

        if (result.type === "created") {
          setState({
            status: "ready",
            watchlist: result.watchlist,
            message: "카드를 추가했습니다."
          });
          return;
        }

        setState((current) => ({
          ...current,
          status: "ready",
          message:
            result.type === "duplicate-card"
              ? "이미 같은 시장과 심볼의 카드가 있습니다."
              : "보관된 카드가 있어 복원할 수 있습니다."
        }));
      } catch (error) {
        showError(error);
      }
    },
    [showError, watchlistClient]
  );

  const hideCard = useCallback(
    async (cardId: string): Promise<void> => {
      try {
        const result = await watchlistClient.hide(cardId);
        setState({ status: "ready", watchlist: result.watchlist, message: "카드를 숨겼습니다." });
      } catch (error) {
        showError(error);
      }
    },
    [showError, watchlistClient]
  );

  const archiveCard = useCallback(
    async (cardId: string): Promise<void> => {
      try {
        const result = await watchlistClient.archive(cardId);
        setState({ status: "ready", watchlist: result.watchlist, message: "카드를 보관했습니다." });
      } catch (error) {
        showError(error);
      }
    },
    [showError, watchlistClient]
  );

  const restoreCard = useCallback(
    async (cardId: string): Promise<void> => {
      try {
        const result = await watchlistClient.restore(cardId);
        setState({ status: "ready", watchlist: result.watchlist, message: "카드를 복원했습니다." });
      } catch (error) {
        showError(error);
      }
    },
    [showError, watchlistClient]
  );

  const deleteCard = useCallback(
    async (cardId: string): Promise<void> => {
      try {
        const watchlist = await watchlistClient.delete(cardId);
        setState({ status: "ready", watchlist, message: "카드를 삭제했습니다." });
      } catch (error) {
        showError(error);
      }
    },
    [showError, watchlistClient]
  );

  return {
    ...state,
    refresh,
    createCard,
    hideCard,
    archiveCard,
    restoreCard,
    deleteCard
  };
}
