# 다중 시장상태 자율연구 캠페인 V3 설계

## 1. 목적

현재 활성 목표를 정확히 보존하면서 시점 t까지 이용 가능한 시장 데이터로 다음 다섯 형성과정을 결과 확정 전에 탐지하는 재현 가능한 연구 캠페인을 만든다.

1. 상승 가속·추격 참여 확산
2. 하방 변위·고강도 매도 확산
3. 상승 이후 매도압력 형성
4. 하락 이후 반전·정상화 형성
5. 비정상 과열과 구별되는 지속 상승세 형성

OHLCV와 집계 시장자료만 사용하는 개발 단계에서는 심리나 매도 동기를 직접 식별했다고 주장하지 않는다. 공식 출력은 `price_volume_regime.*` 국면 프록시이며 FOMO·패닉·차익실현·회복·상승세는 설명용 별칭으로만 사용한다.

## 2. 해결해야 하는 결함

기존 `QR-CAMPAIGN-7C20B7A414D9166539BC`는 현재 목표와 다른 Goal 원문에 결박되어 있고 상승세가 누락되어 있다. 기존 `quant-research-dataset.v2`는 단일 이진 라벨만 표현하며, target·horizon·instrument·session·censoring·label availability·lineage를 동결하지 않는다. 또한 fold 경계만 확인하고 fold별 학습과 검증 예측을 재계산하지 않으므로 전체 자료 정확도를 OOF 증거로 오인할 수 있다.

기존 Goal 원문, 캠페인 원장, 확인자료, 원자료는 수정하지 않는다. V3는 별도 ID·스키마·출력 루트에서 시작하고 기존 캠페인을 `superseded_for_goal_binding_mismatch`로 참조만 한다.

## 3. 검토한 접근

### 3.1 기존 V2용 20행 이진 자료 생성

가장 빠르지만 다섯 상태와 실제 OOF를 검증하지 못한다. 기술적 차단만 숨기므로 사용하지 않는다.

### 3.2 기존 V2 검증기를 제자리에서 확장

기존 `quant-formula-discovery.v2` 의미가 같은 버전명 아래 바뀌어 과거 원장의 재현성이 깨진다. 사용하지 않는다.

### 3.3 V3 병렬 캠페인

정확한 Goal 결박, 다중 target 자료계약, 실제 purged walk-forward OOF, 상태 메모리 수식 계약을 새 버전으로 만든다. 기존 원장과 데이터를 보존하면서 잘못된 결론을 방지하므로 이 접근을 채택한다.

## 4. 아키텍처

### 4.1 Goal 경계

`GoalBindingV3`는 사용자가 제출한 정확한 UTF-8 바이트와 SHA-256을 보존한다. 캠페인 ID는 Goal SHA-256과 preset ID `quant-multistate-discovery.v3`를 함께 해시해 생성한다. Goal 본문을 요약하거나 다시 쓰지 않는다.

### 4.2 연구 질문

`MultiStateFormationQuestion`은 다음 target을 하나의 묶음으로 동결한다.

| target ID | 공식 의미 | 설명용 별칭 |
| --- | --- | --- |
| `upside_acceleration_onset` | 거래 참여를 동반한 상방 가속 시작 | FOMO 형성 |
| `downside_dislocation_onset` | 거래 참여를 동반한 하방 변위 시작 | 패닉 형성 |
| `post_rally_sell_pressure_onset` | 선행 상승 이후 매도압력 시작 | 차익실현 형성 |
| `selloff_reversal_onset` | 선행 하락 이후 반전·정상화 시작 | 회복 형성 |
| `efficient_uptrend_onset` | 비정상 참여 팽창 없이 효율적인 상승 지속 시작 | 상승세 형성 |

각 target은 horizon 1·3·5·10거래일의 onset estimand를 가진다. 다섯 확률은 상호 배타적인 상태확률로 강제하지 않는다. 같은 구간에 복수 형성과정이 겹칠 수 있으므로 multilabel formation hazard로 평가하고, 같은 일봉의 상·하방 선후만 competing path로 보존한다.

### 4.3 데이터 계약

`quant-multistate-development-release.v3`는 다음을 필수로 둔다.

- exact Goal SHA-256, campaign ID, question ID, data-contract ID
- source manifest 경로·SHA-256·sample role·adjustment policy
- instrument ID, session date, feature `available_at`, signal `as_of`
- target ID, horizon, label, `label_available_at`, censoring reason
- 현재 시점 특징과 미래 라벨 입력의 분리된 해시
- 거래소 달력, market proxy, sector proxy, cohort vintage
- fold별 train·purge·validation·embargo 구간
- feature·label·fold·cost 생성 코드 SHA-256
- 결측·OOD·기업행동·거래정지 처리 사유

한 행은 `instrument × session × target × horizon`이다. 현재 특징은 시점 t 종가 확정 뒤 이용 가능하며 미래 가격은 라벨 생성에만 사용한다. censored 행은 음성 라벨로 바꾸지 않는다.

### 4.4 개발 자료

원자료 SSOT는 `.storage/rp-001-data/daily-archives-v1`의 immutable `seen` 캡처다. 원본은 읽기 전용으로 유지한다.

- 48개 주식·시장 ETF·업종 ETF
- 2016-01-01 이후 일봉
- native·adjusted 자료를 별도 정책으로 사용
- SPY·QQQ·IWM을 시장 프록시로 사용
- XLC·XLE·XLF·XLI·XLK·XLP·XLRE·XLU·XLV·XLY·SOXX를 업종 프록시로 사용

