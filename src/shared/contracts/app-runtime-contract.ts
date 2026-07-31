import contractSpec from "../../../contracts/app-runtime-contract.json";
import type { RuntimeProfileDto } from "../../domain/runtime/AppRuntimeProfile";

export type RuntimeProfileRequestEvent = "app:runtime-profile:request";
export type RuntimeProfileResponseEvent = "app:runtime-profile:response";
export type AppErrorEvent = "app:error";
export type WatchlistListRequestEvent = "watchlist:list:request";
export type WatchlistListResponseEvent = "watchlist:list:response";
export type WatchlistCreateRequestEvent = "watchlist:create:request";
export type WatchlistCreateResponseEvent = "watchlist:create:response";
export type WatchlistUpdateRequestEvent = "watchlist:update:request";
export type WatchlistUpdateResponseEvent = "watchlist:update:response";
export type WatchlistHideRequestEvent = "watchlist:hide:request";
export type WatchlistHideResponseEvent = "watchlist:hide:response";
export type WatchlistArchiveRequestEvent = "watchlist:archive:request";
export type WatchlistArchiveResponseEvent = "watchlist:archive:response";
export type WatchlistRestoreRequestEvent = "watchlist:restore:request";
export type WatchlistRestoreResponseEvent = "watchlist:restore:response";
export type WatchlistDeleteRequestEvent = "watchlist:delete:request";
export type WatchlistDeleteResponseEvent = "watchlist:delete:response";
export type WatchlistReorderRequestEvent = "watchlist:reorder:request";
export type WatchlistReorderResponseEvent = "watchlist:reorder:response";
export type StockReferenceVerifyRequestEvent = "stock-reference:verify:request";
export type StockReferenceVerifyResponseEvent = "stock-reference:verify:response";
export type WatchlistCreateVerifiedRequestEvent = "watchlist:create-verified:request";
export type WatchlistCreateVerifiedResponseEvent = "watchlist:create-verified:response";
export type MarketDataRefreshWatchlistRequestEvent =
  "market-data:refresh-watchlist:request";
export type MarketDataRefreshWatchlistResponseEvent =
  "market-data:refresh-watchlist:response";
export type MarketDataRefreshCardRequestEvent = "market-data:refresh-card:request";
export type MarketDataRefreshCardResponseEvent = "market-data:refresh-card:response";
export type MarketDataLatestSnapshotsRequestEvent =
  "market-data:latest-snapshots:request";
export type MarketDataLatestSnapshotsResponseEvent =
  "market-data:latest-snapshots:response";
export type QuantIndicatorsRefreshWatchlistRequestEvent =
  "quant-indicators:refresh-watchlist:request";
export type QuantIndicatorsRefreshWatchlistResponseEvent =
  "quant-indicators:refresh-watchlist:response";
export type QuantIndicatorsRefreshCardRequestEvent =
  "quant-indicators:refresh-card:request";
export type QuantIndicatorsRefreshCardResponseEvent =
  "quant-indicators:refresh-card:response";
export type QuantIndicatorsLatestSnapshotsRequestEvent =
  "quant-indicators:latest-snapshots:request";
export type QuantIndicatorsLatestSnapshotsResponseEvent =
  "quant-indicators:latest-snapshots:response";
export type MarketStateRefreshWatchlistRequestEvent =
  "market-state:refresh-watchlist:request";
export type MarketStateRefreshWatchlistResponseEvent =
  "market-state:refresh-watchlist:response";
export type MarketStateLatestSnapshotsRequestEvent =
  "market-state:latest-snapshots:request";
export type MarketStateLatestSnapshotsResponseEvent =
  "market-state:latest-snapshots:response";
export type MarketStateTraceRequestEvent = "market-state:trace:request";
export type MarketStateTraceResponseEvent = "market-state:trace:response";
export type MarketStateHistoryRequestEvent = "market-state:history:request";
export type MarketStateHistoryResponseEvent = "market-state:history:response";
export type TossCredentialsReadStatusRequestEvent =
  "settings:toss-credentials:read-status";
export type TossCredentialsReadStatusResponseEvent =
  "settings:toss-credentials:read-status:response";
export type TossCredentialsSaveRequestEvent = "settings:toss-credentials:save";
export type TossCredentialsSaveResponseEvent = "settings:toss-credentials:save:response";
export type TossCredentialsDeleteRequestEvent = "settings:toss-credentials:delete";
export type TossCredentialsDeleteResponseEvent =
  "settings:toss-credentials:delete:response";
export type TossConnectionTestRequestEvent = "settings:toss-connection:test";
export type TossConnectionTestResponseEvent = "settings:toss-connection:test:response";

export type AppRequestEvent =
  | RuntimeProfileRequestEvent
  | WatchlistListRequestEvent
  | WatchlistCreateRequestEvent
  | WatchlistUpdateRequestEvent
  | WatchlistHideRequestEvent
  | WatchlistArchiveRequestEvent
  | WatchlistRestoreRequestEvent
  | WatchlistDeleteRequestEvent
  | WatchlistReorderRequestEvent
  | StockReferenceVerifyRequestEvent
  | WatchlistCreateVerifiedRequestEvent
  | MarketDataRefreshWatchlistRequestEvent
  | MarketDataRefreshCardRequestEvent
  | MarketDataLatestSnapshotsRequestEvent
  | QuantIndicatorsRefreshWatchlistRequestEvent
  | QuantIndicatorsRefreshCardRequestEvent
  | QuantIndicatorsLatestSnapshotsRequestEvent
  | MarketStateRefreshWatchlistRequestEvent
  | MarketStateLatestSnapshotsRequestEvent
  | MarketStateTraceRequestEvent
  | MarketStateHistoryRequestEvent
  | TossCredentialsReadStatusRequestEvent
  | TossCredentialsSaveRequestEvent
  | TossCredentialsDeleteRequestEvent
  | TossConnectionTestRequestEvent;

