# RP-001 SG0–SG2 Foundation 자체감사

## 결론

SG0–SG2의 요구사항 등록·연구객체 사슬·자료 및 명칭 경계는 구조적으로 검증됐지만, 실증 실행·terminal 판정·공식 채택 근거는 아직 없으므로 RP-001은 완료가 아니며 현재 운영 결정은 `NoTrade/no integration`이다.

이 보고서는 foundation의 구조 완전성과 다음 단계의 차단조건을 감사한다. 수익 공식의 성능, 외부 재현 또는 채택을 주장하지 않는다. 시장자료, credential 값, 토큰, `.storage`, `research/indicator-validation`의 data/raw/results/run-manifest, RB-001 실행 파일은 읽거나 실행하거나 수정하지 않았다.

## 1. 감사 범위와 판정어

현재 `RP-001` descriptor는 `proposed / conceptual`이다. 이 보고서의 Gate disposition은 다음 뜻으로만 사용한다.

| disposition | 뜻 |
| --- | --- |
| `foundation_only` | 경계·질문·반례 같은 기반 artifact가 있으나 공식 채택 Gate를 통과했다는 뜻은 아님 |
| `pass_contract` | 단일 estimand·horizon 등 구조 계약이 validator를 통과했으나 경험적 성과는 아직 평가하지 않음 |
| `partial_contract` | 일부 객체만 사전등록됐거나 다음 승격 전 고정항목이 남아 있음 |
| `blocked` | 자료·권리·계보 또는 upstream Gate가 충족될 때까지 실행 금지 |
| `not_started` | 적격 ExperimentRun과 해당 Gate의 EvidenceBundle이 없음 |

`sourceRequirementCoverage=1.00`은 요구사항을 질문·study에 등록한 비율이다. Goal 종료조건의 `RequirementCoverage`는 evidence·decision·report까지 연결된 비율이므로 같은 지표가 아니다. 구조 validator도 연구결론의 참·거짓이나 통계적 타당성을 판정하지 않는다. 검증 근거는 [V-FOUND], [V-TRACE], [V-CAT]이다.

## 2. Goal provenance

| 역할 | 경로 | SHA-256 | bytes | newline / logical lines |
| --- | --- | --- | ---: | ---: |
| active user objective | `/Users/jik/.codex/attachments/a2f9a4f6-4da6-458c-a12a-98f2c5b2df37/goal-objective.md` | `089ee3236ad913388106d0b569cc931e451d6be661c55ee62c2993f093afaad3` | 13,876 | 391 / 392 |
| superseded user objective | `/Users/jik/.codex/attachments/6023f4bd-b626-4150-9e9a-ae7668667509/goal-objective.md` | `ed12fa8ca34644e95b2591b1ac1e0e310420eb0092866454289b011453089e3a` | 13,875 | 391 / 392 |
| repository canonical copy | `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/goal-v1.0.md` | `542160cbad66426db09eb8ec6741c48464a9d80a3a6be2fd71ab1871f8f55594` | 13,876 | 392 / 392 |

세 행의 값은 `shasum`, `wc`, final-byte 검사로 재계산했다. superseded와 active의 차이는 논리 41행의 whitespace-only 공백 1자뿐이다. active와 canonical의 차이는 그 공백 정규화와 canonical의 final LF뿐이다. 규범 문장·순서·392개 논리 행에는 의미 변경이 없다. `requirements.json.sourceSha256`은 active hash를 가리킨다. 검증 근거는 [V-GOAL]이다.

## 3. Foundation 구조

### 3.1 요구사항과 추적성

