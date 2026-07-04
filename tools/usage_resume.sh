#!/usr/bin/env bash
# Resume sleeper: waits until the five-hour usage window has reset (plus a
# grace period), then exits "RESUME <pct>" — re-invoking the coordinator.
# Usage: usage_resume.sh [grace-seconds (default 600)]
# Companion to usage_watch.sh; see CLAUDE.md §Session-usage watch.
set -u
GRACE="${1:-600}"

usage_json() {
    python3 - <<'EOF'
import json, os, urllib.request
try:
    creds = json.load(open(os.path.expanduser("~/.claude/.credentials.json")))
    tok = (creds.get("claudeAiOauth") or creds).get("accessToken", "")
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {tok}",
                 "anthropic-beta": "oauth-2025-04-20"})
    d = json.load(urllib.request.urlopen(req, timeout=15))["five_hour"]
    from datetime import datetime, timezone
    resets = datetime.fromisoformat(d["resets_at"])
    wait = int((resets - datetime.now(timezone.utc)).total_seconds())
    print(f"{int(round(d['utilization']))} {max(wait, 0)}")
except Exception:
    print("-1 -1")
EOF
}

# If the API is unavailable the caller MUST supply the reset wall-clock time
# as $2 (epoch seconds) — never guess a short fallback (a 429 once slept a
# "3-hour" hold in 20 minutes).
FALLBACK_EPOCH="${2:-}"
read -r PCT WAIT <<<"$(usage_json)"
if [ "$WAIT" -lt 0 ] 2>/dev/null; then
    if [ -z "$FALLBACK_EPOCH" ]; then
        echo "NO-API-NO-FALLBACK"
        exit 1
    fi
    TARGET=$(( FALLBACK_EPOCH + GRACE ))
else
    TARGET=$(( $(date +%s) + WAIT + GRACE ))
fi
while [ "$(date +%s)" -lt "$TARGET" ]; do
    REMAIN=$(( TARGET - $(date +%s) ))
    sleep $(( REMAIN < 60 ? REMAIN : 60 ))
done
# Window should have reset; confirm with a few polls.
for _ in 1 2 3 4 5; do
    read -r PCT _ <<<"$(usage_json)"
    if [ "$PCT" -ge 0 ] 2>/dev/null && [ "$PCT" -lt 50 ]; then
        echo "RESUME $PCT"
        exit 0
    fi
    sleep 60
done
echo "RESUME-UNCONFIRMED $PCT"
