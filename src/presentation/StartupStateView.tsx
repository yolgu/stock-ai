import type { ReactElement } from "react";

export type StartupState =
  | {
      status: "loading";
    }
  | {
      status: "error";
      message: string;
      recoverable: boolean;
    };

export interface StartupStateViewProps {
  state: StartupState;
  onRetry?: () => void;
}

export function StartupStateView({
  state,
  onRetry
}: StartupStateViewProps): ReactElement {
  if (state.status === "loading") {
    return (
      <section className="startup-panel" aria-live="polite">
        <div className="startup-spinner" aria-hidden="true" />
        <h1>런타임 확인 중</h1>
        <p>앱 확장과 안전한 통신 경계를 준비하고 있습니다.</p>
      </section>
    );
  }

  return (
    <section className="startup-panel startup-panel--error" role="alert">
      <span className="status-orb status-orb--danger" aria-hidden="true" />
      <h1>시작할 수 없습니다</h1>
      <p>{state.message}</p>
      {state.recoverable ? (
        <button className="secondary-button" type="button" onClick={onRetry}>
          다시 시도
        </button>
      ) : null}
    </section>
  );
}
