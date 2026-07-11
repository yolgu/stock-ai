# 연구 프로그램 메타 거버넌스 설계

## 1. 목적

기존 FOMO·패닉·차익실현 v1.4 연구를 변경하지 않고 보존하면서, 후속 정량금융 연구를 시작하기 전에 무엇을 어떤 증거와 절차로 연구할지 결정하는 메타-메타연구 체계를 만든다. 산출물은 사람이 읽을 수 있는 문서, 기계가 검사할 수 있는 연구객체 원장, 독립 연구가 따를 수 있는 공통 템플릿으로 구성한다.

## 2. 불변 경계

- `research/indicator-validation`과 기존 `docs/codex/research` 파일은 이동·수정·재명명하지 않는다.
- v1.4는 `ResearchBaseline`으로 참조하되 후속 결과로 과거 결론을 다시 쓰지 않는다.
- Bayesian HSMM·경쟁위험 문서는 `ModelCandidate`로만 등록하며 채택된 공식으로 승격하지 않는다.
- 새 체계는 `research/meta-research` 아래에 독립적으로 추가한다.
- 원자료와 비밀정보를 문서 객체 안에 복사하지 않고, 저장소 상대경로·해시·가용시점 계약으로 참조한다.

## 3. 검토한 구조

| 구조 | 장점 | 한계 | 결정 |
| --- | --- | --- | --- |
| 평면 Markdown 문서 모음 | 진입비용이 낮고 읽기 쉽다 | 중복 ID·누락 의존성·근거 단절을 자동 검출하기 어렵다 | 기각 |
| 완전한 지식그래프·RO-Crate·PROV-O 구현 | 상호운용성과 계보 표현력이 높다 | 현재 저장소 규모에 비해 도구·온톨로지 비용이 크다 | 장기 호환 목표 |
| 타입이 있는 파일 우선 연구객체 | Git 친화적이고 사람이 읽기 쉬우며 자동 검사가 가능하다 | 외부 저장소 상호운용은 매핑 계층이 필요하다 | 채택 |

채택 구조는 FAIR의 검색·접근·상호운용·재사용 원칙, RO-Crate의 폴더+메타데이터 연구객체, W3C PROV의 Entity·Activity·Agent 계보 개념을 최소한으로 적용한다. 사전등록은 편집 가능한 프로젝트와 동결된 등록본을 분리하는 OSF의 수명주기를 따른다. 반복성·재현성·복제성은 ACM Artifact Review 용어를 사용해 서로 구분한다.

## 4. 객체 모델

공통 추상기반 클래스를 코드로 만들지 않는다. 대신 모든 연구객체가 동일한 `object.json` 계약을 합성해 사용한다.

| 객체 | 책임 | 핵심 불변식 |
| --- | --- | --- |
| `ResearchBaseline` | 기존 연구와 결론의 변경 불가 기준점 | 원문 경로와 버전을 바꾸지 않는다 |
| `MetaStudy` | 연구방식·자료체계·판정규칙 자체를 연구한다 | 데이터 적합 전에 방법과 한계를 기록한다 |
| `ResearchProgram` | 여러 독립 연구의 목표·순서·통합 조건을 소유한다 | 개별 연구 결과를 직접 수정하지 않는다 |
| `ResearchQuestion` | 하나의 식별 가능한 질문을 표현한다 | 하나의 주요 estimand만 가진다 |
| `StudyProtocol` | 가설·자료·분석·반증·중단 조건을 동결한다 | 결과 열람 후 같은 버전을 수정하지 않는다 |
| `DatasetContract` | 단위·가용시점·결측·기업행동·계보를 정의한다 | 관측 불가능 값을 0으로 대체하지 않는다 |
| `ModelCandidate` | 하나의 모형족과 가정을 기술한다 | 검증 전 운영 지위를 갖지 않는다 |
| `ExperimentRun` | 프로토콜과 입력에 결박된 한 번의 실행이다 | 입력·코드·출력 해시를 가진다 |
| `EvidenceBundle` | 주장과 이를 지지·반박하는 결과를 연결한다 | 실패·무효·판정보류도 보존한다 |
| `DecisionRecord` | 채택·조건부·기각·식별불가 결정을 기록한다 | 결정과 근거를 분리하지 않는다 |

객체 간 관계는 `dependsOn`으로 표현한다. 객체 ID는 전역적으로 유일하고, 의존성 그래프는 순환할 수 없다. 객체의 완전한 정의는 각 객체 폴더의 `object.json` 한 곳에만 두며 중앙 catalog는 ID와 descriptor 경로만 가진다.

## 5. 경계와 폴더 구조