export type AppResponseEvent =
  | RuntimeProfileResponseEvent
  | WatchlistListResponseEvent
  | WatchlistCreateResponseEvent
  | WatchlistUpdateResponseEvent
  | WatchlistHideResponseEvent
  | WatchlistArchiveResponseEvent
  | WatchlistRestoreResponseEvent
  | WatchlistDeleteResponseEvent
  | WatchlistReorderResponseEvent
  | StockReferenceVerifyResponseEvent
  | WatchlistCreateVerifiedResponseEvent
  | MarketDataRefreshWatchlistResponseEvent
  | MarketDataRefreshCardResponseEvent
  | MarketDataLatestSnapshotsResponseEvent
  | QuantIndicatorsRefreshWatchlistResponseEvent
  | QuantIndicatorsRefreshCardResponseEvent
  | QuantIndicatorsLatestSnapshotsResponseEvent
  | MarketStateRefreshWatchlistResponseEvent
  | MarketStateLatestSnapshotsResponseEvent
  | MarketStateTraceResponseEvent
  | MarketStateHistoryResponseEvent
  | TossCredentialsReadStatusResponseEvent
  | TossCredentialsSaveResponseEvent
  | TossCredentialsDeleteResponseEvent
  | TossConnectionTestResponseEvent;

export type AppEvent = AppRequestEvent | AppResponseEvent | AppErrorEvent;

export type AppRuntimeErrorCode =
  | "invalid_request"
  | "runtime_profile_unavailable"
  | "extension_unavailable"
  | "storage_corrupted"
  | "watch_card_not_found"
  | "duplicate_card"
  | "restore_available"
  | "invalid_toss_credentials"
  | "toss_connection_failed"
  | "stock_not_found"
  | "stock_verification_required"
  | "stock_confirmation_required"
  | "stock_reference_unavailable"
  | "toss_rate_limited"
  | "market_data_unavailable"
  | "market_data_rate_limited"
  | "market_data_snapshot_not_found"
  | "market_calendar_unavailable"
  | "quant_indicator_unavailable"
  | "quant_indicator_snapshot_not_found"
  | "quant_indicator_calculation_failed"
  | "market_state_unavailable"
  | "market_state_snapshot_not_found"
  | "market_state_calculation_failed";

export interface AppRuntimeContract {
  extensionId: "app.stockSub.runtime";
  events: {
    runtimeProfileRequest: RuntimeProfileRequestEvent;
    runtimeProfileResponse: RuntimeProfileResponseEvent;
    appError: AppErrorEvent;
    watchlistListRequest: WatchlistListRequestEvent;
    watchlistListResponse: WatchlistListResponseEvent;
    watchlistCreateRequest: WatchlistCreateRequestEvent;
    watchlistCreateResponse: WatchlistCreateResponseEvent;
    watchlistUpdateRequest: WatchlistUpdateRequestEvent;
    watchlistUpdateResponse: WatchlistUpdateResponseEvent;
    watchlistHideRequest: WatchlistHideRequestEvent;
    watchlistHideResponse: WatchlistHideResponseEvent;
    watchlistArchiveRequest: WatchlistArchiveRequestEvent;
    watchlistArchiveResponse: WatchlistArchiveResponseEvent;
    watchlistRestoreRequest: WatchlistRestoreRequestEvent;
    watchlistRestoreResponse: WatchlistRestoreResponseEvent;
    watchlistDeleteRequest: WatchlistDeleteRequestEvent;
    watchlistDeleteResponse: WatchlistDeleteResponseEvent;
    watchlistReorderRequest: WatchlistReorderRequestEvent;
    watchlistReorderResponse: WatchlistReorderResponseEvent;
    stockReferenceVerifyRequest: StockReferenceVerifyRequestEvent;
    stockReferenceVerifyResponse: StockReferenceVerifyResponseEvent;
    watchlistCreateVerifiedRequest: WatchlistCreateVerifiedRequestEvent;
    watchlistCreateVerifiedResponse: WatchlistCreateVerifiedResponseEvent;
    marketDataRefreshWatchlistRequest: MarketDataRefreshWatchlistRequestEvent;
    marketDataRefreshWatchlistResponse: MarketDataRefreshWatchlistResponseEvent;
    marketDataRefreshCardRequest: MarketDataRefreshCardRequestEvent;
    marketDataRefreshCardResponse: MarketDataRefreshCardResponseEvent;
    marketDataLatestSnapshotsRequest: MarketDataLatestSnapshotsRequestEvent;
    marketDataLatestSnapshotsResponse: MarketDataLatestSnapshotsResponseEvent;
    quantIndicatorsRefreshWatchlistRequest: QuantIndicatorsRefreshWatchlistRequestEvent;
    quantIndicatorsRefreshWatchlistResponse: QuantIndicatorsRefreshWatchlistResponseEvent;
    quantIndicatorsRefreshCardRequest: QuantIndicatorsRefreshCardRequestEvent;
    quantIndicatorsRefreshCardResponse: QuantIndicatorsRefreshCardResponseEvent;
    quantIndicatorsLatestSnapshotsRequest: QuantIndicatorsLatestSnapshotsRequestEvent;
    quantIndicatorsLatestSnapshotsResponse: QuantIndicatorsLatestSnapshotsResponseEvent;
    marketStateRefreshWatchlistRequest: MarketStateRefreshWatchlistRequestEvent;
    marketStateRefreshWatchlistResponse: MarketStateRefreshWatchlistResponseEvent;
    marketStateLatestSnapshotsRequest: MarketStateLatestSnapshotsRequestEvent;
    marketStateLatestSnapshotsResponse: MarketStateLatestSnapshotsResponseEvent;
    marketStateTraceRequest: MarketStateTraceRequestEvent;
    marketStateTraceResponse: MarketStateTraceResponseEvent;
    marketStateHistoryRequest: MarketStateHistoryRequestEvent;
    marketStateHistoryResponse: MarketStateHistoryResponseEvent;
    tossCredentialsReadStatusRequest: TossCredentialsReadStatusRequestEvent;
    tossCredentialsReadStatusResponse: TossCredentialsReadStatusResponseEvent;
    tossCredentialsSaveRequest: TossCredentialsSaveRequestEvent;
    tossCredentialsSaveResponse: TossCredentialsSaveResponseEvent;
    tossCredentialsDeleteRequest: TossCredentialsDeleteRequestEvent;
    tossCredentialsDeleteResponse: TossCredentialsDeleteResponseEvent;
    tossConnectionTestRequest: TossConnectionTestRequestEvent;
    tossConnectionTestResponse: TossConnectionTestResponseEvent;
  };
  capabilities: readonly string[];
  errorCodes: readonly AppRuntimeErrorCode[];
}

