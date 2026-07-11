# RQ-007 꼬리위험 연구질문

## 정체성

- 객체 ID: `RQ-007`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-RSK-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-007`
- contract operational decision: NoTrade
- contract primary baseline: NoTrade and fixed simple risk baseline
- contract primary estimand: EΠ-λVar-ηCVaR_0.975(loss) increment over both fixed baselines
- contract primary horizon: `20 거래일`
- contract study slot: `ST-RSK-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 시점 t까지 독립적으로 생성된 적격 외부 OOF 신호와 실행비용 분포를 결합했을 때, 향후 20거래일의 꼬리위험 조정 효용 증분이 NoTrade 및 사전고정 단순 위험 기준선보다 큰가?

## 구성개념 경계

위험 연구는 upstream 신호를 재학습하거나 선택하지 않는다. 입력은 Gate를 통과한 external OOF BEH/VAL/MIC outputs와 EXE cost distribution으로 제한한다. 효용은 수익률 하나가 아니라 분산과 손실 꼬리를 함께 벌점화하며 위험선호는 결과 전에 고정한다.

## Estimand

- 모집단: 동일 시점에 사용 가능하고 적격 판정을 받은 외부 OOF 신호·비용 사건
- 관측단위: 종목·포트폴리오·의사결정 시점
- 예측시점: 포지션 결정 전 시점 t
- 주요 estimand: `EΠ-λVar-ηCVaR_0.975(loss)`의 NoTrade 및 fixed simple risk baseline 대비 향후 20거래일 증분
- horizon: `20 거래일`
- 보조 estimand: turnover·drawdown·stress·coverage별 효용과 calibration
- 비교대상: `NoTrade`와 사전고정 `fixed simple risk baseline`

primary horizon은 하나이며 λ,η,α는 자료 수락과 lifecycle promotion 전에 고정한다.

## 가설과 식별조건

- 귀무가설: 비용과 꼬리손실을 포함한 효용 증분은 0 이하이다.
- 대립가설: 두 기준선 모두에 대해 사전 고정 최소효과보다 크다.
- 필요한 자료: holdings/currency/correlation/stress/risk budget, 외부 OOF 신호와 실행비용 분포
- 승격 전 통제조건: λ,η,α 미고정은 lifecycle promotion 전 실행 disposition `blocked`이며 terminal 결과가 아니다.
- 조건부 자료 판정: 자료 수락 후 실제 downstream 자료 부재가 확인된 실행만 `data_unavailable`로 판정한다.
- 실행계약 위반: 적격 실행 시작 또는 동결 protocol 이후 λ,η,α 미고정·변경이 발견되면 `implementation_invalid`로 판정한다.

## 반증·중단

- 최소 반례: 평균손익 증가는 있으나 분산·CVaR 벌점을 포함하면 기준선 이하인 경우다.
- negative control: future return을 무관한 과거 블록으로 치환해도 개선이 유지되면 연구를 무효화한다.
- 현재 실행 disposition: `blocked`; lifecycle이 `proposed`이고 ledger가 `runs=[]`이므로 ExperimentRun·EvidenceBundle 생성 전 terminal status는 미할당이다.
- 운영 결정: `NoTrade`; downstream Gate가 하나라도 실패하면 위험 최적화를 실행하지 않는다.

## 다음 객체

- DatasetContract: `DC-007`
- StudyProtocol: `SP-007`
