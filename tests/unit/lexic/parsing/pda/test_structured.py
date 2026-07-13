"""Tests for lexic.parsing.pda.structured — folding-aware loop gates (Task 6.6).

Pins the P3-structured / P5-probe classification: which comment-bearing /
LWS-folding loop decisions demote to an ``SG_MATCH`` / ``SG_SCAN`` / ``SG_PROBE``
:class:`~lexic.parsing.pda.scanner.ScanGate`, and the ``_exit_is_noise`` /
``_sem_follow_clear`` / ``_probe_candidate`` licences behind them. Shares the
hand-grammar helpers with ``test_noise`` (the same idiom) and exercises the
real GBNF/ABNF self-grammars.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir.base import IrChr
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing.pda.analysis import GrammarAnalysis
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.scanner import SG_MATCH, SG_PROBE, SG_SCAN
from lexic.parsing.pda.structured import (
    _exit_is_noise,
    _probe_candidate,
    _sem_follow_clear,
    noise_roots,
)
from tests.unit.lexic.parsing.pda.test_analysis import _self_grammar_analysis
from tests.unit.lexic.parsing.pda.test_noise import _WS, _analysis, _item, _noise_rule


def test_noise_roots_on_gbnf_self_grammar():
    """GBNF's run-forming noise roots are its comment/whitespace rule ``n`` and
    the trailing-comment closure member ``tail-comment``."""
    roots = noise_roots(_self_grammar_analysis("gbnf"))
    assert {"n", "tail-comment"} <= roots


def test_noise_roots_on_abnf_self_grammar():
    """ABNF's run-forming noise roots include ``filler``/``c-wsp``/``c-nl`` —
    the LWS-folding and comment/blank-line closure members."""
    roots = noise_roots(_self_grammar_analysis("abnf"))
    assert {"filler", "c-wsp", "c-nl"} <= roots


def _struct_gate(analysis: GrammarAnalysis, rule_name: str, item_index: int):
    """The stored :class:`ScanGate` for ``rule_name``'s body-arm-0 item at
    ``item_index`` — the taxonomy's identity-keyed struct-gate channel."""
    items = [i for i in analysis.rules[rule_name].body[0] if isinstance(i, IrItem)]
    return analysis.taxonomy.struct_loop_gates[id(items[item_index])]


def test_gbnf_sequence_loop_demotes_to_sg_probe():
    """GBNF ``sequence[1]``'s exit skips ``n`` into the next rule's rulename,
    overlapping the item's own lead — the P5 probe (``rulename n* "::="``)
    breaks the tie, refuting the take reading on a matched header."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "sequence", 1)
    assert gate.kind == SG_PROBE
    assert gate.probe is not None
    rev = {v: k for k, v in gate.rec.index.items()}
    name_idx, _noise_idx, lit, take_on_match = gate.probe
    assert rev[name_idx] == "rulename"
    assert lit == "::="
    assert take_on_match is False


def test_gbnf_alternation_loop_demotes_to_sg_scan():
    """GBNF ``alternation[1]``'s bar-arm continuation is a plain post-noise
    take on ``|`` — no header ambiguity, so ``SG_SCAN`` suffices."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "alternation", 1)
    assert gate.kind == SG_SCAN
    assert gate.take is not None
    chars, negated = gate.take
    assert chars == frozenset({"|"})
    assert negated is False


def test_abnf_has_two_pure_folding_sg_match_gates():
    """ABNF's ``rulelist``/``rl-cont`` trailing ``c-wsp*`` loops are pure
    folding (noise↔noise exit) — both demote to ``SG_MATCH``."""
    analysis = _self_grammar_analysis("abnf")
    rulelist_gate = _struct_gate(analysis, "rulelist", 3)
    rl_cont_gate = _struct_gate(analysis, "rl-cont", 0)
    assert rulelist_gate.kind == SG_MATCH
    assert rl_cont_gate.kind == SG_MATCH


