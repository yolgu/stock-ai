import type { WatchStockCardDto } from "../domain/watchlist/Watchlist";
import type {
  MarketStateFormulaSnapshotPayload,
  MarketStateHistoryPayload,
  MarketStateSignalId,
  MarketStateSignalStatus,
  MarketStateTracePayload,
  MarketDataSnapshotPayload,
  QuantIndicatorExplanationTracePayload,
  QuantIndicatorDecisionStatus,
  QuantIndicatorSeverity,
  QuantIndicatorSignalKey,
  QuantIndicatorSignalPayload,
  QuantIndicatorSnapshotPayload
} from "../shared/contracts/app-runtime-contract";
import type { QuantIndicatorLoadStatus } from "./useQuantIndicators";

export type CardStatusFilterValue = "all" | QuantIndicatorDecisionStatus;

export interface CardStatusFilterOption {
  value: CardStatusFilterValue;
  label: string;
}

export interface WatchGroupTabViewModel {
  value: string;
  label: string;
}

export interface WatchlistFilterState {
  groupId: string;
  status: CardStatusFilterValue;
}

export interface WatchStockCardViewModel {
  card: WatchStockCardDto;
  marketContext: MarketContextViewModel;
  marketDataStatusLabel: string;
  marketDataStatusClassName: string;
  quantDecisionLabel: string;
  quantDecisionClassName: string;
  quantUpdatedAtLabel: string;
  nextCheckLabel: string | null;
  signalChips: QuantSignalChipViewModel[];
  marketState: MarketStateViewModel;
}

export interface MarketContextViewModel {
  currentPriceLabel: string | null;
  absoluteChangeLabel: string | null;
  simpleReturnLabel: string | null;
  updatedAtLabel: string;
  tone: "positive" | "neutral" | "danger" | "waiting";
}

export interface QuantSignalChipViewModel {
  key: QuantIndicatorSignalKey;
  label: string;
  displayLabel: string;
  severity: QuantIndicatorSeverity;
}

export interface QuantChecklistRowViewModel {
  key: QuantIndicatorSignalKey;
  label: string;
  statusLabel: string;
  displayStatusLabel: string;
  severity: QuantIndicatorSeverity;
  reason: string | null;
}

export interface BeginnerExplanationSectionViewModel {
  key: QuantIndicatorSignalKey;
  title: string;
  source: string;
  meaning: string;
  usage: string;
  originalFormula: string[];
  substitutedFormula: string[];
  result: string[];
  judgment: string;
  caution: string;
  limitation: string | null;
  inputs: QuantIndicatorExplanationTracePayload["inputs"];
}

export interface ConditionalZoneViewModel {
  key: "watch" | "entry" | "invalidated";
  title: string;
  description: string;
  tone: "blue" | "green" | "red";
  active: boolean;
}

export interface DataQualityViewModel {
  marketLabel: string;
  quantLabel: string;
  tone: "ready" | "warning" | "danger" | "waiting";
}

export interface DetailPanelViewModel {
  title: string;
  subtitle: string;
  marketContext: MarketContextViewModel;
  memo: string;
  tagsText: string;
  groupText: string;
  checklistRows: QuantChecklistRowViewModel[];
  conditionalZones: ConditionalZoneViewModel[];
  dataQuality: DataQualityViewModel;
  explanationSections: BeginnerExplanationSectionViewModel[];
  aiInsightLabel: string;
  quantUpdatedAtLabel: string;
  marketState: MarketStateDetailViewModel;
}

export interface MarketStateSignalCellViewModel {
  signalId: MarketStateSignalId;
  displayName: string;
  status: MarketStateSignalStatus;
  statusLabel: string;
  percentileLabel: string;
  lastDetectionLabel: string | null;
}

export interface MarketStateViewModel {
  asOfLabel: string;
  observedStateLabel: string;
  signals: MarketStateSignalCellViewModel[];
}

