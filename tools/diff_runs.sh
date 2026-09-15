#!/usr/bin/env bash
# diff_runs.sh — what one commit did to every benchmark row.
#
# Pairs two performance runs' uploaded artefacts and prints the ratio of
# ratios per row, with a verdict that says "moved" only when the two
# confidence intervals are disjoint. A job that published nothing is reported
# as such rather than read from its log.
#
# Usage:
#   tools/diff_runs.sh <before> <after>            # commit shas or run ids
#   tools/diff_runs.sh <before> <after> --seat lexic-earley
set -e
cd "$(cd "$(dirname "$0")/.." && pwd)"
exec uv run python -m tools.benchmark.diff_runs "$@"
