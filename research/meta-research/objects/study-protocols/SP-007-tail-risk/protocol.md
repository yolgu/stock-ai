# SP-007 20거래일 꼬리위험 효용 연구 프로토콜

## 정체성과 상태

- 객체 ID: `SP-007`
- 연구질문: `RQ-007`
- DatasetContract: `DC-007`
- study slot: `ST-RSK-001`
- 프로토콜 버전: `1.0.0`
- hash 결박: 본문 bytes의 SHA-256은 별도 `protocol.sha256`과 빈 trial ledger에 기록하며 본문에는 현재 hash를 기록하지 않는다.

현재 lifecycle은 `proposed`다. 자료 source acceptance와 lifecycle promotion Gate를 통과하지 않았으므로 사전등록 상태가 아니며 확증 증거가 아니다. 현재 위험효용의 우월성이나 운영채택을 주장하지 않는다.

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `SP-007`
- contract operational decision: NoTrade
- contract primary baseline: NoTrade and fixed simple risk baseline
- contract primary estimand: EΠ-λVar-ηCVaR_0.975(loss) increment over both fixed baselines
- contract primary horizon: `20 거래일`
- contract study slot: `ST-RSK-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문과 estimand

- 질문: 적격 외부 OOF 신호와 실행비용 분포의 20거래일 꼬리위험 효용이 NoTrade와 사전고정 단순 위험 기준선보다 큰가?
- 주요 estimand: `EΠ-λVar-ηCVaR_0.975(loss)`의 `NoTrade` 및 `fixed simple risk baseline` 대비 향후 20거래일 증분
- 보조 estimand: drawdown, turnover, stress·currency·coverage별 효용과 calibration
- primary horizon: `20 거래일`

primary horizon은 하나다. λ,η,α는 data source acceptance 전에 고정하며 inner tuning 대상이 아니다. α=0.975 손실 CVaR 정의도 같은 시점에 고정하고 결과 후 위험선호 또는 horizon을 바꾸지 않는다.

## 허용·금지 입력과 기준선

- 허용 입력: external OOF BEH/VAL/MIC outputs, EXE cost distribution, holdings/currency/correlation/stress/risk budget와 각 availability·protocol·run ID
- 금지 입력: in-sample·terminal-selected signal, 비용 없는 gross signal, 미래 보유·상관·stress, missing downstream의 0·neutral 대체
- 단순 기준선: `NoTrade`와 사전고정 `fixed simple risk baseline`
- 후보군 1: 고정 λ,η,α를 쓰는 convex utility·risk-budget allocation
- 후보군 2: shrinkage covariance와 사전고정 stress scenario의 robust allocation
- 후보군 3: cost·return·tail loss의 계층 Bayesian posterior predictive allocation

후보군은 3개이며 복잡도 우선순위를 두지 않는다. 신호 자격, risk budget, candidate search space와 기준선은 독립 holdout 열람 전에 고정한다.

## 분할·튜닝·holdout 격리

- outer nested purged walk-forward만 outer 일반화 평가에 사용한다.
- allocation hyperparameter, calibration과 abstain은 inner fold에서만 선택한다. 사전 고정된 λ,η,α는 어떤 fold에서도 선택하거나 변경하지 않는다.
- purge 길이는 outcome horizon 이상이며 겹치는 20거래일 손익·risk window를 제거한다.
- embargo: 20 sessions
- terminal holdout은 한 번만 평가하며 이후 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다.
- 한 study의 terminal holdout은 다른 study의 signal·risk candidate·통합 가중치 튜닝에 쓰지 않는다.

기존 seen TSLA/NVDA/MU/000660 windows는 discovery/regression only다. 이 프로토콜 작성에서는 API를 호출하거나 시장자료를 열람하지 않았다. 기존 창은 synthetic stress와 코드 회귀 보조 외에 outer·terminal 성능 근거가 아니다.

## 평가·불확실성·다중검정

- 주 척도: 두 기준선 대비 `EΠ-λVar-ηCVaR_0.975(loss)` 증분
- 보조 척도: drawdown, turnover, stress loss, calibration, abstain과 risk-coverage
- 불확실성: symbol/event clustered moving-block bootstrap 또는 미리 고정한 posterior interval
- 다중검정: candidate family와 두 primary baseline 비교 전체에 Holm family correction을 적용한다.
- calibration과 abstain: OOD, tail calibration 실패 또는 uncertainty 과대이면 abstain해 NoTrade로 보낸다. risk-coverage를 모든 threshold에 공개한다.

최소효과 δ는 비용·검정력·synthetic data를 함께 사용한다. EXE 비용, 위험예산과 tail scenario로 산정하고 lifecycle promotion 전에 동결한다. terminal 결과로 λ,η,α나 δ를 다시 정하지 않는다.

## 반증·누출검사·ablation

1. 시점 순서 shuffle: 신호·비용·포트폴리오 시점을 교란하면 효용 개선이 사라져야 한다.
2. future-row invariance: 미래 손익·보유 행 변경이 시점 t allocation을 바꾸면 안 된다.
3. negative control: 무관한 signal block 또는 고정 noise score로 utility 개선이 재현되면 안 된다.
4. ablation: cost, covariance, stress, CVaR penalty와 각 upstream signal을 하나씩 제거해 기여와 취약성을 공개한다.

in-sample 혼합, downstream hash 불일치, 겹친 outcome, outer/terminal tuning, risk parameter 사후변경 또는 적격 실행 시작 뒤 λ,η,α 미고정은 무효 실행이며 terminal status `implementation_invalid`다.

## 중단 규칙·판정·공개

λ,η,α 미고정은 lifecycle promotion 전 실행 disposition `blocked`이며 terminal 결과가 아니다. 자료 수락 후 실제 downstream 자료 부재가 확인된 실행만 `data_unavailable`로 판정한다. 적격 실행 시작 또는 동결 protocol 이후 λ,η,α 미고정·변경은 `implementation_invalid`다. 운영 결정은 `NoTrade`이며 외부 처리 실패는 `external_failure`로 분리한다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. `supported`는 두 기준선, 최소효과 δ, Holm, uncertainty, calibration·abstain·risk-coverage와 모든 반증검사를 통과해야 한다.

모든 candidate와 `blocked` 또는 `data_unavailable` 상태는 ledger에서 삭제하지 않는다. signal provenance, fold, 비용·tail 분포, λ,η,α, uncertainty, calibration, abstain, 반증·ablation과 Gate 실패를 모두 공개한다. lifecycle이 proposed인 지금은 `runs=[]`이며 ExperimentRun과 EvidenceBundle을 생성하지 않는다. 이 시점의 terminal status는 미할당이다.

## Amendment

lifecycle promotion 뒤 변경은 원문을 덮어쓰지 않는다. 이미 본 정보, 변경 이유, 폐기 run과 남은 독립 범위를 새 버전에 기록한다. 다른 study holdout을 대신 쓰지 않는다.