export interface MarketStateDetailViewModel extends MarketStateViewModel {
  selectedSignalId: MarketStateSignalId;
  selectedSignal: MarketStateSignalCellViewModel;
  trace: MarketStateTracePayload | null;
  history: MarketStateHistoryPayload | null;
}

export const CARD_STATUS_FILTER_OPTIONS: CardStatusFilterOption[] = [
  { value: "all", label: "전체" },
  { value: "watch", label: "관망" },
  { value: "confirmationWaiting", label: "확인 대기" },
  { value: "riskHigh", label: "리스크 높음" },
  { value: "invalidated", label: "무효화" },
  { value: "dataInsufficient", label: "데이터 부족" }
];

const indicatorLabels: Record<QuantIndicatorSignalKey, string> = {
  basicReturn: "기본 수익률",
  vwap: "VWAP",
  cvd: "CVD",
  spread: "스프레드",
  velocityAcceleration: "속도/가속도",
  distanceProfile: "이격도",
  rsiMomentum: "RSI/모멘텀",
  atrStop: "ATR/손절 폭",
  supplyPressure: "매물대",
  profitTakingPressure: "차익실현 리스크",
  riskReward: "손익비",
  marketSentimentScore: "장중 정량 심리 점수",
  intradayTradeScore: "종합 데이트레이딩 점수"
};

const indicatorOrder: QuantIndicatorSignalKey[] = [
  "basicReturn",
  "vwap",
  "cvd",
  "spread",
  "velocityAcceleration",
  "distanceProfile",
  "rsiMomentum",
  "atrStop",
  "riskReward",
  "marketSentimentScore",
  "intradayTradeScore"
];

export function createWatchStockCardViewModel(input: {
  card: WatchStockCardDto;
  marketDataSnapshot: MarketDataSnapshotPayload | null;
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null;
  quantIndicatorStatus: QuantIndicatorLoadStatus;
  marketStateSnapshot?: MarketStateFormulaSnapshotPayload | null;
}): WatchStockCardViewModel {
  return {
    card: input.card,
    marketContext: createMarketContext(
      input.marketDataSnapshot,
      input.quantIndicatorSnapshot
    ),
    marketDataStatusLabel: formatMarketDataStatus(input.marketDataSnapshot),
    marketDataStatusClassName: formatMarketDataStatusClassName(input.marketDataSnapshot),
    quantDecisionLabel: formatQuantDecisionLabel(
      input.quantIndicatorSnapshot,
      input.quantIndicatorStatus
    ),
    quantDecisionClassName: formatQuantDecisionClassName(input.quantIndicatorSnapshot),
    quantUpdatedAtLabel: formatQuantUpdatedAt(
      input.quantIndicatorSnapshot,
      input.quantIndicatorStatus
    ),
    nextCheckLabel: input.quantIndicatorSnapshot?.nextCheckLabel ?? null,
    signalChips:
      input.quantIndicatorSnapshot?.signals
        .filter(
          (signal: QuantIndicatorSignalPayload): boolean =>
            signal.key !== "profitTakingPressure"
        )
        .slice(0, 3)
        .map(
          (
            signal: QuantIndicatorSignalPayload
          ): QuantSignalChipViewModel => {
            const finalValue: string | null =
              formatIndicatorFinalValue(
                input.quantIndicatorSnapshot,
                signal.key
              );

            return {
              key: signal.key,
              label: signal.label,
              displayLabel: appendFinalValue(signal.label, finalValue),
              severity: signal.severity
            };
          }
        ) ?? [],
    marketState: createMarketStateViewModel(
      input.marketStateSnapshot ?? null
    )
  };
}

