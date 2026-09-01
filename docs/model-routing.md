# 에이전트 모델·토큰 라우팅

## 목표

모든 에이전트에 가장 큰 모델을 사용하지 않습니다. 각 역할은 가장 저렴한 적합 모델에서 시작하고, 사전에 정의한 실패 조건이 확인될 때만 상위 모델로 전환합니다. 모델 선택과 토큰 상한은 분석 결과와 함께 기록해 비용과 품질을 재현할 수 있어야 합니다.

## 역할별 기본 정책

| 역할 | 기본 등급 | 출력 상한 | 설명 |
|---|---:|---:|---|
| 계획 | fast | 700 | 계약 유형과 실행 단계만 구조화 |
| 근거 선별 | fast | 700 | 검색 결과의 관련성·형식 확인 |
| 계약 분석 | balanced | 1,600 | 규칙 신호와 근거를 이용한 핵심 추론 |
| 결과 검증 | deterministic | 0 | 현재 evidence ID, 인용 상태, 스키마와 단정 표현을 코드로 검사 |
| 최종 재검토 | deep | 2,400 | 고위험이면서 근거가 충돌할 때만 제한적으로 사용 |

`fast`, `balanced`, `deep`은 코드에 특정 모델명을 고정하지 않는 논리 등급입니다. OpenAI 실험에서는 다음 설정으로 실제 모델 ID를 연결합니다.

```dotenv
OPENAI_FAST_MODEL=gpt-5.6-luna
OPENAI_BALANCED_MODEL=gpt-5.6-luna
OPENAI_DEEP_MODEL=gpt-5.6-terra
```

Anthropic 공급자는 기존 결과 재현과 롤백을 위해 당분간 유지하며 다음 환경변수를 사용합니다.

```dotenv
ANTHROPIC_FAST_MODEL=<현재 사용 가능한 Haiku 계열 모델 ID>
ANTHROPIC_BALANCED_MODEL=<현재 사용 가능한 Sonnet 계열 모델 ID>
ANTHROPIC_DEEP_MODEL=<현재 사용 가능한 Opus 계열 모델 ID>
```

`.env`와 API 키는 커밋하지 않습니다. 모델의 사용 가능 여부, 가격, 데이터 처리 조건을 배포 전에 다시 확인하고 모델 ID가 바뀌면 실험 버전을 새로 기록합니다.

## 에스컬레이션 조건

- 분석 에이전트는 기본적으로 balanced를 사용합니다.
- `high risk`와 `conflicting evidence`가 동시에 충족될 때만 deep을 요청합니다.
- 현재 검증은 LLM을 다시 호출하지 않습니다. 향후 deterministic 검증의 반복 실패가
  실험으로 확인된 경우에만 fast/balanced 검증 호출을 별도 기능으로 도입합니다.
- deep 사용은 일일 요청 상한을 두고, 상한을 넘으면 사람 검토로 전환합니다.
- 토큰 입력 상한을 넘은 문서는 더 큰 모델로 바로 보내지 않고 조항 단위로 분할하거나 검색 근거 수를 줄입니다.

## LLM을 사용하지 않는 단계

파일 검증, PDF 텍스트 추출, PII 마스킹, 조항 분리, 규칙 엔진, vector search, 인용문의 원문 일치 검사와 리포트 렌더링은 결정론적 코드로 실행합니다. 이 구분이 가장 큰 토큰 절감 수단입니다.

## 추가 최적화

- 고정 시스템 지침과 반복되는 법률 문서는 prompt caching 대상으로 분리합니다.
- 검색 결과는 상위 몇 개의 짧은 chunk만 전달하고 전체 문서를 반복 전송하지 않습니다.
- 에이전트별 대화 기록을 공유하지 않고 구조화된 최소 산출물만 다음 단계로 넘깁니다.
- 비실시간 대량 평가는 Batch API 적용 여부를 별도 실험합니다.
- 매 호출의 input/output/cache token, 모델, 역할, latency와 재시도 원인을 기록합니다.

## 실제 연결 최소 검증

OpenAI는 `make openai-check`로 합성 데이터 1건만 전송합니다. Responses API 요청은
`store=false`와 JSON Schema 형식을 사용합니다. 출력 본문·prompt·API 키는 로그에 남기지 않고
모델, 응답 ID, 토큰 수, 지연시간, schema 및 근거 검증 상태만 출력합니다. 이 호출은 이미 탐지된
규칙 결과의 설명 보강만 시험합니다. 별도 `make openai-context-check`는 합성 조항을 이용해
규칙 미매핑 문맥 후보 생성을 시험합니다.

테스트 전용 키와 합성 데이터만 사용해 `make claude-check`를 실행합니다. 이 명령은 한 번의
bounded structured-output 요청만 보내며 prompt·응답 본문·키를 출력하지 않고 모델,
prompt 버전, input/output token, latency, schema/evidence 검증 여부만 출력합니다. SDK 자체
재시도는 0이며 timeout·rate limit만 worker의 최대 3회 재시도 대상으로 분류됩니다.

Anthropic 공식 문서는 단순 작업에는 작은 모델, 복잡한 추론에는 상위 모델을 선택하고 prompt caching과 batch 처리를 비용 최적화 수단으로 안내합니다. 실제 절감 효과는 FinContract AI의 동일 평가셋에서 품질 지표와 함께 측정합니다.
