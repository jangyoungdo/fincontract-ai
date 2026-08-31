# FinContract AI

금융 계약서에서 불공정 가능성이 있는 위험 신호를 찾고, 검증 가능한 법적 근거와 분쟁사례를 함께 제시하는 의사결정 지원 서비스입니다.

이 프로젝트는 법률 자문, 위법성 확정 또는 재판 결과 예측을 제공하지 않습니다. 결과는 위험 신호와 검토 필요성을 설명하는 보조 자료이며 최종 판단에는 전문가 검토가 필요합니다.

![FinContract AI 시스템 아키텍처](assets/fincontract-ai-architecture-v3.png)

## 현재 상태

- 프로젝트 스캐폴딩 프롬프트 v2 작성 완료
- 시스템 아키텍처 이미지 v3 작성 완료
- 모노레포 디렉터리와 데이터 거버넌스 시작 문서 준비 완료
- 독립 Git 저장소와 worktree 기반 협업 규칙 준비 완료
- 실제 애플리케이션 코드는 아직 구현하지 않음
- 리서치 통계 641건·16건은 근거 manifest 검증 전까지 후보 수로만 관리

상세 상태와 다음 작업은 [PROJECT_STATUS.md](PROJECT_STATUS.md)를 참고하세요.

## 핵심 처리 순서

```text
파일 검증·로컬 추출
  → PII 마스킹·검증
  → 조항 분리
  → 8개 규칙 엔진
  → ChromaDB 근거 검색
  → Claude 구조화 분석
  → 근거·인용 검증
  → 결과 저장 및 리포트
```

마스킹되지 않은 사용자 원문은 ChromaDB 또는 Claude API로 전달하지 않습니다. ChromaDB에는 검증된 공개·허가 리서치 코퍼스만 적재합니다.

## 기술 방향

- Frontend: Next.js App Router, TypeScript, Tailwind CSS
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2
- Operational data: PostgreSQL
- Retrieval: ChromaDB
- LLM: Anthropic Claude Messages API + Structured Outputs
- Optional async processing: Redis + Worker
- Local runtime: Docker Compose

## 주요 문서

- [스캐폴딩 프롬프트 v2](prompts/project_scaffolding_prompt_v2.md)
- [아키텍처 설명](docs/architecture.md)
- [법률 판단 경계](docs/legal-boundary.md)
- [데이터 거버넌스](docs/data-governance.md)
- [평가 기준](docs/evaluation.md)
- [기여 가이드](CONTRIBUTING.md)
- [Git 협업 및 worktree 운영](docs/git-workflow.md)
- [리서치 자료 준비 안내](research/README.md)

## 협업 원칙

- `main`은 동기화와 배포 기준으로만 사용합니다.
- 기능 구현은 작업별 브랜치와 별도 worktree에서 수행합니다.
- Pull Request는 최소 1명 승인과 CI 통과 후 squash merge합니다.
- 새 worktree는 `scripts/new-worktree.sh`로 생성합니다.

## 구현 시작 게이트

다음 항목을 확정한 뒤 1단계 구현을 시작합니다.

1. 리서치 원본 파일과 출처 목록 확보
2. 641건·16건의 집계 기준 및 중복 제거 기준 확인
3. 공개 자료별 라이선스·재배포 가능 여부 확인
4. Python 3.12와 Node 런타임 버전 고정
5. MVP에서 Redis Worker를 사용할지 결정
