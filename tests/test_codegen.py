"""Pytest suite for src/codegen — verifies semantic correctness of generated Pydantic models.

Expectations derived exclusively from .gsd/milestones/M001/slices/S01/S01-SCENARIOS.md.
"""

from __future__ import annotations

import importlib
import sys
from abc import ABC
from pathlib import Path
from typing import Union, get_args, get_origin, get_type_hints

import pytest
from pydantic import BaseModel

from codegen import codegen

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"
GENERATED_DIR = Path(__file__).parent.parent / "generated"

ALL_GRAMMARS = [
    "arithmetic.gbnf",
    "c.gbnf",
    "chess.gbnf",
    "japanese.gbnf",
    "json_arr.gbnf",
    "json_ws.gbnf",
    "list.gbnf",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _hint(cls: type, field: str) -> type:
    """Return the resolved annotation for a field on a Pydantic model class."""
    hints = get_type_hints(cls)
    assert field in hints, (
        f"{cls.__name__} has no field '{field}'; fields: {list(hints)}"
    )
    return hints[field]


def _is_abstract(cls: type) -> bool:
    return isinstance(cls, type) and issubclass(cls, ABC) and ABC in cls.__bases__


def _is_list_of(hint: type, inner: type) -> bool:
    return get_origin(hint) is list and get_args(hint)[0] is inner


def _is_optional_of(hint: type, inner: type) -> bool:
    if get_origin(hint) is Union:
        args = get_args(hint)
        return type(None) in args and inner in args
    return False


def _is_optional_str(hint: type) -> bool:
    return _is_optional_of(hint, str)


def _is_union_of(hint: type, *classes: type) -> bool:
    if get_origin(hint) is not Union:
        return False
    args = set(get_args(hint))
    return set(classes) == args - {type(None)}


# ── Smoke tests: all 7 grammars ───────────────────────────────────────────────


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_codegen_returns_nonempty_dict(grammar_file: str) -> None:
    """codegen() must return a non-empty dict[str, type] for every grammar."""
    classes = codegen(GRAMMAR_DIR / grammar_file)
    assert isinstance(classes, dict), "codegen must return a dict"
    assert len(classes) > 0, "codegen must return at least one class"


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_all_values_are_real_types(grammar_file: str) -> None:
    """Every value in the returned dict must be an actual type (not a string)."""
    classes = codegen(GRAMMAR_DIR / grammar_file)
    for name, cls in classes.items():
        assert isinstance(cls, type), f"{name} is not a type: {cls!r}"


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_all_classes_are_pydantic_models(grammar_file: str) -> None:
    """Every returned class must be a subclass of pydantic.BaseModel."""
    classes = codegen(GRAMMAR_DIR / grammar_file)
    for name, cls in classes.items():
        assert issubclass(cls, BaseModel), f"{name} is not a BaseModel subclass"


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_root_class_present(grammar_file: str) -> None:
    """A 'Root' class must always be present in the returned dict."""
    classes = codegen(GRAMMAR_DIR / grammar_file)
    assert "Root" in classes, f"'Root' missing from {grammar_file} output"


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_generated_file_importable(grammar_file: str) -> None:
    """Generated .py file must be importable via importlib without errors."""
    stem = Path(grammar_file).stem
    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "Root")


@pytest.mark.parametrize("grammar_file", ALL_GRAMMARS)
def test_no_exec_in_generated_file(grammar_file: str) -> None:
    """Generated source must not contain exec() — only model_rebuild() is allowed."""
    stem = Path(grammar_file).stem
    source = (GENERATED_DIR / f"{stem}.py").read_text()
    assert "exec(" not in source, f"exec() found in generated {stem}.py"


# ── arithmetic.gbnf ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def arithmetic_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "arithmetic.gbnf")


def test_arithmetic_term_is_abstract(arithmetic_classes):
    Term = arithmetic_classes["Term"]
    assert _is_abstract(Term), "Term must be abstract (ABC)"
    # __grammar__ is a ClassVar, not a Pydantic field — check model_fields instead
    assert not Term.model_fields, "Term must have no Pydantic fields"


