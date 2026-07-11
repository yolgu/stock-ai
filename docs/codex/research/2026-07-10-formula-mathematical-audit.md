# FOMO·차익실현·패닉셀 수식 및 구현 감사

## 결론

문서에 제시된 원식 가운데 현재 상태 그대로 `validated`로 볼 수 있는 최종 합성식은 없다. 차트 기반 하위 특성 일부는 범위·단위·인과성을 보완하면 일봉 프록시로 검증할 수 있지만, 과거 호가 취소·호가 깊이 변화·aggressor side·OFI가 필요한 원식은 Toss 과거 일봉만으로 식별할 수 없다. 수동 FOMO 점수, 단위가 다른 FOMO 라벨, 항상 0이 되는 과열 항, 범위가 맞지 않는 패닉 통합식은 폐기 대상이다.

현재 앱은 FOMO와 패닉 수식을 구현하지 않았다. 차익실현 구현도 문서의 `PotentialPTP`, `RealizedPTP`, `OverheadSupplyPressure`를 그대로 계산하지 않고, 네 원인을 다시 합산한 별도 앱 내부 지표다. 이 구현에는 표시 산식에 나타나지 않는 점수 하한, 결측 원인의 0점 대체, 가용 입력만 재정규화하는 경로가 있어 보상해킹 위험이 있다.

## 판정 체계

| 판정 | 의미 |
| --- | --- |
| `valid` | 정의역·단위·범위·인과성·결측 계약이 완결됨 |
| `repairable` | 목적은 유지할 수 있으나 수학 또는 상태 계약 수정이 필요함 |
| `proxy_only` | 과거 일봉으로는 원식이 아니라 명시적 프록시만 검증 가능함 |
| `not_identifiable` | 현재 과거 데이터로 입력 또는 정답을 관측할 수 없음 |
| `reject` | 수동 점수, 차원 오류, 항등 오류, 미래 누수 또는 비재현성 때문에 폐기 |

## 공통 수학 계약

검증 후보에 들어가는 각 특성 `x_i(t)`는 유효할 때 `[0,1]`이어야 한다. 합성 점수는

```text
Score_t = 100 × Σ_i w_i x_i(t),  w_i ≥ 0,  Σ_i w_i = 1
```

로만 계산한다. 따라서 모든 입력이 존재하면 볼록결합 성질에 의해 `0 ≤ Score_t ≤ 100`이다. 한 입력이라도 결측이면 해당 시점의 합성 점수는 `unavailable`이며, 남은 가중치를 재정규화하지 않는다.

가격 단위는 분할조정 가격으로 통일한다. 가격 차이는 ATR로, 수익률은 수익률 변동성으로 나누어 무차원화한다. 시점 `t`의 특성은 `t` 종가까지의 값만 사용할 수 있고 `t+1` 이후 값은 정답 라벨에만 쓴다. 분모가 0이거나 lookback이 부족하면 0점이 아니라 결측이다.

## 패닉셀 수식 원장

문서 위치는 `docs/codex/지표/패닉.md` 기준이다.

