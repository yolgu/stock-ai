# SP-004 PIT 상대가치 20거래일 예측 연구 프로토콜

## 정체성과 동결

- 객체 ID: `SP-004`
- study slot: `ST-VAL-001`
- 연구질문: `RQ-004`
- 자료계약: `DC-004`
- 상위 프로그램: `RP-001`
- 프로토콜 버전: `1.0.0`
- 동결일: `2026-07-10`
- 본문 hash 위치: `protocol.sha256`

프로토콜 본문의 SHA-256은 같은 디렉터리의 sidecar에만 기록한다. 본문에는 실제 hash 값을 복제하지 않는다. trial ledger는 이 본문의 exact hash에만 결박한다.

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `SP-004`
- contract operational decision: block_confirmatory_VAL
- contract primary baseline: price/factor baseline
- contract primary estimand: OOF ΔBrier for the 20-session industry/market-adjusted positive excess-return event
- contract primary horizon: `20 거래일`
- contract study slot: `ST-VAL-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 현재 상태와 승격 Gate

현재 lifecycle은 `proposed`다. 이 문서는 사전등록 상태가 아니며 확증 증거가 아니다. 자료 source acceptance와 lifecycle promotion Gate를 모두 통과한 새 version만 실행 가능한 preregistration이 될 수 있다. 현재 설계를 작성하며 시장자료를 열람하지 않았다.

point-in-time universe, factor·fundamental vintage, 기업행동·상장폐지, raw/processed 계보와 권리가 수락되지 않으면 실행 disposition은 `blocked` 또는 `data_unavailable`이다. 후보·분할·최소효과·중단 규칙은 lifecycle promotion 전에 동결한다.

## 질문과 estimand

> 시점 t의 PIT 상대가치 잔차가 가격·요인 기준선보다 향후 20거래일 산업·시장조정 양의 초과수익 사건을 외부표본에서 더 정확히 예측하는가?

- 모집단: DC-004의 모든 수락조건을 통과한 point-in-time universe의 종목·시점 t
- 관측단위: 종목 × 시점 t
- 주요 estimand: 동일 outer test 행에서 가격·요인 기준선 대비 PIT 상대가치 후보의 OOF Brier score 감소
- primary horizon: `20 거래일`
- 결과: `industry/market-adjusted positive excess-return event`
- 부차 estimand: log-loss, calibration, coverage와 사전 비용 시나리오의 `cost-adjusted excess return`
- 성공 방향: 양의 ΔBrier이며 사전 고정 `최소효과 δ` 이상

산업·시장 benchmark, total-return, 기업행동, 통화환산, 상장폐지와 event threshold는 promotion 전에 고정한다.

## 기준선과 후보 registry

- 후보군 V0: 시점 t까지의 가격·거래량과 적격 공통요인만 쓰고 상대가치 잔차는 제외한 기준선
- 후보군 V1: `PIT universe/membership`과 `factors/fundamentals/industry/rates/FX`로 계산한 상대가치 잔차의 mean-reversion 후보
- 후보군 V2: 같은 PIT 잔차의 momentum 후보

`mean-reversion/momentum` 방향은 결과 후 선택하지 않는다. 두 후보를 처음부터 같은 family에 등록하고 성공·실패를 모두 보고한다. 복잡도 우선순위를 두지 않는다. 복잡한 후보는 같은 정보의 단순 기준선보다 δ를 넘는 외부표본 증분이 있을 때만 유지한다.

## feature와 금지 입력

허용 feature는 시점 t 이하 availability timestamp의 가격, point-in-time membership, 산업, factors, fundamentals, rates, FX와 `native/adjusted reconciliation`을 통과한 기업행동 정보뿐이다.

다음을 금지한다.

1. 현재 universe를 과거에 소급하거나 delisted 종목을 제거한 패널
2. 최종 수정 fundamentals·산업분류·factor를 publication 이전 행에 사용
3. 미래 수익, 결과 사건, 미래 기업행동 또는 결과로 정한 benchmark
4. 결측 factor의 0·neutral 대체나 남은 factor 재가중
5. terminal 결과를 본 뒤 방향, threshold, 상태명 또는 후보 변경

`delisting/survivorship/vintage` Gate 하나라도 실패하면 해당 confirmatory 행은 부적격이다.

## 표본 역할과 분할

`TSLA/NVDA/MU/000660`의 기존 연구구간은 `discovery/regression`, failure reproduction과 설계 점검에만 사용한다. 같은 기간의 새 잔차나 factor는 exploratory only이며 `confirmatory VAL` 외부표본으로 재명명하지 않는다.

분할은 시간순 `outer nested purged walk-forward`이며 종목 단면을 같은 날짜 역할 안에 유지한다.

1. outer train에서 잔차 모형과 후보를 적합하고 다음 outer validation·test에 고정 적용한다.
2. factor 선택, regularization, residual scaling, calibration, abstain threshold와 tie-break는 inner fold에서만 정한다.
3. purge 길이는 outcome horizon 이상이며 `embargo: 20 sessions`를 각 outer 경계에 적용한다.
4. 같은 issuer, 겹친 20거래일 outcome window와 corporate-action cluster의 역할 누출을 금지한다.
5. 마지막 `terminal holdout`은 study당 한 번만 연다.

terminal holdout을 연 뒤에는 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다. terminal 결과로 benchmark·industry mapping·방향을 다시 선택하지 않는다.

## 불확실성·다중검정·coverage

- 날짜·issuer·industry 의존성과 겹친 outcome을 보존하는 `clustered moving-block bootstrap`으로 ΔBrier와 순수익 신뢰구간을 계산한다.
- mean-reversion·momentum과 사전 하위집단 family에 `Holm family correction`을 적용하고 보정 전후 값을 공개한다.
- 확률의 reliability curve, calibration intercept·slope와 Brier decomposition을 보고한다.
- `abstain` 규칙은 inner fold에서 고정하고 coverage, 선택표본 오차와 `risk-coverage`를 함께 공개한다.
- PIT coverage 또는 delisting coverage가 최소치를 밑돌면 insufficient_evidence 또는 data_unavailable로 판정한다.

## 반증·leakage 검사

1. 잔차와 outcome의 `시점 순서 shuffle`을 negative control로 실행한다.
2. 예측시점 뒤 fundamentals·membership·price row를 바꾸어도 현재 예측이 같아야 하는 `future-row invariance`를 검사한다.
3. 최신 vintage·현재 constituent·미래 corporate action을 의도적으로 넣은 sentinel을 validator가 거부하는지 검사한다.
4. factor, fundamentals, industry, rates, FX와 residual 방향별 `ablation`을 수행한다.
5. 무작위 industry mapping과 stale residual을 추가 negative control로 사용한다.

negative control이 같은 개선을 보이거나 future-row invariance가 실패하면 무효 실행이다.

## 최소효과 결정

최소효과 δ는 point-in-time 자료 구축·검증 `비용·검정력·synthetic data` 시뮬레이션으로 정한다. 사건률, 단면 상관, industry cluster, vintage missingness와 비용 민감도를 보수적으로 변화시켜 탐지가능 ΔBrier를 계산한다. δ, seed와 시나리오는 lifecycle promotion 전에 동결하고 결과 뒤 낮추지 않는다.

## 무효·중단·terminal 판정

다음은 무효 실행이며 terminal status를 `implementation_invalid`로 기록한다.

- protocol hash, fold, seed, candidate registry 또는 outcome 정의 불일치
- survivorship·future vintage·membership leakage
- purge·embargo 위반 또는 eligibility가 다른 기준선 비교
- negative control·future-row invariance 실패의 은폐

중단 규칙은 source 권리 철회, PIT universe·vintage·delisting 계보 미달, 결과 재현 실패와 회복 불가능한 구현 위반이다. 중단 전 상태와 사유를 보존한다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. 최소효과·불확실성·반증 Gate를 모두 통과하면 supported, 효과가 δ에 못 미치면 refuted, 검정력이 부족하면 insufficient_evidence다. 상대가치 구성이나 방향을 식별할 수 없으면 not_identifiable, PIT 자료가 없으면 data_unavailable, 연구 외부 장애는 external_failure다.

## study 격리와 공개

한 study의 terminal holdout으로 다른 study의 feature, threshold, 상태명, 후보 registry 또는 lifecycle을 바꾸지 않는다. 다른 study의 holdout 결과를 이 study의 factor·industry 선택에 사용하지 않는다.

자료가 없어 계산할 수 없는 후보도 ledger에서 삭제하지 않는다. `blocked` 또는 `data_unavailable` disposition, 모든 terminal status, calibration·coverage·negative control 결과를 방향과 무관하게 공개한다.

현재는 source acceptance 전이므로 ExperimentRun과 EvidenceBundle을 생성하지 않는다. 초기 `ST-VAL-001` ledger의 `runs`는 비어 있어야 한다.

## Amendment 규칙

동결 뒤 변경은 이 파일을 덮어쓰지 않는다. 새 version은 변경 이유, 변경 전에 본 자료와 결과, 영향받는 candidate·fold·δ와 남은 독립 범위를 기록하고 별도 hash를 가진다.
