# FOMO·패닉셀·차익실현 완전 수식 원장 및 등가성 감사

## 완료 판정

- 기계판독 수식/변형: 224
- 문서 내 자동 탐지 수식 선언: 172
- 명시적 비수식 제외: 17
- 누락 수식 선언: 0
- 누락 증명 의무: 0
- 잘못된 위치 참조: 0
- 검증 오류: 0

판정 분포: `not_identifiable` 70, `proxy_only` 74, `reject` 30, `repairable` 32, `valid` 18

## 핵심 결론

- 원문 수식은 문서의 각 코드 선언 단위로 개별 ID와 버전을 부여했습니다.
- `fomo.documented`와 `panic.documented`는 원문 입력식과 같지 않으므로, 일봉 repaired proxy로 분리했습니다.
- production PTP는 원문이나 일봉 연구식과 동치가 아니며 숨은 하한·미래 timestamp·결측 재가중 반례를 보존했습니다.
- 식별 불가능한 과거 flow/order-book 식은 0점 대체 없이 `not_identifiable`로 유지합니다.

## 주요 비동치·보상해킹 반례

| 수식 ID | 판정 | 핵심 증거 |
| --- | --- | --- |
| `fomo.return_impulse.daily_proxy.v1` | `proxy_only` | The daily formula is separately identified from the intraday document formula. |
| `fomo.return_acceleration.daily_proxy.v1` | `proxy_only` | The daily formula is separately identified from the intraday document formula. |
| `panic.liquidity_proxy.daily_proxy.v1` | `proxy_only` | The daily formula is separately identified from the intraday document formula. |
| `fomo.chart_fomo.documented_weights_daily_proxy.v1` | `proxy_only` | Document weights are preserved where named, but intraday inputs are repaired or replaced by explicitly daily proxies. |
| `panic.chart_panic.documented_weights_daily_proxy.v1` | `proxy_only` | Document weights are preserved where named, but intraday inputs are repaired or replaced by explicitly daily proxies. |
| `ptp.production.hidden_floor_score.v1` | `reject` | Cause scores 100,3,0,56 give displayed linear score 42 but production returns 65. |
| `ptp.production.unbounded_asof_input.v1` | `reject` | At as-of 09:34, appending a 09:36 candle changed VWAP from 101.0000 to 498.8066. |
| `ptp.production.missing_reweight.v1` | `reject` | The production path is an app-specific formula rather than the documented PotentialPTP/RealizedPTP system. |
| `ptp.production.risk_reward_dead_branch.v1` | `reject` | The production path is an app-specific formula rather than the documented PotentialPTP/RealizedPTP system. |
| `ptp.production.input_order_dependency.v1` | `reject` | volumeExpansion changed from 1.00 to 0.13 after reversing the same candle set. |
| `ptp.production.duplicate_timestamp_dependency.v1` | `reject` | VWAP changed from 109.0000 to 108.1818 after duplicating one candle timestamp. |
| `ptp.production.split_sensitive_cvd.v1` | `reject` | The same flow changed from CVD 10/neutral to CVD 100/positive. |

## 전체 수식 인덱스

