# Step 11 PRD: News/Event Input And Timeline

## Goal

Collect or accept news and event inputs for watch cards so LLM insight can analyze sentiment, relevance, and event risk on demand.

## User Value

The user can attach market context to a stock card without confusing raw news with deterministic indicators.

## Scope

- News item input/import shape.
- Event timeline per watch card.
- Source, timestamp, headline, summary, URL, and raw text storage.
- Deduplication by URL, timestamp, and normalized headline.
- User-provided event notes.
- Event freshness and source reliability labels.

## Non-Goals

- No automatic claim that a news item caused price movement.
- No LLM sentiment calculation in this step.
- No paid news API dependency in the first implementation.

## Object-Oriented Design

### Entities

- `StockEventTimeline`: aggregate for one card's event context.
- `NewsEvent`: external news or disclosure-like item.
- `UserEventNote`: user-authored event context.

### Value Objects

- `EventSource`
- `EventTimestamp`
- `EventRelevanceHint`
- `EventReliability`
- `NewsUrl`
- `NormalizedHeadline`

### Domain Services

- `EventDeduplicationPolicy`
- `EventFreshnessPolicy`
- `EventTimelineOrderingPolicy`

### Application Use Cases

- `AttachNewsEventToCard`
- `AttachUserEventNoteToCard`
- `ListCardEventTimeline`
- `ImportNewsEventsForCard`

### Repository

- `EventTimelineRepository`

## Acceptance Criteria

- User can attach a news URL or text note to a card.
- Duplicate event inputs are merged or rejected with a clear reason.
- Event timeline is ordered by event time, not import time.
- Each event records whether it is external input or user-provided.
- Events are available as structured input to Step 12 LLM insight snapshots.

## Verification

- Domain tests validate deduplication and ordering.
- Repository tests validate event timeline persistence.
- UI tests validate adding, listing, and removing user event notes.

## Dependencies

- Step 02 watch card CRUD.
