"""Focused model-plan tests for direct and configured recurrences."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.ir import Bound, IrAst
from lexic.model import GrammarModel
from lexic.parsing import ModelExecutable, parse_model
from lexic.parsing.parallel.plan.envelope import Envelope, envelope_plans, unit_witness
from lexic.parsing.parallel.stitch.model import (
    envelope_tails,
    is_run,
    model_at,
    overlaid,
    sole_routes,
    stitch_envelope,
)
from tests.unit.lexic.parsing.parallel.envelope_fixtures import ENVELOPE_SOURCE
from tests.unit.lexic.parsing.parallel.stitch.support import (
    assert_outer_split,
    split_case,
)


def _envelope_case(cache_key: str) -> tuple[IrAst, ModelExecutable, Envelope, IrAst]:
    """The compiled fixture, its envelope shape, and the reparse target."""
    compiled = compile_text(ENVELOPE_SOURCE, cache_key=cache_key)
    grammar, binding = compiled.codegen_grammar, compiled.product
    plan = _first(envelope_plans(grammar, "root"))
    assert plan is not None
    target = IrAst(grammar.rules, plan.shape.item)
    return grammar, binding, plan.shape, target


def _rebuilt_lead(
    grammar: IrAst,
    binding: ModelExecutable,
    shape: Envelope,
    target: IrAst,
    tail_text: str,
) -> GrammarModel:
    """The reparsed separator span a real cut hands to the join — the
    separator itself is empty in every case exercised here, so only the
    piece's own moved tail and the witness feed the reparse."""
    witness = unit_witness(grammar, shape.unit) or ""
    return parse_model(target, tail_text + witness, binding)


def _moved_tails(
    chunks: list[GrammarModel], shape: Envelope, binding: ModelExecutable
) -> tuple[list[str], list[GrammarModel]]:
    """Non-``None`` :func:`envelope_tails`, for callers that already expect it
    to succeed over this fixture's shape."""
    moved = envelope_tails(chunks, shape, binding)
    assert moved is not None
    return moved


def _first(found):
    """The first certified plan, or ``None`` — the shape these tests pin.

    ``envelope_plans`` returns one plan per PROVABLE mark so the
    orchestrator can pick per document; a test naming one grammar wants
    the leading candidate.
    """
    return found[0] if found else None


def test_a_trailing_comment_absorbed_by_a_pieces_own_tail_reparses_and_stitches() -> (
    None
):
    """A piece ending ``rule ; note\\n`` keeps that comment as its OWN tail
    field when parsed alone; :func:`envelope_tails` moves it back out to text,
    and the reparsed separator, joined with the next piece's real head,
    equals the document parsed whole — byte for byte."""
    grammar, binding, shape, target = _envelope_case("test-model-envelope-comment")
    whole = "ua = a; note\nub = b"
    piece1 = parse_model(grammar, "ua = a; note\n", binding)
    piece2 = parse_model(grammar, "ub = b", binding)

    texts, trimmed = _moved_tails([piece1, piece2], shape, binding)
    assert texts == ["; note\n"]

    lead = _rebuilt_lead(grammar, binding, shape, target, texts[0])
    stitched = stitch_envelope(trimmed, [lead], shape, binding)

    assert stitched is not None
    assert stitched == parse_model(grammar, whole, binding)
    assert stitched.to_text() == whole


def test_a_moved_bare_newline_supplies_the_next_items_required_line_ending() -> None:
    """A piece ending with nothing but its own trailing blank line still
    moves that ``\\n`` to the separator, which is what lets ``cont``'s
    mandatory ``cnl`` item resolve once the witness is appended."""
    grammar, binding, shape, target = _envelope_case("test-model-envelope-blank")
    whole = "ua = a\nub = b"
    piece1 = parse_model(grammar, "ua = a\n", binding)
    piece2 = parse_model(grammar, "ub = b", binding)

    texts, trimmed = _moved_tails([piece1, piece2], shape, binding)
    assert texts == ["\n"]

    lead = _rebuilt_lead(grammar, binding, shape, target, texts[0])
    stitched = stitch_envelope(trimmed, [lead], shape, binding)

    assert stitched is not None
    assert stitched == parse_model(grammar, whole, binding)
    assert stitched.to_text() == whole


def test_a_non_final_piece_carrying_a_head_field_declines_the_envelope_stitch() -> None:
    """The head belongs to the document's opening edge alone: a later piece
    that parsed one when read independently has read a boundary differently
    than the split did, and the stitch must refuse rather than silently keep
    only the first piece's head."""
    grammar, binding, shape, target = _envelope_case("test-model-envelope-head")
    piece1 = parse_model(grammar, "ua = a\n", binding)
    piece2 = parse_model(grammar, "; lead\nub = b", binding)

    texts, trimmed = _moved_tails([piece1, piece2], shape, binding)
    lead = _rebuilt_lead(grammar, binding, shape, target, texts[0])

    assert stitch_envelope(trimmed, [lead], shape, binding) is None


