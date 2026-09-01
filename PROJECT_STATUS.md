# 프로젝트 상태

## 현재 단계

`전체 스택 MVP 구현 완료 — 공개 법령 RAG 확보, Claude·컨테이너 운영 검증 대기`

## 확보된 산출물

- `assets/fincontract-ai-architecture-v3.png`: 현재 기준 최종 아키텍처 이미지
- `prompts/project_scaffolding_prompt_v2.md`: 구현 요구사항과 승인 기준
- `docs/`: 아키텍처, 법률 경계, 데이터 관리, 평가 기준
- `research/`: 공개 리서치 코퍼스와 manifest를 위한 격리 영역
- `research/public_corpus/statutes.jsonl`: 출처와 SHA-256을 고정한 약관법 7개 조문
- `backend/`, `frontend/`: 구현 대상 모노레포 구조
- `CONTRIBUTING.md`, `docs/git-workflow.md`: 2인 이상 협업과 worktree 운영 규칙
- `.github/`: Pull Request 템플릿과 저장소 기본 검사
- `scripts/setup-dev.sh`, `.githooks/pre-push`: 저장소별 협업 설정과 main 직접 push 방지
- `experiments/001-rule-baseline/`: 첫 번째 버티컬 AI 비교 실험 명세
- `backend/app/rules/`: 합성 데이터로 검증하는 14개 위험 신호 규칙 기준선과 규칙 미매핑 로컬 검토 후보
- `backend/app/services/`: 암호화 저장, 문서 처리, RAG 검색, 비동기 작업, 감사·보존, PDF 리포트
- `backend/app/api/`: 문서·분석·리포트와 보호된 관리자 감사 API
- `frontend/`: 비개발자용 업로드·분석·근거·PDF 다운로드 화면
- `docs/implementation-matrix.md`: 레이어별 구현·실행 검증과 남은 외부 의존성

## 아직 확인되지 않은 사항

- 불공정약관 관련 자료 후보 641건의 원본과 집계 단위
- 분쟁사례 후보 16건의 원본과 포함 기준
- 심결·판례·분쟁사례·표준약관 자료의 개별 라이선스 및 재배포 가능 여부
- 14개 규칙의 법률 전문가 검토 여부
- 실제 Claude API의 배포 환경별 보존 정책

## 다음 검증 단계

1. 공정위 심결·판례·분쟁사례의 재배포 조건을 개별 확인하고 코퍼스를 확대
2. 규칙 작성 자료와 분리된 전문가 검토 평가셋 구축
3. 실험 A/C/D 실제 기준선과 검토자 동의율 측정
4. 승인된 Claude 키로 structured output 연결 검증
5. Docker 런타임에서 전체 Compose와 네트워크 단절·복구 E2E 실행
6. 운영 KMS 키 회전과 관리자 감사 UI 범위 결정

구현 단계가 완료될 때마다 이 문서의 상태와 검증 결과를 갱신합니다.

내일 이후의 의존성, 완료 조건, 권장 시간표는
[남은 구현 실행 계획](docs/next-session-execution-plan.md)을 기준으로 진행합니다.
