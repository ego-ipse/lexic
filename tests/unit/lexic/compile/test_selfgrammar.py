"""Tests for compile/selfgrammar.py — the generated-module self-grammar.

``module_grammar()`` is the statement skeleton merged with the notation
rules; ``parse_module(text)`` folds an exported twin module to an
:class:`MModule`; ``verify_module(compiled, text)`` cross-checks that model
against the SAME binding-view functions the exporter rendered from (L2) —
so a mismatch means the FILE drifted, not the renderer.
"""

from __future__ import annotations

import pytest

from lexic.compile import (
    compile_from_path,
    compile_text,
    export_source,
    parse_module,
    verify_module,
)
from lexic.compile.notation import NOTATION_GRAMMAR
from lexic.compile.selfgrammar import MClass, MField, MModule, module_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrNoneType
from lexic.ir.nodes import IrAst
from tests.paths import GROUND_TRUTH

LIST_GRAMMAR = GROUND_TRUTH / "list.gbnf"
JSON_WS_GRAMMAR = GROUND_TRUTH / "json_ws.gbnf"

# ── module_grammar() shape pins ─────────────────────────────────────────


def test_module_grammar_starts_at_m_module():
    """The merged grammar's start rule is the statement-skeleton root."""
    assert module_grammar().start == "m-module"


def test_module_grammar_merges_m_rules_with_notation_rules_minus_start():
    """The rule set is the m-prefixed statement rules plus every notation
    rule EXCEPT notation's own "start" (the module skeleton supplies its
    own top-level rule instead)."""
    grammar = module_grammar()
    names = [str(rule.name) for rule in grammar.rules]
    m_names = {n for n in names if n.startswith("m-")}
    non_m_names = {n for n in names if not n.startswith("m-")}
    notation_names = {
        str(rule.name) for rule in NOTATION_GRAMMAR.rules if str(rule.name) != "start"
    }
    assert non_m_names == notation_names
    assert "start" not in names
    assert m_names  # the statement skeleton contributed rules too


def test_module_grammar_has_no_duplicate_rule_names():
    """m-rule names and notation rule names never collide (concatenation,
    not merge-by-name)."""
    grammar = module_grammar()
    names = [str(rule.name) for rule in grammar.rules]
    assert len(names) == len(set(names))


def test_m_gap_is_non_semantic():
    """m-gap (blank-line runs) is structural noise, not semantic content."""
    grammar = module_grammar()
    gap = next(r for r in grammar.rules if str(r.name) == "m-gap")
    assert gap.semantic is False


# ── parse_module on a real export (bind-mode) ───────────────────────────


def test_parse_module_on_a_bind_mode_export():
    """parse_module reconstructs doc/imports/classes/grammar/has_bind for a
    real compiled grammar's default (bind-mode) export."""
    compiled = compile_from_path(LIST_GRAMMAR)
    source = export_source(compiled)
    module = parse_module(source)

    assert isinstance(module, MModule)
    assert "Generated twin module for grammar 'list'" in module.doc
    assert not module.typing_names
    assert "IrAst" in module.ir_names
    assert isinstance(module.grammar, IrAst)
    assert module.grammar == compiled.grammar
    assert module.has_bind is True
    assert len(module.classes) == 2


def test_parse_module_class_fields_and_bases():
    """Each MClass carries its name, bases, docstring and MField list."""
    compiled = compile_from_path(LIST_GRAMMAR)
    module = parse_module(export_source(compiled))
    by_name = {c.name: c for c in module.classes}

    root = by_name["Root"]
    assert isinstance(root, MClass)
    assert root.bases == ("GrammarModel",)
    assert "root ::= item+" in root.doc
    assert root.fields == (MField("item", "list[Item]"),)

    item = by_name["Item"]
    assert item.bases == ("GrammarModel",)
    assert item.fields == (MField("value", "str"),)


def test_parse_module_bind_mode_has_no_inline_tables():
    """A bind-mode export's classes carry no inline __grammar__/__binds__."""
    compiled = compile_from_path(LIST_GRAMMAR)
    module = parse_module(export_source(compiled))
    for mclass in module.classes:
        assert isinstance(mclass.inline_grammar, IrNoneType)
        assert not mclass.inline_binds


# ── parse_module on inline_tables=True ──────────────────────────────────


def test_parse_module_on_an_inline_tables_export():
    """An inline_tables export has no bind_module call and no bind-only
    typing import; ClassVar/IrBind names appear instead."""
    compiled = compile_from_path(LIST_GRAMMAR)
    module = parse_module(export_source(compiled, inline_tables=True))
    assert module.has_bind is False
    assert "ClassVar" in module.typing_names


