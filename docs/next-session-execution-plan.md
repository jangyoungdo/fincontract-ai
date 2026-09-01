# FinContract AI 남은 구현 실행 계획

기준일: 2026-08-31  
대상 브랜치: `codex/full-stack-foundation`  
상태 기준: `docs/implementation-matrix.md`

## 2026-09-01 진행 업데이트

- P0 완료: 공개 이력·비밀·고위험 의존성 검사, Dependabot, main 보호 규칙 적용
- P1 완료: macOS Colima arm64에서 9-service clean build/recreate, migration·corpus gate,
  PostgreSQL·Redis·Chroma read/write와 Frontend proxy 문서 lifecycle 검증. Windows WSL2 clean-room은 인계 단계에서 확인
- P2 런타임 부분 완료: Docker 이미지의 PDFium+한국어 Tesseract 설치와 page/pixel/time/quality gate,
  암호화 PDF 차단, OCR 결과 PII masking 경계 테스트 구현. 실제 한국어 스캔 PDF E2E는 미실행
- P3 안전 경계 완료/실제 호출 pending: outbound PII·schema·evidence·timeout·rate-limit,
  단일 retry budget, 분석당 8-call 상한, non-content telemetry와 1-call 점검 명령 구현
- P5 평가 배선 완료/실제 평가 pending: 자유서술·신원 필드 차단 annotation 계약,
  2인 이상 gate, Fleiss κ·불일치 보존 스크립트와 합성 fixture 구현

## 목표

남은 작업을 단순 기능 추가가 아니라 아래 네 가지 완료 조건으로 닫는다.

1. 실제 런타임에서 재현된다.
2. 원문·개인정보·비밀정보가 안전 경계를 넘지 않는다.
3. 실패했을 때 추정 결과를 만들지 않고 `needs_review`로 종료된다.
4. 실행 증거, 제한 사항, 버전이 문서와 테스트에 남는다.

## 현재 기준선

- PDF/DOCX/TXT 업로드, 암호화 저장, TTL, 분석, 리포트, 감사 API 구현
- 전체 마스킹 문서 뷰어와 6-case PII 회귀셋 구현
- 실제 Redis 성공 경로와 retry 2회 → DLQ → `needs_review` 검증
- 약관법 7개 조문 verified corpus와 로컬 hashing/MiniLM 검색 평가 구현
- Backend 87 tests, Frontend 10 tests, production build, Compose Frontend proxy E2E 통과
- 미완료 핵심: 실제 한국어 스캔 OCR, 실제 Claude, Windows WSL2 clean-room, 4개 corpus 확대, 전문가 평가,
  은행 비교 데이터, 운영 키 회전·관리자 UI·장애 복구

## 가장 효율적인 실행 순서

```text
공개 저장소 안전장치
  → Docker 재현 환경
  → OCR 입력 경로
  → 실제 Claude 안전 연결
  → 공개 법률 corpus 확대
  → 블라인드 전문가 평가
  → 운영·관리 기능
  → 전체 릴리스 검증
```

이 순서를 지키는 이유는 Docker가 OCR과 장애 재현의 공통 기반이고, OCR이 완료되어야
스캔 계약서의 PII 안전성을 검증할 수 있기 때문이다. Claude와 corpus 확대는 안전한
입력 경로가 확정된 뒤 진행하며, 전문가 평가는 시스템 구성이 고정된 후 수행한다.

## 내일 시작 시 필요한 사용자 결정 — 약 15분

| 결정 | 필요한 이유 | 결정 전 진행 가능한 범위 |
|---|---|---|
| Docker Desktop 또는 Colima 설치 승인 | Compose, OCR 시스템 패키지, 네트워크 장애 검증 | 코드·Dockerfile 작성과 정적 검증 |
| Claude 테스트 키와 최대 사용 예산 | 실제 structured output·보존정책·오류 검증 | fake provider 테스트 |
| 저장소 소스 라이선스 선택 | Public은 열람만 허용하며 재사용 권한을 자동 부여하지 않음 | 라이선스 없이 Public 유지 |
| 법률 검토자 확보 가능 여부 | 규칙·정답셋의 법률 타당성 검증 | 소프트웨어 배선 평가 |

키는 채팅이나 Git에 붙이지 않고 로컬 `.env` 또는 비밀 저장소에만 입력한다.

