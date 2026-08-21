"""ε-heavy property coverage for ABNF artefact reduction.

The shared harness reduces generated ABNF twice. Accepted samples must reach
an identical raw AST.

The generator emits ε-heavy ABNF *meta-syntax*: ``c-wsp`` line folding (a
bare ``wsp`` char, or a ``c-nl`` — comment / CRLF — followed by one),
bracketed ``[...]`` options, counted repetition (``N``, ``N*M``, ``N*``,
``*M``, ``*``), and incremental ``=/`` rule extension — straight against
``ABNF_GRAMMAR``'s own productions (``rule``, ``alternation``,
``concatenation``/``catrest``, ``repetition``/``rep-core``/``option``,
``repeat``/``repeat-num``/``repeat-nolo``). Rule-name atoms are drawn from a
fixed pool and never checked for definition — the meta-grammar parses ABNF
*syntax*, not the semantics of the grammar it describes, so an undefined ref
is syntactically fine here. ``prose``/``cs-string``/``ci-string``/``num-val``
element forms are out of the generator's scope: ``prose`` is a declared
formal-semantics refusal in ``ABNF_REDUCTIONS`` (both routes would raise
identically, so it exercises no new ε shape), and the other two don't add
ε-heavy coverage beyond what ``char-val``/``rulename``/``group`` already
give this differential.

**Known non-ε ambiguity (RFC 5234's own ``rulelist`` grammar, not a bug in
either route):** ``rl-cont = *c-wsp c-nl *filler rule`` — when the text
between two rule-lines has the shape ``c-nl wsp c-nl`` (a ``wsp`` sandwiched
between two line-endings), the middle ``wsp`` can attach either to a
``*c-wsp`` fold (``c-wsp``'s ``c-nl wsp`` arm) ending just before the second
``c-nl``, or to ``*filler``'s own ``blank`` (``*wsp crlf``) starting just
after the first — two distinct derivations of the same text, genuinely
ambiguous per the grammar as authored. Earley correctly reports the
ambiguity (raising, so :func:`earley` returns ``None``); the PDA's
predictive descent resolves it one way and recognises the text — which
would read as a false "PDA recognised text Earley rejected" divergence. The
generator sidesteps the shape by construction rather than special-casing the
test: :func:`rl_sep`'s own ``*c-wsp`` prefix draws bare (unfolded) ``wsp``
only (:func:`bare_wsp_run`), and ``blank`` never carries leading ``wsp``
(:func:`blank_line`) — see each function's docstring. The general, fold-
capable :func:`c_wsp_run` stays in full use everywhere else (inside rule
bodies), where no competing ``filler`` production sits nearby to create the
same overlap.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import example, given, settings

from lexic.grammars.abnf import ABNF_FLAVOUR
from tests.property.lexic.reduce_differential_helpers import ReduceDifferential

# ReduceDifferential.earley_grammar runs the same lifted grammar the PDA
# compiles over — the product's actual (grammar, completion) pair (M29).
_diff = ReduceDifferential(ABNF_FLAVOUR)


# ── the generator — ε-heavy ABNF meta-syntax ───────────────────────────────

NAMES = ("root", "aa", "bb", "cc")
LIT_ALPHABET = "abcxyz012 "
MAX_DEPTH = 1  # one level of [...] / (...) nesting — bounds shrinking cost


@st.composite
def crlf(draw: st.DrawFn) -> str:
    """``crlf``'s own shape: an optional ``cr`` then ``lf``."""
    return "\r\n" if draw(st.booleans()) else "\n"


@st.composite
def comment_line(draw: st.DrawFn) -> str:
    """``comment``'s own shape: ``";" *cchar crlf``."""
    body = draw(st.text(alphabet="abc ", max_size=4))
    return f";{body}" + draw(crlf())


@st.composite
def c_nl(draw: st.DrawFn) -> str:
    """``c-nl``'s own shape: ``comment / crlf``."""
    return draw(comment_line()) if draw(st.booleans()) else draw(crlf())


@st.composite
def wsp_char(draw: st.DrawFn) -> str:
    """``wsp``'s own shape: ``sp / htab``."""
    return draw(st.sampled_from(" \t"))


@st.composite
def c_wsp_unit(draw: st.DrawFn) -> str:
    """``c-wsp``'s own shape: a bare ``wsp``, or a folded ``c-nl wsp``."""
    if draw(st.booleans()):
        return draw(wsp_char())
    return draw(c_nl()) + draw(wsp_char())


