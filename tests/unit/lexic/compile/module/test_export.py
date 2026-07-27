"""Tests for ``lexic.compile.module.export`` — the importable ``.py`` twin renderer.

Ported from the reader-view exporter (260718 rework): assertions kept
wherever their target survived; the ruff/subprocess seam, ``_HEADER``,
``export_module_source`` and ``_binds_repr`` tests went with their symbols
(the formatter is the layout algebra now, the header is derived from the
emitted content, and the binds table renders only under ``inline_tables``).
"""

from __future__ import annotations

import ast
import inspect

import pytest

from lexic.compile import compile_from_path, compile_text, export_module, export_source
from lexic.compile.module import export
from lexic.compile.module.export import (
    WIDTH,
    _group_model_type,
    _ws_inl_leak,
    docstring_lines,
    field_type,
    value_str_type,
)
from lexic.compile.pipeline.binding import (
    _RESERVED_CLASS_NAMES,
    RuleBinding,
    compute_binding,
)
from lexic.ir.base import IrNone
from lexic.ir.encoding import IrTokenizer
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


# ── the ws-inl invariant guard (module self-grammar reparse) ──────────────


def test_ws_inl_leak_guard_shape():
    """The guard flags a value-final token (name/``)``) with a newline before
    its delimiter, but not the valid AFTER-``(``/``,`` layout breaks (whose
    ``ws`` DOES cross a newline in the module self-grammar)."""
    assert _ws_inl_leak("IrNone\n)")
    assert _ws_inl_leak("IrRange(a, b)\n,")
    assert not _ws_inl_leak("IrCharClass(\n    IrRange")  # break after (
    assert not _ws_inl_leak("IrRange(a, b),\n    )")  # break after ,


def test_ws_inl_leak_does_not_stop_at_a_leading_newline():
    """A newline at index 0 cannot start a match but must not end the scan.

    The scan's predecessor bug: a leading newline terminated it, so every later
    leak went unreported — and the caller RAISES on a leak, so a false negative
    ships a broken twin in silence.
    """
    assert _ws_inl_leak("\na\n,") == "a\n,"
    assert _ws_inl_leak("\n\n\nx\n  )") == "x\n  )"


def test_ws_inl_leak_reports_the_offending_slice():
    """The refusal quotes the text it objected to, delimiter included."""
    assert _ws_inl_leak("IrRange(a, b)\n   ,") == ")\n   ,"
    assert _ws_inl_leak("a\nb\n)") == "b\n)"


def test_ws_inl_leak_word_test_is_unicode_like_the_pattern_it_replaced():
    """``\\w`` is ``isalnum() or "_"`` — a Unicode letter or digit counts."""
    assert _ws_inl_leak("é\n)")
    assert _ws_inl_leak("٣\n)")  # ARABIC-INDIC DIGIT THREE
    assert _ws_inl_leak("_\n)")
    assert not _ws_inl_leak("!\n)")
    assert not _ws_inl_leak(" \n)")


@pytest.mark.parametrize("stem", ["list", "json_ws", "arithmetic"])
def test_export_notation_never_leaks_a_newline_before_a_delimiter(stem: str):
    """Every real export honours the invariant its module reparse relies on:
    no value-final token is separated from its ``,``/``)`` by a newline."""
    cg = compile_from_path(GROUND_TRUTH / f"{stem}.gbnf")
    for inline_tables in (False, True):
        source = export_source(cg, stem=stem, inline_tables=inline_tables)
        grammar_region = source.split("GRAMMAR: IrAst = ", 1)[1]
        assert not _ws_inl_leak(grammar_region)


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


# ── docstring_lines — the class docstring fill-wrap ────────────────────────


def test_docstring_lines_short_rule_is_one_line():
    """A rule text that fits under the width renders as a single docstring line."""
    lines = docstring_lines('a ::= "x"')
    assert len(lines) == 1
    assert lines[0] == '    """``a ::= \\"x\\"``"""'


def test_docstring_lines_short_rule_starts_and_ends_correctly():
    """The single line opens ``    \"\"\"`` `` and closes `` \"\"\"``."""
    lines = docstring_lines("a ::= b")
    assert lines[0].startswith('    """``')
    assert lines[0].endswith('``"""')