export function createDetailPanelViewModel(input: {
  card: WatchStockCardDto;
  marketDataSnapshot: MarketDataSnapshotPayload | null;
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null;
  quantIndicatorStatus: QuantIndicatorLoadStatus;
  marketStateSnapshot?: MarketStateFormulaSnapshotPayload | null;
  selectedMarketStateSignalId?: MarketStateSignalId;
  marketStateTrace?: MarketStateTracePayload | null;
  marketStateHistory?: MarketStateHistoryPayload | null;
}): DetailPanelViewModel {
  return {
    title: input.card.displayName,
    subtitle: `${input.card.market} · ${input.card.symbol}`,
    marketContext: createMarketContext(
      input.marketDataSnapshot,
      input.quantIndicatorSnapshot
    ),
    memo: input.card.memo,
    tagsText: input.card.tags.join(", "),
    groupText: input.card.groupId ?? "",
    checklistRows: createChecklistRows(input.quantIndicatorSnapshot),
    conditionalZones: createConditionalZones(input.quantIndicatorSnapshot),
    dataQuality: createDataQuality(input.marketDataSnapshot, input.quantIndicatorSnapshot),
    explanationSections: createExplanationSections(input.quantIndicatorSnapshot),
    aiInsightLabel: "AI 분석 대기",
    quantUpdatedAtLabel: formatQuantUpdatedAt(
      input.quantIndicatorSnapshot,
      input.quantIndicatorStatus
    ),
    marketState: createMarketStateDetailViewModel({
      snapshot: input.marketStateSnapshot ?? null,
      selectedSignalId:
        input.selectedMarketStateSignalId ?? "FOMO_LIKE",
      trace: input.marketStateTrace ?? null,
      history: input.marketStateHistory ?? null
    })
  };
}

const marketStateSignalOrder: readonly MarketStateSignalId[] = [
  "FOMO_LIKE",
  "PANIC_LIKE",
  "PROFIT_TAKING_PROXY",
  "PERSISTENT_RECOVERY",
  "EFFICIENT_UPTREND"
];

const marketStateSignalLabels: Record<MarketStateSignalId, string> = {
  FOMO_LIKE: "FOMO",
  PANIC_LIKE: "패닉",
  PROFIT_TAKING_PROXY: "차익실현",
  PERSISTENT_RECOVERY: "회복",
  EFFICIENT_UPTREND: "상승세"
};

export function createMarketStateViewModel(
  snapshot: MarketStateFormulaSnapshotPayload | null
): MarketStateViewModel {
  const signalsById: Map<
    MarketStateSignalId,
    MarketStateFormulaSnapshotPayload["signals"][number]
  > = new Map(
    snapshot?.signals.map(
      (
        signal: MarketStateFormulaSnapshotPayload["signals"][number]
      ): [
        MarketStateSignalId,
        MarketStateFormulaSnapshotPayload["signals"][number]
      ] => [signal.signalId, signal]
    ) ?? []
  );

  return {
    asOfLabel:
      snapshot === null || snapshot.sessionDate === ""
        ? "5분봉 판정 대기"
        : `${formatSnapshotTime(snapshot.asOf).slice(0, 5)} 확정`,
    observedStateLabel:
      snapshot?.observedStateLabel ?? "데이터 부족",
    signals: marketStateSignalOrder.map(
      (signalId: MarketStateSignalId): MarketStateSignalCellViewModel => {
        const signal = signalsById.get(signalId);

        return {
          signalId,
          displayName:
            signal?.displayName ?? marketStateSignalLabels[signalId],
          status: signal?.status ?? "collecting",
          statusLabel: formatMarketStateStatus(
            signal?.status ?? "collecting"
          ),
          percentileLabel:
            signal?.percentile === null ||
            signal?.percentile === undefined
              ? "—"
              : signal.percentile.toFixed(1),
          lastDetectionLabel: formatLastDetection(
            signal?.currentDetectionStartedAt ?? null,
            signal?.lastDetectedAt ?? null
          )
        };
      }
    )
  };
}

function createMarketStateDetailViewModel(input: {
  snapshot: MarketStateFormulaSnapshotPayload | null;
  selectedSignalId: MarketStateSignalId;
  trace: MarketStateTracePayload | null;
  history: MarketStateHistoryPayload | null;
}): MarketStateDetailViewModel {
  const summary: MarketStateViewModel = createMarketStateViewModel(
    input.snapshot
  );
  const selectedSignal: MarketStateSignalCellViewModel =
    summary.signals.find(
      (signal: MarketStateSignalCellViewModel): boolean =>
        signal.signalId === input.selectedSignalId
    ) ?? summary.signals[0];

  return {
    ...summary,
    selectedSignalId: input.selectedSignalId,
    selectedSignal,
    trace:
      input.trace?.signalId === input.selectedSignalId
        ? input.trace
        : null,
    history:
      input.history?.signalId === input.selectedSignalId
        ? input.history
        : null
  };
}

