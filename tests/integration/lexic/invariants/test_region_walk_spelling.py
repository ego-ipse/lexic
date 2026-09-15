"""The region walk's answer does not depend on how its role tables are spelled.

`regions._walk` reads private spelling strings rather than the shared dicts
`Vocab` carries, because shared-dict membership in that loop does not scale
across threads. That is a representation change to a hot loop, and a hot loop
whose answer shifts is worse than a slow one — so this re-derives every region
through the dict form the change replaced and demands byte-identical results:
same count, same offsets, same rule, same separators, same order.

The dict form is spelled out HERE, independently, rather than imported: if it
were a helper in `src` both arms could drift together and the differential
would pass while meaning nothing.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.parallel.discovery.interiors import skip_delimited
from lexic.parsing.parallel.discovery.regions import (
    Region,
    _roles,
    _sweep,
    _vocabulary,
    _walk,
    find,
)
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

JSON_GRAMMARS = ("json.gbnf", "json.abnf")
"""Both ground-truth json formulations — neither is privileged."""

MIN_SPANS = (0, 64)
"""The floor a scheduling caller passes, and no floor at all."""

JSON_DOCUMENT = (
    "{"
    + ", ".join(f'"k{i}": [1, 2, {{"b": "x, y"}}]' for i in range(40))
    + ', "e": "]"}'
)
"""One long outer object over many short inner ones.

Sized so both floors discriminate and neither is vacuous: the outer region
clears 64 characters and every inner one falls under it, so ``min_span=64``
exercises the filter rather than emptying the answer. The quoted ``"]"`` and
``"x, y"`` put a closer and a separator inside a string, which is where an
interior skip has to hold.
"""


def outside_interiors(text, offsets, vocab) -> list[int]:
    """The offsets no opaque interior covers, as a pass of its own.

    The module under test carries the interior on a `skip_to` cursor threaded
    through its single loop. Stating it as a separate filter keeps this
    reading independent in SHAPE and not merely in wording: a copy of the
    cursor form could not expose a fault in the cursor form.
    """
    live: list[int] = []
    covered_to = 0
    for at in offsets:
        if at < covered_to:
            continue
        entry = vocab.skips.get(text[at])
        if entry is None:
            live.append(at)
        else:
            covered_to = skip_delimited(text, at, entry)
    return live


def walk_through_dicts(text, offsets, vocab, min_span) -> list[Region]:
    """The walk as it read before the spelling change, kept independent.

    The dict form: `char in pairs`, `char in vocab.closers` with the stack-top
    check, then `char in vocab.marks`, over the offsets an interior leaves
    behind. The branch ORDER is part of the contract — a character with two
    roles takes the first that claims it, and a closer the stack does not want
    falls through to the mark branch.
    """
    pairs = vocab.pairs
    found: list[Region] = []
    stack: list[tuple[int, str, list[int]]] = []
    for at in outside_interiors(text, offsets, vocab):
        char = text[at]
        if char in pairs:
            stack.append((at, char, []))
        elif char in vocab.closers and stack and stack[-1][1] == vocab.closers[char]:
            opener, open_char, inside = stack.pop()
            if inside and at - opener >= min_span:
                found.append(Region(opener, at, pairs[open_char][1], tuple(inside)))
        elif char in vocab.marks and stack:
            stack[-1][2].append(at)
    return found


def both_walks(grammar, text: str, min_span: int):
    """`(spelled, dicts)` over one grammar and document."""
    vocab = _vocabulary(grammar)
    offsets = _sweep(text, vocab.watched)
    return (
        _walk(text, offsets, _roles(vocab), min_span),
        walk_through_dicts(text, offsets, vocab, min_span),
    )


@pytest.mark.parametrize("min_span", MIN_SPANS)
@pytest.mark.parametrize("name", JSON_GRAMMARS)
def test_both_json_formulations_walk_identically(name: str, min_span: int) -> None:
    """Both ground-truth json grammars, both floors, region for region."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    spelled, dicts = both_walks(compiled.codegen_grammar, JSON_DOCUMENT, min_span)
    assert spelled == dicts
    assert spelled, f"{name} found no regions — the comparison proved nothing"


@pytest.mark.parametrize("min_span", MIN_SPANS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_walks_identically(bench, min_span: int) -> None:
    """Every benchmark grammar over its own corpus, both floors.

    Region-bearing grammars are the point; the rest still assert that an empty
    answer is empty in both forms, and the roster-level non-vacuity check
    below is what stops that being the whole suite.
    """
    grammar = bench.compiled.codegen_grammar
    spelled, dicts = both_walks(grammar, bench.corpus, min_span)
    assert spelled == dicts


def test_the_roster_differential_is_not_vacuous() -> None:
    """Several bench grammars really do yield regions.

    Most of the roster has no bracketed run, so most rows above compare two
    empty lists. This is what keeps that from passing for coverage: named by
    count, not by grammar, so no formulation is privileged and a roster change
    that quietly emptied the sweep fails here.
    """
    bearing = {
        b.name: len(find(b.compiled.codegen_grammar, b.corpus))
        for b in BENCHES
        if find(b.compiled.codegen_grammar, b.corpus)
    }
    assert len(bearing) >= 2, f"only {bearing} produced regions"
    assert sum(bearing.values()) >= 100, f"too few regions to compare: {bearing}"


def test_a_sabotaged_spelling_is_caught() -> None:
    """The differential can FAIL — the tables' order is load-bearing.

    Permuting a spelling string without permuting its parallel tuple is
    exactly the defect the representation invites, and it must not pass.
    """
    compiled = compile_text(
        "root ::= obj\n"
        'obj ::= "{" item ("," item)* "}"\n'
        "item ::= [a-z]+\n"
        'arr ::= "[" item ("," item)* "]"\n'
    )
    vocab = _vocabulary(compiled.codegen_grammar)
    text = "{a,b,c}"
    offsets = _sweep(text, vocab.watched)
    roles = _roles(vocab)
    honest = _walk(text, offsets, roles, 0)
    assert honest == walk_through_dicts(text, offsets, vocab, 0)
    assert honest, "the fixture must produce a region for sabotage to mean anything"

    assert len(set(roles.names)) > 1, "the fixture must carry distinct values"
    sabotaged = roles._replace(names=tuple(reversed(roles.names)))
    assert _walk(text, offsets, sabotaged, 0) != honest
