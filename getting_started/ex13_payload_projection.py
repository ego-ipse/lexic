"""Ship a parsed value as a module that does not import lexic.

A parsed model is a live object graph on the IR spine. ``project`` flattens it
onto three tables — symbols, rows, and a root — which is all the information
needed to rebuild it. ``export_value`` writes those tables as an importable
``.py`` and byte-compiles it, so the consumer pays an **import** rather than a
parse — no grammar compiled, no text scanned.

The decoder it ships beside the value (`lexic.compile.payload.reader`) has zero
lexic imports, by design and by test. So a `plain` or reduced-`ir` artefact,
which names only spine classes or nothing, is readable with lexic absent
entirely. A MODEL names its own generated classes, so it needs its twin module
alongside — shown below, and the honest limit of the "no lexic" claim.

The projection is gated. ``project_checked`` refuses unless the tables are a
fixpoint — ``project(decode(project(v))) == project(v)`` — and ``export_value``
runs that gate always. What a fixpoint does NOT establish is that the tables
represent the source: a wrong value is a perfectly good fixpoint of a wrong
encoder. So provenance is asked separately, by ``built_under``.

Run::

    uv run python -m getting_started.ex13_payload_projection
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from lexic import compile_text
from lexic.compile import export_module
from lexic.compile.payload import built_under, export_value, project

GRAMMAR = """root ::= entry+
entry ::= key "=" value nl
key ::= [a-z]+
value ::= [0-9]+
nl ::= "\\n"
"""

DOCUMENT = "width=1920\nheight=1080\ndepth=32\n"

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "generated" / "ex13_payload"
"""Where the artefacts land. Real files, kept — the point is to open them and
see that a projected value is three flat literals and a digest."""


def main() -> None:
    """Parse, project, export, and read the export back without lexic."""
    compiled = compile_text(GRAMMAR, cache_key="ex13-config")
    model = compiled.parse(DOCUMENT)
    assert model.to_text() == DOCUMENT  # the round-trip invariant, as ever

    # ── the projection: one object graph, three flat tables ──────────
    payload = project(model)
    print(
        f"symbols: {len(payload.symbols)}  "
        f"strings: {len(payload.strs)}  ints: {len(payload.nodes)}"
    )

    # Ints and strings — no objects. That is what makes them shippable, and why
    # the reader needs nothing from lexic to rebuild the value.
    assert all(isinstance(n, int) for n in payload.nodes)

    # `origins` records each symbol's module as DATA, so a rule name that
    # legitimately repeats across two grammars stays recoverable by inspection
    # instead of silently colliding.
    print(f"origins: {sorted(set(payload.origins))}")

    OUT.mkdir(parents=True, exist_ok=True)

    # A model names its own classes, so the value module needs somewhere to
    # import them FROM — that is the twin module, and `module=` names it.
    # (A `plain` or reduced-`ir` value names only spine classes or nothing,
    # and needs no companion at all.)
    export_module(compiled, OUT / "config_model.py")

    # ── export: projected under the fixpoint gate, then byte-compiled ──
    written = export_value(model, OUT / "config_value.py", module="config_model")
    print(f"wrote {written.relative_to(REPO)} ({written.stat().st_size} bytes)")

    # ── read it back the way a CONSUMER would ────────────────────────
    # The consumer puts the directory on the path and imports by name, exactly
    # as it would from a wheel. Importing the VALUE costs a decode of three flat
    # tables — no grammar is compiled and no text is parsed.
    sys.path.insert(0, str(OUT))
    try:
        module = importlib.import_module("config_value")
    finally:
        sys.path.remove(str(OUT))

    print(f"rebuilt by import, not by parse: {type(module.VALUE).__name__}")
    assert module.VALUE.to_text() == DOCUMENT
    print(f"artefacts left for inspection: {sorted(q.name for q in OUT.glob('*.py'))}")

    # ── provenance is a SEPARATE question from the fixpoint ──────────
    # The grammar half is checked at decode, because a class carries its rules.
    # A reduction cannot be carried — the symbols an artefact names are the same
    # under every reduction there is — so whoever holds a live one asks here.
    # That is the party deciding whether a cached artefact needs rebuilding.
    # `None` is not the reduction this value was built under, and `built_under`
    # says so — which is the point. A cache asks this before trusting an
    # artefact it did not just produce.
    print(f"built under an unrelated reduction: {built_under(payload, None)}")


if __name__ == "__main__":
    main()
