# EC2 단일 서버 운영 배포

이 문서는 Ubuntu 26.04 LTS EC2 한 대에서 FinContract AI 전체 Compose 스택을 운영하는 절차를 설명합니다.
외부에는 Caddy의 HTTP/HTTPS 포트만 공개하고 Next.js, FastAPI, ChromaDB, PostgreSQL, Redis는
Docker 네트워크 또는 호스트 루프백에서만 접근합니다.

## 전제 조건

- Docker Engine 및 Docker Compose 플러그인
- Git
- 보안 그룹 인바운드 HTTP 80, HTTPS 443
- 외부 모델을 사용할 경우 별도 API 프로젝트 키
- 암호화된 EBS와 운영 비밀값 백업

## 최초 배포

저장소를 `/opt/fincontract`에 받은 뒤 예제 환경 파일을 복사합니다.

```bash
cp .env.example .env
chmod 600 .env
```

`.env`에는 최소한 다음 값을 운영값으로 교체합니다.

```dotenv
APP_ENV=production
FINCONTRACT_SITE_ADDRESS=http://15.164.4.137
FRONTEND_ORIGIN=http://15.164.4.137
POSTGRES_PASSWORD=<긴 무작위 비밀번호>
DOCUMENT_ENCRYPTION_KEY=<Fernet 키>
ADMIN_AUDIT_TOKEN=<긴 무작위 토큰>
```

OpenAI를 활성화할 때만 다음 값을 추가합니다. 키는 저장소, 이슈, 로그에 남기지 않습니다.

```dotenv
LLM_PROVIDER=openai
ALLOW_EXTERNAL_LLM=true
OPENAI_API_KEY=<OpenAI API 프로젝트 키>
OPENAI_CONTEXT_REVIEW_ENABLED=true
```

Compose 구성을 검증한 뒤 실행합니다.

```bash
docker compose -f docker-compose.yml -f compose.production.yml config --quiet
docker compose -f docker-compose.yml -f compose.production.yml up -d --build
docker compose -f docker-compose.yml -f compose.production.yml ps
```

초기 IP 기반 검증은 `http://15.164.4.137`에서 수행합니다. 도메인을 연결한 뒤에는 두 환경값을
같은 HTTPS 주소로 변경하고 gateway와 backend를 다시 생성합니다.

```dotenv
FINCONTRACT_SITE_ADDRESS=fincontract.example.com
FRONTEND_ORIGIN=https://fincontract.example.com
```

```bash
docker compose -f docker-compose.yml -f compose.production.yml up -d --force-recreate gateway backend
```

Caddy는 도메인의 A 레코드가 EC2 Elastic IP를 가리키고 80/443 포트가 열려 있으면 인증서를
자동으로 발급하고 갱신합니다.

## 일상 운영

```bash
docker compose -f docker-compose.yml -f compose.production.yml ps
docker compose -f docker-compose.yml -f compose.production.yml logs --tail=100 backend worker retention gateway
git pull --ff-only
docker compose -f docker-compose.yml -f compose.production.yml up -d --build
```

운영 중에는 `docker compose down -v`를 실행하지 않습니다. `-v`는 PostgreSQL, ChromaDB,
업로드 문서와 보고서 볼륨을 삭제합니다.

## 백업과 복구 경계

- `DOCUMENT_ENCRYPTION_KEY`를 분실하면 저장 문서를 복호화할 수 없으므로 비밀 저장소에 별도 보관합니다.
- EBS 스냅샷은 인스턴스와 별도의 주기로 생성합니다.
- PostgreSQL 논리 백업과 업로드·보고서 볼륨 백업은 사용자 문서 보존 정책과 함께 운영합니다.
- 공개 접속 검증 후 보안 그룹에서 SSH 22번 규칙을 제거하고 Session Manager를 기본 관리 경로로 사용합니다.
