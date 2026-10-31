"""A bracketed run separated by a SET of lead characters divides.

``"(" expr ")"`` over ``expr ::= term (addop term)*`` with ``addop ::= "+" |
"-"``: the run's separator is whichever of ``+`` and ``-`` stands between two
terms, so a region cuts at either and rebuilds each joint with the character the
document holds there. It must never cut at the terms' own ``*`` and ``/``, which
stand INSIDE an item, even where another run's lead puts them in the scan's
vocabulary at the same depth.

Every case's model is the sequential one — class, model and text — at every
worker count, over documents drawn so the cuts fall on both leads.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.discovery.regions import find, pair_rules
from lexic.parsing.parallel.roles.derive import run_leads
from tests.paths import GROUND_TRUTH
from tests.split_helpers import (
    PAREN_SUM,
    assert_parallel_matches_sequential,
    engages,
)
from tools.benchmark.cases.grammars import BENCHES

_CORES = (2, 8, 16)

_ARITH = next(b for b in BENCHES if b.name == "arithmetic")

STARS = PAREN_SUM.replace(
    "root ::= expr\n", 'root ::= factor stars\nstars ::= (star [a-z])*\nstar ::= "*"\n'
)
"""Arithmetic whose ``*`` is ALSO a separator elsewhere: ``stars`` separates its
items by ``*`` at the top level, so the scan watches ``*`` and a paren frame
meets its terms' ``*`` at its own depth. The frame keeps ``+-``."""


def _expr(rng: random.Random, terms: int) -> str:
    """A flat sum of products, both additive leads drawn at random."""
    out = [f"{rng.randrange(1, 97)}*{rng.randrange(1, 13)}"]
    for _ in range(terms - 1):
        out.append(rng.choice("+-"))
        out.append(f"{rng.randrange(1, 97)}/{rng.randrange(1, 13)}")
    return "".join(out)


def _gt_expr(rng: random.Random, terms: int) -> str:
    """The ground-truth formulation's expression: one lead class ``[-+*/]``."""
    return rng.choice("ab") + "".join(
        rng.choice("-+*/") + str(rng.randrange(1, 97)) for _ in range(terms - 1)
    )


def _documents() -> list[tuple[str, str, str]]:
    """``(id, grammar, document)``: three formulations, three sizes each,
    every draw seeded."""
    rng = random.Random(22)
    gt = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    out = []
    for seed in range(3):
        terms = 3000 + 700 * seed
        bench = f"({_expr(rng, terms)})"
        out.append((f"bench-paren-{seed}", _ARITH.source, bench))
        ground = f"({_gt_expr(rng, terms)})=x\n"
        out.append((f"gt-paren-{seed}", gt, ground))
        stars = f"({_expr(rng, terms)})*a*b"
        out.append((f"stars-{seed}", STARS, stars))
    return out


DOCUMENTS = _documents()


@pytest.mark.parametrize("cores", _CORES)
@pytest.mark.parametrize(
    ("source", "text"), [d[1:] for d in DOCUMENTS], ids=[d[0] for d in DOCUMENTS]
)
def test_a_lead_set_region_divides_to_the_sequential_model(
    source: str, text: str, cores: int
) -> None:
    """The split takes the document and answers the sequential model."""
    compiled = compile_text(source, cache_key=f"lead-set-{hash(source)}")
    assert engages(compiled, text, cores), f"at {cores}: the region declined"
    assert_parallel_matches_sequential(compiled, text, cores)


def test_the_run_leads_are_its_own_and_not_its_terms() -> None:
    """The paren pair's run leads with ``+-``; ``*/`` lead the terms' runs."""
    compiled = compile_text(_ARITH.source, cache_key="lead-set-leads")
    view = compiled.split_analysis or compiled.grammar
    assert run_leads(view, pair_rules(view)) == {"(": frozenset("+-")}


def test_a_frame_never_keeps_another_runs_lead_at_its_depth() -> None:
    """``*`` is watched (``stars``), and the paren frame meets its terms' ``*``
    at its own depth: the region keeps only the ``+`` and ``-`` offsets."""
    compiled = compile_text(STARS, cache_key="lead-set-stars")
    text = "(1*2+3*4-5/6+7)*a*b"
    (region,) = find(compiled.split_analysis or compiled.grammar, text)
    assert [text[at] for at in region.marks] == ["+", "-", "+"]


LIST_OF_SUMS = (
    'root ::= "[" e ("," e)* "]"\n'
    "e ::= t (addop t)*\n"
    'addop ::= "+" | "-"\n'
    't ::= [0-9]+ | "(" e ")"\n'
)
"""A one-literal list beside a lead-set pair: the list's items are sums, so
``+`` and ``-`` are watched for the paren pair and stand at the list's depth
too. The list's region keeps its commas, and its run is ``e ("," e)*``, never
the sum each ``e`` holds."""


@pytest.mark.parametrize("cores", _CORES)
def test_a_list_of_sums_keeps_its_own_split(cores: int) -> None:
    """The list divides on its commas, to the sequential model."""
    compiled = compile_text(LIST_OF_SUMS, cache_key="lead-set-list-of-sums")
    text = (
        "["
        + ",".join(
            f"{k}+{k % 7}-{k % 5}" if k % 3 else f"({k}-1)+{k}" for k in range(6000)
        )
        + "]"
    )
    assert engages(compiled, text, cores), f"at {cores}: the list declined"
    assert_parallel_matches_sequential(compiled, text, cores)


def test_a_list_of_sums_region_keeps_only_its_commas() -> None:
    """``[`` has no lead set: its region keeps the one-literal marks it always
    had, and its run's container is the list rule, not the sum."""
    compiled = compile_text(LIST_OF_SUMS, cache_key="lead-set-list-marks")
    view = compiled.split_analysis or compiled.grammar
    assert run_leads(view, pair_rules(view)) == {"(": frozenset("+-")}
    text = "[1+2,3-4,(5+6)-7]"
    (outer,) = [r for r in find(view, text) if text[r.opener] == "["]
    assert [text[at] for at in outer.marks] == [",", ","]
