# 주식 포모 시장 상태 정량 관찰 명세

## OHLCV 기반 점화·확산·소진·해소 지표와 상태 전이

## 1. 문서 정체성

| 항목 | 내용 |
| --- | --- |
| 문서 유형 | 독립 정량 관찰 명세 |
| 버전 | 0.1.0 |
| 기준일 | 2026-07-13 |
| 연구 지위 | 검증 전 고정 후보 |
| 기본 관찰 주기 | 일봉 |
| 핵심 입력 | 수정 OHLCV, 시장·업종·구성 종목 OHLCV |
| 핵심 출력 | 중립 점수, 점화 점수, 진행 점수, 해소 점수, 시장 상태, 전이 사유 |
| 상태 집합 | 중립, 기타 비정상, 포모 시작 전, 포모 진행, 포모 해소, 산출 불가 |

이 문서는 주식 포모를 유발하고 유지하며 해소하는 시장 상태를 가격·거래량·시장 확산의 관측값으로 조직화한다. 공식 산출물은 OHLCV 추격상승 프록시 국면이며 심리적 포모 자체, 매수 권고, 매매 전략과 수익 보장은 출력하지 않는다.

기존 포모 문서, 수식 감사 보고서, 연구 프로토콜을 대체하거나 수정하지 않는다. 이 문서에서 정의하는 후보 모델과 상태 계약은 이 파일 안에서만 완결된 독립 명세다.

## 2. 제목과 문서 구성 원칙

문서 제목은 **주식 포모 시장 상태 정량 관찰 명세**로 정한다. 제목에는 다음 세 가지 범위가 모두 드러난다.

1. 대상은 일반적인 사회 현상이 아니라 주식시장이다.
2. 관찰 대상은 개인의 감정 자체가 아니라 시장 상태다.
3. 결과물은 설명문이 아니라 재현 가능한 정량 명세다.

내용은 대화나 발견 순서가 아니라 다음 의존 순서로 구성한다.

1. 관찰하려는 현상과 단계 정의
2. 개념과 관측값의 대응
3. 데이터와 시점 계약
4. 공통 수학 연산
5. 원자 지표
6. 합성 특징과 점수
7. 상태 진입·유지·이탈
8. 해소 유형과 재점화
9. 결측·경계·데이터 품질
10. 검증과 출력 계약
11. 비차트 확장 지표

## 3. 핵심 정의

### 3.1 주식 포모

주식 포모는 투자자가 주가 상승을 관찰한 뒤 추가 상승 기회를 놓칠 수 있다는 압박 때문에 원래 계획보다 늦고 급하게 추격 매수하는 현상이다.

시장 데이터에서는 다음 자기강화 구조를 관찰 대상으로 삼는다.

\[
\text{가격 상승}
\rightarrow
\text{거래 참여 증가}
\rightarrow
\text{상승 종목 확산}
\rightarrow
\text{추가 가격 상승}
\]

### 3.2 포모 시장 상태

포모 시장 상태는 설명을 위한 별칭이다. 공식적으로는 다음 조건이 결합된 OHLCV 추격상승 프록시 국면을 뜻한다.

\[
\text{비정상 가격 상승}
+
\text{상승 가속}
+
\text{거래 참여 팽창}
+
\text{고점 추격}
+
\text{업종·후발주 확산}
\]

### 3.3 공식 출력명과 설명용 상태명

OHLCV만으로 산출하는 시스템 출력에는 심리명 대신 가격·거래량 국면명을 사용한다. 설명 화면에서는 대응되는 포모 상태명을 별칭으로 표시할 수 있지만, 별칭에는 가격·거래량 프록시라는 표시를 함께 둔다.

| 설명용 상태명 | 공식 출력명 |
| --- | --- |
| 중립 | price_volume_regime.baseline |
| 기타 비정상 | price_volume_regime.other_abnormal |
| 포모 시작 전 | price_volume_regime.pre_upside_acceleration |
| 포모 점화 사건 | price_volume_regime.upside_breakout_onset |
| 포모 진행 | price_volume_regime.upside_momentum_continuation |
| 포모 해소 | price_volume_regime.upside_momentum_exhaustion |
| 완전 정상화 | price_volume_regime.post_event_normalization |
| 산출 불가 | unavailable |

포모 점화는 독립적인 장기 상태가 아니라 포모 시작 전에서 포모 진행으로 넘어가는 전이 사건이다.

## 4. 단계 모델

### 4.1 중립

가격, 거래량, 변동성, 시장 확산이 각 종목의 평상시 범위에 있다. 점화·진행·해소 조건이 어느 쪽으로도 충분히 누적되지 않은 기준 상태다.

### 4.1.1 기타 비정상

중립 기준선에서 벗어났지만 상승 점화 조건을 충족하지 않은 상태다. 급락, 하방 변동성 확대, 거래정지 전후 충격, 비방향성 고변동처럼 포모 상태기계 밖의 비정상 국면을 중립으로 잘못 분류하지 않기 위해 둔다.

### 4.2 포모 시작 전

가격과 거래량이 먼저 움직이고 상승 속도가 빨라지거나 고점 돌파가 시작된다. 대장주 또는 일부 종목에 움직임이 집중되어 있으며 업종 전체와 후발주로의 확산은 아직 제한적이다.

### 4.3 포모 진행

가격 상승과 거래량 팽창이 동시에 강하고, 가격이 고점 부근에 머물며, 상승 참여가 업종과 후발주로 확산된다. 가격 상승이 새로운 참여를 만들고 참여 증가가 다시 가격을 밀어 올리는 자기강화 구간이다.

### 4.4 포모 해소

추가 거래량이 더 이상 같은 크기의 가격 상승을 만들지 못한다. 상승 가속도 둔화, 돌파 실패, 긴 위꼬리, 약한 종가, 음의 비정상 수익률, 상승 확산 축소가 나타난다.

해소는 세 가지 경로를 가진다.

1. **가격 조정:** 가격이 빠르게 하락한다.
2. **기간 조정:** 가격은 크게 하락하지 않지만 모멘텀과 거래량이 정상화된다.
3. **재점화:** 해소 도중 거래량을 동반해 이전 고점을 다시 돌파한다.

## 5. 포모 발생 조건과 관측값 대응

| 발생 조건 | 차트 기반 핵심 관측값 | 차트 밖에서 필요한 값 |
| --- | --- | --- |
| 단기간 급등 | 기간 수익률, 수익률 이상도, 초과수익률, 상승 속도, 상승 가속도, 장대양봉, 신고가 돌파 | 없음 |
| 거래량과 참여 급증 | 상대 거래량, 거래량 이상도, 거래량 지속성, 거래대금, 거래 회전율 | 정확한 참여자 수와 계좌 수 |
| 강한 상승 서사 | 차트 핵심 모델에서는 사용하지 않음 | 뉴스량, 검색량, 주제 반복성, 감성 |
| 주변 종목 동반 상승 | 상승 종목 비율, 급등 종목 비율, 신고가 비율, 후발주 확산, 수익률 집중도 | 정확한 테마 분류가 필요할 수 있음 |
| 상승을 놓쳤다는 압박 | 누적 상승폭, 얕은 최대 낙폭, 고점 체류도, 추세 효율성 | 개인의 최초 조회·관심 등록·과거 매도 가격 |
| 사전 매수 기준 부재 | 차트만으로 관찰하지 않음 | 목표 매수가, 손절 조건, 사전 계획, 주문 전 분석 기록 |
| 즉시 결정 압박 | 시가 갭, 상승 속도·가속도, 장중 범위, 고점 갱신 빈도 | 체결 속도, 호가 소진, 가격 제한폭 접근 |

이 대응표는 처음 제시된 일곱 조건을 모두 보존하면서, 핵심 모델에 들어가는 차트 관측값과 별도 데이터가 필요한 개념을 분리한다.

## 6. 관찰 계층

### 6.1 핵심 계층: 단일 종목 OHLCV

단일 종목 차트로 계산한다.

- 수익률과 비정상 수익률
- 상승 속도와 가속도
- ATR과 변동성
- 고점 돌파와 가격 위치
- 이동평균 이격
- 갭과 봉 구조
- 상승 지속성
- 런업, 낙폭, 추세 효율성
- 상대 거래량과 거래량 지속성
- 가격·거래량 결합 및 소진

### 6.2 확산 계층: 시장·업종 지수와 구성 종목별 OHLCV

시장과 업종 구성 종목의 차트를 함께 사용한다.

- 상승 종목 비율
- 시장 초과 상승 종목 비율
- 급등·신고가 종목 비율
- 상승 확산 속도와 가속도
- 대장주와 후발주의 수익률 차이
- 대장주 편중과 후발주 확산
- 업종 수익률 집중도와 동조화

### 6.3 확장 계층: 체결·호가·투자자·행동 데이터

다음 값은 개념 원장에 남기지만 핵심 점수에는 넣지 않는다.

- 공격적 매수 비율
- 체결 불균형과 CVD
- 개인투자자 순매수와 추격 매수
- 호가 잔량 불균형과 매도호가 소진
- 개인별 놓친 상승폭과 계획 없는 매수
- 뉴스·검색·커뮤니티 관심도와 상승 서사

## 7. 데이터 계약

### 7.1 기본 표기

관찰 대상 종목을 \(i_0\)라고 하고, 시점 \(t\)의 일봉을 다음과 같이 정의한다.

\[
O_t=\text{시가},\quad
H_t=\text{고가},\quad
L_t=\text{저가},\quad
C_t=\text{종가},\quad
V_t=\text{거래량}
\]

시장 로그수익률은 \(r_{m,t}\), 업종 로그수익률은 \(r_{g,t}\), 업종 \(g\)의 공식 시점별 구성 종목 집합은 \(\mathcal{G}_{g,t}\)로 쓴다.

시점 \(t\)의 유효 횡단면 집합:

\[
G_{g,t}
=
\left\{
i\in\mathcal{G}_{g,t}:
\text{시점 }t\text{와 해당 지표 lookback의 필수 자료가 유효}
\right\}
\]

\[
GroupCoverage_{g,t}
=
\operatorname{safeRatio}
\left(
|G_{g,t}|,
|\mathcal{G}_{g,t}|
\right)
\]

모든 확산 지표의 분모는 \(G_{g,t}\)다. \(GroupCoverage_{g,t}<0.80\)이거나 \(|G_{g,t}|<5\)이면 해당 확산 지표를 산출하지 않는다.

### 7.2 필수 데이터

| 데이터 | 용도 |
| --- | --- |
| 수정 OHLC | 모든 가격 지표 |
| 기업행동과 단위가 일관된 거래량 | 거래량·거래대금 지표 |
| 시장지수 OHLCV | 시장 초과수익률 |
| 업종지수 OHLCV | 업종 초과수익률 |
| 시점별 공식 업종 구성 종목과 각 구성 종목 OHLCV | 유효 횡단면, 확산도와 후발주 지표 |
| 거래소 세션 달력 | lookback과 연속 거래일 판정 |

### 7.3 시점 계약

1. 시점 \(t\)의 일봉 특징과 상태는 \(t\) 종가 확정 뒤 산출한다.
2. 이동 기준선은 특별히 명시하지 않는 한 현재 봉을 제외한 \(t-1\) 이전 자료로 계산한다.
3. 상태 전이는 확인 조건이 충족된 당일에 기록하며 과거 시점으로 소급하지 않는다.
4. 미래 가격은 검증 라벨에만 사용한다.
5. 업종 구성 종목은 현재 구성을 과거에 소급하지 않고 당시 구성을 사용한다.
6. 시가 갭은 \(t\)일 시가에 관측되지만 이 명세의 상태 판정에는 \(t\)일 종가 확정 뒤 반영한다.
7. 각 봉에는 거래소 기준 bar_end, 공급자 확정시각, 실제 수신시각, revision ID를 기록한다.
8. 공급자 정정이나 backfill은 기존 산출물을 조용히 덮어쓰지 않고 새 data revision으로 재계산한다.
9. 원자료와 정제자료의 버전·해시·변환 버전을 상태 출력에 연결한다.

### 7.4 가격·거래량 단위

1. 가격은 분할과 배당 정책이 일관된 수정주가를 사용한다.
2. 거래량은 공급자의 기업행동 조정 계약을 확인한다.
3. 가격이 수정됐지만 거래량 단위가 분할 전후로 일관되지 않으면 거래량 기반 특징은 결측으로 처리한다.
4. 통화 단위에 민감한 가격 차이는 ATR로 나누어 무차원화한다.
5. 연속 수익률·추세에는 분할과 배당 정책이 일관된 수정가격 계열을 사용한다.
6. 실제 overnight gap에는 분할만 중립화하고 현금배당 효과를 소거하지 않은 별도 gap 가격 계열 \(O_t^{Gap},C_t^{Gap}\)을 사용한다.
7. 두 가격 계열을 같은 필드명으로 혼용하지 않고 adjustment policy ID를 출력한다.

### 7.5 최소 관측 길이

| 지표 | 현재 봉을 포함한 최소 이력 |
| --- | ---: |
| 20일 이동 기준선 | 21개 완성 봉 |
| ATR20 | 22개 완성 봉 |
| 5일 수익률의 RZ120 | 126개 완성 봉 |
| 10일 원시 가속도의 RZ120 | 131개 완성 봉 |
| 가격 진전 둔화의 RZ120 | 165개 완성 봉 |
| 252일 이전 고점 돌파 | 253개 완성 봉 |
| 전체 상태 모델 | 최소 165개 완성 봉과 필요한 횡단면 이력 |
| 업종 확산 | 시점별 leave-one-out 유효 구성 종목 최소 5개 |

120세션 창의 coverage가 95% 미만이면 더 오래된 관측으로 빈자리를 채우지 않는다. 조건을 충족하지 못하면 값을 0이나 중립 상태로 만들지 않고 산출 불가로 둔다.

실제 구현은 각 특징의 의존성 그래프에서 최소 이력을 계산하고 하드코딩한 하나의 숫자로 축소하지 않는다.

## 8. 공통 수학 연산

### 8.1 클리핑

\[
\operatorname{clip}(x,a,b)
=
\min(\max(x,a),b)
\]

### 8.2 지시함수

\[
\mathbb{1}(A)
=
\begin{cases}
1,& A\text{가 참}\\
0,& A\text{가 거짓}
\end{cases}
\]

