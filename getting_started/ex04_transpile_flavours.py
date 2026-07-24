"""Transpile a grammar between flavours (GBNF ↔ ABNF ↔ EBNF).

Lexic's flavour singletons (:data:`GBNF_FLAVOUR`, :data:`ABNF_FLAVOUR`,
:data:`EBNF_FLAVOUR`) are :class:`IrEmitter` instances. They take an IR AST
and render it as their flavour's grammar text. By round-tripping through the
shared IR you can move a grammar from any flavour to any other:

    GBNF text ──parse_grammar──► IrAst ──<FLAVOUR>.apply──► flavour text

``parse_grammar`` is the public grammar-text → IR seam — the same one
``compile_text`` runs through: the flavour's own self-grammar parses the
source, and the flavour's ``Reducer`` folds the derivation to an ``IrAst``.

Run::

    uv run python getting_started/ex04_transpile_flavours.py
"""

from __future__ import annotations

from lexic import parse_grammar
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR

GBNF_SOURCE = """\
root  ::= digit ("+" digit)*
digit ::= [0-9]
"""


def main() -> None:
    """Parse a GBNF grammar, emit it in every other flavour, re-parse each."""
    # GBNF source → IR AST (the flavour-neutral canonical form).
    gbnf_ast = parse_grammar(GBNF_SOURCE, GBNF_FLAVOUR)
    print("=== GBNF source ===")
    print(GBNF_SOURCE)

    for flavour in (ABNF_FLAVOUR, EBNF_FLAVOUR):
        text = str(flavour.apply(gbnf_ast))
        print(f"=== Transpiled to {flavour.name.upper()} ===")
        print(text)
        # Round-trip through the target flavour's own parser: same rule set.
        back = parse_grammar(text, flavour)
        assert {r.name for r in back.rules} == {r.name for r in gbnf_ast.rules}

    print("=== Round-trips confirmed: rule names match in every flavour ===")
    print(" ", sorted(r.name for r in gbnf_ast.rules))


if __name__ == "__main__":
    main()
