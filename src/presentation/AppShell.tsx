import {
  AlertTriangle,
  Archive,
  Bell,
  EyeOff,
  Plus,
  RotateCcw,
  Settings,
  ShieldCheck,
  Trash2,
  X
} from "lucide-react";
import { type FormEvent, type ReactElement, useState } from "react";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { StockReferenceClient } from "../infrastructure/neutralino/NeutralinoStockReferenceClient";
import type { TossSettingsClient } from "../infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "../infrastructure/neutralino/NeutralinoWatchlistClient";
import type {
  MarketDataSnapshotPayload,
  QuantIndicatorSnapshotPayload,
  VerifiedStockReferencePayload
} from "../shared/contracts/app-runtime-contract";
import { useMarketDataPolling } from "./useMarketDataPolling";
import { useQuantIndicators } from "./useQuantIndicators";
import { useStockReferenceVerification } from "./useStockReferenceVerification";
import { useTossCredentialSettings } from "./useTossCredentialSettings";
import { useWatchlist } from "./useWatchlist";

export interface AppShellProps {
  runtimeProfile: RuntimeProfileDto;
  watchlistClient: WatchlistClient;
  stockReferenceClient: StockReferenceClient;
  marketDataClient: MarketDataClient;
  quantIndicatorClient: QuantIndicatorClient;
  tossSettingsClient: TossSettingsClient;
}

const stockMarketOptions = ["NASDAQ", "NYSE", "AMEX", "KOSPI", "KOSDAQ"] as const;

type StockMarketOption = (typeof stockMarketOptions)[number];

interface TickerAddFormState {
  market: StockMarketOption;
  ticker: string;
  tags: string;
  memo: string;
}

type PendingTickerConfirmation =
  | {
      kind: "marketMismatch";
      identity: VerifiedStockReferencePayload;
    }
  | {
      kind: "risk";
      identity: VerifiedStockReferencePayload;
    };

interface TossCredentialFormState {
  clientId: string;
  clientSecret: string;
}

const initialTickerAddFormState: TickerAddFormState = {
  market: "NASDAQ",
  ticker: "",
  tags: "",
  memo: ""
};

const initialCredentialFormState: TossCredentialFormState = {
  clientId: "",
  clientSecret: ""
};

