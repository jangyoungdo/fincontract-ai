#!/usr/bin/env bash
set -euo pipefail

# Validate the application-specific checkpoint without exposing resolved
# Compose environment values. Run only after prepare-local-env.sh.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

./scripts/check-wsl-environment.sh

if [[ ! -f .env ]]; then
  echo "[compose] .env is missing; run ./scripts/prepare-local-env.sh" >&2
  exit 1
fi

required_setting() {
  local key="$1"
  local expected="$2"
  if grep -qx "$key=$expected" .env; then
    echo "[ok] $key is safely configured"
  else
    echo "[fail] $key must be $expected" >&2
    exit 1
  fi
}

secret_is_replaced() {
  local key="$1"
  local placeholder="$2"
  local value
  value="$(sed -n "s/^$key=//p" .env | head -n 1)"
  if [[ -z "$value" || "$value" == "$placeholder" ]]; then
    echo "[fail] $key has not been generated" >&2
    exit 1
  fi
  echo "[ok] $key is set (value hidden)"
}

required_setting LLM_PROVIDER fake
required_setting ALLOW_EXTERNAL_LLM false
required_setting ANTHROPIC_API_KEY ""
secret_is_replaced DOCUMENT_ENCRYPTION_KEY replace-with-a-generated-fernet-key
secret_is_replaced ADMIN_AUDIT_TOKEN replace-with-a-long-random-admin-token

for port in 3000 8000 8001; do
  if command -v ss >/dev/null 2>&1 && ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .; then
    echo "[fail] TCP port $port is already in use" >&2
    exit 1
  fi
  echo "[ok] TCP port $port is available"
done

docker compose config --quiet
if grep -Eq '^[[:space:]]*FRONTEND_ORIGIN:[[:space:]]*["'"']?\*["'"']?[[:space:]]*$' docker-compose.yml; then
  echo "[fail] wildcard FRONTEND_ORIGIN is not allowed" >&2
  exit 1
fi
echo "[compose] configuration passed; no secret values were printed"
