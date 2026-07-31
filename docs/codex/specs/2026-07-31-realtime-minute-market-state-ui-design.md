# 실시간 분봉 시장상태 신호 UI·계산 설계

승인일: 2026-07-31  
상태: 설계 승인·구현 계획 대기  
대상: Neutralino + React 데스크톱 앱

## 1. 목적

수집된 1분 OHLCV와 장중 API 관측을 이용해 다음 다섯 연구 수식을 앱
백엔드에서 재현하고, 완료된 5분봉마다 공식 신호를 갱신한다.

1. FOMO
2. 패닉
3. 차익실현
4. 회복
5. 상승세

가격은 가능한 주기로 더 자주 갱신하되, 시장상태 신호는 완료된 5분봉에서만
확정한다. 예측 신호와 실제 가격 경로로 관측된 생애주기 상태를 분리하고,
사용자가 모든 수치의 의미와 계산 과정을 확인할 수 있게 한다.

이 기능은 OHLCV 기반 reduced-form phenotype을 표시한다. 투자자 심리·주문
동기·향후 수익률을 직접 식별하거나 매수·매도를 권고하지 않는다.

## 2. 결정된 범위

### 2.1 포함

- 완료된 1분봉을 정확히 5개씩 집계한 정규장 5분봉
- 다섯 신호의 현재 백분위와 판정
- 관측된 시장 생애주기 상태
- 카드의 다섯 신호 동시 표시
- 신호별 상세 계산 trace
- 최근 60분 변화선과 당일 전체 세션 이력
- 신규 감지 카드 강조와 앱 내부 알림
- 앱 실행 중 수집과 실행 재개 시 누락 구간 백필
- 연구 수식의 앱 백엔드 이식과 Python 기준 결과 동등성 검증
- 기존 차익실현 휴리스틱의 교체
- 현재 분봉 수집·시점 경계·저장 경쟁 문제의 범위 내 수정

### 2.2 제외

- 진행 중인 5분봉의 잠정 신호
- 매수·매도 추천과 예상 수익률
- 수식 출력의 보정된 발생확률 표현
- 운영체제 알림과 소리
- 앱 종료 중 상주 수집
- 서버 기반 수집
- 여러 날짜를 비교하는 장기 신호 차트
- 자동 재학습과 런타임 계수 변경
- 체결·호가 기반 초단위 또는 sub-second 심리 추론

## 3. 연구 근거와 수식 SSOT

### 3.1 최종 연구 결론

제품 통합의 연구 근거는 다음 두 파일의 바이트와 SHA-256으로 고정한다.

| 파일 | SHA-256 |
| --- | --- |
| `.worktrees/quant-research-minute-v4/research/rp-001/reports/RP001-MINUTE-MULTISTATE-20260723-formula-validation-conclusion.md` | `24b26de9ceb310dc7460eddde7f6639b3ef56f525a9a949afcf599710ba4f09d` |
| `.worktrees/quant-research-minute-v4/research/rp-001/reports/RP001-MINUTE-MULTISTATE-20260723-formula-validation-disposition.json` | `5d8363f26c851c243c38d9676275bd3a61cb2b7836b41ef0674bc5ecae2a7633` |

첫 네 상태의 정확한 `featureNames`, `featureMeans`, `featureScales`,
`ridgeCoefficients`, `intercept`, 보정 임계값, 꼬리비율과 게이트는 다음
artifact의 `audits[0].states[].fixedFormula`가 SSOT다.

| 파일 | SHA-256 |
| --- | --- |
| `.storage/rp-001-data/causal-gated-challenger-historical-audit-v3/causal-gated-challenger-historical-audit-v3.json` | `0aa61bd488f65e7e950e532a0f9a6308495991dee535f6d7d0377221c8b83c25` |

현행 상승세는 위 artifact의 predecessor 상승세 수식을 사용하지 않는다. 다음
동결 계약과 상세 결과에 결박된 `PORTABLE_TREND_QUALITY_SCORE`를 사용한다.

