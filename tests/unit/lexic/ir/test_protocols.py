"""Tests for ir/protocols.py — structural Protocol conformance."""

from __future__ import annotations

from typing import ClassVar, Literal

from lexic.ir import LiteralAtom, RuleRefAtom, RuleSpec
from lexic.ir.atoms import Atom
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import (
    AtomEmitHandler,
    EscapeCodec,
    FieldHandler,
    FlavourAdapter,
    FlavourParser,
    FlavourEmitter,
    LarkHandler,
    RuleClassifier,
    SequenceConverter,
    ToTextHandler,
    TransformHandler,
)


# ---------------------------------------------------------------------------
# Atom — runtime-checkable Protocol
# ---------------------------------------------------------------------------


def test_literal_atom_satisfies_atom_protocol():
    """LiteralAtom structurally satisfies the Atom marker Protocol."""
    assert isinstance(LiteralAtom(value="x"), Atom)


def test_rule_ref_atom_satisfies_atom_protocol():
    """RuleRefAtom structurally satisfies the Atom marker Protocol."""
    assert isinstance(RuleRefAtom(rule_name="r", min=1, max=1), Atom)


# ---------------------------------------------------------------------------
# RuleClassifier — structural conformance (not runtime-checkable)
# ---------------------------------------------------------------------------


class _FakeClassifier:
    """Minimal RuleClassifier[str] implementation for conformance tests."""

    def rule_name(self, rule: str) -> str:
        """Return the rule string itself as its name."""
        return rule

    def is_start_rule(self, rule: str) -> bool:
        """Treat 'root' as the start rule."""
        return rule == "root"

    def kind(self, rule: str) -> Literal["sequence", "alternation", "value_str"]:
        """Classify by convention: rules containing '|' are alternations."""
        if "|" in rule:
            return "alternation"
        return "sequence"

    def alternation_arm_nodes(self, rule: str) -> list[str]:
        """Split alternation rules on '|' to produce arm nodes."""
        return rule.split("|")

    def sequence_body(self, rule: str) -> str:
        """Return the rule itself as its body node."""
        return rule

    def value_str_body(self, rule: str) -> str:
        """Return the rule itself as its value_str body node."""
        return rule

    def single_ruleref(self, arm: str) -> str | None:
        """Return the arm name if it looks like a plain identifier."""
        return arm if arm.isidentifier() else None


def test_rule_classifier_structural_conformance():
    """A correctly-shaped class satisfies RuleClassifier structurally."""
    c: RuleClassifier[str] = _FakeClassifier()
    assert c.rule_name("r") == "r"
    assert c.is_start_rule("root") is True
    assert c.is_start_rule("other") is False
    assert c.kind("seq") == "sequence"
    assert c.kind("a|b") == "alternation"
    assert c.sequence_body("b") == "b"
    assert c.value_str_body("v") == "v"
    assert c.single_ruleref("expr") == "expr"
    assert c.single_ruleref("a|b") is None


# ---------------------------------------------------------------------------
# SequenceConverter — structural conformance
# ---------------------------------------------------------------------------


class _FakeConverter:
    """Minimal SequenceConverter implementation for conformance tests."""

    def value_str_atoms(self, body: object) -> list[Atom]:
        """Wrap the body string in a single LiteralAtom."""
        return [LiteralAtom(value=str(body))]

    def sequence_atoms(
        self,
        body: object,
        parent_class_name: str,
        helpers: HelperRuleRegistry,
    ) -> list[Atom]:
        """Return a LiteralAtom labelled with the parent class name."""
        helpers.all_specs()  # confirm helpers is accessible
        return [LiteralAtom(value=f"{parent_class_name}:{body}")]


def test_sequence_converter_structural_conformance():
    """A correctly-shaped class satisfies SequenceConverter structurally."""
    cv: SequenceConverter[str] = _FakeConverter()
    assert cv.value_str_atoms("hi") == [LiteralAtom(value="hi")]
    result = cv.sequence_atoms("b", "Cls", HelperRuleRegistry())
    assert result == [LiteralAtom(value="Cls:b")]


# ---------------------------------------------------------------------------
# EscapeCodec — ABC subclass conformance
# ---------------------------------------------------------------------------