def test_gbnf_n_loop_demotes_to_sg_match_via_sem_follow_clear():
    """GBNF's own ``n`` rule (``nunit+``) demotes to ``SG_MATCH`` too — not via
    :func:`_exit_is_noise` (its own body has no arm-local exit to inspect),
    but via the P6 precision clause :func:`_sem_follow_clear`: the ``#``
    overlap with the trailing ``tail-comment`` resolves by exact recognition
    (an incomplete ``comment-line`` simply fails to match)."""
    analysis = _self_grammar_analysis("gbnf")
    gate = _struct_gate(analysis, "n", 0)
    assert gate.kind == SG_MATCH


# ── _sem_follow_clear (the P6 precision clause for SG_MATCH) ───────────────


class _Scope(NamedTuple):
    """A minimal duck-typed stand-in for analysis' private ``_Scope`` — only
    the ``rule``/``tail``/``body`` fields :func:`_sem_follow_clear` reads."""

    rule: str
    tail: CharSet
    body: bool = True


def test_sem_follow_clear_true_on_the_gbnf_n_shape():
    """The positive control, at the function level: ``n``'s own ``nunit+``
    loop (empty rest, no semantic follower) clears."""
    analysis = _self_grammar_analysis("gbnf")
    items = [i for i in analysis.rules["n"].body[0] if isinstance(i, IrItem)]
    scope = _Scope("n", analysis.follow["n"])
    assert _sem_follow_clear(analysis, items, 0, scope) is True


