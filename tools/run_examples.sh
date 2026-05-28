#!/usr/bin/env bash
# Run every getting_started/ex*.py example and assert it exits 0.
# Silent on success; prints captured stdout/stderr on failure.
# Pass -v to mirror each example's output verbatim.

set -u

verbose=0
[[ "${1:-}" == "-v" ]] && verbose=1

cd "$(cd "$(dirname "${0}")/.." && pwd)"

run_example() {
    local example="${1}"
    local output rc=0
    output="$(uv run python "${example}" 2>&1)" || rc="$?"
    if [[ "${rc}" -ne 0 ]]; then
        echo "FAIL: ${example}\n${output}" >&2
    elif (( verbose )); then
        echo "── ${example} ──"
        echo "${output}"
    fi
    return "${rc}"
}

failed=0
for example in getting_started/ex*.py; do
    run_example "${example}" || failed="$?"
done

tools/auto_fix.sh >/dev/null 2>&1

exit "${failed}"