\(A\)가 결측이면 \(\mathbb{1}(A)=NA\)이며 0으로 바꾸지 않는다. 산술식의 필수 입력에 NA가 있으면 결과도 NA다. 연속 확인 중 NA가 나오면 연속 카운터를 0으로 초기화한다.

### 8.3 안전한 나눗셈

\[
\operatorname{safeRatio}(a,b)
=
\begin{cases}
a/b,& b>0\\
NA,& b\leq0
\end{cases}
\]

분모가 0인 값을 작은 상수로 숨기지 않는다.

### 8.4 강건 정규화

원시 특징 \(x_t\)를 현재 봉을 제외한 직전 \(N\)세션으로 정규화한다.

창은 정확히 \(t-N,\ldots,t-1\) 세션으로 고정한다. 창 안의 유효값만 중앙값·MAD·표준편차에 사용하되 coverage가 95% 미만이면 결측이며 \(t-N\)보다 오래된 값으로 보충하지 않는다. 아래 중앙값 표기는 이 유효 부분집합에 대한 연산이다.

\[
\operatorname{Med}_{t,N}(x)
=
\operatorname{Median}(x_{t-1},\ldots,x_{t-N})
\]

\[
\operatorname{MAD}_{t,N}(x)
=
\operatorname{Median}
\left(
|x_{t-j}-\operatorname{Med}_{t,N}(x)|
\right)
\]

유효 관측 수를 \(m_{t,N}(x)\), 유효 관측 평균을 \(\bar{x}_{t,N}\)라고 한다.

\[
SD_{t,N}(x)
=
\sqrt{
\frac{
\sum_{j\in ValidWindow_{t,N}(x)}
\left(
x_{t-j}-\bar{x}_{t,N}
\right)^2
}{
m_{t,N}(x)-1
}
}
\]

\(m_{t,N}(x)<2\)이면 표본 표준편차는 결측이다.

\[
Scale_{t,N}(x)
=
\begin{cases}
1.4826\operatorname{MAD}_{t,N}(x),
& \operatorname{MAD}_{t,N}(x)>0\\
SD_{t,N}(x),
& \operatorname{MAD}_{t,N}(x)=0,\ SD_{t,N}(x)>0\\
0,
& \operatorname{MAD}_{t,N}(x)=SD_{t,N}(x)=0
\end{cases}
\]

\[
RZ_{t,N}(x)
=
\begin{cases}
\operatorname{clip}
\left(
\dfrac{x_t-\operatorname{Med}_{t,N}(x)}
{Scale_{t,N}(x)},
-3,3
\right),
& Scale_{t,N}(x)>0\\
0,
& Scale_{t,N}(x)=0,\ x_t=\operatorname{Med}_{t,N}(x)\\
3\operatorname{sign}
\left(
x_t-\operatorname{Med}_{t,N}(x)
\right),
& Scale_{t,N}(x)=0,\ x_t\neq\operatorname{Med}_{t,N}(x)
\end{cases}
\]

별도 기간이 없으면 \(RZ_t(x)=RZ_{t,120}(x)\)를 뜻한다. MAD가 0이고 표준편차를 사용하면 fallback_standard_deviation, 과거 분포가 상수이면 constant_reference 플래그를 기록한다. 입력 coverage가 부족하면 이 분기를 적용하지 않고 결측으로 둔다.

### 8.4.1 스케일 정규화

가격 차이를 ATR처럼 음수가 아닌 스케일로 나눌 때 사용한다.

\[
\operatorname{scaleRatio}(a,s)
=
\begin{cases}
a/s,& s>0\\
0,& s=0,\ a=0\\
NA,& s=0,\ a\neq0
\end{cases}
\]

평탄한 가격과 0 ATR에서 가격 차이도 0이면 정상적인 0으로 정의한다. 0 ATR 뒤 실제 가격 차이가 발생하면 기준 스케일이 없으므로 결측이다.

### 8.5 0~1 활성화

\[
\operatorname{Ramp}(z;a,b)
=
\operatorname{clip}
\left(
\frac{z-a}{b-a},
0,1
\right),
\qquad a<b
\]

### 8.6 연속 확인

조건 \(A_t\)가 최근 \(k\)거래일 연속 성립했는지 다음과 같이 정의한다.

\[
\operatorname{Consecutive}_k(A_t)
=
\prod_{j=0}^{k-1}\mathbb{1}(A_{t-j})
\]

### 8.7 횡단면 백분위

시점 \(t\)의 적격 집합 \(\mathcal{U}_t\)에서 종목 \(i\)보다 \(x\)가 작은 종목 수를 \(N_{i,t}^{<}(x)\), 같은 종목 수를 \(N_{i,t}^{=}(x)\), 전체 종목 수를 \(n_t=|\mathcal{U}_t|\)라고 한다.

\[
Midrank_{i,t}(x)
=
N_{i,t}^{<}(x)
+
\frac{N_{i,t}^{=}(x)+1}{2}
\]

\[
CrossSectionalPercentile_{i,t}(x)
=
\operatorname{safeRatio}
\left(
Midrank_{i,t}(x)-1,
n_t-1
\right)
\]

동일값에는 같은 midrank를 부여한다. 적격 종목이 하나뿐이면 백분위는 결측이다.

## 9. 가격 원자 지표

### 9.1 기간 수익률

단순 수익률과 로그수익률을 함께 정의한다.

\[
R_t^{(h)}
=
\frac{C_t}{C_{t-h}}-1
\]

\[
r_t^{(h)}
=
\ln\left(\frac{C_t}{C_{t-h}}\right)
\]

기본 기간은 \(h\in\{1,3,5,10,20\}\)이다.

### 9.2 수익률 이상도

\[
Z_t^{Return}(h,N)
=
RZ_{t,N}\left(r^{(h)}\right)
\]

기본 조합은 \((h,N)\in\{(1,60),(5,120),(20,252)\}\)이다. 공통 합성 점수에서는 \(RZ_t=RZ_{t,120}\)을 사용한다.

### 9.3 시장·업종 초과수익률

단순 시장 초과수익률:

\[
AR_{i,t}^{Market}
=
r_{i,t}^{(1)}-r_{m,t}^{(1)}
\]

단순 업종 초과수익률:

\[
AR_{i,t}^{Sector}
=
r_{i,t}^{(1)}-r_{g,t}^{(1)}
\]

베타 조정 초과수익률은 직전 \(N\)세션에서 다음 회귀계수를 구한다.

\[
(\hat{\alpha},\hat{\beta}_m,\hat{\beta}_g)
=
\arg\min_{\alpha,\beta_m,\beta_g}
\sum_{j=1}^{N}
\left[
r_{i,t-j}
-\alpha
-\beta_m r_{m,t-j}
-\beta_g r_{g,t-j}
\right]^2
\]

\[
AR_{i,t}^{Adjusted}
=
r_{i,t}
-
\left(
\hat{\alpha}
+\hat{\beta}_m r_{m,t}
+\hat{\beta}_g r_{g,t}
\right)
\]

회귀 설계행렬 \([\mathbf{1},r_m,r_g]\)이 full column rank이고 유효 관측이 최소 60개일 때만 베타 조정 초과수익률을 계산한다. 시장과 업종 수익률이 완전히 공선적이면 조정값은 결측으로 두고 단순 시장·업종 초과수익률만 별도로 출력한다.

누적 초과수익률:

\[
CAR_{i,t}^{(h)}
=
\sum_{j=0}^{h-1}AR_{i,t-j}^{Adjusted}
\]

기본 회귀 창은 \(N=120\)이다.

CAR의 각 날짜별 초과수익률은 해당 날짜까지의 과거 자료로 추정한 point-in-time 회귀계수를 사용한다. 현재 시점의 회귀계수를 과거 날짜에 소급하지 않는다.

### 9.4 상승 속도

\[
Velocity_t^{(h)}
=
\frac{r_t^{(h)}}{h}
\]

기본 단기 속도는 \(h=3\), 중기 속도는 \(h=10\)이다.

### 9.5 상승 가속도

최근 3일의 일평균 상승 속도와 그 직전 7일의 일평균 상승 속도를 비교한다.

\[
RecentVelocity_t
=
\frac{\ln(C_t/C_{t-3})}{3}
\]

\[
PreviousVelocity_t
=
\frac{\ln(C_{t-3}/C_{t-10})}{7}
\]

\[
Acceleration_t
=
RecentVelocity_t-PreviousVelocity_t
\]

\(Acceleration_t>0\)이면 최근 상승 속도가 빨라졌고, \(r_t^{(5)}>0\)이면서 \(Acceleration_t<0\)이면 가격은 상승 중이지만 속도는 둔화한 상태다.

### 9.6 진폭과 ATR

\[
TR_t
=
\max
\left(
H_t-L_t,\,
|H_t-C_{t-1}|,\,
|L_t-C_{t-1}|
\right)
\]

현재 봉을 제외한 직전 20개 봉의 ATR:

\[
ATR_{t,20}
=
\frac{1}{20}
\sum_{j=1}^{20}TR_{t-j}
\]

ATR 대비 종가 상승:

\[
ATRReturn_t
=
\operatorname{scaleRatio}
\left(
C_t-C_{t-1},
ATR_{t,20}
\right)
\]

ATR 대비 당일 범위:

\[
ATRRange_t
=
\operatorname{scaleRatio}
\left(
H_t-L_t,
ATR_{t,20}
\right)
\]

### 9.7 실현 변동성

\[
RealizedVolatility_{t,N}
=
\sqrt{
\sum_{j=0}^{N-1}
\left(r_{t-j}^{(1)}\right)^2
}
\]

연율화:

\[
AnnualizedVolatility_{t,N}
=
RealizedVolatility_{t,N}
\sqrt{\frac{252}{N}}
\]

단기와 중기 변동성 비율:

\[
VolatilityRatio_t
=
\begin{cases}
\dfrac{
RealizedVolatility_{t,5}/\sqrt{5}
}{
RealizedVolatility_{t,20}/\sqrt{20}
},
& RealizedVolatility_{t,20}>0\\
1,
& RealizedVolatility_{t,5}=RealizedVolatility_{t,20}=0\\
NA,
& \text{그 밖의 경우}
\end{cases}
\]

변동성 정상화 거리:

\[
VolatilityNormalization_t
=
|\ln(VolatilityRatio_t)|
\]

### 9.8 신고가 돌파

\[
PriorHigh_{t,N}
=
\max(H_{t-1},\ldots,H_{t-N})
\]

\[
BreakoutStrength_{t,N}
=
\operatorname{scaleRatio}
\left(
C_t-PriorHigh_{t,N},
ATR_{t,20}
\right)
\]

\[
BreakoutFlag_{t,N}
=
\mathbb{1}
\left(
C_t>PriorHigh_{t,N}
\right)
\]

기본 기간은 \(N\in\{20,60,120,252\}\)이며 합성 점수에는 \(N=20\)을 사용한다.

### 9.9 가격 범위 내 위치

\[
RollingHigh_{t,N}
=
\max(H_t,\ldots,H_{t-N+1})
\]

\[
RollingLow_{t,N}
=
\min(L_t,\ldots,L_{t-N+1})
\]

\[
RangePosition_{t,N}
=
\operatorname{safeRatio}
\left(
C_t-RollingLow_{t,N},
RollingHigh_{t,N}-RollingLow_{t,N}
\right)
\]

### 9.10 고점 거리와 고점 체류도

\[
HighDistance_{t,N}
=
\operatorname{scaleRatio}
\left(
RollingHigh_{t,N}-C_t,
ATR_{t,20}
\right)
\]

\[
HighPersistence_{t,N,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
HighDistance_{t-j,N}\leq1
\right)
\]

기본값은 \(N=20,\ k=5\)다.

평탄한 가격을 고점 추격으로 보지 않도록 방향 게이트를 적용한다.

\[
QualifiedHighPersistence_{t,N,k}
=
HighPersistence_{t,N,k}
\mathbb{1}(r_t^{(5)}>0)
\mathbb{1}(RunUp_{t,N}>0)
\]

### 9.11 이동평균과 이격

\[
MA_{t,N}
=
\frac{1}{N}
\sum_{j=1}^{N}C_{t-j}
\]

\[
MADistance_{t,N}
=
\frac{C_t}{MA_{t,N}}-1
\]

ATR 단위 이격:

\[
ATRDistanceFromMA_{t,N}
=
\operatorname{scaleRatio}
\left(
C_t-MA_{t,N},
ATR_{t,20}
\right)
\]

기본 이동평균 기간은 \(N\in\{5,10,20,60,120\}\)이다.

### 9.11.1 거래량가중 평균가격과 이격

일봉 OHLCV에서 계산하는 \(N\)일 rolling VWAP 프록시:

\[
TypicalPrice_t
=
\frac{H_t+L_t+C_t}{3}
\]

\[
RollingVWAP_{t,N}
=
\operatorname{safeRatio}
\left(
\sum_{j=1}^{N}TypicalPrice_{t-j}V_{t-j},
\sum_{j=1}^{N}V_{t-j}
\right)
\]

\[
VWAPDistance_{t,N}
=
\operatorname{scaleRatio}
\left(
C_t-RollingVWAP_{t,N},
ATR_{t,20}
\right)
\]

이는 단일 세션의 실제 장중 VWAP가 아니라 일봉 rolling VWAP다. 두 값을 같은 지표 ID로 저장하지 않는다.

이동평균 위 지속일:

\[
DaysAboveMA_{t,N}
=
\begin{cases}
0,& C_t\leq MA_{t,N}\\
1+DaysAboveMA_{t-1,N},& C_t>MA_{t,N}
\end{cases}
\]

rolling VWAP 위 지속일:

\[
DaysAboveVWAP_{t,N}
=
\begin{cases}
0,& C_t\leq RollingVWAP_{t,N}\\
1+DaysAboveVWAP_{t-1,N},& C_t>RollingVWAP_{t,N}
\end{cases}
\]

### 9.12 시가 갭과 갭 유지

\[
Gap_t
=
\frac{O_t^{Gap}}{C_{t-1}^{Gap}}-1
\]

상승 갭에서만 계산하는 갭 유지율:

\[
GapRetention_t
=
\operatorname{clip}
\left(
\operatorname{safeRatio}
\left(
C_t^{Gap}-C_{t-1}^{Gap},
O_t^{Gap}-C_{t-1}^{Gap}
\right),
-1,2
\right),
\qquad O_t^{Gap}>C_{t-1}^{Gap}
\]

### 9.13 봉의 몸통과 종가 위치