export interface AppRequestEnvelope<
  EventName extends AppRequestEvent = AppRequestEvent,
  Payload = unknown
> {
  event: EventName;
  requestId: string;
  occurredAt: string;
  payload: Payload;
}

export interface AppResponseEnvelope<
  EventName extends AppResponseEvent = AppResponseEvent,
  Payload = unknown
> {
  event: EventName;
  requestId: string;
  occurredAt: string;
  payload: Payload;
}

export interface RuntimeProfileRequestEnvelope {
  event: RuntimeProfileRequestEvent;
  requestId: string;
  occurredAt: string;
  payload: Record<string, never>;
}

export interface RuntimeProfileResponseEnvelope {
  event: RuntimeProfileResponseEvent;
  requestId: string;
  occurredAt: string;
  payload: RuntimeProfileDto;
}

export interface AppErrorEnvelope {
  event: AppErrorEvent;
  requestId: string;
  occurredAt: string;
  error: {
    code: AppRuntimeErrorCode;
    message: string;
    recoverable: boolean;
  };
}

export type RuntimeProfileRequestParseResult =
  | {
      ok: true;
      request: RuntimeProfileRequestEnvelope;
    }
  | {
      ok: false;
      error: AppErrorEnvelope;
    };

export const APP_RUNTIME_CONTRACT = contractSpec as AppRuntimeContract;

export type TossConnectionStatus = "notConfigured" | "saved" | "valid" | "invalid" | "error";

export interface TossCredentialStatusPayload {
  configured: boolean;
  maskedClientId: string | null;
  lastValidatedAt: string | null;
  connectionStatus: TossConnectionStatus;
}

export interface StockReferenceVerifyRequestPayload {
  rawInput: string;
}

export type StockReferenceRejectedReason =
  | "stock_not_found"
  | "invalid_request"
  | "stock_reference_unavailable";

export interface VerifiedStockReferencePayload {
  symbol: string;
  market: string;
  displayName: string;
  englishName: string;
  currency: string;
  status: string;
  securityType: string;
  requiresConfirmation: boolean;
  confirmationReasons: string[];
  verifiedAt: string;
}

export interface RejectedStockReferencePayload {
  symbol: string;
  reason: StockReferenceRejectedReason;
  message: string;
}

export interface StockReferenceVerificationPayload {
  verified: VerifiedStockReferencePayload[];
  rejected: RejectedStockReferencePayload[];
}

export interface CreateVerifiedWatchCardPayload {
  symbol: string;
  confirmedRisk: boolean;
  groupId: string | null;
  tags: string[];
  memo: string;
}

export type MarketDataFreshness = "fresh" | "stale" | "missing";
export type MarketDataQuality = "complete" | "partial" | "degraded" | "unavailable";
export type MarketCountry = "KR" | "US";
export type MarketSessionState = "pre" | "regular" | "after" | "closed" | "holiday";

export interface MarketDataAdapterErrorPayload {
  endpoint: string;
  code: AppRuntimeErrorCode;
  message: string;
  recoverable: boolean;
}

export interface MarketPriceObservationPayload {
  symbol: string;
  timestamp: string | null;
  lastPrice: string;
  currency: string;
}

export interface MarketTradeObservationPayload {
  price: string;
  volume: string;
  timestamp: string;
  currency: string;
}

export interface MarketOrderbookEntryPayload {
  price: string;
  volume: string;
}

export interface MarketOrderbookObservationPayload {
  timestamp: string | null;
  currency: string;
  asks: MarketOrderbookEntryPayload[];
  bids: MarketOrderbookEntryPayload[];
}

export interface MarketCandleObservationPayload {
  timestamp: string;
  openPrice: string;
  highPrice: string;
  lowPrice: string;
  closePrice: string;
  volume: string;
  currency: string;
}

export interface MarketCandlePageObservationPayload {
  interval: "1m" | "1d";
  candles: MarketCandleObservationPayload[];
  nextBefore: string | null;
}

export interface MarketExchangeRateObservationPayload {
  baseCurrency: string;
  quoteCurrency: string;
  rate: string;
  midRate: string;
  validFrom: string;
  validUntil: string;
}

export interface MarketSessionObservationPayload {
  country: MarketCountry;
  state: MarketSessionState;
  source: "calendar" | "fallback";
}

export interface MarketDataObservationsPayload {
  price: MarketPriceObservationPayload | null;
  trades: MarketTradeObservationPayload[];
  orderbook: MarketOrderbookObservationPayload | null;
  intradayCandles: MarketCandlePageObservationPayload | null;
  dailyCandles: MarketCandlePageObservationPayload | null;
  exchangeRate: MarketExchangeRateObservationPayload | null;
  marketSession: MarketSessionObservationPayload | null;
}

export interface MarketDataSnapshotPayload {
  snapshotId: string;
  cardId: string;
  market: string;
  symbol: string;
  capturedAt: string;
  freshness: MarketDataFreshness;
  quality: MarketDataQuality;
  observations: MarketDataObservationsPayload;
  adapterErrors: MarketDataAdapterErrorPayload[];
}

export interface RefreshMarketDataForWatchlistPayload {
  visibleCardIds: string[];
}

