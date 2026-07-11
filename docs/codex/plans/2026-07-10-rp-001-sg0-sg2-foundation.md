# RP-001 SG0–SG2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GOAL-RP-001 v1.0을 저장소 안의 불변 요구사항·추적·질문·자료계약·사전등록 객체로 전환하고, RB-001 변이를 숨기지 않는 검증 가능한 SG0–SG2 기반을 만든다.

**Architecture:** 기존 `research/meta-research` 객체모델을 유지하면서 `ST-*` slot을 `RQ/DC/SP` 객체 사슬에 매핑한다. 프로그램 수준 ledger는 `research/rp-001` 검증기가 읽고, catalog 구조검증기는 schema를 SSOT로 사용하며 새 객체 수를 하드코딩하지 않는다. RB-001은 수정하지 않고 관찰된 전후 hash를 새 EvidenceBundle과 DecisionRecord로 기록한다.

**Tech Stack:** Markdown, canonical JSON, Python 3.12 표준 라이브러리, `unittest`, SHA-256, 기존 meta-research catalog

---

### Task 1: Meta-research validator 확장성 RED/GREEN

**Files:**
- Modify: `research/meta-research/tools/test_validate_research_program.py`
- Modify: `research/meta-research/tools/validate_research_program.py`
- Test: `research/meta-research/tools/test_validate_research_program.py`

- [x] **Step 1: schema drift와 객체 수 하드코딩을 드러내는 실패검사를 작성한다**

`ResearchProgramValidatorTest`에 schema의 `type.enum`에서 `MetaStudy`를 제거한 fixture를 만들고 `MetaStudy` descriptor가 거부되는지 검사한다. 저장소 구조 테스트는 정확한 객체 수 대신 필수 ID 집합과 `catalog_coverage == 1.0`을 검사한다.

```python
def test_descriptor_validation_uses_catalog_schema_enums(self) -> None:
    schema_path = self.program_root / "catalog" / "research-object.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["type"]["enum"] = ["ResearchBaseline"]
    self._write_json(schema_path, schema)
    meta_study = self._create_object("MS-001", "MetaStudy")
    self._write_catalog([meta_study])

    with self.assertRaisesRegex(
        ResearchProgramValidationError,
        "invalid object type: MS-001",
    ):
        self._validator().validate()
```

저장소 검사는 다음 형태로 바꾼다.

```python
self.assertTrue({"MC-001", "MS-001", "RB-001", "RP-001"}.issubset(report.object_ids))
self.assertEqual(report.catalog_coverage, 1.0)
```

- [x] **Step 2: RED를 확인한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/meta-research/tools/test_validate_research_program.py -v
```

Expected: schema enum을 코드 상수가 무시하거나 `ValidationReport.object_ids`가 없어 FAIL.

- [x] **Step 3: schema를 validator의 enum·pattern·required SSOT로 사용한다**

`ResearchObjectSchema` 불변 dataclass를 추가하고 schema JSON의 `required`, `properties.id.pattern`, `properties.version.pattern`, `properties.type.enum`, `properties.lifecycleState.enum`, `properties.evidenceLevel.enum`을 읽는다. `ValidationReport`에는 정렬된 `object_ids: tuple[str, ...]`를 추가한다. `_VALID_*`, `_REQUIRED_DESCRIPTOR_FIELDS`, 고정 regex는 제거하고 schema 객체를 사용한다.

```python
@dataclass(frozen=True)
class ResearchObjectSchema:
    required_fields: frozenset[str]
    identifier_pattern: re.Pattern[str]
    version_pattern: re.Pattern[str]
    valid_types: frozenset[str]
    valid_lifecycle_states: frozenset[str]
    valid_evidence_levels: frozenset[str]


@dataclass(frozen=True)
class ValidationReport:
    object_ids: tuple[str, ...]
    object_count: int
    dependency_count: int
    artifact_count: int
    catalog_coverage: float
