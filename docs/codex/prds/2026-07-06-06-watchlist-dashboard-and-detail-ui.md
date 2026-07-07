# Step 06 PRD: Watchlist Dashboard And Detail UI

## Goal

Create the first screen as a multi-stock watchlist dashboard and provide a detail view for one selected card.

## User Value

The user can monitor many analysis cards at once, then open a detailed decision-support panel without losing the Toss chart context.

## Scope

- Watchlist dashboard.
- Add-by-symbol modal.
- Card CRUD actions.
- Group, tag, sort, and filter controls.
- Quant status cards.
- Detail panel with checklist, conditional zones, data quality, and AI insight placeholder.
- Separate timestamps for quant update and AI insight update.

## Non-Goals

- No automatic LLM refresh.
- No in-app raw price chart.
- No order execution UI.

## Object-Oriented Design

### Presentation Components

- `WatchlistPage`
- `WatchStockCardList`
- `WatchStockCardView`
- `AddSymbolDialog`
- `CardActionMenu`
- `WatchGroupTabs`
- `CardStatusFilter`
- `WatchStockDetailPanel`
- `QuantChecklistView`
- `ConditionalZoneView`
- `DataQualityBadge`

### Hooks And Application Facades

- `useWatchlistCards`
- `useAddWatchStockCard`
- `useCardActions`
- `useQuantCardState`

### View Models

- `WatchStockCardViewModel`
- `QuantStatusViewModel`
- `DetailPanelViewModel`

## UI Behavior

- The dashboard shows multiple cards, not one large hero card.
- Cards avoid raw volume, candlestick chart, and orderbook table, while later steps may show compact price coordinates.
- Cards show derived qualitative status.
- Detail panel shows why a card is in its current state through deterministic checklist rows.
- AI insight area is visibly stale until the user requests manual refresh in Step 12.

## Acceptance Criteria

- User can add a verified symbol from the dashboard.
- User can edit memo, tags, group, and analysis settings.
- User can hide, archive, restore, delete, and reorder cards.
- List can filter by card status and group.
- Card displays `지표 업데이트` timestamp.
- Detail panel reserves `AI 분석` timestamp and manual refresh affordance without running LLM yet.

## Verification

- Renderer tests validate add dialog behavior, card actions, filtering, sorting, and empty states.
- Contract tests validate renderer calls typed watchlist and quant events.
- Visual smoke check validates text does not overflow compact card surfaces.

## Dependencies

- Step 05 quant indicator engine and card status.
