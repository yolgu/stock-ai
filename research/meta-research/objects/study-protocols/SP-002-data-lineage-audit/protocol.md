# SP-002 필수자료 계보·가용시점·권리 감사 프로토콜

## 정체성과 동결

- 객체 ID: `SP-002`
- study slot: `ST-DAT-001`
- 연구질문: `RQ-002`
- 자료계약: `DC-002`
- 상위 프로그램: `RP-001`
- 프로토콜 버전: `1.0.1`
- 동결일: `2026-07-10`
- 본문 hash 위치: `protocol.sha256`

프로토콜 본문의 SHA-256은 같은 디렉터리의 `protocol.sha256`에만 기록한다. 본문에는 현재 hash 값을 복제하지 않는다. `source-matrix.json`과 `ST-DAT-001.json`은 동결 뒤 그 exact protocol hash에 결박한다.

## Pre-run amendment 001

- 이전 protocol SHA-256: `54909d419db11ce6394f7be467cd54732b9d5db94ad5b36d0805d663f8e7ee34`
- 발견 경로: independent spec review
- 적용 시점: 어떤 ExperimentRun이나 EvidenceBundle도 생성되기 전

이 amendment는 다음 계약 오류만 교정한다.

1. daily/minute `componentStatuses`에서 derived output을 제거하고 raw input component만 availability로 기록한다.
2. 동결 전 local credential file presence/path 관측, file contents·file-origin values 미접근을 분리한 credential provenance로 교정한다.
3. evidence에 `authorityRefs`를 추가하고 외부 문서 사실과 내부 research inference·operational control의 권위를 분리한다.
4. Markdown semantic validator가 binding·policy·행·evidence와 명시적 계약 모순을 구조적으로 거부하도록 고정한다.

적용 시점의 trial ledger는 `runs=[]`다. 라이브 API, credential file contents, credential values, token, 시장 데이터 또는 연구결과에는 접근하지 않았고, 이 amendment로 결과를 선택하거나 evidence를 생성하지 않았다.

## 사전 열람과 연구 경계

`official-source-register.json`의 네 공식 문서는 모두 `design_seen_before_freeze`다. 설계 전에 본 자료이므로 독립 confirmatory 근거가 아니다. 문서에서 추출한 endpoint·schema·권리 한계는 사전 공개된 설계 근거일 뿐, API 응답이나 시장 현상의 확인 결과가 아니다.

각 공식 URL과 FAQ claim asset은 인증 없이 짧은 간격으로 두 번 GET해 pair hash 일치를 확인했다. full-second timezone `retrievedAt`, 현재 `httpResponseSha256`, 이전 관측 hash, `revisionObservation`을 등록한다. OpenAPI와 overview는 같은 canonical API version 1.2.2 설계 중 byte drift가 관측됐다. `latest`와 `info.version`은 immutable revision identifier가 아니며 exact response hash와 retrievedAt이 필수다. 이 documentation revision risk는 비보상적이다.

홈페이지 initial HTTP hash는 FAQ text나 rendered DOM을 결박하지 않는다. current page가 참조하는 official Next.js asset을 별도로 두 번 확인하고 asset URL·hash를 결박했다. 권리 문구는 exact text에 `utf8_original_bytes_plus_single_lf_no_unicode_normalization`을 적용한 extracted text hash로 별도 결박한다.

repository boundary audit는 코드와 기존 등록 seen-data metadata만 읽었다. 새로운 unseen data를 읽지 않았다. 라이브 API를 호출하지 않았다. local credential file의 존재 또는 경로는 동결 전에 상위 세션에서 관측됐다. exact path와 credential 값은 artifact에 기록하지 않는다. file contents와 file-origin credential values는 읽지 않았다. 시장 데이터나 연구결과도 열지 않았다.

대화에서 plaintext credential이 동결 전에 공개됐다는 disclosure risk만 기록한다. 그 값을 반복·복사·사용하지 않았다. 공개된 credential은 `compromised`이며 반드시 `rotate`해야 한다. 값 자체는 artifact, 로그, command 또는 source matrix에 남기지 않는다.

## 질문과 estimand

질문은 다음과 같다.

> GOAL-RP-001이 요구하는 각 필수 입력군에 대해, 시점 t 가용성·계보·단위·수정·권리 계약을 모두 만족하는 자료가 현재 존재하며 어떤 연구에 사용할 수 있는가?

- availability estimand: 8개 입력군과 구성요소 각각의 `usable`, `limited`, `data_unavailable`
- identifiability estimand: 입력군에서 허용하려는 주장 각각의 `identifiable`, `not_identifiable`
- 축 분리: `componentStatuses`에는 availability만, `identifiabilityImplications`에는 claim identifiability만 기록한다.
- horizon: 적용하지 않음. 접근일 현재의 contemporaneous data-contract audit다.
- 자료 이용: 공식 문서와 기존 등록 metadata만 사용한다.
- 통계적 효과·예측성능·경제적 성과: 추정하지 않는다.

