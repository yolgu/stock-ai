# RP-001 상태 온톨로지와 명칭허용 규칙

## 문서 역할과 SSOT

이 문서는 사람이 읽는 해설이다. 14개 상태 × 5개 자료 계층의 terminal 판정, 출력명, 조건, 반례와 출처 결박의 구조화 SSOT는 [state-ontology.json](state-ontology.json)이다. 서지·적용 주장·비적용 범위의 구조화 SSOT는 [source-register.json](../../dataset-contracts/DC-001-ontology-evidence/source-register.json)이다. 프로토콜은 `SP-001`, 질문은 `RQ-001`, 자료계약은 `DC-001`이며 구조화 온톨로지는 동결된 프로토콜 SHA-256에 결박되어 있다.

이 결과는 설계 전에 본 14개 1차 문헌에서 만든 개념적 명칭 계약이다. 독립 확인, 예측 성능, 경제효과 또는 거래 채택의 근거가 아니다.

## 네 층의 분리

1. 관측층은 가격, 거래량, 검색, 계좌 거래, 호가, 체결, 취소와 자기보고처럼 직접 기록된 값이다.
2. 추정층은 `price_volume_regime.*`, 상태확률과 `latent_state.k`다.
3. 구성개념층은 FOMO, 패닉, 공포, 차익실현 의도다.
4. 결정층은 매수, 매도, 헤지, 축소와 무거래다.

관측층과 추정층을 구성개념층으로 자동 승격하지 않는다. 상태는 거래를 직접 승인하지 않는다. 거래 행동은 비용·위험·불확실성을 별도로 다루는 decision layer에서만 결정한다.

## Terminal 규칙

- `identifiable`: 동시적으로 연결된 직접 측정, 독립 방법의 수렴·판별타당도, 경쟁 생성경로 분리가 모두 충족됨
- `proxy_only`: 관측이 관련 있지만 구성개념 또는 동기가 유일하지 않음
- `not_identifiable`: 직접 측정이 없거나 관측등가성이 남음

판정은 T0 심리·의도 또는 시간가용성 위반의 `not_identifiable`, 모든 직접 측정·타당도 Gate를 통과한 `identifiable`, 관련 관측이 직접 기록되지만 후보 구성개념이 유일하지 않은 `proxy_only`, 그 밖의 `not_identifiable` 순서로 상호배타 적용한다. `proxy_only`는 별도의 관측 출력만 허용하며 후보명은 `candidateNameAllowed=false`다.

같은 OHLCV를 변환한 여러 점수는 독립 방법이 아니다. 동일 OHLCV 경로는 뉴스, 유동성 충격, 리밸런싱, 숏커버링, 기계적 손절 또는 서로 다른 믿음에서 나올 수 있다. 이 대안을 외부 측정으로 구별하지 못하면 심리·의도명은 허용하지 않는다.

T0에서 FOMO 4개, 차익실현 2개, 패닉·항복 4개 후보의 구성개념·의도 terminal은 모두 `not_identifiable`이다. 같은 셀의 `price_volume_regime.*`는 허용되는 관측 출력명일 뿐 후보 심리·의도가 식별됐다는 뜻이 아니다. 비심리적 관측명인 `Normal`, `Relief`, `PostEventNormalization`은 T0에서 `proxy_only`이며, 미래경로가 필요한 `FakeRelief`는 `not_identifiable`이다.

## 결측 관측 정책

구조화 SSOT의 `missingObservationPolicy`는 `reject_no_zero_or_neutral_imputation`이다. 결측 관측을 0, neutral, baseline으로 대체하지 않는다. 빈 direct measure 또는 결측 direct measure는 Gate 실패이며 `not_identifiable`이다. 결측 항목을 제외한 뒤 남은 항목의 reweight와 renormalize를 금지한다. 이 정책은 다섯 자료 계층과 14개 상태 모두에 적용된다.

## 자료 계층

