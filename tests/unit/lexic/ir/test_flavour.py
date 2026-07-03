# tests/unit/lexic/ir/test_flavour.py
"""IrFlavour ABC contract tests — the R1 surface (metadata + grammar/reducer).

After the Lark cutover the flavour carries **zero methods** beyond the
inherited emitter protocol: only the R1 ClassVars (``name``, ``extensions``,
``line_comment``, ``escapes``, ``grammar``, ``reducer``) and the emitter
``actions``.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_ESCAPES, GBNF_FLAVOUR
from lexic.ir.base import IrNone, IrStr
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.flavour import IrEscape, IrFlavour
from lexic.ir.nodes import IrLiteral, IrQuantifier
from lexic.ir.walk import IrEmitter


def test_concrete_flavour_with_required_attrs_works():
    """A concrete subclass supplying the R1 metadata carries it on the class."""

    class _Fake(IrFlavour):
        name = "fake"
        extensions = (".fake",)
        escapes = CANONICAL_ESCAPES
        line_comment = "#"

    assert _Fake.name == "fake"
    assert _Fake.extensions == (".fake",)
    assert _Fake.line_comment == "#"


def test_default_line_comment_is_empty_string():
    """line_comment defaults to empty string when not set by a subclass."""

    class _F(IrFlavour):
        name = "f"
        extensions = ()
        escapes = CANONICAL_ESCAPES

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
_R1_ALLOWED = frozenset(
    {"name", "extensions", "line_comment", "escapes", "grammar", "reducer", "actions"}
)

# Public names the inherited emitter protocol already provides (e.g. the
# dispatch ``default``) — allowed by R1's "beyond IrEmitter inheritance".
_INHERITED = frozenset(n for n in dir(IrEmitter) if not n.startswith("_"))

# The Lark-era flavour methods that R1 deletes and nothing replaces.
_DELETED_MEMBERS = (
    "parse_quantifier",
    "parse_charclass",
    "normalize_literal",
    "meta_grammar",
)


def _own_public_names(cls: type) -> set[str]:
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
    stray = _own_public_names(flavour_cls) - _R1_ALLOWED - _INHERITED
    assert not stray, f"{flavour_cls.__name__} defines beyond R1 surface: {stray}"


@pytest.mark.parametrize(
    "flavour_cls",
    [IrFlavour, type(GBNF_FLAVOUR), type(ABNF_FLAVOUR)],
    ids=["IrFlavour", "GbnfFlavour", "AbnfFlavour"],
)
def test_flavour_has_no_deleted_lark_members(flavour_cls: type):
    """The Lark-era methods are gone (not even inherited) — R1 replaces none."""
    present = [m for m in _DELETED_MEMBERS if hasattr(flavour_cls, m)]
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
