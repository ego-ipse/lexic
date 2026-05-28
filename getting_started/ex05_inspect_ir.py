"""Inspect the IR that backs a compiled grammar.

Every generated grammar class exposes its ``RuleSpec`` (the canonical IR for
that rule) via the ``__grammar__`` class variable. The spec is what powers
``to_text()`` round-trips and what the codegen pipeline consumes.

This example compiles a small grammar, then walks ``__grammar__`` for each
generated class and prints its shape.

Run::

    uv run python getting_started/05_inspect_ir.py
"""

from __future__ import annotations

from lexic import compile_text
from lexic.ir.nodes import IrAlternation, IrItem, IrLiteral

GRAMMAR = """\
expr ::= num op num
op   ::= "+" | "-" | "*" | "/"
num  ::= [0-9]+
"""


def main() -> None:
    """Compile a small grammar, walk each ``RuleSpec``, then emit the model in both flavours."""
    compiled = compile_text(GRAMMAR, cache_key="inspect")

    for rule_name, spec in compiled.specs.items():
        print(f"\n── rule {rule_name!r} ──")
        print(f"  class:        {spec.class_name}")
        print(f"  parent:       {spec.parent_class_name}")
        print(f"  kind:         {spec.kind}")
        print(f"  field_map:    {spec.field_map}")
        print(f"  items[{len(spec.items)}]:")
        for i, item in enumerate(spec.items):
            if isinstance(item, IrAlternation):
                arms = [arm.items[0].atom for arm in item.arms]
                print(f"    [{i}] alternation arms: {arms}")
            elif isinstance(item, IrItem):
                atom = item.atom
                if isinstance(atom, IrLiteral):
                    print(f"    [{i}] literal {atom.value!r} (×{item.quantifier})")
                else:
                    print(
                        f"    [{i}] {type(atom).__name__} {atom} (×{item.quantifier})"
                    )

    # Now show how the spec drives round-trip emission.
    model = compiled.parse("3+4")
    print("\nParsed model:           ", model)
    print("model.to_text():        ", repr(model.to_text()))
    print("model.to_grammar('gbnf'):", repr(model.to_grammar("gbnf")))
    print("model.to_grammar('abnf'):", repr(model.to_grammar("abnf")))


if __name__ == "__main__":
    main()
