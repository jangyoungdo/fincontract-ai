# FinContract AI Windows 11 개발·운영·롤백 가이드

## 문서 목적

이 문서는 Windows 11 + WSL2 + Docker Desktop 환경에서 FinContract AI를 매일 켜고 끄는
방법뿐 아니라 Windows VS Code와 Claude Code로 수정하고, Docker에 반영해 실험하고, 문제가
생겼을 때 안전하게 되돌리는 전체 과정을 설명합니다. 최초 설치와 저장소 준비가 끝난 사용자를
대상으로 하며, 프로그램 이름과 명령 입력 위치를 단계별로 구분합니다.

기준 프로젝트 위치는 다음과 같습니다.

```text
/home/skhb1/src/fincontract-ai
```

웹 접속 주소는 다음과 같습니다.

```text
http://localhost:3000
```

코드는 `C:\`로 복사하지 않고 WSL의 위 경로를 유일한 작업 복사본으로 유지합니다. Windows
VS Code는 WSL 확장을 통해 그 폴더를 열고, Git·Docker·Claude 명령은 WSL에서 실행합니다.

```text
Windows Docker Desktop ─┐
Windows VS Code ─────────┼─ WSL: Ubuntu ─ ~/src/fincontract-ai
Windows 웹 브라우저 ────┘                      │
                                               └─ Docker Compose
                                                  ├─ frontend
                                                  ├─ backend / worker / retention
                                                  └─ PostgreSQL / Redis / Chroma
```

## 안전 원칙

1. `.env`, 암호화 키, 관리자 토큰, 사용자 PDF와 분석 원문을 Claude 대화, GitHub, PR,
   메신저에 올리지 않습니다.
2. 기능 변경은 `main`이 아닌 작업 브랜치에서 시작합니다.
3. Claude에게 커밋과 push를 자동으로 맡기지 않습니다. 사람이 diff와 테스트 결과를 확인한
   뒤 수행합니다.
4. 코드 롤백과 데이터베이스 롤백은 다릅니다. migration이나 데이터 구조 변경은 담당자와
   복구 방법을 먼저 결정합니다.
5. 일반 종료와 롤백에 `docker compose down --volumes` 또는 `docker compose down -v`를
   사용하지 않습니다.
6. 명령은 코드 블록별로 한 줄씩 실행합니다. 서로 다른 명령을 붙여넣어 `frontenddocker`와
   같은 잘못된 서비스명을 만들지 않습니다.

## 전체 흐름

```text
앱 켜기
Windows → Docker Desktop → PowerShell → Ubuntu → Docker Compose → 웹 브라우저

