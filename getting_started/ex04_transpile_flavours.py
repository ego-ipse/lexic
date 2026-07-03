"""Transpile a grammar between flavours (GBNF ↔ ABNF).

Lexic's flavour singletons (:data:`GBNF_FLAVOUR`, :data:`ABNF_FLAVOUR`) are
:class:`IrEmitter` instances. They take an IR AST and render it as their
flavour's grammar text. By round-tripping through the shared IR you can move a
grammar from one flavour to another:

    GBNF text ──parse_grammar──► IrAst ──ABNF_FLAVOUR.apply──► ABNF text

``parse_grammar`` is the public grammar-text → IR seam — the same one
``compile_text`` runs through: the flavour's own self-grammar parses the
source, and the flavour's ``Reducer`` folds the derivation to an ``IrAst``.

Run::

    uv run python getting_started/04_transpile_flavours.py
"""

from __future__ import annotations

from lexic import parse_grammar
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR

GBNF_SOURCE = """\
root  ::= digit ("+" digit)*
digit ::= [0-9]
"""


def main() -> None:
    """Parse a GBNF grammar, emit it as ABNF, confirm the ABNF re-parses cleanly."""
    # GBNF source → IR AST.
    gbnf_ast = parse_grammar(GBNF_SOURCE, GBNF_FLAVOUR)

    # IR AST → ABNF text (via the ABNF flavour singleton).
    abnf_text = str(ABNF_FLAVOUR.apply(gbnf_ast))

    print("=== GBNF source ===")
    print(GBNF_SOURCE)
    print("=== Transpiled to ABNF ===")
    print(abnf_text)

    # Round-trip the ABNF back through its parser to confirm it's well-formed.
    abnf_ast = parse_grammar(abnf_text, ABNF_FLAVOUR)
    assert {r.name for r in abnf_ast.rules} == {r.name for r in gbnf_ast.rules}
    print("=== Round-trip confirmed: rule names match ===")
    print(" ", sorted(r.name for r in abnf_ast.rules))


if __name__ == "__main__":
    main()
