"""Write any IR value to a file and read it back — `repr` with an inverse.

Saving an IR value is just ``repr(node)``. This is the other half:
``load_ir(repr(node))`` reconstructs the node, so **anything lexic parses can be
written to a file and read back** — a grammar, a flavour manifest, a tokenizer.

``emit_ir`` is the formatted version of the same text: width-aware, laid out
through the same layout algebra the rest of lexic emits with, so a saved grammar
is legible rather than one enormous line.

The notation is not a second data format sitting beside the real one. It spells
IR *constructors* — the same class names you would type — and `load_ir` parses
it with the ordinary engine over `NOTATION_GRAMMAR`. That is why the round-trip
is exact rather than approximate.

Run::

    uv run python -m getting_started.ex14_ir_notation
"""

from __future__ import annotations

from lexic.compile import canonical_grammar
from lexic.compile.notation import emit_ir, load_ir
from lexic.grammars import GBNF_FLAVOUR

GRAMMAR = """root ::= greeting name
greeting ::= "hello" ws
name ::= [a-zA-Z]+
ws ::= " "
"""


def main() -> None:
    """Round-trip a real grammar's IR through its own notation."""
    ast = canonical_grammar(GRAMMAR, GBNF_FLAVOUR)

    # ── emit: the IR as constructor notation, laid out to a width ────
    text = emit_ir(ast, width=72)
    print(text.splitlines()[0])
    print(f"... {len(text.splitlines())} lines of notation")

    # ── read it back ────────────────────────────────────────────────
    rebuilt = load_ir(text)

    # Exact, not approximate: the IR spine gives records value equality, so
    # this is a real assertion rather than a comparison of printed forms.
    assert rebuilt == ast
    print(f"round-trip exact: {rebuilt == ast}")

    # `repr` is the unformatted half of the same thing — `load_ir` takes either.
    assert load_ir(repr(ast)) == ast

    # ── and the node goes straight back into the pipeline ───────────
    # What came back is a node, not a copy of one — a flavour is an emitter,
    # so applying it spells the IR as grammar text again.
    assert isinstance(rebuilt, type(ast))
    spelled = str(GBNF_FLAVOUR.apply(rebuilt, 88))
    print(f"back to GBNF text: {spelled.splitlines()[0]!r}")
    assert canonical_grammar(spelled, GBNF_FLAVOUR) == ast


if __name__ == "__main__":
    main()
