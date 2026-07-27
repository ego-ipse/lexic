# pylint: disable=too-many-lines
# Test files may exceed max-module-lines (user ruling, 2026-07-04).
"""ABNF_FLAVOUR — full IrFlavour binding and the native-IR self-grammar."""

from __future__ import annotations

from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from lexic.compile import parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import (
    ABNF_ACTIONS,
    ABNF_CORE_RULES,
    ABNF_ESCAPES,
    ABNF_FLAVOUR,
    ABNF_GRAMMAR,
    ABNF_PREFIX_QUANTIFIER,
    ABNF_REDUCER,
    ABNF_REDUCTIONS,
)
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import (
    EscapeCodec,
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrFlavour,
    IrItem,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    canonicalize,
)
from lexic.parsing import parse, recognize
from lexic.parsing.earley.forest import ParseTree
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import YIELD, Reducer
from tests.unit.lexic.conftest import (
    GRAMMAR_AST_TYPES,
    assert_wide_rule_wraps_and_round_trips,
    contains_ir_type,
)


def test_abnf_flavour_is_a_flavour():
    """`ABNF_FLAVOUR` is an `IrFlavour` singleton."""
    assert isinstance(ABNF_FLAVOUR, IrFlavour)


def test_abnf_flavour_metadata():
    """`ABNF_FLAVOUR` has expected metadata"""
    assert ABNF_FLAVOUR.name == "abnf"
    assert ".abnf" in ABNF_FLAVOUR.extensions
    assert ABNF_FLAVOUR.line_comment == ";"


def test_abnf_flavour_grammar_is_abnf_grammar():
    """ABNF_FLAVOUR.grammar is the ABNF_GRAMMAR singleton."""
    assert ABNF_FLAVOUR.grammar is ABNF_GRAMMAR


def test_abnf_flavour_reducer_is_abnf_reducer():
    """ABNF_FLAVOUR.reducer is the ABNF_REDUCER singleton."""
    assert ABNF_FLAVOUR.reducer is ABNF_REDUCER


def test_abnf_flavour_reducer_is_a_reducer_instance():
    """ABNF_FLAVOUR.reducer satisfies isinstance(..., Reducer)."""
    assert isinstance(ABNF_FLAVOUR.reducer, Reducer)


def test_abnf_flavour_grammar_is_an_ir_ast_instance():
    """ABNF_FLAVOUR.grammar satisfies isinstance(..., IrAst)."""
    assert isinstance(ABNF_FLAVOUR.grammar, IrAst)


def test_abnf_escapes_is_an_escape_codec():
    """ABNF_ESCAPES is an EscapeCodec singleton."""
    assert isinstance(ABNF_ESCAPES, EscapeCodec)


def test_encode_is_identity():
    """Encode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.encode("hello") == "hello"
    assert ABNF_ESCAPES.encode("") == ""
    assert ABNF_ESCAPES.encode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.encode("\n") == "\n"


def test_abnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for ABNF.
    """
    registered = set(ABNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"ABNF_FLAVOUR missing explicit actions for: {missing}"


# ── Structured IrCharClass emission ──────────────────────────────────


def test_abnf_charclass_range_emits_hex_range():
    """A range IrCharClass emits ``%xNN-MM``."""
    cls = IrCharClass(IrRange(IrChr("A"), IrChr("Z")))
    assert ABNF_FLAVOUR.apply(cls) == "%x41-5A"


def test_abnf_charclass_run_single_char_emits_single_hex():
    """A single code point emits one ``%xNN`` atom (no parens)."""
    cls = IrCharClass(IrChr("A"))
    assert ABNF_FLAVOUR.apply(cls) == "%x41"


def test_abnf_charclass_run_multiple_chars_emits_parenthesised_alternation():
    """Multiple code points emit ``(%xNN / %xMM / …)``."""
    cls = IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63)"


def test_abnf_charclass_mixed_run_and_range():
    """Code points followed by a range emit all atoms parenthesised."""
    cls = IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("A"), IrChr("Z"))
    )
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63 / %x41-5A)"