@st.composite
def c_wsp_run(draw: st.DrawFn, min_units: int, max_units: int) -> str:
    """``*c-wsp`` / ``1*c-wsp`` — a run of ``c_wsp_unit``."""
    count = draw(st.integers(min_value=min_units, max_value=max_units))
    return "".join(draw(c_wsp_unit()) for _ in range(count))


@st.composite
def bare_wsp_run(draw: st.DrawFn, min_units: int, max_units: int) -> str:
    """A run of bare ``wsp`` chars only — no ``c-nl`` fold.

    Used only where a fold immediately abuts a *separately drawn* ``c-nl``
    (:func:`rl_sep`'s own ``*c-wsp`` prefix): ``c-wsp``'s fold form is
    ``c-nl wsp``, and a fold ending right before another ``c-nl`` produces the
    ``c-nl wsp c-nl`` shape ``rl-cont``'s grammar is genuinely ambiguous over
    (the trailing ``wsp`` can attach to the fold *or* to a following
    ``filler``'s ``blank``) — see the module docstring's ambiguity note. Plain
    (unfolded) ``c-wsp`` runs elsewhere carry no such neighbour and stay on
    the general :func:`c_wsp_run`.
    """
    count = draw(st.integers(min_value=min_units, max_value=max_units))
    return "".join(draw(wsp_char()) for _ in range(count))


@st.composite
def blank_line(draw: st.DrawFn) -> str:
    """``blank``'s own shape: ``*wsp crlf`` — no leading ``wsp`` here either,
    for the same ``c-nl wsp c-nl`` reason :func:`bare_wsp_run` documents (a
    leading ``wsp`` right after ``rl-cont``'s mandatory ``c-nl`` is the other
    half of that ambiguous shape)."""
    return draw(crlf())


@st.composite
def filler_unit(draw: st.DrawFn) -> str:
    """``filler``'s own shape: ``comment / blank``."""
    return draw(comment_line()) if draw(st.booleans()) else draw(blank_line())


@st.composite
def filler_run(draw: st.DrawFn, min_units: int, max_units: int) -> str:
    """``*filler`` — a run of ``filler_unit``."""
    count = draw(st.integers(min_value=min_units, max_value=max_units))
    return "".join(draw(filler_unit()) for _ in range(count))


@st.composite
def literal(draw: st.DrawFn) -> str:
    """A short double-quoted ABNF ``char-val`` (RFC 7405 case-insensitive form)."""
    body = draw(st.text(alphabet=LIT_ALPHABET, max_size=3))
    return f'"{body}"'


@st.composite
def bracketed(draw: st.DrawFn, open_c: str, close_c: str, depth: int) -> str:
    """A ``[...]``/``(...)`` wrapper: brackets around ``*c-wsp alternation *c-wsp``."""
    ws1 = draw(c_wsp_run(0, 2))
    body = draw(alternation(depth))
    ws2 = draw(c_wsp_run(0, 2))
    return f"{open_c}{ws1}{body}{ws2}{close_c}"


@st.composite
def element(draw: st.DrawFn, depth: int) -> str:
    """``element``: a literal, rule-name reference, or (if ``depth`` allows) a
    parenthesised ``group``."""
    choices = ["literal", "ruleref"]
    if depth > 0:
        choices.append("group")
    kind = draw(st.sampled_from(choices))
    if kind == "literal":
        return draw(literal())
    if kind == "ruleref":
        return draw(st.sampled_from(NAMES))
    return draw(bracketed("(", ")", depth - 1))


def _digit(draw: st.DrawFn) -> str:
    """One ``decits``-sized draw: a single decimal digit."""
    return str(draw(st.integers(min_value=0, max_value=9)))


@st.composite
def repeat(draw: st.DrawFn) -> str:
    """``repeat``: exact ``N``, ranged ``N*M``, open-hi ``N*``, ``*M``, or ``*``."""
    kind = draw(
        st.sampled_from(("exact", "range", "open-hi", "nolo-bounded", "nolo-open"))
    )
    if kind == "exact":
        return _digit(draw)
    if kind == "range":
        return f"{_digit(draw)}*{_digit(draw)}"
    if kind == "open-hi":
        return f"{_digit(draw)}*"
    if kind == "nolo-bounded":
        return f"*{_digit(draw)}"
    return "*"


@st.composite
def repeat_opt(draw: st.DrawFn) -> str:
    """``repeat-opt``: ``[repeat]`` — empty, or one ``repeat``."""
    if draw(st.booleans()):
        return ""
    return draw(repeat())


