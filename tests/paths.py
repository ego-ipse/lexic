"""Shared path constants for the test suite."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = PROJECT_ROOT / "resources" / "ground_truth"
GENERATED = PROJECT_ROOT / "generated"
CORPORA = PROJECT_ROOT / "resources" / "corpora"
GRAMMARS = PROJECT_ROOT / "src" / "lexic" / "grammars"
"""Shipped flavour package data — the ``*.flavour.ir`` manifests + ``*.ir``."""

GBNF_GRAMMARS: tuple[str, ...] = (
    "arithmetic.gbnf",
    "c.gbnf",
    "chess.gbnf",
    "japanese.gbnf",
    "json.gbnf",
    "json_arr.gbnf",
    "json_ws.gbnf",
    "list.gbnf",
    "markdown.gbnf",
    "think.gbnf",
    "vyx.gbnf",
)
"""Every GBNF ground-truth grammar (the shared corpus for cross-file gates)."""

ABNF_GRAMMARS: tuple[str, ...] = ("arithmetic.abnf", "json.abnf")
"""Every ABNF ground-truth grammar."""