```text
research/meta-research/
├── README.md
├── governance/
│   ├── document-management-policy.md
│   ├── lifecycle-and-evidence-gates.md
│   ├── measurement-and-quality-model.md
│   ├── research-object-model.md
│   └── source-register.md
├── catalog/
│   ├── research-object.schema.json
│   └── research-objects.json
├── objects/
│   ├── baselines/RB-001-v1-4-indicator-validation/
│   ├── meta-studies/MS-001-research-program-governance/
│   ├── model-candidates/MC-001-bayesian-hsmm-competing-risks/
│   └── programs/RP-001-quantitative-market-behavior/
├── templates/
│   ├── data-contract.md
│   ├── decision-record.md
│   ├── evidence-bundle.md
│   ├── research-question.md
│   └── study-protocol.md
├── archive/README.md
└── tools/
    ├── test_validate_research_program.py
    └── validate_research_program.py
```

- `governance`: 모든 연구에 적용되는 정책만 둔다.
- `catalog`: 검색과 참조의 단일 진입점이다.
- `objects`: 객체별 응집 경계다. 다른 객체의 내용을 복제하지 않고 ID로 참조한다.
- `templates`: 객체 생성 계약이다. 실제 연구 결과를 저장하지 않는다.
- `archive`: 대체되거나 종료된 객체를 삭제하지 않고 보존하는 경계다.
- `tools`: 구조·ID·의존성·경로만 검증하며 연구결론을 계산하지 않는다.

## 6. 수명주기

```text
proposed -> preregistered -> active -> frozen -> completed -> archived
     |             |          |
     +-------------+----------+-> rejected
```

- `proposed`: 질문과 필요자료를 논의할 수 있다.
- `preregistered`: 가설·자료·평가·중단조건이 동결됐다.
- `active`: 동결된 프로토콜에 따라 자료수집 또는 분석 중이다.
- `frozen`: 입력과 결과가 해시로 봉인됐다.
- `completed`: 해석·반증·한계를 포함한 결론이 있다.
- `rejected`: 식별불가, 자료부족, 반증 또는 품질실패로 중단됐다.
- `archived`: 후속 객체가 대체했지만 역사적 근거로 보존된다.

동결 이후 수정은 금지한다. 정정은 새 버전·새 객체로 만들고 `supersedes` 관계로 연결한다.

## 7. 계측 품질모형

| 지표 | 정의 | 통과 기준 |
| --- | --- | --- |
| Catalog coverage | 등록 descriptor 수 / 발견 descriptor 수 | 1.00 |
| Descriptor validity | 유효 descriptor 수 / 등록 descriptor 수 | 1.00 |
| Referential integrity | 존재하는 의존 ID 수 / 전체 의존 ID 수 | 1.00 |
| Artifact availability | 존재하는 artifact 경로 수 / 전체 artifact 경로 수 | 1.00 |
| Dependency cycles | 순환 의존성 수 | 0 |
| Frozen mutation | 해시 불일치 동결 객체 수 | 0 |
| Evidence completeness | 주장·결과·한계·판정이 연결된 evidence 수 / 전체 evidence 수 | 확인 연구에서 1.00 |
| Reproduction status | 미검증·repeatable·reproducible·replicable | 단계별 별도 보고 |

자동 검증기는 앞의 첫 네 지표와 순환 의존성을 계산한다. 연구결론의 옳고 그름은 자동 판정하지 않는다.

## 8. 메타-메타연구 방식

이번 조사는 체계적 문헌고찰이라고 부르지 않는다. 단일 연구자가 공식 표준·원 논문·현재 저장소를 대상으로 수행한 `bounded standards synthesis + repository gap analysis`다.

1. 연구문서 체계가 만족해야 할 평가기준을 먼저 고정한다.
2. 평면 문서, 완전한 시맨틱 패키지, 타입이 있는 파일 우선 객체를 비교한다.
3. 공식 표준과 저장소의 현재 v1.4 계약을 대조한다.
4. 채택 구조의 한계와 향후 RO-Crate/PROV-O 변환 경로를 남긴다.
5. 독립 검토가 없다는 한계를 명시하고, 구조검증과 출처원장으로 보완한다.

## 9. 검증

- 단위검사: 정상 catalog, 중복 ID, 누락 descriptor, 미등록 의존성, 순환 의존성을 검사한다.
- 실제 구조검사: 저장소의 `research/meta-research`를 대상으로 전체 객체·artifact 경로를 검사한다.
- 문서검사: 미완성 표기, 깨진 저장소 상대경로, 비밀키 패턴이 없는지 검사한다.
- 변경범위검사: 기존 v1.4 파일이 diff에 포함되지 않았음을 확인한다.

## 10. 완료 조건

- 메타연구의 질문·방법·비교·한계·결정이 기록돼 있다.
- 연구객체의 책임, 수명주기, 근거수준, 통합 Gate가 정의돼 있다.
- 기존 v1.4와 HSMM 후보가 변경 없이 새 catalog에서 참조된다.
- 첫 번째 정량시장 연구 프로그램의 질문지도와 독립 연구 포트폴리오가 있다.
- 자동 구조검사가 통과하고 새로운 문서에서 비밀정보가 검출되지 않는다.
