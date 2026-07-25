#!/usr/bin/env bash
# Run every getting_started/ex*.py example and assert it exits 0.
# Silent on success; prints captured stdout/stderr on failure.
# Pass -v to mirror each example's output verbatim.

set -u

verbose=0
[[ "${1:-}" == "-v" ]] && verbose=1

cd "$(cd "$(dirname "${0}")/.." && pwd)"

# Run as MODULES from the repo root — one uniform invocation, and the root is
# on sys.path for any example that needs it.
run_example() {
    local module="${1}"
    local output rc=0
    output="$(uv run python -m "${module}" 2>&1)" || rc="$?"
    if [[ "${rc}" -ne 0 ]]; then
        echo "FAIL: ${module}\n${output}" >&2
    elif (( verbose )); then
        echo "── ${module} ──"
        echo "${output}"
    fi
    return "${rc}"
}

failed=0
for example in getting_started/ex*.py; do
    run_example "getting_started.$(basename "${example}" .py)" || failed="$?"
done

exit "${failed}"
