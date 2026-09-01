#!/usr/bin/env bash
set -euo pipefail

# Read-only preflight for the supported collaborator environment. Failures are
# grouped before exit so the operator can fix one checkpoint at a time.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0
warnings=0

pass() { echo "[ok] $*"; }
fail() { echo "[fail] $*" >&2; failures=$((failures + 1)); }
warn() { echo "[warn] $*" >&2; warnings=$((warnings + 1)); }

if grep -qi microsoft /proc/version 2>/dev/null; then
  pass "running inside WSL"
else
  fail "run this check in an Ubuntu WSL2 terminal"
fi

architecture="$(uname -m)"
if [[ "$architecture" == "x86_64" ]]; then
  pass "CPU architecture is x86_64"
else
  fail "expected x86_64, found $architecture"
fi

for command_name in git docker openssl; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name is available"
  else
    fail "$command_name is not installed or not on PATH"
  fi
done

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    pass "Docker Engine is reachable from WSL"
  else
    fail "Docker Engine is not reachable; start Docker Desktop and enable WSL integration"
  fi
  if docker compose version >/dev/null 2>&1; then
    pass "Docker Compose plugin is available"
  else
    fail "docker compose is unavailable"
  fi
fi

cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)"
memory_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
disk_kib="$(df -Pk "$repo_root" | awk 'NR == 2 {print $4}')"
if (( cpu_count >= 4 )); then pass "available CPUs: $cpu_count"; else warn "fewer than 4 CPUs available: $cpu_count"; fi
if (( memory_kib >= 8 * 1024 * 1024 )); then pass "available memory is at least 8 GiB"; else warn "less than 8 GiB memory is visible to WSL"; fi
if (( disk_kib >= 30 * 1024 * 1024 )); then pass "free repository disk is at least 30 GiB"; else warn "less than 30 GiB free disk is available"; fi

if [[ "$repo_root" == /mnt/* ]]; then
  warn "repository is under /mnt; cloning under ~/src is recommended for Docker performance"
else
  pass "repository is stored in the WSL Linux filesystem"
fi

if (( failures > 0 )); then
  echo "[preflight] $failures blocking check(s), $warnings warning(s)" >&2
  exit 1
fi
echo "[preflight] environment passed with $warnings warning(s)"
