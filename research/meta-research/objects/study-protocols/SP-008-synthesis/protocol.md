# SP-008 독립 외부표본 20거래일 통합 연구 프로토콜

## 정체성과 상태

- 객체 ID: `SP-008`
- 연구질문: `RQ-008`
- DatasetContract: `DC-008`
- study slot: `ST-SYN-001`
- 프로토콜 버전: `1.0.0`
- hash 결박: 본문 bytes의 SHA-256은 별도 `protocol.sha256`과 빈 trial ledger에 기록하며 본문에는 현재 hash를 기록하지 않는다.

현재 lifecycle은 `proposed`다. 자료 source acceptance와 lifecycle promotion Gate를 통과하지 않았으므로 사전등록 상태가 아니며 확증 증거가 아니다. 현재 통합 성능이나 운영채택을 주장하지 않는다.

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `SP-008`
- contract operational decision: no_integration; NoTrade
- contract primary baseline: NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline
- contract primary estimand: 20-session cost/risk-adjusted utility increment from independent external OOF only
- contract primary horizon: `20 거래일`
- contract study slot: `ST-SYN-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문과 estimand

- 질문: independent external OOF only 통합의 20거래일 cost/risk-adjusted utility가 네 사전고정 기준선보다 큰가?
- 주요 estimand: Gate-passing external OOF 통합의 향후 20거래일 cost/risk-adjusted utility에서 각 primary baseline 효용을 뺀 증분
- 보조 estimand: calibration, uncertainty/OOD/abstain, coverage, turnover, 기준선별 효용 차이
- primary horizon: `20 거래일`

primary horizon은 하나다. 네 baseline 모두에 대한 동시 우월성을 요구하며 결과 후 horizon, 자격 Gate 또는 baseline을 바꾸지 않는다.

## 허용·금지 입력과 기준선

- 허용 입력: protocol/run/evidence IDs와 hash가 일치하는 Gate-passing external OOF, calibration·uncertainty/OOD/abstain, EXE cost and RSK output
- 금지 입력: in-sample/holdout-selected/failed output, 교차 study hash, terminal holdout 선택값, 자격 없는 prediction, 결측 중립화
- 단순 기준선: `NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline`
- 후보군 1: nonnegative constrained stacking과 calibration-aware weight cap
- 후보군 2: 사전고정 Gate-weighted rule ensemble
- 후보군 3: uncertainty와 abstain을 포함한 Bayesian model averaging

후보군은 3개이며 복잡도 우선순위를 두지 않는다. 통합기는 upstream candidate를 재학습하거나 재명명하지 않고, Gate-passing 입력의 closed-world 목록만 사용한다.

## 분할·튜닝·holdout 격리

- outer nested purged walk-forward만 outer 평가에 사용한다.
- integration weight, calibration, abstain, OOD와 risk-coverage threshold는 inner fold에서만 선택한다.
- purge 길이는 outcome horizon 이상이며 겹치는 20거래일 utility window를 제거한다.
- embargo: 20 sessions
- terminal holdout은 한 번 평가하고 이후 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다.
- 한 study의 terminal holdout은 다른 study의 candidate·Gate·통합 가중치 튜닝에 쓰지 않는다. 한 study holdout 결과로 다른 study를 포함·제외하지 않는다.

기존 seen TSLA/NVDA/MU/000660 windows는 discovery/regression only다. 이 프로토콜 작성에서는 API를 호출하거나 시장자료를 열람하지 않았다. 기존 창은 synthetic integration·코드 회귀 보조이며 outer·terminal evidence가 아니다.

## 평가·불확실성·다중검정

- 주 척도: 네 baseline 각각에 대한 20거래일 cost/risk-adjusted utility 증분
- 보조 척도: calibration, uncertainty, OOD, abstain, turnover와 risk-coverage
- 불확실성: symbol/event clustered moving-block bootstrap 또는 promotion 전에 고정한 posterior interval
- 다중검정: candidate family와 네 primary baseline 전체에 Holm family correction을 적용한다.
- calibration과 abstain: input 또는 integration calibration이 실패하거나 OOD이면 abstain해 NoTrade로 보낸다. risk-coverage 전체를 공개한다.

최소효과 δ는 비용·검정력·synthetic data를 함께 사용한다. EXE 비용, RSK 위험벌점과 조합 시나리오로 산정하고 lifecycle promotion 전에 동결한다. terminal 결과로 δ나 baseline을 바꾸지 않는다.

## 반증·누출검사·ablation

1. 시점 순서 shuffle: study prediction 시점을 교란하면 통합 개선이 사라져야 한다.
2. future-row invariance: 미래 input·outcome 행 변경이 시점 t prediction·weight를 바꾸면 안 된다.
3. negative control: study ID·prediction을 무관한 block에 배정한 통합은 개선을 만들지 않아야 한다.
4. ablation: 각 study, EXE cost, RSK penalty, calibration·abstain을 하나씩 제거해 증분과 취약성을 공개한다.

external OOF와 in-sample 혼합, holdout-selected/failed input, 교차 hash, outer/terminal tuning, 한 study holdout의 재사용은 무효 실행이며 terminal status `implementation_invalid`다.

## 중단 규칙·판정·공개

필수 Gate-passing external OOF, protocol/run/evidence IDs, uncertainty/OOD/abstain, EXE cost 또는 RSK output이 없으면 terminal status `data_unavailable`로 중단한다. 운영 결정은 `no integration/NoTrade`다. 외부 artifact 실패는 `external_failure`다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. `supported`는 네 baseline, δ, Holm, uncertainty, calibration·abstain·risk-coverage와 모든 반증검사를 통과해야 한다.

모든 candidate와 `blocked` 또는 `data_unavailable` 상태는 ledger에서 삭제하지 않는다. input 자격, fold, hash·ID, weight, 비용·위험, uncertainty, calibration, abstain, 반증·ablation과 Gate 실패를 결과 방향과 무관하게 공개한다. lifecycle이 proposed인 지금은 `runs=[]`이며 ExperimentRun과 EvidenceBundle을 생성하지 않는다.

## Amendment

lifecycle promotion 뒤 변경은 원문을 덮어쓰지 않는다. 변경 이유, 이미 본 정보, 폐기 run, 남은 독립 범위를 새 버전·hash에 기록한다. terminal holdout을 재튜닝에 쓰지 않는다.
