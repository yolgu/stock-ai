# DC-004 PIT 상대가치·기업행동 데이터 계약

## 정체성

- 객체 ID: `DC-004`
- 적용 질문: `RQ-004`
- 적용 study: `ST-VAL-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-004`
- contract operational decision: block_confirmatory_VAL
- contract primary baseline: price/factor baseline
- contract primary estimand: OOF ΔBrier for the 20-session industry/market-adjusted positive excess-return event
- contract primary horizon: `20 거래일`
- contract study slot: `ST-VAL-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 상속 경계

provider/source, 통화·단위, 권리, 공통 시점과 계보 규칙의 SSOT는 `DC-002`다. 이 문서는 그 공통 필드를 복사하지 않는다. 각 값은 event timestamp, publication timestamp, `clientReceivedAt`, revision, exchange·timezone과 이용권리 Gate를 통과해야 한다.

연구별 `availability timestamp`는 event timestamp, publication timestamp, clientReceivedAt과 적용 가능한 공급자 지연·확정시각 중 예측시점에 실제 사용 가능한 가장 늦은 시각이다. raw/processed artifact를 분리하여 각각 hash하고, processed 행은 입력 raw hash·vintage·변환 버전을 참조한다.

수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다.

## 관측단위와 point-in-time 키

- 기본 관측단위: instrument × effective interval × source vintage
- 예측행: instrument × 거래세션 close 시점 t
- universe 키: canonical instrument ID × membership effective-from/effective-to
- 비교집단 키: point-in-time industry·market ID × 분류 vintage

현재 constituent 목록으로 과거 `PIT universe/membership`을 재구성하지 않는다. 합병, ticker 변경, dual listing, 상장폐지와 거래정지는 원래 effective interval을 보존한다.

## 필수 입력군

| 입력군 | 필수 study 고유 필드 | 수락 경계 |
| --- | --- | --- |
| universe·membership | instrument ID, index·exchange membership, effective interval, announcement·effective·availability 시각 | 당시 적격 비교집단만 사용 |
| `factors/fundamentals/industry/rates/FX` | 값·단위·통화, fiscal period, as-of·filing·publication·availability 시각, revision vintage | 예측시점 이후 공시·최종수정 금지 |
| 가격·수익 | native close, adjusted close, 통화, split·dividend·rights event | `native/adjusted reconciliation` 필수 |
| 기업행동 | action type, announcement·ex·pay date, ratio·cash·currency | 가격·주식수·수익 변환과 연결 |
| 상장폐지 | 마지막 거래, delisting reason·return, 현금·주식 대가 | 표본 제거 또는 0 수익 대체 금지 |
| 비용 | spread·fee·tax·FX·borrow 가정과 관측시각 | 부차 순수익의 비용 시나리오에만 사용 |

`delisting/survivorship/vintage`는 하나의 비보상적 계보 Gate다. 최신 fundamentals, 최신 산업분류 또는 현재 생존종목만 남긴 패널은 confirmatory 입력으로 사용할 수 없다.

## 결과 라벨 계약

`industry/market-adjusted positive excess-return event`는 시점 t 뒤 20개 거래세션의 instrument total return에서 사전 고정 산업·시장 benchmark total return을 차감한 값이 고정 threshold를 넘는 사건이다.

1. 산업·시장 조정식과 fallback 금지를 protocol 동결 전에 정한다.
2. native price와 adjusted price를 한 수익열에 혼합하지 않는다.
3. 배당·split·합병·상장폐지를 포함한 total-return 계보를 재현한다.
4. 휴장·거래정지·통화환산 시각과 20세션 calendar를 고정한다.
5. 부차 `cost-adjusted excess return`은 명시된 비용 시나리오별로만 계산한다.

## 결측과 vintage

- 결측 direct input을 0 또는 neutral로 대체하지 않는다.
- 결측 입력을 제외한 남은 입력을 reweight 또는 renormalize하지 않는다.
- unavailable factor를 현재값, 장기평균 또는 다른 시장 proxy로 채우지 않는다.
- 산업분류가 없다는 이유로 결과를 본 뒤 비교집단을 바꾸지 않는다.
- vintage 또는 membership 계보가 없는 종목은 confirmatory VAL 적격행에서 제외하고 사유를 기록한다.

행 제거가 outcome과 연관될 수 있으므로 제외 수, 시기, 산업, delisting 상태를 공개한다.

## 방향 사전고정

상대가치 잔차의 `mean-reversion/momentum` 후보를 함께 등록하며 결과 후 선택하지 않는다. 잔차 부호나 threshold를 terminal holdout에서 바꾸지 않는다. 한 방향 실패를 다른 방향의 사후 선택으로 숨기지 않는다.

## 수락조건

다음 조건을 모두 만족한 입력만 `ST-VAL-001`에 허용한다.

1. universe와 비교집단 membership을 예측시점 기준으로 복원할 수 있다.
2. 요인·재무·산업·금리·환율의 publication과 revision vintage가 보존된다.
3. native/adjusted reconciliation과 기업행동 원장이 일치한다.
4. delisted instrument와 상장폐지 수익을 포함해 survivorship bias를 통제한다.
5. 결과 라벨과 비용 시나리오의 calendar·통화·benchmark가 고정되어 있다.
6. raw/processed hash와 권리 Gate가 완전하다.

하나라도 충족하지 못하면 관련 행 또는 `confirmatory VAL`은 `blocked` 또는 `data_unavailable`이며 실행을 차단한다. 이용 가능한 최신값으로 우회하지 않는다.

## 현재 상태와 공개

이 계약은 source acceptance 이전의 conceptual 계약이다. 실제 PIT panel이나 결과의 존재를 주장하지 않는다. 수락·제외·차단·data_unavailable 상태는 결과 방향과 무관하게 trial ledger에 남긴다.