| 수식군 | 문서 줄 | 판정 | 핵심 감사 결과 |
| --- | ---: | --- | --- |
| `PanicSellEarlyRisk` | 51–65, 642–650 | `not_identifiable` | 가중치 합은 1이지만 과거 bid cancel·depth·spread·OFI가 없어 역사적 재생 불가 |
| `LiquidityWithdrawal` | 76–104 | `not_identifiable` | `SpreadStress`, `BidDepthDrop`, `BidCancelPressure`는 동일 시간대 과거 호가 사건이 필요함 |
| `SellFlowAcceleration` | 124–160 | `not_identifiable` | aggressor side, CVD, OFI 가속도 이력이 필요함 |
| `DownsideBreakPressure` | 172–191 | `proxy_only` | `NearRollingLow`는 일봉화 가능하나 support depth와 VWAP reclaim 실패는 원식 재현 불가 |
| `PriceImpactSensitivity`·`OFI_PriceImpact` | 209–222 | `proxy_only`/`not_identifiable` | 일봉 Amihud형 프록시는 가능, OFI형 원식은 불가; 분모 0 계약 필요 |
| `MarketStress` | 239–243 | `repairable` | 시장 컨텍스트로는 유효하나 선택적 제거 후 동적 재가중은 비교 가능성을 깨뜨림 |
| `PanicSellIntensity` | 254–263, 653–662 | `proxy_only` | 합성 범위는 타당하나 체결·호가 항은 과거 식별 불가; 가격 붕괴 항 중복 가능 |
| `DownMoveImpulse`·`RealizedVol` | 272–281 | `repairable` | 변동성 조정 방향은 타당; `RV=0`, lookback, percentile 모집단을 고정해야 함 |
| `VolumeSurprise` | 293–307 | `repairable` | 동일 시간대 비교는 타당; 기대 거래량과 0거래량 계약 필요 |
| `SellFlowPressure`·`AggSellScore`·`CVDDownScore`·`OFIDownScore` | 316–342 | `not_identifiable` | 과거 aggressor side/OFI 부재. `AggSellScore`는 중립을 0으로 두는 점은 수학적으로 일관됨 |
| `VWAPDownPressure` | 367–380 | `proxy_only` | 두 입력은 `[0,1]`이면 범위가 보장됨; 일봉 rolling VWAP은 장중 VWAP과 다른 프록시 |
| `LiquidityStress` | 398–416 | `not_identifiable` | spread/depth 필요; price impact가 별도 합성항과 중복됨 |
| `BreakdownCascade` | 425–438 | `repairable` | 두 입력이 `[0,1]`이면 범위 보장; rolling low가 현재 봉을 포함하면 자기참조가 되므로 직전 구간만 사용 |
| `PanicSellRelief` | 448–457, 665–674 | `not_identifiable` | 원식 대부분이 과거 flow/orderbook 입력을 요구함 |
| `SellFlowDecay` | 466–472 | `not_identifiable` | 원식의 선행 `SellFlowPressure` 자체가 식별 불가 |
| `CVDDivergence` 이산·연속형 | 489–504 | `not_identifiable` | 과거 CVD와 이전 가격 저점의 대응 규칙이 필요함 |
| `BidReplenishment` 두 형태 | 524–546 | `not_identifiable` | 단일 orderbook snapshot이 아니라 시간축 depth/OFI 이력이 필요함 |
| `FailedBreakdown` 이산·연속형 | 563–579 | `repairable` | 일봉 프록시 가능. 이산형과 연속형은 같은 ID로 덮어쓰지 말고 별도 버전이어야 함 |
| `SpreadNormalization` | 596–602 | `not_identifiable` | 역사적 intraday spread가 필요함 |
| `AbsorptionVolume`·`LowerWickRecovery` | 613–622 | `repairable` | `H=L`이면 분모 0. 1회 아랫꼬리를 완화 확정으로 쓰면 가짜 반등 오탐이 큼 |
| `PanicAvoidScore` | 695–698 | `reject` | 입력이 `[0,100]`이면 이론 범위는 `[-30,100]`; 표의 `0~100` 계약과 불일치 |
| `PanicAbsorptionScore` | 713–717 | `reject` | 0–100 점수와 0–1 `BidReplenishment`를 직접 더해 스케일이 불일치 |
| `ChartPanicSell`·`LiquidityProxy` | 762–779 | `proxy_only` | 이번 일봉 연구의 주 후보. price/volume 붕괴를 여러 항에서 중복 집계하는지 비교 필요 |
| `FullPanicSell`·`TossPanicSellRisk` | 788–792, 874–878 | `reject` | `0.35E+0.45I-0.20R`의 범위는 `[-20,80]`, 0–100 위험점수가 아님 |
| 상태표 | 678–685 | `reject` | `Early=50, Intensity=30` 같은 입력은 어느 상태에도 속하지 않으며 relief/fake-relief 조건은 서로 겹칠 수 있음 |

### 패닉 최소 반례

1. `E=I=0, R=100`이면 `FullPanicSell=-20`이다.
2. `E=I=R=100`이면 `FullPanicSell=60`이다. 모든 위험 입력이 최대인데도 100이 아니다.
3. `Early=50, Intensity=30`은 Normal도 Pre-Panic도 아니어서 상태 완전성이 깨진다.
4. `Intensity=80, Relief=62`이고 매도 압력이 재상승하면 `Capitulation Watch`와 `Fake Relief Risk`가 동시에 참일 수 있다.

## 차익실현 수식 원장

문서 위치는 `docs/codex/지표/차익실현.md` 기준이다. 앞부분의 초안과 384줄 이후 개선안을 별도 버전으로 취급하며, 서로 섞지 않는다.