\(H_t>L_t\)이면 아래 수식을 사용한다. \(H_t=L_t=O_t=C_t\)인 유효 무변동 봉에서는 다음 중립값을 사용한다.

\[
SignedBodyRatio_t=0,\quad
AbsoluteBodyRatio_t=0,\quad
CloseLocation_t=0.5,\quad
UpperWickRatio_t=0,\quad
LowerWickRatio_t=0
\]

OHLC 관계가 일관되지 않은 0범위 봉은 결측이다.

\[
SignedBodyRatio_t
=
\operatorname{safeRatio}
\left(
C_t-O_t,
H_t-L_t
\right)
\]

\[
AbsoluteBodyRatio_t
=
\operatorname{safeRatio}
\left(
|C_t-O_t|,
H_t-L_t
\right)
\]

\[
CloseLocation_t
=
\operatorname{safeRatio}
\left(
C_t-L_t,
H_t-L_t
\right)
\]

\[
UpperWickRatio_t
=
\operatorname{safeRatio}
\left(
H_t-\max(O_t,C_t),
H_t-L_t
\right)
\]

\[
LowerWickRatio_t
=
\operatorname{safeRatio}
\left(
\min(O_t,C_t)-L_t,
H_t-L_t
\right)
\]

### 9.14 상승 봉 비율과 연속 상승

\[
PositiveBarRatio_{t,N}
=
\frac{1}{N}
\sum_{j=0}^{N-1}
\mathbb{1}
\left(
C_{t-j}>C_{t-j-1}
\right)
\]

\[
UpStreak_t
=
\begin{cases}
0,& C_t\leq C_{t-1}\\
1+UpStreak_{t-1},& C_t>C_{t-1}
\end{cases}
\]

\[
BullishCandleStreak_t
=
\begin{cases}
0,& C_t\leq O_t\\
1+BullishCandleStreak_{t-1},& C_t>O_t
\end{cases}
\]

### 9.15 누적 상승과 현재 조정

\[
RunUp_{t,N}
=
\frac{C_t}
{\min(L_{t-1},\ldots,L_{t-N})}
-1
\]

\[
CurrentDrawdown_{t,N}
=
\frac{C_t}
{\max(H_t,\ldots,H_{t-N+1})}
-1
\]

### 9.16 최대 낙폭

\[
Peak_\tau
=
\max_{s\in[t-N+1,\tau]}C_s
\]

\[
Drawdown_\tau
=
\frac{C_\tau}{Peak_\tau}-1
\]

\[
MaximumDrawdown_{t,N}
=
\min_{\tau\in[t-N+1,t]}Drawdown_\tau
\]

### 9.17 추세 효율성

\[
TrendEfficiency_{t,N}
=
\operatorname{scaleRatio}
\left(
|C_t-C_{t-N}|,
\sum_{j=0}^{N-1}|C_{t-j}-C_{t-j-1}|
\right)
\]

상승 방향만 반영하는 방향성 추세 효율:

\[
DirectionalTrendEfficiency_{t,N}
=
\operatorname{scaleRatio}
\left(
C_t-C_{t-N},
\sum_{j=0}^{N-1}|C_{t-j}-C_{t-j-1}|
\right)
\]

### 9.18 눌림 거부

\[
PullbackHold_{t,N}
=
1-
\operatorname{clip}
\left(
\operatorname{scaleRatio}
\left(
RollingHigh_{t,N}-C_t,
ATR_{t,20}
\right),
0,1
\right)
\]

고점에서 ATR 1배 이상 밀리면 0, 고점에 가까울수록 1에 가까워진다.

\[
QualifiedPullbackHold_{t,N}
=
PullbackHold_{t,N}
\mathbb{1}(r_t^{(5)}>0)
\mathbb{1}(RunUp_{t,N}>0)
\]

### 9.19 고점 갱신 빈도

\[
HighRenewalCount_{t,N,k}
=
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
H_{t-j}>
\max(H_{t-j-1},\ldots,H_{t-j-N})
\right)
\]

기본값은 \(N=20,\ k=10\)이다.

## 10. 거래량 원자 지표

### 10.1 상대 거래량

\[
RVOL_{t,N}
=
\operatorname{safeRatio}
\left(
V_t,
\operatorname{Median}(V_{t-1},\ldots,V_{t-N})
\right)
\]

기본 기간은 \(N=20\)이며 장기 확인에는 \(N=60\)을 사용한다.

### 10.2 거래량 이상도

\[
LogVolume_t
=
\ln(1+V_t)
\]

\[
Z_{t,N}^{Volume}
=
RZ_{t,N}(LogVolume)
\]

### 10.3 거래량 가속

\[
RecentVolume_{t,s}
=
\operatorname{Median}(V_t,\ldots,V_{t-s+1})
\]

\[
PreviousVolume_{t,s,l}
=
\operatorname{Median}(V_{t-s},\ldots,V_{t-l+1})
\]

\[
VolumeAcceleration_t^{(s,l)}
=
\ln
\left(
\frac{1+RecentVolume_{t,s}}
{1+PreviousVolume_{t,s,l}}
\right)
\]

기본값은 \(s=5,\ l=20\)이다.

### 10.4 거래량 증가 지속성

\[
VolumePersistence_{t,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
RVOL_{t-j,20}\geq1.5
\right)
\]

기본값은 \(k=5\)다.

### 10.5 거래량 정상화

\[
VolumeNormalization_t
=
|\ln(RVOL_{t,20})|
\]

\(RVOL_{t,20}=0\)이면 거래정지·무거래 판정을 먼저 적용하고 거래량 정상화 값은 결측으로 둔다.

\[
StableVolumeRatio_{t,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
0.67\leq RVOL_{t-j,20}\leq1.5
\right)
\]

### 10.6 거래대금

공식 거래대금이 있으면 그 값을 사용한다. OHLCV만 있으면 전형가격으로 근사한다.

\[
EstimatedTradingValue_t
=
TypicalPrice_tV_t
\]

공식 거래대금과 근사 거래대금은 동일한 필드로 혼용하지 않는다.

실행 전체에 고정하는 \(TradingValueSource\in\{official,estimated\}\)를 둔다.

\[
SelectedTradingValue_t
=
\begin{cases}
OfficialTradingValue_t,& TradingValueSource=official\\
EstimatedTradingValue_t,& TradingValueSource=estimated
\end{cases}
\]

한 실행 안에서 날짜별로 source를 전환하지 않는다. source가 다른 결과는 별도 model run ID로 저장한다.

시점 \(t\)의 전체 적격 종목 집합을 \(\mathcal{U}_t\)라고 할 때 거래대금 횡단면 백분위는 다음과 같다.

\[
TradingValuePercentile_{i,t}
=
\operatorname{CrossSectionalPercentile}_{i,t}
\left(
SelectedTradingValue
\right)
\]

거래대금 상위 종목 진입 여부:

\[
TopTradingValueFlag_{i,t}(p)
=
\mathbb{1}
\left(
TradingValuePercentile_{i,t}\geq p
\right)
\]

기본 상위 기준은 \(p=0.95\)다.

### 10.7 상승 봉 거래량 비율

\[
UpVolumeRatio_{t,N}
=
\operatorname{safeRatio}
\left(
\sum_{j=0}^{N-1}
V_{t-j}\mathbb{1}(C_{t-j}>C_{t-j-1}),
\sum_{j=0}^{N-1}V_{t-j}
\right)
\]

\[
UpDownVolumeRatio_{t,N}
=
\operatorname{safeRatio}
\left(
\sum_{j=0}^{N-1}
V_{t-j}\mathbb{1}(C_{t-j}>C_{t-j-1}),
\sum_{j=0}^{N-1}
V_{t-j}\mathbb{1}(C_{t-j}<C_{t-j-1})
\right)
\]

두 값은 공격적 매수량이 아니라 상승 봉에 귀속된 거래량 프록시다.

### 10.8 가격·거래량 동시 팽창

\[
PriceVolumeExpansion_t
=
\operatorname{Ramp}
\left(
RZ_t(r^{(1)});0.5,2.5
\right)
\times
\operatorname{Ramp}
\left(
RZ_t(LogVolume);0.5,2.5
\right)
\]

### 10.9 거래량 대비 가격 진전

\[
PriceProgress_t
=
\frac{
\max(r_t^{(1)},0)
}{
\max(RVOL_{t,20},1)
}
\]

\[
VolumeEfficiency_t
=
\operatorname{safeRatio}
\left(
r_t^{(1)},
RVOL_{t,20}
\right)
\]

### 10.10 고거래량·가격 반응 분해

\[
HighVolumeActivation_t
=
\operatorname{Ramp}
\left(
RZ_t(LogVolume);0.5,2.5
\right)
\]

\[
AbsoluteMoveActivation_t
=
\operatorname{Ramp}
\left(
RZ_t(|r^{(1)}|);0.5,2.5
\right)
\]

\[
HighVolumeLowAbsoluteMove_t
=
HighVolumeActivation_t
\left(
1-AbsoluteMoveActivation_t
\right)
\]

\[
UpsideProgressActivation_t
=
\operatorname{Ramp}
\left(
RZ_t(\max(r^{(1)},0));0.5,2.5
\right)
\]

\[
HighVolumeNoUpsideProgress_t
=
HighVolumeActivation_t
\left(
1-UpsideProgressActivation_t
\right)
\]

\[
DownsideBreakActivation_t
=
\operatorname{Ramp}
\left(
-RZ_t(r^{(1)});0.5,2.5
\right)
\]

\[
HighVolumeDownsideBreak_t
=
HighVolumeActivation_t
\times
DownsideBreakActivation_t
\]

절대 이동 부족, 상승 진전 부족, 하방 붕괴를 서로 다른 값으로 저장한다. 고거래량 급락을 저가격진전과 같은 의미로 합치지 않는다.

## 11. 시장·업종 확산 지표

### 11.1 상승 종목 비율

\[
AdvanceRatio_{g,t}
=
\frac{
\sum_{i\in G_{g,t}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|G_{g,t}|
}
\]

관찰 대상 종목 자체가 확산 증거에 포함되지 않도록 상태 점수에는 leave-one-out 집합을 사용한다.

\[
G_{g,t}^{(-i_0)}
=
G_{g,t}\setminus\{i_0\}
\]

\[
AdvanceRatio_{g,t}^{(-i_0)}
=
\frac{
\sum_{i\in G_{g,t}^{(-i_0)}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|G_{g,t}^{(-i_0)}|
}
\]

leave-one-out 뒤 유효 종목이 5개 미만이면 관찰 대상의 확산 특징을 산출하지 않는다. 이후 확산 점수에서 별도 표시가 없으면 관찰 대상별 leave-one-out 값을 사용한다.

### 11.2 시장 초과 상승 종목 비율

\[
ExcessAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in G_{g,t}}
\mathbb{1}(r_{i,t}^{(1)}>r_{m,t}^{(1)})
}{
|G_{g,t}|
}
\]

### 11.3 급등 종목 비율

\[
SurgeBreadth_{g,t}(q)
=
\frac{
\sum_{i\in G_{g,t}}
\mathbb{1}(R_{i,t}^{(1)}>q)
}{
|G_{g,t}|
}
\]

기본 임계값은 \(q\in\{0.03,0.05,0.10\}\)이다.

### 11.4 신고가 종목 비율

\[
NewHighBreadth_{g,t}^{(N)}
=
\frac{
\sum_{i\in G_{g,t}}
BreakoutFlag_{i,t,N}
}{
|G_{g,t}|
}
\]

### 11.5 확산 속도와 가속도

\[
C_{g,t}^{(2)}
=
G_{g,t}\cap G_{g,t-1}
\]

\[
\operatorname{AdvanceRatio}
\left(
g,s\mid C
\right)
=
\frac{
\sum_{i\in C}
\mathbb{1}(r_{i,s}^{(1)}>0)
}{
|C|
}
\]

\[
BreadthVelocity_{g,t}
=
\operatorname{AdvanceRatio}
\left(
g,t\mid C_{g,t}^{(2)}
\right)
-
\operatorname{AdvanceRatio}
\left(
g,t-1\mid C_{g,t}^{(2)}
\right)
\]

3일 공통 코호트:

\[
C_{g,t}^{(3)}
=
G_{g,t}\cap G_{g,t-1}\cap G_{g,t-2}
\]

\[
\begin{aligned}
BreadthAcceleration_{g,t}
={}&
\operatorname{AdvanceRatio}
\left(
g,t\mid C_{g,t}^{(3)}
\right)\\
&-2
\operatorname{AdvanceRatio}
\left(
g,t-1\mid C_{g,t}^{(3)}
\right)\\
&+
\operatorname{AdvanceRatio}
\left(
g,t-2\mid C_{g,t}^{(3)}
\right)
\end{aligned}
\]

공통 코호트가 각 비교일 공식 구성종목의 80% 미만이거나 5종목 미만이면 속도·가속도를 산출하지 않는다.

### 11.6 확산 지속성

\[
BreadthPersistence_{g,t,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
AdvanceRatio_{g,t-j}\geq0.60
\right)
\]

\[
ExcessBreadthPersistence_{g,t,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
ExcessAdvanceRatio_{g,t-j}\geq0.60
\right)
\]

기본값은 \(k=5\)다.

### 11.7 업종 동일가중 수익률

\[
EqualWeightedReturn_{g,t}
=
\frac{1}{|G_{g,t}|}
\sum_{i\in G_{g,t}}r_{i,t}^{(1)}
\]

### 11.8 선도주와 후발주

시점 \(t-1\)까지의 5일 수익률 횡단면 백분위를 다음처럼 계산한다.

\[
LeaderPercentile_{i,g,t}
=
\operatorname{CrossSectionalPercentile}_{i,t-1}
\left(
r^{(5)}
\mid
G_{g,t-1}
\right)
\]

\[
EligibleGroup_{g,t}
=
\left\{
i\in G_{g,t}\cap G_{g,t-1}:
r_{i,t-1}^{(5)}\text{가 유효}
\right\}
\]

\[
Leader_{g,t}
=
\left\{
i\in EligibleGroup_{g,t}:
LeaderPercentile_{i,g,t}>0.80
\right\}
\]

\[
Laggard_{g,t}
=
EligibleGroup_{g,t}\setminus Leader_{g,t}
\]

상위 20% 경계는 엄격한 초과 조건이다. 수익률이 모두 같으면 선도주 집합은 비고 후발주 집합은 전체 종목이 된다. 선도주 집합이 비면 선도주 전용 지표는 결측 또는 명시적 거짓으로 처리하지만 후발주 확산은 계속 계산한다.