def test_direct_trailing_boundary_whitespace_round_trips_after_split() -> None:
    """Direct recurrence reconstruction retains whitespace before its closer."""
    source = (
        "root ::= group\n"
        "group ::= open node more* close\n"
        'open ::= "(" ws\n'
        'close ::= ws ")"\n'
        'more ::= "," node\n'
        "node ::= [a-z]+\n"
        'ws ::= " "*\n'
    )

    text = "(" + ",".join("a" * 20 for _ in range(900)) + "   )"
    assert_outer_split(split_case(source, text, "group", 4), text)


# ── the run container: exactly a plain tuple, on every stitch route ───────

SEPARATED = (
    "root ::= entry more*\nmore ::= nl entry\n"
    'entry ::= name eq name\nname ::= [a-z0-9_]+\neq ::= "="\nnl ::= "\\n"\n'
)
"""A separated repetition — the route :func:`_stitch_separated` rebuilds."""


def _separated_doc(rows: int) -> str:
    """A SEPARATED document of ``rows`` entries."""
    return "\n".join(f"field_{'n' * (n % 12 + 4)}_{n}=value_{n}" for n in range(rows))


def test_the_separated_stitch_builds_the_run_as_a_plain_tuple() -> None:
    """``is_run`` is a class test, not an ``isinstance``: every record and
    every ``IrTuple`` is a tuple subclass and none of them is a run.

    A stitched ``IrTuple`` compared equal, rendered the same text and walked to
    the same structure as a sequential parse — and then answered "not a
    repetition" to the one question the stitch itself asks of a bound field.
    """
    text = _separated_doc(700)
    compiled = compile_text(SEPARATED, cache_key="stitch-separated-run")
    sequential = parse_model(compiled.codegen_grammar, text, compiled.product)
    _plan, _seq, parallel = split_case(SEPARATED, text, "root", 8)
    assert parallel is not None, "the fixture must split"

    run = tuple(parallel)[1]
    assert run.__class__ is tuple, f"the run is a {type(run).__name__}"
    assert is_run(run)
    assert run.__class__ is tuple(sequential)[1].__class__
    assert parallel.to_text() == sequential.to_text() == text


# ── sole_routes, model_at, overlaid ───────────────────────────────────────

LISTS = (
    "root ::= list\n"
    'list ::= "[" items "]"\n'
    "items ::= item more*\n"
    'more ::= "," item\n'
    "item ::= list | word\n"
    "word ::= [a-z]+\n"
)


def _lists(text: str) -> GrammarModel:
    """``text`` parsed under :data:`LISTS`."""
    model = compile_text(LISTS, cache_key="sole-routes").parse(text, cores=1)
    assert isinstance(model, GrammarModel)
    return model


def _inner(text: str) -> GrammarModel:
    """The first nested list's model in ``text``, found by walking."""
    stack: list[Bound] = [_lists(text)]
    root_list = None
    while stack:
        node = stack.pop()
        if isinstance(node, GrammarModel):
            if type(node).__name__ == "List":
                if root_list is not None:
                    return node
                root_list = node
            stack.extend(reversed(node.children()))
        elif is_run(node):
            stack.extend(reversed(node))
    raise AssertionError("no nested list")


def test_every_needle_gets_its_own_route_from_one_walk():
    """Two different needles, each once: both routed, and each route reaches
    a node equal to its needle."""
    root = _lists("[a,[b],c,[d]]")
    needles = [_inner("[x,[b]]"), _inner("[x,[d]]")]
    routes = sole_routes(root, needles)
    assert all(route is not None for route in routes)
    reached = [model_at(root, route) for route in routes if route is not None]
    assert reached == needles


def test_a_needle_found_twice_or_never_has_no_route():
    """A collision is refused, and so is an absence — each needle for itself."""
    root = _lists("[a,[b],c,[b],[e]]")
    twice, never, once = _inner("[x,[b]]"), _inner("[x,[q]]"), _inner("[x,[e]]")
    routes = sole_routes(root, [twice, never, once])
    assert routes[0] is None
    assert routes[1] is None
    assert routes[2] is not None and model_at(root, routes[2]) == once


def test_the_root_itself_is_never_a_route():
    """A needle equal to the whole model has no non-root route."""
    root = _lists("[a]")
    assert sole_routes(root, [root]) == [None]


def test_overlaid_replaces_only_the_named_slots_and_keeps_the_class():
    """The node's other slots stay as they were; its class is its own."""
    node = _inner("[x,[b,c]]")
    other = _inner("[x,[d,e]]")
    slots = dict(enumerate(other.children()))
    rebuilt = overlaid(node, slots)
    assert rebuilt == other
    assert type(rebuilt) is type(node)
    assert overlaid(node, {len(node.children()): None}) is None
