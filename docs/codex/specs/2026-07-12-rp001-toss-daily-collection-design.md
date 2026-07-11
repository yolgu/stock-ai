# RP-001 Toss Daily Collection Design

## Objective

Collect every daily bar returned for a frozen Toss `provider × symbol × period × adjustment` scope without disturbing the active one-minute collector. Start the 48 registered instruments at a strict 0.1 requests/second and freeze the 10,864-symbol US universe for later execution at 4 requests/second after minute collection ends.

Alpaca remains a separate provider path. Its daily transport and parser exist, but live execution is `blocked_missing_credentials` until both required credentials are available. No fallback may silently change SIP data into IEX data.

## Chosen architecture

The implementation adds a separate daily bounded context rather than reusing either the six-symbol legacy runner or the minute archive schema:

1. `daily_scope_plan.py` creates deterministic whole-period scopes, one per symbol and adjustment mode. Sample role is presentation metadata and cannot change the acquisition key.
2. `daily_archive_storage.py` stores each successful scope exactly once as compressed raw response bodies, canonical Parquet rows, a canonical manifest, and a separate SHA-256 sidecar. Existing archives are verified before resume.
3. `toss_daily_collection.py` reuses the strict GET-only Toss candle transport and one ephemeral token per bounded batch. Every scope appends a terminal event to a dedicated append-only ledger, including failed and invalid attempts.
4. `collect_toss_daily.py` loads a frozen plan, skips verified archives, and processes bounded symbol batches. It never calls order, conditional-order, account, or asset endpoints.

The legacy daily runner is not used because its symbols and period are hard-coded. The minute archive is not reused because its invariants require one-minute bar endings and minute-specific Parquet schemas.

## Rate isolation

Recent Toss response headers show a limit of five requests per one-second reset. The active minute process is approximately 3.85 requests/second. The initial daily process therefore uses a fixed 10-second interval (0.1 requests/second), leaving a material shared-provider margin.

The existing pacers are process-local. The daily process must never be started above 0.1 requests/second while the minute process is active. The frozen all-universe plan records `deferred_until_minute_collection_terminal`; its 4 requests/second execution is a separate phase after the minute process ends.

## Evidence and failure behavior

- Raw response bodies are stored without transformation as `.json.zst` and bound by uncompressed and stored SHA-256 values.
- Canonical rows retain response-body hash, capture ordinal, source row index, and every duplicate occurrence.
- Same timestamp and same values merge; conflicting duplicates invalidate the scope.
- Missing bars are not synthesized and volumes are never replaced with zero.
- Failed responses with safe captures are stored as immutable failure evidence and remain retryable.
- A terminal ledger event is appended for every attempted or resumed scope.
- Credentials, authorization headers, and access tokens are never persisted or printed.

## Verification

Tests cover deterministic scope identity, immutable archive verification and tamper rejection, exact raw-to-row lineage, resume without network access, failure preservation, one-session-per-bounded-batch authentication, and the 10-second default daily pacing contract.
