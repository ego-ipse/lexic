"""ε-channel differential: the raw reduce PDA vs the forced Earley completion.

The EBNF sibling of ``test_reduce_differential.py`` (GBNF) — read that file's
docstring first, this one only restates what's EBNF-specific. ``parse_reduced``
(the public product) is PDA-first with an internal Earley fallback — calling
it alone would trivially pass via fallback and never isolate the PDA. This
module instead drives the two routes independently, straight off
``EBNF_FLAVOUR``'s own self-grammar (the meta-grammar EBNF text is parsed
*against*):

- the raw reduce PDA (:func:`~lexic.parsing.pda.runtime.reduce_runtime.pda_reduce`
  over the compiled reduce product, ``fold=None``), and
- the forced Earley completion (:func:`~lexic.parsing.products.earley_reduce`
  over the same lifted, normalised self-grammar the PDA compiled from).

Per ``_reduce_product``, both routes run
``normalize(lift_optional_nullables(grammar))`` — the one grammar
``parse_reduced`` actually ships. This file is the guard that the authored
reduce bodies keep the two routes' IR equivalent on it: PDA-recognised text
must be a subset of Earley-recognised text, and wherever both recognise, the
reduced :class:`IrAst` must be equal.

**The ``ws`` island.** ``EBNF_GRAMMAR``'s ``ws`` rule (``ws = wsunit*``,
``semantic=False``) is an island in the compiled PDA — its own occurrences
delegate to an inline Earley sub-parse rather than a fully compiled
predictive loop (see ``pda/compiler/clones.py``'s ``IslandRef``). An
island-splice boundary decision diverging from the whole-text Earley route's
own choice is *expected* there and is NOT an ε-bug in the reduce channel —
``ws`` is dropped by :data:`EBNF_NOISE` (every non-semantic name is DROP), so
its content never reaches the reduced :class:`IrAst` regardless of exactly
where a splice boundary falls, as long as no *semantic* token's characters
get misattributed to it.

**Known non-ε ambiguity (``EBNF_GRAMMAR`` itself, not a bug in either
route — the EBNF sibling of the ABNF differential's ``rl-cont`` note).**
``rule = rulename, ws, "=", ws, alternation, ws, ";", ws`` names an explicit
``ws`` right after ``alternation``. But *every* ``factor`` arm
(``repetition``/``option``/``quantified``/``multiplied``) already ends in
its own baked-in trailing ``ws`` several rules down (``terminal`` →
``dq``/``sq``, ``ruleref``, ``group``, ``repetition``, ``option`` — each
production ends ``..., ws``) — so ``alternation`` structurally always ends
with a *second*, independently nullable ``ws`` sitting directly against
``rule``'s own, with no literal between them to firewall the two: any actual
whitespace there has no fixed attribution (it could belong to either ``ws``),
which is exactly the shape Earley reports ambiguous
(``"root = \"x\" ;\n"`` → 2 derivations; ``"root=\"x\";\n"``, no interior
whitespace at that seam, → 1). The same doubling recurs at *any* point where
one construct's own baked ``ws`` would otherwise sit last inside
``alternation``, not just at the outermost ``rule`` level — e.g. a
``quantified`` factor with an empty ``quant-opt`` also ends in ``primary``'s
own baked ``ws``, doubling against the *same* outer ``rule`` ``ws`` two
levels down.

The generator sidesteps this by construction: every production that could
end up contributing the LAST characters of a rule's ``alternation`` takes a
``trailing: bool`` parameter (:func:`terminal`, :func:`range_terminal`,
:func:`strprim`, :func:`primary`, :func:`factor`, :func:`concat`,
:func:`altrest`, :func:`alternation`) — ``trailing=False`` forces that one
specific production's own baked ``ws`` draw to empty, so it defers to
``rule``'s own (also-forced-empty) trailing ``ws`` for that final position;
``trailing=True`` (the default everywhere a literal firewalls the
position — ``,``, ``|``, a quantifier symbol, a closing bracket) draws
normally. :func:`rule_line` is the sole ``trailing=False`` caller.

The generator emits ε-heavy EBNF *meta-syntax*: ``{}``/``[]``/``()``
repetition/option/grouping, ``,`` concatenation, ``(* *)`` comments, postfix
``* + ?`` quantifiers, exact repetition (``3 * x``), and ``".."`` terminal
ranges — straight against ``EBNF_GRAMMAR``'s own productions (``rule``,
``alternation``/``altrest``, ``concat``/``catrest``, ``factor``,
``repetition``/``option``/``multiplied``/``quantified``, ``strprim``/
``rangetail``). Rule-name atoms are drawn from a fixed pool and never checked
for definition — the meta-grammar parses EBNF *syntax*, not the semantics of
the grammar it describes, so an undefined ref is syntactically fine here.
Escape sequences (``esc-x``/``esc-u``/... ) are out of the generator's scope
— they add decode-radix coverage, not new ε shapes.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import example, given, settings

from lexic.grammars.ebnf import EBNF_FLAVOUR
from tests.property.reduce_differential_helpers import ReduceDifferential

# ReduceDifferential.earley_grammar runs the same lifted grammar the PDA
# compiles over — the product's actual (grammar, completion) pair (M29).
_diff = ReduceDifferential(EBNF_FLAVOUR)


# ── the generator — ε-heavy EBNF meta-syntax ───────────────────────────────

NAMES = ("root", "aa", "bb", "cc")
LIT_ALPHABET = "abcxyz012 "
COMMENT_ALPHABET = "abc \t"  # anything but "*" — comment body cannot self-close
MAX_DEPTH = 1  # one level of {}/[]/() nesting — bounds shrinking cost


@st.composite
def wschar(draw: st.DrawFn) -> str:
    """One ``wsunit`` whitespace char: ``"\\t" | "\\n" | "\\r" | " "``."""
    return draw(st.sampled_from("\t\n\r "))


@st.composite
def comment(draw: st.DrawFn) -> str:
    """``comment``: ``"(*", (not "*")*, "*)"``."""
    body = draw(st.text(alphabet=COMMENT_ALPHABET, max_size=4))
    return f"(*{body}*)"


@st.composite
def wsunit(draw: st.DrawFn) -> str:
    """``wsunit``: ``wschar | comment`` — the two arms never overlap."""
    return draw(wschar()) if draw(st.booleans()) else draw(comment())


@st.composite
def ws_run(draw: st.DrawFn, min_units: int, max_units: int) -> str:
    """``ws``'s own shape: 0+ (bounded here) ``wsunit``."""
    n = draw(st.integers(min_value=min_units, max_value=max_units))
    return "".join(draw(wsunit()) for _ in range(n))