| 파일 | SHA-256 |
| --- | --- |
| `.storage/rp-001-data/uptrend-confirmation-freeze-v1/contract.json` | `06c9126d971013a73435f462e44344d00ce51b1836763bd280287e5c75134247` |
| `.storage/rp-001-data/uptrend-confirmation-results-v1/uptrend-2025-cross-sectional-registered-detail.json` | `c6bf19568e55eccb69747c1ef7dd8b8e50bf1cb87ddf21319010cd8f374b7399` |

통합 현행 formula payload의 연구 SHA-256은
`2ce9e3f48c8437f8f3e218ce39028b81f2279f16fe17bc68111682f7c070e842`,
상승세 단독 payload SHA-256은
`54a5d84b2b4c28a378455e82aeb6bfa22d155dac03c903b0c4511cbb0ac34aff`
이다.

`.storage`와 `.worktrees`는 제품 런타임 입력이 아니다. 구현 단계에서 위
바이트와 해시를 검증해 하나의 불변 production formula payload를 생성하고
추적 가능한 앱 리소스로 커밋한다. production payload에는 연구 원본 해시와
자기 자신의 canonical JSON SHA-256을 모두 기록한다.

payload는 계수 배열뿐 아니라 상태별 horizon·위험상태·게이트·tail share·
안전계수·쿨다운, 33개 고정 target roster와 SPY 역할을 포함한다. 특징 계산과
관측 생애주기 전이는 별도 코드에 암묵적으로 남기지 않고
`featureDefinitionVersion`, `lifecycleDefinitionVersion`과 정확한 연구
source binding SHA-256으로 결박한다. 앱의 formula engine도 독립
`engineVersion`과 source hash를 가지며 Python golden fixture와 함께
production payload의 재현 계약을 이룬다.

### 3.2 사용하지 않는 수식

- 2026-07-13 일봉 V3 계획
- `FrozenFormulaRuntimeV4`의 LANDMARK/FSM/CUSUM 후보 묶음
- 기존 앱의 `profitTakingPressure` 휴리스틱
- historical audit에 남아 있는 안전계수 `2/3`의 predecessor 상승세
- 미래 label 또는 회고적 episode onset을 입력으로 사용하는 코드

### 3.3 공통 점수

상태 \(s\)와 완료 5분봉 \(t\)의 점수는 다음과 같다.

\[
\eta_{s,t}
=
\alpha_s
+
\sum_j
\beta_{s,j}
\frac{x_{j,t}-\mu_{s,j}}{\sigma_{s,j}}
\]

\[
p_{s,t}=\frac{1}{1+e^{-\eta_{s,t}}}
\]

경보 판정과 저장 임계값은 확률 \(p\)가 아니라 log-odds 점수 \(\eta\)를
사용한다. \(p\)는 제품에서 발생확률로 표시하지 않는다.

당일 동적 임계값은 현재 세션과 미래 label을 제외하고 직전 20개 등록
세션의 해당 인과적 위험집합 점수로 계산한다.

\[
\widetilde q_s=a_s q_s
\]

\[
\tau_{s,d}
=
Q_{1-\widetilde q_s}
\left(
\{\eta_{s,u}:u\in d-20,\ldots,d-1\}
\right)
\]

카드 백분위는 같은 직전 20세션 점수집합의 우측 연속 경험적 누적분포로
계산한다.

\[
B_{s,t}
=
100
\frac{
\#\{\eta_{s,u}\le\eta_{s,t}\}
}{
N_{s,d}
}
\]

`B=99.8`은 과거 비교점수의 99.8%보다 높다는 뜻이며 사건 발생확률이
99.8%라는 뜻이 아니다. 카드에서는 소수점 한 자리로 표시하고 상세에서는
계산에 사용한 분자·분모와 원래 정밀도를 제공한다.

### 3.4 상태별 계약

| 표시명 | 연구 ID | 위험 상태 | 목표 | horizon | 특징 | 보조 게이트 |
| --- | --- | --- | --- | ---: | ---: | --- |
| FOMO | `FOMO_LIKE` | `BASELINE` | 상방 price passage | 6봉·30분 | 22 | `PressureMean_3 > 0` |
| 패닉 | `PANIC_LIKE` | `BASELINE` | 하방 price passage | 6봉·30분 | 36 | 없음 |
| 차익실현 | `PROFIT_TAKING_PROXY` | `AFTER_UP` | 상승 후 retracement | 6봉·30분 | 22 | 없음 |
| 회복 | `PERSISTENT_RECOVERY` | `AFTER_DOWN` | 하락 후 recovery | 6봉·30분 | 22 | 없음 |
| 상승세 | `EFFICIENT_UPTREND` | `BASELINE` | 역행이 작은 지속 상승 | 12봉·60분 | 1 | `RelativeVolume > 1` |

