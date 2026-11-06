"""Tests for lexic.parsing.pda.analysis.predicates — per-node predicates and
their dispatch tables.

``FIRST``/``HARD``/``FOLLOW_FEED``/``SEQ_ATOM`` need a live ``GrammarAnalysis``
to drive them and are exercised through it in
``tests/unit/lexic/parsing/pda/analysis/test_analysis.py``; this file targets
the table usable standalone: ``STOPSET_ATOM`` (a pure per-type predicate
needing no dispatcher context). Nullability is the grammar's own fact
(``IrAst.nullable``), pinned in ``tests/unit/lexic/ir/grammar/test_nodes.py``.
``EXTEND`` and ``NON_INITIAL`` are pinned beside their own modules, in
``tests/unit/lexic/parsing/pda/analysis/extend/``.
"""

from __future__ import annotations

import math

import pytest

from lexic.compile import compile_text
from lexic.ir import (
    IrCharClass,
    IrChr,
    IrLiteral,
    IrRuleRef,
)
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.predicates import (
    STOPSET_ATOM,
    rule_spans,
)


def test_stopset_atom_is_true_only_for_a_single_char_loop_atom():
    """Only a char class is a single-char loop atom — a literal or ref is not."""
    charclass = IrCharClass(IrChr("a"))
    assert STOPSET_ATOM.resolve(charclass).eval(None, charclass, ()) is True

    literal = IrLiteral("x")
    assert STOPSET_ATOM.resolve(literal).eval(None, literal, ()) is False

    ref = IrRuleRef("r")
    assert STOPSET_ATOM.resolve(ref).eval(None, ref, ()) is False


# ── SPAN — how short and how long a match can be ──────────────────────────


def span_of(source: str, rule: str = "x") -> tuple[float, float]:
    """``rule``'s span in ``source``, over the grammar the PDA analyses."""
    compiled = compile_text(source, cache_key=f"span-{hash(source)}")
    grammar = lift_optional_nullables(compiled.codegen_grammar)
    return rule_spans({str(one.name): one for one in grammar.rules})[rule]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('x ::= "abc"\n', (3.0, 3.0)),
        ("x ::= [a-z]\n", (1.0, 1.0)),
        ('x ::= "ab" "c"?\n', (2.0, 3.0)),
        ("x ::= [a-z]{2,4}\n", (2.0, 4.0)),
        ('x ::= "a" | "bcd"\n', (1.0, 3.0)),
        ("x ::= [a-z]*\n", (0.0, math.inf)),
        ('x ::= "(" x ")" | "y"\n', (1.0, math.inf)),
    ],
    ids=["literal", "class", "optional", "bounded", "arms", "unbounded", "recursion"],
)
def test_span_is_the_shortest_and_longest_match(
    source: str, expected: tuple[float, float]
) -> None:
    """Fewest and most characters a match of ``x`` can take."""
    assert span_of(source) == expected


def test_a_cycle_of_rules_is_unbounded_in_every_rule_it_reaches() -> None:
    """``a → b → c → a``: each round one rule rises, so widening must reach
    all three, not stop at whichever rose last — and must not undo itself."""
    source = 'a ::= "x" b | "y"\nb ::= "x" c | "y"\nc ::= "x" a | "y"\n'
    for rule in ("a", "b", "c"):
        assert span_of(source, rule) == (1.0, math.inf), rule


def test_an_unmeasured_rule_under_a_zero_count_does_not_poison_the_low_end() -> None:
    """``a*`` before ``a`` is measured: ``inf`` times a count of zero is NaN,
    which ``min`` never lowers. A zero count contributes nothing instead."""
    source = 'root ::= a* "x"\na ::= "y" a?\n'
    for rule in ("root", "a"):
        low, high = span_of(source, rule)
        assert not (math.isnan(low) or math.isnan(high)), rule
        assert (low, high) == (1.0, math.inf), rule