export interface RefreshMarketDataForCardPayload {
  cardId: string;
}

export interface ReadLatestMarketDataSnapshotsPayload {
  cardIds?: string[];
}

export interface MarketDataRefreshPayload {
  refreshedAt: string;
  nextPollDelayMs: number;
  snapshots: MarketDataSnapshotPayload[];
}

export interface MarketDataRefreshCardPayload {
  refreshedAt: string;
  nextPollDelayMs: number;
  snapshot: MarketDataSnapshotPayload;
}

export interface MarketDataLatestSnapshotsPayload {
  snapshots: MarketDataSnapshotPayload[];
}

export type QuantIndicatorQuality = "complete" | "partial" | "unavailable";
export type QuantIndicatorDecisionStatus =
  | "watch"
  | "confirmationWaiting"
  | "riskHigh"
  | "invalidated"
  | "dataInsufficient";
export type QuantIndicatorSeverity = "positive" | "neutral" | "warning" | "danger" | "unavailable";
export type QuantIndicatorCalculationStatus = "available" | "estimated" | "unavailable";
export type QuantIndicatorSignalKey =
  | "basicReturn"
  | "vwap"
  | "cvd"
  | "spread"
  | "velocityAcceleration"
  | "distanceProfile"
  | "rsiMomentum"
  | "atrStop"
  | "supplyPressure"
  | "profitTakingPressure"
  | "riskReward"
  | "marketSentimentScore"
  | "intradayTradeScore";

export interface QuantIndicatorSignalPayload {
  key: QuantIndicatorSignalKey;
  label: string;
  severity: QuantIndicatorSeverity;
  status: QuantIndicatorCalculationStatus;
  reason: string | null;
}

