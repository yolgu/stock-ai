# DC-008 Gate 통과 외부표본 통합입력 데이터 계약

## 정체성

- 객체 ID: `DC-008`
- 적용 질문: `RQ-008`
- 적용 study: `ST-SYN-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-008`
- contract operational decision: no_integration; NoTrade
- contract primary baseline: NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline
- contract primary estimand: 20-session cost/risk-adjusted utility increment from independent external OOF only
- contract primary horizon: `20 거래일`
- contract study slot: `ST-SYN-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## DC-002 참조 경계

DC-002의 공통 provider/source, event timestamp, publication timestamp, clientReceivedAt, 거래소·시간대·세션, native/adjusted 단위, 기업행동, revision, 권리와 raw/processed hash 계약을 규범적으로 참조하고 복사하지 않는다. 이 계약은 연구 통합을 위한 자격·추적·불확실성 필드만 추가한다.

## Closed-world 허용 입력

| 입력군 | 필수 필드 | 배제 규칙 |
| --- | --- | --- |
| 연구 정체성 | study ID, protocol/run/evidence IDs, protocol hash, lifecycle, Gate decision | 미등록·교차 study ID와 hash 불일치 |
| 예측 | Gate-passing external OOF prediction, fold, horizon, prediction availability | in-sample/holdout-selected/failed output |
| 신뢰도 | calibration version, interval, uncertainty/OOD/abstain, risk-coverage | confidence 없는 점예측과 결측 중립화 |
| 비용·위험 | EXE cost and RSK output, 통화, cost/risk-adjusted utility 구성요소 | 비용 전 gross output, 위험 Gate 실패 출력 |
| 기준선 | NoTrade, buy-hold, fixed simple strategy, eligible single-study baseline | 결과 후 유리한 기준선 선택 |

허용 목록은 closed-world다. Gate-passing external OOF만 수락하며 independent external OOF only 원칙을 적용한다. 한 study의 terminal holdout은 다른 study 또는 통합기의 튜닝·threshold·가중치 선택에 사용할 수 없다.

## 결측·계보·무결성

결측 direct input을 0 또는 neutral로 대체하지 않는다. 남은 입력을 reweight 또는 renormalize하지 않는다. 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다. 각 입력은 자기 protocol hash, run ID, evidence ID, OOF fold, calibration ID와 결박한다.

필수 연구, EXE cost 또는 RSK output이 없을 때 terminal status는 `data_unavailable`이다.

운영 결정은 `no integration/NoTrade`다. in-sample과 external OOF를 혼합하지 않고, holdout-selected 또는 failed output을 낮은 가중치로 살려두지 않는다. blocked candidate는 입력으로 쓰지 않되 ledger에서 삭제하지 않는다.

## 수락조건

1. 모든 입력이 자기 연구의 promotion Gate를 통과한 독립 external OOF다.
2. protocol/run/evidence IDs, protocol hash, fold와 availability가 서로 일치한다.
3. calibration, uncertainty, OOD, abstain, risk-coverage가 공통 20거래일 판정시점에 가용하다.
4. EXE 비용분포와 RSK 효용 출력이 동일한 통화·universe·결정범위와 결박된다.
5. 네 기준선과 통합 규칙이 terminal holdout 열람 전에 고정된다.

하나라도 실패하면 terminal status는 `data_unavailable`이다. 운영 결정은 `no integration/NoTrade`이며 통합을 실행하지 않는다. 누락을 0·neutral·재가중으로 우회하거나 한 연구의 holdout으로 다른 연구를 선택하면 전체 통합 run이 무효다.

## 권리·실행·공개

권리와 보안은 DC-002를 따른다. 현재 자료 source acceptance, 통합 실행, 시장자료·결과 열람을 하지 않았다. 이 proposed 계약은 ExperimentRun 또는 EvidenceBundle을 만들지 않으며, 향후 실패·차단·abstain과 no integration/NoTrade 결과를 함께 공개한다.