| 상태 | calibration tail \(q_s\) | 안전계수 \(a_s\) | 감지 기준 백분위 |
| --- | ---: | ---: | ---: |
| FOMO | `0.003044903968413304` | `0.8` | 약 `99.756` |
| 패닉 | `0.0017734056079769791` | `1.0` | 약 `99.823` |
| 차익실현 | `0.011899416255051639` | `0.8` | 약 `99.048` |
| 회복 | `0.02947695035460993` | `0.5` | 약 `98.526` |
| 상승세 | `0.0030354497163299966` | `1.0` | 약 `99.696` |

위 백분위는 빠른 해석을 위한 표시 기준이다. 최종 판정은 정확한
\(\eta\ge\tau_{s,d}\), 위험 상태와 게이트를 모두 적용한다.

### 3.5 현행 상승세

\[
M_t
=
\operatorname{clip}
\left(
\frac{r^{res}_{t,3}}{\sqrt 3\,RV_{t,6}},
-8,
8
\right)
\]

\[
T_t
=
\frac{
\tanh(M_t/2)
+
Efficiency_{t,6}
+
\tanh(PressureMean_{t,3})
}{3}
\]

\[
\eta_{UP,t}
=
-0.029831931438622377
+
0.17602169948270716
\frac{
T_t-(-0.014638577473975942)
}{
0.32331193229646277
}
\]

상승세는 현재 거래량이 직전 40개 완전 세션의 동일 5분 bucket 거래량
중앙값보다 큰 경우에만 감지한다.

## 4. 의미 경계

### 4.1 전조와 형성 중

연구의 회고적 적중 분류는 다음과 같다.

| 상태 | strict-pre-onset | in-formation |
| --- | ---: | ---: |
| FOMO | 18.5% | 81.5% |
| 패닉 | 6.8% | 93.2% |
| 차익실현 | 96.2% | 3.8% |
| 회복 | 99.6% | 0.4% |
| 상승세 | 5.6% | 94.4% |

회고적 onset은 feature, 위험집합, 임계값과 live 판정에 사용하지 않는다.
따라서 live 화면은 적중 전에 `strict-pre-onset`과 `in-formation`을 구별하지
않는다. FOMO·패닉·상승세는 `형성 감지`, 차익실현·회복은 조건부 `조짐`으로
설명한다.

### 4.2 예측과 관측의 분리

예측 신호는 다섯 formula evaluation이다. 관측 상태는 시점 \(t\)까지 실제로
확인된 가격 경로의 상태다.

| 내부 관측 상태 | 표시명 |
| --- | --- |
| `BASELINE` | 방향성 확인 전 |
| `AFTER_UP` | 상승 확인 후 |
| `AFTER_DOWN` | 하락 확인 후 |
| visible normalization transition | 기준 구간 복귀 |
| `UNAVAILABLE` | 데이터 부족 |

상방 사건 확인 뒤 `AFTER_UP`, 하방 사건 확인 뒤 `AFTER_DOWN`으로 이동한다.
상승 후 되돌림 확인은 `AFTER_DOWN`, 하락 후 회복 확인은 `AFTER_UP`으로
전환될 수 있다. `BASELINE` 복귀는 시점 \(t\)에서 보이는 정상화·경쟁 사건·
censor·종료 규칙으로만 결정한다.

점수가 임계값 아래로 내려간 것은 `현재 미감지`일 뿐 `해소`가 아니다.
관측 상태 전환도 투자자 심리의 해소로 표현하지 않는다.

## 5. UI 설계

### 5.1 종목 카드

카드는 실시간 가격과 공식 5분 신호의 시각을 분리한다.

