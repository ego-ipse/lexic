"""A reader shown an ambiguous key sees one carving per arm — that arm's own.

Families naming ONE arm over different spans are that arm carved two ways, and
the split rule has already said which carving the arm has. Offering a consumer
the other one offers a derivation this engine would never produce, and the
ambiguity walk — which visited every family at a point — could report a
difference from it and refuse a span whose real choice between ARMS was never
reached.

The grammar below is the smallest shape that makes it visible. ``u`` ends at two
columns, so the key after ``t`` collects families with different predecessor
ends; ``t`` has two arms that both derive ``"aa"``, so the same key also
collects families naming different arms. On ``"aaaa"`` one of those carvings is
``u="a", t="aaa"`` — which the split rule rejects, because ``doc ::= u t tail``
gives the first slot as much as it can take and that makes ``u="aa"``. Refusing
the span over it was refusing over a reading nobody would be handed.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.fasttree import ParseTree
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.splits import (
    dominant,
    is_arm_choice,
    leftmost_chain,
    spec_for,
)
from lexic.parsing.products import _model_product, earley_model, parse_model

MIXED = 'doc ::= u t tail\nu ::= "a" | "aa"\nt ::= "a"+ | "aa"\ntail ::= "a"*\n'
"""A grammar whose chart holds keys that are BOTH an arm choice and a split."""

THREE_SLOTS = 'doc ::= a b c\na ::= "xx" "x"?\nb ::= "x" "xx"?\nc ::= "x"+\n'
"""Two slots trading against each other: left-to-right and right-to-left differ."""

SPLIT_HEAVY = 'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t?\nt ::= ";"\n'
"""A shape whose keys pack many carvings of one arm."""


def _built(source: str, key: str):
    """Compile ``source``; return its compiled grammar and model product."""
    compiled = compile_text(source, cache_key=key)
    return compiled, _model_product(compiled.codegen_grammar, compiled.product)


def _answer(source: str, key: str, text: str, resolve=None) -> str:
    """``text``'s model through the Earley model route, or ``"REFUSED"``."""
    compiled, product = _built(source, key)
    try:
        return repr(
            earley_model(
                product.instance_grammar,
                text,
                compiled.product,
                product.tables,
                resolve,
            )
        )
    except UnsupportedConstructError:
        return "REFUSED"


def test_a_rejected_carving_no_longer_makes_a_span_ambiguous() -> None:
    """The defect, pinned as the value it produces rather than as a claim.

    ``"aaaa"`` refused. The two readings compared were ``u="aa", t="aa"`` and
    ``u="a", t="aaa"``, and the second is not a reading this engine produces.
    With one carving per arm what remains to compare is the arm choice, and
    both arms of ``t`` mean ``T('aa')`` here: one meaning, so one answer.
    """
    assert _answer(MIXED, "canonical-mixed", "aaaa") == (
        "Doc(U('aa'), T('aa'), Tail(''))"
    )


def test_a_real_arm_choice_still_refuses() -> None:
    """The fix may not be "refuse less" — it must refuse the same spans.

    ``"aaa"`` has a genuine choice: ``u`` can take either of its arms and the
    rest still derives, with different values. Nothing about lengths settles a
    choice between arms, so the span still refuses.
    """
    assert _answer(MIXED, "canonical-mixed", "aaa") == "REFUSED"


def test_the_resolver_is_offered_exactly_one_pair_on_that_span() -> None:
    """And what it is offered are two readings covering the same text.

    One pair, not two: the carvings of a single arm have been settled by the
    rule that owns them, so what is left to ask about is the arm.
    """
    seen: list[tuple[ParseTree, ParseTree]] = []

    def spy(first: ParseTree, other: ParseTree) -> ParseTree:
        seen.append((first, other))
        return first

    got = _answer(MIXED, "canonical-mixed", "aaa", spy)

    assert len(seen) == 1, f"expected one pair, got {len(seen)}"
    first, other = seen[0]
    assert first != other
    assert _spelling(first) == _spelling(other) == "aaa"
    assert got == "Doc(U('a'), T('aa'), Tail(''))"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("aaaaa", "Doc(U('aa'), T('aaa'), Tail(''))"),
        ("aaaaaa", "Doc(U('aa'), T('aaaa'), Tail(''))"),
    ],
)
def test_the_longer_spans_are_untouched(text: str, expected: str) -> None:
    """Derived by hand from the rule: ``u`` takes two, ``t`` keeps the rest."""
    assert _answer(MIXED, "canonical-mixed", text) == expected