function formatMarketStateStatus(
  status: MarketStateSignalStatus
): string {
  switch (status) {
    case "detected":
      return "감지";
    case "notDetected":
      return "미감지";
    case "notApplicable":
      return "대상 아님";
    case "collecting":
      return "수집 중";
    case "unavailable":
      return "계산 불가";
  }
}

function formatLastDetection(
  currentDetectionStartedAt: string | null,
  lastDetectedAt: string | null
): string | null {
  if (currentDetectionStartedAt !== null) {
    return `${formatSnapshotTime(currentDetectionStartedAt).slice(0, 5)}부터 감지`;
  }

  if (lastDetectedAt !== null) {
    return `최근 감지 ${formatSnapshotTime(lastDetectedAt).slice(0, 5)}`;
  }

  return null;
}

function createMarketContext(
  marketDataSnapshot: MarketDataSnapshotPayload | null,
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null
): MarketContextViewModel {
  const basicReturn = quantIndicatorSnapshot?.indicators.basicReturn ?? null;

  if (basicReturn?.status === "available") {
    return {
      currentPriceLabel: formatCurrencyValue(basicReturn.currentPrice, basicReturn.currency),
      absoluteChangeLabel: formatSignedCurrencyValue(
        basicReturn.absoluteChange,
        basicReturn.currency
      ),
      simpleReturnLabel: formatSignedPercent(basicReturn.simpleReturnPercent),
      updatedAtLabel: formatMarketContextUpdatedAt(marketDataSnapshot),
      tone: formatMarketContextTone(basicReturn.severity)
    };
  }

  const price = marketDataSnapshot?.observations.price ?? null;

  if (price !== null) {
    return {
      currentPriceLabel: formatCurrencyValue(price.lastPrice, price.currency),
      absoluteChangeLabel: null,
      simpleReturnLabel: null,
      updatedAtLabel: formatMarketContextUpdatedAt(marketDataSnapshot),
      tone: "neutral"
    };
  }

  return {
    currentPriceLabel: null,
    absoluteChangeLabel: null,
    simpleReturnLabel: null,
    updatedAtLabel: "시장 데이터 대기",
    tone: "waiting"
  };
}

export function createWatchGroupTabs(cards: WatchStockCardDto[]): WatchGroupTabViewModel[] {
  const groupIds = new Set(cards.map((card) => card.groupId ?? "ungrouped"));

  return [
    { value: "all", label: "전체" },
    ...[...groupIds].map((groupId) => ({
      value: groupId,
      label: groupId === "ungrouped" ? "미분류" : groupId
    }))
  ];
}

export function filterWatchCards(input: {
  cards: WatchStockCardDto[];
  snapshotsByCardId: Record<string, QuantIndicatorSnapshotPayload>;
  filter: WatchlistFilterState;
}): WatchStockCardDto[] {
  return input.cards.filter((card) => {
    const cardGroupId = card.groupId ?? "ungrouped";
    const groupMatched = input.filter.groupId === "all" || input.filter.groupId === cardGroupId;
    const snapshot = input.snapshotsByCardId[card.id] ?? null;
    const statusMatched =
      input.filter.status === "all" || snapshot?.decisionStatus === input.filter.status;

    return groupMatched && statusMatched;
  });
}

export function splitTags(tags: string): string[] {
  return tags
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag !== "");
}

export function formatSnapshotTime(capturedAt: string): string {
  const match = capturedAt.match(/T(\d{2}:\d{2}:\d{2})/);

  return match?.[1] ?? "--:--:--";
}

