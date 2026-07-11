# DC-006 주문 수명주기·실행비용 데이터 계약

## 정체성

- 객체 ID: `DC-006`
- 적용 질문: `RQ-006`
- 적용 study: `ST-EXE-001`
- 계약 버전: `1.0.0`
- 수명주기: `proposed`

## 구조화 계약 projection

- contract data gate: 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단한다.
- contract evidence level: `conceptual`
- contract lifecycle: `proposed`
- contract missing policy: 결측 direct input을 0 또는 neutral로 대체하지 않고 남은 입력을 reweight 또는 renormalize하지 않는다.
- contract object id: `DC-006`
- contract operational decision: NoTrade; prohibit_operational_adoption
- contract primary baseline: NoTrade
- contract primary estimand: expected fill-weighted NetEdge_0:5m minus NoTrade
- contract primary horizon: `decision 후 5분`
- contract study slot: `ST-EXE-001`
- contract terminal statuses: supported, refuted, insufficient_evidence, not_identifiable, data_unavailable, implementation_invalid, external_failure

## DC-002 참조 경계

DC-002의 공통 provider/source, event timestamp, publication timestamp, clientReceivedAt, 거래소·시간대·세션, native/adjusted 단위, 기업행동, revision, 권리와 raw/processed hash 계약을 규범적으로 참조하고 복사하지 않는다. 이 계약은 실행 연구에만 필요한 주문 수명주기·비용·유동성 필드를 추가한다.

## Study 고유 관측계약

| 필드군 | 필수 내용 | 단위·가용시점 | 차단 의미 |
| --- | --- | --- | --- |
| 주문 시계 | decision/submit/provider-received/ack/fill/cancel/reject timestamps | 단조 증가하는 venue·provider clock과 각 메시지의 availability timestamp | 한 단계라도 없거나 clock mapping이 불명확하면 latency와 실행결과를 식별하지 못한다. |
| 체결 경로 | order ID, parent/child ID, partial fills/queue, remaining quantity, reject reason | share·contract 단위와 각 fill 수신시점 | 완전체결만 남기거나 reject를 삭제하면 무효다. |
| 직접 비용 | fees/tax/FX/borrow/hedge | 주문·체결별 native currency와 환율 적용시점 | 비용 구성요소가 누락되면 NetEdge를 계산하지 않는다. |
| 유동성 비용 | spread/depth/impact, slippage, venue, tick | decision 직전과 event-time 주문장 | snapshot만으로 queue·impact를 회고 구성하지 않는다. |
| 결과창 | decision 시점부터 5분까지 GrossEdge와 fill-weighted NetEdge | 동일 calendar session의 5분 | 다른 horizon으로 대체하지 않는다. |

## 시간·부분체결·비용 규칙

모든 메시지는 exchange 또는 provider sequence와 연결한다. provider-received와 clientReceivedAt을 혼동하지 않고, 동일 timestamp 충돌은 sequence로 정렬한다. partial fill은 체결수량으로 가중하며 미체결 잔량, cancel, reject와 만료는 별도 결과 질량으로 유지한다. 미래 5분 이후의 체결이나 가격은 시점 t 특징에 들어갈 수 없다.

`NetEdge=GrossEdge-Fees-Tax-FX-Slippage-Impact-Borrow/Hedge cost`의 각 항을 별도 필드에서 재구성한다. 비용이 0이라고 추정하지 않으며, NoTrade의 비용 0은 자료 결측 대체가 아니라 사전고정 기준선이다.

## 결측·계보·무결성

결측 direct input을 0 또는 neutral로 대체하지 않는다. 남은 입력을 reweight 또는 renormalize하지 않는다. 수락된 raw/processed artifact의 SHA-256과 availability timestamp는 모두 존재해야 하며 하나라도 없으면 실행을 차단하고 `data_unavailable`로 기록한다. 수락값은 protocol·run lineage에 연결하며 sequence 또는 수량 보존식의 누락도 같은 차단조건이다.

raw 주문 메시지와 processed 주문 수명주기 artifact는 분리하며, 각각 별도 hash를 가진다. fill 수량 합계는 원 주문수량을 넘을 수 없고, 처리된 비용 합계는 fill-level 구성요소에서 재현되어야 한다. 현재 계약은 실제 주문자료나 결과가 존재한다고 주장하지 않는다.

## 수락·차단·운영 경계

다음을 모두 통과해야 한다.

1. 주문 수명주기 시각과 sequence가 단조·완전하며 event-time과 receive-time이 분리된다.
2. partial fill, cancel, reject, queue와 미체결 잔량이 삭제되지 않는다.
3. 모든 직접·간접 비용이 통화·단위·가용시점과 함께 보존된다.
4. decision 직전 spread/depth와 5분 결과창이 미래행 없이 연결된다.
5. accepted raw/processed hashes와 availability timestamps가 protocol/run ID에 결박된다.

하나라도 실패하면 terminal status는 `data_unavailable`이다.

운영 결정은 `NoTrade`이며 `operational adoption prohibited`다. 자료 부재를 합성값, snapshot/recent trades 또는 다른 study 비용으로 대체할 수 없다.

## 권리·보안·공개

권리와 보안 Gate는 DC-002를 따른다. 이 proposed 계약에서는 수집, 주문 실행, 운영채택을 수행하지 않았고 ExperimentRun 또는 EvidenceBundle을 만들지 않는다. 차단 상태와 결측 구성요소는 향후 ledger에서 숨기거나 삭제하지 않는다.
