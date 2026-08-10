#!/usr/bin/env bash
# One gesture: serve a fixture, photograph a deterministic state, show it inline.
#
#   atlas/shot.sh [fixture] [query] [out.png]
#   atlas/shot.sh long 'break=5000'            # the refusal frontier, inline
#   atlas/shot.sh vyx 't=4205&sel=4205' > frame.term   # frozen terminal artifact
#
# Requires a kitty-graphics terminal (ghostty, kitty, wezterm) to SEE the frame;
# any terminal can still redirect it into a .term artifact.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
FIXTURE="${1:-long}"
QUERY="${2:-t=5000}"
OUT="${3:-/tmp/opsis_shot.png}"
PORT="${OPSIS_SHOT_PORT:-8917}"
CHS="$(ls "$HOME"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell 2>/dev/null | head -1)"
[ -x "$CHS" ] || { echo "no chrome-headless-shell under ~/.cache/ms-playwright" >&2; exit 1; }

cd "$ROOT"
uv run python "$HERE/serve.py" "$FIXTURE" "$PORT" >/tmp/opsis_shot_serve.log 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
for _ in $(seq 1 120); do
  curl -s -m 1 "http://127.0.0.1:$PORT/scene" >/dev/null 2>&1 && break
  sleep 0.5
done
"$CHS" --no-sandbox --disable-gpu --headless --window-size=1720,1000 \
  --virtual-time-budget=9000 --screenshot="$OUT" \
  "http://127.0.0.1:$PORT/?$QUERY" 2>/dev/null
uv run python "$HERE/inline.py" "$OUT"
