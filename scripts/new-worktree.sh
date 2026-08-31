#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <branch-name> <worktree-path>" >&2
  exit 2
fi

branch_name="$1"
worktree_path="$2"
repo_root="$(git rev-parse --show-toplevel)"

case "$branch_name" in
  feature/*|fix/*|docs/*|research/*|chore/*|codex/*) ;;
  *)
    echo "Branch must start with feature/, fix/, docs/, research/, chore/, or codex/." >&2
    exit 2
    ;;
esac

if [[ -e "$worktree_path" ]]; then
  echo "Worktree path already exists: $worktree_path" >&2
  exit 2
fi

case "$(cd "$(dirname "$worktree_path")" && pwd -P)/$(basename "$worktree_path")" in
  "$repo_root"|"$repo_root"/*)
    echo "Worktree path must be outside the main repository: $repo_root" >&2
    exit 2
    ;;
esac

git fetch origin --prune

if git show-ref --verify --quiet "refs/heads/$branch_name"; then
  git worktree add "$worktree_path" "$branch_name"
else
  git worktree add -b "$branch_name" "$worktree_path" origin/main
fi

echo "Created worktree: $worktree_path"
echo "Branch: $branch_name"

