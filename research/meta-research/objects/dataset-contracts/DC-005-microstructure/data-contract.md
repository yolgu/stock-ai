# DC-005 순서보존 주문장·체결 사건 데이터 계약

## 정체성

- 객체 ID: `DC-005`
- 적용 질문: `RQ-005`
- 적용 study: `ST-MIC-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-005`
- contract operational decision: block_MIC_execution
- contract primary baseline: price-history baseline
- contract primary estimand: OOF squared-error reduction for the event-plus-60-second signed midquote markout
- contract primary horizon: `event 후 60초`
- contract study slot: `ST-MIC-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## 상속 경계

provider/source, 권리, 공통 시점·단위·revision과 계보 규칙의 SSOT는 `DC-002`다. 이 문서는 그 공통 필드를 복사하지 않는다. 각 packet·message는 event timestamp, publication timestamp가 있는 경우 그 시각, collector의 `clientReceivedAt`, 거래소·venue·timezone과 권리 Gate를 통과해야 한다.

연구별 `availability timestamp`는 sequence message가 예측 프로세스에 완전히 수신·검증된 시각이며 clientReceivedAt보다 이를 앞당길 수 없다. raw/processed artifact를 분리하고 packet bytes, decoded message, reconstructed book과 feature table을 각각 hash 계보로 연결한다.

수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다.

## 관측단위와 순서키

- 기본 관측단위: venue × instrument × session × sequence message
- 예측 event: 사전 지정 message type의 검증된 sequence 위치
- 결과행: 예측 event × event 후 60초 endpoint
- 정렬키: venue session ID × channel ID × sequence number

provider timestamp가 같아도 sequence를 임의 정렬하지 않는다. venue clock과 client clock의 offset·drift를 별도로 기록하고, packet 재전송과 중복 message를 원 event로 합치되 audit trail을 보존한다.

## 필수 사건 필드

| 입력군 | 필수 study 고유 필드 | 검증 |
| --- | --- | --- |
| book event | add·modify·cancel·delete·reset type, side, price, size, order 또는 level ID | sequence replay 뒤 비음수 depth와 book invariant |
| trade event | trade ID, price, size, venue, aggressor side 또는 고정 추론규칙 | book event와 순서 결합, duplicate 검사 |
| clock·sequence | venue timestamp precision, session·channel·sequence, clientReceivedAt | monotonicity, gap, wrap·reset 정책 |
| reference | instrument status, `tick/halts/message loss`, auction·continuous session, lot size | session state와 message 적용 가능성 |
| markout | event 직전·60초 후 best bid/ask와 midquote, endpoint availability | crossed·locked book와 session-end 처리 |

`ordered book/trade/cancel/aggressor sequence`가 모두 보존되어야 OFI/depth/spread/cancel/aggressor/Hawkes 후보가 적격이다.

## snapshot 대체 금지

`snapshot/recent trades`는 현재 book 단면이나 제한된 체결 목록만 보여준다. 취소 event, aggressor history, message 사이의 순서와 intensity history를 복구하지 못하므로 순서보존 자료를 대체할 수 없다. 일정 간격 snapshot을 이어 붙이거나 변화량을 취소로 간주하는 것도 금지한다.

필수 ordered feed가 `currently unavailable`이면 `ST-MIC-001`은 `data_unavailable`이다. snapshot 기반 설명은 별도 exploratory artifact일 수 있지만 이 계약의 confirmatory event row가 아니다.

## 60초 결과 계약

`signed midquote markout`은 사전 고정 event 부호 s와 event 직전 midquote를 사용해 s × 60초 midquote 변화로 계산한다.

1. 부호 s의 정의, reference event와 quote selection을 protocol 동결 전에 고정한다.
2. 60초 endpoint의 venue timestamp를 사용하고 미래 quote를 앞당겨 채우지 않는다.
3. halt·session end·message gap·crossed book의 적격 또는 censoring 규칙을 사전 고정한다.
4. 같은 event cluster에서 겹치는 60초 창을 보존하여 분할·bootstrap에서 군집 처리한다.
5. markout processed row는 양 endpoint의 source message hash를 참조한다.

## 결측과 무결성

- 결측 direct input을 0 또는 neutral로 대체하지 않는다.
- 결측 입력을 제외한 남은 입력을 reweight 또는 renormalize하지 않는다.
- message gap 구간의 취소·체결·depth를 0으로 추정하지 않는다.
- unknown aggressor를 임의 방향으로 배정하지 않는다.
- halt와 무거래, feed loss, venue reset을 같은 상태로 합치지 않는다.

sequence gap, clock drift, invalid tick, crossed book, 음수 depth 또는 검증되지 않은 reset이 발견되면 영향 범위를 격리하고 해당 범위 실행을 차단한다.

## 수락조건

다음 조건을 모두 만족한 입력만 `ST-MIC-001`에 허용한다.

1. venue clock/sequence와 client receipt clock을 함께 보존한다.
2. order book, trade, cancel, aggressor 사건을 재생 가능한 순서로 제공한다.
3. tick·lot·session·halt·auction reference data가 point-in-time으로 연결된다.
4. message loss·duplicate·reset·retransmission을 검출하고 영향 범위를 안다.
5. 60초 midquote endpoint와 event 부호를 누출 없이 재현한다.
6. raw packet부터 feature table까지 raw/processed hash와 이용권리를 추적한다.

하나라도 충족하지 못하면 관련 session 또는 전체 study는 `blocked` 또는 `data_unavailable`이며 실행을 차단한다. snapshot, 최근 체결 또는 가격 bar로 우회하지 않는다.

## 현재 상태와 공개

DC-002 감사 범위에서는 필요한 순서보존 feed가 currently unavailable이다. 이 문서는 향후 source acceptance를 위한 conceptual 계약이며 실제 ordered data나 결과의 존재를 주장하지 않는다. 차단과 무효 session도 trial ledger에서 삭제하지 않는다.
