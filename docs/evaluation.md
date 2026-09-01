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

- 검색 회귀셋: `backend/tests/fixtures/retrieval_eval_public_v0_1.jsonl`
- 검색 기준선: Hit@3 1.0, MRR 0.8 이상
- evidence ID 유효성 비율
- 인용문과 원본 chunk의 일치율
- 근거 없는 법적 참조 수
- `needs_review` 안전 종료 성공률
- 처리 실패율과 평균 처리시간

현재 공개 코퍼스 평가는 7개 조문과 7개 개발 질의로 구성된 배선·회귀 검증이다.
`local_hashing`과 로컬 `all-MiniLM-L6-v2` 모두 Hit@3 1.0, MRR 1.0을 기록했지만,
표본이 작고 같은 법률의 문구로 정답을 구성했으므로 일반화 성능이나 법률 정확도의
증거로 사용하지 않는다. 다음 평가는 별도 작성한 블라인드 계약 조항과 전문가 판단을
사용해야 한다.

## 블라인드 전문가 평가 계약

전문가용 문서와 원문은 승인된 비공개 시스템에서 제시하고, 저장소에 들어오는 JSONL에는
익명 `case_id`·`reviewer_id`, `risk_level`, 검증 근거 ID와 사전 정의된 reason/question
code만 기록합니다. 이름, 이메일, 소속, 자유서술 원문 필드는 평가기가 거부합니다.
모든 case는 같은 수의 2인 이상 독립 검토가 필요합니다.

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/evaluate_experts.py /approved/path/annotations.jsonl
```

출력은 exact agreement, observed/expected pair agreement, Fleiss κ, 위험도 분포와
case/reviewer ID별 불일치만 포함합니다. 합의 전 원판정은 덮어쓰지 않으며, 합의 결과는
별도 버전 파일로 관리합니다. `make evaluate-expert-demo`는 합성 annotation 6건으로
배선과 계산만 검증하며 실제 전문가 평가 결과가 아닙니다.

## 데이터 누수 방지

검색 코퍼스 또는 조항 패턴 작성에 사용한 문서는 같은 평가 정답셋에 포함하지 않습니다. 평가 자료는 별도 manifest로 출처와 분할 기준을 기록합니다.