function createChecklistRows(
  snapshot: QuantIndicatorSnapshotPayload | null
): QuantChecklistRowViewModel[] {
  if (snapshot === null) {
    return indicatorOrder.map((key) => ({
      key,
      label: indicatorLabels[key],
      statusLabel: "지표 대기",
      displayStatusLabel: "지표 대기",
      severity: "unavailable",
      reason: "시장 데이터 수집 후 계산됩니다."
    }));
  }

  return indicatorOrder.map((key) => {
    const indicator = snapshot.indicators[key];

    return {
      key,
      label: indicatorLabels[key],
      statusLabel: indicator.label,
      displayStatusLabel: appendFinalValue(
        indicator.label,
        formatIndicatorFinalValue(snapshot, key)
      ),
      severity: indicator.severity,
      reason: indicator.unavailableReason
    };
  });
}

function appendFinalValue(label: string, finalValue: string | null): string {
  return finalValue === null ? label : `${label} (${finalValue})`;
}

function formatIndicatorFinalValue(
  snapshot: QuantIndicatorSnapshotPayload | null,
  key: QuantIndicatorSignalKey
): string | null {
  if (snapshot === null) {
    return null;
  }

  const indicator = snapshot.indicators[key];
  const currency = snapshot.indicators.basicReturn.currency;

  if (indicator.status === "unavailable") {
    return null;
  }

  switch (key) {
    case "basicReturn":
      return formatSignedPercent(snapshot.indicators.basicReturn.simpleReturnPercent);
    case "vwap":
      return formatCurrencyValue(snapshot.indicators.vwap.value, currency);
    case "cvd":
      return snapshot.indicators.cvd.value;
    case "spread":
      return formatBasisPoints(snapshot.indicators.spread.spreadBps);
    case "velocityAcceleration":
      return formatSignedPercent(
        snapshot.indicators.velocityAcceleration.latestLogReturnPercent
      );
    case "distanceProfile":
      return formatBasisPoints(snapshot.indicators.distanceProfile.vwapDistanceBps);
    case "rsiMomentum":
      return formatFixedNumber(snapshot.indicators.rsiMomentum.rsi, 2);
    case "atrStop":
      return formatPercent(snapshot.indicators.atrStop.stopDistancePercent);
    case "supplyPressure":
      return formatFixedNumber(snapshot.indicators.supplyPressure.overheadRatio, 2);
    case "profitTakingPressure":
      return formatScore(snapshot.indicators.profitTakingPressure.score);
    case "riskReward":
      return formatRiskReward(snapshot.indicators.riskReward.ratio);
    case "marketSentimentScore":
      return formatScore(snapshot.indicators.marketSentimentScore.score);
    case "intradayTradeScore":
      return formatPercent(snapshot.indicators.intradayTradeScore.conditionStrengthPercent);
  }
}

function createExplanationSections(
  snapshot: QuantIndicatorSnapshotPayload | null
): BeginnerExplanationSectionViewModel[] {
  return (
    snapshot?.explanationTraces
      .filter(
        (trace: QuantIndicatorExplanationTracePayload): boolean =>
          trace.key !== "profitTakingPressure"
      )
      .map(
        (
          trace: QuantIndicatorExplanationTracePayload
        ): BeginnerExplanationSectionViewModel => ({
          key: trace.key,
          title: trace.title,
          source: trace.source,
          meaning: trace.meaning,
          usage: trace.usage,
          originalFormula: trace.originalFormula,
          substitutedFormula: trace.substitutedFormula,
          result: trace.result,
          judgment: trace.judgment,
          caution: trace.caution,
          limitation: trace.limitation,
          inputs: trace.inputs
        })
      ) ?? []
  );
}

