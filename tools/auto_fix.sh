#!/usr/bin/env bash
set -e

cd "$(cd "$(dirname "$0")/.." && pwd)"

echo "Running lint checks..." >&2
uv run ruff format --exclude ".venv*" || exit_code="$?"

echo "Running import sorting checks..." >&2
uv run isort . --skip-glob ".venv*" || exit_code="$?"

echo "Running auto-fix checks..." >&2
uv run ruff check --fix --exclude ".venv*" || exit_code="$?"

exit "${exit_code:-0}"