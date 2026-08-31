#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

git config --local pull.ff only
git config --local fetch.prune true
git config --local rerere.enabled true
git config --local push.autoSetupRemote true
git config --local branch.autoSetupRebase always
git config --local core.hooksPath .githooks

echo "Configured repository-local collaboration settings:"
echo "- pull.ff=only"
echo "- fetch.prune=true"
echo "- rerere.enabled=true"
echo "- push.autoSetupRemote=true"
echo "- branch.autoSetupRebase=always"
echo "- core.hooksPath=.githooks"
