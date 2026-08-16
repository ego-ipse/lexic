"""Doc-drift guard: the wiki's public-api page vs. ``lexic.compile.__all__``.

`export_value` was documented as public API for months while being absent from
`lexic.compile` entirely — the only route was `from lexic.compile.payload
import export_value`, which the layering rule forbids. Reachable-but-unlisted
is the same defect one step milder, and the page carried several.

Both halves are gated here:

- every symbol the page documents with a ``compile/`` home is exported from
  ``lexic.compile`` (name in ``__all__``, attribute present);
- every such heading names ``compile/__init__.py`` as its home, because that
  is the module a caller imports from — a heading naming a submodule reads as
  an instruction to breach the seam.

The heading parser is deliberately narrow: a heading counts only when its tail
(after the em dash) is a backticked path ending in ``.py``, so prose headings
like ``### `.bind(...)` — one grammar, many vocabularies`` never match.
"""

from __future__ import annotations

import re
from pathlib import Path

import lexic.compile as compile_pkg

ROOT = Path(__file__).resolve().parents[4]
PUBLIC_API = ROOT / ".wiki" / "lexic" / "public-api.md"

HEADING_RE = re.compile(r"^###\s+(?P<head>.*?)\s+—\s+(?P<tail>.*)$")
PATH_RE = re.compile(r"`([\w./\-]+\.py)`")
SYMBOL_RE = re.compile(r"`([A-Za-z_]\w*)[(`]")
ROOT_HOME = "compile/__init__.py"


def documented_compile_entries() -> list[tuple[str, str]]:
    """``(symbol, documented home)`` for every ``compile/``-homed heading.

    :returns: One pair per symbol named in a qualifying heading; a heading may
        name several (``parse_instance`` / ``parse_instance_from_path``).
    """
    out: list[tuple[str, str]] = []
    for line in PUBLIC_API.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if match is None:
            continue
        paths = PATH_RE.findall(match["tail"])
        if not paths or not paths[0].startswith("compile/"):
            continue
        out.extend((name, paths[0]) for name in SYMBOL_RE.findall(match["head"]))
    return out


def test_the_page_documents_compile_entries_at_all() -> None:
    """Guard the parser itself: a silent zero would make the rest vacuous."""
    entries = documented_compile_entries()
    names = {name for name, _home in entries}
    assert len(entries) >= 10, f"heading parser found only {entries!r}"
    assert {"compile_text", "export_value", "compile_ast"} <= names, sorted(names)


def test_every_documented_compile_symbol_is_exported() -> None:
    """The page's ``compile/`` symbols are all in ``lexic.compile.__all__``."""
    exported = set(compile_pkg.__all__)
    missing = sorted({name for name, _home in documented_compile_entries()} - exported)
    assert not missing, (
        f"documented as public but absent from lexic.compile.__all__: {missing}"
    )


def test_every_exported_name_resolves() -> None:
    """``__all__`` names an attribute that exists — no stale entries."""
    absent = [name for name in compile_pkg.__all__ if not hasattr(compile_pkg, name)]
    assert not absent, f"lexic.compile.__all__ names missing attributes: {absent}"


def test_documented_home_is_the_package_root() -> None:
    """A ``compile/`` heading names the import route, not the implementation."""
    wrong = sorted(
        f"{name} → {home}"
        for name, home in documented_compile_entries()
        if home != ROOT_HOME
    )
    assert not wrong, (
        "public-api headings must name compile/__init__.py (the import route); "
        f"put the implementing module in the body instead: {wrong}"
    )