def test_sem_follow_clear_denies_on_a_semantic_follower():
    """A semantic ref after the loop denies the clause outright — the
    arm-local check alone cannot see past a real content boundary."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    z = IrRule("z", IrAlternation(IrSequence(_item(IrLiteral("z")))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("z"))]
    shaped = IrRule("shaped", IrAlternation(IrSequence(*items)))
    analysis = _analysis(shaped, nz, z, start="shaped")
    scope = _Scope("shaped", analysis.follow["shaped"])
    assert _sem_follow_clear(analysis, items, 0, scope) is False


def test_sem_follow_clear_denies_when_the_overeaten_char_is_semantic():
    """An empty rest, but the loop's own alphabet overlaps a char that CAN
    follow the rule as semantic content (``sem_follow_table``) — denied."""
    cc = IrCharClass(IrRange(IrChr(97), IrChr(99)))  # [a-c]
    nz = IrRule(
        "nz", IrAlternation(IrSequence(_item(cc, lo=0, hi=None))), semantic=False
    )
    items = [_item(IrRuleRef("nz"), lo=0, hi=None)]
    shaped = IrRule("shaped", IrAlternation(IrSequence(*items)))
    top = IrRule(
        "top",
        IrAlternation(IrSequence(_item(IrRuleRef("shaped")), _item(IrLiteral("a")))),
    )
    analysis = _analysis(top, shaped, nz, start="top")
    scope = _Scope("shaped", analysis.follow["shaped"])
    assert _sem_follow_clear(analysis, items, 0, scope) is False


# ── _exit_is_noise (the SG_MATCH licence) ───────────────────────────────────


def test_exit_is_noise_denies_on_nullable_semantic_follower():
    """A nullable but ``semantic=True`` follower after the loop denies the
    licence — the exit could steal semantic content, not just noise."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    z = IrRule(
        "z",
        IrAlternation(
            IrSequence(_item(IrLiteral(""))), IrSequence(_item(IrLiteral("z")))
        ),
    )
    loop_item = _item(IrRuleRef("nz"), lo=0, hi=None)
    items = [loop_item, _item(IrRuleRef("z"), lo=0, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, z, start="root")
    assert _exit_is_noise(analysis, items, 0) is False


def test_exit_is_noise_denies_on_empty_rest():
    """An empty rest (the loop is the arm's last item) denies the licence —
    the exit is then the rule's FOLLOW, whose noise-ness this arm-local walk
    cannot see."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, start="root")
    assert _exit_is_noise(analysis, items, 0) is False


def test_exit_is_noise_licenses_a_required_noise_follower():
    """A required (``lo>=1``) non-semantic follower licenses the take — the
    exit boundary is itself noise."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    nz2 = _noise_rule("nz2", IrSequence(_item(IrLiteral(";"))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("nz2"), lo=1, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, nz2, start="root")
    assert _exit_is_noise(analysis, items, 0) is True


def test_exit_is_noise_licenses_an_optional_noise_only_run_to_arm_end():
    """A run of optional non-semantic refs to the arm's end (GBNF ``grammar``'s
    trailing ``n? tail-comment?`` shape) licenses the take."""
    nz = _noise_rule("nz", IrSequence(_item(_WS, lo=0, hi=None)))
    nz2 = _noise_rule("nz2", IrSequence(_item(IrLiteral(";"))))
    items = [_item(IrRuleRef("nz"), lo=0, hi=None), _item(IrRuleRef("nz2"), lo=0, hi=1)]
    root = IrRule("root", IrAlternation(IrSequence(*items)))
    analysis = _analysis(root, nz, nz2, start="root")
    assert _exit_is_noise(analysis, items, 0) is True


# ── _probe_candidate (P5 uniqueness + refutation licence) ──────────────────


def _name_ws_headers(*extra: IrRule, start: str, headers: tuple[IrRule, ...]):
    """A hand grammar: ``name`` ([a-z]+), a noise ``ws``, and the given header
    rules, wired to a ``start`` rule that references every header (so each is
    reachable)."""
    name = IrRule(
        "name",
        IrAlternation(IrSequence(_item(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))),
    )
    ws = _noise_rule("ws", IrSequence(_item(_WS, lo=0, hi=None)))
    return _analysis(name, ws, *headers, *extra, start=start)


def test_probe_candidate_none_when_two_distinct_headers_cover_the_overlap():
    """Two distinct header-shaped rules (``name ws+ "::="`` and
    ``name ws+ "="``), both covering the overlap via the same ``R`` — the spec
    is not unique, so no probe is licensed (the decision stays an island)."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    h2 = IrRule(
        "h2",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("="), lo=1, hi=1),
            )
        ),
    )
    root = IrRule(
        "root",
        IrAlternation(IrSequence(_item(IrRuleRef("h1")), _item(IrRuleRef("h2")))),
    )
    analysis = _name_ws_headers(root, start="root", headers=(h1, h2))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) is None


def test_probe_candidate_none_when_lead_char_follows_r_elsewhere():
    """A single header (``name ws+ "::="``), but ``name`` is also directly
    followed by ``":"`` (``L``'s lead char) elsewhere in the grammar — the
    refutation licence fails, so no probe is licensed."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    other = IrRule(
        "other",
        IrAlternation(
            IrSequence(_item(IrRuleRef("name")), _item(IrLiteral(":"), lo=1, hi=1))
        ),
    )
    root = IrRule(
        "root",
        IrAlternation(IrSequence(_item(IrRuleRef("h1")), _item(IrRuleRef("other")))),
    )
    analysis = _name_ws_headers(root, start="root", headers=(h1, other))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) is None


def test_probe_candidate_finds_the_unique_spec_with_no_interference():
    """The positive control: one header, no competing spec, no refutation —
    ``_probe_candidate`` resolves the ``(R, noise root, L)`` triple."""
    h1 = IrRule(
        "h1",
        IrAlternation(
            IrSequence(
                _item(IrRuleRef("name")),
                _item(IrRuleRef("ws"), lo=1, hi=None),
                _item(IrLiteral("::="), lo=1, hi=1),
            )
        ),
    )
    root = IrRule("root", IrAlternation(IrSequence(_item(IrRuleRef("h1")))))
    analysis = _name_ws_headers(root, start="root", headers=(h1,))
    overlap = CharSet.from_chars("a")
    assert _probe_candidate(analysis, frozenset({"ws"}), overlap) == (
        "name",
        "ws",
        "::=",
    )
