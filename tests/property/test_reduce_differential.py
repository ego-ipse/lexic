"""ε-channel differential: the raw reduce PDA vs the forced Earley completion.

``parse_reduced`` (the public product, :mod:`lexic.parsing.products`) is
PDA-first with an internal Earley fallback — calling it alone would trivially
pass via fallback and never isolate the PDA. This module instead drives the
two routes independently, straight off ``GBNF_FLAVOUR``'s own self-grammar
(the meta-grammar GBNF text is parsed *against*):

- the raw reduce PDA (:func:`~lexic.parsing.pda.runtime.reduce_runtime.parse_pda` over
  the compiled reduce product, ``fold=None``), and
- the forced Earley completion (:func:`~lexic.parsing.products.earley_reduce`
  over the normalised, *unlifted* self-grammar).

Per ``_reduce_product``, the PDA compiles over
``lift_optional_nullables(grammar)`` while ``earley_grammar`` stays
``normalize(grammar)`` (unlifted) — the two routes run different normalised
shapes BY DESIGN, and the authored reduce bodies are what's supposed to make
a lifted-nullable reduction (e.g. an optional ``R?`` producing empty children)
agree with the unlifted route's node-skip. This file is the guard that they
actually do agree: PDA-recognised text must be a subset of Earley-recognised
text, and wherever both recognise, the reduced :class:`IrAst` must be equal.

A divergence is a release-blocking finding, not a test to weaken — see
``zzz_current_work/260712-totality-cleanup/PLAN.md`` Task 6.

The generator emits ε-heavy GBNF *meta-syntax* — optional/star/plus
quantifiers, empty alternation arms, comments and whitespace/noise runs —
straight against ``GBNF_GRAMMAR``'s own productions (``rule``, ``alternation``,
``arm``/``empty-seq``, ``item``/``quant-opt``, ``n``/``nunit``). Rule-name
atoms are drawn from a fixed pool and never checked for definition — the
meta-grammar parses GBNF *syntax*, not the semantics of the grammar it
describes, so an undefined ref is syntactically fine here.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import example, given, settings

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrAst
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import _as_ast, _reduce_product, earley_reduce

_product = _reduce_product(GBNF_FLAVOUR.grammar, GBNF_FLAVOUR.reducer)
_earley_grammar = normalize(GBNF_FLAVOUR.grammar)


def _pda(text: str) -> IrAst | None:
    """The raw reduce PDA in isolation — ``None`` on any :class:`PdaFail`."""
    try:
        return _as_ast(parse_pda(_product.pda, text, None))
    except PdaFail:
        return None


def _earley(text: str) -> IrAst | None:
    """The forced Earley completion — ``None`` on any unparseable text."""
    try:
        return _as_ast(earley_reduce(_earley_grammar, text, GBNF_FLAVOUR.reducer))
    except UnsupportedConstructError:
        return None


# ── the generator — ε-heavy GBNF meta-syntax ───────────────────────────────

_NAMES = ("root", "aa", "bb", "cc")
_LIT_ALPHABET = "abcxyz012 "
_CHARCLASSES = ("[a-z]", "[A-Z]", "[0-9]", "[abc]", "[^xyz]", "[]", "[^]")
_QUANTS = ("", "?", "*", "+")


@st.composite
def _noise(draw: st.DrawFn, min_units: int, max_units: int) -> str:
    """``n``'s own shape: 0+ (or 1+) of ``wschar`` / ``comment-line``."""
    count = draw(st.integers(min_value=min_units, max_value=max_units))
    units = []
    for _ in range(count):
        if draw(st.booleans()):
            units.append(draw(st.sampled_from(" \t\r\n")))
        else:
            body = draw(st.text(alphabet="abc ", max_size=4))
            units.append(f"#{body}\n")
    return "".join(units)


@st.composite
def _literal(draw: st.DrawFn) -> str:
    body = draw(st.text(alphabet=_LIT_ALPHABET, max_size=3))
    return f'"{body}"'


