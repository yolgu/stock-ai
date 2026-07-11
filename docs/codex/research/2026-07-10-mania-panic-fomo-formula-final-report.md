# FOMO·차익실현·패닉셀 수식 최종 연구 보고서

## 1. 최종 결론

**현재 데이터와 동결된 v1.4 연구설계에서 운영에 채택할 수 있는 최적 공식은 없다.** 최종 판정은 `adoption_not_identifiable`이며, 채택 공식 수는 0개다.

이 결론은 다음 세 문장을 구분해 해석해야 한다.

1. 기존 문서 합성식과 현재 production 차익실현 식은 수학·등가성·인과성·결측 계약을 통과하지 못했으므로 운영 의사결정식으로 채택하지 않는다.
2. 반복표본에 진입한 일봉 후보 중 TSLA 개발구간에서 단순 학습 기준선을 통계적으로 이긴 후보는 0개였다. 29개 경쟁군 모두 `no_valid_formula`로 종료됐다.
3. 외부 채택 규칙이 v1.4 사전등록에 없고, 거래량 단위 결함과 사건 수 부족이 있으므로 “모든 가능한 공식이 보편적으로 실패했다”고 주장하지 않는다. 정확한 결론은 **현 증거로 채택 여부를 식별할 수 없고, 억지 가중치 조정도 허용되지 않는다**이다.

따라서 가중치나 임계값을 사후 조정하지 않았고, production에 적용할 새 점수도 만들지 않았다. 사용자께서 제안한 `계층 Bayesian HSMM + 경쟁위험`은 [후속 연구 틀](2026-07-10-bayesian-hsmm-competing-risks-framework.md)의 주 도전자 모형으로 확정했지만 아직 검증된 공식은 아니다.

## 2. 판정표

| 대상 | 최종 판정 | 사용 결정 |
| --- | --- | --- |
| production `calculateProfitTakingPressure` 계열 | `rejected` | 숨은 하한, 미래 as-of 누출, 결측 0점화·재가중, 입력순서·중복 timestamp 의존, 도달 불가 분기가 있어 의사결정에 사용 금지 |
| 문서 FOMO·패닉·차익실현 원식 | `reject`·`not_identifiable`·`proxy_only` 혼재 | 인간심리 또는 호가·체결 원식으로 사용 금지 |
| v1.4 거래량 의존 일봉 후보 12개 | `data_unavailable` | 분할 전후 거래량 단위 계약이 없어 0점 대체 없이 제외 |
| `panic.baseline.drawdown3` | `proxy_only`, 통계 gate 실패 | 점 추정상 일부 개선이 있었지만 모든 Brier 개선구간이 0을 포함하므로 채택 금지 |
| FOMO·차익실현·relief 가격 전용 기준선 | `insufficient_evidence` | 사건 수·보정·기준선 우월성 부족으로 채택 금지 |
| MU·SK하이닉스 최근 120일·4개월 | `insufficient_evidence` | 기술적 산출은 설명용만 허용, 확률 공식 확정 금지 |
| Bayesian HSMM + 이산 경쟁위험 | `research_candidate` | v1.5+ 사전등록과 보지 않은 전향·외부 표본 전에는 운영 금지 |
| OFI + Hawkes | `not_identifiable_now` | 순서보존 호가·체결·취소 자료를 전향 수집한 뒤 별도 검증 |

## 3. 연구 범위와 실제 데이터

연구 기준시점은 2026-07-09 종가까지다. Toss 수정주가 일봉을 공식 pagination 계약에 따라 수집했고 원자료는 변경하지 않았다.

| 구간 | 날짜 | 거래일 | 역할 |
| --- | --- | ---: | --- |
| TSLA 광풍기 | 2020-07-23 ~ 2021-12-23 | 360 | 후보 선택용 OOF |
| TSLA 시작점 민감도 | 2020-08-12 ~ 2022-01-13 | 360 | 선택에 사용하지 않는 민감도 |
| NVDA 광풍기 | 2023-05-25 ~ 2024-10-29 | 360 | 외부 복제 |
| MU 최신 | 2026-01-15 ~ 2026-07-09 | 120 | 잠금 holdout |
| SK하이닉스 최신 | 2026-01-13 ~ 2026-07-09 | 120 | 잠금 holdout |
| MU·SK하이닉스 최근 4개월 | 2026-03-10 ~ 2026-07-09 | 각 84 | 120일 holdout의 기술적 부분집합 |

