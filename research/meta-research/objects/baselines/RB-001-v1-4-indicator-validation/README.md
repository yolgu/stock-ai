# RB-001: v1.4 지표 검증 기준선

## 지위

- 객체 유형: `ResearchBaseline`
- 수명주기: `frozen`
- 원 연구 버전: `1.4.0`
- 핵심 결론: 현재 증거에서 운영에 채택할 수 있는 공식은 식별되지 않았다.

## 원본

- [동결 사전등록](../../../../indicator-validation/preregistration.json)
- [최종 연구 보고서](../../../../../docs/codex/research/2026-07-10-mania-panic-fomo-formula-final-report.md)
- [수학 감사](../../../../../docs/codex/research/2026-07-10-formula-mathematical-audit.md)

## 허용되는 사용

- 새 후보가 넘어야 하는 기준선
- 기존 수식의 반례와 데이터 결함 목록
- 이미 관측한 개발·복제·holdout 구간의 식별
- 후속 연구의 금지조건과 실패사례

## 금지되는 사용

- 새 모형 결과가 좋아지도록 v1.4 가중치·라벨·결론을 수정하는 행위
- 이미 확인한 구간을 새 모형의 봉인된 확인표본으로 부르는 행위
- `adoption_not_identifiable`을 모든 가능한 수식의 보편적 실패로 확대하는 행위

후속 정정이 필요하면 이 객체를 수정하지 않고 새 `ResearchBaseline` 또는 `DecisionRecord`로 연결한다.
