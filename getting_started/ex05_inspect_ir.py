"""Inspect the IR that backs a compiled grammar.

Every generated grammar class exposes its rule as ``__grammar__: IrRule`` (the
codegen-grammar rule the class structurally IS), and the compiled grammar
carries the whole canonical ``IrAst`` on ``CompiledGrammar.grammar``. Both are
what power ``to_text()`` round-trips and what the codegen pipeline consumes.

This example compiles a small grammar, then walks each rule of the canonical
AST and prints its shape.

Run::

    uv run python getting_started/ex05_inspect_ir.py
"""

from __future__ import annotations

from lexic import compile_text
from lexic.ir.nodes import IrItem, IrLiteral


def main() -> None:
    """Compile a small grammar, walk its canonical rules, then emit in both flavours."""
    grammar = """\
expr ::= num op num
op   ::= "+" | "-" | "*" | "/"
num  ::= [0-9]+
"""
    compiled = compile_text(grammar, cache_key="inspect")

    for rule in compiled.grammar.rules:
        print(f"\n── rule {rule.name!r} ──")
        for arm_index, arm in enumerate(rule.body):
            print(f"  arm[{arm_index}]:")
            for i, item in enumerate(arm):
                atom = item.atom
                if isinstance(atom, IrLiteral):
                    print(f"    [{i}] literal {atom!r} (×{item.quantifier})")
                elif isinstance(item, IrItem):
                    print(
                        f"    [{i}] {type(atom).__name__} {atom} (×{item.quantifier})"
                    )

    # Now show how the grammar drives round-trip emission.
    model = compiled.parse("3+4")
    print("\nParsed model:           ", model)
    print("model.to_text():        ", repr(model.to_text()))
    print("model.to_grammar('gbnf'):", repr(model.to_grammar("gbnf")))
    print("model.to_grammar('abnf'):", repr(model.to_grammar("abnf")))


if __name__ == "__main__":
    main()
