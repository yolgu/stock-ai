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
import type { QuantIndicatorClient } from "../infrastructure/neutralino/NeutralinoQuantIndicatorClient";
import type { StockReferenceClient } from "../infrastructure/neutralino/NeutralinoStockReferenceClient";
import type { TossSettingsClient } from "../infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "../infrastructure/neutralino/NeutralinoWatchlistClient";
import type {
  TossCredentialStatusPayload,
  VerifiedStockReferencePayload
} from "../shared/contracts/app-runtime-contract";
import { useMarketDataPolling } from "./useMarketDataPolling";
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
  const [selectedGroupId, setSelectedGroupId] = useState("all");
  const [selectedStatusFilter, setSelectedStatusFilter] =
    useState<CardStatusFilterValue>("all");
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
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
                  marketDataSnapshot: marketData.snapshotsByCardId[card.id] ?? null,
                  quantIndicatorSnapshot: quantIndicators.snapshotsByCardId[card.id] ?? null
                })}
                key={card.id}
                onArchive={() => void watchlist.archiveCard(card.id)}
                onDelete={() => void watchlist.deleteCard(card.id)}
                onHide={() => void watchlist.hideCard(card.id)}
                onMoveDown={() => moveCard(card.id, "down")}
                onMoveUp={() => moveCard(card.id, "up")}
                onSelect={() => setSelectedCardId(card.id)}
                canMoveDown={activeCards.findIndex((current) => current.id === card.id) < activeCards.length - 1}
                canMoveUp={activeCards.findIndex((current) => current.id === card.id) > 0}
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
                      quantIndicators.snapshotsByCardId[selectedCard.id] ?? null
                  })}
                  onClose={() => setSelectedCardId(null)}
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
  onArchive(): void;
  onDelete(): void;
  onHide(): void;
  onMoveDown(): void;
  onMoveUp(): void;
  onSelect(): void;
}

function WatchStockCardView({
  viewModel,
  canMoveDown,
  canMoveUp,
  onArchive,
  onDelete,
  onHide,
  onMoveDown,
  onMoveUp,
  onSelect
}: WatchStockCardViewProps): ReactElement {
  const card = viewModel.card;

  return (
    <article className="watch-card">
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

interface WatchStockDetailPanelProps {
  card: WatchStockCardDto;
  viewModel: DetailPanelViewModel;
  onClose(): void;
  onSave(input: { groupId: string | null; tags: string[]; memo: string }): void;
}

function WatchStockDetailPanel({
  card,
  viewModel,
  onClose,
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
