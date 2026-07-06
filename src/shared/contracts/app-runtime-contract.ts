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
  | "toss_connection_failed";

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
