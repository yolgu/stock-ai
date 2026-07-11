# FOMO·차익실현·패닉셀 연구 최종 검증 로그

검증일: 2026-07-10  
작업공간: `/Users/jik/Documents/stock-sub`

## 고정 런타임

- CPython 3.12.13
- NumPy 2.3.5
- pandas 2.2.3
- dependency lock: `research/indicator-validation/requirements.lock.txt`

## 자동 테스트

| 검증 | 명령 | 결과 |
| --- | --- | --- |
| Python 연구 전체 | `python3 -m unittest discover -s research/indicator-validation -p 'test_*.py'` | 127/127, exit 0 |
| Node 연구 계약·반례 | `node --test research/indicator-validation/*.test.cjs` | 45/45, exit 0 |
| React/Vitest | `pnpm test` | 24 files, 96/96, exit 0 |
| TypeScript | `pnpm typecheck` | exit 0 |
| Neutralino extension syntax | `pnpm extension:check` | exit 0 |

Python 실행 파일은 다음의 고정 번들을 사용했다.

```text
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

## 결정적 전체 실행

명령:

```bash
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/indicator-validation/run_validation.py --run
```

최종 코드·입력을 서로 다른 결과 디렉터리에서 각각 실행한 결과:

| 실행 | conclusion | hypotheses | outputs | manifest SHA-256 |
| --- | --- | ---: | ---: | --- |
| 기본 결과 디렉터리 | `adoption_not_identifiable` | 130 | 8 | `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e` |
| 별도 임시 디렉터리 | `adoption_not_identifiable` | 130 | 8 | `b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e` |

두 실행의 manifest는 `cmp`로 바이트 단위 일치를 확인했다. 따라서 결과 저장 위치가 달라도 동일 런타임·입력·코드·seed에서 결정적이다.

## 최종 무결성·의미 검증

명령:

```bash
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/indicator-validation/run_validation.py --verify
```

출력:

```json
{
  "inputCount": 24,
  "manifestPayloadSha256": "b6f3b49372b60c608692a233bd0abba790af58a3604204084d670cd802325b7f",
  "metricRows": 650,
  "outputCount": 8,
  "predictionRows": 94800,
  "runManifestSha256": "b4ebe5e41c8f8ca536a80fa05bddfe868e1669832555d6c00daffc21c4e0038e",
  "semanticStatus": "verified",
  "status": "verified"
}
```

`--verify`는 다음을 검사한다.

- 고정 preregistration, trial ledger, 데이터 manifest와 모든 raw·code·formula input SHA
- 130개 trial의 ID·family·candidate·kind·outcome·horizon 일치
- 130개 frozen calibrator의 상태, TSLA source window, 내부 SHA와 외부 stage binding
- 5개 stage별 정확한 심볼·거래일 축·예측 행 수와 중복 부재
- 650개 trial×stage metric key와 29개 selection group
- `RegisteredFormulaSelector`를 통한 29개 selection group의 전체 재계산
- metric과 trial stage 수치의 일치 및 BH/Holm의 metric 기반 재계산
- 미등록 채택 결론 차단과 `adoption_not_identifiable` 계약
- 330개 signal 및 145개 ground-truth·phase 그룹의 심볼·거래일 축 일치
- 결과 8개 파일의 strict canonical JSON, SHA-256와 size
- 저장된 verification 문서와 결과에서 다시 계산한 등록 산출물 간 의미 일관성

이 명령은 2,000회 bootstrap을 재계산하지 않는다. 계산 재현성은 위의 두 `--run`으로 검증했고, `--verify`는 고정 입력·결과의 무결성과 등록 산출물 간 의미 일관성을 검증한다.

## 데이터 불가 확률 회귀검사

최종 `metrics.json` 상태 분포:

```text
calibration_unavailable 320
insufficient_evidence   239
data_unavailable         80
evaluated                11
```

- `data_unavailable`: alerts/posterior `null` 80/80
- `calibration_unavailable`: alerts/posterior `null` 320/320
- 결측 상태에서 `Beta(0.5,0.5)` 또는 0.5 추정확률을 생성하지 않음

## 자격증명 검사

연구 데이터·결과·보고서에서 provider live credential 장문 패턴 검출 파일은 0개다. 실제 자격증명 문자열은 이 로그에 기록하지 않았다.