\[
LeaderReturn_{g,t}
=
\operatorname{safeRatio}
\left(
\sum_{i\in Leader_{g,t}}r_{i,t}^{(1)},
|Leader_{g,t}|
\right)
\]

\[
LaggardReturn_{g,t}
=
\frac{1}{|Laggard_{g,t}|}
\sum_{i\in Laggard_{g,t}}r_{i,t}^{(1)}
\]

\[
LeaderLaggardGap_{g,t}
=
LeaderReturn_{g,t}
-LaggardReturn_{g,t}
\]

\[
LaggardAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in Laggard_{g,t}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|Laggard_{g,t}|
}
\]

후발주 반응 속도:

\[
LaggardDiffusionVelocity_{g,t}
=
EpisodeLaggardAdvanceRatio_{g,t}
-EpisodeLaggardAdvanceRatio_{g,t-1}
\]

### 11.8.1 사건 고정 코호트

포모 시작 전 진입 시점을 \(\tau_P\)라고 한다. 상태 모델은 매일 다시 선도주·후발주를 선정하지 않고 다음 코호트를 사건 종료까지 고정한다.

\[
EpisodeGroup_g
=
EligibleGroup_{g,\tau_P}\setminus\{i_0\}
\]

\[
EpisodeLeader_g
=
Leader_{g,\tau_P}\cap EpisodeGroup_g
\]

\[
EpisodeLaggard_g
=
Laggard_{g,\tau_P}\cap EpisodeGroup_g
\]

시점 \(t\)의 유효 사건 코호트:

\[
EpisodeGroup_{g,t}^{valid}
=
EpisodeGroup_g\cap G_{g,t}
\]

\[
EpisodeLaggard_{g,t}^{valid}
=
EpisodeLaggard_g\cap G_{g,t}
\]

\[
EpisodeAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in EpisodeGroup_{g,t}^{valid}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|EpisodeGroup_{g,t}^{valid}|
}
\]

\[
EpisodeExcessAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in EpisodeGroup_{g,t}^{valid}}
\mathbb{1}(r_{i,t}^{(1)}>r_{m,t}^{(1)})
}{
|EpisodeGroup_{g,t}^{valid}|
}
\]

\[
EpisodeLaggardAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in EpisodeLaggard_{g,t}^{valid}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|EpisodeLaggard_{g,t}^{valid}|
}
\]

\[
EpisodeLaggardReturn_{g,t}
=
\frac{
\sum_{i\in EpisodeLaggard_{g,t}^{valid}}
r_{i,t}^{(1)}
}{
|EpisodeLaggard_{g,t}^{valid}|
}
\]

현재 유효 사건 코호트가 고정 코호트의 80% 미만이거나 5종목 미만이면 사건 확산 특징을 산출하지 않는다. 중립 복귀 또는 산출 불가 후 재시작 시 코호트를 폐기한다.

사건 확산 특징의 강건 기준선은 \(\tau_P\)에 고정된 코호트로 직전 120세션을 재계산해 만든다. 이후 구성 재분류로 과거 기준선을 바꾸지 않는다.

\[
EpisodeRZ_{t;\tau_P}(x)
=
AnchorRZ_{t;\tau_P}(x)
\]

여기서 \(x\)는 고정 코호트로 과거 120세션까지 재계산한 확산 시계열이다.

### 11.9 대장주 편중도

\[
PositiveReturn_{i,t}
=
\max(r_{i,t}^{(1)},0)
\]

\[
EpisodeLeaderConcentration_{g,t}
=
\begin{cases}
\dfrac{
\sum_{i\in EpisodeLeader_g\cap G_{g,t}}PositiveReturn_{i,t}
}{
\sum_{i\in EpisodeGroup_{g,t}^{valid}}PositiveReturn_{i,t}
},
& \sum_{i\in EpisodeGroup_{g,t}^{valid}}PositiveReturn_{i,t}>0\\
0,
& \sum_{i\in EpisodeGroup_{g,t}^{valid}}PositiveReturn_{i,t}=0
\end{cases}
\]

\[
LeadershipRelease_{g,t}
=
EpisodeLeaderConcentration_{g,t-1}
-EpisodeLeaderConcentration_{g,t}
\]

양의 LeadershipRelease는 사건 시작 때 고정한 선도주 편중이 약해졌다는 뜻이다.

### 11.10 상승 수익률의 균등 확산도

\[
w_{i,t}
=
\begin{cases}
\dfrac{
\max(r_{i,t}^{(1)},0)
}{
\sum_{j\in G_{g,t}}\max(r_{j,t}^{(1)},0)
},
& \sum_{j\in G_{g,t}}\max(r_{j,t}^{(1)},0)>0\\
0,
& \sum_{j\in G_{g,t}}\max(r_{j,t}^{(1)},0)=0
\end{cases}
\]

\[
ReturnConcentration_{g,t}
=
\sum_{i\in G_{g,t}}w_{i,t}^2
\]

\[
ReturnDiffusion_{g,t}
=
\begin{cases}
\dfrac{
1-ReturnConcentration_{g,t}
}{
1-\frac{1}{|G_{g,t}|}
},
& \sum_{j\in G_{g,t}}\max(r_{j,t}^{(1)},0)>0\\
0,
& \sum_{j\in G_{g,t}}\max(r_{j,t}^{(1)},0)=0
\end{cases}
\]

값이 1에 가까울수록 양의 수익률이 여러 종목에 고르게 분산된다.

### 11.11 업종 동조화

직전 \(N\)세션 모두에 유효 수익률이 있고 수익률 분산이 양수인 공통 종목 집합을 \(CorrelationCohort_{g,t,N}\)로 정의한다. pairwise deletion을 사용하지 않는다. 공통 코호트가 공식 구성의 80% 미만이거나 5종목 미만이면 동조화 지표는 결측이다.

\[
AverageCorrelation_{g,t,N}
=
\frac{2}
{|CorrelationCohort_{g,t,N}|
\left(
|CorrelationCohort_{g,t,N}|-1
\right)}
\sum_{\substack{i<j\\i,j\in CorrelationCohort_{g,t,N}}}
\rho_{i,j,t}^{(N)}
\]

\(\rho_{i,j,t}^{(N)}\)는 직전 \(N\)세션의 종목 \(i,j\) 로그수익률 상관계수다. 기본값은 \(N=20\)이다.

업종 구성 종목 수익률 공분산행렬의 고유값을
\(\lambda_{1,t}\geq\lambda_{2,t}\geq\cdots\geq\lambda_{n,t}\geq0\)으로 정렬한다.

\[
FirstComponentShare_{g,t,N}
=
\operatorname{safeRatio}
\left(
\lambda_{1,t},
\sum_{j=1}^{n}\lambda_{j,t}
\right)
\]

값이 높을수록 업종 구성 종목이 하나의 공통 방향으로 움직이는 비중이 크다.

공분산행렬은 같은 공통 행과 같은 코호트로 계산해 대칭 positive-semidefinite 성질을 보존한다. 전체 고유값 합이 0이면 첫 주성분 비율은 결측이다.

## 12. 소진·해소 원자 지표

### 12.1 모멘텀 둔화

\[
MomentumDecay_t^{(h)}
=
r_t^{(h)}-r_{t-h}^{(h)}
\]

음수이면 최근 \(h\)일 모멘텀이 바로 이전 \(h\)일보다 약하다.

상승 가속도의 반전값:

\[
NegativeAcceleration_t
=
-Acceleration_t
\]

### 12.2 돌파 실패

\[
FailedBreakout_{t,N}
=
\mathbb{1}
\left(
H_t>PriorHigh_{t,N}
\land
C_t\leq PriorHigh_{t,N}
\right)
\]

돌파 거부 강도:

\[
BreakoutRejection_{t,N}
=
\operatorname{clip}
\left(
\operatorname{safeRatio}
\left(
H_t-C_t,
H_t-PriorHigh_{t,N}
\right),
0,1
\right)
\]

돌파 거부 강도는 \(H_t>PriorHigh_{t,N}\)인 봉에서만 계산한다.

### 12.3 가격 진전 둔화

최근 5일 평균 가격 진전과 그 이전 20일 평균 가격 진전을 비교한다.

\[
RecentProgress_t
=
\frac{1}{5}
\sum_{j=0}^{4}PriceProgress_{t-j}
\]

\[
PreviousProgress_t
=
\frac{1}{20}
\sum_{j=5}^{24}PriceProgress_{t-j}
\]

\[
ProgressDecay_t
=
PreviousProgress_t-RecentProgress_t
\]

양수이면 이전보다 거래량 단위당 상승 진전이 감소했다.

### 12.4 가격·모멘텀 다이버전스

직전 \(N\)세션에서 최고 종가가 발생한 시점을 다음처럼 정의한다.

\[
t^\*
=
\max
\left(
\arg\max_{\tau\in[t-N,t-1]}C_\tau
\right)
\]

최고 종가가 여러 번이면 현재와 가장 가까운 최근 시점을 사용한다.

\[
BearishMomentumDivergence_{t,N}
=
\mathbb{1}
\left(
C_t>C_{t^\*}
\land
r_t^{(5)}<r_{t^\*}^{(5)}
\right)
\]

### 12.5 가격·확산도 다이버전스

선도주 바스켓 돌파 여부:

\[
LeaderBreakout_{g,t}
=
\begin{cases}
\mathbb{1}
\left(
\dfrac{
\sum_{i\in Leader_{g,t}}
BreakoutFlag_{i,t,20}
}{
|Leader_{g,t}|
}
\geq0.5
\right),
& |Leader_{g,t}|>0\\
0,
& |Leader_{g,t}|=0
\end{cases}
\]

\[
BreadthDivergence_{g,t}
=
\mathbb{1}
\left(
LeaderBreakout_{g,t}=1
\land
AdvanceRatio_{g,t}<AdvanceRatio_{g,t-1}
\right)
\]

5일 평균으로 안정화한 형태:

\[
BreadthMA_{g,t}^{(5)}
=
\frac{1}{5}
\sum_{j=0}^{4}AdvanceRatio_{g,t-j}
\]

\[
StableBreadthDivergence_{g,t}
=
\mathbb{1}
\left(
LeaderBreakout_{g,t}=1
\land
BreadthMA_{g,t}^{(5)}
<
BreadthMA_{g,t-5}^{(5)}
\right)
\]

하나의 대장주를 사후 선택하지 않고 시점 \(t-1\)에 정해진 선도주 집합의 과반이 돌파했는지를 사용한다.

### 12.6 포모 사건 기준점

하나의 episode 안에서 재점화가 일어날 수 있으므로 포모 진행 구간을 segment \(k=1,2,\ldots\)로 관리한다. segment \(k\)의 포모 진입 시점을 \(\tau_F^{(k)}\), 해소 진입 시점을 \(\tau_R^{(k)}\)라고 한다.

\[
RunningFOMOPeak_t^{(k)}
=
\max_{\tau_F^{(k)}\leq s\leq t}H_s,
\qquad
\tau_F^{(k)}\leq t\leq\tau_R^{(k)}
\]

\[
P_k^{FOMO}
=
RunningFOMOPeak_{\tau_R^{(k)}}^{(k)}
\]

\[
\tau_T
=
\min
\left\{
s:
\tau_R^{(k)}<s<t,\,
C_s\leq C_{s-1},\,
C_{s+1}>C_s
\right\}
\]

\[
T^{FOMO}
=
C_{\tau_T}
\]

\(RunningFOMOPeak_t^{(k)}\)는 각 포모 segment에서 매일 갱신한다. Resolving 진입일에 \(P_k^{FOMO}\)로 고정하며 이후 소급 변경하지 않는다. 별도 첨자가 없는 \(P^{FOMO}\)는 현재 해소 중인 segment의 \(P_k^{FOMO}\)를 뜻한다. \(\tau_T\)는 해소 진입 뒤 처음 확인된 종가 기준 swing 저점이며, 다음 거래일 반등으로 확인된 뒤 해당 segment 동안 고정한다. 확인된 저점이 없으면 반등 관련 지표는 결측이다.

### 12.6.1 사건 전 고정 기준선

장기 과열이 rolling 120세션 기준선에 흡수되는 것을 막기 위해 포모 시작 전 진입 시점 \(\tau_P\) 직전의 분포를 사건 종료까지 고정한다.

\[
AnchorMedian_{\tau_P}(x)
=
\operatorname{Med}_{\tau_P,120}(x)
\]

\[
AnchorScale_{\tau_P}(x)
=
Scale_{\tau_P,120}(x)
\]

\[
AnchorRZ_{t;\tau_P}(x)
=
\begin{cases}
\operatorname{clip}
\left(
\dfrac{x_t-AnchorMedian_{\tau_P}(x)}
{AnchorScale_{\tau_P}(x)},
-3,3
\right),
& AnchorScale_{\tau_P}(x)>0\\
0,
& AnchorScale_{\tau_P}(x)=0,\ x_t=AnchorMedian_{\tau_P}(x)\\
3\operatorname{sign}
\left(
x_t-AnchorMedian_{\tau_P}(x)
\right),
& AnchorScale_{\tau_P}(x)=0,\ x_t\neq AnchorMedian_{\tau_P}(x)
\end{cases}
\]

\[
AnchorRVOL_{t;\tau_P}
=
\operatorname{safeRatio}
\left(
V_t,
\operatorname{Median}
\left(
V_{\tau_P-1},\ldots,V_{\tau_P-20}
\right)
\right)
\]

사건 전 일평균 변동성:

\[
AnchorVolatility_{\tau_P}
=
\frac{RealizedVolatility_{\tau_P-1,20}}{\sqrt{20}}
\]

\[
AnchorVolatilityRatio_{t;\tau_P}
=
\begin{cases}
\dfrac{
RealizedVolatility_{t,5}/\sqrt{5}
}{
AnchorVolatility_{\tau_P}
},
& AnchorVolatility_{\tau_P}>0\\
1,
& AnchorVolatility_{\tau_P}=0,\ RealizedVolatility_{t,5}=0\\
NA,
& \text{그 밖의 경우}
\end{cases}
\]

### 12.7 기간 조정

기간 조정은 Resolving 상태에서만 평가한다.

\[
DrawdownFromFOMOPeak_t
=
\frac{C_t}{P^{FOMO}}-1
\]

