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

from lexic.compile import Directives, compile_from_path, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel.plan.routed import routed_plan
from lexic.parsing.parallel.stitch.interior import interior_route, stitch_interior
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
    """``at`` (the arm's own item index) and ``run`` (the unit's item index
    inside the interior rule) resolve to real field slots on both models."""
    compiled = compile_text(ROUTED_GRAMMAR)
    grammar, binding = compiled.codegen_grammar, compiled.product
    plan = routed_plan(grammar)
    assert plan is not None

    route = interior_route(binding, str(grammar.start), plan.at, plan.rule, plan.run)

    assert route is not None
    slot, child = route
    assert isinstance(slot, int)
    assert isinstance(child, int)


def test_interior_route_declines_a_container_or_rule_the_fold_does_not_know():
    """A shape surprise — a rule name the fold has no configuration for —
    declines rather than guessing a slot."""
    compiled = compile_text(ROUTED_GRAMMAR)
    binding = compiled.product

    assert interior_route(binding, "no-such-rule", 0, "block", 1) is None
    assert interior_route(binding, "start", 0, "no-such-rule", 1) is None


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
    route = interior_route(binding, str(grammar.start), plan.at, plan.rule, plan.run)
    assert route is not None

    stitched = stitch_interior(shell, pieces, route)
    sequential = parse_model(grammar, text, binding)

    assert stitched is not None
    assert stitched == sequential
    assert stitched.to_text() == text


def test_stitch_interior_declines_a_shape_surprise_at_the_slot():
    """A route slot that does not land on a model at all is a shape
    surprise, not a crash."""
    compiled = compile_text(ROUTED_GRAMMAR)
    grammar, binding = compiled.codegen_grammar, compiled.product
    text = routed_document(20)
    shell = parse_model(grammar, text, binding)

    assert stitch_interior(shell, [shell], (999, 0)) is None


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
