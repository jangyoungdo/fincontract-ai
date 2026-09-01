# OpenAI 문맥 검토 후보 설계

## 목적과 불변성

OpenAI 문맥 검토는 19개 결정론 규칙과 로컬 E5가 놓친 표현을 추가 검토 후보로 제안한다.
결정론 `findings[]`를 생성·수정·삭제하지 않으며 결과는 항상 `candidate_findings[]`에만 들어간다.
외부 호출 실패, 예산 소진, 잘못된 출력은 기존 결과에 영향을 주지 않는다.

## 입력 경계

- 개인정보 마스킹 검증을 통과한 `제N조`와 `별지 N`만 전송한다.
- 제목·전문·시험 설명과 원본 파일 바이트는 전송하지 않는다.
- 조문은 기본 12,000자 이하 묶음, 문서당 최대 2회로 제한한다.
- 규칙 taxonomy에는 ID, 이름, 유형 설명, 검토 질문과 대표 표현만 포함한다.
- Responses API 요청은 `store=false`와 `context-review-v1` JSON Schema를 사용한다.

## 출력 검증

모델은 `section_id`, `rule_id`, 원문 그대로의 `evidence_quote`, 이유, 검토 질문,
반대 사정과 신뢰 구간만 반환한다. 애플리케이션은 다음 조건을 모두 통과한 후보만 채택한다.

1. 입력에 존재한 조문 ID와 R01~R19 규칙 ID일 것
2. `evidence_quote`가 해당 마스킹 조문의 정확한 연속 문자열일 것
3. 동일 조문·동일 유형의 규칙 또는 E5 후보가 없을 것
4. 조문별 최대 3개 이내일 것
5. 위법·적법·무효 등 확정적 법률 결론을 포함하지 않을 것

R01은 위약금·손해배상 예정처럼 손실 보전 명목의 정액·정률 부담이고, R15는 사업자 운영비·
소송비·제세공과금 등 본래 사업자 측 비용을 고객에게 이전하는 유형이다. 금액 부담이라는 이유만으로
R15로 분류하지 않는다.

## 호출 우선순위와 비용

문서 전체 LLM 예산 8회 중 최대 2회를 문맥 후보 탐지에 먼저 예약한다. 나머지는 기존 규칙 결과의
설명 보강에 사용할 수 있다. 실제 호출마다 모델, prompt 버전, 응답 ID, 입출력 토큰과 지연시간만
기록하며 입력 조문과 출력 본문은 로그에 남기지 않는다.

## 평가

비공개 평가기는 세 지표를 분리한다.

- `metrics`: 결정론 규칙 precision/recall/F1
- `candidate_metrics`: 기대 의미 후보 대비 E5 + OpenAI 후보 precision/recall/F1
- `combined_metrics`: 후보 유형을 R01~R19 ID로 매핑한 최종 검토 범위

OpenAI 전송은 명시적 `--openai-context` 옵션에서만 수행한다. 규칙 결과 보존율은 별도로 100%인지
확인하고, 후보가 많아져 recall만 오르면서 precision이 하락하지 않는지 함께 평가한다.

```bash
set -a; . ./.env; set +a
cd backend
PYTHONPATH=. .venv/bin/python scripts/evaluate_private_document.py \
  /private/path/test.pdf /private/path/ground-truth.json \
  --mode full --openai-context
```

평가 출력은 파일 해시, 버전, 조문별 ID와 집계만 포함하며 문서 원문은 출력하지 않는다.
