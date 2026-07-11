# RP-001 통합 계약

## 1. 목적

통합은 여러 지표를 다시 가중합하는 단계가 아니다. 독립 외부검증을 통과한 study의 확률분포와 불확실성을 비용·위험 의사결정에 연결한다.

## 2. 허용 입력

- 동일 시점까지 이용 가능했던 외부 OOF 예측
- 사건별 확률과 calibration 상태
- 예측구간 또는 posterior uncertainty
- 입력 결측·OOD·abstain 상태
- 체결확률과 비용분포
- 포지션별 손익분포와 CVaR

다음 입력은 금지한다.

- in-sample fitted value
- terminal holdout을 본 뒤 고른 모형 출력
- 실패하거나 식별불가인 study의 점수
- 미래 종가·사후 스무딩 상태·수정된 과거 공표자료
- 출처와 availability timestamp가 없는 대체변수

## 3. 의사결정 목적함수

\[
a_t^*=\arg\max_{a\in\mathcal A}
\left[
\sum_k P(k\mid I_t)\Pi(a,k)
-C(a)
-\lambda Var(\Pi_a)
-\eta CVaR_\alpha(-\Pi_a)
\right]
\]

- `a`: 매수, 매도, 헤지, 축소, 관망
- `P(k|I_t)`: 독립 study의 외부 OOF 사건확률
- `C(a)`: 수수료, 세금, 환전, 슬리피지, 시장충격, 차입·헤지비용
- `CVaR`: 사전 고정 tail 수준의 조건부 손실

## 4. 판정보류

다음 중 하나면 `NoTrade/Abstain`을 우선한다.

- 필수 study가 `missing`, `not_identifiable`, `OOD`
- calibration 또는 risk–coverage Gate 실패
- 비용분포의 상위구간에서 기대효용이 음수
- 데이터 공표시각 또는 시장시간 정렬이 모호함
- stress scenario에서 위험예산 초과

판정보류 비율을 낮추는 것을 성능으로 보지 않는다. coverage와 조건부 오류를 함께 보고한다.

## 5. 기준선

- 현금 또는 무거래
- 단순 buy-and-hold
- 비용 포함 단순 모멘텀
- 비용 포함 단순 평균회귀
- 각 study의 최선이 아닌 사전 고정 단순 기준선

통합모형은 개별 분류 점수뿐 아니라 무거래 대비 순효용과 단순 거래전략 대비 증분효용을 모두 넘어야 한다.

## 6. 금지되는 통합

- 외부결과가 좋은 study에 사후 가중치 확대
- 성과가 나쁜 시기·종목·거래를 결과표에서 제외
- 여러 horizon 중 최고값만 보고
- 거래비용을 평균 한 값으로 고정해 tail을 제거
- 전체 데이터로 재학습한 출력의 OOF 위장
- 패닉·FOMO 점수를 실제 투자자의 감정확률로 재명명

## 7. 통합 채택조건

1. 입력 study가 각각 자신의 외부 Gate를 통과한다.
2. 통합규칙과 비용·위험계수는 terminal holdout 개봉 전에 동결된다.
3. 통합기가 단순 기준선 대비 사전 고정 최소효과를 보인다.
4. 종목·시기·변동성 국면별 손익과 calibration이 보고된다.
5. 독립 실행자가 제공된 artifact로 주요 결과를 재현한다.
6. 적용범위와 중단조건이 `DecisionRecord`에 명시된다.

하나라도 실패하면 기존 study의 연구결과는 보존하되 통합 거래공식은 채택하지 않는다.