앱 끄기
웹 브라우저 → Ubuntu → Docker Compose down → Ubuntu 종료 → Docker Desktop 종료(선택)
```

## 앱 켜기

### 1. Docker Desktop 실행

실행 프로그램: **Windows Docker Desktop**

1. Windows 시작 메뉴를 엽니다.
2. `Docker Desktop`을 검색해 실행합니다.
3. Docker Desktop이 `Engine running` 상태가 될 때까지 기다립니다.

Docker Desktop이 Windows 로그인 시 자동 실행되고 이미 정상 상태라면 이 단계는 생략합니다.
별도의 컨테이너를 Dashboard에서 수동 생성하거나 시작할 필요는 없습니다.

### 2. Ubuntu 터미널 실행

실행 프로그램: **Windows PowerShell**

관리자 권한이 아닌 일반 PowerShell에서 실행합니다.

```powershell
wsl -d Ubuntu
```

정상적으로 열리면 다음과 같은 Ubuntu 프롬프트가 표시됩니다.

```text
skhb1@localhost:~$
```

`/mnt/c/...` 위치에서 시작해도 다음 단계의 `cd` 명령으로 이동하면 됩니다.

### 3. 프로젝트 폴더로 이동

실행 프로그램: **Ubuntu 터미널**

```bash
cd ~/src/fincontract-ai
```

위치를 확인하려면 다음 명령을 사용합니다.

```bash
pwd
```

정상 결과:

```text
/home/skhb1/src/fincontract-ai
```

### 4. 전체 서비스 시작

실행 프로그램: **Ubuntu 터미널**

```bash
docker compose up --detach --wait
```

- `up`: Compose 서비스를 시작합니다.
- `--detach`: 터미널을 점유하지 않고 백그라운드에서 실행합니다.
- `--wait`: 필요한 서비스가 준비될 때까지 기다립니다.

코드를 수정하지 않은 평상시 실행에는 `--build`를 붙이지 않습니다.

### 5. 서비스 상태 확인

실행 프로그램: **Ubuntu 터미널**

```bash
docker compose ps --all
```

정상 상태 기준:

| 서비스 | 정상 상태 |
|---|---|
| `postgres`, `redis`, `chroma`, `backend` | `Up` 또는 `healthy` |
| `frontend`, `worker`, `retention` | `Up` |
| `migrate`, `corpus-init` | `Exited (0)` |

`migrate`와 `corpus-init`은 초기화 후 종료되는 일회성 서비스입니다. `Exited (0)`은 오류가
아니라 정상 완료를 의미합니다.

### 6. 웹 화면 접속

실행 프로그램: **Windows Chrome, Edge 등 웹 브라우저**

주소창에 다음 주소를 입력합니다.

```text
http://localhost:3000
```

업로드 화면이 나타나면 앱 실행이 완료된 것입니다. 브라우저 창만 닫아도 Docker 서비스는
계속 실행됩니다.

## 앱 끄기

### 1. Ubuntu 터미널 준비

기존 Ubuntu 터미널이 열려 있으면 그대로 사용합니다. 닫혀 있다면 Windows PowerShell에서
다시 실행합니다.

```powershell
wsl -d Ubuntu
```

### 2. 프로젝트 폴더로 이동

실행 프로그램: **Ubuntu 터미널**

```bash
cd ~/src/fincontract-ai
```

### 3. 서비스 안전 종료

실행 프로그램: **Ubuntu 터미널**

```bash
docker compose down
```

이 명령은 실행 중인 컨테이너와 Compose 네트워크를 종료하지만 다음 항목은 보존합니다.

- PostgreSQL 데이터
- Chroma 데이터
- 암호화된 업로드 파일과 리포트
- 빌드된 Docker 이미지
- 로컬 `.env`와 암호화 키

### 4. 종료 여부 확인

```bash
docker compose ps --all
```

실행 서비스 목록이 비어 있으면 정상적으로 종료된 것입니다.

### 5. Ubuntu 종료

```bash
exit
```

PowerShell로 돌아오거나 터미널 창이 닫힙니다.

### 6. Docker Desktop 종료 — 선택 사항

다른 Docker 작업을 사용하지 않는 경우에만 종료합니다.

1. Windows 오른쪽 아래 시스템 트레이를 엽니다.
2. Docker 고래 아이콘을 마우스 오른쪽 버튼으로 누릅니다.
3. **Quit Docker Desktop**을 선택합니다.

Docker Desktop 창의 `X`는 Dashboard 창만 닫고 엔진은 계속 실행할 수 있습니다.

## 범위를 모를 때 전체 재빌드

여러 영역을 동시에 바꿨거나 영향 서비스를 아직 판단할 수 없다면 전체 이미지를 다시 빌드합니다.
일상적인 단일 영역 변경은 아래의 `변경 영역별 Docker 반영` 절차로 필요한 서비스만 빌드하는
편이 더 빠릅니다.

```bash
cd ~/src/fincontract-ai
docker compose up --build --detach --wait
```

코드를 변경하지 않았다면 더 빠른 일반 시작 명령을 사용합니다.

```bash
docker compose up --detach --wait
```

## 로그 확인

Backend, Worker, Frontend의 최근 로그를 계속 확인합니다.

```bash
cd ~/src/fincontract-ai
docker compose logs --follow --tail=100 backend worker frontend
```

로그 보기에서 나갈 때는 `Ctrl+C`를 누릅니다. 이 동작은 로그 보기만 종료하며 백그라운드
컨테이너는 계속 실행됩니다.

지원 요청에 `.env`, 암호화 키, 관리자 토큰, 계약서 내용이나 분석 원문을 포함하지 않습니다.
안전한 진단 정보가 필요하면 다음 명령을 사용합니다.

```bash
./scripts/collect-diagnostics.sh
```

## 코드 수정 후 자동 스모크 테스트

다음 명령은 합성 문서를 사용해 Frontend 프록시부터 업로드, Worker 분석, PDF 리포트와 삭제까지
확인합니다. 사용자 계약서는 사용하지 않습니다.

```bash
docker compose run --rm --no-deps -T -v "$PWD/scripts:/smoke:ro" -v "$PWD/backend/tests/fixtures:/fixtures:ro" -e FRONTEND_SMOKE_ADDRESS=frontend:3000 backend python /smoke/check_frontend_proxy.py /fixtures/e2e-contract.txt
```

정상 결과에는 다음 문구가 포함됩니다.

```text
[proxy] lifecycle passed
```

## 비정상 상황별 확인

### `docker` 명령을 찾을 수 없음

1. Docker Desktop이 실행 중인지 확인합니다.
2. Docker Desktop의 **Settings → Resources → WSL Integration**에서 Ubuntu가 활성화되어
   있는지 확인합니다.
3. Ubuntu 터미널을 닫았다가 다시 실행합니다.

Ubuntu 내부에 별도 Docker Engine을 임의로 설치하지 않습니다.

### Docker daemon 연결 실패

Docker Desktop이 `Engine running` 상태인지 확인한 후 다시 시도합니다.

```bash
docker version
```

Client와 Server 정보가 모두 나오면 정상입니다.

### 웹 페이지가 열리지 않음

```bash
docker compose ps --all
```

Frontend와 Backend 상태를 확인한 다음 제한된 진단 정보를 수집합니다.

```bash
./scripts/collect-diagnostics.sh
```

### 포트 충돌 또는 시작 실패

임의로 포트를 변경하지 말고 사전 점검을 다시 실행합니다.

```bash
./scripts/check-compose-prereqs.sh
```

## 데이터 삭제 주의

평소에는 다음 명령만 사용합니다.

```bash
docker compose down
```

다음 명령은 PostgreSQL, Chroma, 업로드와 리포트 볼륨까지 삭제하므로 사용하지 않습니다.

```bash
docker compose down --volumes
```

축약형인 `docker compose down -v`도 동일하게 데이터를 삭제합니다.

## 비밀값과 로컬 데이터

- `.env`를 Git, 메신저, 이메일 또는 PR에 올리지 않습니다.
- `DOCUMENT_ENCRYPTION_KEY`를 잃거나 변경하면 기존 암호화 문서를 읽지 못할 수 있습니다.
- 각 노트북은 서로 다른 암호화 키와 관리자 토큰을 사용합니다.
- PDF와 분석 원문은 코드 저장소에 추가하지 않습니다.
- 실험 결과가 생성되는 `output/`은 로컬에만 보관합니다.

## Windows VS Code로 WSL 프로젝트 열기

Windows VS Code에 Microsoft의 `WSL` 확장을 설치한 뒤 다음 순서로 엽니다.

1. VS Code에서 `Ctrl+Shift+P`를 누릅니다.
2. `WSL: Connect to WSL using Distro`를 선택합니다.
3. `Ubuntu`를 선택합니다.
4. `File → Open Folder`에서 `/home/skhb1/src/fincontract-ai`를 엽니다.
5. 저장소 신뢰 여부를 묻는다면 경로를 확인한 후 승인합니다.

정상이라면 왼쪽 아래에 `WSL: Ubuntu`가 표시되고 탐색기에 `backend`, `frontend`,
`docker-compose.yml` 등이 나타납니다. VS Code의 `Terminal → New Terminal`에서 다음을
확인합니다.

```bash
pwd
```

```bash
git status --short --branch
```

WSL에서 `code .`을 찾지 못해도 위 방식으로 폴더가 열리면 개발에는 문제가 없습니다. 다음
명령으로 Ubuntu용 VS Code를 중복 설치하지 않습니다.

```bash
sudo snap install code
```

## GitHub와 작업 브랜치

### 원격 저장소 역할 확인

```bash
git remote -v
```

인계 노트북의 정상 구성은 다음과 같습니다.

```text
origin    https://github.com/skhb12050523-lab/fincontract-ai-real (fetch)
origin    https://github.com/skhb12050523-lab/fincontract-ai-real (push)
upstream  https://github.com/jangyoungdo/fincontract-ai.git (fetch)
upstream  DISABLED (push)
```

- `origin`: 친구가 브랜치와 PR을 올리는 포크
- `upstream`: 원본 변경을 읽어오는 저장소

### 새 작업 시작

수정 전에 현재 상태를 확인합니다.

```bash
git status --short --branch
```

새 기능은 깨끗한 `main`에서 목적이 드러나는 브랜치를 만들어 시작합니다.

```bash
git switch main
```

```bash
git pull --ff-only origin main
```

```bash
git switch -c codex/작업-이름
```

`작업-이름`은 실제 목적에 맞는 영문 소문자와 하이픈으로 바꿉니다. 한 브랜치에서는 한 기능만
수정합니다. 현재 UI 실습 브랜치는 `codex/first-maintenance-experiment`입니다.

## Claude Code로 안전하게 작업하기

### Claude 시작

실행 프로그램: **VS Code의 WSL 터미널**

```bash
cd ~/src/fincontract-ai
```

```bash
claude
```

새 터미널에서 `claude`를 찾지 못하지만 설치 파일이 `~/.local/bin/claude`에 있다면 다음처럼
직접 실행할 수 있습니다.

```bash
~/.local/bin/claude
```

현재 터미널에서 짧은 명령을 사용하려면 PATH를 연결합니다.

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Claude가 프로젝트 신뢰를 물으면 `/home/skhb1/src/fincontract-ai`가 맞는지 확인합니다. Claude가
읽거나 수정하려는 파일은 요청 범위와 일치할 때만 승인합니다.

### 요청문 템플릿

아래 대괄호를 실제 작업 내용과 파일로 바꿉니다.

```text
현재 작업 브랜치에서 [원하는 변경]을 구현해주세요.