def test_parse_module_inline_tables_populates_inline_grammar_and_binds():
    """Each class's inline __grammar__ is its codegen IrRule; __binds__
    entries carry (slot, field name, IrBind)."""
    compiled = compile_from_path(LIST_GRAMMAR)
    module = parse_module(export_source(compiled, inline_tables=True))
    by_name = {c.name: c for c in module.classes}
    root = by_name["Root"]

    assert root.inline_grammar == compiled.classes["Root"].__grammar__
    assert len(root.inline_binds) == 1
    slot, field_name, bind = root.inline_binds[0]
    assert (slot, field_name) == (0, "item")
    assert bind == compiled.classes["Root"].__binds__[0][1]

    # A value_str class (no bound fields) carries an inline grammar but no binds.
    item = by_name["Item"]
    assert item.inline_grammar == compiled.classes["Item"].__grammar__
    assert not item.inline_binds


# ── parse_module refuses non-module text ────────────────────────────────


def test_parse_module_refuses_garbage_text():
    """Text that isn't a canonical exported module refuses to parse."""
    with pytest.raises(UnsupportedConstructError):
        parse_module("this is not a generated module\n")


def test_parse_module_refuses_empty_text():
    """An empty string is not a valid module either."""
    with pytest.raises(UnsupportedConstructError):
        parse_module("")


# ── verify_module: the L2 binding cross-check ───────────────────────────


@pytest.mark.parametrize("inline_tables", [False, True])
def test_verify_module_passes_for_a_real_export(inline_tables: bool):
    """verify_module accepts a genuine export in both table modes and
    returns the same model parse_module would."""
    compiled = compile_from_path(JSON_WS_GRAMMAR)
    source = export_source(compiled, inline_tables=inline_tables)
    verified = verify_module(compiled, source)
    assert verified == parse_module(source)


def test_verify_module_refuses_a_mismatched_compiled_grammar():
    """A module claiming to be one grammar's twin, checked against a
    DIFFERENT compiled grammar, refuses on the GRAMMAR mismatch."""
    list_compiled = compile_from_path(LIST_GRAMMAR)
    other_source = export_source(compile_from_path(JSON_WS_GRAMMAR))
    with pytest.raises(UnsupportedConstructError, match="GRAMMAR"):
        verify_module(list_compiled, other_source)


# ── the tamper matrix — each seeded drift refuses ───────────────────────


@pytest.fixture(name="tamper_fixture")
def tamper_fixture_source():
    """A compiled grammar + its bind-mode export, source for tampering."""
    compiled = compile_from_path(JSON_WS_GRAMMAR)
    source = export_source(compiled)
    assert "class Object(Value):" in source
    return compiled, source


def test_tamper_renamed_field_refuses(tamper_fixture):
    """Renaming a bound field's name diverges from the binding view."""
    compiled, source = tamper_fixture
    tampered = source.replace(
        "    ws: Ws | None = None\n    object_item2",
        "    ws_renamed: Ws | None = None\n    object_item2",
        1,
    )
    with pytest.raises(UnsupportedConstructError, match="fields"):
        verify_module(compiled, tampered)


def test_tamper_wrong_annotation_text_refuses(tamper_fixture):
    """A field's rendered type text no longer matches the binding's type."""
    compiled, source = tamper_fixture
    tampered = source.replace(
        "    ws: Ws | None = None\n    object_item2",
        "    ws: str | None = None\n    object_item2",
        1,
    )
    with pytest.raises(UnsupportedConstructError, match="fields"):
        verify_module(compiled, tampered)


def test_tamper_dropped_default_refuses(tamper_fixture):
    """Dropping an optional field's `` = None`` default changes has_default."""
    compiled, source = tamper_fixture
    tampered = source.replace(
        "    ws: Ws | None = None\n    object_item2",
        "    ws: Ws | None\n    object_item2",
        1,
    )
    with pytest.raises(UnsupportedConstructError, match="fields"):
        verify_module(compiled, tampered)


def test_tamper_reordered_fields_refuses(tamper_fixture):
    """Field declaration order must match the binding's field order exactly."""
    compiled, source = tamper_fixture
    old_block = (
        "    ws: Ws | None = None\n"
        "    object_item2: ObjectItem2 | None = None\n"
        "    ws2: Ws | None = None\n"
    )
    new_block = (
        "    object_item2: ObjectItem2 | None = None\n"
        "    ws: Ws | None = None\n"
        "    ws2: Ws | None = None\n"
    )
    assert old_block in source
    tampered = source.replace(old_block, new_block, 1)
    with pytest.raises(UnsupportedConstructError, match="fields"):
        verify_module(compiled, tampered)


def test_tamper_docstring_drift_refuses(tamper_fixture):
    """A class docstring that no longer matches the rule's rendered grammar
    text refuses, even collapsing the exporter's line-wrap."""
    compiled, source = tamper_fixture
    tampered = source.replace(
        '"""``root ::= object``"""', '"""``root ::= objectx``"""', 1
    )
    with pytest.raises(UnsupportedConstructError, match="docstring drift"):
        verify_module(compiled, tampered)


