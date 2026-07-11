# RP-001 연구 실행 설계

## 1. 목적

`RP-001`을 메타 거버넌스 설계에서 실제 연구 프로그램으로 전환한다. 프로그램은 가격·거래량 현상, 잠재 국면, 인간 심리, 거래 의사결정을 분리하고, 독립 study가 생성한 외부 OOF 근거만 최종 의사결정에 사용한다. 채택 가능한 공식이 없거나 핵심 개념을 식별할 수 없는 결론도 완전한 근거와 재현 명령을 갖춘 terminal 결과로 인정한다.

## 2. 불변 경계

- `RB-001`의 v1.4 파일, 가중치, 결과, 원자료, manifest, 보고서는 후속 연구가 수정하지 않는다.
- 이미 열람한 TSLA·NVDA·MU·000660 구간은 `seen_development_data`이며 새 확인 연구의 외부표본으로 사용할 수 없다.
- 현재 작업공간에서 발견된 RB-001 manifest·보고서 재기록은 복구하거나 정당화하지 않는다. 최초 관찰값과 변경 후 값을 별도 무결성 근거로 보존하고 G0 실패 여부를 판정한다.
- 기존 renderer·Neutralino extension의 미커밋 변경은 수정하지 않는다.
- `MC-001`은 `proposed/conceptual` 후보이며 다른 후보보다 우선권을 갖지 않는다.
- 운영 앱은 최종 `DecisionRecord`가 `adopt` 또는 `conditional_adopt`일 때만 별도 후속 작업으로 변경할 수 있다.
- 인증정보는 기존 외부 경계가 일회성 프로세스 환경에서만 읽는다. 연구 artifact, 명령행, 로그, 보고서에는 secret을 남기지 않는다.

## 3. 선택한 구조

각 독립 study를 `ResearchQuestion → DatasetContract → StudyProtocol → ExperimentRun → EvidenceBundle → DecisionRecord` 객체 사슬로 표현한다. 객체는 기존 `research/meta-research` catalog에 등록하고, 실행 코드·데이터·결과는 `research/rp-001` 아래의 별도 artifact store에 둔다.

이 구조를 선택한 이유는 다음과 같다.

- 한 study의 holdout 결과가 다른 study의 변수·상태명·threshold에 영향을 주는 경로를 구조적으로 차단할 수 있다.
- 자료가 없는 study도 `data_unavailable` 또는 `not_identifiable` EvidenceBundle과 DecisionRecord로 종료할 수 있다.
- 질문, 자료, 실행, 근거, 결정의 변경 이유가 분리되고, 최종 추적률을 기계적으로 계산할 수 있다.
- RB-001과 새 연구의 해시·경로·표본 역할을 별도 원장으로 고정할 수 있다.

평면 문서만 추가하는 방식은 추적성과 trial 완전성을 기계적으로 보장하지 못해 제외한다. 모든 후보와 study를 하나의 대형 프로토콜로 묶는 방식은 holdout 오염과 사후 선택 위험이 커 제외한다.

## 4. 프로그램 산출물 경계

### 4.1 RP-001 프로그램 aggregate

`research/meta-research/objects/programs/RP-001-quantitative-market-behavior/`는 다음 프로그램 수준 artifact를 소유한다.

- Goal 원문과 SHA-256
- 원자화 요구사항 원장
- 요구사항→질문→study→근거→결정→보고서 추적행렬
- RB-001 경계·무결성 감사
- seen/unseen 표본 역할 원장
- 상태 온톨로지와 명칭허용 규칙
- source matrix
- candidate registry
- study registry
- 수식·구현·보상해킹 감사 원장
- 최종 품질 대시보드와 종료조건 판정

### 4.2 Study 객체 사슬

| Study slot | 질문 객체 | 자료계약 객체 | 프로토콜 객체 | terminal 책임 |
| --- | --- | --- | --- | --- |
| ST-ONT-001 | RQ-001 | DC-001 | SP-001 | 구성개념·상태 식별과 명칭허용 |
| ST-DAT-001 | RQ-002 | DC-002 | SP-002 | 데이터 계보·단위·가용시점 |
| ST-BEH-001 | RQ-003 | DC-003 | SP-003 | 행동 또는 가격국면·지속시간 |
| ST-VAL-001 | RQ-004 | DC-004 | SP-004 | 상대가치·공정가격 잔차 |
| ST-MIC-001 | RQ-005 | DC-005 | SP-005 | OFI·depth·spread·Hawkes |
| ST-EXE-001 | RQ-006 | DC-006 | SP-006 | 체결·슬리피지·시장충격·비용 |
| ST-RSK-001 | RQ-007 | DC-007 | SP-007 | 상관·CVaR·포지션 규모 |
| ST-SYN-001 | RQ-008 | DC-008 | SP-008 | 독립 외부 OOF 통합 |

