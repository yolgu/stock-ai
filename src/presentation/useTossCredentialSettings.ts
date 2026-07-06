import { useCallback, useEffect, useState } from "react";

import type { TossSettingsClient } from "../infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { TossCredentialStatusPayload } from "../shared/contracts/app-runtime-contract";

export interface TossCredentialSettingsState {
  status: "ready" | "loading" | "error";
  credentials: TossCredentialStatusPayload;
  message: string | null;
}

export interface UseTossCredentialSettingsResult extends TossCredentialSettingsState {
  refresh(): Promise<void>;
  saveCredentials(input: { clientId: string; clientSecret: string }): Promise<void>;
  deleteCredentials(): Promise<void>;
  testConnection(): Promise<void>;
}

const notConfiguredStatus: TossCredentialStatusPayload = {
  configured: false,
  maskedClientId: null,
  lastValidatedAt: null,
  connectionStatus: "notConfigured"
};

export function useTossCredentialSettings(
  tossSettingsClient: TossSettingsClient
): UseTossCredentialSettingsResult {
  const [state, setState] = useState<TossCredentialSettingsState>({
    status: "ready",
    credentials: notConfiguredStatus,
    message: null
  });

  const showError = useCallback((error: unknown): void => {
    setState((current) => ({
      ...current,
      status: "error",
      message: error instanceof Error ? error.message : "Toss 설정 요청에 실패했습니다."
    }));
  }, []);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const credentials = await tossSettingsClient.readStatus();
      setState({ status: "ready", credentials, message: null });
    } catch (error) {
      showError(error);
    }
  }, [showError, tossSettingsClient]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveCredentials = useCallback(
    async (input: { clientId: string; clientSecret: string }): Promise<void> => {
      try {
        const credentials = await tossSettingsClient.saveCredentials(input);
        setState({ status: "ready", credentials, message: "Toss 키를 저장했습니다." });
      } catch (error) {
        showError(error);
      }
    },
    [showError, tossSettingsClient]
  );

  const deleteCredentials = useCallback(async (): Promise<void> => {
    try {
      const credentials = await tossSettingsClient.deleteCredentials();
      setState({ status: "ready", credentials, message: "Toss 키를 삭제했습니다." });
    } catch (error) {
      showError(error);
    }
  }, [showError, tossSettingsClient]);

  const testConnection = useCallback(async (): Promise<void> => {
    try {
      const credentials = await tossSettingsClient.testConnection();
      setState({ status: "ready", credentials, message: "Toss 연결을 확인했습니다." });
    } catch (error) {
      showError(error);
    }
  }, [showError, tossSettingsClient]);

  return {
    ...state,
    refresh,
    saveCredentials,
    deleteCredentials,
    testConnection
  };
}