```

- [x] **Step 4: GREEN을 확인한다**

Run: Task 1 Step 2와 동일.

Expected: 모든 meta-research validator 테스트 `OK`.

### Task 2: RP-001 프로그램 계약 validator RED/GREEN

**Files:**
- Create: `research/rp-001/src/rp001/__init__.py`
- Create: `research/rp-001/src/rp001/program_contract.py`
- Create: `research/rp-001/tests/test_program_contract.py`
- Create: `research/rp-001/run_program.py`
- Create: `research/rp-001/README.md`
- Create: `research/rp-001/requirements.lock.txt`

- [x] **Step 1: 요구사항·study·candidate 계약 실패검사를 작성한다**

임시 fixture는 다음 네 canonical JSON을 가진다.

```text
program/requirements.json
program/traceability.json
program/study-registry.json
program/candidate-registry.json
```

테스트는 정상 fixture와 다음 실패를 검증한다.

```python
class ProgramContractTest(unittest.TestCase):
    def test_accepts_complete_registered_foundation(self) -> None:
        report = self._validator().validate_foundation()
        self.assertEqual(report.source_requirement_coverage, 1.0)
        self.assertEqual(report.study_slot_coverage, 1.0)
        self.assertEqual(report.candidate_family_coverage, 1.0)

    def test_rejects_duplicate_requirement_id(self) -> None:
        self._duplicate_requirement("REQ-001")
        with self.assertRaisesRegex(ProgramContractError, "duplicate requirement id"):
            self._validator().validate_foundation()

    def test_rejects_missing_study_contract_chain(self) -> None:
        self._remove_study_contract("ST-MIC-001", "datasetContractId")
        with self.assertRaisesRegex(ProgramContractError, "incomplete study contract"):
            self._validator().validate_foundation()

    def test_rejects_unregistered_required_candidate_family(self) -> None:
        self._remove_candidate_family("nonlinear")
        with self.assertRaisesRegex(ProgramContractError, "missing candidate family"):
            self._validator().validate_foundation()
```

- [x] **Step 2: RED를 확인한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest discover -s research/rp-001/tests -p 'test_*.py' -v
```

Expected: `ModuleNotFoundError: No module named 'rp001'`.

- [x] **Step 3: 최소 프로그램 계약 validator를 구현한다**

공개 계약은 다음과 같다.

```python
@dataclass(frozen=True)
class FoundationValidationReport:
    requirement_count: int
    source_requirement_coverage: float
    study_slot_coverage: float
    candidate_family_coverage: float


class ProgramContractValidator:
    REQUIRED_STUDY_SLOTS = (
        "ST-ONT-001",
        "ST-DAT-001",
        "ST-BEH-001",
        "ST-VAL-001",
        "ST-MIC-001",
        "ST-EXE-001",
        "ST-RSK-001",
        "ST-SYN-001",
    )
    REQUIRED_CANDIDATE_FAMILIES = (
        "unconditional",
        "simple_price_volume",
        "legacy_weighted_sum",
        "repair_candidate",
        "bayesian_competing_risk",
        "hmm_hsmm",
        "dynamic_relative_value",
        "prospect_reference_price",
        "ofi_depth_hawkes",
        "execution_control",
        "nonlinear",
    )
```

공개 메서드 `validate_foundation() -> FoundationValidationReport`는 네 원장을 strict JSON으로 읽어 중복·형식·누락 참조를 검증한 뒤 위 report를 반환한다. 모든 JSON은 duplicate key를 거부하고, `REQ-[0-9]{3}`, `ST-[A-Z]{3}-[0-9]{3}`, catalog object ID 형식을 검사한다. `run_program.py --verify-foundation`은 report를 canonical JSON으로 출력하고 실패 시 exit 1을 반환한다.

- [x] **Step 4: GREEN을 확인한다**

Run: Task 2 Step 2와 동일.

Expected: 모든 RP-001 program contract 테스트 `OK`.

### Task 3: GOAL 원문·요구사항·추적 원장 동결

