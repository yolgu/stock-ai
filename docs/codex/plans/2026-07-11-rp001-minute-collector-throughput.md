# RP-001 Minute Collector Throughput Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the measured request, authentication, and ledger bottlenecks while preserving the frozen daily acquisition identities and all existing immutable evidence.

**Architecture:** Keep the domain `CollectionScope` and archive formats unchanged. Optimize only the application/infrastructure execution path with a four-request-per-second global pacer, a lazy batch-scoped authenticated session, and a ledger transaction that performs one initial and one final full-chain validation with constant-time validation of each new tail.

**Tech Stack:** Python 3.12, `unittest`, Toss read-only REST boundary, immutable JSON/ZSTD/Parquet archive storage, local append-only SHA-256 ledger.

---

### Task 1: Linear append-only ledger transaction

**Files:**
- Modify: `research/rp-001/src/rp001/local_evidence.py`
- Modify: `research/rp-001-s2/src/rp001_s2/toss_batch_collection.py`
- Test: `research/rp-001/tests/test_local_evidence_contract.py`
- Test: `research/rp-001-s2/tests/test_toss_batch_collection.py`

- [ ] Add a failing test that appends three records in one ledger transaction and asserts that `_validate_existing_entries` is called only for the initial state and transaction-exit verification.
- [ ] Add a failing test that modifies a published record before transaction exit and asserts that full final verification rejects it.
- [ ] Run the two focused tests and confirm the expected call-count and tamper-detection failures.
- [ ] Cache the validated tail inside `LocalLedgerTransaction`, validate each newly published record and sidecar against that tail, and perform a complete `transaction.validate()` at clean transaction exit.
- [ ] Wrap the complete scope loop in `run_toss_minute_batch` in one ledger transaction and append terminal events through that transaction.
- [ ] Run `test_local_evidence_contract.py` and `test_toss_batch_collection.py` and confirm GREEN.

### Task 2: Provider-safe four-request-per-second pacing

**Files:**
- Modify: `research/rp-001-s2/src/rp001_s2/toss_batch_collection.py`
- Test: `research/rp-001-s2/tests/test_toss_batch_collection.py`

- [ ] Replace the existing one-second test with a failing test that expects the default interval to be 250 ms and four calls to span at least 750 ms under a deterministic clock.
- [ ] Add a failing boundary test that rejects an interval below 210 ms and accepts 250 ms.
- [ ] Run the focused pacer tests and confirm RED against the one-second implementation.
- [ ] Separate the 210 ms absolute floor from the 250 ms default and keep the existing global lock and monotonic-clock behavior.
- [ ] Run the focused pacer and full batch tests and confirm GREEN.

### Task 3: Lazy batch-scoped Toss authentication

**Files:**
- Modify: `research/rp-001-s2/src/rp001_s2/toss_intraday_run.py`
- Modify: `research/rp-001-s2/src/rp001_s2/toss_batch_collection.py`
- Test: `research/rp-001-s2/tests/test_toss_intraday_run.py`
- Test: `research/rp-001-s2/tests/test_toss_batch_collection.py`

- [ ] Add a failing batch test with two unarchived scopes asserting one credential load, one session creation, two scope collections, and one session close.
- [ ] Preserve and run the resumed-only test asserting zero credential and session access.
- [ ] Add a failing session test proving that two scope collections share one authenticated opener/token and that closing clears further use.
- [ ] Introduce a `TossMinuteSession` that authenticates once, validates each scope through the existing strict transport, and clears its token on close.
- [ ] Implement the existing single-shard entry point with a temporary session and make the batch open its session lazily and close it in `finally`.
- [ ] Run both intraday and batch test modules and confirm GREEN.

### Task 4: Verify and resume the live collection

**Files:**
- No production format or frozen plan changes.

- [ ] Run the relevant unit suites with the repository's pinned external Python packages.
- [ ] Run the complete RP-001-S2 test suite and confirm zero failures.
- [ ] Stop the legacy collector only after the last atomic scope publication returns.
- [ ] Verify the last archive manifest, sidecar, canonical Parquet hashes, and ledger chain.
- [ ] Restart the same supervisor against the same plan, archive root, ledger root, and credential file.
- [ ] Measure at least 100 live candle responses and report request rate, HTTP failure count, new terminal scopes, new rows, and preserved zero order/account/asset calls.