def test_tamper_edited_grammar_expression_refuses(tamper_fixture):
    """An edited GRAMMAR literal no longer equals the compiled canonical AST."""
    compiled, source = tamper_fixture
    tampered = source.replace('IrLiteral("{")', 'IrLiteral("[")', 1)
    with pytest.raises(UnsupportedConstructError, match="GRAMMAR"):
        verify_module(compiled, tampered)


def test_tamper_swapped_base_class_refuses(tamper_fixture):
    """A class whose base no longer matches the binding's parent chain
    refuses on the bases check."""
    compiled, source = tamper_fixture
    tampered = source.replace("class Object(Value):", "class Object(GrammarModel):", 1)
    with pytest.raises(UnsupportedConstructError, match="bases"):
        verify_module(compiled, tampered)


def test_tamper_inline_tables_in_a_bind_mode_module_refuses():
    """A bind-mode module whose class carries inline __grammar__/__binds__
    (i.e. claims table-inline shape while GRAMMAR still ends in
    bind_module) refuses on the inline-mismatch check."""
    compiled = compile_from_path(LIST_GRAMMAR)
    bind_source = export_source(compiled)
    inline_source = export_source(compiled, inline_tables=True)
    # Splice the inline Root class body into the bind-mode module, keeping
    # the bind-mode module's own trailing GRAMMAR + bind_module() tail —
    # an internally-inconsistent module (inline class, but still bind-mode).
    inline_root_start = inline_source.index("class Root(GrammarModel):")
    inline_root_end = inline_source.index("class Item(GrammarModel):")
    bind_root_start = bind_source.index("class Root(GrammarModel):")
    bind_root_end = bind_source.index("class Item(GrammarModel):")
    tampered = (
        bind_source[:bind_root_start]
        + inline_source[inline_root_start:inline_root_end]
        + bind_source[bind_root_end:]
    )
    with pytest.raises(UnsupportedConstructError, match="inline tables"):
        verify_module(compiled, tampered)


# ── the module model record spine ───────────────────────────────────────


def test_mfield_is_indexable_and_field_by_name():
    """MField is an IrNamedTuple record: index and attribute agree."""
    field = MField("x", "str", True)
    assert field[0] == field.name == "x"
    assert field[1] == field.type_text == "str"
    assert field[2] == field.has_default
    assert field.has_default is True


def test_mfield_has_default_defaults_to_false():
    """MField's has_default defaults False when not supplied."""
    assert MField("x", "str").has_default is False


def test_mclass_defaults():
    """MClass defaults: no fields, no inline tables."""
    mclass = MClass("X", (), "doc")
    assert not mclass.fields
    assert mclass.inline_grammar is IrNone
    assert not mclass.inline_binds


def test_mmodule_defaults():
    """MModule defaults: empty names/classes, no grammar, no bind."""
    module = MModule("doc")
    assert not module.typing_names
    assert not module.ir_names
    assert not module.classes
    assert module.grammar is IrNone
    assert module.has_bind is False


def test_mmodule_is_indexable():
    """MModule is an IrNamedTuple record: index and attribute agree."""
    module = MModule("doc", ("ClassVar",))
    assert module[0] == module.doc == "doc"
    assert module[1] == module.typing_names == ("ClassVar",)


def test_value_str_class_multi_arm_literal_type_round_trips():
    """A multi-arm pure-literal value_str rule's Literal[...] annotation
    survives the m-type-arg string-token grammar unchanged.

    Two rules (not one) so the ``from lexic.ir import (...)`` block renders
    in its long parenthesized form — see
    ``test_short_single_line_ir_import_fails_to_parse`` below for why a
    short single-line import can't be used here yet.
    """
    compiled = compile_text(
        'root ::= mode "-" [0-9]+\nmode ::= "add" | "sub" | "mul"\n'
    )
    source = export_source(compiled)
    module = parse_module(source)
    by_name = {c.name: c for c in module.classes}
    assert by_name["Mode"].fields == (MField("value", "Literal['add', 'sub', 'mul']"),)
    verify_module(compiled, source)


def test_short_single_line_ir_import_parses_and_verifies():
    """A minimal grammar's export uses the SHORT single-line ir-import form
    — the m-import-tail arm split (paren | flat sibling rules) parses it."""
    compiled = compile_text('root ::= "x"\n')
    source = export_source(compiled)
    assert (
        "from lexic.ir import IrAlternation" in source
    )  # the short form, unparenthesized
    module = parse_module(source)
    assert "IrAlternation" in module.ir_names
    verify_module(compiled, source)