\[
\begin{aligned}
TimeCorrection_t
={}&
\mathbb{1}
\left(
State_t=Resolving
\right)\\
&\times
\mathbb{1}
\left(
DrawdownFromFOMOPeak_t\geq-0.10
\land
DrawdownFromFOMOPeak_t\leq0
\right)\\
&\times
\mathbb{1}
\left(
|RZ_t(r^{(5)})|<1
\right)\\
&\times
\mathbb{1}
\left(
0.67\leq RVOL_{t,20}\leq1.5
\right)
\end{aligned}
\]

연속 기간 조정 일수:

\[
TimeCorrectionDuration_t
=
\begin{cases}
0,& TimeCorrection_t=0\\
1+TimeCorrectionDuration_{t-1},& TimeCorrection_t=1
\end{cases}
\]

### 12.8 반등 회복률

\[
ReboundRecovery_t
=
\operatorname{safeRatio}
\left(
C_t-T^{FOMO},
P^{FOMO}-T^{FOMO}
\right)
\]

- 0은 해소 구간 저점이다.
- 0.5는 하락폭의 절반 회복이다.
- 1은 이전 포모 고점 회복이다.
- 1 초과는 이전 포모 고점 돌파다.

### 12.9 반등 실패

\[
ReboundHigh_t
=
\max_{\tau_T\leq s\leq t}C_s
\]

\[
MaximumRecovery_t
=
\operatorname{safeRatio}
\left(
ReboundHigh_t-T^{FOMO},
P^{FOMO}-T^{FOMO}
\right)
\]

\[
ReboundFailureEvent_t
=
\mathbb{1}
\left(
MaximumRecovery_t\geq0.30
\right)
\mathbb{1}
\left(
ReboundRecovery_t
\leq
MaximumRecovery_t-0.20
\lor
C_t<T^{FOMO}
\right)
\]

\[
ReboundFailure_t
=
\max
\left(
ReboundFailure_{t-1},
ReboundFailureEvent_t
\right)
\]

\[
ReboundFailure_{\tau_R^{(k)}}=0
\]

해당 사건에서 한 번 확인된 반등 실패는 새 저점이 생겨도 0으로 되돌리지 않는다. 새 포모 사건이 시작될 때만 반등 실패 상태를 초기화한다.

### 12.10 포모 고점 재돌파

\[
RebreakStrength_t
=
\operatorname{scaleRatio}
\left(
C_t-P^{FOMO},
ATR_{t,20}
\right)
\]

\[
RebreakHold_{t,k}
=
\frac{1}{k}
\sum_{j=0}^{k-1}
\mathbb{1}
\left(
C_{t-j}>P^{FOMO}
\right)
\]

\[
StrongRebreakHold_{t,2}
=
\prod_{j=0}^{1}
\mathbb{1}
\left(
C_{t-j}>
P^{FOMO}+0.25ATR_{t-j,20}
\right)
\]

### 12.11 공동 정상화

공동 정상화는 진행·해소 점수와 중립 점수가 모두 정의된 뒤 판정해야 하므로 16.10에서 하나의 완전 해소 Gate로 정의한다.

## 13. 점화·진행 특징 활성화

모든 활성화 값은 0과 1 사이이며, 필요한 원시값이 결측이면 활성화 값도 결측이다.

### 13.1 가격 모멘텀

\[
M_t
=
\operatorname{Ramp}
\left(
RZ_t(r^{(5)});0.5,2.5
\right)
\]

### 13.2 상승 가속

\[
A_t
=
\operatorname{Ramp}
\left(
RZ_t(Acceleration);0,2
\right)
\]

### 13.3 돌파 강도

\[
B_t
=
\operatorname{Ramp}
\left(
BreakoutStrength_{t,20};0,1.5
\right)
\]

### 13.4 거래량 팽창

\[
V_t^\*
=
\operatorname{Ramp}
\left(
RZ_t(LogVolume);0.5,2.5
\right)
\]

### 13.5 방향성 추세 효율

\[
E_t
=
\operatorname{Ramp}
\left(
DirectionalTrendEfficiency_{t,10};0.3,0.8
\right)
\]

### 13.6 고점 확장

\[
U_t^{raw}
=
ATRDistanceFromMA_{t,20}
\]

\[
U_t
=
\operatorname{Ramp}
\left(
U_t^{raw};1,4
\right)
\]

### 13.7 업종 확산

\[
\begin{aligned}
D_t
={}&
0.5
\operatorname{Ramp}
\left(
EpisodeRZ_{t;\tau_P}(EpisodeAdvanceRatio_g);0,2
\right)\\
&+
0.5
\operatorname{Ramp}
\left(
EpisodeRZ_{t;\tau_P}(EpisodeExcessAdvanceRatio_g);0,2
\right)
\end{aligned}
\]

### 13.8 후발주 확산

\[
\begin{aligned}
\Lambda_t
={}&
0.5
\operatorname{Ramp}
\left(
EpisodeRZ_{t;\tau_P}(EpisodeLaggardAdvanceRatio_g);0,2
\right)\\
&+
0.5
\operatorname{Ramp}
\left(
EpisodeRZ_{t;\tau_P}(EpisodeLaggardReturn_g);0,2
\right)
\end{aligned}
\]

## 14. 해소 특징 활성화

### 14.1 모멘텀 둔화

\[
Q_t^M
=
\operatorname{Ramp}
\left(
RZ_t(-Acceleration);0,2
\right)
\]

### 14.2 거래량 대비 가격 진전 둔화

\[
Q_t^V
=
HighVolumeActivation_t
\times
\operatorname{Ramp}
\left(
RZ_t(ProgressDecay);0,2
\right)
\]

### 14.3 위꼬리

\[
Q_t^W
=
\operatorname{Ramp}
\left(
UpperWickRatio_t;0.25,0.65
\right)
\]

### 14.4 약한 종가

\[
Q_t^C
=
\operatorname{Ramp}
\left(
1-CloseLocation_t;0.4,0.8
\right)
\]

### 14.5 돌파 실패

\[
Q_t^F
=
FailedBreakout_{t,20}
\]

### 14.6 음의 비정상 수익률

\[
Q_t^R
=
\operatorname{Ramp}
\left(
-RZ_t(r^{(1)});0.5,2.5
\right)
\]

### 14.7 확산도 약화

\[
BreadthDecay_{g,t}
=
-
\left(
EpisodeAdvanceRatio_{g,t}
-EpisodeAdvanceRatio_{g,t-1}
\right)
\]

\[
Q_t^D
=
\operatorname{Ramp}
\left(
EpisodeRZ_{t;\tau_P}(BreadthDecay_g);0,2
\right)
\]

## 15. 합성 점수

필수 구성요소가 하나라도 결측이면 해당 합성 점수를 산출하지 않는다. 남은 요소의 가중치를 재조정하지 않는다.

### 15.1 중립 기준선 근접 점수

\[
N_t^R
=
1-
\operatorname{Ramp}
\left(
|RZ_t(r^{(5)})|;0.5,2
\right)
\]

\[
N_t^V
=
1-
\operatorname{Ramp}
\left(
|RZ_t(LogVolume)|;0.5,2
\right)
\]

\[
N_t^B
=
1-
\operatorname{Ramp}
\left(
|RZ_t(AdvanceRatio_g)|;0.5,2
\right)
\]

\[
N_t^\sigma
=
1-
\operatorname{Ramp}
\left(
|RZ_t(RealizedVolatility_{\cdot,5})|;0.5,2
\right)
\]

\[
S_t^{Neutral}
=
0.30N_t^R
+0.25N_t^V
+0.25N_t^B
+0.20N_t^\sigma
\]

중립 점수는 다른 세 점수의 보수가 아니다. 수익률, 거래량, 시장 확산, 실현 변동성이 각자의 기준선에 얼마나 가까운지 독립적으로 측정한다.

### 15.2 포모 시작 전 점수

\[
PrePriceFamily_t
=
0.35M_t
+0.30A_t
+0.20B_t
+0.15E_t
\]

\[
S_t^{Pre}
=
0.65PrePriceFamily_t
+0.35V_t^\*
\]

### 15.3 포모 진행 점수

\[
FOMOPriceFamily_t
=
0.25M_t
+0.15A_t
+0.20B_t
+0.20E_t
+0.20U_t
\]

\[
FOMOParticipationFamily_t
=
0.40V_t^\*
+0.30D_t
+0.30\Lambda_t
\]

\[
S_t^{FOMO}
=
0.55FOMOPriceFamily_t
+0.45FOMOParticipationFamily_t
\]

### 15.4 포모 해소 점수

\[
Q_t^{Candle}
=
0.5Q_t^W
+0.5Q_t^C
\]

\[
S_t^{Resolve}
=
0.25Q_t^M
+0.20Q_t^V
+0.15Q_t^{Candle}
+0.15Q_t^F
+0.15Q_t^R
+0.10Q_t^D
\]

가격 파생값은 가격 가족 안에서 먼저 결합하고, 거래량·확산은 참여 가족으로 분리해 같은 가격 경로의 반복 가중을 제한한다. 위꼬리와 약한 종가는 봉 거부 가족으로 먼저 묶는다.

네 점수는 서로 합해서 1이 되는 상태확률이 아니다. 각 점수는 기준선 근접, 점화, 진행, 해소 증거의 독립적인 0~1 강도다.

## 16. 상태 전이 계약

\[
State_t
\in
\{
Neutral,\,
OtherAbnormal,\,
PreFOMO,\,
FOMO,\,
Resolving,\,
Unavailable
\}
\]

### 16.1 산출 불가

현재 상태 판정에 필요한 점수 또는 게이트가 결측이면 \(State_t=Unavailable\)이다. 산출 불가를 중립으로 바꾸지 않는다.

| 이전 유효 상태 | 현재 판정에 필수인 점수·메모리 |
| --- | --- |
| Neutral, OtherAbnormal | \(S^{Neutral},S^{Pre}\) |
| PreFOMO | \(S^{Neutral},S^{Pre},S^{FOMO},S^{Resolve}\), 사건 코호트 |
| FOMO | \(S^{FOMO},S^{Resolve}\), 사건 코호트와 \(\tau_P,\tau_F,RunningFOMOPeak\) |
| Resolving | 네 점수, 사건 코호트와 모든 가용 사건 anchor |
| Unavailable | 복구 판정에 \(S^{Neutral}\) |

현재 상태에 필요하지 않은 선택적 점수가 결측이라는 이유만으로 Unavailable로 바꾸지 않는다.

이전 상태는 마지막 유효 상태로 별도 보존할 수 있지만, 산출 불가 기간에 상태가 유지됐다고 기록하지 않는다.

### 16.1.1 허용 전이 행렬

| 이전 상태 | 허용되는 다음 상태 |
| --- | --- |
| Neutral | Neutral, OtherAbnormal, PreFOMO, Unavailable |
| OtherAbnormal | OtherAbnormal, Neutral, PreFOMO, Unavailable |
| PreFOMO | PreFOMO, FOMO, Neutral, OtherAbnormal, Unavailable |
| FOMO | FOMO, Resolving, Unavailable |
| Resolving | Resolving, FOMO, Neutral, OtherAbnormal, Unavailable |
| Unavailable | Unavailable, Neutral, OtherAbnormal |

Neutral에서 FOMO로 직접 이동하지 않는다. 강한 신호가 두 점수의 진입 조건을 동시에 충족해도 먼저 PreFOMO를 기록하고, 다음 유효 거래일 이후에만 FOMO로 이동할 수 있다.

모델의 첫 유효 산출일과 Unavailable 복구일에는 연속 확인 카운터를 모두 0으로 초기화한다. \(S_t^{Neutral}\geq0.70\)이면 Neutral, 그렇지 않으면 OtherAbnormal에서 시작한다.

### 16.1.2 중립과 기타 비정상

중립 진입 또는 복귀:

\[
\operatorname{Consecutive}_2
\left(
S_t^{Neutral}\geq0.70
\right)=1
\]

기타 비정상 진입:

\[
\operatorname{Consecutive}_2
\left(
S_t^{Neutral}<0.50
\right)=1
\]

두 임계값 사이에서는 이전의 중립 또는 기타 비정상 상태를 유지한다. 단, 포모 시작 전 진입 조건이 충족되면 PreFOMO 전이가 우선한다.

### 16.2 중립에서 포모 시작 전으로 진입

다음 조건이 모두 충족되어야 한다.

1. 포모 시작 전 점수가 0.55 이상인 상태가 이틀 연속 이어진다.
2. 가격 모멘텀 활성화가 0.30 이상이다.
3. 거래량 팽창 활성화가 0.30 이상이다.
4. 상승 가속과 돌파 강도 중 하나가 0.40 이상이다.

수식:

\[
\operatorname{Consecutive}_2
\left(
S_t^{Pre}\geq0.55
\right)=1
\]

\[
M_t\geq0.30,\qquad
V_t^\*\geq0.30,\qquad
\max(A_t,B_t)\geq0.40
\]

PreFOMO 진입일의 계산 순서는 다음 두 단계로 고정한다.

1. 사건 메모리가 필요 없는 \(S_t^{Neutral}\), \(S_t^{Pre}\)와 진입 게이트로 전이를 먼저 판정한다.
2. 전이가 확인되면 같은 행의 \(\tau_P=t\)를 기록하고 사건 코호트·고정 기준선을 생성한 뒤 \(S_t^{FOMO}\), \(S_t^{Resolve}\)를 재계산해 저장한다.

같은 \(\tau_P\) 행에서 FOMO로 다시 전이하지 않는다. \(\tau_P\) 행은 FOMO·해소 연속 확인의 첫 번째 관측으로만 사용할 수 있으므로 가장 빠른 FOMO 진입은 다음 유효 거래일이다.

### 16.3 포모 시작 전 유지

다음 조건이면 기존 포모 시작 전 상태를 유지한다.

1. 포모 시작 전 점수가 0.35 이상이다.
2. 해소 점수가 0.60 미만이다.
3. 포모 진행 진입 조건은 아직 충족하지 않았다.

임계값 사이의 하루짜리 모호한 관측은 기존 상태를 유지한다.

### 16.4 포모 시작 전 이탈

포모 진행으로 이동하려면 16.5의 전체 포모 진행 진입 조건을 충족해야 한다. 점수 조건은 다음과 같다.

\[
\operatorname{Consecutive}_2
\left(
S_t^{FOMO}\geq0.68
\right)=1
\]

시작 전 점수가 약해졌을 때 중립 점수가 이틀 연속 0.70 이상이면 중립으로 복귀하고, 그렇지 않으면 기타 비정상으로 이동한다.