| 수식군 | 문서 줄 | 판정 | 핵심 감사 결과 |
| --- | ---: | --- | --- |
| `ProfitLongRatio` | 17–26, 252–254 | `proxy_only` | `[0,1]` 범위는 증명되지만 과거 거래량은 현재 생존 보유량이 아님 |
| `WeightedProfitPressure` | 43–45 | `proxy_only` | 무차원 가중 평균이나 상한이 없고 보유자 원가로 해석할 수 없음 |
| `ATR_Adjusted_ProfitPressure` 두 형태 | 75–90 | `repairable` | 가격차/ATR 또는 수익률/ATR%는 무차원. ATR=0 계약 필요 |
| `VWAP_ProfitPressure`·결합형 | 109–125 | `proxy_only` | 장중 평균가 프록시이며 실제 매도 의도를 뜻하지 않음 |
| `SellPressure`·`TradeImbalance` | 143–152 | `not_identifiable` | Toss 과거 일봉에는 aggressor side가 없음 |
| 곱셈형 `RealizedProfitTakingPressure` | 157–161 | `not_identifiable` | 한 결측 또는 0이 전체를 죽임. 문서 후반도 분리 출력을 권고함 |
| `OBI`·`Orderbook_ProfitTakingPressure` | 172–184 | `not_identifiable` | 역사적 호가 snapshot/변화가 없고 spoofing을 구분하지 못함 |
| `CGO`·정규화 CGO | 203–220 | `repairable` | 개념은 타당하지만 `RP` 추정, turnover 정의, 임계값 0.15가 데이터 전에 고정돼야 함 |
| 초안 `ProfitTakingPressureScore` | 239–274 | `repairable` | 입력을 `[0,1]`로 고정하면 0–100. 후반 개선안과 가중치·중립점이 충돌함 |
| `SimpleProfitTakingPressure` | 293–295 | `proxy_only` | 두 프록시를 곱해 원인 분리가 사라짐 |
| `DailyProxyProfitTakingPressure` | 300–302 | `reject` | `100×max((C−VWAP)/ATR,0)`은 상한이 없어 0–100 점수가 아님 |
| `RP`·`Survival`·`CGO` | 391–403 | `repairable` | `Turnover>1` 방지, 생존곱 인덱스, lookback, 분모 0을 명시해야 함 |
| `ProfitBreadth`·`ProfitGainMass`·`VWAP_Extension` | 419–432 | `proxy_only` | 일봉 거래량 프록시로 계산 가능하나 실제 보유물량과 구분해야 함 |
| `PotentialPTP` | 435–441 | `proxy_only` | 입력 clamp와 가중치 합으로 0–100 범위가 증명됨; 이번 연구의 일봉 후보 |
| `SellOFI`·`AggressiveSellRatio`·`AskBookPressure` | 452–464 | `not_identifiable` | 역사적 flow/orderbook 필요 |
| `RealizedPTP` | 467–473 | `not_identifiable` | `AggressiveSellRatio=0.5` 중립이어도 15점을 기여해 앞부분의 중립 0 정의와 충돌 |
| `PTP_Final` | 478–481 | `not_identifiable` | 두 하위 점수가 모두 관측될 때만 해석 가능; 결측 시 재정규화 금지 |
| `OverheadSupplyPressure` | 492–508 | `proxy_only` | 0–100 범위는 증명되지만 차익실현이 아니라 본전·손실축소 매도 원인 |
| 문서의 MU 수동 산출 | 514–569 | `reject` | 웹 스냅샷·프록시 범위·수동 민감도 값은 사전등록 반복표본 성능 증거가 아님 |

## FOMO 수식 원장

문서 위치는 `docs/codex/지표/포모.md` 기준이다. 1–320줄의 수동 종합점수는 폐기하고 394줄 이후의 차트·flow 분리 구조만 후보 원천으로 쓴다.

