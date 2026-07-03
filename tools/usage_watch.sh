#!/usr/bin/env bash
# Session-usage watcher: polls the OAuth usage endpoint every POLL seconds for
# up to DURATION seconds. Exits immediately with "ALERT <pct>" when the
# session (five_hour) utilization >= THRESHOLD, else "OK <pct>" at the end.
# The coordinator relaunches it on every wake, acting on ALERT per the
# PLAN.md context-usage protocol (90% stop-and-report, 95% force).
set -u
THRESHOLD="${1:-90}"
POLL="${2:-60}"
DURATION="${3:-540}"
END=$(( $(date +%s) + DURATION ))
PCT=-1
while [ "$(date +%s)" -lt "$END" ]; do
    PCT=$(python3 - <<'EOF'
import json, os, urllib.request
try:
    creds = json.load(open(os.path.expanduser("~/.claude/.credentials.json")))
    tok = (creds.get("claudeAiOauth") or creds).get("accessToken", "")
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {tok}",
                 "anthropic-beta": "oauth-2025-04-20"})
    data = json.load(urllib.request.urlopen(req, timeout=15))
    print(int(round(data["five_hour"]["utilization"])))
except Exception:
    print(-1)
EOF
)
    if [ "$PCT" -ge "$THRESHOLD" ] 2>/dev/null; then
        echo "ALERT $PCT"
        exit 0
    fi
    sleep "$POLL"
done
echo "OK $PCT"
