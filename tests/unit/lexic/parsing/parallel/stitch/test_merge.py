"""Focused shell and boundary reconstruction tests."""

from __future__ import annotations

from itertools import islice

import pytest

import lexic.parsing.parallel.stitch.merge as merge_module
from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing import DEFAULT_CONFIG, parse_model
from lexic.parsing.parallel.discovery.regions import find
from lexic.parsing.parallel.discovery.partition import Division, partition, units
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.stitch.merge import MergeRequest, witnesses
from lexic.parsing.parallel.stitch.plan import RegionWork
from lexic.parsing.parallel.stitch.tasks import region_works
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_exact_split,
    assert_outer_split,
    record_stitches,
    recorded_split,
    split_case,
)

OUTER = (
    "root ::= outer\n"
    "outer ::= lead group trail\n"
    'lead ::= "[" ws\n'
    "group ::= open items close\n"
    'open ::= "{" ws\n'
    'close ::= ws "}"\n'
    "items ::= item more*\n"
    "more ::= comma item\n"
    'comma ::= "," ws\n'
    "item ::= [a-z]+\n"
    'trail ::= ws "]"\n'
    'ws ::= " "*\n'
)

INLINE_BOUNDARIES = (
    "root ::= array\n"
    'array ::= "[" ws items "]" ws\n'
    "items ::= value more*\n"
    "more ::= comma value\n"
    'comma ::= "," ws\n'
    "value ::= object\n"
    'object ::= "{" word "}" ws\n'
    "word ::= [a-z]+\n"
    'ws ::= " "*\n'
)

TRAILING_ONLY = (
    "root ::= array\n"
    'array ::= "[" items close\n'
    "items ::= word more*\n"
    'more ::= "," word\n'
    'close ::= ws "]"\n'
    "word ::= [a-z]+\n"
    'ws ::= " "*\n'
)


def test_configured_outer_arm_preserves_closing_boundary_spaces() -> None:
    """An indirect group keeps whitespace owned by its closing arm."""
    text = "[ { " + ", ".join("a" * 20 for _ in range(900))
    text += "   } ]"
    assert_outer_split(split_case(OUTER, text, "group", 4), text)


def test_mixed_separator_whitespace_survives_shallow_joint_reconstruction() -> None:
    """Boundary tails retain varying separator whitespace during a shallow join."""
    separators = [", ", ",    ", ",   ", ",  "]
    items = ["a" * 20]
    for index in range(899):
        items.append(separators[index % len(separators)] + "a" * 20)
    text = "[ { " + "".join(items) + " } ]"
    assert_exact_split(split_case(OUTER, text, "group", 8), text)


def test_inline_closer_preserves_opening_whitespace_slot() -> None:
    """Opening whitespace survives despite an inline closing bracket."""
    text = "[   " + ", ".join("{" + "a" * 20 + "}" for _ in range(900)) + "]"
    assert_exact_split(split_case(INLINE_BOUNDARIES, text, "array", 8), text)


def test_trailing_only_close_preserves_closing_boundary_spaces() -> None:
    """A trailing close arm retains its final whitespace during stitching."""
    words = ",".join("a" * 20 for _ in range(900))
    text = "[" + words + "   ]"
    plan, sequential, parallel = split_case(TRAILING_ONLY, text, "array", 8)

    assert plan is not None
    assert plan.outer_begin is None
    assert plan.outer_end is not None
    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text


