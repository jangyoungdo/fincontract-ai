#!/usr/bin/env bash
set -euo pipefail

# Print a deliberately narrow support bundle. Never resolve Compose config or
# print .env because both operations could expose local secrets.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

redact() {
  sed -E \
    -e 's/(DOCUMENT_ENCRYPTION_KEY|ADMIN_AUDIT_TOKEN|ANTHROPIC_API_KEY)=([^[:space:]]+)/\1=[REDACTED]/g' \
    -e 's/(authorization: bearer )[A-Za-z0-9._-]+/\1[REDACTED]/Ig'
}

echo "[diagnostics] collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[diagnostics] uname=$(uname -srvmo)"
echo "[diagnostics] architecture=$(uname -m)"
echo "[diagnostics] commit=$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "[diagnostics] working_tree=dirty"
else
  echo "[diagnostics] working_tree=clean"
fi
docker version --format '[diagnostics] docker_client={{.Client.Version}} docker_server={{.Server.Version}}' 2>&1 | redact || true
docker compose version 2>&1 | redact || true
docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Ports}}' 2>&1 | redact || true
echo "[diagnostics] recent service logs (document contents and environment are not requested)"
docker compose logs --no-color --tail=80 backend worker frontend 2>&1 | redact || true
