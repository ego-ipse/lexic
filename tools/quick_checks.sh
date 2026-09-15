#!/usr/bin/env bash
# quick_checks.sh — the gate for ONE diff, not for the tree.
#
# Runs only the lint, type and test commands that can see the files this
# change touched. `tools/run_checks.sh` remains the done-gate over everything;
# this is what to run while the change is still being made.
#
# Usage:
#   tools/quick_checks.sh          # diff against HEAD
#   tools/quick_checks.sh <ref>    # diff against any ref
set -e
cd "$(cd "$(dirname "$0")/.." && pwd)"
exec uv run python -m tools.quick_checks "$@"
