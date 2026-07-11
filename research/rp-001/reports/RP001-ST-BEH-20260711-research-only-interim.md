# RP-001 ST-BEH-001 연구용 중간결과

작성 시각: 2026-07-11T01:55:26Z  
결정 범위: `research_only`  
운영 처분: `NoTrade/no integration`

## 1. 한 문장 결론

보지 않은 6종목의 2023-01-03~2026-06-30 일봉 5,250행을 동결된 규칙으로 평가한 결과, 채택 가능한 공식은 없으며 SF는 `proxy_only + insufficient_evidence`, SP·ST·SR은 `proxy_only + reject`, 모든 후보의 source-vintage point-in-time 채택 Gate는 `not_identifiable`이다.

## 2. 표본과 동결 규칙

- 종목: AMZN, CAT, XOM, AAPL, AMD, COST
- 종목별 공통 세션: 875개, 총 분석행 5,250개
- 후보: 3개 family, 4개 head(SF, SP, ST, SR)
- 대조군: B1 Jeffreys constant, B2 directional-shock bins
- 목표: 10거래일 upside/downside price-volume continuation
- 개발 검증: expanding train, 63-session validation, purge 10, embargo 10
- terminal holdout: 126 sessions, pre-holdout mapping 1회 고정
- 후보 선택 문맥: `selected_from_multiple_candidates`
- 최소 Brier 개선량: `δ = 0.005`
- 경보 threshold: `0.5`
- bootstrap: synchronized moving block, block 20, 2,000회, seed 20260710
- 비용 민감도: 왕복 100 bps와 300 bps

실제 세션 수가 최소 607보다 많아 개발 OOF 6개와 terminal holdout 1개가 생성됐고, 4개 head에 대해 총 28개 평가가 수행됐다.

## 3. terminal holdout 예측 성능

`ΔBrier = Brier(best baseline) - Brier(candidate)`이며 양수가 개선이다. 모든 terminal 평가에서 최선 대조군은 B2였다. 아래 95% 구간은 다중선택 보정 전의 사전등록 moving-block bootstrap 구간이므로 기술적 근거이며 채택 근거가 아니다.

| Head | 가격·거래량 proxy | 행 | Candidate Brier | B2 Brier | ΔBrier | 95% 구간 | 등록 판정 | 중간 처분 |
|---|---|---:|---:|---:|---:|---:|---|---|
| SF | 상승 지속 proxy | 694 | 0.225591 | 0.227755 | +0.002164 | [0.000371, 0.006156] | insufficient_evidence | proxy_only |
| SP | 하락 지속 proxy | 694 | 0.137555 | 0.137209 | -0.000346 | [-0.000931, 0.000220] | does_not_meet_delta_selection_adjustment_required | reject |
| ST | 상승 후 하락반전 proxy | 691 | 0.136678 | 0.136745 | +0.000067 | [-0.000772, 0.000760] | does_not_meet_delta_selection_adjustment_required | reject |
| SR | 하락 후 상승반전 proxy | 692 | 0.229030 | 0.227585 | -0.001445 | [-0.005071, 0.003981] | does_not_meet_delta_selection_adjustment_required | reject |

SF의 관측 개선은 δ=0.005보다 작고 구간이 δ를 가로지르므로 성공으로 판정할 수 없다. SP·ST·SR의 구간 상한은 δ 이하이므로 현 버전 후보는 최소효과 Gate를 통과하지 못한다.

| Head | Candidate log loss | 최선 대조군 대비 개선 | ECE | MCE |
|---|---:|---:|---:|---:|
| SF | 0.645159 | +0.006114 | 0.076135 | 0.076312 |
| SP | 0.447750 | -0.001328 | 0.010062 | 0.156250 |
| ST | 0.445108 | +0.000221 | 0.009391 | 0.009391 |
| SR | 0.654746 | -0.003820 | 0.075940 | 0.103717 |

## 4. 경보, 오탐·미탐과 사건구간 식별

모든 개발 OOF와 terminal holdout에서 후보 확률이 동결 threshold 0.5를 넘은 경보는 0건이다.

- terminal recall: 전 head 0.0
- terminal miss rate: 전 head 1.0
- terminal false-alarm rate: 전 head 0.0이나 경보가 전혀 없어서 실용적 우수성을 뜻하지 않는다.
- terminal precision: 경보 분모가 0이므로 `not_estimable_zero_denominator`
- onset 오차, lead time, segment IoU, 종료 오차: 이진 10일 continuation label만으로는 `not_identifiable`
- FOMO·패닉·차익실현·회복의 인간 심리 또는 실제 매도 의도: price-volume proxy만으로는 `not_identifiable`

개발 OOF 6개에서도 head별 경보 합계는 모두 0건이었다. Brier 개선의 개발 OOF 중앙값도 SF -0.001540, SP -0.000107, ST -0.000457, SR -0.000635로 모두 음수였다. 양의 개선 fold는 SF 2/6, SP 2/6, ST 2/6, SR 1/6이었다.

## 5. 비용, 체결과 꼬리위험

동결 threshold에서 수락된 가상 거래는 0건이다. 따라서 100 bps와 300 bps 비용 시나리오 모두 비용차감 수익, VaR, CVaR를 추정할 거래 표본이 없다.

- 비용차감 성과: `not_estimable_zero_trades`
- VaR/CVaR: `not_estimable_zero_trades`
- downside short: 차입·체결자료 부재로 `not_identifiable_without_borrow_and_execution_data`
- 다종목 포트폴리오: 사전 고정 비중 부재로 `not_identifiable_without_portfolio_weights_and_common_calendar`
- 최종 행동: `NoTrade`