def test_abnf_irnot_raises_unsupported():
    """ABNF has no native negation — IrNot raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        ABNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))


def test_abnf_token_terminal_refuses_declaratively():
    """Token terminals are a GBNF surface — ABNF refuses an IrAlphabet (F5)."""
    with pytest.raises(UnsupportedConstructError, match="token terminals"):
        ABNF_FLAVOUR.apply(IrAlphabet("tokens", IrLiteral("<think>")))


# ── ABNF quantifier emission matrix ──────────────────────────────────


def emit_q(q: IrQuantifier) -> str:
    """Evaluate ``ABNF_PREFIX_QUANTIFIER`` for ``q`` and return the string result.

    :param q: The quantifier to evaluate.
    :returns: The emitted ABNF quantifier string.
    """
    return str(ABNF_PREFIX_QUANTIFIER.eval(ABNF_FLAVOUR, q, ()))


@pytest.mark.parametrize(
    "quantifier, expected",
    [
        (IrQuantifier(1, 1), ""),
        (IrQuantifier(0, IrNone), "*"),
        # Regression: N* forms with N != 0 were silently mishandled.
        (IrQuantifier(1, IrNone), "1*"),
        (IrQuantifier(2, IrNone), "2*"),  # the fixed regression — MUST stay pinned
        (IrQuantifier(7, IrNone), "7*"),
        (IrQuantifier(3, 3), "3"),
        (IrQuantifier(0, 5), "*5"),
        (IrQuantifier(2, 5), "2*5"),
        (IrQuantifier(0, 1), "*1"),
        (IrQuantifier(1, 3), "1*3"),
    ],
    ids=[
        "exactly-once",
        "zero-or-more",
        "one-or-more",
        "two-or-more-regression",
        "seven-or-more",
        "exactly-three",
        "zero-to-five",
        "two-to-five",
        "zero-to-one",
        "one-to-three",
    ],
)
def test_abnf_quantifier_emission_matrix(quantifier: IrQuantifier, expected: str):
    """``ABNF_PREFIX_QUANTIFIER.eval`` emits the authoritative ABNF prefix string.

    Each row pins one case; the ``2*`` row guards the regression that was fixed.
    """
    assert emit_q(quantifier) == expected


def test_abnf_quantifier_default_emits_empty():
    """``IrQuantifier()`` (the ``(1, 1)`` default) emits the empty string.

    ``parse_quantifier`` does not handle the empty token — the meta-parser
    synthesises ``IrQuantifier()`` directly, so this case is tested by
    constructing the default quantifier directly.
    """
    assert emit_q(IrQuantifier()) == ""


# ── End-to-end: IrItem with 2* prefix through ABNF_FLAVOUR.apply ─────


def test_abnf_item_with_n_star_quantifier_emits_prefix_form():
    """A full ``IrItem`` with ``2*`` quantifier emits ``"2*<atom>"`` via ``ABNF_FLAVOUR.apply``.

    Covers the ``2*``-style prefix path end-to-end through the action table,
    not just the quantifier map in isolation.
    """
    item = IrItem(atom=IrRuleRef("foo"), quantifier=IrQuantifier(2, IrNone))
    assert str(ABNF_FLAVOUR.apply(item)) == "2*foo"


# ── ABNF literal spellability boundaries (%s char-val vs %x num-val) ──
#
# RFC 7405's char-val body admits printable ASCII except the double quote:
# 0x20-0x21 / 0x23-0x7E. Each row below pins one boundary; the round-trip
# variant proves the emitted form survives emit -> parse_grammar ->
# canonicalize back to the identical IrLiteral, not just that the string
# looks plausible.


def round_trip_literal(text: str) -> IrAst:
    """Wrap ``text`` in a one-rule canonical grammar, emit through ABNF,
    reparse and canonicalize; return the round-tripped ``IrAst``.

    :param text: The literal body to carry through the round-trip.
    :returns: ``canonicalize(parse_grammar(emit(ast), ABNF_FLAVOUR))``.
    """
    ast = canonicalize(IrAst(IrSeq(IrRule("s", IrLiteral(text))), "s"))
    emitted = str(ABNF_FLAVOUR.apply(ast))
    return canonicalize(parse_grammar(emitted, ABNF_FLAVOUR))


SPELLABILITY_BOUNDARY_CASES = [
    ("\x1f", "%x1F"),  # 0x1F control, just below the char-val floor
    (" ", '%s" "'),  # 0x20 — the floor
    ("!", '%s"!"'),  # 0x21 — top of the first spellable run
    ('"', "%x22"),  # 0x22 — the double quote, never spellable
    ("#", '%s"#"'),  # 0x23 — bottom of the second spellable run
    ("~", '%s"~"'),  # 0x7E — the ceiling
    ("\x7f", "%x7F"),  # 0x7F DEL, just past the ceiling
    ("é", "%xE9"),  # non-ASCII, single code point
    ("😀", "%x1F600"),  # non-ASCII, astral code point
    ('a"b', "%x61.22.62"),  # mixed spellable/unspellable -> num-seq
    ("\x1f\x7f", "%x1F.7F"),  # two unspellable code points -> num-seq
    ("hello world", '%s"hello world"'),  # ordinary multi-char literal
    ("", '%s""'),  # empty body is (vacuously) all-spellable
]
SPELLABILITY_IDS = [
    "0x1f-control-below-floor",
    "0x20-floor-space",
    "0x21-top-of-first-run",
    "0x22-double-quote",
    "0x23-bottom-of-second-run",
    "0x7e-ceiling",
    "0x7f-del-above-ceiling",
    "non-ascii-single",
    "non-ascii-astral",
    "mixed-spellable-and-not",
    "two-unspellable-numseq",
    "ordinary-multichar",
    "empty-literal",
]


@pytest.mark.parametrize(
    "text, expected", SPELLABILITY_BOUNDARY_CASES, ids=SPELLABILITY_IDS
)
def test_abnf_literal_emission_at_spellability_boundaries(text: str, expected: str):
    """Each boundary emits the exact expected ``%s``/``%x`` spelling."""
    assert str(ABNF_FLAVOUR.apply(IrLiteral(text))) == expected


@pytest.mark.parametrize(
    "text, _expected", SPELLABILITY_BOUNDARY_CASES, ids=SPELLABILITY_IDS
)
def test_abnf_literal_boundary_round_trips(text: str, _expected: str):
    """Every boundary case survives emit -> parse_grammar -> canonicalize."""
    original = canonicalize(IrAst(IrSeq(IrRule("s", IrLiteral(text))), "s"))
    assert round_trip_literal(text) == original


@given(
    text=st.text(
        alphabet=st.characters(
            min_codepoint=0, max_codepoint=0x10FFFF, exclude_categories=("Cs",)
        ),
        min_size=1,
        max_size=6,
    )
)
@settings(max_examples=75)
def test_abnf_literal_round_trip_property(text: str):
    """Any Unicode literal (control, quote, non-ASCII, astral) round-trips."""
    original = canonicalize(IrAst(IrSeq(IrRule("s", IrLiteral(text))), "s"))
    assert round_trip_literal(text) == original


# ── ABNF_GRAMMAR / ABNF_REDUCTIONS — native IR grammar + reducer ──────────
#
# Formerly tests/unit/lexic/grammars/test_abnf_2.py. API changes carried over
# from that file's own header:
#
# - ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.
# - ``Reducer(...).reduce(tree)`` → ``Reducer(...).apply(tree)``.


def normalize_grammar(g: IrAst) -> IrAst:
    """Full normalization pipeline: flatten_groups -> desugar_quantifiers.

    Multi-char literals stay atomic (no split_literals step).
    """
    return normalize(g)


# ── ABNF_GRAMMAR structure ────────────────────────────────────────────


def test_abnf_grammar_is_ir_ast():
    """ABNF_GRAMMAR is an IrAst."""
    assert isinstance(ABNF_GRAMMAR, IrAst)


def test_abnf_grammar_start_rule_is_rulelist():
    """ABNF_GRAMMAR start rule is 'rulelist'."""
    assert ABNF_GRAMMAR.start == "rulelist"


def test_abnf_grammar_has_expected_rule_count():
    """ABNF_GRAMMAR has at least 20 rules (RFC 5234 §4 subset)."""
    assert len(list(ABNF_GRAMMAR.rules)) >= 20


def test_abnf_grammar_rule_names_include_core():
    """ABNF_GRAMMAR contains expected core rule names."""
    names = {r.name for r in ABNF_GRAMMAR.rules}
    for expected in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
    ):
        assert expected in names, f"Missing rule: {expected}"


def test_abnf_grammar_rulelist_left_factor_shape():
    """The Task 6.6 ``rulelist`` left-factor: ``rl-cont`` exists, and the old
    ``rl-item``/``rl-final``/``endrule`` helper rules are gone."""
    names = {r.name for r in ABNF_GRAMMAR.rules}
    assert "rl-cont" in names
    assert not ({"rl-item", "rl-final", "endrule"} & names)


def test_abnf_grammar_rule_arm_shape_is_factored():
    """``rule``'s single arm is ``[rulename, c-wsp*, defined, c-wsp*, alternation]``
    — the factored shape ``rl-cont`` was split out of."""
    rule = next(r for r in ABNF_GRAMMAR.rules if r.name == "rule")
    arm = rule.body[0]
    assert [str(item.atom) for item in arm] == [
        "rulename",
        "c-wsp",
        "defined",
        "c-wsp",
        "alternation",
    ]


# ── ABNF_GRAMMAR emits as well-formed ABNF ───────────────────────────


def test_abnf_grammar_emits_non_empty_string():
    """ABNF_FLAVOUR.apply(ABNF_GRAMMAR) returns a non-empty string."""
    result = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_abnf_grammar_emitted_text_contains_rulelist():
    """The emitted ABNF text contains the 'rulelist' rule definition."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert "rulelist" in text


