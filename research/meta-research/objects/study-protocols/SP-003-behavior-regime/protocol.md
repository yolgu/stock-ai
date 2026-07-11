# SP-003 직접 행동 5거래일 예측 연구 프로토콜

## 정체성과 동결

- 객체 ID: `SP-003`
- study slot: `ST-BEH-001`
- 연구질문: `RQ-003`
- 자료계약: `DC-003`
- 상위 프로그램: `RP-001`
- 프로토콜 버전: `1.0.0`
- 동결일: `2026-07-10`
- 본문 hash 위치: `protocol.sha256`

프로토콜 본문의 SHA-256은 같은 디렉터리의 sidecar에만 기록한다. 본문에는 실제 hash 값을 복제하지 않는다. trial ledger는 이 본문과 정확히 일치하는 hash에만 결박한다.

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `SP-003`
- contract operational decision: block_human_behavior_claim; allow_research_only_price_volume_regime
- contract primary baseline: price-only price_volume_regime baseline
- contract primary estimand: ΔBrier=baseline-candidate for the predefined 5-session onset event
- contract primary horizon: `5 거래일`
- contract study slot: `ST-BEH-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 현재 상태와 승격 Gate

현재 lifecycle은 `proposed`다. 이 문서는 사전등록 상태가 아니며 확증 증거가 아니다. 자료 source acceptance와 lifecycle promotion Gate를 모두 통과한 새 version만 실행 가능한 preregistration이 될 수 있다. 현재 설계를 작성하며 시장자료를 열람하지 않았다.

source identity·권리, 직접 행동 입력의 시점·분모·revision, 5거래일 라벨 계보, 재현 가능한 raw/processed hash가 수락되지 않으면 실행 disposition은 `blocked` 또는 `data_unavailable`이다. 후보·분할·최소효과·중단 규칙은 lifecycle promotion 전에 동결한다.

## 질문과 estimand

> 시점 t까지 가용한 직접 행동 측정치가 가격 전용 기준선보다 향후 5거래일 onset event 확률을 외부표본에서 개선하는가?

- 모집단: DC-003의 모든 수락조건을 통과한 종목·시점 t
- 관측단위: 종목 × 시점 t
- 주요 estimand: 동일 outer test 행에서 `ΔBrier=baseline-candidate`로 계산한 가격 전용 기준선 대비 직접 행동 후보의 OOF Brier score 감소
- primary horizon: `5 거래일`
- 부차 estimand: 같은 행의 `Δlog-loss`, calibration 차이와 coverage
- 성공 방향: 양의 ΔBrier이며 사전 고정 `최소효과 δ` 이상

`interval outcome labels`는 시점 t 뒤 5개 거래세션 안의 사전 고정 onset event 최초 발생 여부다. 사건식, threshold, 겹친 위험창과 censoring 규칙은 promotion 전에 고정한다.

## 기준선과 후보 registry

- 후보군 B0: 무조건부 발생률과 시점 t까지의 가격 이력만 쓰는 `price_volume_regime` 기준선
- 후보군 B1: B0에 적격 `direct attention/news exposure`와 `symbol flow`를 더한 사전 정규화 선형 확률모형
- 후보군 B2: B0에 적격 `options/short/borrow`와 `linked account/self-report`를 더한 사전 제한 비선형 확률모형

모든 후보는 같은 fold·같은 eligibility·같은 outcome을 사용한다. 복잡도 우선순위를 두지 않는다. 복잡한 후보는 같은 정보의 단순 후보보다 δ를 넘는 외부표본 증분이 있을 때만 유지한다.

## feature와 금지 입력

허용 feature는 시점 t 이하 availability timestamp를 가진 가격이력과 DC-003이 수락한 직접 입력뿐이다. `human behavior claim`은 직접 측정과 판별타당도가 모두 있을 때만 평가하며, 그렇지 않으면 `not_identifiable`이다.

다음을 금지한다.

1. 결과창의 가격·수익·event 여부 또는 사후 revision
2. 미래 publication·client receipt 시각을 가진 행동행
3. 가격 파생 점수를 attention·심리·의도로 재명명한 입력
4. 결측 행동 입력의 0·neutral 대체나 남은 입력 재가중
5. terminal 결과를 본 뒤의 feature, threshold, 상태명 또는 후보 변경

## 표본 역할과 분할

`TSLA/NVDA/MU/000660`의 기존 연구구간은 `discovery/regression`, failure reproduction과 설계 점검에만 사용한다. 같은 기간의 새 feature는 exploratory only이며 confirmatory 외부표본으로 재명명하지 않는다.

분할은 시간순 `outer nested purged walk-forward`다.

1. outer train에서 후보를 적합하고 다음 outer validation·test 구간에 한 번 적용한다.
2. feature 선택, hyperparameter, calibration map, abstain threshold와 candidate tie-break는 inner fold에서만 정한다.
3. purge 길이는 outcome horizon 이상이며 `embargo: 20 sessions`를 각 outer 경계에 적용한다.
4. 겹친 5거래일 outcome window와 동일 event cluster는 서로 다른 역할로 분할하지 않는다.
5. 마지막 `terminal holdout`은 study당 한 번만 연다.

terminal holdout을 연 뒤에는 refit하지 않는다. threshold를 바꾸지 않는다. 상태명을 바꾸지 않는다. 후보를 추가하지 않는다. 실패한 holdout을 새 validation set으로 재사용하지 않는다.

## 불확실성·다중검정·coverage

- 종목과 겹친 사건창을 보존하는 `clustered moving-block bootstrap`으로 ΔBrier와 Δlog-loss 신뢰구간을 계산한다.
- 후보·horizon 고정 family에 `Holm family correction`을 적용하고 보정 전후 값을 모두 공개한다.
- 확률의 reliability curve, calibration intercept·slope와 Brier decomposition을 보고한다.
- `abstain` 규칙은 inner fold에서 고정하고 전체 coverage, 선택표본 오차와 `risk-coverage` 곡선을 함께 공개한다.
- 낮은 coverage로 오류를 숨길 수 없으며 최소 coverage 미달은 insufficient evidence다.

## 반증·leakage 검사

1. 행동행의 `시점 순서 shuffle`을 negative control로 실행한다.
2. 예측시점 뒤 모든 row를 바꾸어도 현재 예측이 같아야 하는 `future-row invariance`를 검사한다.
3. 미래 publication timestamp, outcome label 또는 사후 revision을 의도적으로 주입한 leakage sentinel이 validator에서 거부되는지 검사한다.
4. 직접 행동 입력군별 `ablation`과 가격기준선 복제를 비교한다.
5. label·symbol linkage permutation과 무관한 시계열을 추가 negative control로 사용한다.

negative control이 실제 후보와 같은 방향·크기의 개선을 보이거나 future-row invariance가 실패하면 무효 실행이다.

## 최소효과 결정

최소효과 δ는 예상 수집·검증 `비용·검정력·synthetic data` 시뮬레이션으로 정한다. event rate, cluster 길이, missingness와 calibration drift를 보수적으로 변화시키며 Brier 단위의 탐지가능 효과를 계산한다. δ, seed, 시나리오와 선택근거는 lifecycle promotion 전에 동결하고 terminal 결과를 본 뒤 낮추지 않는다.

## 무효·중단·terminal 판정

다음은 무효 실행이며 terminal status를 `implementation_invalid`로 기록한다.

- protocol hash, fold, seed, feature registry 또는 outcome 정의 불일치
- 미래행·사후 revision leakage, purge·embargo 위반
- eligibility가 다른 기준선과 후보 비교
- negative control·future-row invariance 실패를 숨기거나 제외

중단 규칙은 source 권리 철회, 필수 direct input coverage 미달, label 계보 실패, 회복 불가능한 구현 위반이다. 중단 전 생성된 상태와 사유는 보존한다.

terminal status는 `supported`, `refuted`, `insufficient_evidence`, `not_identifiable`, `data_unavailable`, `implementation_invalid`, `external_failure` 중 하나다. 최소효과·불확실성·반증 Gate를 모두 통과하면 supported, 효과가 δ에 못 미치면 refuted, 검정력이 부족하면 insufficient_evidence다. 직접 측정으로 human behavior claim을 분리하지 못하면 not_identifiable, 수락 자료가 없으면 data_unavailable, 연구 외부 장애는 external_failure다.

## study 격리와 공개

한 study의 terminal holdout으로 다른 study의 feature, threshold, 상태명, 후보 registry 또는 lifecycle을 바꾸지 않는다. 다른 study의 holdout 결과를 이 study의 inner fold로 가져오지 않는다.

자료가 없어 계산할 수 없는 후보도 ledger에서 삭제하지 않는다. `blocked` 또는 `data_unavailable` disposition, 모든 terminal status, calibration·coverage·negative control 결과를 방향과 무관하게 공개한다.

현재는 source acceptance 전이므로 ExperimentRun과 EvidenceBundle을 생성하지 않는다. 초기 `ST-BEH-001` ledger의 `runs`는 비어 있어야 한다.

## Amendment 규칙

동결 뒤 변경은 이 파일을 덮어쓰지 않는다. 새 version은 변경 이유, 변경 전에 본 자료와 결과, 영향받는 후보·fold·δ와 남은 독립 범위를 기록하고 별도 hash를 가진다.