\[
\operatorname{Consecutive}_3
\left(
S_t^{Pre}<0.35
\right)=1
\]

해소 점수가 높아져 포모로 발전하지 못한 setup 실패도 중립 점수가 이틀 연속 0.70 이상이면 중립, 그렇지 않으면 기타 비정상으로 이동한다.

\[
\operatorname{Consecutive}_2
\left(
S_t^{Resolve}\geq0.60
\right)=1
\]

### 16.5 포모 진행 진입

직전 유효 상태가 PreFOMO일 때만 다음 조건을 평가하며, 모두 충족되어야 한다.

1. 포모 진행 점수가 0.68 이상인 상태가 이틀 연속 이어진다.
2. 가격 모멘텀 활성화가 0.50 이상이다.
3. 거래량 팽창 활성화가 0.40 이상이다.
4. 업종 확산과 후발주 확산 중 하나가 0.40 이상이다.
5. 방향성 추세 효율 활성화가 0.30 이상이다.
6. 해소 점수가 0.55 미만이다.

\[
\operatorname{Consecutive}_2
\left(
S_t^{FOMO}\geq0.68
\right)=1
\]

\[
M_t\geq0.50,\qquad
V_t^\*\geq0.40
\]

\[
\max(D_t,\Lambda_t)\geq0.40,\qquad
E_t\geq0.30
\]

\[
S_t^{Resolve}<0.55
\]

조건이 확인된 두 번째 거래일이 포모 점화 사건일이다.

### 16.6 포모 진행 유지

다음 조건이면 포모 진행 상태를 유지한다.

1. 포모 진행 점수가 0.42 이상이다.
2. 해소 점수가 0.62 미만이다.
3. 급격한 붕괴 조건이 발생하지 않았다.

진입 기준 0.68보다 유지 기준 0.42를 낮게 두어 임계값 근처의 상태 진동을 막는다.

### 16.7 포모 진행 이탈

다음 중 하나가 발생하면 포모 해소 상태로 이동한다.

1. 해소 점수가 0.62 이상인 상태가 이틀 연속 이어진다.
2. 포모 진행 점수가 0.42 미만인 상태가 사흘 연속 이어진다.
3. 급격한 붕괴 조건이 하루에 모두 충족된다.

\[
\operatorname{Consecutive}_2
\left(
S_t^{Resolve}\geq0.62
\right)=1
\]

\[
\operatorname{Consecutive}_3
\left(
S_t^{FOMO}<0.42
\right)=1
\]

급격한 붕괴:

\[
HardBreakdown_t
=
\mathbb{1}
\left(
RZ_t(r^{(1)})\leq-2
\right)
\mathbb{1}
\left(
C_t<MA_{t,10}
\right)
\mathbb{1}
\left(
CloseLocation_t\leq0.25
\right)
\]

급격한 붕괴는 연속 확인 없이 당일 즉시 적용한다.

### 16.8 포모 해소 유지

먼저 16.9의 재점화와 16.10의 완전 정상화·기타 비정상 인계 조건을 평가한다. 어느 이탈 조건도 충족하지 않았을 때만 Resolving을 유지한다.

해소 점수, 포모 진행 점수, 10일 이동평균 위치와 공동 정상화 진행도는 해소 경로를 설명하는 진단값이며, 우선순위가 높은 이탈 조건을 무효화하지 않는다.

### 16.9 재점화

다음 조건이 모두 충족되면 해소에서 포모 진행으로 이동한다.

1. 포모 진행 점수가 0.70 이상인 상태가 이틀 연속 이어진다.
2. 거래량 팽창 활성화가 0.40 이상이다.
3. 이전 포모 고점을 ATR 0.25배 이상 넘은 종가를 이틀 유지한다.
4. 해소 점수가 0.45 미만이다.

\[
\operatorname{Consecutive}_2
\left(
S_t^{FOMO}\geq0.70
\right)=1
\]

\[
V_t^\*\geq0.40,\qquad
StrongRebreakHold_{t,2}=1,\qquad
S_t^{Resolve}<0.45
\]

재점화가 확인된 당일에는 같은 episode에서 segment ID를 \(k\leftarrow k+1\)로 증가시키고 다음 메모리를 초기화한다.

\[
\tau_F^{(k)}=t,\qquad
RunningFOMOPeak_t^{(k)}=H_t
\]

새 segment의 \(\tau_R^{(k)},P_k^{FOMO},\tau_T,T^{FOMO}\)와 반등 실패 상태는 아직 not_applicable이다. episode의 \(\tau_P\), 고정 정규화 기준선과 사건 코호트는 유지한다.

### 16.10 완전 해소

다음 조건이 5거래일 연속 유지되면 해소에서 중립으로 이동한다.

1. 중립 점수가 0.70보다 높다.
2. 포모 진행 점수가 0.35 미만이다.
3. 해소 점수가 0.35 미만이다.
4. 5일 수익률의 rolling 이상도와 사건 전 고정 이상도가 모두 1 미만이다.
5. 거래량의 rolling 이상도와 사건 전 고정 이상도가 모두 1 미만이다.
6. 거래량이 사건 전 기준의 약 0.67배에서 1.5배 사이다.
7. 단기 변동성이 rolling·사건 전 기준 모두에서 약 0.67배에서 1.5배 사이다.
8. 가격이 20일 이동평균에서 ATR 1배 이내에 있다.

\[
JointNormalizationDistance_t
=
\max
\left(
\frac{1-S_t^{Neutral}}{0.30},
\frac{S_t^{FOMO}}{0.35},
\frac{S_t^{Resolve}}{0.35},
|RZ_t(r^{(5)})|,
|AnchorRZ_{t;\tau_P}(r^{(5)})|,
|RZ_t(LogVolume)|,
\left|AnchorRZ_{t;\tau_P}(LogVolume)\right|,
\frac{|\ln(AnchorRVOL_{t;\tau_P})|}{\ln(1.5)},
\frac{VolatilityNormalization_t}{\ln(1.5)},
\frac{
|\ln(AnchorVolatilityRatio_{t;\tau_P})|
}{
\ln(1.5)
},
|U_t^{raw}|
\right)
\]

\[
JointNormalization_t
=
\mathbb{1}
\left(
JointNormalizationDistance_t<1
\right)
\]

\[
JointNormalizationPersistence_{t,5}
=
\prod_{j=0}^{4}
JointNormalization_{t-j}
\]

완전 해소 조건:

\[
JointNormalizationPersistence_{t,5}=1
\]

포모·해소 점수는 모두 낮지만 중립 점수가 0.50 미만인 상태가 5일 연속 이어지면 포모 사건을 종료하고 기타 비정상으로 인계한다.

\[
\operatorname{Consecutive}_5
\left(
S_t^{FOMO}<0.35
\land
S_t^{Resolve}<0.35
\land
S_t^{Neutral}<0.50
\right)=1
\]

### 16.11 전이 우선순위

전이는 16.1.1의 이전 상태별 허용 행렬 안에서만 평가한다. 같은 이전 상태에서 여러 조건이 동시에 성립하면 다음 순서를 적용한다.

1. 산출 불가
2. FOMO의 급격한 붕괴 또는 해소 진입
3. Resolving의 재점화
4. Resolving의 완전 정상화
5. Resolving의 기타 비정상 인계
6. PreFOMO의 포모 진행 진입
7. PreFOMO의 setup 무산
8. Neutral·OtherAbnormal의 포모 시작 전 진입
9. Neutral과 OtherAbnormal 사이의 전이
10. 기존 상태 유지

### 16.12 상태 조건 요약

| 상태 | 진입 | 유지 | 이탈 |
| --- | --- | --- | --- |
| 포모 시작 전 | 시작 전 점수 0.55 이상 2일과 모멘텀·거래량·가속 또는 돌파 게이트 | 시작 전 점수 0.35 이상, 해소 점수 0.60 미만 | 진행 조건 확인 시 포모 진행, setup 무산 시 중립 점수에 따라 Neutral 또는 OtherAbnormal |
| 포모 진행 | 진행 점수 0.68 이상 2일과 모멘텀·거래량·확산·추세 게이트 | 진행 점수 0.42 이상, 해소 점수 0.62 미만 | 해소 점수 0.62 이상 2일, 진행 점수 0.42 미만 3일 또는 급격한 붕괴 |
| 포모 해소 | 진행 상태의 해소 증거 또는 동력 상실 | 해소 증거가 남거나 진행 조건이 회복되지 않음 | 공동 정상화 5일 또는 재점화 |
| 중립 | 중립 점수 0.70 이상 2일 또는 완전 해소 | 중립 점수 0.50 이상이고 시작 전 조건 미충족 | 시작 전 조건 또는 기타 비정상 조건 충족 |
| 기타 비정상 | 중립 점수 0.50 미만 2일 또는 해소 후 비정상 인계 | 중립 점수가 0.70 미만이고 포모 시작 전 조건 미충족 | 중립 점수 0.70 이상 2일 또는 시작 전 조건 충족 |
| 산출 불가 | 필수 입력·점수·게이트 결측 | 결측 지속 | 입력 복구 후 확인 카운터를 초기화하고 중립 점수에 따라 Neutral 또는 OtherAbnormal에서 새로 판정 |

### 16.13 해소 모드

해소 모드는 서로 배타적이라고 가정하지 않고 확인된 모드 목록으로 출력한다.

\[
PriceCorrectionMode_t
=
\mathbb{1}
\left(
DrawdownFromFOMOPeak_t<-0.10
\lor
HardBreakdown_t=1
\right)
\]

\[
TimeCorrectionMode_t
=
\mathbb{1}
\left(
TimeCorrectionDuration_t\geq5
\right)
\]

\[
ReboundFailureMode_t
=
ReboundFailure_t
\]

\[
NormalizationMode_t
=
JointNormalizationPersistence_{t,5}
\]

재점화 조건이 확인되면 re_ignition을 기록하고 Resolving에서 FOMO로 이동한다.

## 17. 단계별 관찰 프로필

### 17.1 포모 시작 전 프로필

가격:

- 5일 수익률 이상도가 상승한다.
- 최근 상승 속도가 직전 구간보다 빨라진다.
- 20일 고점에 접근하거나 돌파한다.
- 장대양봉과 고점 부근 종가가 증가한다.

거래량:

- RVOL과 로그 거래량 이상도가 상승하기 시작한다.
- 최근 5일 거래량 중앙값이 이전 15일보다 커진다.
- 거래량 급증이 아직 모든 날에 지속되지는 않는다.

확산:

- 선도주 수익률이 후발주보다 먼저 높아진다.
- 대장주 편중도가 높다.
- 업종 상승 종목 비율은 아직 광범위하지 않다.

### 17.2 포모 진행 프로필

가격:

- 비정상 수익률, 상승 가속, 돌파 강도가 동시에 높다.
- 가격이 최근 고점과 이동평균 위에 머문다.
- 최대 낙폭이 얕고 방향성 추세 효율이 높다.

거래량:

- RVOL, 거래량 이상도, 거래량 지속성이 높다.
- 상승 봉 거래량 비율이 높다.
- 가격과 거래량이 동시에 팽창한다.

확산:

- 업종 상승 종목 비율과 시장 초과 상승 종목 비율이 높다.
- 후발주 상승 비율과 후발주 평균 수익률이 증가한다.
- 대장주 편중도가 낮아지고 수익률 균등 확산도가 높아진다.

### 17.3 포모 해소 프로필

가격:

- 가격이 고점에 있더라도 상승 가속도가 음수로 전환한다.
- 신고가 돌파가 종가까지 유지되지 않는다.
- 위꼬리가 길어지고 종가 위치가 약해진다.
- 음의 비정상 수익률이 나타난다.

거래량:

- 거래량은 높은데 가격 진전이 줄어든다.
- 거래량 대비 가격 효율이 하락한다.
- 가격 신고가와 거래량·모멘텀이 서로 다른 방향으로 움직인다.

확산:

- 대장주는 버티지만 상승 종목 비율이 감소한다.
- 후발주 상승 비율이 하락한다.
- 대장주 편중도가 다시 높아진다.

정상화:

- 가격 조정에서는 고점 대비 낙폭이 확대된다.
- 기간 조정에서는 가격 낙폭이 제한된 채 모멘텀과 거래량이 정상화된다.
- 완전 해소에서는 가격, 수익률, 거래량, 변동성, 이동평균 이격이 함께 평상시 범위로 돌아온다.

## 18. 핵심 점수 밖의 확장 지표

이 절은 앞서 다룬 개념을 빠뜨리지 않기 위한 확장 원장이다. 아래 값은 OHLCV 핵심 점수에 넣지 않는다.

### 18.1 회전율

유통주식 수가 추가로 제공될 때 계산한다.

\[
Turnover_t
=
\operatorname{safeRatio}
\left(
V_t,
FreeFloatShares_t
\right)
\]

\[
RelativeTurnover_t
=
\operatorname{safeRatio}
\left(
Turnover_t,
\operatorname{Median}(Turnover_{t-1},\ldots,Turnover_{t-20})
\right)
\]

시점별 유통 시가총액이 제공될 때 소형 후발주 확산을 별도로 계산한다. 시점 \(t-1\) 유통 시가총액 하위 50% 집합을 \(SmallCap_{g,t}\)라고 한다.

\[
SmallCapAdvanceRatio_{g,t}
=
\frac{
\sum_{i\in SmallCap_{g,t}}
\mathbb{1}(r_{i,t}^{(1)}>0)
}{
|SmallCap_{g,t}|
}
\]

시가총액 가중 업종 수익률:

\[
CapWeightedReturn_{g,t}
=
\sum_{i\in G_{g,t}}
\omega_{i,t-1}r_{i,t}^{(1)}
\]

\[
\omega_{i,t-1}
=
\frac{
FreeFloatMarketCap_{i,t-1}
}{
\sum_{j\in G_{g,t}}
FreeFloatMarketCap_{j,t-1}
}
\]

광범위한 참여와 대형주 중심 상승의 차이:

\[
ParticipationGap_{g,t}
=
EqualWeightedReturn_{g,t}
-CapWeightedReturn_{g,t}
\]

### 18.2 공격적 매수 비율

체결 방향이 제공될 때 계산한다.

\[
AggressiveBuyRatio_t
=
\operatorname{safeRatio}
\left(
BuyerInitiatedVolume_t,
BuyerInitiatedVolume_t+SellerInitiatedVolume_t
\right)
\]