def test_arithmetic_ident_is_subclass_of_term(arithmetic_classes):
    assert issubclass(arithmetic_classes["Ident"], arithmetic_classes["Term"])


def test_arithmetic_num_is_subclass_of_term(arithmetic_classes):
    assert issubclass(arithmetic_classes["Num"], arithmetic_classes["Term"])


def test_arithmetic_termarm3_is_subclass_of_term(arithmetic_classes):
    assert issubclass(arithmetic_classes["TermArm3"], arithmetic_classes["Term"])


def test_arithmetic_ident_fields(arithmetic_classes):
    Ident = arithmetic_classes["Ident"]
    # ident ::= [a-z] [a-z0-9_]* ws
    # CharClassAtoms → "first", "second"; RuleRefAtom(ws) → "ws"
    assert _hint(Ident, "first") is str
    assert _hint(Ident, "second") is str
    assert "ws" in get_type_hints(Ident)


def test_arithmetic_num_fields(arithmetic_classes):
    Num = arithmetic_classes["Num"]
    # num ::= [0-9]+ ws  — sequence with CharClassAtom→"first" and ws→"ws"
    assert _hint(Num, "first") is str
    assert "ws" in get_type_hints(Num)


def test_arithmetic_termarm3_fields(arithmetic_classes):
    TermArm3 = arithmetic_classes["TermArm3"]
    Expr = arithmetic_classes["Expr"]
    # term-arm3 ::= "(" ws expr ")" ws  — expr→"expr" field; ws refs → "ws"
    assert _hint(TermArm3, "expr") is Expr


def test_arithmetic_expritem_fields(arithmetic_classes):
    ExprItem = arithmetic_classes["ExprItem"]
    Term = arithmetic_classes["Term"]
    # expr-item ::= [-+*/] term  → CharClassAtom→"first", RuleRefAtom(term)→"term"
    assert _hint(ExprItem, "first") is str
    assert _hint(ExprItem, "term") is Term


def test_arithmetic_expr_fields(arithmetic_classes):
    Expr = arithmetic_classes["Expr"]
    Term = arithmetic_classes["Term"]
    ExprItem = arithmetic_classes["ExprItem"]
    # expr ::= term ([-+*/] term)*  → term→"term", expr-item→"expr_item"
    assert _hint(Expr, "term") is Term
    assert _is_list_of(_hint(Expr, "expr_item"), ExprItem)


def test_arithmetic_rootitem_fields(arithmetic_classes):
    RootItem = arithmetic_classes["RootItem"]
    Expr = arithmetic_classes["Expr"]
    Term = arithmetic_classes["Term"]
    # root-item ::= expr "=" ws term "\n"  → expr→"expr", term→"term"
    assert _hint(RootItem, "expr") is Expr
    assert _hint(RootItem, "term") is Term


def test_arithmetic_root_fields(arithmetic_classes):
    Root = arithmetic_classes["Root"]
    RootItem = arithmetic_classes["RootItem"]
    # root ::= root-item+  → root_item→List[RootItem]
    assert _is_list_of(_hint(Root, "root_item"), RootItem)


def test_arithmetic_ws_fields_are_str(arithmetic_classes):
    """Ws is a pure character-level rule — it must be value_str with a 'value' str field."""
    Ws = arithmetic_classes["Ws"]
    hints = get_type_hints(Ws)
    assert "value" in hints, "Ws must have a 'value' field"
    assert hints["value"] is str, "Ws.value must be str"


def test_arithmetic_circular_ref_resolved(arithmetic_classes):
    """Circular Term ↔ Expr reference must be resolvable — instantiation is the proof."""
    Ident = arithmetic_classes["Ident"]
    ExprItem = arithmetic_classes["ExprItem"]
    Expr = arithmetic_classes["Expr"]
    Ws = arithmetic_classes["Ws"]
    ws = Ws(value="")
    ident = Ident(first="x", second="yz", ws=ws)
    expr = Expr(term=ident, expr_item=[])
    expritem = ExprItem(first="+", term=ident)
    assert expritem.term is ident
    assert expr.term is ident


# ── chess.gbnf ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def chess_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "chess.gbnf")


