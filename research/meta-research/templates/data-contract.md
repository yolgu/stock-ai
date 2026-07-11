# <DC-ID> 데이터 계약

## 정체성

- 객체 ID: `<DC-ID>`
- 공급자·원천: `<PROVIDER/SOURCE>`
- 적용 연구질문: `<RQ-IDS>`
- 계약 버전: `<MAJOR.MINOR.PATCH>`

## 관측단위와 스키마

| 필드 | 의미 | 단위 | 빈도 | nullable | 가용시점 |
| --- | --- | --- | --- | --- | --- |
| `<FIELD>` | `<DEFINITION>` | `<UNIT>` | `<FREQUENCY>` | `<YES/NO>` | `<TIMESTAMP-RULE>` |

## 시간 계약

- event timestamp: `<EVENT-TIME>`
- provider timestamp: `<PROVIDER-TIME>`
- received timestamp: `<RECEIVED-TIME>`
- 예측에 사용 가능한 기준: `<AVAILABILITY-RULE>`
- 거래소·시간대·세션: `<CALENDAR/TIMEZONE>`
- 공표수정·revision 정책: `<REVISION-POLICY>`

## 단위와 기업행동

- 가격 조정: `<ADJUSTMENT>`
- 거래량 조정: `<ADJUSTMENT>`
- 주식수·유통주식수: `<SOURCE/UNIT>`
- split·배당·합병·ticker 변경: `<CORPORATE-ACTION-LEDGER>`
- 통화와 환율시점: `<CURRENCY-CONTRACT>`

## 품질과 결측

- 중복 정의: `<DUPLICATE-RULE>`
- 결측 정의: `<MISSING-RULE>`
- 거래정지·0거래량: `<HALT/ZERO-RULE>`
- outlier 처리: `<OUTLIER-RULE>`
- 관측 불가능 값의 처리: `not_identifiable`
- 공급자 교차대조: `<CROSS-CHECK>`

## 계보와 무결성

- 원시 artifact: `<PATH/EXTERNAL-ID>`
- manifest: `<PATH>`
- 수집시각: `<ISO-8601>`
- 원시 SHA-256: `<SHA-256>`
- 정제 코드·버전: `<CODE-ID/VERSION>`
- 정제 출력 SHA-256: `<SHA-256>`

## 권리와 보안

- 라이선스·이용약관: `<TERMS>`
- 재배포 가능범위: `<SCOPE>`
- 개인정보 여부: `<YES/NO>`
- 인증정보 저장: `금지`
- 보존·삭제 정책: `<RETENTION>`

## 수락조건

- 필수 품질검사: `<CHECKS>`
- 허용오차: `<TOLERANCES>`
- 차단조건: `<BLOCKING-CONDITIONS>`

