# 평가 기준

## 규칙 엔진

- 규칙별 precision, recall, F1
- 전체 macro/micro F1
- 양성·음성·부정문·경계 사례
- 위험 수준별 confusion matrix

## 개인정보 보호

- PII 탐지 recall
- 정상 금액·날짜·법인정보에 대한 오탐률
- 외부 provider payload의 원문 PII 잔존 여부
- 로그와 오류 응답의 원문 노출 여부
- 회귀셋: `backend/tests/fixtures/pii_regression_v0_1.jsonl`
- 새 식별자 패턴은 양성 사례와 날짜·금액·기관명 음성 사례를 함께 추가

## RAG와 LLM

- evidence ID 유효성 비율
- 인용문과 원본 chunk의 일치율
- 근거 없는 법적 참조 수
- `needs_review` 안전 종료 성공률
- 처리 실패율과 평균 처리시간

## 데이터 누수 방지

검색 코퍼스 또는 조항 패턴 작성에 사용한 문서는 같은 평가 정답셋에 포함하지 않습니다. 평가 자료는 별도 manifest로 출처와 분할 기준을 기록합니다.