원자료 규모는 TSLA 4,031행, NVDA 6,907행, MU 9,196행, SK하이닉스 7,371행이다. 데이터 manifest SHA-256은 `ed5126ed94c6316e5bc0389f33443f3e3a38576a55164eda758016ff5d37dae9`다. SK하이닉스의 KRX 공식 일봉 교차대조는 수행하지 못했으므로 한국 종목 결과는 Toss 단일 공급자 주장으로 제한한다.

## 4. 거래량 단위 결함과 폐기된 1차 실행

Toss 원자료는 가격이 분할조정돼 있지만 과거 거래량의 분할조정 계약이 선언돼 있지 않았다. 실제로 알려진 분할일에 거래량 단위가 불연속이었다.

| 종목 | 분할조정 거래일 | 공식 분할비율 | 당일 거래량 / 직전 20일 중앙값 |
| --- | --- | ---: | ---: |
| TSLA | 2020-08-31 | 5:1 | 8.8283 |
| TSLA | 2022-08-25 | 3:1 | 1.9378 |
| NVDA | 2021-07-20 | 4:1 | 4.3549 |
| NVDA | 2024-06-10 | 10:1 | 0.7416 |

분할 사실과 효력일은 Tesla·NVIDIA IR과 SEC 자료로 교차확인했다. 상세 URL과 접근일은 [`data-quality-amendment.v1.json`](../../../research/indicator-validation/data-quality-amendment.v1.json)에 고정했다.

이 결함을 발견하기 전에 생성된 run manifest `8424ef22dc10e4f2aedc8fff018ed1e5940908cd5b382286279ce0e0cdd78fcf`는 최종 추론에서 폐기했다. 원자료나 결과가 좋아지는 방향의 split factor를 사후 추정하지 않았다. 대신 다음 9개 특징을 사용하는 12개 후보를 분할일이 포함된 창에서 `data_unavailable`로 만들었다.

```text
volumeSurprise, volume20, vwap20, vwapPersistenceProxy,
vwapDownPressure, liquidityProxy, profitBreadth,
profitGainMass, vwapExtension
```

이 수정은 결측을 위험 0으로 위장하지 않으며, 남은 항의 가중치도 재정규화하지 않는다. 변경 원장 SHA-256은 `c93c7758ffbc4bdb10fa8ece3e375063301d083705603c82f04385a7025f1688`다.

## 5. 수식 전수 감사

기계판독 수식 원장은 224개 수식·변형, 문서 선언 172개, 명시적 비수식 제외 17개를 포함한다. 탐지 범위 안에서 누락 선언, 중복 ID, 누락된 증명 판정 필드, 잘못된 위치 참조, 구조 검증 오류는 모두 0개다.

| 수식 판정 | 개수 | 의미 |
| --- | ---: | --- |
| `valid` | 18 | 정의된 조건에서 범위·단위·인과성 계약을 만족 |
| `repairable` | 32 | 목적은 유지할 수 있으나 정의역·단위·경계·상태 규칙 수정 필요 |
| `proxy_only` | 74 | 원래 심리·미시구조 개념이 아니라 명시적 일봉 프록시로만 사용 가능 |
| `not_identifiable` | 70 | 현재 과거 데이터에 필수 입력 또는 진실 라벨이 없음 |
| `reject` | 30 | 범위·차원·인과·항등·재현성 반례로 폐기 |

증명 의무 2,240개 중 `proved` 186개, `conditional` 1,032개, `not_identifiable` 559개, `not_applicable` 445개, 명시적 `counterexample` 18개다. 기계판독·탐지 범위 원장은 [`formula-ledger.json`](../../../research/indicator-validation/formula-ledger.json), 사람이 읽는 대응표는 [수식 원장·등가성 감사](2026-07-10-formula-ledger-and-equivalence.md), 유도와 최소 반례는 [수학 감사](2026-07-10-formula-mathematical-audit.md)에 있다.

