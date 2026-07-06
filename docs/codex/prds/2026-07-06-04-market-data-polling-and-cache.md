# Step 04 PRD: Market Data Polling And Cache

## Goal

Fetch Toss market data for active watch cards with rate-limit-aware polling and cache enough raw observations for deterministic indicator calculation.

## User Value

The watchlist can update derived states automatically without asking the user to refresh each stock manually.

## Scope

- Poll active watch cards.
- Fetch prices, trades, orderbook, candles, exchange rate, and market calendar as needed.
- Respect Toss rate limits and market sessions.
- Maintain in-memory and persisted recent data cache.
- Track freshness, missing data, and adapter errors.

## Non-Goals

- No LLM insight.
- No user-facing raw chart replacement.
- No websocket behavior, because Toss Open API currently documents REST only.

## Object-Oriented Design

### Entities

- `MarketDataSnapshot`: aggregate of raw observations for one symbol at one polling moment.
- `PollingPlan`: schedule for which endpoints to call and when.

### Value Objects

- `DataFreshness`
- `RateLimitBudget`
- `MarketSession`
- `PollingInterval`
- `MarketDataQuality`

### Domain Services

- `PollingPriorityPolicy`: prioritizes visible and recently selected cards.
- `MarketSessionPolicy`: changes polling behavior for regular, pre, after, closed, and holiday sessions.

### Application Use Cases

- `RefreshMarketDataForWatchlist`
- `RefreshMarketDataForCard`
- `ReadLatestMarketDataSnapshot`

### Adapters

- `TossMarketDataAdapter`
- `TossMarketInfoAdapter`
- `RateLimitAwareTossClient`
- `MarketDataSnapshotRepository`

## Acceptance Criteria

- Active cards are polled automatically.
- Hidden and archived cards are excluded from default polling.
- Visible cards can be prioritized over off-screen cards.
- API failures degrade individual card data quality without breaking the full list.
- Rate limit headers inform subsequent polling delay.
- Market closed state reduces unnecessary polling.
- Raw market data is not shown as a primary product surface; it feeds indicator calculation.

## Verification

- Unit tests validate polling plan generation by card status and market session.
- Adapter tests validate rate-limit header handling and retry delay calculation.
- Snapshot repository tests validate latest snapshot retrieval and stale snapshot detection.

## Dependencies

- Step 03 symbol verification.