## P0. Public 저장소 안전장치

### 작업

1. Git 전체 이력에서 토큰, 개인키, `.env`, 업로드·리포트·DB 추적 여부 검사
2. `SECURITY.md`에 취약점 비공개 신고 경로와 테스트 데이터 정책 기록
3. 선택된 라이선스가 있으면 `LICENSE`와 제3자 데이터 고지 추가
4. Dependabot과 dependency/security workflow 활성화
5. GitHub branch protection 또는 ruleset 적용
   - PR 필수
   - repository checks 필수
   - main 직접 push 차단
   - force push와 branch deletion 차단

### 완료 조건

- secret scan 0건 또는 모든 탐지 건의 사유·조치 기록
- main 보호 규칙 활성화
- README에 데이터·법률·보안 한계가 보임

## P1. Docker Compose 전체 재현

### 작업

1. Backend, Frontend, PostgreSQL, Redis, Chroma, worker, retention을 clean build
2. health/readiness와 서비스 의존 순서를 검증
3. named volume과 bind mount의 민감 데이터 범위를 검토
4. 새 환경에서 migration → corpus ingest → API E2E → browser E2E 실행
5. 컨테이너 재시작 후 작업·DB·index 상태를 확인

### 완료 조건

- `docker compose up --build` 한 번으로 전체 서비스 기동
- health endpoint가 DB·Redis·Chroma 상태를 정확히 반영
- 종료·재기동 후 암호화 파일과 메타데이터 정책이 유지
- 로그에 원문·PII·키가 남지 않음

### 중단 조건

- Docker 설치 또는 관리자 권한이 필요하면 사용자 승인 전 시스템을 변경하지 않는다.

## P2. 스캔 PDF OCR

### 권장 구조

`PDF 판별 → 페이지 렌더링 → 로컬 OCR → 텍스트 품질 게이트 → PII 마스킹 → 기존 파이프라인`

운영 재현성을 위해 Docker 이미지에 Tesseract 한국어 모델을 고정하는 방식을 우선한다.
호스트에 직접 패키지를 설치하지 않는다. 모델·패키지 버전과 해시를 이미지 빌드에 남긴다.

### 작업

1. 텍스트 PDF와 스캔 PDF를 페이지별로 판별
2. 페이지 수·해상도·처리시간 상한을 적용해 PDF bomb와 무한 처리를 차단
3. OCR 결과가 최소 문자수·언어 비율 기준을 통과하지 못하면 `OCR_LOW_CONFIDENCE`
4. OCR 결과 전체에 PII 마스킹을 적용한 뒤에만 조항 분리·검색·LLM 허용
5. 한국어/숫자/표/회전/빈 페이지 fixture와 PII 잔존 회귀 테스트 추가

### 완료 조건

- 정상 스캔 PDF E2E 성공
- 저품질·암호화·과대 PDF가 정의된 오류 코드로 안전 종료
- OCR 전후 원문이 Chroma·Claude·로그에 전달되지 않음
- 처리 시간과 페이지 제한 테스트 통과

## P3. 실제 Claude 연결 검증

### 작업

1. 테스트 전용 키와 저비용 모델을 사용하고 호출 횟수·토큰 상한 설정
2. 합성 계약서만 사용해 experiment B/C/D의 structured output 검증
3. outbound payload를 테스트 double로 캡처해 마스킹 전 PII가 없음을 확인
4. timeout, rate limit, schema 오류, 빈 응답, 잘못된 evidence ID를 장애 주입
5. 모델명, prompt, corpus manifest, 비용, latency를 분석 결과에 기록
6. 공급자 보존정책과 배포 지역이 요구사항에 맞지 않으면 외부 호출을 비활성화

### 완료 조건

- 실제 응답이 출력 schema와 evidence ID 검증을 통과
- 장애 시 재시도 한도 이후 `needs_review`
- 원문 PII 외부 전송 0건
- 실행 비용과 latency가 문서화됨

## P4. 공개 법률 corpus 확대

### 우선순위

1. 공정위 심결·시정 사례
2. 법원 판례
3. 분쟁조정 사례
4. 검증된 위험·비위험 조항 패턴
5. 출처가 명확한 은행 상품 정보

### 작업

