# RP-001 필수자료 source matrix

## 결박

- Goal: `GOAL-RP-001`
- Program: `RP-001`
- ResearchQuestion: `RQ-002`
- DatasetContract: `DC-002`
- Study slot: `ST-DAT-001`
- StudyProtocol: `SP-002`
- 구조화 SSOT: [source-matrix.json](source-matrix.json)
- 공식 문서 근거: [official-source-register.json](../../dataset-contracts/DC-002-program-data/official-source-register.json)
- 문서 접근일: `2026-07-10`

이 문서는 구조화 JSON의 사람이 읽는 projection이다. availability 상태는 `usable`, `limited`, `data_unavailable`만 사용하고 identifiability 상태는 `identifiable`, `not_identifiable`만 사용한다. raw input availability와 claim identifiability를 한 terminal 상태로 합치지 않는다.

raw OHLCV schema availability와 derived claim identifiability를 분리한다. daily/minute component 열에는 raw input만 두고 `price_volume_regime`은 identifiability implication과 usableFor에만 둔다.

## Provider use policy

- policyId: `TOSS-POLICY-001`
- provider: `토스증권`
- source: `TOSS-DOC-004`
- documentedPurpose: `personal_trading_only`
- documentedExternalDistributionRestriction: API는 본인의 매매 목적으로만 이용할 수 있어요. 외부 배포나 상업적 용도로는 사용할 수 없으며, 자세한 내용은 이용약관을 확인해 주세요.
- commercialUse: `prohibited_by_faq`
- localInternalResearch: `not_documented`
- localRetention: `not_documented`
- derivedPublication: `not_documented`
- operationalControl: `blocked_pending_provider_clarification`
- legalConclusion: `null`

FAQ exact text를 raw market data의 법적 허용·금지 결론으로 확대하지 않는다. live collection은 credential 회전과 provider clarification 전까지 `blocked_pending_rotated_credentials_and_provider_retention_clarification`이다.

## 입력군 판정

