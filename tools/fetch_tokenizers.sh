#!/usr/bin/env bash
# Fetch the real HF tokenizer.json fixtures into the gitignored cache.
# Tests skip when a file is absent; nothing LGPL-licensed is ever committed.
set -euo pipefail

cache="$(dirname "$0")/../resources/tokenizers"
mkdir -p "$cache"

fetch() {
    local name="$1" url="$2" out
    out="$cache/$name"
    if [ -s "$out" ]; then
        echo "have  $name"
        return
    fi
    echo "fetch $name"
    curl -fsSL "$url" -o "$out.tmp" && mv "$out.tmp" "$out"
}

fetch smollm2.tokenizer.json \
    "https://huggingface.co/HuggingFaceTB/SmolLM2-135M/resolve/main/tokenizer.json"
fetch gemma4.tokenizer.json \
    "https://huggingface.co/unsloth/gemma-3-4b-it/resolve/main/tokenizer.json"
