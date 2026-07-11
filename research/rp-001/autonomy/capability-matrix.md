# Autonomous Runtime Capability Matrix

| 책임 | 결정 주체 | 강제 방식 |
|---|---|---|
| Goal·ProgramSpec 결박 | Goal compiler + Controller | 원본 Goal SHA-256에서 program ID를 결정하고 frozen preset으로 canonical ProgramSpec 생성, 별도 sidecar |
| 현재 상태 복원 | Reducer | 전체 ledger replay; checkpoint 불신 |
| 다음 행동 선택 | Policy | 상태별 단일 NextAction |
| 가설·수식·진단 생성 | Codex | ActionContract 범위 안에서만 생성 |
| 결과 유효성 | Validator | action identity, transition replay, path, hash, secret scan |
| 개발 데이터 제공 | 사용자 | DataRelease manifest 등록 |
| confirmation 개봉 | Controller + 사용자 | freeze 후 물리적 release, 동결 FormulaVersion SHA-256 결박, 등록 즉시 single-use |
| 채택 경로 | Reducer | confirmation 통과 후 비용·위험 Gate를 거쳐야만 `ConfirmationPassed` 허용 |
| cycle 실패 판정 | 수치 artifact + Reducer | `CycleTerminal → NEXT_CYCLE` |
| 프로그램 종료 | Policy | 주관적 `no successor`가 아니라 동결 hard search budget의 실제 소진과 bounded terminal claim |
| 중단·재개 | Ledger | idempotent action ID와 append-only event |
| Hook | 선택적 보조장치 | 비활성 preset; 보안 경계로 간주하지 않음 |
| 독립 재현 | 외부 실행자 | 동일 모델 검토로 대체 불가 |

## 지원하지 않는 주장

- 열린 연구공간 전체가 소진됐다는 주장
- 동일 모델 자기검토를 독립 재현으로 승격
- 개발표본 성능을 confirmation 증거로 재분류
- 확인표본 반복 열람
- Hook만으로 모든 도구 경로가 차단된다는 주장
- 데이터 수집이나 주문 실행의 자율화
