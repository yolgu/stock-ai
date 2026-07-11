# DC-002 프로그램 필수자료 데이터 계약

## 정체성

- 객체 ID: `DC-002`
- 적용 질문: `RQ-002`
- 적용 study: `ST-DAT-001`
- 계약 버전: `1.0.1`
- 공식 문서 근거 SSOT: [official-source-register.json](official-source-register.json)
- 입력군 판정 SSOT: [source-matrix.json](../../programs/RP-001-quantitative-market-behavior/source-matrix.json)

이 계약은 공개된 토스증권 기술 문서의 범위와 실제 자료 수집·이용 권한을 구분한다. 문서에 API가 표시된 사실은 현재 수집이나 보존을 승인하지 않는다. local credential file의 존재 또는 경로는 동결 전에 상위 세션에서 관측됐다. exact path와 credential 값은 artifact에 기록하지 않는다. file contents와 file-origin credential values는 읽지 않았다. 라이브 API, token, 새로운 시장자료와 결과에는 접근하지 않았다. 대화 plaintext disclosure는 파일 관측과 별도 사실이다.

## 공통 필드 계약

| 필드 ID | 계약 의미 | 현재 문서 판정 |
| --- | --- | --- |
| `providerAndSource` | provider/source의 법적·기술적 정체성과 원천 endpoint | 토스증권 공식 문서와 endpoint 후보는 기록하지만 수집 권한은 별도 Gate다. |
| `eventTimestamp` | 관측 사건 또는 candle bar-start의 시각 | candle bar-start timestamp는 문서화됐지만 timezone 보장은 `undocumented`다. |
| `publicationTimestamp` | 공급자가 값을 공개한 시각 | `undocumented` |
| `clientReceivedAt` | 수집 프로세스가 raw HTTP response bytes를 받은 시각 | 현재는 `not_applicable_no_collection`; 향후 collector-generated field로 필수 기록한다. |
| `exchange` | 거래소 또는 venue 식별자 | 완전한 보장은 `undocumented` |
| `timezone` | timestamp 해석 시간대 | `undocumented` |
| `calendarSessionAvailability` | 별도 market-calendar가 제공하는 시장 운영일·세션 가용성 | KR/US calendar endpoint는 문서화됐지만 candle 계약과 분리한다. |
| `candleMembership` | 각 candle이 어느 거래소 세션에 속하는지 나타내는 직접 필드 | `undocumented` |
| `adjustedPrice` | 조정 가격 요청·응답 경로 | candle의 adjusted default true는 문서화됐지만 조정 방법은 `undocumented`다. |
| `nativePrice` | 비조정 원시 가격 경로와 단위 | adjusted 옵션 경계만 문서화됐고 원천 조정 이력은 `undocumented`다. |
| `priceUnit` | 가격 통화와 호가 단위 | 응답 currency 필드는 있으나 종목·venue별 완전한 단위 계약은 `undocumented`다. |
| `volumeUnit` | 주식수·계약수·금액 등 거래량 단위 | `undocumented` |
| `sharesOutstanding` | 발행주식수 값, 단위, event/publication 시점 | 현재값 후보만 제한적으로 문서화됐고 point-in-time 이력은 없다. |
| `floatShares` | 유통주식수 값, 단위, event/publication 시점 | `undocumented` |
| `corporateActions` | split·배당·합병·ticker 변경 원장 | 완전한 이력과 adjusted 연결 규칙은 `undocumented`다. |
| `missingDataPolicy` | 결측 정의와 누락 bar 처리 | 공급자 정책은 `undocumented`; 결측을 0 또는 neutral로 대체하지 않는다. |
| `haltPolicy` | 거래정지 구간 표현 | `undocumented` |
| `zeroVolumePolicy` | 실제 0거래량과 미수집·결측 구분 | `undocumented` |
| `revisionPolicy` | 공표수정, backfill, correction, 재수집 버전 | 시장자료 정책은 `undocumented`; 공개 `latest` 문서 자체에도 byte drift가 관측됐다. |
| `rawHttpResponseSha256` | 수신한 raw HTTP response bytes의 SHA-256 | 시장자료는 수집하지 않아 현재 값이 없으며 향후 실행에서 필수다. |
| `processedCanonicalDataSha256` | 별도 processed canonical data artifact의 SHA-256 | 시장자료는 처리하지 않아 현재 값이 없으며 향후 실행에서 필수다. |
| `license` | 문서화된 provider use policy | FAQ exact text의 본인 매매 목적과 상업적 이용 제한만 기록하며 legalConclusion은 `null`이다. |
| `redistribution` | 문서화된 외부 배포 제한과 미문서 영역 | FAQ exact text의 외부 배포 제한을 원문 범위로 기록한다. local internal research, local retention/cache, derived publication은 `not_documented`다. |

## 시간·단위 수락 규칙

1. event timestamp, publication timestamp, `clientReceivedAt`을 서로 대체하지 않는다.
2. calendar session availability와 candle membership을 분리한다. 별도 calendar endpoint가 있어도 각 candle의 세션 소속을 추론하지 않는다.
3. 거래소·시간대·candle membership이 문서 또는 검증으로 확정되지 않으면 해당 시점 t 주장에 사용할 수 없다.
4. adjusted/native 가격을 같은 열로 혼합하지 않는다. adjustment method와 기업행동 이력이 불명확하면 기업행동 조정의 정확성을 요구하는 연구를 차단한다.
5. volume 필드가 있다는 사실만으로 `volumeUnit`을 추론하지 않는다.
6. 공식 문서의 예시를 계약으로 승격하지 않는다. 보장되지 않은 값은 항상 `undocumented`다.

## 결측·revision 규칙

