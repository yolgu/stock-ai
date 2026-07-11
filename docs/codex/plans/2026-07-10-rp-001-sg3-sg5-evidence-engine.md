# RP-001 SG3–SG5 Evidence Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GOAL-RP-001 v1.0의 SG3 수식·구현·보상해킹 감사부터 SG4 독립 연구, SG5 후보 비교, 외부·전향검증, 비용·위험·독립재현과 최종 DecisionRecord까지 실행하되, 자료가 없거나 식별할 수 없는 결과도 삭제하지 않는 증거 엔진을 만든다.

**Architecture:** `research/rp-001`에는 strict schema validator, canonical artifact/hash-chain, 수식·구현 결박, 사전 동결 설계, 실행·증거·결정 orchestration만 둔다. 연구 의미의 historical SSOT는 기존 `RQ-001..008`, `DC-001..008`, `SP-001..008`, 프로그램 원장에 두고, 현재 `proposed`인 `SP-003..008`의 bytes와 hash는 수정하지 않는다. 기존 v1 validator가 `research/meta-research/objects/**/object.json`을 재귀 탐색하므로 모든 신규 v2 descriptor와 body는 별도 root `research/meta-research/objects-v2/`에만 생성한다. v1 `objects/`, v1 catalog, v1 validator/test는 byte-for-byte 불변이고 신규 v2 validator만 `objects-v2/`를 탐색한다. `objects/programs/RP-001-quantitative-market-behavior/`에는 `object.json`이 아닌 append-only program event·projection만 둘 수 있다. 254개 요구사항 의미·적용성·완료 predicate, RequiredDeliverableRegistry와 8개 study terminal total-function은 `PreDataRuleFreeze`로 첫 empirical read 전에 봉인한다. `SP-015` ontology adjudication이 먼저 심리명칭의 사용 가능성을 판정하고, refuted/not-identifiable이면 downstream 이름을 `price_volume_regime`으로 동결한다. raw parsing·정규화·PIT timestamp·corporate-action·결측 처리는 `ProcessingCodeBundleManifest`로, feature·label·validation·metric·application·backend·terminal/evidence/decision/completion·reproduction 의미 코드는 `AnalysisCodeBundleManifest`로 그 뒤 동결한다. actual SourcePlanSetManifest의 모든 per-plan `eligible_metadata | exhausted_unavailable | nonterminal_blocked` outcome을 `SP-016`이 scoped DataLineageDisposition으로 audit·anchor하고 `DataLineageEligibilitySnapshot`을 발행한 뒤, multi-input StudyCandidateAdmission이 각 formula의 mandatory input scope만 검사해 unaffected branches를 골라야 empirical promotion을 시작할 수 있다. 설계 DAG는 정확히 `8A DesignCore → 9A SuccessorProtocolCore(s) → 8B PlannedRunKey grid/six-digit ReservationManifest/final CD → 9B final successor protocols → ReservationLineageBindingEvent/external receipt`이며 각 unit은 별도 RED, GREEN, review를 갖는다. 이후에만 admitted branch별 RawCollectionAuthorization을 발행한다. collection reader와 analysis reader를 분리하고 모든 단계는 직전 artifact hash, 두 frozen code-bundle hash와 externally anchored predecessor receipt를 요구한다.

**Tech Stack:** Python 3.12.13 표준 라이브러리, 현재 bundled NumPy 2.3.5·pandas 2.2.3, canonical JSON, JSON Schema 문서, SHA-256 hash-chain, `unittest`, Markdown, 기존 meta-research catalog. scipy/sklearn/statsmodels/pymc/jax/torch는 현재 없으며, 표준/NumPy 경로 밖 통계·모형 backend는 versioned dependency lock·wheel/source hash·environment hash·SVR 합성검증·재현성 비교를 통과한 별도 `BackendDecision`으로만 추가한다.

## Strict executable TDD contract

모든 구현 unit은 같은 순서를 따른다. 먼저 named behavioral assertion이 있는 test file을 작성한다. 다음으로 import만 성립시키는 최소 counterexample 구현을 작성하되, 그 구현은 unit에 명시된 잘못된 concrete result를 실제로 반환해야 한다. 그 뒤 exact test command를 실행하여 명시된 assertion failure를 확인한다. import, module discovery, syntax, file-existence 실패는 RED 증거로 인정하지 않는다. 최소 올바른 구현을 작성한 뒤 test file과 command를 바꾸지 않고 같은 exact command를 GREEN으로 다시 실행한다. RED와 GREEN output hash, 실행시각, test count와 reviewer binding을 unit checkpoint에 보존한다. test command가 RED와 GREEN 중 한쪽에만 나타나는 unit은 완료되지 않은 것으로 판정한다.

API 계약은 body-free text signature table로만 표기한다. 구현 설명은 입력 정규화, closed-world validation, canonical serialization, append transaction, 반환값 순서로 작성한다. executable snippet은 모든 branch가 concrete value를 반환하고 표준 라이브러리 import와 사용 타입을 같은 block 안에서 정의해야 한다.

다음 최소 구현은 이후 unit이 그대로 확장하는 공통 알고리즘이다.

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