```text
NVDA                         $124.52
실시간 가격                    +1.24%

심리·시장 신호             10:35 확정
FOMO       99.8  감지
패닉       72.4  미감지
차익실현     —   대상 아님
회복         —   대상 아님
상승세     91.3  미감지

관측 상태 · 방향성 확인 전
```

다섯 신호는 `FOMO → 패닉 → 차익실현 → 회복 → 상승세` 순서로 고정하고,
좁은 카드에서는 3개+2개 grid로 배치한다. 각 셀은 버튼이며 이름, 백분위,
판정을 항상 함께 표시한다.

### 5.2 신호 판정

| 표시 | 조건 |
| --- | --- |
| `감지` | 위험 상태가 적격이고 점수·임계값·게이트를 모두 충족 |
| `미감지` | 위험 상태가 적격이며 계산됐지만 최종 조건 미충족 |
| `대상 아님` | 현재 위험 상태에서 해당 formula를 평가하지 않음 |
| `수집 중` | 필요한 API 백필 또는 현재 bucket 동기화가 진행 중 |
| `계산 불가` | 인증·데이터·수식·품질 계약 위반으로 계산할 수 없음 |

`대상 아님`, `수집 중`, `계산 불가`에는 백분위를 표시하지 않는다. 높은
백분위라도 게이트가 실패하면 `미감지`이며 상세에 실패 이유를 표시한다.

### 5.3 현재·최근 감지

- 최신 완료 5분봉이 조건을 만족하면 `감지`
- 연속 감지 중에는 `10:35부터 감지`
- 조건을 벗어나면 즉시 `미감지`
- 미감지 뒤에는 `최근 감지 10:45`
- 최근 감지 기록은 해당 거래세션 동안 유지
- 새 거래세션의 카드 표시에서는 초기화
- 세션 이력 저장소에는 원래 시각을 보존

### 5.4 상세 설명

신호 셀 또는 `?` 버튼은 선택 신호의 상세 패널을 연다. 기본 공개 순서는
다음과 같다.

1. 현재 판정
2. 점수를 높이거나 낮춘 상위 요인
3. 최근 60분 변화선
4. 전체 입력값과 계수
5. 정확한 수식
6. 연구 근거와 한계

현재 판정에는 다음 값을 표시한다.

- 백분위와 경험적 CDF 분자·분모
- 원점수 \(\eta\)
- 당일 동적 임계값 \(\tau_d\)
- 임계 대비 거리 \(\eta-\tau_d\)
- 현재 위험 상태와 요구 위험 상태
- 게이트의 원수치·연산자·임계값·통과 여부
- horizon
- 마지막 완료 5분봉
- `asOf`, 입력 generation, formula version과 payload hash

전체 계산표는 모든 특징에 대해 다음 열을 제공한다.

| 열 | 의미 |
| --- | --- |
| \(x_j\) | 현재 원수치 |
| \(\mu_j\) | 동결 수식의 특징 평균 |
| \(\sigma_j\) | 동결 수식의 특징 척도 |
| \(z_j\) | 표준화값 |
| \(\beta_j\) | 동결 ridge 계수 |
| \(\beta_jz_j\) | 최종 점수 기여 |

절편과 모든 기여의 합이 저장된 \(\eta\)와 일치해야 한다. 기본 화면에는
절댓값 기준 상위 기여 요인을 보여주고 전체 22개·36개 행은 접어둔다.
각 원수치에는 단위와 자연어 해석을 붙인다. `signed volume pressure` 같은
proxy는 실제 매수자·매도자 신원으로 설명하지 않는다.

### 5.5 변화선

- 기본 범위: 최근 12개 완료 5분봉, 즉 60분
- 확장 범위: 현재 거래세션 전체
- 표시값: 백분위
- 함께 표시: 당일 감지 임계선, 감지 bucket, 데이터 공백
- 점수 하락 표현: `약화`
- 금지 표현: `해소`, `정상 복귀`의 예측적 사용

새 범용 차트 라이브러리를 도입하지 않고 작은 SVG 시계열 컴포넌트를
사용한다. 데이터 이력이 없으면 선을 추정하지 않고 명시적 빈 상태를 보인다.

### 5.6 접근성

