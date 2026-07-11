# RQ-003 직접 행동측정의 5거래일 사건 예측 증분

## 정체성

- 객체 ID: `RQ-003`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-BEH-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-003`
- contract operational decision: block_human_behavior_claim; allow_research_only_price_volume_regime
- contract primary baseline: price-only price_volume_regime baseline
- contract primary estimand: ΔBrier=baseline-candidate for the predefined 5-session onset event
- contract primary horizon: `5 거래일`
- contract study slot: `ST-BEH-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 시점 t까지 가용한 직접 행동 측정치가 같은 시점의 가격 이력만 쓰는 기준선보다, 사전 정의된 향후 5거래일 `interval outcome labels`의 onset event 확률을 외부표본에서 더 정확히 예측하는가?

## 구성개념 경계

관측된 행동, 가격에서 추정한 국면, 인간의 심리·의도, 거래결정을 분리한다. `price_volume_regime`은 가격 이력만으로 만드는 research-only 추정명이며 인간 행동이나 심리의 직접 관측이 아니다. `human behavior claim`은 시점에 맞게 연결된 직접 측정과 판별타당도가 있을 때만 평가한다. 직접 자료가 없거나 심리·의도를 경쟁 설명과 분리할 수 없으면 해당 주장은 `not_identifiable`이며 가격국면 결과만 유지한다.

`direct attention/news exposure`, `symbol flow`, `options/short/borrow`, `linked account/self-report`는 서로 다른 관측층이다. 한 계층의 존재로 다른 계층을 관측했다고 간주하지 않으며, 연결 계좌의 매매도 동기나 감정을 자동 식별하지 않는다.

## 주요 estimand

- 모집단: 자료계약을 통과한 종목·세션의 시점 t 예측행
- 관측단위: 종목 × 시점 t
- 결과: 시점 t 뒤 5개 거래세션 안에 최초 발생하는 사전 고정 가격·거래량 onset event의 이진 라벨
- 주요 estimand: 동일 outer fold에서 `ΔBrier=baseline-candidate`로 정의한 가격 전용 기준선 대비 직접 행동 후보의 외부표본 Brier score 감소
- horizon: `5 거래일`
- 비교대상: 같은 fold·같은 적격행에서 가격 이력만 쓰는 `price_volume_regime` 기준선
- 방향: 양의 ΔBrier가 후보의 개선을 뜻한다.

결과 라벨의 사건식, 최초 발생 규칙, 중복 위험창 처리와 관측 가능 시각은 자료 열람 전에 고정한다. 시점 t 이후에 만들어진 행동 입력은 예측행에 포함하지 않는다.

## 부차 분석

- 외부표본 `Δlog-loss`와 calibration 차이를 같은 적격행에서 보고한다.
- abstain이 허용된 경우 전체 coverage와 risk-coverage를 함께 보고한다.
- 행동 입력군별 ablation은 주요 estimand를 대체하지 않는다.

## 가설

- 귀무가설: 직접 행동 후보의 기대 ΔBrier는 사전 고정 최소효과 이하이다.
- 대립가설: 직접 행동 후보가 최소효과를 넘는 양의 외부표본 ΔBrier를 보이고 leakage·negative control·calibration Gate를 통과한다.

통계적 유의성만으로 인간 심리명칭, 인과효과 또는 거래채택을 승인하지 않는다.

## 식별·실행 조건

1. 각 직접 입력은 종목 연결키, event·publication·수신 가용시각, 표본분모, revision과 이용권리가 확인되어야 한다.
2. 행동 입력과 결과 라벨은 동일 시점 규칙으로 결합하고 결과구간과 겹치는 입력을 금지한다.
3. 필수 행동 입력군이 없으면 행동 후보 실행을 차단하고 `data_unavailable`을 기록한다.
4. 직접 측정이 있어도 인간 심리·의도를 유일하게 구분하지 못하면 human behavior claim은 `not_identifiable`로 남긴다.
5. 확률예측 개선은 별도 실행비용·위험 연구를 통과하기 전 거래결정으로 변환하지 않는다.

## 반증과 terminal 의미

- 시점 순서를 섞은 입력, 미래행을 주입한 검사 또는 가격 이력만 복제한 행동 점수가 같은 개선을 보이면 반증 실패다.
- 행동 입력 제거 뒤 성능이 유지되면 행동 증분 주장을 기각한다.
- 가격 기준선만 계산 가능하면 가격국면 회귀검사는 남길 수 있지만 행동연구의 성공으로 보고하지 않는다.
- terminal 결과는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure`만 사용하며 실패와 차단도 삭제하지 않는다.

## 연구 격리

이 질문의 5거래일 holdout 결과는 다른 study의 특징, threshold, 상태명 또는 후보 선택에 사용하지 않는다. 기존 네 종목 연구구간은 설계·회귀검사 역할에만 두고 독립 확증표본으로 승격하지 않는다.

## 다음 객체

- 자료계약: `DC-003`
- 연구 프로토콜: `SP-003`
- trial ledger: `ST-BEH-001`