| 수식군 | 문서 줄 | 판정 | 핵심 감사 결과 |
| --- | ---: | --- | --- |
| `norm` | 50–53 | `repairable` | `high=low`일 때 미정의; 고정 임계값보다 train-only percentile 사용 |
| `ASVI` | 58–60 | `not_identifiable` | Toss OHLCV 범위 밖. `SVI=0`이면 로그도 미정의 |
| `VolumePace` | 73–76 | `repairable` | 예상 장중 누적비율 0과 동일 시간대 모집단 계약 필요 |
| `CallShare`·`PutCallRatio` | 87–94 | `not_identifiable` | 이번 Toss 일봉 원장에는 옵션 flow가 없음 |
| `StockFOMO_Potential`·`BuyFlowConfirm`·`StockFOMO_Final` | 111–134 | `reject`/`not_identifiable` | 수동 Attention/상대강도 점수와 결측 flow를 혼합 |
| MU `57점` 산출 | 152–181, 255–309 | `reject` | 산식 없는 수동 점수가 결론을 만든 보상해킹 예시이며 문서도 762–775줄에서 이를 인정 |
| `PercentileRank` | 418–420 | `repairable` | 과거만 사용, midrank, 60–252 세션, 동일값·결측 계약을 고정해야 함 |
| `ReturnImpulse` | 429–433 | `repairable` | 변동성 0 처리 필요; 양의 추격만 보려면 음수 부분의 방향을 명시해야 함 |
| `ReturnAccel`·`PriceAccel` | 448–459 | `repairable`/`reject` | 수익률 가속은 가능; 가격 2차차분은 통화·분할 스케일에 민감해 폐기 |
| `VolumeSurprise` | 468–476 | `repairable` | 동일 시간대 percentile 원칙은 타당 |
| `CloseLocation`·`BreakoutStrength`·`RangeChaseScore` | 487–500 | `repairable` | `High=Low`, ATR=0 계약 필요. 가격 위치 항끼리 중복 가능 |
| `VWAP_Extension`·`VWAP_Persistence` | 518–525 | `proxy_only` | 장중 원식은 과거 분봉이 필요; 일봉 rolling VWAP은 명시적 프록시 |
| `PullbackHold` | 541–543 | `repairable` | ATR=0 처리 후 `[0,1]` 범위 보장 |
| `ChartFOMO` | 560–569 | `proxy_only` | 가중치 합 1로 범위는 증명됨; 문서·동일가중·중복제거 가중치를 경쟁시킴 |
| `AggBuyRatio`·`CVD`·`CVD_Slope`·`CVD_Accel` | 592–618 | `not_identifiable` | 과거 aggressor side가 없음 |
| `OFI`·`OFI_Score` | 629–641 | `not_identifiable` | 시간축 호가 사건·depth가 필요함 |
| `OBI`·`OBI_Score` | 648–656 | `not_identifiable` | 역사적 orderbook snapshot이 없음 |
| `FlowFOMO` | 665–675 | `not_identifiable` | 핵심 입력이 없으면 계산하지 않는다는 문서 규칙은 타당 |
| `FOMO_Intensity` 두 형태 | 684–694 | `repairable` | Flow 결측 때 Chart만 쓰면 동일 이름 점수의 의미가 바뀜; 별도 모델 ID가 필요 |
| `SpreadRisk`·`SlippageRisk` | 699–706 | `not_identifiable` | 역사적 체결비용 입력이 없음 |
| `ExhaustionRisk` | 709–712 | `reject` | `CVD_AccelScore∈[0,1]`이면 `max(-score,0)=0`이어서 두 번째 항이 항상 사라짐 |
| `FOMO_Tradability` | 715–720 | `reject` | 위험 입력이 0–1이면 이론 범위 `[-35,100]`; 0–100이면 감산 스케일이 붕괴함 |
| `ContinuationLabel` | 812–816 | `reject` | `FutureMaxReturn`은 무차원인데 `ATR_h`는 가격 단위로 읽혀 차원이 맞지 않음 |
| `ExhaustionLabel` | 829–834 | `repairable` | 미래 라벨 용도는 가능하나 VWAP 시점·wick 임계값·first-passage 충돌 규칙이 미정 |
| `TradableLabel` | 847–851 | `not_identifiable` | 역사적 spread/slippage 비용이 없어 일봉 연구에서 증명 불가 |

### FOMO 최소 반례

1. `CVD_AccelScore=0.8`이면 `max(-0.8,0)=0`; 가속 감속 위험이 전혀 반영되지 않는다.
2. `FOMO_Intensity=0`, 세 위험이 모두 1이면 `FOMO_Tradability=-35`다.
3. 가격 단위가 달러에서 센트로 100배 바뀌면 `PriceAccel`도 100배가 되므로 분할·통화 불변성이 없다.
4. `RollingHigh=RollingLow`이면 `CloseLocation`의 분모가 0이다.