## 포함·제외 규칙

### 포함

1. `official-source-register.json`에 고정된 정확히 네 공식 토스증권 문서만 설계 코퍼스로 포함한다.
2. 접근일, full-second timezone retrievedAt, 문서 버전, 현재·이전 raw HTTP response hash, revision 관측, 추출 방식, 적용 주장, 문서화되지 않은 주장을 모두 기록한다.
3. Goal의 8개 입력군과 공통 시간·단위·revision·계보·권리 필드를 모두 판정한다.
4. 저장소 코드는 API 경계와 제공 가능성의 정적 근거로만 읽고, 실행하거나 인증하지 않는다.

### 제외

1. credential file contents·file-origin values와 환경의 credential 값을 읽지 않는다.
2. 라이브 또는 시험 API 요청을 하지 않는다.
3. 기존 등록 seen-data metadata가 가리키는 시장자료 파일을 열지 않는다.
4. 문서에 없는 시간대·candle membership·단위·revision·보존권리를 추론하지 않는다.
5. 예시 응답을 보장된 계약으로 승격하지 않는다.

## Availability와 identifiability 판정 규칙

- availability `usable`: provider/source, event·publication timestamp와 collector-generated `clientReceivedAt`, 거래소·시간대·calendar/candle session 구분, adjusted/native 가격·거래량 단위, 주식수·기업행동, 결측·revision, raw/processed 계보, 운영 권리 Gate를 모두 충족한다.
- availability `limited`: 자료 또는 문서 일부는 있으나 하나 이상의 필수 Gate가 불완전하여 명시된 제한 연구만 가능하다.
- availability `data_unavailable`: retrievedAt에 확인한 public v1.2.2 scope에서 필요한 documented path/field를 찾지 못했다는 관측이다. 공급자 전체에 자료가 존재하지 않는다는 단정이 아니다.
- identifiability `identifiable`: 해당 관측이 명시된 claim을 직접 분리할 때만 허용한다.
- identifiability `not_identifiable`: 자료가 존재해도 목표 구성개념, 종목 행동, 사건 순서 또는 동기를 관측으로 분리할 수 없다.

raw availability와 claim identifiability를 하나의 four-way terminal로 합치지 않는다. 기술 문서의 존재와 수집·이용 권한도 별도 판정하며, 권리 또는 documentation revision 실패는 다른 품질로 상쇄하지 않는다.

각 입력군의 `evidenceStatements`는 exact `{evidenceKind,text,sourceIds,sourceLocation,authorityRefs}` 객체다. `evidenceKind`는 `document_fact`, `document_absence_observation`, `research_inference`, `operational_control`만 허용한다. 문서 사실·부재 관측은 등록된 외부 source ID를, research inference와 operational control은 내부 authority를 갖는다. operational control은 외부 문서를 단독 권위로 오표기하지 않는다. 문서 부재 관측은 retrievedAt의 public version scope와 검색한 path/field를 명시하며 “공급자에 없다”로 일반화하지 않는다.

## 결측과 우회 금지

공통 정책은 `reject_no_zero_or_neutral_imputation`이다. 결측 direct input을 0, neutral 또는 baseline으로 대체하지 않는다. 결측 항목을 뺀 뒤 나머지 입력의 reweight와 renormalize를 금지한다. 대체 provider, 유사 endpoint, snapshot 또는 최근 체결로 필수 순서자료를 충족했다고 주장하지 않는다.

## Credential과 현재 라이브 Gate

- 대화 disclosure는 사실과 위험만 기록하고 값은 기록하지 않는다.
- local credential file의 presence/path 관측과 contents/value 접근을 분리한다. contents와 file-origin values는 읽지 않았다.
- renderer, persistent repository, CLI arguments는 credential 전달 위치로 금지한다.
- 현재 disposition은 `blocked_pending_rotation`이다.
- provider use policy `TOSS-POLICY-001`은 FAQ exact text의 `personal_trading_only`, external distribution restriction, `commercialUse=prohibited_by_faq`만 문서화한다. local internal research, local retention/cache, derived publication은 `not_documented`이며 `legalConclusion=null`이다.
- 미문서 영역을 금지라고 단정하지 않고 `blocked_pending_provider_clarification` 운영통제로 처리한다.
- 현재 live collection은 `blocked_pending_rotated_credentials_and_provider_retention_clarification`이다.
- credential 회전과 provider clarification 전에는 라이브 수집, 응답 저장, 데이터 처리 또는 endpoint 탐색 호출을 시작하지 않는다.

이 차단은 자료 부재를 중립값으로 채우거나 다른 입력을 재가중하는 방식으로 우회할 수 없다.