### 대표 수학 반례

- `FullPanicSell = 0.35E + 0.45I - 0.20R`의 범위는 `[-20,80]`이지 `[0,100]`이 아니다.
- `PanicAbsorptionScore`는 0~100 점수와 0~1 항을 직접 더해 단위가 맞지 않는다.
- `FOMO_Tradability`는 입력에 따라 -35가 되어 0~100 계약을 깬다.
- `ExhaustionRisk`의 `max(-CVD_AccelScore,0)` 항은 입력이 `[0,1]`이면 항상 0이다.
- `ContinuationLabel`은 무차원 미래수익률과 가격 단위 ATR을 직접 비교한다.
- 패닉 상태표에는 어느 상태에도 속하지 않는 입력과 동시에 참이 되는 상태가 존재한다.

### production 보상해킹 진단

현재 production 차익실현 구현은 문서식과 동치가 아니다. 반례 테스트에서 다음을 재현했다.

- 표시 선형합이 62인데 실제 반환값은 숨은 하한 때문에 75가 된다.
- 낮은 선형합이어도 한 원인이 85 이상이면 65점 하한이 적용된다.
- 미래 timestamp의 캔들을 추가하면 과거 as-of VWAP과 판단이 바뀐다.
- 입력 순서를 뒤집거나 timestamp를 중복하면 결과가 바뀐다.
- 결측 원인은 0점으로 바뀌고, 하위 계산은 가용항만으로 가중치를 다시 합친다.
- 목표가를 `current + 2ATR` 이상으로 강제해 risk/reward의 warning·danger 분기가 도달 불가능하다.
- 분할 조정 가격·거래량 변환에 CVD 상태가 불변이 아니다.

따라서 이 함수는 설명·경보·거래결정의 검증 공식으로 사용할 수 없다. 연구용 reference와 production의 `researchToProduction` 등가성은 224개 중 26개가 명시적 `non_equivalent`, 198개가 `not_implemented`다.

## 6. 통계 설계

- 고유 공식 후보 19개에서 후보식 × 결과 × 1·3·5·10일 horizon을 전개한 사전등록 trial 130개
- TSLA 3개 120일 test fold의 expanding past-only 학습, 최대 horizon purge와 embargo
- NVDA·MU·SK하이닉스에는 TSLA 전체에서 한 번 고정한 calibrator·base rate·q80 적용
- Jeffreys prior `Beta(0.5,0.5)`의 성공·실패 사후분포와 다음 10건 Beta-Binomial 예측분포
- 5·10·20일 이동블록 bootstrap 각 2,000회
- 2,000회 circular placebo
- TSLA 선택은 BH, 사전등록 핵심 4개 가설은 Holm 보정
- 과거 학습 q80 이상으로 올라가는 상승교차만 alert episode로 만들고 horizon 동안 중복 신호 억제. 동점은 분할하지 않으므로 실제 alert 비율이 20%라는 뜻은 아님

동결 v1.4는 후보 정의·가중치·보정 **알고리즘**을 고정하지만, TSLA OOF에서는 각 fold의 과거 학습구간으로 calibrator와 q80을 expanding refit한다. 따라서 원 Goal 문구의 “첫 블록 수치 자체를 이후 fold에 그대로 적용”하는 estimand와 같지 않다. 이 결과는 `fold-adaptive past-only recalibration` 연구로만 해석한다. NVDA·MU·SK하이닉스에서는 TSLA 최종 fit을 바꾸지 않았다.

## 7. 최종 반복표본 결과

최종 코드·입력을 기본 결과 디렉터리와 별도 임시 디렉터리에서 재실행해 같은 run manifest SHA-256 `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e`를 생성했다. 두 manifest는 바이트 단위로도 같았다. 결과는 130개 trial, 650개 stage×trial metric 행, 94,800개 prediction 행, 29개 경쟁군을 포함한다.

