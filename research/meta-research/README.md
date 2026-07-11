# 연구 메타프로그램

이 디렉터리는 개별 수식이나 모형을 개발하는 곳이 아니라, **무엇을 어떤 자료와 증거로 연구할지 결정하고 그 결정을 추적하는 연구객체 시스템**이다. 기존 FOMO·패닉·차익실현 v1.4 연구는 변경하지 않고 `ResearchBaseline`으로 참조한다.

## 빠른 탐색

1. [메타-메타연구 보고서](objects/meta-studies/MS-001-research-program-governance/report.md)
2. [연구객체 모델](governance/research-object-model.md)
3. [수명주기와 증거 Gate](governance/lifecycle-and-evidence-gates.md)
4. [문서 관리 정책](governance/document-management-policy.md)
5. [품질 계측모형](governance/measurement-and-quality-model.md)
6. [정량 시장행동 연구 프로그램](objects/programs/RP-001-quantitative-market-behavior/README.md)
7. [연구객체 catalog](catalog/research-objects.json)

## 경계

```text
governance  공통 정책과 불변식
catalog     객체 검색용 최소 원장
objects     객체별 aggregate root
templates   새 객체를 만드는 문서 계약
archive     대체·종료 객체의 불변 보존
tools       구조 검증만 담당하는 도구
```

객체의 제목·상태·의존성·artifact는 각 객체 폴더의 `object.json`이 단일 진실 공급원이다. `catalog/research-objects.json`은 이 내용을 복사하지 않고 descriptor 경로만 보유한다.

## 연구객체 생성 순서

1. [객체모델](governance/research-object-model.md)에서 적합한 객체 유형을 선택한다.
2. 전역적으로 사용하지 않은 ID를 부여한다.
3. 해당 객체 폴더 안에 `object.json`과 필요한 문서를 둔다.
4. catalog에 descriptor 경로를 ID 순서로 등록한다.
5. 구조검증기를 실행한다.
6. `preregistered` 이후 변경이 필요하면 기존 객체를 수정하지 않고 새 버전 또는 후속 객체로 만든다.

## 구조검증

Python 3.9 이상에서 실행한다.

```bash
python3 -m unittest research/meta-research/tools/test_validate_research_program.py -v
python3 research/meta-research/tools/validate_research_program.py \
  --repository-root . \
  --program-root research/meta-research
```

검증기는 다음을 확인한다.

- 필수 bounded context와 catalog 존재
- descriptor의 필드·타입·상태·근거수준
- 전역 고유 ID와 catalog 정렬
- artifact 경로의 저장소 내부 존재
- 미등록 의존성과 순환 의존성 부재
- 발견된 descriptor와 catalog의 100% 대응

검증기는 연구결론의 참·거짓이나 통계적 타당성을 자동 판정하지 않는다. 그 책임은 `EvidenceBundle`, 독립 검토, 외부검증에 남겨 둔다.