@st.composite
def dq_literal(draw: st.DrawFn) -> str:
    """A double-quoted terminal body (safe alphabet, no embedded quote —
    never empty, see :func:`terminal`)."""
    body = draw(st.text(alphabet=LIT_ALPHABET, min_size=1, max_size=3))
    return f'"{body}"'


@st.composite
def sq_literal(draw: st.DrawFn) -> str:
    """A single-quoted terminal body (safe alphabet, no embedded quote —
    never empty, see :func:`terminal`)."""
    body = draw(st.text(alphabet=LIT_ALPHABET, min_size=1, max_size=3))
    return f"'{body}'"


@st.composite
def terminal(draw: st.DrawFn, trailing: bool) -> str:
    """``terminal``: ``dq | sq`` — includes its own trailing ``ws`` (both
    ``dq``/``sq`` productions end in ``ws``), unless ``trailing`` is
    ``False`` — see the module docstring's ambiguity note: whichever
    construct ends up LAST inside a rule's ``alternation`` must not draw its
    own trailing ``ws`` there, since that position sits directly against
    ``rule``'s own separate, explicit trailing ``ws`` (before ``";"``) with
    no literal in between to firewall the two. ``trailing`` threads down
    from :func:`rule_line` through every production that could end up last."""
    body = draw(dq_literal()) if draw(st.booleans()) else draw(sq_literal())
    return body + (draw(ws_run(0, 2)) if trailing else "")