export interface BasicReturnIndicatorPayload {
  status: "available" | "unavailable";
  currentPrice: string | null;
  referencePrice: string | null;
  absoluteChange: string | null;
  simpleReturnPercent: number | null;
  logReturnPercent: number | null;
  currency: string;
  referenceLabel: string;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface VwapIndicatorPayload {
  status: "available" | "unavailable";
  value: string | null;
  distanceBps: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface CvdIndicatorPayload {
  status: "estimated" | "unavailable";
  value: string | null;
  confidence: "estimated" | "unavailable";
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface SpreadIndicatorPayload {
  status: "available" | "unavailable";
  spreadBps: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface AtrStopIndicatorPayload {
  status: "available" | "unavailable";
  atr: string | null;
  stopDistancePercent: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface SupplyPressureIndicatorPayload {
  status: "available" | "unavailable";
  pocPrice: string | null;
  overheadRatio: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export type ProfitTakingPressureCauseKey =
  | "profitBurden"
  | "realizedSellPressure"
  | "overheadSupplyPressure"
  | "liquidityImpactRisk";

export interface ProfitTakingPressureCausePayload {
  status: QuantIndicatorCalculationStatus;
  score: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  reason: string | null;
}

export interface ProfitTakingPressureCausesPayload {
  profitBurden: ProfitTakingPressureCausePayload;
  realizedSellPressure: ProfitTakingPressureCausePayload;
  overheadSupplyPressure: ProfitTakingPressureCausePayload;
  liquidityImpactRisk: ProfitTakingPressureCausePayload;
}

export interface ProfitTakingPressureIndicatorPayload {
  status: "available" | "unavailable";
  profitLongRatio: number | null;
  weightedProfitPressure: number | null;
  vwapAtrExtension: number | null;
  sellFlowPressure: number | null;
  askBookPressure: number | null;
  volumeExpansion: number | null;
  score: number | null;
  causes: ProfitTakingPressureCausesPayload;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface RiskRewardIndicatorPayload {
  status: "available" | "unavailable";
  ratio: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface VelocityAccelerationIndicatorPayload {
  status: "available" | "unavailable";
  latestLogReturnPercent: number | null;
  priceAccelerationPercent: number | null;
  volumeChangePercent: number | null;
  estimatedCvdChange: string | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface DistanceProfileIndicatorPayload {
  status: "available" | "unavailable";
  vwapDistanceBps: number | null;
  movingAverageDistanceBps: number | null;
  atrMultipleFromPreviousClose: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface RsiMomentumIndicatorPayload {
  status: "available" | "unavailable";
  rsi: number | null;
  momentumPercent: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface MarketSentimentScoreIndicatorPayload {
  status: "available" | "unavailable";
  score: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface IntradayTradeScoreIndicatorPayload {
  status: "available" | "unavailable";
  conditionStrengthPercent: number | null;
  label: string;
  severity: QuantIndicatorSeverity;
  unavailableReason: string | null;
}

export interface QuantIndicatorsPayload {
  basicReturn: BasicReturnIndicatorPayload;
  vwap: VwapIndicatorPayload;
  cvd: CvdIndicatorPayload;
  spread: SpreadIndicatorPayload;
  velocityAcceleration: VelocityAccelerationIndicatorPayload;
  distanceProfile: DistanceProfileIndicatorPayload;
  rsiMomentum: RsiMomentumIndicatorPayload;
  atrStop: AtrStopIndicatorPayload;
  supplyPressure: SupplyPressureIndicatorPayload;
  profitTakingPressure: ProfitTakingPressureIndicatorPayload;
  riskReward: RiskRewardIndicatorPayload;
  marketSentimentScore: MarketSentimentScoreIndicatorPayload;
  intradayTradeScore: IntradayTradeScoreIndicatorPayload;
}

export interface QuantIndicatorExplanationInputPayload {
  label: string;
  value: string;
}

export interface QuantIndicatorExplanationTracePayload {
  key: QuantIndicatorSignalKey;
  title: string;
  source: string;
  originalFormula: string[];
  substitutedFormula: string[];
  result: string[];
  inputs: QuantIndicatorExplanationInputPayload[];
  meaning: string;
  usage: string;
  judgment: string;
  caution: string;
  limitation: string | null;
}

export interface QuantIndicatorSnapshotPayload {
  snapshotId: string;
  sourceMarketDataSnapshotId: string;
  cardId: string;
  market: string;
  symbol: string;
  calculatedAt: string;
  quality: QuantIndicatorQuality;
  decisionStatus: QuantIndicatorDecisionStatus;
  decisionLabel: string;
  nextCheckLabel: string;
  indicators: QuantIndicatorsPayload;
  signals: QuantIndicatorSignalPayload[];
  explanationTraces: QuantIndicatorExplanationTracePayload[];
}

export interface RefreshQuantIndicatorsForWatchlistPayload {
  cardIds: string[];
}

export interface RefreshQuantIndicatorsForCardPayload {
  cardId: string;
}

export interface ReadLatestQuantIndicatorSnapshotsPayload {
  cardIds?: string[];
}

export interface QuantIndicatorRefreshPayload {
  refreshedAt: string;
  snapshots: QuantIndicatorSnapshotPayload[];
}

export interface QuantIndicatorRefreshCardPayload {
  refreshedAt: string;
  snapshot: QuantIndicatorSnapshotPayload;
}

export interface QuantIndicatorLatestSnapshotsPayload {
  snapshots: QuantIndicatorSnapshotPayload[];
}

export type MarketStateSignalId =
  | "FOMO_LIKE"
  | "PANIC_LIKE"
  | "PROFIT_TAKING_PROXY"
  | "PERSISTENT_RECOVERY"
  | "EFFICIENT_UPTREND";
export type MarketStateSignalStatus =
  | "detected"
  | "notDetected"
  | "notApplicable"
  | "collecting"
  | "unavailable";
export type ObservedMarketState =
  | "BASELINE"
  | "AFTER_UP"
  | "AFTER_DOWN"
  | "UNAVAILABLE";
export type MarketStateBackfillStatus =
  | "idle"
  | "running"
  | "complete"
  | "incomplete"
  | "failed";

export interface MarketStateGatePayload {
  gateId: "POSITIVE_PRESSURE_MEAN_3" | "POSITIVE_RELATIVE_VOLUME";
  label: string;
  value: number;
  operator: ">";
  threshold: number;
  passed: boolean | null;
}

export interface MarketStateContributionPayload {
  featureName: string;
  rawValue: number;
  mean: number;
  scale: number;
  standardizedValue: number;
  coefficient: number;
  contribution: number;
}

export interface MarketStateFormulaTracePayload {
  intercept: number;
  contributions: MarketStateContributionPayload[];
  effectiveTailShare: number;
  calibrationTailShare: number;
  transportTailSafetyFactor: number;
  candidateId: string;
  cause: string;
  phenotypeTag: string;
}

export interface MarketStateSignalPayload {
  signalId: MarketStateSignalId;
  displayName: string;
  formationLabel: string;
  horizonMinutes: number;
  status: MarketStateSignalStatus;
  unavailableReason?: string;
  percentile: number | null;
  percentileNumerator: number | null;
  percentileDenominator: number | null;
  rawScore: number | null;
  dynamicThreshold: number | null;
  thresholdDistance: number | null;
  gate: MarketStateGatePayload | null;
  requiredRiskState: Exclude<ObservedMarketState, "UNAVAILABLE">;
  currentRiskState: ObservedMarketState;
  currentDetectionStartedAt: string | null;
  lastDetectedAt: string | null;
  trace: MarketStateFormulaTracePayload | null;
}

export interface MarketStateFormulaSnapshotPayload {
  snapshotId: string;
  cardId: string;
  symbol: string;
  sessionDate: string;
  asOf: string;
  bucketIndex: number | null;
  sourceGenerationId: string;
  formulaVersion: string;
  formulaContentSha256: string;
  observedState: ObservedMarketState;
  observedStateLabel: string;
  signals: MarketStateSignalPayload[];
  notifiedSignalIds: MarketStateSignalId[];
}

export interface MarketStateBackfillProgressPayload {
  jobId: string;
  status: MarketStateBackfillStatus;
  requiredSessions: number;
  completedSessions: number;
  currentInstrumentId: string | null;
  totalInstrumentCount: number;
  completedInstrumentCount: number;
  error: string | null;
}

export interface RefreshMarketStateForWatchlistPayload {
  cardIds: string[];
}

export interface ReadLatestMarketStateSnapshotsPayload {
  cardIds?: string[];
}

export interface MarketStateRefreshPayload {
  refreshedAt: string;
  snapshots: MarketStateFormulaSnapshotPayload[];
  backfillProgress: MarketStateBackfillProgressPayload;
}

export interface MarketStateLatestSnapshotsPayload {
  snapshots: MarketStateFormulaSnapshotPayload[];
  backfillProgress: MarketStateBackfillProgressPayload;
}

export interface ReadMarketStateTracePayload {
  cardId: string;
  signalId: MarketStateSignalId;
}

export interface MarketStateTracePayload extends MarketStateSignalPayload {
  cardId: string;
  symbol: string;
  sessionDate: string;
  asOf: string;
  sourceGenerationId: string;
  formulaVersion: string;
  formulaContentSha256: string;
  observedState: ObservedMarketState;
  observedStateLabel: string;
}

export interface MarketStateTraceResponsePayload {
  trace: MarketStateTracePayload | null;
}

export interface ReadMarketStateHistoryPayload {
  cardId: string;
  signalId: MarketStateSignalId;
  sessionDate: string;
}

export interface MarketStateHistoryPointPayload {
  asOf: string;
  bucketIndex: number | null;
  status: MarketStateSignalStatus;
  percentile: number | null;
  rawScore: number | null;
  dynamicThreshold: number | null;
  detected: boolean;
}

export interface MarketStateHistoryPayload {
  cardId: string;
  signalId: MarketStateSignalId;
  sessionDate: string;
  points: MarketStateHistoryPointPayload[];
}

export interface CreateTossCredentialStatusPayloadInput {
  configured: boolean;
  clientId?: string | null;
  lastValidatedAt?: string | null;
  connectionStatus: TossConnectionStatus;
}

export type AppRequestParseResult =
  | {
      ok: true;
      request: AppRequestEnvelope;
    }
  | {
      ok: false;
      error: AppErrorEnvelope;
    };

export interface CreateRuntimeProfileRequestInput {
  requestId: string;
  occurredAt: string;
}

export function createRuntimeProfileRequest(
  input: CreateRuntimeProfileRequestInput
): RuntimeProfileRequestEnvelope {
  return {
    event: APP_RUNTIME_CONTRACT.events.runtimeProfileRequest,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
    payload: {}
  };
}

export interface CreateAppRequestInput<
  EventName extends AppRequestEvent,
  Payload
> {
  event: EventName;
  requestId: string;
  occurredAt: string;
  payload: Payload;
}

export function createAppRequest<EventName extends AppRequestEvent, Payload>(
  input: CreateAppRequestInput<EventName, Payload>
): AppRequestEnvelope<EventName, Payload> {
  return {
    event: input.event,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
    payload: input.payload
  };
}

export interface CreateAppResponseInput<
  EventName extends AppResponseEvent,
  Payload
> {
  event: EventName;
  requestId: string;
  occurredAt: string;
  payload: Payload;
}

export function createAppResponse<EventName extends AppResponseEvent, Payload>(
  input: CreateAppResponseInput<EventName, Payload>
): AppResponseEnvelope<EventName, Payload> {
  return {
    event: input.event,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
    payload: input.payload
  };
}

export interface CreateRuntimeProfileResponseInput {
  requestId: string;
  occurredAt: string;
  payload: RuntimeProfileDto;
}

export function createRuntimeProfileResponse(
  input: CreateRuntimeProfileResponseInput
): RuntimeProfileResponseEnvelope {
  return {
    event: APP_RUNTIME_CONTRACT.events.runtimeProfileResponse,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
    payload: input.payload
  };
}

export interface CreateAppErrorInput {
  requestId: string;
  occurredAt: string;
  code: AppRuntimeErrorCode;
  message: string;
  recoverable: boolean;
}

export function createAppError(input: CreateAppErrorInput): AppErrorEnvelope {
  return {
    event: APP_RUNTIME_CONTRACT.events.appError,
    requestId: input.requestId,
    occurredAt: input.occurredAt,
    error: {
      code: input.code,
      message: input.message,
      recoverable: input.recoverable
    }
  };
}

export function createTossCredentialStatusPayload(
  input: CreateTossCredentialStatusPayloadInput
): TossCredentialStatusPayload {
  return {
    configured: input.configured,
    maskedClientId: input.configured ? maskClientId(input.clientId ?? "") : null,
    lastValidatedAt: input.lastValidatedAt ?? null,
    connectionStatus: input.connectionStatus
  };
}

export function parseAppRequest(input: unknown, occurredAt: string): AppRequestParseResult {
  const request = readRecord(input);
  const requestId = readString(request, "requestId");
  const event = readString(request, "event");

  if (requestId === undefined || requestId.trim() === "") {
    return {
      ok: false,
      error: createAppError({
        requestId: "unavailable",
        occurredAt,
        code: "invalid_request",
        message: "request requires requestId",
        recoverable: true
      })
    };
  }

  return {
    ok: true,
    request: {
      event: isAppRequestEvent(event) ? event : APP_RUNTIME_CONTRACT.events.runtimeProfileRequest,
      requestId,
      occurredAt: readString(request, "occurredAt") ?? occurredAt,
      payload: request.payload
    }
  };
}

export function parseRuntimeProfileRequest(
  input: unknown,
  occurredAt: string
): RuntimeProfileRequestParseResult {
  const request = readRecord(input);
  const requestId = readString(request, "requestId");

  if (requestId === undefined || requestId.trim() === "") {
    return {
      ok: false,
      error: createAppError({
        requestId: "unavailable",
        occurredAt,
        code: "invalid_request",
        message: "runtime profile request requires requestId",
        recoverable: true
      })
    };
  }

  return {
    ok: true,
    request: {
      event: APP_RUNTIME_CONTRACT.events.runtimeProfileRequest,
      requestId,
      occurredAt: readString(request, "occurredAt") ?? occurredAt,
      payload: {}
    }
  };
}

export function isRuntimeProfileResponseEnvelope(
  input: unknown
): input is RuntimeProfileResponseEnvelope {
  const record = readRecord(input);

  return (
    readString(record, "event") === APP_RUNTIME_CONTRACT.events.runtimeProfileResponse &&
    readString(record, "requestId") !== undefined &&
    typeof record.payload === "object" &&
    record.payload !== null
  );
}

export function isAppResponseEnvelope(input: unknown): input is AppResponseEnvelope {
  const record = readRecord(input);

  return (
    isAppResponseEvent(readString(record, "event")) &&
    readString(record, "requestId") !== undefined &&
    readString(record, "occurredAt") !== undefined &&
    "payload" in record
  );
}

export function isAppErrorEnvelope(input: unknown): input is AppErrorEnvelope {
  const record = readRecord(input);
  const error = readRecord(record.error);

  return (
    readString(record, "event") === APP_RUNTIME_CONTRACT.events.appError &&
    readString(record, "requestId") !== undefined &&
    readString(error, "code") !== undefined &&
    readString(error, "message") !== undefined &&
    typeof error.recoverable === "boolean"
  );
}

const MARKET_STATE_SIGNAL_IDS: readonly MarketStateSignalId[] = [
  "FOMO_LIKE",
  "PANIC_LIKE",
  "PROFIT_TAKING_PROXY",
  "PERSISTENT_RECOVERY",
  "EFFICIENT_UPTREND"
];

export function isMarketStateRefreshPayload(
  input: unknown
): input is MarketStateRefreshPayload {
  const payload: Record<string, unknown> = readRecord(input);

  return (
    isIsoTimestamp(payload.refreshedAt) &&
    Array.isArray(payload.snapshots) &&
    payload.snapshots.every(isMarketStateFormulaSnapshotPayload) &&
    isMarketStateBackfillProgressPayload(payload.backfillProgress)
  );
}

export function isMarketStateLatestSnapshotsPayload(
  input: unknown
): input is MarketStateLatestSnapshotsPayload {
  const payload: Record<string, unknown> = readRecord(input);

  return (
    Array.isArray(payload.snapshots) &&
    payload.snapshots.every(isMarketStateFormulaSnapshotPayload) &&
    isMarketStateBackfillProgressPayload(payload.backfillProgress)
  );
}

export function isMarketStateTraceResponsePayload(
  input: unknown
): input is MarketStateTraceResponsePayload {
  const payload: Record<string, unknown> = readRecord(input);

  return (
    payload.trace === null ||
    isMarketStateTracePayload(payload.trace)
  );
}

export function isMarketStateHistoryPayload(
  input: unknown
): input is MarketStateHistoryPayload {
  const payload: Record<string, unknown> = readRecord(input);

  return (
    readString(payload, "cardId") !== undefined &&
    isMarketStateSignalId(payload.signalId) &&
    isSessionDate(payload.sessionDate) &&
    Array.isArray(payload.points) &&
    payload.points.every(isMarketStateHistoryPointPayload)
  );
}

export function isMarketStateFormulaSnapshotPayload(
  input: unknown
): input is MarketStateFormulaSnapshotPayload {
  const snapshot: Record<string, unknown> = readRecord(input);
  const signalIds: string[] = Array.isArray(snapshot.signals)
    ? snapshot.signals.map(
        (signal: unknown): string =>
          readString(readRecord(signal), "signalId") ?? ""
      )
    : [];

  return (
    readString(snapshot, "snapshotId") !== undefined &&
    readString(snapshot, "cardId") !== undefined &&
    readString(snapshot, "symbol") !== undefined &&
    typeof snapshot.sessionDate === "string" &&
    isIsoTimestamp(snapshot.asOf) &&
    (
      snapshot.bucketIndex === null ||
      Number.isInteger(snapshot.bucketIndex)
    ) &&
    readString(snapshot, "sourceGenerationId") !== undefined &&
    isSha256(snapshot.formulaVersion) &&
    isSha256(snapshot.formulaContentSha256) &&
    isObservedMarketState(snapshot.observedState) &&
    readString(snapshot, "observedStateLabel") !== undefined &&
    Array.isArray(snapshot.signals) &&
    signalIds.join("|") === MARKET_STATE_SIGNAL_IDS.join("|") &&
    snapshot.signals.every(isMarketStateSignalPayload) &&
    Array.isArray(snapshot.notifiedSignalIds) &&
    snapshot.notifiedSignalIds.every(isMarketStateSignalId)
  );
}

function isMarketStateSignalPayload(
  input: unknown
): input is MarketStateSignalPayload {
  const signal: Record<string, unknown> = readRecord(input);

  return (
    isMarketStateSignalId(signal.signalId) &&
    readString(signal, "displayName") !== undefined &&
    readString(signal, "formationLabel") !== undefined &&
    typeof signal.horizonMinutes === "number" &&
    Number.isFinite(signal.horizonMinutes) &&
    isMarketStateSignalStatus(signal.status) &&
    isNullablePercentile(signal.percentile) &&
    isNullableFiniteNumber(signal.percentileNumerator) &&
    isNullableFiniteNumber(signal.percentileDenominator) &&
    isNullableFiniteNumber(signal.rawScore) &&
    isNullableFiniteNumber(signal.dynamicThreshold) &&
    isNullableFiniteNumber(signal.thresholdDistance) &&
    (
      signal.gate === null ||
      isMarketStateGatePayload(signal.gate)
    ) &&
    isObservedMarketRiskState(signal.requiredRiskState) &&
    isObservedMarketState(signal.currentRiskState) &&
    isNullableIsoTimestamp(signal.currentDetectionStartedAt) &&
    isNullableIsoTimestamp(signal.lastDetectedAt) &&
    (
      signal.trace === null ||
      isMarketStateFormulaTracePayload(signal.trace)
    ) &&
    (
      signal.unavailableReason === undefined ||
      typeof signal.unavailableReason === "string"
    )
  );
}

function isMarketStateTracePayload(
  input: unknown
): input is MarketStateTracePayload {
  const trace: Record<string, unknown> = readRecord(input);

  return (
    isMarketStateSignalPayload(trace) &&
    readString(trace, "cardId") !== undefined &&
    readString(trace, "symbol") !== undefined &&
    isSessionDate(trace.sessionDate) &&
    isIsoTimestamp(trace.asOf) &&
    readString(trace, "sourceGenerationId") !== undefined &&
    isSha256(trace.formulaVersion) &&
    isSha256(trace.formulaContentSha256) &&
    isObservedMarketState(trace.observedState) &&
    readString(trace, "observedStateLabel") !== undefined
  );
}

function isMarketStateGatePayload(
  input: unknown
): input is MarketStateGatePayload {
  const gate: Record<string, unknown> = readRecord(input);

  return (
    [
      "POSITIVE_PRESSURE_MEAN_3",
      "POSITIVE_RELATIVE_VOLUME"
    ].includes(String(gate.gateId)) &&
    readString(gate, "label") !== undefined &&
    isFiniteNumber(gate.value) &&
    gate.operator === ">" &&
    isFiniteNumber(gate.threshold) &&
    (
      gate.passed === null ||
      typeof gate.passed === "boolean"
    )
  );
}

function isMarketStateFormulaTracePayload(
  input: unknown
): input is MarketStateFormulaTracePayload {
  const trace: Record<string, unknown> = readRecord(input);

  return (
    isFiniteNumber(trace.intercept) &&
    Array.isArray(trace.contributions) &&
    trace.contributions.length > 0 &&
    trace.contributions.every(isMarketStateContributionPayload) &&
    isProbability(trace.effectiveTailShare) &&
    isProbability(trace.calibrationTailShare) &&
    isFiniteNumber(trace.transportTailSafetyFactor) &&
    Number(trace.transportTailSafetyFactor) > 0 &&
    readString(trace, "candidateId") !== undefined &&
    readString(trace, "cause") !== undefined &&
    readString(trace, "phenotypeTag") !== undefined
  );
}

function isMarketStateContributionPayload(
  input: unknown
): input is MarketStateContributionPayload {
  const contribution: Record<string, unknown> = readRecord(input);

  return (
    readString(contribution, "featureName") !== undefined &&
    isFiniteNumber(contribution.rawValue) &&
    isFiniteNumber(contribution.mean) &&
    isFiniteNumber(contribution.scale) &&
    Number(contribution.scale) > 0 &&
    isFiniteNumber(contribution.standardizedValue) &&
    isFiniteNumber(contribution.coefficient) &&
    isFiniteNumber(contribution.contribution)
  );
}

function isMarketStateHistoryPointPayload(
  input: unknown
): input is MarketStateHistoryPointPayload {
  const point: Record<string, unknown> = readRecord(input);

  return (
    isIsoTimestamp(point.asOf) &&
    (
      point.bucketIndex === null ||
      isNonNegativeInteger(point.bucketIndex)
    ) &&
    isMarketStateSignalStatus(point.status) &&
    isNullablePercentile(point.percentile) &&
    isNullableFiniteNumber(point.rawScore) &&
    isNullableFiniteNumber(point.dynamicThreshold) &&
    typeof point.detected === "boolean"
  );
}

function isMarketStateBackfillProgressPayload(
  input: unknown
): input is MarketStateBackfillProgressPayload {
  const progress: Record<string, unknown> = readRecord(input);

  return (
    readString(progress, "jobId") !== undefined &&
    ["idle", "running", "complete", "incomplete", "failed"].includes(
      String(progress.status)
    ) &&
    isNonNegativeInteger(progress.requiredSessions) &&
    isNonNegativeInteger(progress.completedSessions) &&
    (
      progress.currentInstrumentId === null ||
      typeof progress.currentInstrumentId === "string"
    ) &&
    isNonNegativeInteger(progress.totalInstrumentCount) &&
    isNonNegativeInteger(progress.completedInstrumentCount) &&
    (
      progress.error === null ||
      typeof progress.error === "string"
    )
  );
}

function isMarketStateSignalId(
  input: unknown
): input is MarketStateSignalId {
  return MARKET_STATE_SIGNAL_IDS.includes(input as MarketStateSignalId);
}

function isMarketStateSignalStatus(
  input: unknown
): input is MarketStateSignalStatus {
  return [
    "detected",
    "notDetected",
    "notApplicable",
    "collecting",
    "unavailable"
  ].includes(String(input));
}

function isObservedMarketState(
  input: unknown
): input is ObservedMarketState {
  return [
    "BASELINE",
    "AFTER_UP",
    "AFTER_DOWN",
    "UNAVAILABLE"
  ].includes(String(input));
}

function isObservedMarketRiskState(
  input: unknown
): input is Exclude<ObservedMarketState, "UNAVAILABLE"> {
  return ["BASELINE", "AFTER_UP", "AFTER_DOWN"].includes(String(input));
}

function isSha256(input: unknown): input is string {
  return typeof input === "string" && /^[a-f0-9]{64}$/.test(input);
}

function isSessionDate(input: unknown): input is string {
  return typeof input === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(input);
}

function isIsoTimestamp(input: unknown): input is string {
  return (
    typeof input === "string" &&
    input.trim() !== "" &&
    Number.isFinite(Date.parse(input))
  );
}

function isNullableIsoTimestamp(input: unknown): input is string | null {
  return input === null || isIsoTimestamp(input);
}

function isNullableFiniteNumber(input: unknown): input is number | null {
  return input === null || (
    typeof input === "number" &&
    Number.isFinite(input)
  );
}

function isFiniteNumber(input: unknown): input is number {
  return typeof input === "number" && Number.isFinite(input);
}

function isProbability(input: unknown): input is number {
  return isFiniteNumber(input) && input > 0 && input < 1;
}

function isNullablePercentile(input: unknown): input is number | null {
  return (
    input === null ||
    (
      typeof input === "number" &&
      Number.isFinite(input) &&
      input >= 0 &&
      input <= 100
    )
  );
}

function isNonNegativeInteger(input: unknown): input is number {
  return Number.isInteger(input) && Number(input) >= 0;
}

function readRecord(input: unknown): Record<string, unknown> {
  if (typeof input === "object" && input !== null) {
    return input as Record<string, unknown>;
  }

  return {};
}

function readString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];

  return typeof value === "string" ? value : undefined;
}

function maskClientId(clientId: string): string {
  if (clientId.length <= 8) {
    return "****";
  }

  return `${clientId.slice(0, 4)}…${clientId.slice(-4)}`;
}

function isAppRequestEvent(event: string | undefined): event is AppRequestEvent {
  if (event === undefined) {
    return false;
  }

  return Object.values(APP_RUNTIME_CONTRACT.events).includes(event as AppEvent) &&
    event.endsWith(":request") || event === APP_RUNTIME_CONTRACT.events.tossCredentialsSaveRequest ||
    event === APP_RUNTIME_CONTRACT.events.tossConnectionTestRequest ||
    event === APP_RUNTIME_CONTRACT.events.tossCredentialsDeleteRequest ||
    event === APP_RUNTIME_CONTRACT.events.tossCredentialsReadStatusRequest;
}

function isAppResponseEvent(event: string | undefined): event is AppResponseEvent {
  if (event === undefined) {
    return false;
  }

  return Object.values(APP_RUNTIME_CONTRACT.events).includes(event as AppEvent) &&
    event.endsWith(":response");
}