- `requirements.json`에는 고유하고 순차적인 요구사항 254개가 있다. SHA-256은 `852a8efa16be0554856aea2d6dd5cb0230bb112e96a36bac6543406a2622917e`다. [V-FOUND]
- 254/254 행에 `questionIds`와 `studySlots`가 있어 `sourceRequirementCoverage=1.00`이다. [V-FOUND] [V-TRACE]
- evidence·decision·report가 모두 비어 있지 않은 행은 0/254다. 따라서 Goal 의미의 현재 최종 `RequirementCoverage`는 `0.00`이며, foundation 등록 coverage `1.00`을 연구 완료로 해석하면 안 된다. [V-TRACE]
- study slot은 8/8, 필수 candidate family는 11/11로 foundation coverage가 각각 `1.00`이다. [V-FOUND]
- 상태 온톨로지는 14개 상태 × 5개 자료계층 = 70개 판정 셀을 가지며 T0 심리·의도 명칭 허용 수는 0이다. 이는 명칭 경계의 개념적 완결성이지 예측 성과가 아니다. [V-ONTOLOGY]

### 3.2 Catalog와 객체 그래프

meta validator의 현재 결과는 `objects=30`, `dependencies=46`, `artifacts=70`, `catalogCoverage=1.00`이다. 중앙 객체 그래프 projection SHA-256 pin은 `228a4cb3b47b78e926b0a42eef8ac9d5ba5279052785f9280fbb56b59d5eb0a0`이다. 객체·의존성·artifact 수는 구조 완전성 지표이며 과학적 증거 수가 아니다. [V-CAT]

### 3.3 Candidate family 등록

등록된 11개 family는 다음과 같다. [V-CANDIDATE]

```text
unconditional
simple_price_volume
legacy_weighted_sum
repair_candidate
bayesian_competing_risk
hmm_hsmm
dynamic_relative_value
prospect_reference_price
ofi_depth_hawkes
execution_control
nonlinear
```

이 중 `bayesian_competing_risk`만 `MC-001 / object_registered`이고 나머지 10개는 `registry_only`다. `registry_only`는 실행 가능한 후보 ID나 구현이 존재한다는 뜻이 아니다. [V-CANDIDATE]

## 4. Study 계약과 실행 상태

### 4.1 여덟 계약 사슬

| study | RQ / DC / SP | descriptor lifecycle | protocol SHA-256 | run / terminal | 현재 실행 disposition |
| --- | --- | --- | --- | --- | --- |
| `ST-ONT-001` | `RQ-001 / DC-001 / SP-001` | `completed / completed / preregistered` | `a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e` | `runs=[]`; study terminal 미할당 | conceptual 명칭 계약만 존재; 경험적 실행 없음 |
| `ST-DAT-001` | `RQ-002 / DC-002 / SP-002` | `completed / completed / preregistered` | `bbdf0603b55a5b3b18dd20cdc7f2f0161b47dffb35edeffd39026f464fe29a7e` | `runs=[]`; study terminal 미할당 | 문서·권리 감사만 존재; live collection 차단 |
| `ST-BEH-001` | `RQ-003 / DC-003 / SP-003` | `proposed / proposed / proposed` | `2c6a92f319f7a4c1150c31c2bf3dae948504d60399c2314d3a79815446555a5c` | `runs=[]`; terminal 미할당 | `block_human_behavior_claim`; 자료 Gate 뒤 price-volume 연구만 research-only 가능 |
| `ST-VAL-001` | `RQ-004 / DC-004 / SP-004` | `proposed / proposed / proposed` | `59e87a90f507dc4d54de8c1cc307c144a6d8b2a10fe1c0d76000b2a19ad18f25` | `runs=[]`; terminal 미할당 | `block_confirmatory_VAL` |
| `ST-MIC-001` | `RQ-005 / DC-005 / SP-005` | `proposed / proposed / proposed` | `2fc7865e4904198a20e68238c912b38883d08e1385f240c03eb174983e4c9ca3` | `runs=[]`; terminal 미할당 | `block_MIC_execution` |
| `ST-EXE-001` | `RQ-006 / DC-006 / SP-006` | `proposed / proposed / proposed` | `95f1ff3da6020a24238fb32a39d799bd3c54d379e53bd81ea3bb9d8dbfb6849d` | `runs=[]`; terminal 미할당 | `NoTrade; prohibit_operational_adoption` |
| `ST-RSK-001` | `RQ-007 / DC-007 / SP-007` | `proposed / proposed / proposed` | `b867c51f314ef7e30020b93245cd7d4a6b9f04029f9cfa20793077b0765410ac` | `runs=[]`; terminal 미할당 | `NoTrade`; upstream OOF·비용·위험계수 전부 미수락 |
| `ST-SYN-001` | `RQ-008 / DC-008 / SP-008` | `proposed / proposed / proposed` | `08e7b13e55ebd86879ca2efc2e0376b7906ccdc3f9cd13dbe3093fba8c4eed9d` | `runs=[]`; terminal 미할당 | `no_integration; NoTrade` |

