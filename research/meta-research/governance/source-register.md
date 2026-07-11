# 메타연구 출처 원장

접근일은 모두 `2026-07-10`이다. 공식 사양과 원 논문을 우선했다.

| ID | 출처 | 적용한 근거 | 이 체계의 적용 범위 |
| --- | --- | --- | --- |
| SRC-001 | [FAIR Guiding Principles](https://doi.org/10.1038/sdata.2016.18) | 연구자료는 findable, accessible, interoperable, reusable해야 한다 | 고유 ID, catalog, metadata, 재사용 계약의 방향성 |
| SRC-002 | [RO-Crate Technical Overview](https://www.researchobject.org/ro-crate/technical_overview) | 폴더와 기계판독 metadata로 자료·코드·문서·관계를 하나의 research object로 묶을 수 있다 | 파일 우선 aggregate와 향후 JSON-LD adapter 경로 |
| SRC-003 | [Packaging research artefacts with RO-Crate](https://arxiv.org/abs/2108.06503) | 경량 연구객체 패키징과 metadata 동반 이동 | 완전 구현이 아닌 호환 목표의 근거 |
| SRC-004 | [W3C PROV-O](https://www.w3.org/TR/prov-o/) | Entity·Activity·Agent와 파생관계로 계보를 교환할 수 있다 | 객체 의존성과 실행계보의 개념모델 |
| SRC-005 | [OSF Registrations](https://help.osf.io/article/330-welcome-to-registrations) | 편집 가능한 project와 시점이 고정된 read-only registration을 분리한다 | proposed/active와 preregistered/frozen의 분리 |
| SRC-006 | [PRISMA-ScR](https://www.prisma-statement.org/scoping) | scoping review의 검색·선정·보고 투명성을 위한 항목을 제공한다 | 향후 정식 범위고찰의 보고 기준; 이번 조사를 체계적 고찰로 과장하지 않는 경계 |
| SRC-007 | [ACM Artifact Review and Badging](https://www.acm.org/publications/policies/artifact-review-and-badging-current) | artifact 기능성, 가용성, repeatability, reproducibility, replicability를 구분한다 | 증거수준과 독립 재현 Gate |
| SRC-008 | [Data Package v2](https://datapackage.org/blog/2024-06-26-v2-release/) | descriptor와 resource로 자료 묶음을 기술한다 | 향후 `DatasetContract` adapter 후보 |

## 저장소 내부 근거

| ID | 경로 | 역할 |
| --- | --- | --- |
| LOCAL-001 | `research/indicator-validation/preregistration.json` | 실제 사전등록·가설원장·분석계약 사례 |
| LOCAL-002 | `research/indicator-validation/artifact_store.py` | 입력·출력 artifact와 manifest hash 검증 사례 |
| LOCAL-003 | `docs/codex/research/2026-07-10-mania-panic-fomo-formula-final-report.md` | 실패·식별불가·무효 실행까지 보존한 기준선 |
| LOCAL-004 | `docs/codex/research/2026-07-10-bayesian-hsmm-competing-risks-framework.md` | 후속 후보가 기존 연구를 변경하지 않아야 한다는 버전 경계 |

## 제외한 접근

- 개인 블로그와 검색결과 요약은 규범 근거로 사용하지 않았다.
- 특정 연구관리 SaaS의 UI 구조를 저장소 표준으로 채택하지 않았다.
- 완전한 RDF/OWL 지식그래프는 현재 규모의 필수조건으로 보지 않았다.
- 이번 조사는 이중 독립 선별과 전체 학술 데이터베이스 검색이 없으므로 systematic review 또는 PRISMA-ScR 준수 고찰로 주장하지 않는다.