각 자료는 `출처 → 시행/결정일 → 라이선스 근거 URL → 재배포 여부 → 원문 hash →
중복 제거 → 평가셋 중복 검사 → manifest review`를 통과한 경우에만 적재한다.
641건·16건 같은 기존 후보 수치는 원본과 집계 단위가 확인될 때까지 목표치로 사용하지 않는다.

### 완료 조건

- 5개 Chroma collection 각각 최소 하나 이상의 verified record 보유
- stable ID 재적재가 add가 아니라 skip으로 종료
- 원문 변경은 update로 탐지되고 manifest 버전이 갱신
- corpus와 별도인 query set에서 Hit@K/MRR 및 근거 일치율 측정

## P5. 전문가 평가와 실험 A/C/D

### 작업

1. 실제 개인정보를 제거한 블라인드 계약 조항 평가셋 작성
2. 두 명 이상의 검토자가 위험도, 근거, 반대사정, 검토질문을 독립 평가
3. 불일치는 합의 결과뿐 아니라 사유와 원래 판단을 보존
4. 같은 입력·버전으로 A(규칙), C(RAG+분석), D(계획+검색+분석+검증) 실행
5. 품질, 검토시간, 비용, latency, 수정률을 함께 비교

### 완료 조건

- 규칙별 precision/recall/F1과 인용 일치율 확보
- 검토자 간 일치도와 수정·기각률 확보
- D가 C보다 이점이 없으면 C를 기본 구조로 채택
- 전문가 평가가 없으면 `production ready`로 표시하지 않음

## P6. 제품·운영 마감

### 작업

- 은행 비교: 기준일·출처·상품 조건이 검증된 데이터만 제공하고 stale 상태 표시
- 키 회전: key ID 기반 복호화, 신규 키 암호화, 점진적 재암호화, rollback 테스트
- 관리자 감사 UI: token 보호, 최소 정보, pagination, 접근 감사
- 관측성: analysis ID 중심 구조화 로그, latency·오류·DLQ 지표, 원문 배제
- 장애 복구: Redis/DB/Chroma 네트워크 단절·복구와 worker 재시작 검증

### 완료 조건

- 실패 모드별 운영 절차와 복구 명령 문서화
- 오래된 키·자료·감사 이벤트 만료 검증
- 브라우저에서 업로드부터 삭제·감사 확인까지 운영 E2E 통과

## P7. 최종 릴리스 게이트

아래 검증을 한 번의 기록 가능한 실행으로 수행한다.

```bash
make test-backend
make test-frontend
make infra-check
make failure-e2e
make ingest-public
make evaluate-public
docker compose up --build
```

추가로 PDF·DOCX·TXT·스캔 PDF 브라우저 E2E, Claude 장애 주입, Redis 네트워크 복구,
보존정책을 확인한다. 결과는 `docs/implementation-matrix.md`에 `implemented`,
`verified`, `partial`, `pending`으로 사실대로 반영한다.

## 내일 권장 시간표

| 시간 블록 | 목표 | 사용자 개입 |
|---|---|---|
| 0:00–0:15 | Docker, Claude 키, 라이선스, 검토자 결정 | 필요 |
| 0:15–1:00 | Public 저장소 보호·보안 문서 | 라이선스 선택 시 필요 |
| 1:00–2:30 | Compose clean build와 인프라 E2E | Docker 설치 시 필요 |
| 2:30–5:00 | OCR 구현·fixture·PII 회귀 | 불필요 |
| 5:00–6:00 | 실제 Claude 최소 호출·장애 검증 | 키 입력 필요 |
| 6:00–7:00 | 전체 회귀·매트릭스·도식 갱신·push | 불필요 |

하루 안에 모든 corpus와 전문가 평가까지 끝내려 하지 않는다. 내일의 현실적인 종료선은
`Compose 재현 + OCR 안전 경로 + 실제 Claude 최소 검증 + 전체 회귀 통과`다. 이후 공개
corpus 확대와 전문가 평가는 품질을 희생하지 않고 별도 작업 단위로 진행한다.

## 진행 로그 운영

- 장시간 작업은 사용자가 볼 수 있는 터미널 패널에서 실행한다.
- 각 명령의 시작·종료·exit code와 핵심 지표를 남긴다.
- 로그 파일에는 원문, 마스킹 전 PII, API 키를 기록하지 않는다.
- 60분 이상 걸리는 작업은 완료 여부가 아니라 현재 단계와 다음 검증을 중간 보고한다.
