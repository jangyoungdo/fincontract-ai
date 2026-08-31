# 코드 유지보수 가이드

이 문서는 기능을 변경할 때 함께 확인해야 하는 코드와 안전 불변식을 정리합니다. 실제 구현·검증 상태는 `implementation-matrix.md`를 기준으로 판단합니다.

## 문서 수명주기

- API: `backend/app/api/documents.py`
- 파일 검증·추출: `backend/app/services/file_validation.py`, `text_extraction.py`
- 암호화 저장: `backend/app/services/encrypted_storage.py`
- 보존·삭제: `backend/app/services/retention.py`

원문은 최초 저장 전에 암호화하며, Redis·ChromaDB·감사 로그에는 원문이나 추출 텍스트를 넣지 않습니다. 업로드 형식을 추가할 때는 시그니처 검증, 추출 상한, 암호화 왕복, TTL 삭제 테스트를 함께 추가합니다.

## 분석과 근거 검증

- 전체 조정: `backend/app/services/analysis_pipeline.py`
- PII 게이트: `backend/app/prototype/pii.py`
- 규칙 기준선: `backend/app/rules/rule_engine.py`, `rules_v0_1.yaml`
- 검색: `backend/app/services/retrieval.py`
- LLM·검증: `backend/app/prototype/pipeline.py`, `backend/app/llm/`

처리 순서는 `PII 마스킹 → 규칙 → RAG 검색 → 분석 → 인용 검증`입니다. 검색과 외부 provider에는 마스킹된 조항만 전달합니다. 검증된 근거가 없거나 인용 ID가 맞지 않으면 결과를 `needs_review`로 유지합니다.

## 비동기 작업과 운영

- 큐 상태·재시도·DLQ: `backend/app/services/analysis_jobs.py`
- worker: `backend/scripts/run_worker.py`
- 준비 상태: `backend/app/api/health.py`
- 감사 조회: `backend/app/api/admin.py`

큐 메시지는 분석 ID만 포함합니다. 최대 재시도 이후에는 DLQ로 이동시키고 `analysis_failed` 감사 이벤트를 남깁니다. 관리자 감사 API는 토큰이 비어 있어도 열리지 않는 fail-closed 방식입니다.

## 화면과 리포트

- 화면 흐름: `frontend/components/AnalysisWorkspace.tsx`
- API 클라이언트: `frontend/lib/api.ts`
- PDF 생성: `backend/app/services/pdf_report.py`

화면은 법률 결론 대신 위험 신호, 근거 상태와 확인 질문을 표시합니다. 삭제 버튼은 서버 삭제가 성공한 뒤에만 로컬 화면 상태를 지웁니다. PDF는 완료된 분석에서만 만들고 생성 이벤트를 감사 로그에 남깁니다.

## 변경 후 최소 검증

```bash
make test-backend
make frontend-check
git diff --check
```

PostgreSQL·Redis·ChromaDB 또는 Compose 설정을 변경한 경우 `make infra-check`와 `docker compose up --build`도 실행하고, 실제로 실행하지 못한 항목은 매트릭스에 `verified`로 기록하지 않습니다.