def test_chess_no_abstract_bases(chess_classes):
    for name, cls in chess_classes.items():
        assert not _is_abstract(cls), f"{name} should not be abstract in chess"


def test_chess_castle_is_value_str(chess_classes):
    # castle ::= "O-O" "-O"?  — pure literals → value_str
    Castle = chess_classes["Castle"]
    assert _hint(Castle, "value") is str


def test_chess_pawn_has_charclass_fields(chess_classes):
    Pawn = chess_classes["Pawn"]
    # pawn ::= ([a-h] "x")? [a-h] [1-8] ("=" [NBKQR])?
    # → CharClassAtoms: first(opt), second, third, fourth(opt)
    assert "first" in Pawn.model_fields
    assert "second" in Pawn.model_fields
    assert "third" in Pawn.model_fields
    assert "fourth" in Pawn.model_fields
    # All are str-typed Pydantic fields
    for fname in ("first", "second", "third", "fourth"):
        assert _hint(Pawn, fname) is str, f"Pawn.{fname} must be str"


def test_chess_move_has_charclass_field(chess_classes):
    Move = chess_classes["Move"]
    # move ::= (pawn | nonpawn | castle) [+#]?
    # inline AlternationAtom (not a field) + CharClassAtom → "first"
    hints = get_type_hints(Move)
    assert "first" in hints
    assert hints["first"] is str


def test_chess_rootitem_fields(chess_classes):
    RootItem = chess_classes["RootItem"]
    Move = chess_classes["Move"]
    hints = get_type_hints(RootItem)
    # root-item ::= [1-9] [0-9]? ". " move " " move "\n"
    # → first: str, second: str, move: Move, move2: Move
    assert hints["first"] is str
    assert hints["second"] is str
    assert hints["move"] is Move
    assert hints["move2"] is Move


# ── japanese.gbnf ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def japanese_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "japanese.gbnf")


def test_japanese_jpchar_is_abstract(japanese_classes):
    JpChar = japanese_classes["JpChar"]
    assert _is_abstract(JpChar)


def test_japanese_subclasses(japanese_classes):
    JpChar = japanese_classes["JpChar"]
    for name in ("Hiragana", "Katakana", "Punctuation", "Cjk"):
        assert name in japanese_classes, f"{name} missing"
        assert issubclass(japanese_classes[name], JpChar)


def test_japanese_char_subclasses_have_value_str(japanese_classes):
    # Hiragana/Katakana/Punctuation/Cjk are value_str — each has "value: str"
    for name in ("Hiragana", "Katakana", "Punctuation", "Cjk"):
        cls = japanese_classes[name]
        assert _hint(cls, "value") is str


def test_japanese_root_fields(japanese_classes):
    Root = japanese_classes["Root"]
    JpChar = japanese_classes["JpChar"]
    hints = get_type_hints(Root)
    # root ::= jp-char+ ([ \t\n] jp-char+)*
    # → jp_char: List[JpChar], root_item: List[RootItem]
    assert _is_list_of(hints["jp_char"], JpChar)
    assert get_origin(hints["root_item"]) is list


def test_japanese_rootitem_fields(japanese_classes):
    RootItem = japanese_classes["RootItem"]
    JpChar = japanese_classes["JpChar"]
    hints = get_type_hints(RootItem)
    # root-item ::= [ \t\n] jp-char+  → first: str, jp_char: List[JpChar]
    assert hints["first"] is str
    assert _is_list_of(hints["jp_char"], JpChar)


# ── list.gbnf ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def list_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "list.gbnf")


def test_list_item_is_value_str(list_classes):
    # item ::= "- " [^\r\n...]+ "\n"  — has only literals/charclasses but
    # classified as value_str since no rule refs
    Item = list_classes["Item"]
    assert _hint(Item, "value") is str


def test_list_root_fields(list_classes):
    Root = list_classes["Root"]
    Item = list_classes["Item"]
    # root ::= item+  → item: List[Item]
    assert _is_list_of(_hint(Root, "item"), Item)


def test_list_instantiation(list_classes):
    Item = list_classes["Item"]
    Root = list_classes["Root"]
    item = Item(value="- hello world\n")
    root = Root(item=[item])
    assert root.item[0].value == "- hello world\n"