def test_abnf_grammar_emitted_text_contains_equals():
    """The emitted ABNF text contains '=' rule assignments."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert " = " in text


# ── ABNF_REDUCTIONS structure ─────────────────────────────────────────


def test_abnf_reductions_is_ir_map():
    """ABNF_REDUCTIONS is an IrMap."""
    assert isinstance(ABNF_REDUCTIONS, IrMap)


def test_abnf_reductions_covers_all_structural_rules():
    """ABNF_REDUCTIONS has entries for all structural rules."""
    for rule_name in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
        "element",
        "group",
        "char-val",
        "num-val",
    ):
        assert ABNF_REDUCTIONS[IrRuleRef(rule_name)] is not None, (
            f"Missing reduction for {rule_name!r}"
        )


def test_abnf_reductions_covers_terminal_rules():
    """Terminal rules fall through to the reducer's ``default`` → YIELD."""
    for rule_name in ("ALPHA", "DIGIT", "HEXDIG", "CR", "LF", "SP", "HTAB", "DQUOTE"):
        assert ABNF_REDUCER.body(IrRuleRef(rule_name)) is YIELD, (
            f"Expected YIELD for {rule_name!r}"
        )


# ── ABNF_REDUCTIONS leaf reductions on simple trees ───────────────────


def test_rulename_reduction_yields_irruleref():
    """rulename reduction: children joined -> IrRuleRef."""
    reducer = Reducer(actions=ABNF_REDUCTIONS)
    tree = ParseTree(IrRuleRef("rulename"), IrSeq(IrLiteral("a"), IrLiteral("b")))
    result = reducer.apply(tree)
    assert isinstance(result, IrRuleRef)
    assert str(result) == "ab"