function createConditionalZones(
  snapshot: QuantIndicatorSnapshotPayload | null
): ConditionalZoneViewModel[] {
  const nextCheck = snapshot?.nextCheckLabel ?? "시장 데이터 수집 후 조건을 확인합니다.";

  return [
    {
      key: "watch",
      title: "관망",
      description: snapshot?.decisionStatus === "watch" ? nextCheck : "조건이 충족될 때까지 대기",
      tone: "blue",
      active: snapshot?.decisionStatus === "watch"
    },
    {
      key: "entry",
      title: "확인 후 진입",
      description:
        snapshot?.decisionStatus === "confirmationWaiting"
          ? nextCheck
          : "VWAP, 체결 압력, 스프레드가 동시에 개선될 때만 고려",
      tone: "green",
      active: snapshot?.decisionStatus === "confirmationWaiting"
    },
    {
      key: "invalidated",
      title: "무효화",
      description:
        snapshot?.decisionStatus === "invalidated"
          ? nextCheck
          : "직전 저점 이탈, CVD 악화, 변동성 확대 시 우선 회피",
      tone: "red",
      active: snapshot?.decisionStatus === "invalidated" || snapshot?.decisionStatus === "riskHigh"
    }
  ];
}

function createDataQuality(
  marketDataSnapshot: MarketDataSnapshotPayload | null,
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null
): DataQualityViewModel {
  if (marketDataSnapshot === null && quantIndicatorSnapshot === null) {
    return {
      marketLabel: "시장 데이터 대기",
      quantLabel: "정량 지표 대기",
      tone: "waiting"
    };
  }

  const marketLabel =
    marketDataSnapshot === null
      ? "시장 데이터 대기"
      : `${formatMarketDataQuality(marketDataSnapshot.quality)} · ${formatMarketFreshness(
          marketDataSnapshot.freshness
        )}`;
  const quantLabel =
    quantIndicatorSnapshot === null
      ? "정량 지표 대기"
      : formatQuantQuality(quantIndicatorSnapshot.quality);

  return {
    marketLabel,
    quantLabel,
    tone: resolveDataQualityTone(marketDataSnapshot, quantIndicatorSnapshot)
  };
}

