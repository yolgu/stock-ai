# DC-007 외부표본 신호·비용·꼬리위험 데이터 계약

## 정체성

- 객체 ID: `DC-007`
- 적용 질문: `RQ-007`
- 적용 study: `ST-RSK-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-007`
- contract operational decision: NoTrade
- contract primary baseline: NoTrade and fixed simple risk baseline
- contract primary estimand: EΠ-λVar-ηCVaR_0.975(loss) increment over both fixed baselines
- contract primary horizon: `20 거래일`
- contract study slot: `ST-RSK-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## DC-002 참조 경계

DC-002의 공통 provider/source, event timestamp, publication timestamp, clientReceivedAt, 거래소·시간대·세션, native/adjusted 단위, 기업행동, revision, 권리와 raw/processed hash 계약을 규범적으로 참조하고 복사하지 않는다. 이 계약은 downstream 위험연구에 필요한 외부표본 신호·비용·포트폴리오 상태만 추가한다.

## 허용 입력

| 입력군 | 필수 계약 | 금지되는 대체 |
| --- | --- | --- |
| 신호 | only external OOF BEH/VAL/MIC outputs, study·protocol·run ID, OOF fold, prediction availability | in-sample, terminal holdout 선택값, 실패한 candidate |
| 실행 | EXE cost distribution, partial/reject 질량, 비용 통화와 시점 | 평균비용 하나, 비용 0, 다른 기간의 비용 |
| 포트폴리오 | holdings/currency/correlation/stress/risk budget, 의사결정 전 availability | 현재 보유를 0으로 추정하거나 상관결측을 독립으로 추정 |
| 위험선호 | λ,η,α와 고정시각, 승인 ID | 결과 후 위험선호·CVaR 수준 변경 |
| 결과 | 향후 20거래일 손익·분산·CVaR 계산에 필요한 event-time outcome | 겹치는 학습·검증 결과의 혼합 |

λ,η,α는 lifecycle promotion 전 모두 고정하고 `α=0.975` 손실 CVaR 정의와 연결한다. 위험예산, 포지션·통화 변환, stress scenario와 상관 입력은 같은 시점 t 정보집합을 사용한다.

## 결측·계보·무결성

결측 direct input을 0 또는 neutral로 대체하지 않는다. 남은 입력을 reweight 또는 renormalize하지 않는다. 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다. 외부 OOF 예측은 protocol hash, run ID, fold, calibration version과 직접 연결한다.

자료 수락 후 실제 downstream 자료 부재가 확인된 실행만 `data_unavailable`로 판정한다. λ,η,α 미고정은 lifecycle promotion 전에는 실행 disposition `blocked`다. 적격 실행 시작 또는 동결 protocol 이후 λ,η,α 미고정·변경은 `implementation_invalid`다.

운영 결정은 `NoTrade`다. 하나의 신호가 없다고 다른 신호 비중을 늘리거나, 상관 결측을 0으로 두거나, EXE cost distribution을 점추정으로 바꾸지 않는다. 차단 후보와 실패 run은 lineage에서 삭제하지 않는다.

## 수락조건

1. 모든 BEH·VAL·MIC 입력이 각 독립 terminal holdout 밖에서 생성된 external OOF다.
2. EXE 비용분포가 같은 결정·시장·통화 범위를 덮고 partial/reject를 포함한다.
3. 보유·통화·상관·stress·risk budget이 시점 t 이전에 가용하다.
4. λ,η,α와 단순 위험 기준선이 결과 열람 전에 고정됐다.
5. accepted raw/processed hashes와 availability timestamps가 재현 가능하다.

현재 `proposed` lifecycle에서 수락조건 하나라도 미충족이면 promotion 전 실행 disposition은 `blocked`다. 자료 수락 후 실제 downstream 자료 부재는 `data_unavailable`, 적격 실행 시작 또는 동결 protocol 이후 λ,η,α 계약 위반은 `implementation_invalid`로 분리한다. 운영 결정은 `NoTrade`이며 위험 최적화를 실행하지 않는다. Gate 실패를 낮은 신뢰도 가중치로 보상하지 않는다.

## 권리·실행·공개

권리와 보안은 DC-002를 따른다. 현재 downstream 자료를 수락하거나 결과를 열람하지 않았다. proposed 계약은 ExperimentRun 또는 EvidenceBundle을 만들지 않으며, 향후 차단·abstain·NoTrade 사례를 모두 공개 대상으로 남긴다.
