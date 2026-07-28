# tests/unit/lexic/ir/test_flavour.py
"""IrFlavour ABC contract tests — the R1 surface (metadata + grammar/reducer).

After the Lark cutover the flavour carries **zero methods** beyond the
inherited emitter protocol: only the R1 ClassVars (``name``, ``extensions``,
``line_comment``, ``block_comment``, ``escapes``, ``grammar``, ``reducer``)
and the emitter
``actions``.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_ESCAPES, ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_ESCAPES, GBNF_FLAVOUR
from lexic.ir.action.walk import IrEmitter
from lexic.ir.flavour import IrEscape, IrEscapePoint, IrFlavour, IrSpellable
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrAst,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spine.records import IrSeq
from lexic.ir.spine.scalars import IrInt, IrStr
from lexic.ir.spine.spine import IrNone
from lexic.ir.text.escapes import EscapeCodec


def test_concrete_flavour_with_required_attrs_works():
    """A concrete subclass supplying the R1 metadata carries it on the class."""

    class _Fake(IrFlavour):
        name = "fake"
        extensions = (".fake",)
        escapes = EscapeCodec()
        line_comment = "#"

    assert _Fake.name == "fake"
    assert _Fake.extensions == (".fake",)
    assert _Fake.line_comment == "#"


def test_default_line_comment_is_empty_string():
    """line_comment defaults to empty string when not set by a subclass."""

    class _F(IrFlavour):
        name = "f"
        extensions = ()
        escapes = EscapeCodec()

    assert _F.line_comment == ""


def test_irflavour_is_subclass_of_iremitter():
    """IrFlavour inherits from IrEmitter."""
    assert issubclass(IrFlavour, IrEmitter)


def test_irflavour_declares_grammar_and_reducer_class_var_annotations():
    """IrFlavour annotates grammar/reducer as ClassVars (self-grammar + parse Reducer)."""
    annotations = IrFlavour.__annotations__
    assert "grammar" in annotations
    assert "reducer" in annotations


def test_irflavour_grammar_and_reducer_carry_no_default_on_the_abc():
    """grammar/reducer are annotation-only on the ABC — unlike line_comment
    (which defaults to ''), no concrete value lives on IrFlavour itself; each
    concrete flavour singleton must supply its own."""
    assert "grammar" not in IrFlavour.__dict__
    assert "reducer" not in IrFlavour.__dict__


# ── R1 gate: zero methods beyond the inherited emitter protocol ───────

# The only public names a flavour class may define beyond what IrEmitter
# provides: the R1 metadata ClassVars, grammar/reducer, and the emitter
# actions. (Underscore-prefixed names are dataclass/ABC machinery — the
# inherited emitter protocol — not flavour-authored surface.)
R1_ALLOWED = frozenset(
    {
        "name",
        "extensions",
        "line_comment",
        "escapes",
        "grammar",
        "reducer",
        "actions",
        # flavour-layout additions (2026-07-18): the width-aware emitter
        # protocol refinement + the core-rules prelude data ClassVar.
        "apply",
        "core_rules",
        # a flavour declares its comment syntax so DIRECTIVES are not a
        # privilege of the surfaces that happen to have a line comment: EBNF
        # has only `(* *)`, and could carry no @directive at all until it could
        # say so.
        "block_comment",
    }
)

# Public names the inherited emitter protocol already provides (e.g. the
# dispatch ``default``) — allowed by R1's "beyond IrEmitter inheritance".
INHERITED = frozenset(n for n in dir(IrEmitter) if not n.startswith("_"))

# The Lark-era flavour methods that R1 deletes and nothing replaces.
DELETED_MEMBERS = (
    "parse_quantifier",
    "parse_charclass",
    "normalize_literal",
    "meta_grammar",
)


def own_public_names(cls: type) -> set[str]:
    """Public names defined directly on ``cls`` — excludes dunders and the
    underscore-prefixed dataclass/ABC internals that the emitter base adds."""
    return {name for name in vars(cls) if not name.startswith("_")}


@pytest.mark.parametrize(
    "flavour_cls",
    [IrFlavour, type(GBNF_FLAVOUR), type(ABNF_FLAVOUR)],
    ids=["IrFlavour", "GbnfFlavour", "AbnfFlavour"],
)
def test_flavour_defines_no_members_beyond_r1_surface(flavour_cls: type):
    """The ABC and both concrete flavours define only the R1 ClassVars + actions.

    Any stray callable (a ``parse_quantifier``/``parse_charclass``-style
    method) or extra attribute beyond what IrEmitter provides would show up
    here — R1 mandates none.
    """
    stray = own_public_names(flavour_cls) - R1_ALLOWED - INHERITED
    assert not stray, f"{flavour_cls.__name__} defines beyond R1 surface: {stray}"


@pytest.mark.parametrize(
    "flavour_cls",
    [IrFlavour, type(GBNF_FLAVOUR), type(ABNF_FLAVOUR)],
    ids=["IrFlavour", "GbnfFlavour", "AbnfFlavour"],
)
def test_flavour_has_no_deleted_lark_members(flavour_cls: type):
    """The Lark-era methods are gone (not even inherited) — R1 replaces none."""
    present = [m for m in DELETED_MEMBERS if hasattr(flavour_cls, m)]
    assert not present, f"{flavour_cls.__name__} still exposes: {present}"


# ── IrEscape ──────────────────────────────────────────────────────────


def test_irescape_encodes_via_gbnf_flavour_codec():
    """IrEscape.eval under GBNF_FLAVOUR encodes a str-leaf via GBNF_ESCAPES."""
    node = IrLiteral('a"b\n')
    result = IrEscape().eval(GBNF_FLAVOUR, node, ())
    assert result == GBNF_ESCAPES.encode('a"b\n')
    assert isinstance(result, IrStr)


def test_irescape_result_is_irstr():
    """IrEscape.eval returns an IrStr (not just str)."""
    result = IrEscape().eval(GBNF_FLAVOUR, IrLiteral("abc"), ())
    assert isinstance(result, IrStr)


def test_irescape_dispatcher_without_escapes_raises():
    """IrEscape.eval raises UnsupportedConstructError when the dispatcher has no escapes."""
    with pytest.raises(UnsupportedConstructError):
        IrEscape().eval(IrNone, IrLiteral("a"), ())


def test_irescape_non_string_node_raises():
    """IrEscape.eval raises UnsupportedConstructError for a non-str-leaf node."""
    with pytest.raises(UnsupportedConstructError):
        IrEscape().eval(GBNF_FLAVOUR, IrQuantifier(1, 1), ())


def test_irescape_repr_is_codegen():
    """IrEscape repr is 'IrEscape()' — fieldless leaf."""
    assert repr(IrEscape()) == "IrEscape()"


# ── IrEscapePoint ─────────────────────────────────────────────────────


def test_irescapepoint_encodes_via_gbnf_flavour_codec():
    """IrEscapePoint.eval under GBNF_FLAVOUR spells a code-point leaf via
    GBNF_ESCAPES.encode_point — the class-member sibling of IrEscape."""
    result = IrEscapePoint().eval(GBNF_FLAVOUR, IrChr(10), ())
    assert result == GBNF_ESCAPES.encode_point(10)
    assert isinstance(result, IrStr)


def test_irescapepoint_result_is_irstr():
    """IrEscapePoint.eval returns an IrStr (not just str)."""
    result = IrEscapePoint().eval(GBNF_FLAVOUR, IrChr(ord("a")), ())
    assert isinstance(result, IrStr)


def test_irescapepoint_dispatcher_without_escapes_raises():
    """IrEscapePoint.eval raises UnsupportedConstructError when the
    dispatcher has no escapes codec."""
    with pytest.raises(UnsupportedConstructError):
        IrEscapePoint().eval(IrNone, IrChr(10), ())


def test_irescapepoint_non_codepoint_node_raises():
    """IrEscapePoint.eval raises UnsupportedConstructError for a focus that
    isn't an integer code point."""
    with pytest.raises(UnsupportedConstructError):
        IrEscapePoint().eval(GBNF_FLAVOUR, IrLiteral("a"), ())


