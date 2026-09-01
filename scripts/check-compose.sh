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

echo "[compose] building and waiting for healthy long-running services"
docker compose up --build --detach --wait
docker compose ps

echo "[compose] showing one-shot migration and public-corpus initialization"
docker compose logs --no-color migrate corpus-init

echo "[compose] verifying PostgreSQL, Redis, and Chroma read/write paths"
docker compose exec -T backend python scripts/check_infrastructure.py

echo "[compose] verifying host-facing API and frontend endpoints"
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:3000/

echo "[compose] smoke verification passed; run 'make compose-logs' to follow logs"
