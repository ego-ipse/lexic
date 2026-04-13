"""
tests/test_codegen.py — Contract test suite for build() only.

Tests-first: these tests define the contract that S05 must satisfy.
They MUST fail on the current (pre-rewrite) codegen.py.

Contract:
  - build(grammar_path) -> dict[str, type]
  - No class name matches r'.+Alt\\d+$'
  - SOLID inheritance: alternation rules → abstract base + typed concrete subclasses
  - Exact class names per grammar (no ValueAlt4, TermAlt2, StatementAlt5, etc.)
  - Field types reflect grammar structure (ObjectValue.object: Object, not Union[...])

Do NOT test parse(), to_text(), to_json() — those belong to S06/S07.
Only build() is exercised here.

Naming contract (locked by T01):
  json_ws value arms  : ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral
  arithmetic term arm2: TermExpr (first non-ws rule ref = expr)
  c.gbnf statement    : StatementDataType, StatementIdentifier, StatementIdentifier2,
                        StatementReturn, StatementWhile, StatementFor, StatementIf,
                        SingleLineCommentStatement, MultiLineCommentStatement
  c.gbnf for_init     : ForInitDataType, ForInitIdentifier
  chess / japanese    : identical value structure → same names as json_ws
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.codegen import build

GROUND = Path("resources/ground_truth")

JSON_WS    = GROUND / "json_ws.gbnf"
ARITHMETIC = GROUND / "arithmetic.gbnf"
LIST_GBNF  = GROUND / "list.gbnf"
CHESS      = GROUND / "chess.gbnf"
JAPANESE   = GROUND / "japanese.gbnf"
C_GBNF     = GROUND / "c.gbnf"

ALL_GRAMMARS = [JSON_WS, ARITHMETIC, LIST_GBNF, CHESS, JAPANESE, C_GBNF]


# ---------------------------------------------------------------------------
# 1. No AltN class names — for any grammar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grammar", ALL_GRAMMARS, ids=lambda p: p.name)
def test_no_alt_n_names(grammar: Path) -> None:
    """No generated class name may match r'.+Alt\\d+$'."""
    classes = build(grammar)
    bad = [name for name in classes if re.match(r".+Alt\d+$", name)]
    assert not bad, (
        f"AltN class names found in {grammar.name}: {bad}\n"
        "Alternation arms must receive semantic names derived from the grammar."
    )


# ---------------------------------------------------------------------------
# 2. Root always present; all classes are BaseModel subclasses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grammar", ALL_GRAMMARS, ids=lambda p: p.name)
def test_root_present(grammar: Path) -> None:
    """build() must produce at least one class and always include Root."""
    classes = build(grammar)
    assert classes, f"No classes generated from {grammar.name}"
    assert "Root" in classes, (
        f"No Root class in {grammar.name} output. Got: {sorted(classes)}"
    )
    assert all(issubclass(cls, BaseModel) for cls in classes.values()), (
        "Non-BaseModel class in output"
    )


# ---------------------------------------------------------------------------
# 3. json_ws — exact class names and SOLID hierarchy
#
# value ::= object | array | string | number | ("true"|"false"|"null") ws
# Arms: ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral
# (arm 4 is a SequenceNode whose first non-ws node is AlternativeNode of literals
#  → "Literal" suffix)
# ---------------------------------------------------------------------------

def test_json_ws_value_arm_names() -> None:
    """json_ws value arms must be named ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral."""
    classes = build(JSON_WS)
    expected = {"ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"}
    for name in expected:
        assert name in classes, (
            f"{name!r} not found in generated classes for json_ws.\n"
            f"Got: {sorted(classes)}"
        )


def test_json_ws_value_solid_hierarchy() -> None:
    """Value must be an abstract base; all arm classes must inherit from Value."""
    classes = build(JSON_WS)
    assert "Value" in classes, f"No Value class. Got: {sorted(classes)}"
    Value = classes["Value"]

    # Abstract base: no required fields
    required = [n for n, f in Value.model_fields.items() if f.is_required()]
    assert not required, f"Abstract base Value has required fields: {required}"

    # All concrete arms inherit from Value
    for name in ("ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"):
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], Value), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected Value in bases"
        )


def test_json_ws_object_value_field_type() -> None:
    """ObjectValue must have a field typed as Object (not Union[...] or str)."""
    classes = build(JSON_WS)
    assert "ObjectValue" in classes, "ObjectValue not generated"
    assert "Object" in classes, "Object not generated"
    ObjectValue = classes["ObjectValue"]
    Object = classes["Object"]

    fields = ObjectValue.model_fields
    assert fields, "ObjectValue has no fields"

    # Every field must be typed as Object (not Union, not str)
    for fname, finfo in fields.items():
        ann = finfo.annotation
        assert ann is Object, (
            f"ObjectValue.{fname} is typed as {ann!r}, expected Object.\n"
            "Field types must be concrete class references, not Union[...]."
        )


def test_json_ws_root_inherits_object() -> None:
    """Root must inherit from Object (root ::= object)."""
    classes = build(JSON_WS)
    assert "Root" in classes
    assert "Object" in classes
    Root, Object = classes["Root"], classes["Object"]
    assert issubclass(Root, Object), (
        f"Root.__bases__ = {Root.__bases__}, expected Object in bases"
    )


# ---------------------------------------------------------------------------
# 4. arithmetic — exact class names and SOLID hierarchy
#
# term ::= ident | num | "(" ws expr ")" ws
# Arm 0: ident (RuleRefNode) → IdentTerm
# Arm 1: num   (RuleRefNode) → NumTerm
# Arm 2: "(" ws expr ")" ws (SequenceNode, first non-ws rule ref = expr) → TermExpr
# ---------------------------------------------------------------------------

def test_arithmetic_term_arm_names() -> None:
    """arithmetic term arms: IdentTerm, NumTerm, TermExpr (not TermAlt2)."""
    classes = build(ARITHMETIC)
    for name in ("IdentTerm", "NumTerm", "TermExpr"):
        assert name in classes, (
            f"{name!r} not found in arithmetic classes.\nGot: {sorted(classes)}"
        )


def test_arithmetic_term_solid_hierarchy() -> None:
    """Term must be abstract base; IdentTerm, NumTerm, TermExpr must inherit from Term."""
    classes = build(ARITHMETIC)
    assert "Term" in classes, f"No Term class. Got: {sorted(classes)}"
    Term = classes["Term"]

    required = [n for n, f in Term.model_fields.items() if f.is_required()]
    assert not required, f"Abstract base Term has required fields: {required}"

    for name in ("IdentTerm", "NumTerm", "TermExpr"):
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], Term), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected Term in bases"
        )


# ---------------------------------------------------------------------------
# 5. c.gbnf — statement arm names and SOLID hierarchy
#
# statement has 9 arms:
#   0: (dataType identifier ...)        → StatementDataType
#   1: (identifier ws "=" ...)          → StatementIdentifier
#   2: (identifier ws "(" ...)          → StatementIdentifier2  (collision dedup)
#   3: ("return" ...)                   → StatementReturn
#   4: ("while" ...)                    → StatementWhile
#   5: ("for" ...)                      → StatementFor
#   6: ("if" ...)                       → StatementIf
#   7: (singleLineComment) RuleRefNode  → SingleLineCommentStatement
#   8: (multiLineComment)  RuleRefNode  → MultiLineCommentStatement
# ---------------------------------------------------------------------------

STATEMENT_ARMS = [
    "StatementDataType",
    "StatementIdentifier",
    "StatementIdentifier2",
    "StatementReturn",
    "StatementWhile",
    "StatementFor",
    "StatementIf",
    "SingleLineCommentStatement",
    "MultiLineCommentStatement",
]


def test_c_statement_arm_names() -> None:
    """c.gbnf statement arms must have semantic names (no StatementAltN)."""
    classes = build(C_GBNF)
    for name in STATEMENT_ARMS:
        assert name in classes, (
            f"{name!r} not found in c.gbnf classes.\nGot: {sorted(classes)}"
        )


def test_c_statement_solid_hierarchy() -> None:
    """Statement must be abstract base; all arm classes must inherit from Statement."""
    classes = build(C_GBNF)
    assert "Statement" in classes, f"No Statement class. Got: {sorted(classes)}"
    Statement = classes["Statement"]

    required = [n for n, f in Statement.model_fields.items() if f.is_required()]
    assert not required, f"Abstract base Statement has required fields: {required}"

    for name in STATEMENT_ARMS:
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], Statement), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected Statement in bases"
        )


# ---------------------------------------------------------------------------
# 6. c.gbnf — for_init arm names and SOLID hierarchy
#
# forInit ::= dataType identifier ... | identifier ...
# Arm 0: ForInitDataType  (first non-ws rule ref = dataType → DataType)
# Arm 1: ForInitIdentifier (first non-ws rule ref = identifier → Identifier)
# ---------------------------------------------------------------------------

def test_c_for_init_arm_names() -> None:
    """c.gbnf forInit arms: ForInitDataType, ForInitIdentifier."""
    classes = build(C_GBNF)
    for name in ("ForInitDataType", "ForInitIdentifier"):
        assert name in classes, (
            f"{name!r} not found in c.gbnf classes.\nGot: {sorted(classes)}"
        )


def test_c_for_init_solid_hierarchy() -> None:
    """ForInit must be abstract base; ForInitDataType/ForInitIdentifier must inherit from ForInit."""
    classes = build(C_GBNF)
    assert "ForInit" in classes, f"No ForInit class. Got: {sorted(classes)}"
    ForInit = classes["ForInit"]

    required = [n for n, f in ForInit.model_fields.items() if f.is_required()]
    assert not required, f"Abstract base ForInit has required fields: {required}"

    for name in ("ForInitDataType", "ForInitIdentifier"):
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], ForInit), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected ForInit in bases"
        )


# ---------------------------------------------------------------------------
# 7. chess — same value structure as json_ws, same class names expected
# ---------------------------------------------------------------------------

def test_chess_value_arm_names() -> None:
    """chess value arms must be named ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral."""
    classes = build(CHESS)
    for name in ("ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"):
        assert name in classes, (
            f"{name!r} not found in chess classes.\nGot: {sorted(classes)}"
        )


def test_chess_value_solid_hierarchy() -> None:
    """chess Value must be abstract base; concrete arms inherit from Value."""
    classes = build(CHESS)
    assert "Value" in classes, f"No Value class. Got: {sorted(classes)}"
    Value = classes["Value"]

    required = [n for n, f in Value.model_fields.items() if f.is_required()]
    assert not required, f"chess Value has required fields: {required}"

    for name in ("ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"):
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], Value), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected Value in bases"
        )


# ---------------------------------------------------------------------------
# 8. japanese — same value structure as json_ws, same class names expected
# ---------------------------------------------------------------------------

def test_japanese_value_arm_names() -> None:
    """japanese value arms must be named ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral."""
    classes = build(JAPANESE)
    for name in ("ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"):
        assert name in classes, (
            f"{name!r} not found in japanese classes.\nGot: {sorted(classes)}"
        )


def test_japanese_value_solid_hierarchy() -> None:
    """japanese Value must be abstract base; concrete arms inherit from Value."""
    classes = build(JAPANESE)
    assert "Value" in classes, f"No Value class. Got: {sorted(classes)}"
    Value = classes["Value"]

    required = [n for n, f in Value.model_fields.items() if f.is_required()]
    assert not required, f"japanese Value has required fields: {required}"

    for name in ("ObjectValue", "ArrayValue", "StringValue", "NumberValue", "ValueLiteral"):
        assert name in classes, f"{name} not in classes"
        assert issubclass(classes[name], Value), (
            f"{name}.__bases__ = {classes[name].__bases__}, expected Value in bases"
        )


# ---------------------------------------------------------------------------
# 9. list.gbnf — simple grammar, just verify Root
# ---------------------------------------------------------------------------

def test_list_root_present_and_no_alt_names() -> None:
    """list.gbnf must generate Root with no AltN names."""
    classes = build(LIST_GBNF)
    assert "Root" in classes, f"No Root in list.gbnf. Got: {sorted(classes)}"
    bad = [name for name in classes if re.match(r".+Alt\d+$", name)]
    assert not bad, f"AltN names in list.gbnf: {bad}"
