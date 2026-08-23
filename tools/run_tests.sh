#!/usr/bin/env bash
# run_tests.sh — the whole suite, in three phases, identically here and in CI.
#
# One script so local and CI cannot drift. The phases exist because the suite
# holds three populations with incompatible execution needs:
#
#   A  the bulk           parallel under `-n auto`; pure correctness, no timing
#   B  the concurrency    SERIAL; xdist process-parallelism oversubscribes a
#      lane               thread storm and lets the threads serialise, which
#                         both hides races and inflates the clock (measured
#                         75s -> 257s on the guarded gates this way)
#   C  the timing gates   SERIAL; a wall-clock bound on a saturated machine
#                         measures scheduler starvation, not the parse
#
# The split is BY MARKER, not by path, and each lane's conftest applies its own
# marker to everything it collects — so a test added to a lane is phased
# correctly the moment it exists, with nobody remembering a decorator.
#
# Usage:
#   tools/run_tests.sh                 # all three phases, in order
#   tools/run_tests.sh A               # one phase
#   tools/run_tests.sh B -x            # one phase, extra pytest args
#
# Environment:
#   LEXIC_REQUIRE_FREE_THREADED=1  fail the session unless the GIL is off
#   LEXIC_REQUIRE_CORES=<n>        fail the session below n usable workers
#
# Both guards FAIL rather than skip: a concurrency phase that runs with the
# GIL on, or on one core, reports green having proven nothing.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

PHASES="${1:-ABC}"
[ $# -gt 0 ] && shift || true

run_phase_a() {
    echo "── Phase A: the parallel bulk (-n auto) ────────────────────────────"
    uv run pytest tests/ -q -n auto -m "not concurrency and not performance" "$@"
}

run_phase_b() {
    echo "── Phase B: the concurrency lane (serial) ──────────────────────────"
    # Serial by construction: no -n. The lane's own overlap witnesses decide
    # whether threads really raced; xdist would only take cores away from them.
    LEXIC_REQUIRE_CORES="${LEXIC_REQUIRE_CORES:-2}" \
        uv run pytest tests/ -q -m concurrency "$@"
}

run_phase_c() {
    echo "── Phase C: the timing gates (serial) ──────────────────────────────"
    uv run pytest tests/ -q -m performance "$@"
}

case "$PHASES" in
    *[!ABC]*) echo "usage: $0 [A|B|C|ABC] [pytest args...]" >&2; exit 2 ;;
esac

[[ "$PHASES" == *A* ]] && run_phase_a "$@"
[[ "$PHASES" == *B* ]] && run_phase_b "$@"
[[ "$PHASES" == *C* ]] && run_phase_c "$@"
echo "── all requested phases green ──────────────────────────────────────"