범위:
- 수정 허용: [수정할 파일 또는 디렉터리]
- 수정 금지: Backend, API 계약, Docker 설정, .env, 데이터 파일

안전 조건:
- .env, 비밀값, 업로드 문서와 분석 원문을 읽거나 출력하지 마세요.
- 기존 기능을 삭제하거나 우회하지 마세요.
- 관련 테스트와 빌드 검사를 실행하세요.
- 커밋하거나 push하지 마세요.
- 변경 파일, 핵심 diff와 검사 결과만 보고한 뒤 기다리세요.
```

### Claude 작업 후 직접 확인

Claude의 설명만 보고 push하지 않습니다. 새 WSL 터미널에서 직접 확인합니다.

```bash
git status --short
```

```bash
git diff --stat
```

```bash
git diff
```

다음을 확인합니다.

- 요청하지 않은 파일이 바뀌지 않았는가
- `.env`, PDF, `output/`이 포함되지 않았는가
- Backend나 Docker 설정 같은 범위 밖 변경이 없는가
- 삭제된 코드가 실제 의도와 일치하는가

## 변경 영역별 Docker 반영

파일 저장만으로 실행 중인 컨테이너가 자동 변경되지는 않습니다. 먼저 이미지를 빌드하고, 빌드가
성공했을 때 서비스를 재기동합니다. 이 두 단계를 분리하면 빌드 실패 시 기존 정상 컨테이너를
유지하기 쉽습니다.

### Frontend만 수정

대상 예시: `frontend/components/`, `frontend/app/`, `frontend/lib/`

```bash
docker compose build frontend
```

빌드 성공 후:

```bash
docker compose up --detach frontend
```

```bash
docker compose ps frontend
```

Windows 브라우저에서 `http://localhost:3000`을 열고 `Ctrl+F5`로 강력 새로고침합니다.

