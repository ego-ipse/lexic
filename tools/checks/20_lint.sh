#!/usr/bin/env bash
set -e
uv run ruff check src/ tests/ bootstrap/
uv run ruff format --check src/ tests/ bootstrap/
echo "lint: OK"