**Files:**
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/goal-v1.0.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirements.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/traceability.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/candidate-registry.json`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/seen-data-register.json`
- Modify: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/object.json`

- [x] **Step 1: 외부 Goal 원문과 저장소 canonical copy의 무결성을 보존한다**

active 원본은 `/Users/jik/.codex/attachments/a2f9a4f6-4da6-458c-a12a-98f2c5b2df37/goal-objective.md`이며 다음 값이 유지돼야 한다.

```text
newline_count=391
logical_lines=392
bytes=13876
sha256=089ee3236ad913388106d0b569cc931e451d6be661c55ee62c2993f093afaad3
```

이전에 active였던 `/Users/jik/.codex/attachments/6023f4bd-b626-4150-9e9a-ae7668667509/goal-objective.md`는 superseded provenance로 보존한다. 이전 원본은 newline 391개, logical line 392개, 13,875바이트이고 SHA-256은 `ed12fa8ca34644e95b2591b1ac1e0e310420eb0092866454289b011453089e3a`다.

기존 `goal-v1.0.md`는 변경하지 않는다. canonical copy는 newline 392개, logical line 392개, 13,876바이트이고 SHA-256은 `542160cbad66426db09eb8ec6741c48464a9d80a3a6be2fd71ab1871f8f55594`다. 새 active 원본과 canonical copy의 byte-level 차이는 두 가지뿐이다. active 원본의 whitespace-only 41행에 있는 ASCII 공백 한 칸은 canonical copy에서 빈 행으로 정규화되어 있고, active 원본에는 없는 final LF가 canonical copy에 있다. 규범 내용과 392개 논리 행의 line mapping은 동일하다. `requirements.json.sourceSha256`은 새 active 원본의 SHA-256을 유지한다.

- [x] **Step 2: 원자 요구사항에 고유 ID를 부여한다**

`requirements.json`은 다음 계약을 사용한다.

```json
{
  "schemaVersion": "rp001-requirements.v1",
  "goalId": "GOAL-RP-001",
  "goalVersion": "1.0",
  "sourceSha256": "089ee3236ad913388106d0b569cc931e451d6be661c55ee62c2993f093afaad3",
  "requirements": [
    {
      "id": "REQ-001",
      "sourceSection": "1",
      "sourceLines": [6, 7],
      "category": "role",
      "text": "정량금융 연구책임자·수학 검증자·시장미시구조 연구자·행동경제학 연구자·재현성 감사자의 책임을 함께 수행한다."
    }
  ]
}
```

역할, SSOT, 궁극 목표, 성공조건, SG0~SG5, 표본, 사건구간, 검증, G0~G10, 목적함수, 모든 필수 산출물, 보안, 검토 순서, 종료조건, 최종 응답 항목을 각각 최소 판정단위로 분리한다. ID는 source line 순서와 일치해야 하고 빈 줄을 제외한 모든 규범 문장을 적어도 한 requirement가 덮어야 한다.

- [x] **Step 3: 추적·study·candidate·seen-data 원장을 작성한다**

초기 `traceability.json`의 각 행은 `questionIds`, `studySlots`, `evidenceIds`, `decisionIds`, `reportPaths`를 갖는다. SG0에서는 evidence·decision·report가 비어 있어도 되지만 요구사항에서 질문·study로의 등록 추적은 완전해야 한다.

`study-registry.json`은 설계 문서의 고정 매핑 `ST-ONT-001→RQ-001/DC-001/SP-001`부터 `ST-SYN-001→RQ-008/DC-008/SP-008`까지 정확히 8개를 가진다. 각 slot의 `trialLedgerPath`는 `research/rp-001/trials/ST-ONT-001.json`과 같은 실제 slot ID 경로다.

`candidate-registry.json`은 Task 2의 11개 필수 family를 모두 등록하고 `MC-001`만 `objectId`를 가지며, 나머지는 `registry_only` 상태로 시작한다.

`seen-data-register.json`은 TSLA·NVDA 360거래일, MU·000660 120거래일 및 4개월 부분집합을 `seen_development_data`로 표시하고 `confirmatoryAllowed=false`를 고정한다.

- [x] **Step 4: foundation validator로 원장을 검증한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_program.py --verify-foundation
```

Expected: `sourceRequirementCoverage=1.00`, `studySlotCoverage=1.00`, `candidateFamilyCoverage=1.00`.

### Task 4: RB-001 동결 변이 EvidenceBundle과 경계 결정

**Files:**
- Create: `research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit/object.json`
- Create: `research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit/evidence.md`
- Create: `research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit/integrity-observations.json`
- Create: `research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit/current-input-bindings.json`
- Create: `research/meta-research/objects/decision-records/DR-001-rb001-boundary/object.json`
- Create: `research/meta-research/objects/decision-records/DR-001-rb001-boundary/decision.md`
- Create: `research/meta-research/objects/decision-records/DR-001-rb001-boundary/boundary-contract.json`
- Create: `research/rp-001/src/rp001/sensitive_value_policy.py`
- Create: `research/rp-001/tests/test_rb001_boundary.py`
- Create: `research/rp-001/tests/test_sensitive_value_policy.py`
- Modify: `research/meta-research/catalog/research-objects.json`

- [x] **Step 1: 최초 관찰과 변경 후 상태를 append-only 증거로 기록한다**