## 6. 데이터·시간 무결성과 탈락행

- 입력 분석행: 5,250
- feature 적격: 5,103
- label 적격: 5,043
- history 부족: 126
- OOD feature: 21
- terminal future 부족 censoring: 60
- training-bin count 부족 probability mapping abstention: 52
- invalid row: 0
- feature-window 행순서 위반: 0
- source-window mismatch: 0

행 인덱스 기준으로 feature가 t 이하 행만 사용하고 t 이후 10개 행은 label에만 사용됐다는 점은 검증됐다. 그러나 일봉 timestamp는 candle 사건시각이고 실제 raw 응답은 2026-07-11에 사후 수신됐다. 공급자의 historical publication timestamp, revision/backfill 정책, adjusted-price vintage가 문서화되지 않았으므로 source-vintage PIT와 공식 채택 Gate는 `not_identifiable`이다. 본 수치는 `research_only_price_volume_proxy`이지 confirmatory adoption 증거가 아니다.

## 7. 후보별 판정

| 대상 | 판정 | 근거 |
|---|---|---|
| B1 Jeffreys constant | retain_as_comparator_only | 단순 기준선 역할만 유지 |
| B2 directional-shock bins | retain_as_comparator_only | 네 terminal 비교에서 모두 최선 기준선 |
| SF family | proxy_only + insufficient_evidence | terminal +0.002164 < δ, 개발 OOF 중앙값 음수, 경보 0건 |
| SP family | reject_current_version | terminal 성능 악화, 구간 상한이 δ 이하, 경보 0건 |
| ST head | reject_current_version | 개선량이 사실상 0이고 구간 상한이 δ 이하, 경보 0건 |
| SR head | reject_current_version | terminal 성능 악화, 구간 상한이 δ 이하, 경보 0건 |

공식별 `P(개선량 > δ)`는 사전등록되지 않았고 현재 artifact가 bootstrap 반복값 자체를 보존하지 않으므로 추정하지 않는다. 성공·실패 분포의 현 단계 근거는 위 2,000회 paired bootstrap 95% 구간이며, 이를 사후 확률로 재해석하지 않는다.

## 8. 보상해킹 감사

- 표본, 기간, horizon, 후보, 대조군, fold, seed, 비용, δ, threshold는 가격 열람 전에 동결됐다.
- 결과 열람 뒤 수식, 가중치, threshold, 상태명 또는 표본 변경은 0건이다.
- 후보와 두 기준선은 같은 fold와 common row mask를 사용했다.
- 결측을 0 또는 중립값으로 대체하거나 남은 항목을 재가중하지 않았다.
- 네 후보 head, 모든 28개 평가, abstention·censoring·실패 Gate를 함께 공개했다.
- 주문·계좌·자산 API 호출과 운영 앱 변경은 0건이다.
- source-vintage PIT를 증명하지 못한 한계를 성공으로 바꾸지 않고 `not_identifiable`로 보존했다.

## 9. 재현성과 핵심 artifact

- candle raw: `research/rp-001/candle-runs/RP001-CANDLE-20260711-001/raw-candles.json` (`fec5b407ad0cb0a956f4c8db390c532fa76a604b40325615d57c19605ae1567e`)
- candle processed: `research/rp-001/candle-runs/RP001-CANDLE-20260711-001/processed-candles.json` (`84468f6e3d94d3a4a84fa29695188fc893824696c569a1c99257b2a9b17a31e3`)
- candle manifest: `research/rp-001/candle-runs/RP001-CANDLE-20260711-001/manifest.json` (`041ca0abcbcb4f26a4f8fbb35ed8ef96b0b41e31c3cb7936bc23cfef863d04c8`)
- evaluation result: `research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/result.json` (`0ea2d5ad313780a37aec904f6aa3ef351aedb617c2cb6d159cdca6df282ea80a`)
- evaluation trial: `research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/trial.json` (`16c708673389e808c549de3ed96ae2eaf1c2ea8e97d2c22a731f322ef59d7e5f`)
- evaluation manifest: `research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/manifest.json` (`cb4ced057b7aa9243ef9f3540b959cb48aa95bb4bee152c5b08d66c3ad5bbfac`)
- evaluation runner: `research/rp-001/run_interim_evaluation.py` (`c1147f0b5bfc5c004cc42227670a568b017fdf74d95d23ade0a24e5a7541fd5b`)
- runner audit: `research/rp-001/audits/interim-evaluation-runner-v1-audit.json` (`5a5836bd3348683244754b192a4747e275e3785bda9eb95c3d40575f0de4ed51`)
- terminal ledger event 17: `research/rp-001/local-ledgers/interim-program/events/000017.json` (`53eea2a4851af29670e594c1095c7c667c6aba80192301ce44de2388e82be927`)

검증 명령:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=research/rp-001/src \
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
-m unittest discover -s research/rp-001/tests -p 'test_*.py'
```

실제 평가는 `run_interim_evaluation.InterimEvaluationRunArguments`에 위 processed/sample/MERC path와 SHA, 격리된 output/ledger 경로, 새 run ID를 주입해 실행한다. 기존 run ID와 기존 원장은 append-only이므로 재현 실행에서 덮어쓰지 않는다.

## 10. 중간 종료 판정

`no_adoptable_formula`. 이 중간결과는 성공 공식을 만들지 못했지만, 실패·불충분·식별불가를 포함한 동결 후보 전체를 실제 데이터로 실행하고 단일 terminal evidence로 남겼다. 현 공식·threshold를 사후 수리하지 않으며, 후속 후보는 새 질문·새 프로토콜·새 사전등록으로만 시작할 수 있다.