- 신호 셀과 `?`는 키보드로 접근 가능한 실제 `button`
- 판정은 색만이 아니라 텍스트와 아이콘으로 함께 표현
- 숫자는 `tabular-nums`
- 신규 감지 앱 알림은 `aria-live="polite"`
- 실시간 가격 갱신은 매번 screen reader에 강제 공지하지 않음
- `prefers-reduced-motion`에서는 카드 강조 애니메이션 제거
- Neutralino 최소 창 폭 920px에서 다섯 신호가 잘리거나 겹치지 않아야 함

## 6. 시간과 알림

### 6.1 공식 갱신

- 가격: 기존 장중 polling과 독립적으로 갱신
- 공식 신호: 완료된 5분봉을 수락한 뒤 한 번 평가
- 정상 목표: 5분봉 종료 뒤 30초 이내 게시
- 30초 초과: `갱신 지연`
- 60초 초과 또는 필수 관측 누락: 해당 신호 `수집 중`

실시간 가격과 공식 신호는 서로 다른 generation과 시각을 가질 수 있으며
카드에 각각의 기준시각을 표시한다. 다만 하나의 공식 신호를 계산한 모든
종목·SPY·횡단면 입력은 동일한 `sourceGenerationId`와 `asOf`로 원자 결박한다.
renderer는 실시간 가격의 generation을 공식 신호의 입력 generation으로
오인하거나 두 시각을 하나의 `최신` 시각으로 합쳐 표시하지 않는다.

### 6.2 재알림

현재 판정과 알림 event는 분리한다. 카드의 `감지/미감지`는 매 완료 5분봉마다
갱신한다.

연구 구현과 동일하게 마지막 알림 bucket과 현재 bucket의 차이가 `<= 6`이면
새 알림을 억제한다. 따라서 후속 6개 bucket을 모두 막고 7번째 bucket부터
허용한다. 종점 기준 최소 간격은 35분이다.

새 알림은 다음으로 제한한다.

- 카드 한 번 강조
- 앱 내부 알림
- 동일 `instrument + signal + session + bucket + formulaVersion` 중복 금지

소리와 운영체제 알림은 사용하지 않는다.

## 7. 데이터 계약

### 7.1 필요한 이력

- 특징 정규화: 엄격한 과거 40개 완전 세션의 동일 5분 bucket
- 동적 임계값: 특징 계산이 가능한 직전 20개 등록 세션
- 신규 종목의 오늘 계산: 최소 60개 이전 완전 세션
- 시장 proxy: SPY
- 패닉 횡단면: 2026 개발 formula release의 33개 target 고정 roster

고정 target roster는 사용자의 관심종목과 분리한다. 사용자가 카드를
추가·삭제해도 패닉 점수 정의는 바뀌지 않는다. production formula
payload에 정확한 정렬 roster와 roster SHA-256을 한 번만 저장하고 다른
설정에 복제하지 않는다.

SPY는 별도 시장 proxy이며 33개 target의 coverage 분모에 포함하지 않는다.
고정 target roster 자체의 연구 불변조건은 최소 10개다. 패닉 횡단면 계산은
동일 endpoint에서 관측된 target이 최소 5개이면서 고정 roster의 80% 이상일
때만 허용한다. 충족하지 못하면 패닉만 `수집 중` 또는 `계산 불가`로 두고
다른 준비된 신호는 계속 표시한다.

### 7.2 1분봉

각 canonical 1분봉은 최소 다음 필드를 가진다.

- instrument ID
- exchange session date
- minute bucket
- `barStart`
- `barEnd`
- OHLCV
- provider event time
- `receivedAt`
- `availableAt=max(barEnd, receivedAt)`
- source request ID
- provider revision identity
- canonical content hash

동일 instrument·session·minute의 provider 수정본은 lineage를 보존하고
현재 canonical revision을 명시한다. 입력은 항상 timestamp 정렬 후
중복 제거한다.

### 7.3 5분봉

정규장 동일 5분 구간에 속한 완료 1분봉 5개가 모두 있어야 생성한다.

- open: 첫 1분봉 open
- high: 다섯 high의 최댓값
- low: 다섯 low의 최솟값
- close: 마지막 1분봉 close
- volume: 다섯 volume의 합
- `availableAt`: 다섯 1분봉 `availableAt`의 최댓값
- source hash: 정렬된 다섯 canonical content hash의 결합 해시

