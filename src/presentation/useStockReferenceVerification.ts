import { useCallback, useState } from "react";

import type {
  CreateVerifiedWatchCardPayload,
  StockReferenceVerificationPayload
} from "../shared/contracts/app-runtime-contract";
import type {
  CreateVerifiedWatchCardResponse,
  StockReferenceClient
} from "../infrastructure/neutralino/NeutralinoStockReferenceClient";

export interface StockReferenceVerificationState {
  status: "ready" | "loading" | "error";
  verification: StockReferenceVerificationPayload | null;
  message: string | null;
}

export interface UseStockReferenceVerificationResult
  extends StockReferenceVerificationState {
  verify(rawInput: string): Promise<StockReferenceVerificationPayload | null>;
  createVerifiedCard(
    input: CreateVerifiedWatchCardPayload
  ): Promise<CreateVerifiedWatchCardResponse | null>;
  clear(): void;
}

export function useStockReferenceVerification(
  stockReferenceClient: StockReferenceClient
): UseStockReferenceVerificationResult {
  const [state, setState] = useState<StockReferenceVerificationState>({
    status: "ready",
    verification: null,
    message: null
  });

  const showError = useCallback((error: unknown): void => {
    setState((current) => ({
      ...current,
      status: "error",
      message: error instanceof Error ? error.message : "종목 검증에 실패했습니다."
    }));
  }, []);

  const verify = useCallback(
    async (rawInput: string): Promise<StockReferenceVerificationPayload | null> => {
      try {
        setState((current) => ({ ...current, status: "loading", message: null }));
        const verification = await stockReferenceClient.verify({ rawInput });
        setState({
          status: "ready",
          verification,
          message: selectVerificationMessage(verification)
        });
        return verification;
      } catch (error) {
        showError(error);
        return null;
      }
    },
    [showError, stockReferenceClient]
  );

  const createVerifiedCard = useCallback(
    async (
      input: CreateVerifiedWatchCardPayload
    ): Promise<CreateVerifiedWatchCardResponse | null> => {
      try {
        return await stockReferenceClient.createVerifiedCard(input);
      } catch (error) {
        showError(error);
        return null;
      }
    },
    [showError, stockReferenceClient]
  );

  const clear = useCallback((): void => {
    setState({
      status: "ready",
      verification: null,
      message: null
    });
  }, []);

  return {
    ...state,
    verify,
    createVerifiedCard,
    clear
  };
}

function selectVerificationMessage(verification: StockReferenceVerificationPayload): string {
  if (verification.verified.length > 0) {
    return "검증된 종목을 확인했습니다.";
  }

  return verification.rejected[0]?.message ?? "추가할 수 있는 종목을 찾지 못했습니다.";
}
