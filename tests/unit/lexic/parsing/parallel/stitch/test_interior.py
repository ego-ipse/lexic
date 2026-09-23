"""Tests for ``lexic.parsing.parallel.stitch.interior`` — the routed-interior
split.

A routed interior holds a TERMINATED repetition, not a separated one: every
unit owns its final character, so putting the pieces back is a concatenation
of their runs rather than a rebuild of consumed separators. These tests pin
that seam directly (``interior_route`` + ``stitch_interior``), then exercise
the whole thing through the public ``compiled.parse`` seam — the split's own
entry point via ``lexic.parsing.parallel.orchestrate``.
"""

from __future__ import annotations

from typing import NamedTuple, cast

import pytest

from lexic.compile import Directives, compile_from_path, compile_text
from lexic.exceptions import EngineInvariantError, UnsupportedConstructError
from lexic.model import GrammarModel
from lexic.parsing import parse_model
from lexic.parsing.parallel.plan.folded import divide, folded_plan, locate
from lexic.parsing.parallel.plan.routed import REF, Descent, routed_plan
from lexic.parsing.parallel.stitch.interior import (
    _walk_down,
    fold_spines,
    interior_route,
    left_slot,
    stitch_interior,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.parallel.routed_fixtures import (
    ROUTED_GRAMMAR,
    routed_document,
    routed_pieces,
)
from tests.unit.lexic.parsing.parallel.stitch.support import recorded_split


def _vyx_document(rows: int) -> str:
    lines = "\n".join(f"id=ORD-{n:04d} qty={n % 9 + 1} note=_" for n in range(rows))
    body = lines + "\n"
    return f"!I o:wf L{len(body.encode())}<\n{body}>"


# ── interior_route + stitch_interior: the seam itself ─────────────────────


def test_interior_route_finds_the_shells_slot_and_the_runs_slot():
    """The descent's chain maps step for step onto real field slots.

    One route step per `Descent`, so the route says exactly as much as the
    descent did — the two-integer form it replaces derived the interior's
    depth and its run's index independently and could disagree.
    """
    compiled = compile_text(ROUTED_GRAMMAR)
    grammar, binding = compiled.codegen_grammar, compiled.product
    plan = routed_plan(grammar)
    assert plan is not None

    route = interior_route(binding, plan.chain, plan.rule, plan.run, plan.whole)

    assert route is not None
    steps, child = route
    assert len(steps) == len(plan.chain), "one step per descent, never derived"
    assert all(isinstance(slot, int) for slot, _index in steps)
    assert isinstance(child, int)


def test_interior_route_declines_a_container_or_rule_the_fold_does_not_know():
    """A shape surprise — a rule name the fold has no configuration for —
    declines rather than guessing a slot."""
    compiled = compile_text(ROUTED_GRAMMAR)
    binding = compiled.product

    unknown = (Descent("no-such-rule", 0, REF),)
    assert interior_route(binding, unknown, "block", 1, False) is None
    known = (Descent("start", 0, REF),)
    assert interior_route(binding, known, "no-such-rule", 1, False) is None


def test_stitch_interior_replaces_the_stand_ins_run_with_the_concatenated_pieces():
    """Parsing the stand-in shell plus every piece by hand, then stitching,
    reproduces the sequential model exactly — the seam ``routed_split`` itself
    calls through the pool."""
    compiled = compile_text(ROUTED_GRAMMAR)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = routed_document(700)
    found = routed_pieces(grammar, text, 4)
    assert found is not None
    plan, region, parts = found

    stand_in = (
        text[: region.opener + 1]
        + text[region.opener + 1 : region.marks[0] + 1]
        + text[region.closer :]
    )
    shell = parse_model(grammar, stand_in, binding)
    pieces = [parse_model(plan.rooted, part, binding) for part in parts]
    route = interior_route(binding, plan.chain, plan.rule, plan.run, plan.whole)
    assert route is not None

    stitched = stitch_interior(shell, pieces, route)
    sequential = parse_model(grammar, text, binding)

    assert stitched is not None
    assert stitched == sequential
    assert stitched.to_text() == text


def test_stitch_interior_refuses_a_chain_the_model_does_not_have():
    """A route slot that does not land on a model at all is a shape
    surprise, not a crash."""
    compiled = compile_text(ROUTED_GRAMMAR)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = routed_document(20)
    shell = parse_model(grammar, text, binding)

    with pytest.raises(EngineInvariantError, match="names slot 999"):
        stitch_interior(shell, [shell], (((999, None),), 0))


# ── the public seam: exactness, non-vacuity, refusal parity ───────────────


def test_the_split_equals_sequential_and_round_trips_at_two_and_eight_workers():
    """Byte-identical text and an equal model at both worker counts, through
    the public ``compiled.parse`` seam."""
    compiled = compile_text(ROUTED_GRAMMAR)
    text = routed_document(700)
    sequential = parse_model(compiled.codegen_grammar, text, compiled.product)

    for cores in (2, 8):
        parallel = compiled.parse(text, cores=cores)
        assert parallel == sequential
        assert parallel.to_text() == text


def test_the_split_is_not_vacuous_the_interior_actually_divides():
    """Worker-sensitive instrumentation: more than one ``block`` piece must
    actually have been parsed, not just the stand-in shell."""
    compiled = compile_text(ROUTED_GRAMMAR)
    text = routed_document(700)

    recording, parallel = recorded_split(compiled, text, 8)

    assert parallel is not None
    block_calls = [call for call in recording.calls if call[0] == "block"]
    assert len(block_calls) >= 2


def test_a_malformed_document_declines_then_sequential_parse_refuses_identically():
    """The split must never silently resolve a broken chunk; the sequential
    fallback raises the SAME refusal at every worker count."""
    compiled = compile_text(ROUTED_GRAMMAR)
    text = routed_document(700)
    bad = text.replace("abcdef", "abc1ef", 1)

    for cores in (1, 2, 8):
        try:
            compiled.parse(bad, cores=cores)
        except UnsupportedConstructError as error:
            assert "does not derive" in str(error)
        else:
            raise AssertionError(f"cores={cores} did not refuse a malformed document")


def test_a_lex_ns_style_variant_engages_the_same_route_and_region():
    """``@lexical`` marking the interior's own unit inlines ``line``'s
    reference into ``block-item``'s body without changing the derived route
    or the region it locates — same plan, same split, same model."""
    plain = compile_text(ROUTED_GRAMMAR)
    variant = compile_text(
        ROUTED_GRAMMAR, directives=Directives(lexical=frozenset({"block-item"}))
    )
    text = routed_document(700)

    plain_plan = routed_plan(plain.codegen_grammar)
    variant_plan = routed_plan(variant.codegen_grammar)
    assert plain_plan is not None
    assert variant_plan is not None
    assert variant_plan.rule == plain_plan.rule
    assert variant_plan.opening == plain_plan.opening
    assert variant_plan.closing == plain_plan.closing
    assert variant_plan.mark == plain_plan.mark

    sequential = parse_model(variant.codegen_grammar, text, variant.product)
    recording, parallel = recorded_split(variant, text, 8)

    assert parallel is not None
    assert parallel == sequential
    assert parallel.to_text() == text
    assert len([call for call in recording.calls if call[0] == "block"]) >= 2


# ── the ground-truth vyx fixture ────────────────────────────────────────


def test_the_vyx_fixtures_block_body_engages_the_route_and_splits_exactly():
    """vyx's own ``packet ::= ... envelope body? "\\n"?`` shape is the real
    grammar this mechanism was built for: ``block-body`` is reached by route,
    not by scanning, and both worker counts reproduce the sequential model
    byte for byte through the public seam."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    text = _vyx_document(600)
    plan = routed_plan(compiled.codegen_grammar)

    assert plan is not None
    assert plan.rule == "block-body"

    sequential = parse_model(compiled.codegen_grammar, text, compiled.product)
    for cores in (2, 8):
        parallel = compiled.parse(text, cores=cores)
        assert parallel == sequential
        assert parallel.to_text() == text

    recording, parallel = recorded_split(compiled, text, 8)
    assert parallel is not None
    assert len([call for call in recording.calls if call[0] == "block-body"]) >= 2


def test_a_malformed_vyx_document_declines_then_sequential_parse_refuses():
    """The same refusal-parity contract, over the real self-grammar rather
    than an authored one."""
    compiled = compile_from_path(GROUND_TRUTH / "vyx.gbnf")
    text = _vyx_document(600)
    bad = text.replace("id=ORD-0300", "id ORD-0300", 1)

    for cores in (1, 2, 8):
        try:
            compiled.parse(bad, cores=cores)
        except UnsupportedConstructError as error:
            assert "does not derive" in str(error)
        else:
            raise AssertionError(f"cores={cores} did not refuse a malformed document")


WRAPPED_TWO_PARA = (
    "root ::= open body close\n"
    "body ::= para+\n"
    'open ::= "<<<" nl\n'
    'close ::= ">>>" nl\n'
    "para ::= line+ blank\n"
    "line ::= [a-z ]+ nl\n"  # `+`, so a blank line is NOT a line
    "blank ::= nl\n"
    'nl ::= "\\n"\n'
)
"""wrapped-unit's shape, but a blank line cannot be absorbed as a line.

The shipped grammar writes `line ::= [a-z ]* nl`, so a blank line parses AS a
line and `line+` swallows the whole body: every document has exactly one
paragraph, and an intermediate run step can only ever address one element.
This variant is what makes a second paragraph reachable at all.
"""


def test_an_intermediate_run_of_two_declines_rather_than_taking_the_first():
    """The arity guard: `splice` bounds a run INDEX but never checks arity.

    `model.py`'s `repeated >= len(child)` lets a step naming element 0 of a
    run of three succeed and rewrite the first, leaving the other two — a
    wrong model, not a refusal. The exactly-one check that used to stand in
    the two-slot caller was written about a PIECE, where one unit is true by
    construction; an intermediate step walks the WHOLE model, where it is not.
    """
    compiled = compile_text(WRAPPED_TWO_PARA, cache_key="wrapped-two-para")
    para = "".join("line of text here\n" for _ in range(400)) + "\n"
    document = "<<<\n" + para * 2 + ">>>\n"

    model = compiled.parse(document, cores=1)
    body = list(list(model.children())[1].children())[0]
    assert len(body) == 2, "the variant grammar really does build two paragraphs"

    walked = _walk_down(model, ((1, None), (0, 0)))

    assert walked is None, "a run of two is not one run; the plan declines"


def test_the_two_paragraph_document_parses_identically_at_every_width():
    """Declining is not enough — the answer must still be the right one."""
    compiled = compile_text(WRAPPED_TWO_PARA, cache_key="wrapped-two-para-widths")
    para = "".join("line of text here\n" for _ in range(400)) + "\n"
    document = "<<<\n" + para * 2 + ">>>\n"
    sequential = compiled.parse(document, cores=1)

    for cores in (2, 4, 8, 16):
        split = compiled.parse(document, cores=cores)
        assert split.dump() == sequential.dump(), cores
        assert split.to_text() == document, cores


# ── the folded spine's join, and the licence it builds through ────────────


FOLDED = (
    "root ::= expr nl\n"
    "expr ::= expr op term | term\n"
    "term ::= [a-z]+\n"
    'op ::= " + "\n'
    'nl ::= "\\n"\n'
)
"""A spine under a required tail — the folded source's served shape."""


class FoldedCase(NamedTuple):
    """One folded document, parsed into the pieces a join is given.

    Named rather than a bare tuple of four: three of its members are models of
    a generated class and the fourth is the text they came from, and a caller
    unpacking them positionally is exactly how the lead models and the spines
    get swapped.

    :ivar spines: Each piece's folded-rule model, in document order.
    :ivar leads: The removed separators' models — one per join.
    :ivar step: The generated class one iteration of the spine is.
    :ivar text: The document the pieces were cut from.
    """

    spines: list[GrammarModel]
    leads: tuple[GrammarModel, ...]
    step: type[GrammarModel]
    text: str


def folded_pieces(terms: int, workers: int) -> FoldedCase:
    """One folded document of ``terms``, divided into ``workers`` pieces.

    The term count is chosen against the 2 KiB per worker floor, not for
    readability: a document too small for ``workers`` pieces divides into
    fewer, and a case that quietly got two where it asked for four would still
    pass while testing a narrower join than it names.
    """
    compiled = compile_text(FOLDED, cache_key="interior-folded")
    plan = folded_plan(compiled.codegen_grammar)
    assert plan is not None
    text = " + ".join("abcdefgh" for _ in range(terms)) + "\n"
    region = locate(text, plan)
    assert region is not None
    cut = divide(text, region, workers, plan)
    assert cut is not None
    assert len(cut.parts) == workers, (
        f"{terms} terms divided into {len(cut.parts)} pieces, not {workers} — "
        "the document is under the split floor for this worker count"
    )
    roots = [compiled.parse(part, cores=1) for part in cut.parts]
    leads = [
        parse_model(plan.lead_grammar, mark, compiled.product) for mark in cut.leads
    ]
    spines = [root.children()[0] for root in roots]
    # The narrowing sits here, once, at the boundary where a parse hands back
    # the protocol's base and this file needs the model. Everything below
    # reads plain fields.
    assert all(isinstance(one, GrammarModel) for one in (*spines, *leads))
    kept = cast(list[GrammarModel], spines)
    return FoldedCase(kept, tuple(cast(list[GrammarModel], leads)), type(kept[0]), text)


def test_left_slot_is_the_recursive_fields_own_index() -> None:
    """The licence wants a FIELD index, not a rank among bound children.

    They coincide whenever every item captures, which is every shape the
    roster offers — so a reading that returned the bound rank would pass every
    end-to-end case here and be wrong on the first class with an unbound
    field. Both are asserted, and their agreement is asserted as a FACT about
    this class rather than assumed of every class.
    """
    step = folded_pieces(1200, 2).step
    at = left_slot(step)
    bound = sorted(step.bound_fields().items())
    assert at == step._fields.index(bound[0][1][0])
    assert step._fields[at] == "expr"


def test_the_licence_build_is_the_checked_build() -> None:
    """The fold's fast construction produces what ``rebuild`` produces.

    The join skips the validating constructor because the values it holds are
    already-parsed models — the same reason the parse itself skips it. This is
    what says the two agree, since nothing else would notice if they stopped.
    """
    case = folded_pieces(1200, 2)
    spines, step = case.spines, case.step
    node = spines[0]
    at = left_slot(step)
    kids = list(node.children())
    construct, _defaults, _fields = step.fast_construct()
    values = list(node)
    values[at] = kids[0]
    assert construct(values).dump() == node.rebuild(kids).dump()


def test_the_join_rebuilds_the_removed_mark() -> None:
    """The stitched spine round-trips — so no separator went missing.

    The cut CONSUMES its mark, so the join is the only thing that can put it
    back. Without that the model is one level short PER CUT, which reads as a
    plain off-by-one at a single width and is why the widths vary here.
    """
    for workers in (2, 3, 4, 5):
        case = folded_pieces(1200, workers)
        merged = fold_spines(list(case.spines), case.leads, case.step)
        assert merged is not None
        assert merged.to_text() + "\n" == case.text


def test_a_lead_count_that_does_not_match_the_pieces_declines() -> None:
    """One mark per join, or the fold has no idea what joins what."""
    case = folded_pieces(1200, 4)
    assert fold_spines(list(case.spines), case.leads[:-1], case.step) is None
