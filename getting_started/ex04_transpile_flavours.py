"""Transpile a grammar between flavours (GBNF ↔ ABNF).

Lexic's flavour singletons (:data:`GBNF_FLAVOUR`, :data:`ABNF_FLAVOUR`) are
:class:`IrEmitter` instances. They take an IR AST and render it as their
flavour's grammar text. By round-tripping through the shared IR you can move a
grammar from one flavour to another:

    GBNF text ──parse_reduced──► IrAst ──ABNF_FLAVOUR.apply──► ABNF text

``parse_reduced`` drives the same engine seam ``compile_grammar`` uses: the
flavour's own self-grammar (Earley-normalised) parses the source text, and the
flavour's ``Reducer`` folds the derivation straight to an ``IrAst``.

Run::

    uv run python getting_started/04_transpile_flavours.py
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.parsing import parse_reduced
from lexic.parsing.normalize import normalize
from lexic.parsing.reduce import Reducer

GBNF_SOURCE = """\
root  ::= digit ("+" digit)*
digit ::= [0-9]
"""


def _parse(flavour: IrFlavour, text: str) -> IrAst:
    """Parse ``text`` under ``flavour``'s self-grammar and reduce it to IrAst."""
    reducer = flavour.reducer
    if not isinstance(reducer, Reducer):
        raise UnsupportedConstructError(
            f"flavour {flavour.name!r} carries no parse Reducer"
        )
    ast = parse_reduced(normalize(flavour.grammar), text, reducer)
    if not isinstance(ast, IrAst):
        raise UnsupportedConstructError(
            f"flavour {flavour.name!r} reduction produced "
            f"{type(ast).__name__!r}, not an IrAst"
        )
    return ast


def main() -> None:
    """Parse a GBNF grammar, emit it as ABNF, confirm the ABNF re-parses cleanly."""
    # GBNF source → IR AST.
    gbnf_ast = _parse(GBNF_FLAVOUR, GBNF_SOURCE)

    # IR AST → ABNF text (via the ABNF flavour singleton).
    abnf_text = str(ABNF_FLAVOUR.apply(gbnf_ast))

    print("=== GBNF source ===")
    print(GBNF_SOURCE)
    print("=== Transpiled to ABNF ===")
    print(abnf_text)

    # Round-trip the ABNF back through its parser to confirm it's well-formed.
    abnf_ast = _parse(ABNF_FLAVOUR, abnf_text)
    assert {r.name for r in abnf_ast.rules} == {r.name for r in gbnf_ast.rules}
    print("=== Round-trip confirmed: rule names match ===")
    print(" ", sorted(r.name for r in abnf_ast.rules))


if __name__ == "__main__":
    main()
