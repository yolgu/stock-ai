# Multistate Quant Research Campaign V3 Implementation Plan

> **For implementation:** Use executing-plans inline in the current session to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale binary V2 data wait with an exact-Goal-bound V3 campaign, a lineage-complete five-target development release, and real purged walk-forward OOF evidence built from immutable local daily archives.

**Architecture:** Add `rp001.autonomy_v3` beside immutable V2. Domain contracts define Goal, targets, rows, folds, releases, and campaign state; infrastructure adapters verify immutable Parquet archives and append-only artifacts; application services build features/labels, execute fold-local models, publish a canonical release, and register it into a new V3 campaign.

**Tech Stack:** Python 3.12, `unittest`, standard-library dataclasses/JSON/hashlib, NumPy 2.3.5, PyArrow 19.0.1, existing `rp001.local_evidence` append-only storage.

---

## File map

- Create `research/rp-001/src/rp001/autonomy_v3/contracts.py`: exact Goal, target, row, fold, release, and campaign domain contracts.
- Create `research/rp-001/src/rp001/autonomy_v3/archive_reader.py`: verified read-only adapter for immutable daily archive manifests and Parquet.
- Create `research/rp-001/src/rp001/autonomy_v3/features.py`: point-in-time daily feature calculations.
- Create `research/rp-001/src/rp001/autonomy_v3/labels.py`: future-only five-target onset labels and censoring.
- Create `research/rp-001/src/rp001/autonomy_v3/folds.py`: session-level purge/validation/embargo construction.
- Create `research/rp-001/src/rp001/autonomy_v3/oof.py`: fold-local binary logistic baselines/candidates and multilabel metrics.
- Create `research/rp-001/src/rp001/autonomy_v3/release_builder.py`: dataset assembly and canonical release publication.
- Create `research/rp-001/src/rp001/autonomy_v3/controller.py`: V3 bootstrap, release registration, status, and next action.
- Create `research/rp-001/src/rp001/autonomy_v3/cli.py` and `research/rp-001/quant_autonomous_research_v3.py`: internal CLI.
- Create `research/rp-001/autonomy-v3/requirements.lock.txt`: reproducible PyArrow dependency.
- Create focused tests under `research/rp-001/tests/test_autonomy_v3_*.py`.
- Generate only under `research-data/releases/quant-research-v3/development/**` and `research/rp-001/autonomy-v3/campaigns/**`; never modify `.storage` or V2 roots.

### Task 1: Exact Goal and domain contracts

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/__init__.py`
- Create: `research/rp-001/src/rp001/autonomy_v3/contracts.py`
- Test: `research/rp-001/tests/test_autonomy_v3_contracts.py`

- [ ] **Step 1: Write failing exact-binding and invariant tests**

```python
def test_campaign_id_binds_exact_goal_and_preset() -> None:
    source = "[QUANT_RESEARCH_GOAL]\n\n시점 t까지 이용 가능한 시장 데이터로...".encode()
    binding = GoalBindingV3.from_bytes(source)
    assert binding.campaign_id.startswith("QR3-CAMPAIGN-")
    assert binding.goal_sha256 == sha256(source).hexdigest()

def test_row_rejects_future_feature_and_nonfuture_label() -> None:
    with self.assertRaisesRegex(ContractError, "feature_time_invalid"):
        DevelopmentRowV3.fixture(feature_available_at="2024-01-03", as_of="2024-01-02")
    with self.assertRaisesRegex(ContractError, "label_time_invalid"):
        DevelopmentRowV3.fixture(label_available_at="2024-01-02", as_of="2024-01-02")
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `PYTHONPATH=research/rp-001/src /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s research/rp-001/tests -p 'test_autonomy_v3_contracts.py' -v`

Expected: import failure for `rp001.autonomy_v3.contracts`.

- [ ] **Step 3: Implement precise immutable contracts**

