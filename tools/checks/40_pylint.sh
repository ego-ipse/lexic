#!/usr/bin/env bash
set -e
uv run pylint src/ tests/ getting_started/
echo "pylint: OK"