현재 보유 자료에는 point-in-time 역사적 업종 구성과 직접 계좌·호가·체결·자기보고가 없다. 따라서 업종 구성 확산은 고정 주식 코호트의 진단값으로만 사용하고, 심리·의도 식별 Gate는 `not_identifiable`로 유지한다.

### 4.5 특징과 상태 메모리

기존 FOMO 명세의 강건 정규화, ATR, 수익률 속도·가속도, 돌파, RVOL, 가격 진전, 위꼬리, 고점 체류, 정상화를 공통 SSOT로 사용한다. 하방 특징은 단순 부호 반전으로 끝내지 않고 하방 gap·저점 돌파·종가 위치·매도 거래량 효율을 별도 가족으로 둔다.

`FormationFeatureVector`는 다음 가족을 분리한다.

- price direction·velocity·acceleration
- abnormal return·volatility·range
- breakout·breakdown·distance·persistence
- volume expansion·persistence·price progress
- market/sector relative return
- fixed-cohort breadth·diffusion
- post-rally overhang·failed breakout
- post-selloff deceleration·reversal·normalization

상태 메모리는 episode·segment·anchor 시점과 진입·유지·이탈 counter를 명시적으로 직렬화한다. 수식 표현과 참조 구현은 같은 입력에서 허용오차 내 동일한 값을 내야 한다.

### 4.6 라벨

라벨은 현재 특징과 독립된 미래 경로 함수로 생성한다.

- 상방 가속: horizon 안에서 상방 ATR 장벽을 먼저 통과하고 이후 모멘텀·거래량 조건이 지속
- 하방 변위: horizon 안에서 하방 ATR 장벽을 먼저 통과하고 약한 종가·거래량 조건이 지속
- 상승 후 매도압력: 사전 고정 run-up 적격 상태 뒤 하방 장벽 또는 돌파 실패가 발생
- 회복: 사전 고정 downside 적격 상태 뒤 상방 반전과 10일 비음수 후속 모멘텀이 확인
- 효율적 상승세: 방향성 효율과 양의 누적수익이 지속되지만 비정상 거래량·가속 Gate는 충족하지 않음

같은 일봉에서 상·하방 장벽을 모두 통과하면 `both_same_bar_ambiguous`로 보존한다. 라벨 선택 규칙과 threshold는 OOF 결과를 보기 전에 동결한다.

### 4.7 실제 OOF

세션 단위 expanding walk-forward를 사용한다. 최대 horizon 10세션만큼 purge하고 10세션 embargo를 둔다. 모든 종목과 target의 같은 session은 같은 fold에 들어가야 한다.

각 outer fold에서 다음 순서를 독립적으로 실행한다.

1. train 구간으로만 normalizer·결측정책·모형계수·threshold를 적합한다.
2. validation 구간을 한 번 예측한다.
3. 예측 행과 fold artifact를 SHA-256으로 고정한다.
4. 모든 fold의 예측을 결합해 multilabel Brier·log loss·PR-AUC·MCC·lead time을 계산한다.

단순 기준선은 상태별 prevalence, 방향성 모멘텀, 돌파·붕괴 단일 특징, 기존 차트 FOMO 0.1.0 점수다. 후보는 같은 적격 행 mask에서 비교한다.

### 4.8 확인자료 경계

현재 `seen` 자료는 개발에만 사용한다. 어떤 부분도 독립 확인자료라고 부르지 않는다. 후보·수식·threshold가 동결된 뒤 신규 사용자 제공 release 또는 이후 시점의 미개봉 forward capture만 single-use confirmation으로 등록한다.

## 5. 오류 처리

- source hash·Goal hash·계약 hash가 다르면 등록을 거부한다.
- `available_at > as_of`, `label_available_at <= as_of`, 미래행 특징 유입을 거부한다.
- history·coverage·분모·기업행동 정책이 부족하면 0 대체 없이 abstain한다.
- target 또는 horizon 일부가 빠지면 가중치 재조정 없이 해당 평가를 unavailable로 둔다.
- 과거 V2 자료를 V3로 자동 승격하지 않는다.
- 확인자료는 freeze 전 읽기 자체를 거부한다.

## 6. 검증

### 6.1 계약 검증

- canonical JSON·SHA-256·일반 파일·허용 루트
- exact Goal과 campaign 결박
- 모든 target·horizon·source lineage 존재
- 중복 row ID, 역전 시각, fold 중첩, purge·embargo 위반 거부

### 6.2 수학 검증

- 가격 단위 스케일 불변성
- 미래행 추가·변경에 대한 시점 t 특징 불변성
- 동일 입력의 수식·참조 구현 등가성
- 상태 전이 허용행렬과 counter 초기화
- 결측 시 unavailable 전파

### 6.3 통계 검증

- 실제 fold별 OOF 예측만 성능 계산에 사용
- target·horizon 다중성 보정
- session·instrument block bootstrap
- calibration·risk–coverage·상태별 lead time
- 단순 기준선 대비 사전 고정 최소효과

## 7. 산출물과 완료 조건

1. exact Goal-bound V3 campaign과 supersession 기록
2. V3 data-contract JSON과 schema validator
3. immutable daily archive reader와 development release builder
4. feature·label·state-memory reference implementation
5. purged walk-forward OOF evaluator
6. canonical development release와 등록 원장 사건
7. 데이터 품질·target coverage·fold 검증 보고서
8. 다음 ActionContract가 데이터 대기가 아닌 연구 실행 상태임을 보이는 controller status

기존 캠페인이나 합성 fixture가 단지 다음 상태로 이동한 것은 완료 증거가 아니다. 위 산출물의 해시와 검증 결과가 모두 일치해야 차단 해결로 판정한다.