| 계층 | 관측범위 | 허용 출력 | 금지 |
| --- | --- | --- | --- |
| `T0_OHLCV` | 시점 t까지의 가격·거래량 | `price_volume_regime.*` | FOMO·패닉·차익실현 의도명 |
| `T1_AGGREGATE_ATTENTION_FLOW` | 집계 검색·뉴스노출·주체별 흐름·옵션/공매도 | `proxy.*` | 심리·동기명 |
| `T2_ORDER_BOOK` | 순서보존 호가·체결·취소와 aggressor 추론 | `observed.*`, `proxy.*` 미시구조명 | 공포·의도명 |
| `T3_ACCOUNT_POSITION` | 연결 계좌 거래·포지션·취득원가 | 직접 행동명, 계좌 `proxy.*` | 행동에서 동기 자동 추론 |
| `T4_LINKED_VALIDATED_SELF_REPORT` | 계좌·사건에 동시 연결된 검증 자기보고와 독립 행동/흐름 | Gate 통과 시 `latent_investor_state.*` | 연결·타당도 없는 자동 심리명 |

T4의 `identifiable`은 현재 코퍼스가 해당 상태를 이미 식별했다는 결과가 아니다. `contemporaneous_account_linkage`, `validated_direct_measurement`, `convergent_and_discriminant_validity`, `observational_alternatives_separated`, 단계별 시간 anchor와 label permutation 안정성을 모두 충족했을 때 FOMO·패닉·차익실현 동기에 적용할 조건부 허용규칙이다. 현재 FoMO 척도는 일반·사회적 자기보고이고, 연결 설문 연구는 월별이므로 정확한 투자자 일중 단계의 직접 검증을 대신하지 않는다. `Normal`, `Relief`, `PostEventNormalization`은 T4에서도 심리명으로 승격하지 않고 관측 가능한 기준선·반전·정상화 이름만 사용한다.

## Label permutation과 잠재상태

HMM·HSMM의 통계적 식별가능성과 구성타당도는 다른 주장이다. full-rank 전이행렬과 선형독립 방출분포는 매개변수 식별에 관한 조건이지 심리명칭의 증거가 아니다. 외부 anchor가 label permutation 뒤에도 같은 의미를 보존하고 수렴·판별타당도를 통과할 때까지 상태는 `latent_state.k`다. 사후 가격경로를 보고 상태 번호에 FOMO·패닉·차익실현 이름을 붙이지 않는다.

## 14개 상태 후보