def test_the_composed_entry_answers_the_same_way() -> None:
    """The route callers use, PDA first with Earley completion, not just the half."""
    compiled, _product = _built(MIXED, "canonical-mixed")
    model = parse_model(compiled.codegen_grammar, "aaaa", compiled.product)

    assert repr(model) == "Doc(U('aa'), T('aa'), Tail(''))"


def test_the_first_slot_still_takes_as_much_as_it_can() -> None:
    """The six-character pin: ``(3, 1, 2)``, not the right-to-left ``(2, 3, 1)``.

    Kept in this file because the canonical selection is a second reader of the
    same rule, and a selection that answered from the right would show up here
    first.
    """
    compiled = compile_text(THREE_SLOTS, cache_key="canonical-three")
    model = compiled.parse("xxxxxx", cores=1)

    assert tuple(len(part.to_text()) for part in model) == (3, 1, 2)
    assert model.to_text() == "xxxxxx"


@pytest.mark.parametrize(
    ("source", "key", "documents"),
    [
        (MIXED, "canonical-mixed", ["a" * n for n in range(3, 12)]),
        (SPLIT_HEAVY, "canonical-heavy", ["ab;;" * n for n in (2, 4, 8, 16)]),
    ],
)
def test_the_primitive_answers_what_the_chain_reader_answers(
    source: str, key: str, documents: list[str]
) -> None:
    """One rule, two entry points, every packed key of a real forest.

    `dominant` decides between two families; `leftmost_chain` reads a whole
    chain. They are the same rule, so folding the first over a key's bucket
    must land on the family the second descends into — at EVERY key, not only
    the ones some parse happened to visit.

    This is the test a comparison that walked ``bucket[0]`` fails: these charts
    are full of multi-family predecessors, and a predecessor's first-recorded
    family is not the rule's answer there.
    """
    _compiled, product = _built(source, key)
    checked = 0
    for text in documents:
        kernel = Kernel(product.tables, text, True).run()
        checked += _agreeing_keys(kernel, product.tables)
    assert checked, "no packed key was compared — the test proves nothing"


def _agreeing_keys(kernel: Kernel, tables) -> int:
    """Assert the two entry points agree at every packed split key; count them."""
    links = kernel.family_reader()
    codes, bits = tables.codes, tables.packing.bits
    checked = 0
    for handle, bucket in links.items():
        if len(bucket) < 2 or is_arm_choice(bucket, bits, tables.code_choice):
            continue
        spec = spec_for(codes, bits, tables.code_choice, handle)
        chain = leftmost_chain(links, handle, spec, {})
        if chain is None:
            continue
        best = bucket[0]
        for rival in bucket[1:]:
            best = dominant(links, best, rival, spec)
        checked += 1
        # Compared by VALUE, not identity: a family IS its
        # ``(waiter, origin, child)`` triple — the same triple names the same
        # family however it was obtained — and a promoted key's families are
        # rebuilt per read rather than being one shared object.
        assert best == chain[-1], (
            f"at key {handle} the primitive keeps {best[:2]} where the chain "
            f"reader descends into {chain[-1][:2]}"
        )
    return checked


def _spelling(tree: ParseTree | str) -> str:
    """Every leaf of ``tree``, concatenated — the text it derives."""
    if isinstance(tree, str):
        return str(tree)
    return "".join(_spelling(kid) for kid in tree[1])
