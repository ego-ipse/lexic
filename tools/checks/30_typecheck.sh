#!/usr/bin/env bash
set -e
uv run pyright src/ tests/ getting_started/
echo "typecheck: OK"