| inputGroupId | availabilityStatus | componentStatuses | identifiabilityImplications | blockingEffects | usableFor | blockedResearchUses |
| --- | --- | --- | --- | --- | --- | --- |
| `daily_ohlcv` | `limited` | adjusted_request_option_without_method=limited<br />bar_start_ohlc_currency_schema=limited<br />candle_session_membership=data_unavailable<br />volume_field_without_unit_contract=limited | price_path_or_price_volume_regime=identifiable<br />human_behavior_psychology_or_intent=not_identifiable | candleMembership·publicationTimestamp·volumeUnit·adjustmentMethod·market-data revision이 undocumented다.<br />현재 live collection Gate가 닫혀 있어 실제 자료 가용성과 품질은 확인하지 않았다. | 공식 문서에 근거한 adjusted 가격 경로 schema 설계<br />향후 Gate 통과 뒤 price_volume_regime과 price-path behavior-regime의 제한 연구 | human_behavior_psychology_or_intent_inference와 미시구조·체결 연구<br />단위·시점·권리 Gate를 통과하지 않은 confirmatory 또는 경제효과 분석 |
| `minute_ohlcv` | `limited` | adjusted_request_option_without_method=limited<br />bar_start_ohlc_currency_schema=limited<br />candle_session_membership=data_unavailable<br />volume_field_without_unit_contract=limited | price_path_or_price_volume_regime=identifiable<br />human_behavior_psychology_or_intent=not_identifiable | candleMembership·publicationTimestamp·volumeUnit·adjustmentMethod·revision이 undocumented다.<br />현재 live collection Gate가 닫혀 있어 분봉 연속성·중복·cutoff를 확인하지 않았다. | 공식 문서에 근거한 adjusted 가격 경로 schema 설계<br />향후 Gate 통과 뒤 price_volume_regime과 price-path behavior-regime의 제한 연구 | human_behavior_psychology_or_intent_inference와 미시구조·체결 연구<br />session·중복·cutoff 검증 전 confirmatory intraday 분석 |
| `market_sector_rates_fx_vol` | `limited` | kr_index_bond_fx_price_derived_subset=limited<br />us_sector_volatility_canonical_factor_feed=data_unavailable | documented_kr_price_derived_subset_scope=identifiable<br />canonical_cross_market_factor_set=not_identifiable | 미국·업종·변동성·canonical factor feed의 documented path/field가 없다.<br />factor publication vintage와 revision policy가 undocumented다. | 한국 지수·채권·환율 일부의 제한적 schema 설계와 price-derived factor 연구 | 미국·업종·변동성을 포함한 완전한 cross-market factor model<br />vintage와 revision을 요구하는 point-in-time factor 검증 |
| `shares_and_corporate_actions` | `limited` | corporate_actions=data_unavailable<br />current_shares_snapshot=limited<br />float_shares=data_unavailable<br />point_in_time_shares=data_unavailable | current_shares_snapshot=identifiable<br />point_in_time_float_and_corporate_action_state=not_identifiable | point-in-time effective timestamp·float shares·split·배당·합병·ticker change ledger가 없다.<br />current snapshot으로 과거 분모나 corporate-action adjustment를 재구성할 수 없다. | 현재 발행주식수 snapshot field의 schema 설계 | 유통주식수와 시점 t point-in-time shares를 요구하는 turnover 연구<br />기업행동 이력과 adjusted/native reconciliation 연구 |
| `attention_and_news` | `data_unavailable` | raw_attention=data_unavailable<br />raw_news_exposure=data_unavailable | human_psychology_or_intent_from_attention_or_news=not_identifiable | raw attention과 news exposure input availability가 data_unavailable이다.<br />raw availability의 data_unavailable과 인간 심리·의도 implication의 not_identifiable은 서로 다른 판정이다. | 문서 부재 관측과 향후 provider requirement의 계약 기록 | attention·news exposure를 입력으로 하는 행동 연구<br />가격만으로 인간 심리·의도를 대체 추론하는 연구 |
| `participant_flow` | `limited` | final_revision_history=data_unavailable<br />krw_market_aggregate_buy_sell_amounts=limited<br />symbol_level_flow=data_unavailable<br />updated_at=limited | market_aggregate_buy_sell_amounts=identifiable<br />symbol_level_behavior_or_intent=not_identifiable | symbol-level participant flow와 과거 final revision history가 없다.<br />시장 집계를 종목 행동·심리·의도로 일반화할 수 없다. | KOSPI/KOSDAQ 시장 집계 KRW integer buy/sell amount와 updatedAt의 제한 연구 | 종목별 participant behavior 또는 인간 의도 연구<br />final revision이 보장된 point-in-time symbol flow 연구 |
| `options_short_and_borrow` | `data_unavailable` | options=data_unavailable<br />securities_lending=data_unavailable<br />short_interest=data_unavailable | options_short_or_borrow_state=not_identifiable | options surface·short balance·borrow inventory/rate input availability가 data_unavailable이다.<br />다른 가격·흐름 입력으로 이 필수 input group을 대체하지 않는다. | 문서 부재 관측과 향후 provider requirement의 계약 기록 | 옵션·공매도·대차 신호 또는 crowding 연구<br />대체 프록시로 필수 direct input을 충족했다고 주장하는 연구 |
| `ordered_book_trade_cancel` | `data_unavailable` | aggressor_side=data_unavailable<br />cancel_events=data_unavailable<br />historical_depth=data_unavailable<br />orderbook_snapshot=limited<br />ordered_sequence=data_unavailable<br />recent_same_day_trades=limited | current_snapshot_or_recent_trade=identifiable<br />ordered_sequence_cancel_aggressor_historical_depth=not_identifiable | 순서보존 주문·체결 sequence와 취소 event·aggressor side·historical depth가 없다.<br />homepage marketing과 달리 canonical OpenAPI+overview는 REST only이고 documented WebSocket endpoint 없음이 확인됐다. | 현재 호가 snapshot과 당일 최근 체결 response schema의 제한적 설계<br />ordered event data의 향후 수집 requirement 정의 | ST-MIC-001의 OFI·queue·cancel·Hawkes ordered-event 연구<br />ST-EXE-001의 aggressor·execution·historical depth 연구 |

## 근거 projection

### `daily_ohlcv`

- `document_fact` — OpenAPI 1.2.2는 /api/v1/candles의 1d, bar-start timestamp, OHLC, volume, currency와 adjusted default true를 문서화한다. — source: TOSS-DOC-002 — authority: none — location: paths./api/v1/candles; components.schemas.Candle
- `research_inference` — 문서화된 가격·거래량 경로는 가격·거래량 regime에는 제한적으로 쓰일 수 있으나 인간 심리·의도를 식별하지 않는다. — source: TOSS-DOC-002 — authority: RQ-002, DC-002 — location: DC-002 시간·단위 수락 규칙
- `operational_control` — 회전된 credential과 provider clarification 전에는 실제 일봉을 수집하지 않는다. — source: none — authority: SP-002 — location: SP-002 Credential과 현재 라이브 Gate

### `minute_ohlcv`

- `document_fact` — OpenAPI 1.2.2는 /api/v1/candles의 1m interval과 bar-start candle schema를 문서화한다. — source: TOSS-DOC-002 — authority: none — location: paths./api/v1/candles parameters.interval
- `research_inference` — 분봉 price/path regime는 제한적으로 식별 가능하지만 주문 사건 순서나 인간 의도는 식별되지 않는다. — source: TOSS-DOC-002 — authority: RQ-002, DC-002 — location: DC-002 현재 수락범위

### `market_sector_rates_fx_vol`