### 18.3 체결 불균형

\[
TradeImbalance_t
=
\operatorname{safeRatio}
\left(
BuyerInitiatedVolume_t-SellerInitiatedVolume_t,
BuyerInitiatedVolume_t+SellerInitiatedVolume_t
\right)
\]

### 18.4 누적 체결량 델타

\[
TradeVolume_t
=
BuyerInitiatedVolume_t
+SellerInitiatedVolume_t
\]

\[
CVD_t
=
\sum_{\tau=\tau_0}^{t}
\left(
BuyerInitiatedVolume_\tau
-SellerInitiatedVolume_\tau
\right)
\]

\(\tau_0\)는 세션 시작 또는 사전 고정된 관찰 창 시작이며 모델 버전에 기록한다.

\[
CVDSlope_t^{(h)}
=
\operatorname{safeRatio}
\left(
CVD_t-CVD_{t-h},
\sum_{j=0}^{h-1}TradeVolume_{t-j}
\right)
\]

\[
CVDAcceleration_t^{(h)}
=
CVDSlope_t^{(h)}
-CVDSlope_{t-h}^{(h)}
\]

### 18.5 개인투자자의 공격적 매수

체결과 투자자 유형이 연결될 때 계산한다.

\[
RetailAggressiveBuyRatio_t
=
\operatorname{safeRatio}
\left(
RetailBuyerInitiatedVolume_t,
BuyerInitiatedVolume_t
\right)
\]

\[
RetailNetBuyIntensity_t
=
\operatorname{safeRatio}
\left(
RetailBuyValue_t-RetailSellValue_t,
\operatorname{Median}
\left(
TradingValue_{t-1},\ldots,TradingValue_{t-20}
\right)
\right)
\]

기준가격 \(P_t^{reference}\)보다 높은 가격에서 체결된 개인 매수의 비율:

\[
RetailChasingRatio_t
=
\operatorname{safeRatio}
\left(
RetailBuyVolume_t(P>P_t^{reference}),
RetailTotalBuyVolume_t
\right)
\]

기준가격은 전일 종가, 당일 VWAP, 직전 고점 또는 돌파가격 중 하나로 모델 버전에서 고정한다.

### 18.6 호가 잔량 불균형

\[
OrderBookImbalance_t
=
\operatorname{safeRatio}
\left(
BidDepth_t-AskDepth_t,
BidDepth_t+AskDepth_t
\right)
\]

1호가, 5호가, 10호가 깊이는 서로 다른 지표 ID로 저장한다.

매도호가 소진율:

\[
AskDepletionRate_t^{(h)}
=
\operatorname{safeRatio}
\left(
AskDepth_{t-h}-AskDepth_t,
AskDepth_{t-h}
\right)
\]

매수호가 증가율:

\[
BidBuildRate_t^{(h)}
=
\operatorname{safeRatio}
\left(
BidDepth_t-BidDepth_{t-h},
BidDepth_{t-h}
\right)
\]

가격 충격:

\[
AggressiveBuyImpact_t^{(h)}
=
\operatorname{safeRatio}
\left(
\ln(P_t/P_{t-h}),
\sum_{\tau=t-h+1}^{t}
\left(
BuyerInitiatedVolume_\tau-SellerInitiatedVolume_\tau
\right)
\right)
\]

순공격매수량이 0 이하이면 공격적 매수 가격 충격은 결측으로 둔다.

### 18.7 가격 제한폭 접근

거래소의 당일 상한가가 \(UpperLimitPrice_t\)로 제공될 때 계산한다.

\[
UpperLimitDistance_t
=
\operatorname{scaleRatio}
\left(
UpperLimitPrice_t-C_t,
ATR_{t,20}
\right)
\]

\[
UpperLimitProximity_t
=
1-
\operatorname{clip}
\left(
UpperLimitDistance_t,
0,1
\right)
\]

### 18.8 개인별 놓친 상승폭

사용자 \(u\)가 종목 \(i\)를 처음 확인한 시점을 \(t_{first}\)라고 한다.

\[
PersonalMissedGain_{u,i,t}
=
\frac{C_{i,t}}{C_{i,t_{first}}}-1
\]

과거 매도 이후 놓친 상승폭:

\[
PostSaleMissedGain_{u,i,t}
=
\frac{C_{i,t}}{SalePrice_{u,i}}-1
\]

### 18.9 계획 없는 매수

\[
UnplannedBuy_{u,i,t}
=
\mathbb{1}
\left(
NoPriorWatchlist_{u,i,t}
\land
NoTargetPrice_{u,i,t}
\land
DecisionTime_{u,i,t}<\delta
\right)
\]

의사결정 시간 임계값 \(\delta\)는 사용자 행동 모델의 별도 버전에서 고정한다.

### 18.10 관심도와 상승 서사

뉴스와 관심도는 핵심 모델에서 제외하지만 확장 계층에서는 다음처럼 정의할 수 있다.

\[
AttentionSurprise_t
=
RZ_t(Attention)
\]

\[
NarrativeStrength_t
=
w_1NewsVolume_t
+w_2PositiveSentiment_t
+w_3Novelty_t
+w_4TopicConcentration_t
\]

가중치는 별도 연구에서 고정해야 하며 이 문서의 합성 점수에는 사용하지 않는다.

### 18.11 가격 상승과 추격 매수의 자기강화

직전 수익률이 다음 구간의 공격적 매수를 증가시키는지 추정한다.

\[
\widehat{AggressiveBuyRatio}_t
=
\alpha
+\beta r_{t-1}^{(1)}
+\epsilon_t
\]

\[
\beta>0
\]

공격적 매수가 같은 구간의 가격 상승과 연결되는지도 별도로 추정한다.

\[
r_t^{(1)}
=
\gamma
+\delta TradeImbalance_t
+\eta_t
\]

\[
\delta>0
\]

\(\beta\)와 \(\delta\)가 모두 양수인 구간은 가격 상승과 추격 매수가 서로 강화되는 후보 구간이다. 계수는 rolling OLS 또는 사전 고정된 상태공간 모형으로 추정하며 OHLCV 핵심 점수에는 넣지 않는다.

### 18.12 개념별 확장 데이터

| 개념 | 추가 데이터 |
| --- | --- |
| 개인 공격적 매수 | 체결 방향과 투자자 유형 |
| 체결 압력 | 틱 체결과 aggressor side |
| 체결 참여도 | 체결 건수, 평균 체결 크기, 소액·대량 체결 구분 |
| 호가 압력 | 시점 순서가 보존된 호가·취소·수정 사건 |
| 소형주 확산 | point-in-time 유통 시가총액 |
| 가격 제한폭 접근 | 거래소별 당일 상·하한 가격과 VI 상태 |
| 개인적 후회 | 최초 조회, 관심 등록, 과거 매도, 미체결 기록 |
| 계획 부재 | 목표 가격, 손절 기준, 주문 전 계획 기록 |
| 상승 서사 | 뉴스, 검색, 커뮤니티, 주제 모델 |

## 19. 결측·경계·예외 처리

### 19.1 결측 원칙

1. 필수 입력 결측을 0, 중립 또는 직전값으로 대체하지 않는다.
2. 결측 구성요소를 제거한 뒤 남은 가중치를 재정규화하지 않는다.
3. 결측 상태는 Unavailable로 출력한다.
4. 결측이 해소된 첫날에는 연속 확인 카운터를 초기화하고 중립 상태에서 새로 판정한다.
5. 결측 기간을 연속 확인 일수에 포함하지 않는다.

### 19.2 분모가 0인 경우

원자 지표에 명시된 piecewise 정의가 공통 safeRatio보다 우선한다.

- scaleRatio는 스케일과 분자가 모두 0이면 0, 스케일만 0이고 분자가 0이 아니면 결측이다.
- \(H=L=O=C\)인 유효 무변동 봉은 9.13의 중립 봉 값으로 계산한다.
- 업종 내 양의 수익률 합이 0이면 선도주 집중도와 수익률 확산도는 11.9~11.10의 명시식에 따라 0이다.
- 위의 명시적 예외가 없는 safeRatio 분모 0 또는 음수는 결측이다.
- 과거 거래량 중앙값 0, rank-deficient 초과수익률 회귀, 포모 고점과 확인 저점이 같은 반등 회복률은 결측이다.
- OHLC 관계가 일관되지 않은 0범위 봉은 결측이다.

### 19.3 거래정지와 무거래

- 거래정지 봉은 0수익률 정상 관측으로 처리하지 않는다.
- 거래량 0이 실제 무거래인지 데이터 누락인지 공급자 상태로 구분한다.
- 거래정지 기간은 연속 상승·연속 확인 일수에서 제외한다.

### 19.4 기업행동

- 액면분할, 병합, 대규모 배당, 권리락을 수정주가 정책으로 처리한다.
- 가격과 거래량의 조정 단위가 일치하지 않으면 거래량 특징을 산출하지 않는다.
- 종목 합병·분할·티커 변경은 point-in-time 식별자로 연결한다.

### 19.5 업종 구성 변경

- 시점 \(t\)에 실제 편입된 종목만 \(G_{g,t}\)에 포함한다.
- 상장폐지 종목을 과거 표본에서 제거하지 않는다.
- 신규 상장 종목은 필요한 lookback을 확보하기 전 개별 특징과 확산 계산에서 결측으로 처리한다.
- 유효 구성 종목 비율과 제외 사유를 함께 출력한다.

### 19.6 상한가와 하한가

- 가격 제한폭 도달은 수익률과 돌파 지표에 그대로 반영한다.
- 상한가의 짧은 고가 체류를 일반적인 유동시장 고점 체류와 혼합하지 않도록 limit_state를 별도 출력한다.
- 다음 거래일 갭과 거래량으로 상태 지속 여부를 다시 판정한다.

### 19.7 동일값과 순위

- 횡단면 순위에서 동일값은 midrank를 사용한다.
- 선도주는 5일 수익률 midrank 백분위가 0.80을 엄격히 초과한 종목만 포함한다.
- 경계 동일값을 억지로 잘라 선도주 수를 20%에 맞추지 않으며 실제 선도주 비율을 출력한다.
- 모든 수익률이 같아 선도주가 없으면 후발주 집합을 전체 종목으로 유지한다.
- 임의의 종목 코드 순서로 경계값을 나누지 않는다.

### 19.8 일봉과 장중 모델 분리

이 문서의 가중치와 임계값은 일봉용이다. 분봉 모델은 별도 버전으로 관리한다.

분봉으로 변환할 때 지켜야 할 규칙:

1. 거래량은 과거 동일 시간대 분포와 비교한다.
2. 장 시작과 장 마감의 계절성을 같은 기준선으로 섞지 않는다.
3. 일 단위의 2일·3일·5일 확인 조건을 봉 개수로 단순 치환하지 않는다.
4. 장중 미완성 봉은 상태 판정에서 제외한다.
5. 일봉과 분봉 상태를 같은 점수 ID로 저장하지 않는다.

## 20. 검증 계약

### 20.1 수학적 불변조건

다음 조건을 자동 검증한다.

1. Ramp 출력은 항상 0과 1 사이다.
2. 각 합성 점수의 가중치 합은 1이다.
3. 유효 입력에서 네 합성 점수는 항상 0과 1 사이다.
4. 가격을 동일 비율로 환산해도 ATR 정규화 특징은 변하지 않는다.
5. 미래 행을 추가하거나 변경해도 시점 \(t\)의 특징과 상태는 변하지 않는다.
6. 구성 종목 순서를 바꿔도 확산 지표는 변하지 않는다.
7. 결측 구성요소가 생기면 점수가 낮아지는 것이 아니라 산출 불가가 된다.

### 20.2 합성 시나리오

| 시나리오 | 기대 결과 |
| --- | --- |
| 평평한 가격과 정상 거래량 | 중립 |
| 가격만 급등하고 거래량·확산 없음 | 포모 진행 진입 거부 |
| 가격·거래량 상승, 확산 전 | 포모 시작 전 |
| 가격·거래량·업종·후발주 동시 상승 | 포모 진행 |
| 고거래량, 낮은 가격 진전, 긴 위꼬리 | 포모 해소 |
| 얕은 낙폭과 모멘텀·거래량 정상화 | 기간 조정형 해소 |
| 거래량을 동반한 이전 고점 재돌파 | 포모 재점화 |
| 가격·거래량·변동성 공동 정상화 5일 | 중립 복귀 |
| 필수 업종 구성 데이터 결측 | 산출 불가 |

### 20.3 미래 경로 라벨

시점 \(t\)의 ATR로 향후 \(h\)일 최대유리변동과 최대불리변동을 무차원화한다.

라벨은 \(t+1\)부터 \(t+h\)까지 거래소 달력의 \(h\)개 세션에 유효한 고가·저가·종가가 모두 있을 때만 계산한다.

\[
LabelAvailability_{t,h}
=
\begin{cases}
available,& \text{향후 }h\text{개 세션이 모두 유효}\\
censored,& \text{표본 말단, 거래정지, 상장폐지 또는 미래 봉 결측}\\
\end{cases}
\]

censored 행의 MFE, MAE, 지속·해소 라벨과 path outcome은 모두 결측이다. 음성 라벨로 바꾸지 않으며 horizon별 label coverage를 함께 보고한다.

\[
MFE_{t,h}^{ATR}
=
\operatorname{scaleRatio}
\left(
\max_{1\leq j\leq h}H_{t+j}-C_t,
ATR_{t,20}
\right)
\]

\[
MAE_{t,h}^{ATR}
=
\operatorname{scaleRatio}
\left(
\min_{1\leq j\leq h}L_{t+j}-C_t,
ATR_{t,20}
\right)
\]

지속 라벨:

\[
ContinuationLabel_{t,h}
=
\mathbb{1}
\left(
MFE_{t,h}^{ATR}\geq0.5
\land
MAE_{t,h}^{ATR}>-0.3
\right)
\]

해소 라벨:

\[
ExhaustionLabel_{t,h}
=
\mathbb{1}
\left(
MAE_{t,h}^{ATR}\leq-0.5
\lor
C_{t+h}<MA_{t,10}
\right)
\]

지속과 해소 라벨은 독립 다중라벨이다. 둘이 동시에 1인 관측을 임의로 한쪽에 배정하지 않고 joint_positive로 별도 보고한다.

일봉 안에서 상방·하방 장벽의 선후를 알 수 없는 문제를 다음 competing path 결과로 보존한다.

