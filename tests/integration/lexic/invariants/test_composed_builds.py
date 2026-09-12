"""The composed builds produce exactly the records the plan walks produced.

`vstr_model` and the validated keyword build were per-call walks over a table
fixed at bake. Both are now composed once, at bake, and the only acceptable
evidence for that is identity: same class, same field values, same absences,
same intern key behaviour — over every grammar the ground truth and the bench
roster can supply, not over one witness.

Each expectation is re-derived HERE from the clone's own plan or capture
layout, in the shape the old code used, so the two arms cannot drift together.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    no_fast_construction,
    vstr_model,
)
from lexic.parsing.pda.compiler.program.lowering import validated_build, vstr_build
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    BUILD_VALUE_STR,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
)
from lexic.parsing.pda.compiler.program.specialize import clone_arms
from lexic.parsing.products import pda_tables
from tests.paths import ABNF_GRAMMARS, GBNF_GRAMMARS, GROUND_TRUTH

NEEDS_VOCABULARY = frozenset({"think.gbnf"})
"""Token-terminal grammars cannot concretize without a tokenizer fixture."""

SPANS = ("", "x", "hello", '"quoted"', "0123456789" * 4)
"""Extents to build each ``value_str`` shape over, empty included."""


def every_clone(node, seen: dict[int, FlatClone]) -> None:
    """Each clone of a compiled program, once, by identity."""
    if not isinstance(node, FlatClone) or id(node) in seen:
        return
    seen[id(node)] = node
    if node.mode == BUILD_DISPATCH:
        for _chars, _negated, target in node.selectors:
            every_clone(target, seen)
        every_clone(node.default, seen)
        return
    for arm in clone_arms(node):
        for payload in arm.payloads:
            every_clone(payload, seen)
    for entry in node.attempt[1] if node.attempt else ():
        every_clone(entry[-1], seen)


def clones_of(name: str) -> list[FlatClone]:
    """Every clone of one ground-truth grammar's compiled program."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    tables = pda_tables(compiled.codegen_grammar, compiled.product)
    seen: dict[int, FlatClone] = {}
    every_clone(tables.program.start, seen)
    return list(seen.values())


def vstr_by_plan(clone: FlatClone, span: str):
    """What the plan walk produced — restated here, independently.

    The form `vstr_model` carried before the build was composed: one pass over
    the plan per call, the matched extent in the M_VALUE slot and each other
    field's constant beside it.
    """
    fast = clone.fast
    if fast is not no_fast_construction and (plan := clone.plan):
        return fast(
            [span if mode == M_VALUE else default for mode, _i, _lo, default in plan]
        )
    return clone.ctor(**{clone.matched: span})


def kwargs_by_layout(fields, text, ends, sinks):
    """What the capture walk produced — restated here, independently.

    Absence is OMITTED rather than filled, and still represented in the key
    parts: that is the whole contract the composed form has to keep.
    """
    kwargs: dict = {}
    keys: list = []
    for item, mode, name, _lo in fields:
        if mode == M_TEXT:
            span = text[ends[item] : ends[item + 1]]
            kwargs[name] = span
            keys.append(span)
        elif mode == M_GTEXT:
            span = text[ends[item] : ends[item + 1]]
            if span:
                kwargs[name] = span
            keys.append(span or None)
        elif mode == M_MODEL:
            sub = sinks[item] if sinks else None
            if sub:
                kwargs[name] = sub[0]
            keys.append(id(sub[0]) if sub else None)
        elif mode == M_MODELS:
            sub = (sinks[item] if sinks else None) or []
            kwargs[name] = sub
            keys.append(tuple(id(model) for model in sub))
        elif mode == M_SPAN:
            extent = IrSpan(ends[item], ends[item + 1])
            kwargs[name] = extent
            keys.append(extent)
    return kwargs, tuple(keys)


# ── the value_str build ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name", [n for n in (*GBNF_GRAMMARS, *ABNF_GRAMMARS) if n not in NEEDS_VOCABULARY]
)
def test_every_value_str_clone_builds_what_its_plan_said(name: str) -> None:
    """Across the corpus, the composed build equals the plan walk exactly."""
    checked = 0
    for clone in clones_of(name):
        if clone.mode != BUILD_VALUE_STR:
            continue
        for span in SPANS:
            built = vstr_model(clone, span)
            want = vstr_by_plan(clone, span)
            assert built == want, (name, clone.name, span)
            assert type(built) is type(want), (name, clone.name, span)
            checked += 1
    assert checked, f"{name} has no value_str clone — the comparison proved nothing"


def test_the_corpus_really_carries_value_str_clones() -> None:
    """Several grammars supply them, so the sweep above is not vacuous."""
    bearing = {
        name: sum(1 for c in clones_of(name) if c.mode == BUILD_VALUE_STR)
        for name in ("json.gbnf", "json.abnf", "arithmetic.gbnf")
    }
    assert all(bearing.values()), bearing
    assert sum(bearing.values()) >= 10, bearing


def test_a_value_str_shape_with_a_field_beside_the_extent() -> None:
    """The multi-field form: constants fixed at bake, the extent placed."""
    seen: list = []
    plan = ((M_VALUE, 0, 0, None), (7, 0, 0, "DEF"))  # 7 == M_CONST
    build = vstr_build(seen.append, plan, lambda **kw: None, "value")
    build("42")
    assert seen == [["42", "DEF"]]


def test_a_value_str_shape_without_a_licence_builds_by_keyword() -> None:
    """No positional licence: the class's own checked constructor, by name."""
    build = vstr_build(None, (), lambda **kw: ("kw", kw), "value")
    assert build("42") == ("kw", {"value": "42"})


# ── the validated keyword build ───────────────────────────────────────────


def test_the_validated_build_matches_the_capture_walk() -> None:
    """Every capture mode, present and absent, against the restated walk."""
    fields = (
        (0, M_TEXT, "head", 1),
        (1, M_GTEXT, "opt", 0),
        (2, M_MODEL, "kid", 0),
        (3, M_MODELS, "kids", 0),
        (4, M_SPAN, "at", 1),
    )
    build = validated_build(fields)
    text = "abcdefgh"
    ends = [0, 2, 2, 4, 6, 8]
    for sinks in (None, [None, None, ["K"], ["A", "B"], None]):
        assert build(text, ends, sinks) == kwargs_by_layout(fields, text, ends, sinks)


def test_an_absent_capture_is_omitted_not_defaulted() -> None:
    """The contract the composed form must not quietly change."""
    build = validated_build(((0, M_GTEXT, "opt", 0), (1, M_MODEL, "kid", 0)))
    kwargs, keys = build("ab", [0, 0, 0], None)
    assert not kwargs, "an absent capture must not appear in the keywords"
    assert keys == (None, None), "absence must still be represented in the key"


def test_an_unknown_capture_mode_is_refused_at_bake() -> None:
    """A mode nothing can serve fails where the layout is read."""
    with pytest.raises(UnsupportedConstructError, match="unknown capture mode"):
        validated_build(((0, 99, "x", 1),))


def test_a_grammar_whose_class_declines_the_licence_parses_validated() -> None:
    """The validated path end to end, on a real parse.

    The roster's own grammars all grant the positional licence, so nothing in
    it reaches this path; a surface whose construction carries no licence is
    what exercises it, and the parse is the assertion.
    """
    compiled = compile_text('root ::= word+\nword ::= [a-z]+ " "?\n')
    model = compiled.parse("alpha beta gamma ")
    assert model.to_text() == "alpha beta gamma "