def test_char_val_alpha_reduces_to_case_insensitive_alternation():
    """char-val with letters reduces to a case-insensitive IrAlternation (RFC 7405).

    Ported from the old case-sensitive-literal assertion after the Phase 3
    re-author made char-val case-insensitive, matching ``normalize_literal``.
    """
    g = normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, 'x = "ab"\n'))
    assert isinstance(result, IrAst)
    atom = list(list(result.rules)[0].body)[0][0].atom
    assert isinstance(atom, IrAlternation)
    seq = atom[0]
    assert seq[0].atom == IrCharClass(IrChr("a"), IrChr("A"))
    assert seq[1].atom == IrCharClass(IrChr("b"), IrChr("B"))


def hexdig(ch: str) -> ParseTree:
    """Wrap a single hex character in a HEXDIG ParseTree (as the real parser produces)."""
    return ParseTree(IrRuleRef("HEXDIG"), IrSeq(IrLiteral(ch)))


def test_num_x_empty_tail_yields_ircharclass_chr():
    """num-x over a hexits subtree with an empty x-tail yields IrCharClass(IrChr('A')).

    Ported from the pre-P4 test_num_single_yields_ircharclass_chr — num-single
    is gone (left-factored into num-x + x-tail); the empty x-tail is the
    single-point case.
    """
    hexits = ParseTree(IrRuleRef("hexits"), IrSeq(hexdig("4"), hexdig("1")))
    x_tail = ParseTree(IrRuleRef("x-tail"), IrSeq())
    tree = ParseTree(
        IrRuleRef("num-x"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), hexits, x_tail),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrChr("A"))


def test_num_x_range_tail_yields_ircharclass_range():
    """num-x with an x-range x-tail yields IrCharClass(IrRange('A','Z')).

    Ported from the pre-P4 test_num_range_yields_ircharclass_range — num-range
    is gone (left-factored into num-x + x-tail/x-range).
    """
    lo = ParseTree(IrRuleRef("hexits"), IrSeq(hexdig("4"), hexdig("1")))
    hi = ParseTree(IrRuleRef("hexits"), IrSeq(hexdig("5"), hexdig("A")))
    x_range = ParseTree(IrRuleRef("x-range"), IrSeq(IrLiteral("-"), hi))
    x_tail = ParseTree(IrRuleRef("x-tail"), IrSeq(x_range))
    tree = ParseTree(
        IrRuleRef("num-x"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), lo, x_tail),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))


# ── In-subset single-rule parse+reduce ───────────────────────────────


def test_parse_reduce_single_literal_rule():
    """'s = \"+-\"' parses and reduces to IrAst with IrLiteral('+-') item.

    Uses a non-alpha literal: an alpha literal case-expands (RFC 7405), so a
    bare-``IrLiteral`` assertion needs a body with no letters.
    """
    g = normalize_grammar(ABNF_GRAMMAR)
    tree = parse(g, 's = "+-"\n')
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    assert result.start == "s"
    rules = list(result.rules)
    assert rules[0].name == "s"
    arm = list(rules[0].body)[0]
    item = arm[0]
    assert item.atom == IrLiteral("+-")
    assert item.quantifier == IrQuantifier(1, 1)


def test_parse_reduce_alternation_rule():
    """'s = foo / bar' reduces to two-arm IrAlternation of IrRuleRef atoms."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = 's = foo / bar\nfoo = "x"\nbar = "y"\n'
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    s_rule = list(result.rules)[0]
    assert s_rule.name == "s"
    arms = list(s_rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrRuleRef("foo")
    assert arms[1][0].atom == IrRuleRef("bar")


def test_parse_reduce_charclass_rule():
    """'x = %x41-5A' reduces to IrCharClass(IrRange('A','Z'))."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = "x = %x41-5A\n"
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    item = list(rules[0].body)[0][0]
    assert isinstance(item.atom, IrCharClass)
    assert item.atom == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))


def quant_of(text: str) -> IrQuantifier:
    """Parse a one-rule ABNF snippet and return its single item's quantifier."""
    g = normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, text))
    assert isinstance(result, IrAst)
    return list(list(result.rules)[0].body)[0][0].quantifier


def test_repeat_exact_quantifier():
    """'5"a"' → IrQuantifier(5, 5)."""
    assert quant_of('x = 5"a"\n') == IrQuantifier(5, 5)


