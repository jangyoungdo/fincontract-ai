#!/usr/bin/env bash
set -euo pipefail

# Create workstation-local secrets without printing them or overwriting an
# operator's existing environment file. This is intentionally separate from
# service startup so a collaborator can inspect each onboarding checkpoint.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_example="$repo_root/.env.example"
env_file="$repo_root/.env"

if [[ -e "$env_file" ]]; then
  echo "[env] .env already exists; leaving it unchanged"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "[env] openssl is required to generate local secrets" >&2
  exit 127
fi

encryption_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
admin_token="$(openssl rand -hex 32)"
temporary_file="$(mktemp "$repo_root/.env.tmp.XXXXXX")"
trap 'rm -f "$temporary_file"' EXIT
umask 077

sed \
  -e "s|^DOCUMENT_ENCRYPTION_KEY=.*$|DOCUMENT_ENCRYPTION_KEY=$encryption_key|" \
  -e "s|^ADMIN_AUDIT_TOKEN=.*$|ADMIN_AUDIT_TOKEN=$admin_token|" \
  -e 's|^ANTHROPIC_API_KEY=.*$|ANTHROPIC_API_KEY=|' \
  -e 's|^LLM_PROVIDER=.*$|LLM_PROVIDER=fake|' \
  -e 's|^ALLOW_EXTERNAL_LLM=.*$|ALLOW_EXTERNAL_LLM=false|' \
  "$env_example" >"$temporary_file"
mv "$temporary_file" "$env_file"
trap - EXIT

echo "[env] created .env with workstation-local secrets"
echo "[env] secret values were not printed; do not commit or share .env"
