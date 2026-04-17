"""parse(text, grammar_path) → GrammarModel instance.

Thin entry point. Delegates to codegen (IR + ModelEmitter) and LarkBuilder.
"""

from __future__ import annotations

from pathlib import Path

import lark

from codegen import codegen
from codegen.ir_builder import IRBuilder
from codegen.lark_builder import LarkBuilder
from codegen.parser import parse_gbnf


def parse(text: str, grammar_path: str | Path) -> object:
    """Parse text against a GBNF grammar and return a typed GrammarModel instance."""
    grammar_path = Path(grammar_path)

    # Generate (or regenerate) Pydantic model classes.
    classes = codegen(grammar_path)

    # Rebuild specs to drive LarkBuilder (avoids storing state between calls).
    rules = parse_gbnf(grammar_path.read_text())
    specs = IRBuilder(rules).build()

    builder = LarkBuilder(specs)
    grammar_str, start_rule = builder.build_grammar()

    parser = lark.Lark(
        grammar_str,
        parser="earley",
        ambiguity="resolve",
        start=start_rule,
    )
    tree = parser.parse(text)
    transformer = builder.build_transformer(classes)
    return transformer.transform(tree)
