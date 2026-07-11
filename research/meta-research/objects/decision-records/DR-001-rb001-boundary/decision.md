# DR-001 RB-001 연구 사용 경계 결정

## 정체성

- 객체 ID: `DR-001`
- 결정 대상: `RB-001`
- 근거 묶음: `EB-001`
- 근거 수준: `exploratory`

`boundary-contract.json`은 권위 있는 경계 SSOT다. 이 문서는 해당 구조화 계약을 사람이 읽을 수 있게 설명한다. `boundary-contract.json`과 충돌하는 prose는 허용 범위를 넓힐 수 없다.

## 결정

- 상태: `research_only`
- 운영 사용 가능 여부: `NO`

RB-001은 아래 세 연구 목적에만 사용할 수 있다. 운영 앱, 거래 판단, 공식 성능 평가 또는 채택 판정에는 사용할 수 없다.

## 허용 범위

다음 세 용도만 허용한다.

- `failure_reproduction_descriptive_defect_evidence` — 실패 재현과 관찰된 결함의 기술적 근거
- `prohibited_condition_design` — 후속 프로토콜의 금지조건 설계
- `seen_development_data_boundary_identification` — 이미 본 개발자료 경계 식별

이 목록 밖의 용도는 허용하지 않는다.

## 금지 범위

다음 세 증거 역할로 사용할 수 없다.

- `performance_or_adoption_evidence` — 성능 또는 공식 채택 근거
- `independent_reproducibility_or_replicability_evidence` — 독립 재현성 또는 독립 반복검증 근거
- `proof_of_frozen_generation_provenance` — 원래 동결 생성 계보의 증명

현재 snapshot의 자체 일관성이나 보고된 결정적 반복은 이 금지를 완화하지 않는다.

## Gate 한계

G0: 원래 동결 생성 계보가 입증되지 않아 기존 RB-001의 경계 통과 근거로 사용할 수 없다.

G9: 현재 self-consistency와 보고된 반복 실행은 독립 artifact reproduction이 아니므로 독립재현 통과 근거가 아니다.

세 phase transition의 실행 주체와 명령은 알려져 있지 않으므로 특정 행위나 실행 계보를 추정하지 않는다. 현재 snapshot self-consistency는 원래 frozen provenance를 증명하지 않는다.

## 운영 계약

RB-001의 수치, 결론, manifest 또는 보고서를 운영 앱 변경, 거래 신호, 가중치 선택, threshold 선택, 채택 또는 조건부 채택의 근거로 전달하지 않는다. 후속 연구는 RB-001에 노출된 구간을 `seen_development_data`로 취급하고 별도 객체·자료·실행 계보를 사용한다.

## 재개 조건

운영 또는 재현성 근거 자격은 기존 RB-001을 수정해 되살리지 않는다. 아래 조건을 순서대로 충족하는 새 기준선에서만 다시 심사한다.

- `new_separately_versioned_baseline` — 기존 RB-001과 분리된 새 버전의 기준선
- `immutable_pre_run_code_and_inputs` — 실행 전에 불변으로 봉인된 코드와 입력
- `witnessed_manifest_generation` — 실행 주체와 명령을 포함해 목격·기록된 manifest 생성
- `same_team_repeat` — 동일 팀의 반복 실행
- `independent_artifact_reproduction` — 다른 실행자의 독립 artifact 재현
- `external_replication_as_applicable` — 주장 범위에 적용되는 경우 외부 자료 또는 독립 구현 반복검증

이 조건을 충족해도 새 기준선의 별도 DecisionRecord가 필요하며 DR-001의 기존 판정은 덮어쓰지 않는다.

## 보안

등록된 민감값 패턴 정책으로 이 aggregate의 artifact를 검사한 결과 match는 0건이다. 이 결과는 등록 패턴 범위에 한정되며 모든 가능한 민감값 부재를 증명하지 않는다.
