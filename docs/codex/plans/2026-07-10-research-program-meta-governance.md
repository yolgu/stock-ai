# Research Program Meta-Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 v1.4 연구를 변경하지 않고, 타입이 있는 연구객체·계측 가능한 품질규칙·독립 연구 프로그램을 관리하는 `research/meta-research` 체계를 구축한다.

**Architecture:** 파일 시스템의 각 객체 폴더를 aggregate root로 보고 `object.json`을 객체의 단일 정의로 사용한다. 중앙 catalog는 ID와 descriptor 경로만 보유하며, Python 표준 라이브러리 검증기가 ID·타입·상태·artifact·의존성·순환을 검사한다.

**Tech Stack:** Markdown, JSON Schema 2020-12, Python 3 표준 라이브러리 `unittest`, Git 상대경로

---

### Task 1: 연구객체 검증기 RED/GREEN

**Files:**
- Create: `research/meta-research/tools/test_validate_research_program.py`
- Create: `research/meta-research/tools/validate_research_program.py`

- [x] **Step 1: 정상 fixture와 중복 ID·누락 의존성·순환 의존성 실패검사를 먼저 작성한다**

테스트는 임시 저장소에 `governance`, `catalog`, `objects`, `templates`, `archive`, `tools`와 두 descriptor를 만들고 `ResearchProgramValidator.validate()`의 `object_count`, `dependency_count`를 검증한다. 변형 fixture에서는 `ResearchProgramValidationError`의 메시지에 각각 `duplicate object id`, `unknown dependency`, `dependency cycle`이 포함돼야 한다.

- [x] **Step 2: RED를 확인한다**

Run: `python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v`

Expected: `ModuleNotFoundError: No module named 'validate_research_program'`

- [x] **Step 3: 최소 검증기를 구현한다**

`ValidationReport`는 불변 dataclass로 `object_count`, `dependency_count`, `artifact_count`를 가진다. `ResearchProgramValidator`는 필수 디렉터리, catalog 정렬, descriptor 필수 필드·enum, 저장소 내부 artifact 경로, 전역 고유 ID, 미등록 의존성, DFS 순환을 검증한다. 모든 공개 메서드에는 명시적 반환형을 둔다.

- [x] **Step 4: GREEN을 확인한다**

Run: `python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v`

Expected: 모든 fixture 테스트 `OK`

### Task 2: 실제 구조검사 RED와 객체 계약

**Files:**
- Modify: `research/meta-research/tools/test_validate_research_program.py`
- Create: `research/meta-research/catalog/research-object.schema.json`
- Create: `research/meta-research/catalog/research-objects.json`
- Create: `research/meta-research/objects/baselines/RB-001-v1-4-indicator-validation/object.json`
- Create: `research/meta-research/objects/meta-studies/MS-001-research-program-governance/object.json`
- Create: `research/meta-research/objects/model-candidates/MC-001-bayesian-hsmm-competing-risks/object.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/object.json`

- [x] **Step 1: 실제 저장소 구조를 검증하는 테스트를 추가한다**

테스트는 저장소 root와 `research/meta-research`를 넘겨 검증한 뒤 `object_count == 4`, `dependency_count == 4`, `artifact_count >= 10`을 요구한다.

- [x] **Step 2: RED를 확인한다**

Run: `python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v`

Expected: 실제 `catalog/research-objects.json` 부재로 FAIL

- [x] **Step 3: schema·catalog·네 객체 descriptor를 작성한다**

공통 필드는 `schemaVersion`, `id`, `type`, `title`, `version`, `lifecycleState`, `evidenceLevel`, `purpose`, `dependsOn`, `artifacts`다. catalog는 `MC-001`, `MS-001`, `RB-001`, `RP-001` 순으로 정렬하며 descriptor 경로만 저장한다. 기존 v1.4와 HSMM 문서는 artifact로 참조만 한다.

### Task 3: 메타-메타연구와 거버넌스 자료

**Files:**
- Create: `research/meta-research/README.md`
- Create: `research/meta-research/governance/document-management-policy.md`
- Create: `research/meta-research/governance/lifecycle-and-evidence-gates.md`
- Create: `research/meta-research/governance/measurement-and-quality-model.md`
- Create: `research/meta-research/governance/research-object-model.md`
- Create: `research/meta-research/governance/source-register.md`
- Create: `research/meta-research/objects/meta-studies/MS-001-research-program-governance/protocol.md`
- Create: `research/meta-research/objects/meta-studies/MS-001-research-program-governance/report.md`
- Create: `research/meta-research/objects/meta-studies/MS-001-research-program-governance/evidence-matrix.md`

