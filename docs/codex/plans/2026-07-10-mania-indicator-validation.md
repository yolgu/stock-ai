# Mania Indicator Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toss 실제 일봉으로 FOMO·패닉셀·차익실현 수식의 인과적 예측력, 보상해킹, 국면 탐지 성능을 120거래일 단위로 검증하고 최종 수식을 결정한다.

**Architecture:** 앱 런타임과 연구 코드를 분리한다. Node 수집기는 기존 OAuth 저장 경계를 재사용해 수정주가 일봉을 안전하게 페이지네이션하고, Python 분석기는 원시 JSON을 읽어 인과적 특성·독립 라벨·walk-forward 확률분포를 만든다. 앱의 현재 미커밋 변경은 수정하지 않는다.

**Tech Stack:** Node.js CommonJS, Node test runner, Toss Securities Open API, Python 3, NumPy, pandas, unittest, Markdown/JSON

---

### Task 1: Toss 일봉 페이지네이션 경계

**Files:**
- Create: `research/indicator-validation/toss-daily-client.test.cjs`
- Create: `research/indicator-validation/toss-daily-client.cjs`

- [ ] **Step 1: 실패 테스트 작성**

`count=200`, 두 번째 요청의 `before` 전달, 중복 timestamp 제거, `nextBefore=null` 종료, 자격증명·토큰 비노출을 검증한다.

- [ ] **Step 2: RED 확인**

Run: `node --test research/indicator-validation/toss-daily-client.test.cjs`

Expected: 모듈 부재로 FAIL.

- [ ] **Step 3: 최소 구현**

`TossDailyCandleArchiveClient.fetchRange()`가 공식 페이지네이션 계약만 책임지게 한다.

- [ ] **Step 4: GREEN 확인**

Run: `node --test research/indicator-validation/toss-daily-client.test.cjs`

Expected: 모든 페이지네이션·중복·종료 테스트 PASS.

### Task 2: 실제 원시 데이터 수집

**Files:**
- Create: `research/indicator-validation/fetch-toss-daily.cjs`
- Create: `research/indicator-validation/data/raw/*.json`
- Create: `research/indicator-validation/data/manifest.json`

- [ ] **Step 1: 수집 명령의 dry-run 테스트 추가**

심볼, 시작일, 필요 봉 수, 출력 경로만 출력하고 비밀값은 출력하지 않는지 확인한다.

- [ ] **Step 2: RED 확인 후 수집기 구현**

기존 `StoredTossCredentialRepository`와 `TossOAuthClient`를 사용하고 원시 키·토큰은 직렬화하지 않는다.

- [ ] **Step 3: 실제 수집**

TSLA, NVDA, MU, 000660의 필요한 여유기간을 수집하고 미완성 일봉을 제외한다.

- [ ] **Step 4: 계보 검증**

manifest에 SHA-256, 행 수, 최초·최종 timestamp, 중복·제외 수를 기록한다. 비밀 문자열 패턴이 없는지 검사한다.

### Task 3: 인과 특성과 독립 라벨

**Files:**
- Create: `research/indicator-validation/test_validation.py`
- Create: `research/indicator-validation/validation.py`

- [ ] **Step 1: 실패 테스트 작성**

미래값 변경이 시점 `t` 특성을 바꾸지 않는지, percentile이 expanding past-only인지, 라벨만 미래 구간을 쓰는지, 점수 범위와 결측 상태가 맞는지 검증한다.

- [ ] **Step 2: RED 확인**

Run: `python3 -m unittest research/indicator-validation/test_validation.py -v`

Expected: 모듈 부재로 FAIL.

- [ ] **Step 3: FOMO·패닉·차익실현 일봉 프록시 구현**

문서 가중치, 가용항 동일가중, 단순 기준선을 각각 독립 후보로 유지한다. flow·orderbook 결측은 0점으로 대체하지 않는다.

- [ ] **Step 4: 독립 라벨과 상태 국면 구현**

설계 문서의 horizon 라벨과 전조·시작·중간·정점/저점·확인·끝 사건 분할을 구현한다.

- [ ] **Step 5: GREEN 확인**

모든 인과성·범위·라벨 테스트가 PASS해야 한다.

### Task 4: 120거래일 walk-forward와 확률분포

**Files:**
- Modify: `research/indicator-validation/test_validation.py`
- Modify: `research/indicator-validation/validation.py`
- Create: `research/indicator-validation/run_validation.py`

- [ ] **Step 1: 실패 테스트 작성**

purge/embargo 경계, Jeffreys beta 사후분포, moving-block bootstrap, calibration, MCC·AUC·PR-AUC, BH 보정을 고정 예제로 검증한다.

- [ ] **Step 2: RED 확인 후 최소 구현**

무작위 과정은 seed를 고정하고 후보군 전체를 출력한다.

- [ ] **Step 3: 네 종목 분석 실행**

360일 광풍 두 구간과 MU·SK hynix 120일/최근 4개월 구간을 실행한다.

- [ ] **Step 4: 산출물 검증**

`metrics.json`, `events.json`, `predictions.json`이 입력 manifest hash와 분석 버전을 포함하는지 확인한다.

### Task 5: 수식 감사와 최종 보고서

**Files:**
- Create: `docs/codex/research/2026-07-10-mania-panic-fomo-formula-report.md`

- [ ] **Step 1: 문서식↔구현식 매핑**

줄 번호, 입력 가용성, 범위·단위 오류, 결측 처리, 중복 집계, 보상해킹 위험을 수식별로 기록한다.

- [ ] **Step 2: 실데이터 결과 통합**

블록별 성공·실패 확률분포, 신용구간, 기준선 비교, 패닉·차익실현·FOMO 국면별 선행 여부를 기록한다.

- [ ] **Step 3: 최종 결정**

각 식을 유지·수정·폐기·식별불가 중 하나로 판정하고, 네 개 상태전이 hazard와 권장 가중치·확정 조건을 제시한다.

- [ ] **Step 4: 재현 검증**

Run: `node --test research/indicator-validation/toss-daily-client.test.cjs`

Run: `python3 -m unittest research/indicator-validation/test_validation.py -v`

Run: `python3 research/indicator-validation/run_validation.py --verify`

Expected: 모든 테스트 PASS, 산출물 hash 일치, 비밀정보 검사 PASS.

## Git 처리

기존 작업트리에 사용자의 미커밋 변경이 있으므로 이 계획은 자동 commit, stage, branch 전환을 수행하지 않는다. 연구 파일만 추가하고 최종 diff를 분리해 보고한다.

