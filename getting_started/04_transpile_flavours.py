"""Transpile a grammar between flavours (GBNF ↔ ABNF).

Lexic's flavour singletons (:data:`GBNF_FLAVOUR`, :data:`ABNF_FLAVOUR`) are
:class:`IrEmitter` instances. They take an IR AST and render it as their
flavour's grammar text. By round-tripping through the shared IR you can move a
grammar from one flavour to another:

    GBNF text ──parse──► IrAst ──ABNF_FLAVOUR.apply──► ABNF text

Run::

    uv run python getting_started/04_transpile_flavours.py
"""

from __future__ import annotations

from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.parsing.meta_parser import MetaGrammarParser

GBNF_SOURCE = """\
root  ::= digit ("+" digit)*
digit ::= [0-9]
"""


def main() -> None:
    # GBNF source → IR AST.
    gbnf_ast = MetaGrammarParser(GBNF_FLAVOUR).parse(GBNF_SOURCE)

    # IR AST → ABNF text (via the ABNF flavour singleton).
    abnf_text = str(ABNF_FLAVOUR.apply(gbnf_ast))

    print("=== GBNF source ===")
    print(GBNF_SOURCE)
    print("=== Transpiled to ABNF ===")
    print(abnf_text)

    # Round-trip the ABNF back through its parser to confirm it's well-formed.
    abnf_ast = MetaGrammarParser(ABNF_FLAVOUR).parse(abnf_text)
    assert {r.name for r in abnf_ast.rules} == {r.name for r in gbnf_ast.rules}
    print("=== Round-trip confirmed: rule names match ===")
    print(" ", sorted(r.name for r in abnf_ast.rules))


if __name__ == "__main__":
    main()
