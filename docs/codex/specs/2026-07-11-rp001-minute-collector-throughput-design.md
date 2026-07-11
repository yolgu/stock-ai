# RP-001 Minute Collector Throughput Design

## Objective

Speed up the active Toss one-minute collection without changing the frozen
`provider × instrument × adjustment mode × calendar-day` acquisition identity,
rewriting any existing archive, weakening raw-response lineage, or widening the
read-only endpoint boundary.

## Evidence and constraints

- The live candle responses advertise `x-ratelimit-limit=5` and
  `x-ratelimit-reset=1`; the current batch pacer permits only one request per
  second.
- The frozen plan contains 369,024 daily scopes. A US daily scope normally
  requires roughly five candle pages.
- The local ledger currently validates every historical record before and
  after every append, producing quadratic work as the ledger grows.
- Each daily scope currently reloads credentials and obtains a new OAuth token.
- Existing raw archives, canonical Parquet files, manifests, sidecar hashes,
  failure evidence, and ledger events are immutable inputs to the optimized
  continuation.

## Considered approaches

### Replace the daily plan with seven-day identities

This would reduce scope count, but it would create a new acquisition identity
and prevent direct reuse of already collected daily archives. It is rejected
for the active continuation.

### Increase request rate only

This is simple, but the quadratic ledger and per-scope authentication would
become the next bottlenecks immediately. It is insufficient by itself.

### Preserve identities and optimize execution

This is selected. It changes orchestration costs while preserving every data
and evidence contract.

## Selected design

### Rate control

Use one batch-wide, thread-safe market-data pacer with a default interval of
250 ms, or four candle requests per second. This stays below the observed
provider ceiling of five requests per second. Intervals below the existing
transport safety floor of 210 ms remain invalid. HTTP failures continue to be
captured and terminally recorded; no retry may bypass the endpoint or evidence
boundary.

### Batch authentication session

Open one authenticated Toss minute session lazily on the first unarchived valid
scope in a batch. Reuse its opener and bearer token for the remaining scopes in
that batch, then clear the token at batch exit. A batch containing only verified
archives or invalid scopes must not read credentials or authenticate.

The existing one-scope `run_toss_minute_shard` API remains available and is
implemented through a temporary session. Tests inject a session factory rather
than exposing credentials to application code.

### Linear ledger append session

Hold the existing ledger lock for one `run_toss_minute_batch` invocation. Fully
validate the existing chain once before its first append, validate each newly
published body and sidecar against the cached tail in constant time, and fully
validate the complete chain once at transaction exit. Any tampering detected at
the final verification fails the batch transaction. Canonical bodies, separate
sidecars, contiguous sequences, previous-record hashes, and append-only files
remain unchanged.

### Restart behavior

The running legacy collector remains active while the new code is tested. Once
the relevant and full RP-001-S2 tests pass, stop the legacy process, verify the
last published archive and ledger, then restart from the same frozen plan. The
batch resume path skips network and credential access for verified archives.

## Verification

- RED then GREEN tests prove four-per-second default pacing and rejection below
  the 210 ms floor.
- A multi-scope batch proves one credential load and one authenticated session.
- A resumed-only batch proves zero credential and network use.
- A multi-entry ledger transaction proves two full-chain validations rather
  than two per event and still detects tampering.
- Existing read-only boundary, archive hash, failure continuation, and resume
  tests remain green.
- A live post-restart observation reports requests per second, HTTP failures,
  completed scopes, and row growth without exposing credentials.
