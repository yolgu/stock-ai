# RP-001 프로그램 계약 검증기

RP-001 foundation의 동결 Goal, 254개 요구사항, 추적성, 독립 study 슬롯, 후보 모형족, seen-data 등록과 RP 객체 결박을 검증한다. 다섯 JSON ledger는 UTF-8 compact·sorted canonical JSON이며 trailing LF를 허용하지 않는다. 이 도구는 foundation의 구조 계약만 검증하며 연구 결론이나 통계적 타당성은 검증하지 않는다.

JSON canonicalization은 저장소 연구 artifact 계약과 같은 `allow_nan=False`, `ensure_ascii=False`, `sort_keys=True`, `separators=(",", ":")` 규칙을 이 검증기 안에 독립적으로 구현한다. RP foundation 검증은 동결된 RB-001 baseline 패키지의 코드 가용성이나 import 경로에 의존해서는 안 되기 때문이다.

기본 program directory는 `research/meta-research/objects/programs/RP-001-quantitative-market-behavior`이다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_program.py --verify-foundation
```

별도 fixture는 다음과 같이 검증한다.

```bash
PYTHONPATH=research/rp-001/src PYTHONDONTWRITEBYTECODE=1 \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/rp-001/run_program.py --verify-foundation \
  --program-directory /tmp/rp001-fixture
```

검증 실패는 stderr에 `INVALID`로 출력되고 exit code 1을 반환한다.

출력되는 세 coverage 값은 부분 연구성과를 측정하는 지표가 아니라 foundation 등록 완전성 assertion이다. 검증에 성공하면 source requirement, study slot, candidate family coverage가 모두 `1.0`이어야 한다.
