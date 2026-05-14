#!/usr/bin/env bash
set -e
uv run pylint src/ tests/
echo "pylint: OK"