def test_docstring_lines_long_rule_wraps_at_spaces_within_width():
    """A rule text wider than 88 columns wraps onto continuation lines, each
    within the width budget."""
    rule_text = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    lines = docstring_lines(rule_text)
    assert len(lines) > 1
    assert all(len(line) <= WIDTH for line in lines)


def test_docstring_lines_long_rule_continuations_are_indented_four_spaces():
    """Every continuation line (after the first) starts with 4-space indent —
    the class-body indent level."""
    rule_text = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    lines = docstring_lines(rule_text)
    for line in lines[1:]:
        assert line.startswith("    ")
        assert not line.startswith("     ")  # exactly 4, not more


def test_docstring_lines_long_rule_closes_with_the_triple_quote():
    """The last wrapped line ends the docstring with the closing marker."""
    rule_text = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    lines = docstring_lines(rule_text)
    assert lines[-1].endswith('``"""')


def test_docstring_lines_word_reassembly_matches_the_source_text():
    """Rejoining the wrapped words (stripping the docstring wrapper) recovers
    the original (escaped) rule text — wrapping never drops or duplicates text."""
    rule_text = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    lines = docstring_lines(rule_text)
    joined = " ".join(line.strip() for line in lines)
    stripped = joined.removeprefix('"""``').removesuffix('``"""')
    assert stripped == rule_text


def test_docstring_lines_single_over_budget_token_overflows_without_chopping():
    """A single token wider than the whole width is never split mid-word —
    it lands on its own line and simply overflows the budget."""
    huge_token = "x" * 120
    lines = docstring_lines(f"a ::= {huge_token}")
    overflow_lines = [line for line in lines if huge_token in line]
    assert len(overflow_lines) == 1
    # the last word carries the closing ``"""`` glued on with no space
    assert overflow_lines[0].strip() == huge_token + '``"""'
    assert len(overflow_lines[0]) > WIDTH


def test_docstring_lines_escapes_backslash_and_quote():
    """Backslashes and double quotes escape so the text is triple-quote-safe."""
    lines = docstring_lines('a ::= "x" \\ "y"')
    text = " ".join(lines)
    assert '\\"x\\"' in text
    assert "\\\\" in text


# ── the header is what emission SPELLED, not what the body mentions ───────


def test_header_imports_the_literal_the_annotation_used() -> None:
    """A pure-literal ``value_str`` alternation types as ``Literal[...]``.

    The typing import used to be found by looking for ``Literal[`` anywhere in
    the finished module; it is now declared by the renderer that produced the
    annotation. No corpus grammar reaches this branch, so it needs its own
    grammar.
    """
    compiled = compile_text(
        'root ::= flag\nflag ::= "true" | "false"\n', cache_key="export-literal-header"
    )
    source = export_source(compiled, stem="lit")
    assert "from typing import Literal" in source
    assert "    value: Literal['true', 'false']" in source


def test_header_omits_typing_when_no_annotation_needs_it() -> None:
    """The same grammar without the literal alternation imports no typing name."""
    compiled = compile_text('root ::= "a" "b"\n', cache_key="export-no-typing-header")
    source = export_source(compiled, stem="flat")
    assert "from typing import" not in source


def test_header_omits_an_elided_default() -> None:
    """``root ::= "a" "b"`` holds a unit ``IrQuantifier`` the notation never
    spells, so the header must not import it — a value-walk would."""
    compiled = compile_text('root ::= "a" "b"\n', cache_key="export-elided-header")
    source = export_source(compiled, stem="flat")
    assert "IrQuantifier" not in source


def test_export_imports_no_regex_engine() -> None:
    """``export.py`` declares no ``re`` import — read from its AST.

    A name check divides *binds the name* from *uses a regex*;
    ``from re import compile`` binds neither. The import statements are the
    property.
    """
    tree = ast.parse(inspect.getsource(export))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "re" not in imported


# ── docstrings and GRAMMAR agree about resolution state ───────────────────


