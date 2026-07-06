# Step 03 PRD: Symbol Intake And Toss Stock Verification

## Goal

Let users add cards through symbol paste/direct input, then verify the symbol against Toss Securities Open API before creating the card.

## User Value

The user can copy `MU`, `AAPL`, `005930`, `NASDAQ:MU`, or `마이크론 테크놀로지 MU` into the app and get a verified analysis card without relying on a Toss-provided search API.

## Scope

- Symbol input normalization.
- Multi-symbol paste support.
- Toss `GET /api/v1/stocks?symbols=...` verification.
- Verified stock reference cache.
- Graceful handling for unsupported or unknown symbols.

## Non-Goals

- No full-text stock-name search index.
- No Toss watchlist synchronization.
- No market data polling beyond stock info verification.

## Object-Oriented Design

### Value Objects

- `RawSymbolInput`: original user input.
- `NormalizedSymbol`: parsed symbol candidate.
- `VerifiedStockIdentity`: market, symbol, display name, currency, listing status, trading halt flag.

### Domain Services

- `SymbolInputParser`: extracts one or more symbols from pasted text.
- `StockIdentityValidator`: ensures market and symbol can create a watch card.

### Application Use Cases

- `ParseSymbolInput`
- `VerifyStockSymbol`
- `CreateVerifiedWatchStockCard`

### Adapters

- `TossStockInfoAdapter`: calls `/api/v1/stocks`.
- `StockReferenceCache`: stores verified stock metadata with refresh time.

## User Flow

1. User opens `+ 종목 추가`.
2. User pastes one or more symbols.
3. App parses candidates and displays normalized symbols.
4. Extension verifies symbols through Toss stock info API.
5. Verified symbols can be added as cards.
6. Invalid symbols show actionable errors without creating cards.

## Acceptance Criteria

- `mu` normalizes to `MU`.
- `NASDAQ: MU` normalizes to `MU`.
- `AAPL, MSFT, MU` creates three verification requests batched up to Toss limits.
- `005930 삼성전자` extracts `005930`.
- Unknown symbols are rejected with `stock-not-found`.
- Trading-halted or delisted symbols can be displayed with warnings and require explicit user confirmation before card creation.

## Verification

- Parser tests cover case conversion, prefixes, suffixes, Korean text with embedded numeric symbol, comma-separated symbols, and invalid inputs.
- Adapter contract tests mock Toss stock info success and `stock-not-found` responses.
- Use case tests confirm only verified identities reach card creation.

## Dependencies

- Step 02 watch card CRUD.