class _FakeCodec(EscapeCodec):
    """Minimal EscapeCodec subclass for conformance tests."""

    SHORT_ESCAPES = {'"': '"'}
    HEX_ESCAPES = ()


def test_escape_codec_subclass_conformance():
    """A subclass with declared tables inherits a working encode/decode."""
    ec: EscapeCodec = _FakeCodec()
    assert ec.encode('"') == '\\"'
    assert ec.decode('\\"') == '"'


# ---------------------------------------------------------------------------
# FlavourParser — structural conformance
# ---------------------------------------------------------------------------


class _FakeParser:
    """Minimal FlavourParser implementation for conformance tests."""

    def parse(self, text: str) -> list[RuleSpec]:
        """Return empty spec list; validate text is a string."""
        assert isinstance(text, str)
        return []

    def trivia_rules(self) -> frozenset[str]:
        """Return the standard whitespace trivia rule."""
        return frozenset({"ws"})


def test_flavour_parser_structural_conformance():
    """A correctly-shaped class satisfies FlavourParser structurally."""
    p: FlavourParser = _FakeParser()
    assert len(p.parse("root ::= x")) == 0
    assert "ws" in p.trivia_rules()


# ---------------------------------------------------------------------------
# FlavourEmitter — structural conformance
# ---------------------------------------------------------------------------


class _FakeEmitter(FlavourEmitter):
    """Minimal FlavourEmitter subclass for conformance tests."""

    def __init__(self) -> None:
        """Initialise with the no-op codec defined above."""
        super().__init__(escapes=_FakeCodec())

    supports: ClassVar[frozenset[str]] = frozenset({"literal"})


def test_flavour_emitter_structural_conformance():
    """A correctly-shaped subclass satisfies FlavourEmitter structurally."""
    e: FlavourEmitter = _FakeEmitter()
    assert "literal" in e.supports
    spec = RuleSpec(
        "r", "R", "GrammarModel", "sequence", items=[LiteralAtom("x")], field_map={}
    )
    assert e.emit_rule(spec) == 'r ::= "x"'


# ---------------------------------------------------------------------------
# FlavourAdapter — structural conformance
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """Minimal FlavourAdapter implementation for conformance tests."""

    name: str = "fake"
    extensions: tuple[str, ...] = (".fake",)
    parser: FlavourParser = _FakeParser()
    emitter: FlavourEmitter = _FakeEmitter()
    escapes: EscapeCodec = _FakeCodec()
    supports: frozenset[str] = frozenset({"literal"})
    field_handlers: dict[type, FieldHandler] = {}
    lark_handlers: dict[type, LarkHandler] = {}
    transform_handlers: dict[type, TransformHandler] = {}
    to_text_handlers: dict[type, ToTextHandler] = {}

    def emit(self, specs: list[RuleSpec]) -> str:
        """Return a newline-joined list of rule names."""
        return "\n".join(s.rule_name for s in specs)

    def emit_rule(self, spec: RuleSpec) -> str:
        """Return the rule name as a one-line stub."""
        return f"{spec.rule_name} ::= ..."


def test_flavour_adapter_structural_conformance():
    """A correctly-shaped class satisfies FlavourAdapter structurally."""
    a: FlavourAdapter = _FakeAdapter()
    assert a.name == "fake"
    assert ".fake" in a.extensions
    assert "literal" in a.supports
    assert a.emitter is not None
    assert isinstance(a.field_handlers, dict)
    assert isinstance(a.lark_handlers, dict)
    assert isinstance(a.transform_handlers, dict)
    assert isinstance(a.to_text_handlers, dict)
    assert a.emit([]) == ""
    spec = RuleSpec("r", "R", "GrammarModel", "sequence")
    assert a.emit_rule(spec) == "r ::= ..."


# ---------------------------------------------------------------------------
# Handler type aliases are importable
# ---------------------------------------------------------------------------


def test_handler_aliases_are_importable():
    """All per-consumer handler aliases are exported from the protocols module."""
    aliases = [
        AtomEmitHandler,
        FieldHandler,
        LarkHandler,
        TransformHandler,
        ToTextHandler,
    ]
    assert all(a is not None for a in aliases)
