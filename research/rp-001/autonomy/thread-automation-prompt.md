# Dormant Thread Automation Prompt

아래 prompt는 합성 파일럿과 사용자 검토가 끝난 뒤 기존 research thread를 깨우는 scheduled task에 사용합니다. 현재 scheduled task를 생성하거나 활성화하지 않습니다.

```text
Use $autonomous-research to resume the Goal-bound program at
research/rp-001/autonomy-runs/<programId>.

Replay status from the verified ledger, request next, and perform only the
returned ActionContract. Do not collect data, call market-data APIs, inspect an
unreleased confirmation set, access orders/accounts/assets, modify live
collection roots, or add planning while a runnable action exists.

Stop at AWAITING_DATA_RELEASE, an unresolved P0 blocker, the activation step
budget, a user pause, or ProgramVersionTerminal.
```

운용 시 `RP001_AUTONOMY_PROGRAM_ROOT`를 해당 program root로 결박하고, missed wake는 다음 wake의 ledger replay로 복구합니다.
