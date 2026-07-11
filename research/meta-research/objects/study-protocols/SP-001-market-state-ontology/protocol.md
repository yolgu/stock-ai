# SP-001 시장 상태 온톨로지 프로토콜

## 정체성과 동결

- 객체 ID: `SP-001`
- study slot: `ST-ONT-001`
- 연구질문: `RQ-001`
- 자료계약: `DC-001`
- 상위 프로그램: `RP-001`
- 프로토콜 버전: `1.0.1`
- 동결일: `2026-07-10`
- 본문 hash 위치: `protocol.sha256`

프로토콜 본문의 SHA-256은 같은 디렉터리의 `protocol.sha256`에만 기록한다. 이 문장에는 해시값을 복제하지 않는다.

## Pre-run amendment 001

- 이전 protocol SHA-256: `30ccf01ea1337a96d316d30c03c0daacfe3ed2bbba085a500e3e55965f54a895`
- 발견 경로: 독립 사양 검토
- 적용 시점: 어떤 accepted run이나 evidence도 생성되기 전

이 amendment는 다음 세 변경만 적용한다.

1. `SRC-010`을 Springer 최종 출판본 `Inference in finite state space non parametric Hidden Markov Models and applications`, DOI `10.1007/s11222-014-9523-8`, 공식 Springer URL로 교정한다.
2. source unit의 발행연도 필드명을 `year`로 통일한다.
3. `missingObservationPolicy`를 `reject_no_zero_or_neutral_imputation`으로 고정하고 결측 direct measure의 Gate 실패와 재가중 금지를 명시한다.

실행 상태는 trial ledger `runs=[]`다. ExperimentRun과 EvidenceBundle은 생성되지 않았다. 시장 데이터는 사용하지 않았다. 이 amendment로 예측·채택·식별 결과를 선택하거나 변경하지 않았다.

## 사전 열람 코퍼스 공개

`DC-001`의 14개 1차 문헌은 `design_seen_before_freeze`다. 연구자가 프로토콜 설계 전에 이미 열람한 문헌이며, 이 코퍼스에서 도출한 온톨로지는 회고적 확인 근거가 아니다. 이 프로토콜은 열람 사실과 적용 한계를 공개한 개념적 명칭 계약이지 독립 확인 연구나 예측 성능 검증이 아니다.

## 질문과 estimand

질문은 다음과 같다.

> 사전 지정된 각 상태명에 대해, 시점 t까지 가용한 관측과 외부 측정치가 가격·거래량 국면, 잠재상태, 인간 심리, 거래결정을 서로 구별할 충분한 관측가능성과 판별타당도를 제공하는가?

- 주요 estimand: 14개 상태 후보 × 5개 자료 계층 각각의 terminal `identifiable`, `proxy_only`, `not_identifiable`
- horizon: 적용하지 않음. 시점 t의 동시적 구성개념 식별이며 미래예측이 아니다.
- 보수적 귀무가설: OHLCV는 심리·의도를 식별하지 못하고 T0에는 `price_volume_regime`만 허용된다.
- 대립 가능성: 직접 측정, 동시적 연결, 수렴·판별타당도, 대안 분리를 모두 충족하는 상위 계층에서만 제한된 구성개념 명칭이 가능하다.
- 최소 경제효과를 두지 않는다. 이 study는 수익·예측 또는 채택 주장을 하지 않는다.

## 포함·제외 규칙

### 포함

1. `source-register.json`에 동결된 정확히 14개 문헌만 1차 분석 코퍼스에 포함한다.
2. 모든 문헌은 원 연구, 원 방법론 논문 또는 공식 working paper인 1차 출처여야 한다.
3. 구성타당도, 투자자 행동 직접측정과 프록시, 잠재상태 식별, 주문장 관측의 의미 한계 중 하나 이상에 적용해야 한다.
4. DOI, 공식 URL, 접근일, 적용 주장, 비적용 범위를 모두 기록한다.

### 제외

1. 2차 리뷰, 블로그, 가격서사, 매체의 심리명칭은 제외한다.
2. 저작권 원문, 장문 인용, 표 전체는 저장하지 않는다.
3. 동결 뒤 발견한 출처는 기존 결과를 보강하는 방식으로 삽입하지 않으며 amendment와 새 버전 없이는 분석에 포함하지 않는다.
4. `primarySource=true`가 아니거나 `nonApplicableClaims`가 비어 있는 행은 제외하고 실행 전체를 무효로 판정한다.

