#!/usr/bin/env bash
set -e
uv run ruff check src/ tests/ tools/ ext/
uv run ruff format --check src/ tests/ getting_started/ tools/ ext/
echo "lint: OK"