def test_repeat_range_quantifier():
    """'1*5"a"' → IrQuantifier(1, 5)."""
    assert quant_of('x = 1*5"a"\n') == IrQuantifier(1, 5)


def test_repeat_open_upper_quantifier():
    """'5*"a"' → IrQuantifier(5, IrNone) — empty hi-bound is unbounded."""
    assert quant_of('x = 5*"a"\n') == IrQuantifier(5, IrNone)


def test_repeat_open_lower_quantifier():
    """'*5"a"' → IrQuantifier(0, 5) — empty lo-bound is zero."""
    assert quant_of('x = *5"a"\n') == IrQuantifier(0, 5)


def test_repeat_star_quantifier():
    """'*"a"' → IrQuantifier(0, IrNone) — both bounds empty."""
    assert quant_of('x = *"a"\n') == IrQuantifier(0, IrNone)


def test_repeat_absent_defaults_to_one_one():
    """No repeat prefix → repeat-opt defaults to IrQuantifier(1, 1)."""
    assert quant_of('x = "a"\n') == IrQuantifier(1, 1)


def test_num_single_parse_reduce():
    """'x = %x41' reduces to IrCharClass(IrChr('A'))."""
    g = normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, "x = %x41\n"))
    assert isinstance(result, IrAst)
    item = list(list(result.rules)[0].body)[0][0]
    assert item.atom == IrCharClass(IrChr("A"))


def test_json_abnf_ground_truth_reduces_to_32_rules():
    """resources/ground_truth/json.abnf reduces to 32 rules via the native reducer."""
    path = Path(__file__).parents[4] / "resources" / "ground_truth" / "json.abnf"
    g = normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, path.read_text(encoding="utf-8")))
    assert isinstance(result, IrAst)
    assert len(list(result.rules)) == 32


# ── THE SELF-HOSTING FIXPOINT ─────────────────────────────────────────


def test_self_hosting_recognize():
    """normalize(ABNF_GRAMMAR) recognizes its own emitted text."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert recognize(g, text)


def test_self_hosting_fixpoint():
    """The headline test: emitting ABNF_GRAMMAR, re-parsing and reducing, then
    canonicalising, returns ABNF_GRAMMAR (stored in canonical form). The
    canonical pass is what closes the loop — a merged char class re-emits as a
    parenthesised num-val alternation that reparses un-merged."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert canonicalize(result) == ABNF_GRAMMAR


def test_self_hosting_fixpoint_idempotent():
    """Reduce → re-emit → re-parse → re-reduce: result is the same IrAst."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))

    # First round
    tree1 = parse(g, text)
    result1 = ABNF_REDUCER.apply(tree1)
    assert isinstance(result1, IrAst)

    # Re-emit and re-parse
    text2 = str(ABNF_FLAVOUR.apply(result1))
    tree2 = parse(g, text2)
    result2 = ABNF_REDUCER.apply(tree2)

    assert result2 == result1
    assert canonicalize(result2) == ABNF_GRAMMAR


def test_self_hosting_crlf_recognized():
    """CRLF line endings in the emitted text are recognized and parse correctly."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    assert recognize(g, text_crlf)


def test_self_hosting_crlf_reduces_to_abnf_grammar():
    """CRLF-terminated emitted text reduces back to ABNF_GRAMMAR."""
    g = normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    tree = parse(g, text_crlf)
    result = ABNF_REDUCER.apply(tree)
    assert canonicalize(result) == ABNF_GRAMMAR


# ── Phase 3 remainder: per-construct native-grammar unit tests ────────
# Companion to tests/integration/test_abnf_ir_equivalence.py (corpus-wide
# Lark parity); these assert the reduced IrAst shape per construct.

NORM_ABNF = normalize_grammar(ABNF_GRAMMAR)


def reduce(text: str) -> IrAst:
    """Parse+reduce ``text`` against the native ABNF self-grammar.

    :param text: ABNF source, a single small grammar snippet.
    :returns: The reduced :class:`IrAst`.
    """
    result = ABNF_REDUCER.apply(parse(NORM_ABNF, text))
    assert isinstance(result, IrAst)
    return result


def make_item(
    ast: IrAst, rule_index: int = 0, arm_index: int = 0, item_index: int = 0
) -> IrItem:
    """Drill into ``ast.rules[rule_index].body[arm_index][item_index]``.

    :param ast: The reduced grammar.
    :returns: The selected :class:`IrItem`.
    """
    return ast.rules[rule_index].body[arm_index][item_index]


# ── (1) num-seq: %x-dotted value sequences → case-sensitive IrLiteral ──


def test_numseq_three_part_becomes_literal():
    """``%x66.61.6c`` → ``IrLiteral("fal")`` — one glyph per dot-part."""
    ast = reduce("s = %x66.61.6c\n")
    assert make_item(ast).atom == IrLiteral("fal")


