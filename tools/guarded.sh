#!/usr/bin/env bash
# guarded.sh — run a command under a hard memory ceiling so a runaway
# allocation self-terminates instead of taking the machine down.
#
# The property-test suite drives hypothesis; at very high `max_examples` the
# hypothesis harness retains memory proportional to examples explored (the
# parse engine itself is leak-free — flat over 20k parses). Running pytest
# un-capped at raised example counts can exhaust RAM. Always run the property
# suite, and any high-example exploration, through this wrapper.
#
# Usage:
#   tools/guarded.sh <mem> <timeout_s> -- <command...>
# Example:
#   tools/guarded.sh 8G 600 -- uv run pytest tests/ -q
#   tools/guarded.sh 6G 400 -- bash tools/run_checks.sh
#
# The command is placed in a transient systemd user scope with MemoryMax set
# and swap disabled, so it is OOM-killed (exit 137) at the ceiling rather than
# thrashing swap or crashing the host. A wall-clock RuntimeMaxSec is also set.
set -euo pipefail

if [ "$#" -lt 3 ]; then
    echo "usage: tools/guarded.sh <mem, e.g. 8G> <timeout_s> -- <command...>" >&2
    exit 2
fi

mem="$1"; shift
tmo="$1"; shift
[ "$1" = "--" ] && shift

exec systemd-run --user --scope -q \
    -p MemoryMax="$mem" \
    -p MemorySwapMax=0 \
    -p RuntimeMaxSec="$tmo" \
    "$@"
