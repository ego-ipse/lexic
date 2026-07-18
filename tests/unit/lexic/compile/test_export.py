"""Tests for ``lexic.compile.export`` — the importable ``.py`` twin renderer.

Ported from the reader-view exporter (260718 rework): assertions kept
wherever their target survived; the ruff/subprocess seam, ``_HEADER``,
``export_module_source`` and ``_binds_repr`` tests went with their symbols
(the formatter is the layout algebra now, the header is derived from the
emitted content, and the binds table renders only under ``inline_tables``).
"""

from __future__ import annotations

import ast

import pytest

from lexic.compile import compile_from_path, compile_text, export_module, export_source
from lexic.compile.binding import _RESERVED_CLASS_NAMES, RuleBinding, compute_binding
from lexic.compile.export import (
    _group_model_type,
    field_type,
    value_str_type,
)
from lexic.ir.base import IrNone
from lexic.ir.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.compile.compile_helpers import import_hermetic_module


def by_name(binding: list[RuleBinding]) -> dict[str, RuleBinding]:
    """A binding list keyed by rule name."""
    return {b.rule_name: b for b in binding}


# ── syntactic validity (also an always-on export gate) ────────────────────


@pytest.mark.parametrize("stem", ["list", "json", "arithmetic"])
@pytest.mark.parametrize("inline_tables", [False, True])
def test_export_source_is_valid_python_syntax(stem: str, inline_tables: bool):
    """The rendered module parses as Python in both table modes."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    source = export_source(cg, stem=stem, inline_tables=inline_tables)
    ast.parse(source)  # raises SyntaxError on failure


# ── fidelity spot-checks (>= 2 GT grammars) ───────────────────────────────


@pytest.mark.parametrize("stem", ["list", "json"])
def test_export_source_names_every_class_and_its_rule(stem: str):
    """Every binding's class name and rule name appear in the rendered source."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    binding = compute_binding(cg.codegen_grammar)
    source = export_source(cg, stem=stem)
    for bound in binding:
        assert f"class {bound.class_name}(" in source
        assert bound.rule_name in source


@pytest.mark.parametrize("stem", ["list", "json"])
def test_export_source_names_every_bound_field(stem: str):
    """Every sequence-kind rule's field names appear in its class body."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    binding = compute_binding(cg.codegen_grammar)
    source = export_source(cg, stem=stem)
    for bound in binding:
        for name in bound.fields:
            assert f"{name}:" in source, f"field {name!r} of {bound.class_name} missing"


def test_class_docstring_carries_the_rule_in_grammar_syntax():
    """Each class documents its own rule as flavour-rendered grammar text."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert '"""``word ::= [a-z]+``"""' in source


def test_fields_render_in_defaults_last_declaration_order():
    """Required fields precede ``= None`` optionals in the class body."""
    cg = compile_text("root ::= [0-9]? word\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    body = source.split("class Root(", 1)[1]
    assert body.index("word: Word") < body.index("digit: str | None = None")


# ── watch-out 4: never repr a reducer / noise map ─────────────────────────


@pytest.mark.parametrize("stem", ["list", "json", "arithmetic"])
def test_export_source_never_mentions_lambda_or_reducer(stem: str):
    """The rendered source carries pure grammar-AST notation — no action-algebra."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    source = export_source(cg, stem=stem)
    assert "IrLambda" not in source
    assert "Reducer" not in source


# ── field typing / optional defaults / union groups ───────────────────────


def test_optional_field_renders_a_none_default():
    """A field whose item can match zero times is typed Optional-like with = None."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert "digit: str | None = None" in source


def test_required_field_has_no_default():
    """A required (lo >= 1) field carries no ``= None`` default."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert "word: Word\n" in source


def test_group_model_union_type_lists_every_arm_class_once():
    """A model-mode alternation field renders as a ' | '-joined class union."""
    alt = IrAlternation(
        IrSequence(IrItem(IrRuleRef("a"))), IrSequence(IrItem(IrRuleRef("b")))
    )
    class_by_rule = {"a": "A", "b": "B"}
    assert _group_model_type(alt, class_by_rule) == "A | B"


def test_value_str_pure_literal_alternation_types_as_literal():
    """A multi-arm pure-literal alternation types its permitted-value set."""
    body = IrAlternation(
        IrSequence(IrItem(IrLiteral("true"))),
        IrSequence(IrItem(IrLiteral("false"))),
    )
    rule = IrRule("b", body)
    assert value_str_type(rule) == "Literal['true', 'false']"