def _think_compiled():
    """``think.gbnf`` against a synthetic vocabulary — no fixture, no download.

    The property is that a docstring shows the SPELLING the grammar was written
    with, not the id it resolved to. A five-entry vocabulary establishes that as
    well as a 150 000-entry one, and it runs in the fast lane.
    """
    tokenizer = IrTokenizer.from_merges(
        "tokens", {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "ab": 4}, [("a", "b")]
    )
    return compile_from_path(GROUND_TRUTH / "think.gbnf", tokenizer=tokenizer)


def test_twin_docstrings_render_the_authored_token_spelling() -> None:
    """A token terminal reads as ``<think>``, not as ``<[0]>``."""
    source = export_source(_think_compiled(), stem="think")
    docstrings = [
        ln.strip() for ln in source.splitlines() if ln.strip().startswith('"""``')
    ]
    assert docstrings
    assert any("<think>" in line for line in docstrings)
    assert not any("<[" in line for line in docstrings)


def test_twin_docstrings_and_grammar_agree_about_resolution() -> None:
    """One file, one resolution state.

    ``GRAMMAR`` round-trips to the canonical AST, which holds the authored
    spellings; a docstring rendered off the resolved codegen grammar put a
    second, contradictory state in the same module.
    """
    source = export_source(_think_compiled(), stem="think")
    assert "<[" not in source


def test_char_grammar_docstrings_are_unchanged_by_the_resolution_rule() -> None:
    """Nothing to resolve, nothing to change — the rule is not a rewrite."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    source = export_source(compiled, stem="json")
    assert '"""``object ::= begin-object object-item2? end-object``"""' in source


def test_inline_grammar_table_keeps_the_resolved_rule() -> None:
    """``__grammar__`` is RUNTIME data — the docstring rule must not reach it.

    The docstring shows the authored spelling; the ClassVar the class binds has
    to stay the rule the engine resolved, or an inline-tables export would ship
    a grammar whose token terminals were never bound to ids.

    Read by AST rather than by slicing the text: ``GRAMMAR`` later in the same
    module legitimately holds the authored spelling, so any cut that overshoots
    the statement finds it and reports the wrong thing.
    """
    source = export_source(_think_compiled(), stem="think", inline_tables=True)
    tables = [
        ast.get_source_segment(source, node.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__grammar__"
        and node.value is not None
    ]
    assert tables
    for table in tables:
        assert table
        # The synthetic vocabulary puts `<think>` at id 0 and `</think>` at 1.
        assert "IrCharClass(IrChr(" in table
        assert "<think>" not in table and "</think>" not in table
    docstrings = [ln for ln in source.splitlines() if ln.strip().startswith('"""``')]
    assert any("<think>" in line for line in docstrings)


def test_a_terminal_spelling_the_gates_marker_still_exports() -> None:
    """The export gate reads the module structurally, never by splitting text.

    The docstring renders the grammar in its own flavour, so a grammar whose
    terminal spells ``GRAMMAR: IrAst = `` put ``source.split(...)`` inside the
    DOCSTRING — and a legal grammar was refused with a notation error about its
    own documentation.
    """
    source = export_source(compile_text('root ::= "GRAMMAR: IrAst = oops"'))
    assert "GRAMMAR: IrAst = oops" in source
    assert "IrLiteral" in source


@pytest.mark.parametrize("inline_tables", [False, True])
def test_a_twin_carries_the_same_shape_as_its_runtime_classes(
    tmp_path, inline_tables: bool
) -> None:
    """Both table modes, because they write the class's tables differently.

    The bind mode attaches ``__shape__`` at import; the inline mode writes it as
    a ClassVar. Wiring only the first left an inline twin's classes carrying no
    provenance at all, so a payload naming them lost its shape silently one way
    and was refused the other.
    """
    compiled = compile_text("root ::= item\nitem ::= num | word\nnum ::= [0-9]+\n")
    path = export_module(compiled, tmp_path / "tw.py", inline_tables=inline_tables)
    twin = import_hermetic_module(path, "tw")
    for name, cls in compiled.classes.items():
        assert getattr(twin, name).__shape__ == cls.__shape__
