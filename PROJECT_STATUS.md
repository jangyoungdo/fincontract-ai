# 프로젝트 상태

## 현재 단계

`준비 완료 — 구현 전 검증 게이트`

## 확보된 산출물

- `assets/fincontract-ai-architecture-v3.png`: 현재 기준 최종 아키텍처 이미지
- `prompts/project_scaffolding_prompt_v2.md`: 구현 요구사항과 승인 기준
- `docs/`: 아키텍처, 법률 경계, 데이터 관리, 평가 기준
- `research/`: 공개 리서치 코퍼스와 manifest를 위한 격리 영역
- `backend/`, `frontend/`: 구현 대상 모노레포 구조
- `CONTRIBUTING.md`, `docs/git-workflow.md`: 2인 이상 협업과 worktree 운영 규칙
- `.github/`: Pull Request 템플릿과 저장소 기본 검사
- `scripts/setup-dev.sh`, `.githooks/pre-push`: 저장소별 협업 설정과 main 직접 push 방지

## 아직 확인되지 않은 사항

- 불공정약관 관련 자료 후보 641건의 원본과 집계 단위
- 분쟁사례 후보 16건의 원본과 포함 기준
- 각 자료의 라이선스 및 재배포 가능 여부
- 8개 규칙의 법률 전문가 검토 여부
- 실제 Claude API의 배포 환경별 보존 정책

## 다음 구현 단계

1. 환경 및 패키지 설정
2. DB 모델과 API 스키마
3. 파일 검증·추출·PII 마스킹
4. YAML 규칙 엔진
5. 리서치 manifest 검증과 ChromaDB 적재
6. Claude provider와 grounding 검증
7. 분석 API 및 frontend
8. Docker·통합 테스트·평가

구현 단계가 완료될 때마다 이 문서의 상태와 검증 결과를 갱신합니다.