- `document_fact` — OpenAPI는 KOSPI/KOSDAQ, 한국 국채 2~30년과 KRW↔USD 환율 관련 path·unit을 문서화한다. — source: TOSS-DOC-002 — authority: none — location: Market Indicators symbol catalog; paths./api/v1/exchange-rate
- `document_absence_observation` — retrievedAt에 확인한 public v1.2.2 scope에서 미국·업종·변동성·canonical factor feed의 documented path/field를 찾지 못했다. — source: TOSS-DOC-002, TOSS-DOC-003 — authority: none — location: OpenAPI paths and Market Indicators symbol catalog
- `research_inference` — 문서화된 한국 subset을 완전한 cross-market factor set으로 일반화할 수 없다. — source: TOSS-DOC-002 — authority: RQ-002, DC-002 — location: DC-002 현재 수락범위

### `shares_and_corporate_actions`

- `document_fact` — StockInfo schema는 current sharesOutstanding field를 문서화한다. — source: TOSS-DOC-002 — authority: none — location: components.schemas.StockInfo.sharesOutstanding
- `document_absence_observation` — retrievedAt에 확인한 public v1.2.2 scope에서 point-in-time shares, float shares, corporate actions ledger의 documented path/field를 찾지 못했다. — source: TOSS-DOC-002 — authority: none — location: OpenAPI paths and components.schemas.StockInfo
- `research_inference` — current shares snapshot은 과거 시점 t 분모나 기업행동 상태를 식별하지 않는다. — source: TOSS-DOC-002 — authority: RQ-002, DC-002 — location: DC-002 time and corporate-action contract

### `attention_and_news`

- `document_absence_observation` — retrievedAt에 확인한 public v1.2.2 scope에서 attention, search exposure, news exposure의 documented path/field를 찾지 못했다. — source: TOSS-DOC-002, TOSS-DOC-003 — authority: none — location: OpenAPI paths and overview sections
- `research_inference` — raw input 부재와 인간 심리·의도 비식별은 서로 다른 축이며 가격 입력으로 attention을 대체하지 않는다. — source: TOSS-DOC-002 — authority: RQ-002 — location: RQ-002 availability and identifiability boundary

### `participant_flow`

- `document_fact` — InvestorTradingRecord는 KOSPI/KOSDAQ 시장 집계, KRW integer buy/sell amounts, updatedAt와 당일 잠정 갱신을 문서화한다. — source: TOSS-DOC-002 — authority: none — location: paths./api/v1/market-indicators/{symbol}/investor-trading; components.schemas.InvestorTradingRecord
- `research_inference` — 시장 aggregate flow는 symbol-level behavior 또는 인간 의도를 식별하지 않는다. — source: TOSS-DOC-002 — authority: RQ-002 — location: RQ-002 identifiability boundary
- `operational_control` — provider clarification과 revision contract 전에는 flow data를 수집하거나 보존하지 않는다. — source: none — authority: SP-002 — location: SP-002 Credential과 현재 라이브 Gate

### `options_short_and_borrow`

- `document_absence_observation` — retrievedAt에 확인한 public v1.2.2 scope에서 options, short interest, securities lending의 documented path/field를 찾지 못했다. — source: TOSS-DOC-002, TOSS-DOC-003 — authority: none — location: OpenAPI paths and overview sections
- `operational_control` — 필수 direct input 부재를 0·neutral 또는 다른 factor reweighting으로 우회하지 않는다. — source: none — authority: SP-002 — location: SP-002 missing-data policy

### `ordered_book_trade_cancel`

- `document_fact` — OpenAPI는 /api/v1/orderbook snapshot과 /api/v1/trades 당일 최근 체결을 문서화한다. — source: TOSS-DOC-002 — authority: none — location: paths./api/v1/orderbook; paths./api/v1/trades
- `document_fact` — homepage marketing 표현은 REST/WebSocket을 언급한다. — source: TOSS-DOC-004 — authority: none — location: official homepage marketing copy in current claim asset
- `document_absence_observation` — retrievedAt에 확인한 public v1.2.2 scope에서 canonical OpenAPI와 overview의 documented WebSocket endpoint, ordered sequence, cancel event, aggressor side, historical depth path/field를 찾지 못했다. — source: TOSS-DOC-002, TOSS-DOC-003 — authority: none — location: OpenAPI paths and overview REST API scope
- `research_inference` — snapshot과 최근 체결은 ordered event sequence를 대체하지 못하므로 MIC/EXE study를 차단한다. — source: TOSS-DOC-002 — authority: SP-002 — location: SP-002 input-group boundary

## 공통 운영통제

- 결측 direct input을 0·neutral로 대체하지 않는다.
- 결측 뒤 reweight·renormalize하지 않는다.
- raw HTTP response와 processed canonical data는 별도 artifact·hash·`clientReceivedAt` 계약을 가진다.
- `latest`와 version은 immutable하지 않으므로 exact response hash·retrievedAt가 없으면 문서근거를 수락하지 않는다.
- 기술 문서 접근은 수집·보존·연구공개 권한을 대신하지 않는다.