`ST-*`는 포트폴리오 slot ID이고 catalog 객체 ID는 기존 `^[A-Z]{2,4}-[0-9]{3}$` 계약을 유지한다.

### 4.3 실행 artifact store

`research/rp-001/`은 다음 책임만 가진다.

```text
research/rp-001/
├── README.md
├── requirements.lock.txt
├── src/
│   └── rp001/
├── tests/
├── data/
│   ├── raw/
│   ├── processed/
│   └── manifest.json
├── protocols/
├── trials/
├── runs/
└── reports/
```

원시 데이터는 공급자 응답을 canonical JSON으로 저장하고, 정제 데이터는 원시 SHA-256·코드 SHA-256·변환 매개변수에 결박한다. 실행 결과는 append-only run directory에 저장하며 한 실행이 다른 실행의 파일을 덮어쓰지 않는다.

## 5. 요구사항과 상태 모델

Goal의 각 의무는 최소 판정단위로 나누고 `REQ-001`부터 순차 ID를 부여한다. 각 행은 원문 section·line 범위, 정규화된 요구사항, 적용 객체, 현재 상태를 가진다.

```text
registered → implemented → evidenced → decided → reported
          └→ blocked/data_unavailable/not_identifiable → evidenced → decided → reported
```

최종 `RequirementCoverage`의 분자는 `EvidenceBundle`, `DecisionRecord`, 최종 보고서 경로가 모두 연결된 요구사항만 센다. 문서가 존재하거나 코드가 실행됐다는 이유만으로 covered로 계산하지 않는다.

Study terminal status는 다음 중 하나다.

- `supported`
- `refuted`
- `insufficient_evidence`
- `not_identifiable`
- `data_unavailable`
- `implementation_invalid`
- `external_failure`

`blocked`는 외부 권한·유료계약·인증 없이는 실행할 수 없는 현재 실행상태다. 최종 종료 시에는 해당 장애가 만드는 과학적 결론인 `data_unavailable` 또는 `not_identifiable` DecisionRecord를 함께 남긴다.

## 6. 상태 온톨로지

네 층을 섞지 않는다.

1. 관측층: 가격, 거래량, spread, depth, 체결, 취소처럼 직접 기록된 값
2. 추정층: `price_volume_regime`, 번호가 붙은 잠재상태, 필터링 사후확률
3. 구성개념층: FOMO, 공포, 차익실현 의도처럼 외부 행동 측정과 식별검사가 필요한 개념
4. 결정층: 매수·매도·헤지·축소·NoTrade

OHLCV만 사용한 결과에는 심리명칭을 붙이지 않는다. 목표 상태명은 독립 행동·흐름 자료가 수렴타당도와 판별타당도를 통과한 경우에만 허용한다. 그렇지 않으면 `upside_acceleration`, `post_runup_reversal`, `downside_acceleration`, `relief_rebound`, `normalization` 같은 관측 가능한 가격국면 이름을 사용한다.

## 7. 데이터 전략

### 7.1 표본 역할 고정

- RB-001 네 종목 구간: failure reproduction·설계·회귀검사 전용
- 저장소에 없고 프로토콜 동결 뒤 처음 수집하는 종목·기간: retrospective external candidate
- 사전등록 이후 새로 발생한 기간: prospective confirmation candidate
- 순서보존 주문장 자료: ST-MIC-001 전용

회고 외부표본은 연구자가 시장사를 알고 있을 수 있으므로 전향표본과 동일한 복제수준으로 과장하지 않는다.

### 7.2 가용 데이터와 차단

기존 Toss 일봉 경계는 인증정보를 노출하지 않고 adjusted OHLCV를 수집할 수 있지만 publication timestamp, revision history, native/adjusted volume 단위, 주식수, 기업행동 원장이 완전하지 않다. 따라서 가격경로 연구만 활성화할 수 있고, 거래량·회전율·실제 심리·OFI·Hawkes·체결시장충격 주장은 필수 자료가 충족될 때까지 차단한다.

필수 필드가 없으면 0, 중립점수, 원수익률, 평균 비용으로 대체하지 않는다. 각 차단은 DatasetContract와 trial ledger에 남긴다.

## 8. 후보 비교

candidate registry는 다음 가족을 결과 열람 전에 모두 등록한다.

