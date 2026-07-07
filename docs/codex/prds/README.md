# Trading Assistant PRD Index

## Product Summary

The product is a Neutralino + React + TypeScript desktop app for day-trading support beside Toss Securities. It does not replace Toss charts. It manages local analysis watch cards, uses Toss Securities Open API data as calculation input, automatically recalculates deterministic indicators during polling, and runs LLM insight only when the user manually requests it.

## Step Documents

| Step | PRD |
| --- | --- |
| 00 | [Step And PRD Definition Best Practices](./2026-07-06-00-step-prd-best-practices.md) |
| 01 | [App Shell And Typed Boundary Foundation](./2026-07-06-01-app-shell-and-typed-boundary-foundation.md) |
| 02 | [Watch Stock Card CRUD And Local Persistence](./2026-07-06-02-watch-stock-card-crud-and-local-persistence.md) |
| 03 | [Symbol Intake And Toss Stock Verification](./2026-07-06-03-symbol-intake-and-toss-stock-verification.md) |
| 04 | [Market Data Polling And Cache](./2026-07-06-04-market-data-polling-and-cache.md) |
| 05 | [Quant Indicator Engine And Card Status](./2026-07-06-05-quant-indicator-engine-and-card-status.md) |
| 06 | [Watchlist Dashboard And Detail UI](./2026-07-06-06-watchlist-dashboard-and-detail-ui.md) |
| 07 | [Market Context And Basic Returns](./2026-07-06-07-market-context-and-basic-returns.md) |
| 08 | [Indicator Explanation Model](./2026-07-06-08-indicator-explanation-model.md) |
| 09 | [Beginner Explanation Popover UI](./2026-07-06-09-beginner-explanation-popover-ui.md) |
| 10 | [LLM-Free Deterministic Indicator Expansion](./2026-07-06-10-llm-free-deterministic-indicator-expansion.md) |
| 11 | [News/Event Input And Timeline](./2026-07-06-11-news-event-input-and-timeline.md) |
| 12 | [Manual LLM Insight Engine With Codex OAuth Proxy](./2026-07-06-12-manual-llm-insight-engine-with-codex-oauth-proxy.md) |
| 13 | [Backtesting Engine And Strategy Report](./2026-07-06-13-backtesting-engine-and-strategy-report.md) |
| 14 | [Order Integration And User Confirmation Guardrails](./2026-07-06-14-order-integration-and-user-confirmation-guardrails.md) |

## Core Architecture Decision

Deterministic calculations and LLM insight are separate.

- Polling updates Toss market snapshots and deterministic quant indicators.
- Manual AI refresh creates an immutable `InsightSnapshot`.
- LLM reports are attached to the snapshot that produced them.
- Order submission remains behind user-authored drafts and explicit confirmation.