RQ-001의 70개 ontology cell 판정과 RQ-002의 availability/identifiability matrix는 study-level terminal status가 아니다. 모든 ledger가 비어 있으므로 8개 study 모두 `supported/refuted/...` 중 어느 terminal도 할당되지 않았다. [V-STUDY] [V-LIFECYCLE]

### 4.2 Task 7 portfolio 무결성

`study-contracts.json`의 SHA-256은 `c9a73212bdb4dc4bc79dc2fcec1c6b2ffdb5ff23a1879d266ea9d8d1227a9994`다. 이 portfolio는 아래 6개 proposed study의 RQ/DC/SP 문서 18개를 결박한다. 각 SP document hash는 `protocol.sha256` 및 빈 trial ledger의 hash와 일치한다. [V-STUDY]

| study | RQ document SHA-256 | DC document SHA-256 | SP document / protocol SHA-256 |
| --- | --- | --- | --- |
| `ST-BEH-001` | `57324534df8f6ffc6b80b9fad27e94b7eec1ab47b653d4df46e391391e8ecfcd` | `7bf0663c2f9b92a35065ccfbe882f15631d2095f0bc890764bae6e3b1cc068b4` | `2c6a92f319f7a4c1150c31c2bf3dae948504d60399c2314d3a79815446555a5c` |
| `ST-VAL-001` | `9aac1b18a92f1af5fffefd0b3aa4e82bed74531322539bfa676c2bd576da2948` | `d85a70d99499eb7a61349996e24ed3035bb6ac92aa5a0972d8a76e6411294613` | `59e87a90f507dc4d54de8c1cc307c144a6d8b2a10fe1c0d76000b2a19ad18f25` |
| `ST-MIC-001` | `8d80340d53a4bd72b7cd812c90b62bffcddea9b08ec5f8fb7eee8038d4ec4189` | `beb8bb187e359eb9b1cb3730f6d173556ce302ad6fe35a1b80c2a9f4402c1b96` | `2fc7865e4904198a20e68238c912b38883d08e1385f240c03eb174983e4c9ca3` |
| `ST-EXE-001` | `b2e6f745e4c4436fd8d41211629bbb91933317f45f87f3c6e9d169f7c9b3b2a8` | `a9d964023941db597fbf843f57c701ed53466b807913c1b6d7a55d10d67aadc8` | `95f1ff3da6020a24238fb32a39d799bd3c54d379e53bd81ea3bb9d8dbfb6849d` |
| `ST-RSK-001` | `d676d48bcecc5d2aaf8557940c2fb10ae06b9d5f81bbfc6c450b0e07b9a9270a` | `5ea3278a669a4981e6d760f4345d43552cd0e9f080513d90ea133339954a89f0` | `b867c51f314ef7e30020b93245cd7d4a6b9f04029f9cfa20793077b0765410ac` |
| `ST-SYN-001` | `4b2dab1bd2ccf4277b71da3126c7d7adf0de07392e516bccd1e327d26a351044` | `ec96880161827b1f34af1bc099d16f70c59fd37cc6c8fcf2d41592233bda0dfa` | `08e7b13e55ebd86879ca2efc2e0376b7906ccdc3f9cd13dbe3093fba8c4eed9d` |

## 5. RB-001 경계

이 감사는 RB-001 파일을 재실행하거나 직접 검증하지 않았다. 아래 값은 등록된 `EB-001`과 `DR-001`만 다시 읽은 결과다. “변경 없음”은 이번 foundation 감사가 RB-001을 수정하지 않았다는 뜻이며, 역사적 세 snapshot이 동일했다는 뜻이 아니다. [EB-001] [DR-001]