```python
class FormationTarget(str, Enum):
    UPSIDE_ACCELERATION_ONSET = "upside_acceleration_onset"
    DOWNSIDE_DISLOCATION_ONSET = "downside_dislocation_onset"
    POST_RALLY_SELL_PRESSURE_ONSET = "post_rally_sell_pressure_onset"
    SELLOFF_REVERSAL_ONSET = "selloff_reversal_onset"
    EFFICIENT_UPTREND_ONSET = "efficient_uptrend_onset"

@dataclass(frozen=True)
class GoalBindingV3:
    source: bytes
    goal_sha256: str
    campaign_id: str

    @classmethod
    def from_bytes(cls, source: bytes) -> "GoalBindingV3":
        digest = sha256(source).hexdigest()
        campaign_digest = sha256(source + b"\0quant-multistate-discovery.v3").hexdigest()
        return cls(source, digest, f"QR3-CAMPAIGN-{campaign_digest[:20].upper()}")
```

Require exact enums, ISO timestamps, unique row ID, finite numeric features, horizons `{1,3,5,10}`, explicit `available|censored|not_applicable`, and canonical `to_dict()` output for every public artifact.

- [ ] **Step 4: Run focused tests and commit**

Run: `PYTHONPATH=research/rp-001/src /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s research/rp-001/tests -p 'test_autonomy_v3_contracts.py' -v`

Expected: PASS.

Commit: `feat(research): add multistate v3 contracts`

### Task 2: Verified immutable archive reader

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/archive_reader.py`
- Create: `research/rp-001/autonomy-v3/requirements.lock.txt`
- Test: `research/rp-001/tests/test_autonomy_v3_archive_reader.py`

- [ ] **Step 1: Write failures for hash, role, mode, and lineage**

```python
def test_reader_accepts_only_seen_daily_archives() -> None:
    reader = ImmutableDailyArchiveReader(root)
    archive = reader.open_manifest(manifest)
    self.assertEqual("seen", archive.sample_role)
    self.assertEqual("1d", archive.interval)

def test_reader_rejects_confirmation_role_and_hash_mismatch() -> None:
    with self.assertRaisesRegex(ArchiveReadError, "sample_role_denied"):
        reader.open_manifest(confirmation_manifest)
    with self.assertRaisesRegex(ArchiveReadError, "canonical_digest_mismatch"):
        reader.load(tampered_manifest)
```

- [ ] **Step 2: Run RED, then implement a read-only port**

`ImmutableDailyArchiveReader.discover()` must ignore `failure-evidence`, require canonical manifest bytes and sidecar, require `scope.sampleRole == "seen"`, `scope.interval == "1d"`, validate acquisition key and Parquet SHA-256, and return typed `DailyBar` tuples without writing to the source tree.

Pin:

```text
pyarrow==19.0.1
```

- [ ] **Step 3: Verify real archive discovery without reading confirmation roots**

Run: `PYTHONPATH=research/rp-001/src:/Users/jik/.cache/codex-runtimes/quant-research-v3 /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s research/rp-001/tests -p 'test_autonomy_v3_archive_reader.py' -v`

Expected: 48 unique symbols, one native and one adjusted completed archive per symbol, manifest and Parquet hashes valid.

- [ ] **Step 4: Commit**

Commit: `feat(research): add immutable daily archive reader`

### Task 3: Point-in-time features and five target labels

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/features.py`
- Create: `research/rp-001/src/rp001/autonomy_v3/labels.py`
- Test: `research/rp-001/tests/test_autonomy_v3_features.py`
- Test: `research/rp-001/tests/test_autonomy_v3_labels.py`

- [ ] **Step 1: Write feature invariance and boundary tests**

```python
def test_future_rows_do_not_change_features_at_t() -> None:
    prefix = engine.compute(rows[:180])[-1]
    extended = engine.compute(rows[:180] + adversarial_future_rows)[179]
    self.assertEqual(prefix, extended)

def test_scale_change_preserves_atr_normalized_features() -> None:
    self.assertAlmostEqual(
        engine.compute(rows)[-1].atr_return,
        engine.compute(scale_prices(rows, 100.0))[-1].atr_return,
    )
```

- [ ] **Step 2: Implement shared formulas with explicit return types**

Implement prior-only median/MAD RZ120, ATR20, returns 1/3/5/10/20, acceleration, breakout/breakdown, range position, directional efficiency, RVOL20, log-volume RZ120, wick/close position, run-up/drawdown, SPY excess return, sector ETF excess return, and fixed-cohort breadth. A required missing value returns an explicit `FeatureUnavailable` instead of zero.

- [ ] **Step 3: Write synthetic label scenarios**