| stage×trial 상태 | 행 수 | 해석 |
| --- | ---: | --- |
| `evaluated` | 11 | 최소 사건·확률 요건을 통과해 수치 비교 가능 |
| `insufficient_evidence` | 239 | 최소 사건 또는 selection gate 부족 |
| `data_unavailable` | 80 | TSLA 분할 거래량 단위 결함의 직접 영향 |
| `calibration_unavailable` | 320 | TSLA에서 고정 calibrator를 만들 수 없어 외부 단계 적용 불가 |

### 평가 가능했던 11개 시험

`s/f`는 q80 상승교차 alert episode의 성공/실패다. `Brier 개선`은 `기준선 Brier - 후보 Brier`이므로 양수가 개선이다. 모든 보수적 95% bootstrap 구간이 0을 포함했다.

| 단계 | 시험 | s/f | 사후분포 | 중앙값 | 95% CrI | Brier 개선 | 보수적 95% CI | p |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| TSLA OOF | `panic.baseline.drawdown3::panicContinuation@1` | 12/24 | Beta(12.5,24.5) | 0.335 | [0.197, 0.495] | 0.001057 | [-0.000544, 0.002251] | 0.131 |
| TSLA OOF | `panic.baseline.drawdown3::panicContinuation@3` | 12/21 | Beta(12.5,21.5) | 0.365 | [0.216, 0.534] | -0.000127 | [-0.001198, 0.000772] | 0.735 |
| TSLA OOF | `panic.baseline.drawdown3::panicContinuation@5` | 13/17 | Beta(13.5,17.5) | 0.434 | [0.269, 0.610] | -0.000131 | [-0.001056, 0.000536] | 0.856 |
| TSLA OOF | `panic.baseline.drawdown3::panicOnset@1` | 5/33 | Beta(5.5,33.5) | 0.135 | [0.052, 0.265] | 0.000386 | [-0.000126, 0.001129] | 0.078 |
| TSLA OOF | `panic.baseline.drawdown3::panicOnset@3` | 8/27 | Beta(8.5,27.5) | 0.231 | [0.114, 0.385] | 0.000060 | [-0.001019, 0.001326] | 0.434 |
| TSLA OOF | `panic.baseline.drawdown3::panicOnset@5` | 8/24 | Beta(8.5,24.5) | 0.253 | [0.126, 0.417] | -0.000359 | [-0.001023, 0.000439] | 0.802 |
| NVDA 외부 | `fomo.baseline.momentum5::fomoExhaustion@1` | 10/20 | Beta(10.5,20.5) | 0.335 | [0.186, 0.511] | 0.000017 | [-0.000153, 0.000209] | 0.366 |
| TSLA 민감도 | `panic.baseline.drawdown3::panicContinuation@1` | 12/22 | Beta(12.5,22.5) | 0.354 | [0.209, 0.520] | 0.002349 | [-0.001905, 0.007552] | 0.124 |
| TSLA 민감도 | `panic.baseline.drawdown3::panicContinuation@3` | 12/19 | Beta(12.5,19.5) | 0.388 | [0.232, 0.562] | 0.002011 | [-0.003086, 0.007839] | 0.199 |
| TSLA 민감도 | `panic.baseline.drawdown3::panicOnset@1` | 4/31 | Beta(4.5,31.5) | 0.118 | [0.040, 0.249] | 0.000631 | [-0.000443, 0.001841] | 0.136 |
| TSLA 민감도 | `panic.baseline.drawdown3::panicOnset@3` | 7/25 | Beta(7.5,25.5) | 0.222 | [0.104, 0.382] | 0.000273 | [-0.001664, 0.002556] | 0.392 |

29개 `family×outcome×horizon` BH 가족 중 시험을 포함할 수 있었던 가족은 6개뿐이었고, 각 가족에는 한 시험만 남아 보정 p가 raw p와 같았다. 유의한 시험은 0개였다. 핵심 4개 Holm 가설은 모두 `insufficient`, 보정 p=1이었다. 점 추정상 가장 큰 개선은 TSLA 민감도 구간의 1일 패닉 지속 0.002349였지만 선택구간이 아니며 구간 `[-0.001905, 0.007552]`가 0을 포함한다. 이를 최적 공식으로 부르면 선택 편향이다.