- [x] **Step 1: 메타연구 protocol을 작성한다**

질문, 범위, 후보 세 구조, 평가기준과 가중치, 출처 포함·제외 기준, 한계, 사전 결정 규칙을 명시한다. 이번 조사를 체계적 문헌고찰로 과장하지 않는다.

- [x] **Step 2: 비교 보고서와 근거행렬을 작성한다**

평면 문서, 완전 시맨틱 패키지, 타입이 있는 파일 우선 객체를 7개 기준으로 1~5점 평가하고 가중합 `2.80`, `4.00`, `4.15`를 재현한다. FAIR, RO-Crate, W3C PROV-O, OSF, PRISMA-ScR, ACM Artifact Review의 적용 결정과 비적용 범위를 기록한다.

- [x] **Step 3: 객체모델·수명주기·문서정책·품질지표를 작성한다**

DDD bounded context, aggregate, SSOT, composition, ID·버전·동결·정정 규칙, evidence level, Gate, catalog coverage와 dangling reference 등 정량 품질지표를 명시한다.

### Task 4: 첫 연구 프로그램과 템플릿

**Files:**
- Create: `research/meta-research/objects/baselines/RB-001-v1-4-indicator-validation/README.md`
- Create: `research/meta-research/objects/model-candidates/MC-001-bayesian-hsmm-competing-risks/README.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/README.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/question-map.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-portfolio.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/integration-contract.md`
- Create: `research/meta-research/templates/data-contract.md`
- Create: `research/meta-research/templates/decision-record.md`
- Create: `research/meta-research/templates/evidence-bundle.md`
- Create: `research/meta-research/templates/research-question.md`
- Create: `research/meta-research/templates/study-protocol.md`
- Create: `research/meta-research/archive/README.md`

- [x] **Step 1: 기존 연구 wrapper와 새 프로그램을 작성한다**

v1.4는 불변 기준선, HSMM은 미검증 후보임을 명시한다. 새 프로그램은 행동·상대가치·미시구조·체결비용·위험 연구를 독립 study로 정의하고, 이미 본 데이터는 discovery 전용으로 제한한다.

- [x] **Step 2: 연구객체 템플릿을 작성한다**

각 템플릿은 ID, 상태, 질문 또는 주장, estimand, 관측단위, 가용시점, 기준선, 반증, 중단조건, evidence, 결정근거 중 해당 필드를 명시한다. 실제 값 대신 각괄호 토큰을 사용해 템플릿임을 분명히 한다.

- [x] **Step 3: 실제 구조 GREEN을 확인한다**

Run: `python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v`

Expected: 모든 테스트 `OK`

### Task 5: 전체 검증과 변경범위 확인

**Files:**
- Verify only: `research/meta-research/**`
- Verify only: `docs/codex/specs/2026-07-10-research-program-meta-governance-design.md`
- Verify only: `docs/codex/plans/2026-07-10-research-program-meta-governance.md`

- [x] **Step 1: 구조검증기를 직접 실행한다**

Run: `python3 research/meta-research/tools/validate_research_program.py --repository-root . --program-root research/meta-research`

Expected: `objects=4 dependencies=4 artifacts>=10`

- [x] **Step 2: 문서 품질과 비밀정보를 검사한다**

Run: `rg -n "TO[D]O|TB[D]|tsc[k]_live_|tss[k]_live_" research/meta-research docs/codex/specs/2026-07-10-research-program-meta-governance-design.md docs/codex/plans/2026-07-10-research-program-meta-governance.md`

Expected: exit 1, 출력 없음

- [x] **Step 3: 기존 연구 변경이 없음을 확인한다**

Run: `git status --short research/indicator-validation docs/codex/research research/meta-research docs/codex/specs/2026-07-10-research-program-meta-governance-design.md docs/codex/plans/2026-07-10-research-program-meta-governance.md`

Expected: 기존 경로는 이전 상태 그대로이고 새 메타연구 경로와 두 설계·계획 문서만 이번 작업 범위로 추가됨