## 다섯 자료 계층

| 계층 | 최소 관측 | 허용 명칭 경계 |
| --- | --- | --- |
| `T0_OHLCV` | 시점 t까지의 가격·거래량 | `price_volume_regime.*`만 허용하며 심리·의도 명칭 금지 |
| `T1_AGGREGATE_ATTENTION_FLOW` | 집계 검색·뉴스노출·주체별 흐름·집계 옵션/공매도 | `proxy.*`만 허용하며 동기·심리 명칭 금지 |
| `T2_ORDER_BOOK` | 순서보존 호가·체결·취소·aggressor 추론과 availability timestamp | `observed.*` 또는 `proxy.*` 미시구조명만 허용 |
| `T3_ACCOUNT_POSITION` | 연결 계좌 거래·포지션·취득원가 | 직접 행동명 또는 계좌 기반 `proxy.*`만 허용하며 동기는 별도 |
| `T4_LINKED_VALIDATED_SELF_REPORT` | 계좌·사건에 동시 연결된 검증 자기보고와 독립 행동/흐름 | 모든 타당도 Gate 통과 시에만 조건부 잠재 투자자 구성개념명 허용 |

## 추출 필드와 추출 절차

각 상태 행은 다음을 빠짐없이 추출한다.

- `stateCandidate`
- `observablePricePathLabel`
- `requiredDirectBehaviorOrFlowMeasure`
- `distinguishingEvidence`
- `counterexample`
- 5개 계층 각각의 `terminalStatus`, `outputName`, `candidateNameAllowed`, 조건과 시점 사용범위
- `decisionLayerProhibitions`
- `sourceIds`

1차 추출자는 14개 source unit의 적용 주장과 비적용 범위를 먼저 기록한다. 독립 2차 추출자는 출처 포함 여부, 각 상태의 terminal 판정, 명칭허용, 반례, source 결박을 별도로 재추출한다. 불일치는 숨기지 않고 후보·계층·두 판정·각 근거·보수적 해결을 공개한다. 합의되지 않은 경우 더 강한 명칭을 택하지 않고 `proxy_only` 또는 `not_identifiable`로 낮춘다.

## Terminal 판정 규칙

- `identifiable`: 동시적으로 연결된 직접 측정이 있고, 독립 방법의 수렴타당도와 판별타당도가 있으며, 뉴스·유동성 충격·리밸런싱·숏커버링·기계적 손절·서로 다른 믿음 같은 관측등가 대안이 분리된 경우에만 사용한다.
- `proxy_only`: 관측이 상태 후보와 관련 있지만 구성개념 또는 동기가 유일하지 않을 때 사용한다.
- `not_identifiable`: 직접 측정이 없거나 관측등가성이 남을 때 사용한다.

판정순서는 상호배타적으로 적용한다. 첫째, T0의 심리·의도 후보와 시점 t에 가용하지 않은 후보는 보수적으로 `not_identifiable`이다. 둘째, 직접 구성개념 측정과 모든 타당도 Gate를 통과하면 `identifiable`이다. 셋째, 후보 구성개념이나 동기는 유일하지 않지만 해당 계층에서 관련 관측이 직접 기록되고 별도의 비구성개념 출력명으로 정직하게 표현할 수 있으면 `proxy_only`다. 넷째, 관련 관측 출력조차 직접 측정되지 않거나 관측등가성 때문에 관련 프록시의 의미도 분리할 수 없으면 `not_identifiable`이다. 따라서 `proxy_only`는 후보 심리·의도가 식별됐다는 뜻이 아니며 `candidateNameAllowed=false`를 유지한다.

같은 OHLCV에서 파생한 복수 점수는 독립 방법으로 세지 않는다. 예측력, 상관, 분류 정확도 또는 경제효과는 구성개념 식별의 대체 조건이 아니다.

## 결측 관측 정책

구조화 SSOT의 `missingObservationPolicy`는 `reject_no_zero_or_neutral_imputation`이다. 결측 관측을 0, neutral, baseline으로 대체하지 않는다. 빈 direct measure 또는 결측 direct measure는 해당 Gate 실패이며 terminal은 `not_identifiable`이다. 결측 항목을 제외한 뒤 남은 항목의 reweight와 renormalize를 금지한다. 자료 계층이나 상태 후보에 따라 이 규칙을 완화하지 않는다.

## Label permutation 규칙