`integrity-observations.json`에는 최초 불일치, 첫 재결박, 이후 결정적 재실행으로
바뀐 현재 snapshot의 세 관찰을 모두 포함한다. 세 번째 상태가 추가되었으므로
이전 두 관찰을 덮어쓰지 않고 append-only로 보존한다.

```json
{
  "schemaVersion": "rb001-integrity-observations.v1",
  "baselineId": "RB-001",
  "observations": [
    {
      "phase": "initial_audit",
      "runManifestSha256": "09e2ddf1e9acb3dbf54336ea5265a737ebba4a702dce61cdd194f4827a260eda",
      "manifestPayloadSha256": "6874c351cd5efe3f061c05af134ae569c0d0227e225340dd0f85d52b27e59356",
      "boundRunnerSha256": "1e6d5d4053f61fdb4d3af17848658c8a0942880774c8c7f33d7e5f6f0bd12d2a",
      "boundRunnerSizeBytes": 42115,
      "verifyStatus": "failed_input_hash_mismatch"
    },
    {
      "phase": "first_rebind_observed",
      "runManifestSha256": "90e6e3ac59bf408b609fc5a5422a763a090e47c5578f9b0419a957814b93415f",
      "manifestPayloadSha256": "3b4957020bdea2f060eab7e8f2cd784c5a0acc98ef6d57cd83fe3916a5bb0ae2",
      "boundRunnerSha256": "b625d724d8363b2d5d74a25b698e7911787d01dfcb5b7b5c41c392b3a748851b",
      "boundRunnerSizeBytes": 50585,
      "verifyStatus": "self_consistent_after_rebind"
    },
    {
      "phase": "later_deterministic_rerun_observed",
      "runManifestSha256": "b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e",
      "manifestPayloadSha256": "b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f",
      "boundRunnerSha256": "f906fd61b9b55e2e264adae032517151f9ee7ed24b8804ab878e102944736708",
      "boundRunnerSizeBytes": 52600,
      "verifyStatus": "current_snapshot_self_consistent"
    }
  ],
  "generationLineageVerified": false
}
```

최초 관찰의 결과 8개 mtime `2026-07-10T07:56:52+09:00`, runner mtime
`08:02:27`, 첫 재결박 manifest mtime `08:09:33`, 당시 보고서·검증로그 mtime
`08:09:56`을 기록한다. 현재 snapshot에는 runner mtime `08:12:21`, 결과 8개와
manifest mtime `08:16:31`, 최종보고서 mtime `08:16:58`, 검증로그 mtime
`08:17:10`을 별도 기록한다. 현재 manifest와 runner의 byte/hash 일치는
read-only로 재계산하되, 세 상태 사이의 실행 주체·명령 계보는 독립적으로
입증되지 않았으므로 `generationLineageVerified=false`를 유지한다.

- [x] **Step 2: RB-001 사용범위를 DecisionRecord로 제한한다**

DR-001은 `research_only`로 판정하고 RB-001을 failure reproduction·금지조건·seen-data 식별에만 허용한다. 성능·독립재현·frozen provenance 근거로는 사용하지 않는다. RB-001 원본은 수정하지 않는다.

- [x] **Step 3: descriptor와 catalog 구조를 검증한다**

EB-001은 `dependsOn=["RB-001"]`, DR-001은 `dependsOn=["EB-001", "RB-001"]`로
catalog에 즉시 등록한다. 미등록 descriptor가 생긴 채 Task 8까지 방치하지 않고 ID 순서를
유지하며, Task 8은 이후 객체를 포함한 최종 통합을 담당한다. artifact는 해당 aggregate
내부 파일만 선언한다.

### Task 5: ST-ONT-001 온톨로지 객체와 명칭허용 규칙