@st.composite
def range_terminal(draw: st.DrawFn, trailing: bool) -> str:
    """A terminal usable as a ``..`` range endpoint.

    ``rangetail-opt``'s reduction wraps the endpoint in :class:`IrChr`,
    which requires exactly one glyph — so unlike the general :func:`terminal`
    (any length, used for a plain literal), both a range's low and high
    endpoint must be exactly one character. ``trailing`` — see
    :func:`terminal`.
    """
    ch = draw(st.sampled_from(LIT_ALPHABET))
    quote = '"' if draw(st.booleans()) else "'"
    return f"{quote}{ch}{quote}" + (draw(ws_run(0, 2)) if trailing else "")


@st.composite
def strprim(draw: st.DrawFn, trailing: bool) -> str:
    """``strprim``: ``terminal, rangetail-opt`` — sometimes a ``".." terminal``
    char range, whose two endpoints are :func:`range_terminal` (exactly one
    glyph each — see its docstring). ``trailing`` — see :func:`terminal`;
    only the LAST terminal (the range's ``hi``, when present) needs it, the
    range's ``..`` literal firewalls the ``lo`` end regardless."""
    if not draw(st.booleans()):
        return draw(terminal(trailing))
    lo = draw(range_terminal(True))
    hi = draw(range_terminal(trailing))
    return lo + ".." + draw(ws_run(0, 1)) + hi


@st.composite
def primary(draw: st.DrawFn, depth: int, trailing: bool) -> str:
    """``primary``: ``strprim | group | ruleref`` (``group`` only while
    ``depth`` allows — it wraps a fresh nested ``alternation``). ``trailing``
    — see :func:`terminal`; a nested ``alternation`` inside ``group`` is
    always ``trailing=True`` (firewalled by ``")"``) — only ``group``'s own
    final ``ws`` needs to respect the outer ``trailing``."""
    choices = ["strprim", "ruleref"]
    if depth > 0:
        choices.append("group")
    kind = draw(st.sampled_from(choices))
    if kind == "strprim":
        return draw(strprim(trailing))
    if kind == "ruleref":
        name = draw(st.sampled_from(NAMES))
        return name + (draw(ws_run(0, 2)) if trailing else "")
    ws1 = draw(ws_run(0, 2))
    body = draw(alternation(depth - 1, True))
    ws2 = draw(ws_run(0, 2)) if trailing else ""
    return f"({ws1}{body}){ws2}"


@st.composite
def count(draw: st.DrawFn) -> str:
    """``count``: ``digit+, ws`` — a single digit here, exact-repetition
    scope. Always followed by the literal ``"*"`` in :func:`factor`'s
    ``multiplied`` arm, so its own trailing ``ws`` is always firewalled."""
    return str(draw(st.integers(min_value=0, max_value=9))) + draw(ws_run(0, 1))


@st.composite
def factor(draw: st.DrawFn, depth: int, trailing: bool) -> str:
    """``factor``: ``repetition | option | multiplied | quantified`` —
    ``repetition``/``option`` only while ``depth`` allows (each wraps a fresh
    nested ``alternation``, always ``trailing=True`` — firewalled by ``"}"``/
    ``"]"``; only their own final ``ws`` respects the outer ``trailing``).
    ``quantified``'s ``primary`` gets ``trailing`` only when ``quant-opt``
    (``q-star | q-plus | q-opt | ""``) matches empty — a non-empty symbol
    firewalls ``primary``'s own trailing ``ws`` regardless, and then it is
    ``quant-opt``'s own trailing ``ws`` that must respect the outer
    ``trailing`` instead."""
    choices = ["multiplied", "quantified"]
    if depth > 0:
        choices += ["repetition", "option"]
    kind = draw(st.sampled_from(choices))
    if kind == "quantified":
        symbol = draw(st.sampled_from(("", "*", "+", "?")))
        prim = draw(primary(depth, trailing if not symbol else True))
        if not symbol:
            return prim
        return prim + symbol + (draw(ws_run(0, 1)) if trailing else "")
    if kind == "multiplied":
        return draw(count()) + "*" + draw(ws_run(0, 1)) + draw(primary(depth, trailing))
    ws1 = draw(ws_run(0, 2))
    body = draw(alternation(depth - 1, True))
    ws2 = draw(ws_run(0, 2)) if trailing else ""
    if kind == "repetition":
        return f"{{{ws1}{body}}}{ws2}"
    return f"[{ws1}{body}]{ws2}"