### Backend API만 수정

대상 예시: `backend/app/api/`, API 응답 모델과 상태 확인 코드

```bash
docker compose build backend
```

```bash
docker compose up --detach --wait backend
```

```bash
curl http://localhost:8000/health/ready
```

### 분석 규칙·파이프라인 수정

분석 요청은 Backend가 받고 실제 분석은 Worker가 수행하므로 두 서비스를 함께 반영합니다.

```bash
docker compose build backend worker
```

```bash
docker compose up --detach --wait backend worker
```

### 보존 정책 수정

```bash
docker compose build retention
```

```bash
docker compose up --detach retention
```

### Dockerfile·Compose·의존성 수정

```bash
./scripts/check-compose-prereqs.sh
```

```bash
docker compose build
```

```bash
docker compose up --detach --wait
```

## 수정 결과 확인

### 로그 확인

```bash
docker compose logs --follow --tail=100 frontend backend worker
```

로그 보기를 끝낼 때 `Ctrl+C`를 누릅니다. 로그 보기만 종료되며 컨테이너는 계속 실행됩니다.

### 수동 확인표

- `http://localhost:3000`이 열리는가
- 변경한 UI가 보이고 클릭 동작이 정상인가
- Backend `/health/ready`가 `ready`인가
- 파일 업로드와 분석 상태 변화가 유지되는가
- 로그에 반복 재시작이나 예외가 없는가
- 합성 문서 스모크 테스트가 `[proxy] lifecycle passed`로 끝나는가

