# RP-001 최종 연구보고서

완료 시각: `2026-07-11T04:18:39Z`

권위 규칙: `authoritative_only_with_matching_rp001_program_completed_no_adoptable_formula_ledger_event`. 아래 산출물은 이 규칙과 일치하는 ledger event 19가 있을 때만 권위가 있습니다.

## 1. 한 문장 최종 결론

채택 가능한 공식은 없으며, 확인 가능한 가격·거래량 프록시도 채택 Gate를 통과하지 못했으므로 최종 행동은 NoTrade/no integration입니다.

## 2. 채택·조건부·기각·식별불가 공식 목록

- adopt: 없음
- conditional_adopt: 없음
- proxy_only/insufficient_evidence: SF 가격·거래량 상승 지속 후보
- reject: SP 하락 지속, ST·SR 극단 반전 후보
- not_identifiable: FOMO·패닉·차익실현·회복의 인간 심리·의도 구성개념
- registry-only legacy/복잡 모형: 자료·식별 Gate 때문에 실행하지 않았으며 성능치를 만들지 않음

RQ-003/SP-003의 5거래일 직접 행동 연구는 등록된 본 연구이며 data_unavailable로 종료됐습니다. [EB-002#STE-ST-BEH-001-001; research/meta-research/objects/research-questions/RQ-003-behavior-regime/question.md] 실제 실행된 RQ-003-PV10-v1/SP-003-PV10-v1은 별도의 연구용 가격·거래량 프록시이고, 10-session binary continuation을 대상으로 하므로 본 연구의 실행이나 대체물이 아닙니다. [EB-002#CLM-PROXY-ESTIMAND-10S; research/rp-001/contracts/interim-formula-contract-v1.0.1.json]

상태 온톨로지는 70개 cell(identifiable 10, proxy_only 45, not_identifiable 15)을 보존합니다. [EB-002#CLM-METRIC-ONTOLOGY-CELLS; research/meta-research/objects/programs/RP-001-quantitative-market-behavior/state-ontology.json]

## 3. 수식별 성공·실패 확률분포

- SF: Brier 개선 0.0021638167070835157, 95% 구간 [0.00037120901797999624, 0.006156005646251266], 판정 proxy_only [EB-002#CLM-METRIC-BRIER-SF; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]
- SP: Brier 개선 -0.000345785497798734, 95% 구간 [-0.0009313547688962396, 0.00022021357754718648], 판정 reject [EB-002#CLM-METRIC-BRIER-SP; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]
- ST: Brier 개선 6.719686592471241e-05, 95% 구간 [-0.0007718569631020115, 0.0007596300560890151], 판정 reject [EB-002#CLM-METRIC-BRIER-ST; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]
- SR: Brier 개선 -0.001444694173986183, 95% 구간 [-0.005071183032926315, 0.003981163144879557], 판정 reject [EB-002#CLM-METRIC-BRIER-SR; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]

성공확률 자체는 사전등록되지 않아 사후 확률로 변환하지 않았습니다. 위 paired moving-block bootstrap 95% 구간은 기술적 요약이며, 사전등록된 다중비교·selection 조정을 적용하지 않았으므로 확인적 성공확률로 해석할 수 없습니다.

## 4. 사건·국면별 예측성과

terminal holdout의 모든 head에서 alarm 0 [EB-002#CLM-METRIC-ALARMS; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json], recall 0 [EB-002#CLM-METRIC-TERMINAL-RECALL; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json], miss rate 1.0 [EB-002#CLM-METRIC-TERMINAL-MISS-RATE; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]이었습니다. 실행 estimand는 10-session binary continuation이며 [EB-002#CLM-PROXY-ESTIMAND-10S; research/rp-001/contracts/interim-formula-contract-v1.0.1.json], 이 label로 onset·종료 오차, segment IoU와 회복 구간을 식별하지 않았습니다.

## 5. 비용 차감 경제적 성과와 꼬리위험

수용된 가상거래는 0건입니다. [EB-002#CLM-METRIC-ACCEPTED-TRADES; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json] 기본 100 bps [EB-002#CLM-METRIC-BASE-COST-BPS; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]와 stress 300 bps [EB-002#CLM-METRIC-STRESS-COST-BPS; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json] 비용 계약은 유지했으나 순성과, drawdown, VaR·CVaR는 zero-trade로 추정할 수 없습니다. 결과 행동은 NoTrade입니다.

## 6. 반증·실패·한계

G2·G3·G6·G7a가 실패했고, G7b·G8·G9·G10은 필요한 자료나 적격 입력이 없어 not_evaluated입니다. source-vintage point-in-time, 인간 심리 직접자료, 상대가치 panel, ordered microstructure, execution events와 portfolio risk inputs는 현재 승인·동결된 자료 범위에서 확인되지 않았습니다. 이는 제공자 전체 또는 법적 부재를 뜻하지 않습니다. 일봉은 이 입력들을 대체하지 않습니다. [EB-002#CLM-SCOPE-SOURCE-MATRIX-SNAPSHOT; research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-matrix.json]

## 7. 보상해킹 감사결과

동결 후 가중치·threshold·표본·상태명 변경, 결측 대체·재가중, 미공개 후보, 주문·계좌·자산 호출 및 운영 앱 변경에 대한 기록된 위반 합계는 0건입니다. [EB-002#CLM-METRIC-REWARD-AUDIT-ZERO; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]

## 8. 재현성·외부검증 결과

source matrix는 liveApiCalled=false였던 historical design snapshot입니다. [EB-002#CLM-SCOPE-SOURCE-MATRIX-SNAPSHOT; research/meta-research/objects/programs/RP-001-quantitative-market-behavior/source-matrix.json] 그 뒤 별도 동결 계약 아래 Toss 가격·거래량을 읽은 candle manifest는 5,250행의 successor live read-only observation이며 주문·계좌·자산에는 접근하지 않았습니다. [EB-002#CLM-SCOPE-CANDLE-SUCCESSOR; research/rp-001/candle-runs/RP001-CANDLE-20260711-001/manifest.json] 수식 계약 v1.0.1과 구현·테스트 hash가 고정되어 있고, 분석 입력 5,250행 [EB-002#CLM-METRIC-INPUT-ROWS; research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json]과 28개 평가 [EB-002#CLM-METRIC-EVALUATIONS; research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/result.json]가 append-only ledger에 연결됩니다. local canonical body·sidecar·ledger 검증은 제공하지만 외부 CAS와 signed anchor는 deferred_until_final_adoption이므로 모든 로컬 파일의 coordinated rewrite 탐지는 제공하지 않습니다. [DR-002#deferredCapabilities; research/rp-001/final/DR-002-no-adoptable-formula.json] 이 한계는 채택 근거가 아니며 최종 no-adoption 판정을 완화하지 않습니다. 외부 전향표본(G7b)과 독립 실행(G9)은 수행하지 않아 not_evaluated입니다.

재현 명령: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001/src /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -B research/rp-001/finalize_program.py --verify`

## 9. 최종 공식 또는 no-adoptable 결론

최종 판정은 `no_adoptable_formula`입니다. 우수한 한 Gate로 다른 Gate의 실패를 상쇄하지 않았습니다.

## 10. 모든 핵심 artifact의 경로

- `research/rp-001/final/EB-002-program-terminal-evidence.json`
- `research/rp-001/final/completion-traceability.json`
- `research/rp-001/final/DR-002-no-adoptable-formula.json`
- `research/rp-001/final/PC-001-program-completion.json`
- `research/rp-001/reports/RP001-20260711-final-research-report.md`
- `research/rp-001/reports/RP001-ST-BEH-20260711-interim-disposition.json`
- `research/rp-001/evaluation-runs/RP001-EVAL-20260711-001/result.json`
