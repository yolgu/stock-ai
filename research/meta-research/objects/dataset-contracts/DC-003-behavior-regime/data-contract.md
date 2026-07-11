# DC-003 직접 행동·노출·흐름 데이터 계약

## 정체성

- 객체 ID: `DC-003`
- 적용 질문: `RQ-003`
- 적용 study: `ST-BEH-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-003`
- contract operational decision: block_human_behavior_claim; allow_research_only_price_volume_regime
- contract primary baseline: price-only price_volume_regime baseline
- contract primary estimand: ΔBrier=baseline-candidate for the predefined 5-session onset event
- contract primary horizon: `5 거래일`
- contract study slot: `ST-BEH-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 상속 경계

provider/source, 단위, 권리, 수정, 공통 시점과 계보 규칙의 SSOT는 `DC-002`다. 이 문서는 그 공통 필드를 복사하지 않는다. 각 수락행은 DC-002의 event timestamp, publication timestamp, `clientReceivedAt`, 거래소·시간대, revision, license와 redistribution Gate를 통과해야 한다.

연구별 `availability timestamp`는 event timestamp, publication timestamp, clientReceivedAt과 공급자 확정시각 중 예측시점 t에 실제 사용 가능한 가장 늦은 시각이다. raw/processed artifact는 분리하고 각각 byte hash, 변환 버전과 상위 raw hash를 보존한다.

수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다.

## 관측단위와 결합키

- 기본 관측단위: 종목 × 측정주체 또는 집계집단 × event
- 예측행 결합키: canonical instrument ID × 거래소 세션 × 시점 t
- 결과행: canonical instrument ID × 시점 t × 5거래일 위험창
- 시간 정렬: 입력 availability timestamp가 시점 t 이하인 행만 허용한다.

공급자의 현재 ticker를 과거 식별자로 소급하지 않는다. 종목 변경, 상장시장, 통화와 기업행동은 DC-002의 point-in-time 계보를 따른다.

## 직접 입력군

| 입력군 | 필수 study 고유 필드 | 허용 주장 | 금지된 대체 |
| --- | --- | --- | --- |
| `direct attention/news exposure` | 노출·검색 event ID, symbol linkage, 집계창, 대상 population과 denominator, bot·중복 정책, publication·availability 시각 | 종목별 직접 관심·노출의 관측 | 가격 전용 점수를 관심으로 재명명 |
| `symbol flow` | symbol, participant scope, buy·sell 방향, 수량·금액 단위, 집계창, 잠정·확정 revision | 정의된 집단의 종목별 흐름 | 시장 전체 흐름을 종목 행동으로 배분 |
| `options/short/borrow` | 계약·기초자산 linkage, expiry·strike, open interest·volume·short·borrow 단위, 보고 지연 | 직접 파생·공매도·대차 관측 | 가격 변동성으로 포지션을 역추정 |
| `linked account/self-report` | 동의된 pseudonymous linkage, 계좌 event 또는 응답시각, 모집·탈락·무응답 정보 | 연결 표본의 관측된 매매·보유·응답 | 매매에서 동기·감정을 자동 추론 |

입력군은 교환 가능하지 않다. attention 부재를 flow로, self-report 부재를 계좌거래로 보충했다고 간주하지 않는다.

## 결과 라벨 계약

`interval outcome labels`는 시점 t 뒤 5개 거래세션 안에 사전 고정 onset event가 처음 발생했는지를 나타낸다.

1. 사건식, threshold, 최초 발생, 동시 사건과 중복 위험창 처리를 프로토콜 동결 전에 정의한다.
2. 라벨은 시점 t 뒤 자료로 계산하되 어떤 결과 필드도 입력 feature나 eligibility에 들어가지 않는다.
3. 거래정지·상장폐지·세션 누락은 0 수익 또는 음성 라벨로 자동 변환하지 않는다.
4. 라벨 생성 raw 경로, calendar version과 processed label hash를 보존한다.

## 구성개념 판정

- 직접 행동자료가 가격 기준선 대비 예측을 개선해도 인간 심리·의도의 인과적 `human behavior claim`을 자동 승인하지 않는다.
- 직접 attention, flow, linked account 또는 self-report가 없으면 그 관측층의 availability는 `data_unavailable`이다.
- 직접 측정이 있어도 경쟁 동기와 표본선택을 분리할 수 없으면 심리·의도는 `not_identifiable`이다.
- 가격 이력만 적격이면 research-only `price_volume_regime` 회귀검사만 허용하고 행동 후보 실행을 차단한다.

availability와 identifiability는 별도 축이며 한 축의 성공으로 다른 축의 실패를 상쇄하지 않는다.

## 결측과 표본선택

- 결측 direct input을 0 또는 neutral로 대체하지 않는다.
- 결측 입력을 제외한 남은 입력을 reweight 또는 renormalize하지 않는다.
- 무노출과 노출 미관측, 무거래와 거래 미수집, 무응답과 중립응답을 같은 값으로 합치지 않는다.
- linked 표본의 가입·탈락·동의철회와 coverage 분모를 보존한다.
- 입력군별 coverage가 사전 최소치를 밑돌면 해당 후보 실행을 차단한다.

## 수락조건

다음 조건을 모두 만족한 입력만 `ST-BEH-001`에 허용한다.

1. provider 권리, 모집단, denominator와 symbol linkage가 문서화되어 있다.
2. event·publication·수신·확정시각으로 point-in-time 가용성을 재현할 수 있다.
3. raw/processed 계보와 revision이 일대일로 추적된다.
4. 직접 측정과 가격 파생 proxy가 명시적으로 분리된다.
5. 5거래일 라벨 calendar·사건식·중복 정책이 고정되어 있다.
6. 개인정보·동의·보존·재배포 Gate가 승인되어 있다.

하나라도 충족하지 못하면 관련 후보는 `blocked` 또는 `data_unavailable`이며 실행을 차단한다. 다른 입력의 높은 품질로 실패를 보상하지 않는다.

## 현재 상태와 공개

이 계약은 자료 source acceptance 이전의 conceptual 계약이다. 실제 행동 raw data나 결과의 존재를 주장하지 않는다. 수락·차단·not_identifiable·coverage 상태는 결과 방향과 무관하게 trial ledger에 남긴다.
