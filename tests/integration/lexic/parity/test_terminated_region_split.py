"""A bracketed TERMINATED run divides: ``"[" entry+ "]"`` with each entry closed by
``;``.

No separator stands between two entries, so the cut falls AFTER a terminator
and each piece keeps the one it was cut after; the region's node is its first
piece's with the run the pieces' runs in order. A unit that spells its
terminator inside itself owns some of the marks and never splits, and a
separator another run uses inside the units never becomes a cut.

Every case's model is the sequential one — class, model and text — at every
worker count, over documents drawn so the cuts fall on both kinds of entry.
"""

from __future__ import annotations

import random

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.discovery.regions import find, scan_vocabulary
from lexic.parsing.parallel.stitch.plan import derive_plan
from lexic.parsing.parallel.stitch.tasks import safe_leads
from tests.split_helpers import assert_parallel_matches_sequential, engages

_CORES = (2, 8, 16)

UNITS = (
    'entry ::= "set " name " = " value ";" | "get " name ";"\n'
    "name ::= [a-z]+\n"
    "value ::= [0-9]+\n"
)
BRACKETED = 'root ::= "[" entry+ "]"\n' + UNITS
HELD = 'root ::= "{" block ("," block)* "}"\nblock ::= "[" entry+ "]"\n' + UNITS
"""Terminated runs HELD by a comma list: each `[` region needs a stand-in its
holder cannot confuse, and two kinds of cut nest."""
LISTED = (
    'root ::= "[" entry+ "]"\n'
    'entry ::= "set " name ("," name)* " = " value ";" | "get " name ";"\n'
    "name ::= [a-z]+\nvalue ::= [0-9]+\n"
)
"""A unit holding a comma run of its own: `,` is watched, and stands at the
bracket's depth inside the units. The terminated frame keeps only `;`."""
LED = (
    'root ::= "[" entry more* "]"\nmore ::= "," entry\nentry ::= e ";"\ne ::= [a-z]+\n'
)
"""A run both led by `,` and closed by `;`: one reading calls it led for the
scan and the plan alike, so a cut never keeps `;` and merges as if `,` had been
dropped."""


def _entries(rng: random.Random, n: int) -> str:
    return "".join(
        f"set k{rng.choice('abcdefgh')} = {rng.randrange(1000)};"
        if rng.random() < 0.6
        else f"get k{rng.choice('abcdefgh')};"
        for _ in range(n)
    )


def _documents() -> list[tuple[str, str, str]]:
    """``(id, grammar, document)``, every draw seeded."""
    rng = random.Random(22)
    out = []
    for seed in range(3):
        n = 3000 + 900 * seed
        out.append((f"bracketed-{seed}", BRACKETED, "[" + _entries(rng, n) + "]"))
        blocks = ",".join("[" + _entries(rng, n // 4) + "]" for _ in range(4))
        out.append((f"held-{seed}", HELD, "{" + blocks + "}"))
        listed = "".join(
            f"set k{rng.choice('ab')},q{rng.choice('cd')} = {rng.randrange(99)};"
            for _ in range(n)
        )
        out.append((f"listed-{seed}", LISTED, "[" + listed + "]"))
    return out


DOCUMENTS = _documents()


@pytest.mark.parametrize("cores", _CORES)
@pytest.mark.parametrize(
    ("source", "text"), [d[1:] for d in DOCUMENTS], ids=[d[0] for d in DOCUMENTS]
)
def test_a_terminated_region_divides_to_the_sequential_model(
    source: str, text: str, cores: int
) -> None:
    """The split takes the document and answers the sequential model."""
    compiled = compile_text(source, cache_key=f"terminated-{hash(source)}")
    assert engages(compiled, text, cores), f"at {cores}: the region declined"
    assert_parallel_matches_sequential(compiled, text, cores)


def test_a_terminated_frame_keeps_only_its_terminators() -> None:
    """`,` runs inside the units at the bracket's depth; the region's marks are
    the entries' `;` and nothing else, and they END items."""
    compiled = compile_text(LISTED, cache_key="terminated-marks")
    text = "[set a,c = 1;get b;set a,d,c = 2;]"
    (region,) = find(compiled.split_analysis or compiled.grammar, text)
    assert region.ends
    assert [text[at] for at in region.marks] == [";", ";", ";"]


def test_a_unit_spelling_its_terminator_inside_is_refused() -> None:
    """``"a;b;"`` ends with `;` and holds one more: a cut after the inner one
    would end a piece inside a unit, so the proof refuses the plan."""
    compiled = compile_text(
        'root ::= "[" entry+ "]"\nentry ::= "a;b;" | "c;"\n', cache_key="inner-term"
    )
    plan = derive_plan(compiled.codegen_grammar, compiled.product, "root")
    assert plan is not None and plan.ends
    assert not safe_leads(compiled.split_analysis or compiled.grammar, plan)
    text = "[" + "a;b;c;" * 3000 + "]"
    assert not engages(compiled, text, 8)
    assert_parallel_matches_sequential(compiled, text, 8)


@pytest.mark.parametrize("cores", _CORES)
def test_a_run_both_led_and_terminated_is_led_for_scan_and_plan_alike(
    cores: int,
) -> None:
    """The scan does not call the bracket terminated, the plan is not a
    terminated one, and the document divides exactly or not at all."""
    compiled = compile_text(LED, cache_key="terminated-led")
    grammar = compiled.codegen_grammar
    assert "[" not in scan_vocabulary(grammar).ends
    plan = derive_plan(grammar, compiled.product, "root")
    assert plan is None or not plan.ends
    rng = random.Random(7)
    words = [
        "".join(rng.choice("abc") for _ in range(rng.randint(1, 6)))
        for _ in range(6000)
    ]
    doc = "[" + words[0] + ";" + "".join("," + w + ";" for w in words[1:]) + "]"
    assert_parallel_matches_sequential(compiled, doc, cores)
