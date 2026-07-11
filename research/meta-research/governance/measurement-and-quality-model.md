# 연구문서 품질 계측모형

## 1. 목적

문서가 많다는 사실을 품질로 간주하지 않는다. 검색성, 참조무결성, 계보, 사전등록 충실도, 재현성의 상태를 각각 측정한다.

## 2. 구조 품질지표

### Catalog coverage

\[
Coverage_{catalog}
=
\frac{N(registered\ descriptors)}{N(discovered\ descriptors)}
\]

목표는 `1.00`이다. 미등록 descriptor와 존재하지 않는 catalog 항목을 모두 실패로 처리한다.

### Descriptor validity

\[
Validity_{descriptor}
=
\frac{N(valid\ descriptors)}{N(registered\ descriptors)}
\]

필드·ID·유형·버전·상태·근거수준·경로가 schema와 일치해야 한다.

### Referential integrity

\[
Integrity_{reference}
=
\frac{N(resolved\ dependencies)}{N(all\ dependencies)}
\]

목표는 `1.00`이고 의존성 cycle은 `0`이어야 한다.

### Artifact availability

\[
Availability_{artifact}
=
\frac{N(existing\ artifact\ paths)}{N(declared\ artifact\ paths)}
\]

경로 존재는 내용의 과학적 타당성을 뜻하지 않는다.

## 3. 연구설계 품질지표

| 지표 | 분자 | 분모 | 확인 연구 목표 |
| --- | --- | --- | --- |
| Question completeness | estimand·단위·horizon·범위가 모두 있는 질문 | 전체 질문 | 1.00 |
| Identifiability coverage | 관측·프록시·식별불가 판정이 있는 변수 | 전체 핵심 변수 | 1.00 |
| Baseline coverage | 사전 고정 기준선이 있는 가설 | 전체 확인 가설 | 1.00 |
| Falsification coverage | 최소 한 개 반증검사가 있는 가설 | 전체 확인 가설 | 1.00 |
| Temporal integrity | availability timestamp 계약이 있는 입력 | 전체 시변 입력 | 1.00 |
| Trial disclosure | 성공·실패·무효가 원장에 있는 trial | 실행한 전체 trial | 1.00 |
| Claim traceability | evidence ID로 역추적되는 수치 주장 | 전체 수치 주장 | 1.00 |

## 4. 계산 재현성 단계

ACM Artifact Review의 구분을 따라 세 단계를 별도로 기록한다.

1. `repeatable`: 같은 팀·같은 artifact·같은 환경에서 허용오차 내 동일 결과
2. `reproducible`: 다른 실행자가 제공된 artifact로 주요 결과 재생
3. `replicable`: 다른 자료 또는 독립 구현으로 주요 결론 재확인

각 단계는 이진 배지가 아니라 실행자, 환경, 입력 hash, 허용오차, 불일치를 포함한 `EvidenceBundle`로 기록한다.

## 5. 연구성과 지표

분류 정확도와 수익률을 한 점수로 합치지 않는다.

- 확률예측: Brier score, log loss, calibration intercept/slope
- 사건탐지: 민감도, 정밀도, 오경보율, 선행시간, 중복경보율
- 의사결정: 비용 차감 기대효용, turnover, slippage, market impact
- 위험: 변동성, 최대낙폭, VaR, CVaR, 국면별 손실
- 안정성: 종목·기간·거래소·변동성 국면별 효과분포
- 선택성: coverage 대비 오류인 risk–coverage curve

서로 다른 목적의 지표를 임의 가중합으로 합쳐 채택판정을 만들지 않는다. 필수 Gate별 통과 여부와 전체 분포를 함께 보고한다.

## 6. 대시보드 최소 출력

```text
objects=<count>
catalogCoverage=<0..1>
descriptorValidity=<0..1>
referentialIntegrity=<0..1>
artifacts=<count>
missingArtifacts=<count>
dependencyCycles=<count>
frozenHashMismatches=<count>
confirmatoryStudies=<count>
reproducedStudies=<count>
replicatedStudies=<count>
```

현재 구조검증기는 첫 단계로 객체·의존성·artifact·catalog coverage를 출력한다. 연구성과와 동결 hash는 실제 `StudyProtocol`·`ExperimentRun` 객체가 생길 때 확장한다.