**Files:**
- Create: `research/meta-research/objects/research-questions/RQ-001-market-state-identifiability/object.json`
- Create: `research/meta-research/objects/research-questions/RQ-001-market-state-identifiability/question.md`
- Create: `research/meta-research/objects/dataset-contracts/DC-001-ontology-evidence/object.json`
- Create: `research/meta-research/objects/dataset-contracts/DC-001-ontology-evidence/data-contract.md`
- Create: `research/meta-research/objects/dataset-contracts/DC-001-ontology-evidence/source-register.json`
- Create: `research/meta-research/objects/study-protocols/SP-001-market-state-ontology/object.json`
- Create: `research/meta-research/objects/study-protocols/SP-001-market-state-ontology/protocol.md`
- Create: `research/meta-research/objects/study-protocols/SP-001-market-state-ontology/protocol.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/state-ontology.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/state-ontology.json`
- Create: `research/rp-001/trials/ST-ONT-001.json`
- Create: `research/rp-001/tests/test_ontology_contract.py`
- Modify: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/object.json`
- Modify: `research/meta-research/catalog/research-objects.json`

- [x] **Step 1: 질문을 단일 식별 estimand로 고정한다**

RQ-001의 질문은 다음으로 고정한다.

> 사전 지정된 각 상태명에 대해, 시점 t까지 가용한 관측과 외부 측정치가 가격·거래량 국면, 잠재상태, 인간 심리, 거래결정을 서로 구별할 충분한 관측가능성과 판별타당도를 제공하는가?

주요 estimand는 상태명별 `identifiable / proxy_only / not_identifiable` 판정이다. OHLCV만 있는 경우 심리명칭은 자동으로 `not_identifiable`이고 `price_volume_regime`만 허용한다.

- [x] **Step 2: 자료계약과 프로토콜을 작성한다**

DC-001은 이론 원문·공식 사양·저장소 artifact를 source unit으로 하고 제목, 발행주체, URL, 접근일, 적용 주장, 비적용 범위를 필수 필드로 둔다. SP-001은 상태별 관측가능성 행렬, 동일 관측분포 반례, 수렴·판별타당도, 명칭 downgrade 규칙을 사전 고정한다.

- [x] **Step 3: 상태 온톨로지를 작성한다**

14개 목표 상태 각각에 대해 다음 필드를 채운다.

```text
state candidate
observable price-path label
required direct behavior or flow measure
distinguishing evidence
counterexample
allowed output name by data tier
decision-layer prohibition
```

`Normal`, `Relief`, `PostEventNormalization`도 심리적으로 해석하지 않고 관측 가능한 회복·정상화 조건과 별도 이름을 가진다.

- [x] **Step 4: protocol hash를 동결하고 trial ledger를 초기화한다**

`protocol.sha256`은 `protocol.md`의 SHA-256 한 줄을 저장한다. trial ledger는 `schemaVersion`, `studySlot`, `protocolId`, `protocolSha256`, 빈 `runs` 배열을 가진 canonical JSON이다.

### Task 6: ST-DAT-001 데이터 계약 객체와 source matrix

**Files:**
- Create: `research/meta-research/objects/research-questions/RQ-002-data-lineage/object.json`
- Create: `research/meta-research/objects/research-questions/RQ-002-data-lineage/question.md`
- Create: `research/meta-research/objects/dataset-contracts/DC-002-program-data/object.json`
- Create: `research/meta-research/objects/dataset-contracts/DC-002-program-data/data-contract.md`
- Create: `research/meta-research/objects/dataset-contracts/DC-002-program-data/official-source-register.json`
- Create: `research/meta-research/objects/study-protocols/SP-002-data-lineage-audit/object.json`
- Create: `research/meta-research/objects/study-protocols/SP-002-data-lineage-audit/protocol.md`
- Create: `research/meta-research/objects/study-protocols/SP-002-data-lineage-audit/protocol.sha256`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-matrix.md`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-matrix.json`
- Create: `research/rp-001/trials/ST-DAT-001.json`
- Create: `research/rp-001/tests/test_data_lineage_contract.py`
- Modify: `research/rp-001/tests/test_ontology_contract.py`
- Modify: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/object.json`
- Modify: `research/meta-research/catalog/research-objects.json`

- [x] **Step 1: RED로 전체 데이터계보 계약을 먼저 고정한다**

`test_data_lineage_contract.py`는 필수 artifact 부재, 정확한 객체 사슬, canonical JSON,
공식 출처 4개, 8개 입력군, 공통 시간·단위·revision·권리 필드, 결측 금지,
credential 경계와 protocol hash 결박을 검사한다. `test_ontology_contract.py`의 catalog
checkpoint도 Task 6 이후 상태로 먼저 갱신한다.