METADATA_CLASS_UNIVERSE = frozenset({
    "instrument_identity",
    "trading_calendar",
    "coverage_bounds",
    "field_catalog",
})


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def sha256_canonical_json(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def validate_metadata_classes(
    declared: frozenset[str],
    actual: frozenset[str],
) -> None:
    if not declared <= METADATA_CLASS_UNIVERSE:
        raise ValueError("declared metadata class is outside the closed universe")
    if actual != declared:
        raise ValueError("actual metadata classes differ from the frozen subset")


def validate_credential_contract(
    provider_auth_requirement: str,
    credential_status: str,
    credential_event_ids: Sequence[str],
) -> None:
    expected = "rotated" if provider_auth_requirement == "required" else "not_required"
    if provider_auth_requirement not in {"required", "public"}:
        raise ValueError("unknown provider authentication requirement")
    if credential_status != expected:
        raise ValueError("credential status conflicts with provider requirement")
    if provider_auth_requirement == "public" and credential_event_ids:
        raise ValueError("public source cannot depend on credential events")


def build_planned_run_key(fields: Mapping[str, str | int]) -> str:
    required = {
        "studySlot",
        "designCoreSha256",
        "protocolCoreSha256",
        "inputContractOrSnapshotSha256",
        "candidateOrControlId",
        "sampleRole",
        "foldId",
        "horizon",
        "seed",
        "implementationBindingSha256",
        "processingCodeBundleManifestSha256",
        "analysisCodeBundleManifestSha256",
    }
    if set(fields) != required:
        raise ValueError("planned run key fields are not exact")
    return sha256_canonical_json(dict(fields))


def validate_formula_matrix(
    formula_ids: frozenset[str],
    obligation_ids: frozenset[str],
    cells: Sequence[Mapping[str, str]],
) -> None:
    expected = {(formula_id, obligation_id) for formula_id in formula_ids for obligation_id in obligation_ids}
    actual = {(cell["formulaId"], cell["obligationId"]) for cell in cells}
    if actual != expected or len(cells) != len(expected):
        raise ValueError("formula audit matrix is not a bijection")
    allowed = {"proof", "counterexample", "not_applicable_with_predicate"}
    if any(cell["cellResult"] not in allowed for cell in cells):
        raise ValueError("formula audit cell result is invalid")
```

---

## Current evidence baseline

계획 실행자는 다음 관찰을 새 연구결과로 재해석하지 않고 출발점으로 고정한다.

| 영역 | 현재 증거 | 실행 의미 |
| --- | --- | --- |
| 요구사항 | `requirements.json` 254개, 질문·study 등록 추적 254/254 | evidence·decision·report 역추적은 SG3–SG5에서 채운다. |
| study | `RQ/DC/SP` 8개 chain, `SP-003..008`은 `proposed/conceptual` | 현재 문서는 사전등록이나 확인근거가 아니다. |
| 후보 모형족 | 11개 family 중 `MC-001`만 객체화, 나머지는 `registry_only` | family 이름만으로 실행하지 않는다. |
| 기존 수식 원장 | 224식: `valid` 18, `repairable` 32, `proxy_only` 74, `reject` 30, `not_identifiable` 70 | 이 값은 historical `sourceDisposition` provenance일 뿐 현재 math disposition이나 채택이 아니다. 모든 FormulaRecord는 `auditStatus=unassessed`로 등록한다. |
| 기존 후보 | RB-001의 19개 candidate와 Jeffreys `Beta(0.5,0.5)` training-only base rate | FormulaRecord가 아니라 DR-001 감사 전용 `CandidateAuditAliasRecord` 20개로 격리하고 `empiricalEligibility=false`다. |
| 기존 등가성 | 원장상 `equivalent` 표기 52개이나 독립 reference 계산기는 composite 3개 중심 | 구조 매핑을 수치 등가성 증거로 간주하지 않고 19개 candidate를 각각 검증한다. |
| 현재 자료 | Toss 문서 감사상 8개 입력군이 `limited/data_unavailable`; ordered event·PIT 기업행동·직접 행동자료가 불완전 | probe credential은 operational exposure 전용이며 raw 저장은 `blocked_pending_rotated_credentials_and_provider_retention_and_redistribution_clarification`을 유지한다. |
| read-only operational exposure | 사용자가 Toss read-only 연구 호출을 승인했고, 기존 mode `0600`·Git-ignored local credential file을 기존 OAuth 경계가 읽어 2026-07-10 OAuth와 `GET /api/v1/stocks?symbols=MU`의 HTTP 200/result count 1을 확인했다. key/token/response body 저장·출력과 주문/account 호출은 0이다. | accepted raw market dataset, CD 또는 G7 evidence가 아니다. foundation의 `liveApiCalled=false` historical snapshot은 소급수정하지 않고 새 current metadata-only event로만 기록한다. |
| 기존 표본 | `seen-data-register.json`의 모든 심볼·기간·원자료 노출은 `seen_development_data` | G7 terminal prospective evidence로 재사용하지 않는다. |
| RB 경계 | `DR-001=research_only`, 생성계보와 G9 독립재현 미확인 | 실패 재현·금지조건·seen 경계 외 성능/채택 근거로 쓰지 않는다. |

## Concrete candidate portfolio

SG3 current FormulaRecord registry는 `formulaRegistryIds = historicalFormulaIds ∪ newRpEmpiricalFormulaIds` exact set만 가진다. 아래 RB 20개 ID는 FormulaRecord가 아니라 별도 alias registry의 `CandidateAuditAliasRecord`다. 두 registry의 ID 교집합은 정확히 0이어야 하며 alias는 empirical/CD/G6~G10 경로로 들어갈 수 없다. 새 RP FormulaRecord의 입력·단위·availability·ImplementationBinding이 불완전하면 `blocked`이고 실행기가 거부한다.

### 기존 19개 RB candidate와 base rate audit aliases

```text
fomo.documented
fomo.equal
fomo.deduplicated
fomo.baseline.momentum5
fomo.baseline.volume20
fomo.baseline.breakout20
panic.documented
panic.equal
panic.deduplicated
panic.baseline.drawdown3
panic.baseline.volume20
panic.baseline.lowBreak20
potentialPtp.documented
potentialPtp.equal
potentialPtp.breadth
potentialPtp.baseline.runup20
potentialPtp.baseline.vwapExtension
relief.originalProxy
relief.persistenceGated
baseline.jeffreys_rate.v1
```

위 exact `rbCandidateAuditAliasIds` 20개는 모두 `CandidateAuditAliasRecord`이며 `provenanceLane=RB-001-audit`, `empiricalEligibility=false`, `allowedUses=[failure_reproduction_descriptive_defect_evidence, prohibited_condition_design, seen_development_data_boundary_identification]`로 고정한다. `rbCandidateAuditAliasIds ∩ formulaRegistryIds = ∅`가 정상이다. RB의 performance, results, threshold, weight 또는 selection을 G6~G10이나 empirical candidate 선택에 사용할 수 없다.

### 11개 필수 family의 concrete coverage

| family | concrete FormulaRecord ID | 초기 실행자격 |
| --- | --- | --- |
| `unconditional` | `rp001.control.beh.unconditional.jeffreys.v1` | 새 FormulaRecord/reference와 training-only fit 계약 필요 |
| `simple_price_volume` | 아래 study별 `control.*` ID | accepted price/unit/time input이 있을 때만 허용 |
| `legacy_weighted_sum` | `rp001.legacy.fomo_chart.v1`, `rp001.legacy.panic_chart.v1`, `rp001.legacy.potential_ptp.v1` | 원문 docs에서 새로 versioned한 식·reference만 허용 |
| `repair_candidate` | `rp001.repair.fomo_deduplicated.v1`, `rp001.repair.panic_deduplicated.v1`, `rp001.repair.potential_ptp_breadth.v1`, `rp001.repair.relief_persistence.v1` | pre-data immutable `EligibilityDecision`이 식·binding·감사 자격만 승인한 경우 허용; DR-002/003은 post-evidence 판정 전용 |
| `bayesian_competing_risk` | `rp001.mc001.discrete_competing_risk.v1` | P4와 BackendDecision 통과 전 blocked |
| `hmm_hsmm` | `rp001.mc001.explicit_duration_hsmm.v1` | P4와 상태명 Gate 통과 전 `latent_state.k`만 허용 |
| `dynamic_relative_value` | `rp001.val.dynamic_point_in_time_factor.v1` | PIT universe/factor/revision 수락 전 blocked |
| `prospect_reference_price` | `rp001.val.prospect_reference_distribution.v1` | shares/corporate-action/unit 수락 전 blocked |
| `ofi_depth_hawkes` | `rp001.mic.ordered_ofi_depth_hawkes.v1` | ordered event feed 수락 전 blocked; snapshot 대체 금지 |
| `execution_control` | `rp001.exe.fill_cost_stochastic_control.v1` | order lifecycle/cost distribution 수락 전 blocked |
| `nonlinear` | `rp001.nonlinear.gradient_boosted_tree.v1`, `rp001.nonlinear.temporal_neural_model.v1` | backend·동일 정보·동일 fold 결박 전 blocked |

### Study별 required exact control set

| study | exact required control IDs |
| --- | --- |
| `ST-BEH-001` | `rp001.control.beh.unconditional.jeffreys.v1`, `rp001.control.beh.price_only_regime.v1` |
| `ST-VAL-001` | `rp001.control.val.price_factor.v1`, `rp001.control.val.momentum20.v1`, `rp001.control.val.mean_reversion20.v1` |
| `ST-MIC-001` | `rp001.control.mic.price_history.v1` |
| `ST-EXE-001` | `rp001.control.exe.no_trade.v1`, `rp001.control.exe.fixed_simple_execution.v1` |
| `ST-RSK-001` | `rp001.control.rsk.no_trade.v1`, `rp001.control.rsk.fixed_simple_risk.v1` |
| `ST-SYN-001` | `rp001.control.syn.no_trade.v1`, `rp001.control.syn.buy_hold.v1`, `rp001.control.syn.fixed_simple_strategy.v1`, `rp001.control.syn.eligible_single_study.v1` |

각 study의 `requiredControlIds`는 위 집합과 set-equality로 같아야 한다. CD의 `eligibleCandidateIds`는 `empiricalEligibility=true`, accepted input, verified binding을 모두 만족한 새 RP FormulaRecord의 결과 독립적 exact set이며, 위 required controls를 항상 포함한다.

## File and responsibility map

### Contract and engine code

```text
research/rp-001/schemas/formula-record.schema.json
research/rp-001/schemas/candidate-audit-alias-record.schema.json
research/rp-001/schemas/implementation-binding.schema.json
research/rp-001/schemas/formula-audit.schema.json
research/rp-001/schemas/formula-obligation-matrix-cell.schema.json
research/rp-001/schemas/math-disposition-event.schema.json
research/rp-001/schemas/formula-audit-coverage-certificate.schema.json
research/rp-001/schemas/eligibility-decision.schema.json
research/rp-001/schemas/study-candidate-admission.schema.json
research/rp-001/schemas/audit-execution.schema.json
research/rp-001/schemas/audit-execution-reservation.schema.json
research/rp-001/schemas/synthetic-verification-run.schema.json
research/rp-001/schemas/synthetic-verification-reservation.schema.json
research/rp-001/schemas/study-terminal-event.schema.json
research/rp-001/schemas/terminal-decision-computation.schema.json
research/rp-001/schemas/lifecycle-event.schema.json
research/rp-001/schemas/artifact-binding.v2.schema.json
research/rp-001/schemas/artifact-external-anchor-binding-event.schema.json
research/rp-001/schemas/research-graph-snapshot.v2.schema.json
research/rp-001/schemas/source-metadata-acceptance.schema.json
research/rp-001/schemas/design-metadata-capture-authorization.schema.json
research/rp-001/schemas/universe-metadata-snapshot.schema.json
research/rp-001/schemas/raw-collection-authorization.schema.json
research/rp-001/schemas/raw-capture-manifest.schema.json
research/rp-001/schemas/processing-authorization.schema.json
research/rp-001/schemas/processed-manifest.schema.json
research/rp-001/schemas/source-availability-search-plan.schema.json
research/rp-001/schemas/source-plan-set-manifest.schema.json
research/rp-001/schemas/source-plan-outcome.schema.json
research/rp-001/schemas/source-availability-closure.schema.json
research/rp-001/schemas/data-lineage-disposition.schema.json
research/rp-001/schemas/data-lineage-eligibility-snapshot.schema.json
research/rp-001/schemas/confirmation-design.schema.json
research/rp-001/schemas/experiment-run.schema.json
research/rp-001/schemas/run-id-reservation-manifest.schema.json
research/rp-001/schemas/reservation-lineage-binding-event.schema.json
research/rp-001/schemas/actual-run-lineage-binding-event.schema.json
research/rp-001/schemas/append-transaction-intent.schema.json
research/rp-001/schemas/append-transaction-commit.schema.json
research/rp-001/schemas/append-recovery-event.schema.json
research/rp-001/schemas/external-head-anchor-receipt.schema.json
research/rp-001/schemas/executor-identity-binding.schema.json
research/rp-001/schemas/reproduction-rights-attestation.schema.json
research/rp-001/schemas/reproduction-attestation.schema.json
research/rp-001/schemas/independent-reviewer-attestation.schema.json
research/rp-001/schemas/reproduction-input-authorization.schema.json
research/rp-001/schemas/reproduction-manifest.schema.json
research/rp-001/schemas/evidence-cli-command-dispatch-registry.schema.json
research/rp-001/schemas/study-terminal-decision-rules.schema.json
research/rp-001/schemas/ontology-name-mapping.schema.json
research/rp-001/schemas/analysis-code-bundle-manifest.schema.json
research/rp-001/schemas/processing-code-bundle-manifest.schema.json
research/rp-001/schemas/evidence-bundle.schema.json
research/rp-001/schemas/decision-record.schema.json
research/rp-001/schemas/completion-obligation.schema.json
research/rp-001/schemas/completion-observation-binding-event.schema.json
research/rp-001/schemas/completion-predicate-registry.schema.json
research/rp-001/schemas/gate-applicability-rules.schema.json
research/rp-001/schemas/requirement-obligation-definitions.schema.json
research/rp-001/schemas/predata-rule-freeze.schema.json
research/rp-001/schemas/required-deliverable-registry.schema.json
research/rp-001/src/rp001/canonical_artifact.py
research/rp-001/src/rp001/external_head_anchor.py
research/rp-001/src/rp001/append_transaction.py
research/rp-001/src/rp001/evidence_contracts.py
research/rp-001/src/rp001/audit_execution.py
research/rp-001/src/rp001/formula_obligation_matrix.py
research/rp-001/src/rp001/formula_obligation_auditors.py
research/rp-001/src/rp001/formula_audit_cell_publisher.py
research/rp-001/src/rp001/analysis_code_bundle.py
research/rp-001/src/rp001/processing_code_bundle.py
research/rp-001/src/rp001/formula_registry.py
research/rp-001/src/rp001/candidate_calculators.py
research/rp-001/src/rp001/reference_calculators.py
research/rp-001/src/rp001/metamorphic_audit.py
research/rp-001/src/rp001/trial_ledger.py
research/rp-001/src/rp001/hsmm_competing_risk_contract.py
research/rp-001/src/rp001/source_acceptance.py
research/rp-001/src/rp001/source_availability.py
research/rp-001/src/rp001/credential_broker.py
research/rp-001/src/rp001/read_only_toss_adapter.py
research/rp-001/src/rp001/external_raw_sink.py
research/rp-001/src/rp001/external_artifact_locator.py
research/rp-001/src/rp001/collection_reader.py
research/rp-001/src/rp001/analysis_reader.py
research/rp-001/src/rp001/data_lineage_terminalization.py
research/rp-001/src/rp001/study_candidate_admission.py
research/rp-001/src/rp001/data_lineage_registers.py
research/rp-001/src/rp001/research_graph.py
research/rp-001/src/rp001/confirmation_design.py
research/rp-001/src/rp001/experiment_run.py
research/rp-001/src/rp001/executor_identity.py
research/rp-001/src/rp001/validation_design.py
research/rp-001/src/rp001/evidence_synthesis.py
research/rp-001/src/rp001/program_completion.py
research/rp-001/src/rp001/completion_predicates.py
research/rp-001/src/rp001/terminal_decision_computation.py
research/rp-001/src/rp001/study_terminal_publisher.py
research/rp-001/src/rp001/source_plan_set.py
research/rp-001/src/rp001/source_impact_terminalizer.py
research/rp-001/src/rp001/evidence_cli_contract.py
research/rp-001/contracts/evidence-cli-command-dispatch-registry.json
research/rp-001/contracts/evidence-cli-command-dispatch-registry.json.sha256
research/rp-001/freeze_predata_rules.py
research/rp-001/run_evidence_engine.py
```

`canonical_artifact.py`는 strict JSON, canonical bytes, SHA-256, immutable one-record-per-file hash-chain과 externally pinned head를 소유한다. `evidence_contracts.py`는 schema별 의미 검증을 소유하고, FormulaRecord·ImplementationBinding·FormulaAudit·ExperimentRun·EvidenceBundle·DecisionRecord·CompletionObligation 사이의 참조를 검사한다. 모형 계산과 source I/O를 이 모듈들에 섞지 않는다.

### Program ledgers and frozen design

```text
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/input-symbol-registry.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-registry.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/rb-candidate-audit-alias-registry.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/rb-candidate-audit-alias-registry.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/implementation-bindings.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-ledger.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-matrix.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/math-disposition-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-coverage-certificate.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-coverage-certificate.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-candidate-admission-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-metadata-acceptance-ledger/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/design-metadata-capture-authorizations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/universe-metadata-snapshots/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/raw-collection-authorizations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/raw-capture-manifests/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processing-authorizations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processed-manifests/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-search-plan-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/source-availability-search-plans/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-search-plans.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-search-plans.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-closures/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-outcome-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/data-lineage-disposition-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/data-lineage-eligibility-snapshots/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/completion-predicate-registry.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/completion-predicate-registry.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/gate-applicability-rules.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/gate-applicability-rules.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirement-obligation-definitions.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirement-obligation-definitions.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/predata-rule-freeze.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/predata-rule-freeze.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-terminal-decision-rules.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-terminal-decision-rules.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/required-deliverable-registry.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/required-deliverable-registry.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ontology-name-mapping.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ontology-name-mapping.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/analysis-code-bundle-manifest.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/analysis-code-bundle-manifest.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processing-code-bundle-manifest.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processing-code-bundle-manifest.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/confirmation-design-register.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/protocol-promotion-ledger/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/experiment-run-id-reservations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reservation-lineage-binding-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/actual-run-lineage-binding-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/run-event-ledger-heads/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-transaction-intents/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-transaction-commits/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-recovery-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-external-anchor-binding-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-external-anchor-bindings.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-external-anchor-bindings.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/executor-identity-binding-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-rights-attestation-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-attestation-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/independent-reviewer-attestation-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-input-authorization-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-manifest-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-execution-id-reservations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verification-id-reservations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-execution-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verification-events/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/audit-execution-reservations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/synthetic-verification-reservations/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/audit-executions/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/synthetic-verifications/
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-executions.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-executions.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verifications.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verifications.pending_unanchored.json.sha256
research/meta-research/catalog/research-objects.v2.pending_unanchored.json
research/meta-research/catalog/research-objects.v2.pending_unanchored.json.sha256
research/meta-research/catalog/artifact-bindings.v2.pending_unanchored.json
research/meta-research/catalog/artifact-bindings.v2.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.v2.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.v2.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/current-program-state.v2.pending_unanchored.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/current-program-state.v2.pending_unanchored.json.sha256
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/historical-v1-graph-snapshot.json
research/meta-research/objects/programs/RP-001-quantitative-market-behavior/historical-v1-graph-snapshot.json.sha256
research/rp-001/designs/CD-001-confirmation-design.json
research/rp-001/designs/CD-001-confirmation-design.sha256
research/rp-001/contracts/model-backend-decision.json
```

신규 descriptor/body의 유일한 object root는 다음과 같다.

```text
research/meta-research/objects-v2/study-protocols/
research/meta-research/objects-v2/experiment-runs/
research/meta-research/objects-v2/evidence-bundles/
research/meta-research/objects-v2/decision-records/
research/meta-research/objects-v2/synthesis-reports/
```

`validate_research_program.py`는 오직 frozen `objects/`를 탐색해 계속 30-object historical graph만 검증한다. `validate_research_program_v2.py --graph-mode current-v2`만 `objects-v2/`를 재귀 탐색하고 v1 object는 `historical-v1-graph-snapshot.json`의 exact path/hash reference로만 읽는다. 두 root의 descriptor count, dependency graph와 artifact ownership을 합쳐 하나의 discovery set으로 만들지 않는다.

`candidate-registry.json`의 11개 family coverage와 기존 v1 30-object catalog/traceability/RP descriptor bytes는 frozen historical SSOT로 보존한다. 새 `formula-registry.pending_unanchored.json`은 concrete candidate projection이며 기존 family 원장을 덮어쓰거나 registry-only 상태를 실행 가능으로 재해석하지 않는다. current registration/lifecycle은 append-only v2 events가 authoritative이고 `research-objects.v2.pending_unanchored.json`, `artifact-bindings.v2.pending_unanchored.json`, `traceability.v2.pending_unanchored.json`, `current-program-state.v2.pending_unanchored.json`은 deterministic rebuild projection이다.

append-only authoritative state와 derived projection은 다음처럼 분리한다. 아래의 모든 local event·head pin·projection filename은 정식 anchor 전후 모두 `.pending_unanchored` suffix를 유지한다. 외부 receipt를 받았다고 local file을 rename하거나 suffix를 지우지 않는다.

| domain | authoritative immutable records | local immutable head candidate | rebuildable local projection |
| --- | --- | --- | --- |
| implementation binding | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/implementation-binding-events/<sequence>.pending_unanchored.json` | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/implementation-bindings/<sequence>.pending_unanchored.json` | `implementation-bindings.pending_unanchored.json` |
| formula audit | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-events/<sequence>.pending_unanchored.json` | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/formula-audit/<sequence>.pending_unanchored.json` | `formula-audit-ledger.pending_unanchored.json` |
| eligibility | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/eligibility-decision-events/<sequence>.pending_unanchored.json` | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/eligibility-decisions/<sequence>.pending_unanchored.json` | `eligibility-decisions.pending_unanchored.json` |
| successor trial | `research/rp-001/trials/<successor-ledger-id>/events/<sequence>.pending_unanchored.json` | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/<successor-ledger-id>/<sequence>.pending_unanchored.json` | `research/rp-001/trials/<successor-ledger-id>/projection.pending_unanchored.json` |
| run/lifecycle/terminal | `research/rp-001/run-events/<runId>/<sequence>.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/lifecycle-events/<sequence>.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-terminal-events/<studySlot>/<sequence>.pending_unanchored.json` | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/<ledger-id>/<sequence>.pending_unanchored.json` | domain별 `.pending_unanchored` current graph/status projection |

projection file의 변경은 event append 뒤 새 suffix file로 deterministic rebuild할 때만 허용하고, projection hash와 source head hash를 `ArtifactBindingV2`에 기록한다. 각 local bundle은 full fsync 뒤 `ExternalHeadAnchorPort.compare_and_swap(expectedAnchoredSequence, expectedAnchoredHeadSha256, proposedSequence, proposedBundleSha256)`에 제출한다. distinct trust boundary의 signed WORM receipt 또는 protected remote에 push된 immutable git commit receipt가 검증되기 전 상태는 `pending_unanchored`이며 EvidenceBundle, terminal, checkpoint 통과와 completion의 근거가 될 수 없다. anchor authority가 실제로 없으면 local SG3 작업은 계속할 수 있지만 해당 checkpoint와 G9는 blocked다. 기존 proposed `SP-001..008` 및 그 trial ledger bytes는 immutable historical input이므로 append·projection rebuild 대상이 아니다.

### Tests

```text
research/rp-001/tests/test_evidence_contracts.py
research/rp-001/tests/test_formula_registry.py
research/rp-001/tests/test_formula_equivalence.py
research/rp-001/tests/test_formula_metamorphic_audit.py
research/rp-001/tests/test_reward_hacking_contract.py
research/rp-001/tests/test_hsmm_competing_risk_contract.py
research/rp-001/tests/test_source_acceptance.py
research/rp-001/tests/test_source_availability.py
research/rp-001/tests/test_read_only_toss_adapter.py
research/rp-001/tests/test_external_raw_sink.py
research/rp-001/tests/test_external_artifact_locator.py
research/rp-001/tests/test_confirmation_design.py
research/rp-001/tests/test_protocol_promotion.py
research/rp-001/tests/test_experiment_run.py
research/rp-001/tests/test_evidence_cli_contract.py
research/rp-001/tests/test_evidence_engine_cli.py
research/rp-001/tests/test_source_runtime_cli.py
research/rp-001/tests/test_source_plan_set.py
research/rp-001/tests/test_collection_reader.py
research/rp-001/tests/test_analysis_reader.py
research/rp-001/tests/test_data_lineage_terminalization.py
research/rp-001/tests/test_study_candidate_admission.py
research/rp-001/tests/test_data_lineage_registers.py
research/rp-001/tests/test_source_impact_terminalizer.py
research/rp-001/tests/test_validation_design.py
research/rp-001/tests/test_evidence_synthesis.py
research/rp-001/tests/test_independent_reproduction.py
research/rp-001/tests/test_program_completion.py
research/rp-001/tests/test_research_graph.py
research/rp-001/tests/test_credential_broker.py
```

## Source acceptance and credential boundary

1. `SourceMetadataAcceptance`는 시장값 열람보다 먼저 공식 provider 문서·권리·entitlement·schema/timestamp/unit/revision, `providerAuthRequirement=required|public`, `credentialStatus=rotated|not_required`와 문서 response hash만 수락한다. `required` source는 `rotated`와 nonsecret rotation provenance를 요구하고, `public` source는 `not_required`만 허용하며 credential material/event dependency가 없어야 한다. 실제 market raw/processed hash는 이 단계의 필드도 통과조건도 아니다.
2. foundation 당시 `liveApiCalled=false` 문서와 과거 `blocked_pending_rotated_credentials_and_provider_retention_clarification` event는 소급수정하지 않는다. 2026-07-10 current event는 user-authorized read-only probe의 OAuth success, exact GET path/query, HTTP 200, result count 1, token/key/body persistence 0, order/account call 0만 기록한다. 이것은 metadata-only operational exposure이며 accepted raw dataset·CD·G7 evidence가 아니다. probe에 사용된 credential은 raw collection acceptance에 재사용하지 않으며 raw 저장 status는 `blocked_pending_rotated_credentials_and_provider_retention_and_redistribution_clarification`다.
3. `CredentialBroker`는 `providerAuthRequirement=required`인 source에만 적용한다. 이 broker만 mode `0600`·Git-ignored local credential file을 읽고 allowlisted names를 one-shot child-process environment에 전달한다. `public` source path는 broker, rotation event와 credential environment를 참조하면 실패한다. parent process, renderer, 저장소, CLI 인자, 문서, stdout/stderr, manifest와 trial ledger에는 값이 존재할 수 없다. child stdout/stderr는 기존 `SensitiveValuePolicy`로 전송 전·후 redact하고 redaction spy가 secret-like bytes 0을 증명한다.
4. `DesignMetadataCaptureAuthorization`은 study×provider별 `declaredMetadataClasses`를 사전 동결한다. closed universe는 `{instrument_identity,trading_calendar,coverage_bounds,field_catalog}`이고 declared set은 그 부분집합이다. actual response classes는 declared set과 set-equality여야 하며, 모든 study/provider가 네 class를 전부 요구하지 않는다. price, return, volume, order, book/trade/cancel, label, outcome과 그 파생값은 어느 subset에도 들어갈 수 없다.
5. metadata capture는 별도 audit event와 immutable response manifest를 만들고 `UniverseMetadataSnapshot`에 declared subset, actual subset, 각 metadata path·bytes hash·receivedAt·source response hash를 결박한다. 이 snapshot 외 정보로 universe를 정하지 않는다.
6. CD와 successor SP가 snapshot hash에 결박된 뒤에만 `RawCollectionAuthorization`을 봉인한다. `CollectionReadGuard`는 이 authorization의 source·universe·period·field allowlist만 collection reader에 전달하고 raw market bytes를 content-addressed immutable sink에 한 번 기록한다. analysis code는 이 reader를 import할 수 없다.
7. collection 종료 뒤 `RawCaptureManifest`에는 raw absolute path 대신 각 `ExternalArtifactLocator(sinkId,artifactId,contentSha256,relativeContentAddressKey,sinkDescriptorHash)`, `clientReceivedAt`와 authorization hash를 기록한다. 그 뒤 `ProcessingAuthorization`이 raw manifest hash와 processing code hash를 봉인하고 processed artifact를 만든다. processed manifest와 `SourceAvailabilityClosure`의 provider request/response도 같은 locator contract와 raw backreference를 사용한다.
8. `AnalysisReadGuard`는 processed manifest, CD, successor SP, code/environment hash가 모두 일치할 때만 analysis reader를 연다. raw collection authorization만으로 analysis할 수 없고, source metadata acceptance만으로 raw bytes를 읽을 수 없다.
9. 대체 source는 이름부터 미리 정하지 않는다. 공식 1차 문서와 계약으로 provider identity, 이용 목적, local/processed retention, derived-publication, redistribution, schema/timestamp/unit/revision/credential 상태와 문서 hash를 수락한 뒤 같은 단계 순서를 적용한다.
10. 한 필드라도 불완전하면 해당 plan은 `nonterminal_blocked`, touched study/formula는 pre-run `blocked`로 두고 SG3 수학·합성·코드 감사와 unrelated eligible research를 계속한다. required source의 rotation 미완과 public source의 잘못된 credential dependency는 서로 다른 blocker evidence/reopen condition을 가진다. 결측을 0·neutral로 채우거나 closure/exhaustion을 발명하거나 다른 source·snapshot·feature를 재가중해 Gate를 우회하지 않는다.
11. `blocked`는 pre-run execution disposition이며 terminal status가 아니다. SourcePlanSetManifest의 각 plan은 exact plan ID/hash와 closed outcome `eligible_metadata | exhausted_unavailable | nonterminal_blocked` 중 하나를 가진다. eligible은 anchored metadata acceptance/snapshot, exhausted는 complete SourceAvailabilityClosure, blocked는 exact blockingReason/evidence/affectedStudySlots/reopenCondition/observedAt만 허용한다. 미승인·미수집·미회전 credential·rights/entitlement/anchor/provider transport 미완은 `nonterminal_blocked`이며 closure·data_unavailable·invented exhaustion으로 바꿀 수 없다. partial closure/blocker는 touched input/formula/study만 막고 다른 eligible branches는 scoped DataLineageEligibilitySnapshot으로 계속한다. 한 study의 required input plans 전부가 valid closure일 때만 frozen SourceImpactTerminalizer가 그 study를 `data_unavailable` terminal로 전환한다. program completion은 blocked count=0과 ST-DAT terminal을 모두 요구한다.
12. `ReadOnlyTossAdapter`는 HTTP `GET` exact public market/metadata endpoint allowlist와 OAuth token 발급용 `POST https://openapi.tossinvest.com/oauth2/token` 한 경로만 허용한다. OAuth body key set은 정확히 `{grant_type,client_id,client_secret}`이고 `grant_type=client_credentials`다. 그 밖의 POST/body key, `/orders`, conditional-orders, account/asset endpoint, `X-Tossinvest-Account` header, PUT/PATCH/DELETE는 입력 validation 단계에서 hard reject하고 transport spy 호출 수 0을 검사한다. GET allowlist는 accepted official OpenAPI operation IDs/path hashes로 authorization마다 봉인하고 임의 prefix match를 금지한다. 공식 문서상 market/stock info는 token-only objective data이고 account/order는 account header가 필요하지만, 이 구분이 rotation·retention·redistribution 미확정을 해소하지는 않는다.
13. raw sink는 repository root 밖의 pre-authorized local root에만 만들고 descriptor event의 exact mode/owner policy, VCS non-membership, retention deadline, tombstone contract, approver binding과 resolver-config hash를 검증한다. authoritative descriptor는 `external-sink-descriptor-events/<sinkId>/<sequence>.pending_unanchored.json`, local head는 `ledger-head-pin-events/external-sink-descriptors/<sinkId>/<sequence>.pending_unanchored.json`, projection은 `external-sink-descriptors.pending_unanchored.json`과 각 sidecar에 둔다. absolute resolver-config path와 local root는 repository 밖 local config와 `ExternalSinkResolver` process memory에만 존재하며 repo artifact·log·manifest에는 config hash, `resolverKey`, relative content-address locator만 직렬화한다. descriptor rotation 또는 permission/owner/VCS/retention/tombstone policy 변경은 기존 record 수정이 아니라 `predecessorDescriptorEventId`를 가진 successor event와 새 external anchor receipt로만 가능하다. raw bytes를 repository, shared temporary path 또는 renderer storage에 쓰지 않는다. 주문·조건주문·계좌·자산 호출은 연구 전 과정에서 절대 금지한다.

## Pre-data ConfirmationDesign freeze

`CD-001-confirmation-design.json`은 source metadata는 수락했지만 **첫 accepted market row를 reader가 반환하기 전** 완전히 채우고 hash sidecar를 만든다. 부분 문서, 빈 문자열, `null`, 미정 표식, 추후 선택 값이 하나라도 있으면 생성 자체를 거부한다.

필수 필드는 다음과 같다.

```text
designId/version/createdAt
preDataRuleFreezeId/preDataRuleFreezeSha256/protectedPathManifestSha256
designCoreHash/protocolCoreHashes/plannedRunKeys/reservationManifestHash
goal/SourceMetadataAcceptance/UniverseMetadataSnapshot/seen-data/protocol source hashes
study eligibility and blocked reasons
studyDesigns oneOf: eligible design | blocked disposition
universe snapshot ID/hash and deterministic selection rule
historical_external_oof period and role
prospective_terminal period/start-stop rule and role
calendar/session/fold/purge/embargo definitions
study별 outcome/interval-label/censoring estimand와 estimator
training-only censoring fit rule와 weight truncation actual value
study별 class-imbalance rule와 outcome-dependent exclusion=false
cluster bootstrap 또는 posterior method, resample count와 actual seed list
success/failure probability distribution definition과 uncertainty output
plannedCellKey=(studySlot,designCoreHash,protocolCoreHash,inputContractOrSnapshotHash,
 candidateOrControlId,sampleRole,fold,horizon,implementationBindingHash,
 processingCodeBundleManifestSha256,analysisCodeBundleManifestSha256)
plannedRunKey=(plannedCellKey,seed); planned cell별 preregistered distinct seed와 distinct runId 최소 2개
repeat plannedGridCoverage=1.00; executedCoverage는 CD에 존재 금지
study별 MCSE/ESS/convergence/precision stopping rule과 maximum budget
closed candidate IDs and ImplementationBinding hashes
seed list and deterministic derivation evidence
baseline and falsification grid
cost/base-stress grid with source hashes
minimum effect delta and ex-ante selection evidence
power/precision assumptions and effective-sample-size target
multiplicity family and decision rule
multiplicity universe: study, primary/secondary metric, horizon, candidate/control, model-selection comparison
eligible_single_study baseline: pre-data fixed ID 또는 모든 single-study comparison 동시 보정
terminal no-tuning and G7/G9 rules
```

비순환 publication 순서는 정확히 다음과 같다.

```text
DesignCore canonical bytes + sidecar
→ SuccessorProtocolCore canonical bytes + sidecar(s)
→ PlannedRunKey grid
→ ER-000001..ER-999999 six-digit ReservationManifest
→ final ConfirmationDesign canonical bytes + sidecar; body binds D1–D4 only
→ final successor protocol canonical bytes + sidecar(s)
→ ReservationLineageBindingEvent binds D1–D6
→ external CAS receipt and post-CAS ArtifactExternalAnchorBindingEvent
```

`DesignCore`는 자기 hash, reservation, final CD/protocol hash 또는 dataset manifest를 포함하지 않는다. `SuccessorProtocolCore`는 `designCoreHash`만 참조하고 자기 hash나 final artifact hash를 포함하지 않는다. `PlannedRunKey`는 `designCoreHash`, 해당 `protocolCoreHash`, `inputContractSha256` 또는 `universeMetadataSnapshotSha256`, candidate/control ID, sample role, fold, horizon, seed, `implementationBindingSha256`, `processingCodeBundleManifestSha256`, `analysisCodeBundleManifestSha256`만 갖는다. D5 final CD canonical body는 D1 DesignCore, D2 ProtocolCore, D3 PlannedRunKey grid와 D4 ReservationManifest predecessor hashes만 결박하며 자기 `ArtifactBindingV2`, 자기 sidecar hash, D6 final protocol 또는 D7 ReservationLineageBindingEvent를 참조하지 않는다. D6 final protocol은 D2 core, D4 reservation과 이미 발행·anchor된 D5 hash를 참조한다. D7만 D1–D6 exact path/hash와 각 predecessor anchor binding을 한 방향으로 결박한다. 모든 artifact의 hash SSOT는 별도 sidecar와 `ArtifactBindingV2`이며 own external receipt는 canonical body에 들어가지 않는다. future raw/processed dataset hash는 이 사전 key와 reservation 어디에도 존재할 수 없다.

값 선택은 결과와 무관한 다음 결정규칙을 사용한다.

- universe는 sealed DesignMetadataCaptureAuthorization으로 수집한 exact `UniverseMetadataSnapshot` manifest/hash/audit event의 적격 canonical instrument를 정렬해 만들고, `seen-data-register.json`과 겹치는 symbol×period는 confirmatory role에서 제외한다. 계산자원 상한이 있으면 상한을 먼저 기록한 뒤 `SHA256(designId|canonicalInstrumentId)` 오름차순으로 선택한다. 가격·수익·거래량·주문·outcome 값은 metadata capture와 선택에 쓰지 않는다.
- historical external OOF는 연구자가 보지 않았다는 exposure ledger와 accepted coverage/calendar metadata로만 정한다. 후보축소·G6 근거로는 쓸 수 있지만 prospective terminal과 합치지 않는다.
- prospective terminal은 `CD-001`과 새 preregistration hash가 모두 발행된 뒤 첫 적격 세션부터 시작한다. 종료는 market row를 보기 전에 합성자료·검정력·정밀도 규칙으로 정한 사건수/시간 상한 중 먼저 충족되는 규칙으로 고정한다.
- fold는 accepted calendar와 primary horizon에서 결정하며 purge는 outcome horizon 이상, embargo는 각 protocol의 고정값 이상이다. 같은 event·issuer·cluster와 겹친 outcome 구간을 서로 다른 역할로 나누지 않는다.
- candidate set은 해당 study의 `empiricalEligibility=true`, accepted inputs와 verified binding을 만족하는 새 RP FormulaRecord의 exact set과 위 `requiredControlIds` set-equality를 ID 순으로 닫는다. RB CandidateAuditAliasRecord 20개는 포함할 수 없다. 결과를 보고 후보를 빼거나 더하지 않는다.
- seed 수는 합성 power와 계산예산으로 먼저 정하되 각 CD-eligible empirical candidate/control의 모든 planned cell마다 최소 2개의 distinct seed를 보장한다. 각 정수 seed는 `SHA256(designId|studySlot|plannedCellKey|ordinal)`에서 결정적으로 파생해 artifact에 실제 값으로 기록하며, expected grid는 cell별 distinct six-digit runId도 최소 2개 예약한다.
- 비용 grid는 accepted fee/tax/FX/borrow/hedge와 실행·영향 source evidence로만 만든다. 근거가 없으면 0을 넣지 않고 EXE/RSK/SYN을 차단한다.
- 최소효과 `δ`는 비용·위험상 경제적 최소효과와 합성 power/precision을 결과 열람 전 결합해 정한다. pre-run 합성 power/precision이 부족하면 `δ`를 낮추거나 terminal을 만들지 않고 해당 study branch를 `blocked`와 exact `blockingReason=blocked_pre_run_power_or_precision`으로 기록한다. `insufficient_evidence`는 적격 actual run이 시작되고 preregistered maximum budget을 실제로 모두 소진한 뒤에도 power/ESS/precision Gate가 미달일 때만 허용한다.
- censoring estimand·estimator, training-only fit, weight truncation 값, class imbalance rule, cluster resampling/posterior method, resample count·seed와 성공/실패 확률분포 정의를 study별 closed field에 실제 값으로 기록한다. outcome-dependent row exclusion은 항상 false이며 하나라도 미정이면 CD를 동결하지 않는다.
- study별 entry는 conditional schema `oneOf`다. `eligible` entry는 source/snapshot/candidate/control/grid/reservation/stopping rule을 모두 요구하고 blocked field를 금지한다. `blocked` entry는 blocking evidence, dependency scope와 reopen condition을 요구하고 candidate/run grid·reservation·실행값을 금지한다. 한 study의 blocked entry는 독립 eligible study의 CD freeze를 막지 않는다.
- `plannedGridCoverage`는 pre-data candidate/control×sampleRole×fold×horizon×preregistered seed의 `PlannedRunKey`↔six-digit runId reservation set-equality만 측정하며 1.00이어야 한다. terminal run, final dataset manifest 또는 `executedCoverage`는 CD core/key/동결조건이 아니며 Task 14에서만 사후 계산한다.
- distinct seed/runId 2개는 integrity floor일 뿐 market sample independence나 정밀도 충분성을 뜻하지 않는다. 각 study는 결과 전 MCSE 상한, ESS 하한, chain/convergence criterion, interval-width/precision target, 최대 seed/resample budget과 outcome-independent stopping rule을 실제 값으로 동결한다.
- multiplicity family는 study, primary·secondary metric, horizon, candidate/control과 model-selection comparison 전체를 포함한다. SYN의 `eligible_single_study`는 pre-data fixed upstream ID 하나로 닫거나 모든 eligible single-study comparator를 family에 포함해 동시 보정한다.
- G7은 prospective terminal에서만 통과할 수 있다. historical external OOF가 좋아도 prospective evidence가 없으면 adoption은 불가하다.

`StudyTerminalDecisionRule`은 `ST-ONT-001`, `ST-DAT-001`, `ST-BEH-001`, `ST-VAL-001`, `ST-MIC-001`, `ST-EXE-001`, `ST-RSK-001`, `ST-SYN-001` exact 8-slot set마다 하나씩 pre-data freeze한다. 각 rule은 estimand ID, interval decision region, required Gate predicates, accepted-run/failure/closure preconditions와 다음 closed precedence를 가진다: `implementation_invalid → external_failure → data_unavailable → not_identifiable → supported → refuted → insufficient_evidence`. 높은 precedence predicate가 참이면 낮은 predicate는 schema상 거짓이어야 하며, supported/refuted region과 residual insufficient region은 CD에 고정한 symbolic boundary로 서로 겹치지 않고 terminalizable evidence domain 전체를 덮어야 한다. `data_unavailable`은 valid `SourceAvailabilityClosure`가 있으면 successor empirical protocol이 없는 branch에도 적용할 수 있다. `blocked`는 이 terminal codomain에 없고 `NonTerminalBlocked` 결과로만 남는다. terminal event는 exact 한 predicate가 참일 때만 발행하며 overlap, terminalizable-state gap, precedence mismatch, estimand/Gate/closure/run-failure hash mismatch를 모두 거부한다.

## Change control, rollback, and terminal rules

### Immutable versioning

- `SP-003..008/protocol.md`와 `protocol.sha256`은 byte-for-byte 보존한다.
- promotion은 새 객체 `SP-009..014`, 새 protocol file, 새 sidecar, 새 trial ledger를 추가한다. 기존 proposed protocol을 덮어쓰거나 같은 hash 이름으로 재결박하지 않는다.
- preregistration 뒤 변경은 다음 미사용 SP ID의 successor object와 새 `ConfirmationDesign` ID를 만든다. 기존 run과 evidence는 삭제하지 않는다.
- canonical event는 one-record-per-file로 `sequence`, `previousRecordSha256`, `recordSha256` hash-chain을 가진다. `recordSha256`은 유일하게 자기 field를 제외한 canonical bytes로 계산되는 chain checksum이며 artifact의 자기 hash SSOT가 아니다. artifact 자기 bytes hash는 sidecar와 `ArtifactBindingV2`에만 존재한다. 각 append는 새 `.pending_unanchored` immutable event file, ledger 밖의 local head candidate와 projection을 만들고 full fsync 뒤 외부 CAS anchor receipt를 요청한다. frozen v1 RP descriptor나 mutable latest-head singleton을 수정하지 않는다. v2 current projection은 전체 event/head를 재생해 만들고 append 전 모든 이전 file hash와 externally anchored receipt를 검증해 수정·재정렬·삭제·suffix rewrite를 거부한다.

append transaction 순서는 `Intent fsync+atomic rename → event+sidecar fsync → local head+sidecar fsync → projection+sidecar fsync → Commit fsync+atomic rename → ExternalHeadAnchorPort CAS → signed receipt local copy fsync`다. intent는 last externally anchored sequence/head, proposed sequence, 모든 staged path/hash와 transaction ID를 기록한다. 외부 CAS는 monotonic sequence와 expected prior anchored head가 exact match할 때만 성공할 수 있고 local bundle 전체 fsync 전 호출할 수 없다. crash recovery는 orphan intent/event/head/commit을 삭제하지 않는다. 모든 bytes가 intent와 일치하면 남은 phase를 deterministic finalize하고, 불일치하면 orphan hash를 참조하는 append-only invalidation/recovery event를 다음 sequence에 만든 뒤 그 새 head를 anchor한다. 외부 authority, receipt signature 또는 protected-remote proof가 없으면 local work는 `pending_unanchored`로 계속하되 EvidenceBundle, checkpoint, terminal, G9와 completion은 blocked다.

### Rollback

- intent 발행 전 staging 생성 실패만 이번 task의 staging file을 제거하고 다시 RED부터 시작할 수 있다.
- intent가 fsync·publish된 뒤의 orphan intent/event/head/projection/commit은 절대 삭제하거나 rename하지 않고 deterministic finalize 또는 append-only invalidation/recovery로만 닫는다.
- hash 또는 catalog 등록 뒤에는 파일을 되돌리거나 덮어쓰지 않는다. 오류 record, 무효 사유, successor ID를 append한다.
- 권리상 원자료 삭제가 필요하면 bytes를 보존하지 않고 삭제시각·대상 content hash·권리근거를 tombstone record로 남긴다. 연구결과가 불리하다는 이유로 삭제하지 않는다.
- RB-001, `research/indicator-validation`의 code/data/results/manifest와 사용자 앱 변경은 rollback 대상으로도 수정하지 않는다.

### Status separation

```text
pre-run disposition: eligible | blocked
run status: reserved | running | completed | failed | invalid
study terminal: supported | refuted | insufficient_evidence | not_identifiable |
                data_unavailable | implementation_invalid | external_failure
formula math disposition: retain | repair | proxy_only | reject | not_identifiable
decision: adopt | conditional_adopt | research_only | reject | not_identifiable
operation: Trade only after adopt/conditional_adopt; otherwise NoTrade/Abstain
```

수학적으로 `retain`인 공식도 G0~G10을 통과하기 전 `adopt`가 아니다. `adopt`와 `conditional_adopt`는 G0,G1,G2,G3,G4,G5,G6,G7,G8,G9,G10이 정확히 모두 `pass`이고 `not_applicable=0`일 때만 가능하다. `not_applicable`은 applicability registry와 evidence가 있는 비채택 결정에서만 허용한다. `blocked`를 terminal로 기록하지 않고, NoTrade를 연구 terminal로 기록하지 않는다. Gate 하나의 초과성과로 다른 Gate 실패를 보상하지 않는다.

P0–P4와 backend recovery의 synthetic 실행은 `AuditExecution(AE-*)` 또는 `SyntheticVerificationRun(SVR-*)`만 사용한다. 이 객체는 synthetic generator/input/code/environment hash를 갖지만 sampleRole, market dataset, G6~G10 또는 empirical claim을 가질 수 없다. `ExperimentRun(ER-*)` ID reservation, run count, repeat coverage와 program empirical completion에는 절대 포함하지 않는다.

## Review checkpoints

| Checkpoint | 시점 | 독립 검토 범위 | 통과 전 금지 |
| --- | --- | --- | --- |
| A | Task 0–6 뒤 | protected prehash, schema, 11 family/19 candidate 완전성, P0–P4 AE/SVR 반례, 수학↔구현 독립성 | source·market read |
| B | Task 7 뒤 | SourceMetadataAcceptance와 allowlisted DesignMetadataCaptureAuthorization; UniverseMetadataSnapshot manifest/hash/audit | 비allowlist metadata, raw market collection·analysis |
| C | Task 8–9 뒤 | CD·successor SP·global ER capacity freeze와 RawCollectionAuthorization; CollectionReadGuard/RawCaptureManifest/ProcessingAuthorization/processed manifest/AnalysisReadGuard 순서 | authorization 없는 raw read, processed manifest 없는 analysis read |
| D | Task 10–13 뒤 | run bijection, split/leakage, multiplicity/calibration, 비용·CVaR, 실패 공개 | terminal 개봉 후 재튜닝 |
| E | Task 14 | 독립 artifact reproduction, adversarial opposite-conclusion review, G0–G10 | 운영 앱 반영 |

### Task-local sidecar Files contract

모든 Task의 **Files**에서 생성하는 canonical `.json` 또는 `.md` path `P`는 같은 Task에 exact sidecar path `S(P)`도 생성하는 것으로 규범적으로 확장한다. 기본 함수는 `S(P)=P + ".sha256"`이다. 새 study protocol의 `protocol.md`만 기존 객체 convention을 따라 같은 directory의 `protocol.sha256`을 `S(P)`로 명시한다. frozen predecessor sidecar 이름은 바꾸지 않는다. 각 Task RED/GREEN은 `SidecarPathSet == CanonicalArtifactPathSet`, sidecar 하나당 owner file 하나, lowercase SHA-256 64자+LF 한 개를 set-equality로 검사한다. schema/test fixture가 아닌 runtime artifact에서 sidecar 누락·공유·고아 sidecar는 통과할 수 없다.

---

### Task 0: protected-path prehash와 변경 allowlist 봉인

**Files:**
- Create: `research/rp-001/capture_protected_paths.py`
- Create: `research/rp-001/contracts/protected-path-manifest.json`
- Create: `research/rp-001/contracts/protected-path-manifest.sha256`
- Create: `research/rp-001/src/rp001/protected_path_guard.py`
- Create: `research/rp-001/src/rp001/artifact_hygiene.py`
- Create: `research/rp-001/tests/test_protected_path_guard.py`
- Create: `research/rp-001/tests/test_artifact_hygiene.py`

- [ ] **Step 1: RED로 보호경계와 manifest 자체결박을 고정한다**

`extensions/`, `src/`, `research/indicator-validation/`, RB-001, frozen v1 30-object catalog/traceability/RP descriptor, `SP-001..008`과 기존 trial ledgers의 prehash를 exact path별로 기록한다. 기존 `research/meta-research/tools/validate_research_program.py`, `research/meta-research/tools/test_validate_research_program.py`, `research/rp-001/src/rp001/__init__.py`도 별도 protected exact path로 등록하여 byte 변경을 금지한다. manifest 밖 write, path 추가/삭제, prehash 누락, manifest/sidecar 불일치, symlink 우회, secret-like bytes를 manifest에 넣는 mutation을 실패시킨다.

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protected_path_guard.py \
                  research/rp-001/tests/test_artifact_hygiene.py -v
```

Expected RED: 두 test module과 최소 importable counterexample guard가 정상 discovery된 뒤 `test_manifest_sidecar_mismatch_is_rejected`, `test_symlink_cannot_escape_allowed_roots`, `test_sensitive_scalar_is_rejected`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다. 아직 존재하지 않는 Task 7C2 `run_evidence_engine.py`를 Task 0 bootstrap에 사용하지 않는다.

- [ ] **Step 2: guard API와 허용 변경 root를 구현한다**

```text
ProtectedPathGuard.capture_preflight(protectedPaths: Sequence[Path], allowedWriteRoots: Sequence[Path]) -> ProtectedPathManifest
ProtectedPathGuard.verify_postflight(manifest: ProtectedPathManifest) -> ProtectedPathReport
ArtifactHygieneValidator.validate_structured_artifacts(bindings: Sequence[ArtifactBindingV2]) -> ArtifactHygieneReport
```

allowed write root는 이 계획에 열거한 새 RP-001/v2 event·projection/artifact path만 exact prefix로 봉인한다. raw sink는 repository 밖이라 별도 authorization으로만 다룬다. 기존 `SensitiveValuePolicy`가 manifest/path metadata와 모든 produced text/JSON scalar를 검사하고 matched value를 결과에 반환하지 않는다. 미완성 값 검사는 schema가 terminal value를 요구하는 structured artifact field만 대상으로 하고 plan·code의 path templates, type variables와 test fixtures는 제외해 정규식 오탐을 만들지 않는다.

`capture_protected_paths.py`는 `ProtectedPathGuard`만 조립하는 bootstrap entrypoint이며 `--repository-root`, `--manifest`, `--sidecar`, `--capture|--verify`만 받는다. capture는 manifest/sidecar를 같은 staging directory에서 만든 뒤 원자적으로 publish한다. Task 1 이후 모든 test/CLI/application service는 `protectedPathManifestSha256` 입력을 필수로 받고 누락·불일치 시 import 이후 작업이나 write 전에 exit 2로 거부한다.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/capture_protected_paths.py \
  --repository-root . \
  --manifest research/rp-001/contracts/protected-path-manifest.json \
  --sidecar research/rp-001/contracts/protected-path-manifest.sha256 \
  --capture
```

Expected GREEN: manifest와 sidecar가 처음 생성되고 stdout에는 hash와 count만 나오며 protected file content·secret은 출력되지 않는다.

- [ ] **Step 3: GREEN을 확인한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protected_path_guard.py \
                  research/rp-001/tests/test_artifact_hygiene.py -v

PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/capture_protected_paths.py \
  --repository-root . \
  --manifest research/rp-001/contracts/protected-path-manifest.json \
  --sidecar research/rp-001/contracts/protected-path-manifest.sha256 \
  --verify
```

Expected GREEN: tests `OK`, protected prehash/posthash 동일, unauthorized changed path 0, allowed new path만 존재, manifest와 sidecar 재해시 PASS. manifest hash 누락 fixture는 downstream entrypoint 호출 전 exit 2다.

### Task 1: Evidence schema, v2 graph/anchor, pre-data rule core

Task 1은 `1A canonical/schema → 독립 review → 1B v2 graph/anchor → 독립 review → 1C pre-data rules → 독립 review`의 세 execution unit이다. 뒤 unit은 앞 unit의 RED→GREEN 명령과 reviewer verdict가 저장되기 전 시작하지 않는다.

**Files:**
- Create: `research/rp-001/schemas/formula-record.schema.json`
- Create: `research/rp-001/schemas/candidate-audit-alias-record.schema.json`
- Create: `research/rp-001/schemas/implementation-binding.schema.json`
- Create: `research/rp-001/schemas/formula-audit.schema.json`
- Create: `research/rp-001/schemas/formula-obligation-matrix-cell.schema.json`
- Create: `research/rp-001/schemas/math-disposition-event.schema.json`
- Create: `research/rp-001/schemas/formula-audit-coverage-certificate.schema.json`
- Create: `research/rp-001/schemas/eligibility-decision.schema.json`
- Create: `research/rp-001/schemas/study-candidate-admission.schema.json`
- Create: `research/rp-001/schemas/audit-execution.schema.json`
- Create: `research/rp-001/schemas/audit-execution-reservation.schema.json`
- Create: `research/rp-001/schemas/synthetic-verification-run.schema.json`
- Create: `research/rp-001/schemas/synthetic-verification-reservation.schema.json`
- Create: `research/rp-001/schemas/study-terminal-event.schema.json`
- Create: `research/rp-001/schemas/terminal-decision-computation.schema.json`
- Create: `research/rp-001/schemas/lifecycle-event.schema.json`
- Create: `research/rp-001/schemas/artifact-binding.v2.schema.json`
- Create: `research/rp-001/schemas/artifact-external-anchor-binding-event.schema.json`
- Create: `research/rp-001/schemas/external-artifact-locator.schema.json`
- Create: `research/rp-001/schemas/external-sink-descriptor.schema.json`
- Create: `research/rp-001/schemas/research-graph-snapshot.v2.schema.json`
- Create: `research/rp-001/schemas/source-metadata-acceptance.schema.json`
- Create: `research/rp-001/schemas/design-metadata-capture-authorization.schema.json`
- Create: `research/rp-001/schemas/universe-metadata-snapshot.schema.json`
- Create: `research/rp-001/schemas/raw-collection-authorization.schema.json`
- Create: `research/rp-001/schemas/raw-capture-manifest.schema.json`
- Create: `research/rp-001/schemas/processing-authorization.schema.json`
- Create: `research/rp-001/schemas/processed-manifest.schema.json`
- Create: `research/rp-001/schemas/processing-code-bundle-manifest.schema.json`
- Create: `research/rp-001/schemas/analysis-code-bundle-manifest.schema.json`
- Create: `research/rp-001/schemas/source-availability-search-plan.schema.json`
- Create: `research/rp-001/schemas/source-plan-set-manifest.schema.json`
- Create: `research/rp-001/schemas/source-plan-outcome.schema.json`
- Create: `research/rp-001/schemas/source-availability-closure.schema.json`
- Create: `research/rp-001/schemas/data-lineage-disposition.schema.json`
- Create: `research/rp-001/schemas/data-lineage-eligibility-snapshot.schema.json`
- Create: `research/rp-001/schemas/confirmation-design.schema.json`
- Create: `research/rp-001/schemas/experiment-run.schema.json`
- Create: `research/rp-001/schemas/run-id-reservation-manifest.schema.json`
- Create: `research/rp-001/schemas/reservation-lineage-binding-event.schema.json`
- Create: `research/rp-001/schemas/actual-run-lineage-binding-event.schema.json`
- Create: `research/rp-001/schemas/append-transaction-intent.schema.json`
- Create: `research/rp-001/schemas/append-transaction-commit.schema.json`
- Create: `research/rp-001/schemas/append-recovery-event.schema.json`
- Create: `research/rp-001/schemas/external-head-anchor-receipt.schema.json`
- Create: `research/rp-001/schemas/executor-identity-binding.schema.json`
- Create: `research/rp-001/schemas/reproduction-rights-attestation.schema.json`
- Create: `research/rp-001/schemas/reproduction-attestation.schema.json`
- Create: `research/rp-001/schemas/independent-reviewer-attestation.schema.json`
- Create: `research/rp-001/schemas/reproduction-input-authorization.schema.json`
- Create: `research/rp-001/schemas/reproduction-manifest.schema.json`
- Create: `research/rp-001/schemas/evidence-cli-command-dispatch-registry.schema.json`
- Create: `research/rp-001/schemas/study-terminal-decision-rules.schema.json`
- Create: `research/rp-001/schemas/evidence-bundle.schema.json`
- Create: `research/rp-001/schemas/decision-record.schema.json`
- Create: `research/rp-001/schemas/completion-obligation.schema.json`
- Create: `research/rp-001/schemas/completion-observation-binding-event.schema.json`
- Create: `research/rp-001/schemas/completion-predicate-registry.schema.json`
- Create: `research/rp-001/schemas/gate-applicability-rules.schema.json`
- Create: `research/rp-001/schemas/requirement-obligation-definitions.schema.json`
- Create: `research/rp-001/schemas/predata-rule-freeze.schema.json`
- Create: `research/rp-001/schemas/required-deliverable-registry.schema.json`
- Create: `research/rp-001/src/rp001/canonical_artifact.py`
- Create: `research/rp-001/src/rp001/append_transaction.py`
- Create: `research/rp-001/src/rp001/external_head_anchor.py`
- Create: `research/rp-001/src/rp001/evidence_contracts.py`
- Create: `research/rp-001/src/rp001/audit_execution.py`
- Create: `research/rp-001/src/rp001/research_graph.py`
- Create: `research/rp-001/src/rp001/completion_predicates.py`
- Create: `research/rp-001/freeze_predata_rules.py`
- Create: `research/rp-001/tests/test_evidence_contracts.py`
- Create: `research/rp-001/tests/test_audit_execution.py`
- Create: `research/rp-001/tests/test_research_graph.py`
- Create: `research/rp-001/tests/test_append_transaction.py`
- Create: `research/rp-001/tests/test_external_head_anchor.py`
- Create: `research/rp-001/tests/test_completion_predicates.py`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/completion-predicate-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/completion-predicate-registry.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/gate-applicability-rules.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/gate-applicability-rules.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirement-obligation-definitions.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirement-obligation-definitions.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/predata-rule-freeze.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/predata-rule-freeze.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-terminal-decision-rules.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-terminal-decision-rules.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/required-deliverable-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/required-deliverable-registry.json.sha256`
- Create intent records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-transaction-intents/`
- Create commit records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-transaction-commits/`
- Create recovery records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/append-recovery-events/`
- Create verified receipt copies under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/`
- Create post-CAS binding events under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-external-anchor-binding-events/`
- Create binding projection and sidecar: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-external-anchor-bindings.pending_unanchored.json`, `artifact-external-anchor-bindings.pending_unanchored.json.sha256`
- Create one-record reservations under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-execution-id-reservations/`
- Create one-record reservations under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verification-id-reservations/`
- Create one-record events under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-execution-events/`
- Create one-record events under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/synthetic-verification-events/`
- Create immutable local head candidates with `.pending_unanchored` filenames under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/audit-execution-reservations/`, `synthetic-verification-reservations/`, `audit-executions/`, `synthetic-verifications/`
- Create projections with sidecars: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/audit-executions.pending_unanchored.json`, `.sha256`, `synthetic-verifications.pending_unanchored.json`, `.sha256`
- Create: `research/meta-research/catalog/research-objects.v2.pending_unanchored.json`, `.sha256`
- Create: `research/meta-research/catalog/artifact-bindings.v2.pending_unanchored.json`, `.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.v2.pending_unanchored.json`, `.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/current-program-state.v2.pending_unanchored.json`, `.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/historical-v1-graph-snapshot.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/historical-v1-graph-snapshot.json.sha256`
- Create: `research/meta-research/tools/validate_research_program_v2.py`
- Create: `research/meta-research/tools/test_validate_research_program_v2.py`
- Read only and byte-verify: `research/meta-research/tools/validate_research_program.py`, `research/meta-research/tools/test_validate_research_program.py`, `research/rp-001/src/rp001/__init__.py`

#### Task 1A execution unit: canonical schema core

**Files:** all `research/rp-001/schemas/*.schema.json` listed above, `canonical_artifact.py`, `evidence_contracts.py`, `audit_execution.py`, `test_evidence_contracts.py`, `test_audit_execution.py`.

- [ ] **Step 1: RED로 schema·canonical·hash-chain 불변식을 고정한다**

`test_evidence_contracts.py`에 정상 최소 fixture와 다음 변이를 각각 독립 test로 작성한다.

```text
unknown/missing field
duplicate JSON key, NaN/Infinity
sorted compact no-LF가 아닌 JSON
sidecar hash mismatch
event/head/projection/authorization/manifest/CD/run/EB/DR/SR file 중 개별 sidecar 누락 또는 다른 file과 sidecar 공유
Task-local `SidecarPathSet`과 `CanonicalArtifactPathSet` set-equality 불일치 또는 orphan sidecar
record sequence gap 또는 previousRecordSha256 mismatch
기존 prefix record 수정·삭제·재정렬
한 파일에 record 배열 또는 두 개 이상의 event 저장
local head candidate와 마지막 record hash 불일치
`.pending_unanchored` suffix rewrite·삭제·rename 또는 receipt 없이 EvidenceBundle/terminal/completion 사용
artifact canonical body 안에 어떤 자기 sidecar/descriptor hash field라도 삽입
final ConfirmationDesign canonical body가 자기 ArtifactBinding/sidecar, D6 final protocol 또는 D7 ReservationLineageBindingEvent를 참조
DesignMetadataCaptureAuthorization, UniverseMetadataSnapshot, ProcessingCodeBundleManifest,
AnalysisCodeBundleManifest, RawCollectionAuthorization, RawCaptureManifest,
ProcessingAuthorization, ProcessedManifest, ActualRunLineageBindingEvent,
ReproductionRightsAttestation, ReproductionInputAuthorization, ReproductionManifest,
ReproductionAttestation, IndependentReviewerAttestation 중 하나가 자기 external receipt ID/hash를 포함
ArtifactExternalAnchorBindingEvent가 대상 artifact path/hash와 receipt ID/hash/bundle hash를 결박하지 않거나 자기 receipt를 body에 포함
StudyTerminalEvent가 아직 존재하지 않는 EvidenceBundle ID/hash를 참조하거나 EvidenceBundle을 terminal보다 먼저 publish
SourceMetadataAcceptance에 raw/processed market hash 요구 또는 포함
SourcePlanOutcome이 closed three-state enum 밖 값을 사용하거나 한 plan에 두 outcome을 기록
nonterminal_blocked outcome에 SourceAvailabilityClosure, metadata snapshot, exhaustion 또는 data_unavailable terminal reference 삽입
nonterminal_blocked outcome의 blockingReason/evidence/affectedStudySlots/reopenCondition/observedAt 중 하나 누락
단계 authorization 없이 후속 manifest/reader 생성
synthetic audit가 `ER-*` ID 또는 ExperimentRun schema를 사용
AE/SVR consume에 reservation 누락, duplicate/reused reservation 또는 cross-namespace ID
AE/SVR allocator가 기존 high-water 이하 ID를 재사용하거나 ID syntax를 혼합
EligibilityDecision이 holdout/result/DecisionRecord를 참조하거나 adoption을 판정
historical frozen graph snapshot을 current lifecycle 값으로 덮어쓰기
lifecycle 상태를 descriptor in-place 수정으로 전이
artifact binding에 exact path/hash/mediaType/role 누락
public API/type annotation이 `ArtifactBindingV2` 대신 legacy `ArtifactBinding`을 사용
raw/processed/closure repo artifact에 absolute/home/tmp path 또는 sink local root 직렬화
ExternalArtifactLocator의 sinkId/artifactId/contentSha256/relativeContentAddressKey/sinkDescriptorHash 누락
relativeContentAddressKey가 absolute, URI, `..` 포함 또는 content-address 규칙 불일치
v1 descriptor가 표현할 수 없는 path/hash를 자유 문자열로 삽입
MathDispositionEvent의 disposition에 adopt 삽입
DecisionRecord의 gate failure와 adopt 동시 기록
EvidenceBundle의 numeric claim에 run/evidence artifact hash 누락
ExperimentRun의 protocol/design/input/code hash 누락
ExperimentRun lineage의 plannedRunKey, executorIdentityBindingSha256,
 checkoutInstanceBindingSha256, sourceTreeSha256, environmentSha256 누락
CompletionObligation의 requirement별 evidence type 누락
requirement→evidence만 있고 evidence→requirement backreference 누락
claim 또는 artifact path에 SHA-256 binding 누락
completion/applicability/obligation rule에 observed result, holdout metric, evidence ID 또는 DecisionRecord 포함
254 requirement semantic definition 중 하나 누락·중복 또는 expectedCardinality/requiredEvidenceTypes를 결과 후 변경
first empirical read 뒤 predata rule freeze 생성·수정 또는 frozen rule file 덮어쓰기
gate applicability rule 없이 not_applicable 허용하거나 DR 결과를 보고 applicability 변경
기존 v1 validator/test 또는 `rp001/__init__.py` bytes 변경, v1 CLI에 graph-mode 옵션 추가
신규 v2 descriptor/body `object.json`이 `research/meta-research/objects/` 아래 생성됨
v2 validator가 `objects-v2/` 이외 descriptor root를 scan하거나 package `__init__` export를 통해 import하거나 historical/current 결과를 하나의 mode로 혼합
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_evidence_contracts.py \
                  research/rp-001/tests/test_audit_execution.py -v
```

Expected RED: 최소 importable schema validator가 unknown field, final-CD self/future reference와 own-receipt field를 잘못 수락하여 `test_closed_world_rejects_unknown_field`, `test_canonical_body_rejects_self_hash`, `test_final_cd_rejects_self_and_future_references`, `test_every_canonical_body_rejects_own_external_receipt`, `test_terminal_event_cannot_reference_future_evidence_bundle`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: schema의 closed-world 필드를 구현한다**

각 schema는 `additionalProperties=false`와 다음 핵심 필드를 강제한다.

```text
FormulaRecord: formulaId, version, family, kind, purpose, economicMechanism,
 expression, domain, codomain, outputRange, inputSymbols, predictionTargets,
 horizons, invariances, missingPolicy, oodPolicy, sourceRefs,
 implementationBindingIds, sourceDisposition, auditStatus, provenanceHashes

CandidateAuditAliasRecord: aliasId, sourceCandidateId, sourceDefinitionSha256,
 provenanceLane, empiricalEligibility, allowedUses, referenceAuditId,
 blockingReason, createdAt

ImplementationBinding: bindingId, formulaId, modulePath, callableName,
 referenceModulePath, referenceCallableName, inputMap, outputContract,
 codeSha256, referenceSha256, tolerance, testPath, equivalenceStatus, evidenceIds

FormulaAudit: auditId, formulaId, formulaRecordSha256, obligations,
 rewardHackingChecks, counterexamples, auditStatus,
 limitations, reviewer, createdAt

MathDispositionEvent: eventId, formulaId, formulaRecordSha256,
 formulaAuditCoverageCertificateSha256, disposition, evidenceIds,
 independentReviewerBinding, sequence, previousRecordSha256, recordSha256

FormulaAuditCoverageCertificate: certificateId, formulaRegistrySha256,
 formulaIds, obligationIds, expectedCellCount, observedCellCount,
 matrixProjectionSha256, coverage, independentReviewerBinding, createdAt

EligibilityDecision: eligibilityDecisionId, formulaId, formulaRecordSha256,
 bindingSha256, formulaAuditCoverageCertificateSha256, mathDispositionEventSha256,
 allowedStudySlots, eligibility,
 blockingReasons, reviewer, frozenAt

StudyCandidateAdmission: admissionId, studySlot, formulaId,
 eligibilityDecisionSha256, sourceAcceptanceHashes, inputContractHashes,
 sourceAvailabilityClosureHashes, inputSymbolSourceBindings,
 ontologyNameMappingSha256, dataLineageEligibilitySnapshotSha256,
 dataLineageDispositionHashes, sourcePlanOutcomeBindings,
 admission, blockingReasons, frozenAt

AuditExecution: auditExecutionId, formulaId, auditType, syntheticInputHashes,
 codeSha256, environmentSha256, status, outputBindings, createdAt

AuditExecutionReservation: reservationId, reservedAuditExecutionId,
 auditKey, protectedPathManifestSha256, sequence, previousRecordSha256,
 recordSha256, reservedAt

SyntheticVerificationRun: syntheticRunId, contractId, seed, generatorSha256,
 codeSha256, environmentSha256, status, outputBindings, createdAt

SyntheticVerificationReservation: reservationId, reservedSyntheticRunId,
 verificationKey, protectedPathManifestSha256, sequence,
 previousRecordSha256, recordSha256, reservedAt

StudyTerminalEvent: terminalEventId, studySlot, predecessorStatus,
 terminalDecisionRuleId, terminalDecisionRuleSha256, matchedPredicateId,
 terminalStatus, terminalDecisionComputationSha256, inputArtifactBindings,
 runEventHeadHashes, sourceClosureHashes, adjudicationReviewHashes,
 reviewerIds, lifecycleSnapshotSha256, createdAt

TerminalDecisionComputation: computationId, studySlot,
 terminalDecisionRuleSha256, orderedInputArtifactBindings,
 runEventHeadHashes, sourceClosureHashes, adjudicationReviewHashes,
 matchedPredicateId, terminalStatus, evaluatorCodeSha256, computedAt

ArtifactBindingV2: bindingId, ownerId, role, mediaType, exactPath,
 artifactSha256, historicalSnapshotSha256, currentLifecycleEventId

ArtifactExternalAnchorBindingEvent: anchorBindingEventId, artifactBindingId,
 exactArtifactPath, artifactSha256, externalReceiptId, externalReceiptSha256,
 anchoredBundleSha256, anchorAuthorityFingerprint, sequence,
 previousRecordSha256, recordSha256, createdAt

ExternalArtifactLocator: sinkId, artifactId, contentSha256,
 relativeContentAddressKey, sinkDescriptorHash

ExternalSinkDescriptor: sinkId, descriptorVersion, permissionMode, ownerPolicy,
 vcsExclusionPolicy, retentionPolicy, tombstonePolicy, resolverKey,
 resolverConfigSha256, approverBinding, predecessorDescriptorEventId, createdAt

SourceMetadataAcceptance: acceptanceId, studySlot, providerId, officialDocumentBindings,
 rights, entitlement, retention, derivedPublication, redistribution,
 timestampTimezoneSessionContract, unitCorporateActionRevisionContract,
 providerAuthRequirement, credentialStatus, nonsecretRotationProvenance, createdAt

DesignMetadataCaptureAuthorization: authorizationId, acceptanceSha256,
 declaredMetadataClasses, endpointOperationIds, fieldAllowlist, expiresAt,
 protectedPathManifestSha256, sourceAcceptanceAnchorReceiptSha256

UniverseMetadataSnapshot: snapshotId, authorizationSha256,
 declaredMetadataClasses, actualMetadataClasses, responseArtifactBindings,
 responseHashes, clientReceivedAt, selectionRule,
 designMetadataAuthorizationAnchorReceiptSha256

ProcessingCodeBundleManifest: manifestId, sourceFileBindings,
 callableBindings, dependencyLockBindings, environmentLockSha256,
 sortedFileSetDigest, protectedPathManifestSha256

AnalysisCodeBundleManifest: manifestId, sourceFileBindings, testFileBindings,
 callableAndModelClassBindings, formulaRecordBindings, ontologyNameMappingSha256,
 dependencyLockBindings, environmentLockSha256, sortedFileSetDigest,
 protectedPathManifestSha256

RawCollectionAuthorization: authorizationId, sourceAcceptanceHashes,
 universeMetadataSnapshotSha256, reservationLineageBindingEventSha256,
 finalConfirmationDesignSha256, finalProtocolHashes, sourceUniversePeriodFields,
 sinkDescriptorSha256, processingCodeBundleManifestSha256,
 analysisCodeBundleManifestSha256, protectedPathManifestSha256,
 universeMetadataSnapshotAnchorReceiptSha256,
 reservationLineageAnchorReceiptSha256, sinkDescriptorAnchorReceiptSha256,
 processingCodeBundleAnchorReceiptSha256, analysisCodeBundleAnchorReceiptSha256

RawCaptureManifest: manifestId, rawArtifactLocators, clientReceivedAt,
 rawCollectionAuthorizationSha256, sinkDescriptorSha256,
 rawCollectionAuthorizationAnchorReceiptSha256

ProcessingAuthorization: authorizationId, rawCaptureManifestSha256,
 processingCodeBundleManifestSha256, processedSchemaContractSha256,
 protectedPathManifestSha256, rawCaptureManifestAnchorReceiptSha256,
 processingCodeBundleAnchorReceiptSha256

ProcessedManifest: manifestId, processedArtifactLocators,
 rawCaptureManifestSha256, processingAuthorizationSha256,
 processingCodeBundleManifestSha256, schemaAndUnitSummary,
 rowCount, availabilityBounds, processingAuthorizationAnchorReceiptSha256

ActualRunLineageBindingEvent: eventId, plannedRunKey,
 finalConfirmationDesignSha256, finalProtocolSha256,
 rawCaptureManifestSha256, processingAuthorizationSha256, processedManifestSha256,
 processingCodeBundleManifestSha256, analysisCodeBundleManifestSha256,
 executorIdentityBindingSha256, checkoutInstanceBindingSha256,
 sourceTreeSha256, environmentSha256,
 reservationLineageAnchorReceiptSha256, processedManifestAnchorReceiptSha256,
 processingCodeBundleAnchorReceiptSha256, analysisCodeBundleAnchorReceiptSha256

ExperimentRun: runId, runKey, studySlot, protocolId, protocolSha256,
 confirmationDesignId, confirmationDesignSha256, candidateId,
 formulaRecordSha256, implementationBindingSha256, datasetManifestSha256,
 sampleRole, foldId, horizon, seed, controlKind,
 processingCodeBundleManifestSha256, analysisCodeBundleManifestSha256,
 executorIdentityBindingSha256, checkoutInstanceBindingSha256,
 sourceTreeSha256, environmentSha256, actualRunLineageBindingEventId,
 status, timestamps, outputArtifacts, failure

EvidenceBundle: evidenceId, claimId, requirementIds, questionIds, studySlots,
 protocolIds, runIds, sourceAcceptanceIds, results, gateResults,
 supportingArtifacts, contradictingArtifacts, invalidRuns, limitations,
 reproduction, terminalStatus, terminalEventBindings,
 terminalAnchorBindingEventHashes, createdAt

DecisionRecord: decisionId, targetIds, evidenceIds, gateResults,
 mathDispositions, decision, scope, operationalUse, noTradeConditions,
 residualRisks, reviewer, reconsideration, createdAt

CompletionObligation: obligationId, requirementId, requiredEvidenceTypes,
 predicateId, targetType, expectedCardinality, observedTargetBindings,
 evidenceBindings, decisionIds, reportBindings, bidirectionalBackreferences,
 completionStatus, reviewer, createdAt

CompletionObservationBindingEvent: eventId, requirementId,
 requirementDefinitionSha256, predicateId, predicateSha256, observedTargetBindings,
 evidenceBindings, decisionBindings, reportBindings, bidirectionalBackreferences,
 evaluationStatus, evaluatorCodeSha256, sequence, previousRecordSha256,
 recordSha256, observedAt

CompletionPredicate: predicateId, version, targetType, targetSelector,
 expectedCardinalityRule, requiredEvidenceTypes, terminalRule,
 evaluatorName, evaluatorCodeSha256

GateApplicabilityRule: ruleId, gateId, targetType, applicabilityPredicate,
 allowedNonAdoptDecisions, requiredEvidenceTypes, frozenAt

RequirementObligationDefinition: requirementId, predicateId, targetType,
 expectedCardinalityRule, requiredEvidenceTypes, terminalRule

PreDataRuleFreeze: freezeId, version, predicateRegistrySha256,
 gateApplicabilityRulesSha256, requirementDefinitionsSha256,
 studyTerminalDecisionRulesSha256, requiredDeliverableRegistrySha256,
 protectedPathManifestSha256, artifactBindings, frozenAt,
 firstEmpiricalReadMustBeAfter

RequiredDeliverableRegistry: registryId, version, deliverableRows,
 exactDeliverableIds, exactPathSet, ownerUnitSet, protectedPathManifestSha256,
 frozenAt

StudyTerminalDecisionRule: ruleId, studySlot, estimandId,
 terminalizableDomainPredicate, precedence, statusPredicates,
 intervalDecisionRegions, requiredGatePredicates, closurePredicate,
 acceptedRunPredicate, failurePredicates, nonTerminalBlockedPredicate,
 evaluatorName, evaluatorCodeSha256, frozenAt

AppendTransactionIntent: transactionId, ledgerId, expectedAnchoredSequence,
 expectedAnchoredHeadSha256, proposedSequence, stagedBindings,
 protectedPathManifestSha256, createdAt

AppendTransactionCommit: transactionId, ledgerId, proposedSequence,
 eventBinding, localHeadBinding, projectionBinding, fsyncAttestation,
 committedAt

AppendRecoveryEvent: recoveryEventId, transactionId, orphanBindings,
 disposition, successorSequence, previousRecordSha256, recordSha256, createdAt

ExternalHeadAnchorReceipt: receiptId, ledgerId, anchoredSequence,
 anchoredHeadSha256, anchoredBundleSha256, priorAnchoredSequence,
 priorAnchoredHeadSha256, authorityType, authorityKeyFingerprint,
 signatureOrProtectedRemoteProof, issuedAt

ExecutorIdentityBinding: identityBindingId, pseudonymousRoleFingerprint,
 signingKeyFingerprint, sessionBindingSha256, checkoutInstanceBindingSha256,
 environmentSha256, signature, createdAt

ReproductionRightsAttestation: attestationId, version,
 processedManifestHashes, sourceAcceptanceHashes, permittedReproductionPurpose,
 reproductionRights, retentionDeadline, derivedUsePolicy, redistributionPolicy,
 resolverScope, reproductionResolverConfigSha256, approverBindingSha256,
 independentReviewerBindingSha256, createdAt

ReproductionAttestation: attestationId, originalExecutorBindingSha256,
 reproducerExecutorBindingSha256, originalCheckoutInstanceBindingSha256,
 reproducerCheckoutInstanceBindingSha256, sourceTreeSha256,
 cleanCheckoutAttestation, environmentSha256, reproductionManifestSha256,
 reproductionManifestAnchorReceiptSha256, reproducedArtifactBindings,
 toleranceReport, signature, createdAt

IndependentReviewerAttestation: attestationId, reviewerRoleFingerprint,
 reviewerSigningKeyFingerprint, reproductionAttestationSha256,
 reproductionAttestationAnchorReceiptSha256, disjointnessPredicateResult,
 signature, createdAt

ReproductionInputAuthorization: authorizationId, version,
 reproducerRoleFingerprint, reproducerSigningKeyFingerprint,
 sourceExperimentRunIds, sourceActualRunLineageHashes,
 processedInputLocators, expectedContentHashes, processedManifestHashes,
 processingCodeBundleManifestSha256, analysisCodeBundleManifestSha256,
 rightsAttestationExactPath, rightsAttestationSha256, entitlementScope,
 permittedReproductionPurpose,
 derivedUsePolicy, retentionDeadline, tombstonePolicy,
 reproductionResolverKey, reproductionResolverConfigSha256,
 reproductionOutputSinkId, reproductionOutputSinkDescriptorSha256,
 environmentManifestSha256, sourceTreeSha256, expiresAt,
 protectedPathManifestSha256, reviewerBindingSha256,
 rightsAttestationAnchorReceiptSha256, processedManifestAnchorReceiptHashes,
 reproductionOutputSinkAnchorReceiptSha256

ReproductionManifest: manifestId, reproductionInputAuthorizationSha256,
 sourceExperimentRunIds, seedBindings, processedInputRehashes,
 processingCodeBundleManifestSha256, analysisCodeBundleManifestSha256,
 environmentManifestSha256, outputArtifactLocators, aggregateHashes,
 toleranceReport, resolverConfigSha256, outputSinkDescriptorSha256,
 reproductionInputAuthorizationAnchorReceiptSha256,
 outputSinkDescriptorAnchorReceiptSha256, createdAt

EvidenceCliCommandDispatchRegistry: registryId, version, orderedCommandIds,
 commandBindings, protectedManifestArgumentName, exactInvokedCommandSetSha256,
 registryCodeSha256, frozenAt

SourceAvailabilitySearchPlan: planId, version, studySlot, sourceId,
 requiredFieldIds, plannedSources, exactEndpointOperationIds,
 requestCap, stopRule, coverageDenominator, alternativeSourceRule,
 independentReviewerBinding, protectedPathManifestSha256, frozenAt,
 sequence, previousRecordSha256, recordSha256

SourcePlanSetManifest: manifestId, version, registeredStudyInputContractSha256,
 orderedPlanIds, planArtifactBindings, expectedPlanCount,
 studySourceFieldCellSet, protectedPathManifestSha256, frozenAt

SourcePlanOutcome: outcomeId, searchPlanId, searchPlanSha256, studySlot,
 outcome, sourceMetadataAcceptanceSha256, universeMetadataSnapshotSha256,
 sourceAvailabilityClosureSha256, blockingReason, blockingEvidenceBindings,
 affectedStudySlots, reopenCondition, observedAt, reviewerBinding

SourceAvailabilityClosure: closureId, studySlot, sourceId, searchPlanId,
 searchPlanSha256, searchPlanFrozenAt, firstRequestAt, finalRequestAt,
 requestAuditEventIds, requestResponseLocators, attemptedCoverageNumerator,
 plannedCoverageDenominator, alternativeSourceDisposition,
 independentReviewerBinding, closureReason, createdAt

DataLineageDisposition: dispositionId, studySlot, sourcePlanId,
 sourceAcceptanceHashes, sourceAvailabilityClosureHashes,
 sourcePlanOutcomeSha256, inputContractHashes, inputSymbolSourceBindings, classification,
 affectedFormulaIds, affectedRequiredFieldIds, reviewerBinding, createdAt

DataLineageEligibilitySnapshot: snapshotId, sourcePlanSetManifestSha256,
 orderedSourcePlanOutcomeBindings, dataLineageDispositionHashes,
 eligiblePlanIds, exhaustedPlanIds, blockedPlanIds,
 eligibleStudyInputBindings, blockedStudyInputBindings,
 independentReviewerBindings, createdAt
```

`SourcePlanOutcome.outcome`의 closed enum은 정확히 `eligible_metadata | exhausted_unavailable | nonterminal_blocked`다. conditional `oneOf`는 eligible branch에 anchored SourceMetadataAcceptance와 UniverseMetadataSnapshot만, exhausted branch에 complete SourceAvailabilityClosure만, blocked branch에 nonempty `blockingReason`, exact `blockingEvidenceBindings`, `affectedStudySlots`, `reopenCondition`, `observedAt`만 허용한다. `nonterminal_blocked`에는 SourceAvailabilityClosure, metadata snapshot, attempted exhaustion 또는 data_unavailable terminal reference를 금지한다.

`evidenceBindings`는 requirement가 요구하는 evidence type별로 `evidenceId`, `claimId`, `artifactPath`, `artifactSha256`를 갖고, 연결된 EvidenceBundle에도 같은 requirement ID와 claim/artifact hash가 역참조되어야 한다. `reportBindings`도 exact file path와 hash를 사용하며 directory만 참조할 수 없다.

모든 repository artifact reference field와 public API annotation은 `ArtifactBindingV2`만 사용한다. `AuditExecution.outputBindings`, `SyntheticVerificationRun.outputBindings`, `ExperimentRun.outputArtifacts`, EvidenceBundle supporting/contradicting artifacts와 CompletionObligation evidence/report bindings는 schema `$ref`로 `artifact-binding.v2.schema.json`에 결박한다. external raw/processed/closure bytes만 `ExternalArtifactLocator`를 사용하고 두 타입을 혼용하지 않는다.

meta-research v1 descriptor와 catalog bytes는 historical snapshot으로 보존한다. v1에 표현할 수 없는 exact artifact path/hash는 `ArtifactBindingV2` object가 소유하고, `ResearchGraphSnapshotV2`가 frozen historical descriptor hash와 append-only current lifecycle event head를 분리해 결박한다. `HistoricalGraphValidator`는 과거 snapshot bytes만, `CurrentLifecycleGraphValidator`는 lifecycle event chain·binding·current projection만 검증한다. descriptor의 현행 필드명은 `lifecycleState`이며 이를 수정해 전이하지 않는다.

- [ ] **Task 1A GREEN과 schema review를 통과한다**

Run: Task 1A Step 1과 동일한 두 test module.

Expected GREEN: strict schema/canonical/sidecar mutation 전체가 `OK`, artifact canonical body의 self-hash field 0, `recordSha256`은 자기 field 제외 chain checksum으로만 사용된다. schema reviewer가 closed-world field, self-hash 배제와 `ArtifactBindingV2` SSOT를 승인하기 전 Task 1B로 가지 않는다.

#### Task 1B execution unit: v2 graph, crash-safe append, external anchor

**Files:** `canonical_artifact.py`, `append_transaction.py`, `external_head_anchor.py`, `research_graph.py`, `test_research_graph.py`, `test_append_transaction.py`, `test_external_head_anchor.py`, `validate_research_program_v2.py`, `test_validate_research_program_v2.py`, program의 intent/commit/recovery/receipt exact directories와 sidecars.

- [ ] **Task 1B RED로 별도 object root와 외부 신뢰 경계를 고정한다**

다음 mutation을 독립 test로 먼저 작성한다.

```text
v2 validator가 objects/ 아래 신규 object.json을 발견·수락
v1 validator가 objects-v2/를 scan하거나 historical object count가 30이 아님
local event/head/projection이 `.pending_unanchored` suffix를 갖지 않음
suffix를 anchor 뒤 제거·rename·rewrite하거나 prefix file 삭제
local head만으로 EvidenceBundle·terminal·checkpoint·completion 통과
signed WORM/protected-remote proof가 아닌 fake receipt 또는 authority fingerprint mismatch
anchored sequence rollback, prior head mismatch, skipped sequence, CAS 없이 receipt 삽입
target artifact CAS receipt 전에 ArtifactExternalAnchorBindingEvent 발행
ArtifactExternalAnchorBindingEvent와 target artifact path/hash/receipt/bundle hash 불일치
anchor-binding event가 자기 external receipt를 canonical body에 삽입
intent 없이 event, full local bundle fsync 전 anchor call, commit 없이 anchor call
intent/event만, event/head만, head/projection만, commit/receipt 전후 각 crash phase
crash recovery가 orphan intent/event/head/projection/commit을 삭제·덮어쓰기
recovery가 deterministic finalize 또는 append-only invalidation/recovery 이외 동작
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_research_graph.py \
                  research/rp-001/tests/test_append_transaction.py \
                  research/rp-001/tests/test_external_head_anchor.py \
                  research/meta-research/tools/test_validate_research_program_v2.py -v
```

Expected RED: 최소 importable append coordinator가 local head를 external receipt로 오인하여 `test_local_head_cannot_satisfy_external_anchor`와 `test_recovery_preserves_prefix_and_monotonic_sequence`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니며 fake receipt나 local suffix file은 evidence port에 도달하지 못해야 한다.

- [ ] **Task 1B GREEN으로 strict canonical artifact와 transaction API를 구현한다**

공개 API는 다음 서명을 유지한다.

```text
load_strict_json(path: Path) -> Mapping[str, object]
canonical_json_bytes(value: object) -> bytes
sha256_bytes(source: bytes) -> str
sha256_canonical_json(value: object) -> str
verify_hash_sidecar(artifact: Path, sidecar: Path) -> None
ImmutableRecordLedger.validate_chain(recordPaths: Sequence[Path], anchoredReceipt: ExternalHeadAnchorReceipt) -> None
ImmutableRecordLedger.stage_record(transaction: AppendTransaction, record: Mapping[str, object]) -> ArtifactBindingV2
DerivedProjectionBuilder.rebuild(eventPaths: Sequence[Path], outputPath: Path) -> ArtifactBindingV2
ExternalHeadAnchorPort.compare_and_swap(request: ExternalHeadAnchorRequest) -> ExternalHeadAnchorReceipt
AppendTransactionCoordinator.append(command: AppendCommand, anchor: ExternalHeadAnchorPort) -> AnchoredAppendResult | PendingUnanchoredResult
AppendTransactionCoordinator.recover(transactionId: str, anchor: ExternalHeadAnchorPort) -> AppendRecoveryResult
HistoricalGraphValidator.validate(snapshot: ResearchGraphSnapshotV2) -> GraphValidationReport
CurrentLifecycleGraphValidator.validate(snapshot: ResearchGraphSnapshotV2, lifecycleEvents: Sequence[LifecycleEvent]) -> GraphValidationReport
AuditExecutionRepository.consume_reservation(reservation: AuditExecutionReservation) -> AuditExecutionEvent
AuditExecutionRepository.append_terminal(executionId: str, result: AuditResult) -> AuditExecutionEvent
SyntheticVerificationRepository.consume_reservation(reservation: SyntheticVerificationReservation) -> SyntheticVerificationEvent
SyntheticVerificationRepository.append_terminal(syntheticRunId: str, result: SyntheticResult) -> SyntheticVerificationEvent
GlobalAuditExecutionIdAllocator.reserve(auditKeys: Sequence[AuditKey], protectedPathManifestSha256: str) -> Sequence[AuditExecutionReservation]
GlobalSyntheticVerificationIdAllocator.reserve(verificationKeys: Sequence[VerificationKey], protectedPathManifestSha256: str) -> Sequence[SyntheticVerificationReservation]
ArtifactExternalAnchorBindingPublisher.publish(targetBinding: ArtifactBindingV2, targetReceipt: ExternalHeadAnchorReceipt) -> ArtifactExternalAnchorBindingEvent
AnchorEligibilityVerifier.require_anchored(targetBinding: ArtifactBindingV2, anchorBindingEvent: ArtifactExternalAnchorBindingEvent, anchorBindingEventReceipt: ExternalHeadAnchorReceipt) -> AnchoredArtifactBinding
```

`validate_research_program_v2.py`는 `canonical_artifact.py`와 `research_graph.py`의 필요 symbol을 file/module path에서 직접 import하고 `rp001/__init__.py`에 export를 추가하지 않는다. 기존 v1 CLI와 test는 byte-for-byte 불변이고 기존 인자 계약과 `objects/` scan만 검증한다. 신규 v2 CLI만 `--graph-mode historical-snapshot|current-v2`를 받아 current mode에서 `objects-v2/`만 discover한다.

canonical JSON은 UTF-8, allow_nan=False, ensure_ascii=False, key 정렬, compact separators, trailing LF 없음이다. sidecar만 lowercase 64-hex와 LF 한 개를 사용한다. 각 immutable event file은 record 정확히 하나만 가지며, ledger record hash는 recordSha256 필드를 제외한 canonical record bytes로 계산한다. 모든 local event/head/projection은 pending_unanchored suffix를 영구 유지한다. coordinator는 intent file과 sidecar를 fsync하고 atomic rename+directory fsync한 뒤 event, local head, projection 각각을 같은 순서로 fsync·publish한다. commit record와 sidecar까지 full fsync한 뒤에만 대상 artifact bundle을 외부 CAS에 제출한다.

CAS 성공 뒤 receipt를 검증·fsync한 다음에만 별도 후속 append transaction으로 ArtifactExternalAnchorBindingEvent를 발행한다. 이 event는 target ArtifactBindingV2, exact path, artifact SHA-256, external receipt ID/hash, anchored bundle SHA-256과 authority fingerprint를 결박한다. anchor-binding event 자체도 full fsync 뒤 외부 CAS로 anchor하며 그 receipt는 external authority receipt index와 local verified receipt copy에서 검증할 뿐 event canonical body에 넣지 않는다. 대상 artifact와 anchor-binding event/receipt가 모두 검증된 경우에만 AnchoredArtifactBinding으로 승격한다. downstream canonical body는 processedManifestAnchorReceiptSha256처럼 이미 존재하는 predecessor receipt를 구체적 field로 참조할 수 있지만 own receipt field는 가질 수 없다. suffix file rename API, 기존 file/head overwrite API와 local-only evidence API는 제공하지 않는다.

crash injector는 intent publish, event publish, head publish, projection publish, commit publish, external anchor success, receipt local-copy 직전·직후 모든 phase를 끊는다. recovery는 orphan을 보존하며 intent의 staged bindings와 bytes가 같으면 남은 phase를 재개하고, 다르면 orphan bindings를 참조하는 recovery/invalidation record를 새 sequence로 append한다. anchor authority가 구성되지 않은 정상 환경은 오류를 발명하지 않고 `PendingUnanchoredResult`를 반환한다.

AE/SVR도 ER과 분리된 global reservation allocator, one-record reservation/event, local head candidate와 각 JSON/Markdown의 독립 sidecar를 사용한다. ID syntax는 reservation AER-000001→execution AE-000001, reservation SVRR-000001→verification SVR-000001의 six-digit namespace로 고정한다. allocator는 namespace별 global high-water 뒤에서 audit/verification key 정렬순으로 원자 예약하고 publisher/repository는 unconsumed exact reservation 한 번만 소비한다. duplicate/reuse/cross-namespace/unreserved consume는 event append 전에 거부한다. AE/SVR ID가 ER namespace나 ExperimentRun catalog/type/count에 들어가거나 G6~G10·empirical completion에 연결되면 schema validation이 실패한다. 모든 canonical event, head pin, projection, authorization, manifest, CD, run, EB, DR, SR의 JSON/Markdown file 각각은 자기 bytes를 결박한 별도 sidecar를 가져야 한다. evidence use에는 target artifact의 post-CAS ArtifactExternalAnchorBindingEvent와 그 event의 external receipt가 모두 필요하다.

terminal publication도 같은 비순환 규칙을 따른다. frozen evaluator가 exact run/closure/adjudication inputs로 TerminalDecisionComputation을 만들고 anchor한 뒤, 별도 transaction의 StudyTerminalEvent가 그 computation hash와 exact input bindings만 참조한다. terminal event를 anchor한 다음에야 또 다른 transaction에서 EvidenceBundle이 terminal event binding과 predecessor terminal anchor receipt를 참조한다. StudyTerminalEvent는 future EB ID/hash를 가지지 않고 terminal과 EB를 같은 append transaction에 넣지 않는다.

Run: Task 1B RED command와 동일.

Expected GREEN: v1 scan은 frozen `objects/` 30개, v2 scan은 `objects-v2/` 신규 descriptor exact set이다. crash phase 전부에서 prefix/orphan bytes가 보존되고 finalize 또는 invalidation/recovery만 발생한다. fake/rollback receipt 0건 수락, external authority가 없을 때 anchored evidence count 0과 local pending work count>0이 정상이다. graph/transaction reviewer가 root split, fsync order, CAS와 recovery를 승인하기 전 Task 1C로 가지 않는다.

#### Task 1C execution unit: pre-data semantic, terminal and required-deliverable rules

**Files:**

- Create code/tests: completion_predicates.py, freeze_predata_rules.py, test_completion_predicates.py
- Create canonical registries with sidecars: completion-predicate-registry.json, gate-applicability-rules.json, requirement-obligation-definitions.json, study-terminal-decision-rules.json, required-deliverable-registry.json
- Create only after GREEN: predata-rule-freeze.json and sidecar
- Register all six canonical artifacts through ArtifactBindingV2, lifecycle, traceability, ArtifactExternalAnchorBindingEvent and current-v2 projections

- [ ] **Task 1C behavioral RED를 먼저 실행한다**

test를 먼저 작성하고 최소 importable counterexample freezer가 overlapping terminal predicates와 required-deliverable row 하나가 빠진 registry를 수락하도록 만든다. 같은 command에서 test_terminal_rules_are_total_and_mutually_exclusive, test_required_deliverable_registry_is_exact, test_freeze_rejects_result_dependent_rules가 assertion failure여야 한다. import/discovery/syntax/file-existence failure는 RED가 아니다. RED 단계에서는 canonical registry나 predata freeze artifact를 publish하지 않는다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_completion_predicates.py -v
~~~

- [ ] **semantic total-functions와 RequiredDeliverableRegistry를 구현한다**

completion, applicability, 254 requirement obligation과 8 study terminal rule은 exact set-equality로 닫는다. terminal rule은 status overlap, terminalizable-domain gap, precedence mismatch, blocked-as-terminal, estimand/interval/Gate/source-closure/accepted-run/failure input 누락과 exact-one 위반을 거부한다.

~~~text
StudyTerminalDecisionEvaluator.decide(rule: StudyTerminalDecisionRule, state: StudyEvidenceState) -> StudyTerminalDecision | NonTerminalBlocked
PreDataRuleFreezer.freeze(predicates: Sequence[CompletionPredicate], applicabilityRules: Sequence[GateApplicabilityRule], obligations: Sequence[RequirementObligationDefinition], terminalRules: Sequence[StudyTerminalDecisionRule], requiredDeliverables: RequiredDeliverableRegistry, protectedPathManifestSha256: str) -> PreDataRuleFreeze
PreDataRuleFreezer.verify(freeze: PreDataRuleFreeze) -> PreDataRuleFreezeReport
CompletionPredicateEvaluator.evaluate(predicate: CompletionPredicate, targets: Sequence[PredicateTarget], evidence: Sequence[EvidenceBundle]) -> PredicateEvaluation
RequiredDeliverableRegistryValidator.validate(registry: RequiredDeliverableRegistry) -> RequiredDeliverableRegistryReport
~~~

RequiredDeliverableRegistry의 각 row는 deliverableId, exactArtifactPath, schemaId, mediaType, ownerTaskUnit, requiredCardinality, evidenceTraceabilityBackreferenceRule, sidecarRequired=true, externalAnchorBindingRequired=true를 모두 가진다. 최소 exact rows는 다음과 같다.

| deliverableId | exact artifact path | schema/media | owner | cardinality | binding rule |
| --- | --- | --- | --- | --- | --- |
| RD-001 | research/rp-001/reports/requirement-trace-matrix.json | trace-matrix/JSON | Task14D | 1 | sidecar+anchor+v2↔trace |
| RD-002 | research/rp-001/reports/research-question-ledger.json | rq-ledger/JSON | Task14D | 1 | sidecar+anchor+v2↔trace |
| RD-003 | research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ontology-name-mapping.json | ontology-map/JSON | Task6D | 1 | sidecar+anchor+v2↔trace |
| RD-004 | research/rp-001/reports/dataset-contract-register.json | dataset-contract/JSON | Task7D | 1 | sidecar+anchor+v2↔trace |
| RD-005 | research/rp-001/reports/source-matrix.current.json | source-matrix/JSON | Task7D | 1 | sidecar+anchor+v2↔trace |
| RD-006 | research/meta-research/objects/programs/RP-001-quantitative-market-behavior/implementation-bindings.pending_unanchored.json | implementation-binding/JSON | Task3 | 1 | sidecar+anchor+v2↔trace |
| RD-007 | research/rp-001/reports/formula-proof-counterexample-reward-audit.json | formula-audit-table/JSON | Task6B | 1 | sidecar+anchor+v2↔trace |
| RD-008 | research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-registry.pending_unanchored.json | formula-registry/JSON | Task2 | 1 | sidecar+anchor+v2↔trace |
| RD-009 | research/rp-001/reports/trial-ledger-register.json | trial-register/JSON | Task13 | 1 | sidecar+anchor+v2↔trace |
| RD-010 | research/rp-001/reports/raw-capture-manifest-register.json | raw-manifest-register/JSON | Task10B | 1 | sidecar+anchor+v2↔trace |
| RD-011 | research/rp-001/reports/processed-manifest-register.json | processed-manifest-register/JSON | Task10B | 1 | sidecar+anchor+v2↔trace |
| RD-012 | research/rp-001/reports/experiment-run-register.json | experiment-run-register/JSON | Task13 | 1 | sidecar+anchor+v2↔trace |
| RD-013 | research/rp-001/reports/formula-success-failure-distributions.json | uncertainty-distribution/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-014 | research/rp-001/reports/symbol-era-horizon-regime-performance.json | performance-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-015 | research/rp-001/reports/event-intervals.json | event-interval-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-016 | research/rp-001/reports/phase-predictions.json | phase-prediction-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-017 | research/rp-001/reports/false-miss-lead-calibration.json | detection-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-018 | research/rp-001/reports/cost-slippage-impact-sensitivity.json | cost-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-019 | research/rp-001/reports/drawdown-var-cvar-stress.json | risk-table/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-020 | research/rp-001/reports/failure-invalid-not-identifiable-evidence-register.json | evidence-register/JSON | Task14B | 1 | sidecar+anchor+v2↔trace |
| RD-021 | research/rp-001/reports/independent-reproduction-report.json | reproduction-report/JSON | Task14C | 1 | sidecar+anchor+v2↔trace |
| RD-022 | research/meta-research/objects-v2/decision-records/DR-002-formula-dispositions/decision.json | decision-record/JSON | Task14D | 1 | sidecar+anchor+v2↔trace |
| RD-023 | research/meta-research/objects-v2/decision-records/DR-003-rp001-final-decision/decision.json | decision-record/JSON | Task14D | 1 | sidecar+anchor+v2↔trace |
| RD-024 | research/meta-research/objects-v2/synthesis-reports/SR-001-rp001-final-report/report.md | synthesis-report/Markdown | Task14D | 1 | sidecar+anchor+v2↔trace |
| RD-025 | research/rp-001/reports/execution-commands-environment.json | execution-environment/JSON | Task14D | 1 | sidecar+anchor+v2↔trace |

Registry exact row IDs and paths are frozen before data. Repeated raw/processed/run instances are closed through their exact register row: the register body enumerates every deterministic individual artifact path/hash and required cardinality from the relevant authorization/reservation SSOT. Directory-only reference, runtime-added deliverable ID, missing schema/media/owner/cardinality, absent sidecar or absent post-CAS anchor binding is invalid.

- [ ] **GREEN: RED와 동일한 exact unittest command를 실행한다**

Expected GREEN: 254/254 requirement definitions, predicate/applicability references, 8/8 terminal total-functions and RD-001 through RD-025 exact registry rows pass. missing artifact, wrong exact path, generic directory, wrong owner/cardinality, absent sidecar/anchor/traceability backreference mutations are rejected.

- [ ] **GREEN 뒤에만 six-artifact PreDataRuleFreeze를 publish한다**

freeze_predata_rules.py는 five predecessor registries, their sidecars, evaluator code hashes, protectedPathManifestSha256를 재해시해 sixth artifact predata-rule-freeze.json과 sidecar를 crash-safe transaction으로 발행한다. six artifacts 각각은 post-CAS ArtifactExternalAnchorBindingEvent까지 닫혀야 한다. rule/registry에는 observed outcome, holdout metric, EvidenceBundle/DecisionRecord ID가 없어야 한다. first governed search or accepted empirical read보다 freeze가 먼저여야 한다. historical Toss metadata-only probe는 preexistingExposure=true and ineligible for closure/source acceptance로 남으며 denominator나 Gate evidence가 아니다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/freeze_predata_rules.py --freeze \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/freeze_predata_rules.py --verify \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Expected: five predecessor registries plus PreDataRuleFreeze equals six canonical artifact/sidecar/anchor-binding records; first governed event before freeze count 0.

**Task 1C reviewer checkpoint:** reviewer는 RED와 GREEN이 동일 unittest command인지, freeze artifact가 GREEN 뒤에만 생성됐는지, 254 requirements, 8 terminal total-functions, RD-001–025 exact paths and six-artifact binding을 독립 검증한다. verdict 전 Task 2로 가지 않는다.

### Task 2: 11-family structured FormulaRecord와 input/binding registry

**Files:**
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/input-symbol-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-registry.pending_unanchored.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/rb-candidate-audit-alias-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/rb-candidate-audit-alias-registry.json.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/implementation-bindings.pending_unanchored.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-ledger.pending_unanchored.json`
- Create: `research/rp-001/src/rp001/formula_registry.py`
- Create: `research/rp-001/src/rp001/candidate_audit_alias_registry.py`
- Create: `research/rp-001/tests/test_formula_registry.py`
- Append authoritative registration events; rebuild v2 current projections only. Frozen v1 RP `object.json` remains byte-identical.

- [ ] **Step 1: RED로 P0 blocker를 명시한다**

다음 변이가 반드시 실패하는 test를 먼저 작성한다.

```text
11개 family 중 concrete FormulaRecord가 없는 family
exact rbCandidateAuditAliasIds 20개 중 하나 누락·중복·추가
RB alias를 FormulaRecord로 역직렬화하거나 `formulaRegistryIds`에 포함
`rbCandidateAuditAliasIds ∩ formulaRegistryIds`가 공집합이 아님
상단 study별 required control ID 하나라도 누락·추가·대체되어 set-equality 불일치
current formula-registry exact set이 historical 224 formula ID와 모든 새 RP empirical control/candidate ID의 union과 불일치
새 FormulaRecord를 denominator에서 빼거나 historical 224-only count를 전체 audit coverage로 사용
RB alias에 provenanceLane!=RB-001-audit
RB alias에 empiricalEligibility!=false
RB alias의 allowedUses가 DR-001 허용 세 역할과 set-equality 불일치
RB performance/results/threshold/weight를 empirical formula 또는 SG5 candidate source로 참조
registry_only family를 FormulaRecord/ImplementationBinding 없이 실행 가능으로 표시
expression token이 input-symbol-registry에 없음
input symbol의 unit/dimension/availabilityRule/DC reference 누락
FormulaRecord가 선언한 callable path/function이 실제로 없음
`gradient_boosted_tree`/`temporal_neural_model` ID를 NumPy simple nonlinear callable/model class에 결박
sourceDisposition을 adopt로 자동 변환
FormulaRecord registration에 final math disposition 또는 assessed audit status 삽입
not_identifiable 입력을 0 또는 neutral default로 선언
repair candidate eligibility가 post-evidence DR-002/DR-003 존재를 요구
Task 2 registration 중 EligibilityDecision/event/head/projection 생성
binding 또는 P1–P4 audit 완료 전에 FormulaRecord를 empirical executable로 표시
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_formula_registry.py -v
```

Expected RED: 최소 importable registry가 RB alias 한 개를 FormulaRecord 집합에 섞어 `test_alias_and_formula_registries_are_disjoint`와 `test_all_eleven_families_have_concrete_formula_records`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: 기존 원장을 provenance로 import한다**

`formula_registry.py`는 `research/indicator-validation/formula-ledger.json`의 historical 224개 formula definition만 읽기 전용 FormulaRecord provenance로 mirror한다. `candidate_audit_alias_registry.py`는 `preregistration.json`의 정확한 19개 candidate definition과 Jeffreys base alias 하나를 별도 `CandidateAuditAliasRecord` 20개로 mirror한다. market data, results, run-manifest, RB runner는 읽거나 실행하지 않는다. 각 alias에는 source path, bytes SHA-256, 원 ID, `provenanceLane=RB-001-audit`, `empiricalEligibility=false`, DR-001이 허용한 세 `allowedUses`를 기록한다. alias의 성능, 결과, threshold, weight, selection은 RP empirical FormulaRecord, CD candidate set, G6~G10 근거가 될 수 없다.

`historicalFormulaIds`는 원장 hash에 결박된 기존 224개 ID의 provenance submetric이다. current formula audit denominator는 `historicalFormulaIds ∪ newRpEmpiricalFormulaIds`의 exact set이며, `newRpEmpiricalFormulaIds`는 상단의 모든 RP controls/candidates와 이후 versioned registration event로 추가된 모든 RP FormulaRecord를 포함한다. registry projection은 두 집합, union cardinality와 set-difference를 기록한다. RB alias/config audit는 exact `rbCandidateAuditAliasIds` 20개 별도 denominator이고 FormulaRecord denominator를 증가시키지 않는다. 두 exact set의 교집합은 0이어야 한다.

historical source 판정은 다음 값 그대로 `sourceDisposition`에 보존하고 현재 판정으로 변환하지 않는다.

```text
valid
repairable
proxy_only
reject
not_identifiable
```

historical FormulaRecord는 원 값을 `sourceDisposition`에 두고 `auditStatus=unassessed`로 등록한다. 새 RP FormulaRecord는 `sourceDisposition=new_formula_without_historical_disposition`, `auditStatus=unassessed`이며 final math disposition field가 없다. Task 2는 registration만 수행하고 binding·audit·disposition·eligibility event를 만들지 않는다. full Cartesian audit 뒤 append-only `MathDispositionEvent`가 현재 disposition의 SSOT가 되고 DR-002가 이를 인용한다. FormulaRecord는 in-place mutation하지 않는다. source-independent 수학 `EligibilityDecision`과 source-dependent `StudyCandidateAdmission`은 분리한다.

- [ ] **Step 3: 11개 family concrete portfolio와 symbol registry를 작성한다**

상단 표의 모든 concrete ID를 등록한다. 각 expression symbol은 `input-symbol-registry.json`의 한 행만 참조하며 행은 다음을 가진다.

```text
symbolId, semanticName, dimension, unit, frequency, availabilityRule,
datasetContractId, required, sourceAcceptanceStatus, missingDisposition
```

자유 문자열 token, 문서에만 있는 phantom `rv20` 표기, unit 없는 volume·shares·price 조합을 거부한다. `potentialPtp.*`는 production path가 없다는 사실을 숨기지 않고 새 research callable이 생기기 전 `blocked_implementation_missing`으로 둔다.

- [ ] **Step 4: registry-only와 executable 경계를 구현한다**

```text
FormulaRegistry.validate_registration() -> FormulaRegistryReport
FormulaRegistry.registered_for_audit(studySlot) -> ordered FormulaRecord sequence
```

Task 2 API는 execution을 열 수 없다. registered-for-audit query는 AE/SVR 대상만 반환하고 empirical runner에 import되지 않는다. FormulaRecord는 unassessed registration이므로 coverage certificate, MathDispositionEvent, EligibilityDecision과 StudyCandidateAdmission 없이는 실행할 수 없다. eligibility/DR lookup과 event append는 이 module의 import graph에서 금지한다.

- [ ] **Step 5: GREEN과 program artifact 결박을 확인한다**

Run: Step 1과 동일.

Expected: 11/11 family, `CandidateAuditAliasRecord` 20/20과 `empiricalEligibility=false`, `rbCandidateAuditAliasIds ∩ formulaRegistryIds = ∅`, RB alias→SG5 참조 0, `formulaRegistryIds == historicalFormulaIds ∪ newRpEmpiricalFormulaIds`, missing/extra ID 0, phantom symbol 0, Task 2 eligibility event 0, executable record 0, adoption 자동승격 0으로 PASS.

### Task 3: P1—RB 20개 alias/config audit와 별도 RP empirical 수학↔구현 등가성

**Files:**
- Create: `research/rp-001/src/rp001/candidate_calculators.py`
- Create: `research/rp-001/src/rp001/reference_calculators.py`
- Create: `research/rp-001/tests/test_formula_equivalence.py`
- Append: authoritative `implementation-binding-events/` and `formula-audit-events/`; rebuild the named JSON projections deterministically.

- [ ] **Step 1: RED로 독립성·완전성을 고정한다**

exact `rbCandidateAuditAliasIds` 20개 모두 alias/config audit matrix에 존재해야 한다. 19개 candidate alias는 production/research calculator와 reference calculator가 서로 다른 module/callable/code hash를 가져야 하고 Jeffreys alias는 별도 closed-form reference를 가져야 한다. 다음 변이를 실패시킨다.

```text
20개 alias 중 하나의 audit row/reference 누락
CandidateAuditAliasRecord를 FormulaRecord/binding/empirical candidate로 승격
reference가 candidate calculator를 import 또는 호출
같은 callable/hash를 양쪽 binding에 등록
RB CandidateAuditAliasRecord를 empirical candidate binding으로 재사용
RB results/threshold/weight를 reference expected output으로 사용
새 `rp001.*` empirical FormulaRecord에 별도 version/reference/ImplementationBinding/P1 FormulaAudit 누락
P1–P4 audit head가 모두 닫히기 전에 EligibilityDecision 발행
Task 6 EligibilityDecision 없이 empirical runner/CD candidate set 진입
경계값·결측·lookback에서 값이 다름
candidate와 reference가 다른 eligible mask를 사용
expression과 callable input map이 다름
기존 원장의 equivalent 문자열만으로 verified 처리
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_formula_equivalence.py -v
```

Expected RED: 최소 importable equivalence runner가 동일 callable을 production/reference 양쪽에 사용하여 `test_reference_is_independent`와 `test_alias_audit_denominator_is_exactly_twenty`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: clean-room candidate reference 19개와 base closed-form을 구현한다**

`reference_calculators.py`는 frozen alias source definition 또는 RP FormulaRecord 수학식만 사용하고 `candidate_calculators.py` 또는 RB 구현을 import하지 않는다. RB 20개 alias 경로는 DR-001 허용 목적의 결함·동등성 감사만 수행하며 `empiricalEligibility=false`를 유지하고 FormulaRecord/ImplementationBinding을 만들지 않는다. SG5에 들어갈 각 `rp001.*` empirical FormulaRecord는 RB alias ID와 다른 versioned ID, 새 식 source hash, 별도 production/reference callable, ImplementationBinding과 P1 FormulaAudit을 가진다. 이 단계에서는 EligibilityDecision과 DR-002/003을 생성·요구·조회하지 않는다. 두 경로 모두 synthetic rows만으로 test하며 RB code/data/results를 실행하지 않는다.

각 candidate는 최소 다음 vector를 가진다.

```text
정상 내부값
최소 lookback 직전과 직후
분모 0
동점 percentile
결측 required input
극단값과 declared output boundary
```

Jeffreys base alias는 별도 closed-form `Beta(0.5+s,0.5+f)` reference test로 alias/config denominator의 20번째 row를 닫고 FormulaRecord denominator에는 들어가지 않는다.

- [ ] **Step 3: 수치 equivalence evidence를 append한다**

P1–P4 audit/verification key는 실행 전에 Task 1 global AE/SVR allocators가 exact reservation/head를 발행하고 repository가 이를 한 번만 소비한다. alias audit record는 alias ID, source definition hash, input vector/output hashes, tolerance, pass/fail, test path와 reserved `AE-*` ID를 기록한다. 이는 ImplementationBinding이 아니며 synthetic equivalence는 ExperimentRun/G6~G10 evidence가 아니다. RB alias 20/20 `verified/failed` disclosure는 감사 완전성만 뜻하며 empirical eligibility를 바꾸지 않는다. RP empirical binding `verified`는 별도 FormulaRecord별 정상·경계·결측 case가 모두 통과할 때만 허용한다. 실패 FormulaRecord는 Task 3에서 FormulaAudit counterexample와 dispositionContribution만 append하며 FormulaRecord나 수학식을 구현 결과에 맞춰 수정하지 않는다. MathDispositionEvent의 유일한 publisher는 Task 6B이고, full formula-specific cell set과 anchored FormulaAuditCoverageCertificate=1.00 이후에만 formula별 event를 발행한다.

- [ ] **Step 4: GREEN을 확인한다**

Run: Step 1과 동일.

Expected: RB alias/config audit matrix 20/20, candidate independent reference/same-mask 19/19와 Jeffreys closed-form 1/1은 DR-001 lane에만 존재하고 FormulaRecord/empirical candidate count에는 0개로 집계된다. 별도 RP empirical reference/binding은 자기 version과 P1 FormulaAudit에 결박되며 EligibilityDecision count는 아직 0이다. 해결할 수 없는 alias/candidate도 failed/blocked audit row로 denominator에 남는다.

**Checkpoint A-1:** 수학 검토자는 RP FormulaRecord 식 또는 RB CandidateAuditAliasRecord의 frozen source definition만 보고 reference를 재계산하며 기존 `equivalent=52`를 증거로 사용하지 않는다. alias와 FormulaRecord denominator를 합치지 않는다.

### Task 4: P2—split·currency·scale·missing·future timestamp metamorphic audit

**Files:**
- Create: `research/rp-001/src/rp001/metamorphic_audit.py`
- Create: `research/rp-001/tests/test_formula_metamorphic_audit.py`
- Append: authoritative `formula-audit-events/`; rebuild `formula-audit-ledger.pending_unanchored.json` projection deterministically.

- [ ] **Step 1: RED metamorphic matrix를 작성한다**

FormulaRecord의 `invariances` 선언에 따라 다음 변환 전후의 output·eligibility를 검사한다.

```text
split: price/fx/share/volume을 동일 corporate-action contract로 변환
currency: 모든 가격과 FX를 일관되게 변환
price scale: 달러↔센트와 같은 단순 스케일
missing: required input 한 개 제거
future timestamp: t 이후 row append/replace
row order/duplicate timestamp: 같은 set의 순서 변경과 중복 삽입
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_formula_metamorphic_audit.py -v
```

Expected RED: 최소 importable audit runner가 future row와 missing input을 수치 0으로 허용하여 `test_future_row_invariance`와 `test_missing_required_input_is_unavailable`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: 변환과 판정 규칙을 구현한다**

불변을 선언한 식은 tolerance 안에서 같아야 한다. 불변이 아닌 식은 변환 민감성을 FormulaAudit에 명시하고 confirmatory candidate에서 제외한다. missing 변환은 수치 0이 아니라 `unavailable`을 반환하고 reweight/renormalize를 금지한다. future row를 바꿔 현재 출력이 달라지면 즉시 `implementation_invalid`다.

- [ ] **Step 3: 알려진 반례를 regression evidence로 고정한다**

숨은 floor, 미래 candle, 결측 재가중, input order, duplicate timestamp, split-sensitive flow, dead branch 반례를 FormulaAudit에 source hash와 함께 append한다. production 앱을 수정하거나 반례를 “수정됨”으로 재명명하지 않는다.

- [ ] **Step 4: GREEN을 확인한다**

Run: Step 1과 동일.

Expected: 모든 retain/repair candidate가 선언한 metamorphic contract를 통과하거나 명시적 reject/block disposition을 가지며, 미래행 불변성 위반 은폐 0건.

### Task 5: P3—reward-hacking, trial bijection, identical-mask와 terminal-no-tuning

**Files:**
- Create: `research/rp-001/src/rp001/trial_ledger.py`
- Create: `research/rp-001/tests/test_reward_hacking_contract.py`
- Append: authoritative `formula-audit-events/`; rebuild `formula-audit-ledger.pending_unanchored.json` projection deterministically.

- [ ] **Step 1: RED로 보상해킹 변이를 작성한다**

```text
ConfirmationDesign candidate×fold×horizon×seed×control 조합 하나 누락/중복
성공 run만 ledger에 남기고 failed/invalid run 삭제
baseline과 candidate의 eligible row mask 불일치
비용·불리한 symbol·기간을 결과 후 제외
결측 뒤 남은 feature 재가중
terminal holdout 뒤 weight/threshold/state name/candidate 변경
같은 event의 중복 표본을 독립 사건으로 계수
점수 범위·dead branch·manual exception 은폐
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_reward_hacking_contract.py -v
```

Expected RED: 최소 importable ledger validator가 failed run 누락과 control/candidate mask 차이를 허용하여 `test_trial_grid_is_bijective`와 `test_identical_mask_is_required`가 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: expected trial grid와 ledger bijection을 구현한다**

```text
TrialLedgerValidator.expected_run_keys(design: ConfirmationDesign) -> Sequence[RunKey]
TrialLedgerValidator.validate_bijection(expected: Sequence[RunKey], events: Sequence[RunEvent]) -> None
TrialLedgerValidator.validate_identical_mask(baseline: RunArtifact, candidate: RunArtifact) -> None
TrialLedgerValidator.validate_terminal_freeze(design: ConfirmationDesign, events: Sequence[RunEvent]) -> None
```

Task 5의 mutation fixtures와 reward-hacking audit 결과는 AE/SVR로만 기록하고 ExperimentRun을 생성하지 않는다. validator의 actual application contract에서 blocked pre-run 조합은 ExperimentRun을 발명하지 않고 promotion/source disposition에 남긴다. Task 10 이후 실제 empirical 실행을 시작한 조합만 `completed/failed/invalid` 중 하나의 terminal run event를 반드시 가진다.

- [ ] **Step 3: 전 후보·실패 공개 검사를 구현한다**

FormulaAudit와 final report의 candidate ID 집합이 registry 및 design과 정확히 일치해야 한다. winner-only 표, identical-mask 위반, terminal 개봉 뒤 amendment 없는 변경을 거부한다.

- [ ] **Step 4: GREEN을 확인한다**

Run: Step 1과 동일.

Expected: 33개 이상의 adversarial mutation이 각각 거부되고 ledger prefix/hash가 보존된다.

### Task 6: P4—HSMM·CIF·filtering·duration·label switching·OFI 결측 계약

**Files:**
- Create: `research/rp-001/src/rp001/hsmm_competing_risk_contract.py`
- Create: `research/rp-001/src/rp001/eligibility_decision.py`
- Create: `research/rp-001/tests/test_hsmm_competing_risk_contract.py`
- Create: `research/rp-001/tests/test_eligibility_decision.py`
- Create: `research/rp-001/contracts/model-backend-decision.json`
- Create: `research/rp-001/contracts/backend-environment-lock.json`
- Create records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/eligibility-decision-events/`
- Create local head candidates with `.pending_unanchored` filenames under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/eligibility-decisions/`
- Create projection: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/eligibility-decisions.pending_unanchored.json`
- Create sidecar: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/eligibility-decisions.pending_unanchored.json.sha256`
- Append: authoritative implementation-binding/formula-audit events; rebuild projections deterministically.

- [ ] **Step 1: RED로 P4 수학 invariant를 작성한다**

```text
duration PMF가 비음수이고 합 1
explicit duration과 transition self-loop 중복 금지
filter P(z_t|I_t) 합 1 및 미래행 불변
smoother P(z_t|I_T)를 prediction output으로 전달 금지
원인별 q_k>=0, sum(q_k)<=1
S(h)+sum_k CIF_k(h)=1, CIF 단조 비감소
state label permutation 후 관측 likelihood/CIF 불변
외부 anchor 없는 상태를 FOMO/Panic/ProfitTaking으로 명명 금지
OFI/depth/Hawkes required input 결측을 0으로 대체 금지
Hawkes intensity 비음수와 kernel stability 위반 거부
synthetic recovery를 ER-* 또는 empirical evidence로 기록
dependency lock/environment hash 없는 backend import·선택
현재 환경에 없는 scipy/sklearn/statsmodels/pymc/jax/torch를 available로 표시
P1/P2/P3/P4 audit head 중 하나가 없거나 FormulaRecord/binding hash가 다른데 EligibilityDecision 발행
EligibilityDecision에 holdout/result/DR/adoption field 포함
동일 formula/version에 두 active eligibility event 또는 기존 decision 덮어쓰기
EligibilityDecision 없이 Task 7 이후 empirical execution/CD 진입
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_hsmm_competing_risk_contract.py \
                  research/rp-001/tests/test_eligibility_decision.py -v
```

Expected RED: 최소 importable contract evaluator가 smoother를 prediction output으로 내보내고 CIF mass를 정규화하지 않아 `test_filtering_never_uses_future_rows`와 `test_survival_plus_cif_equals_one`이 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **Step 2: 표준 라이브러리 synthetic reference를 구현한다**

작은 상태수·짧은 duration의 exact enumeration으로 filtering, duration, discrete cause-specific hazard와 CIF를 계산한다. 알려진 상태·duration·transition·event를 seeded synthetic sequence에서 생성해 recovery와 label permutation을 검사한다. 실제 시장자료나 RB 결과는 사용하지 않는다.

- [ ] **Step 3: backend 비교를 evidence로 고정한다**

`model-backend-decision.json`은 다음 세 경로를 현재 환경에서 비교한다.

```text
A. Python stdlib + 설치 확인된 NumPy 2.3.5 기반 명시적 finite-state dynamic programming
B. 별도 versioned dependency lock·license·seed·wheel hash가 검증된 probabilistic/statistical backend
C. 재현 가능한 외부 compiled backend와 독립 environment manifest
```

bundled Python에서 확인된 수치 package는 NumPy 2.3.5와 pandas 2.2.3뿐이며 scipy, sklearn, statsmodels, pymc, jax, torch는 없다. 이 사실을 capability matrix와 environment hash에 기록하고, 없는 package를 설치됐다고 가정하거나 실행 결과를 발명하지 않는다. must-have는 filtering API, explicit duration, posterior predictive, fixed seed, offline dependency lock, wheel/source hash, 독립 reference 비교, 환경 manifest다. 합성 recovery는 `SVR-*`로만 기록한다. 통과한 후보 중 transitive dependency와 platform variance가 가장 작은 경로를 선택하고, 동률이면 A→B→C 순으로 택한다. 어느 것도 통과하지 못하면 해당 MC/HSMM/Hawkes/neural 실행을 `blocked_implementation_missing`으로 두고 empirical ER을 만들지 않는다. 이름만 등록한 backend를 선택하지 않는다.

- [ ] **Step 4: prior dominance·abstain·미시구조 분리를 구현한다**

실제 적격 run에서 prior가 posterior를 사실상 결정하거나 label permutation이 안정되지 않으면 `not_identifiable/abstain`이다. 아직 backend/input/source가 승인·수집되지 않은 pre-run 상태는 terminal로 바꾸지 않고 `blocked`다. ordered event source가 승인·수집되지 않았으면 OFI/Hawkes 계층 전체를 blocked로 유지하며 daily layer 가중치를 재정규화하지 않는다. 사전 고정 search plan을 실제로 수행하고 provider request/response·coverage·독립 판정자 hash를 갖춘 `SourceAvailabilityClosure`가 부재를 닫은 경우에만 `data_unavailable` terminal로 전환한다.

#### Task 6B execution unit: actual formula-specific 15-obligation evidence production

**Files:**

- Create: research/rp-001/src/rp001/formula_obligation_matrix.py
- Create: research/rp-001/src/rp001/formula_obligation_auditors.py
- Create: research/rp-001/src/rp001/formula_audit_cell_publisher.py
- Create: research/rp-001/tests/test_formula_obligation_matrix.py
- Create: research/rp-001/tests/test_formula_obligation_auditors.py
- Create: research/rp-001/tests/test_formula_audit_cell_publisher.py
- Create formula-specific artifacts at research/rp-001/artifacts/formula-audit-cells/{formulaId}/{obligationId}/input.json, input.json.sha256, result.json, result.json.sha256, proof.md, proof.md.sha256
- Create one-record events at research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-matrix-events/{formulaId}/{obligationId}.pending_unanchored.json and sidecar
- Create projection and sidecar: research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-matrix.pending_unanchored.json and .sha256
- Create certificate and sidecar: research/meta-research/objects/programs/RP-001-quantitative-market-behavior/formula-audit-coverage-certificate.json and .sha256
- Create the sole MathDispositionEvent records at research/meta-research/objects/programs/RP-001-quantitative-market-behavior/math-disposition-events/{formulaId}/{sequence}.pending_unanchored.json and sidecars
- Create deliverable table and sidecar: research/rp-001/reports/formula-proof-counterexample-reward-audit.json and .sha256

- [ ] **Task 6B behavioral RED를 먼저 실행한다**

test를 먼저 작성하고 importable counterexample producer가 one obligation auditor를 등록하지 않고 FormulaRecord declaration text를 proof로 복사하며 unanchored generic artifact를 여러 formula cell에 재사용하도록 만든다. 동일 command에서 다음 named assertions가 실패해야 한다.

~~~text
test_every_obligation_has_a_concrete_auditor
test_every_formula_obligation_cell_is_produced
test_declaration_is_not_proof
test_rejects_generic_or_copied_proof
test_rejects_false_not_applicable_predicate
test_rejects_missing_cell_artifact_anchor
test_rejects_historical_224x10_as_current_proof
test_math_disposition_requires_anchored_full_certificate
~~~

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_formula_obligation_matrix.py \
                  research/rp-001/tests/test_formula_obligation_auditors.py \
                  research/rp-001/tests/test_formula_audit_cell_publisher.py -v
~~~

Import/discovery/syntax/file-existence failure는 RED가 아니다.

- [ ] **15 concrete obligation auditors를 구현한다**

exact obligation set은 economic_purpose, economic_mechanism, domain, codomain_output_range, unit_dimension, boundary_extreme, monotonicity, sign, split_currency_scale_invariance, missing, ood, temporal_future_invariance, formula_implementation_equivalence, probability_calibration_applicability, reward_hacking이다. denominator는 current exact formulaRegistryIds와 15 obligation applicability product다. historical 224×10 proof는 bytes/hash/meaning을 검증한 provenance input일 뿐 current cell을 충족시키지 않는다.

~~~text
FormulaObligationAuditorRegistry.require_exact(obligationIds: Sequence[str]) -> AuditorRegistryReport
FormulaSpecificAuditInputBuilder.build(formula: FormulaRecord, obligationId: str) -> FormulaAuditInput
FormulaObligationAuditor.audit(input: FormulaAuditInput) -> FormulaAuditCellResult
FormulaAuditCellPublisher.publish(inputArtifact: ArtifactBindingV2, resultArtifact: ArtifactBindingV2, proofArtifact: ArtifactBindingV2, independentReview: ArtifactBindingV2) -> FormulaAuditMatrixCellEvent
FormulaAuditCoverageCertificateBuilder.build(registry: FormulaRegistry, anchoredCells: Sequence[AnchoredFormulaAuditCell]) -> FormulaAuditCoverageCertificate
MathDispositionPublisher.publish(formula: FormulaRecord, certificate: AnchoredFormulaAuditCoverageCertificate, cellEvents: Sequence[AnchoredFormulaAuditCell]) -> MathDispositionEvent
~~~

각 auditor는 formulaId/formulaRecordSha256, expression/symbol/input-map, obligation-specific fixtures와 expected invariant를 입력으로 받는다.

- economic purpose/mechanism auditors는 source citations, falsifiable mechanism chain and independent theory review를 요구하며 declaration string 단독 제출을 거부한다.
- domain/codomain-range/unit-dimension auditors는 parsed expression, symbol units, interval/constraint solver output and counterexample search artifact를 만든다.
- boundary/extreme/monotonicity/sign auditors는 formula-specific boundary partitions, analytic proof where available and seeded computational counterexample AE/SVR artifacts를 만든다.
- split/currency/scale, missing, OOD, temporal/future auditors는 formula-specific metamorphic vectors, exact transformed inputs, outputs/masks and future-row mutation AE/SVR를 만든다.
- formula-implementation equivalence auditor는 FormulaRecord expression/reference callable/production callable exact bindings, independent vector results and tolerance evidence를 만든다.
- calibration applicability auditor는 output semantics에 따른 frozen applicability predicate를 증명하고 probabilistic output이면 calibration test contract, 아니면 formula-specific non-applicability rationale and review를 만든다.
- reward-hacking auditor는 formula-specific threshold/weight/dead-branch/missing-reweight/future-normalization/manual-exception checks and trial-ledger backreferences를 만든다.

각 computational cell은 reserved AE or SVR ID를 사용한다. 비계산 cell도 formula-specific input artifact, proof/counterexample or true N-A predicate artifact and independent reviewer hash를 가져야 한다. 같은 proof hash를 formula 간 재사용하거나 FormulaRecord declaration을 proof body로 그대로 복사하면 거부한다.

- [ ] **cell artifacts/events를 전부 anchor한 뒤 projection과 certificate를 만든다**

순서는 cell input/result/proof sidecars → cell event transaction → target CAS receipt → post-CAS ArtifactExternalAnchorBindingEvent → cell anchor-binding receipt다. 모든 expected cell이 이 순서를 닫은 뒤에만 matrix projection을 deterministic rebuild하고 별도 transaction으로 FormulaAuditCoverageCertificate를 publish·anchor한다. coverage는 exact set and count 기준 1.00이어야 한다. missing auditor, missing artifact, false N-A, generic proof, copied proof, missing review/AE/SVR or missing anchor는 certificate 발행 전에 실패한다.

certificate가 anchored된 뒤 Task 6B의 MathDispositionPublisher만 formula별 retain, repair, proxy_only, reject, not_identifiable event를 exactly one current sequence로 발행한다. Tasks 2–5는 dispositionContribution만 제공하며 MathDispositionEvent를 만들 수 없다. RD-007 deliverable table은 모든 formula×obligation cell path/hash/result/reviewer/anchor binding을 열거한다.

- [ ] **GREEN: RED와 동일한 exact command를 실행한다**

Expected GREEN: concrete auditor coverage 15/15, formula-specific current matrix coverage 1.00, cell artifact/anchor coverage 1.00, historical provenance/current evidence separation, truthful N-A and exactly one Task6B-owned MathDispositionEvent per formula가 통과한다. independent formula-audit reviewer가 cell artifacts, certificate and dispositions를 승인하기 전 Task 6C로 가지 않는다.

#### Task 6C execution unit: source-independent mathematical EligibilityDecision

**Files:** research/rp-001/src/rp001/eligibility_decision.py, research/rp-001/tests/test_eligibility_decision.py, eligibility-decision event/head/projection/sidecar/anchor-binding paths.

- [ ] **Task 6C behavioral RED를 먼저 실행한다**

test를 먼저 작성하고 최소 importable publisher가 unanchored/incomplete certificate로 eligible decision을 발행하고 source acceptance를 decision body에 삽입하도록 만든다. 같은 command에서 test_eligibility_requires_anchored_full_certificate, test_eligibility_requires_matching_math_disposition, test_eligibility_is_source_independent가 assertion failure여야 한다. import/discovery/syntax/file-existence failure는 RED가 아니다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_eligibility_decision.py -v
~~~

- [ ] **immutable EligibilityDecision publisher를 구현한다**

~~~text
EligibilityDecisionPublisher.publish(formulaRecord: FormulaRecord, binding: ImplementationBinding, coverageCertificate: AnchoredFormulaAuditCoverageCertificate, mathDispositionEvent: MathDispositionEvent, registrationSha256: str, protectedManifestSha256: str) -> EligibilityDecisionEvent
EmpiricalEligibilityGate.require_eligible(formulaId: str, decisionSha256: str) -> EligibleFormulaBinding
~~~

publisher는 Task 2 registration, verified binding, anchored FormulaAuditCoverageCertificate=1.00, matching Task6B MathDispositionEvent and post-CAS anchor bindings를 재해시한 뒤에만 source-independent EligibilityDecisionEvent를 append한다. decision은 mathematical/implementation eligibility and allowed study slots만 포함하고 source acceptance, closure, holdout, result, DecisionRecord and adoption fields를 금지한다. 동일 formula/version 변경은 successor event다. 실제 투입은 Task7 StudyCandidateAdmission이 multi-input source contracts로 결정한다.

- [ ] **GREEN: RED와 동일한 exact command를 실행한다**

Expected GREEN: incomplete/mismatched/unanchored certificate and source-dependent decision mutations are rejected; exact current certificate fixture만 immutable eligibility event/head/projection/anchor binding을 만든다.

- [ ] **Checkpoint A를 통과한다**

Task 6 main HSMM/CIF command, Task6B three-test command and Task6C RED/GREEN command가 모두 GREEN이고 independent math/formula-audit/eligibility reviewers가 registration→binding/P1–P4 contributions→15-obligation certificate→MathDispositionEvent→EligibilityDecision 순서를 승인한 뒤에만 Task 6D/7로 간다.

#### Task 6D execution unit: SP-015 ontology adjudication before empirical design

**Files:**
- Create: `research/rp-001/src/rp001/ontology_terminalization.py`
- Create: `research/rp-001/run_ontology_terminalization.py`
- Create: `research/rp-001/tests/test_ontology_terminalization.py`
- Create: `research/meta-research/objects-v2/study-protocols/SP-015-ontology-independent-adjudication/object.json`
- Create: `research/meta-research/objects-v2/study-protocols/SP-015-ontology-independent-adjudication/object.json.sha256`
- Create: `research/meta-research/objects-v2/study-protocols/SP-015-ontology-independent-adjudication/protocol.md`
- Create: `research/meta-research/objects-v2/study-protocols/SP-015-ontology-independent-adjudication/protocol.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/object.json`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/object.json.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/evidence.json`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/evidence.json.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/evidence.md`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-010-ontology-independent-adjudication/evidence.md.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ontology-name-mapping.json`, `.sha256`
- Create registration events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/registration-events/SP-015/<sequence>.pending_unanchored.json`, `registration-events/EB-010/<sequence>.pending_unanchored.json` and sidecars
- Create lifecycle events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/lifecycle-events/SP-015/<sequence>.pending_unanchored.json`, `lifecycle-events/EB-010/<sequence>.pending_unanchored.json` and sidecars
- Create artifact-binding events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-binding-events/SP-015/<sequence>.pending_unanchored.json`, `artifact-binding-events/EB-010/<sequence>.pending_unanchored.json` and sidecars
- Create terminal/computation/anchor records: `terminal-decision-computations/ST-ONT-001/<sequence>.pending_unanchored.json`, `study-terminal-events/ST-ONT-001/<sequence>.pending_unanchored.json`, corresponding local heads, ArtifactExternalAnchorBindingEvents and receipts
- Rebuild and anchor exactly: `research/meta-research/catalog/research-objects.v2.pending_unanchored.json`, `research/meta-research/catalog/artifact-bindings.v2.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.v2.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/current-program-state.v2.pending_unanchored.json` and four sidecars

SP-015 dependsOn remains `[DC-001,RQ-001,SP-001]`. Pinned DC descriptor/body hashes are `adfac49a5f00a0af463399c7db59809ed892f3e550ca6d65ac0fc80977a59084` / `520ee9fb212a947f94c1c1c5d768f93db2e8324eaeb36de2e53c654a8302ee1a`; RQ hashes are `63fc934691c539335d9f427ba63dc8e1d8bef308aeb7f2e5799e617160c76284` / `562aa75e19e45afe10c0d383bab0f5ae15d363d9dec870c48b787c3b79b12a34`; SP hashes are `15237b804dd0633da5eaee02181280b0a85d71c714304acab92d8f5cc04bc458` / `a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e`.

- [ ] **Task 6D RED: ontology precedence behavior를 먼저 고정한다**

test를 먼저 작성하고 importable counterexample evaluator가 refuted fixture에도 psychological name을 반환하도록 작성한다. 아래 command는 `test_refuted_or_unidentifiable_forces_price_volume_regime`로 실패해야 한다. nonterminal promotion, two-reviewer 미달, SP-001 mutation, terminal/EB/receipt 누락도 named assertions로 실패한다. import/discovery/syntax failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_ontology_terminalization.py -v
```

두 독립 adjudicator가 frozen ontology에서 관측, latent state, 인간 심리와 trading decision을 분리한다. terminal `supported`만 scoped psychological names를 허용한다. `refuted` 또는 `not_identifiable`이면 exact downstream mapping을 `price_volume_regime`으로 동결한다. 다른 terminal 또는 nonterminal 상태는 dependent analysis bundle, DesignCore와 promotion을 blocked로 둔다. ontology mapping과 adjudication input으로 TerminalDecisionComputation을 먼저 anchor하고, 첫 번째 독립 append transaction에서 EB ID가 없는 StudyTerminalEvent를 publish·anchor한다. 그 다음 두 번째 transaction에서만 EB-010이 terminal event binding과 terminal anchor receipt를 참조해 publish·anchor된다. SP-015 dependency를 SP-016 descriptor에 추가하지 않고, promotion schema의 mandatory prerequisite field가 anchored SP-015 terminal ID/hash와 ontology mapping hash를 요구한다.

Run GREEN: RED와 같은 exact command. 그 뒤 terminal-first, EB-second commands and current-v2 validator를 실행한다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_ontology_terminalization.py --publish-study-terminal ST-ONT-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_ontology_terminalization.py --publish-evidence-bundle EB-010 \
  --terminal-study ST-ONT-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/meta-research/tools/validate_research_program_v2.py \
  --repository-root . --program-root research/meta-research --graph-mode current-v2
```

Expected GREEN: SP-015와 terminal을 먼저 등록·anchor하고 그 뒤 EB-010을 별도 등록·anchor한 event order, exact four projection rebuild와 current-v2 validation, two-reviewer decision and name mapping이 통과한다. ontology reviewer 승인 전 Task 6E를 시작하지 않는다.

#### Task 6E/U7 execution unit: frozen processing and analysis code bundles

**Files:**
- Create: `research/rp-001/src/rp001/processing_pipeline.py`
- Create: `research/rp-001/src/rp001/processing_code_bundle.py`
- Create: `research/rp-001/src/rp001/analysis_code_bundle.py`
- Create: `research/rp-001/src/rp001/validation_design.py`
- Create: `research/rp-001/src/rp001/interval_labels.py`
- Create: `research/rp-001/src/rp001/research_metrics.py`
- Create: `research/rp-001/src/rp001/evidence_synthesis.py`
- Create: `research/rp-001/src/rp001/reproduction_authorization.py`
- Create: `research/rp-001/src/rp001/reproduction_identity.py`
- Create: `research/rp-001/src/rp001/program_completion.py`
- Create: `research/rp-001/src/rp001/terminal_decision_computation.py`
- Create: `research/rp-001/src/rp001/study_terminal_publisher.py`
- Create: `research/rp-001/src/rp001/source_impact_terminalizer.py`
- Create: `research/rp-001/src/rp001/source_acceptance.py`
- Create: `research/rp-001/src/rp001/source_availability.py`
- Create: `research/rp-001/src/rp001/source_plan_set.py`
- Create: `research/rp-001/src/rp001/credential_broker.py`
- Create: `research/rp-001/src/rp001/read_only_toss_adapter.py`
- Create: `research/rp-001/src/rp001/external_raw_sink.py`
- Create: `research/rp-001/src/rp001/external_artifact_locator.py`
- Create: `research/rp-001/src/rp001/collection_reader.py`
- Create: `research/rp-001/src/rp001/analysis_reader.py`
- Create: `research/rp-001/src/rp001/data_lineage_terminalization.py`
- Create: `research/rp-001/src/rp001/study_candidate_admission.py`
- Create: `research/rp-001/src/rp001/data_lineage_registers.py`
- Create: `research/rp-001/src/rp001/experiment_run.py`
- Create: `research/rp-001/src/rp001/evidence_cli_contract.py`
- Create: `research/rp-001/run_evidence_engine.py`
- Create: `research/rp-001/contracts/evidence-cli-command-dispatch-registry.json`, `.sha256`
- Create: `research/rp-001/src/rp001/studies/study_application.py`
- Create: `research/rp-001/src/rp001/studies/behavior_study.py`
- Create: `research/rp-001/src/rp001/studies/relative_value_study.py`
- Create: `research/rp-001/src/rp001/studies/microstructure_study.py`
- Create: `research/rp-001/src/rp001/studies/execution_study.py`
- Create: `research/rp-001/src/rp001/studies/tail_risk_study.py`
- Create: `research/rp-001/src/rp001/studies/synthesis_study.py`
- Create: `research/rp-001/src/rp001/studies/candidate_comparison.py`
- Create: `research/rp-001/src/rp001/backends/hsmm_competing_risk_adapter.py`
- Create: `research/rp-001/src/rp001/backends/dynamic_value_adapter.py`
- Create: `research/rp-001/src/rp001/backends/ofi_hawkes_adapter.py`
- Create: `research/rp-001/src/rp001/backends/execution_cost_adapter.py`
- Create: `research/rp-001/src/rp001/backends/portfolio_risk_adapter.py`
- Create: `research/rp-001/src/rp001/backends/synthesis_adapter.py`
- Create: `research/rp-001/src/rp001/backends/nonlinear_adapter.py`
- Create: `research/rp-001/tests/test_terminal_decision_computation.py`, `research/rp-001/tests/test_study_terminal_publisher.py`, `research/rp-001/tests/test_source_impact_terminalizer.py`
- Create: `research/rp-001/tests/test_experiment_run.py`, `research/rp-001/tests/test_evidence_cli_contract.py`, `research/rp-001/tests/test_evidence_engine_cli.py`, `research/rp-001/tests/test_source_runtime_cli.py`
- Create: `research/rp-001/tests/test_source_acceptance.py`, `research/rp-001/tests/test_source_availability.py`, `research/rp-001/tests/test_source_plan_set.py`, `research/rp-001/tests/test_credential_broker.py`, `research/rp-001/tests/test_read_only_toss_adapter.py`
- Create: `research/rp-001/tests/test_external_raw_sink.py`, `research/rp-001/tests/test_external_artifact_locator.py`, `research/rp-001/tests/test_collection_reader.py`, `research/rp-001/tests/test_analysis_reader.py`
- Create: `research/rp-001/tests/test_data_lineage_terminalization.py`, `research/rp-001/tests/test_study_candidate_admission.py`, `research/rp-001/tests/test_data_lineage_registers.py`
- Create: `research/rp-001/tests/test_processing_code_bundle.py`, `test_analysis_code_bundle.py`, `test_validation_design.py`, `test_evidence_synthesis.py`, `test_independent_reproduction.py`, `test_program_completion.py`, `test_completion_predicates.py` and all seven study/comparison E2E tests
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processing-code-bundle-manifest.json`, `.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/analysis-code-bundle-manifest.json`, `.sha256`

- [ ] **Task 6E RED: result-semantic code coverage를 먼저 고정한다**

test를 먼저 작성하고 importable counterexample manifest builder가 `research_metrics.py`, `study_terminal_publisher.py`, `experiment_run.py`, Task 7 source/data-lineage modules, `evidence_cli_contract.py`와 thin CLI hash를 누락하고 one callable을 wrong model class에 결박하도록 작성한다. counterexample terminal publisher는 failed/invalid input을 exact-one rule 밖으로 버리고 future EB ID를 terminal에 삽입한다. counterexample run store는 ProcessedManifest/ActualRunLineage 없이 reservation을 consume하고, counterexample CLI registry는 실제 downstream command 하나를 누락하고 미등록 command 하나를 허용한다. counterexample source flow는 unrotated Toss plan을 closure로 위조하고 blocked MIC plan을 global blocker로 확장하며 RD-004/005 output 하나를 생략한다. counterexample reproduction flow는 RRA producer 없이 RIA를 만들고 unanchored/same-identity attestation으로 G9/RD-021/EB-009를 통과시킨다. 동일 exact command는 다음 named assertions에서 실패해야 한다.

~~~text
test_manifest_covers_every_result_semantic_file
test_callable_model_class_binding_is_exact
test_terminal_computation_precedes_terminal
test_terminal_cannot_reference_future_evidence_bundle
test_failed_invalid_and_closure_are_exact_one
test_processed_manifest_and_actual_lineage_are_required_before_consume
test_closed_dispatch_registry_equals_all_runtime_commands
test_cli_rejects_every_unregistered_subcommand
test_every_registered_command_requires_protected_manifest
test_reproduction_rights_attestation_is_produced_before_ria
test_g9_requires_anchored_reproduction_and_independent_reviewer_attestations
test_rd021_and_eb009_require_g9
test_every_task7_command_module_and_callable_is_frozen
test_unrotated_toss_plan_is_nonterminal_blocked_not_closure
test_blocked_plan_cannot_produce_data_unavailable
test_blocked_mic_plan_does_not_block_unrelated_beh_val_admission
test_blocked_mic_keeps_mic_and_dependent_rsk_syn_blocked
test_program_completion_fails_when_blocked_count_is_positive
test_dataset_contract_register_output_is_required
test_current_source_matrix_output_is_required
~~~

Import/discovery/syntax/file-existence failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_processing_code_bundle.py \
                  research/rp-001/tests/test_analysis_code_bundle.py \
                  research/rp-001/tests/test_validation_design.py \
                  research/rp-001/tests/test_behavior_study_e2e.py \
                  research/rp-001/tests/test_relative_value_study_e2e.py \
                  research/rp-001/tests/test_microstructure_study_e2e.py \
                  research/rp-001/tests/test_execution_study_e2e.py \
                  research/rp-001/tests/test_tail_risk_study_e2e.py \
                  research/rp-001/tests/test_synthesis_study_e2e.py \
                  research/rp-001/tests/test_candidate_comparison_e2e.py \
                  research/rp-001/tests/test_evidence_synthesis.py \
                  research/rp-001/tests/test_independent_reproduction.py \
                  research/rp-001/tests/test_program_completion.py \
                  research/rp-001/tests/test_completion_predicates.py \
                  research/rp-001/tests/test_terminal_decision_computation.py \
                  research/rp-001/tests/test_study_terminal_publisher.py \
                  research/rp-001/tests/test_source_impact_terminalizer.py \
                  research/rp-001/tests/test_experiment_run.py \
                  research/rp-001/tests/test_evidence_cli_contract.py \
                  research/rp-001/tests/test_evidence_engine_cli.py \
                  research/rp-001/tests/test_source_runtime_cli.py \
                  research/rp-001/tests/test_source_acceptance.py \
                  research/rp-001/tests/test_source_availability.py \
                  research/rp-001/tests/test_source_plan_set.py \
                  research/rp-001/tests/test_credential_broker.py \
                  research/rp-001/tests/test_read_only_toss_adapter.py \
                  research/rp-001/tests/test_external_raw_sink.py \
                  research/rp-001/tests/test_external_artifact_locator.py \
                  research/rp-001/tests/test_collection_reader.py \
                  research/rp-001/tests/test_analysis_reader.py \
                  research/rp-001/tests/test_data_lineage_terminalization.py \
                  research/rp-001/tests/test_study_candidate_admission.py \
                  research/rp-001/tests/test_data_lineage_registers.py -v
```

`ProcessingCodeBundleManifest`는 raw parser, timestamp/PIT normalization, corporate-action/unit reconciliation, missing policy, processed serializer, `credential_broker.py`, `read_only_toss_adapter.py`, `external_raw_sink.py`, `external_artifact_locator.py`, `collection_reader.py`와 각 associated test의 exact relative path/hash, dependency/environment locks, public callable binding, sorted file-set digest와 protected manifest hash를 갖는다. `AnalysisCodeBundleManifest`는 feature, interval label, validation split, calibration/uncertainty/metric, BEH/VAL/MIC/EXE/RSK/SYN/candidate-comparison application, 위 exact backend adapters, `source_acceptance.py`, `source_availability.py`, `source_plan_set.py`, `analysis_reader.py`, `data_lineage_terminalization.py`, `study_candidate_admission.py`, `source_impact_terminalizer.py`, `data_lineage_registers.py`와 모든 associated test, TerminalDecisionComputation/StudyTerminalPublisher, ExperimentRunRepository, EvidenceBundle/DecisionRecord/completion builder, reproduction authorization·comparison logic, `evidence_cli_contract.py`, generic thin `run_evidence_engine.py`, closed dispatch registry JSON and all run-store/CLI tests의 exact relative path/hash, callable/model-class/FormulaRecord binding, dependency/environment locks, ontology mapping hash와 sorted file-set digest를 갖는다. artifact 자기 hash는 sidecar가 소유한다.

`ExperimentRunRepository`는 Task 6E에서 RED→GREEN으로 구현·동결한다. frozen API는 reserved six-digit ID만 consume하고 anchored ProcessedManifestVerification과 ActualRunLineageBindingEvent를 요구하며 `reserved→running→completed|failed|invalid` append-only lifecycle, output bindings, run descriptor와 successor-ledger backreference를 보존한다. Task 10은 이 code/test를 다시 쓰지 않고 재해시·재실행만 한다.

`EvidenceCliCommandDispatchRegistry`의 exact ordered command ID set은 다음 49개이며, 각 row는 command ID, application-port ID, exact pre-frozen module/callable binding, argument schema hash, `protectedManifestRequired=true`와 redaction/exit-code policy를 갖는다.

```text
bind-actual-run-lineage
build-cost-sensitivity-table
build-decision-record
build-detection-calibration-table
build-event-interval-table
build-failure-evidence-register
build-formula-distributions
build-formula-evidence-bundle
build-independent-reproduction-report
build-performance-table
build-phase-prediction-table
build-risk-table
build-run-ledger-registers
build-source-manifest-registers
build-synthesis-report
build-terminal-evidence-bundles
build-traceability-deliverables
capture-authorized-metadata
close-source-availability
collect-authorized-raw
evaluate-gates-and-build-decision
execute-source-search
execute-study
freeze-source-search-plan
process-authorized-raw
publish-completion-observations
publish-current-source-matrix
publish-data-lineage-eligibility-snapshot
publish-dataset-contract-register
publish-evidence-bundle
publish-independent-reviewer-attestation
publish-reproduction-attestation
publish-reproduction-input-authorization
publish-reproduction-manifest
publish-reproduction-rights-attestation
publish-reproduction-sink-descriptor
publish-study-terminal
reproduce
validate-artifact-hygiene
validate-program-completion
verify-g9
verify-metadata-snapshot
verify-processed-manifest
verify-protected-paths
verify-raw-capture-manifest
verify-reproduction-input-authorization
verify-reproduction-resolver-rights
verify-reproduction-rights-attestation
verify-trial-bijection
```

`EvidenceCliContractValidator` computes set-equality between this registry and every `run_evidence_engine.py --<command>` invocation fixed in Tasks 7C2, 7D and 10–14; missing, extra, alias or duplicate commands fail. The thin shell owns only strict argument parsing, required protected-manifest preflight, redaction, dependency injection to the registered application port and exit-code mapping. It cannot contain source acceptance, parsing, feature, metric, terminal, evidence, reproduction or decision semantics.

두 manifest는 provider access가 0인 synthetic-only tests와 external anchor receipt를 통과해야 한다. source tree file set과 manifest file set은 set-equality다. DesignCore, ProtocolCore와 PlannedRunKey는 두 manifest sidecar hash를 모두 결박한다. 어느 result/source/terminal/admission/run-store/CLI/dispatch file, dependency lock, callable binding 또는 environment가 바뀌면 기존 manifest/CD/SP/reservation을 수정하지 않고 successor processing+analysis manifests, successor DAG와 새 reservations를 발행한다. Tasks 7A/B/C/C2/D/E and 10–14는 pre-frozen services/tests/shell/registry/run-store와 두 bundle을 read-only로 소비하며 post-6E result/source/terminal/admission/CLI code or test Create/Modify count는 0이어야 한다.

Run GREEN: RED와 같은 exact command.

Expected GREEN: processing/analysis and every Task 7 service/test file coverage, run-store lifecycle, closed 49-command dispatch set-equality, three-state source outcomes, scoped blocked propagation, RD-004/005 producers, mandatory protected-manifest handling, RRA→RIA and RM→RA→IRA→G9→RD-021/EB-009 prerequisites, synthetic behavior, exact callable/model-class bindings, ontology mapping, dependency/environment locks와 two anchored sidecars가 모두 통과한다. provider/search transport count is zero. code-bundle reviewer 승인 전 actual source runtime or DesignCore로 가지 않는다.

### Task 7: staged source authorization과 분리된 collection/analysis reader Gate

Task 7 command-meaning source/tests are already RED→GREEN and frozen in Task 6E before provider access. Runtime order is `7A source/credential read-only preflight and plan events → review → 7B sink preflight and descriptor events → review → 7C reader-chain preflight → review → 7C2 actual three-outcome source runtime → review → 7D SP-016 scoped snapshot/registers/optional terminal → 7E scoped admission`. Each unit rehashes/reruns frozen tests and may publish only the listed runtime artifacts/events; post-6E code/test Create/Modify is zero.

**Files:**
- Read only and rehash Task 6E-frozen source services: `source_acceptance.py`, `source_availability.py`, `source_plan_set.py`, `credential_broker.py`, `read_only_toss_adapter.py`, `external_raw_sink.py`, `external_artifact_locator.py`, `collection_reader.py`, `analysis_reader.py`, `data_lineage_terminalization.py`, `study_candidate_admission.py`, `source_impact_terminalizer.py`, `data_lineage_registers.py`
- Read only and rerun all associated Task 6E tests: `test_source_acceptance.py`, `test_source_availability.py`, `test_source_plan_set.py`, `test_credential_broker.py`, `test_read_only_toss_adapter.py`, `test_external_raw_sink.py`, `test_external_artifact_locator.py`, `test_collection_reader.py`, `test_analysis_reader.py`, `test_data_lineage_terminalization.py`, `test_study_candidate_admission.py`, `test_source_impact_terminalizer.py`, `test_data_lineage_registers.py`
- Read only from Task 6E in Task 7C2: `research/rp-001/run_evidence_engine.py`, `research/rp-001/src/rp001/evidence_cli_contract.py`, `research/rp-001/contracts/evidence-cli-command-dispatch-registry.json`
- Read only from Task 6E in Task 7C2: `research/rp-001/tests/test_evidence_cli_contract.py`, `research/rp-001/tests/test_evidence_engine_cli.py`, `research/rp-001/tests/test_source_runtime_cli.py`
- Create records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-metadata-acceptance-ledger/`
- Create records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/design-metadata-capture-authorizations/`
- Create records under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/universe-metadata-snapshots/`
- Create one-record plan events under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-search-plan-events/`
- Create immutable local plan-head candidates with `.pending_unanchored` filenames under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/source-availability-search-plans/`
- Create projection with sidecar: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-search-plans.pending_unanchored.json`, `source-availability-search-plans.pending_unanchored.json.sha256`
- Create records when authorized: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/raw-collection-authorizations/`
- Create records after collection: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/raw-capture-manifests/`
- Create records after raw manifest: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processing-authorizations/`
- Create records after processing: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/processed-manifests/`
- Create records only after exhausted search: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-availability-closures/`
- Create one exact outcome record per executed plan: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-outcome-events/`
- Create descriptor events under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-sink-descriptor-events/<sinkId>/`
- Create descriptor local heads under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/ledger-head-pin-events/external-sink-descriptors/<sinkId>/`
- Create descriptor projection and sidecar: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-sink-descriptors.pending_unanchored.json`, `external-sink-descriptors.pending_unanchored.json.sha256`
- Create descriptor anchor receipts under: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/external-sink-descriptors/<sinkId>/`
- Append source registration/lifecycle events; rebuild v2 current projections only. Frozen v1 RP descriptor is not modified.

- [ ] **Step 1: Task 6E-frozen integration tests와 bundle bindings를 read-only 검증한다**

Task 6E RED/GREEN output hashes, exact source/test/module/callable bindings and both bundle receipts를 재해시한 뒤 아래 frozen tests를 변경 없이 다시 실행한다. Task 6E RED fixtures가 public source credential dependency, metadata authorization 없는 reader, invalid closure와 three-outcome violations을 이미 행동으로 실패시켰어야 한다. 이 단계의 source/test write와 reader/transport/sink spy는 0이다.

다음 mutation을 각각 reader spy가 호출되기 전에 실패시킨다.

```text
SourceMetadataAcceptance의 provider/right/retention/derived-publication/redistribution 미판정
SourceMetadataAcceptance의 timestamp/timezone/session, unit, corporate-action/revision 문서계약 누락
SourceMetadataAcceptance가 raw/processed market path 또는 hash를 요구·포함
required source가 `credentialStatus=rotated` 또는 nonsecret provenance를 갖지 않음
public source가 `credentialStatus=not_required`가 아니거나 credential event/material에 의존
Toss current blocked record를 accepted로 변경
미등록 alternative source 또는 공식 1차 문서 response hash 없는 source
DesignMetadataCaptureAuthorization의 accepted source ID/hash 누락
declared metadata subset이 closed four-class universe 밖이거나 actual set과 다름
study/provider가 필요하지 않은 metadata class까지 강제하거나 outcome 파생값 포함
authorization 없이 metadata capture 또는 snapshot 생성
UniverseMetadataSnapshot의 response manifest/hash/receivedAt/audit event 누락
CD와 successor SP freeze 전에 RawCollectionAuthorization 생성
RawCollectionAuthorization 없이 CollectionReadGuard 호출
collection reader가 immutable sink 밖으로 raw bytes 반환 또는 두 번 수집
RawCaptureManifest의 locator/clientReceivedAt/authorization backreference 누락
raw manifest/code hash 없는 ProcessingAuthorization
processed locator/raw backreference 없는 processed manifest
SourceAvailabilityClosure request/response가 locator contract 대신 local path 사용
`future_plan_governed_availability_request`로 분류된 provider 검색·문서 조회·API request가 `SourceAvailabilitySearchPlan.frozenAt` 이전에 발생
preexisting metadata-only probe가 `legacy_metadata_only_operational_exposure`, `preexistingExposure=true`, `eligibleForClosure=false`, `eligibleForSourceAcceptance=false`를 갖지 않거나 future search-plan request로 재분류됨
search plan에 study/source/required field, exact source/endpoint operation, request cap/stop rule, coverage denominator, alternative-source rule 또는 independent reviewer binding 누락
search plan event/pin/sidecar 누락, prefix 수정, projection과 head 불일치, 결과 후 plan 교체
closure의 searchPlanId/searchPlanSha256가 실제 frozen event/head와 다르거나 request audit timestamp가 freeze를 선행
repo artifact/log/projection에 absolute path, home path, shared temporary path 또는 sink local root 노출
processed manifest·CD·SP·code·environment hash 없이 AnalysisReadGuard 호출
collection reader와 analysis reader가 같은 class/module/import path 사용
불완전한 SourceAvailabilityClosure로 blocked를 data_unavailable로 변경
credential value가 child environment allowlist 밖, parent env, CLI, log 또는 artifact에 노출
credential file mode가 0600이 아니거나 Git-ignored가 아님
stdout/stderr redaction spy가 기존 SensitiveValuePolicy finding을 놓침
OAuth exact token POST와 GET/public allowlist 밖 method/path/body-key 또는 account header가 transport까지 도달
raw sink가 repository 내부·VCS tracked·shared temp이거나 permission/retention/tombstone 누락
metadata-only probe를 accepted raw dataset/CD/G7 evidence로 승격
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_source_acceptance.py \
                  research/rp-001/tests/test_source_availability.py \
                  research/rp-001/tests/test_credential_broker.py \
                  research/rp-001/tests/test_read_only_toss_adapter.py \
                  research/rp-001/tests/test_external_raw_sink.py -v
```

Expected: frozen GREEN tests pass, Task 6E RED evidence contains `test_public_source_has_no_credential_dependency`, `test_metadata_subset_must_equal_actual_classes`, `test_raw_reader_requires_final_design_lineage` assertion failures, provider/search/request·reader·sink spy count is 0, and Task 7 source/test Create/Modify count is 0. 특히 pre-reader `SourceMetadataAcceptance`와 `DesignMetadataCaptureAuthorization` fixture는 raw/processed market hash를 포함하지 않아야 한다.

#### Task 7A execution unit: source search, credential broker, Toss read-only adapter

**Files:** read only and rehash Task 6E-frozen `source_acceptance.py`, `source_availability.py`, `credential_broker.py`, `read_only_toss_adapter.py` and their four tests; publish only search-plan/source-acceptance outcome event·head·projection·receipt runtime paths.

- [ ] **Task 7A frozen tests and callable bindings를 read-only 재검증한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_source_acceptance.py \
                  research/rp-001/tests/test_source_availability.py \
                  research/rp-001/tests/test_credential_broker.py \
                  research/rp-001/tests/test_read_only_toss_adapter.py -v
```

Expected: Task 6E GREEN output과 exact source/test hashes가 일치하고 `test_search_plan_precedes_every_future_request`, `test_public_source_has_no_credential_dependency`, `test_unrotated_toss_plan_is_nonterminal_blocked_not_closure`가 pass한다. provider/search/transport spy와 source/test write는 0이다.

- [ ] **Step 2: frozen publisher로 첫 provider request 전 SourceAvailabilitySearchPlan runtime artifact를 immutable publish한다**

각 study×source×required-field set에 대해 `SourceAvailabilitySearchPlan` 하나를 **이후에 새로 시작하는** provider 검색, 문서 열람, token/request probe 전에 발행한다. plan 이전의 Toss metadata-only probe는 이 plan의 request/audit/coverage 집합에 들어가지 않으며 closure의 numerator나 exhaustion evidence가 될 수 없다. plan은 exact `planId/version/studySlot/sourceId/requiredFieldIds`, 사전 알려진 primary source와 official endpoint operation ID/path hash, 최대 request 횟수, success/exhaustion/rights-failure stop rule, `coverageDenominator=requiredFieldIds×plannedSourceEndpointCells`, 이름을 사후 고르지 않는 contract-based alternative-source inclusion rule, 독립 reviewer `ArtifactBindingV2`, `protectedPathManifestSha256`, `frozenAt`을 닫는다. plan event 하나를 파일 하나에 append하고 별도 immutable head pin과 projection을 재생하며 event·pin·projection 각 file의 별도 sidecar를 생성한다.

```text
SourceAvailabilitySearchPlanPublisher.publish(plan: SourceAvailabilitySearchPlan, protectedPathManifestSha256: str) -> SourceAvailabilitySearchPlanEvent
SourceAvailabilitySearchPlanPublisher.verify_head(planId: str, planSha256: str) -> SourceAvailabilitySearchPlanVerification
SourcePlanOutcomeClassifier.classify(plan: SourceAvailabilitySearchPlan, evidence: Sequence[SourcePlanEvidence]) -> SourcePlanOutcome
SourceAvailabilityClosureValidator.close(plan: SourceAvailabilitySearchPlan, requests: Sequence[ProviderRequestAuditEvent], reviewer: ArtifactBindingV2) -> SourceAvailabilityClosure
```

publisher는 predata rule freeze/hash와 protected manifest를 먼저 검증하고 provider transport/search spy 호출 전에 event/head/sidecar를 원자 발행한다. plan 수정 API는 제공하지 않으며 다른 탐색은 새 ID와 독립 사전 reviewer를 갖는 successor plan으로만 발행한다. 결과/response를 본 후 current plan의 source, endpoint, cap, stop, denominator, alternative rule을 바꾸는 mutation은 RED다.

- [ ] **Step 3: historical foundation과 current Toss operational event를 분리해 append한다**

`SourceMetadataAcceptance`는 provider identity, 공식 문서 path/bytes SHA-256/response hash/receivedAt, rights·entitlement·retention·derived-publication·redistribution, timestamp/timezone/session, native/adjusted/volume/shares/currency unit, corporate-action/revision, `providerAuthRequirement`와 conditional `credentialStatus`만 닫는다. raw 또는 processed market artifact의 path/hash는 허용하지 않는다. 기존 `DC-002`, `SP-002`, `source-matrix.json`, `official-source-register.json`의 exact hashes를 historical provenance로 사용하고 그 bytes와 `liveApiCalled=false`를 바꾸지 않는다. required branch는 `rotated`, nonsecret `rotationEvidenceId`, `deliveryBoundary`만 허용한다. public branch는 `not_required`이고 rotation/delivery/credential event field를 금지한다. secret-like value는 두 branch 모두 거부한다.

새 current operational event에는 `observedAt=2026-07-10`, `authorizationScope=read_only_research_probe`, `eventKind=legacy_metadata_only_operational_exposure`, `preexistingExposure=true`, `eligibleForClosure=false`, `eligibleForSourceAcceptance=false`, OAuth success, `GET /api/v1/stocks?symbols=MU`, HTTP 200, result count 1, response body persisted=false, secret persisted=false, order/account calls=0만 기록한다. key/token/body는 읽기 가능한 artifact에 포함하지 않는다. 이 event는 과거 credential operability 노출의 audit input일 뿐 raw data acceptance·future search request·closure coverage가 아니며 probe credential은 raw collection에 부적격이다. raw acceptance에는 별도 rotated credential evidence와 rights/retention/redistribution closure가 필요하다. current raw 저장 status는 다음 exact string이다.

같은 current event의 별도 source-document stability observation에는 official OpenAPI latest HTTP 200, `info.version=1.2.2`, body size 340381 bytes, 27 paths/30 operations와 response SHA-256 `2c54ebfd038a8c135f4b7f9036c42934d8ab9906c026251a7ae827b81e8e6aa8`이 DC-002 `TOSS-DOC-002.httpResponseSha256`과 exact match했다는 사실만 기록한다. response body는 저장·출력하지 않고 이 observation을 새 data 결과, raw dataset, CD/G7 또는 rights/retention evidence로 사용하지 않는다.

```text
blocked_pending_rotated_credentials_and_provider_retention_and_redistribution_clarification
```

Any governed plan that still has this status emits `nonterminal_blocked` with exact blocker evidence and reopen condition. It cannot emit SourceAvailabilityClosure, `exhausted_unavailable` or `data_unavailable` until the blocker is resolved and a new governed plan actually exhausts its frozen search contract.

- [ ] **Task 7A runtime artifact와 security review를 통과한다**

Run: Task 7A read-only command와 동일.

Expected GREEN: search-plan chronology, exact Toss GET/OAuth allowlist, credential boundary, historical/current 분리가 모두 `OK`; secret/key/token/body persistence와 order/account transport call은 0이다. source/security reviewer가 승인하기 전 Task 7B로 가지 않는다.

#### Task 7B execution unit: external sink descriptor, resolver, immutable sink

**Files:** read only and rehash Task 6E-frozen `external_raw_sink.py`, `external_artifact_locator.py`, their two tests and `external-sink-descriptor.schema.json`; publish only authoritative descriptor event/local-head/projection/receipt runtime paths.

- [ ] **Task 7B frozen sink tests and callable bindings를 read-only 재검증한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_external_raw_sink.py \
                  research/rp-001/tests/test_external_artifact_locator.py -v
```

Expected: Task 6E GREEN output과 exact source/test hashes가 일치하고 `test_sink_must_be_external_and_content_addressed`, `test_locator_never_serializes_absolute_root`가 pass한다. repository/shared-temporary write spy와 source/test write는 0이다.

- [ ] **Step 4: frozen services로 sealed metadata-only authorization/snapshot과 sink runtime artifacts를 publish한다**

```text
SourceMetadataAcceptanceValidator.validate(record: SourceMetadataAcceptance) -> SourceMetadataAcceptanceReport
SourceMetadataAcceptanceValidator.eligible_studies(record: SourceMetadataAcceptance) -> Sequence[str]
DesignMetadataCaptureAuthorizer.seal(acceptance: SourceMetadataAcceptance, requestedClasses: FrozenSet[str]) -> DesignMetadataCaptureAuthorization
UniverseMetadataSnapshotBuilder.capture(sealedContract: DesignMetadataCaptureAuthorization) -> UniverseMetadataSnapshot
CredentialBroker.spawn_read_only(request: ReadOnlyRequest, environmentAllowlist: FrozenSet[str]) -> RedactedChildResult
ReadOnlyTossAdapter.get_public_market_metadata(request: PublicMarketMetadataRequest) -> MetadataResponseEnvelope
ExternalRawSink.open(sealedContract: RawCollectionAuthorization) -> ImmutableRawSink
ExternalRawSink.tombstone(artifactHash: str, retentionBasis: RetentionBasis) -> TombstoneEvent
ExternalSinkResolver.resolve_for_process(sinkId: str, resolverKey: str) -> LocalSinkRoot
ExternalArtifactLocatorFactory.create(sink: ImmutableRawSink, contentSha256: str) -> ExternalArtifactLocator
```

`ExternalSinkDescriptorPublisher`는 `sinkId`, monotonically increasing `descriptorVersion`, exact `permissionMode`, owner UID/GID policy, VCS non-membership evidence, retention deadline/policy, tombstone policy, `resolverKey`, external local resolver config bytes의 SHA-256, approver `ArtifactBindingV2`, optional predecessor event ID를 closed schema로 발행한다. canonical descriptor 안에는 자기 bytes hash field를 두지 않고 sidecar와 `ArtifactBindingV2`가 자기 hash SSOT다. event/local head/projection은 `.pending_unanchored` suffix와 독립 sidecar를 갖고 검증된 external receipt 전 raw authorization에 사용할 수 없다. absolute resolver-config path와 resolved sink root는 one-shot process-local input이며 serializer/logger의 타입에 들어갈 수 없다. mode/owner/VCS/retention/tombstone/approver 또는 resolver-config hash가 바뀌면 기존 descriptor를 수정하지 않고 predecessor를 가리키는 successor event를 발행한다.

`requested_classes`는 study-specific frozen `declaredMetadataClasses`와 같고 `{instrument_identity,trading_calendar,coverage_bounds,field_catalog}`의 부분집합이어야 한다. authorization은 endpoint/request schema/field allowlist/source ID/hash/expiry와 declared subset을 봉인한다. capture manifest는 actual class set이 declared subset과 같은지 검사하고 응답별 exact path, bytes SHA-256, source response hash, `clientReceivedAt`, audit-event hash를 갖는다. price, return, volume, order/book/trade/cancel, label, outcome 또는 파생값이 한 필드라도 있으면 snapshot을 폐기하고 다음 단계로 가지 않는다. universe 선택은 이 snapshot만 사용한다.

- [ ] **Task 7B runtime artifact와 storage-policy review를 통과한다**

Run: Task 7B read-only command와 동일.

Expected GREEN: descriptor event/head/projection/sidecar/receipt lineage, mode/owner/VCS/retention/tombstone/approver/resolver-config hash가 `OK`; descriptor self-hash field, repo absolute root, suffix rewrite, unanchored authorization과 in-repo/shared-temp write는 0이다. storage-policy reviewer 승인 전 Task 7C로 가지 않는다.

#### Task 7C execution unit: collection, processing, analysis readers

**Files:** read only and rehash Task 6E-frozen `collection_reader.py`, `analysis_reader.py`, `test_collection_reader.py`, `test_analysis_reader.py` and reader-chain tests; publish only raw/processing/processed authorization·manifest runtime paths.

- [ ] **Task 7C frozen reader-chain tests and callable bindings를 read-only 재검증한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_collection_reader.py \
                  research/rp-001/tests/test_analysis_reader.py \
                  research/rp-001/tests/test_source_acceptance.py \
                  research/rp-001/tests/test_source_availability.py \
                  research/rp-001/tests/test_external_raw_sink.py -v
```

Expected: Task 6E GREEN output과 exact source/test hashes가 일치하고 `test_collection_and_analysis_guards_are_separate`, `test_processed_manifest_and_code_bundles_are_required`가 pass한다. raw/model reader spy와 source/test write는 0이다.

- [ ] **Step 5: frozen services의 CD/SP 이후 raw→processing→analysis 권한 사슬과 reader 분리를 적용한다**

```text
RawCollectionAuthorizer.seal(snapshot: UniverseMetadataSnapshot, lineage: ReservationLineageBindingEvent, anchorReceipt: ExternalHeadAnchorReceipt, sinkDescriptor: ExternalSinkDescriptorEvent) -> RawCollectionAuthorization
CollectionReadGuard.capture_once(sealedContract: RawCollectionAuthorization, sink: ImmutableRawSink) -> RawCaptureManifest
ProcessingAuthorizer.seal(rawManifest: RawCaptureManifest, processingCodeBundleManifestSha256: str) -> ProcessingAuthorization
AnalysisReadGuard.open(processedManifest: ProcessedManifest, design: ConfirmationDesign, protocol: StudyProtocol, analysisCodeBundleManifestSha256: str, environmentSha256: str) -> AnalysisReader
```

`RawCollectionAuthorization`은 accepted source, snapshot, anchored `ReservationLineageBindingEvent`, final CD/protocol artifact bindings, universe, period, fields와 anchored sink descriptor event/hash만 갖고 아직 존재하지 않는 raw/processed hash나 local root를 요구하지 않는다. binding event와 sink descriptor의 external receipt가 없거나 CAS head가 rollback이면 authorization을 만들 수 없다. `ExternalSinkResolver`만 `sinkId+resolverKey+resolverConfigSha256`를 process-local absolute root로 해석하며 이 값은 serializer/logger API에 전달할 수 없다. `CollectionReadGuard`는 별도 `collection_reader.py`와 `CredentialBroker`/read-only adapter를 통해 한 번만 읽고 raw bytes를 content-addressed external immutable sink에 직접 기록하며 분석 객체를 반환하지 않는다. 그 결과인 `RawCaptureManifest`가 locator/`clientReceivedAt`를 고정한 뒤에만 raw manifest hash와 processing code hash로 `ProcessingAuthorization`을 만든다. processed manifest와 closure evidence도 locator와 raw backreference만 고정한다. 별도 `analysis_reader.py`의 `AnalysisReadGuard`는 locator content hash, processed manifest·final CD·final SP·analysis code·environment hash와 lineage event를 모두 확인할 때만 model-visible rows를 반환한다. 두 reader module은 상호 import할 수 없다.

- [ ] **Step 6: frozen three-state outcome과 data_unavailable formal closure를 적용한다**

`nonterminal_blocked`는 권한·승인·entitlement·수집·credential·anchor·provider transport가 미완인 pre-run outcome이고 terminal이 아니다. It requires exact blockingReason/evidence/affectedStudySlots/reopenCondition/observedAt and forbids SourceAvailabilityClosure, metadata snapshot, attempted exhaustion and data_unavailable. `SourceAvailabilityClosure`는 실제 request budget을 수행해 unavailable을 소진한 경우에만 frozen plan event/head와 exact `searchPlanId/searchPlanSha256`를 재해시하고 `searchPlanFrozenAt < firstRequestAt <= finalRequestAt <= closure.createdAt`을 검증한다. 또한 plan에 등록된 exact source/endpoint/required-field cell의 `future_plan_governed_availability_request` audit event 전체, provider request/response `ExternalArtifactLocator`, planned denominator와 attempted numerator, cap/stop 준수, alternative-source disposition, plan에 동결된 독립 판정자 `ArtifactBindingV2`, closure reason을 모두 가져야 한다. `eligibleForClosure=false`인 event, 특히 preexisting Toss probe와 any blocker는 numerator·denominator·stop/exhaustion evidence에 들어가면 validator가 거부한다. request/response timestamp는 immutable audit event와 locator metadata에서 재계산하며 closure 자체의 주장을 신뢰하지 않는다. 이 closure가 validator를 통과한 경우에만 `data_unavailable` terminal을 허용한다.

blocked ordered-feed plan은 MIC와 dependent RSK/SYN만, blocked order-lifecycle/cost plan은 EXE와 dependent RSK/SYN만, blocked PIT factor/corporate-action plan은 VAL만 막는다. One blocked MIC plan cannot block unrelated BEH/VAL admission. 독립 SG3·합성 tests와 scoped snapshot에서 수락된 다른 study는 계속 가능해야 한다.

- [ ] **Step 7: 7C read-only verification과 reader-boundary review를 확인한다**

Run: Step 1과 동일.

Expected: historical foundation hash 불변, post-hoc plan mutation 거부, conditional credential contract, external sink descriptor와 collection/analysis reader 분리가 frozen synthetic contract tests에서 통과한다. provider/search/request·raw/model reader와 source/test writes는 0이다. 7C reviewer는 source chain의 단계별 import boundary를 승인하지만 actual metadata snapshot과 Checkpoint B는 아직 선언하지 않는다.

#### Task 7C2 execution unit: exact SourcePlanSetManifest and per-plan actual runtime

Task 7A source/security, Task 7B storage-policy and Task 7C reader-boundary reviewer verdict hashes가 모두 검증된 뒤에만 actual CLI command를 실행한다. 하나라도 없으면 provider/search transport and runtime write are zero.

**Files:**

- Read only and rehash Task 6E-frozen thin shell/registry: research/rp-001/run_evidence_engine.py, research/rp-001/src/rp001/evidence_cli_contract.py, research/rp-001/contracts/evidence-cli-command-dispatch-registry.json and sidecar
- Read only and rerun Task 6E CLI tests: research/rp-001/tests/test_evidence_cli_contract.py, research/rp-001/tests/test_evidence_engine_cli.py, research/rp-001/tests/test_source_runtime_cli.py
- Read only and rehash Task 6E-frozen: research/rp-001/src/rp001/source_plan_set.py, research/rp-001/tests/test_source_plan_set.py, research/rp-001/src/rp001/source_availability.py, research/rp-001/tests/test_source_availability.py
- Create and anchor: research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json and .sha256
- Create one plan event/sidecar/anchor binding per deterministic plan ID under source-availability-search-plan-events/{planId}/
- Read only: registered study/input contracts and Task 6E-frozen Task 7 service bindings
- Create exactly one SourcePlanOutcome runtime event per plan: eligible metadata artifacts, exhausted closure, or nonterminal blocker according to the closed three-state contract

Task 7C2는 CLI shell, dispatch registry 또는 CLI tests를 생성·수정·확장하지 않는다. 각 actual invocation 전에 Task 6E AnalysisCodeBundleManifest가 결박한 세 file과 tests를 재해시하고 closed registry membership을 확인한다. source acceptance, metadata validation, closure classification or result semantics는 Task 7A/B/C와 source_plan_set application service가 소유하며 CLI에 재구현하지 않는다.

- [ ] **Task 7C2 frozen three-outcome tests and callable bindings를 read-only 재검증한다**

Task 6E RED artifacts는 registered study/input cell 누락, plan receipt 전 request, two resolved outcomes, blocker→closure 위조와 global over-block counterexamples를 보존한다. 여기서는 tests/source를 바꾸지 않고 다음 named assertions의 GREEN과 bundle hashes를 재검증한다.

~~~text
test_source_plan_set_equals_registered_study_source_field_cells
test_every_plan_is_anchored_before_provider_request
test_each_plan_has_exactly_one_of_three_outcomes
test_resolved_plan_cannot_have_both_metadata_and_closure
test_unrotated_toss_plan_is_nonterminal_blocked_not_closure
test_blocked_plan_cannot_produce_data_unavailable
test_blocked_mic_plan_does_not_block_unrelated_beh_val_admission
test_blocked_mic_keeps_mic_and_dependent_rsk_syn_blocked
test_planned_executed_plan_bijection_is_required
~~~

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_source_plan_set.py \
                  research/rp-001/tests/test_source_availability.py \
                  research/rp-001/tests/test_study_candidate_admission.py \
                  research/rp-001/tests/test_program_completion.py -v
~~~

Expected: all named tests pass, exact Task 6E source/test hashes match, and Task 7C2 code/test writes are zero.

- [ ] **all-plan manifest와 actual plan events를 provider access 없이 freeze·anchor한다**

SourcePlanSetManifest expected set은 registered study slots × FormulaRecord required input symbols × accepted DatasetContract source/required-field cells에서 결과 독립적으로 계산한다. deterministic plan ID는 studySlot, sourceId and requiredFieldSet hash의 canonical function이다. orderedPlanIds, exact plan artifact bindings, expected count and studySourceFieldCellSet은 set-equality여야 한다. plan 하나를 합치거나 누락하거나 global catch-all plan을 만들 수 없다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --freeze-source-search-plan \
  --plan-set-manifest research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --for-each-plan \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

이 command는 every individual plan and SourcePlanSetManifest를 sidecar→CAS→ArtifactExternalAnchorBindingEvent 순서로 닫으며 provider/search/transport spy는 0이다. manifest and every plan anchor receipt가 없으면 다음 command는 exit 2다.

- [ ] **every exact plan을 governed search로 실행한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-source-search \
  --plan-set-manifest research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --for-each-plan \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

executor는 manifest order로 exact plan ID/hash/receipt를 재검증하고 각 plan의 endpoint/request cap/stop rule만 실행한다. 각 plan outcome은 정확히 `eligible_metadata | exhausted_unavailable | nonterminal_blocked` 중 하나다. planned plan IDs and executed outcome plan IDs are bijective; disclosure coverage counts all three states. `nonterminal_blocked` is selected for unrotated credential, unresolved rights/approval/entitlement, incomplete collection/anchor or provider transport blocker and records exact blockingReason/evidence/affectedStudySlots/reopenCondition/observedAt without inventing requests or exhaustion.

- [ ] **eligible plan subset의 metadata를 capture and verify한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --capture-authorized-metadata \
  --plan-set-manifest research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --eligible-plans \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-metadata-snapshot \
  --plan-set-manifest research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --eligible-plans \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

eligible plan마다 anchored SourceMetadataAcceptance, DesignMetadataCaptureAuthorization and UniverseMetadataSnapshot을 만든다. actual metadata classes must equal the frozen declared subset. successful metadata plan은 exhausted와 blocked set에서 제외되며 close command가 같은 plan을 받으면 transport/write 전 exit 2다. blocked plan은 metadata capture command에 들어오면 exit 2다.

- [ ] **exhausted plan subset만 closure한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --close-source-availability \
  --plan-set-manifest research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --exhausted-plans \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

closure는 frozen denominator, actual request/response locators, timestamps, cap/stop exhaustion and independent review를 요구한다. exhausted plan은 eligible/blocked set에서 제외된다. blocked plan에는 close command가 exit 2이며 SourceAvailabilityClosure, attempted exhaustion and data_unavailable reference가 없다. program 전체를 여기서 중단하지 않는다: all three anchored outcome events를 Task7D SP-016에 전달하여 scoped DataLineageDisposition과 DataLineageEligibilitySnapshot을 만든다. unaffected eligible formula/study inputs continue; only bindings that touch blocked or closed mandatory plans are blocked.

- [ ] **Task 7C2 GREEN and independent runtime review로 Checkpoint B를 닫는다**

Run: Task7C2 read-only unittest command와 아래 Task 6E-frozen CLI test command를 실행하며 source/test/registry write count는 0이어야 한다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_evidence_cli_contract.py \
                  research/rp-001/tests/test_evidence_engine_cli.py \
                  research/rp-001/tests/test_source_runtime_cli.py -v
~~~

Expected: SourcePlanSet expected/actual count and disclosure bijection 1.00 across all three outcomes, every plan anchor-before-request 1.00, per-plan outcome exact-one 1.00, resolved metadata/closure overlap 0, blocked closure/snapshot/exhaustion count 0, secret/body persistence and order/account calls 0. Closure/exhaustion coverage denominator contains only `exhausted_unavailable` and excludes blocked. All outcomes, including mixed eligible/exhausted/blocked results, proceed to Task7D; program completion remains false while blocked count>0.

#### Task 7D execution unit: SP-016 data-lineage audit before empirical promotion

**Files:**
- Read only and rehash Task 6E-frozen: `research/rp-001/src/rp001/data_lineage_terminalization.py`, `data_lineage_registers.py`, `source_plan_set.py`, `source_impact_terminalizer.py` and `research/rp-001/tests/test_data_lineage_terminalization.py`, `test_data_lineage_registers.py`, `test_source_plan_set.py`, `test_source_impact_terminalizer.py`
- Create: `research/meta-research/objects-v2/study-protocols/SP-016-data-lineage-operational-audit/object.json`
- Create: `research/meta-research/objects-v2/study-protocols/SP-016-data-lineage-operational-audit/object.json.sha256`
- Create: `research/meta-research/objects-v2/study-protocols/SP-016-data-lineage-operational-audit/protocol.md`
- Create: `research/meta-research/objects-v2/study-protocols/SP-016-data-lineage-operational-audit/protocol.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/object.json`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/object.json.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/evidence.json`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/evidence.json.sha256`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/evidence.md`
- Create after terminal anchor: `research/meta-research/objects-v2/evidence-bundles/EB-011-data-lineage-operational-audit/evidence.md.sha256`
- Publish runtime artifacts only through frozen `data_lineage_registers.py`: `research/rp-001/reports/dataset-contract-register.json`, `.sha256`, `research/rp-001/reports/source-matrix.current.json`, `.sha256`
- Create registration events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/registration-events/SP-016/<sequence>.pending_unanchored.json`, `registration-events/EB-011/<sequence>.pending_unanchored.json` and sidecars
- Create lifecycle events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/lifecycle-events/SP-016/<sequence>.pending_unanchored.json`, `lifecycle-events/EB-011/<sequence>.pending_unanchored.json` and sidecars
- Create artifact-binding events: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/artifact-binding-events/SP-016/<sequence>.pending_unanchored.json`, `artifact-binding-events/EB-011/<sequence>.pending_unanchored.json` and sidecars
- Create runtime outcome/disposition/snapshot/terminal paths: `source-plan-outcome-events/<planId>/<sequence>.pending_unanchored.json`, `data-lineage-disposition-events/<studySlot>/<planId>.pending_unanchored.json`, `data-lineage-eligibility-snapshots/SP-016/<sequence>.pending_unanchored.json`, optional `terminal-decision-computations/ST-DAT-001/<sequence>.pending_unanchored.json`, optional `study-terminal-events/ST-DAT-001/<sequence>.pending_unanchored.json`, local heads, ArtifactExternalAnchorBindingEvents and receipts
- Rebuild and anchor exactly: `research/meta-research/catalog/research-objects.v2.pending_unanchored.json`, `research/meta-research/catalog/artifact-bindings.v2.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.v2.pending_unanchored.json`, `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/current-program-state.v2.pending_unanchored.json` and four sidecars

SP-016 dependsOn remains `[DC-002,RQ-002,SP-002]`. Pinned DC descriptor/body hashes are `4583bc6ff9778a9314c8967e98778809530d048f2a8eb3cb1ba767188c8d646c` / `0eb5926196b5ebb1ba6f2f704430a05033336f4363482cdfa85634ecf5a0cca0`; RQ hashes are `3cb34e74ae26db703c28bbe8a5e1bd4cfe3655aa59d8e8c213abfce5cb680c46` / `371d69165b2c2baddc88e39375dd3a66497d278a5b94f44bd86908cfc862db69`; SP hashes are `ca718b670855a84fba1bbe60175ca506da3404dfe48401fbc9e73a31b73c4ebe` / `bbdf0603b55a5b3b18dd20cdc7f2f0161b47dffb35edeffd39026f464fe29a7e`.

- [ ] **Task 7D frozen SP-016/snapshot/register tests and callable bindings를 read-only 재검증한다**

Task 6E RED artifacts preserve counterexamples for a missing plan outcome, partial closure/global over-block, blocked→closure forgery, impacted RawCollectionAuthorization and missing RD-004/005 output. Here the same frozen tests must be GREEN: `test_sp016_aggregates_every_plan_outcome`, `test_nonterminal_blocked_is_scoped_and_anchored`, `test_blocked_plan_cannot_produce_data_unavailable`, `test_data_lineage_snapshot_allows_unaffected_admission`, `test_impacted_input_blocks_raw_authorization_and_g3`, `test_dataset_contract_register_output_is_required`, `test_current_source_matrix_output_is_required`. historical/current mixing, legacy Toss denominator, EB-before-terminal and G3 auto-pass remain named failures in Task 6E RED evidence.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_data_lineage_terminalization.py \
                  research/rp-001/tests/test_data_lineage_registers.py \
                  research/rp-001/tests/test_source_plan_set.py \
                  research/rp-001/tests/test_study_candidate_admission.py \
                  research/rp-001/tests/test_program_completion.py -v
```

SP-016은 actual SourcePlanSetManifest의 every anchored SourcePlanOutcome and its eligible metadata artifacts, exhausted SourceAvailabilityClosure or nonterminal blocker evidence를 두 독립 reviewer가 재해시하고 all-plan scoped DataLineageDisposition을 만든다. Metadata and closure remain mutually exclusive for resolved outcomes; blocked is the third nonterminal branch. 기존 metadata-only Toss probe는 operational provenance에만 있고 acceptance/search denominator, closure, raw reuse와 G3에 들어가지 않는다. Every disposition is anchored before a separate DataLineageEligibilitySnapshot deterministically binds the exact outcome set, eligible/exhausted/blocked plan IDs and per-study input scope. This snapshot may feed unaffected admission even when blockedPlanIds is nonempty.

If blockedPlanIds is nonempty, frozen ST-DAT evaluator returns `NonTerminalBlocked`; it publishes no StudyTerminalEvent and EB-011 is not created. When blocked count is zero and the frozen rule is terminalizable, TerminalDecisionComputation is anchored, then an EB-free ST-DAT StudyTerminalEvent is published/anchored, and only then EB-011 is published in another transaction. ST-DAT terminal does not auto-pass G3; G3 remains per-study and requires actual lineage. Final program completion still requires an anchored ST-DAT terminal, blocked count=0 and EB-011.

- [ ] **anchored scoped snapshot을 publish한 뒤 RD-004와 RD-005를 exact order로 publish한다**

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-data-lineage-eligibility-snapshot \
  --source-plan-set research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-plan-set-manifest.json \
  --output research/meta-research/objects/programs/RP-001-quantitative-market-behavior/data-lineage-eligibility-snapshots/SP-016/000001.pending_unanchored.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-dataset-contract-register \
  --eligibility-snapshot research/meta-research/objects/programs/RP-001-quantitative-market-behavior/data-lineage-eligibility-snapshots/SP-016/000001.pending_unanchored.json \
  --output research/rp-001/reports/dataset-contract-register.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-current-source-matrix \
  --eligibility-snapshot research/meta-research/objects/programs/RP-001-quantitative-market-behavior/data-lineage-eligibility-snapshots/SP-016/000001.pending_unanchored.json \
  --output research/rp-001/reports/source-matrix.current.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
```

`DataLineageRegisterPublisher.publish_dataset_contract_register(snapshot: AnchoredDataLineageEligibilitySnapshot, outputPath: Path) -> AnchoredArtifactBinding` and `DataLineageRegisterPublisher.publish_current_source_matrix(snapshot: AnchoredDataLineageEligibilitySnapshot, outputPath: Path) -> AnchoredArtifactBinding` are Task 6E-frozen APIs. Each command requires all SP-016 audit inputs/dispositions anchored and publishes exact body→sidecar→v2 registration/artifact binding→trace backreference→CAS→ArtifactExternalAnchorBindingEvent. Missing output, wrong RD path, sidecar, anchor, v2 or trace fails before admission. RD-004/005 RequiredDeliverableRegistry owner/path bindings are exact Task7D rows.

- [ ] **ST-DAT를 evaluate하고 terminal인 경우에만 terminal-first, EB-second를 실행한다**

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-DAT-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-evidence-bundle EB-011 \
  --terminal-study ST-DAT-001 \
  --require-anchored-terminal \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/meta-research/tools/validate_research_program_v2.py \
  --repository-root . --program-root research/meta-research --graph-mode current-v2
```

When ST-DAT evaluation returns NonTerminalBlocked, the EB command is skipped and current-v2 validation accepts the anchored scoped snapshot/dispositions but reports terminal/completion pending. When terminalizable, SP-016 and ST-DAT terminal registration/anchor precede separate EB-011 registration/anchor. Expected: exact four projection rebuild and current-v2 validation pass; plan-level dispositions cover SourcePlanSetManifest exactly; RD-004/005 exist with sidecar/anchor/v2/trace; G3 auto-pass count is 0; unaffected study branches remain eligible for Task7E through the snapshot. data-lineage reviewer 승인 전 Task 7E와 8A로 가지 않는다.

#### Task 7E execution unit: multi-input StudyCandidateAdmission and scoped source-impact terminalization

**Files:**

- Read only and rehash Task 6E-frozen: research/rp-001/src/rp001/study_candidate_admission.py, source_impact_terminalizer.py, terminal_decision_computation.py, study_terminal_publisher.py and research/rp-001/tests/test_study_candidate_admission.py, test_source_impact_terminalizer.py, test_data_lineage_terminalization.py
- Create append-only study-candidate-admission-events/{studySlot}/{formulaId}/{sequence}.pending_unanchored.json, sidecars, anchor-binding events and receipts
- When all required study inputs have valid closures, create TerminalDecisionComputation and StudyTerminalEvent at terminal-decision-computations/{studySlot}/ and study-terminal-events/{studySlot}/ without ExperimentRun

- [ ] **Task 7E frozen scoped-admission tests and callable bindings를 read-only 재검증한다**

Task 6E RED artifacts preserve one-source multi-input admission, missing required symbol, global terminal prerequisite, closure/global over-block and blocked MIC propagation counterexamples. Here the frozen tests must be GREEN without source/test changes.

~~~text
test_mathematical_eligibility_does_not_imply_study_admission
test_required_input_symbols_equal_source_contract_field_bindings
test_admission_uses_ordered_exact_multi_input_hashes
test_partial_closure_blocks_only_impacted_formula_and_study
test_blocked_mic_plan_does_not_block_unrelated_beh_val_admission
test_blocked_mic_keeps_mic_and_dependent_rsk_syn_blocked
test_admission_uses_scoped_snapshot_without_global_supported_terminal
test_all_required_closures_terminalize_only_affected_study
test_data_unavailable_terminal_creates_no_experiment_run
~~~

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_study_candidate_admission.py -v
~~~

Expected: exact Task 6E source/test hashes match, all named tests pass and Task 7E source/test writes are zero.

- [ ] **frozen evaluator로 ordered multi-input scoped admission runtime events를 publish한다**

~~~text
StudyCandidateAdmissionEvaluator.evaluate(formula: FormulaRecord, eligibility: EligibilityDecision, dataLineageEligibilitySnapshot: AnchoredDataLineageEligibilitySnapshot, sourceAcceptanceHashes: Sequence[str], inputContractHashes: Sequence[str], sourceAvailabilityClosureHashes: Sequence[str], sourcePlanOutcomeBindings: Sequence[SourcePlanOutcomeBinding], inputSymbolSourceBindings: Sequence[InputSymbolSourceBinding], dataLineageDispositions: Sequence[DataLineageDisposition], ontologyMappingSha256: str) -> StudyCandidateAdmission
SourceImpactTerminalizer.evaluate(studySlot: str, requiredInputSymbols: Sequence[str], closures: Sequence[SourceAvailabilityClosure], frozenRule: StudyTerminalDecisionRule) -> TerminalDecisionComputation | NonTerminalBlocked
~~~

inputSymbolSourceBindings row는 formulaId, inputSymbolId, DatasetContract ID/hash, source plan ID/outcome hash, source/closure artifact hash, provider field ID, unit, availability rule and disposition을 갖는다. evaluator는 FormulaRecord required inputSymbols exact set과 binding inputSymbol IDs set-equality, accepted source/contract/field exact bijection, anchored DataLineageEligibilitySnapshot, SP-016 DataLineageDisposition and ontology mapping을 검증한다. sourceAcceptanceHashes, inputContractHashes, closure hashes and sourcePlanOutcomeBindings are ordered exact arrays, not singular convenience fields. A global supported ST-DAT terminal is not an admission prerequisite.

한 formula의 every mandatory input binding이 snapshot에서 `eligible_metadata`이고 blocked/closed mandatory input이 없으면 admitted다. A touched `nonterminal_blocked` plan blocks that formula/study; MIC blockers also block dependent RSK/SYN but not unrelated BEH/VAL. A touched valid exhausted closure blocks only that formula/control until all required inputs for the affected study are validly closed; then SourceImpactTerminalizer may create its data_unavailable terminal. Other formula/study eligible bindings continue to DesignCore through the anchored scoped snapshot even while ST-DAT is NonTerminalBlocked. No successor protocol, PlannedRunKey, reservation or ExperimentRun is fabricated for blocked/closed branches.

- [ ] **scoped admission reviewer verdict를 기록한다**

Expected: FormulaRecord symbol→source/contract/field/outcome bijection 1.00, ordered multi-input and snapshot hash coverage 1.00, blocked/closure over-block count 0, affected MIC/RSK/SYN blocked, unrelated BEH/VAL continuation, affected all-closure study terminal exact-one and ER count 0. admission reviewer 승인 후 unaffected admitted set만 8A로 간다.

### Task 8A: D1 DesignCore

**Files:** `research/rp-001/src/rp001/confirmation_design.py`, `research/rp-001/tests/test_confirmation_design_core.py`, `research/rp-001/designs/CD-001-confirmation-design-core.json`, `.sha256`.

- [ ] **RED:** test를 먼저 작성하고 importable counterexample builder가 analysis code-bundle hash를 누락하도록 작성한다. exact command는 `test_design_core_binds_both_code_bundles_and_all_prerequisites`에서 실패해야 한다. import/discovery/syntax failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_confirmation_design_core.py -v
```

D1은 PreDataRuleFreeze, ontology mapping, anchored DataLineageEligibilitySnapshot, scoped StudyCandidateAdmission exact set, each admitted formula의 no-blocked/no-closed mandatory input proof, eligible UniverseMetadataSnapshot, seen-data exclusion, required controls, cost/δ/censoring/imbalance/resampling/stopping/multiplicity rules와 anchored Processing/AnalysisCodeBundleManifest sidecar hashes를 canonicalize한다. A global ST-DAT terminal is not required for unaffected D1 branches; final program completion still requires it. reservation, protocol core, final CD/protocol와 dataset hash는 금지한다.

Run GREEN: RED와 같은 exact command. DesignCore reviewer가 hash set과 no-future-reference를 승인한 뒤에만 9A로 간다. 8A는 Task 8 전체 완료가 아니다.

### Task 9A: D2 SuccessorProtocolCore(s)

**Files:** `research/rp-001/src/rp001/protocol_core.py`, `research/rp-001/tests/test_protocol_core.py`, each `objects-v2/study-protocols/SP-009` through `SP-014` directory의 `protocol-core.json`, `.sha256`.

- [ ] **RED:** test를 먼저 작성하고 counterexample core가 DesignCore hash 대신 final CD hash를 참조하도록 작성한다. exact command는 `test_protocol_core_depends_only_on_prior_dag_nodes`에서 실패해야 한다. import/discovery/syntax failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protocol_core.py -v
```

predecessor protocol hashes are pinned: SP-003 `2c6a92f319f7a4c1150c31c2bf3dae948504d60399c2314d3a79815446555a5c`; SP-004 `59e87a90f507dc4d54de8c1cc307c144a6d8b2a10fe1c0d76000b2a19ad18f25`; SP-005 `2fc7865e4904198a20e68238c912b38883d08e1385f240c03eb174983e4c9ca3`; SP-006 `95f1ff3da6020a24238fb32a39d799bd3c54d379e53bd81ea3bb9d8dbfb6849d`; SP-007 `b867c51f314ef7e30020b93245cd7d4a6b9f04029f9cfa20793077b0765410ac`; SP-008 `08e7b13e55ebd86879ca2efc2e0376b7906ccdc3f9cd13dbe3093fba8c4eed9d`. Exact dependsOn orders are SP-009 `[DC-003,RQ-003,SP-003]`, SP-010 `[DC-004,RQ-004,SP-004]`, SP-011 `[DC-005,RQ-005,SP-005]`, SP-012 `[DC-006,RQ-006,SP-006]`, SP-013 `[DC-007,RQ-007,SP-007]`, SP-014 `[DC-008,RQ-008,SP-008]`. `study-contracts.json` hash is `c9a73212bdb4dc4bc79dc2fcec1c6b2ffdb5ff23a1879d266ea9d8d1227a9994`.

D2 binds D1, predecessor/RQ/DC descriptor+body hashes, both code bundles, admitted candidates/controls, estimand, folds, horizons and terminal rules. It cannot contain reservation, final artifact, raw/processed dataset or its own sidecar hash. blocked studies receive a promotion event with blocker, not an empty core.

Run GREEN: RED와 같은 exact command. protocol-core reviewer approves exact dependencies before 8B.

### Task 8B: D3 PlannedRunKey grid → D4 ReservationManifest → D5 final CD

**Files:** `run_id_reservation.py`, `test_run_id_reservation.py`, `test_confirmation_design_finalization.py`, reservation event roots, `CD-001-confirmation-design.json`, `.sha256`, `confirmation-design-register-events/`, and the single projection `confirmation-design-register.pending_unanchored.json`, `.sha256`.

- [ ] **RED:** tests를 먼저 작성하고 counterexample grid가 processing bundle hash를 누락하고 one ID를 재사용하며 D5 body에 자기 sidecar와 future D7 hash를 삽입하도록 작성한다. exact command는 `test_planned_keys_bind_frozen_code_and_reservations_are_bijective`, `test_final_cd_binds_only_d1_through_d4`, `test_final_cd_rejects_self_sidecar_and_future_d6_d7_references`에서 실패해야 한다. import/discovery/syntax failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_run_id_reservation.py \
                  research/rp-001/tests/test_confirmation_design_finalization.py -v
```

D3 key exact fields are study slot, D1 hash, D2 hash, input contract/snapshot hash, candidate/control, sample role, fold, horizon, seed, ImplementationBinding, ProcessingCodeBundleManifest and AnalysisCodeBundleManifest hashes. Final CD/protocol and future dataset hashes are forbidden. D4 assigns sorted keys bijectively to `ER-000001..ER-999999`; capacity excess returns `blocked_pending_new_successor_id_schema_version` without partial reservation. D5 binds D1/D2/D3/D4 and no self hash. Authoritative register events stay separate from the one named projection.

Run GREEN: RED와 같은 exact command. reservation/CD reviewer approves D3–D5 before 9B. Only now is Task 8 complete.

### Task 9B: D6 final successor protocols → D7 lineage receipt → v2 registration → RawCollectionAuthorization

**Files:** `protocol_promotion.py`, `reservation_lineage.py`, `test_protocol_promotion.py`, `test_reservation_lineage.py`; final `object.json`, `.sha256`, `protocol.md`, `protocol.sha256` in SP-009 through SP-014; successor trial event/projection files; promotion, lineage and RawCollectionAuthorization event roots.

- [ ] **RED:** tests를 먼저 작성하고 counterexample publisher가 final protocol before D5 and v2 registration before anchored D7을 시도하도록 작성한다. exact command는 `test_dag_order_precedes_registration_and_raw_authorization`에서 실패해야 한다. frozen v1 mutation, wrong dependsOn, missing SP-015 prerequisite, missing or unanchored `DataLineageEligibilitySnapshot`, the target admission's mandatory input binding touching a blocked or closed plan, code-bundle mismatch and partial capacity are separate named failures. `test_unaffected_admission_can_promote_with_nonterminal_st_dat`는 scoped snapshot상 mandatory inputs가 모두 eligible인 branch의 promotion을 허용하고, `test_affected_admission_cannot_promote`는 blocked/closed mandatory input을 가진 branch만 거부한다. import/discovery/syntax failure는 RED가 아니다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protocol_promotion.py \
                  research/rp-001/tests/test_reservation_lineage.py -v
```

D6 final protocol binds its D2 core, D5 sidecar and D4 manifest without a self hash. D7 binds D1→D6 exact paths/hashes and obtains the external receipt. Only after D7 may v2 registration/lifecycle/artifact projections rebuild. Promotion schema requires anchored SP-015 terminal+ontology mapping plus anchored DataLineageEligibilitySnapshot and the specific admission's no-blocked/no-closed mandatory input proof; it does not require a global supported ST-DAT terminal and does not alter either descriptor dependsOn. RawCollectionAuthorization requires completed v2 registration, D7 receipt, that branch's accepted source/snapshot/scoped disposition, anchored sink descriptor, exact period/fields, both code-bundle hashes and protected manifest. It contains no future raw/processed hash. Missing authority or a touched blocked/closed plan leaves that branch canonically blocked with raw read count zero while unrelated eligible branches continue.

Run GREEN: RED와 같은 exact command, then run both v1/v2 validators. Expected: D1→D2→D3→D4→D5→D6→D7→v2 registration→RawCollectionAuthorization exact order, frozen v1 graph, objects-v2 isolation and no hash cycle. independent promotion reviewer approval closes Checkpoint C.

### Task 10: actual raw→processed pipeline, ActualRunLineage와 ExperimentRun store

Task 10은 Task 6E에서 동결한 결과 의미 코드, ExperimentRunRepository, generic thin `run_evidence_engine.py`, `evidence_cli_contract.py`, closed dispatch registry와 tests를 절대 생성·수정·확장하지 않는다. raw/process/lineage subcommands는 이미 Task 6E registry에 존재해야 하며 Task 10은 exact bundle hash를 재검증한 뒤 실행만 한다. parser, normalization, point-in-time 처리, corporate action, feature, label, split, metric, model, candidate comparison, evidence 판단 또는 새 dispatch wiring을 CLI에 넣으면 manifest 밖 의미 변경이므로 실패다.

**Files:**

- Read only and rehash Task 6E-frozen: research/rp-001/src/rp001/experiment_run.py, research/rp-001/tests/test_experiment_run.py
- Read only and rehash Task 6E-frozen CLI: research/rp-001/run_evidence_engine.py, research/rp-001/src/rp001/evidence_cli_contract.py, research/rp-001/contracts/evidence-cli-command-dispatch-registry.json and its sidecar, research/rp-001/tests/test_evidence_cli_contract.py, research/rp-001/tests/test_evidence_engine_cli.py, research/rp-001/tests/test_source_runtime_cli.py
- Read only and rehash: processing-code-bundle-manifest.json, analysis-code-bundle-manifest.json과 두 bundle의 exact source/test/dependency/environment file set
- Read only: D1–D7 artifacts, v2 registration, RawCollectionAuthorization, actual source snapshot, both code-bundle manifests and upstream external receipts
- Create through frozen Task 7C/6E services during runtime: RawCaptureManifest, ProcessingAuthorization, ProcessedManifest and their sidecars/receipts
- Create append-only: actual-run-lineage-binding-events, executor-identity-binding-events, run-events, run-event-ledger-heads
- Create during empirical execution: objects-v2/experiment-runs/{runId}/object.json과 sidecar, research/rp-001/artifacts/{studySlot}/{runId}.json과 sidecar
- Append only to successor trial ledgers; 기존 proposed ledger와 frozen v1 bytes는 수정하지 않는다.

#### Task 10A: frozen ExperimentRun repository and CLI read-only verification

- [ ] **Task 6E RED/GREEN artifacts를 재해시하고 같은 tests를 read-only로 재실행한다**

Task 6E가 저장한 RED/GREEN output hashes, test count, run-store/CLI source·test hashes, dispatch registry sidecar와 AnalysisCodeBundleManifest binding을 먼저 검증한다. Task 10은 test fixture, source 또는 registry를 변경하지 않으며 아래 command는 GREEN이어야 한다. 실패하면 runtime을 시작하지 않고 successor AnalysisCodeBundleManifest→D1–D7→new reservations로 되돌아간다.

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_experiment_run.py \
                  research/rp-001/tests/test_evidence_cli_contract.py \
                  research/rp-001/tests/test_evidence_engine_cli.py \
                  research/rp-001/tests/test_source_runtime_cli.py -v
~~~

Task 6E에서 이미 RED→GREEN으로 동결한 거부 fixture는 다음을 모두 포함한다.

~~~text
reservation/PlannedRunKey/runId 중복 또는 exact ER-NNNNNN 형식 위반
Task 10의 allocate, high-water, capacity, namespace-transition 시도
ProcessedManifest locator, sidecar 또는 external receipt 누락
processed content를 resolver로 다시 읽고 SHA-256 재검증하지 않음
ActualRunLineageBindingEvent 없이 consume/start
actual lineage의 D1–D7, final CD/SP, dataset, processing bundle,
analysis bundle, executor, checkout, source tree, environment hash 불일치
AnalysisReadGuard보다 먼저 model/application import
running 없이 terminal, terminal 뒤 mutation, failed/invalid 누락
event file 한 개에 둘 이상의 record, prefix overwrite 또는 receipt mismatch
output path/hash, run descriptor, successor ledger backreference 누락
sensitive value, credential path, external absolute root 직렬화
~~~

- [ ] **frozen repository API와 선행조건 결박을 검증한다**

~~~text
ExperimentRunRepository.consume_reservation(
  RunIdReservation,
  ProcessedManifestVerification,
  ActualRunLineageBindingEvent
) -> RunEvent

ExperimentRunRepository.start(
  runId,
  AnalysisReadAuthorization,
  ExecutorIdentityBinding
) -> RunEvent

ExperimentRunRepository.complete(
  runId,
  outputArtifactBindings
) -> ExperimentRun

ExperimentRunRepository.fail(
  runId,
  RunFailure
) -> ExperimentRun

ExperimentRunRepository.invalidate(
  runId,
  RunFailure
) -> ExperimentRun
~~~

Task 6E-frozen repository는 Task 8B가 예약한 ER-000001부터 ER-999999까지만 소비한다. descriptor, artifact, event, local-head 경로는 runId와 six-digit sequence의 total function으로 계산한다. Task 10에는 ID 할당 또는 repository/dispatch 변경 API가 없다.

RawCaptureManifest 뒤 anchored ProcessingAuthorization을 발행하고, ProcessingCodeBundleManifest의 exact callable로 처리한 뒤 ProcessedManifest와 개별 sidecar·external receipt를 먼저 만든다. ProcessedManifest는 processed ExternalArtifactLocator, raw manifest backreference, processing bundle hash, schema/unit/row-count/availability bounds와 content hash를 가진다. ExternalSinkResolver가 locator를 별도 process-local root로 해석하고 bytes를 다시 SHA-256 한 결과가 manifest와 같을 때만 ProcessedManifestVerification을 발행한다.

그 다음 ActualRunLineageBindingEvent가 reserved PlannedRunKey를 final CD, final protocol, RawCaptureManifest, ProcessingAuthorization, ProcessedManifest, ProcessingCodeBundleManifest, AnalysisCodeBundleManifest, executor identity, checkout instance, source tree와 environment hashes에 one-way 결박한다. processed manifest와 ActualRunLineageBindingEvent가 모두 anchored되기 전에는 reservation consume/start가 0이어야 한다. planned key는 수정하지 않는다.

- [ ] **read-only run-store/CLI reviewer verdict를 기록한다**

Expected: Task 6E source/test/registry hash가 exact match하고 named behavior assertions가 모두 통과하며 Task 10 source/test/CLI wiring Create/Modify와 ID allocation은 0, terminal failure disclosure는 100%, processed bytes rehash와 PlannedRunKey→ActualRunLineage→ExperimentRun bijection이 성립한다. 독립 run-store reviewer 승인 뒤에만 10B로 간다.

#### Task 10B: post-9B raw capture → processing → ActualRunLineage runtime

- [ ] **Task 9B RawCollectionAuthorization 이후에만 CLI raw pipeline을 연다**

Task 10B는 anchored D7, completed v2 registration과 Task 9B가 발행한 RawCollectionAuthorization을 entry prerequisite로 받는다. source search, SourceMetadataAcceptance, metadata capture, snapshot verification 또는 SourceAvailabilityClosure를 생성하는 subcommand를 소유하거나 다시 호출하지 않는다. 모든 명령은 exact protected manifest를 요구하고 CLI는 frozen processing callable을 orchestration할 뿐 결과 의미를 구현하지 않는다.

실제 순서는 정확히 다음과 같다.

~~~text
Task 9B anchored RawCollectionAuthorization
→ protected manifest and both frozen code-bundle receipt verification
→ authorized raw collection
→ RawCaptureManifest and locator rehash verification
→ ProcessingAuthorization
→ frozen ProcessingCodeBundleManifest callable execution
→ ProcessedManifest and locator rehash verification
→ ActualRunLineageBindingEvent and external receipt
~~~

ActualRunLineage receipt 전에는 AnalysisReadGuard, application/backend import, ExperimentRun reservation consume/start가 모두 0이다.

- [ ] **raw capture와 manifest verification을 실행한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --collect-authorized-raw --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-raw-capture-manifest --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

CollectionReadGuard는 RawCollectionAuthorization의 source/universe/period/field allowlist만 읽고 raw bytes를 external immutable content-addressed sink에 한 번 기록한다. verification은 locator를 resolver로 다시 읽어 bytes SHA-256, authorization, sink descriptor, received timestamp, sidecar와 receipt를 확인한다.

- [ ] **processing, processed verification과 actual lineage binding을 실행한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --process-authorized-raw --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-processed-manifest --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --bind-actual-run-lineage --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-source-manifest-registers \
  --raw-output research/rp-001/reports/raw-capture-manifest-register.json \
  --processed-output research/rp-001/reports/processed-manifest-register.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

ProcessingAuthorization은 RawCaptureManifest와 ProcessingCodeBundleManifest exact hashes를 봉인한다. ProcessedManifest verification은 processed locator bytes를 다시 해시하고 raw backreference, schema/unit/availability bounds, processing bundle, sidecar와 external receipt를 확인한다. ActualRunLineageBindingEvent는 reserved PlannedRunKey를 final CD/protocol, raw/processing/processed manifests, 두 code bundles, executor/checkout/source-tree/environment bindings에 one-way 결박한다.

source contract, frozen snapshot, RawCollectionAuthorization 또는 receipt가 달라지면 raw read와 write 전에 scoped canonical blocked disposition을 남긴다. 새 metadata가 필요하면 Task 10에서 갱신하지 않고 successor Task 7C2 plan set → 7D → 7E → D1–D7과 새 reservations를 다시 수행한다. closure로 blocked되거나 data_unavailable terminal인 affected study branch는 Task10B에 도달하지 않지만, accepted bindings를 가진 unaffected study branches는 계속 실행한다.

Task 10B reviewer는 protected pre/post manifest, raw/processed content rehash, external receipts, D1–D7 immutability와 order/account transport spy=0을 승인한다.

### Task 11: frozen validation/label/metric bundle read-only verification

Task 11은 결과 의미 코드를 소유하지 않는다. validation_design.py, interval_labels.py, research_metrics.py와 관련 tests는 Task 6E AnalysisCodeBundleManifest의 read-only content다.

**Files:**

- Read only and rehash: validation_design.py, interval_labels.py, research_metrics.py
- Read only and run: test_validation_design.py와 Task 6E의 synthetic fixtures
- Read only: AnalysisCodeBundleManifest, ontology-name-mapping, CD, final protocols
- Append only: validation-bundle-review-events와 external receipt
- Create source or test files: none

- [ ] **frozen bundle integrity와 계약을 재검증한다**

Task 6E에서 RED와 GREEN에 사용한 exact test command를 변경 없이 다시 실행하고 source file set, callable bindings, dependency/environment lock, ontology mapping과 manifest sidecar의 set-equality를 검사한다. 이 단계에서 새 RED를 주장하거나 test/implementation을 고치지 않는다. failure가 있으면 analysis를 blocked로 두고 successor AnalysisCodeBundleManifest→successor D1–D7→new reservations를 거친다.

재검증 대상 behavior는 purged walk-forward/embargo, event·issuer·interval cluster 분리, availability<=t, interval onset/end/phase label, identical control/candidate mask, training-only censoring/imbalance fit, fixed truncation, multiplicity universe, calibration, risk-coverage, cluster bootstrap/posterior seed, MCSE/ESS/convergence/precision, failed/invalid/abstain mass 보존이다.

Expected: frozen source/test bytes가 manifest와 같고 synthetic behavior test가 GREEN이며 file write count는 review event 이외 0이다. 독립 statistical reviewer 승인 전 empirical applications를 시작하지 않는다.

### Task 12: frozen BEH·VAL·MIC·EXE frontier execution and terminal publication

**Files:**

- Read only and rehash exact Task6E study/backend/terminal publisher sources and tests
- Read only: six pre-data artifacts and sidecars, both code bundles, SP-015 mapping, SP-016 dispositions and anchored DataLineageEligibilitySnapshot, optional ST-DAT terminal if already terminalized, multi-input StudyCandidateAdmission, D1–D7, RawCaptureManifest, ProcessedManifest, ActualRunLineageBindingEvent
- Create through Task10 repository: ST-BEH-001, ST-VAL-001, ST-MIC-001, ST-EXE-001 run events/artifacts
- Create through frozen Task6E publisher: terminal-decision-computations/{studySlot}/, study-terminal-events/{studySlot}/, sidecars, post-CAS anchor bindings and receipts
- Create or modify result-semantic source/test: none

six pre-data artifacts are completion-predicate-registry, gate-applicability-rules, requirement-obligation-definitions, study-terminal-decision-rules, required-deliverable-registry and predata-rule-freeze. Application/model import 전에 six artifacts, protected manifest, code bundles, ontology/DAT/admission, CD/SP, processed rehash and actual lineage를 검증한다. Every Task 12 command must already exist in the Task 6E closed dispatch registry; Task 12 CLI/registry/source/test Create/Modify count is zero.

BEH, VAL, MIC and EXE form one parallel frontier. BEH respects SP-015 name mapping; VAL requires PIT contracts; MIC requires ordered events; EXE requires order lifecycle/spread/depth/slippage/impact/fee/tax/FX/borrow/hedge inputs. Missing input is never zero-filled. A study already terminalized data_unavailable by Task7E consumes no ER; terminal publish command verifies the existing exact terminal and does not append a duplicate.

- [ ] **four frontier studies를 실행한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-BEH-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-VAL-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-MIC-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-EXE-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

completed, failed and invalid run events remain in each reserved cell ledger. backend unavailable remains candidate-specific blocked state. SourceImpactTerminalizer closure terminal has no fabricated run.

- [ ] **four frontier terminal computations/events를 publish and anchor한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-BEH-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-VAL-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-MIC-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-EXE-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Each command executes frozen TerminalDecisionComputation first, anchors it, then publishes an EB-free StudyTerminalEvent in a separate transaction and anchors it. exact run heads or closure inputs must match one frozen predicate for supported, refuted, insufficient_evidence, not_identifiable, data_unavailable or implementation_invalid. EvidenceBundle does not exist yet.

Expected: frontier execution precedes all four terminals; terminal exact-one and terminal anchor coverage are 1.00; failed/invalid/closure inputs are preserved. Independent study reviewers approve terminal receipts before RSK.

### Task 13: frozen RSK → terminal → SYN → terminal execution

**Files:**

- Read only and rehash exact Task6E risk, synthesis, comparison, terminal computation/publisher sources and tests
- Read only: four anchored frontier StudyTerminalEvents and all Task12 preflight inputs
- Create through Task10 repository: ST-RSK-001 and ST-SYN-001 run events/artifacts
- Create through frozen publisher: ST-RSK-001 and ST-SYN-001 computations/terminal events/sidecars/anchor bindings
- Create: research/rp-001/reports/trial-ledger-register.json, .sha256, research/rp-001/reports/experiment-run-register.json, .sha256
- Create or modify result-semantic source/test: none

Every Task 13 command must already exist in the Task 6E closed dispatch registry; Task 13 CLI/registry/source/test Create/Modify count is zero. A missing command is a bundle defect and cannot be wired at runtime.

Exact empirical DAG is:

~~~text
BEH ─┐
VAL ─┤
MIC ─┼→ four anchored frontier terminals → RSK → anchored RSK terminal → SYN → anchored SYN terminal
EXE ─┘
~~~

RSK cannot import/run until all four terminal anchor receipts verify. It computes correlation, drawdown, VaR, CVaR, stress and NoTrade utility. SYN cannot import/run until RSK terminal receipt verifies and uses only independent OOF outputs under the frozen correction family. RSK or SYN already terminalized `data_unavailable` by Task 7E consumes no ER: its execute command verifies the existing terminal and exits without a run, and its terminal publish command verifies the exact anchored terminal without appending a duplicate.

- [ ] **RSK를 실행하고 terminal을 publish한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-RSK-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-RSK-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

- [ ] **SYN을 실행하고 terminal을 publish한다**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --execute-study ST-SYN-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-study-terminal ST-SYN-001 --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-trial-bijection --design CD-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-run-ledger-registers \
  --trial-output research/rp-001/reports/trial-ledger-register.json \
  --run-output research/rp-001/reports/experiment-run-register.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Terminal publisher uses exact run/closure inputs and never references future EB. Candidate comparison preserves unavailable backends and all losing/failed candidates. EB-003 through EB-008 are built only in Task14B after all six empirical terminals are anchored.

Expected: frontier→four terminals→RSK→RSK terminal→SYN→SYN terminal topological order is exact; terminal count is six unique empirical slots, terminal anchor coverage and trial bijection are 1.00, source/test mutations are zero. Statistical/execution/risk reviewers approve before Task14.

### Task 14: terminal-referencing evidence, reproduction and final completion

Task14 code, generic CLI, closed dispatch registry and CLI tests are already frozen in Task6E AnalysisCodeBundleManifest. Task14 may invoke only registered commands and append runtime artifacts; it cannot modify source/tests/dispatch wiring or result meaning. Any command/code semantic change requires successor code bundles, D1–D7 and reservations.

**Read-only code/tests:** evidence_synthesis.py, reproduction_identity.py, reproduction_authorization.py, program_completion.py and their Task6E tests; all formula cells/certificate/dispositions; SourcePlanSet/dispositions/admissions; all eight anchored StudyTerminalEvents; run/source/receipt artifacts; six pre-data artifacts including RequiredDeliverableRegistry.

**Runtime ownership:**

- 14A reads and verifies SP-015/EB-010 and SP-016/EB-011; creates no protocol/terminal/EB.
- 14B creates EB-002 through EB-008 after terminal anchors and RD-013 through RD-020 tables/register.
- 14C creates persistent reproduction sink, RRA-001, RIA-001, reproduction outputs, RM-001, RA-001, IRA-001, G9 verification, RD-021 and EB-009 in that order.
- 14D creates DR-002, DR-003, SR-001, RD-001/RD-002/RD-025, completion observations and validation reports.
- EB-010/011 remain owned by Task6D/7D. Final EvidenceBundle IDs are exact EB-002 through EB-011.

#### Task 14A: read-only foundation verification

Task14A rehashes SP-015, ontology mapping, ST-ONT terminal, EB-010, SP-016, all DataLineageDispositions, ST-DAT terminal, EB-011, their exact registration/lifecycle/artifact-binding events, four current-v2 projections, post-CAS anchor-binding events and receipts. It reruns Task6D/7D behavioral tests and current-v2 validator without modifying artifacts. Terminal must precede EB in both chains. Duplicate build count is zero.

#### Task 14B: terminal-referencing EB-002 through EB-008 and required result tables

Frozen builder first verifies all six empirical terminal events and their anchor receipts. EB-003 through EB-008 reference exact terminal event bindings and terminal predecessor receipt hashes; no terminal references an EB. EB-002 references formula-specific 15-obligation cell artifacts, certificate and MathDispositionEvents. failed, invalid, abstain, insufficient_evidence, not_identifiable and data_unavailable are preserved.

- [ ] **build terminal-referencing EvidenceBundles**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-formula-evidence-bundle EB-002 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-terminal-evidence-bundles \
  --evidence-ids EB-003,EB-004,EB-005,EB-006,EB-007,EB-008 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Builder publishes body/sidecars, registration/lifecycle/artifact-binding events, target CAS receipts and post-CAS ArtifactExternalAnchorBindingEvents in order. It refuses an EB whose terminal anchor is absent or whose terminal was published later.

- [ ] **build exact Goal result tables**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-formula-distributions \
  --output research/rp-001/reports/formula-success-failure-distributions.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-performance-table \
  --output research/rp-001/reports/symbol-era-horizon-regime-performance.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-event-interval-table \
  --output research/rp-001/reports/event-intervals.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-phase-prediction-table \
  --output research/rp-001/reports/phase-predictions.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-detection-calibration-table \
  --output research/rp-001/reports/false-miss-lead-calibration.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-cost-sensitivity-table \
  --output research/rp-001/reports/cost-slippage-impact-sensitivity.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-risk-table \
  --output research/rp-001/reports/drawdown-var-cvar-stress.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-failure-evidence-register \
  --output research/rp-001/reports/failure-invalid-not-identifiable-evidence-register.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Each output has exact sidecar, v2 binding, traceability backreference and post-CAS anchor binding. Formula distributions include success/failure/invalid/abstain mass. Performance, event, prediction, detection, cost and risk tables bind every numeric row to run/terminal/EB artifacts.

#### Task 14C: rights-scoped persistent independent reproduction

ReproductionRightsAttestation, ReproductionInputAuthorization, ReproductionManifest, ReproductionAttestation and IndependentReviewerAttestation have no own receipt field. Each canonical body binds only already anchored predecessor hashes/receipts; its own receipt is attached later through ArtifactExternalAnchorBindingEvent. Original raw entitlement, resolver or credential is never inherited.

Exact canonical paths are `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-rights-attestation-events/RRA-001/000001.pending_unanchored.json`, `reproduction-input-authorization-events/RIA-001/000001.pending_unanchored.json`, `reproduction-manifest-events/RM-001/000001.pending_unanchored.json`, `reproduction-attestation-events/RA-001/000001.pending_unanchored.json` and `independent-reviewer-attestation-events/IRA-001/000001.pending_unanchored.json`, each with its own sidecar, target CAS receipt, post-CAS anchor-binding event and anchor-binding receipt. RRA-001 receipt is `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/reproduction-rights-attestations/RRA-001/000001.json` with sidecar.

The exact prerequisite sequence is sink descriptor → RRA-001 publish/anchor/verify → separate resolver/rights verification → RIA publish/anchor → RIA and processed rehash entitlement verification → reproduce with signed reproducer identity → ReproductionManifest publish/anchor → ReproductionAttestation publish/anchor → IndependentReviewerAttestation publish/anchor → G9 verify → RD-021 build/anchor → EB-009 publish/anchor.

- [ ] **publish and anchor persistent reproduction sink descriptor**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-reproduction-sink-descriptor \
  --sink-id RP001-REPRO-SINK-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

- [ ] **create, publish, anchor and verify RRA-001 before RIA**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-reproduction-rights-attestation \
  --attestation-id RRA-001 \
  --processed-manifest-register research/rp-001/reports/processed-manifest-register.json \
  --source-matrix research/rp-001/reports/source-matrix.current.json \
  --resolver-scope independent-reproduction-read-only \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-reproduction-rights-attestation \
  --rights-attestation-event research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-rights-attestation-events/RRA-001/000001.pending_unanchored.json \
  --rights-attestation-receipt research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/reproduction-rights-attestations/RRA-001/000001.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

The publisher derives processed-input reproduction/retention/derived-use/redistribution rights from the exact processed-manifest register and accepted source contracts, binds resolver scope/config hash plus approver and independent rights-reviewer bindings, then publishes sidecar→CAS→ArtifactExternalAnchorBindingEvent. The verifier rehashes the exact event, receipt and anchor binding. Validation-only without this producer is invalid.

- [ ] **verify separate resolver config against anchored RRA-001**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-reproduction-resolver-rights \
  --sink-id RP001-REPRO-SINK-001 \
  --rights-attestation-event research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-rights-attestation-events/RRA-001/000001.pending_unanchored.json \
  --rights-attestation-receipt research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/reproduction-rights-attestations/RRA-001/000001.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

This command proves reproduction resolver key/config differ from original, processed-input reproduction/retention rights are explicit, and rights/sink artifacts have anchor bindings. Absolute roots remain process-local.

- [ ] **publish, anchor and verify RIA before reproduction**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-reproduction-input-authorization \
  --authorization-id RIA-001 --sink-id RP001-REPRO-SINK-001 \
  --rights-attestation-event research/meta-research/objects/programs/RP-001-quantitative-market-behavior/reproduction-rights-attestation-events/RRA-001/000001.pending_unanchored.json \
  --rights-attestation-receipt research/meta-research/objects/programs/RP-001-quantitative-market-behavior/external-head-anchor-receipts/reproduction-rights-attestations/RRA-001/000001.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-reproduction-input-authorization \
  --authorization-id RIA-001 --rehash-processed-inputs \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

RIA canonical body records the exact RRA event path, event SHA-256 and predecessor receipt SHA-256. Verification resolves each processed locator with the separate resolver, checks entitlement and rehashes bytes before AnalysisReadGuard. Missing rights producer, path/hash mismatch, sink, resolver, processed hash or any anchor receipt fails before reproduction.

- [ ] **reproduce, then publish and anchor ReproductionManifest**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --reproduce --design CD-001 \
  --input-authorization RIA-001 --output-sink-id RP001-REPRO-SINK-001 \
  --reproducer-identity-binding EIB-REPRO-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-reproduction-manifest \
  --manifest-id RM-001 --input-authorization RIA-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

The reproduce command publishes and anchors signed EIB-REPRO-001 before reading inputs. RM-001 binds that identity, reproduced output locators/hashes, environment/source tree and predecessor RIA/output-sink receipts; RM-001 does not claim G9 and does not create RD-021.

- [ ] **after RM-001 anchor, publish RA-001 then third-identity IRA-001 and verify G9**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-reproduction-attestation \
  --attestation-id RA-001 --reproduction-manifest RM-001 \
  --original-executor-bindings-from research/rp-001/reports/experiment-run-register.json \
  --reproducer-identity-binding EIB-REPRO-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-independent-reviewer-attestation \
  --attestation-id IRA-001 --reproduction-attestation RA-001 \
  --reviewer-role-id G9-INDEPENDENT-REVIEWER-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-g9 \
  --reproduction-attestation RA-001 --reviewer-attestation IRA-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

RA-001 is signed by the reproducer and binds RM-001 anchor receipt plus the original/reproducer identity, session, checkout, source-tree, environment, output and tolerance comparison. IRA-001 is signed by a third reviewer identity only after RA-001 anchor and binds the RA-001 anchor receipt. The G9 verifier recomputes pairwise disjoint role/signing/session/checkout identities and both signatures/receipts; missing, unsigned, same-identity or unanchored input returns fail and keeps completion incomplete.

- [ ] **only after RA-001/IRA-001 receipts and G9 pass, build RD-021 then EB-009**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-independent-reproduction-report \
  --output research/rp-001/reports/independent-reproduction-report.json \
  --reproduction-manifest RM-001 --reproduction-attestation RA-001 \
  --reviewer-attestation IRA-001 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-evidence-bundle EB-009 \
  --reproduction-manifest RM-001 --reproduction-attestation RA-001 \
  --reviewer-attestation IRA-001 \
  --reproduction-report research/rp-001/reports/independent-reproduction-report.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Output is written only to the persistent content-addressed sink. Original executor, reproducer and reviewer identities/sessions/checkouts/keys are pairwise disjoint. RM-001, RA-001, IRA-001, RD-021 and EB-009 each get their own sidecar, CAS receipt and later anchor-binding event in topological order. RD-021 and EB-009 builders independently reverify both attestation receipts and G9; missing prerequisite or actual empirical run keeps G9 fail and completion incomplete and produces neither artifact.

#### Task 14D: DR-002 → DR-003 → SR-001 → observations → validation

DR-002 references current anchored MathDispositionEvents. DR-003 evaluates exact G0–G10 with non-compensation. Adopt/conditional_adopt requires all eleven pass, certificate=1.00 and no not_applicable. Failed G7/G8/G9/G10 means NoTrade.

- [ ] **build decisions and final human report in prerequisite order**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-decision-record DR-002 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --evaluate-gates-and-build-decision DR-003 \
  --formula-decision DR-002 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-synthesis-report SR-001 \
  --final-decision DR-003 \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

- [ ] **build traceability deliverables and completion observations after SR-001**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --build-traceability-deliverables \
  --requirement-trace research/rp-001/reports/requirement-trace-matrix.json \
  --rq-ledger research/rp-001/reports/research-question-ledger.json \
  --execution-environment research/rp-001/reports/execution-commands-environment.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --publish-completion-observations \
  --required-deliverable-registry research/meta-research/objects/programs/RP-001-quantitative-market-behavior/required-deliverable-registry.json \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

Completion recomputes RequiredDeliverableRegistry exact deliverable IDs, exact path set, file bytes hashes, sidecars, v2 registrations, artifact bindings, traceability/backreferences, post-CAS anchor-binding events and required cardinality. It does not trust a generic boolean. Missing artifact/path/hash/owner/cardinality/sidecar/anchor/v2/trace mutation tests must fail.

- [ ] **validate completion, artifact hygiene and protected paths**

~~~bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --validate-program-completion \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --validate-artifact-hygiene \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_evidence_engine.py --verify-protected-paths \
  --protected-manifest research/rp-001/contracts/protected-path-manifest.json
~~~

ProgramCompletionValidator also recomputes requirement/semantic coverage, formula cell certificate, RB alias separation, SourcePlan planned↔executed disclosure bijection across all three outcomes, eligible/exhausted/blocked counts, multi-input scoped admission, eight terminal exact-one and terminal→EB order, D1–D7/raw/process/lineage/run bijection, repeated-cell precision, success/failure distributions, G9, external anchor bindings and secret/order/account findings. Closure/exhaustion coverage uses only the `exhausted_unavailable` denominator and never counts `nonterminal_blocked`. Complete requires blocked count=0, anchored ST-DAT terminal and EB-011, all eight terminal slots closed, all frozen predicates and RequiredDeliverableRegistry coverage 1.00, accepted empirical runs for eligible studies, G9 pass and zero security findings. `test_program_completion_fails_when_blocked_count_is_positive` is mandatory. Otherwise exact unmet obligations and incomplete are emitted. no_adoptable_formula/not_identifiable remains a valid completed research conclusion only when these contracts pass.

Adversarial reviewers evaluate both “adopt is wrong” and “reject is wrong” from the same artifacts. Task14 source/test mutation is zero.

## Execution handoff

이 계획은 Task 0부터, 그리고 implementation units 1A/1B/1C·6B/6C/6D/6E·8A/9A/8B/9B를 strict behavioral RED→동일 명령 GREEN→독립 review 순서로 실행한다. Task 6E가 all Task 7 command-meaning services/tests, ExperimentRunRepository, generic CLI and closed 49-command dispatch registry를 provider access 전에 구현·동결한다. 실행 chronology는 정확히 `6E → 7A/B/C read-only preflight/runtime → 7C2 all-plan three-state outcomes → 7D SP-016 scoped snapshot/RD-004/RD-005/optional terminal → 7E scoped StudyCandidateAdmission/source-impact terminalization → 8A → 9A → 8B → 9B → 10 raw/process/lineage → 11–14`다. Tasks 7A/B/C/C2/D/E, Task 10A and Tasks 11–14는 Task 6E에서 이미 RED/GREEN으로 동결된 source/reader/data-lineage/admission/run-store/CLI/result-semantic code/tests를 read-only로 재해시·실행하고 새 implementation RED, code/test Create/Modify or wiring을 주장하지 않는다. Task 0–6은 source·credential·market data 없이 즉시 수행할 수 있다. Task 7 runtime이 nonterminal blocked여도 SG3 FormulaAudit와 독립 synthetic work는 계속한다. 실제 시장자료 경로는 `7C2 anchored SourcePlanSetManifest/all plans → governed per-plan search → per-plan eligible_metadata | exhausted_unavailable | nonterminal_blocked outcome → SP-016 anchored scoped DataLineageDisposition + DataLineageEligibilitySnapshot → RD-004/RD-005 → per-formula multi-input StudyCandidateAdmission → unaffected-only D1 DesignCore → D2 SuccessorProtocolCore → D3 PlannedRunKey grid → D4 six-digit ReservationManifest → D5 final CD → D6 final protocols → D7 ReservationLineageBindingEvent/receipt → v2 registration → branch-scoped RawCollectionAuthorization → CollectionReadGuard → RawCaptureManifest → ProcessingAuthorization → ProcessedManifest/receipt → ActualRunLineageBindingEvent → AnalysisReadGuard → ExperimentRun`이다. Affected blocked inputs remain blocked; all-required valid closures may terminalize only the affected study as data_unavailable; unrelated eligible branches continue. Final program completion separately requires blocked count=0, anchored ST-DAT terminal/EB-011 and every other frozen completion predicate.

실제 구현의 첫 명령은 Task 0 Step 1 RED다. test와 최소 importable counterexample가 정상 discovery된 뒤 named behavioral assertion failure를 확인한다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protected_path_guard.py \
                  research/rp-001/tests/test_artifact_hygiene.py -v
```

Expected RED: `test_manifest_sidecar_mismatch_is_rejected`, `test_symlink_cannot_escape_allowed_roots`, `test_sensitive_scalar_is_rejected`의 assertion failure다. import/discovery/syntax/file-existence failure는 RED가 아니다. 그 뒤 구현과 capture를 수행하고 아래의 같은 exact unittest command를 GREEN으로 다시 실행한다.

```bash
PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/capture_protected_paths.py \
  --repository-root . \
  --manifest research/rp-001/contracts/protected-path-manifest.json \
  --sidecar research/rp-001/contracts/protected-path-manifest.sha256 \
  --capture

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_protected_path_guard.py \
                  research/rp-001/tests/test_artifact_hygiene.py -v
```

Task 0 GREEN과 review 뒤 Task 1A RED를 실행한다.

```bash

PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_evidence_contracts.py \
                  research/rp-001/tests/test_audit_execution.py \
                  research/rp-001/tests/test_research_graph.py -v
```

`run_evidence_engine.py`, `evidence_cli_contract.py`, dispatch registry와 CLI tests는 Task 6E에서 처음 생성·RED→GREEN·AnalysisCodeBundleManifest에 동결되고 exact `--protected-manifest research/rp-001/contracts/protected-path-manifest.json`을 49개 모든 subcommand의 필수 인자로 받는다. 누락·다른 path·hash mismatch는 provider/application import와 write 전에 exit 2다. Task 0–7C는 CLI를 runtime 호출하지 않고 Task 7C2가 첫 actual invocation을 수행한다. Task 7C2 이후에는 shell/registry/test를 생성·수정·확장하지 않으며 registry와 실제 invoked subcommand set이 달라지면 successor bundle→D1–D7→new reservations 없이는 실행할 수 없다.

그 뒤 Checkpoint A→B→C→D→E를 순서대로 통과한다. external anchor authority가 없으면 local pending 작업은 계속하되 해당 checkpoint/G9/completion은 blocked다. source나 권한이 해결되지 않은 study는 blocked 상태를 보존하고 독립 작업을 계속한다. 실제 부재를 terminalize하려면 valid `SourceAvailabilityClosure`와 frozen terminal rule의 exact-one 판정이 필요하다. 공식 후보가 하나도 남지 않더라도 protected path 불변, 254개 requirement semantic predicate/target cardinality/양방향 추적, `formulaRegistryIds` 전체 applicable-audit matrix 1.00, RB alias/config matrix 20/20과 alias/formula 교집합 0, Question·Identifiability·Baseline·Falsification·Temporal·TrialDisclosure·ClaimTrace coverage와 actual source-chain 재해시가 모두 1.00이고, external receipt coverage가 1.00이며, 8개 study가 frozen total-function으로 모두 terminal이고 blocked가 0이며, actual accepted market-data run이 존재하고 planned-cell execution coverage와 MCSE/ESS/convergence/precision predicate가 1.00이고, 각 uncertainty distribution이 해당 terminal run ID 전부를 역참조하고, signed disjoint-identity G9 재현과 필수 deliverable exact path/hash가 모두 존재할 때만 `no_adoptable_formula` 또는 `not_identifiable` DecisionRecord로 종료한다. historical 224는 provenance submetric으로만 보고한다. 그 전에는 program status를 `incomplete`로 유지한다.
