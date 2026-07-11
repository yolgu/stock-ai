# EB-001 RB-001 무결성 관찰 감사 근거 묶음

## 정체성

- 객체 ID: `EB-001`
- 기준선: `RB-001`
- 근거 수준: `exploratory`
- 관찰 원장: `integrity-observations.json`
- 후속 결정: `DR-001`

## 평가 주장

RB-001에서 서로 다른 세 무결성 상태가 순서대로 관찰되었다. 이 근거 묶음은 각 상태를 append-only로 보존하고, 현재 snapshot의 자체 일관성과 원래 동결 생성 계보 및 독립 재현을 구별한다.

## 관찰 1: 최초 감사

- phase: `initial_audit`
- run manifest SHA-256: `09e2ddf1e9acb3dbf54336ea5265a737ebba4a702dce61cdd194f4827a260eda`
- manifest payload SHA-256: `6874c351cd5efe3f061c05af134ae569c0d0227e225340dd0f85d52b27e59356`
- bound runner SHA-256: `1e6d5d4053f61fdb4d3af17848658c8a0942880774c8c7f33d7e5f6f0bd12d2a`
- bound runner 크기: `42115` bytes
- 검증 상태: `failed_input_hash_mismatch`
- 결과 8개 파일의 관찰 mtime: `2026-07-10T07:56:52+09:00`
- runner 관찰 mtime: `2026-07-10T08:02:27+09:00`

이 상태는 `docs/codex/plans/2026-07-10-rp-001-sg0-sg2-foundation.md`에 기록된 session-observation evidence다. 역사적 byte는 더 이상 확보되어 있지 않아 독립적으로 재계산할 수 없다.

## 관찰 2: 첫 재결박

- phase: `first_rebind_observed`
- run manifest SHA-256: `90e6e3ac59bf408b609fc5a5422a763a090e47c5578f9b0419a957814b93415f`
- manifest payload SHA-256: `3b4957020bdea2f060eab7e8f2cd784c5a0acc98ef6d57cd83fe3916a5bb0ae2`
- bound runner SHA-256: `b625d724d8363b2d5d74a25b698e7911787d01dfcb5b7b5c41c392b3a748851b`
- bound runner 크기: `50585` bytes
- 검증 상태: `self_consistent_after_rebind`
- manifest 관찰 mtime: `2026-07-10T08:09:33+09:00`
- 당시 보고서와 검증 로그의 관찰 mtime: `2026-07-10T08:09:56+09:00`

이 상태도 같은 계획 문서에 기록된 session-observation evidence다. 역사적 byte는 더 이상 확보되어 있지 않아 독립적으로 재계산할 수 없다.

## 관찰 3: 이후 결정적 재실행으로 보고된 현재 snapshot

- phase: `later_deterministic_rerun_observed`
- run manifest SHA-256: `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e`
- run manifest 크기: `5064` bytes
- manifest payload SHA-256: `b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f`
- bound runner SHA-256: `f906fd61b9b55e2e264adae032517151f9ee7ed24b8804ab878e102944736708`
- bound runner 크기: `52600` bytes
- 검증 상태: `current_snapshot_self_consistent`
- runner 관찰 mtime: `2026-07-10T08:12:21+09:00`
- manifest 및 bound output 8개 파일의 관찰 mtime: `2026-07-10T08:16:31+09:00`
- 최종 보고서 `docs/codex/research/2026-07-10-mania-panic-fomo-formula-final-report.md` 관찰 mtime: `2026-07-10T08:16:58+09:00`
- 검증 로그 관찰 mtime: `2026-07-10T08:17:10+09:00`

현재 파일을 변경하거나 RB-001 실행기를 실행하지 않고 manifest canonical bytes와 payload SHA-256을 다시 계산했다. manifest의 `code:run-validation` binding은 현재 runner의 SHA-256 및 크기와 일치했다. 현재 manifest 입력 24/24의 repository path·크기·SHA-256을 읽기 전용으로 재계산해 각 binding과 일치함을 확인했다. manifest에 결박된 output 8개 모두의 경로·크기·SHA-256을 읽기 전용으로 재계산해 각 binding과 일치함을 확인했다. mtime은 관찰 사실로만 기록하며 검증 통과 조건으로 사용하지 않는다.

`docs/codex/research/2026-07-10-verification-log.md`는 서로 다른 결과 디렉터리의 두 실행이 같은 `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e` manifest를 생성했다고 보고한다. 보고된 두 결정적 실행은 이 감사가 독립적으로 목격하거나 재실행한 사실이 아니다.

## 해석 한계

- `generationLineageVerified=false`
- 세 phase transition의 실행 주체와 명령은 알려져 있지 않다.
- 현재 snapshot의 self-consistency는 원래 동결 생성 계보 또는 G9 재현을 입증하지 않는다.
- 현재 상태는 원래 frozen provenance를 복구하거나 과거 phase를 덮어쓰지 않는다.
- 보고된 두 실행은 동일 실행자 또는 동일 팀이 수행했는지 알 수 없으므로 same-team repeatability로도 분류할 수 없다.
- 이 감사가 확인한 independent reproducibility 또는 replicability 증거도 아니다.
- 등록된 민감값 패턴 정책으로 이 aggregate의 artifact를 검사한 결과 match는 0건이다.
- 이 결과는 등록 패턴 범위에 한정되며 모든 가능한 민감값 부재를 증명하지 않는다.

## 근거 판정

- 결론: 현재 snapshot의 내부 결박은 확인되었으나 원래 동결 생성 계보와 독립 재현 근거는 불충분하다.
- 적용범위: failure reproduction, prohibited-condition 설계, seen-development-data 경계 식별에 한정한다.
- 운영 또는 채택 근거: 사용 불가
- 다음 결정기록: `DR-001`
