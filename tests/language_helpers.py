"""A grammar's language, enumerated — the oracle the charset-fixpoint tests check against."""

from __future__ import annotations

from itertools import product

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing import recognize
from lexic.parsing.earley.normalize import normalize


def members(
    source: str, alphabet: str, longest: int, start: str | None = None
) -> set[str]:
    """Every string over ``alphabet`` up to ``longest`` that ``source`` derives
    from ``start`` (its own start rule by default), by Earley recognition — an
    ambiguous member is a member all the same, and no answer here reads EXTEND."""
    compiled = compile_text(source, cache_key=f"members-{hash(source)}")
    rules = compiled.codegen_grammar
    grammar = normalize(rules if start is None else IrAst(rules.rules, start))
    return {
        text
        for size in range(longest + 1)
        for text in map("".join, product(alphabet, repeat=size))
        if recognize(grammar, text)
    }
