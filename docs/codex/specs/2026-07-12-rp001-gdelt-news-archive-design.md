# RP-001 GDELT 뉴스 타임라인 아카이브 설계

## 목적

동결된 RP-001 48개 instrument를 대상으로 2026-04-12 00:00:00 UTC부터
2026-07-11 00:00:00 UTC까지 GDELT DOC 2.0 `TimelineVolRaw`와
`TimelineTone` 원문 응답을 무료·읽기 전용으로 수집하고 해시 보존한다.

## 입력과 동결

- 대상 집합은 기존 Toss 1분봉 scope plan의 정확한 48개 symbol을 재사용한다.
- 미국 47개 instrument의 이름 근거는 보존된 Nasdaq Trader
  `instrument-master.json`의 `securityName`이다.
- `000660`은 기존 RP-001 등록 명칭 `SK hynix`를 사용한다.
- 각 검색어는 ticker가 아니라 따옴표로 감싼 고유 회사·ETF 명칭 하나다.
- query map에는 원본 plan과 directory master의 SHA-256을 바인딩하고 별도
  sidecar를 둔다. map 자체 안에는 자기 hash를 넣지 않는다.

## 실행 경계

- 허용 요청은 `GET https://api.gdeltproject.org/api/v2/doc/doc` 하나뿐이다.
- 단일 global worker가 요청 시작을 최소 10초 간격으로 직렬화한다.
- HTTP 429는 30초, 60초, 120초 뒤 재시도하고 네 번째 429에서
  `provider_rate_limited`로 종료한다.
- redirect, 다른 host/path, 비 UTF-8 또는 2 MiB 초과 응답은 거부한다.
- secret, 주문, 계좌, 자산 endpoint는 존재하지 않는다.

## 보존 계약

각 scope는 query-map SHA, symbol, mode, 기간과 형식으로 content identity를
갖는다. 모든 시도는 원문 body와 수신 metadata를 별도 파일과 SHA-256
sidecar로 보존한다. scope manifest는 시도 목록과 terminal status를
바인딩하며 manifest hash는 별도 sidecar에만 둔다. 재실행 시 검증된 terminal
manifest는 네트워크 호출 없이 재사용하고, 충돌하거나 변조된 artifact는
덮어쓰지 않는다.

## 검증

테스트는 정확한 48개 query, strict endpoint, 10초 global pacing, 429 bounded
retry, 재실행 무호출, raw/metadata/manifest sidecar, 변조 검출을 확인한다.
live 실행은 TSLA, NVDA, AAPL을 먼저 terminal로 만든 뒤 나머지 45개를 같은
동결 map으로 순차 수집한다.
