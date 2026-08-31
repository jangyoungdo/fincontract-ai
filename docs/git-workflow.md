# Git 협업 및 worktree 운영

## 목표

두 명 이상 또는 여러 코딩 에이전트가 동시에 작업할 때 파일과 브랜치 상태가 섞이지 않도록 작업 디렉터리를 물리적으로 분리합니다.

```text
fincontract-ai/                  main 전용 checkout
fincontract-worktrees/
├── api-foundation/              feature/api-foundation
├── pii-masking/                 feature/pii-masking
└── frontend-upload/             feature/frontend-upload
```

main checkout은 동기화와 worktree 관리에만 사용하고 기능 구현은 하지 않습니다.

## 최초 1회 로컬 설정

각 개발자는 clone 직후 아래 명령을 실행합니다.

```bash
./scripts/setup-dev.sh
```

이 설정은 현재 저장소에만 적용되며 다음을 보장합니다.

- `git pull`은 fast-forward만 허용
- 삭제된 원격 브랜치를 fetch 시 정리
- 반복 충돌 해결 기록 재사용
- 새 브랜치의 upstream 자동 설정
- `.githooks/pre-push`를 활성화해 `main` 직접 push 차단

## 새 작업 시작

```bash
cd fincontract-ai
git fetch origin --prune
git switch main
git pull --ff-only
./scripts/new-worktree.sh feature/pii-masking ../fincontract-worktrees/pii-masking
cd ../fincontract-worktrees/pii-masking
```

스크립트는 브랜치가 없으면 최신 `origin/main`에서 생성하고, 이미 존재하면 해당 브랜치로 worktree를 연결합니다.

## 충돌을 줄이는 작업 분할

| 영역 | 기본 소유 범위 |
|---|---|
| API·DB | `backend/app/api`, `backend/app/models`, migration |
| 문서 처리·PII | `backend/app/services/file_*`, `text_*`, `pii_*` |
| 규칙·RAG | `backend/app/rules`, `backend/app/vectorstore`, `research/` |
| Claude·grounding | `backend/app/llm`, grounding service |
| Frontend | `frontend/` |
| Infra·CI | Docker, workflow, 환경 설정 |

같은 파일을 두 작업자가 동시에 수정해야 한다면 먼저 인터페이스와 병합 순서를 이슈에 기록합니다.

## 동기화

작업 중에는 정기적으로 원격 main을 반영합니다.

```bash
git fetch origin --prune
git rebase origin/main
```

공유 중인 브랜치에서는 임의의 force push를 하지 않습니다. 개인 작업 브랜치를 rebase한 경우에도 `--force-with-lease`만 사용하고 PR 참여자에게 알립니다.

## 병합 정책

GitHub `main` 브랜치에 다음 보호 규칙을 권장합니다.

- pull request 필수
- 승인 1명 이상
- status check 필수: `repository-checks`
- conversation resolution 필수
- force push와 branch deletion 금지
- merge 전 최신 main 반영 필수

GitHub Free 개인 비공개 저장소에서 일부 규칙을 지원하지 않으면 팀 규칙과 PR 체크리스트로 동일한 절차를 유지합니다.

로컬 pre-push hook은 실수 방지 장치일 뿐 원격 보호 규칙의 대체물이 아닙니다. 저장소 관리자는 GitHub에서 branch protection 또는 repository ruleset을 별도로 활성화해야 합니다.

## worktree 종료

PR 병합 후 main checkout에서 실행합니다.

```bash
git fetch origin --prune
git switch main
git pull --ff-only
git worktree remove ../fincontract-worktrees/pii-masking
git branch -d feature/pii-masking
git worktree prune
```

미커밋 변경이 있는 worktree는 강제로 삭제하지 않습니다.