| ID | 버전 | 이름 | 판정 | 문서/구현 위치 |
| --- | --- | --- | --- | --- |
| `fomo.aggbuyratio_h.documented_l592.v1` | `1.0.0` | `AggBuyRatio_h` | `not_identifiable` | docs/codex/지표/포모.md:592 |
| `fomo.aggbuyscore_h.documented_l597.v1` | `1.0.0` | `AggBuyScore_h` | `not_identifiable` | docs/codex/지표/포모.md:597 |
| `fomo.asvi_t.documented_l58.v1` | `1.0.0` | `ASVI_t` | `not_identifiable` | docs/codex/지표/포모.md:58 |
| `fomo.attentionscore.documented_l769.v1` | `1.0.0` | `AttentionScore` | `reject` | docs/codex/지표/포모.md:769 |
| `fomo.breakoutstrength_n.documented_l492.v1` | `1.0.0` | `BreakoutStrength_n` | `repairable` | docs/codex/지표/포모.md:492 |
| `fomo.buyflowconfirm.documented_l124.v1` | `1.0.0` | `BuyFlowConfirm` | `not_identifiable` | docs/codex/지표/포모.md:124 |
| `fomo.callshare.documented_l87.v1` | `1.0.0` | `CallShare` | `not_identifiable` | docs/codex/지표/포모.md:87 |
| `fomo.chart_fomo.documented_weights_daily_proxy.v1` | `1.4.0` | `fomo.documented` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.documented |
| `fomo.chartfomo.documented_l560.v1` | `1.0.0` | `ChartFOMO` | `proxy_only` | docs/codex/지표/포모.md:560, CandidateRegistry.fomo.documented |
| `fomo.closelocation_n.documented_l487.v1` | `1.0.0` | `CloseLocation_n` | `repairable` | docs/codex/지표/포모.md:487 |
| `fomo.continuationlabel.documented_l812.v1` | `1.0.0` | `ContinuationLabel_{t,h}` | `reject` | docs/codex/지표/포모.md:812 |
| `fomo.cvd_accel_h.documented_l616.v1` | `1.0.0` | `CVD_Accel_h` | `not_identifiable` | docs/codex/지표/포모.md:616 |
| `fomo.cvd_slope_h.documented_l611.v1` | `1.0.0` | `CVD_Slope_h` | `not_identifiable` | docs/codex/지표/포모.md:611 |
| `fomo.cvd_t.documented_l606.v1` | `1.0.0` | `CVD_t` | `not_identifiable` | docs/codex/지표/포모.md:606 |
| `fomo.exhaustionlabel.documented_l829.v1` | `1.0.0` | `ExhaustionLabel_{t,h}` | `repairable` | docs/codex/지표/포모.md:829 |
| `fomo.exhaustionrisk.documented_l709.v1` | `1.0.0` | `ExhaustionRisk` | `reject` | docs/codex/지표/포모.md:709 |
| `fomo.flowfomo.documented_l665.v1` | `1.0.0` | `FlowFOMO` | `not_identifiable` | docs/codex/지표/포모.md:665 |
| `fomo.fomo.documented_l22.v1` | `1.0.0` | `FOMO` | `not_identifiable` | docs/codex/지표/포모.md:22 |
| `fomo.fomo_intensity.documented_l684.v1` | `1.0.0` | `FOMO_Intensity` | `repairable` | docs/codex/지표/포모.md:684 |
| `fomo.fomo_intensity.documented_l692.v1` | `1.0.1` | `FOMO_Intensity` | `repairable` | docs/codex/지표/포모.md:692 |
| `fomo.fomo_potential.documented_l247.v1` | `1.0.0` | `FOMO_Potential` | `reject` | docs/codex/지표/포모.md:247 |
| `fomo.fomo_tradability.documented_l715.v1` | `1.0.0` | `FOMO_Tradability` | `reject` | docs/codex/지표/포모.md:715 |
| `fomo.intradaychasequalityscore.documented_l772.v1` | `1.0.0` | `IntradayChaseQualityScore` | `reject` | docs/codex/지표/포모.md:772 |
| `fomo.marketriskappetitescore.documented_l770.v1` | `1.0.0` | `MarketRiskAppetiteScore` | `reject` | docs/codex/지표/포모.md:770 |
| `fomo.norm.documented_l51.v1` | `1.0.0` | `norm` | `repairable` | docs/codex/지표/포모.md:51 |
| `fomo.obi_k.documented_l648.v1` | `1.0.0` | `OBI_k` | `not_identifiable` | docs/codex/지표/포모.md:648 |
| `fomo.obi_score.documented_l654.v1` | `1.0.0` | `OBI_Score` | `not_identifiable` | docs/codex/지표/포모.md:654 |
| `fomo.ofi_score_h.documented_l639.v1` | `1.0.0` | `OFI_Score_h` | `not_identifiable` | docs/codex/지표/포모.md:639 |
| `fomo.ofi_t.documented_l629.v1` | `1.0.0` | `OFI_t` | `not_identifiable` | docs/codex/지표/포모.md:629 |
| `fomo.percentilerank_t.documented_l418.v1` | `1.0.0` | `PercentileRank_t` | `repairable` | docs/codex/지표/포모.md:418 |
| `fomo.priceaccel_t.documented_l457.v1` | `1.0.0` | `PriceAccel_t` | `reject` | docs/codex/지표/포모.md:457 |
| `fomo.pullbackhold_n.documented_l541.v1` | `1.0.0` | `PullbackHold_n` | `repairable` | docs/codex/지표/포모.md:541 |
| `fomo.putcallratio.documented_l92.v1` | `1.0.0` | `PutCallRatio` | `not_identifiable` | docs/codex/지표/포모.md:92 |
| `fomo.rangechasescore.documented_l497.v1` | `1.0.0` | `RangeChaseScore` | `repairable` | docs/codex/지표/포모.md:497 |
| `fomo.relativestrengthscore.documented_l771.v1` | `1.0.0` | `RelativeStrengthScore` | `reject` | docs/codex/지표/포모.md:771 |
| `fomo.return_acceleration.daily_proxy.v1` | `1.4.0` | `returnAccel` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.returnAccel |
| `fomo.return_impulse.daily_proxy.v1` | `1.4.0` | `returnImpulse` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.returnImpulse |
| `fomo.returnaccel_h.documented_l448.v1` | `1.0.0` | `ReturnAccel_h` | `repairable` | docs/codex/지표/포모.md:448, DailyFeatureEngine.returnAccel |
| `fomo.returnimpulse_h.documented_l429.v1` | `1.0.0` | `ReturnImpulse_h` | `repairable` | docs/codex/지표/포모.md:429, DailyFeatureEngine.returnImpulse |
| `fomo.slippagerisk.documented_l704.v1` | `1.0.0` | `SlippageRisk` | `not_identifiable` | docs/codex/지표/포모.md:704 |
| `fomo.spreadrisk.documented_l699.v1` | `1.0.0` | `SpreadRisk` | `not_identifiable` | docs/codex/지표/포모.md:699 |
| `fomo.stockfomo_final.documented_l131.v1` | `1.0.0` | `StockFOMO_Final` | `reject` | docs/codex/지표/포모.md:131 |
| `fomo.stockfomo_potential.documented_l111.v1` | `1.0.0` | `StockFOMO_Potential` | `reject` | docs/codex/지표/포모.md:111 |
| `fomo.stockfomo_potential.documented_l167.v1` | `1.0.1` | `StockFOMO_Potential` | `reject` | docs/codex/지표/포모.md:167 |
| `fomo.tradablelabel.documented_l847.v1` | `1.0.0` | `TradableLabel_{t,h}` | `not_identifiable` | docs/codex/지표/포모.md:847 |
| `fomo.volumepace.documented_l73.v1` | `1.0.0` | `VolumePace` | `repairable` | docs/codex/지표/포모.md:73 |
| `fomo.volumepace_h.documented_l468.v1` | `1.0.0` | `VolumePace_h` | `repairable` | docs/codex/지표/포모.md:468 |
| `fomo.volumesurprise_h.documented_l474.v1` | `1.0.0` | `VolumeSurprise_h` | `repairable` | docs/codex/지표/포모.md:474, DailyFeatureEngine.volumeSurprise |
| `fomo.vwap_extension.documented_l518.v1` | `1.0.0` | `VWAP_Extension` | `proxy_only` | docs/codex/지표/포모.md:518, DailyFeatureEngine.vwapExtension |
| `fomo.vwap_persistence_h.documented_l523.v1` | `1.0.0` | `VWAP_Persistence_h` | `proxy_only` | docs/codex/지표/포모.md:523 |
| `panic.absorptionvolume_t.documented_l613.v1` | `1.0.0` | `AbsorptionVolume_t` | `proxy_only` | docs/codex/지표/패닉.md:613 |
| `panic.aggsellaccel_t.documented_l137.v1` | `1.0.0` | `AggSellAccel_t` | `not_identifiable` | docs/codex/지표/패닉.md:137 |
| `panic.aggsellratio_t.documented_l131.v1` | `1.0.0` | `AggSellRatio_t` | `not_identifiable` | docs/codex/지표/패닉.md:131 |
| `panic.aggsellscore_t.documented_l323.v1` | `1.0.0` | `AggSellScore_t` | `not_identifiable` | docs/codex/지표/패닉.md:323 |
| `panic.bidcancelpressure_t.documented_l100.v1` | `1.0.0` | `BidCancelPressure_t` | `not_identifiable` | docs/codex/지표/패닉.md:100 |
| `panic.biddepthdrop_t.documented_l93.v1` | `1.0.0` | `BidDepthDrop_t` | `not_identifiable` | docs/codex/지표/패닉.md:93 |
| `panic.biddepthrecovery_t.documented_l539.v1` | `1.0.0` | `BidDepthRecovery_t` | `not_identifiable` | docs/codex/지표/패닉.md:539 |
| `panic.bidreplenishment_t.documented_l524.v1` | `1.0.0` | `BidReplenishment_t` | `not_identifiable` | docs/codex/지표/패닉.md:524 |
| `panic.bidreplenishment_t.documented_l533.v1` | `1.0.1` | `BidReplenishment_t` | `not_identifiable` | docs/codex/지표/패닉.md:533 |
| `panic.breakdowncascade_t.documented_l435.v1` | `1.0.0` | `BreakdownCascade_t` | `repairable` | docs/codex/지표/패닉.md:435, DailyFeatureEngine.breakdownCascade |
| `panic.breakdownstrength_t.documented_l425.v1` | `1.0.0` | `BreakdownStrength_t` | `repairable` | docs/codex/지표/패닉.md:425 |
| `panic.chart_panic.documented_weights_daily_proxy.v1` | `1.4.0` | `panic.documented` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.documented |
| `panic.chartpanicsell_t.documented_l762.v1` | `1.0.0` | `ChartPanicSell_t` | `proxy_only` | docs/codex/지표/패닉.md:762, CandidateRegistry.panic.documented |
| `panic.cvd_slope_t.documented_l328.v1` | `1.0.0` | `CVD_Slope_t` | `not_identifiable` | docs/codex/지표/패닉.md:328 |
| `panic.cvd_t.documented_l144.v1` | `1.0.0` | `CVD_t` | `not_identifiable` | docs/codex/지표/패닉.md:144 |
| `panic.cvddivergence_t.documented_l489.v1` | `1.0.0` | `CVDDivergence_t` | `not_identifiable` | docs/codex/지표/패닉.md:489 |
| `panic.cvddivergence_t.documented_l498.v1` | `1.0.1` | `CVDDivergence_t` | `not_identifiable` | docs/codex/지표/패닉.md:498 |
| `panic.cvddownaccel_t.documented_l149.v1` | `1.0.0` | `CVDDownAccel_t` | `not_identifiable` | docs/codex/지표/패닉.md:149 |
| `panic.cvddownscore_t.documented_l333.v1` | `1.0.0` | `CVDDownScore_t` | `not_identifiable` | docs/codex/지표/패닉.md:333 |
| `panic.depthstress_t.documented_l405.v1` | `1.0.0` | `DepthStress_t` | `not_identifiable` | docs/codex/지표/패닉.md:405 |
| `panic.downmoveimpulse_t.documented_l272.v1` | `1.0.0` | `DownMoveImpulse_t` | `repairable` | docs/codex/지표/패닉.md:272, DailyFeatureEngine.downMoveImpulse |
| `panic.downsidebreakpressure_t.documented_l172.v1` | `1.0.0` | `DownsideBreakPressure_t` | `proxy_only` | docs/codex/지표/패닉.md:172 |
| `panic.failedbreakdown_t.documented_l563.v1` | `1.0.0` | `FailedBreakdown_t` | `repairable` | docs/codex/지표/패닉.md:563 |
| `panic.failedbreakdown_t.documented_l573.v1` | `1.0.1` | `FailedBreakdown_t` | `repairable` | docs/codex/지표/패닉.md:573 |
| `panic.failedvwapreclaim_t.documented_l189.v1` | `1.0.0` | `FailedVWAPReclaim_t` | `not_identifiable` | docs/codex/지표/패닉.md:189 |
| `panic.fullpanicsell_t.documented_l788.v1` | `1.0.0` | `FullPanicSell_t` | `reject` | docs/codex/지표/패닉.md:788 |
| `panic.liquidity_proxy.daily_proxy.v1` | `1.4.0` | `liquidityProxy` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.liquidityProxy |
| `panic.liquidityproxy_t.documented_l775.v1` | `1.0.0` | `LiquidityProxy_t` | `proxy_only` | docs/codex/지표/패닉.md:775, DailyFeatureEngine.liquidityProxy |
| `panic.liquiditystress_t.documented_l398.v1` | `1.0.0` | `LiquidityStress_t` | `not_identifiable` | docs/codex/지표/패닉.md:398 |
| `panic.liquiditywithdrawal_t.documented_l76.v1` | `1.0.0` | `LiquidityWithdrawal_t` | `not_identifiable` | docs/codex/지표/패닉.md:76 |
| `panic.lowerlowcount_t.documented_l430.v1` | `1.0.0` | `LowerLowCount_t` | `repairable` | docs/codex/지표/패닉.md:430 |
| `panic.lowerwickrecovery_t.documented_l620.v1` | `1.0.0` | `LowerWickRecovery_t` | `proxy_only` | docs/codex/지표/패닉.md:620 |
| `panic.marketstress_t.documented_l239.v1` | `1.0.0` | `MarketStress_t` | `repairable` | docs/codex/지표/패닉.md:239 |
| `panic.nearrollinglow_t.documented_l179.v1` | `1.0.0` | `NearRollingLow_t` | `proxy_only` | docs/codex/지표/패닉.md:179 |
| `panic.ofi_priceimpact_t.documented_l218.v1` | `1.0.0` | `OFI_PriceImpact_t` | `not_identifiable` | docs/codex/지표/패닉.md:218 |
| `panic.ofidownaccel_t.documented_l156.v1` | `1.0.0` | `OFIDownAccel_t` | `not_identifiable` | docs/codex/지표/패닉.md:156 |
| `panic.ofidownscore_t.documented_l338.v1` | `1.0.0` | `OFIDownScore_t` | `not_identifiable` | docs/codex/지표/패닉.md:338 |
| `panic.panicabsorptionscore_t.documented_l713.v1` | `1.0.0` | `PanicAbsorptionScore_t` | `reject` | docs/codex/지표/패닉.md:713 |
| `panic.panicavoidscore_t.documented_l695.v1` | `1.0.0` | `PanicAvoidScore_t` | `reject` | docs/codex/지표/패닉.md:695 |
| `panic.paniccontinuationlabel.documented_l856.v1` | `1.0.0` | `PanicContinuationLabel` | `not_identifiable` | docs/codex/지표/패닉.md:856 |
| `panic.panicexhaustionlabel.documented_l857.v1` | `1.0.0` | `PanicExhaustionLabel` | `not_identifiable` | docs/codex/지표/패닉.md:857 |
| `panic.panicsellearlyrisk_t.documented_l57.v1` | `1.0.0` | `PanicSellEarlyRisk_t` | `not_identifiable` | docs/codex/지표/패닉.md:57 |
| `panic.panicsellearlyrisk_t.documented_l642.v1` | `1.0.1` | `PanicSellEarlyRisk_t` | `not_identifiable` | docs/codex/지표/패닉.md:642 |
| `panic.panicsellintensity_t.documented_l254.v1` | `1.0.0` | `PanicSellIntensity_t` | `proxy_only` | docs/codex/지표/패닉.md:254 |
| `panic.panicsellintensity_t.documented_l653.v1` | `1.0.1` | `PanicSellIntensity_t` | `proxy_only` | docs/codex/지표/패닉.md:653 |
| `panic.panicsellrelief_t.documented_l448.v1` | `1.0.0` | `PanicSellRelief_t` | `not_identifiable` | docs/codex/지표/패닉.md:448 |
| `panic.panicsellrelief_t.documented_l665.v1` | `1.0.1` | `PanicSellRelief_t` | `not_identifiable` | docs/codex/지표/패닉.md:665 |
| `panic.positiveofirecovery_t.documented_l544.v1` | `1.0.0` | `PositiveOFIRecovery_t` | `not_identifiable` | docs/codex/지표/패닉.md:544 |
| `panic.priceimpactsensitivity_t.documented_l209.v1` | `1.0.0` | `PriceImpactSensitivity_t` | `proxy_only` | docs/codex/지표/패닉.md:209 |
| `panic.priceimpactstress_t.documented_l412.v1` | `1.0.0` | `PriceImpactStress_t` | `not_identifiable` | docs/codex/지표/패닉.md:412 |
| `panic.realizedvol_h.documented_l279.v1` | `1.0.0` | `RealizedVol_h` | `repairable` | docs/codex/지표/패닉.md:279 |
| `panic.sellflowacceleration_t.documented_l124.v1` | `1.0.0` | `SellFlowAcceleration_t` | `not_identifiable` | docs/codex/지표/패닉.md:124 |
| `panic.sellflowdecay_t.documented_l466.v1` | `1.0.0` | `SellFlowDecay_t` | `not_identifiable` | docs/codex/지표/패닉.md:466 |
| `panic.sellflowpressure_t.documented_l316.v1` | `1.0.0` | `SellFlowPressure_t` | `not_identifiable` | docs/codex/지표/패닉.md:316 |
| `panic.spreadnormalization_t.documented_l596.v1` | `1.0.0` | `SpreadNormalization_t` | `not_identifiable` | docs/codex/지표/패닉.md:596 |
| `panic.spreadpct_t.documented_l88.v1` | `1.0.0` | `SpreadPct_t` | `not_identifiable` | docs/codex/지표/패닉.md:88 |
| `panic.spreadstress_t.documented_l83.v1` | `1.0.0` | `SpreadStress_t` | `not_identifiable` | docs/codex/지표/패닉.md:83 |
| `panic.state_partition.documented_l678.v1` | `1.0.0` | `PanicStateTable` | `reject` | docs/codex/지표/패닉.md:678-685 |
| `panic.supportthinness_t.documented_l184.v1` | `1.0.0` | `SupportThinness_t` | `not_identifiable` | docs/codex/지표/패닉.md:184 |
| `panic.tosspanicsellrisk_t.documented_l874.v1` | `1.0.0` | `TossPanicSellRisk_t` | `reject` | docs/codex/지표/패닉.md:874 |
| `panic.tosspanicsellsystem.documented_l18.v1` | `1.0.0` | `TossPanicSellSystem` | `not_identifiable` | docs/codex/지표/패닉.md:18 |
| `panic.tradabilitylabel.documented_l858.v1` | `1.0.0` | `TradabilityLabel` | `not_identifiable` | docs/codex/지표/패닉.md:858 |
| `panic.volumesurprise_t.documented_l293.v1` | `1.0.0` | `VolumeSurprise_t` | `repairable` | docs/codex/지표/패닉.md:293 |
| `panic.vwap_downextension_t.documented_l367.v1` | `1.0.0` | `VWAP_DownExtension_t` | `proxy_only` | docs/codex/지표/패닉.md:367 |
| `panic.vwap_downpersistence_t.documented_l372.v1` | `1.0.0` | `VWAP_DownPersistence_t` | `proxy_only` | docs/codex/지표/패닉.md:372 |
| `panic.vwapdownpressure_t.documented_l377.v1` | `1.0.0` | `VWAPDownPressure_t` | `proxy_only` | docs/codex/지표/패닉.md:377, DailyFeatureEngine.vwapDownPressure |
| `ptp.aggressivesellratio.documented_l457.v1` | `1.0.0` | `AggressiveSellRatio` | `not_identifiable` | docs/codex/지표/차익실현.md:457 |
| `ptp.askbookpressure.documented_l267.v1` | `1.0.0` | `AskBookPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:267 |
| `ptp.askbookpressure.documented_l462.v1` | `1.0.1` | `AskBookPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:462 |
| `ptp.atr_adjusted_profitpressure.documented_l75.v1` | `1.0.0` | `ATR_Adjusted_ProfitPressure` | `repairable` | docs/codex/지표/차익실현.md:75 |
| `ptp.atr_adjusted_profitpressure.documented_l82.v1` | `1.0.1` | `ATR_Adjusted_ProfitPressure` | `repairable` | docs/codex/지표/차익실현.md:82 |
| `ptp.atr_pct.documented_l89.v1` | `1.0.0` | `ATR_pct` | `repairable` | docs/codex/지표/차익실현.md:89 |
| `ptp.cgo_profittakingpressure.documented_l211.v1` | `1.0.0` | `CGO_ProfitTakingPressure` | `proxy_only` | docs/codex/지표/차익실현.md:211 |
| `ptp.cgo_t.documented_l203.v1` | `1.0.0` | `CGO_t` | `proxy_only` | docs/codex/지표/차익실현.md:203 |
| `ptp.cgo_t.documented_l402.v1` | `1.0.1` | `CGO_t` | `repairable` | docs/codex/지표/차익실현.md:402 |
| `ptp.dailyproxyprofittakingpressure.documented_l300.v1` | `1.0.0` | `DailyProxyProfitTakingPressure` | `reject` | docs/codex/지표/차익실현.md:300 |
| `ptp.finalptp.documented_l334.v1` | `1.0.0` | `FinalPTP` | `not_identifiable` | docs/codex/지표/차익실현.md:334 |
| `ptp.normalized_cgo_pressure.documented_l218.v1` | `1.0.0` | `Normalized_CGO_Pressure` | `proxy_only` | docs/codex/지표/차익실현.md:218 |
| `ptp.obi_k.documented_l172.v1` | `1.0.0` | `OBI_k` | `not_identifiable` | docs/codex/지표/차익실현.md:172 |
| `ptp.orderbook_profittakingpressure.documented_l179.v1` | `1.0.0` | `Orderbook_ProfitTakingPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:179 |
| `ptp.overheadlossmass.documented_l497.v1` | `1.0.0` | `OverheadLossMass` | `proxy_only` | docs/codex/지표/차익실현.md:497 |
| `ptp.overheadsupplypressure.documented_l503.v1` | `1.0.0` | `OverheadSupplyPressure` | `proxy_only` | docs/codex/지표/차익실현.md:503, calculateOverheadSupplyPressureCause |
| `ptp.overheadsupplyratio.documented_l492.v1` | `1.0.0` | `OverheadSupplyRatio` | `proxy_only` | docs/codex/지표/차익실현.md:492 |
| `ptp.potentialptp.documented_l435.v1` | `1.0.0` | `PotentialPTP` | `proxy_only` | docs/codex/지표/차익실현.md:435, CandidateRegistry.potentialPtp.documented, calculateProfitBurdenCause |
| `ptp.production.directional_tick_flow.v1` | `audit-v1.0.0+current-production` | `calculateDirectionalTradeFlow` | `proxy_only` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:679-730 |
| `ptp.production.duplicate_timestamp_dependency.v1` | `audit-v1.0.0+current-production` | `calculateVwap.duplicateTimestamp` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:244-265 |
| `ptp.production.explanation_trace_mismatch.v1` | `audit-v1.0.0+current-production` | `createProfitTakingPressureTrace` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:1969-2008 |
| `ptp.production.hidden_floor_score.v1` | `audit-v1.0.0+current-production` | `calculateProfitTakingRiskScore.hiddenFloors` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:581-593 |
| `ptp.production.input_order_dependency.v1` | `audit-v1.0.0+current-production` | `createVolumeProfile.inputOrder` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:596-656 |
| `ptp.production.intraday_sigmoid.v1` | `audit-v1.0.0+current-production` | `calculateIntradayTradeScore` | `repairable` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:1180-1210 |
| `ptp.production.linear_score.v1` | `audit-v1.0.0+current-production` | `calculateProfitTakingRiskScore.baseScore` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:574-580 |
| `ptp.production.liquidity_impact.v1` | `audit-v1.0.0+current-production` | `calculateLiquidityImpactRiskCause` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:548-572 |
| `ptp.production.missing_reweight.v1` | `audit-v1.0.0+current-production` | `calculateWeightedComponentScore/readCauseScore` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:871-889 |
| `ptp.production.overhead_supply.v1` | `audit-v1.0.0+current-production` | `calculateOverheadSupplyPressureCause` | `proxy_only` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:532-546 |
| `ptp.production.profit_burden.v1` | `audit-v1.0.0+current-production` | `calculateProfitBurdenCause` | `proxy_only` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:488-503 |
| `ptp.production.realized_sell_pressure.v1` | `audit-v1.0.0+current-production` | `calculateRealizedSellPressureCause` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:505-530 |
| `ptp.production.risk_reward_dead_branch.v1` | `audit-v1.0.0+current-production` | `calculateRiskReward` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:892-922 |
| `ptp.production.sentiment_cap.v1` | `audit-v1.0.0+current-production` | `calculateMarketSentimentScore` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:1146-1178 |
| `ptp.production.split_sensitive_cvd.v1` | `audit-v1.0.0+current-production` | `calculateEstimatedCvd.splitAdjustment` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:285-326 |
| `ptp.production.unbounded_asof_input.v1` | `audit-v1.0.0+current-production` | `createQuantIndicatorSnapshot.asOfBoundary` | `reject` | docs/codex/지표/차익실현.md, extensions/app/quant-indicators.cjs:121-169 |
| `ptp.profitbreadth.documented_l419.v1` | `1.0.0` | `ProfitBreadth` | `proxy_only` | docs/codex/지표/차익실현.md:419, DailyFeatureEngine.profitBreadth |
| `ptp.profitgainmass.documented_l424.v1` | `1.0.0` | `ProfitGainMass` | `proxy_only` | docs/codex/지표/차익실현.md:424, DailyFeatureEngine.profitGainMass |
| `ptp.profitlongratio.documented_l17.v1` | `1.0.0` | `ProfitLongRatio` | `proxy_only` | docs/codex/지표/차익실현.md:17, createVolumeProfile |
| `ptp.profitlongratio.documented_l24.v1` | `1.0.1` | `ProfitLongRatio` | `proxy_only` | docs/codex/지표/차익실현.md:24, createVolumeProfile |
| `ptp.profitlongratio.documented_l252.v1` | `1.0.2` | `ProfitLongRatio` | `proxy_only` | docs/codex/지표/차익실현.md:252, createVolumeProfile |
| `ptp.profitlongratio.documented_l314.v1` | `1.0.3` | `ProfitLongRatio` | `proxy_only` | docs/codex/지표/차익실현.md:314, createVolumeProfile |
| `ptp.profittakingpressurescore.documented_l239.v1` | `1.0.0` | `ProfitTakingPressureScore` | `repairable` | docs/codex/지표/차익실현.md:239 |
| `ptp.ptp_final.documented_l478.v1` | `1.0.0` | `PTP_Final` | `not_identifiable` | docs/codex/지표/차익실현.md:478 |
| `ptp.realizedprofittakingpressure.documented_l157.v1` | `1.0.0` | `RealizedProfitTakingPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:157 |
| `ptp.realizedptp.documented_l329.v1` | `1.0.0` | `RealizedPTP` | `not_identifiable` | docs/codex/지표/차익실현.md:329, calculateRealizedSellPressureCause |
| `ptp.realizedptp.documented_l467.v1` | `1.0.1` | `RealizedPTP` | `not_identifiable` | docs/codex/지표/차익실현.md:467, calculateRealizedSellPressureCause |
| `ptp.rp_t.documented_l391.v1` | `1.0.0` | `RP_t` | `repairable` | docs/codex/지표/차익실현.md:391 |
| `ptp.sellflowpressure.documented_l262.v1` | `1.0.0` | `SellFlowPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:262 |
| `ptp.sellofi.documented_l452.v1` | `1.0.0` | `SellOFI` | `not_identifiable` | docs/codex/지표/차익실현.md:452 |
| `ptp.sellpressure.documented_l143.v1` | `1.0.0` | `SellPressure` | `not_identifiable` | docs/codex/지표/차익실현.md:143 |
| `ptp.simpleprofittakingpressure.documented_l293.v1` | `1.0.0` | `SimpleProfitTakingPressure` | `proxy_only` | docs/codex/지표/차익실현.md:293 |
| `ptp.survival_i.documented_l397.v1` | `1.0.0` | `Survival_i` | `repairable` | docs/codex/지표/차익실현.md:397 |
| `ptp.tradeimbalance.documented_l150.v1` | `1.0.0` | `TradeImbalance` | `not_identifiable` | docs/codex/지표/차익실현.md:150 |
| `ptp.volumeexpansion.documented_l272.v1` | `1.0.0` | `VolumeExpansion` | `repairable` | docs/codex/지표/차익실현.md:272 |
| `ptp.vwap_adjusted_profitpressure.documented_l116.v1` | `1.0.0` | `VWAP_Adjusted_ProfitPressure` | `proxy_only` | docs/codex/지표/차익실현.md:116 |
| `ptp.vwap_atr_extension.documented_l257.v1` | `1.0.0` | `VWAP_ATR_Extension` | `proxy_only` | docs/codex/지표/차익실현.md:257 |
| `ptp.vwap_atr_extension.documented_l324.v1` | `1.0.1` | `VWAP_ATR_Extension` | `proxy_only` | docs/codex/지표/차익실현.md:324 |
| `ptp.vwap_atr_profitpressure.documented_l123.v1` | `1.0.0` | `VWAP_ATR_ProfitPressure` | `proxy_only` | docs/codex/지표/차익실현.md:123 |
| `ptp.vwap_extension.documented_l430.v1` | `1.0.0` | `VWAP_Extension` | `proxy_only` | docs/codex/지표/차익실현.md:430, DailyFeatureEngine.vwapExtension |
| `ptp.vwap_profitpressure.documented_l109.v1` | `1.0.0` | `VWAP_ProfitPressure` | `proxy_only` | docs/codex/지표/차익실현.md:109 |
| `ptp.weightedprofitpressure.documented_l319.v1` | `1.0.1` | `WeightedProfitPressure` | `proxy_only` | docs/codex/지표/차익실현.md:319, createVolumeProfile |
| `ptp.weightedprofitpressure.documented_l43.v1` | `1.0.0` | `WeightedProfitPressure` | `proxy_only` | docs/codex/지표/차익실현.md:43, createVolumeProfile |
| `research.candidate.fomo_baseline_breakout20.daily.v1` | `1.4.0` | `fomo.baseline.breakout20` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.baseline.breakout20 |
| `research.candidate.fomo_baseline_momentum5.daily.v1` | `1.4.0` | `fomo.baseline.momentum5` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.baseline.momentum5 |
| `research.candidate.fomo_baseline_volume20.daily.v1` | `1.4.0` | `fomo.baseline.volume20` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.baseline.volume20 |
| `research.candidate.fomo_deduplicated.daily.v1` | `1.4.0` | `fomo.deduplicated` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.deduplicated |
| `research.candidate.fomo_equal.daily.v1` | `1.4.0` | `fomo.equal` | `proxy_only` | docs/codex/지표/포모.md, CandidateRegistry.fomo.equal |
| `research.candidate.panic_baseline_drawdown3.daily.v1` | `1.4.0` | `panic.baseline.drawdown3` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.baseline.drawdown3 |
| `research.candidate.panic_baseline_lowbreak20.daily.v1` | `1.4.0` | `panic.baseline.lowBreak20` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.baseline.lowBreak20 |
| `research.candidate.panic_baseline_volume20.daily.v1` | `1.4.0` | `panic.baseline.volume20` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.baseline.volume20 |
| `research.candidate.panic_deduplicated.daily.v1` | `1.4.0` | `panic.deduplicated` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.deduplicated |
| `research.candidate.panic_equal.daily.v1` | `1.4.0` | `panic.equal` | `proxy_only` | docs/codex/지표/패닉.md, CandidateRegistry.panic.equal |
| `research.candidate.potentialptp_baseline_runup20.daily.v1` | `1.4.0` | `potentialPtp.baseline.runup20` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.potentialPtp.baseline.runup20 |
| `research.candidate.potentialptp_baseline_vwapextension.daily.v1` | `1.4.0` | `potentialPtp.baseline.vwapExtension` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.potentialPtp.baseline.vwapExtension |
| `research.candidate.potentialptp_breadth.daily.v1` | `1.4.0` | `potentialPtp.breadth` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.potentialPtp.breadth |
| `research.candidate.potentialptp_documented.daily.v1` | `1.4.0` | `potentialPtp.documented` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.potentialPtp.documented |
| `research.candidate.potentialptp_equal.daily.v1` | `1.4.0` | `potentialPtp.equal` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.potentialPtp.equal |
| `research.candidate.relief_originalproxy.daily.v1` | `1.4.0` | `relief.originalProxy` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.relief.originalProxy |
| `research.candidate.relief_persistencegated.daily.v1` | `1.4.0` | `relief.persistenceGated` | `proxy_only` | docs/codex/지표/차익실현.md, CandidateRegistry.relief.persistenceGated |
| `research.feature.atr14.daily.v1` | `1.4.0` | `atr14` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.atr14 |
| `research.feature.breakdowncascade.daily.v1` | `1.4.0` | `breakdownCascade` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.breakdownCascade |
| `research.feature.breakout20.daily.v1` | `1.4.0` | `breakout20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.breakout20 |
| `research.feature.downmoveimpulse.daily.v1` | `1.4.0` | `downMoveImpulse` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.downMoveImpulse |
| `research.feature.drawdown3.daily.v1` | `1.4.0` | `drawdown3` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.drawdown3 |
| `research.feature.highprev20.daily.v1` | `1.4.0` | `highPrev20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.highPrev20 |
| `research.feature.lowbreak20.daily.v1` | `1.4.0` | `lowBreak20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.lowBreak20 |
| `research.feature.lowprev20.daily.v1` | `1.4.0` | `lowPrev20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.lowPrev20 |
| `research.feature.momentum5.daily.v1` | `1.4.0` | `momentum5` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.momentum5 |
| `research.feature.newlowcount5.daily.v1` | `1.4.0` | `newLowCount5` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.newLowCount5 |
| `research.feature.nonewlow.daily.v1` | `1.4.0` | `noNewLow` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.noNewLow |
| `research.feature.persistence.daily.v1` | `1.4.0` | `persistence` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.persistence |
| `research.feature.potentialptpproxy.daily.v1` | `1.4.0` | `potentialPtpProxy` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.potentialPtpProxy |
| `research.feature.profitbreadth.daily.v1` | `1.4.0` | `profitBreadth` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.profitBreadth |
| `research.feature.profitgainmass.daily.v1` | `1.4.0` | `profitGainMass` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.profitGainMass |
| `research.feature.pullbackhold.daily.v1` | `1.4.0` | `pullbackHold` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.pullbackHold |
| `research.feature.rangechase.daily.v1` | `1.4.0` | `rangeChase` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.rangeChase |
| `research.feature.rebound.daily.v1` | `1.4.0` | `rebound` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.rebound |
| `research.feature.runup20.daily.v1` | `1.4.0` | `runup20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.runup20 |
| `research.feature.rv20.daily.v1` | `1.4.0` | `rv20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.rv20 |
| `research.feature.single_session_rebound.daily.v1` | `1.4.0` | `single_session_rebound` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.single_session_rebound |
| `research.feature.truerange.daily.v1` | `1.4.0` | `trueRange` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.trueRange |
| `research.feature.two_session_persistence_and_no_new_low.daily.v1` | `1.4.0` | `two_session_persistence_and_no_new_low` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.two_session_persistence_and_no_new_low |
| `research.feature.typicalprice.daily.v1` | `1.4.0` | `typicalPrice` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.typicalPrice |
| `research.feature.volume20.daily.v1` | `1.4.0` | `volume20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.volume20 |
| `research.feature.volumesurprise.daily.v1` | `1.4.0` | `volumeSurprise` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.volumeSurprise |
| `research.feature.vwap20.daily.v1` | `1.4.0` | `vwap20` | `valid` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.vwap20 |
| `research.feature.vwapdownpressure.daily.v1` | `1.4.0` | `vwapDownPressure` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.vwapDownPressure |
| `research.feature.vwapextension.daily.v1` | `1.4.0` | `vwapExtension` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.vwapExtension |
| `research.feature.vwappersistenceproxy.daily.v1` | `1.4.0` | `vwapPersistenceProxy` | `proxy_only` | docs/codex/지표/포모.md, docs/codex/지표/패닉.md, docs/codex/지표/차익실현.md, DailyFeatureEngine.vwapPersistenceProxy |

## 재현 명령

```bash
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 research/indicator-validation/formula_ledger.py --validate
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest research/indicator-validation/test_formula_ledger.py
node --test research/indicator-validation/formula-production-counterexamples.test.cjs
```

상세 입력·단위·lookback·범위·결측·가중치·임계값·10개 증명 의무·수정 전후식·삼자 등가성은 `research/indicator-validation/formula-ledger.json`을 단일 원장으로 사용합니다.
