# 시스템 아키텍처 구현·검증 매트릭스

아키텍처 이미지의 상자를 파일 존재 여부가 아니라 실제 실행 검증으로 추적합니다. `verified`는 아래 검증 명령과 결과가 확보된 경우에만 표시합니다.

| 레이어 | 구성요소 | 구현 상태 | 실행 검증 | 남은 제한 |
|---|---|---:|---:|---|
| Frontend | PDF 업로드 | implemented | TXT browser E2E verified | 실제 PDF browser E2E 추가 필요 |
| Frontend | 분석 대시보드 | implemented | browser E2E, unit/build verified | mock 분석만 연결 |
| Frontend | 원문 뷰어 | partial | build verified | 마스킹 조항만 표시, 전체 원문 미제공 |
| Frontend | 은행 비교 | partial | API fail-closed + build verified | 검증된 비교 데이터 미확보로 결과 미제공 |
| Backend | FastAPI Gateway | implemented | API integration verified | 동기식 분석 runner |
| Backend | PDF/DOCX/TXT 처리 | implemented | TXT browser E2E, real PDF/DOCX API verified | 실제 PDF/DOCX browser E2E 추가 필요 |
| Backend | PII 마스킹 | prototype | unit verified | 이름·주소 탐지 미완료 |
| Backend | 조항 분리 | implemented | integration verified | 복잡한 표·OCR 제외 |
| Backend | 위험도 판정 | prototype | 8-rule unit verified | 합성 데이터, 전문가 검토 미완료 |
| Backend | LLM 분석 | implemented | fake-provider E2E, opt-in/fail-closed tests | 실제 Claude 키·연결 미검증 |
| Backend | 리포트 생성 | partial | API integration verified | JSON 리포트만 제공, PDF/다운로드 미구현 |
| RAG | 5개 컬렉션 | implemented | read/write verified | 실제 검증 코퍼스 없음 |
| RAG | Hybrid Search | implemented | synthetic retrieval and analysis grounding verified | hashing vector는 데모 전용 |
| Data | PostgreSQL | implemented | local process read/write + idempotent migration verified | Alembic 전환 여부 미결정 |
| Data | Redis | implemented | local Redis worker E2E (`queued→completed`) verified | 재시도·DLQ 코드 구현, 실패 E2E 추가 필요 |
| Data | Data Pipeline | implemented | manifest/ingest/index verified | 합성 3건만 적재 |
| Infra | Docker Compose | implemented | pending | Docker·Colima 미설치 |

## 검증 단계

1. `make test-backend`: 순수 단위·통합 테스트
2. `make infra-check`: PostgreSQL, Redis, ChromaDB 실제 연결과 읽기·쓰기
3. `make api-check`: health, 업로드, 분석, 삭제 API
4. `make frontend-check`: TypeScript, Vitest, production build
5. `make e2e`: 샘플 API 업로드부터 결과 삭제까지 (브라우저 E2E는 별도 수동 검증)
6. `docker compose up --build`: 컨테이너 전체 기동

각 단계의 실패는 다음 레이어를 완료 처리하지 않는 근거로 기록합니다.
