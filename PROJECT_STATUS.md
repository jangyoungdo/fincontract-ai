# 프로젝트 상태

## 현재 단계

`실험 001 진행 — 여신약관 3개 규칙 기준선`

## 확보된 산출물

- `assets/fincontract-ai-architecture-v3.png`: 현재 기준 최종 아키텍처 이미지
- `prompts/project_scaffolding_prompt_v2.md`: 구현 요구사항과 승인 기준
- `docs/`: 아키텍처, 법률 경계, 데이터 관리, 평가 기준
- `research/`: 공개 리서치 코퍼스와 manifest를 위한 격리 영역
- `backend/`, `frontend/`: 구현 대상 모노레포 구조
- `CONTRIBUTING.md`, `docs/git-workflow.md`: 2인 이상 협업과 worktree 운영 규칙
- `.github/`: Pull Request 템플릿과 저장소 기본 검사
- `scripts/setup-dev.sh`, `.githooks/pre-push`: 저장소별 협업 설정과 main 직접 push 방지
- `experiments/001-rule-baseline/`: 첫 번째 버티컬 AI 비교 실험 명세
- `backend/app/rules/`: 합성 데이터로 검증하는 3개 위험 신호 규칙 기준선

## 아직 확인되지 않은 사항

- 불공정약관 관련 자료 후보 641건의 원본과 집계 단위
- 분쟁사례 후보 16건의 원본과 포함 기준
- 각 자료의 라이선스 및 재배포 가능 여부
- 8개 규칙의 법률 전문가 검토 여부
- 실제 Claude API의 배포 환경별 보존 정책

## 다음 구현 단계

1. 실험 001 규칙 엔진과 합성 스모크 평가 완료
2. 첫 대상 공개 약관의 출처·라이선스 manifest 검증
3. 규칙 작성 자료와 분리된 전문가 검토 평가셋 구축
4. 실험 A 실제 기준선 측정
5. 동일 출력 스키마의 실험 C(RAG + 단일 분석 에이전트) 구현
6. A/C 비교 후 계획·검증 에이전트 도입 여부 결정

구현 단계가 완료될 때마다 이 문서의 상태와 검증 결과를 갱신합니다.
