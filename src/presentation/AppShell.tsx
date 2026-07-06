import {
  Archive,
  Bell,
  EyeOff,
  Plus,
  RotateCcw,
  Save,
  Settings,
  ShieldCheck,
  Trash2,
  X
} from "lucide-react";
import { type FormEvent, type ReactElement, useState } from "react";

import type { RuntimeProfileDto } from "../domain/runtime/AppRuntimeProfile";
import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type { TossSettingsClient } from "../infrastructure/neutralino/NeutralinoTossSettingsClient";
import type { WatchlistClient } from "../infrastructure/neutralino/NeutralinoWatchlistClient";
import { useTossCredentialSettings } from "./useTossCredentialSettings";
import { useWatchlist } from "./useWatchlist";

export interface AppShellProps {
  runtimeProfile: RuntimeProfileDto;
  watchlistClient: WatchlistClient;
  tossSettingsClient: TossSettingsClient;
}

interface CardFormState {
  market: string;
  symbol: string;
  displayName: string;
  groupId: string;
  tags: string;
  memo: string;
}

interface TossCredentialFormState {
  clientId: string;
  clientSecret: string;
}

const initialCardFormState: CardFormState = {
  market: "NASDAQ",
  symbol: "",
  displayName: "",
  groupId: "",
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
  tossSettingsClient
}: AppShellProps): ReactElement {
  const watchlist = useWatchlist(watchlistClient);
  const tossSettings = useTossCredentialSettings(tossSettingsClient);
  const [isAddFormOpen, setIsAddFormOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [cardForm, setCardForm] = useState<CardFormState>(initialCardFormState);
  const [credentialForm, setCredentialForm] =
    useState<TossCredentialFormState>(initialCredentialFormState);
  const activeCards = watchlist.watchlist.activeCards;

  const submitCard = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void watchlist
      .createCard({
        market: cardForm.market,
        symbol: cardForm.symbol,
        displayName: cardForm.displayName,
        groupId: cardForm.groupId.trim() === "" ? null : cardForm.groupId.trim(),
        tags: splitTags(cardForm.tags),
        memo: cardForm.memo
      })
      .then(() => {
        setCardForm(initialCardFormState);
        setIsAddFormOpen(false);
      });
  };

  const submitCredentials = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void tossSettings.saveCredentials(credentialForm).then(() => {
      setCredentialForm(initialCredentialFormState);
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
          <form className="inline-form" aria-label="종목 카드 추가" onSubmit={submitCard}>
            <label>
              시장
              <input
                value={cardForm.market}
                onChange={(event) =>
                  setCardForm((current) => ({ ...current, market: event.target.value }))
                }
              />
            </label>
            <label>
              심볼
              <input
                value={cardForm.symbol}
                onChange={(event) =>
                  setCardForm((current) => ({ ...current, symbol: event.target.value }))
                }
              />
            </label>
            <label>
              표시 이름
              <input
                value={cardForm.displayName}
                onChange={(event) =>
                  setCardForm((current) => ({
                    ...current,
                    displayName: event.target.value
                  }))
                }
              />
            </label>
            <label>
              태그
              <input
                value={cardForm.tags}
                onChange={(event) =>
                  setCardForm((current) => ({ ...current, tags: event.target.value }))
                }
              />
            </label>
            <label className="inline-form__wide">
              메모
              <input
                value={cardForm.memo}
                onChange={(event) =>
                  setCardForm((current) => ({ ...current, memo: event.target.value }))
                }
              />
            </label>
            <button className="primary-button" type="submit">
              <Save size={16} />
              카드 저장
            </button>
          </form>
        ) : null}

        {activeCards.length === 0 ? (
          <section className="empty-watchlist-panel" aria-label="관심종목 목록">
            <div className="empty-watchlist-copy">
              <div className="signal-icon signal-icon--blue" aria-hidden="true">
                <ShieldCheck size={24} />
              </div>
              <h2>분석 카드가 없습니다</h2>
              <p>다음 단계에서 심볼 입력과 로컬 카드 저장을 연결합니다.</p>
            </div>
          </section>
        ) : (
          <section className="watch-card-grid" aria-label="관심종목 목록">
            {activeCards.map((card) => (
              <WatchStockCardView
                card={card}
                key={card.id}
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
  onArchive(): void;
  onDelete(): void;
  onHide(): void;
}

function WatchStockCardView({
  card,
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
        <span className="watch-card__status">분석 대기</span>
      </header>
      {card.memo.trim() !== "" ? <p className="watch-card__memo">{card.memo}</p> : null}
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