def test_irescapepoint_repr_is_codegen():
    """IrEscapePoint repr is 'IrEscapePoint()' — fieldless leaf."""
    assert repr(IrEscapePoint()) == "IrEscapePoint()"


# ── IrSpellable ───────────────────────────────────────────────────────


def test_irspellable_true_via_abnf_flavour_codec():
    """IrSpellable.eval under ABNF_FLAVOUR tests the focus against
    ABNF_ESCAPES' QUOTE_SAFE ranges — true for plain printable ASCII."""
    result = IrSpellable().eval(ABNF_FLAVOUR, IrLiteral("abc"), ())
    assert result == IrInt(1)
    assert isinstance(result, IrInt)


def test_irspellable_false_for_unsafe_char():
    """IrSpellable.eval is false when a character falls outside QUOTE_SAFE
    (RFC 7405 char-val excludes the quote)."""
    result = IrSpellable().eval(ABNF_FLAVOUR, IrLiteral('a"b'), ())
    assert result == IrInt(0)


def test_irspellable_matches_codec_spellable():
    """IrSpellable.eval matches the dispatcher's own codec.spellable call."""
    result = IrSpellable().eval(ABNF_FLAVOUR, IrLiteral('a"b'), ())
    assert bool(result) == ABNF_ESCAPES.spellable('a"b')