결측·거래정지·0거래량 정책은 서로 다른 원인을 보존해야 한다.

- 공통 정책은 `reject_no_zero_or_neutral_imputation`이다.
- 결측 direct input을 0 또는 neutral로 대체하지 않는다.
- 결측 입력을 제외하고 남은 입력을 reweight 또는 renormalize하지 않는다.
- 거래정지, 실제 0거래량, 미수집, 공급자 결측을 임의로 같은 값으로 합치지 않는다.
- revision과 backfill 정책을 알 수 없는 데이터는 point-in-time 확인 연구에 사용하지 않는다.

## 계보와 무결성

공식 문서의 `httpResponseSha256`은 `retrievedAt`에 받은 문서 raw HTTP response body bytes에만 결박된다. 같은 URL을 짧은 간격으로 두 번 받아 hash가 같을 때만 현재 관측을 수락한다. `priorObservedHttpResponseSha256`와 `revisionObservation`은 같은 `latest` URL의 byte drift를 숨기지 않는다. `latest` 경로와 `info.version=1.2.2`는 immutable revision identifier가 아니므로 exact response hash와 full-second timezone `retrievedAt`이 필수다. 이 documentation revision risk는 비보상적이다.

홈페이지 initial HTTP hash의 scope는 `initial_http_response_bytes_not_rendered_dom`이다. initial page hash가 FAQ text를 포함한다고 주장하지 않는다. 공식 page가 현재 참조한 Next.js asset URL과 asset SHA-256을 별도로 결박하고, exact FAQ text는 `utf8_original_bytes_plus_single_lf_no_unicode_normalization`으로 canonicalize한 `extractedTextSha256`에 결박한다.

향후 시장자료를 수집할 수 있게 되더라도 raw HTTP response와 processed canonical data는 별도 artifact로 보존하고 서로 다른 SHA-256을 계산한다. 각 raw response에는 collector-generated `clientReceivedAt`을 기록하며, 정제 출력은 입력 raw hash와 정제 코드 버전에 역추적되어야 한다. 두 계층 중 하나라도 없으면 계보 Gate를 실패한다.

## 권리와 보안

- 기술 문서 접근과 수집·이용 허가는 별도다.
- provider use policy `TOSS-POLICY-001`이 권리 문구의 SSOT다.
- documented purpose는 `personal_trading_only`다. documented external distribution restriction은 exact FAQ text 그대로 기록하고, commercial use는 `prohibited_by_faq`로 기록한다.
- FAQ 문구를 raw market data의 법적 허용·금지 결론으로 재해석하지 않는다. `legalConclusion=null`이다.
- local internal research, local retention/cache, derived publication은 `not_documented`다. 금지라고 단정하지 않고 `blocked_pending_provider_clarification` 운영통제로 차단한다.
- 대화에서 공개된 credential은 compromised로 간주하고 rotate 전에는 사용하지 않는다.
- credential 값을 renderer, persistent repository, CLI arguments, 문서, 로그에 기록하지 않는다.
- 향후 회전된 credential은 일회성 child process environment에서만 사용할 수 있다.

권리 Gate는 비보상적이다. 자료 품질, 범위 또는 예상 연구가치가 높아도 license/redistribution 실패를 상쇄하지 못한다.

## 현재 수락범위

`source-matrix.json`은 availability와 identifiability를 분리한 SSOT다. 입력군과 구성요소는 `usable/limited/data_unavailable`, 주장은 `identifiable/not_identifiable`만 사용한다. 하나의 four-way terminal status로 합치지 않는다.

raw OHLCV schema availability와 derived claim identifiability를 분리한다. bar-start OHLC·currency schema, unit 계약 없는 volume field, 방법이 없는 adjusted request option은 raw input availability `limited`이고 candle session membership은 `data_unavailable`이다. `price_volume_regime`은 raw component가 아니라 derived claim이며 `identifiabilityImplications`와 `usableFor`에서만 제한 범위를 정한다. OHLCV 경로를 human_behavior_psychology_or_intent로 해석하거나 미시구조·체결 연구에 사용하는 것은 차단한다.

한국 시장 지수·국채·환율 일부, 현재 발행주식수 snapshot, KOSPI/KOSDAQ 시장 집계 KRW integer buy/sell amounts와 `updatedAt`는 제한된 schema·연구 설계 근거다. 완전한 미국·업종·변동성 factor feed, point-in-time 주식수·유통주식수·기업행동, 검색·뉴스, 옵션·공매도·대차, 순서보존 주문·체결·취소·aggressor·historical depth는 현재 공개 문서 범위에서 `data_unavailable`이다.

홈페이지 marketing의 REST/WebSocket 언급과 canonical OpenAPI·overview의 현재 REST-only 문서 범위가 충돌할 때 canonical OpenAPI·overview를 endpoint SSOT로 우선한다. documented WebSocket endpoint가 없으므로 snapshot과 당일 최근 체결을 ordered event data로 대체하지 않는다.

라이브 수집은 `blocked_pending_rotated_credentials_and_provider_retention_clarification`이다. 이 상태를 대체 자료, 중립값, 재가중 또는 다른 endpoint로 우회하지 않는다.

## 수락조건

1. 8개 입력군에 availability, component availability, identifiability implication, 차단효과, usableFor, blockedResearchUses가 모두 존재한다.
2. 모든 필수 시간·단위·revision·권리 필드가 문서화되거나 명시적으로 `undocumented`다.
3. raw HTTP response와 processed canonical data의 계보가 분리된다.
4. 결측값 대체와 재가중이 없다.
5. credential 회전, provider clarification, 수집 전 검증 Gate가 모두 통과한다.
6. official source register와 source matrix는 canonical JSON이고 protocol hash와 일치한다.