@st.composite
def rep_core(draw: st.DrawFn, depth: int) -> str:
    """``rep-core``: ``repeat-opt element`` — no gap between the two."""
    return draw(repeat_opt()) + draw(element(depth))


@st.composite
def repetition(draw: st.DrawFn, depth: int) -> str:
    """``repetition``: ``rep-core / option`` (option only while ``depth`` allows)."""
    if depth > 0 and draw(st.booleans()):
        return draw(bracketed("[", "]", depth - 1))
    return draw(rep_core(depth))


@st.composite
def concatenation(draw: st.DrawFn, depth: int, max_reps: int = 3) -> str:
    """``concatenation``: ``repetition (1*c-wsp repetition)*`` (``catrest``)."""
    n = draw(st.integers(min_value=1, max_value=max_reps))
    parts = [draw(repetition(depth))]
    for _ in range(n - 1):
        parts.append(draw(c_wsp_run(1, 3)))
        parts.append(draw(repetition(depth)))
    return "".join(parts)


@st.composite
def alt_rest(draw: st.DrawFn, depth: int) -> str:
    """``altrest``: ``*c-wsp "/" *c-wsp concatenation``."""
    pre = draw(c_wsp_run(0, 1))
    post = draw(c_wsp_run(0, 1))
    return f"{pre}/{post}" + draw(concatenation(depth))


@st.composite
def alternation(draw: st.DrawFn, depth: int, max_arms: int = 3) -> str:
    """``alternation``: ``concatenation (altrest)*``."""
    n_arms = draw(st.integers(min_value=1, max_value=max_arms))
    first = draw(concatenation(depth))
    rest = [draw(alt_rest(depth)) for _ in range(n_arms - 1)]
    return first + "".join(rest)


@st.composite
def rule_line(draw: st.DrawFn, name: str, defined: str) -> str:
    """``rule``: ``rulename *c-wsp defined *c-wsp alternation``."""
    pre = draw(c_wsp_run(0, 1))
    post = draw(c_wsp_run(0, 1))
    alt = draw(alternation(MAX_DEPTH))
    return f"{name}{pre}{defined}{post}{alt}"


@st.composite
def rl_sep(draw: st.DrawFn) -> str:
    """``rl-cont``'s own separator shape: ``*c-wsp c-nl *filler`` before a
    ``rule``. ``*c-wsp`` here draws bare (unfolded) ``wsp`` only — see
    :func:`bare_wsp_run`."""
    pre = draw(bare_wsp_run(0, 2))
    return pre + draw(c_nl()) + draw(filler_run(0, 1))


@st.composite
def abnf_text(draw: st.DrawFn) -> str:
    """``*filler rule (rl-cont)* *c-wsp *1c-nl`` over a fixed rule-name pool —
    each subsequent name is a fresh ``"="`` rule, plus (sometimes) one
    incremental ``"=/"`` extension of an already-defined name."""
    n_rules = draw(st.integers(min_value=1, max_value=len(NAMES)))
    names = list(NAMES[:n_rules])
    leading = draw(filler_run(0, 2))
    lines = [draw(rule_line(names[0], "="))]
    for name in names[1:]:
        lines.append(draw(rl_sep()))
        lines.append(draw(rule_line(name, "=")))
    if draw(st.booleans()):
        extend_name = draw(st.sampled_from(names))
        lines.append(draw(rl_sep()))
        lines.append(draw(rule_line(extend_name, "=/")))
    trailing_ws = draw(c_wsp_run(0, 2))
    trailing_nl = draw(c_nl()) if draw(st.booleans()) else ""
    return leading + "".join(lines) + trailing_ws + trailing_nl


# ── the differential ────────────────────────────────────────────────────────


@example('root = "x"\n')
@example('root = 2*4"x" / 3aa\n')
@example('root = ["x" / aa]\n')
@example('root = "x"\nroot =/ "y"\n')
@example('root = ("x" / aa)\n')
@given(text=abnf_text())
@settings(max_examples=100, deadline=None)
def test_pda_and_earley_agree_on_reduce(text: str) -> None:
    """PDA-recognised text ⊆ Earley-recognised text, and equal where both do.

    Only asserts when the PDA recognises the text — the property is
    one-directional (see the module docstring): the PDA runs the lifted
    self-grammar, Earley the unlifted one, and this is the guard that the
    authored reduce bodies keep the two routes' IR equivalent despite that.
    """
    _diff.assert_agree(text)