| 관찰 phase | run manifest SHA-256 | bound runner SHA-256 | 등록 판정 |
| --- | --- | --- | --- |
| initial audit | `09e2ddf1e9acb3dbf54336ea5265a737ebba4a702dce61cdd194f4827a260eda` | `1e6d5d4053f61fdb4d3af17848658c8a0942880774c8c7f33d7e5f6f0bd12d2a` | `failed_input_hash_mismatch` |
| first rebind observed | `90e6e3ac59bf408b609fc5a5422a763a090e47c5578f9b0419a957814b93415f` | `b625d724d8363b2d5d74a25b698e7911787d01dfcb5b7b5c41c392b3a748851b` | `self_consistent_after_rebind` |
| current registered snapshot | `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e` | `f906fd61b9b55e2e264adae032517151f9ee7ed24b8804ab878e102944736708` | `current_snapshot_self_consistent` |

`generationLineageVerified=false`다. 현재 self-consistency는 원래 동결 생성 계보나 독립 재현을 증명하지 않는다. `DR-001`의 결정은 `research_only`, 운영 사용 금지이며 failure reproduction, prohibited-condition 설계, seen-development-data 경계 식별에만 허용한다. `boundary-contract.json`은 RB-001에 대해 G0과 G9를 모두 `not_passed`로 고정한다. [EB-001] [DR-001]

## 6. 데이터·credential 경계

`source-matrix.json` SHA-256은 `f411dac963717aa7ed8ea1d5351ccbed70987150f6ca0e9a608d54f7677e9e61`, 공식 문서 원장은 `fe976ecd724a3a5f9e81d20804ba823a58c98d4ef1db9d1911e1cae4b4f3412d`다. [V-DATA]

대화에서 credential이 plaintext로 공개됐다는 사실은 기록됐지만 값은 artifact·로그·명령에 복사하거나 저장하지 않았다. local credential file의 contents 및 file-origin 값은 읽지 않았고 live API도 호출하지 않았다. 공개된 값은 compromised로 분류되어 rotation 전 사용 금지다. 현재 live gate는 정확히 다음과 같다. [V-DATA]

```text
blocked_pending_rotated_credentials_and_provider_retention_clarification
```

provider의 local internal research, local retention/cache, derived publication 범위는 `not_documented`, `legalConclusion=null`이다. 회전된 credential, provider clarification, raw/processed 별도 hash와 수신시각, 단위·세션·revision 검증, secret scan이 모두 충족되기 전에는 수집·저장·처리를 시작하지 않는다. 이 차단을 0, neutral, 대체 endpoint, reweight 또는 renormalize로 우회하지 않는다. [V-DATA]

## 7. G0–G10 disposition

아래 disposition은 프로그램 전체의 현재 상태다. `pass_contract`도 채택 Gate의 경험적 통과를 뜻하지 않는다. Gate 정의는 [GATE], study 계약은 [V-STUDY], RB 경계는 [DR-001]에 근거한다.