한 봉이라도 없으면 보간하거나 0으로 대체하지 않는다. late revision이
오면 영향받는 5분봉과 이후 현재 세션 feature를 결정적으로 재계산하되
동일 알림 idempotency key로 중복 알림을 막는다.

## 8. 수집 설계

### 8.1 수명주기

- 앱 실행 중에만 수집
- 시작 시 로컬 coverage와 체크포인트 검사
- 빠진 세션·분봉만 API pagination으로 백필
- 이미 검증된 canonical 분봉은 다시 받지 않음
- 장중에는 완료된 새 1분봉을 증분 수집
- 종료 중 공백은 다음 실행 시 보충

백필은 5초 renderer IPC 응답 안에서 완료하려 하지 않는다. backend-owned
job으로 실행하고 UI에는 job ID, 상태, 수집 세션 수와 필요한 세션 수를
반환한다.

### 8.2 우선순위

1. 현재 선택 종목과 SPY
2. 화면에 보이는 관심종목
3. 나머지 활성 관심종목
4. 패닉 고정 기준 종목군

다섯 신호는 dependency가 준비되는 즉시 개별적으로 활성화한다. 패닉 기준
종목군 백필이 끝날 때까지 다른 네 신호를 기다리지 않는다.

수집기는 provider rate limit을 지키는 제한된 동시성 queue를 사용한다.
일시 오류만 제한적으로 재시도하고, 인증·입력·permission 오류는 같은
요청을 무한 반복하지 않는다.

### 8.3 저장

canonical 분봉은 repository interface 뒤에 instrument·session 단위로
분할 저장한다. 첫 구현은 현재 Neutralino 배포에 native DB 의존성을
추가하지 않는 atomic JSON partition과 manifest index를 사용한다.

- temp file 작성 후 atomic rename
- instrument·session partition별 직렬 쓰기
- 전체 read-modify-write 구간에 lock 적용
- content hash와 revision 기록
- 전체 snapshot 500개 같은 전역 cap을 분봉 보존정책으로 사용하지 않음

formula snapshot과 세션 history는 canonical 분봉과 별도 repository에
저장한다.

## 9. 애플리케이션 경계

### 9.1 Domain

- `MarketStateSignal`
- `ObservedMarketState`
- `SignalEligibility`
- `SignalDetection`
- `FormulaVersion`
- `CompletedMinuteBar`
- `CompletedFiveMinuteBar`
- `DetectionCooldown`

수식, 위험 상태, 게이트, 판정, 쿨다운 규칙은 domain에 둔다. React,
Neutralino, filesystem, API 타입을 domain에 노출하지 않는다.

### 9.2 Application

- 누락 minute history 백필
- canonical minute 수락
- 완료 5분봉 조립
- formula dependency readiness 평가
- 다섯 상태 계산
- 현재·최근 감지와 알림 event 기록
- summary·history·explanation 조회

application service는 orchestration만 담당하고 계수나 판정 규칙을
복제하지 않는다.

### 9.3 Infrastructure

- Toss REST adapter
- exchange calendar와 clock
- canonical minute repository
- formula snapshot repository
- immutable formula payload loader
- Neutralino request·broadcast adapter

API 응답 경계에서 `receivedAt`을 기록한다. 수집 결과 저장과 formula
평가는 같은 source generation으로 결박한다.

### 9.4 Presentation

renderer는 다음 세 계약만 소비한다.

1. 카드용 다섯 신호 summary
2. 신호별 explanation trace
3. 신호별 당일 history

이 세 계약은 기존 `QuantIndicatorSnapshot`에 선택 필드를 덧붙이지 않고
별도의 `MarketStateFormulaSnapshot` aggregate로 정의한다. 이벤트 이름은
`contracts/app-runtime-contract.json`, TypeScript payload 타입과 경계
validator는 `src/shared/contracts/app-runtime-contract.ts`를 SSOT로 삼는다.
extension의 CJS 객체 생성 결과도 같은 validator와 contract fixture를
통과해야 하며 renderer에서 검증되지 않은 payload를 type cast로 수락하지
않는다.

