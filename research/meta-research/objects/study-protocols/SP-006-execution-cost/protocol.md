# SP-006 5분 실행 NetEdge 분포 연구 프로토콜

## 정체성과 상태

- 객체 ID: `SP-006`
- 연구질문: `RQ-006`
- DatasetContract: `DC-006`
- study slot: `ST-EXE-001`
- 프로토콜 버전: `1.0.0`
- hash 결박: 본문 bytes의 SHA-256은 별도 `protocol.sha256`과 빈 trial ledger에 기록한다. 본문에는 현재 hash를 기록하지 않는다.

현재 lifecycle은 `proposed`다. 자료 source acceptance와 lifecycle promotion Gate를 통과하지 않았으므로 사전등록 상태가 아니며 확증 증거가 아니다. 이 문서는 실행 전에 고정할 연구계약이며 현재 채택 또는 성과를 주장하지 않는다.

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `SP-006`
- contract operational decision: NoTrade; prohibit_operational_adoption
- contract primary baseline: NoTrade
- contract primary estimand: expected fill-weighted NetEdge_0:5m minus NoTrade
- contract primary horizon: `decision 후 5분`
- contract study slot: `ST-EXE-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문과 estimand

- 질문: decision 시점부터 5분까지 partial/reject를 포함한 fill-weighted NetEdge 분포에서 계산한 기대값이 NoTrade보다 양수인가?
- 주요 estimand: `E[fill-weighted NetEdge_0:5m | decision-time information] - E[NetEdge | NoTrade]`라는 단일 scalar. 여기서 `NetEdge=GrossEdge-Fees-Tax-FX-Slippage-Impact-Borrow/Hedge cost`다.
- 보조 estimand: NetEdge 분포 하한·양의 질량·conditional quantile, fill·reject probability, latency·queue·규모별 비용과 calibration
- primary horizon: `decision 후 5분`

primary horizon은 하나다. 5분 결과를 본 뒤 체결창이나 보유기간을 늘리거나 줄이지 않는다. partial fill은 fill-weighted로 유지하고 reject·cancel·무체결을 삭제하지 않는다.

## 허용·금지 입력과 기준선

- 허용 입력: decision/submit/provider-received/ack/fill/cancel/reject timestamps, partial fills/queue, fees/tax/FX/borrow/hedge, spread/depth/impact, 시점 t에 가용한 적격 OOF gross signal
- 금지 입력: future fill·future midprice, terminal holdout 결과, complete-fill survivor sample, snapshot으로 만든 가상 queue, 누락 비용 0 처리
- 단순 기준선: `NoTrade`; 추가 진단 기준선은 decision-price 전량체결 가정이지만 채택 기준선을 대신하지 않는다.
- 후보군 1: fill·reject competing-risk와 latency survival을 결합한 hurdle 분포모형
- 후보군 2: NetEdge conditional quantile·distributional regression
- 후보군 3: 주문 수명주기와 비용 구성요소의 계층 Bayesian posterior predictive

후보군은 3개이며 복잡도 우선순위를 두지 않는다. 후보군·hyperparameter 범위·feature availability는 terminal holdout을 열기 전에 고정한다.

## 분할·튜닝·holdout 격리

- outer nested purged walk-forward가 일반화 평가의 유일한 outer 구조다.
- hyperparameter, feature subset, calibration과 abstain threshold는 inner fold에서만 선택한다.
- purge 길이는 outcome horizon 이상이며 겹치는 5분 주문·markout 결과를 outer train에서 제거한다.
- embargo: one full session plus 5 minutes
- terminal holdout은 단 한 번 평가하며 이후 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다.
- 한 study의 terminal holdout은 다른 study의 후보·가중치·threshold 튜닝이나 상태명 선택에 쓰지 않는다.

기존 seen TSLA/NVDA/MU/000660 windows는 discovery/regression only다. 이 프로토콜 작성에서는 API를 호출하거나 시장자료를 열람하지 않았다. 그 창은 검정력·synthetic data 설계 보조 외에 outer 또는 terminal 평가에 들어가지 않는다.

## 평가·불확실성·다중검정

- 주 척도: NoTrade 대비 expected fill-weighted NetEdge 증분과 사전 고정 confidence interval
- 보조 척도: NetEdge 분포 하한·양의 질량, cost component error, fill/reject Brier, quantile coverage, latency·규모별 utility
- 불확실성: symbol/event clustered moving-block bootstrap 또는 lifecycle promotion 전에 고정된 posterior interval
- 다중검정: 세 candidate family의 primary comparison 전체에 Holm family correction을 적용한다.
- calibration과 abstain: 분포 calibration이 실패하거나 OOD이면 abstain하고 NoTrade로 보낸다. risk-coverage 곡선은 coverage를 낮춰 생긴 개선을 함께 공개한다.

최소효과 δ는 비용·검정력·synthetic data를 함께 사용한다. 구체적으로 fees·tax·FX·slippage·impact·borrow/hedge 비용과 검정력으로 산정하고 lifecycle promotion 전에 동결한다. terminal 결과를 본 뒤 δ를 낮추지 않는다.

## 반증·누출검사·ablation

1. 시점 순서 shuffle: 결정과 fill sequence를 교란했을 때 개선이 사라져야 한다.
2. future-row invariance: 시점 t 이후 행을 바꿔도 t의 입력·예측이 변하지 않아야 한다.
3. negative control: 무관한 주문 ID·venue-time block과 결합한 입력은 개선을 만들지 않아야 한다.
4. ablation: latency, queue, direct cost, depth/impact를 각각 제거해 의존성을 공개한다.

미래행 사용, outer/terminal tuning, 겹친 outcome 미제거, partial/reject 삭제, 비용 0 대체, hash·sequence 불일치는 무효 실행이며 terminal status `implementation_invalid`다.

## 중단 규칙·판정·공개

필수 실행자료 또는 accepted raw/processed hash와 availability timestamp가 없으면 terminal status `data_unavailable`로 중단한다.

운영 결정은 `NoTrade`이며 `operational adoption prohibited`다. 외부 공급 실패는 `external_failure`, 최소효과 미달은 `refuted`, 불확실성 과다는 `insufficient_evidence`다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. `supported`는 δ, uncertainty, Holm, calibration, abstain/risk-coverage, 모든 반증검사와 NoTrade 비교를 통과한 경우에만 가능하다.

모든 candidate와 `blocked` 또는 `data_unavailable` 상태는 ledger에서 삭제하지 않는다. 중단 규칙, fold별 예측, 비용 구성, uncertainty, calibration, abstain, 반증·ablation, Gate 실패를 결과 방향과 무관하게 공개한다. lifecycle이 proposed인 지금은 `runs=[]`이며 ExperimentRun과 EvidenceBundle을 생성하지 않는다.

## Amendment

lifecycle promotion 뒤 변경은 원문을 덮어쓰지 않는다. 변경 이유, 이미 본 정보, 폐기 run, 남은 독립 범위를 기록한 새 버전과 새 hash를 만든다. terminal holdout을 열었다면 같은 표본을 다시 봉인표본이라 부르지 않는다.
