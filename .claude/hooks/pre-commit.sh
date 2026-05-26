#!/bin/bash
# Runs before every git commit. Exit 2 = block. Exit 0 = allow.

set -e

# Detect which files are staged
STAGED_PY=$(git diff --cached --name-only | grep -E "\.py$" || true)
STAGED_TS=$(git diff --cached --name-only | grep -E "\.(ts|tsx)$" || true)

# --- Python (server/) ---
if [ -n "$STAGED_PY" ]; then
  echo "Running ruff on staged Python files..."
  ruff check $STAGED_PY || exit 2
fi

# --- TypeScript (mobile/) ---
if [ -n "$STAGED_TS" ]; then
  echo "Running eslint on staged TypeScript files..."
  cd mobile && npx eslint $STAGED_TS --quiet || exit 2; cd ..
fi

# Block commits that contain shell=True in subprocess calls
if git diff --cached | grep -q "shell=True"; then
  echo "ERROR: shell=True found in subprocess call — use list args with shell=False"
  exit 2
fi

# Block commits that contain hardcoded common secrets patterns
if git diff --cached | grep -qE "(HF_TOKEN|sk-|api_key)\s*=\s*['\"][a-zA-Z0-9]{10,}"; then
  echo "ERROR: Possible hardcoded secret detected — use .env"
  exit 2
fi

echo "Pre-commit checks passed."
exit 0