def test_value_str_pattern_body_types_as_plain_str():
    """A single-item single-arm body is a pass-through, never Literal[...]."""
    rule = IrRule("digits", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    assert value_str_type(rule) == "str"


def test_field_type_models_mode_is_always_a_list_never_optional():
    """A models-mode field types as list[...] regardless of ``optional``: an
    absent repetition is an empty list, not a None default."""
    item = IrItem(IrRuleRef("a"), IrQuantifier(0, IrNone))
    result = field_type("models", item, {"a": "A"}, optional=True)
    assert result == "list[A]"


# ── table modes ───────────────────────────────────────────────────────────


def test_default_mode_has_no_dunders_and_ends_in_the_bind_call():
    """The pretty default: dunder-free classes + a module-end bind call."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe")
    assert "__grammar__" not in source
    assert "__binds__" not in source
    assert source.rstrip().endswith("bind_module(GRAMMAR, globals())")


def test_inline_tables_mode_writes_classvars_and_no_bind_call():
    """inline_tables: per-class ``__grammar__``/``__binds__``, no bind call."""
    cg = compile_text("root ::= word [0-9]*\nword ::= [a-z]+\n")
    source = export_source(cg, stem="probe", inline_tables=True)
    assert "__grammar__: ClassVar[IrRule] = " in source
    assert "__binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {" in source
    assert "bind_module" not in source
    for bound in compute_binding(cg.codegen_grammar):
        for name, ibind in bound.fields.items():
            tail = ", False" if not ibind.semantic else ""
            entry = (
                f'{ibind.item}: ("{name}", IrBind({ibind.item}, "{ibind.mode}"{tail})),'
            )
            assert entry in source  # double-quoted — the formatter-fixpoint form


# ── reserved-class-name drift pin ─────────────────────────────────────────


def header_bound_names(source: str) -> set[str]:
    """The module-scope names a rendered module's imports bind."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def test_reserved_class_names_cover_the_export_header():
    """Every class-shadowable name a real export's header binds is reserved.

    Union over the GT corpus in both table modes. ``annotations`` (the
    ``__future__`` flag) and ``bind_module`` are lowercase — never a
    PascalCase collision target.
    """
    shadowable: set[str] = set()
    for gt in sorted(GROUND_TRUTH.glob("*.gbnf")):
        cg = compile_from_path(gt)
        for inline_tables in (False, True):
            source = export_source(cg, inline_tables=inline_tables)
            shadowable |= header_bound_names(source)
    shadowable -= {name for name in shadowable if not name[:1].isupper()}
    assert shadowable <= _RESERVED_CLASS_NAMES


# ── public entry surface ──────────────────────────────────────────────────


def test_export_source_docstring_names_the_stem_and_flavour():
    """The rendered module docstring names the stem and the source flavour."""
    cg = compile_text('root ::= "hi"\n')
    source = export_source(cg, stem="my_stem")
    assert "'my_stem'" in source
    assert "(gbnf)" in source


def test_export_source_defaults_to_the_compiled_stem():
    """Without an explicit stem the artefact's own stem names the module."""
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    assert "'list'" in export_source(cg)


# ── export_module: hermetic import parity ──────────────────────────────


@pytest.mark.parametrize("stem,ext", [("json", "gbnf"), ("arithmetic", "abnf")])
@pytest.mark.parametrize("inline_tables", [False, True])
def test_export_module_hermetic_import_matches_the_runtime_compile(
    stem: str, ext: str, inline_tables: bool, tmp_path
):
    """A written twin module imports hermetically and its classes carry the
    same ``__grammar__``/``__binds__``/``_fields`` as the runtime compile's
    own classes, in both table modes, for a GBNF and an ABNF grammar."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.{ext}")
    out_path = tmp_path / f"{stem}_twin.py"
    export_module(cg, out_path, inline_tables=inline_tables)

    module = import_hermetic_module(out_path, f"{stem}_{ext}_{inline_tables}_twin")

    assert module.GRAMMAR == cg.grammar
    for name, cls in cg.classes.items():
        twin = getattr(module, name)
        assert twin.__grammar__ == cls.__grammar__, name
        assert twin.__binds__ == cls.__binds__, name
        assert twin._fields == cls._fields, name


def test_export_module_creates_parent_directories(tmp_path):
    """export_module writes into a nested, not-yet-existing directory tree."""
    cg = compile_text('root ::= "hi"\n')
    out_path = tmp_path / "a" / "b" / "c" / "twin.py"
    assert not out_path.parent.exists()
    export_module(cg, out_path)
    assert out_path.exists()


def test_export_module_returns_the_written_path(tmp_path):
    """export_module's return value is the path it wrote."""
    cg = compile_text('root ::= "hi"\n')
    out_path = tmp_path / "twin.py"
    returned = export_module(cg, out_path)
    assert returned == out_path


def test_export_module_stem_defaults_to_the_output_files_stem(tmp_path):
    """Without an explicit stem, the output filename's stem names the module."""
    cg = compile_text('root ::= "hi"\n')
    out_path = tmp_path / "my_grammar_name.py"
    export_module(cg, out_path)
    assert "'my_grammar_name'" in out_path.read_text(encoding="utf-8")