def test_numseq_two_part_becomes_literal():
    """A two-part num-seq decodes both hex parts in order."""
    ast = reduce("s = %x41.42\n")
    assert make_item(ast).atom == IrLiteral("AB")


def test_numseq_inside_concatenation():
    """A num-seq item composes normally with a ruleref in the same sequence."""
    ast = reduce("kw = %x66.61.6c bar\nbar = %x78\n")
    arm = ast.rules[0].body[0]
    assert arm[0].atom == IrLiteral("fal")
    assert arm[1].atom == IrRuleRef("bar")


# ── (2) [...] option → IrItem(inner-alternation, IrQuantifier(0, 1)) ───


def test_option_produces_item_with_zero_one_quantifier_over_alternation():
    """``[ digits ]`` → an :class:`IrItem` wrapping the inner alternation, ``(0, 1)``."""
    ast = reduce("num = sign [ digits ]\nsign = %x2D\ndigits = %x30-39\n")
    item = ast.rules[0].body[0][1]
    assert item.quantifier == IrQuantifier(0, 1)
    assert isinstance(item.atom, IrAlternation)
    assert item.atom[0][0].atom == IrRuleRef("digits")


def test_nested_option():
    """``[ [ "-" ] ]`` — an option item whose sole arm is itself an option item."""
    outer = make_item(reduce('foo = [ [ "-" ] ]\n'))
    assert outer.quantifier == IrQuantifier(0, 1)
    assert isinstance(outer.atom, IrAlternation)
    inner = outer.atom[0][0]
    assert inner.quantifier == IrQuantifier(0, 1)
    assert isinstance(inner.atom, IrAlternation)
    assert inner.atom[0][0].atom == IrLiteral("-")


def test_option_containing_alternation():
    """``[ "-" / "+" ]`` — the option's atom carries two alternation arms."""
    item = make_item(reduce('foo = [ "-" / "+" ]\n'))
    assert item.quantifier == IrQuantifier(0, 1)
    assert isinstance(item.atom, IrAlternation)
    arms = list(item.atom)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("-")
    assert arms[1][0].atom == IrLiteral("+")


# ── (3) comments/blank lines/folding are noise ──────────────────────────


def test_trailing_comment_after_rule():
    """A ``;`` comment trailing a rule body is noise, not part of the body."""
    ast = reduce("root = digit  ; a digit\ndigit = %x30-39\n")
    assert len(ast.rules) == 2
    assert make_item(ast).atom == IrRuleRef("digit")


def test_comment_only_line_before_rule():
    """A comment-only line preceding a rule is filler, dropped."""
    ast = reduce('; just a comment\nfoo = "-"\n')
    assert len(ast.rules) == 1
    assert ast.rules[0].name == "foo"


def test_blank_line_between_rules():
    """A blank line between two rules is filler, dropped."""
    ast = reduce('foo = "-"\n\nbar = "+"\n')
    assert [r.name for r in ast.rules] == ["foo", "bar"]


def test_line_folding_continuation_before_slash():
    """An alternation arm may continue on the next line, indented (``c-wsp`` folding)."""
    ast = reduce('foo = "-"\n    / "+"\n')
    arms = list(ast.rules[0].body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("-")
    assert arms[1][0].atom == IrLiteral("+")


def test_inline_comment_inside_definition():
    """Inline comments interleaved through a folded group definition are noise."""
    ast = reduce("ws = *(\n        %x20 /   ; space\n        %x09 )   ; tab\n")
    assert len(ast.rules) == 1
    item = make_item(ast)
    assert item.quantifier == IrQuantifier(0, IrNone)
    assert isinstance(item.atom, IrAlternation)
    arms = list(item.atom)
    assert len(arms) == 2
    assert arms[0][0].atom == IrCharClass(IrChr(" "))
    assert arms[1][0].atom == IrCharClass(IrChr("\t"))


def test_final_rule_without_trailing_newline():
    """The last rule in a file may omit its line ending (``rulelist``'s trailing ``c-nl?``)."""
    ast = reduce('foo = "-"\nbar = "+"')
    assert [r.name for r in ast.rules] == ["foo", "bar"]
    assert make_item(ast, rule_index=1).atom == IrLiteral("+")


# ── (4) %s / %i strings and their bare-literal case-insensitive twin ───


def test_cs_string_is_raw_literal_no_case_expansion():
    """``%s"aBc"`` → a single raw case-sensitive ``IrLiteral``, mixed case preserved."""
    ast = reduce('foo = %s"aBc"\n')
    assert make_item(ast).atom == IrLiteral("aBc")


def test_ci_string_matches_bare_literal_expansion():
    """``%i"aBc"`` and bare ``"aBc"`` reduce identically (RFC 7405)."""
    ci = reduce('foo = %i"aBc"\n')
    bare = reduce('foo = "aBc"\n')
    assert ci.rules[0].body == bare.rules[0].body
    atom = make_item(ci).atom
    assert isinstance(atom, IrAlternation)
    seq = atom[0]
    assert seq[0].atom == IrCharClass(IrChr("a"), IrChr("A"))
    assert seq[1].atom == IrCharClass(IrChr("b"), IrChr("B"))
    assert seq[2].atom == IrCharClass(IrChr("c"), IrChr("C"))


def test_empty_char_val_reduces_to_empty_literal():
    """``\"\"`` (empty char-val body) → ``IrLiteral(\"\")``.

    P4 left-factored ``cvbody`` into a shared ``cvnac*`` run followed by an
    inline optional ``(cvalpha cvany*)?`` group; the reduction is an
    ``IrCond`` keyed on ``IrArgs()`` truthiness — this pins its empty-channel
    branch (``else_op``), a code path the alpha/non-alpha cases above don't
    exercise.
    """
    ast = reduce('foo = ""\n')
    assert make_item(ast).atom == IrLiteral("")


# ── (5) %d / %b values, parity with the equivalent %x spelling ─────────


def test_dec_single_matches_hex_equivalent():
    """``%d65`` → ``IrCharClass(IrChr('A'))``, identical to ``%x41``."""
    dec = reduce("a = %d65\n")
    hexa = reduce("a = %x41\n")
    assert make_item(dec).atom == IrCharClass(IrChr("A"))
    assert make_item(dec).atom == make_item(hexa).atom


def test_dec_range_matches_hex_equivalent():
    """``%d65-90`` → ``IrCharClass(IrRange('A', 'Z'))``, identical to ``%x41-5A``."""
    dec = reduce("a = %d65-90\n")
    hexa = reduce("a = %x41-5A\n")
    assert make_item(dec).atom == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))
    assert make_item(dec).atom == make_item(hexa).atom


