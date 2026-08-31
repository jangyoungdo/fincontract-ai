# 기여 가이드

## 1. 저장소 준비

```bash
git clone <repository-url> fincontract-ai
cd fincontract-ai
git switch main
git pull --ff-only
./scripts/setup-dev.sh
```

공유 개발에서는 같은 디렉터리에서 브랜치를 바꾸지 말고 작업별 worktree를 사용합니다.

```bash
./scripts/new-worktree.sh feature/api-foundation ../fincontract-worktrees/api-foundation
```

자세한 내용은 [Git 협업 및 worktree 운영](docs/git-workflow.md)을 참고하세요.

`setup-dev.sh`는 이 저장소에만 fast-forward pull, 원격 정리, conflict resolution 재사용과 versioned Git hook을 설정합니다. 전역 Git 설정은 변경하지 않습니다.

## 2. 브랜치 이름

- `feature/<issue>-<summary>`: 기능
- `fix/<issue>-<summary>`: 버그
- `docs/<issue>-<summary>`: 문서
- `research/<issue>-<summary>`: 리서치 코퍼스
- `chore/<issue>-<summary>`: 도구와 설정
- 에이전트 전용 작업은 `codex/<summary>` 사용 가능

브랜치 이름은 소문자 영문, 숫자와 하이픈을 사용합니다.

## 3. 커밋

예시:

```text
feat(api): add document upload validation
fix(pii): prevent raw text in provider payload
docs(architecture): clarify corpus boundary
research(manifest): add verified FTC source batch
```

## 4. Pull Request

- 하나의 PR은 하나의 목적만 가집니다.
- draft PR을 일찍 열어 작업 경계를 공유합니다.
- 관련 이슈를 연결합니다.
- 테스트·정적 검사·문서 검사를 통과합니다.
- PII 흐름, 법률 표현 또는 RAG 코퍼스가 바뀌면 PR 템플릿의 안전성 항목을 반드시 작성합니다.
- 이미지 또는 UI 변경에는 전후 스크린샷을 포함합니다.

## 5. 병합

- `main` 직접 push를 금지합니다.
- 최소 1명 승인과 CI 통과 후 squash merge합니다.
- 병합 후 사용한 worktree와 로컬 브랜치를 정리합니다.

```bash
git worktree remove ../fincontract-worktrees/api-foundation
git branch -d feature/api-foundation
git worktree prune
```
