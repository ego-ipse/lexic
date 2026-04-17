#!/usr/bin/env bash
set -e
uv run pyright src/ tests/
echo "typecheck: OK"