650개 stage×trial의 상태는 모두 [`metrics.json`](../../../research/indicator-validation/results/metrics.json)에 보존돼 있다. 실제 alert episode를 관측할 수 있는 행에만 성공·실패 수, `Beta(s+0.5,f+0.5)`, 중앙값, 95% 신용구간과 다음 10건 예측분포가 있다. `data_unavailable`과 `calibration_unavailable` 행의 `alerts`와 posterior는 `null`이며 수치 0.5를 생성하지 않는다. 평가 가능한 행에는 Brier·log loss·PR-AUC·MCC, calibration, placebo와 bootstrap도 함께 있다.

### q80 임계값 퇴화 진단

q80은 연속 점수라면 상위 약 20%를 의도하지만, 이산·포화 점수의 동점을 분할하지 않는 사전등록 규칙 때문에 일부 기준선에서 퇴화했다. TSLA OOF의 확률 계산 가능한 50개 trial 중 25개는 fold별 q80이 0 또는 100 하나뿐이었고, 유효 관측의 100%가 `rawAlert=true`였다. 대표적으로 `breakout20`·`lowBreak20`은 q80=0, `runup20`은 q80=100이었다. 상승교차와 cooldown을 적용하면 첫 episode 하나만 남는 trial도 있어 `insufficient_evidence`가 됐다. 따라서 이들의 실패는 단순한 시장 사건 부족뿐 아니라 **임계값이 순위를 분해하지 못한 설계 결함**을 포함한다. 사전등록 뒤 threshold를 바꾸지 않았으며, v1.5+에서는 최소 고유값·alert coverage·tie degeneracy gate를 외부자료 전에 고정해야 한다.

## 8. MU·SK하이닉스 120거래일과 최근 4개월

두 120일 holdout에서 각각 130개 중 가격 전용 50개는 모두 `insufficient_evidence`, TSLA에서 calibrator를 만들 수 없었던 거래량 의존 trial 80개는 `calibration_unavailable`였다. 평가 완료 trial은 0개다.

비중첩 사건의 이론적 최대치는 horizon 1일 60개, 3일 30개, 5일 20개, 10일 10개다. 최소 30건 gate를 유지하면 120일 자료에서 5일·10일은 데이터 값과 무관하게 통과 불가능하다. 최소 이론 길이는 5일 180거래일, 10일 330거래일이며 실제 결측·purge를 고려하면 더 길어야 한다.

최근 4개월 84일은 별도 독립 holdout이 아니라 동일 120일 표본의 부분집합이다. 가격 전용 50개 trial에 기술 통계는 생성됐지만 재집계 추론은 금지했다. 전체 120일 기준 MU의 alert episode는 trial별 1~12개, SK하이닉스는 1~14개에 불과했고 신용구간이 매우 넓었다. 예를 들어 SK하이닉스 `panic.baseline.drawdown3::panicOnset@1`의 120일 alert 결과는 0/14, Beta(0.5,14.5), posterior mean 0.033이지만 95% 구간이 약 [0.00003, 0.162]다. 이 값은 해당 표본의 실패 기록이지 안정된 미래 확률 공식이 아니다.

## 9. 패닉·FOMO·차익실현 국면 예측 판정

사건 카탈로그는 145개 stage×outcome×horizon 그룹, 3,387개 비중첩 episode 기록을 생성했다. 이 숫자는 서로 다른 horizon과 stage가 같은 시장 움직임을 반복 표현하므로 하나의 독립 표본 수로 합산하면 안 된다.

확인 가능한 날짜는 prodrome 후보일, origin/start, first-passage target, 극값, 확인, 종료, fake-relief다. 반면 다음 국면은 정의가 충분하지 않아 전체 episode에서 `phase_not_identifiable`이다.

- 패닉·FOMO의 초기 진행
- 중간 국면
- 일반화된 첫 반등

v1.4 lead time은 `targetDate - alertDate`이며 사건 **시작 전** 시간과 같지 않다. 실제 matched alert 중 origin 뒤에 발생한 신호가 TSLA OOF 139/320, TSLA 민감도 130/333, NVDA 160/382, MU 44/131, SK하이닉스 59/131 포함됐다. 따라서 현재 결과로 “패닉 시작 전조를 맞혔다”거나 “FOMO 시작·끝을 예측했다”고 주장할 수 없다. 이는 향후 경쟁위험 연구에서 `alert < event origin`을 별도 gate로 고정해야 한다.

