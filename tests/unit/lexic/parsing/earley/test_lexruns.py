"""Tests for lexic.parsing.earley.lexruns — run-terminal detection and collapse.

New module: proves a synthetic star/plus rule's collapse to a single
maximal-munch :class:`~lexic.parsing.earley.kernel.tables.RunTerm` (fixed charset,
derivation-uniqueness, follow-disjointness) and reconstructs it as compiled
tables. This file covers ``run_candidates``'s detection and memoisation,
``recognition_tables``'s collapse and result parity with plain tables, and
``unit_leaves``'s transitive charset-rule walk.
"""

from __future__ import annotations

from lexic.compile import Directives, canonical_grammar, compile_text
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.abnf import ABNF_GRAMMAR
from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import (
    RunTerm,
    Spans,
)
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import (
    recognition_tables,
    run_candidates,
    unit_leaves,
)
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX, normalize
from lexic.parsing.products import earley_model, model_product
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import (
    malformed_synthetic_rule,
    nested_synthetic_grammar,
)

# ── run_candidates ────────────────────────────────────────────────────


def test_run_candidates_detects_collapsible_rules_on_abnf_grammar():
    """run_candidates finds synthetic star/plus rules on the real ABNF grammar."""
    g = normalize(ABNF_GRAMMAR)
    tables = compile_tables(g)
    candidates = run_candidates(tables)
    assert candidates
    for name in candidates:
        assert name.startswith(SYNTHETIC_PREFIX)


def test_run_candidates_memoised_per_tables_object():
    """Calling run_candidates twice on the SAME tables returns the same dict."""
    g = normalize(ABNF_GRAMMAR)
    tables = compile_tables(g)
    first = run_candidates(tables)
    second = run_candidates(tables)
    assert first is second


def test_run_candidates_empty_for_grammar_with_no_synthetic_rules():
    """A plain (non-quantified) grammar has no run candidates."""
    tables = compile_tables(_digit_grammar())
    assert run_candidates(tables) == {}


def _quoted() -> IrAst:
    """``s ::= "\"" [^"]* "\""`` — the string body every JSON-ish grammar has."""
    quote = IrItem(IrLiteral('"'))
    body = IrItem(IrNot(IrCharClass(IrChr('"'))), IrQuantifier(0, IrNone))
    rule = IrRule("s", IrAlternation(IrSequence(quote, body, quote)))
    return normalize(IrAst(rules=IrSeq(rule), start="s"))


def test_run_candidates_collapses_a_negated_class_star():
    """``[^"]*`` collapses: its unit is every code point but the quote, and
    the quote that follows it is the one character it excludes."""
    shapes = list(run_candidates(compile_tables(_quoted())).values())
    assert len(shapes) == 1
    unit, has_empty, _rid = shapes[0]
    assert has_empty
    assert unit == IrCharClass(IrChr('"')).complement()


def test_a_negated_run_scans_by_exclusion_and_recognises_what_plain_does():
    """The collapsed ``[^"]*`` is one negated run term listing the quote, and
    the collapsed tables accept and refuse exactly what the plain ones do."""
    grammar = _quoted()
    plain, collapsed = compile_tables(grammar), recognition_tables(grammar)
    runs = [atom for atom in collapsed.terms.atoms if isinstance(atom, RunTerm)]
    assert [(run.charset, run.negated) for run in runs] == [(frozenset('"'), True)]
    for text in ('""', '"abc"', '"a\u00e9\U0001f600"', '"a"b"', '"', 'x""', '"ab'):
        want = accept_item(Kernel(plain, text, record_links=False).run()) >= 0
        got = accept_item(Kernel(collapsed, text, record_links=False).run()) >= 0
        assert got == want, text


# ── a follower the char sets could not list no longer poisons a run ────

LETTERS = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
LOWER = LETTERS.normalized()
DIGITS = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
WIDE = IrCharClass(IrRange(IrChr(chr(0x100)), IrChr(chr(0x3000))))
OPTIONAL_DASH = IrItem(IrLiteral("-"), IrQuantifier(0, 1))


def _word() -> IrItem:
    return IrItem(LETTERS, IrQuantifier(1, IrNone))


def _rule(name: str, *arms: tuple[IrItem, ...]) -> IrRule:
    return IrRule(name, IrAlternation(*(IrSequence(*arm) for arm in arms)))


