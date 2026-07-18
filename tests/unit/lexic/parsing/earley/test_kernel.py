"""Tests for lexic.parsing.earley.kernel — KernelState, Kernel, FastTree.

New module: the flat int-coded Earley loop over compiled ParserTables. This
file covers the behavioral facts callable through the public surface
(``Kernel.run()`` + reading ``.cols``/``.st``/``.accept``, or the top-level
``recognize()``/``parse()`` functions), plus the Leo right-recursion
correctness tests ported from the deleted ``test_ops.py`` (see that file's
git history — its target module ``lexic.parsing.ops`` no longer exists;
its behavioral coverage lives here now, re-expressed over ``Kernel``).
"""

from __future__ import annotations

from typing import cast

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrNoneType, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import derivations, parse, recognize
from lexic.parsing.earley.chart import Chart
from lexic.parsing.earley.forest import ParseTree, PayloadLeaf, SppfNode
from lexic.parsing.earley.kernel import FastTree, Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tables import (
    ADVANCE,
    ORIGIN_BITS,
    ORIGIN_MASK,
    compile_tables,
)
from tests.unit.lexic.parsing.ir_fixtures import digit_grammar as _digit_grammar
from tests.unit.lexic.parsing.ir_fixtures import word_grammar as _word_grammar

# ── Grammar helpers ───────────────────────────────────────────────────


def _norm(*rules: IrRule, start: str) -> IrAst:
    """Build and normalise an IrAst from a sequence of rules."""
    return normalize(IrAst(rules=IrSeq(*rules), start=start))


def _star(char: str, rule_name: str = "S") -> IrAst:
    """Grammar: S = '<char>'*  (zero or more)."""
    return _norm(
        IrRule(
            rule_name,
            IrAlternation(IrSequence(IrItem(IrLiteral(char), IrQuantifier(0, IrNone)))),
        ),
        start=rule_name,
    )


def _plus(char: str, rule_name: str = "S") -> IrAst:
    """Grammar: S = '<char>'+  (one or more)."""
    return _norm(
        IrRule(
            rule_name,
            IrAlternation(IrSequence(IrItem(IrLiteral(char), IrQuantifier(1, IrNone)))),
        ),
        start=rule_name,
    )


def _undefined_ref_grammar() -> IrAst:
    """top = missing ; 'missing' is referenced but never defined."""
    return IrAst(
        rules=IrSeq(
            IrRule("top", IrAlternation(IrSequence(IrItem(IrRuleRef("missing")))))
        ),
        start="top",
    )


# ── Prediction seeding: undefined rule ref seeds nothing ──────────────


def test_undefined_ref_recognize_never_crashes_and_fails():
    """recognize() on a grammar referencing an undefined rule fails cleanly."""
    g = _undefined_ref_grammar()
    assert recognize(g, "anything") == 0
    assert recognize(g, "") == 0


def test_undefined_ref_kernel_accept_is_negative():
    """Kernel.run() over an undefined-ref grammar never resolves accept."""
    tables = compile_tables(_undefined_ref_grammar())
    kernel = Kernel(tables, "x").run()
    assert kernel.accept == -1


# ── FIRST-gated prediction: kernel seeding behavior (Task 2) ──────────