HMM·HSMM과 기타 통계 잠재상태는 외부 anchor가 label permutation 뒤에도 같은 의미를 유지하고 Terminal 판정 규칙을 통과할 때까지 반드시 `latent_state.k`로 기록한다. full-rank 전이행렬이나 선형독립 방출분포에 따른 통계적 식별가능성은 심리적 구성타당도를 자동으로 만들지 않는다. 사후 가격경로를 보고 상태 번호를 FOMO·패닉·차익실현으로 재명명하는 것을 금지한다.

## 반례 검사

1. 동일 OHLCV 경로가 뉴스, 유동성 충격, 리밸런싱, 숏커버링, 기계적 손절 또는 서로 다른 믿음으로 생성될 수 있는지 검사한다.
2. 같은 가격 입력에서 파생한 모든 점수를 하나의 방법군으로 묶고 이를 수렴타당도의 복수 방법으로 세지 않는다.
3. 관심·흐름·호가·계좌·자기보고를 각각 무엇을 직접 관측하고 무엇을 관측하지 않는지 분리한다.
4. Level I에서 시장가 매도와 취소가 구별되지 않는 경우를 미시구조 반례로 남긴다.
5. 계좌의 실현이익 매도와 차익실현 동기가 일치하지 않을 수 있는 대안을 남긴다.
6. `FakeRelief`는 미래 경로로만 판정하는 사후 결과명이며 시점 t 입력이나 거래 신호로 사용하지 않는다. 이 ontology study는 미래 창·반등·재하락 수치기준을 정하지 않으므로 현재 셀은 `not_identifiable`이다. 향후 적용 study가 창과 threshold를 별도 사전등록한 경우에만 그 사후 결과명을 계산할 수 있다.

## 명칭 및 결정층 규칙

- T0 심리·의도 명칭 0개가 필수다.
- T1은 `proxy.*`, T2는 `observed.*` 또는 `proxy.*`만 허용한다.
- T3의 `observed.realized_gain_sale`은 실현이익 매도 행동만 뜻하며 차익실현 동기를 뜻하지 않는다.
- T3의 미실현 이익 보유는 `proxy.unrealized_gain_overhang`으로만 표현한다.
- T4도 연결과 타당도 Gate가 없으면 구성개념명을 자동 허용하지 않는다.
- 상태, 프록시, 잠재상태 또는 사후 결과명은 어떤 거래도 직접 승인하지 않는다. 결정 행동은 별도 decision layer의 책임이다.

## 수락조건

1. 동결 source unit 완전성이 14/14다.
2. 14개 상태 × 5개 계층의 terminal 판정이 모두 존재한다.
3. T0 심리·의도 명칭 0개이며 모든 T0 출력은 `price_volume_regime.*`다.
4. 모든 출처 주장에 적용범위와 비적용 범위가 함께 있다.
5. 모든 상태 행에 최소 하나의 관측등가 반례와 출처 ID가 있다.
6. protocol hash, 온톨로지, 빈 trial ledger의 프로토콜 결박이 일치한다.
7. `FakeRelief`는 모든 계층에서 retrospective-only다.
8. 상태가 거래를 직접 승인하는 경로가 없다.

## 무효 조건

다음 중 하나라도 발생하면 실행을 무효로 공개한다.

- 1차 출처가 아닌 source unit 포함
- protocol hash 뒤 사후 규칙 변경 또는 무기록 출처 추가
- 상태 행의 반례 누락
- 출처의 비적용 범위 누락
- 실패·`proxy_only`·`not_identifiable` 결과 생략
- protocol hash, ontology 또는 trial ledger 결박 불일치
- `FakeRelief`를 시점 t 입력으로 사용

## 공개 계약

14개 상태의 5개 계층 판정을 결과 방향과 무관하게 전부 공개한다. `identifiable`뿐 아니라 실패, 무효, `proxy_only`, `not_identifiable`과 독립 추출 불일치를 포함한다. 이 study는 ExperimentRun 또는 EvidenceBundle을 발명하지 않으며 초기 trial ledger의 `runs`는 비어 있어야 한다. 결과가 특정 명칭을 허용하지 않더라도 그것이 사전 지정된 완전한 terminal 결과다.

## Amendment 규칙

동결 뒤 변경은 이 파일을 덮어쓰지 않는다. 새 버전은 변경 이유, 변경 전에 본 자료와 산출물, 폐기되는 판정, 남은 독립 추출 범위를 기록하고 별도 hash를 가진다.
