# <EB-ID> 근거 묶음

## 정체성

- 객체 ID: `<EB-ID>`
- StudyProtocol: `<SP-ID>`
- ExperimentRun: `<ER-IDS>`
- 근거수준: `<EXPLORATORY/CONFIRMATORY/REPRODUCED/REPLICATED>`

## 주장

> <이 근거가 평가하는 하나의 주장>

## 결과

| 결과 ID | 표본·국면 | 추정치 | 불확실성 | 기준선 차이 | 판정 |
| --- | --- | ---: | --- | ---: | --- |
| `<RESULT-ID>` | `<SCOPE>` | `<ESTIMATE>` | `<INTERVAL>` | `<DIFF>` | `<SUPPORT/REFUTE/INCONCLUSIVE>` |

## 지지 근거

- `<SUPPORTING-RESULT-AND-PATH>`

## 반박 근거

- `<CONTRADICTING-RESULT-AND-PATH>`

## 무효·제외 실행

- `<INVALID-RUN-ID-AND-REASON>`

## 민감도와 반증

- 시간순서·누수검사: `<RESULT>`
- 기준선 민감도: `<RESULT>`
- 종목·시대·국면 이질성: `<RESULT>`
- 비용·슬리피지 민감도: `<RESULT>`
- prior·threshold·모형 민감도: `<RESULT>`

## 재현성

- same-team repeatability: `<STATUS/EVIDENCE>`
- independent reproducibility: `<STATUS/EVIDENCE>`
- independent replicability: `<STATUS/EVIDENCE>`

## 한계

- `<LIMITATION>`

## 근거 판정

- 결론: `<SUPPORTED/REFUTED/INSUFFICIENT/NOT-IDENTIFIABLE>`
- 적용범위: `<SCOPE>`
- 다음 DecisionRecord: `<DR-ID>`