시장 동시사건 cluster는 생성했지만 일별 확률 행에 cluster weight를 매핑하는 규칙이 사전등록되지 않아 global metric은 `not_identifiable`이다. PR-AUC·MCC·lead time의 bootstrap 구간도 등록된 재표본 통계가 완결되지 않아 점 추정만 있고 구간 주장은 하지 않는다. 거래비용과 실제 거래 가능성은 거래 시뮬레이션이 없어 평가하지 않았다.

## 10. 가중치·임계값 결론

최종 조정 가중치와 임계값은 **없다**.

- 문서식, 동일가중식, 중복축소식, 단순 기준선의 경쟁에서 복합식이 유효한 공통 mask로 단순식을 이긴 사례가 없었다.
- 거래량 포함 복합식은 분할 단위 문제로 비교 자체가 불가능했다.
- 가격 전용 `panic.baseline.drawdown3`은 일부 점 추정에서 가장 좋았지만 학습 base-rate gate와 불확실성 gate를 통과하지 못했다.
- 29개 경쟁군 전부 `no_valid_formula`, TSLA 외부평가 선발 0개, 조건부 유효 0개다.
- 결과를 본 뒤 가중치, q80 또는 사건 threshold를 낮추는 것은 trial 누락과 보상해킹이므로 하지 않았다.

운영 출력의 안전한 기본값은 위험 0이 아니라 다음 상태다.

```text
status = not_identifiable
probability = unavailable
reason = no_preregistered_externally_validated_formula
```

## 11. 차세대 연구 틀

단일 가중합 점수 대신 다음을 분리하는 `계층 Bayesian HSMM + 이산 경쟁위험`을 v1.5+ 주 도전자로 둔다.

1. 시장·업종·금리·변동성·환율 요인을 제거한 종목 고유 수익률
2. 분할 일관 거래량과 일별 주식수로 만든 turnover·기준가격 분포
3. 전망이론 기반 이익권 `G_t`와 손실권 `L_t`
4. 명시적 지속시간을 가진 `Normal → PreFOMO → FOMO → Exhaustion → ProfitTaking → PrePanic → Panic → Capitulation → Relief` 잠재상태
5. 상승 지속·FOMO 소진·차익실현형 조정·패닉 진입·추가하락·회복의 상호 배타적 `CIF_k(h)`
6. `estimated`, `missing`, `not_identifiable`, `abstain` 출력 계약

현재 자료에는 일별 주식수, point-in-time factor, 행동·관심도, 투자자 흐름, 옵션·공매도, 과거 주문장 사건이 없다. 따라서 `RP/G/L`, 인간심리 상태, OFI, Hawkes를 지금 소급 계산하지 않는다. 먼저 일봉 HSMM·경쟁위험을 단순 기준선과 봉인된 외부표본에서 비교하고, OFI·Hawkes는 순서보존 호가·체결·취소 자료가 축적된 뒤 결합한다. 상세 수식, identifiability, Fine–Gray와 원인별 hazard 구분, G0~G9 gate는 [후속 연구 틀](2026-07-10-bayesian-hsmm-competing-risks-framework.md)에 있다.

## 12. 최종 산출물 대응표

### ST-01~ST-12 완료도