@st.composite
def _atom(draw: st.DrawFn) -> str:
    kind = draw(st.integers(min_value=0, max_value=2))
    if kind == 0:
        return draw(_literal())
    if kind == 1:
        return draw(st.sampled_from(_CHARCLASSES))
    return draw(st.sampled_from(_NAMES))


@st.composite
def _item(draw: st.DrawFn) -> str:
    """An ``atom`` plus an optional quantifier — ``ws-quant`` allows noise
    before the quantifier symbol, the ε-shape this differential targets."""
    atom = draw(_atom())
    quant = draw(st.sampled_from(_QUANTS))
    if not quant:
        return atom
    gap = draw(_noise(min_units=0, max_units=1))
    return f"{atom}{gap}{quant}"


@st.composite
def _sequence(draw: st.DrawFn, max_items: int = 3) -> str:
    """A ``sequence``, or the ``empty-seq`` arm when ``n_items`` is 0."""
    n_items = draw(st.integers(min_value=0, max_value=max_items))
    if n_items == 0:
        return ""
    leading = draw(_noise(min_units=0, max_units=2))
    parts = [leading]
    for i in range(n_items):
        if i > 0:
            parts.append(draw(_noise(min_units=1, max_units=3)))
        parts.append(draw(_item()))
    return "".join(parts)


@st.composite
def _alternation(draw: st.DrawFn, max_arms: int = 3) -> str:
    """``arm (n(0) "|" arm)*`` — arms (incl. empty ones) joined by ``|``."""
    n_arms = draw(st.integers(min_value=1, max_value=max_arms))
    arms = [draw(_sequence()) for _ in range(n_arms)]
    out = [arms[0]]
    for arm in arms[1:]:
        pre_bar = draw(_noise(min_units=0, max_units=1))
        out.append(f"{pre_bar}|{arm}")
    return "".join(out)


@st.composite
def _rule_line(draw: st.DrawFn, name: str) -> str:
    """``rulename n(0) "::=" alternation``."""
    pre_eq = draw(_noise(min_units=0, max_units=1))
    alt = draw(_alternation())
    return f"{name}{pre_eq}::={alt}"


@st.composite
def gbnf_text(draw: st.DrawFn) -> str:
    """``n(0) rule (n rules-rest)* n(0)`` over a fixed rule-name pool."""
    n_rules = draw(st.integers(min_value=1, max_value=len(_NAMES)))
    names = _NAMES[:n_rules]
    leading = draw(_noise(min_units=0, max_units=2))
    lines = [draw(_rule_line(name)) for name in names]
    body = lines[0]
    for line in lines[1:]:
        body += draw(_noise(min_units=1, max_units=2)) + line
    trailing = draw(_noise(min_units=0, max_units=2))
    return leading + body + trailing


# ── the differential ────────────────────────────────────────────────────────


@example('root ::= aa?\naa ::= "x" |\n')
@example("root ::= |\n")
@example("root ::= aa* | bb+ |\n# trailing comment\n")
@given(text=gbnf_text())
@settings(max_examples=100, deadline=None)
def test_pda_and_earley_agree_on_reduce(text: str) -> None:
    """PDA-recognised text ⊆ Earley-recognised text, and equal where both do.

    Only asserts when the PDA recognises the text — the property is
    one-directional (see the module docstring): the PDA runs the lifted
    self-grammar, Earley the unlifted one, and this is the guard that the
    authored reduce bodies keep the two routes' IR equivalent despite that.
    """
    pda_ir = _pda(text)
    if pda_ir is None:
        return
    earley_ir = _earley(text)
    assert earley_ir is not None, f"PDA recognised text Earley rejected:\n{text!r}"
    assert pda_ir == earley_ir, (
        f"PDA/Earley reduce diverged on:\n{text!r}\n"
        f"  pda:    {pda_ir!r}\n"
        f"  earley: {earley_ir!r}"
    )