def test_missing_shallow_witness_declines_without_reparsing_delegated_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed shell witness does not fall back to a large head parse — and,
    since witnesses are chosen before the pieces, nothing is parsed at all.
    The decline is pinned to its cause: generation WAS asked, and the same
    document with generation intact splits."""
    grammar_source = (
        "root ::= doc\n"
        "doc ::= group\n"
        'group ::= "{" items "}"\n'
        "items ::= item more*\n"
        'more ::= "," item\n'
        "item ::= [0-9]+\n"
    )
    compiled = compile_text(grammar_source)
    text = "{" + ",".join(str(index) for index in range(2600)) + "}"

    asked: list[str] = []

    def fail_generate(rule_name, *_args, **_kwargs):
        asked.append(rule_name)
        raise LexicError("forced shallow witness failure")

    monkeypatch.setattr(merge_module, "_template_tail", lambda *_args: None)
    monkeypatch.setattr(merge_module, "generate", fail_generate)
    recording_parse, parallel = recorded_split(compiled, text, 4)

    assert parallel is None
    assert asked, "generation was never asked — the split declined for another reason"
    assert not recording_parse.calls, "a piece was parsed before the decline"
    short_calls = [
        (start, length) for start, length in recording_parse.calls if length < MIN_CHUNK
    ]
    assert short_calls == []
    assert not any(start == "item" for start, _length in recording_parse.calls)
    # The positive control: generation intact, it splits. A fresh artefact,
    # because the draw above is memoised per grammar and ran dry on purpose.
    monkeypatch.undo()
    stitched = record_stitches(monkeypatch)
    fresh = compile_text(grammar_source, cache_key="missing-witness-control")
    _recording, control = recorded_split(fresh, text, 4)
    assert control is not None
    assert stitched == [True]


def test_multiple_regions_use_unique_generated_standins_not_source_heads() -> None:
    """Shared head rules never make shell routing reparse a delegated item."""
    grammar_source = (
        "root ::= group group\n"
        'group ::= "{" items "}"\n'
        "items ::= item more*\n"
        'more ::= "," item\n'
        "item ::= [a-z]+\n"
    )
    compiled = compile_text(grammar_source)
    item = "a" * 3000
    group = "{" + ",".join([item] * 8) + "}"
    text = group + group
    recording_parse, parallel = recorded_split(compiled, text, 8)

    assert parallel is not None
    assert parallel.to_text() == text
    group_calls = [
        length for start, length in recording_parse.calls if start == "group"
    ]
    # Two groups of eight 3000-byte items at an eighth of 48 KB apiece: each
    # piece packs two adjacent items, so four per group — adjacent items ship
    # together, never one piece per item.
    assert (
        sorted(length for length in group_calls if length >= MIN_CHUNK)
        == [2 * 3000 + 1 + 2] * 8
    )
    assert all(length >= MIN_CHUNK or length <= 256 + 2 for length in group_calls)


TRAILING_NL = "{" + ",".join(f'"k{i}":"' + "q" * 400 + '"' for i in range(60)) + "\n}"
"""An object region whose closer is preceded by a newline its OWN edge slot
holds — the noise a stand-in must leave outside the items it splices in."""


def _trailing_works() -> list[RegionWork]:
    """json.gbnf's object region over :data:`TRAILING_NL`, witnesses assigned."""
    compiled = compile_text((GROUND_TRUTH / "json.gbnf").read_text())
    grammar = compiled.codegen_grammar
    request = MergeRequest(parse_model, TRAILING_NL, compiled.product, DEFAULT_CONFIG)
    found = [r for r in find(grammar, TRAILING_NL) if r.rule != str(grammar.start)]
    return region_works(request, grammar, partition(TRAILING_NL, found, 4), grammar)


def test_a_witness_that_absorbs_the_regions_edge_noise_still_stitches_exactly(
    monkeypatch,
) -> None:
    """``{}`` ends in a value whose own whitespace can take the newline, so
    its stand-in's edge slot comes out without it. The region's edges are the
    pieces' to decide, not the stand-in's: offered only that witness, the
    region divides, and the split keeps the newline where the whole parse
    puts it."""
    monkeypatch.setattr(merge_module, "witnesses", lambda _plan: iter(['"":{}']))
    works = _trailing_works()
    assert [work.witness for work in works] == ['"":{}']
    compiled = compile_text((GROUND_TRUTH / "json.gbnf").read_text())
    stitched = record_stitches(monkeypatch)
    split = compiled.parse(TRAILING_NL, cores=4)
    assert stitched == [True]
    assert split.dump() == compiled.parse(TRAILING_NL, cores=1).dump()
    assert split.to_text() == TRAILING_NL


def test_an_absorbing_witness_offered_first_is_taken_and_keeps_the_newline(
    monkeypatch,
) -> None:
    """Offered the absorbing witness first, assignment takes it — its edges no
    longer matter — and the split stitches with the newline kept."""
    compiled = compile_text((GROUND_TRUTH / "json.gbnf").read_text())
    stitched = record_stitches(monkeypatch)
    monkeypatch.setattr(
        merge_module, "witnesses", lambda _plan: iter(['"":{}', '"":null'])
    )
    split = compiled.parse(TRAILING_NL, cores=4)
    assert stitched == [True]
    assert split.dump() == compiled.parse(TRAILING_NL, cores=1).dump()