def test_irspellable_dispatcher_without_escapes_raises():
    """IrSpellable.eval raises UnsupportedConstructError when the dispatcher
    has no escapes codec."""
    with pytest.raises(UnsupportedConstructError):
        IrSpellable().eval(IrNone, IrLiteral("a"), ())


def test_irspellable_non_string_node_raises():
    """IrSpellable.eval raises UnsupportedConstructError for a non-str-leaf
    focus."""
    with pytest.raises(UnsupportedConstructError):
        IrSpellable().eval(ABNF_FLAVOUR, IrQuantifier(1, 1), ())


def test_irspellable_repr_is_codegen():
    """IrSpellable repr is 'IrSpellable()' — fieldless leaf."""
    assert repr(IrSpellable()) == "IrSpellable()"


# ── IrFlavour.apply(root, width=...) — the width-aware emitter protocol ──


def wide_rule() -> IrRule:
    """A rule whose alternation is wide enough to overflow width 88 flat."""
    names = [f"alternative-name-number-{i}" for i in range(6)]
    arms = [IrSequence(IrItem(IrRuleRef(name))) for name in names]
    return IrRule("wide-rule", IrAlternation(*arms))


def test_apply_default_width_wraps_a_long_rule():
    """apply()'s default width=88 breaks a rule too wide to fit one line."""
    result = GBNF_FLAVOUR.apply(wide_rule())
    assert "\n" in result
    assert all(len(line) <= 88 for line in result.splitlines())


def test_apply_width_none_is_flat_and_equals_the_pre_layout_single_line():
    """width=None renders the doc flat — one line, matching the join-by-space
    single-line form a str-tier (pre-layout) emitter would have produced."""
    rule = wide_rule()
    flat = GBNF_FLAVOUR.apply(rule, width=None)
    assert "\n" not in flat
    expected = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    assert flat == expected


def test_apply_wrapped_and_flat_differ_for_a_wide_rule():
    """The same rule renders differently at the default width vs width=None."""
    rule = wide_rule()
    assert GBNF_FLAVOUR.apply(rule) != GBNF_FLAVOUR.apply(rule, width=None)


def test_apply_narrow_rule_is_unaffected_by_width():
    """A rule that already fits stays a single line at any width."""
    rule = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    assert GBNF_FLAVOUR.apply(rule) == GBNF_FLAVOUR.apply(rule, width=None)


def test_apply_on_a_str_tier_result_passes_through_unchanged():
    """A str-tier emission (e.g. a bare IrQuantifier) ignores width entirely
    — apply() only renders when the action table produces an IrDoc."""
    result_default = GBNF_FLAVOUR.apply(IrQuantifier(2, 5))
    result_flat = GBNF_FLAVOUR.apply(IrQuantifier(2, 5), width=None)
    assert result_default == result_flat == "{2,5}"
    assert isinstance(result_default, IrStr)


def test_apply_on_an_ast_wraps_each_wide_rule_independently():
    """apply() on a whole IrAst wraps each rule's own body against width,
    joined by hard inter-rule breaks."""
    ast = IrAst(IrSeq(wide_rule()), "wide-rule")
    result = GBNF_FLAVOUR.apply(ast)
    assert all(len(line) <= 88 for line in result.splitlines())
    assert result.count("wide-rule ::=") == 1
