import { useEffect, useReducer } from "react";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import {
  RuntimeProfileClientError,
  type RuntimeProfileClient
} from "../infrastructure/neutralino/NeutralinoRuntimeProfileClient";

export type RuntimeProfileState =
  | {
      status: "loading";
    }
  | {
      status: "ready";
      runtimeProfile: RuntimeProfileDto;
    }
  | {
      status: "error";
      message: string;
      recoverable: boolean;
    };

type RuntimeProfileAction =
  | {
      type: "requestStarted";
    }
  | {
      type: "requestSucceeded";
      runtimeProfile: RuntimeProfileDto;
    }
  | {
      type: "requestFailed";
      message: string;
      recoverable: boolean;
    };

export function useRuntimeProfile(
  runtimeProfileClient: RuntimeProfileClient
): RuntimeProfileState {
  const [state, dispatch] = useReducer(reduceRuntimeProfileState, { status: "loading" });

  useEffect(() => {
    let shouldApplyResult = true;

    dispatch({ type: "requestStarted" });
    void runtimeProfileClient
      .loadRuntimeProfile()
      .then((runtimeProfile) => {
        if (shouldApplyResult) {
          dispatch({ type: "requestSucceeded", runtimeProfile });
        }
      })
      .catch((error: unknown) => {
        if (shouldApplyResult) {
          dispatch(toFailedAction(error));
        }
      });

    return () => {
      shouldApplyResult = false;
    };
  }, [runtimeProfileClient]);

  return state;
}

function reduceRuntimeProfileState(
  state: RuntimeProfileState,
  action: RuntimeProfileAction
): RuntimeProfileState {
  switch (action.type) {
    case "requestStarted":
      return { status: "loading" };
    case "requestSucceeded":
      return { status: "ready", runtimeProfile: action.runtimeProfile };
    case "requestFailed":
      return {
        status: "error",
        message: action.message,
        recoverable: action.recoverable
      };
  }

  return state;
}

function toFailedAction(error: unknown): RuntimeProfileAction {
  if (error instanceof RuntimeProfileClientError) {
    return {
      type: "requestFailed",
      message: error.message,
      recoverable: error.recoverable
    };
  }

  return {
    type: "requestFailed",
    message: error instanceof Error ? error.message : "runtime profile request failed",
    recoverable: true
  };
}
