# RQ-008 통합 연구질문

## 정체성

- 객체 ID: `RQ-008`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-SYN-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-008`
- contract operational decision: no_integration; NoTrade
- contract primary baseline: NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline
- contract primary estimand: 20-session cost/risk-adjusted utility increment from independent external OOF only
- contract primary horizon: `20 거래일`
- contract study slot: `ST-SYN-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 독립 external OOF only 원칙으로 Gate 통과 연구를 통합할 때, 향후 20거래일 cost/risk-adjusted utility가 네 사전고정 기준선보다 큰가?

## 구성개념 경계

통합은 upstream 연구를 재선택하거나 한 study의 holdout을 다른 study의 튜닝에 사용하지 않는다. Gate-passing external OOF만 입력이며 in-sample/holdout-selected/failed output은 제외한다. 결측 연구를 중립값으로 채우거나 남은 연구를 재가중해 자격 Gate를 우회하지 않는다.

## Estimand

- 모집단: protocol/run/evidence IDs로 추적되고 독립 외부표본 판정이 완료된 적격 연구 출력
- 관측단위: 20거래일 의사결정 구간의 통합 포트폴리오
- 예측시점: 모든 입력의 availability가 확인된 시점 t
- 주요 estimand: 통합의 향후 20거래일 cost/risk-adjusted utility에서 각 사전고정 기준선 효용을 뺀 증분
- horizon: `20 거래일`
- 보조 estimand: calibration, uncertainty/OOD/abstain, coverage, turnover와 기준선별 효용 차이
- 비교대상: `NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline`

primary horizon은 하나이며 네 기준선 모두를 결과 전에 고정한다.

## 가설과 식별조건

- 귀무가설: 통합 효용은 하나 이상의 기준선 대비 최소효과를 넘지 못한다.
- 대립가설: 통합 효용은 네 기준선 모두보다 사전 고정 최소효과 이상 크다.
- 필요한 자료: EXE cost and RSK output을 포함한 Gate 통과 독립 외부 OOF 연구 출력
- 조건부 자료 판정: 자료 수락 후 필수 입력이나 추적 ID의 실제 부재가 확인된 실행만 `data_unavailable`로 판정한다.

## 반증·중단

- 최소 반례: 적격 단일연구 기준선이 통합과 같거나 더 높은 비용·위험조정 효용을 갖는다.
- negative control: 연구 ID 또는 시점을 shuffle한 통합이 동일한 개선을 보이면 무효다.
- 현재 실행 disposition: `blocked`; lifecycle이 `proposed`이고 ledger가 `runs=[]`이므로 ExperimentRun·EvidenceBundle 생성 전 terminal status는 미할당이다.
- 조건부 terminal 판정: 자료 수락 후 실제 필수 통합입력 부재가 확인되면 `data_unavailable`로 판정한다.
- 운영 결정: `no integration/NoTrade`; required input이 없으면 실패 출력을 다른 입력으로 대체하지 않는다.

## 다음 객체

- DatasetContract: `DC-008`
- StudyProtocol: `SP-008`
