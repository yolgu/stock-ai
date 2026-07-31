import {
  AlertTriangle,
  Archive,
  Bell,
  ChevronDown,
  ChevronUp,
  EyeOff,
  HelpCircle,
  Plus,
  RotateCcw,
  Save,
  Settings,
  ShieldCheck,
  Trash2,
  X
} from "lucide-react";
import {
  type Dispatch,
  type FormEvent,
  type KeyboardEvent,
  type ReactElement,
  type RefObject,
  type SetStateAction,
  useEffect,
  useRef,
  useState
} from "react";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { MarketDataClient } from "../infrastructure/neutralino/NeutralinoMarketDataClient";
import type { MarketStateClient } from "../infrastructure/neutralino/NeutralinoMarketStateClient";
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { StockReferenceClient } from "../infrastructure/neutralino/NeutralinoStockReferenceClient";
import type { TossSettingsClient } from "../infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "../infrastructure/neutralino/NeutralinoWatchlistClient";
import type {
  MarketStateHistoryPointPayload,
  MarketStateSignalId,
  TossCredentialStatusPayload,
  VerifiedStockReferencePayload
} from "../shared/contracts/app-runtime-contract";
import { useMarketDataPolling } from "./useMarketDataPolling";
import { useMarketState } from "./useMarketState";
import { useQuantIndicators } from "./useQuantIndicators";
import { useStockReferenceVerification } from "./useStockReferenceVerification";
import { useTossCredentialSettings } from "./useTossCredentialSettings";
import { useWatchlist } from "./useWatchlist";
import {
  CARD_STATUS_FILTER_OPTIONS,
  createDetailPanelViewModel,
  createWatchGroupTabs,
  createWatchStockCardViewModel,
  filterWatchCards,
  splitTags,
  type CardStatusFilterValue,
  type BeginnerExplanationSectionViewModel,
  type DetailPanelViewModel,
  type MarketContextViewModel,
  type WatchGroupTabViewModel,
  type WatchStockCardViewModel
} from "./watchlistViewModels";

