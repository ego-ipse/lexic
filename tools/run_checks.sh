#!/usr/bin/env bash
set -e
cd "$(cd "$(dirname "$0")/.." && pwd)"
for script in tools/checks/*.sh; do
    bash "$script"
done
