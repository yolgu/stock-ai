# RQ-004 PIT 상대가치 잔차의 20거래일 사건 예측 증분

## 정체성

- 객체 ID: `RQ-004`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-VAL-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-004`
- contract operational decision: block_confirmatory_VAL
- contract primary baseline: price/factor baseline
- contract primary estimand: OOF ΔBrier for the 20-session industry/market-adjusted positive excess-return event
- contract primary horizon: `20 거래일`
- contract study slot: `ST-VAL-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 시점 t의 point-in-time universe와 당시 가용한 요인·기초자료로 계산한 상대가치 잔차가 가격·요인 기준선보다 향후 20거래일 `industry/market-adjusted positive excess-return event`의 외부표본 확률예측을 개선하는가?

## 구성개념 경계

현재 가격과 공정가치 추정치의 잔차는 관측값이 아니라 명시된 비교집단·요인·vintage에 조건부인 추정량이다. 저평가, 평균회귀, 모멘텀, 확정 수익을 같은 개념으로 취급하지 않는다. `mean-reversion/momentum` 방향은 모두 사전에 후보로 두고 결과 후 선택하지 않는다.

`PIT universe/membership`와 `factors/fundamentals/industry/rates/FX`가 예측시점에 실제로 가용해야 한다. 현재 구성종목으로 과거 universe를 재구성하거나 최신 재무 vintage를 과거행에 덮어쓰면 상대가치 주장은 식별되지 않는다.

## 주요 estimand

- 모집단: point-in-time 적격 universe에서 완전한 계보를 가진 종목·시점 t
- 관측단위: 종목 × 시점 t
- 결과: 시점 t 뒤 20개 거래세션 보유수익에서 사전 고정 산업·시장 수익을 차감한 값이 양수인 사건
- 주요 estimand: 동일 outer fold의 가격·요인 기준선 대비 PIT 상대가치 후보의 외부표본 Brier score 감소
- horizon: `20 거래일`
- 비교대상: 상대가치 잔차를 제외하고 같은 가격·요인·적격행을 쓰는 기준선
- 방향: 양의 ΔBrier가 후보의 확률예측 개선을 뜻한다.

사건 threshold, 산업과 시장 조정식, 통화환산, 기업행동, 상장폐지 수익은 결과 열람 전에 고정한다.

## 부차 분석

- 외부표본 log-loss, calibration과 coverage를 보고한다.
- 사전 고정 비용 시나리오별 `cost-adjusted excess return`을 부차 결과로 보고하되 주요 확률 estimand와 합치지 않는다.
- 잔차 크기와 방향, 산업, 시장국면의 이질성은 multiplicity 보정된 보조분석이다.

## 가설

- 귀무가설: PIT 상대가치 후보의 기대 ΔBrier는 사전 고정 최소효과 이하이다.
- 대립가설: 적격 외부표본에서 후보가 최소효과를 넘고 leakage·calibration·다중검정 Gate를 통과한다.

## 식별·실행 조건

1. universe·membership, 산업분류, 요인과 기초자료는 event·publication·availability 시각과 vintage를 가져야 한다.
2. `native/adjusted reconciliation`으로 기업행동과 통화 단위를 추적한다.
3. `delisting/survivorship/vintage` 누락은 보상할 수 없는 실패다.
4. 필수 point-in-time 자료가 없으면 `confirmatory VAL` 실행은 `data_unavailable`이다.
5. 순수익 분석에는 비용 입력을 명시하고 비용이 없으면 운영채택을 금지한다.

## 반증과 terminal 의미

- 최신 universe나 최종 재무값을 과거에 소급했을 때만 나타나는 성능은 leakage 반례다.
- 산업·시장조정, delisting 또는 기업행동을 제거했을 때 방향이 뒤집히면 해당 민감도를 공개한다.
- 평균회귀와 모멘텀 중 terminal 결과가 유리한 방향만 남기는 것을 금지한다.
- terminal 결과는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure`만 사용하며 실패 후보도 보존한다.

## 연구 격리

이 질문의 20거래일 terminal 결과는 행동·미시구조 study의 후보나 threshold를 바꾸지 않는다. 설계에 사용한 종목·기간은 discovery 또는 regression 역할을 유지하며 confirmatory 결과로 재명명하지 않는다.

## 다음 객체

- 자료계약: `DC-004`
- 연구 프로토콜: `SP-004`
- trial ledger: `ST-VAL-001`
