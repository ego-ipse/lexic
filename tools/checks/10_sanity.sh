#!/usr/bin/env bash
set -e
for f in $(git ls-files -- '*.py' '*.md' '*.toml' '*.yaml'); do
    # Trailing newline: $(tail -c 1 ...) is empty iff last byte is \n (shell strips it)
    if [ -n "$(tail -c 1 "$f")" ]; then
        echo "ERROR: missing trailing newline: $f"
        exit 1
    fi
    # Trailing whitespace
    if grep -Pn '\s+$' "$f"; then
        echo "ERROR: trailing whitespace in $f (lines above)"
        exit 1
    fi
    # CRLF line endings
    if grep -Pq '\r\n' "$f"; then
        echo "ERROR: CRLF line endings in $f"
        exit 1
    fi
done
echo "sanity: OK"