\[
\tau_{up}
=
\min
\left\{
j\in\{1,\ldots,h\}:
H_{t+j}\geq C_t+0.5ATR_{t,20}
\right\}
\]

\[
\tau_{down}
=
\min
\left\{
j\in\{1,\ldots,h\}:
L_{t+j}\leq C_t-0.5ATR_{t,20}
\right\}
\]

장벽에 도달하지 않으면 해당 시점을 \(+\infty\)로 둔다.

\[
PathOutcome_{t,h}
=
\begin{cases}
up\_first,& \tau_{up}<\tau_{down}\\
down\_first,& \tau_{down}<\tau_{up}\\
both\_same\_bar\_ambiguous,& \tau_{up}=\tau_{down}<+\infty\\
neither,& \tau_{up}=\tau_{down}=+\infty
\end{cases}
\]

라벨은 특징이나 상태 입력으로 사용하지 않는다.

### 20.4 비교 기준선

복합 점수는 다음 단순 기준선과 비교한다.

1. 5일 로그수익률
2. 20일 상대 거래량
3. 20일 고점 돌파 여부
4. 10일 방향성 추세 효율
5. 업종 상승 종목 비율
6. 위 기준선의 동일가중 결합

### 20.5 시계열 검증

1. 시간순 walk-forward를 사용한다.
2. 결과 horizon 이상을 train과 test 사이에서 purge한다.
3. 인접 사건의 중복을 막기 위해 embargo를 둔다.
4. 임계값과 가중치는 학습 구간에서만 선택한다.
5. 최종 holdout을 확인한 뒤 같은 표본에서 다시 조정하지 않는다.
6. 여러 종목, 시가총액, 업종, 상승장, 하락장, 횡보장에서 따로 보고한다.

### 20.6 평가 지표

- 지속·해소 전이 결과별 precision, recall, F1, MCC
- 지속·해소 다중라벨의 ROC-AUC와 PR-AUC
- competing path 결과의 macro F1과 confusion matrix
- 포모 진행 점수 분위별 미래 MFE와 MAE
- 상태 진입 후 해소까지의 지속시간
- 오탐, 미탐, 조기 탐지 일수
- 종목·업종·시장 국면별 안정성
- 상태 전이 행렬과 비정상 진동 횟수
- 산출 coverage와 결측 원인별 비율

독립적인 상태 구간 정답이 없으면 Neutral·PreFOMO·FOMO·Resolving 자체의 precision이나 recall을 보고하지 않는다. 외부에서 사전 고정한 사건 구간 라벨이 있을 때만 진입일 허용오차와 종료일 허용오차를 별도 정의해 상태 구간 성능을 평가한다.

### 20.7 확률 보정

네 합성 점수는 확률이 아니다. 확률 출력이 필요하면 전이 종류와 예측 horizon별로 학습 구간에서만 다음 보정기를 적합한다.

| probability outcome ID | predictor | target |
| --- | --- | --- |
| continuation_h | \(S_t^{FOMO}\) | \(ContinuationLabel_{t,h}\) |
| exhaustion_h | \(S_t^{Resolve}\) | \(ExhaustionLabel_{t,h}\) |
| up_first_h | 네 점수 벡터 | \(PathOutcome_{t,h}=up\_first\) |
| down_first_h | 네 점수 벡터 | \(PathOutcome_{t,h}=down\_first\) |
| ambiguous_same_bar_h | 네 점수 벡터 | \(PathOutcome_{t,h}=both\_same\_bar\_ambiguous\) |
| neither_h | 네 점수 벡터 | \(PathOutcome_{t,h}=neither\) |

지속과 해소는 독립 이진 보정기로 적합한다. competing path 결과는 하나의 multinomial 보정기로 적합해 범주 확률 합이 1이 되도록 한다. horizon은 \(h\in\{1,3,5,10\}\)에서 사전 고정한다.

1. 표본이 충분하면 logistic calibration을 기본으로 사용한다.
2. 단조 비선형성이 반복 확인되면 isotonic calibration을 사전 선택 후보로 둔다.
3. 보정기 선택과 매개변수는 inner train에서만 정한다.
4. outer test와 terminal holdout에서는 보정기를 다시 적합하지 않는다.
5. Brier score, log loss, calibration intercept·slope, ECE와 reliability curve를 보고한다.
6. 사건 내 상관을 보존하는 episode-block bootstrap으로 불확실성 구간을 계산한다.
7. outcome ID, horizon, predictor schema, target schema, train 종료일과 표본 수를 calibrator artifact에 기록한다.
8. 적격 보정기가 없으면 확률을 임의로 만들지 않고 probability_unavailable을 출력한다.

### 20.8 버전 0.1.0의 고정 후보

이 문서에 적힌 lookback, 활성화 구간, 가중치, 진입·유지·이탈 임계값은 버전 0.1.0 후보의 한 묶음이다. 일부만 바꾼 결과를 같은 버전으로 보고하지 않는다.

## 21. 출력 계약

각 종목·거래일마다 다음 값을 출력한다.

| 필드 | 의미 |
| --- | --- |
| instrument_id | point-in-time 종목 식별자 |
| session_date | 거래소 기준 거래일 |
| as_of | 상태 산출 가능 시각 |
| model_id | chart_fomo_market_state_daily |
| model_version | 0.1.0 |
| official_state | 공식 가격·거래량 국면명 |
| display_alias | 설명용 포모 상태명 |
| previous_valid_state | 마지막 유효 상태 |
| episode_id | 포모 시작 전 진입 때 생성하는 사건 식별자 |
| segment_id | 재점화 때 증가하는 episode 내부 포모 segment 식별자 |
| episode_started_at | \(\tau_P\) |
| fomo_entered_at | 현재 segment의 \(\tau_F^{(k)}\) |
| resolving_entered_at | 현재 segment의 \(\tau_R^{(k)}\) |
| confirmed_trough_at | \(\tau_T\) |
| running_fomo_peak | FOMO 진행 중 갱신되는 \(RunningFOMOPeak_t\) |
| frozen_fomo_peak | Resolving 진입 때 동결된 \(P_k^{FOMO}\) |
| confirmed_trough | \(T^{FOMO}\) |
| state_duration | 현재 상태의 연속 유효 거래일 |
| resolution_modes | 가격 조정, 기간 조정, 반등 실패, 정상화, 재점화 목록 |
| neutral_score | 중립 기준선 근접 점수 |
| pre_score | 포모 시작 전 점수 |
| fomo_score | 포모 진행 점수 |
| resolve_score | 포모 해소 점수 |
| transition_reason | 상태 전이 원인 코드 |
| feature_values | 원자·활성화 특징 |
| required_coverage | 필수 입력 coverage |
| benchmark_id | 시장 기준지수 식별자와 vintage |
| sector_id | 업종 식별자와 분류체계 vintage |
| group_coverage_numerator | 유효 구성 종목 수 |
| group_coverage_denominator | 공식 구성 종목 수 |
| data_quality | complete, partial 또는 unavailable |
| missing_reasons | 결측 원인 목록 |
| fallback_flags | 표준편차 대체 등 예외 경로 |
| normalizer_version | rolling·anchor 정규화 버전 |
| parameter_version | lookback·가중치·임계값 버전 |
| calibrator_version | 확률 보정기 버전 또는 none |
| probabilities | outcome ID·horizon별 보정확률과 불확실성 |
| data_revision | 공급자 revision과 수신시각 |
| raw_data_hash | 원자료 artifact 해시 |
| processed_data_hash | 정제자료 artifact 해시 |
| adjustment_policy_id | 가격·거래량 조정 정책 |

data_quality의 의미는 다음과 같다.

- complete: 현재 상태 판정에 필요한 핵심 점수·게이트·필수 품질 필드가 모두 유효하다.
- partial: 핵심 상태는 완전하게 계산됐지만 선택적 진단 또는 확장 지표만 결측이다.
- unavailable: 핵심 점수·게이트·필수 계보 중 하나라도 결측이다.

running_fomo_peak는 FOMO에서만, frozen_fomo_peak와 confirmed_trough는 Resolving 이후에만 적용된다. 아직 해당 상태에 도달하지 않아 정의되지 않은 필드는 missing이 아니라 not_applicable로 기록한다.

probabilities의 각 원소는 다음 필드를 가진다.

| 필드 | 의미 |
| --- | --- |
| outcome_id | continuation, exhaustion 또는 competing path 범주 |
| horizon_sessions | 1, 3, 5 또는 10 |
| probability | 0과 1 사이의 보정확률 |
| interval_lower | episode-block 불확실성 하한 |
| interval_upper | episode-block 불확실성 상한 |
| calibrator_id | 사용한 보정 artifact |
| trained_through | 보정기가 본 마지막 거래일 |
| training_sample_size | 보정 적격 표본 수 |
| label_coverage | 해당 outcome·horizon 라벨 coverage |

### 21.1 전이 원인 코드

| 코드 | 의미 |
| --- | --- |
| pre_entry_confirmed | 시작 전 점수와 게이트 2일 확인 |
| ignition_confirmed | 진행 점수와 모멘텀·거래량·확산 게이트 확인 |
| pre_signal_faded | 시작 전 점수 3일 약화 |
| pre_signal_failed | 포모 전 해소 신호 확인 |
| other_abnormal_entered | 중립 점수 저하로 기타 비정상 진입 |
| baseline_restored | 중립 점수 회복 |
| resolving_confirmed | 해소 점수 2일 확인 |
| fomo_momentum_lost | 진행 점수 3일 약화 |
| hard_breakdown | 비정상 하락·10일선 이탈·약한 종가 동시 발생 |
| rebreak_confirmed | 거래량 동반 포모 고점 재돌파 |
| normalization_confirmed | 공동 정상화 5일 확인 |
| resolution_abnormal_handoff | 포모·해소 신호는 종료됐지만 기준선은 회복되지 않음 |
| required_input_missing | 필수 입력 결측 |

전이 원인 코드는 표에 정의한 영문 snake_case를 그대로 저장한다.

## 22. 개념 추적표

| 상위 개념 | 핵심 하위 개념 | 문서 위치 |
| --- | --- | --- |
| 단기 급등 | 수익률, 이상도, 초과수익률, 속도, 가속도 | 9.1~9.5 |
| 변동성 대비 상승 | ATR 수익률, 실현 변동성 | 9.6~9.7 |
| 신고가와 추격 위치 | 돌파, 범위 위치, 고점 거리, 이동평균 이격 | 9.8~9.11 |
| 즉시성 | 시가 갭, 장대양봉, 종가 위치 | 9.12~9.13 |
| 상승 지속 | 상승 봉 비율, 연속 상승, 런업, 최대 낙폭, 추세 효율 | 9.14~9.18 |
| 참여 급증 | RVOL, 거래량 이상도·가속·지속성 | 10.1~10.5 |
| 가격·거래량 결합 | 상승 봉 거래량, 동시 팽창, 가격 진전 | 10.7~10.10 |
| 시장 확산 | 상승·급등·신고가 종목 비율 | 11.1~11.6 |
| 후발주 확산 | 선도·후발 수익률, 편중도, 균등 확산 | 11.8~11.10 |
| 시장 동조 | 업종 평균 상관관계 | 11.11 |
| 소진 | 모멘텀 둔화, 돌파 실패, 가격 진전 둔화, 다이버전스 | 12.1~12.5 |
| 해소 유형 | 기간 조정, 반등 회복·실패, 재돌파, 정상화 | 12.6~12.11 |
| 상태 점수 | 중립, 시작 전, 진행, 해소 특징과 합성 점수 | 13~15 |
| 상태 전이 | 진입·유지·이탈·재점화·완전 해소 | 16 |
| 차트 밖 행동 | 공격적 매수, 개인 추격, 호가, 계획 부재, 관심 | 18 |
| 운영 안전성 | 결측·경계·기업행동·업종 변경 | 19 |
| 검증 | 불변조건, 시나리오, 라벨, 기준선, 시계열 검증 | 20 |

## 23. 용어집

| 용어 | 정의 |
| --- | --- |
| 점화 | 포모 시작 전에서 포모 진행으로 넘어가는 확인 사건 |
| 모멘텀 | 정해진 기간의 가격 상승 방향과 크기 |
| 가속도 | 최근 상승 속도와 바로 이전 상승 속도의 차이 |
| 돌파 | 현재 종가가 현재 봉 이전의 기간 고점을 넘어선 상태 |
| 확산 | 상승 참여가 선도주에서 업종·후발주로 넓어지는 현상 |
| 후발주 | 직전 5일 수익률이 업종 상위 20%가 아닌 구성 종목 |
| 소진 | 거래량이나 시장 참여가 유지돼도 추가 가격 상승 효과가 약해지는 상태 |
| 기타 비정상 | 기준선에서는 벗어났지만 포모 점화 조건을 충족하지 않은 국면 |
| 가격 조정 | 포모 고점에서 가격이 직접 하락하며 해소되는 경로 |
| 기간 조정 | 가격 하락은 제한되지만 모멘텀과 거래량이 정상화되는 경로 |
| 재점화 | 해소 중 거래량을 동반해 이전 포모 고점을 다시 돌파하는 사건 |
| 히스테리시스 | 진입 기준과 유지·이탈 기준을 다르게 두어 상태 진동을 막는 구조 |
| 공동 정상화 | 수익률, 거래량, 변동성, 이동평균 이격이 함께 평상시 범위로 돌아온 상태 |
| 산출 불가 | 필수 입력 또는 수학적 정의역이 부족해 상태를 계산하지 않은 결과 |

## 24. 최종 모델 요약

이 명세의 핵심 흐름은 다음과 같다.

\[
\text{가격·거래량 점화}
\rightarrow
\text{고점 돌파}
\rightarrow
\text{업종·후발주 확산}
\rightarrow
\text{추격상승 진행}
\]

\[
\rightarrow
\text{가격 진전 둔화}
\rightarrow
\text{돌파 실패·확산 축소}
\rightarrow
\text{가격 또는 기간 조정}
\rightarrow
\text{정상화 또는 재점화}
\]

운영 출력은 단일 포모 점수 하나가 아니라 다음 네 점수와 하나의 상태를 함께 제공한다.

\[
\left(
S_t^{Neutral},\,
S_t^{Pre},\,
S_t^{FOMO},\,
S_t^{Resolve},\,
State_t
\right)
\]

이 구조를 통해 상승의 초기 점화, 자기강화 진행, 소진, 해소, 재점화를 같은 관측 계약과 상태 전이 규칙 안에서 추적한다.
