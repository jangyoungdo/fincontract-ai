# Windows 11 + WSL2 단계별 인계 가이드

이 문서는 Intel/AMD x64 Windows 11 노트북에서 FinContract AI를 재현하는 체크포인트입니다.
한 번에 한 단계만 실행하고, 각 단계의 정상 여부를 확인한 뒤 다음 단계로 이동합니다.
비밀번호, `.env`, 암호화 키, 관리자 토큰, 계약서 내용은 이슈·PR·메신저에 붙여넣지 않습니다.

## 진행 규칙

- 명령은 코드 블록 단위로 하나씩 실행합니다.
- 오류가 나면 다음 명령을 실행하지 않고 오류 메시지와 단계 번호만 공유합니다.
- 비밀값은 값 자체가 아니라 설정 성공 여부만 확인합니다.
- `docker compose down -v`는 로컬 DB와 업로드·리포트 볼륨을 삭제하므로 이 가이드에서는 사용하지 않습니다.

## 1. Windows 환경 확인 — PowerShell

다음 명령은 시스템을 변경하지 않습니다.

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture, TotalVisibleMemorySize, FreePhysicalMemory
```

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, AddressWidth, NumberOfLogicalProcessors
```

```powershell
Get-PSDrive C | Select-Object Name, Used, Free
```

```powershell
wsl --status
```

```powershell
wsl --list --verbose
```

완료 조건은 Windows 11, 64비트 CPU, WSL 기본 버전 2입니다. 권장 자원은 논리 CPU 4개,
WSL에서 사용 가능한 메모리 8 GiB, 여유 디스크 30 GiB 이상입니다.

## 2. WSL2 Ubuntu 준비

Ubuntu가 없다면 관리자 PowerShell에서 설치합니다. 설치·재부팅은 사용자가 명시적으로
진행할 때만 수행합니다.

```powershell
wsl --install -d Ubuntu
```

재부팅 후 Ubuntu 터미널에서 확인합니다.

```bash
uname -m
```

정상 결과는 `x86_64`입니다. Windows PowerShell의 `wsl --list --verbose`에서 Ubuntu의
VERSION이 `2`여야 합니다.

## 3. Docker Desktop 연결

Docker Desktop에서 **Use the WSL 2 based engine**을 사용하고, Resources의 WSL Integration에서
Ubuntu를 활성화합니다. 이후 Ubuntu 터미널에서 각각 실행합니다.

```bash
docker version
```

```bash
docker compose version
```

```bash
docker run --rm hello-world
```

Client와 Server 정보, Compose 버전, `Hello from Docker!`가 모두 확인되어야 합니다.

## 4. 저장소 내려받기

Docker bind mount 성능과 권한 문제를 줄이기 위해 `/mnt/c`가 아닌 WSL Linux 파일시스템을
사용합니다.

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/jangyoungdo/fincontract-ai.git
cd fincontract-ai
git checkout v0.1.0-pilot.1
```

```bash
git status --short
git rev-parse --verify HEAD
test -f backend/Dockerfile
test -f frontend/Dockerfile
test -f docker-compose.yml
test ! -f .env
```

`git status --short`는 아무것도 출력하지 않아야 합니다.

## 5. 로컬 비밀값 생성

스크립트는 `.env`가 없을 때만 파일을 만들고 비밀값을 출력하지 않습니다. 기존 `.env`는
덮어쓰지 않습니다.

```bash
./scripts/prepare-local-env.sh
```

다음 명령은 값이 아니라 파일 권한과 설정 여부만 표시합니다.

```bash
stat -c '%a %n' .env
grep -E '^(LLM_PROVIDER|ALLOW_EXTERNAL_LLM)=' .env
```

정상 설정은 `LLM_PROVIDER=fake`, `ALLOW_EXTERNAL_LLM=false`입니다. `.env` 전체를 출력하거나
공유하지 않습니다.

## 6. Compose 사전 검사

```bash
./scripts/check-compose-prereqs.sh
```

이 검사는 WSL, x86_64, Docker 연결, Compose 플러그인, 자원, 포트 3000·8000·8001,
필수 비밀값 설정 여부와 Compose 문법을 확인합니다. 비밀값은 출력하지 않습니다.

## 7. 이미지 빌드

```bash
docker compose build
```

Backend 빌드에서 Python 패키지와 Tesseract 한국어 모델, Frontend 빌드에서 Next.js production
build가 성공해야 합니다. 실패하면 다음 명령 결과의 마지막 부분만 공유합니다.

```bash
./scripts/collect-diagnostics.sh
```

## 8. 서비스 기동

```bash
docker compose up --detach --wait
```

```bash
docker compose ps --all
```

PostgreSQL, Redis, Chroma, Backend, Worker, Retention, Frontend가 정상이어야 하며 migrate와
corpus-init은 성공적으로 종료된 one-shot 서비스입니다.

실시간 로그는 다음 명령으로 확인하고 `Ctrl+C`로 로그 보기만 종료합니다.

```bash
docker compose logs --follow --tail=100 backend worker frontend
```

## 9. 자동 스모크 테스트

```bash
docker compose run --rm --no-deps -T \
  -v "$PWD/scripts:/smoke:ro" \
  -v "$PWD/backend/tests/fixtures:/fixtures:ro" \
  -e FRONTEND_SMOKE_ADDRESS=frontend:3000 \
  backend python /smoke/check_frontend_proxy.py /fixtures/e2e-contract.txt
```

호스트에 Python을 설치하지 않고 Backend 이미지를 검사 실행기로 사용합니다. 검사는 Frontend의
`/api/v1`만 사용해 업로드, 분석, 상태 조회, PDF 리포트와 삭제를 검증합니다.

## 10. 사용자 PDF 확인

Windows 브라우저에서 [http://localhost:3000](http://localhost:3000)을 엽니다. 직접 준비한 PDF
한 개로 업로드, 상태 변화, 탐지 문구, 이유, 영향, 확인사항, 검토용 대안, 근거, PDF 리포트와
삭제를 확인합니다. 문서 내용은 지원 요청에 첨부하지 않습니다.

## 11. 오프라인 규칙 기준선

```bash
./scripts/run-baseline.sh
```

결과는 `output/runs/<run-id>/result.json`에 생성됩니다. 커밋, 데이터셋 SHA-256, 규칙 버전,
fake provider, 실제 호스트·컨테이너 아키텍처, 사례 수와 규칙별 지표만 포함하며 계약 문장은
포함하지 않습니다. `output/`은
Git에서 제외되며 결과는 상대 노트북에만 보관합니다.

## 12. 종료와 재기동

볼륨을 보존하며 종료합니다.

```bash
docker compose down
```

재기동에는 이미지 재빌드가 필요하지 않습니다.

```bash
docker compose up --detach --wait
docker compose ps
```

## 문제 보고

다음 결과만 전달합니다. `.env`와 계약서·분석 원문은 전달하지 않습니다.

```bash
./scripts/collect-diagnostics.sh
```

코드를 수정할 때는 [기여 가이드](../CONTRIBUTING.md)에 따라 작업별 브랜치와 PR을 사용합니다.
