"""The demo EBNF-subset flavour — cross-flavour equivalence (exit criterion 4).

``grammars/ebnf.flavour.ir`` is a flavour added as PURE TEXT (no shipped Python
module): a small EBNF-subset self-grammar with lambda-free reductions, loaded
via :func:`load_flavour_from_path`. It proves flavours-from-text end to end —
``resources/ground_truth/arithmetic.ebnf`` parses to canonical IR EQUAL to the
GBNF sibling ``arithmetic.gbnf``'s, and the flavour round-trips its own emitted
text.

The EBNF surface is ISO-family (``=``/``;`` rules, ``,`` concatenation,
``(* *)`` comments, ``..`` char ranges, ``{ }``/``[ ]`` repetition/option,
postfix ``* + ?``, ``( )`` grouping) — genuinely distinct from GBNF, yet
canonicalisation collapses both to one flavour-agnostic tree.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.compile.notation.loader import load_flavour_from_path
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir.canonical import canonicalize
from lexic.ir.flavour import IrFlavour
from tests.paths import GRAMMARS, GROUND_TRUTH


def ebnf() -> IrFlavour:
    """The demo EBNF flavour, loaded from its shipped manifest."""
    return load_flavour_from_path(GRAMMARS / "ebnf.flavour.ir")


def gbnf_arithmetic_canonical():
    """The canonicalized GBNF arithmetic ground-truth grammar."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    return canonicalize(parse_grammar(text, GBNF_FLAVOUR))


def ebnf_arithmetic_canonical():
    """The canonicalized EBNF-demo arithmetic grammar."""
    text = (GROUND_TRUTH / "arithmetic.ebnf").read_text(encoding="utf-8")
    return canonicalize(parse_grammar(text, ebnf()))


def test_ebnf_flavour_loads_from_pure_text() -> None:
    """The demo flavour is a loadable manifest with no shipped Python module."""
    flavour = ebnf()
    assert isinstance(flavour, IrFlavour)
    assert flavour.name == "ebnf"
    assert flavour.extensions == (".ebnf",)


def test_ebnf_arithmetic_canonical_equals_gbnf() -> None:
    """Exit criterion 4: arithmetic.ebnf → the SAME canonical IR as arithmetic.gbnf."""
    assert ebnf_arithmetic_canonical() == gbnf_arithmetic_canonical()


def test_ebnf_arithmetic_canonical_repr_equals_gbnf() -> None:
    """The repr (canonical codegen form) matches too — no hidden semantic drift."""
    assert repr(ebnf_arithmetic_canonical()) == repr(gbnf_arithmetic_canonical())


def test_ebnf_emit_round_trips() -> None:
    """The flavour emits its own canonical IR back to text that reparses equal."""
    flavour = ebnf()
    canonical = gbnf_arithmetic_canonical()
    emitted = flavour.apply(canonical)
    reparsed = canonicalize(parse_grammar(emitted, flavour))
    assert reparsed == canonical
