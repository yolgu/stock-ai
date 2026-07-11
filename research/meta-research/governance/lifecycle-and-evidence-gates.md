# 연구 수명주기와 증거 Gate

## 1. 수명주기 상태

```text
proposed -> preregistered -> active -> frozen -> completed -> archived
     |             |          |
     +-------------+----------+-> rejected
```

| 상태 | 의미 | 허용되는 변경 |
| --- | --- | --- |
| `proposed` | 질문·자료·방법 후보를 설계 중 | 질문과 구조 변경 가능 |
| `preregistered` | 가설·estimand·자료·평가·중단조건 동결 | 실행상 명백한 결함은 amendment로만 기록 |
| `active` | 자료수집 또는 분석 실행 중 | 결과와 실행기록 append-only |
| `frozen` | 입력·코드·출력·manifest가 봉인됨 | 직접 수정 금지 |
| `completed` | 반증·한계·판정을 포함한 보고 완료 | 정정은 후속 객체로만 가능 |
| `rejected` | 식별·자료·품질·반증 Gate 실패 | 실패 이유와 재개조건만 보존 |
| `archived` | 후속 객체가 대체했지만 역사적 근거로 보존 | 수정 금지 |

## 2. 증거수준

수명주기 상태와 증거수준은 다른 축이다. 문서가 완료됐다는 사실이 가설이 확인됐다는 뜻은 아니다.

| 수준 | 의미 | 허용되는 주장 |
| --- | --- | --- |
| `conceptual` | 이론·구조·후보만 존재 | 연구할 가치와 식별조건 |
| `exploratory` | 이미 본 자료 또는 탐색 절차의 결과 | 후보 축소와 후속 가설 |
| `confirmatory` | 사전등록된 봉인 표본의 결과 | 정해진 estimand 범위의 판정 |
| `reproduced` | 다른 실행자가 같은 artifact로 결과 재생 | 계산 재현성과 artifact 기능성 |
| `replicated` | 독립 자료·구현에서 주요 결론 재확인 | 제한된 외적 타당성 |

## 3. 연구 Gate

| Gate | 질문 | 필수 증거 | 실패 상태 |
| --- | --- | --- | --- |
| G0 경계 | 기존 연구와 새 연구가 분리됐는가? | baseline ID, 불변 원문, 새 catalog | `rejected` |
| G1 질문 | 질문·estimand·horizon이 단일 의미인가? | `ResearchQuestion` | `proposed` 유지 |
| G2 식별 | 필요한 현상을 실제 자료로 구별할 수 있는가? | 관측가능성 행렬, 반례 | `rejected/not_identifiable` |
| G3 자료 | 단위·가용시점·계보·결측이 고정됐는가? | `DatasetContract`, manifest | `rejected/data_unavailable` |
| G4 사전등록 | 가설·기준선·반증·중단조건이 동결됐는가? | `StudyProtocol` hash | 분석 금지 |
| G5 구현 | 수학과 구현이 경계·단위·인과성에서 같은가? | reference test, 합성자료 | `rejected/implementation_invalid` |
| G6 내부검증 | 단순 기준선 대비 최소효과와 보정도를 통과하는가? | OOF evidence | `rejected/insufficient_evidence` |
| G7 외부검증 | 보지 않은 기간·종목·전향표본에서 재현되는가? | 봉인 holdout evidence | `rejected/external_failure` |
| G8 경제성 | 비용·체결·시장충격·꼬리위험 이후 양수인가? | net utility evidence | `research_only` |
| G9 독립재현 | 다른 실행자가 같은 artifact로 결과를 얻는가? | reproduction record | `confirmatory` 유지 |
| G10 통합 | 독립 연구의 OOF 출력만으로 증분가치가 있는가? | integration evidence | 통합 기각 |

한 Gate의 초과성과로 다른 Gate의 실패를 상쇄할 수 없다. 특히 높은 백테스트 수익률은 자료 계보·누수·외부검증 실패를 보상하지 못한다.

## 4. 결정 상태

- `adopt`: 모든 필수 Gate를 통과하고 적용범위가 명확하다.
- `conditional_adopt`: 특정 종목·빈도·유동성·자료조건에서만 통과한다.
- `research_only`: 설명 또는 탐색에는 유용하지만 운영 증거가 부족하다.
- `reject`: 사전 정의된 반증 또는 품질실패가 있다.
- `not_identifiable`: 필요한 관측이나 정답이 없어 주장 자체를 판정할 수 없다.
- `abstain`: 특정 시점의 입력·분포·불확실성이 운영 결정을 허용하지 않는다.

## 5. amendment

실행 중 결함이 발견되면 다음을 분리한다.

1. 결함을 발견한 시점과 이미 열람한 결과
2. 원 프로토콜에서 달라지는 항목
3. 변경 전 실행의 폐기 또는 탐색 전환 여부
4. 새 버전과 새 hash
5. 남아 있는 확인표본의 봉인 상태

결과가 좋아지는 방향이라는 이유로 amendment를 정당화할 수 없다.