카드 polling 응답에 22개·36개 전체 기여표를 반복 전송하지 않는다.
상세 trace는 선택한 snapshot과 신호에 대해 요청한다.

## 10. 결과 계약

카드 summary snapshot은 최소 다음 의미를 가진다.

```text
snapshotId
instrumentId
sessionDate
asOf
evaluatedAt
publishedAt
latencyMs
sourceGenerationId
sourceInputHash
formulaVersion
engineVersion
engineSourceSha256
researchFormulaPayloadSha256
productionFormulaPayloadSha256
observedState
freshness
signals[5]
```

`asOf`와 `sourceGenerationId`는 공식 신호의 다종목 입력 세대를 나타낸다.
더 자주 갱신되는 실시간 가격 snapshot의 generation·시각과 같을 필요는 없다.

각 signal summary는 최소 다음 의미를 가진다.

```text
signalId
displayName
status
percentile
rawScore
dynamicThreshold
thresholdDistance
requiredRiskState
currentRiskState
gateStatus
horizonBars
horizonMinutes
currentDetectionStartedAt
lastDetectedAt
lastNotifiedBucket
dataQuality
```

`percentile`, `rawScore`, `dynamicThreshold`, `thresholdDistance`는 계산되지
않은 상태에서 `0`을 사용하지 않고 명시적 optional 값으로 둔다.
감지 이력과 알림 상태는 수학 판정과 별도 하위 객체로 묶어 현재 판정,
재알림 가능 시각과 쿨다운 잔여 봉 수를 독립적으로 표현한다.

explanation trace에는 feature별 \(x,\mu,\sigma,z,\beta,\beta z\), 절편,
합계, threshold history identity, gate 원수치, 자연어 해석과 연구 한계를
포함한다.

## 11. 기존 앱 변경

### 11.1 교체

기존 `profitTakingPressure` 휴리스틱과 전용 차익실현 리스크 표시는 새
`PROFIT_TAKING_PROXY` 결과로 교체한다. 두 값을 병렬 노출하지 않는다.
기존 캐시를 새 formula 결과로 승격하지 않는다.

교체 범위에는 기존 4원인 가중합, 숨은 점수 하한, 전용 explanation trace,
`marketSentimentScore`, 카드 decision·quality와 대표신호 우선순위에 대한
의존성도 포함한다. `AFTER_UP`에서만 적격인 새 formula를 기존 0~100
severity처럼 대입하지 않고, 기존 휴리스틱 의존을 제거한 뒤 각 소비자의
의미를 별도로 재정의한다.

### 11.2 필수 선행 수정

- candle TTL을 snapshot `capturedAt`이 아니라 candle fetch/revision 시각으로 계산
- 매 polling 때 snapshot 시각이 바뀌어도 candle refresh deadline은 보존
- formula 입력에서 `eventAt<=asOf`와 `availableAt<=asOf` 강제
- timestamp 정렬·중복 제거·revision 선택
- market snapshot과 formula source generation 일치 검사
- 겹치는 refresh의 저장 read-modify-write 직렬화
- 대량 백필을 renderer의 5초 request timeout에서 분리

이 수정 없이 formula UI만 추가하는 것은 완료로 보지 않는다.

## 12. 오류 처리

| 실패 | 처리 |
| --- | --- |
| 일시 API 오류 | 제한된 backoff 재시도, checkpoint 유지 |
| rate limit | provider 지시 또는 정책 지연 후 재개 |
| 인증 오류 | 즉시 중단하고 설정 확인 표시 |
| 특정 minute 누락 | 해당 구간만 재요청 |
| 5분봉 불완전 | 보간 없이 `수집 중` |
| 기준 이력 부족 | 확보 세션 수와 60세션 목표 표시 |
| 패닉 roster coverage 부족 | 패닉만 unavailable |
| formula hash·schema 불일치 | 전체 formula 계산 차단 |
| source generation 불일치 | 가격과 신호 결합 금지 |
| 늦은 revision | 영향 구간 재계산, 중복 알림 금지 |
| 앱 재시작 | 마지막 durable checkpoint부터 재개 |

마지막 정상 계산은 상세 화면에 시각과 함께 보존하지만 현재값으로
표시하지 않는다.

## 13. 검증

### 13.1 Formula 동등성