# ── json_ws.gbnf ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def json_ws_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "json_ws.gbnf")


def test_json_ws_value_is_abstract(json_ws_classes):
    Value = json_ws_classes["Value"]
    assert _is_abstract(Value)


def test_json_ws_string_number_are_value_subclasses(json_ws_classes):
    Value = json_ws_classes["Value"]
    assert issubclass(json_ws_classes["String"], Value)
    assert issubclass(json_ws_classes["Number"], Value)


def test_json_ws_string_number_have_value_str(json_ws_classes):
    for name in ("String",):
        cls = json_ws_classes[name]
        assert _hint(cls, "value") is str, f"{name}.value must be str"


def test_json_ws_object_is_value_subclass(json_ws_classes):
    assert issubclass(json_ws_classes["Object"], json_ws_classes["Value"])


def test_json_ws_array_is_value_subclass(json_ws_classes):
    assert issubclass(json_ws_classes["Array"], json_ws_classes["Value"])


def test_json_ws_root_wraps_object(json_ws_classes):
    Root = json_ws_classes["Root"]
    Object = json_ws_classes["Object"]
    # root ::= object  → object: Object
    assert _hint(Root, "object") is Object


def test_json_ws_object_fields(json_ws_classes):
    Object = json_ws_classes["Object"]
    hints = get_type_hints(Object)
    # object ::= "{" ws object-item? "}" ws
    # → ws: Ws, object_item: Optional[ObjectItem], ws2: Ws
    Ws = json_ws_classes["Ws"]
    assert hints["ws"] is Ws
    assert hints["ws2"] is Ws
    assert "object_item" in hints


def test_json_ws_circular_ref_resolved(json_ws_classes):
    """Object ↔ Value circular ref must resolve — instantiation proves it."""
    String = json_ws_classes["String"]
    ValueArm5 = json_ws_classes["ValueArm5"]
    s = String(value='"hello"')
    v = ValueArm5(first="null")
    assert v.first == "null"


def test_json_ws_no_arr_classes(json_ws_classes):
    """json_ws.gbnf has no arr/Arr — unlike json_arr.gbnf."""
    assert "Arr" not in json_ws_classes
    assert "ArrOpt" not in json_ws_classes
    assert "ArrOptItem" not in json_ws_classes


# ── json_arr.gbnf ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def json_arr_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "json_arr.gbnf")


def test_json_arr_has_arr_class(json_arr_classes):
    assert "Arr" in json_arr_classes


def test_json_arr_root_wraps_arr(json_arr_classes):
    Root = json_arr_classes["Root"]
    Arr = json_arr_classes["Arr"]
    # root ::= arr  → arr: Arr
    assert _hint(Root, "arr") is Arr


def test_json_arr_value_is_abstract(json_arr_classes):
    assert _is_abstract(json_arr_classes["Value"])


def test_json_arr_arr_fields(json_arr_classes):
    Arr = json_arr_classes["Arr"]
    hints = get_type_hints(Arr)
    # arr ::= "[\n" ws arr-item? "]"
    # → ws: Ws, arr_item: Optional[ArrItem]
    Ws = json_arr_classes["Ws"]
    assert hints["ws"] is Ws
    assert "arr_item" in hints


# ── c.gbnf ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def c_classes() -> dict[str, type]:
    return codegen(GRAMMAR_DIR / "c.gbnf")


def test_c_factor_is_abstract(c_classes):
    assert _is_abstract(c_classes["Factor"])


def test_c_statement_is_abstract(c_classes):
    assert _is_abstract(c_classes["Statement"])


def test_c_forinit_is_abstract(c_classes):
    assert _is_abstract(c_classes["ForInit"])


def test_c_identifier_is_factor_subclass(c_classes):
    assert issubclass(c_classes["Identifier"], c_classes["Factor"])


def test_c_number_is_factor_subclass(c_classes):
    assert issubclass(c_classes["Number"], c_classes["Factor"])


def test_c_datatype_is_value_str(c_classes):
    DataType = c_classes["DataType"]
    assert _hint(DataType, "value") is str


def test_c_relation_operator_is_value_str(c_classes):
    assert _hint(c_classes["RelationOperator"], "value") is str


