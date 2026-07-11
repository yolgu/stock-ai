# RP-001 독립 연구 포트폴리오

아래 ID는 연구 슬롯이다. 각 Gate를 통과해 실제 객체가 만들어질 때만 catalog에 등록한다.

| Study ID | 연구책임 | 선행조건 | 주요 산출물 | 독립 실패 의미 |
| --- | --- | --- | --- | --- |
| ST-ONT-001 | 패닉·FOMO·차익실현 구성개념과 식별조건 | 없음 | 상태 온톨로지, 반례, 명칭허용 규칙 | 심리명칭 금지, 가격국면만 허용 |
| ST-DAT-001 | 자료계보·단위·가용시점·기업행동 | ST-ONT-001 | DatasetContract, source matrix | 해당 특징·연구 중단 |
| ST-BEH-001 | 행동·잠재국면·지속시간 | ST-ONT-001, ST-DAT-001 | 상태확률, duration, calibration | 행동모형 기각 |
| ST-VAL-001 | 상대가치·공정가격·국면별 괴리 | ST-DAT-001 | fair value residual, OOF forecasts | 상대가치모형 기각 |
| ST-MIC-001 | OFI·depth·spread·Hawkes 전향연구 | ST-DAT-001 + 고빈도 자료 | markout, intensity, liquidity evidence | 미시구조 계층 비활성 |
| ST-EXE-001 | 체결·슬리피지·시장충격·비용 | ST-DAT-001 | fill model, cost distribution | 거래용 사용 금지 |
| ST-RSK-001 | 포트폴리오·상관·CVaR·규모 | ST-BEH/VAL/MIC OOF | risk budget, stress evidence | 단일 연구 출력만 유지 |
| ST-SYN-001 | 독립 출력의 최종 통합 | 필수 외부검증 Gate | DecisionRecord, synthesis report | 통합모형 기각 |

## 연구 간 격리

- 각 study는 별도 `ResearchQuestion`, `StudyProtocol`, `DatasetContract`, trial ledger를 가진다.
- 한 study의 holdout 결과로 다른 study의 특징·threshold·상태명을 변경하지 않는다.
- 공통자료를 사용해도 fold와 availability 계약을 study별로 기록한다.
- 실패 study의 출력을 통합기의 입력으로 되살리지 않는다.
- 통합기는 각 study가 생성한 외부 OOF 확률·불확실성·coverage만 받는다.

## 실행 순서

```text
ST-ONT-001 -> ST-DAT-001 -> ST-BEH-001 ----+
                         -> ST-VAL-001 ----+|
                         -> ST-MIC-001 ----+|-> ST-RSK-001 -> ST-SYN-001
                         -> ST-EXE-001 -----+
```

행동과 상대가치 연구는 자료계약 이후 병렬 수행할 수 있다. 미시구조 연구는 순서보존 고빈도 원자료가 축적되기 전 시작하지 않는다. 체결비용 연구가 실패하면 예측연구가 성공해도 실거래 채택을 금지한다.

## 표본 역할

| 자료 | 허용 역할 |
| --- | --- |
| 기존 TSLA·NVDA·MU·SK하이닉스 연구구간 | discovery, reference regression, failure reproduction |
| 같은 기간의 새 특징 | exploratory only |
| 보지 않은 종목·시기 | confirmatory external validation 후보 |
| 사전 고정 이후 수집된 자료 | prospective confirmation 후보 |
| 순서보존 신규 호가·체결 | ST-MIC-001 전용 |