| Gate | 현재 disposition | 근거와 미충족 조건 |
| --- | --- | --- |
| G0 기존 연구와 버전 격리 | `foundation_only` | 새 RP 객체·catalog·seen-data 경계는 분리됐지만 `DR-001`은 RB-001 원래 생성계보 미입증으로 G0를 `not_passed`로 둔다. |
| G1 질문·estimand·horizon | `pass_contract` | 8개 RQ 사슬이 등록되고 단일 주요 estimand·horizon 계약을 가진다. 구조 통과일 뿐 결과는 없다. |
| G2 관측과 상태 식별 | `foundation_only` | 14×5 ontology와 반례가 있다. T0 심리명칭은 0개이며 direct measure 없는 심리·의도는 `not_identifiable`; 경험적 상태 구별은 미실행이다. |
| G3 자료 계보·단위·가용시점 | `blocked` | 8개 DC는 있으나 accepted raw/processed manifest가 없고 live gate와 여러 필수 입력군이 차단 상태다. |
| G4 사전등록 동결 | `partial_contract` | SP-001·SP-002만 `preregistered`; SP-003~SP-008은 hash가 있어도 lifecycle `proposed`여서 실행 가능한 사전등록이 아니다. |
| G5 수학·구현 등가성 | `not_started` | RP 후보별 독립 reference·구현 mapping·경계/단위/인과성 테스트가 없고 SG3 P0–P4가 남아 있다. |
| G6 내부 OOF 최소효과 | `not_started` | 적격 run, OOF prediction, 최소효과 판정 EvidenceBundle이 없다. |
| G7 외부·전향표본 | `not_started` | unseen/prospective 봉인표본 run과 외부 실패·성공 EvidenceBundle이 없다. |
| G8 비용·체결·시장충격·CVaR | `blocked` | EXE·RSK 자료와 run이 없고 운영계약은 `NoTrade`다. |
| G9 독립 실행자 재현 | `not_started` | RP artifact reproduction record가 없다. RB-001의 self-consistency는 독립재현이 아니며 `DR-001`의 G9는 `not_passed`다. |
| G10 독립 OOF 통합 증분 | `blocked` | 적격 upstream external OOF, EXE cost, RSK output이 없어 통합 금지이며 `NoTrade`다. |

어느 Gate도 다른 Gate의 초과성과로 상쇄할 수 없다. 현재 채택·조건부 채택 후보는 없다.

## 8. SG3 진입 전 formula inventory와 P0–P4 gap

### 8.1 등록된 역사적 inventory의 범위

RB 계열의 기존 탐지 범위 formula ledger는 수식·변형 224개를 `valid 18`, `repairable 32`, `proxy_only 74`, `not_identifiable 70`, `reject 30`으로 분류한다. 이 합은 224다. 이는 역사적 수학·프록시 판정이며 `valid`가 RP-001의 G5–G10 또는 채택을 통과했다는 뜻은 아니다. [V-FORMULA]

기존 RB 후보는 19개다. 보고된 12개 거래량 의존 후보는 분할구간의 거래량 단위 계약 때문에 비교 불가였고, 나머지 7개는 산술적으로 가격 전용 후보군이다. 전체 650개 stage×trial metric 행 중 `evaluated`는 11개였고 유의한 시험은 0개였다. 이와 별도로 MU·SK하이닉스의 각 120일 holdout에서는 가격 전용 50개 trial이 모두 `insufficient_evidence`였고 평가 완료 trial은 각각 0개였다. 각 holdout의 나머지 거래량 의존 80개 trial은 `calibration_unavailable`이었다. 따라서 19개 중 RP-001에 채택 가능한 경험적 공식은 현재 0개다. 이 결론은 `DR-001` 경계상 adoption evidence로 재사용하는 것이 아니라 SG3에서 다시 해결해야 할 defect inventory로만 보존한다. [V-FORMULA] [DR-001]

### 8.2 P0–P4

| 우선순위 | 미충족 계약 | SG3에서 필요한 종료 증거 |
| --- | --- | --- |
| P0 실행 가능성 | 10개 `registry_only` family에는 concrete candidate ID·구현 binding·필수 입력·단위 계약이 없다. 문서 `PotentialPTP`와 앱 내부 합성 경로는 동치가 아니며, 상대가치의 mean-reversion/momentum 양방향도 실행 후보로 구체화되지 않았다. 수학적 `valid`와 채택상태도 분리해야 한다. | candidate별 immutable ID/version, math/input/unit/schema, implementation symbol, eligible study/fold, status를 가진 closed-world registry; 누락·phantom mapping 거부 테스트 |
| P1 reference/equivalence | 기존 보고도 독립 reference 수치계산이 문서 composite 3개와 production 일부뿐이며 224식 전체 삼자 실행은 아니라고 명시한다. | 19개 실행 후보 각각의 독립 reference, production/research 양방향 mapping, exact·tolerance equivalence, 비동치 terminal 판정 |
| P2 metamorphic | 가격척도·통화·split, 결측/OOD, 입력순서·중복 timestamp, 미래행 불변성 반례가 남아 있다. | candidate별 scale/currency/split metamorphic test, 결측 무대체, future-row invariance, 정의역·경계·단조성 증명/반례 |
| P3 보상해킹·trial disclosure | 숨은 하한, 결측 0·재가중, 도달불가 분기, 결과선택 위험이 기록돼 있으나 RP trial ledger는 전부 비어 있다. | candidate×horizon×fold×seed와 run의 전단사, 동일 eligibility mask, 모든 실패·무효 run 보존, terminal holdout 후 tuning 금지 검증 |
| P4 HSMM·경쟁위험 | `MC-001`은 `proposed/conceptual`이며 duration, label switching, filtering/smoothing, CIF 질량, ordered-data 결측 계약을 아직 실행 검증하지 않았다. | filtering `P(z_t\|I_t)` 전용 운영출력, duration/self-transition 중복 금지, CIF+survival 질량 보존, 합성 상태·매개변수 회복, label anchor 안정성, OFI/depth 무대체 검증 |

