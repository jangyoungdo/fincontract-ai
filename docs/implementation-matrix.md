# 시스템 아키텍처 구현·검증 매트릭스

아키텍처 이미지의 상자를 파일 존재 여부가 아니라 실제 실행 검증으로 추적합니다. `verified`는 아래 검증 명령과 결과가 확보된 경우에만 표시합니다.

| 레이어 | 구성요소 | 구현 상태 | 실행 검증 | 남은 제한 |
|---|---|---:|---:|---|
| Frontend | PDF 업로드 | implemented | TXT/PDF browser E2E + PDF component workflow verified | 스캔 PDF browser E2E pending |
| Frontend | 분석 대시보드 | implemented | browser E2E, unit/build verified | mock 분석만 연결 |
| Frontend | 원문 뷰어 | implemented | masked full-document + finding highlight unit/build verified | 마스킹 전 원문은 정책상 미제공 |
| Frontend | 은행 비교 | partial | API fail-closed + build verified | 검증된 비교 데이터 미확보로 결과 미제공 |
| Backend | FastAPI Gateway | implemented | API integration + worker status verified | sync/Redis async 전환은 환경 설정 |
| Backend | PDF/DOCX/TXT 처리 | implemented | native PDF/DOCX/table + OCR policy 8 tests, page/pixel/time/quality/encryption fail-closed verified | 실제 한국어 Tesseract·회전·표 browser E2E pending |
| Backend | PII 마스킹 | implemented | 6-case regression + injected OCR 주민번호 masking boundary verified | 실제 OCR 오인식 변형 회귀셋 pending |
| Backend | 조항 분리 | implemented | paragraph + DOCX table integration verified | PDF 복잡 표 구조 복원 제외 |
| Backend | 위험도 판정 | prototype | 8-rule unit verified | 합성 데이터, 전문가 검토 미완료 |
| Backend | LLM 분석 | partial | fake E2E + structured output, outbound PII, timeout/rate/schema/status, 8-call budget fault injection verified | 실제 Claude 1-call 연결·비용·보존정책 미검증 |
| Backend | 리포트 생성 | implemented | JSON/PDF API integration + browser download E2E verified | 다중 페이지 회귀셋 확장 필요 |
| RAG | 5개 컬렉션 | implemented | read/write + 공식 법령 7개 chunk ingest verified | 심결·판례·분쟁·조항패턴 verified corpus 미확보 |
| RAG | Hybrid Search | implemented | local hashing + local MiniLM 각각 7-query Hit@3 1.0/MRR 1.0, provider mismatch gate verified | 소규모 개발 평가이며 블라인드 전문가 평가 필요 |
| Data | PostgreSQL | implemented | local process read/write + idempotent migration verified | Alembic 전환 여부 미결정 |
| Data | Redis | implemented | local Redis success E2E + real Redis retry x2/DLQ/needs_review verified | 네트워크 단절·복구 시나리오 추가 필요 |
| Data | Data Pipeline | implemented | source/text/corpus SHA-256 manifest + 공식 법령 7건 idempotent ingest verified | 수집 자동화·원문 변경 감지·나머지 4개 corpus 확대 필요 |
| Data | Encrypted file storage | implemented | Fernet round-trip + plaintext absence verified | 운영 키 회전·외부 KMS 미구현 |
| Data | Audit / retention | implemented | lifecycle audit + document TTL + 365-day audit expiry + token-protected query verified | 관리자 조회 UI 미구현 |
| Infra | Docker Compose | implemented | 9-service contract, migration/corpus startup gates, sensitive-volume policy 3 tests verified | Docker·Colima 미설치로 clean build·restart E2E pending |
| Evaluation | 블라인드 전문가 평가 | partial | free-text/identity rejection, 2+ reviewer gate, Fleiss κ/disagreement synthetic fixture verified | 실제 비공개 평가셋·법률 검토자·합의판정 미확보 |

## 검증 단계

1. `make test-backend`: 순수 단위·통합 테스트
2. `make infra-check`: PostgreSQL, Redis, ChromaDB 실제 연결과 읽기·쓰기
3. `make api-check`: health, 업로드, 분석, 삭제 API
4. `make frontend-check`: TypeScript, Vitest, production build
5. `make e2e`: 샘플 API 업로드부터 결과 삭제까지 (브라우저 E2E는 별도 수동 검증)
6. `make compose-check`: 컨테이너 build/up, init 로그, 인프라 read/write, API·프런트엔드 smoke

각 단계의 실패는 다음 레이어를 완료 처리하지 않는 근거로 기록합니다.