## 문서식과 현재 구현의 대응

구현 위치는 `extensions/app/quant-indicators.cjs`다.

| 구현 경로 | 코드 줄 | 문서 등가성 | 판정 |
| --- | ---: | --- | --- |
| `calculateProfitTakingPressure` | 437–485 | 문서 하위 원인을 다시 35/30/25/10으로 합산한 앱 독자식 | `non_equivalent` |
| `calculateProfitBurdenCause` | 488–503 | 후반 `PotentialPTP` 45/35/20과 일치 | `proxy_only` |
| `calculateRealizedSellPressureCause` | 505–530 | `SellOFI` 대신 tick-rule sell pressure 사용, 가용항 재정규화 | `non_equivalent` |
| `calculateOverheadSupplyPressureCause` | 532–546 | 후반 60/40 식과 구조상 일치 | `proxy_only` |
| `calculateLiquidityImpactRiskCause` | 548–572 | 문서의 별도 유동성 위험을 새 합성 원인으로 추가 | `app_specific` |
| `calculateProfitTakingRiskScore` | 574–594 | 선형식 뒤 숨은 75·65점 하한 적용 | `reward_hacking_risk` |
| `calculateDirectionalTradeFlow` | 679–730 | 실제 side가 아니라 가격 상승/하락 tick rule; 동일가 체결은 버림 | `estimated_only` |
| `calculateWeightedComponentScore` | 871–886 | 가용항만으로 가중치 재정규화 | `missingness_distortion` |
| `calculateRiskReward` | 892–922 | 목표가를 항상 `current+2ATR` 이상으로 강제해 비율이 항상 2 이상 | `dead_branch` |
| `calculateMarketSentimentScore`→`calculateIntradayTradeScore` | 1146–1210 | danger가 하나면 64로 cap한 뒤 sigmoid가 약 80.2를 만들어 “강함” 가능 | `semantic_reversal` |
| `selectSignals` | 1296–1315 | 정상 경로에서 실제 심각도와 무관하게 첫 3개만 표시 | `explanation_selection_bias` |
| `createProfitTakingPressureTrace` | 1969–2008 | 선형 대입식만 표시하고 숨은 하한을 표시하지 않음 | `explanation_mismatch` |

## 구현 보상해킹 반례

1. 원인 점수가 `profitBurden=55`, `realized=70`, `overhead=50`, `liquidity=50`이면 표시 선형합은 `61.75→62`지만 실제 반환은 최소 75다.
2. 어떤 단일 원인이 85 이상이면 선형합이 낮아도 최소 65가 된다.
3. `target=max(priorHigh,current+2ATR)`이므로 `(target-current)/ATR≥2`; warning과 danger 분기는 도달하지 않는다.
4. `readCauseScore`는 결측 원인을 0으로 바꾸고, 하위 합성기는 남은 입력을 재정규화한다. 같은 점수라도 어떤 데이터가 없었는지에 따라 의미가 달라진다.
5. 과거 시점 필터가 없어 동일 시점 계산에 미래 캔들을 추가하면 VWAP·volume profile·결정이 바뀔 수 있다.

## 이번 반복표본 연구에 남기는 후보

원식의 역사적 미시구조 성능을 일봉 프록시 성능으로 위장하지 않는다. 검증 후보는 다음처럼 분리한다.

| 상태 | 문서 후보 | 수정 후보 | 단순 기준선 |
| --- | --- | --- | --- |
| FOMO 지속·과열 | `ChartFOMO` 24/16/22/16/14/8 | 가격 중복 축소 30/10/25/15/10/10, 동일가중 | 5일 모멘텀, 거래량, 20일 고점 돌파 |
| 패닉 시작·지속 | `ChartPanicSell` 30/25/20/15/10 | 붕괴 중복 축소 30/25/20/10/15, 동일가중 | 3일 drawdown, 거래량, 20일 저점 이탈 |
| 잠재 차익실현형 하락 | `PotentialPTP` 45/35/20 | breadth 강화 50/30/20, 동일가중 | 20일 run-up, VWAP/ATR 이격 |
| 완화·가짜 완화 | 1회 반등 프록시 | 2회 종가 지속+재저점 부재 gate | 단일 반등 |

과거 호가·체결 원식은 모두 `not_identifiable`로 남기고, 향후 append-only 분봉·체결·호가 수집이 쌓인 뒤 별도 전향 연구로 검증한다.