## 향후 라이브 수집 Gate

향후 live gate는 다음 조건을 모두 충족한 뒤에만 열 수 있다.

1. 이 본문의 exact protocol hash가 `protocol.sha256`, source matrix, trial ledger에 일치한다.
2. 공개된 값을 폐기하고 별도로 발급한 rotated credential만 one-shot child process environment로 전달한다.
3. personal trading FAQ 범위와 별도로 local internal research, local retention/cache, 정제자료 보존, derived publication 범위를 provider에게 명확히 확인한다.
4. 각 raw HTTP response와 processed canonical data를 별도 artifact로 보존하고 별도 SHA-256과 collector-generated `clientReceivedAt`을 기록한다.
5. OHLC invariant, timestamp·timezone, calendar session availability와 candle membership, duplicate, inclusive before·nextBefore cutoff, currency, rate-limit 처리를 사전 검증한다.
6. 수집 명령과 산출물 전체의 secret scan 0을 확인한다.

하나라도 실패하면 Gate는 계속 닫힌다. 인증을 할 수 있다는 사실은 보존·재배포 권리를 보충하지 않는다.

## 입력군별 사전 경계

1. raw OHLCV schema availability와 derived claim identifiability를 분리한다. bar-start OHLC·currency schema, unit 계약 없는 volume field, 방법이 없는 adjusted request option은 raw availability `limited`이고 candle session membership은 `data_unavailable`이다. `price_volume_regime`은 derived claim이므로 `identifiabilityImplications`와 `usableFor`에만 둔다. 같은 OHLCV를 human_behavior_psychology_or_intent로 해석하거나 미시구조·체결에 사용하는 것은 `not_identifiable` 또는 차단이다.
2. factor는 한국 지수·국채·환율의 price-derived subset만 limited로 기록하고 미국·업종·변동성·canonical factor feed는 retrievedAt public v1.2.2 scope의 `data_unavailable`로 기록한다.
3. 현재 발행주식수 후보는 point-in-time 유통주식수나 기업행동 이력을 대신하지 않는다.
4. 검색·뉴스노출의 documented path/field는 retrievedAt public v1.2.2 scope에서 찾지 못했다. raw availability `data_unavailable`과 인간 심리·의도 implication `not_identifiable`을 분리한다.
5. 투자자 흐름은 KOSPI/KOSDAQ 시장 집계의 KRW integer buy/sell amounts와 `updatedAt`를 limited로 허용한다. 당일 값은 잠정 갱신될 수 있고 historical final revision scope는 미문서이며 종목 행동으로 일반화하지 않는다.
6. 옵션·공매도·대차의 documented path/field는 retrievedAt public v1.2.2 scope에서 찾지 못했다.
7. 호가 snapshot과 당일 최근 체결은 순서보존 체결·취소·aggressor·historical depth를 대신하지 않으며 `ST-MIC-001`과 `ST-EXE-001`을 차단한다.

homepage marketing이 REST/WebSocket을 언급하더라도 canonical OpenAPI와 overview는 현재 REST only이고 documented WebSocket endpoint가 없다. canonical OpenAPI+overview를 endpoint SSOT로 우선하며 ordered event availability를 만들지 않는다.

## 수락·무효 조건

다음이 모두 충족될 때만 이 계약 감사를 수락한다.

1. 8개 입력군이 exact availability, component availability와 claim identifiability를 가진다.
2. 각 입력군의 provider 후보, 인증 경계, timestamp·단위·revision·policy reference, 현재 가용성, 차단효과, usableFor, blockedResearchUses, source ID, evidence statement가 비어 있지 않다.
3. protocol hash, source matrix, 빈 trial ledger의 결박이 일치한다.
4. JSON artifact가 strict canonical bytes이며 중복 key가 없다.
5. credential 값, 미완성 표식, 시장자료 또는 결과가 artifact에 없다.

문서에 없는 사실 추론, 라이브 API 호출, credential file contents·values 접근, 권리 Gate 상쇄, 결측 대체, 해시 결박 불일치는 전체 감사를 무효로 한다.

## 실행·공개 계약

초기 trial ledger는 `runs=[]`다. 이 conceptual audit에서는 ExperimentRun과 EvidenceBundle을 생성하지 않는다. trace evidence도 발명하지 않는다. 모든 `limited`와 `data_unavailable` 판정을 숨김없이 source matrix와 Markdown projection에 공개한다.

## Amendment 규칙

동결 뒤 변경은 이 파일을 덮어쓰지 않는다. 새 credential, provider clarification, 문서 bytes·version, endpoint, availability 또는 identifiability가 바뀌면 이미 본 정보, 변경 이유, 영향받는 입력군과 남은 독립 범위를 기록한 새 프로토콜 버전을 만든다.