| 상태 후보 | T0 허용명 | 필요한 직접 측정과 구별 근거 | 자료계층별 핵심 결론 | 최소 관측등가 반례 | 출처 |
| --- | --- | --- | --- | --- | --- |
| `Normal` | `price_volume_regime.baseline` | 검증 자기보고·계좌·주문장 기준선과 다른 저활동 상태의 판별 | T0~T3은 기술적 기준선이며 T4도 심리적 정상명이 아님 | 평탄한 경로는 정보부재·참여자 상쇄·거래중단 전에도 가능 | SRC-001, 002, 009, 010, 013 |
| `PreFOMO` | `price_volume_regime.pre_upside_acceleration` | 투자사건에 동시 연결된 검증 FoMO 측정과 검색·노출·계좌 매수 | T0~T3은 가격·관심·행동 프록시, T4 Gate 통과 시에만 조건부 상태명 | 완만한 상승과 관심 증가는 정보학습·리밸런싱으로도 가능 | SRC-001, 002, 003, 005, 006, 009, 010 |
| `FOMOIgnition` | `price_volume_regime.upside_breakout_onset` | 돌파 시점 FoMO 측정과 같은 계좌의 신규 매수 | T0~T3은 돌파·매수압력, T4 Gate 통과 시에만 조건부 상태명 | 돌파는 뉴스·숏커버링·얇은 호가 충격으로도 가능 | SRC-001, 002, 003, 005, 006, 009, 010, 012, 014 |
| `FOMOContinuation` | `price_volume_regime.upside_momentum_continuation` | 반복 FoMO 측정과 지속 매수·노출·검색의 연결 | T0~T3은 모멘텀·지속 매수 프록시, T4 Gate 통과 시에만 조건부 상태명 | 지속 상승은 정보확산·알고리즘 분할매수로도 가능 | SRC-001, 002, 003, 005, 006, 009, 010, 012, 014 |
| `FOMOExhaustion` | `price_volume_regime.upside_momentum_exhaustion` | FoMO 측정 감소·포화와 매수감속·주문장 압력 소진 | T0~T3은 상승압력 약화 프록시, T4 Gate 통과 시에만 조건부 상태명 | 상승 둔화는 시간대 유동성 감소·대형 매도로도 가능 | SRC-001, 002, 003, 005, 006, 009, 010, 012, 014 |
| `PotentialProfitTaking` | `price_volume_regime.post_rally_sell_risk` | 계좌 취득원가·미실현 이익과 동시 매도 의도 | T1은 `proxy.aggregate.post_rally_sell_risk`; 취득원가가 있는 T3만 `proxy.unrealized_gain_overhang`; T4 Gate 전 동기명 금지 | 매도 위험은 리밸런싱·현금수요·위험한도 축소로도 증가 | SRC-001, 002, 004, 006, 008, 009, 010 |
| `RealizedProfitTaking` | `price_volume_regime.post_rally_sell_flow` | 계좌 매도·취득원가와 동시 차익실현 동기 | T3은 `observed.realized_gain_sale`만 식별하며 동기는 T4 Gate가 필요 | 실현이익 매도는 현금수요·리밸런싱·위험관리로도 가능 | SRC-001, 002, 004, 006, 008, 009, 010, 011, 012 |
| `PrePanic` | `price_volume_regime.pre_downside_stress` | 사건 연결 불안·패닉 측정, 계좌 매도 의도와 주문장 스트레스 | T0~T3은 하락 전 스트레스 프록시, T4 Gate 통과 시에만 조건부 상태명 | 하락 전 스트레스는 공시·헤지 재조정·유동성 축소로도 가능 | SRC-001, 002, 007, 008, 009, 010, 012, 013, 014 |
| `PanicOnset` | `price_volume_regime.downside_dislocation_onset` | 하락 시작의 패닉 측정과 같은 계좌 긴급 매도 | T0~T3은 하락·매도압력 시작, T4 Gate 통과 시에만 조건부 상태명 | 급락 시작은 새 정보·기계적 손절·강제청산으로도 가능 | SRC-001, 002, 007, 008, 009, 010, 011, 012, 013, 014 |
| `ActivePanic` | `price_volume_regime.high_intensity_selloff` | 반복 패닉 측정과 지속 긴급 매도·취소·체결 흐름 | T0~T3은 고강도 매도 관측, T4 Gate 통과 시에만 조건부 상태명 | 지속 매도는 지수 리밸런싱·델타헤지·기관 분할청산으로도 가능 | SRC-001, 002, 007, 008, 009, 010, 011, 012, 013, 014 |
| `Capitulation` | `price_volume_regime.selloff_climax` | 검증 포기·극심 공포 측정과 강제/재량 청산 구분 | T0~T3은 매도절정·청산 행동, T4 Gate 통과 시에만 조건부 상태명 | 매도절정은 강제청산·옵션 만기·단일 대형 주문으로도 가능 | SRC-001, 002, 007, 008, 009, 010, 011, 012, 013, 014 |
| `Relief` | `price_volume_regime.selloff_reversal` | 자기보고와 계좌 매도중단·재진입·호가압력 반전을 분리해 기록 | 모든 계층에서 관측 가능한 반전명만 허용하고 안도 심리명으로 승격하지 않음 | 반전은 숏커버링·유동성 복귀·기계적 평균회귀로도 가능 | SRC-001, 002, 007, 008, 009, 010, 011, 012 |
| `FakeRelief` | `price_volume_regime.failed_rebound` | 향후 적용 study가 창·threshold를 사전등록한 뒤에만 반등 실패를 사후 확인 | 미래 경로로만 판정하는 사후 결과명이며 현재는 `not_identifiable`; 모든 계층에서 retrospective-only, 시점 t 입력 금지 | 시점 t 반등은 지속 반전과 실패 반등이 동일하게 보임 | SRC-001, 002, 007, 008, 009, 010, 012, 014 |
| `PostEventNormalization` | `price_volume_regime.post_event_normalization` | 가격·거래량·주문장·계좌·자기보고가 사전 기준선으로 회복 | 기술적 정상화이며 심리적 정상 상태명으로 승격하지 않음 | 저변동·저거래는 참여자 이탈·거래중단·표본종료로도 가능 | SRC-001, 002, 007, 008, 009, 010, 013 |

