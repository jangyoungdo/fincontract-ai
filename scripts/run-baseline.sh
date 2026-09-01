#!/usr/bin/env bash
set -euo pipefail

# Run the deterministic baseline inside the already-built backend image. Only
# metrics and reproducibility metadata are written; contract text is omitted.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  echo "[experiment] .env is missing; complete the environment checkpoint first" >&2
  exit 1
fi
if ! grep -qx 'LLM_PROVIDER=fake' .env || ! grep -qx 'ALLOW_EXTERNAL_LLM=false' .env; then
  echo "[experiment] offline safety settings are not enabled" >&2
  exit 1
fi

run_id="baseline-$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="$repo_root/output/runs/$run_id"
output_file="$output_dir/result.json"
mkdir -p "$output_dir"

code_commit="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then code_dirty=true; else code_dirty=false; fi
image_reference="fincontract-ai-backend:local"
image_id="$(docker image inspect --format '{{.Id}}' "$image_reference" 2>/dev/null || true)"
if [[ -z "$image_id" ]]; then
  echo "[experiment] backend image is missing; complete the image-build checkpoint first" >&2
  rmdir "$output_dir"
  exit 1
fi
container_architecture="$(docker image inspect --format '{{.Architecture}}' "$image_reference")"
if grep -qi microsoft /proc/version 2>/dev/null; then
  host_platform="windows-wsl2-$(uname -m)"
else
  host_platform="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
fi

dataset_mount="$repo_root/backend/tests/fixtures:/datasets:ro"
if ! docker compose run --rm --no-deps -T \
  -v "$dataset_mount" \
  -e "FINCONTRACT_RUN_ID=$run_id" \
  -e "FINCONTRACT_CODE_COMMIT=$code_commit" \
  -e "FINCONTRACT_CODE_DIRTY=$code_dirty" \
  -e "FINCONTRACT_IMAGE_ID=$image_id" \
  -e "FINCONTRACT_CONTAINER_ARCHITECTURE=$container_architecture" \
  -e "FINCONTRACT_PLATFORM=$host_platform" \
  -e 'LLM_PROVIDER=fake' \
  backend python scripts/evaluate_rule_baseline.py \
  /datasets/loan_terms_synthetic_v0_1.jsonl >"$output_file"; then
  rm -f "$output_file"
  rmdir "$output_dir" 2>/dev/null || true
  echo "[experiment] baseline failed; inspect backend logs without sharing .env" >&2
  exit 1
fi

echo "[experiment] offline baseline completed"
echo "[experiment] result: output/runs/$run_id/result.json"
echo "[experiment] keep this file local; it is ignored by Git"