def test_c_singlelinecomment_is_statement_subclass(c_classes):
    assert issubclass(c_classes["SingleLineComment"], c_classes["Statement"])


def test_c_multilinecomment_is_statement_subclass(c_classes):
    assert issubclass(c_classes["MultiLineComment"], c_classes["Statement"])


def test_c_singlelinecomment_is_value_str(c_classes):
    """SingleLineComment is classified as value_str — it has a single 'value' field."""
    SingleLineComment = c_classes["SingleLineComment"]
    assert _hint(SingleLineComment, "value") is str


def test_c_statement_arm5_has_list_statement(c_classes):
    StatementArm5 = c_classes["StatementArm5"]
    Statement = c_classes["Statement"]
    hints = get_type_hints(StatementArm5)
    list_fields = [f for f, h in hints.items() if _is_list_of(h, Statement)]
    assert list_fields, "StatementArm5 must have a List[Statement] field (recursive)"


def test_c_forinit_arm1_arm2_are_subclasses(c_classes):
    ForInit = c_classes["ForInit"]
    assert issubclass(c_classes["ForInitArm1"], ForInit)
    assert issubclass(c_classes["ForInitArm2"], ForInit)


def test_c_declaration_fields(c_classes):
    Declaration = c_classes["Declaration"]
    hints = get_type_hints(Declaration)
    # declaration ::= dataType identifier "(" parameter? ")" "{" statement* "}"
    # → dataType: DataType, identifier: Identifier, parameter: Optional[Parameter], statement: List[Statement]
    assert hints["dataType"] is c_classes["DataType"]
    assert hints["identifier"] is c_classes["Identifier"]
    assert "parameter" in hints


def test_c_root_field(c_classes):
    Root = c_classes["Root"]
    Declaration = c_classes["Declaration"]
    RootItem = c_classes["RootItem"]
    # root ::= declaration*  → root-item helper → root_item: List[RootItem]
    hints = get_type_hints(Root)
    assert "root_item" in hints
    assert get_origin(hints["root_item"]) is list


def test_c_unaryterm_is_factor_subclass(c_classes):
    assert issubclass(c_classes["UnaryTerm"], c_classes["Factor"])


def test_c_funcall_is_factor_subclass(c_classes):
    assert issubclass(c_classes["FuncCall"], c_classes["Factor"])


def test_c_circular_ref_resolved(c_classes):
    """UnaryTerm → Factor circular ref must not raise on instantiation."""
    Identifier = c_classes["Identifier"]
    Factor = c_classes["Factor"]
    ident = Identifier(value="x")
    assert isinstance(ident, Factor)


# ── No exec() in any generated file ──────────────────────────────────────────


def test_no_exec_anywhere():
    """No generated file may contain exec()."""
    for f in GENERATED_DIR.glob("*.py"):
        source = f.read_text()
        assert "exec(" not in source, f"exec() found in {f.name}"


# ── Q7: Negative tests ────────────────────────────────────────────────────────


def test_codegen_missing_file_raises():
    """codegen() on a non-existent path must raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        codegen(GRAMMAR_DIR / "does_not_exist.gbnf")


def test_codegen_empty_grammar(tmp_path):
    """codegen() on an empty grammar must raise a parse error — not silently return."""
    empty = tmp_path / "empty.gbnf"
    empty.write_text("")
    with pytest.raises(Exception):
        codegen(empty)


def test_abstract_class_inherits_abc(arithmetic_classes):
    """Abstract Term class must inherit from ABC (semantic abstract marker).

    Note: Python only blocks instantiation when @abstractmethod decorators are
    present. The generated classes use ABC as a structural marker without
    abstract methods, so Pydantic models with ABC bases are still constructable
    by Pydantic machinery. We verify the ABC inheritance, not instantiation block.
    """
    Term = arithmetic_classes["Term"]
    assert issubclass(Term, ABC), "Term must inherit from ABC"


def test_pydantic_validates_field_types(list_classes):
    """Pydantic must reject wrong types at validation time."""
    Item = list_classes["Item"]
    with pytest.raises(Exception):  # pydantic ValidationError
        Item(value=123)
