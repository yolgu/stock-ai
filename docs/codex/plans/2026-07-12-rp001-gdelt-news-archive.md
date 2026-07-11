# RP-001 GDELT News Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect and verify both GDELT daily news timeline modes for the frozen 48-instrument RP-001 universe.

**Architecture:** A single Python module owns the GDELT-only query contract, strict GET transport, global pacing, bounded retry, immutable raw publication, terminal manifests, and resume verification. Existing frozen scope and official directory artifacts remain the identity sources; no trading or app boundary is involved.

**Tech Stack:** Python 3.12 standard library, existing `rp001.local_evidence`, `unittest`.

---

### Task 1: Freeze query identities

**Files:**
- Create: `research/rp-001-s2/src/rp001_s2/gdelt_news_archive.py`
- Create: `research/rp-001-s2/tests/test_gdelt_news_archive.py`

- [ ] Write a failing test that loads the frozen scope and official directory fixtures and requires exactly 48 quoted company-name queries, with no raw ambiguous ticker query.
- [ ] Run `python -m unittest research/rp-001-s2/tests/test_gdelt_news_archive.py -v` and confirm the missing module/API failure.
- [ ] Implement immutable query-map construction with source SHA bindings and canonical serialization.
- [ ] Re-run the focused test and confirm GREEN.

### Task 2: Collect with one global worker

**Files:**
- Modify: `research/rp-001-s2/src/rp001_s2/gdelt_news_archive.py`
- Modify: `research/rp-001-s2/tests/test_gdelt_news_archive.py`

- [ ] Add failing tests for exact endpoint/method, 10-second request-start spacing, `TimelineVolRaw` plus `TimelineTone`, and 429 waits of 30/60/120 seconds followed by `provider_rate_limited`.
- [ ] Run the focused tests and confirm RED for missing collection behavior.
- [ ] Implement the strict transport and serial collection use case with injected clock, sleeper, and transport.
- [ ] Re-run focused tests and confirm GREEN.

### Task 3: Publish and verify immutable evidence

**Files:**
- Modify: `research/rp-001-s2/src/rp001_s2/gdelt_news_archive.py`
- Modify: `research/rp-001-s2/tests/test_gdelt_news_archive.py`

- [ ] Add failing tests for every attempt body/metadata sidecar, terminal manifest sidecar, network-free resume, and tamper rejection.
- [ ] Run focused tests and confirm RED.
- [ ] Implement content-addressed scope storage and complete archive verification using the existing local artifact store.
- [ ] Re-run the focused test, then all `research/rp-001-s2/tests`, and confirm GREEN or report unrelated failures exactly.

### Task 4: Execute the frozen live collection

**Files:**
- Data only: `.storage/rp-001-data/gdelt-news-v1/`

- [ ] Publish and verify the 48-entry query map.
- [ ] Collect TSLA, NVDA, AAPL first and verify every raw, metadata, manifest, and sidecar binding.
- [ ] Continue the remaining instruments through the same single worker without changing the map.
- [ ] Report completed, provider-rate-limited, failed, raw-response counts, query-map SHA, manifest SHA values, and remaining scopes.
