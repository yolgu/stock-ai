# SP-005 순서보존 미시구조 60초 예측 연구 프로토콜

## 정체성과 동결

- 객체 ID: `SP-005`
- study slot: `ST-MIC-001`
- 연구질문: `RQ-005`
- 자료계약: `DC-005`
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
- contract object id: `SP-005`
- contract operational decision: block_MIC_execution
- contract primary baseline: price-history baseline
- contract primary estimand: OOF squared-error reduction for the event-plus-60-second signed midquote markout
- contract primary horizon: `event 후 60초`
- contract study slot: `ST-MIC-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 현재 상태와 승격 Gate

현재 lifecycle은 `proposed`다. 이 문서는 사전등록 상태가 아니며 확증 증거가 아니다. 자료 source acceptance와 lifecycle promotion Gate를 모두 통과한 새 version만 실행 가능한 preregistration이 될 수 있다. 현재 설계를 작성하며 시장자료를 열람하지 않았다.

DC-002 범위에서 `ordered book/trade/cancel/aggressor sequence`는 `currently unavailable`이다. `venue clock/sequence`, `tick/halts/message loss`, 60초 quote endpoint, raw/processed 계보와 권리가 수락되지 않으면 실행 disposition은 `blocked` 또는 `data_unavailable`이다. 후보·분할·최소효과·중단 규칙은 lifecycle promotion 전에 동결한다.

## 질문과 estimand

> 시점 t까지 완전히 수신된 순서보존 미시구조 정보가 가격이력 기준선보다 event 후 60초 markout을 외부표본에서 더 정확히 예측하는가?

- 모집단: DC-005의 sequence·clock·book integrity Gate를 통과한 venue event
- 관측단위: instrument × venue × sequence event
- 주요 estimand: 동일 outer test event에서 가격이력 기준선 대비 미시구조 후보의 `OOF squared-error` 감소
- primary horizon: `event 후 60초`
- 결과: 사전 고정 부호와 endpoint로 계산한 `signed midquote markout`
- 부차 estimand: markout 부호 확률의 calibration, coverage와 session별 오차
- 성공 방향: 양의 baseline MSE-candidate MSE이며 사전 고정 `최소효과 δ` 이상

event type, 부호, 직전 midquote, 정확한 60초 endpoint, halt·session-end censoring은 promotion 전에 고정한다.

## 기준선과 후보 registry

- 후보군 M0: 시점 t까지의 짧은 가격이력, 직전 midquote 변화와 현재 spread만 쓰는 기준선
- 후보군 M1: M0에 사전 창의 `OFI/depth/spread/cancel/aggressor/Hawkes` 중 OFI·depth·spread·cancel·aggressor 특징을 더한 단순 후보
- 후보군 M2: M1의 같은 ordered history에 사전 제한 Hawkes intensity를 더한 후보

모든 후보는 같은 event, fold, markout과 eligibility를 사용한다. 복잡도 우선순위를 두지 않는다. Hawkes 후보는 같은 정보의 단순 후보보다 δ를 넘는 외부표본 증분과 안정성 Gate를 통과할 때만 유지한다.

## feature와 금지 입력

허용 feature는 시점 t까지 clientReceivedAt과 sequence validation이 끝난 book, trade, cancel, aggressor message와 point-in-time venue reference뿐이다.

다음을 금지한다.

1. 결과 endpoint 또는 시점 t 뒤 message·quote·revision
2. sequence gap을 0 activity로 채우거나 unknown aggressor를 임의 방향으로 배정
3. `snapshot/recent trades`로 ordered sequence를 대체
4. 미래 halt·message loss·session status로 현재 eligibility를 정함
5. terminal 결과를 본 뒤 event type, threshold, 상태명 또는 후보 변경

snapshot과 recent trades는 ordered event history를 대체할 수 없다.

## 표본 역할과 분할

`TSLA/NVDA/MU/000660`의 기존 일봉·snapshot 연구구간은 `discovery/regression`, failure reproduction과 validator 설계에만 사용한다. 순서보존 원자료가 아니므로 confirmatory 미시구조 외부표본으로 재명명하지 않는다.

분할은 session 순서를 보존한 `outer nested purged walk-forward`다.

1. outer train session에서 feature·후보를 적합하고 다음 outer validation·test session에 고정 적용한다.
2. window, decay, Hawkes regularization, calibration, abstain threshold와 tie-break는 inner fold에서만 정한다.
3. purge 길이는 outcome horizon 이상이며 `embargo: one full session plus 60 seconds`를 각 outer 경계에 적용한다.
4. 겹친 60초 outcome, 같은 burst와 message-loss cluster를 서로 다른 역할로 나누지 않는다.
5. 마지막 `terminal holdout`은 study당 한 번만 연다.

terminal holdout을 연 뒤에는 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다. terminal session을 새 training 또는 validation으로 재사용하지 않는다.

## 불확실성·다중검정·coverage

- venue·session·burst 의존성과 겹친 markout을 보존하는 `clustered moving-block bootstrap`으로 제곱오차 개선 신뢰구간을 계산한다.
- OFI, depth, spread, cancel, aggressor, Hawkes와 사전 venue family에 `Holm family correction`을 적용한다.
- signed markout 연속예측과 함께 부호 확률의 calibration을 보조로 보고한다.
- `abstain` 규칙은 inner fold에서 고정하고 event coverage, 선택표본 오차와 `risk-coverage`를 함께 공개한다.
- message integrity 또는 endpoint coverage가 최소치를 밑돌면 insufficient_evidence 또는 data_unavailable이다.

## 반증·leakage 검사

1. event의 `시점 순서 shuffle`을 negative control로 실행한다.
2. 시점 t 뒤 book·trade·quote row를 바꾸어도 현재 feature와 예측이 같아야 하는 `future-row invariance`를 검사한다.
3. 미래 quote, 결과 markout과 사후 aggressor를 의도적으로 넣은 sentinel을 validator가 거부하는지 검사한다.
4. OFI, depth, spread, cancel, aggressor와 Hawkes별 `ablation`을 수행한다.
5. side permutation, sequence reversal과 무관한 synthetic event stream을 추가 negative control로 사용한다.

negative control이 같은 개선을 보이거나 future-row invariance·book replay invariant가 실패하면 무효 실행이다.

## 최소효과 결정

최소효과 δ는 ordered feed 확보·검증 `비용·검정력·synthetic data` 시뮬레이션으로 정한다. session cluster, burst length, tick size, message loss, Hawkes stability와 endpoint missingness를 보수적으로 변화시켜 탐지가능 제곱오차 감소를 계산한다. δ, seed와 시나리오는 lifecycle promotion 전에 동결하고 terminal 결과 뒤 낮추지 않는다.

## 무효·중단·terminal 판정

다음은 무효 실행이며 terminal status를 `implementation_invalid`로 기록한다.

- protocol hash, fold, seed, event registry 또는 markout 정의 불일치
- future message·quote leakage, sequence·clock 재구성 실패
- purge·embargo 위반 또는 eligibility가 다른 기준선 비교
- negative control·future-row invariance·book invariant 실패 은폐

중단 규칙은 source 권리 철회, ordered feed 부재, 회복 불가능한 sequence gap·clock drift, endpoint coverage 미달과 구현 위반이다. 중단 전 상태와 사유를 보존한다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. 최소효과·불확실성·반증 Gate를 모두 통과하면 supported, 효과가 δ에 못 미치면 refuted, 검정력이 부족하면 insufficient_evidence다. ordered mechanism을 식별할 수 없으면 not_identifiable, ordered feed가 없으면 data_unavailable, 연구 외부 장애는 external_failure다.

## study 격리와 공개

한 study의 terminal holdout으로 다른 study의 feature, threshold, 상태명, 후보 registry 또는 lifecycle을 바꾸지 않는다. 다른 study의 holdout 결과를 이 study의 event·window 선택에 사용하지 않는다.

자료가 없어 계산할 수 없는 후보도 ledger에서 삭제하지 않는다. `blocked` 또는 `data_unavailable` disposition, 모든 terminal status, calibration·coverage·negative control 결과를 방향과 무관하게 공개한다.

현재는 ordered source acceptance 전이므로 ExperimentRun과 EvidenceBundle을 생성하지 않는다. 초기 `ST-MIC-001` ledger의 `runs`는 비어 있어야 한다.

## Amendment 규칙

동결 뒤 변경은 이 파일을 덮어쓰지 않는다. 새 version은 변경 이유, 변경 전에 본 자료와 결과, 영향받는 event·candidate·fold·δ와 남은 독립 범위를 기록하고 별도 hash를 가진다.