def _ref(name: str) -> IrItem:
    return IrItem(IrRuleRef(name))


def _lit(text: str) -> IrItem:
    return IrItem(IrLiteral(text))


def _units(*rules: IrRule) -> set[IrCharClass]:
    """The proved run units, normalised, of the grammar its first rule starts."""
    grammar = normalize(IrAst(rules=IrSeq(*rules), start=str(rules[0].name)))
    shapes = run_candidates(compile_tables(grammar)).values()
    return {unit.normalized() for unit, _empty, _rid in shapes}


def _after_word(follower: IrAtom) -> set[IrCharClass]:
    """The proved run units of ``root ::= [a-z]+ follower``."""
    return _units(_rule("root", (_word(), IrItem(follower))))


def test_a_negated_follower_that_holds_no_letter_lets_the_run_collapse():
    """``[a-z]+ [^a-z]``: nothing after the run begins with a letter."""
    assert LOWER in _after_word(IrNot(LETTERS))


def test_a_follower_too_wide_to_list_lets_the_run_collapse():
    """U+0100..U+3000 spans 12,033 code points and holds no letter a-z."""
    assert LOWER in _after_word(WIDE)


def test_a_negated_follower_that_holds_a_letter_keeps_the_run_per_char():
    """``[a-z]+ [^0-9]``: a letter may follow, so the longest run is not forced."""
    assert LOWER not in _after_word(IrNot(DIGITS))


def test_a_wide_follower_that_holds_a_letter_keeps_the_run_per_char():
    """``[a-z]+ [Z-U+3000]``: the wide class holds a-z, so a letter may follow."""
    wide_with_letters = IrCharClass(IrRange(IrChr("Z"), IrChr(chr(0x3000))))
    assert LOWER not in _after_word(wide_with_letters)


def test_a_token_follower_keeps_the_run_per_char():
    """A token's spelling may begin with a letter, so the run's end is unproved."""
    assert LOWER not in _after_word(IrAlphabet("tokens", IrLiteral("x")))


def test_a_wide_class_reached_through_a_rule_no_longer_poisons_the_run():
    """``root ::= [a-z]+ tail``, ``tail ::= "!" | wide``: the follower's FIRST
    holds a class too wide to list, which poisoned the whole FOLLOW; asked by
    terminal, neither ``"!"`` nor the wide class begins with a letter."""
    root = _rule("root", (_word(), _ref("tail")))
    assert LOWER in _units(root, _rule("tail", (_lit("!"),), (IrItem(WIDE),)))


def test_a_negated_class_reached_through_the_owner_no_longer_poisons_the_run():
    """``w ::= [a-z]+`` ends its rule and ``[^a-z]`` follows ``w``: the run
    inherits a negated follower through its owner, and it holds no letter."""
    root = _rule("root", (_ref("w"), IrItem(IrNot(LETTERS))))
    assert LOWER in _units(root, _rule("w", (_word(),)))


def test_only_terminals_that_can_follow_the_run_decide_it():
    """``"a"`` appears in the grammar but never after the run: it collapses."""
    root = _rule("root", (_word(), _lit("!")), (_lit("q"), _ref("junk")))
    assert LOWER in _units(root, _rule("junk", (_lit("a"),)))


def test_a_follower_inherited_from_the_owner_keeps_the_run_per_char():
    """``w ::= [a-z]+`` ends its rule; ``"a"`` follows ``w`` at its call site."""
    assert LOWER not in _units(
        _rule("root", (_ref("w"), _lit("a"))), _rule("w", (_word(),))
    )


def test_a_follower_past_a_nullable_tail_keeps_the_run_per_char():
    """``x ::= [a-z]+ n`` with ``n`` nullable: ``"a"`` after ``x`` can follow."""
    assert LOWER not in _units(
        _rule("root", (_ref("x"), _lit("a"))),
        _rule("x", (_word(), _ref("n"))),
        _rule("n", (OPTIONAL_DASH,)),
    )


def test_a_follower_first_reached_through_a_nullable_prefix_keeps_it_per_char():
    """``y ::= n "a"`` with ``n`` nullable: ``y`` may begin with ``"a"``."""
    assert LOWER not in _units(
        _rule("root", (_word(), _ref("y"))),
        _rule("y", (_ref("n"), _lit("a"))),
        _rule("n", (OPTIONAL_DASH,)),
    )


