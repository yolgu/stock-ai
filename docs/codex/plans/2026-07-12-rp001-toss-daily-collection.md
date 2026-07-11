# RP-001 Toss Daily Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and start a resume-safe Toss daily collector for the 48 registered instruments while freezing the full eligible US universe for later execution.

**Architecture:** Add a daily-specific scope plan, canonical archive, and batch orchestrator around the existing strict Toss daily transport. Run the active phase at 0.1 requests/second and keep the all-universe phase deferred until minute collection is terminal.

**Tech Stack:** Python 3, unittest, PyArrow/Parquet ZSTD, zstandard, append-only local evidence ledger.

---

### Task 1: Deterministic daily scope plan

**Files:**
- Create: `research/rp-001-s2/src/rp001_s2/daily_scope_plan.py`
- Test: `research/rp-001-s2/tests/test_daily_scope_plan.py`

- [ ] Write tests proving one whole-period scope per symbol and adjustment, stable sorted identities, seen/unseen acquisition equivalence, and deferred all-universe status.
- [ ] Run the focused test and confirm it fails because the module is absent.
- [ ] Implement the smallest immutable plan model and canonical JSON representation.
- [ ] Run the focused test and confirm it passes.

### Task 2: Immutable daily archive

**Files:**
- Create: `research/rp-001-s2/src/rp001_s2/daily_archive_storage.py`
- Create: `research/rp-001-s2/src/rp001_s2/toss_daily_canonicalization.py`
- Test: `research/rp-001-s2/tests/test_daily_archive_storage.py`
- Test: `research/rp-001-s2/tests/test_toss_daily_canonicalization.py`

- [ ] Write tests for raw ZSTD preservation, Parquet lineage, conflicting duplicate rejection, immutable write-once behavior, verification, and tamper rejection.
- [ ] Run the focused tests and confirm the missing production APIs fail.
- [ ] Implement canonical daily rows, raw capture lineage reconstruction, atomic archive publication, and verification.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Secure Toss daily batch runner

**Files:**
- Create: `research/rp-001-s2/src/rp001_s2/toss_daily_collection.py`
- Create: `research/rp-001-s2/collect_toss_daily.py`
- Test: `research/rp-001-s2/tests/test_toss_daily_collection.py`

- [ ] Write tests for GET-only scope enforcement, one ephemeral authentication per bounded batch, 10-second default pacing, verified resume without authentication, terminal ledger events, and failure capture preservation.
- [ ] Run the focused test and confirm it fails because the runner is absent.
- [ ] Implement the session, collector orchestration, archive resume, and CLI supervisor.
- [ ] Run the focused test and confirm it passes.

### Task 4: Freeze plans and start collection

**Files:**
- Runtime artifacts: `.storage/rp-001-data/daily-scope-plans-v1/`
- Runtime artifacts: `.storage/rp-001-data/daily-archives-v1/`
- Runtime artifacts: `.storage/rp-001-data/toss-daily-ledger-v1/`
- Runtime artifact: `.storage/rp-001-data/provider-blockers-v1/alpaca.json`

- [ ] Run all RP-001-S2 tests and confirm no regression.
- [ ] Generate canonical plans for the registered 48 instruments and 10,864 eligible US symbols with SHA-256 sidecars.
- [ ] Record Alpaca as `blocked_missing_credentials` without credential names or values.
- [ ] Start the registered-instrument plan at `--requests-per-second 0.1` and two scopes per authenticated batch.
- [ ] Verify the process is alive, the ledger and archive counts increase, HTTP status remains successful, and secret scans return zero findings.