| 단계 | 상태 | 검토 결과 |
| --- | --- | --- |
| ST-01 사전등록 | 부분 | v1.4 후보·기간·라벨·trial 130개와 해시를 동결했지만 원 Goal의 첫 블록 수치 고정과 다름. 거래량 수정은 별도 사후 데이터 무결성 원장으로 보존 |
| ST-02 수식 원장 | 부분 | regex로 탐지한 224개 선언·변형을 구조 원장화했고 탐지 범위 내 누락은 0. 의미론적 전수성이나 모든 계산 테스트를 뜻하지 않음 |
| ST-03 수학 증명·반례 | 부분 | 10개 의무를 분류했으나 2,240개 중 proved 186, counterexample 18이고 나머지는 conditional·식별불가·해당없음 |
| ST-04 구현 등가성 | 부분(실패 판정) | production 반례와 대응표는 완료했지만 독립 reference 수치 계산은 문서 composite 3개와 production 일부이며 224식 전체 삼자 실행은 아님 |
| ST-05 실제 데이터 | 부분 | pagination·원자료·해시·품질 검사는 완료. 거래량 조정계약과 KRX 교차대조는 미확보로 명시 |
| ST-06 사건 표본 | 부분 | 비중첩 자동 사건·국면·시장 cluster는 생성. 변동성·추세·유동성 matched negative-control 표본은 미완료 |
| ST-07 성공·실패 정의 | 부분 | first-passage binary label과 중복 억제는 완료. 사건 시작 전 신호 gate, 비용·실제 거래 가능성은 미완료 |
| ST-08 반복 시행 | 부분 | purged walk-forward, embargo, 5·10·20 block bootstrap, circular placebo 완료. 첫 블록 수치 고정 estimand, pseudo-event, regime 반복은 미완료 |
| ST-09 수식 경쟁 | 부분 | 등록 trial은 모두 보존했지만 거래량 후보 12개는 비교 불가이고 상태전이 hazard·완전 Pareto 경쟁은 미완료. 승자 없음, 가중치 사후조정 없음 |
| ST-10 확률분포 | 부분 | Jeffreys posterior, Beta-Binomial, Brier bootstrap, BH/Holm 완료. PR-AUC·MCC·lead-time 구간은 식별불가 |
| ST-11 상태전이 확정 | 완료(무채택) | 검증 상태전이는 없음으로 확정하고 운영 계약을 `not_identifiable`로 지정. v1.5+ 후보 명세는 검증 전 연구안 |
| ST-12 독립 재검토 | 부분 | 누수·ledger·reference·시작점·placebo·실패 누락 감사 완료. ATR·regime·matched-control 민감도는 미완료 |

`부분`은 수행한 것처럼 간주하지 않는다. 해당 항목은 결론의 식별 한계를 구성하며, 현 연구에서 공식 채택을 금지하는 근거다. 따라서 이 문서는 전체 연구의 보편적 완결 선언이 아니라 **기존식 운영 무채택과 현 데이터·설계의 식별불가를 확정한 중간 연구 종료점**이다. 후속 v1.5+의 완료는 별도 Goal로 관리해야 한다.

| 요구 산출물 | 증거 파일 |
| --- | --- |
| 1. 연구 헌장·사전등록(부분) | [`preregistration.json`](../../../research/indicator-validation/preregistration.json), [설계서](../specs/2026-07-10-mania-indicator-validation-design.md) |
| 2. 수식 원장(탐지 범위 내) | [`formula-ledger.json`](../../../research/indicator-validation/formula-ledger.json) |
| 3. 수학적 증명·반례(부분) | [수학 감사](2026-07-10-formula-mathematical-audit.md) |
| 4. 문서↔구현 등가성(부분) | [등가성 감사](2026-07-10-formula-ledger-and-equivalence.md), [`formula-production-counterexamples.test.cjs`](../../../research/indicator-validation/formula-production-counterexamples.test.cjs) |
| 5. 데이터 manifest·해시 | [`data/manifest.json`](../../../research/indicator-validation/data/manifest.json), [`data-quality.json`](../../../research/indicator-validation/results/data-quality.json), [수정사항](../../../research/indicator-validation/data-quality-amendment.v1.json) |
| 6. 사건·대조구간 카탈로그(부분) | [`events.json`](../../../research/indicator-validation/results/events.json); 자동 사건은 완료, 명시적 matched negative control은 미완료 |
| 7. 120일 반복 시행 원장 | [`predictions.json`](../../../research/indicator-validation/results/predictions.json), [`trial-results.json`](../../../research/indicator-validation/results/trial-results.json) |
| 8. 성공·실패 확률분포 | [`metrics.json`](../../../research/indicator-validation/results/metrics.json) |
| 9. 국면·선행시간(부분) | [`events.json`](../../../research/indicator-validation/results/events.json)의 `phases`, `signals` |
| 10. 가중치·임계값 경쟁(부분) | [`selection.json`](../../../research/indicator-validation/results/selection.json) |
| 11. 무채택 상태계약·후속 명세 | [`selection.json`](../../../research/indicator-validation/results/selection.json)의 무채택 결정, [Bayesian HSMM·경쟁위험 후속 연구 틀](2026-07-10-bayesian-hsmm-competing-risks-framework.md)은 미검증 연구안 |
| 12. reference·자동검증(부분) | [`formula_reference.py`](../../../research/indicator-validation/formula_reference.py), [`validation.py`](../../../research/indicator-validation/validation.py), 연구 테스트 모음 |
| 13. 재현 명령·실행 로그 | [`run-manifest.json`](../../../research/indicator-validation/results/run-manifest.json), [`verification.json`](../../../research/indicator-validation/results/verification.json), [최종 검증 로그](2026-07-10-verification-log.md) |
| 14. 경영진 요약 | 본 보고서 1~2절 |
| 15. 연구자 기술 부록 | 본 보고서 3~11절과 연결된 원장·raw 결과 |
| 16. 한계·식별불가·폐기 목록 | 본 보고서 2·4·5·8·9절과 수식 원장 판정 |

