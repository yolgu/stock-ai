# RQ-006 실행비용 연구질문

## 정체성

- 객체 ID: `RQ-006`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-EXE-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-006`
- contract operational decision: NoTrade; prohibit_operational_adoption
- contract primary baseline: NoTrade
- contract primary estimand: expected fill-weighted NetEdge_0:5m minus NoTrade
- contract primary horizon: `decision 후 5분`
- contract study slot: `ST-EXE-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 시점 t의 거래 의사결정부터 5분까지 실제 주문 수명주기와 partial/reject를 포함할 때, fill-weighted NetEdge 분포에서 계산한 기대값이 NoTrade보다 양수인가?

## 구성개념 경계

실행가능성은 신호의 gross return과 분리한다. 의사결정, 제출, 공급자 수신, 승인, 체결, 취소, 거절 사이의 지연과 부분체결을 관측하지 못하면 가상 체결을 실제 실행으로 해석하지 않는다. NoTrade는 비용 0의 운영 기준선이며 결과를 본 뒤 바꾸지 않는다.

## Estimand

- 모집단: 사전 수락된 외부 OOF 신호가 만든 적격 주문 의사결정
- 관측단위: 의사결정과 그 주문 수명주기
- 예측시점: 주문 제출 전 시점 t
- 주요 estimand: `E[fill-weighted NetEdge_0:5m | decision-time information] - E[NetEdge | NoTrade]`라는 단일 scalar. `NetEdge=GrossEdge-Fees-Tax-FX-Slippage-Impact-Borrow/Hedge cost`이며 partial fill은 fill-weighted로, reject와 무체결은 기대값 계산에 명시적 질량으로 포함한다.
- horizon: `decision 후 5분`
- 보조 estimand: NetEdge 분포의 하한·양의 질량·quantile, fill probability, reject probability, latency·queue·규모별 비용분포와 calibration
- 비교대상: `NoTrade`

primary horizon은 하나이며 의사결정 후 5분을 다른 체결창 또는 보유기간으로 사후 교체하지 않는다.

## 가설과 식별조건

- 귀무가설: 5분 NetEdge 기대분포의 NoTrade 대비 증분은 0 이하이다.
- 대립가설: 사전 고정 최소효과와 불확실성을 통과한 증분이 0보다 크다.
- 필요한 자료: decision/submit/provider-received/ack/fill/cancel/reject timestamps, partial fills/queue, fees/tax/FX/borrow/hedge, spread/depth/impact
- 조건부 자료 판정: 자료 수락 절차 후 필수 수명주기·비용·유동성 자료나 수락된 raw/processed hash와 availability timestamp의 실제 부재가 확인된 실행만 `data_unavailable`로 판정한다.

## 반증·중단

- 최소 반례: gross edge가 양수여도 partial fill, reject, 지연, slippage와 impact를 포함한 NetEdge가 NoTrade 이하이면 채택하지 않는다.
- negative control: 의사결정 시각과 무관한 미래 체결행을 입력에 섞었을 때만 개선되면 leakage로 무효화한다.
- 현재 실행 disposition: `blocked`; lifecycle이 `proposed`이고 ledger가 `runs=[]`이므로 ExperimentRun·EvidenceBundle 생성 전 terminal status는 미할당이다.
- 조건부 terminal 판정: 자료 수락 후 실제 필수 실행자료 부재가 확인되면 `data_unavailable`로 판정한다.
- 운영 결정: `NoTrade`; 필수 실행자료가 없으면 operational adoption prohibited 상태를 유지한다.

## 다음 객체

- DatasetContract: `DC-006`
- StudyProtocol: `SP-006`