- 무조건부 발생률
- 가격 모멘텀·drawdown·평균회귀와 사용 가능한 경우의 거래량 기준선
- RB-001 기존 문서 가중합
- 수학적으로 repair 가능한 기존식
- MC-001 계층 Bayesian HSMM·경쟁위험
- 단순 HMM·HSMM 가격국면 모형
- 동적 요인·상대가치 모형
- 전망이론·취득가격 분포 후보
- OFI·depth·Hawkes 후보
- 확률적 제어·체결·시장조성 후보
- 동일 정보의 비선형 후보

자료가 없어 계산할 수 없는 후보도 registry와 trial ledger에서 삭제하지 않고 `data_unavailable` 또는 `not_identifiable`로 판정한다. 복잡한 후보는 동일 fold·동일 정보의 단순 기준선보다 사전 고정 최소효과를 외부표본에서 넘을 때만 유지한다.

## 9. 실행 흐름

```text
Goal hash + requirement ledger
  → RB-001 integrity audit + sample-role freeze
  → RQ-001/DC-001/SP-001 ontology study
  → RQ-002/DC-002/SP-002 data audit
  → data-eligible studies preregistered independently
  → raw collection after protocol hashes exist
  → deterministic validation + trial ledger
  → EvidenceBundle per study
  → DecisionRecord per study
  → independent reproduction + adversarial review
  → ST-SYN-001 final DecisionRecord and report
```

한 study의 terminal holdout은 다른 study의 특징, threshold, 상태명, 비용계수, 최소효과를 변경하는 입력으로 사용할 수 없다.

## 10. 검증 설계

각 데이터 적격 확인 연구는 nested purged walk-forward와 outcome horizon 이상의 purge, 사전 고정 embargo를 사용한다. terminal holdout에서는 refit, threshold 변경, 상태 재명명, 후보 추가를 금지한다.

필수 검사는 다음과 같다.

- 과거 출력의 미래행 추가 불변성
- 특징·label 시간순서 교란
- negative control과 특징 ablation
- 분할·가격척도·통화 단위 metamorphic test
- 결측·OOD·abstain 계약
- 같은 사건 중복경보와 비중첩 사건 수
- symbol/event cluster를 보존하는 이동블록 bootstrap
- 다중 후보·horizon·threshold 보정
- 비용 base/stress 시나리오
- 독립 실행자의 manifest·수치 재현

확률예측, 사건탐지, 경제성, 꼬리위험은 한 점수로 합치지 않고 Gate별로 판정한다.

## 11. 오류·외부 장애 처리

- 자료 계약 위반은 해당 feature와 study만 차단하고 다른 study를 계속한다.
- 인증 실패는 secret을 출력하지 않는 안전한 코드와 `blocked` 실행기록으로 남긴다.
- protocol 동결 뒤 결함은 원본을 수정하지 않고 amendment와 새 버전을 만든다.
- baseline frozen mutation은 원본 복구 대신 관찰 시각·전후 hash·영향 범위를 EvidenceBundle로 보존한다.
- 무효 실행도 run ID, seed, 입력 hash, 실패 원인을 trial ledger에 기록한다.

## 12. 완료 판정

프로그램은 다음이 모두 기계적으로 확인될 때만 완료한다.

- 등록 요구사항 전부가 evidence·decision·report로 연결됨
- 모든 질문과 study가 terminal status를 가짐
- 질문·식별·기준선·반증·시점·trial·claim 품질지표가 각각 1.00
- RB-001과 새 연구의 경계 및 관찰된 동결 위반이 숨김없이 기록됨
- 실제 데이터 반복 실행과 불확실성 분포가 있음
- 모든 수치 주장이 EvidenceBundle ID와 artifact 경로를 가짐
- 독립 재현과 반대 결론 adversarial review가 있음
- 최종 DecisionRecord, 사람이 읽는 보고서, 실행 명령이 있음
- 미완성 토큰과 secret 패턴이 없음

채택 Gate를 모두 통과한 후보가 없으면 최종 결정은 `no_adoptable_formula`다. 필요한 관측이나 라벨 자체가 없으면 해당 질문은 `not_identifiable`이다. 두 결론 모두 실패가 아니라 사전 정의된 terminal 결과다.

## 13. 검증 명령 경계

구조·프로그램·실행 검증은 서로 분리한다.

```bash
python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v
python3 research/meta-research/tools/validate_research_program.py \
  --repository-root . \
  --program-root research/meta-research
python3 -m unittest discover -s research/rp-001/tests -p 'test_*.py' -v
python3 research/rp-001/run_program.py --verify
```

마지막 명령은 원자료·정제자료·프로토콜·코드·trial·결과 hash, 수치 claim 추적성, terminal status, 비밀정보 검사를 모두 통과해야 exit 0을 반환한다.