```text
catalog objects=12
dependencies=16
artifacts=39
order=DC-001,DC-002,DR-001,EB-001,MC-001,MS-001,RB-001,RP-001,
      RQ-001,RQ-002,SP-001,SP-002
```

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/rp-001/tests/test_data_lineage_contract.py -v
```

Expected: 필수 Task 6 artifact가 없어서 FAIL. API·credential·시장자료에는 접근하지 않는다.

- [x] **Step 2: RQ-002와 DC-002를 작성한다**

RQ-002의 estimand는 각 필수 입력군의 가용성 `usable / limited / data_unavailable`과
해당 자료로 주장할 구성개념의 식별성 `identifiable / not_identifiable`을 분리한 판정이다.
DC-002는 Goal의 모든 필드—provider/source, event/publication/received timestamp,
exchange/timezone/session, adjusted/native price·volume, shares outstanding/float,
corporate actions, missing/halt/zero, revision, raw/processed SHA-256,
license/redistribution—를 명시한다.

`official-source-register.json`은 다음 네 공식 1차 출처를 `design_seen_before_freeze`로
기록하고 title, publisher, URL, accessedAt=`2026-07-10`, documentVersion,
HTTP-response SHA-256, evidence asset URL/hash, appliedClaims,
undocumentedOrNonApplicableClaims를 가진다.
각 source는 초 단위 timezone `retrievedAt`, prior observed hash 목록과 revision 관찰을 가진다.
동일 `latest`·동일 문서 version에서도 bytes가 바뀔 수 있으므로 동결 직전 공개 URL을 두 번
조회해 hash 안정성을 확인하고, 실제 마지막 응답 hash를 기록한다.

```text
TOSS-DOC-001 https://developers.tossinvest.com/llms.txt
TOSS-DOC-002 https://openapi.tossinvest.com/openapi-docs/latest/openapi.json
TOSS-DOC-003 https://openapi.tossinvest.com/openapi-docs/overview.md
TOSS-DOC-004 https://home.tossinvest.com/ko/open-api
```

OpenAPI canonical version은 `1.2.2`다. 공개 FAQ의 본인 매매 목적 한정,
외부 배포·상업 이용 금지와 로컬 저장·보존·파생물 공개 범위 미문서화를 분리한다.
FAQ page가 client-render shell이면 초기 HTML hash를 FAQ 주장 근거로 사용하지 않고,
실제 FAQ 문구를 포함하는 공식 Next.js asset URL과 SHA-256을 별도로 결박한다.
대화에 credential 값이 사전 노출되었다는 사실만 값 없이 기록하고, 현재 credential은
회전 및 권리 확인 전 live 연구수집에 사용하지 않는다. 로컬 credential 파일 내용,
환경변수 값, API token은 읽거나 출력하지 않는다.

- [x] **Step 3: source matrix를 구조화 SSOT와 Markdown projection으로 작성한다**

행은 daily/minute OHLCV, factors, shares/corporate actions, attention/news, investor flow, options/short/borrow, ordered book/trade/cancel/aggressor side다. 열은 provider candidate, auth, timestamp completeness, unit completeness, revision, license, current availability, blocking effect다.

`source-matrix.json`을 구조화 SSOT로 두고 Markdown은 그 projection임을 명시한다.
각 행은 정확히 하나의 availability status와 claim별 identifiability implication,
usableFor·blockedResearchUses·blockingEffects를 가지며, 복합 입력군은
`componentStatuses`로 부분 가용성과 필수 구성요소 부재를 함께 공개한다.
문서 사실·문서 부재 관찰·연구 추론·운영 통제는 서로 다른 `evidenceKind`로 저장한다.

```text
daily_ohlcv                    limited
minute_ohlcv                   limited
market_sector_rates_fx_vol     limited
shares_and_corporate_actions   limited
attention_and_news             data_unavailable
participant_flow               limited
options_short_and_borrow       data_unavailable
ordered_book_trade_cancel      data_unavailable
```

Toss adjusted candle은 가격경로 연구에만 `limited`다. volume 단위·turnover·조정 산식·
기업행사·revision·세션/venue가 미문서화되어 behavior·microstructure·execution에는
사용하지 않는다. 현재 호가 snapshot과 당일 최근 체결은 순서보존 event·취소·aggressor·
historical depth를 대체하지 않는다. 어떤 결측도 0·중립값으로 채우거나 재가중하지 않는다.
현재 주식수 snapshot과 KR 지수·국채·FX 일부는 `limited`, PIT 주식수·float·기업행사와
US/업종/변동성 factor feed는 `data_unavailable` component로 분리한다. 홈페이지의 WebSocket
홍보문구와 canonical OpenAPI·overview의 REST-only 계약이 충돌하면 canonical 계약을 우선한다.

- [x] **Step 4: 데이터 열람 전 프로토콜과 빈 trial ledger를 동결한다**

SP-002는 이번 실행이 공개 문서·저장소 경계 감사만 사용했고 API·token·credential file·
unseen market data를 열지 않았음을 공개한다. 향후 live 수집은 다음을 모두 만족할 때만 허용한다.

1. protocol.md 재계산 hash가 protocol.sha256·source matrix·trial ledger와 일치
2. 회전된 credential을 renderer·영속 repository·CLI 인자가 아닌 일회성 process environment로 전달
3. 개인 매매 목적 내부 사용과 local retention 범위 확인, 외부 재배포 금지
4. 공급자 HTTP 원응답과 processed canonical data를 분리하고 각각 hash·received timestamp 기록
5. row·timestamp·timezone·OHLC bounds·duplicate·cutoff·currency·rate-limit header 검증
6. 오류·stdout·stderr·manifest·trial 전체의 secret scan 0건

현재 live 수집은 `blocked_pending_rotated_credentials_and_provider_retention_clarification`로 남기며,
이 block을 0·중립 자료로 우회하지 않는다. `protocol.sha256`은 64자 lowercase hash 한 줄과 LF,
trial ledger는 canonical JSON과 `runs=[]`를 가진다.

- [x] **Step 5: GREEN과 전체 foundation 회귀를 확인한다**

Task 6 전용 테스트, 전체 RP 테스트, meta 27개 테스트, meta CLI, foundation CLI를 실행한다.
Expected: 전용·전체 테스트 `OK`, meta `objects=12 dependencies=16 artifacts=39`,
foundation coverage 세 항목 `1.0`. Task 5의 protocol/source/ontology 고정 hash는 변하지 않는다.

### Task 7: 나머지 여섯 study의 RQ/DC/SP 계약 등록

**Files:**
- Create: `research/meta-research/objects/research-questions/RQ-003-behavior-regime/*`
- Create: `research/meta-research/objects/research-questions/RQ-004-relative-value/*`
- Create: `research/meta-research/objects/research-questions/RQ-005-microstructure/*`
- Create: `research/meta-research/objects/research-questions/RQ-006-execution-cost/*`
- Create: `research/meta-research/objects/research-questions/RQ-007-tail-risk/*`
- Create: `research/meta-research/objects/research-questions/RQ-008-synthesis/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-003-behavior-regime/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-004-relative-value/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-005-microstructure/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-006-execution-cost/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-007-tail-risk/*`
- Create: `research/meta-research/objects/dataset-contracts/DC-008-synthesis-inputs/*`
- Create: `research/meta-research/objects/study-protocols/SP-003-behavior-regime/*`
- Create: `research/meta-research/objects/study-protocols/SP-004-relative-value/*`
- Create: `research/meta-research/objects/study-protocols/SP-005-microstructure/*`
- Create: `research/meta-research/objects/study-protocols/SP-006-execution-cost/*`
- Create: `research/meta-research/objects/study-protocols/SP-007-tail-risk/*`
- Create: `research/meta-research/objects/study-protocols/SP-008-synthesis/*`
- Create: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/study-contracts.json`
- Create: `research/rp-001/trials/ST-BEH-001.json`
- Create: `research/rp-001/trials/ST-VAL-001.json`
- Create: `research/rp-001/trials/ST-MIC-001.json`
- Create: `research/rp-001/trials/ST-EXE-001.json`
- Create: `research/rp-001/trials/ST-RSK-001.json`
- Create: `research/rp-001/trials/ST-SYN-001.json`

- [x] **Step 1: RQ-003~RQ-008의 단일 estimand·horizon을 작성한다**

BEH는 행동 측정치의 가격기준선 대비 ΔBrier/Δlog-loss, VAL은 point-in-time 상대가치 잔차의 ΔBrier/순수익, MIC는 ordered event 자료의 markout 증분, EXE는 비용분포 이후 net edge, RSK는 CVaR 차감 효용, SYN은 독립 외부 OOF 입력만 사용한 통합 증분효용을 주요 estimand로 둔다.

- [x] **Step 2: DC-003~DC-008의 필수자료와 차단조건을 작성한다**

각 계약은 Goal의 공통 시간·단위·계보 필드를 반복 복사하지 않고 DC-002를 의존성으로 참조하고 study 고유 필드만 추가한다. 필수 원자료가 없으면 `data_unavailable`, 인간 심리 라벨이 없으면 `not_identifiable`, 실행·비용분포가 없으면 운영 채택 금지다.

- [x] **Step 3: SP-003~SP-008을 preregistration-ready 상태로 작성한다**

각 프로토콜은 기준선, 후보, feature, forbidden input, horizon, nested purged walk-forward, embargo, 불확실성, 다중검정, negative control, leakage test, 최소효과 결정 절차, 무효 실행, stopping rule, disclosure를 갖는다. 아직 데이터 source acceptance가 끝나지 않은 프로토콜은 lifecycle `proposed`이며 빈 hash를 쓰지 않고 실제 문서 SHA-256을 기록한다.

- [x] **Step 4: 여섯 trial ledger를 빈 canonical JSON으로 초기화한다**

각 ledger는 자기 SP hash만 참조하고 다른 study의 run을 포함하지 않는다.

### Task 8: Catalog 통합과 전체 foundation 검증

**Files:**
- Modify: `research/meta-research/catalog/research-objects.json`
- Modify: `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/object.json`
- Modify: `research/meta-research/tools/validate_research_program.py`
- Modify: `research/meta-research/tools/test_validate_research_program.py`
- Modify: `research/rp-001/tests/test_ontology_contract.py`
- Modify: `research/rp-001/tests/test_data_lineage_contract.py`
- Verify: `research/meta-research/**`
- Verify: `research/rp-001/**`

- [x] **Step 1: 모든 새 descriptor를 ID 오름차순으로 catalog에 등록한다**

등록 대상은 DC-001~DC-008, DR-001, EB-001, 기존 MC/MS/RB/RP, RQ-001~RQ-008, SP-001~SP-008이다. descriptor의 `dependsOn`은 catalog 등록 ID만 가리키고 cycle이 없어야 한다.

- [x] **Step 2: meta-research 구조검사를 실행한다**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest research/meta-research/tools/test_validate_research_program.py -v

PYTHONDONTWRITEBYTECODE=1 /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/meta-research/tools/validate_research_program.py \
  --repository-root . \
  --program-root research/meta-research
```

Expected: 모든 테스트 `OK`, validator `VALID`, `catalogCoverage=1.00`.

- [x] **Step 3: RP-001 foundation 검사를 실행한다**

Run:

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_program.py --verify-foundation
```

Expected: requirement source, 8 study slots, 11 candidate families 모두 coverage `1.00`.

- [x] **Step 4: 문서·비밀정보·기존 변경경계를 검사한다**

Run:

```bash
rg -n 'TO[D]O|TB[D]|<[A-Z][A-Z0-9_-]*>' \
  research/meta-research research/rp-001 \
  docs/codex/specs/2026-07-10-rp-001-research-execution-design.md \
  docs/codex/plans/2026-07-10-rp-001-sg0-sg2-foundation.md

rg -n --hidden -S "sk-[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|clientSecret[[:space:]]*[:=][[:space:]]*['\"][^'\"]+" \
  research/meta-research research/rp-001 docs/codex/specs docs/codex/plans

git status --short -- \
  extensions src research/indicator-validation \
  research/meta-research research/rp-001 docs/codex/specs docs/codex/plans
```

Expected: placeholder·secret 검색은 exit 1과 출력 없음. 기존 `extensions`, `src`, `research/indicator-validation` 변경은 작업 시작 시 상태와 같고 이번 foundation diff에는 포함되지 않는다.

### Task 9: Foundation 자체검토와 다음 단계 분리

**Files:**
- Create: `research/rp-001/reports/sg0-sg2-foundation-audit.md`
- Create: `docs/codex/plans/2026-07-10-rp-001-sg3-sg5-evidence-engine.md`

- [ ] **Step 1: 요구사항 완전성·계약 모순을 재검토한다**

감사 보고서는 Goal hash, 등록 요구사항 수, source requirement coverage, 8개 study chain, 11개 candidate family, RB-001 변이, 아직 통과하지 않은 G1~G10을 수치와 artifact 경로로 보고한다.

- [ ] **Step 2: SG3·SG5 실행 계획을 별도 작성한다**

다음 계획은 데이터 열람 전에 price-path 외부표본 universe, 기간, fold, outcome, candidate, seed, 비용 민감도, 최소효과와 차단 후보를 고정한 뒤에만 수집·실행하도록 작성한다. 이 foundation 계획에서는 unseen 시장데이터를 열지 않는다.

- [ ] **Step 3: Foundation을 독립 검토한다**

새 검토자는 Goal 원문과 catalog만으로 requirement→RQ/DC/SP 매핑, protocol hash, RB-001 변이 기록을 재계산하고 차이를 보고한다. 결론 동의가 아니라 동일 artifact로 동일 coverage를 얻는지를 판정한다.
