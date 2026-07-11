# 연구객체 모델

## 1. 모델링 원칙

이 체계는 객체지향 용어를 폴더 수를 늘리는 장식으로 사용하지 않는다. 연구에서 실제로 독립적인 책임과 수명주기를 갖는 개념만 객체로 만든다.

- **Encapsulation:** 객체의 정의와 직접 산출물은 한 객체 폴더 안에 둔다.
- **Single Responsibility:** 질문, 프로토콜, 자료계약, 실행, 근거, 결정은 서로 다른 변경 이유를 가진다.
- **Composition:** 모든 객체는 공통 `object.json` 계약을 합성한다. 불필요한 상속 계층을 만들지 않는다.
- **Dependency Inversion:** 연구 프로그램은 특정 파일 내부 형식이 아니라 객체 ID와 계약에 의존한다.
- **SSOT:** 중앙 catalog에는 제목·상태·근거를 복사하지 않고 descriptor 경로만 저장한다.
- **Bounded Context:** 거버넌스, catalog, 연구객체, template, archive, 검증 도구의 책임을 섞지 않는다.

## 2. Aggregate root

각 `objects/<type>/<id-name>/` 폴더가 aggregate root다. 외부에서는 그 폴더의 `object.json`만 객체 정의로 읽는다.

```text
Object aggregate
├── object.json       identity, type, state, evidence, dependencies, artifacts
├── protocol.md       해당할 때만 존재
├── report.md         해당할 때만 존재
├── evidence*.md      해당할 때만 존재
└── README.md         사람용 진입점
```

한 객체가 다른 객체의 내용이나 결과표를 복사하면 두 진실 공급원이 생긴다. 필요한 관계는 `dependsOn` ID와 artifact 링크로 표현한다.

## 3. 객체 책임

| 객체 유형 | 소유하는 것 | 소유하지 않는 것 |
| --- | --- | --- |
| `ResearchBaseline` | 기존 프로토콜·결과의 불변 참조 | 새 해석에 맞춘 과거 결론 변경 |
| `MetaStudy` | 연구방식·품질규칙의 비교와 결정 | 개별 시장가설의 성능결론 |
| `ResearchProgram` | 상위 목표·연구 포트폴리오·통합 Gate | 개별 study의 파라미터와 결과 |
| `ResearchQuestion` | 질문·estimand·범위·식별조건 | 분석구현과 실행로그 |
| `StudyProtocol` | 가설·자료·분석·반증·중단조건 | 실행 뒤 선택한 유리한 해석 |
| `DatasetContract` | 단위·시점·계보·결측·라이선스 | 모형 성능과 최종 결정 |
| `ModelCandidate` | 수학적 가정·입출력·실패조건 | 검증 전 운영 채택 지위 |
| `ExperimentRun` | 프로토콜·입력·코드·출력의 한 실행 | 여러 실행의 종합 판단 |
| `EvidenceBundle` | 주장과 지지·반박·한계의 연결 | 채택 권한 |
| `DecisionRecord` | 결정·근거·적용범위·재검토 조건 | 원시결과의 수정 |
| `SynthesisReport` | 독립 연구 간 종합과 불일치 | 개별 실패결과 삭제 |

## 4. 식별자와 관계

- 형식: `^[A-Z]{2,4}-[0-9]{3}$`
- 현재 접두사: `RB` baseline, `MS` meta-study, `MC` model candidate, `RP` research program
- ID는 제목이나 폴더명이 바뀌어도 변하지 않는다.
- ID를 재사용하지 않는다.
- `dependsOn`은 실제로 catalog에 등록된 객체만 가리킨다.
- 의존성은 순환할 수 없다.
- 대체 관계가 필요하면 새 schema 버전에서 `supersedes`를 추가하고 기존 schema를 조용히 확장하지 않는다.

## 5. 불변식

1. 모든 발견 가능한 `object.json`은 catalog에 정확히 한 번 등록된다.
2. catalog는 객체 ID 순서다.
3. descriptor 경로와 artifact 경로는 저장소 밖으로 나갈 수 없다.
4. `preregistered` 이후 프로토콜 정정은 새 버전으로 분기한다.
5. `frozen` 객체의 무결성 불일치는 실패다.
6. `conceptual`·`exploratory` 근거를 운영 공식으로 사용할 수 없다.
7. 관측 불가능한 변수를 0 또는 중립값으로 치환하지 않는다.

## 6. 확장 원칙

새 객체 유형은 기존 유형으로 책임을 표현할 수 없고 최소 두 개의 실제 객체가 예상될 때만 schema에 추가한다. 외부 교환이 필요해지면 `object.json`을 버리지 않고 RO-Crate JSON-LD와 W3C PROV-O로 변환하는 adapter를 추가한다.

