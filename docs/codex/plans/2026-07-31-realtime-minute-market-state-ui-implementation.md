# 실시간 분봉 시장상태 신호 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development
> (recommended) or executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** 완료된 5분봉마다 연구로 고정된 FOMO·패닉·차익실현·회복·상승세
신호를 계산하고, 카드와 상세 화면에 재현 가능한 수치로 표시한다.

**Architecture:** Neutralino extension이 분봉 수집·정규화·수식 계산·이력
저장을 소유하고 React renderer는 검증된 summary·trace·history 계약만
표시한다. 실시간 가격 세대와 공식 신호 입력 세대를 분리하며 수학 판정은
renderer에서 다시 계산하지 않는다.

**Tech Stack:** Neutralino, Node.js CommonJS, React, TypeScript, Vitest

---

### Task 1: 분봉 무결성

**Files:**
- Modify: `extensions/app/market-data.cjs`
- Modify: `extensions/app/storage.cjs`
- Test: `extensions/app/market-data.test.ts`
- Test: `extensions/app/storage.test.ts`

- [ ] 반복 polling에도 1분봉 fetch 시각이 보존되고 TTL 뒤 재수집되는 실패
      테스트를 작성하고 RED를 확인한다.
- [ ] timestamp 정렬·중복 제거·완료봉 상한과 정확한 5×1분봉 집계 실패
      테스트를 작성하고 RED를 확인한다.
- [ ] 겹치는 저장이 update를 잃지 않는 실패 테스트를 작성하고 RED를
      확인한다.
- [ ] candle provenance와 직렬 저장을 최소 구현하고 관련 테스트를 GREEN으로
      만든다.

### Task 2: 고정 수식 도메인

**Files:**
- Create: `extensions/app/market-state/formula-release.json`
- Create: `extensions/app/market-state/market-state-formula.cjs`
- Create: `extensions/app/market-state/market-state-formula.test.ts`
- Create: `extensions/app/market-state/completed-five-minute-bar.cjs`
- Create: `extensions/app/market-state/completed-five-minute-bar.test.ts`

- [ ] 연구 artifact에서 현재 다섯 수식만 추출한 content-addressed payload를
      만들고 predecessor 상승세가 배제되는 실패 테스트를 작성한다.
- [ ] 표준화 기여합, 동적 20세션 임계값, 0~100 경험 백분위, 위험상태와
      게이트의 실패 테스트를 작성하고 RED를 확인한다.
- [ ] 현재 판정·세션 내 최근 감지·후속 6봉 억제/7번째 허용의 실패 테스트를
      작성하고 RED를 확인한다.
- [ ] 최소 domain 구현으로 Python golden fixture와 동일한 결과를 만든다.

### Task 3: 수집·백필과 런타임 계약

**Files:**
- Modify: `contracts/app-runtime-contract.json`
- Modify: `src/shared/contracts/app-runtime-contract.ts`
- Create: `extensions/app/market-state/market-state-service.cjs`
- Create: `extensions/app/market-state/market-state-repository.cjs`
- Modify: `extensions/app/main.cjs`
- Test: `extensions/app/app-message-handler.test.ts`

- [ ] 다섯 summary, 선택 trace, 당일 history, background backfill progress
      계약의 실패 테스트를 작성하고 RED를 확인한다.
- [ ] payload runtime validator가 잘못된 신호 수·해시·상태를 거부하는 실패
      테스트를 작성한다.
- [ ] 앱 시작 시 coverage를 읽고 API pagination으로 gap만 채우는 backend
      job과 체크포인트를 구현한다.
- [ ] 준비된 신호를 개별 게시하고 5초 IPC에서 대량 백필을 분리한다.

### Task 4: 카드와 상세 UI

**Files:**
- Modify: `src/presentation/AppShell.tsx`
- Modify: `src/presentation/watchlistViewModels.ts`
- Modify: `src/styles.css`
- Test: `src/presentation/AppShell.test.tsx`

- [ ] 카드에 다섯 신호의 백분위와 판정이 모두 보이는 실패 테스트를 작성한다.
- [ ] 상세 trace의 점수·임계값·게이트·기여표·최근 60분/당일 이력 실패
      테스트를 작성한다.
- [ ] 최신 판정과 마지막 감지 시각을 분리하고 신규 감지에만 카드 강조와
      `aria-live` 앱 알림을 내는 실패 테스트를 작성한다.
- [ ] 920px 창과 키보드 접근성 조건을 만족하도록 최소 UI를 구현한다.
- [ ] 기존 `profitTakingPressure` 전용 표시와 하위 의존을 새 연구 결과로
      교체한다.

### Task 5: 통합 완료

**Files:**
- Modify: 관련 테스트 fixture와 문서

- [ ] `pnpm test`를 실행해 전체 GREEN을 확인한다.
- [ ] `pnpm run typecheck`를 실행해 타입 오류가 없음을 확인한다.
- [ ] 프로젝트의 Neutralino build 명령을 실행해 앱 bundle을 검증한다.
- [ ] formula payload·source generation·stale 상태·쿨다운 경계 회귀를
      재실행한다.
- [ ] 변경을 논리 단위로 커밋하고 `dev` 원격에 푸시한다.