```python
def test_labels_use_future_only_and_preserve_same_bar_ambiguity() -> None:
    result = labeler.label(row_index, horizon=5)
    self.assertEqual("both_same_bar_ambiguous", result.path_outcome)
    self.assertEqual("censored", result.status)

def test_profit_taking_requires_prior_runup() -> None:
    self.assertEqual("not_applicable", flat_result.status)
    self.assertEqual(1, post_rally_reversal.label)
```

- [ ] **Step 4: Implement frozen label rules**

Use current native features only for eligibility; adjusted future prices only for path labels; preserve up-first/down-first/same-bar/neither; require complete future coverage; and emit target-specific labels for all four horizons. Record every threshold in `LabelContractV3.to_dict()`.

- [ ] **Step 5: Run focused tests and commit**

Expected: future mutation, flat series, zero volume, split-like jump, same-bar ambiguity, FOMO, panic, post-rally sell pressure, recovery, and efficient uptrend scenarios all PASS.

Commit: `feat(research): add multistate features and labels`

### Task 4: Session folds and real fold-local OOF

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/folds.py`
- Create: `research/rp-001/src/rp001/autonomy_v3/oof.py`
- Test: `research/rp-001/tests/test_autonomy_v3_oof.py`

- [ ] **Step 1: Write tests proving no whole-dataset fitting**

```python
def test_validation_label_mutation_does_not_change_fold_model() -> None:
    original = evaluator.fit_fold(rows, fold)
    mutated = evaluator.fit_fold(mutate_validation_labels(rows, fold), fold)
    self.assertEqual(original.model_sha256, mutated.model_sha256)

def test_same_session_never_crosses_train_validation_boundary() -> None:
    folds = build_expanding_folds(axis, purge=10, embargo=10)
    assert_session_groups_are_disjoint(folds, rows)
```

- [ ] **Step 2: Implement expanding folds and deterministic logistic models**

```python
@dataclass(frozen=True)
class FoldModel:
    target: FormationTarget
    horizon: int
    intercept: float
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    model_sha256: str
```

Fit normalizers and ridge-logistic coefficients from training rows only, select regularization from an inner purged split, predict outer validation once, and serialize fold models plus row identities. Include prevalence and single-feature baselines on the identical validation mask.

- [ ] **Step 3: Implement metrics and multiplicity inputs**

Calculate target/horizon Brier, log loss, PR-AUC, MCC, ECE, coverage, and onset lead sessions. Preserve per-row loss vectors for synchronized session/instrument block bootstrap and later multiplicity correction.

- [ ] **Step 4: Run tests and commit**

Commit: `feat(research): add real purged multistate oof`

### Task 5: Canonical V3 development release builder

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/release_builder.py`
- Test: `research/rp-001/tests/test_autonomy_v3_release_builder.py`

- [ ] **Step 1: Write end-to-end fixture test**

```python
def test_builder_publishes_bound_release_without_mutating_sources() -> None:
    before = hash_tree(source_root)
    release = builder.build(goal_binding, source_root, output_root)
    self.assertEqual(before, hash_tree(source_root))
    self.assertEqual(goal_binding.goal_sha256, release.goal_sha256)
    self.assertEqual(set(FormationTarget), set(release.target_coverage))
    self.assertTrue(release.oof_evidence_path.is_file())
```

- [ ] **Step 2: Implement deterministic assembly**

Read paired native/adjusted archives, join by instrument/session, build market/sector/cohort features, create eligible target/horizon rows, build folds, execute OOF, and publish Parquet tables plus canonical JSON manifests through a staging directory followed by atomic rename. Bind every artifact path, byte count, row count, schema fingerprint, and SHA-256.

- [ ] **Step 3: Reject incomplete coverage and source changes**

The builder fails if any target/horizon has no eligible positive and negative examples, source hashes change during the run, row IDs duplicate, a fold is empty, or feature/label timestamps violate the contract.

- [ ] **Step 4: Run tests and commit**

Commit: `feat(research): build canonical multistate release`

### Task 6: Goal-bound V3 controller and CLI

**Files:**
- Create: `research/rp-001/src/rp001/autonomy_v3/controller.py`
- Create: `research/rp-001/src/rp001/autonomy_v3/cli.py`
- Create: `research/rp-001/quant_autonomous_research_v3.py`
- Test: `research/rp-001/tests/test_autonomy_v3_controller.py`
- Test: `research/rp-001/tests/test_autonomy_v3_cli.py`