export interface AppShellProps {
  runtimeProfile: RuntimeProfileDto;
  watchlistClient: WatchlistClient;
  stockReferenceClient: StockReferenceClient;
  marketDataClient: MarketDataClient;
  marketStateClient?: MarketStateClient;
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

const idleMarketStateClient: MarketStateClient = {
  refreshWatchlist: async () => ({
    refreshedAt: new Date().toISOString(),
    snapshots: [],
    backfillProgress: {
      jobId: "not-started",
      status: "idle",
      requiredSessions: 0,
      completedSessions: 0,
      currentInstrumentId: null,
      totalInstrumentCount: 0,
      completedInstrumentCount: 0,
      error: null
    }
  }),
  readLatestSnapshots: async () => ({
    snapshots: [],
    backfillProgress: {
      jobId: "not-started",
      status: "idle",
      requiredSessions: 0,
      completedSessions: 0,
      currentInstrumentId: null,
      totalInstrumentCount: 0,
      completedInstrumentCount: 0,
      error: null
    }
  }),
  readTrace: async () => ({ trace: null }),
  readHistory: async (input) => ({
    cardId: input.cardId,
    signalId: input.signalId,
    sessionDate: input.sessionDate,
    points: []
  })
};

export function AppShell({
  runtimeProfile,
  watchlistClient,
  stockReferenceClient,
  marketDataClient,
  marketStateClient,
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
  const [selectedGroupId, setSelectedGroupId] = useState("all");
  const [selectedStatusFilter, setSelectedStatusFilter] =
    useState<CardStatusFilterValue>("all");
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [selectedMarketStateSignalId, setSelectedMarketStateSignalId] =
    useState<MarketStateSignalId>("FOMO_LIKE");
  const activeCards = watchlist.watchlist.activeCards;
  const marketData = useMarketDataPolling(marketDataClient, {
    activeCards,
    credentials: tossSettings.credentials
  });
  const marketDataGenerationKey: string = Object.values(
    marketData.snapshotsByCardId
  )
    .map((snapshot): string => `${snapshot.cardId}:${snapshot.snapshotId}`)
    .sort()
    .join("|");
  const marketState = useMarketState(
    marketStateClient ?? idleMarketStateClient,
    {
      activeCards,
      credentials: tossSettings.credentials,
      marketDataStatus: marketData.status,
      marketDataGenerationKey
    }
  );
  const quantIndicators = useQuantIndicators(quantIndicatorClient, {
    activeCards,
    credentials: tossSettings.credentials,
    marketDataStatus: marketData.status
  });
  const canVerifySymbols =
    tossSettings.credentials.configured &&
    tossSettings.credentials.connectionStatus !== "invalid";
  const filteredCards = filterWatchCards({
    cards: activeCards,
    snapshotsByCardId: quantIndicators.snapshotsByCardId,
    filter: {
      groupId: selectedGroupId,
      status: selectedStatusFilter
    }
  });
  const groupTabs = createWatchGroupTabs(activeCards);
  const selectedCard = activeCards.find((card) => card.id === selectedCardId) ?? null;

  useEffect(() => {
    if (selectedCardId !== null && activeCards.every((card) => card.id !== selectedCardId)) {
      setSelectedCardId(null);
    }
  }, [activeCards, selectedCardId]);

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

  const moveCard = (cardId: string, direction: "up" | "down"): void => {
    const currentIndex = activeCards.findIndex((card) => card.id === cardId);

    if (currentIndex < 0) {
      return;
    }

    const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;

    if (targetIndex < 0 || targetIndex >= activeCards.length) {
      return;
    }

    const orderedCardIds = activeCards.map((card) => card.id);
    [orderedCardIds[currentIndex], orderedCardIds[targetIndex]] = [
      orderedCardIds[targetIndex],
      orderedCardIds[currentIndex]
    ];
    void watchlist.reorderCards(orderedCardIds);
  };

  const closeAddDialog = (): void => {
    setIsAddFormOpen(false);
    setPendingTickerConfirmation(null);
    stockReference.clear();
  };

  const selectMarketStateSignal = (
    cardId: string,
    signalId: MarketStateSignalId
  ): void => {
    setSelectedCardId(cardId);
    setSelectedMarketStateSignalId(signalId);
    const snapshot = marketState.snapshotsByCardId[cardId];

    if (snapshot !== undefined && snapshot.sessionDate !== "") {
      void marketState.loadSignalDetail(
        cardId,
        signalId,
        snapshot.sessionDate
      );
    }
  };

  const openCardDetail = (cardId: string): void => {
    selectMarketStateSignal(cardId, "FOMO_LIKE");
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
          <AddSymbolDialog
            canVerifySymbols={canVerifySymbols}
            form={tickerAddForm}
            pendingConfirmation={pendingTickerConfirmation}
            stockReferenceMessage={stockReference.message}
            stockReferenceStatus={stockReference.status}
            onChangeForm={setTickerAddForm}
            onClose={closeAddDialog}
            onConfirmPendingTicker={confirmPendingTicker}
            onOpenSettings={() => setIsSettingsOpen(true)}
            onSubmit={submitTickerAddition}
          />
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
          <>
            <WatchDashboardControls
              groupTabs={groupTabs}
              selectedGroupId={selectedGroupId}
              selectedStatus={selectedStatusFilter}
              onSelectGroup={(groupId) => {
                setSelectedGroupId(groupId);
                setSelectedStatusFilter("all");
              }}
              onSelectStatus={setSelectedStatusFilter}
            />
            <section className="watch-dashboard-layout" aria-label="관심종목 대시보드">
              <section className="watch-card-grid" aria-label="관심종목 목록">
                {filteredCards.map((card) => (
                  <WatchStockCardView
                    viewModel={createWatchStockCardViewModel({
                      card,
                      marketDataSnapshot:
                        marketData.snapshotsByCardId[card.id] ?? null,
                      quantIndicatorSnapshot:
                        quantIndicators.snapshotsByCardId[card.id] ?? null,
                      quantIndicatorStatus: quantIndicators.status,
                      marketStateSnapshot:
                        marketState.snapshotsByCardId[card.id] ?? null
                    })}
                    key={card.id}
                    onArchive={() => void watchlist.archiveCard(card.id)}
                    onDelete={() => void watchlist.deleteCard(card.id)}
                    onHide={() => void watchlist.hideCard(card.id)}
                    onMoveDown={() => moveCard(card.id, "down")}
                    onMoveUp={() => moveCard(card.id, "up")}
                    onSelect={() => openCardDetail(card.id)}
                    onSelectMarketStateSignal={(signalId) =>
                      selectMarketStateSignal(card.id, signalId)
                    }
                    highlighted={marketState.highlightedCardIds.has(card.id)}
                    canMoveDown={
                      activeCards.findIndex(
                        (current) => current.id === card.id
                      ) < activeCards.length - 1
                    }
                    canMoveUp={
                      activeCards.findIndex(
                        (current) => current.id === card.id
                      ) > 0
                    }
                  />
                ))}
              </section>
              {selectedCard !== null ? (
                <WatchStockDetailPanel
                  card={selectedCard}
                  viewModel={createDetailPanelViewModel({
                    card: selectedCard,
                    marketDataSnapshot: marketData.snapshotsByCardId[selectedCard.id] ?? null,
                    quantIndicatorSnapshot:
                      quantIndicators.snapshotsByCardId[selectedCard.id] ?? null,
                    quantIndicatorStatus: quantIndicators.status,
                    marketStateSnapshot:
                      marketState.snapshotsByCardId[selectedCard.id] ?? null,
                    selectedMarketStateSignalId,
                    marketStateTrace: marketState.selectedTrace,
                    marketStateHistory: marketState.selectedHistory
                  })}
                  onClose={() => setSelectedCardId(null)}
                  onSelectMarketStateSignal={(signalId) =>
                    selectMarketStateSignal(selectedCard.id, signalId)
                  }
                  onSave={(input) => void watchlist.updateCard(selectedCard.id, input)}
                />
              ) : null}
            </section>
          </>
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

        <p className="sr-only" aria-live="polite">
          {marketState.announcement ?? ""}
        </p>

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
        <SettingsDialog
          credentialForm={credentialForm}
          credentials={tossSettings.credentials}
          message={tossSettings.message}
          onChangeForm={setCredentialForm}
          onClose={() => setIsSettingsOpen(false)}
          onDeleteCredentials={() => void tossSettings.deleteCredentials()}
          onSubmit={submitCredentials}
          onTestConnection={() => void tossSettings.testConnection()}
        />
      ) : null}
    </main>
  );
}