def test_bin_single_matches_hex_and_dec_equivalent():
    """``%b1000001`` → ``IrCharClass(IrChr('A'))``, same value as ``%d65`` / ``%x41``."""
    binv = reduce("a = %b1000001\n")
    assert make_item(binv).atom == IrCharClass(IrChr("A"))


def test_bin_range_matches_hex_and_dec_equivalent():
    """``%b1000001-1011010`` → the same range as ``%d65-90`` / ``%x41-5A``."""
    binv = reduce("a = %b1000001-1011010\n")
    assert make_item(binv).atom == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))


# ── (6) prose-val → UnsupportedConstructError, via the native reducer ──


def test_prose_val_raises_via_native_reducer():
    """``<...>`` → ``IrRaise`` at reduce time (Lark-path twin test above)."""
    with pytest.raises(UnsupportedConstructError):
        reduce("foo = <any prose text>\n")


# ── (7) =/ incremental alternatives merge into one IrRule ──────────────


def test_single_incremental_extension_merges_two_arms():
    """One ``=/`` extension merges into the original rule — 2 arms, source order."""
    ast = reduce('foo = "-"\nfoo =/ "+"\n')
    assert len(ast.rules) == 1
    arms = list(ast.rules[0].body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("-")
    assert arms[1][0].atom == IrLiteral("+")


def test_two_incremental_extensions_merge_in_definition_order():
    """Two ``=/`` extensions append arms onto one ``IrRule``, in source order."""
    ast = reduce('foo = "-"\nfoo =/ "+"\nfoo =/ "0"\n')
    assert len(ast.rules) == 1
    arms = list(ast.rules[0].body)
    assert [arm[0].atom for arm in arms] == [
        IrLiteral("-"),
        IrLiteral("+"),
        IrLiteral("0"),
    ]


def test_incremental_extensions_with_intervening_comments():
    """Comments between ``=`` and ``=/`` definitions do not disturb the merge."""
    text = 'foo = "-"\n; first extension\nfoo =/ "+"\n; second extension\nfoo =/ "0"\n'
    ast = reduce(text)
    assert len(ast.rules) == 1
    arms = list(ast.rules[0].body)
    assert [arm[0].atom for arm in arms] == [
        IrLiteral("-"),
        IrLiteral("+"),
        IrLiteral("0"),
    ]


# ── Structural guard: abnf.py is data + pure IR algebra, no procedural bodies ──


def test_abnf_actions_and_reductions_carry_no_irlambda():
    """ABNF_ACTIONS and ABNF_REDUCTIONS contain no :class:`IrLambda` anywhere.

    abnf.py holds zero ``def`` beyond dataclass/ABC machinery — its emit and
    parse halves are pure IR algebra. A stray :class:`IrLambda` escape hatch
    creeping back into either table would be a regression from that ruling.
    """
    assert not contains_ir_type(ABNF_ACTIONS.values(), IrLambda)
    assert not contains_ir_type(ABNF_REDUCTIONS.values(), IrLambda)


# ── Width-aware structure emission (trailing-slash wrap / RFC folding) ────


def test_wide_alternation_wraps_and_round_trips():
    """Wide-rule structure-level doc emission: trailing-slash wrap at indent
    6 (RFC 5234 c-wsp folding, past 'name = '), no over-width line,
    reparse-canonicalize-equal, and width=None reproduces the flat form."""
    flat_text = "wide-rule = " + " / ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    assert_wide_rule_wraps_and_round_trips(ABNF_FLAVOUR, "/", flat_text)


# ── RFC parity: %d / %b dot-sequences ─────────────────────────────────────


def test_dec_dot_seq_decodes_crlf():
    """``%d13.10`` (decimal dot-sequence) decodes to the two-char literal CRLF."""
    ast = reduce("a = %d13.10\n")
    assert make_item(ast).atom == IrLiteral("\r\n")


def test_bin_dot_seq_decodes_crlf():
    """``%b1101.1010`` (binary dot-sequence) decodes to the same CRLF literal."""
    ast = reduce("a = %b1101.1010\n")
    assert make_item(ast).atom == IrLiteral("\r\n")


def test_dec_dot_seq_matches_hex_dot_seq_equivalent():
    """``%d13.10`` and ``%x0D.0A`` decode to the identical literal."""
    dec = reduce("a = %d13.10\n")
    hexa = reduce("a = %x0D.0A\n")
    assert make_item(dec).atom == make_item(hexa).atom


def test_bin_dot_seq_matches_dec_dot_seq_equivalent():
    """``%b1101.1010`` and ``%d13.10`` decode to the identical literal."""
    binv = reduce("a = %b1101.1010\n")
    dec = reduce("a = %d13.10\n")
    assert make_item(binv).atom == make_item(dec).atom


# ── RFC parity: case-insensitive marker letters ────────────────────────────


@pytest.mark.parametrize(
    ("upper", "lower"),
    [
        ("a = %X41\n", "a = %x41\n"),
        ("a = %D65\n", "a = %d65\n"),
        ("a = %B1000001\n", "a = %b1000001\n"),
        ('a = %S"HI"\n', 'a = %s"HI"\n'),
        ('a = %I"hi"\n', 'a = %i"hi"\n'),
    ],
    ids=["x", "d", "b", "s", "i"],
)
def test_uppercase_marker_parses_identically_to_lowercase(upper: str, lower: str):
    """An uppercase radix/case marker (%X/%D/%B/%S/%I) reduces to the same IR
    as its lowercase form — the marks are noise, only case affects nothing."""
    assert reduce(upper) == reduce(lower)


# ── RFC parity: canonical fixpoint still holds with the new grammar surface ──


def test_canonicalize_abnf_grammar_is_a_fixpoint():
    """canonicalize(ABNF_GRAMMAR) == ABNF_GRAMMAR — the self-hosting invariant
    survives the %d/%b dot-sequence and uppercase-marker additions."""
    assert canonicalize(ABNF_GRAMMAR) == ABNF_GRAMMAR


# ── RFC parity: ABNF_CORE_RULES — the flavour's std-namespace prelude ────


def test_abnf_core_rules_has_sixteen_entries():
    """RFC 5234 B.1 core rules: exactly 16 prelude entries."""
    assert len(list(ABNF_CORE_RULES.keys())) == 16


def test_abnf_core_rules_names_are_lowercase():
    """Every core-rule name folds lowercase (ABNF rulenames are case-insensitive)."""
    for key in ABNF_CORE_RULES.keys():
        name = str(key)
        assert name == name.lower()


def test_abnf_core_rules_bodies_are_ir_rules():
    """Every prelude entry's value is the named IrRule."""
    for key, rule in ABNF_CORE_RULES.items():
        assert isinstance(rule, IrRule)
        assert str(rule.name) == str(key)


# ── RFC parity: prelude resolution is dangling-ref-only ───────────────────


def test_prelude_injects_dangling_ref_closure():
    """A grammar referencing ALPHA/CRLF without defining them gets the whole
    closure appended: word, alpha, crlf, and crlf's own cr/lf dependencies."""
    ast = parse_grammar("word = 1*ALPHA CRLF\n", ABNF_FLAVOUR)
    assert {str(r.name) for r in ast.rules} == {"word", "alpha", "crlf", "cr", "lf"}


def test_prelude_does_not_inject_a_rule_the_grammar_already_defines():
    """A grammar defining alpha itself is not overridden by the prelude."""
    ast = parse_grammar("alpha = %x41\nword = 1*alpha\n", ABNF_FLAVOUR)
    assert {str(r.name) for r in ast.rules} == {"alpha", "word"}


def test_prelude_only_injects_referenced_core_rules():
    """Referencing one core rule does not pull in unrelated prelude entries."""
    ast = parse_grammar("word = ALPHA\n", ABNF_FLAVOUR)
    names = {str(r.name) for r in ast.rules}
    assert names == {"word", "alpha"}
    assert "digit" not in names
    assert "vchar" not in names


def test_gbnf_flavour_has_no_prelude_so_grammar_text_is_untouched():
    """GBNF_FLAVOUR carries no core_rules — parse_grammar never injects
    anything, even for a rule name that happens to match an ABNF core name."""
    ast = parse_grammar('alpha ::= "a"\nword ::= alpha\n', GBNF_FLAVOUR)
    assert {str(r.name) for r in ast.rules} == {"alpha", "word"}