## 13. 재현과 검증

고정 Python은 3.12.13, NumPy 2.3.5, pandas 2.2.3이다. 저장소 루트에서 다음 명령으로 재현한다.

```bash
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/indicator-validation/run_validation.py --run

/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/indicator-validation/run_validation.py --verify
```

최종 검증 결과는 다음과 같다.

- Python 연구 테스트: 127/127 통과
- Node 연구 계약·반례 테스트: 45/45 통과
- React/Vitest: 96/96 통과
- TypeScript typecheck: 통과
- Neutralino extension syntax check: 통과
- 두 번의 전체 2,000회 실행 manifest: 동일
- 최종 input 24개, output 8개 SHA와 trial·calibrator·거래일 축 의미 검증: 통과
- 원자료·manifest 내 provider credential pattern: 0건

최종 manifest payload SHA-256은 `b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f`다.

## 14. 한계와 보안 조치

- 이 연구는 미래 주가를 보편적으로 맞힌다는 수학적 증명이 아니다. 증명 범위는 수식 성질·구현 반례·동결 표본의 통계적 불확실성이다.
- Toss 단일 공급자의 거래량 조정 계약과 SK하이닉스 공식 교차대조가 부족하다.
- 실제 투자자 취득원가·심리·주문 방향·호가취소·체결비용은 일봉 OHLCV로 식별할 수 없다.
- 120일은 5·10일 비중첩 사건 최소 30건에 구조적으로 부족하다.
- v1.4 lead time은 사건 시작 전 예측이 아니라 목표 장벽까지의 잔여시간이다.
- 4개월 표본은 120일 표본의 부분집합이라 독립 재검정할 수 없다.
- 외부 채택 규칙, global row-weight mapping, PR-AUC·MCC·lead-time 구간, 거래비용 연구가 사전등록에서 완결되지 않았다.
- pseudo-event, 변동성·추세·유동성 matched negative control, regime별 반복, ATR 민감도는 완료되지 않았다.
- 이 대화에 전달된 API 자격증명은 노출된 것으로 간주해 공급자 콘솔에서 즉시 폐기·재발급해야 한다. 연구 산출물과 로그에는 원문 자격증명을 저장하지 않았다.

## 최종 연구 결정

> 기존 고정 가중합과 production 차익실현 구현은 채택하지 않는다. `panic.baseline.drawdown3`을 포함한 가격 전용 기준선도 예측 공식으로 승격하지 않는다. 현재 운영 출력은 `not_identifiable`로 둔다. 다음 연구는 별도 v1.5+ 사전등록 아래 Bayesian HSMM·경쟁위험을 주 도전자, 고정 가중합을 기준선으로 삼고 보지 않은 외부·전향 표본에서 검증한다. OFI·Hawkes는 주문장 원자료가 확보되기 전에는 활성화하지 않는다.
