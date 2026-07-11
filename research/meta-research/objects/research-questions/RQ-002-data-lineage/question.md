# RQ-002 프로그램 데이터 계보와 사용범위

## 정체성

- 객체 ID: `RQ-002`
- 상위 프로그램: `RP-001`
- 적용 study: `ST-DAT-001`
- 수명주기: `completed`
- 증거수준: `conceptual`
- 버전: `1.0.1`

## 질문

> GOAL-RP-001이 요구하는 각 필수 입력군에 대해, 시점 t 가용성·계보·단위·수정·권리 계약을 모두 만족하는 자료가 현재 존재하며 어떤 연구에 사용할 수 있는가?

## 구성개념 경계

이 질문은 공개된 기술 문서의 가용성과 실제 수집·이용 권한을 별도로 판정한다. endpoint나 schema가 문서에 있다는 사실은 수집 권한, 보존 권한, 재배포 권한 또는 연구결과 공개 권한을 뜻하지 않는다. 인증 가능성도 권리 계약을 대신하지 않는다.

현재 평가는 공식 공개 문서와 저장소 코드 및 기존 등록 seen-data metadata의 계약만 감사한다. local credential file의 존재 또는 경로는 동결 전에 상위 세션에서 관측됐다. exact path와 credential 값은 artifact에 기록하지 않는다. file contents와 file-origin credential values는 읽지 않았다. 라이브 API 응답, token, 새로운 시장자료 또는 결과에는 접근하지 않았다. 대화에서 plaintext credential이 공개된 사실은 별도 disclosure로 기록한다.

## 주요 estimand

- 모집단: GOAL-RP-001의 8개 필수 입력군
- 관측단위: 필수 입력군 하나
- availability estimand: 입력군과 구성요소별 `usable/limited/data_unavailable`
- identifiability estimand: 입력군에서 허용하려는 주장별 `identifiable/not_identifiable`
- 두 축 표기: availability: `usable/limited/data_unavailable`, identifiability: `identifiable/not_identifiable`
- 예측시점: 문서 접근일 `2026-07-10` 현재의 계약 상태
- horizon: `N/A` — contemporaneous data-contract audit
- 결과변수: 현재 사용 가능범위, 차단효과, 허용 연구, 금지 연구
- 비교대상: 없다. 입력군 간 성능 순위를 추정하지 않는다.

availability의 `usable`은 시점·계보·단위·수정·운영 Gate를 모두 만족할 때만 허용한다. 일부 문서화 또는 일부 자료만 존재하면 `limited`, retrievedAt 현재 공개 문서 범위에서 필요한 path나 field가 문서화되지 않으면 `data_unavailable`이다. 이는 공급자 전체에 자료가 존재하지 않는다는 법적·사실적 단정이 아니다.

identifiability의 `identifiable`은 해당 자료가 주장에 필요한 관측을 직접 제공할 때만 허용한다. 자료가 있더라도 인간 심리·의도, 종목별 행동, 순서보존 취소·aggressor 같은 목표 주장을 분리할 수 없으면 `not_identifiable`이다. raw availability의 `data_unavailable`과 구성개념의 `not_identifiable`을 같은 상태로 합치지 않는다. 한 축이나 Gate의 충족은 다른 축이나 Gate의 실패를 상쇄하지 않는다.

## 필수 입력군

1. 일봉 OHLCV
2. 분봉 OHLCV
3. 시장·업종·금리·환율·변동성 요인
4. 발행·유통주식수와 기업행동
5. 검색·뉴스노출
6. 주체별 흐름
7. 옵션·공매도·대차
8. 순서보존 호가·체결·취소·aggressor side

## 식별 및 사용 조건

각 입력군은 provider/source, event·publication timestamp, `clientReceivedAt`, 거래소·시간대, calendar session availability, candle membership, adjusted/native 가격과 거래량 단위, 주식수, 기업행동, 결측·거래정지·0거래량, revision, raw/processed hash, license/redistribution를 모두 평가한다.

`componentStatuses`에는 availability 상태만 기록하고, `identifiabilityImplications`에는 주장과 identifiability 상태만 기록한다. 서로 다른 상태축을 하나의 four-way terminal 값으로 합치지 않는다.

raw OHLCV schema availability와 derived claim identifiability를 분리한다. daily/minute `componentStatuses`에는 bar-start OHLC·currency schema, unit 계약 없는 volume field, 방법이 없는 adjusted request option, candle session membership 같은 raw input component만 둔다. `price_volume_regime`은 derived claim이므로 `identifiabilityImplications`와 `usableFor`에만 둔다.

문서가 보장하지 않는 값은 `undocumented`로 유지한다. 예시 응답이나 추정으로 계약을 채우지 않는다. 필수 direct input의 결측은 0 또는 neutral로 대체하지 않으며, 남은 입력의 reweight 또는 renormalize로 우회하지 않는다.

## 반증과 중단

- 최소 반례: endpoint가 존재하지만 시점·단위·revision 또는 운영권리 중 하나가 불명확한 경우 availability `usable`을 기각한다.
- 권리 반례: 개인 투자 목적의 접근 허용은 외부 재배포, 상업적 이용, 장기 보존 또는 파생결과 공개를 자동 허용하지 않는다.
- 미시구조 반례: 호가 snapshot과 당일 최근 체결은 순서보존 주문·체결·취소·aggressor·historical depth를 대신하지 않는다.
- 중단조건: credential 회전과 provider의 보존·내부연구 범위 clarification 전에는 라이브 수집을 시작하지 않는다.

## 다음 객체

- 자료계약: `DC-002`
- 연구 프로토콜: `SP-002`
- 구조화 SSOT: `source-matrix.json`
