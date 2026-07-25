"""Where fetched third-party artefacts live locally.

A filesystem question, deliberately separate from any client that answers the
network one: nothing here imports a hub library, so a test or an example can
ask *"is the fixture present?"* — and skip cleanly when it is not — in an
environment where the fetch dependencies are not installed at all.

Nothing in this cache is ever committed. The files are third-party and their
licences vary, so the directory is gitignored and the suite skips when empty.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["CACHE", "cached", "path"]

CACHE = Path(__file__).resolve().parents[2] / "resources" / "tokenizers"
"""The gitignored cache directory. Entries are named ``<name>.<filename>``."""


def path(name: str, filename: str = "tokenizer.json") -> Path:
    """Where ``name``'s copy of ``filename`` belongs — present or not.

    :param name: The cache name (see :data:`~ext.API.hf.FIXTURES`).
    :param filename: The file fetched from the source.
    :returns: The location, which may not exist.
    """
    return CACHE / f"{name}.{filename}"


def cached(name: str, filename: str = "tokenizer.json") -> Path | None:
    """``name``'s cached file, or ``None`` when absent or empty.

    :param name: The cache name.
    :param filename: The file fetched from the source.
    :returns: The cached file, or ``None``.
    """
    entry = path(name, filename)
    return entry if entry.is_file() and entry.stat().st_size else None