## 변경 확정과 GitHub 반영

테스트가 성공한 경우에만 커밋합니다.

```bash
git status --short
```

```bash
git diff --check
```

`git add .` 대신 검토한 파일만 명시합니다. 다음은 UI 실습 예시입니다.

```bash
git add frontend/components/AnalysisWorkspace.tsx frontend/app/globals.css
```

```bash
git diff --cached
```

```bash
git commit -m "feat(frontend): add local UI experiment control"
```

```bash
git push
```

GitHub에서 작업 브랜치에서 친구 포크의 `main`으로 PR을 만들고 diff와 비민감 테스트 결과를
다시 확인합니다. 원본 저장소 반영이 필요할 때만 별도의 upstream PR을 만듭니다.

## 잘못 수정했을 때 안전한 롤백

롤백 전 현재 상태를 확인합니다.

```bash
git status --short --branch
```

```bash
git diff --stat
```

무엇을 되돌리는지 모르는 상태에서는 `git reset --hard`, `git clean -fd` 또는 볼륨 삭제 명령을
실행하지 않습니다.

### 아직 커밋하지 않은 파일 하나 되돌리기

먼저 버릴 내용을 확인합니다.

```bash
git diff -- frontend/components/AnalysisWorkspace.tsx
```

해당 파일의 수정 전체를 버려도 되는 경우에만 실행합니다.

```bash
git restore -- frontend/components/AnalysisWorkspace.tsx
```

CSS도 별도로 확인하고 되돌립니다.

```bash
git diff -- frontend/app/globals.css
```

```bash
git restore -- frontend/app/globals.css
```