P0–P4는 SG3 계획의 입력이며 이 foundation 보고서가 해결했다고 간주하지 않는다. [V-FORMULA] [V-MC]

## 9. 독립 검토의 유지보수 위험

아래 두 항목은 `independent_review_note`이며 formal EvidenceBundle이 아니다. 현재 correctness 실패가 아니라 향후 합법적 변경 때 의미 검토가 약화될 수 있는 유지보수 위험이다.

1. Task 7 final review의 Minor: `test_study_contracts.py`는 `EXPECTED_PORTFOLIO_SHA256`, 전체 `expected_record` 동등성, raw document SHA에 강하게 의존한다. 현재 변이를 막지만 정당한 pin 갱신 때 동의어 형태의 의미 모순을 별도 normative-rule ID나 semantic review로 재확인해야 한다. 실행 가능한 근거는 `test_rejects_five_normative_body_mutations`, `_assert_document_projection`, `_assert_portfolio_record`다. [V-REVIEW]
2. Task 8 final review의 Minor: 동일한 30개 descriptor path snapshot이 `test_ontology_contract.py`와 `test_data_lineage_contract.py`에 중복되어 객체 추가 때 오래된 Task 5/6 test도 함께 바꿔야 한다. 중앙 graph oracle과 SHA pin이 correctness를 보완하지만 snapshot SSOT 중복은 유지보수 비용이다. [V-REVIEW]

## 10. 현재 완료가 아닌 이유와 다음 증거조건

현재 연구를 완료로 표시할 수 없는 직접 이유는 다음과 같다.

- 최종 evidence·decision·report 추적은 0/254이고 source 등록만 254/254다. [V-TRACE]
- 8개 study ledger가 모두 `runs=[]`이며 terminal status가 모두 미할당이다. [V-STUDY]
- 6개 실증 프로토콜은 `proposed`; SP-001·SP-002도 conceptual 사전등록일 뿐 예측·경제성 결과가 없다. [V-LIFECYCLE]
- G3은 live 권리·계보·단위 Gate로 차단되고 G5–G10 EvidenceBundle이 없다. [V-DATA] [GATE]
- 실제 데이터 반복 시행, 성공·실패 확률분포, 사건·국면 성과, 비용·체결·시장충격·CVaR, 외부표본과 독립 재현이 없다. [V-TRACE] [V-STUDY]
- 최종 채택/기각/not-identifiable DecisionRecord와 전체 재현 명령이 없다. catalog의 유일한 DecisionRecord인 DR-001은 RB 경계 결정일 뿐 프로그램 최종결정이 아니다. [V-CAT] [DR-001]

다음 단계는 아래 증거조건을 순서대로 충족해야 한다.