- [ ] **Step 1: Write bootstrap/register/status transition tests**

```python
snapshot = controller.bootstrap(exact_goal_path, occurred_at=NOW)
self.assertEqual("AWAITING_DEVELOPMENT_RELEASE", snapshot.state)
registered = controller.register_development_release(snapshot.campaign_id, manifest, occurred_at=NOW2)
self.assertEqual("READY_FOR_PREREGISTRATION", registered.state)
self.assertEqual("PREREGISTER_MULTISTATE_FORMATION", controller.next_action(registered.campaign_id).kind)
```

- [ ] **Step 2: Implement side-by-side campaign storage**

Store V3 under `research/rp-001/autonomy-v3/campaigns/QR3-CAMPAIGN-770B0655A846F354B10C`, reuse append-only ledger and canonical artifact primitives, bind exact Goal/data/release hashes, and publish a supersession record referencing V2 without writing its files.

- [ ] **Step 3: Add CLI commands**

Expose `bootstrap-campaign`, `build-development-release`, `register-development-release`, `status`, and `next`. Every command emits one canonical JSON object and generic error text without sensitive values.

- [ ] **Step 4: Run tests and commit**

Commit: `feat(research): add goal-bound multistate controller`

### Task 7: Produce and register the real local release

**Files:**
- Create: `research/rp-001/autonomy-v3/goals/6e4d4bec75f93d9c7040283afed0caf600b68b21fb5a4225b1d78f7c3e51163b/goal-request.json`
- Generate: `research-data/releases/quant-research-v3/development/DEV-MULTISTATE-20160101-20260711-V1/**`
- Generate: `research/rp-001/autonomy-v3/campaigns/QR3-CAMPAIGN-770B0655A846F354B10C/**`

- [ ] **Step 1: Install the locked runtime dependency outside source roots**

Run: `/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pip install --target /Users/jik/.cache/codex-runtimes/quant-research-v3 -r research/rp-001/autonomy-v3/requirements.lock.txt`

Expected: PyArrow 19.0.1 imports successfully without modifying repository source or bundled runtime.

- [ ] **Step 2: Bootstrap from the exact active Goal bytes**

Verify the goal file byte-for-byte against the active objective before bootstrap. Run V3 CLI with the absolute Goal path and current UTC timestamp.

- [ ] **Step 3: Build the real development release**

Run the builder against `.storage/rp-001-data/daily-archives-v1` and the V3 development output root. Do not access orders, accounts, assets, V2 confirmation content, or minute archives.

- [ ] **Step 4: Verify release evidence**

Run schema/hash/lineage verification, source-tree before/after hashes, target/horizon coverage, fold disjointness, future-row invariance, and OOF row identity checks. Save a canonical verification report and sidecar.

- [ ] **Step 5: Register and prove the blocker is removed**

Run `register-development-release`, followed by `status` and `next`.

Expected state: `READY_FOR_PREREGISTRATION`.

Expected next action: `PREREGISTER_MULTISTATE_FORMATION`.

- [ ] **Step 6: Commit only source, tests, lockfile, and reproducibility metadata**

Commit: `feat(research): unblock multistate development campaign`

Do not commit large generated data unless the repository policy explicitly tracks that output root.

### Task 8: Final verification checkpoint

**Files:**
- Verify all files changed by Tasks 1–7.

- [ ] **Step 1: Run focused V3 suite**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001/src:/Users/jik/.cache/codex-runtimes/quant-research-v3 /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s research/rp-001/tests -p 'test_autonomy_v3_*.py' -v`

Expected: all V3 tests PASS.

- [ ] **Step 2: Run affected V2 regression suite**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001/src /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s research/rp-001/tests -p 'test_autonomy_v2_*.py' -v`

Expected: all V2 tests PASS and V2 campaign bytes remain unchanged.

- [ ] **Step 3: Audit completion evidence**

Confirm exact Goal coverage, all five targets and four horizons, source lineage, actual fold-local predictions, generated release registration, non-waiting next action, no confirmation access, no source mutation, and no secret findings.

- [ ] **Step 4: Update the working plan**

Mark the data blocker complete and continue the autonomous scientific campaign from the verified V3 `next` action. Do not mark the full research Goal complete until candidate search, confirmation, risk, reproduction, and final decision Gates have terminal evidence.