Claude가 새 파일을 만들었다면 `git status --short`로 이름을 확인합니다. 추적되지 않은 파일은
`git restore`로 없어지지 않으므로 바로 삭제하지 말고 저장소 밖에 보관합니다.

```bash
mkdir -p ~/fincontract-rollback-backup
```

```bash
mv 새파일경로 ~/fincontract-rollback-backup/
```

### 커밋했지만 push하지 않은 변경 되돌리기

이력 자체를 없애는 reset보다 되돌림 기록이 남는 `revert`를 사용합니다.

```bash
git log --oneline -5
```

```bash
git revert 잘못된-커밋-해시
```

### 이미 GitHub에 push한 변경 되돌리기

공유된 브랜치에는 force push를 사용하지 않습니다.

```bash
git pull --ff-only
```

```bash
git revert 잘못된-커밋-해시
```

```bash
git push
```

PR이 아직 병합되지 않았다면 되돌림 커밋을 포함하거나 PR을 닫습니다. 이미 `main`에 병합됐다면
`main`을 강제로 이전 상태로 움직이지 말고 revert PR을 사용합니다.

### 롤백한 코드를 Docker에 다시 반영

Git 파일만 되돌려도 잘못된 이미지가 컨테이너에서 계속 실행될 수 있습니다. 소스를 되돌린 뒤
영향 서비스를 다시 빌드하고 재기동합니다.

Frontend 롤백:

```bash
docker compose build frontend
```

```bash
docker compose up --detach frontend
```

Backend와 Worker 롤백:

```bash
docker compose build backend worker
```

```bash
docker compose up --detach --wait backend worker
```

그다음 상태, 로그와 스모크 테스트를 다시 확인합니다.

### 빌드 자체가 실패

```bash
docker compose ps --all
```

기존 컨테이너가 `Up`이면 사용 가능한 이전 이미지가 계속 실행 중일 수 있으므로 전체를 무작정
내리지 않습니다. 빌드 로그의 마지막 오류부터 수정한 뒤 해당 서비스의 build를 다시 실행합니다.

### migration·DB·볼륨 문제

다음은 일반 코드 롤백보다 영향이 큽니다.

- 데이터베이스 migration 변경
- corpus 구조 변경
- 암호화 키 변경 또는 분실
- PostgreSQL·Chroma·업로드 볼륨 초기화

이 경우 `git restore`만 실행하거나 볼륨을 삭제하지 않습니다. 현재 상태와 로그를 보존하고
저장소 관리자와 복구 방법을 결정합니다.

## 매 작업 체크리스트

### 시작

- [ ] Docker Desktop이 실행 중이다.
- [ ] VS Code 왼쪽 아래에 `WSL: Ubuntu`가 보인다.
- [ ] 터미널 경로가 `/home/skhb1/src/fincontract-ai`다.
- [ ] 작업 브랜치를 확인했다.
- [ ] Compose 서비스 상태가 정상이다.

### 수정과 검증

- [ ] Claude에게 수정 허용·금지 범위를 명시했다.
- [ ] `.env`, PDF와 비밀값을 노출하지 않았다.
- [ ] `git diff`를 직접 검토했다.
- [ ] 영향 서비스만 빌드하고 재기동했다.
- [ ] 로그, 화면과 스모크 테스트를 확인했다.

### GitHub 반영과 종료

- [ ] 검토한 파일만 stage하고 커밋했다.
- [ ] 친구 포크의 작업 브랜치에 push했다.
- [ ] 필요한 변경을 확정하거나 안전하게 롤백했다.
- [ ] `docker compose down`으로 종료했다.
- [ ] 볼륨 삭제 옵션을 사용하지 않았다.

## 일상 명령 요약

켜기:

```powershell
wsl -d Ubuntu
```

```bash
cd ~/src/fincontract-ai
docker compose up --detach --wait
docker compose ps --all
```

접속:

```text
http://localhost:3000
```

끄기:

```bash
cd ~/src/fincontract-ai
docker compose down
exit
```