1. SG3 P0 closed-world candidate registry와 수학·구현·입력·단위 mapping을 동결한다.
2. P1–P4 reference, metamorphic, reward-hacking, HSMM/CIF 테스트를 RED→GREEN으로 만들고 실패 후보도 보존한다.
3. credential 회전과 provider clarification 뒤에만 accepted raw/processed lineage를 만들고, 각 해당 SP를 별도 version으로 `preregistered` 승격한다.
4. candidate·seed·fold·horizon·eligibility·실패 원인을 모든 trial ledger에 append-only 기록한다.
5. 내부 OOF, unseen/prospective 외부표본, 비용·체결·tail-risk Gate를 순서대로 판정한다.
6. 다른 실행자가 hash-bound artifact를 재현한 뒤에만 독립 OOF 통합을 평가한다.
7. 254개 요구사항을 EvidenceBundle·DecisionRecord·최종 보고서에 연결하고, 채택 후보가 없으면 `no_adoptable_formula` 또는 관측 불가 범위의 `not_identifiable`을 재현 가능하게 증명한다.

## 11. 검증 참조

아래 `V-*`는 이 감사의 재계산 참조이며 formal EvidenceBundle ID가 아니다.

- **[V-GOAL]** 세 Goal 경로에 대한 `shasum -a 256`, `wc -c -l`, final-byte `od`, `diff -u`; canonical 결박 검사는 `research/rp-001/src/rp001/program_contract.py`와 `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/requirements.json`.
- **[V-FOUND]** `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/{requirements.json,study-registry.json,candidate-registry.json}` 및 `research/rp-001/run_program.py --verify-foundation`.
- **[V-TRACE]** `traceability.json`의 총행, question/study 비어있지 않은 행, evidence/decision/report 모두 비어있지 않은 행을 strict JSON으로 재집계.
- **[V-CAT]** `research/meta-research/tools/validate_research_program.py`, `research/meta-research/catalog/research-objects.json`, `research/meta-research/tools/test_validate_research_program.py::test_repository_graph_matches_centralized_traceability_oracle`.
- **[V-CANDIDATE]** `research/meta-research/objects/programs/RP-001-quantitative-market-behavior/candidate-registry.json`.
- **[V-ONTOLOGY]** `state-ontology.json`의 `stateCandidates`, `measurementTiers`, `allowedOutputsByTier`, `t0PsychologicalOrIntentNameCount`; SHA-256 `4e11c9c3a754d542759a0e27f43d9181fa749920a41566a67895c49a71cbcaac`.
- **[V-STUDY]** `study-registry.json`, `study-contracts.json`, RQ-003~RQ-008, DC-003~DC-008, SP-001~SP-008의 document SHA 재계산, 모든 `research/rp-001/trials/ST-*.json`의 protocol binding과 `runs` 길이 검사.
- **[V-LIFECYCLE]** RQ-001~RQ-008, DC-001~DC-008, SP-001~SP-008의 `object.json` lifecycle/evidenceLevel과 각 본문의 현재 실행 disposition.
- **[EB-001]** `research/meta-research/objects/evidence-bundles/EB-001-rb001-integrity-audit/{evidence.md,integrity-observations.json}`.
- **[DR-001]** `research/meta-research/objects/decision-records/DR-001-rb001-boundary/{decision.md,boundary-contract.json}`.
- **[V-DATA]** `DC-002/data-contract.md`, `DC-002/official-source-register.json`, `SP-002/protocol.md`, `source-matrix.json`, `source-matrix.md`.
- **[GATE]** `research/meta-research/governance/lifecycle-and-evidence-gates.md`, `measurement-and-quality-model.md`, `document-management-policy.md`.
- **[V-FORMULA]** `docs/codex/research/2026-07-10-mania-panic-fomo-formula-final-report.md`, `2026-07-10-formula-ledger-and-equivalence.md`, `2026-07-10-formula-mathematical-audit.md`. 기존 RB 결과는 DR-001 경계 때문에 채택 증거가 아니라 gap inventory로만 인용한다.
- **[V-MC]** `research/meta-research/objects/model-candidates/MC-001-bayesian-hsmm-competing-risks/README.md`와 `docs/codex/research/2026-07-10-bayesian-hsmm-competing-risks-framework.md`.
- **[V-REVIEW]** `research/rp-001/tests/test_study_contracts.py`, `test_ontology_contract.py`, `test_data_lineage_contract.py`, 중앙 graph oracle test. 독립 검토 메모 자체는 EvidenceBundle로 표시하지 않는다.
