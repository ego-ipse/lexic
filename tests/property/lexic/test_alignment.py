"""Property-based equality up to renaming: rename a grammar, find it again.

The corpus gates in
``tests/integration/lexic/roundtrip/test_rename_alignment.py`` pin the answer
on one hand-written rename; this drives it over random bijections of every
small corpus grammar's rule names, which is where a colour refinement that
keyed on anything name-shaped would show.

The renaming under test is applied by the witness type itself. That is not
circular: what is being checked is the SEARCH — that alignment recovers a
bijection it was never told, and that every bijection it offers really carries
one grammar onto the other.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from lexic.compile import canonical_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAst, IrRename, IrRenaming, align_names, canonicalize
from tests.paths import GROUND_TRUTH

BUDGET = {
    "suppress_health_check": [HealthCheck.too_slow],
    "deadline": None,
}
"""No per-example deadline: the first example of a grammar pays its parse and
canonicalisation, which lands inside hypothesis's timed window. The timing
gates live in ``tests/performance/``."""

GRAMMARS = ("arithmetic.gbnf", "list.gbnf", "json.gbnf", "chess.gbnf")

LABELS = 48
"""Enough distinct labels to relabel any grammar in ``GRAMMARS`` (the largest
has 32 rules); a rule takes the label standing at its own position."""


def loaded(name: str) -> IrAst:
    """One corpus grammar, canonical and directive-bound."""
    text = (GROUND_TRUTH / name).read_text(encoding="utf-8")
    return canonicalize(canonical_grammar(text, GBNF_FLAVOUR))


def relabelled(ast: IrAst, order: list[int]) -> tuple[IrAst, IrRenaming]:
    """The grammar with its rules renamed by position, and the renaming used.

    :param ast: The canonical grammar.
    :param order: A permutation of enough labels to cover any corpus grammar;
        each rule takes the label at its position, so a rule's new spelling
        carries no trace of its old one.
    :returns: The renamed grammar and the bijection that produced it.
    """
    names = [str(rule.name) for rule in ast.rules]
    renaming = IrRenaming(
        *sorted(IrRename(name, f"n{order[i]}") for i, name in enumerate(names))
    )
    return renaming.renamed(ast), renaming


@settings(max_examples=30, **BUDGET)
@given(st.sampled_from(GRAMMARS), st.permutations(range(LABELS)))
def test_a_renamed_grammar_aligns_back_by_the_renaming_used(
    name: str, order: list[int]
) -> None:
    """The search recovers the bijection nobody told it about."""
    ast = loaded(name)
    target, renaming = relabelled(ast, order)
    alignment = align_names(ast, target)
    assert renaming in alignment.renamings or alignment.capped


@settings(max_examples=30, **BUDGET)
@given(st.sampled_from(GRAMMARS), st.permutations(range(LABELS)))
def test_every_offered_bijection_carries_the_grammar_across(
    name: str, order: list[int]
) -> None:
    """Offered means valid, on every grammar and every relabelling."""
    ast = loaded(name)
    target, _ = relabelled(ast, order)
    canonical = canonicalize(target)
    for offered in align_names(ast, target).renamings:
        assert canonicalize(offered.renamed(ast)) == canonical


@settings(max_examples=20, **BUDGET)
@given(st.sampled_from(GRAMMARS), st.permutations(range(LABELS)))
def test_alignment_is_symmetric(name: str, order: list[int]) -> None:
    """If one grammar renames to another, the other renames back."""
    ast = loaded(name)
    target, _ = relabelled(ast, order)
    there, back = align_names(ast, target), align_names(target, ast)
    assert bool(there.renamings) == bool(back.renamings)
