# RP001-AUTO-PILOT-001

합성자료 전용 자율 연구 파일럿입니다. 라이브 수집자료, confirmation 자료, 외부 API를 사용하지 않습니다.

## 합격 기준

- Goal 단독 bootstrap 후 ledger 상태 복원
- validate 전 crash 뒤 동일 ActionContract 복원
- failed action 공개 후 동일 상태 재시도
- 두 failed cycle이 각각 `CycleTerminal`로 종료되고 다음 cycle 진행
- 등록 탐색범위 충족 뒤에만 bounded `ProgramVersionTerminal`
- ledger body 또는 sidecar 변조 탐지
- 중복 action commit 거부
- 주문·계좌·자산 접근 0건

실행 검증은 `research/rp-001/tests/test_autonomous_research_e2e.py`가 담당합니다. Hook과 scheduled task는 이 파일럿만으로 자동 활성화되지 않습니다.
