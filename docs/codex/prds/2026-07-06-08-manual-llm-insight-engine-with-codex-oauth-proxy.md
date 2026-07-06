# Step 08 PRD: Manual LLM Insight Engine With Codex OAuth Proxy

## Goal

Run LLM-dependent insight only when the user manually refreshes it, using the Codex OAuth backend proxy pattern from `/Users/jik/Projects/adp` instead of storing an OpenAI API key.

## User Value

The user can request higher-level interpretation, news sentiment, 3-trading-day scenarios, and indicator conflict explanations without slowing every polling cycle or making LLM output look like deterministic calculation.

## Scope

- Manual AI refresh per card.
- Insight snapshot creation from quant indicators, market data quality, event timeline, and optional backtest summary.
- Codex OAuth backend proxy integration.
- News sentiment, relevance, event risk, 3-trading-day outlook, and scenario narrative.
- AI output stored with snapshot ID and source data timestamps.
- Clear separation between quant update time and AI insight update time.

## Non-Goals

- No automatic LLM refresh during polling.
- No direct order execution by LLM.
- No hidden API key storage.
- No LLM recalculation of deterministic indicators.

## Object-Oriented Design

### Entities

- `InsightSnapshot`: immutable input bundle sent to the LLM.
- `LlmInsightReport`: generated interpretation tied to one snapshot.

### Value Objects

- `InsightSnapshotId`
- `InsightRefreshRequestedAt`
- `QuantSnapshotReference`
- `EventTimelineReference`
- `LlmModelName`
- `LlmOutputSafetyLabel`

### Domain Services

- `InsightInputPolicy`: decides which deterministic fields may be sent to LLM.
- `InvestmentLanguageSafetyPolicy`: rejects wording that sounds like certain investment advice.

### Application Use Cases

- `CreateInsightSnapshot`
- `RefreshLlmInsightForCard`
- `ReadLatestLlmInsightForCard`

### Adapters

- `CodexOAuthLlmAdapter`
- `CodexOAuthCredentialsReader`
- `CodexBackendResponsesClient`

## Codex OAuth Proxy Requirements

The adapter follows the `adp` pattern:

- Verify `codex login status`.
- Read `~/.codex/auth.json` or configured auth file.
- Extract `access_token`, `refresh_token`, and `account_id`.
- Call Codex backend Responses endpoint.
- Use SSE response parsing.
- Keep credentials out of renderer code.

## AI Insight Outputs

- News sentiment: positive, negative, neutral, mixed, or unavailable.
- Relevance: high, medium, low, or unavailable.
- Event risk: earnings, disclosure, macro, FX, market selloff, rumor-like, or unavailable.
- Indicator conflict explanation.
- Strong/base/weak 3-trading-day scenarios.
- Conditions that would invalidate the scenario.
- Model limitations and data gaps.

## Acceptance Criteria

- AI refresh runs only from explicit user action.
- Insight report stores the exact snapshot ID used as input.
- If Codex OAuth login is missing, the UI shows a recoverable login-required state.
- AI report cannot overwrite deterministic indicator values.
- AI report displays `AI 분석` timestamp separate from `지표 업데이트`.
- Reports identify unavailable data instead of inventing missing facts.

## Verification

- Adapter tests use injected fake command executor, fake auth file reader, and fake SSE response.
- Use case tests verify snapshot creation and report persistence.
- Safety policy tests reject direct buy/sell certainty language.

## Dependencies

- Step 05 quant indicator engine.
- Step 07 news/event timeline.