def test_arm_gated_out_by_first_charset_is_not_seeded_at_column():
    """s = digit / letter — a digit char seeds only the digit arm at column 0.

    Partitions ``s``'s own dot-0 seeds by whether their gate contains the
    scanned char (``gate is None`` also counts as seeding, per the
    always-seed rule), then checks the packed dot-0 item's presence in
    ``cols[0]`` directly — no reliance on ``waiting``/``scannable`` internals.
    """
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    letter = IrRule(
        "letter",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    s = IrRule(
        "s",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("digit"))),
            IrSequence(IrItem(IrRuleRef("letter"))),
        ),
    )
    g = IrAst(rules=IrSeq(s, digit, letter), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    seeds = tables.codes.rule_seed_gates[s_rid]
    char = "5"
    should_seed = [
        shifted for shifted, _sym, gate in seeds if gate is None or char in gate
    ]
    should_not_seed = [
        shifted
        for shifted, _sym, gate in seeds
        if gate is not None and char not in gate
    ]
    assert should_seed and should_not_seed  # both partitions are non-empty

    kernel = Kernel(tables, char).run()
    for shifted in should_seed:
        assert shifted in kernel.cols[0]
    for shifted in should_not_seed:
        assert shifted not in kernel.cols[0]


def test_eof_column_only_gate_none_arms_seed():
    """s = digit / '' over empty input: at the EOF column, only the empty
    (always-seed) arm seeds — the digit arm's gate matches no char, and the
    EOF column's char slice is the empty string, which is in no charset."""
    digit = IrRule(
        "digit",
        IrAlternation(IrSequence(IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))))),
    )
    s = IrRule(
        "s",
        IrAlternation(IrSequence(IrItem(IrRuleRef("digit"))), IrSequence()),
    )
    g = IrAst(rules=IrSeq(s, digit), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    seeds = tables.codes.rule_seed_gates[s_rid]
    (always_shifted,) = [shifted for shifted, _sym, gate in seeds if gate is None]
    (gated_shifted,) = [shifted for shifted, _sym, gate in seeds if gate is not None]

    kernel = Kernel(tables, "").run()
    assert always_shifted in kernel.cols[0]
    assert gated_shifted not in kernel.cols[0]


def test_empty_literal_terminal_arm_never_seeds_at_any_column():
    """An IrLiteral('') unit's FIRST gate is frozenset() — a real (unpoisoned)
    but empty charset, distinct from the `None` always-seed sentinel — so the
    arm seeds at no column, for any input."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrLiteral("")))))
    g = IrAst(rules=IrSeq(rule), start="s")
    tables = compile_tables(g)
    s_rid = tables.decode.rule_ids["s"]
    ((shifted, _sym, gate),) = tables.codes.rule_seed_gates[s_rid]
    assert gate == frozenset()

    for text in ("", "a", "ab"):
        kernel = Kernel(tables, text).run()
        assert all(shifted not in col for col in kernel.cols)


# ── Completion advancement: two-rule grammar ──────────────────────────


def test_kernel_accepts_valid_two_char_word():
    """word = letter letter accepts 'hi' — kernel.accept resolves >= 0."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi").run()
    assert kernel.accept >= 0


def test_kernel_rejects_wrong_input():
    """word = letter letter rejects a digit — kernel.accept stays -1."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "h1").run()
    assert kernel.accept == -1


def test_kernel_cols_grows_one_per_char():
    """Kernel.cols has len(text) + 1 columns after construction."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi")
    assert len(kernel.cols) == 3


# ── Aycock-Horspool nullable advance ───────────────────────────────────


def test_nullable_star_accepts_empty_via_kernel():
    """S = 'a'* (normalized) recognizes the empty string."""
    g = _star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "").run()
    assert kernel.accept >= 0


def test_nullable_star_accepts_single_via_kernel():
    """S = 'a'* recognizes a single 'a'."""
    g = _star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a").run()
    assert kernel.accept >= 0


def test_nullable_star_accepts_many_via_kernel():
    """S = 'a'* recognizes a run of 'a's."""
    g = _star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "aaa").run()
    assert kernel.accept >= 0


# ── Leo correctness: right-recursive grammars accept/reject properly ──
# (ported from the deleted test_ops.py)


def test_leo_star_accepts_empty():
    """S = 'a'* accepts the empty string."""
    g = _star("a")
    assert recognize(g, "") == 1


def test_leo_star_accepts_single():
    """S = 'a'* accepts a single 'a'."""
    g = _star("a")
    assert recognize(g, "a") == 1


def test_leo_star_accepts_many():
    """S = 'a'* accepts a run of four 'a's."""
    g = _star("a")
    assert recognize(g, "aaaa") == 1


def test_leo_star_rejects_wrong_char():
    """S = 'a'* rejects input containing a 'b'."""
    g = _star("a")
    assert recognize(g, "aab") == 0


def test_leo_plus_rejects_empty():
    """S = 'a'+ rejects the empty string."""
    g = _plus("a")
    assert recognize(g, "") == 0


def test_leo_plus_accepts_one():
    """S = 'a'+ accepts a single 'a'."""
    g = _plus("a")
    assert recognize(g, "a") == 1


def test_leo_plus_accepts_many():
    """S = 'a'+ accepts a run of five 'a's."""
    g = _plus("a")
    assert recognize(g, "aaaaa") == 1


