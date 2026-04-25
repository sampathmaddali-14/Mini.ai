#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: ./commit.sh \"commit message\" [--push]"
  exit 1
fi

MSG="$1"
PUSH="${2:-}"

git add -A
git status --short

if git diff --cached --quiet; then
  echo "No staged changes. Nothing to commit."
  exit 0
fi

git commit -m "$MSG"

if [ "$PUSH" = "--push" ]; then
  git push
fi
