"""Tests for compile/binding.py — the per-rule binding view.

The actual test bodies live in :mod:`tests.unit.lexic.compile.pipeline.binding_cases`, bound here to
:mod:`lexic.compile.pipeline.binding`.
"""

from __future__ import annotations

import ast as pyast

import pytest

from lexic.compile import (
    compile_from_path,
    compile_text,
    compute_binding,
    export_source,
)
from lexic.compile.pipeline import binding
from tests.paths import GBNF_GRAMMARS, GROUND_TRUTH
from tests.unit.lexic.compile.pipeline.binding_cases import make_binding_tests

globals().update(make_binding_tests(binding))


# ── the declaration-order rule, over every generated class ────────────────


def _declared(source: str) -> dict[str, tuple[list[str], set[str]]]:
    """Per class in an exported module: its field order and which are defaulted.

    Read off the EXPORT rather than off ``cls._fields`` / ``cls._field_defaults``:
    the declaration order is a claim about what a record's fields look like where
    someone reads them, the export is that surface, and it needs no reach into a
    protected member and no re-implementation of the optionality predicate.
    """
    out: dict[str, tuple[list[str], set[str]]] = {}
    for node in pyast.parse(source).body:
        if not isinstance(node, pyast.ClassDef):
            continue
        order: list[str] = []
        defaulted: set[str] = set()
        for stmt in node.body:
            if not isinstance(stmt, pyast.AnnAssign) or not isinstance(
                stmt.target, pyast.Name
            ):
                continue
            name = stmt.target.id
            if name.startswith("__"):  # the inline_tables ClassVars
                continue
            order.append(name)
            if stmt.value is not None:
                defaulted.add(name)
        out[node.name] = (order, defaulted)
    return out


@pytest.mark.parametrize("stem", GBNF_GRAMMARS)
def test_declaration_order_is_required_first_on_every_generated_class(
    stem: str,
) -> None:
    """``bind_fields``' documented order, over every rule of every grammar.

    Two hand-built arms pin the rule in ``binding_cases``; this pins it on the
    whole corpus, and against the item slots the binding view reports rather
    than against the order the same function produced.
    """
    compiled = compile_from_path(GROUND_TRUTH / stem)
    declared = _declared(export_source(compiled, stem=stem))
    seen = 0
    for bind in compute_binding(compiled.codegen_grammar):
        # A `value_str` class declares an implicit single `value` field that no
        # IrBind names — nothing to order, and not what the rule is about.
        if not bind.fields:
            continue
        order, defaulted = declared.get(bind.class_name, ([], set()))
        if not order:
            continue
        seen += 1
        slot = {name: ibind.item for name, ibind in bind.fields.items()}
        by_item = sorted(order, key=slot.__getitem__)
        want = [f for f in by_item if f not in defaulted]
        want += [f for f in by_item if f in defaulted]
        assert order == want, f"{stem}/{bind.class_name}"
    assert seen


def test_declaration_order_really_does_diverge_from_item_order() -> None:
    """The docstring's claim needs a witness, or it is describing nothing.

    An optional item before a required one is where the two orders disagree,
    and it is ordinary rather than exotic — 32 of the corpus's 162
    field-carrying classes are in that case.
    """
    compiled = compile_text(
        'root ::= ws? value\nws ::= " "\nvalue ::= [a-z]+\n',
        cache_key="binding-order-witness",
    )
    order, defaulted = _declared(export_source(compiled, stem="witness"))["Root"]
    fields = next(
        b.fields
        for b in compute_binding(compiled.codegen_grammar)
        if b.class_name == "Root"
    )
    slot = {name: ibind.item for name, ibind in fields.items()}
    assert sorted(order, key=slot.__getitem__) == ["ws", "value"]
    assert order == ["value", "ws"]
    assert defaulted == {"ws"}