def test_vyx_indent_run_collapses():
    """``indent ::= " "*`` is followed by key, scope-path, ``"- "`` and
    ``"$"``, none of which begins with a space."""
    source = (GROUND_TRUTH / "vyx.gbnf").read_text(encoding="utf-8")
    grammar = normalize(canonical_grammar(source, GBNF_FLAVOUR))
    shapes = run_candidates(compile_tables(grammar)).values()
    space = IrCharClass(IrChr(" ")).normalized()
    assert (space, True) in {(unit.normalized(), empty) for unit, empty, _rid in shapes}


INDENTED = (
    'line ::= indent key "="\nindent ::= " "*\nkey ::= [A-Za-z\\x80-\\U0010FFFF]+\n'
)


def test_a_wide_unit_collapses_listed_by_what_it_excludes():
    """``key ::= [A-Za-z\\x80-\\U0010FFFF]+`` holds over a million code
    points; its run lists the 76 below U+0080 it leaves out, negated."""
    grammar = normalize(canonical_grammar(INDENTED, GBNF_FLAVOUR))
    runs = [
        atom
        for atom in recognition_tables(grammar).terms.atoms
        if isinstance(atom, RunTerm) and atom.negated
    ]
    assert len(runs) == 1
    assert len(runs[0].charset) == 128 - 52
    assert "a" in runs[0].charset and "\u00e9" in runs[0].charset
    assert "=" not in runs[0].charset


def test_a_follower_inside_a_co_finite_unit_keeps_the_run_per_char():
    """``[^"]* "x"``: the unit holds ``x``, so a longer run could eat it."""
    body = IrItem(IrNot(IrCharClass(IrChr('"'))), IrQuantifier(0, IrNone))
    assert not _units(_rule("root", (body, _lit("x"))))


JAPANESE = (
    'root ::= jp-char+ ("\\n" jp-char+)*\n'
    "jp-char ::= hiragana | katakana | punctuation | cjk\n"
    "hiragana ::= [\\u3041-\\u309F]\n"
    "katakana ::= [\\u30A1-\\u30FF]\n"
    "punctuation ::= [\\u3001-\\u303E]\n"
    "cjk ::= [\\u4E00-\\u9FFF]\n"
)
JAPANESE_TEXTS = (
    "\u3042",
    "\u65e5\u672c\u8a9e",
    "\u3042\n\u30a2",
    "a",
    "\u3042a",
    "\n",
    "",
)


def test_a_unit_too_large_to_list_on_either_side_runs_on_its_ranges():
    """japanese.gbnf's ``jp-char``: 21,244 members and over a million
    non-members, so its run tests membership by its ranges, and the collapsed
    tables recognise exactly what the plain ones do."""
    grammar = normalize(canonical_grammar(JAPANESE, GBNF_FLAVOUR))
    plain, collapsed = compile_tables(grammar), recognition_tables(grammar)
    runs = [atom for atom in collapsed.terms.atoms if isinstance(atom, RunTerm)]
    assert runs and all(isinstance(run.charset, Spans) for run in runs)
    for text in JAPANESE_TEXTS:
        want = accept_item(Kernel(plain, text, record_links=False).run()) >= 0
        got = accept_item(Kernel(collapsed, text, record_links=False).run()) >= 0
        assert got == want, text


def test_a_ranged_run_builds_the_model_the_per_char_tables_build():
    """``@lexical root`` over japanese.gbnf folds its text through a ranged
    run; the Earley model equals the per-char tables' and the PDA's."""
    source = (GROUND_TRUTH / "japanese.gbnf").read_text(encoding="utf-8")
    compiled = compile_text(
        source,
        cache_key="lexruns-ranged-run",
        flavour="gbnf",
        directives=Directives(lexical=frozenset({"root"})),
    )
    product = model_product(compiled.codegen_grammar, compiled.product)
    runs = [atom for atom in product.tables.terms.atoms if isinstance(atom, RunTerm)]
    assert [type(run.charset) for run in runs] == [Spans]
    plain = compile_tables(product.instance_grammar)
    for text in ("\u3042\u65e5\u672c", "\u3042 \u30a2\u3001"):
        got = earley_model(
            product.instance_grammar, text, compiled.product, product.tables
        )
        want = earley_model(product.instance_grammar, text, compiled.product, plain)
        assert got == want == compiled.parse(text, cores=1)


