# 저장소 문제점 수정 계획

상태: 2026-07-25 작업공간의 역사적 진단 스냅샷. 2026-07-31에 잘못 유입된
`AGENTS.md`와 불완전한 스킬 삭제를 복원했으므로 이 문서를 현재 실행계획이나
현행 저장소 상태의 SSOT로 사용하지 않는다.

## 1. 목적

현재 작업 공간에서 확인된 저장소 운영 설정, 자동화 구성, 테스트 경고, 생성물 관리 문제를 안전하게 정리한다.

애플리케이션 기능 코드는 현재 타입 검사와 전체 테스트를 통과하고 있으므로, 기능 코드를 성급하게 변경하지 않고 저장소 지침과 자동화 구성부터 정상화한다.

## 2. 현재 확인 상태

- `pnpm run typecheck`: 통과
- `pnpm test`: 24개 테스트 파일, 96개 테스트 통과
- React 테스트에서 `act(...)` 경고 2회 발생
- pnpm 명령 실행 시 SDKMAN 셸 호환성 경고 발생
- 작업 트리에 Codex 설정, 스킬, 문서, 실행 산출물 관련 변경이 다수 존재

## 3. 확인된 문제점

### P0 — `AGENTS.md`가 프로젝트와 맞지 않음

현재 변경본은 제목이 `Meeting Minutes Project Guidelines`로 바뀌었으며, 다음과 같은 프로젝트 비관련 규칙이 포함되어 있다.

- Java 코딩 규칙
- `controller -> service -> repository` 구조
- 기존 Neutralino, React, TypeScript 전용 경계 제거
- 렌더러와 Neutralino 확장 간 보안 및 계약 규칙 제거
- 프로젝트 실행 및 검증 지침 제거

이 상태로 자동 구현을 진행하면 잘못된 아키텍처나 검증 기준을 적용할 위험이 있다.

### P0 — Codex 워크플로 파일 간 불일치

다음 스킬들이 삭제되어 있다.

- `dispatching-parallel-agents`
- `requesting-code-review`
- `subagent-driven-development`
- `using-superpowers`

동시에 `implement-orchestrator.toml`과 일부 스킬은 서브에이전트를 사용하지 않는 방향으로 수정되어 있다.

이 변경이 의도적이라도 삭제된 스킬을 참조하는 문서나 에이전트가 남아 있으면 워크플로가 중간에 끊길 수 있다.

### P1 — 생성물과 실제 소스가 섞여 있음

현재 미추적 파일에는 다음 항목이 함께 포함되어 있다.

- `.ai-bridge/*`
- `research/rp-001/autonomy-runs/*`
- `helloworld.md`
- 새 설계 문서

런타임 로그, 상태 파일, 임시 패치와 영구 보관해야 할 연구 산출물을 분리할 필요가 있다.

### P1 — React 테스트 경고

모든 테스트는 통과하지만 `src/presentation/AppShell.test.tsx`에서 비동기 상태 변경이 `act(...)`로 처리되지 않았다는 경고가 발생한다.

잠재 영향:

- 테스트가 최종 사용자 상태를 완전히 기다리지 않을 가능성
- 향후 React 또는 Testing Library 업데이트에서 실패로 전환될 가능성
- 간헐적인 테스트 실패 가능성

### P2 — 로컬 셸 초기화 경고

모든 pnpm 명령에서 다음 SDKMAN 경고가 발생한다.

```text
sdkman-path-helpers.sh: ${candidate_name^^}: bad substitution
```

프로젝트 코드 오류보다는 현재 실행 셸과 SDKMAN 스크립트의 호환 문제로 보인다. 테스트 결과에는 영향을 주지 않았지만 명령 출력의 신뢰성을 낮춘다.

## 4. 수정 계획

### 1단계 — 변경 의도 분류 및 복구 기준 확정

대상:

```text
AGENTS.md
.codex/agents/implement-orchestrator.toml
.codex/skills/**
```

수행 내용:

1. 각 변경이 의도적인 단일 세션 실행 방식 전환인지 확인한다.
2. 프로젝트와 무관한 `AGENTS.md` 변경을 별도로 분리한다.
3. 삭제된 스킬을 참조하는 파일을 전체 검색한다.
4. 삭제된 스킬의 기능이 다른 스킬로 대체되었는지 확인한다.
5. 전체 파일을 일괄 복구하지 않고 의도된 개선과 오염된 변경을 구분한다.

완료 기준:

- 삭제된 스킬에 대한 깨진 참조가 없다.
- 에이전트와 스킬의 실행 정책이 하나의 방식으로 통일된다.
- 프로젝트 지침과 도구 지침이 충돌하지 않는다.

### 2단계 — `AGENTS.md` 프로젝트 지침 복구

기존 Neutralino 및 React 지침을 기준으로 복구하고, 현재 추가된 일반 코드 품질 원칙 중 유효한 부분만 병합한다.

반드시 복구할 내용:

- Neutralino + React + TypeScript 데스크톱 앱이라는 프로젝트 설명
- `src/` 렌더러 경계
- `extensions/` Node 확장 경계
- Domain, Application, Infrastructure, Presentation 의존성 방향
- Neutralino API 객체가 도메인으로 누출되지 않아야 한다는 규칙
- 비밀정보가 렌더러에 저장되면 안 된다는 규칙
- `pnpm dev:neutralino`와 `pnpm dev:vite`의 차이
- 테스트, 타입 검사, 확장 문법 검사 명령

제거할 내용:

- `Meeting Minutes Project` 제목
- Java 규칙
- 이 프로젝트에 없는 Controller 및 Repository 중심 설명
- HTTP 및 ORM 중심의 무관한 예시

완료 기준:

- 문서만 읽어도 현재 디렉터리 구조와 실행 방식이 정확히 설명된다.
- 실제 `package.json`, `neutralino.config.json`, `src/`, `extensions/`와 내용이 일치한다.

### 3단계 — Codex 스킬 및 에이전트 정합성 복구

두 가지 실행 방식 중 하나로 완전히 통일한다.

#### 권장안: 단일 세션 실행 방식 유지

현재 환경이 서브에이전트를 사용하지 않는 방향이라면 다음과 같이 정리한다.

- 의도적으로 삭제한 스킬은 삭제 상태를 유지한다.
- 삭제된 스킬에 대한 남은 참조를 모두 제거한다.
- `implement-orchestrator`가 인라인 실행과 검토 체크포인트를 담당하도록 명확히 한다.
- `executing-plans`, `writing-plans`, `verification-before-completion`의 흐름을 일치시킨다.
- 삭제된 `requesting-code-review` 기능을 어떤 검토 절차가 대신하는지 명시한다.

대안은 삭제된 스킬을 모두 복구하고 서브에이전트 방식으로 되돌리는 것이다. 두 방식을 혼합하지 않는다.

완료 기준:

- 스킬 이름 참조 검사 결과 누락 파일이 없다.
- YAML, TOML, Markdown frontmatter 파싱이 성공한다.
- 계획, 구현, 검토, 검증 흐름이 중간에 끊기지 않는다.

### 4단계 — 작업 산출물과 저장소 파일 분리

파일을 다음 세 범주로 나눈다.

| 범주 | 처리 방향 |
|---|---|
| 임시 실행 상태 | `.gitignore` 추가 |
| 재현에 필요한 연구 증거 | 저장소에 보존 |
| 단순 검증 파일 | 삭제 |

구체적인 후보:

- `helloworld.md`: 쓰기 검증 목적이 끝났으므로 삭제
- `.ai-bridge/execution-log.jsonl`, 상태 파일, 패치 파일: 기본적으로 ignore 후보
- `.ai-bridge/README.md`: 도구 사용법 문서라면 추적 가능
- `research/rp-001/autonomy-runs/*`: 재현 가능한 연구 기록인지 검토 후 추적 여부 결정
- 설계 문서: 실제 프로젝트 문서라면 추적

주의사항:

`.ai-bridge` 전체를 무조건 무시하지 않고 README, 계약 파일, 런타임 로그를 구분한다.

### 5단계 — React `act(...)` 경고 수정

대상:

```text
src/presentation/AppShell.test.tsx
```

진행 순서:

1. 경고가 발생하는 테스트의 비동기 상태 변경 출처를 확인한다.
2. 렌더 직후 effect인지 mock client 응답인지 추적한다.
3. 경고를 숨기지 않고 사용자에게 보이는 최종 상태를 기다리도록 테스트를 변경한다.
4. `findBy...`, `waitFor`, 명시적 `act` 중 가장 자연스러운 방법을 적용한다.
5. 대상 테스트만 반복 실행하여 경고가 사라지는지 확인한다.
6. 전체 테스트를 실행한다.

완료 기준:

```text
24 test files passed
96 tests passed
act(...) warning 0개
```

### 6단계 — 셸 환경 경고 분리 수정

프로젝트 파일이 아니라 로컬 실행 환경 문제로 분리한다.

확인할 내용:

- CodexPro가 사용하는 실제 셸
- macOS 기본 Bash 3.2에서 `${value^^}`가 실행되는지
- SDKMAN 초기화가 비대화형 셸에서도 필요한지
- `.bashrc`, `.bash_profile`, `.zshrc` 중 잘못 로드되는 파일이 있는지

권장 수정:

- Bash 4 전용 구문을 사용하는 SDKMAN 초기화를 호환 셸에서만 로드한다.
- 또는 명령 실행 셸을 적절한 Bash 또는 Zsh로 통일한다.
- 프로젝트 스크립트에서 SDKMAN 오류를 억지로 처리하지 않는다.

완료 기준:

- pnpm 명령 시작 시 SDKMAN 경고가 나타나지 않는다.
- Node와 pnpm 버전은 기존과 동일하다.

### 7단계 — 최종 검증

수정 후 다음 순서로 검증한다.

```bash
pnpm run typecheck
pnpm test
pnpm run extension:check
pnpm run build
```

추가 검증:

- 삭제된 Codex 스킬 이름에 대한 전체 참조 검색
- TOML, YAML, Markdown frontmatter 검사
- `git status`에서 의도한 파일만 남았는지 확인
- `pnpm dev:neutralino` 데스크톱 스모크 테스트
- 렌더러와 Node 확장 간 기본 요청 및 응답 확인

## 5. 권장 작업 순서

```text
1. AGENTS.md 복구
2. Codex 스킬 및 에이전트 정합성 정리
3. 생성물 및 .gitignore 정책 정리
4. AppShell 테스트 경고 수정
5. SDKMAN 환경 경고 수정
6. 전체 검증
```

## 6. 핵심 원칙

현재 통과 중인 애플리케이션 코드는 불필요하게 변경하지 않는다.

먼저 잘못된 저장소 지침과 자동화 구성을 정상화하고, 이후 테스트 경고와 로컬 환경 경고를 독립적으로 수정한다.
