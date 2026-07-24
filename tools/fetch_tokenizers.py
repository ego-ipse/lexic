#!/usr/bin/env python3
"""Fetch the real HF ``tokenizer.json`` fixtures into the gitignored cache.

Downloads through ``huggingface_hub`` (a dev-dependency, like the
``tokenizers`` oracle — never imported from src). Tests skip when a file is
absent; nothing LGPL-licensed is ever committed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

CACHE = Path(__file__).resolve().parent.parent / "resources" / "tokenizers"
"""The gitignored fixture cache the integration tests resolve against."""

FIXTURES: dict[str, str] = {
    "smollm2.tokenizer.json": "HuggingFaceTB/SmolLM2-135M",
    "gemma4.tokenizer.json": "unsloth/gemma-3-4b-it",
}
"""Cache filename → the HF repo whose ``tokenizer.json`` fills it."""


def fetch(name: str, repo: str) -> None:
    """Fill cache entry ``name`` from ``repo`` unless already present."""
    out = CACHE / name
    if out.is_file() and out.stat().st_size:
        print(f"have  {name}")
        return
    print(f"fetch {name} ({repo})")
    shutil.copyfile(hf_hub_download(repo_id=repo, filename="tokenizer.json"), out)


def main() -> None:
    """Fetch every fixture into the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, repo in FIXTURES.items():
        fetch(name, repo)


if __name__ == "__main__":
    main()
