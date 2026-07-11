# MS-001 근거행렬

| 근거 | 핵심 내용 | 현 저장소의 문제 | 채택한 적용 | 적용하지 않은 부분 |
| --- | --- | --- | --- | --- |
| FAIR | 검색·접근·상호운용·재사용 가능한 metadata | 연구 산출물이 여러 폴더에 흩어져 탐색 시작점이 약함 | 전역 ID, catalog, source register | 공개 저장소·DOI 발급은 현재 범위 밖 |
| RO-Crate | 폴더와 metadata descriptor로 research object 구성 | 문서·코드·자료·결과 관계가 사람용 링크에 의존 | 객체 폴더 + `object.json` | JSON-LD 전체 context와 crate packaging은 보류 |
| W3C PROV-O | Entity·Activity·Agent 및 파생관계 | 결과가 어느 protocol·자료·실행에서 나왔는지 공통 모델 부족 | 객체 의존성, 향후 ExperimentRun 계보 | RDF/OWL 저장소는 도입하지 않음 |
| OSF Registration | 편집 가능한 project와 불변 registration 분리 | 탐색과 확인, active와 frozen을 혼동할 위험 | 수명주기와 amendment 규칙 | 외부 OSF 업로드는 별도 결정 |
| PRISMA-ScR | 검색·선정·보고의 투명성 | 메타연구를 체계적 고찰로 과장할 위험 | 출처 포함·제외와 조사 한계 명시 | 이번 조사를 PRISMA 준수 고찰로 부르지 않음 |
| ACM Artifact Review | artifact 기능성·가용성과 결과 재현·복제 구분 | 테스트 통과와 외부 타당성을 같은 완료로 오인할 위험 | evidence level과 독립 재현 Gate | 공식 badge 발급은 범위 밖 |
| Data Package | descriptor와 resources로 자료 패키지 기술 | 공급자별 원자료 manifest 형식이 달라질 수 있음 | DatasetContract adapter 후보 | 현 v1.4 manifest 교체는 금지 |
| v1.4 local evidence | 사전등록·trial ledger·manifest·실패보존 | 하나의 연구 안에서는 강하지만 상위 프로그램 catalog가 없음 | 불변 baseline wrapper와 전역 catalog | 기존 파일 재배치·재작성 금지 |

## 근거에서 도출한 설계명제

1. 연구의 SSOT는 보고서 한 파일이 아니라 타입이 있는 객체와 관계다.
2. 사람용 Markdown과 기계용 metadata를 함께 유지해야 한다.
3. 동결과 정정은 파일 덮어쓰기가 아니라 수명주기 전이와 새 객체로 표현해야 한다.
4. 구조 재현성과 과학적 복제성은 별도 지표다.
5. 완전한 시맨틱 표준은 즉시 도입할 필요가 없지만 변환 가능한 필드를 유지해야 한다.

