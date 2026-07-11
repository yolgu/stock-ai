# RQ-005 순서보존 미시구조의 60초 markout 예측 증분

## 정체성

- 객체 ID: `RQ-005`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-MIC-001`
- 수명주기: `proposed`
- 증거수준: `conceptual`
- 버전: `1.0.0`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `RQ-005`
- contract operational decision: block_MIC_execution
- contract primary baseline: price-history baseline
- contract primary estimand: OOF squared-error reduction for the event-plus-60-second signed midquote markout
- contract primary horizon: `event 후 60초`
- contract study slot: `ST-MIC-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 질문

> 시점 t까지 완전히 수신된 `ordered book/trade/cancel/aggressor sequence`에서 계산한 OFI·depth·spread·취소·aggressor flow와 Hawkes 정보가 가격이력 기준선보다 event 후 60초 signed midquote markout을 외부표본에서 더 정확히 예측하는가?

## 구성개념 경계

호가 snapshot, 최근 체결 목록, 순서보존 사건열, 유동성 위기, 인간 공포를 서로 구분한다. `OFI/depth/spread/cancel/aggressor/Hawkes`는 주문장·체결 사건의 미시구조 특징이며 인간 심리명칭이나 거래결정이 아니다.

`venue clock/sequence`가 보존되지 않으면 취소와 체결의 순서, aggressor side, intensity history를 복원할 수 없다. `snapshot/recent trades`는 `ordered book/trade/cancel/aggressor sequence`를 대체할 수 없다.

## 주요 estimand

- 모집단: 사전 지정 venue·세션에서 sequence 완전성 Gate를 통과한 적격 event
- 관측단위: 종목 × venue × sequence event
- 결과: event 직전 midquote 대비 event 후 정확히 60초의 `signed midquote markout`
- 주요 estimand: 동일 outer fold의 가격이력 기준선 대비 미시구조 후보의 `OOF squared-error` 감소
- horizon: `event 후 60초`
- 비교대상: 같은 event·fold에서 시점 t까지의 가격이력과 기본 spread만 쓰는 기준선
- 방향: 양의 기준선 MSE-후보 MSE가 후보의 개선을 뜻한다.

markout 부호, event 종류, 60초 endpoint, 거래정지와 세션종료 경계는 자료 열람 전에 고정한다.

## 부차 분석

- calibration이 정의되는 확률적 파생 사건, coverage와 risk-coverage는 보조로 보고한다.
- OFI, depth, spread, cancel, aggressor, Hawkes 구성요소별 ablation을 수행한다.
- venue·tick size·세션 구간별 이질성은 multiplicity 보정된 보조분석이다.

## 가설

- 귀무가설: 순서보존 미시구조 후보의 기대 OOF 제곱오차 감소는 사전 고정 최소효과 이하이다.
- 대립가설: 적격 외부표본에서 후보가 최소효과를 넘고 sequence·leakage·안정성 Gate를 통과한다.

## 식별·실행 조건

1. 모든 event는 거래소 시계, 단조 sequence, 수신시각, 종목·venue, order side·price·size·event type을 가져야 한다.
2. aggressor 규칙과 book reconstruction은 결과 열람 전에 고정한다.
3. `tick/halts/message loss`, crossed book, duplicate와 sequence gap을 탐지하고 영향 구간을 격리한다.
4. 순서보존 원자료가 `currently unavailable`이면 실행은 `data_unavailable`이며 snapshot으로 우회하지 않는다.
5. markout 예측 개선만으로 체결 가능성, 순수익 또는 운영채택을 승인하지 않는다.

## 반증과 terminal 의미

- 시점 순서를 섞거나 미래 book row를 넣은 검사에서 성능이 유지되면 실행을 무효로 한다.
- event sequence를 snapshot으로 축약해도 동일하다는 결과는 ordered-event 증분 주장의 반증 자료다.
- message loss 또는 clock drift가 결과 방향과 결합되면 해당 구간과 전체 민감도를 공개한다.
- terminal 결과는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure`만 사용하며 차단 후보도 삭제하지 않는다.

## 연구 격리

이 질문의 60초 terminal holdout은 다른 study의 후보·threshold·상태명에 영향을 주지 않는다. 순서보존 신규 자료는 이 study 전용이며, 설계에 사용한 snapshot 또는 최근 체결은 confirmatory ordered-event 증거가 아니다.

## 다음 객체

- 자료계약: `DC-005`
- 연구 프로토콜: `SP-005`
- trial ledger: `ST-MIC-001`