def test_leo_star_star_sequence():
    """S = 'a'* 'b'* accepts '', 'aaa', 'bbb', 'aabb', rejects 'ba'."""
    g = _norm(
        IrRule(
            "S",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("b"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        start="S",
    )
    assert recognize(g, "") == 1
    assert recognize(g, "aaa") == 1
    assert recognize(g, "bbb") == 1
    assert recognize(g, "aabb") == 1
    assert recognize(g, "ba") == 0


def test_leo_indirect_ruleref_star():
    """S = X*  where  X = 'a' | 'b'  (right-recursive via an indirect ref)."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = _norm(s_rule, x_rule, start="S")
    assert recognize(g, "") == 1
    assert recognize(g, "abba") == 1
    assert recognize(g, "c") == 0


# ── Parse correctness: Leo-on-parse returns correct trees ────────────


def test_leo_parse_star_single():
    """S = 'a'* — parse 'a' returns correct tree."""
    g = _star("a")
    tree = parse(g, "a")
    assert tree is not None


def test_leo_parse_star_many():
    """S = 'a'* — parse 'aaaa' returns correct tree."""
    g = _star("a")
    tree = parse(g, "aaaa")
    assert tree is not None


def test_leo_parse_plus_many():
    """S = 'a'+ — parse 'aaaaaa' returns correct tree (deep right-recursion)."""
    g = _plus("a")
    tree = parse(g, "aaaaaa")
    assert tree is not None


def test_leo_parse_deep_right_recursion():
    """Leo-on-parse: parse 200 'a's — would crash at ~300 without depth safety."""
    g = _star("a")
    tree = parse(g, "a" * 200)
    assert tree is not None


def test_leo_parse_indirect_ruleref():
    """Leo-on-parse: indirect right-recursion via ruleref."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = _norm(s_rule, x_rule, start="S")
    tree = parse(g, "abba")
    assert tree is not None


# ── Leo engaging on a long right-recursive input: no stack overflow ───


def test_leo_engages_on_long_input_no_recursion_error():
    """S = 'a'* over 200+ chars does not stack overflow and produces a tree."""
    g = _star("a")
    text = "a" * 250
    tree = parse(g, text)
    assert isinstance(tree, ParseTree)


def test_leo_engages_on_long_input_via_kernel_run():
    """Kernel.run() over 200+ chars resolves accept without crashing."""
    g = _star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a" * 250).run()
    assert kernel.accept >= 0


# ── Scan advancement — accept/reject truth values ─────────────────────


def test_scan_accepts_single_char():
    """digit grammar accepts a single valid char."""
    assert recognize(_digit_grammar(), "5") == 1


def test_scan_rejects_wrong_char():
    """digit grammar rejects a non-matching char."""
    assert recognize(_digit_grammar(), "z") == 0


def test_scan_rejects_too_long_input():
    """digit grammar (single char) rejects multi-char input."""
    assert recognize(_digit_grammar(), "12") == 0


def test_scan_rejects_too_short_input():
    """digit grammar rejects the empty string."""
    assert recognize(_digit_grammar(), "") == 0


# ── FastTree single-derivation build ═══════════════════════════════════


def test_fast_tree_builds_correct_shape_for_two_char_word():
    """FastTree(kernel).build(handle) mirrors old tree-shape assertions."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi", record_links=True).run()
    assert kernel.accept >= 0
    handle = (kernel.accept << ORIGIN_BITS) | len("hi")
    tree = FastTree(kernel).build(handle)
    assert isinstance(tree, ParseTree)
    assert tree.symbol == IrRuleRef("word")
    assert len(tree.kids) == 2
    assert isinstance(tree.kids[0], ParseTree)
    assert isinstance(tree.kids[1], ParseTree)
    assert tree.kids[0].kids[0] == IrLiteral("h")
    assert tree.kids[1].kids[0] == IrLiteral("i")


def test_fast_tree_builds_correct_shape_for_digit():
    """FastTree over a single-char digit grammar builds a one-kid tree."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "9", record_links=True).run()
    handle = (kernel.accept << ORIGIN_BITS) | 1
    tree = FastTree(kernel).build(handle)
    assert isinstance(tree, ParseTree)
    assert tree.symbol == IrRuleRef("digit")
    assert tree.kids[0] == IrLiteral("9")


# ── FastTree returns IrNone on ambiguous keys ──────────────────────────


def test_fast_tree_returns_ir_none_on_ambiguous_grammar(sss_grammar: IrAst):
    """FastTree.build() misses (returns IrNone) on an ambiguous grammar's handle."""
    g = normalize(sss_grammar)
    tables = compile_tables(g)
    kernel = Kernel(tables, "aaa", record_links=True).run()
    assert kernel.accept >= 0
    handle = (kernel.accept << ORIGIN_BITS) | len("aaa")
    result = FastTree(kernel).build(handle)
    assert isinstance(result, IrNoneType)
    assert result is IrNone


# ── to_chart / accept_node decode shapes ──────────────────────────────


def test_accept_node_returns_sppf_node_on_success():
    """accept_node() returns an SppfNode when accept >= 0."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "5", record_links=True).run()
    node = kernel.accept_node()
    assert isinstance(node, SppfNode)


def test_accept_node_returns_ir_none_on_failure():
    """accept_node() returns IrNone (IrNoneType) when accept == -1."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "z", record_links=True).run()
    assert kernel.accept == -1
    node = kernel.accept_node()
    assert isinstance(node, IrNoneType)


def test_to_chart_returns_chart_with_links():
    """to_chart() returns a Chart whose links table has entries."""
    tables = compile_tables(_word_grammar())
    kernel = Kernel(tables, "hi", record_links=True).run()
    chart = kernel.to_chart()
    assert isinstance(chart, Chart)
    assert len(chart.links) > 0


# ── expand_leo chain rebuild ────────────────────────────────────────────


def test_expand_leo_via_to_chart_reconstructs_unambiguous_derivation():
    """to_chart() (which expands all leo_links) lets derivations() reconstruct
    the single unambiguous derivation for a long right-recursive input."""
    g = _star("a")
    text = "a" * 60
    trees = derivations(g, text)
    assert len(trees) == 1
    assert isinstance(trees[0], ParseTree)


def test_to_chart_idempotent_across_repeat_calls():
    """Calling to_chart() twice on the same finished kernel agrees / no exception."""
    g = _star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a" * 60, record_links=True).run()
    chart1 = kernel.to_chart()
    chart2 = kernel.to_chart()
    assert len(chart1.links) == len(chart2.links)


def _embedded_ambiguous() -> IrAst:
    """w = p ; p = u u* ; u = [ab]+ — p's split ambiguity embedded under w."""
    ab = IrCharClass(IrRange(IrChr(97), IrChr(98)))
    return _norm(
        IrRule("w", IrAlternation(IrSequence(IrItem(IrRuleRef("p"))))),
        IrRule(
            "p",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("u")),
                    IrItem(IrRuleRef("u"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        IrRule("u", IrAlternation(IrSequence(IrItem(ab, IrQuantifier(1, IrNone))))),
        start="w",
    )


def test_to_chart_expands_leo_links_under_mixed_provenance():
    """A Leo top that also gained normal-completer families keeps its chains.

    Over "aab" the embedded grammar records p's whole-input completion both
    through the normal completer (two families in ``links``) and through a
    deferred Leo chain (one more in ``leo_links``) — mixed provenance.
    ``to_chart()`` must materialise the deferred family too (L4: the old
    ``key not in links`` guard silently dropped it).
    """
    tables = compile_tables(_embedded_ambiguous())
    kernel = Kernel(tables, "aab", record_links=True).run()
    mixed = [k for k in kernel.st.leo_links if k in kernel.st.links]
    assert mixed  # the L4 precondition: mixed provenance actually occurs here
    kernel.to_chart()
    for key in mixed:
        for entry in kernel.st.leo_links[key]:
            assert entry in kernel.st.links[key]


# ── ORIGIN_BITS capacity error ──────────────────────────────────────────


def test_kernel_construction_rejects_input_at_capacity():
    """Constructing Kernel with len(text) >= ADVANCE raises UnsupportedConstructError."""
    tables = compile_tables(_digit_grammar())
    huge = "a" * ADVANCE
    with pytest.raises(UnsupportedConstructError):
        Kernel(tables, huge)


def test_kernel_construction_accepts_input_just_under_capacity_len_check():
    """A text one shorter than ADVANCE does not raise at construction time."""
    tables = compile_tables(_digit_grammar())
    text = "a" * (ADVANCE - 1)
    kernel = Kernel(tables, text)
    assert len(kernel.cols) == ADVANCE


# ── decode_item ──────────────────────────────────────────────────────────


def test_decode_item_returns_earley_item_shape():
    """decode_item(item) returns the (IrRuleRef, IrSequence, dot, origin) tuple."""
    tables = compile_tables(_digit_grammar())
    kernel = Kernel(tables, "5", record_links=True).run()
    decoded = kernel.decode_item(kernel.accept)
    assert isinstance(decoded, tuple)
    assert len(decoded) == 4
    rule_ref, seq, dot, origin = decoded
    assert isinstance(rule_ref, IrRuleRef)
    assert rule_ref == IrRuleRef("digit")
    assert dot == len(seq)
    assert origin == 0


# ── accept_items / root_ambiguous (L2 root arm-choice) ────────────────


def _twin_arm_grammar() -> IrAst:
    """v ::= a | b, a/b both "x" — the start completes the whole input two ways."""
    return _norm(
        IrRule("v", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
        IrRule("a", IrLiteral("x")),
        IrRule("b", IrLiteral("x")),
        start="v",
    )


def test_accept_items_lists_every_accepting_production():
    """A twin-arm start yields two accepting items (one per production)."""
    kernel = Kernel(compile_tables(_twin_arm_grammar()), "x", record_links=True).run()
    items = kernel.accept_items()
    assert len(items) == 2
    # Both are origin-0 completions of the start rule over the whole input.
    for it in items:
        assert it & ORIGIN_MASK == 0
        assert kernel.decode_item(it)[0] == IrRuleRef("v")


def test_accept_items_empty_on_no_parse():
    """accept_items() is empty when the input does not derive."""
    kernel = Kernel(compile_tables(_twin_arm_grammar()), "z", record_links=True).run()
    assert kernel.accept_items() == []


def test_root_ambiguous_true_for_twin_arms():
    """root_ambiguous is True when the start completes via ≥2 productions."""
    kernel = Kernel(compile_tables(_twin_arm_grammar()), "x", record_links=True).run()
    assert kernel.root_ambiguous is True


def test_root_ambiguous_false_for_single_production():
    """root_ambiguous is False for an unambiguous single-production accept."""
    kernel = Kernel(compile_tables(_digit_grammar()), "5", record_links=True).run()
    assert kernel.root_ambiguous is False


# ── can_extend_at — the islands seam's valid-prefix probe ─────────────


def test_can_extend_at_true_when_an_item_faces_the_char(sss_grammar):
    """``s = s s / 'a'`` over 'aa': at col 1 an in-progress item awaits 'a'."""
    tables = compile_tables(sss_grammar)
    kern = Kernel(tables, "aa")
    assert kern.longest_start_completion() is not None
    assert kern.can_extend_at(1, "a") is True


def test_can_extend_at_sighted_refusal_when_nothing_seeds(sss_grammar):
    """Over 'ax' the col-1 seeds were gated by 'x' and none admitted — the
    empty scannable is a SIGHTED refusal (probe char == window char)."""
    tables = compile_tables(sss_grammar)
    kern = Kernel(tables, "ax")
    assert kern.longest_start_completion() is not None
    assert not kern.st.scannable[1]
    assert kern.can_extend_at(1, "x") is False


def test_can_extend_at_out_of_domain_char_answers_may(sss_grammar):
    """A probe char differing from the column's window char proves nothing —
    conservative MAY (the gates were evaluated with the other char)."""
    tables = compile_tables(sss_grammar)
    kern = Kernel(tables, "ax")
    kern.longest_start_completion()
    assert kern.can_extend_at(1, "b") is True


def test_can_extend_at_blind_delegate_end_answers_may(sss_grammar):
    """A delegate-landing column is blind regardless of chart content.

    Landings are derived from ``Kernel.delegated`` handles (low bits = end
    column) — inject one landing at column 1 and the probe must answer MAY.
    """
    tables = compile_tables(sss_grammar)
    kern = Kernel(tables, "ax")
    kern.longest_start_completion()
    kern.delegated[(7 << ORIGIN_BITS) | 1] = cast(PayloadLeaf, None)
    assert kern.can_extend_at(1, "x") is True