@st.composite
def catrest(draw: st.DrawFn, depth: int, trailing: bool) -> str:
    """``catrest``: ``",", ws, factor``."""
    return "," + draw(ws_run(0, 1)) + draw(factor(depth, trailing))


@st.composite
def concat(draw: st.DrawFn, depth: int, trailing: bool, max_reps: int = 3) -> str:
    """``concat``: ``factor, catrest*`` — only the LAST ``factor`` carries the
    outer ``trailing`` (earlier ones are firewalled by ``catrest``'s own
    ``","``)."""
    n = draw(st.integers(min_value=1, max_value=max_reps))
    parts = [draw(factor(depth, trailing if n == 1 else True))]
    for i in range(1, n):
        parts.append(draw(catrest(depth, trailing if i == n - 1 else True)))
    return "".join(parts)


@st.composite
def altrest(draw: st.DrawFn, depth: int, trailing: bool) -> str:
    """``altrest``: ``"|", ws, concat``."""
    return "|" + draw(ws_run(0, 1)) + draw(concat(depth, trailing))


@st.composite
def alternation(draw: st.DrawFn, depth: int, trailing: bool, max_arms: int = 3) -> str:
    """``alternation``: ``concat, altrest*`` — only the LAST arm carries the
    outer ``trailing`` (earlier arms are firewalled by the next ``altrest``'s
    own ``"|"``)."""
    n_arms = draw(st.integers(min_value=1, max_value=max_arms))
    first = draw(concat(depth, trailing if n_arms == 1 else True))
    rest = [
        draw(altrest(depth, trailing if i == n_arms - 1 else True))
        for i in range(1, n_arms)
    ]
    return first + "".join(rest)


@st.composite
def rule_line(draw: st.DrawFn, name: str) -> str:
    """``rule``: ``rulename, ws, "=", ws, alternation, ws, ";", ws`` — ends in
    its own trailing ``ws``, so consecutive rules need no extra separator.

    ``alternation`` is drawn with ``trailing=False``: see the module
    docstring's ambiguity note — every ``factor`` arm ends in its *own*
    baked-in trailing ``ws`` (down through ``primary``/the bracket
    productions), so a second, independently drawn ``ws`` right after
    ``alternation`` (this rule's own explicit one, forced empty below) has
    no fixed attribution — any non-empty text there is genuinely ambiguous
    between the two. ``trailing=False`` threads down to whichever production
    ends up last, forcing that one specific trailing draw to empty instead.
    """
    ws1 = draw(ws_run(0, 1))
    ws2 = draw(ws_run(0, 1))
    alt = draw(alternation(MAX_DEPTH, False))
    ws4 = draw(ws_run(0, 2))
    return f"{name}{ws1}={ws2}{alt};{ws4}"


@st.composite
def ebnf_text(draw: st.DrawFn) -> str:
    """``ws, rule, rrest*`` over a fixed rule-name pool."""
    n_rules = draw(st.integers(min_value=1, max_value=len(NAMES)))
    names = NAMES[:n_rules]
    leading = draw(ws_run(0, 2))
    lines = [draw(rule_line(name)) for name in names]
    return leading + "".join(lines)


# ── the differential ────────────────────────────────────────────────────────


@example('root = "x";\n')
@example('root = 3 * "x" | aa+;\n')
@example('root = ["x" | aa];\n')
@example('root = {"x", aa};\n')
@example('root = "a".."z";\n')
@example("root = (\"x\" | aa);\n(* c *)\naa = 'y';\n")
@given(text=ebnf_text())
@settings(max_examples=100, deadline=None)
def test_pda_and_earley_agree_on_reduce(text: str) -> None:
    """PDA-recognised text ⊆ Earley-recognised text, and equal where both do.

    Only asserts when the PDA recognises the text — the property is
    one-directional (see the module docstring): the PDA runs the lifted
    self-grammar, Earley the unlifted one, and this is the guard that the
    authored reduce bodies keep the two routes' IR equivalent despite that.
    """
    _diff.assert_agree(text)
