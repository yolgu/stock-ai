# Step And PRD Definition Best Practices

## Purpose

This document defines how implementation steps and PRDs are split for the Toss-side day-trading assistant. The product is a Neutralino + React + TypeScript desktop app that manages analysis watch cards, calculates deterministic trading indicators from Toss Securities Open API data, and runs LLM-based insight only when the user asks for it.

## Step Splitting Principles

Each step must produce one independently understandable product capability. A step is valid only when it can be described through a domain outcome, a user-visible result, an explicit boundary, and measurable acceptance criteria.

Good steps are vertical product increments, not loose technical layers. For example, "watch card CRUD with local persistence" is a good step because the user can add, edit, hide, archive, restore, and delete analysis cards. "create repositories" is not enough because it has no user outcome.

The step order follows these rules:

- Build stable boundaries before adding behavior that depends on them.
- Define domain concepts before adapters or UI consume them.
- Keep deterministic quant calculations separate from LLM interpretation.
- Keep order execution behind explicit user confirmation and risk guardrails.
- Add persistence before history-dependent features such as snapshots and backtesting.
- Keep each step small enough to be implemented, tested, and reviewed without knowing all later features.

## PRD Quality Rules

Each PRD must include:

- Product goal and user value.
- Scope and non-goals.
- Domain model names using the product language.
- Object-oriented design boundaries.
- Use cases and event contracts.
- Data inputs and outputs.
- Acceptance criteria.
- Verification strategy.
- Dependencies on earlier steps.

Each PRD avoids implementation trivia unless it affects product behavior or architecture. It names classes, value objects, use cases, repositories, adapters, and policies only when they clarify responsibilities.

## Object-Oriented Design Rules

The domain owns business rules. Renderer components render state and route user intent. Neutralino extension code owns external I/O, local persistence, Toss API calls, Codex OAuth proxy calls, and secrets. Application services orchestrate use cases but do not bury business rules.

Core object categories:

- Entity: identity and lifecycle, such as `WatchStockCard`.
- Value Object: validated immutable value, such as `StockSymbol`, `Market`, `RiskRewardThreshold`, `InsightSnapshotId`.
- Domain Service: stateless domain calculation that does not belong to one entity, such as `CardStatusClassifier`.
- Use Case: application orchestration, such as `AddWatchStockCard`.
- Repository: persistence boundary, such as `WatchlistRepository`.
- Adapter: external boundary, such as `TossStockInfoAdapter`.
- Policy: configurable rule, such as `DuplicateCardPolicy`.

## Recommended Implementation Steps

1. App Shell And Typed Boundary Foundation
2. Watch Stock Card CRUD And Local Persistence
3. Symbol Intake And Toss Stock Verification
4. Market Data Polling And Cache
5. Quant Indicator Engine And Card Status
6. Watchlist Dashboard And Detail UI
7. Market Context And Basic Returns
8. Indicator Explanation Model
9. Beginner Explanation Popover UI
10. LLM-Free Deterministic Indicator Expansion
11. News/Event Input And Timeline
12. Manual LLM Insight Engine With Codex OAuth Proxy
13. Backtesting Engine And Strategy Report
14. Order Integration And User Confirmation Guardrails

These steps build from stable local product state to external data, deterministic calculations, explainable learning surfaces, LLM insight, historical validation, and finally guarded order integration.
