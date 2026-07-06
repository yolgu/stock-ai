# Step 01 PRD: App Shell And Typed Boundary Foundation

## Goal

Create the desktop app foundation that separates renderer UI, application use cases, domain modules, persistence, Toss API adapters, and LLM proxy integration points before feature work begins.

## User Value

The user gets a reliable desktop container that can later run beside Toss Securities without leaking secrets or mixing UI concerns with trading logic.

## Scope

- Neutralino + React + TypeScript app shell.
- Typed app-extension event contract foundation.
- Domain/application/infrastructure/presentation folder boundaries.
- Local configuration shape for non-secret user preferences.
- Extension-side secret boundary for Toss and Codex OAuth-related access.

## Non-Goals

- No market data polling.
- No watch card CRUD.
- No LLM request execution.
- No order API integration.

## Object-Oriented Design

### Domain

- `AppRuntimeProfile`: value object describing runtime mode, market data mode, and feature availability.
- `FeatureCapability`: value object for enabled capabilities such as `watchlist`, `quantIndicators`, `llmInsights`, `orders`.

### Application

- `LoadAppRuntimeProfile`: use case returning renderer-safe startup capabilities.

### Infrastructure

- `RuntimeProfileRepository`: reads local non-secret app settings.
- `AppExtensionEventBus`: typed boundary between renderer and Neutralino extension.

### Presentation

- `AppShell`: root layout and status surface.
- `StartupStateView`: loading, unavailable, and ready states.

## Event Contracts

- `app:runtime-profile:request`
- `app:runtime-profile:response`
- `app:error`

Renderer code must never access local files, shell, environment variables, Toss credentials, Codex auth files, or backend tokens directly.

## Acceptance Criteria

- The app opens to a dark desktop shell with an empty watchlist-ready surface.
- Renderer can request runtime profile through a typed event.
- Extension returns feature capability flags without exposing secrets.
- Extension can report structured startup errors.
- All event payloads have explicit TypeScript types.

## Verification

- Type check confirms renderer and extension event payload compatibility.
- Unit tests validate runtime profile loading with default settings.
- Contract tests validate success and error responses for `app:runtime-profile`.

## Dependencies

None.