def _json_gbnf_works(text: str, workers: int) -> tuple[MergeRequest, list[RegionWork]]:
    """json.gbnf's regions over ``text``, bound — witnesses assigned."""
    compiled = compile_text((GROUND_TRUTH / "json.gbnf").read_text())
    grammar = compiled.codegen_grammar
    request = MergeRequest(parse_model, text, compiled.product, DEFAULT_CONFIG)
    found = [r for r in find(grammar, text) if r.rule != str(grammar.start)]
    works = region_works(request, grammar, partition(text, found, workers), grammar)
    assert works, "the fixture must divide"
    return request, works


def test_the_witness_draw_outlasts_the_regions_a_head_is_shared_by() -> None:
    """json.gbnf's ``value`` head once ran dry at 18 while 28 regions shared it."""
    _request, works = _json_gbnf_works(TRAILING_NL, 4)
    drawn = list(islice(witnesses(works[0].plan), 40))
    assert len(set(drawn)) == 40


ECHOING = (
    '{"echo":[0,{},"",-0,[],null,true,false],"items":['
    + ",".join('"' + "q" * 400 + '"' for _ in range(60))
    + "]}"
)
"""The shell text outside the divided run already holds the draw's first heads."""


def test_a_needle_never_occurs_elsewhere_in_the_unit_holding_it() -> None:
    """A pre-filter for liveness: a needle whose text occurs elsewhere in its
    holder would route ambiguously and the split would decline after its
    pieces. The draw's first choice here IS present, so the filter chose."""
    _request, works = _json_gbnf_works(ECHOING, 4)
    at = next(k for k, w in enumerate(works) if w.region.rule == "array")
    divided = [Division(w.region, w.cuts) for w in works]
    blank = units(ECHOING, divided, [""] * len(works))
    (holder,) = [unit for unit in blank if at in unit.held]
    needle = works[at].needle
    assert next(witnesses(works[at].plan)) in holder.text
    assert needle is not None
    assert needle.to_text() not in holder.text


def test_a_region_without_a_witness_stays_in_the_shell_and_the_rest_divide(
    monkeypatch,
) -> None:
    """Not all-or-nothing: the run with no witness goes back undivided,
    decided before any piece is parsed, and every other run keeps its own."""

    def only_arrays(plan):
        """The real draw, except none for the object's ``member`` head."""
        return witnesses(plan) if plan.head_rule != "member" else iter(())

    text = '{"a":[' + ",".join('"' + "q" * 400 + '"' for _ in range(60)) + "]}"
    text = "[" + text + "," + TRAILING_NL + "]"
    monkeypatch.setattr(merge_module, "witnesses", only_arrays)
    _request, works = _json_gbnf_works(text, 4)
    rules = [work.region.rule for work in works]
    assert "object" not in rules
    assert rules and all(work.witness for work in works)


NESTED = (
    '{"b": 1,\n "a": [\n'
    + ",\n".join('"' + "q" * 400 + '"' for _ in range(120))
    + "\n ]\t, "
    + '"c": {"d": ['
    + ",".join('"' + "r" * 400 + '"' for _ in range(40))
    + "] }\n}"
)
"""An object whose SECOND member holds an array bigger than a piece, with
noise at both of the array's edges, and a third member holding an object
around a smaller array."""


@pytest.mark.parametrize("name", ["json.gbnf", "json.abnf", "json.ebnf"])
@pytest.mark.parametrize("workers", [2, 4, 8])
def test_a_nested_division_stitches_to_the_sequential_model(
    name: str, workers: int, monkeypatch
) -> None:
    """The array is divided inside the divided object and found by the item
    that holds it; the stitch is taken, and the model is the sequential one."""
    path = GROUND_TRUTH / name
    compiled = compile_text(path.read_text(), flavour=path.suffix.lstrip("."))
    grammar = compiled.codegen_grammar
    found = [r for r in find(grammar, NESTED) if r.rule != str(grammar.start)]
    picked = partition(NESTED, found, workers)
    assert len(picked) >= 2, "the fixture must nest a division inside another"
    stitched = record_stitches(monkeypatch)
    split = compiled.parse(NESTED, cores=workers)
    assert stitched == [True]
    assert split == compiled.parse(NESTED, cores=1)
    assert split.to_text() == NESTED
