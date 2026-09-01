#!/usr/bin/env bash
set -euo pipefail

# This script intentionally leaves the stack running so operators can inspect
# worker and retention logs after a smoke run with `make compose-logs`.
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required; install Docker Desktop or a compatible Docker runtime" >&2
  exit 127
fi

echo "[compose] validating resolved configuration"
docker compose config --quiet
if grep -En 'FRONTEND_ORIGIN:.*\*' docker-compose.yml >/dev/null; then
  echo "wildcard FRONTEND_ORIGIN is not allowed" >&2
  exit 1
fi

echo "[compose] building and waiting for healthy long-running services"
docker compose up --build --detach --wait
docker compose ps

echo "[compose] showing one-shot migration and public-corpus initialization"
docker compose logs --no-color migrate corpus-init

echo "[compose] verifying PostgreSQL, Redis, and Chroma read/write paths"
docker compose exec -T backend python scripts/check_infrastructure.py

echo "[compose] verifying upload, analysis, polling, report, and deletion through frontend port 3000"
docker compose run --rm --no-deps -T \
  -v "$PWD/scripts:/smoke:ro" \
  -v "$PWD/backend/tests/fixtures:/fixtures:ro" \
  -e FRONTEND_SMOKE_ADDRESS=frontend:3000 \
  backend python /smoke/check_frontend_proxy.py /fixtures/e2e-contract.txt

echo "[compose] smoke verification passed; run 'make compose-logs' to follow logs"