export function AppShell({
  runtimeProfile,
  watchlistClient,
  stockReferenceClient,
  marketDataClient,
  quantIndicatorClient,
  tossSettingsClient
}: AppShellProps): ReactElement {
  const watchlist = useWatchlist(watchlistClient);
  const stockReference = useStockReferenceVerification(stockReferenceClient);
  const tossSettings = useTossCredentialSettings(tossSettingsClient);
  const [isAddFormOpen, setIsAddFormOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [tickerAddForm, setTickerAddForm] =
    useState<TickerAddFormState>(initialTickerAddFormState);
  const [pendingTickerConfirmation, setPendingTickerConfirmation] =
    useState<PendingTickerConfirmation | null>(null);
  const [credentialForm, setCredentialForm] =
    useState<TossCredentialFormState>(initialCredentialFormState);
  const activeCards = watchlist.watchlist.activeCards;
  const marketData = useMarketDataPolling(marketDataClient, {
    activeCards,
    credentials: tossSettings.credentials
  });
  const quantIndicators = useQuantIndicators(quantIndicatorClient, {
    activeCards,
    credentials: tossSettings.credentials,
    marketDataStatus: marketData.status
  });
  const canVerifySymbols =
    tossSettings.credentials.configured &&
    tossSettings.credentials.connectionStatus !== "invalid";

  const submitTickerAddition = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();

    if (!canVerifySymbols) {
      setIsSettingsOpen(true);
      return;
    }

    void verifyAndCreateTickerCard();
  };

  const submitCredentials = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void tossSettings.saveCredentials(credentialForm).then(() => {
      setCredentialForm(initialCredentialFormState);
    });
  };

  const verifyAndCreateTickerCard = async (): Promise<void> => {
    const ticker = tickerAddForm.ticker.trim().toUpperCase();

    if (ticker === "") {
      return;
    }

    setPendingTickerConfirmation(null);
    const verification = await stockReference.verify(ticker);

    if (verification === null || verification.verified.length !== 1) {
      return;
    }

    continueVerifiedIdentity(verification.verified[0]);
  };

  const continueVerifiedIdentity = (
    identity: VerifiedStockReferencePayload,
    options: { allowMarketMismatch: boolean } = { allowMarketMismatch: false }
  ): void => {
    if (!options.allowMarketMismatch && identity.market !== tickerAddForm.market) {
      setPendingTickerConfirmation({ kind: "marketMismatch", identity });
      return;
    }

    if (identity.requiresConfirmation) {
      setPendingTickerConfirmation({ kind: "risk", identity });
      return;
    }

    createVerifiedCard(identity, false);
  };

  const confirmPendingTicker = (): void => {
    if (pendingTickerConfirmation === null) {
      return;
    }

    if (pendingTickerConfirmation.kind === "marketMismatch") {
      continueVerifiedIdentity(pendingTickerConfirmation.identity, {
        allowMarketMismatch: true
      });
      return;
    }

    createVerifiedCard(pendingTickerConfirmation.identity, true);
  };

  const createVerifiedCard = (
    identity: VerifiedStockReferencePayload,
    confirmedRisk: boolean
  ): void => {
    void stockReference
      .createVerifiedCard({
        symbol: identity.symbol,
        confirmedRisk,
        groupId: null,
        tags: splitTags(tickerAddForm.tags),
        memo: tickerAddForm.memo
      })
      .then((result) => {
        if (result === null) {
          return;
        }

        if (result.type === "created") {
          watchlist.applyWatchlist(result.watchlist, "검증된 카드를 추가했습니다.");
          setTickerAddForm(initialTickerAddFormState);
          setPendingTickerConfirmation(null);
          stockReference.clear();
          setIsAddFormOpen(false);
          return;
        }

        watchlist.applyWatchlist(
          result.watchlist,
          result.type === "duplicate-card"
            ? "이미 같은 시장과 심볼의 카드가 있습니다."
            : "보관된 카드가 있어 복원할 수 있습니다."
        );
      });
  };

  return (
    <main className="app-background">
      <section className="workspace-shell" aria-labelledby="watchlist-ready-heading">
        <header className="workspace-header">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">
              st
            </div>
            <div>
              <p className="eyebrow">Stock Sub</p>
              <h1 id="watchlist-ready-heading">관심종목 분석 대기</h1>
              <p className="muted-copy">토스 차트 옆에서 볼 분석 카드를 준비합니다.</p>
            </div>
          </div>
          <div className="header-actions" aria-label="앱 작업">
            <button
              className="icon-button"
              type="button"
              aria-label="설정"
              onClick={() => setIsSettingsOpen(true)}
            >
              <Settings size={18} />
            </button>
            <button className="icon-button" type="button" aria-label="알림">
              <Bell size={18} />
            </button>
          </div>
        </header>

        <section className="watchlist-toolbar" aria-label="관심종목 작업">
          <div>
            <h2>관심종목 목록</h2>
            <p className="muted-copy">
              {activeCards.length === 0
                ? "분석 카드를 추가해 로컬 관심종목을 구성합니다."
                : `${activeCards.length}개 카드가 준비되었습니다.`}
            </p>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => setIsAddFormOpen((current) => !current)}
          >
            <Plus size={17} />
            종목 추가
          </button>
        </section>

        {isAddFormOpen ? (
          <form
            className="inline-form symbol-intake-form"
            aria-label="종목 카드 추가"
            onSubmit={submitTickerAddition}
          >
            <label>
              시장
              <select
                value={tickerAddForm.market}
                onChange={(event) =>
                  setTickerAddForm((current) => ({
                    ...current,
                    market: event.target.value as StockMarketOption
                  }))
                }
              >
                {stockMarketOptions.map((market) => (
                  <option value={market} key={market}>
                    {market}
                  </option>
                ))}
              </select>
            </label>
            <label>
              티커
              <input
                value={tickerAddForm.ticker}
                placeholder="MU"
                required
                onChange={(event) => {
                  setPendingTickerConfirmation(null);
                  setTickerAddForm((current) => ({
                    ...current,
                    ticker: event.target.value.toUpperCase()
                  }));
                }}
              />
            </label>
            <button
              className="primary-button"
              type="submit"
              disabled={stockReference.status === "loading"}
            >
              <Plus size={16} />
              추가
            </button>
            <label>
              태그
              <input
                value={tickerAddForm.tags}
                onChange={(event) =>
                  setTickerAddForm((current) => ({ ...current, tags: event.target.value }))
                }
              />
            </label>
            <label className="inline-form__wide">
              메모
              <input
                value={tickerAddForm.memo}
                onChange={(event) =>
                  setTickerAddForm((current) => ({ ...current, memo: event.target.value }))
                }
              />
            </label>
            {!canVerifySymbols ? (
              <div className="form-alert inline-form__full">
                <AlertTriangle size={16} />
                <span>Toss API 설정 후 종목을 추가할 수 있습니다.</span>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setIsSettingsOpen(true)}
                >
                  설정 열기
                </button>
              </div>
            ) : null}
            {pendingTickerConfirmation !== null ? (
              <div className="form-alert inline-form__full">
                <AlertTriangle size={16} />
                <span>{formatTickerConfirmationMessage(pendingTickerConfirmation)}</span>
                <button className="secondary-button" type="button" onClick={confirmPendingTicker}>
                  {formatTickerConfirmationAction(pendingTickerConfirmation)}
                </button>
              </div>
            ) : null}
            {stockReference.message !== null ? (
              <p className="status-message inline-form__full">{stockReference.message}</p>
            ) : null}
          </form>
        ) : null}

        {activeCards.length === 0 ? (
          <section className="empty-watchlist-panel" aria-label="관심종목 목록">
            <div className="empty-watchlist-copy">
              <div className="signal-icon signal-icon--blue" aria-hidden="true">
                <ShieldCheck size={24} />
              </div>
              <h2>분석 카드가 없습니다</h2>
              <p>시장과 티커를 입력해 Toss 종목정보 검증 후 카드를 추가합니다.</p>
            </div>
          </section>
        ) : (
          <section className="watch-card-grid" aria-label="관심종목 목록">
            {activeCards.map((card) => (
              <WatchStockCardView
                card={card}
                key={card.id}
                marketDataSnapshot={marketData.snapshotsByCardId[card.id] ?? null}
                quantIndicatorSnapshot={quantIndicators.snapshotsByCardId[card.id] ?? null}
                onArchive={() => void watchlist.archiveCard(card.id)}
                onDelete={() => void watchlist.deleteCard(card.id)}
                onHide={() => void watchlist.hideCard(card.id)}
              />
            ))}
          </section>
        )}

        {watchlist.watchlist.hiddenCards.length > 0 ||
        watchlist.watchlist.archivedCards.length > 0 ? (
          <section className="secondary-card-list" aria-label="숨김 및 보관 카드">
            {watchlist.watchlist.hiddenCards.map((card) => (
              <RecoverableCardRow
                card={card}
                key={card.id}
                label="숨김"
                onDelete={() => void watchlist.deleteCard(card.id)}
                onRestore={() => void watchlist.restoreCard(card.id)}
              />
            ))}
            {watchlist.watchlist.archivedCards.map((card) => (
              <RecoverableCardRow
                card={card}
                key={card.id}
                label="보관"
                onDelete={() => void watchlist.deleteCard(card.id)}
                onRestore={() => void watchlist.restoreCard(card.id)}
              />
            ))}
          </section>
        ) : null}

        {watchlist.message !== null ? (
          <p className="status-message">{watchlist.message}</p>
        ) : null}

        <section className="capability-strip" aria-label="런타임 기능 상태">
          {runtimeProfile.capabilities.map((capability) => (
            <article className="capability-chip" key={capability.name}>
              <span className="capability-name">{capability.name}</span>
              <span
                className={
                  capability.enabled
                    ? "capability-status capability-status--ready"
                    : "capability-status capability-status--waiting"
                }
              >
                {capability.enabled ? "준비됨" : "대기"}
              </span>
            </article>
          ))}
        </section>
      </section>

      {isSettingsOpen ? (
        <section className="modal-backdrop" role="presentation">
          <div
            className="settings-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-heading"
          >
            <header className="settings-panel__header">
              <div>
                <p className="eyebrow">Toss Open API</p>
                <h2 id="settings-heading">설정</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="설정 닫기"
                onClick={() => setIsSettingsOpen(false)}
              >
                <X size={18} />
              </button>
            </header>
            <div className="credential-status">
              <span>연결 상태</span>
              <strong>{formatConnectionStatus(tossSettings.credentials.connectionStatus)}</strong>
              {tossSettings.credentials.maskedClientId !== null ? (
                <span>{tossSettings.credentials.maskedClientId}</span>
              ) : null}
            </div>
            <form className="settings-form" onSubmit={submitCredentials}>
              <label>
                Toss API Key
                <input
                  value={credentialForm.clientId}
                  onChange={(event) =>
                    setCredentialForm((current) => ({
                      ...current,
                      clientId: event.target.value
                    }))
                  }
                />
              </label>
              <label>
                Toss Secret Key
                <input
                  type="password"
                  value={credentialForm.clientSecret}
                  onChange={(event) =>
                    setCredentialForm((current) => ({
                      ...current,
                      clientSecret: event.target.value
                    }))
                  }
                />
              </label>
              <div className="settings-actions">
                <button className="primary-button" type="submit">
                  저장
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void tossSettings.testConnection()}
                >
                  연결 테스트
                </button>
                <button
                  className="secondary-button secondary-button--danger"
                  type="button"
                  onClick={() => void tossSettings.deleteCredentials()}
                >
                  삭제
                </button>
              </div>
            </form>
            {tossSettings.message !== null ? (
              <p className="status-message">{tossSettings.message}</p>
            ) : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}

interface WatchStockCardViewProps {
  card: WatchStockCardDto;
  marketDataSnapshot: MarketDataSnapshotPayload | null;
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null;
  onArchive(): void;
  onDelete(): void;
  onHide(): void;
}

function WatchStockCardView({
  card,
  marketDataSnapshot,
  quantIndicatorSnapshot,
  onArchive,
  onDelete,
  onHide
}: WatchStockCardViewProps): ReactElement {
  return (
    <article className="watch-card">
      <header className="watch-card__header">
        <div>
          <p className="watch-card__symbol">
            {card.market} · {card.symbol}
          </p>
          <h2>{card.displayName}</h2>
        </div>
        <span className={formatMarketDataStatusClassName(marketDataSnapshot)}>
          {formatMarketDataStatus(marketDataSnapshot)}
        </span>
      </header>
      {card.memo.trim() !== "" ? <p className="watch-card__memo">{card.memo}</p> : null}
      <section className="quant-card-state" aria-label={`${card.symbol} 정량 지표 상태`}>
        <div>
          <span className={formatQuantDecisionClassName(quantIndicatorSnapshot)}>
            {formatQuantDecisionLabel(quantIndicatorSnapshot)}
          </span>
          <span className="quant-card-state__time">
            {formatQuantUpdatedAt(quantIndicatorSnapshot)}
          </span>
        </div>
        {quantIndicatorSnapshot !== null ? (
          <>
            <p className="quant-card-state__next">{quantIndicatorSnapshot.nextCheckLabel}</p>
            <div className="quant-signal-row">
              {quantIndicatorSnapshot.signals.slice(0, 3).map((signal) => (
                <span
                  className={`quant-signal quant-signal--${signal.severity}`}
                  key={signal.key}
                >
                  {signal.label}
                </span>
              ))}
            </div>
          </>
        ) : null}
      </section>
      {card.tags.length > 0 ? (
        <div className="tag-row">
          {card.tags.map((tag) => (
            <span className="tag-chip" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      <footer className="watch-card__actions">
        <button className="icon-button" type="button" aria-label="숨김" onClick={onHide}>
          <EyeOff size={16} />
        </button>
        <button className="icon-button" type="button" aria-label="보관" onClick={onArchive}>
          <Archive size={16} />
        </button>
        <button className="icon-button" type="button" aria-label="삭제" onClick={onDelete}>
          <Trash2 size={16} />
        </button>
      </footer>
    </article>
  );
}

interface RecoverableCardRowProps {
  card: WatchStockCardDto;
  label: string;
  onDelete(): void;
  onRestore(): void;
}

function RecoverableCardRow({
  card,
  label,
  onDelete,
  onRestore
}: RecoverableCardRowProps): ReactElement {
  return (
    <article className="recoverable-card-row">
      <span>{label}</span>
      <strong>{card.displayName}</strong>
      <span>
        {card.market} · {card.symbol}
      </span>
      <button className="icon-button" type="button" aria-label="복원" onClick={onRestore}>
        <RotateCcw size={16} />
      </button>
      <button className="icon-button" type="button" aria-label="삭제" onClick={onDelete}>
        <Trash2 size={16} />
      </button>
    </article>
  );
}

function splitTags(tags: string): string[] {
  return tags
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag !== "");
}

function formatConnectionStatus(status: string): string {
  const labels: Record<string, string> = {
    notConfigured: "미설정",
    saved: "저장됨",
    valid: "연결 확인",
    invalid: "키 확인 필요",
    error: "연결 오류"
  };

  return labels[status] ?? "확인 필요";
}

function formatMarketDataStatus(snapshot: MarketDataSnapshotPayload | null): string {
  if (snapshot === null) {
    return "시장 데이터 대기";
  }

  if (snapshot.quality === "unavailable" || snapshot.quality === "degraded") {
    return "수집 오류";
  }

  if (snapshot.quality === "partial") {
    return "부분 수집";
  }

  if (snapshot.freshness === "stale") {
    return "오래됨";
  }

  return `업데이트 ${formatSnapshotTime(snapshot.capturedAt)}`;
}

function formatMarketDataStatusClassName(snapshot: MarketDataSnapshotPayload | null): string {
  if (snapshot === null) {
    return "watch-card__status watch-card__status--waiting";
  }

  if (snapshot.quality === "unavailable" || snapshot.quality === "degraded") {
    return "watch-card__status watch-card__status--danger";
  }

  if (snapshot.quality === "partial" || snapshot.freshness === "stale") {
    return "watch-card__status watch-card__status--warning";
  }

  return "watch-card__status watch-card__status--ready";
}

function formatQuantDecisionLabel(snapshot: QuantIndicatorSnapshotPayload | null): string {
  return snapshot?.decisionLabel ?? "지표 대기";
}

function formatQuantUpdatedAt(snapshot: QuantIndicatorSnapshotPayload | null): string {
  if (snapshot === null) {
    return "지표 업데이트 대기";
  }

  return `지표 업데이트 ${formatSnapshotTime(snapshot.calculatedAt)}`;
}

function formatQuantDecisionClassName(snapshot: QuantIndicatorSnapshotPayload | null): string {
  if (snapshot === null) {
    return "quant-decision quant-decision--waiting";
  }

  const classNames: Record<string, string> = {
    watch: "quant-decision quant-decision--watch",
    confirmationWaiting: "quant-decision quant-decision--waiting",
    riskHigh: "quant-decision quant-decision--risk",
    invalidated: "quant-decision quant-decision--invalidated",
    dataInsufficient: "quant-decision quant-decision--insufficient"
  };

  return classNames[snapshot.decisionStatus] ?? "quant-decision quant-decision--waiting";
}

function formatSnapshotTime(capturedAt: string): string {
  const match = capturedAt.match(/T(\d{2}:\d{2}:\d{2})/);

  return match?.[1] ?? "--:--:--";
}

function formatTickerConfirmationMessage(confirmation: PendingTickerConfirmation): string {
  if (confirmation.kind === "marketMismatch") {
    return `${confirmation.identity.symbol}는 ${confirmation.identity.market} 종목입니다.`;
  }

  return `${confirmation.identity.symbol}는 상태 확인이 필요한 종목입니다.`;
}

function formatTickerConfirmationAction(confirmation: PendingTickerConfirmation): string {
  if (confirmation.kind === "marketMismatch") {
    return `${confirmation.identity.market}으로 추가`;
  }

  return "확인 후 추가";
}
