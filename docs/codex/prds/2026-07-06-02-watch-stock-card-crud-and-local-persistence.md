# Step 02 PRD: Watch Stock Card CRUD And Local Persistence

## Goal

Build the local analysis watchlist model so the user can create and maintain stock cards independently of Toss app watchlists.

## User Value

The user can manage the exact set of stocks they want to analyze, with card-level metadata such as memo, tags, groups, order, hidden state, and archive state.

## Scope

- Add, edit, hide, archive, restore, reorder, and delete watch stock cards.
- Card grouping and tagging.
- Duplicate prevention by `market + symbol`.
- Local JSON persistence for MVP.
- Repository interface that can later move to SQLite without changing use cases.

## Non-Goals

- No Toss symbol verification in this step.
- No real market data.
- No quant indicators.
- No LLM analysis.

## Object-Oriented Design

### Entities

- `WatchStockCard`: aggregate root for one analysis target.
- `WatchGroup`: user-defined grouping container.

### Value Objects

- `WatchStockCardId`
- `StockSymbol`
- `Market`
- `DisplayName`
- `WatchTag`
- `SortOrder`
- `CardLifecycleStatus`: `active`, `hidden`, `archived`, `deleted`

### Domain Policies

- `DuplicateCardPolicy`: prevents active duplicate cards for the same `market + symbol`.
- `ArchiveRestorePolicy`: restores an archived card instead of creating a second card.

### Use Cases

- `CreateWatchStockCard`
- `UpdateWatchStockCard`
- `HideWatchStockCard`
- `ArchiveWatchStockCard`
- `RestoreWatchStockCard`
- `DeleteWatchStockCard`
- `ReorderWatchStockCards`
- `MoveWatchStockCardToGroup`

### Repository

- `WatchlistRepository`
  - `findById`
  - `findByMarketSymbol`
  - `listActive`
  - `listArchived`
  - `save`
  - `delete`

## Event Contracts

- `watchlist:list:request`
- `watchlist:list:response`
- `watchlist:create:request`
- `watchlist:update:request`
- `watchlist:hide:request`
- `watchlist:archive:request`
- `watchlist:restore:request`
- `watchlist:delete:request`
- `watchlist:reorder:request`

## Acceptance Criteria

- A card can be created with symbol, market, display name, group, tags, memo, and analysis defaults.
- Creating the same active `market + symbol` returns a duplicate-card result.
- Creating a card for an archived `market + symbol` offers restoration behavior.
- Hidden cards disappear from the default list but remain recoverable.
- Archived cards are excluded from active analysis polling.
- Deleted cards are removed from local persistence after explicit confirmation.
- Reordering persists across app restart.

## Verification

- Domain tests cover duplicate, archive, restore, hide, delete, and reorder policies.
- Repository tests cover JSON round-trip persistence.
- Contract tests cover extension events and validation failures.

## Dependencies

- Step 01 typed event foundation.