## 출처와 적용 한계

아래 링크는 `source-register.json`의 14개 1차 문헌 공식 경로다. 각 문헌의 적용 주장과 비적용 범위는 구조화 원장에 함께 기록되어 있다.

1. Cronbach & Meehl, 구성타당도: [Construct Validity in Psychological Tests](https://doi.org/10.1037/h0040957). 시장 상태 또는 단계 시계를 검증한 연구는 아니다.
2. Campbell & Fiske, 수렴·판별타당도: [Multitrait-Multimethod Matrix](https://doi.org/10.1037/h0046016). 같은 가격 파생점수를 독립 방법으로 만들지 않는다.
3. Przybylski et al., 일반·사회적 FoMO 자기보고: [Fear of Missing Out](https://doi.org/10.1016/j.chb.2013.02.014). 투자자·고빈도 상태척도가 아니다.
4. Odean, 계좌 거래와 취득원가: [Are Investors Reluctant to Realize Their Losses?](https://doi.org/10.1111/0022-1082.00072). 실현이익 매도는 동기를 유일하게 식별하지 않는다.
5. Da, Engelberg & Gao, 검색 관심: [In Search of Attention](https://doi.org/10.1111/j.1540-6261.2011.01679.x). 검색은 관심 프록시이며 FOMO·매수의도 측정이 아니다.
6. Barber & Odean, 관심 프록시와 계좌 행동: [All That Glitters](https://doi.org/10.1093/rfs/hhm079). 뉴스·거래량·극단수익은 동기명이 아니다.
7. Shiller, 사건 설문: [NBER Working Paper 2446](https://www.nber.org/papers/w2446). 가격의 충분통계성이나 정확한 단계 시계를 주지 않는다.
8. Hoffmann, Post & Pennings, 월별 연결 설문·계좌: [Individual Investor Perceptions and Behavior During the Financial Crisis](https://doi.org/10.1016/j.jbankfin.2012.08.007). 일중 패닉·FOMO를 직접 식별하지 않는다.
9. Allman, Matias & Rhodes, 잠재구조 식별: [arXiv 0809.5032](https://arxiv.org/abs/0809.5032). 상태 순열이 남고 심리 의미를 정하지 않는다.
10. Gassiat, Cleynen & Robin, 비모수 HMM 식별: [Inference in finite state space non parametric Hidden Markov Models and applications](https://link.springer.com/article/10.1007/s11222-014-9523-8). full-rank·선형독립 조건은 구성개념 명칭 규칙이 아니다.
11. Lee & Ready, trade direction 추론: [Inferring Trade Direction from Intraday Data](https://doi.org/10.1111/j.1540-6261.1991.tb02683.x). 추론값은 실제 의도·정서가 아니다.
12. Cont, Kukanov & Stoikov, OFI와 가격영향: [arXiv 1011.6402](https://arxiv.org/abs/1011.6402). queue 압력은 공포가 아니며 Level I 관측등가성이 남는다.
13. Huang, Lehalle & Rosenbaum, queue-reactive 주문장: [arXiv 1312.0563](https://arxiv.org/abs/1312.0563). queue·depth·spread는 물리상태이지 심리가 아니다.
14. Bacry, Jaisson & Muzy, Hawkes event excitation: [arXiv 1412.7096](https://arxiv.org/abs/1412.7096). 모형 endogeneity는 구조 인과나 인간 의도를 증명하지 않는다.

## 결정층 금지

각 구조화 상태 행에는 `no_state_directly_authorizes_trade`가 있다. 특히 `FakeRelief`에는 `never_use_fake_relief_as_time_t_input`이 추가된다. 온톨로지는 명칭허용 경계만 정하며 매수·매도·헤지·축소·무거래를 선택하지 않는다.