interface WatchDashboardControlsProps {
  groupTabs: WatchGroupTabViewModel[];
  selectedGroupId: string;
  selectedStatus: CardStatusFilterValue;
  onSelectGroup(groupId: string): void;
  onSelectStatus(status: CardStatusFilterValue): void;
}

function WatchDashboardControls({
  groupTabs,
  selectedGroupId,
  selectedStatus,
  onSelectGroup,
  onSelectStatus
}: WatchDashboardControlsProps): ReactElement {
  return (
    <section className="dashboard-controls" aria-label="관심종목 필터">
      <div className="segmented-control" role="group" aria-label="그룹 필터">
        {groupTabs.map((group) => (
          <button
            className={group.value === selectedGroupId ? "segment-button is-active" : "segment-button"}
            type="button"
            key={group.value}
            onClick={() => onSelectGroup(group.value)}
          >
            {group.label}
          </button>
        ))}
      </div>
      <div className="segmented-control" role="group" aria-label="상태 필터">
        {CARD_STATUS_FILTER_OPTIONS.map((option) => (
          <button
            className={option.value === selectedStatus ? "segment-button is-active" : "segment-button"}
            type="button"
            key={option.value}
            onClick={() => onSelectStatus(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}

interface WatchStockCardViewProps {
  viewModel: WatchStockCardViewModel;
  canMoveDown: boolean;
  canMoveUp: boolean;
  highlighted: boolean;
  onArchive(): void;
  onDelete(): void;
  onHide(): void;
  onMoveDown(): void;
  onMoveUp(): void;
  onSelect(): void;
  onSelectMarketStateSignal(signalId: MarketStateSignalId): void;
}

function WatchStockCardView({
  viewModel,
  canMoveDown,
  canMoveUp,
  highlighted,
  onArchive,
  onDelete,
  onHide,
  onMoveDown,
  onMoveUp,
  onSelect,
  onSelectMarketStateSignal
}: WatchStockCardViewProps): ReactElement {
  const card = viewModel.card;

  return (
    <article
      className={
        highlighted
          ? "watch-card watch-card--market-state-alert"
          : "watch-card"
      }
    >
      <header className="watch-card__header">
        <div>
          <p className="watch-card__symbol">
            {card.market} · {card.symbol}
          </p>
          <h2>{card.displayName}</h2>
        </div>
        <span className={viewModel.marketDataStatusClassName}>
          {viewModel.marketDataStatusLabel}
        </span>
      </header>
      <MarketContextStrip marketContext={viewModel.marketContext} compact />
      <MarketStateCardView
        marketState={viewModel.marketState}
        symbol={card.symbol}
        onSelectSignal={onSelectMarketStateSignal}
      />
      {card.memo.trim() !== "" ? <p className="watch-card__memo">{card.memo}</p> : null}
      <section className="quant-card-state" aria-label={`${card.symbol} 정량 지표 상태`}>
        <div>
          <span className={viewModel.quantDecisionClassName}>
            {viewModel.quantDecisionLabel}
          </span>
          <span className="quant-card-state__time">
            {viewModel.quantUpdatedAtLabel}
          </span>
        </div>
        {viewModel.nextCheckLabel !== null ? (
          <>
            <p className="quant-card-state__next">{viewModel.nextCheckLabel}</p>
            <div className="quant-signal-row">
              {viewModel.signalChips.map((signal) => (
                <span
                  className={`quant-signal quant-signal--${signal.severity}`}
                  key={signal.key}
                >
                  {signal.displayLabel}
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
        <button
          className="secondary-button secondary-button--compact"
          type="button"
          aria-label={`${card.displayName} 상세 보기`}
          onClick={onSelect}
        >
          상세
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label={`${card.displayName} 위로 이동`}
          disabled={!canMoveUp}
          onClick={onMoveUp}
        >
          <ChevronUp size={16} />
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label={`${card.displayName} 아래로 이동`}
          disabled={!canMoveDown}
          onClick={onMoveDown}
        >
          <ChevronDown size={16} />
        </button>
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

interface MarketStateCardViewProps {
  marketState: WatchStockCardViewModel["marketState"];
  symbol: string;
  onSelectSignal(signalId: MarketStateSignalId): void;
}

function MarketStateCardView({
  marketState,
  symbol,
  onSelectSignal
}: MarketStateCardViewProps): ReactElement {
  return (
    <section
      className="market-state-card"
      aria-label={`${symbol} 심리·시장 신호`}
    >
      <header className="market-state-card__header">
        <strong>심리·시장 신호</strong>
        <span>{marketState.asOfLabel}</span>
      </header>
      <div className="market-state-signal-grid">
        {marketState.signals.map((signal) => (
          <button
            className={`market-state-signal market-state-signal--${signal.status}`}
            type="button"
            key={signal.signalId}
            aria-label={`${signal.displayName} ${signal.percentileLabel} ${signal.statusLabel} 상세`}
            onClick={() => onSelectSignal(signal.signalId)}
          >
            <span className="market-state-signal__name">
              {signal.displayName}
              <HelpCircle size={12} aria-hidden="true" />
            </span>
            <b>{signal.percentileLabel}</b>
            <span>{signal.statusLabel}</span>
            {signal.lastDetectionLabel !== null ? (
              <small>{signal.lastDetectionLabel}</small>
            ) : null}
          </button>
        ))}
      </div>
      <p className="market-state-card__observed">
        관측 상태 · {marketState.observedStateLabel}
      </p>
    </section>
  );
}

interface MarketStateDetailViewProps {
  marketState: DetailPanelViewModel["marketState"];
  onSelectSignal(signalId: MarketStateSignalId): void;
}

function MarketStateDetailView({
  marketState,
  onSelectSignal
}: MarketStateDetailViewProps): ReactElement {
  const trace = marketState.trace;
  const history = marketState.history;
  const recentPoints = history?.points.slice(-12) ?? [];
  const topContributions =
    trace?.trace?.contributions
      .slice()
      .sort(
        (left, right): number =>
          Math.abs(right.contribution) -
          Math.abs(left.contribution)
      )
      .slice(0, 5) ?? [];
  const thresholdPercentile =
    trace?.trace === null || trace?.trace === undefined
      ? null
      : (1 - trace.trace.effectiveTailShare) * 100;

  return (
    <div className="market-state-detail">
      <div className="market-state-detail__summary">
        <span>{marketState.asOfLabel}</span>
        <strong>관측 상태 · {marketState.observedStateLabel}</strong>
      </div>
      <div
        className="market-state-detail__tabs"
        role="tablist"
        aria-label="시장상태 신호 선택"
      >
        {marketState.signals.map((signal) => (
          <button
            className={
              signal.signalId === marketState.selectedSignalId
                ? "market-state-detail__tab is-active"
                : "market-state-detail__tab"
            }
            type="button"
            role="tab"
            aria-selected={
              signal.signalId === marketState.selectedSignalId
            }
            key={signal.signalId}
            onClick={() => onSelectSignal(signal.signalId)}
          >
            <span>{signal.displayName}</span>
            <b>{signal.percentileLabel}</b>
            <small>{signal.statusLabel}</small>
          </button>
        ))}
      </div>

      <article className="market-state-judgment">
        <header>
          <div>
            <p className="eyebrow">
              {marketState.selectedSignal.displayName}
            </p>
            <h4>{marketState.selectedSignal.statusLabel}</h4>
          </div>
          <strong className="market-state-judgment__percentile">
            {marketState.selectedSignal.percentileLabel}
          </strong>
        </header>
        {marketState.selectedSignal.lastDetectionLabel !== null ? (
          <p>{marketState.selectedSignal.lastDetectionLabel}</p>
        ) : null}
        {trace === null ? (
          <p className="muted-copy">
            현재 판정의 계산 상세는 데이터 준비 후 표시됩니다.
          </p>
        ) : (
          <>
            <dl className="market-state-metrics">
              <Metric
                label="20거래일 백분위"
                value={
                  trace.percentile === null
                    ? "—"
                    : `${trace.percentile.toFixed(4)} / 100`
                }
              />
              <Metric
                label="경험 CDF"
                value={
                  trace.percentileNumerator === null ||
                  trace.percentileDenominator === null
                    ? "—"
                    : `${trace.percentileNumerator} / ${trace.percentileDenominator}`
                }
              />
              <Metric
                label="원점수 η"
                value={formatTechnicalNumber(trace.rawScore)}
              />
              <Metric
                label="동적 임계값 τ"
                value={formatTechnicalNumber(trace.dynamicThreshold)}
              />
              <Metric
                label="임계 대비 η−τ"
                value={formatTechnicalNumber(trace.thresholdDistance)}
              />
              <Metric
                label="예측 구간"
                value={`${trace.horizonMinutes}분`}
              />
              <Metric
                label="관측/요구 상태"
                value={`${trace.currentRiskState} / ${trace.requiredRiskState}`}
              />
              <Metric label="마지막 완료봉" value={trace.asOf} />
            </dl>
            {trace.gate !== null ? (
              <p
                className={
                  trace.gate.passed
                    ? "market-state-gate market-state-gate--passed"
                    : "market-state-gate market-state-gate--failed"
                }
              >
                게이트 · {trace.gate.label}{" "}
                {formatTechnicalNumber(trace.gate.value)}{" "}
                {trace.gate.operator} {trace.gate.threshold} ·{" "}
                {trace.gate.passed ? "통과" : "미통과"}
              </p>
            ) : (
              <p className="market-state-gate">
                별도 보조 게이트 없음
              </p>
            )}
          </>
        )}
      </article>

      <section className="market-state-chart-section">
        <h4>최근 60분 변화</h4>
        <SignalHistoryChart
          points={recentPoints}
          thresholdPercentile={thresholdPercentile}
        />
      </section>

      {trace?.trace !== null && trace?.trace !== undefined ? (
        <>
          <section className="market-state-contributions">
            <h4>점수를 크게 움직인 요인</h4>
            <div>
              {topContributions.map((contribution) => (
                <article key={contribution.featureName}>
                  <span>{contribution.featureName}</span>
                  <b>
                    {contribution.contribution >= 0 ? "+" : ""}
                    {formatTechnicalNumber(
                      contribution.contribution
                    )}
                  </b>
                </article>
              ))}
            </div>
          </section>

          <details className="market-state-formula-details">
            <summary>
              전체 수식과 {trace.trace.contributions.length}개 입력 보기
            </summary>
            <p>
              η = {formatTechnicalNumber(trace.trace.intercept)} + Σ
              βⱼ((xⱼ−μⱼ)/σⱼ)
            </p>
            <p className="muted-copy">
              x는 현재 관측값, μ는 연구 표본 평균, σ는 연구 표본 척도,
              z는 표준화값, βz는 최종 원점수 기여입니다.
            </p>
            <div className="market-state-formula-table-wrap">
              <table className="market-state-formula-table">
                <thead>
                  <tr>
                    <th scope="col">입력</th>
                    <th scope="col">x</th>
                    <th scope="col">μ</th>
                    <th scope="col">σ</th>
                    <th scope="col">z</th>
                    <th scope="col">β</th>
                    <th scope="col">βz</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.trace.contributions.map((contribution) => (
                    <tr key={contribution.featureName}>
                      <th scope="row">
                        {contribution.featureName}
                      </th>
                      <td>
                        {formatTechnicalNumber(
                          contribution.rawValue
                        )}
                      </td>
                      <td>
                        {formatTechnicalNumber(contribution.mean)}
                      </td>
                      <td>
                        {formatTechnicalNumber(contribution.scale)}
                      </td>
                      <td>
                        {formatTechnicalNumber(
                          contribution.standardizedValue
                        )}
                      </td>
                      <td>
                        {formatTechnicalNumber(
                          contribution.coefficient
                        )}
                      </td>
                      <td>
                        {formatTechnicalNumber(
                          contribution.contribution
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <dl className="market-state-lineage">
              <Metric
                label="Formula version"
                value={trace.formulaVersion}
              />
              <Metric
                label="Payload SHA-256"
                value={trace.formulaContentSha256}
              />
              <Metric
                label="입력 generation"
                value={trace.sourceGenerationId}
              />
            </dl>
          </details>
        </>
      ) : null}

      {history !== null && history.points.length > 12 ? (
        <details className="market-state-formula-details">
          <summary>당일 전체 변화 보기</summary>
          <SignalHistoryChart
            points={history.points}
            thresholdPercentile={thresholdPercentile}
          />
        </details>
      ) : null}

      <p className="market-state-limitation">
        이 값은 완료된 5분 OHLCV에서 관측한 가격·거래량 형태의
        상대적 강도입니다. 투자자 심리, 사건 발생확률 또는
        매수·매도 권고를 직접 뜻하지 않으며, 임계값 아래로 내려가도
        “해소”로 해석하지 않습니다.
      </p>
    </div>
  );
}

interface MetricProps {
  label: string;
  value: string;
}

function Metric({ label, value }: MetricProps): ReactElement {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

interface SignalHistoryChartProps {
  points: MarketStateHistoryPointPayload[];
  thresholdPercentile: number | null;
}

function SignalHistoryChart({
  points,
  thresholdPercentile
}: SignalHistoryChartProps): ReactElement {
  const width: number = 320;
  const height: number = 92;
  const padding: number = 8;
  const finitePoints = points.filter(
    (
      point
    ): point is MarketStateHistoryPointPayload & {
      percentile: number;
    } => point.percentile !== null
  );

  if (finitePoints.length === 0) {
    return (
      <p className="market-state-chart-empty">
        표시할 완료 5분봉 이력이 없습니다.
      </p>
    );
  }

  const coordinates = finitePoints.map(
    (point, index): { x: number; y: number; detected: boolean } => ({
      x:
        finitePoints.length === 1
          ? width / 2
          : padding +
            (index / (finitePoints.length - 1)) *
              (width - 2 * padding),
      y:
        height -
        padding -
        (point.percentile / 100) * (height - 2 * padding),
      detected: point.detected
    })
  );
  const path: string = coordinates
    .map(
      (coordinate, index): string =>
        `${index === 0 ? "M" : "L"}${coordinate.x.toFixed(2)},${coordinate.y.toFixed(2)}`
    )
    .join(" ");
  const thresholdY: number | null =
    thresholdPercentile === null
      ? null
      : height -
        padding -
        (thresholdPercentile / 100) * (height - 2 * padding);

  return (
    <svg
      className="market-state-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="완료된 5분봉별 시장상태 백분위 변화"
    >
      <line
        className="market-state-chart__baseline"
        x1={padding}
        x2={width - padding}
        y1={height - padding}
        y2={height - padding}
      />
      {thresholdY !== null ? (
        <line
          className="market-state-chart__threshold"
          x1={padding}
          x2={width - padding}
          y1={thresholdY}
          y2={thresholdY}
        />
      ) : null}
      <path className="market-state-chart__line" d={path} />
      {coordinates.map((coordinate, index) =>
        coordinate.detected ? (
          <circle
            className="market-state-chart__detection"
            cx={coordinate.x}
            cy={coordinate.y}
            key={`${coordinate.x}-${index}`}
            r="3"
          />
        ) : null
      )}
    </svg>
  );
}

function formatTechnicalNumber(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }

  if (value === 0) {
    return "0";
  }

  return Math.abs(value) >= 1_000 || Math.abs(value) < 0.0001
    ? value.toExponential(4)
    : value.toFixed(6);
}

interface WatchStockDetailPanelProps {
  card: WatchStockCardDto;
  viewModel: DetailPanelViewModel;
  onClose(): void;
  onSelectMarketStateSignal(signalId: MarketStateSignalId): void;
  onSave(input: { groupId: string | null; tags: string[]; memo: string }): void;
}

function WatchStockDetailPanel({
  card,
  viewModel,
  onClose,
  onSelectMarketStateSignal,
  onSave
}: WatchStockDetailPanelProps): ReactElement {
  const [memo, setMemo] = useState(viewModel.memo);
  const [tags, setTags] = useState(viewModel.tagsText);
  const [group, setGroup] = useState(viewModel.groupText);
  const [activeExplanationKey, setActiveExplanationKey] = useState<string | null>(null);

  useEffect(() => {
    setMemo(viewModel.memo);
    setTags(viewModel.tagsText);
    setGroup(viewModel.groupText);
  }, [viewModel.memo, viewModel.tagsText, viewModel.groupText]);

  const submitEdit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    onSave({
      memo,
      tags: splitTags(tags),
      groupId: group.trim() === "" ? null : group.trim()
    });
  };

  const explanationsByKey: Record<string, BeginnerExplanationSectionViewModel> =
    Object.fromEntries(viewModel.explanationSections.map((section) => [section.key, section]));
  const activeExplanation =
    activeExplanationKey === null ? null : explanationsByKey[activeExplanationKey] ?? null;
  const activeTooltipId =
    activeExplanationKey === null ? null : `indicator-explanation-${activeExplanationKey}`;
  const toggleExplanation = (key: string): void => {
    setActiveExplanationKey((currentKey) => (currentKey === key ? null : key));
  };

  return (
    <>
      <aside
        className="detail-panel"
        aria-label={`${card.symbol} 상세 분석`}
        role="complementary"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            if (activeExplanationKey !== null) {
              event.preventDefault();
              event.stopPropagation();
              setActiveExplanationKey(null);
              return;
            }

            onClose();
          }
        }}
      >
        <header className="detail-panel__header">
          <div>
            <p className="watch-card__symbol">{viewModel.subtitle}</p>
            <h2>{viewModel.title}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="상세 닫기" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <section className="detail-section" aria-labelledby="market-context-heading">
          <h3 id="market-context-heading">현재 가격 좌표</h3>
          <MarketContextStrip marketContext={viewModel.marketContext} />
        </section>

        <section
          className="detail-section"
          aria-labelledby="market-state-detail-heading"
        >
          <h3 id="market-state-detail-heading">심리·시장 신호</h3>
          <MarketStateDetailView
            marketState={viewModel.marketState}
            onSelectSignal={onSelectMarketStateSignal}
          />
        </section>

        <section className="detail-section" aria-labelledby="quant-checklist-heading">
          <h3 id="quant-checklist-heading">진입 전 체크</h3>
          <QuantChecklistView
            activeExplanationKey={activeExplanationKey}
            explanationsByKey={explanationsByKey}
            rows={viewModel.checklistRows}
            onCloseExplanation={() => setActiveExplanationKey(null)}
            onToggleExplanation={toggleExplanation}
          />
        </section>

        <section className="detail-section" aria-labelledby="conditional-zone-heading">
          <h3 id="conditional-zone-heading">조건부 구간</h3>
          <ConditionalZoneView zones={viewModel.conditionalZones} />
        </section>

        <section className="detail-section" aria-labelledby="data-quality-heading">
          <h3 id="data-quality-heading">데이터 품질</h3>
          <DataQualityBadge dataQuality={viewModel.dataQuality} />
        </section>

        <section className="detail-section" aria-labelledby="ai-insight-heading">
          <div className="detail-section__title-row">
            <h3 id="ai-insight-heading">{viewModel.aiInsightLabel}</h3>
            <span className="quant-card-state__time">AI 분석 미실행</span>
          </div>
          <p className="muted-copy">
            뉴스 감성, 3거래일 전망, 지표 충돌 해석은 Step 12에서 수동 새로고침으로 연결됩니다.
          </p>
          <button className="secondary-button" type="button" disabled>
            AI 분석은 Step 12에서 활성화
          </button>
        </section>

        <form className="detail-edit-form" onSubmit={submitEdit}>
          <label>
            상세 메모
            <input value={memo} onChange={(event) => setMemo(event.target.value)} />
          </label>
          <label>
            상세 태그
            <input value={tags} onChange={(event) => setTags(event.target.value)} />
          </label>
          <label>
            상세 그룹
            <input value={group} onChange={(event) => setGroup(event.target.value)} />
          </label>
          <button className="primary-button" type="submit">
            <Save size={16} />
            카드 저장
          </button>
        </form>
      </aside>
      {activeExplanation !== null && activeTooltipId !== null ? (
        <div className="indicator-explanation-layer">
          <button
            aria-label="지표 설명 닫기"
            className="indicator-explanation-backdrop"
            type="button"
            onClick={() => setActiveExplanationKey(null)}
          />
          <IndicatorExplanationPopover id={activeTooltipId} explanation={activeExplanation} />
        </div>
      ) : null}
    </>
  );
}

interface QuantChecklistViewProps {
  activeExplanationKey: string | null;
  explanationsByKey: Record<string, BeginnerExplanationSectionViewModel>;
  rows: DetailPanelViewModel["checklistRows"];
  onCloseExplanation(): void;
  onToggleExplanation(key: string): void;
}

function QuantChecklistView({
  activeExplanationKey,
  explanationsByKey,
  rows,
  onCloseExplanation,
  onToggleExplanation
}: QuantChecklistViewProps): ReactElement {
  return (
    <div className="quant-checklist">
      {rows.map((row) => {
        const explanation = explanationsByKey[row.key] ?? null;
        const isExplanationOpen = activeExplanationKey === row.key && explanation !== null;
        const tooltipId = `indicator-explanation-${row.key}`;

        return (
          <article className="checklist-row" key={row.key}>
            <span className={`checklist-dot checklist-dot--${row.severity}`} aria-hidden="true" />
            <strong>{row.label}</strong>
            <span className="checklist-row__status">
              {row.displayStatusLabel}
              {explanation !== null ? (
                <span className="checklist-help">
                  <button
                    aria-controls={isExplanationOpen ? tooltipId : undefined}
                    aria-describedby={isExplanationOpen ? tooltipId : undefined}
                    aria-expanded={isExplanationOpen}
                    className="icon-button icon-button--inline"
                    type="button"
                    aria-label={`${row.label} 초보자 설명 보기`}
                    onClick={() => onToggleExplanation(row.key)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.preventDefault();
                        event.stopPropagation();
                        onCloseExplanation();
                      }
                    }}
                  >
                    <HelpCircle size={14} />
                  </button>
                </span>
              ) : null}
            </span>
            {row.reason !== null ? <p>{row.reason}</p> : null}
          </article>
        );
      })}
    </div>
  );
}

interface ConditionalZoneViewProps {
  zones: DetailPanelViewModel["conditionalZones"];
}

function ConditionalZoneView({ zones }: ConditionalZoneViewProps): ReactElement {
  return (
    <div className="conditional-zone-grid">
      {zones.map((zone) => (
        <article
          className={`conditional-zone conditional-zone--${zone.tone}${
            zone.active ? " is-active" : ""
          }`}
          key={zone.key}
        >
          <strong>{zone.title}</strong>
          <p>{zone.description}</p>
        </article>
      ))}
    </div>
  );
}

interface DataQualityBadgeProps {
  dataQuality: DetailPanelViewModel["dataQuality"];
}

function DataQualityBadge({ dataQuality }: DataQualityBadgeProps): ReactElement {
  return (
    <div className={`data-quality-badge data-quality-badge--${dataQuality.tone}`}>
      <span>{dataQuality.marketLabel}</span>
      <span>{dataQuality.quantLabel}</span>
    </div>
  );
}

interface MarketContextStripProps {
  compact?: boolean;
  marketContext: MarketContextViewModel;
}

function MarketContextStrip({
  compact = false,
  marketContext
}: MarketContextStripProps): ReactElement {
  if (marketContext.currentPriceLabel === null) {
    return (
      <div className={`market-context-strip${compact ? " market-context-strip--compact" : ""}`}>
        <span className="market-context-strip__empty">{marketContext.updatedAtLabel}</span>
      </div>
    );
  }

  return (
    <div
      className={`market-context-strip market-context-strip--${marketContext.tone}${
        compact ? " market-context-strip--compact" : ""
      }`}
      aria-label="현재 가격 좌표"
    >
      <strong>{marketContext.currentPriceLabel}</strong>
      {marketContext.absoluteChangeLabel !== null ? (
        <span>{marketContext.absoluteChangeLabel}</span>
      ) : null}
      {marketContext.simpleReturnLabel !== null ? (
        <span>{marketContext.simpleReturnLabel}</span>
      ) : null}
      <small>{marketContext.updatedAtLabel}</small>
    </div>
  );
}

interface IndicatorExplanationPopoverProps {
  explanation: BeginnerExplanationSectionViewModel;
  id: string;
}

function IndicatorExplanationPopover({
  explanation,
  id
}: IndicatorExplanationPopoverProps): ReactElement {
  return (
    <aside
      aria-label={`${explanation.title} 설명`}
      className="indicator-explanation-popover indicator-explanation-popover--centered"
      id={id}
      role="tooltip"
    >
      <div className="indicator-explanation-popover__header">
        <p className="watch-card__symbol">{explanation.source}</p>
        <strong>{explanation.title}</strong>
      </div>
      <ExplanationBlock title="무슨 뜻인가요?" lines={[explanation.meaning]} />
      <ExplanationBlock title="왜 보나요?" lines={[explanation.usage]} />
      <ExplanationBlock title="원래 공식" lines={explanation.originalFormula} />
      <ExplanationBlock title="현재 값 대입" lines={explanation.substitutedFormula} />
      <ExplanationBlock title="계산 결과" lines={explanation.result} />
      <ExplanationBlock title="판정 기준" lines={[explanation.judgment]} />
      <ExplanationBlock title="주의점" lines={[explanation.caution]} />
      {explanation.limitation !== null ? (
        <ExplanationBlock title="한계" lines={[explanation.limitation]} />
      ) : null}
    </aside>
  );
}

interface ExplanationBlockProps {
  lines: string[];
  title: string;
}

function ExplanationBlock({ lines, title }: ExplanationBlockProps): ReactElement {
  return (
    <div className="explanation-block">
      <strong>{title}</strong>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

interface AddSymbolDialogProps {
  canVerifySymbols: boolean;
  form: TickerAddFormState;
  pendingConfirmation: PendingTickerConfirmation | null;
  stockReferenceMessage: string | null;
  stockReferenceStatus: "idle" | "loading" | "ready" | "error";
  onChangeForm: Dispatch<SetStateAction<TickerAddFormState>>;
  onClose(): void;
  onConfirmPendingTicker(): void;
  onOpenSettings(): void;
  onSubmit(event: FormEvent<HTMLFormElement>): void;
}

function AddSymbolDialog({
  canVerifySymbols,
  form,
  pendingConfirmation,
  stockReferenceMessage,
  stockReferenceStatus,
  onChangeForm,
  onClose,
  onConfirmPendingTicker,
  onOpenSettings,
  onSubmit
}: AddSymbolDialogProps): ReactElement {
  const dialog = useModalDialog(onClose);

  return (
    <section className="modal-backdrop" role="presentation">
      <div
        className="settings-panel add-symbol-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-symbol-heading"
        ref={dialog.dialogRef}
        onKeyDown={dialog.handleKeyDown}
      >
        <header className="settings-panel__header">
          <div>
            <p className="eyebrow">Watch Card</p>
            <h2 id="add-symbol-heading">종목 추가</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="종목 추가 닫기"
            ref={dialog.initialFocusRef}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <form
          className="inline-form symbol-intake-form"
          aria-label="종목 카드 추가"
          onSubmit={onSubmit}
        >
          <label>
            시장
            <select
              value={form.market}
              onChange={(event) =>
                onChangeForm((current) => ({
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
              value={form.ticker}
              placeholder="MU"
              required
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  ticker: event.target.value.toUpperCase()
                }))
              }
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={stockReferenceStatus === "loading"}
          >
            <Plus size={16} />
            추가
          </button>
          <label>
            태그
            <input
              value={form.tags}
              onChange={(event) =>
                onChangeForm((current) => ({ ...current, tags: event.target.value }))
              }
            />
          </label>
          <label className="inline-form__wide">
            메모
            <input
              value={form.memo}
              onChange={(event) =>
                onChangeForm((current) => ({ ...current, memo: event.target.value }))
              }
            />
          </label>
          {!canVerifySymbols ? (
            <div className="form-alert inline-form__full">
              <AlertTriangle size={16} />
              <span>Toss API 설정 후 종목을 추가할 수 있습니다.</span>
              <button className="secondary-button" type="button" onClick={onOpenSettings}>
                설정 열기
              </button>
            </div>
          ) : null}
          {pendingConfirmation !== null ? (
            <div className="form-alert inline-form__full">
              <AlertTriangle size={16} />
              <span>{formatTickerConfirmationMessage(pendingConfirmation)}</span>
              <button
                className="secondary-button"
                type="button"
                onClick={onConfirmPendingTicker}
              >
                {formatTickerConfirmationAction(pendingConfirmation)}
              </button>
            </div>
          ) : null}
          {stockReferenceMessage !== null ? (
            <p className="status-message inline-form__full">{stockReferenceMessage}</p>
          ) : null}
        </form>
      </div>
    </section>
  );
}

interface SettingsDialogProps {
  credentialForm: TossCredentialFormState;
  credentials: TossCredentialStatusPayload;
  message: string | null;
  onChangeForm: Dispatch<SetStateAction<TossCredentialFormState>>;
  onClose(): void;
  onDeleteCredentials(): void;
  onSubmit(event: FormEvent<HTMLFormElement>): void;
  onTestConnection(): void;
}

function SettingsDialog({
  credentialForm,
  credentials,
  message,
  onChangeForm,
  onClose,
  onDeleteCredentials,
  onSubmit,
  onTestConnection
}: SettingsDialogProps): ReactElement {
  const dialog = useModalDialog(onClose);

  return (
    <section className="modal-backdrop" role="presentation">
      <div
        className="settings-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-heading"
        ref={dialog.dialogRef}
        onKeyDown={dialog.handleKeyDown}
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
            ref={dialog.initialFocusRef}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="credential-status">
          <span>연결 상태</span>
          <strong>{formatConnectionStatus(credentials.connectionStatus)}</strong>
          {credentials.maskedClientId !== null ? <span>{credentials.maskedClientId}</span> : null}
        </div>
        <form className="settings-form" onSubmit={onSubmit}>
          <label>
            Toss API Key
            <input
              value={credentialForm.clientId}
              onChange={(event) =>
                onChangeForm((current) => ({
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
                onChangeForm((current) => ({
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
            <button className="secondary-button" type="button" onClick={onTestConnection}>
              연결 테스트
            </button>
            <button
              className="secondary-button secondary-button--danger"
              type="button"
              onClick={onDeleteCredentials}
            >
              삭제
            </button>
          </div>
        </form>
        {message !== null ? <p className="status-message">{message}</p> : null}
      </div>
    </section>
  );
}

interface ModalDialogHandle {
  dialogRef: RefObject<HTMLDivElement | null>;
  initialFocusRef: RefObject<HTMLButtonElement | null>;
  handleKeyDown(event: KeyboardEvent<HTMLElement>): void;
}

function useModalDialog(onClose: () => void): ModalDialogHandle {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const initialFocusRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const previousActiveElement = document.activeElement;
    initialFocusRef.current?.focus();

    return () => {
      if (previousActiveElement instanceof HTMLElement) {
        previousActiveElement.focus();
      }
    };
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    const focusableElements = findFocusableElements(dialogRef.current);

    if (focusableElements.length === 0) {
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  };

  return {
    dialogRef,
    initialFocusRef,
    handleKeyDown
  };
}

function findFocusableElements(root: HTMLElement | null): HTMLElement[] {
  if (root === null) {
    return [];
  }

  return Array.from(
    root.querySelectorAll<HTMLElement>(
      "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"
    )
  ).filter((element) => !element.hasAttribute("disabled"));
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
