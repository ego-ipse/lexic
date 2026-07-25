"""The Hugging Face hub — fetching files, and nothing else.

One of the resource APIs under ``ext/API/``: each knows how to *get* a
third-party artefact. What an artefact means is not this module's business —
``tokenizer.json`` happens to be hosted here, but reading it is
:mod:`lexic.api.json_tokenizer`'s job, and the model it builds is
``lexic.ir``'s.

**Any repo, any file.** :data:`FIXTURES` is the set this repository's own test
suite prefetches, not a permitted list — :func:`download` takes any repo id
the hub serves, so callers are not limited to the families pinned here.

Importing this module needs ``huggingface_hub``. Asking whether a fixture is
already present does NOT — that is :mod:`ext.API.cache`, which is
dependency-free precisely so tests and examples can skip cleanly in an
environment without the fetch extras.

Run ``uv run python -m ext.API.hf`` to prefetch the fixtures, or
``uv run python -m ext.API.hf <org/model> ...`` for anything else.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

from ext.API.cache import CACHE, cached, path

__all__ = ["FIXTURES", "download"]

FIXTURES: dict[str, str] = {
    "smollm2": "HuggingFaceTB/SmolLM2-135M",
    "gemma4": "unsloth/gemma-3-4b-it",
    "qwen3": "Qwen/Qwen3-0.6B",
}
"""Short name → repo, for the fixtures the test suite expects. An alias table
and a prefetch list — NOT a restriction on what :func:`download` accepts."""


def download(repo: str, *, name: str = "", filename: str = "tokenizer.json") -> Path:
    """Fetch ``filename`` from any hub repo into the cache, unless already there.

    :param repo: A hub repo id (``"org/model"``), or a :data:`FIXTURES` alias.
    :param name: The cache name; defaults to the alias when one was given,
        else the repo's last path segment.
    :param filename: The file to fetch from the repo.
    :returns: The cached file.
    """
    repo_id = FIXTURES.get(repo, repo)
    name = name or (repo if repo in FIXTURES else repo_id.rsplit("/", 1)[-1])
    have = cached(name, filename)
    if have is not None:
        return have
    CACHE.mkdir(parents=True, exist_ok=True)
    out = path(name, filename)
    shutil.copyfile(hf_hub_download(repo_id=repo_id, filename=filename), out)
    return out


def main(argv: list[str] | None = None) -> None:
    """Fetch the named repos, or every fixture when none are named.

    :param argv: Repo ids or :data:`FIXTURES` aliases.
    """
    for repo in argv or list(FIXTURES):
        print(f"{'have ' if cached(repo) else 'fetch'} {repo}")
        print(f"  -> {download(repo)}")


if __name__ == "__main__":
    main(sys.argv[1:])
