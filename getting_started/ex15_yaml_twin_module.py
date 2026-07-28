"""A grammar file in, an importable module out, and a document parsed with it.

This is the whole build path in one file, on a language that ships with no
support in lexic at all: a YAML subset, written as GBNF, compiled, exported as
an importable twin module — the same form `tools/regen_generated.py` writes into
`generated/` — and then imported and used to parse a real `.yaml` document.

The point is that nothing here is YAML-aware. `export_module` takes any
`CompiledGrammar`, so the module this writes has the shape of
`generated/json_grammar.py` for exactly the same reason: one pipeline, no
privileged formulation.

What the twin module buys is that the consumer imports classes instead of
compiling a grammar — the rules travel with the classes, so the module round-
trips text without lexic re-deriving anything.

Run::

    uv run python -m getting_started.ex15_yaml_twin_module
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from lexic import compile_text
from lexic.compile import export_module
from lexic.compile.payload import export_value
from lexic.grammars import GBNF_FLAVOUR

# A YAML subset: `key: value` lines, where a value is a scalar or a flow
# sequence. Whitespace sits on ONE side of each token so no two nullable runs
# are ever adjacent — an ambiguous grammar would be refused by both engines,
# which is the correct behaviour and not what this example is about.
YAML_GRAMMAR = """root ::= entry+
entry ::= key colon value nl
key ::= [a-z_]+
colon ::= ": "
value ::= scalar | flowseq
scalar ::= [A-Za-z0-9._/-]+
flowseq ::= "[" scalar (comma scalar)* "]"
comma ::= ", "
nl ::= "\\n"
"""

DOCUMENT = """name: lexic
kind: grammar_engine
targets: [gbnf, abnf, ebnf]
version: 0.1.0
"""


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "generated" / "ex15_yaml"
"""Where the artefacts land. Real files, kept — open `yaml_subset.py` to see the
classes and `yaml_grammar.py` to see the same grammar as flat data."""


def main() -> None:
    """Compile a YAML grammar, export it, import it, parse with it."""
    compiled = compile_text(YAML_GRAMMAR, cache_key="ex15-yaml")

    OUT.mkdir(parents=True, exist_ok=True)

    # Two exports, two different artefacts:
    #
    #   export_module  → the TWIN: the synthesized classes as source.
    #   export_value   → the GRAMMAR ITSELF as data — the form of
    #                    `generated/json_grammar.py`, three flat tables plus a
    #                    digest, decoded back to a real IrAst.
    written = export_module(compiled, OUT / "yaml_subset.py")
    export_value(compiled.grammar, OUT / "yaml_grammar.py")
    print(f"wrote {sorted(q.name for q in OUT.glob('*.py'))}")
    print(f"twin: {written.stat().st_size:,} bytes")

    sys.path.insert(0, str(OUT))
    try:
        module = importlib.import_module("yaml_subset")

        # ── use it: the classes ARE the language ─────────────────────
        # Checked construction — a ref-bound field takes a sub-model, not a bare
        # string, and every value is validated against the grammar it carries.
        entry = module.Entry(
            key=module.Key("name"),
            colon=module.Colon(": "),
            # `Value` is an abstract alternation — a concrete ARM goes here.
            value=module.Scalar("lexic"),
            nl=module.Nl("\n"),
        )
        print(f"constructed from the twin: {entry.to_text()!r}")
        assert entry.to_text() == "name: lexic\n"

        # ── and the grammar-as-data module ───────────────────────────
        # `VALUE` decodes to a real IrAst under a digest check, so an edit to
        # the tables is refused rather than read as a wrong grammar.
        shipped = importlib.import_module("yaml_grammar").VALUE
        assert shipped == compiled.grammar
        print(f"grammar shipped as data, decoded equal: {shipped == compiled.grammar}")

        # It is the grammar, not a picture of one — it goes straight back
        # through the pipeline and parses the document.
        round_tripped = compile_text(
            str(GBNF_FLAVOUR.apply(shipped, 88)), cache_key="ex15-from-payload"
        )
        assert round_tripped.parse(DOCUMENT).to_text() == DOCUMENT
        print("re-compiled from the shipped grammar and parsed the document")

        assert module.GRAMMAR == compiled.grammar
    finally:
        sys.path.remove(str(OUT))

    # And the document the grammar was written for still parses, in-process,
    # against the same rules the module shipped.
    document = compiled.parse(DOCUMENT)
    assert document.to_text() == DOCUMENT
    print(f"parsed {type(document).__name__} — round-trip exact")


if __name__ == "__main__":
    main()