Python 연구 구현에서 만든 golden fixture로 다음을 대조한다.

- 22개·36개·1개 feature raw value
- 표준화값
- feature contribution
- 절편과 \(\eta\)
- 직전 20세션 quantile과 백분위
- 위험 상태와 게이트
- 최종 감지 판정
- cooldown

JavaScript와 Python의 부동소수점 허용오차를 계약에 명시하고, 임계값
경계 fixture는 판정 결과가 exact 동일해야 한다.

### 13.2 인과성과 데이터

- 미래 봉을 추가해도 과거 snapshot 불변
- `availableAt>asOf` 행 거부
- 역순 입력과 중복 입력의 결과 불변
- revision lineage와 결정적 canonical 선택
- 정확한 1분봉 5개 외에는 5분봉 미생성
- 40세션·20세션 경계와 현재 세션 제외
- SPY 누락 처리
- 패닉 roster 80% 경계
- 앱 재시작 후 gap-only 백필
- 반복 polling 뒤 candle이 실제로 갱신됨
- 겹치는 foreground poll과 background backfill 저장에도 update 유실이 없음

### 13.3 상태와 알림

- 위험 상태별 `대상 아님`
- 감지→미감지 즉시 전환
- 연속 감지 시작시각
- 세션 내 마지막 감지 보존과 다음 세션 카드 초기화
- 후속 6봉 알림 억제
- 7번째 봉 알림 허용
- 동일 bucket revision의 중복 알림 방지

### 13.4 UI

- 카드에 다섯 신호·수치·판정이 모두 표시됨
- 920px 최소 창에서 잘림·겹침 없음
- 상세 trace 합계와 summary 점수 일치
- 최근 60분과 당일 전체 이력
- 키보드 조작과 focus 복귀
- 색상 없이도 판정 식별 가능
- reduced motion
- 카드 강조와 내부 알림 1회
- stale·수집 중·계산 불가 상태

### 13.5 통합 성능

fake clock과 provider adapter를 사용해 정상 응답 조건에서 완료 5분봉 뒤
30초 이내 formula snapshot이 renderer에 게시되는지 검증한다. 30초와
60초 경계의 표시도 결정적 시간으로 테스트한다.

## 14. 완료 기준

다음 조건을 모두 만족해야 구현 완료다.

1. production formula payload가 연구 원본 해시와 결박된다.
2. 다섯 상태의 Python↔앱 동등성 fixture가 통과한다.
3. 미래행·중복·역순·revision 반례가 통과한다.
4. 앱 실행 중 자동 수집과 재시작 gap 백필이 동작한다.
5. 준비된 신호부터 개별적으로 표시된다.
6. 카드에 다섯 백분위와 판정이 한눈에 보인다.
7. 관측 상태가 예측 신호와 분리된다.
8. 상세 패널에서 모든 숫자와 수식을 재현할 수 있다.
9. 최신 판정·최근 감지·알림 cooldown이 서로 독립적으로 동작한다.
10. 기존 차익실현 휴리스틱이 새 연구 수식으로 교체된다.
11. stale 데이터를 현재값으로 표시하지 않는다.
12. 정상 조건에서 5분봉 종료 뒤 30초 이내 갱신된다.
13. 관련 domain·application·infrastructure·renderer 테스트와 typecheck가 통과한다.

## 15. 연구 한계 표시

상세 패널에는 다음 문구와 근거를 축약 없이 접근 가능하게 둔다.

- FOMO·패닉·차익실현은 제품상 이름이며 심리나 동기를 직접 측정하지 않는다.
- FOMO·패닉·상승세는 주로 결과 확인 전의 형성 중 구간을 감지했다.
- 차익실현·회복은 조건부 후속 위험집합에서 대부분 회고적 onset 전에 감지됐다.
- 표시 백분위와 sigmoid 값은 개별 사건 발생확률이 아니다.
- 개발·감사·확인은 완전한 종목축·시간축 동시 미관측 검증이 아니다.
- 이 신호는 실전 수익성, 주문 실행 또는 투자 권고로 검증되지 않았다.

이 한계는 `?` 상세 화면의 연구 근거 섹션에서 항상 확인할 수 있어야 한다.