def test_a_collapsed_indent_recognises_what_the_plain_tables_do():
    """vyx's shape in miniature: the indent run collapses, and the collapsed
    tables accept and refuse exactly what the plain ones do."""
    grammar = normalize(canonical_grammar(INDENTED, GBNF_FLAVOUR))
    plain, collapsed = compile_tables(grammar), recognition_tables(grammar)
    assert any(isinstance(atom, RunTerm) for atom in collapsed.terms.atoms)
    for text in ("a=", "   ab=", " \u00e9=", " =", "  ", "a"):
        want = accept_item(Kernel(plain, text, record_links=False).run()) >= 0
        got = accept_item(Kernel(collapsed, text, record_links=False).run()) >= 0
        assert got == want, text


# ── recognition_tables ────────────────────────────────────────────────


def test_recognition_tables_collapses_when_candidates_exist():
    """recognition_tables introduces RunTerm atoms for a grammar with candidates."""
    g = normalize(ABNF_GRAMMAR)
    tables = recognition_tables(g)
    assert any(isinstance(atom, RunTerm) for atom in tables.terms.atoms)


def test_recognition_tables_returns_plain_when_no_candidates():
    """A grammar with nothing to collapse gets back the plain compiled tables."""
    g = _digit_grammar()
    assert recognition_tables(g) is compile_tables(g)


def test_recognition_tables_memoised_per_grammar_object():
    """Calling recognition_tables twice on the SAME grammar returns the same tables."""
    g = normalize(ABNF_GRAMMAR)
    first = recognition_tables(g)
    second = recognition_tables(g)
    assert first is second


def test_recognition_tables_distinct_grammar_objects_get_distinct_tables():
    """Two structurally-identical but distinct grammar objects don't share tables."""
    g1 = normalize(ABNF_GRAMMAR)
    g2 = normalize(ABNF_GRAMMAR)
    assert recognition_tables(g1) is not recognition_tables(g2)


ABNF_SAMPLES = (
    'rule = "a" "b"\r\n',
    "foo = bar / baz\r\n",
    "x = 1*DIGIT\r\n",
    "not a valid abnf line at all !!\r\n",
    "",
)


def test_recognition_tables_matches_plain_recognition_on_samples():
    """The maximally-collapsed tables accept/reject exactly as the plain ones do."""
    g = normalize(ABNF_GRAMMAR)
    plain = compile_tables(g)
    collapsed = recognition_tables(g)
    for text in ABNF_SAMPLES:
        plain_accept = accept_item(Kernel(plain, text, record_links=False).run()) >= 0
        collapsed_accept = (
            accept_item(Kernel(collapsed, text, record_links=False).run()) >= 0
        )
        assert plain_accept == collapsed_accept, text


# ── unit_leaves ───────────────────────────────────────────────────────


def test_unit_leaves_non_synthetic_rule_is_itself():
    """A non-synthetic rule id resolves to itself, with no bare terminal."""
    tables = compile_tables(_digit_grammar())
    rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, rid) == ({rid}, False)


def test_unit_leaves_synthetic_charset_rule_transitive_leaves_and_bare_flag():
    """A synthetic rule hopping through another synthetic rule collects the
    transitive non-synthetic leaf and sets has_bare from the bare-terminal arm."""
    g = nested_synthetic_grammar()
    tables = compile_tables(g)
    outer_rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}outer"]
    digit_rid = tables.decode.rule_ids["digit"]
    assert unit_leaves(tables, outer_rid) == ({digit_rid}, True)


def test_unit_leaves_malformed_shape_returns_none():
    """A synthetic rule whose arm is not a single item is not a charset shape."""
    bad = malformed_synthetic_rule()
    g = IrAst(rules=IrSeq(bad), start=f"{SYNTHETIC_PREFIX}bad")
    tables = compile_tables(g)
    rid = tables.decode.rule_ids[f"{SYNTHETIC_PREFIX}bad"]
    assert unit_leaves(tables, rid) is None
