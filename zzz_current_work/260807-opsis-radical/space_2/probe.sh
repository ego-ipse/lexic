#!/usr/bin/env bash
# The probe, driven: serve, ask the browser what it sees, print the verdicts.
#
#   space_2/probe.sh [grammar] [document] [port]      # exit 0, or it is not done
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
READER="${1:-$ROOT/resources/ground_truth/json.gbnf}"
DOC="${2:-$HERE/../tk/fixtures_long.json}"
PORT="${3:-8927}"
CHS="$(ls "$HOME"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell 2>/dev/null | head -1)"
[ -x "$CHS" ] || { echo "no chrome-headless-shell under ~/.cache/ms-playwright" >&2; exit 1; }

cd "$ROOT"
uv run python "$HERE/serve.py" "$READER" "$DOC" "$PORT" >/tmp/opsis_probe_serve.log 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
for _ in $(seq 1 200); do
  curl -s -m 1 -X POST --data "size 800 600" "http://127.0.0.1:$PORT/frame" >/dev/null 2>&1 && break
  sleep 0.5
done

SAID="$("$CHS" --no-sandbox --disable-gpu --headless --window-size=1500,850 \
  --virtual-time-budget=15000 --dump-dom "http://127.0.0.1:$PORT/?probe=1" 2>/dev/null \
  | grep -o 'PROBE[^<]*' | head -1)"
[ -n "$SAID" ] || { echo "the probe said nothing — the leaf did not run" >&2; exit 1; }
echo "$SAID" | tr ':' '\n' | grep -v '^ *$' | sed 's/^ */  /'
case "$SAID" in
  "PROBE 0 failures"*) exit 0 ;;
  *) exit 1 ;;
esac
