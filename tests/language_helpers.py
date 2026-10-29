"""A grammar's language, enumerated — the oracle the charset-fixpoint tests check against."""

from __future__ import annotations

from itertools import product

from lexic.compile import compile_text
from lexic.parsing import recognize
from lexic.parsing.earley.normalize import normalize


def members(source: str, alphabet: str, longest: int) -> set[str]:
    """Every string over ``alphabet`` up to ``longest`` that ``source`` derives,
    by Earley recognition — an ambiguous member is a member all the same, and
    no answer here reads EXTEND."""
    compiled = compile_text(source, cache_key=f"members-{hash(source)}")
    grammar = normalize(compiled.codegen_grammar)
    return {
        text
        for size in range(longest + 1)
        for text in map("".join, product(alphabet, repeat=size))
        if recognize(grammar, text)
    }
