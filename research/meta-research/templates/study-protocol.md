# <SP-ID> 연구 프로토콜

## 정체성

- 객체 ID: `<SP-ID>`
- 연구질문: `<RQ-ID>`
- 상위 프로그램: `<RP-ID>`
- 프로토콜 버전: `<MAJOR.MINOR.PATCH>`
- 동결시각: `<ISO-8601>`
- 동결 hash: `<SHA-256>`

## 가설과 Estimand

- 귀무가설: `<H0>`
- 대립가설: `<H1>`
- 주요 estimand: `<PRIMARY-ESTIMAND>`
- 보조 estimand: `<SECONDARY-ESTIMANDS-OR-NONE>`

## 자료

- DatasetContract: `<DC-ID>`
- 모집단·종목: `<UNIVERSE>`
- 표본기간: `<START/END>`
- availability cutoff: `<AS-OF-CUTOFF>`
- 탐색·학습·검증·terminal holdout 역할: `<SPLIT-CONTRACT>`

## 특징과 후보

- 허용 특징: `<FEATURE-IDS>`
- 금지 특징: `<FORBIDDEN-INPUTS>`
- 단순 기준선: `<BASELINE-IDS>`
- 후보 모형: `<MODEL-CANDIDATE-IDS>`
- 파라미터 선택범위: `<LOCKED-SEARCH-SPACE>`

## 분석

- 시계열 분할: `<PURGE/EMBARGO/WALK-FORWARD>`
- 주 평가척도: `<PRIMARY-METRIC>`
- 보조 평가척도: `<SECONDARY-METRICS>`
- 불확실성: `<BOOTSTRAP/POSTERIOR/INTERVAL>`
- 다중가설 보정: `<CORRECTION-FAMILY>`
- 결측·OOD·abstain: `<POLICY>`

## 반증과 중단

- negative control: `<NEGATIVE-CONTROLS>`
- leakage test: `<LEAKAGE-TESTS>`
- 최소효과: `<MINIMUM-EFFECT>`
- 무효 실행조건: `<INVALID-RUN-CONDITIONS>`
- 연구 중단조건: `<STOPPING-RULES>`

## 판정

- 채택 Gate: `<ADOPTION-GATES>`
- 조건부 채택범위: `<CONDITIONAL-SCOPE>`
- 외부검증 요구: `<EXTERNAL-VALIDATION>`
- 결과와 무관하게 공개할 산출물: `<DISCLOSURE-CONTRACT>`

## Amendment 규칙

동결 뒤 변경은 원 프로토콜을 수정하지 않는다. 변경 이유, 이미 열람한 결과, 폐기되는 실행, 남은 봉인표본을 기록한 새 버전을 만든다.

