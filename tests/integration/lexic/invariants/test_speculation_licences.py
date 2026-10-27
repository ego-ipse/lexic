"""The speculation licence over the roster — every unit the planner asks.

The planner asks :func:`~lexic.parsing.parallel.plan.speculation.speculative_openings`
about one unit per grammar: the start rule's sole unbounded repetition. Over
every bench row (plain, ``@lexical`` and ``@lexical`` + ``@non-semantic``) and
the ground-truth corpus there are 24 such asks; one unit is licensed, on
``#``, at all three seats. The exclusive-opening clause reads the PDA's EXTEND
(``rule_extensions``), which is sound; the walk it replaced was not, and the
two agree on every ask here.
"""

from __future__ import annotations

import pytest

from lexic.compile import Directives, compile_from_path, compile_text
from lexic.ir import IrAst
from lexic.parsing.parallel.plan.speculation import speculative_openings
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

_BENCH_ASKS = {
    "markdown": ("block", ""),
    "backtrack": ("stmt", ""),
    "mixedends": ("record", ""),
    "announced": ("section", "#"),
    "split-nullable": ("para", ""),
    "dense-earley": ("line", ""),
}
"""Bench row → (the unit its planner asks about, the licence at every seat)."""

_CORPUS_ASKS = {
    "arithmetic.ebnf": ("root-item", ""),
    "arithmetic.gbnf": ("root-item", ""),
    "c.gbnf": ("declaration", ""),
    "commands.gbnf": ("entry", ""),
    "list.gbnf": ("item", ""),
    "markdown.gbnf": ("block", ""),
}
"""Ground-truth file → (the unit its planner asks about, the licence)."""

_FALLBACK_WITNESSES = {
    ("chess.gbnf", "pawn"): "abcdefgh",
    ("chess.gbnf", "nonpawn"): "BKNQR",
    ("json.abnf", "member"): '"',
    ("json.abnf", "object-item2"): '"',
    ("json.ebnf", "member"): '"',
    ("json.ebnf", "object-item2"): '"',
    ("json.gbnf", "member"): '"',
    ("json.gbnf", "object-item2"): '"',
}
"""Unplanned units whose sound licence EXTEND's ALPHABET fallback refuses: the
walk it replaced granted these, and the true EXTEND excludes each opening.
TODO_3 item 16′'s witnesses for a more precise EXTEND."""


_SEATS = ("pda", "lex", "lex-ns")


def _bench_grammar(name: str, seat: str) -> IrAst:
    bench = next(b for b in BENCHES if b.name == name)
    if seat == "pda":
        return bench.compiled.codegen_grammar
    lexical = frozenset(bench.lexical)
    directives = (
        Directives(lexical=lexical)
        if seat == "lex"
        else Directives(lexical=lexical, non_semantic=frozenset(bench.non_semantic))
    )
    compiled = compile_text(
        bench.source,
        cache_key=f"speculation-licences-{name}-{seat}",
        flavour=bench.flavour,
        directives=directives,
    )
    return compiled.codegen_grammar


@pytest.mark.parametrize("seat", _SEATS)
@pytest.mark.parametrize("name", sorted(_BENCH_ASKS))
def test_every_bench_ask_keeps_its_licence(name: str, seat: str) -> None:
    """Each bench row's asked unit is licensed exactly as the census found."""
    unit, licence = _BENCH_ASKS[name]
    assert speculative_openings(_bench_grammar(name, seat), unit) == frozenset(licence)


@pytest.mark.parametrize("name", sorted(_CORPUS_ASKS))
def test_every_corpus_ask_keeps_its_licence(name: str) -> None:
    """Each ground-truth grammar's asked unit is licensed as the census found."""
    unit, licence = _CORPUS_ASKS[name]
    grammar = compile_from_path(str(GROUND_TRUTH / name)).codegen_grammar
    assert speculative_openings(grammar, unit) == frozenset(licence)


def test_chess_move_is_not_licensed() -> None:
    """``Nd2`` is a complete move that ``f3`` lengthens, so no opening is exclusive."""
    compiled = compile_from_path(str(GROUND_TRUTH / "chess.gbnf"))
    for text in ("1. Nd2 Nd2\n2. e4 e5\n", "1. Nd2 Nd2f3\n2. e4 e5\n"):
        compiled.parse(text)
    assert speculative_openings(compiled.codegen_grammar, "move") == frozenset()


@pytest.mark.xfail(
    strict=True, reason="EXTEND falls back to the rule's ALPHABET (item 16′)"
)
@pytest.mark.parametrize("witness", sorted(_FALLBACK_WITNESSES))
def test_fallback_witness_keeps_its_licence(witness: tuple[str, str]) -> None:
    """A more precise EXTEND grants each witness the opening the old walk did."""
    name, unit = witness
    grammar = compile_from_path(str(GROUND_TRUTH / name)).codegen_grammar
    assert speculative_openings(grammar, unit) == frozenset(
        _FALLBACK_WITNESSES[witness]
    )