function resolveDataQualityTone(
  marketDataSnapshot: MarketDataSnapshotPayload | null,
  quantIndicatorSnapshot: QuantIndicatorSnapshotPayload | null
): DataQualityViewModel["tone"] {
  if (
    marketDataSnapshot?.quality === "unavailable" ||
    marketDataSnapshot?.quality === "degraded" ||
    quantIndicatorSnapshot?.quality === "unavailable"
  ) {
    return "danger";
  }

  if (
    marketDataSnapshot?.quality === "partial" ||
    marketDataSnapshot?.freshness === "stale" ||
    quantIndicatorSnapshot?.quality === "partial"
  ) {
    return "warning";
  }

  if (marketDataSnapshot === null || quantIndicatorSnapshot === null) {
    return "waiting";
  }

  return "ready";
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

function formatMarketContextUpdatedAt(snapshot: MarketDataSnapshotPayload | null): string {
  if (snapshot === null) {
    return "시장 데이터 대기";
  }

  const priceTimestamp = snapshot.observations.price?.timestamp ?? snapshot.capturedAt;

  return `시장 데이터 ${formatSnapshotTime(priceTimestamp)}`;
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

function formatQuantDecisionLabel(
  snapshot: QuantIndicatorSnapshotPayload | null,
  quantIndicatorStatus: QuantIndicatorLoadStatus
): string {
  if (snapshot !== null) {
    return snapshot.decisionLabel;
  }

  if (quantIndicatorStatus === "emptyLoading") {
    return "계산 중";
  }

  if (quantIndicatorStatus === "error") {
    return "계산 실패";
  }

  return "지표 대기";
}

function formatQuantUpdatedAt(
  snapshot: QuantIndicatorSnapshotPayload | null,
  quantIndicatorStatus: QuantIndicatorLoadStatus
): string {
  if (snapshot === null) {
    if (quantIndicatorStatus === "emptyLoading") {
      return "차익실현 리스크 계산 중";
    }

    if (quantIndicatorStatus === "error") {
      return "지표 계산 실패";
    }

    return "지표 업데이트 대기";
  }

  if (quantIndicatorStatus === "refreshing") {
    return `업데이트 중 · ${formatSnapshotTime(snapshot.calculatedAt)} 기준`;
  }

  if (quantIndicatorStatus === "failedRefresh") {
    return `최근값 유지 중 · ${formatSnapshotTime(snapshot.calculatedAt)} 기준`;
  }

  return `지표 업데이트 ${formatSnapshotTime(snapshot.calculatedAt)}`;
}

function formatQuantDecisionClassName(snapshot: QuantIndicatorSnapshotPayload | null): string {
  if (snapshot === null) {
    return "quant-decision quant-decision--waiting";
  }

  const classNames: Record<QuantIndicatorDecisionStatus, string> = {
    watch: "quant-decision quant-decision--watch",
    confirmationWaiting: "quant-decision quant-decision--waiting",
    riskHigh: "quant-decision quant-decision--risk",
    invalidated: "quant-decision quant-decision--invalidated",
    dataInsufficient: "quant-decision quant-decision--insufficient"
  };

  return classNames[snapshot.decisionStatus];
}

function formatMarketDataQuality(quality: MarketDataSnapshotPayload["quality"]): string {
  const labels: Record<MarketDataSnapshotPayload["quality"], string> = {
    complete: "수집 완료",
    partial: "부분 수집",
    degraded: "수집 저하",
    unavailable: "수집 불가"
  };

  return labels[quality];
}

function formatMarketFreshness(freshness: MarketDataSnapshotPayload["freshness"]): string {
  const labels: Record<MarketDataSnapshotPayload["freshness"], string> = {
    fresh: "최신",
    stale: "오래됨",
    missing: "없음"
  };

  return labels[freshness];
}

function formatQuantQuality(quality: QuantIndicatorSnapshotPayload["quality"]): string {
  const labels: Record<QuantIndicatorSnapshotPayload["quality"], string> = {
    complete: "정량 지표 완료",
    partial: "정량 지표 부분",
    unavailable: "정량 지표 불가"
  };

  return labels[quality];
}

function formatMarketContextTone(
  severity: QuantIndicatorSeverity
): MarketContextViewModel["tone"] {
  if (severity === "positive") {
    return "positive";
  }

  if (severity === "danger") {
    return "danger";
  }

  if (severity === "neutral") {
    return "neutral";
  }

  return "waiting";
}

function formatCurrencyValue(value: string | null, currency: string): string | null {
  const decimal = readDecimal(value);

  if (decimal === null) {
    return null;
  }

  if (currency === "USD") {
    return `$${decimal.toFixed(2)}`;
  }

  if (currency === "KRW") {
    return `${Math.round(decimal).toLocaleString("ko-KR")}원`;
  }

  return `${currency} ${decimal.toFixed(2)}`.trim();
}

function formatSignedCurrencyValue(value: string | null, currency: string): string | null {
  const decimal = readDecimal(value);

  if (decimal === null) {
    return null;
  }

  const absoluteValue = Math.abs(decimal).toFixed(2);
  const sign = decimal > 0 ? "+" : decimal < 0 ? "-" : "";

  if (currency === "USD") {
    return `${sign}$${absoluteValue}`;
  }

  if (currency === "KRW") {
    return `${sign}${Math.round(Math.abs(decimal)).toLocaleString("ko-KR")}원`;
  }

  return `${sign}${currency} ${absoluteValue}`.trim();
}

function formatSignedPercent(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  const sign = value > 0 ? "+" : "";

  return `${sign}${value.toFixed(2)}%`;
}

function formatPercent(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  return `${value.toFixed(2)}%`;
}

function formatBasisPoints(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  return `${value}bp`;
}

function formatFixedNumber(value: number | null, fractionDigits: number): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  return value.toFixed(fractionDigits);
}

function formatRiskReward(value: number | null): string | null {
  const fixedValue = formatFixedNumber(value, 2);

  return fixedValue === null ? null : `${fixedValue}x`;
}

function formatScore(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }

  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}점`;
}

function readDecimal(value: string | null): number | null {
  const decimal = Number(value);

  return Number.isFinite(decimal) ? decimal : null;
}
