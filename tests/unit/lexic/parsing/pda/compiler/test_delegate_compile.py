"""Unit tests for the island-interior delegate compile (Task 6.2).

Mirror of :mod:`lexic.parsing.pda.compiler.delegate_compile`. The end-to-end on-vs-off
parity + perf payoff live in :mod:`tests.integration.lexic.parity.test_delegation_parity`;
here we pin the classifier (one end, island-free, triviality floor) and the
:class:`DelegateSource` cache / no-delegates injection mechanism directly.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar, compile_text
from lexic.ir import IrAst
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.delegate_compile import DelegateSource, _delegable
from lexic.parsing.pda.compiler.program.flatten import FlatClone, clone_arms
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    GATE_ATTEMPT,
    OP_AVDISP,
    OP_AVSTR,
)
from tests.unit.lexic.parsing.parsing_helpers import prod
from tests.unit.lexic.parsing.pda.compiler.pda_compiler_helpers import compiled
from tools.benchmark.cases.grammars import BENCHES


class NoDelegates(DelegateSource):
    """A :class:`DelegateSource` that compiles nothing — the off arm of the
    A/B injection seam :mod:`tests.integration.lexic.parity.test_delegation_parity` uses
    (delegation is otherwise unconditional). Constructed the same way as
    the real source; only ``_compile`` differs."""

    def _compile(self, island_name: str) -> dict[int, FlatClone]:
        return {}


def test_delegable_accepts_island_free_long_run() -> None:
    """A long island-free run (``digits`` = ``[0-9]+``) clears the floor."""
    analysis, _source, _cg = compiled()
    assert _delegable(analysis, "digits")


def test_delegable_rejects_island_referencing_interior() -> None:
    """A rule reaching an island (``wrapped`` → ``item``) is not delegated.

    Delegating it would re-enter the Earley island sub-parse for that reference,
    so the PDA-clone wrapper is pure overhead (the json regression the floor
    fixes).
    """
    analysis, _source, _cg = compiled()
    assert "item" in analysis.islands
    assert not _delegable(analysis, "wrapped")


def test_delegable_rejects_short_interior() -> None:
    """A short bounded interior (``short`` = ``"z"``) sits below the floor."""
    analysis, _source, _cg = compiled()
    assert not _delegable(analysis, "short")


def test_source_for_island_returns_flat_clones_for_delegables() -> None:
    """``for_island`` yields rule_id → flat clone for the island's delegables."""
    _analysis, source, cg = compiled()
    delegates = source.for_island("item")
    assert delegates, "the item island should delegate its island-free interior"
    names = {prod(cg).instance_grammar.rules[rid].name for rid in delegates}
    assert "digits" in names and "wrapped" not in names
    assert all(isinstance(clone, FlatClone) for clone in delegates.values())


def test_no_delegates_variant_yields_no_delegates() -> None:
    """A :class:`NoDelegates` source, built from the real source's own
    construction ingredients, compiles nothing for any island — the
    injection mechanism the A/B parity harness swaps in for its off arm."""
    _analysis, source, _cg = compiled()
    off = NoDelegates(source.lifted, source.name_to_rid, source.binding, source.seams)
    assert off.for_island("item") == {}


def test_for_island_is_cached_until_reset() -> None:
    """``for_island`` memoises per island; ``reset`` drops the cache."""
    _analysis, source, _cg = compiled()
    first = source.for_island("item")
    assert source.for_island("item") is first  # same cached object
    source.reset()
    assert source.for_island("item") is not first  # recomputed after reset


# ── one end: a rule that picks its extent by policy never delegates ─────────

STOP_SET = (
    'root ::= expr\nexpr ::= expr op term | expr "|" term | term\n'
    'term ::= ("x" [a-z]+)+\nop ::= "+"\n'
)
"""``term``'s inner run can stop before any ``x`` or run on through it: where
an iteration ends is the greedy take's pick, one of several ends a
continuation accepts."""

LOOKAHEAD = (
    'root ::= expr\nexpr ::= expr op term | expr "or" term | term\n'
    'term ::= "ab" [x]+ | "ac" [y]+\nop ::= "and"\n'
)
"""``term``'s arms share ``a`` and part at the second character — demoted to a
k-window, which decides from the text, so there is still one end."""


def island_analysis(source: str, key: str) -> GrammarAnalysis:
    """The analysis delegation runs over: ``expr``'s island sub-grammar."""
    lifted = lift_optional_nullables(
        compile_text(source, cache_key=key).codegen_grammar
    )
    return GrammarAnalysis(IrAst(lifted.rules, "expr"), delegated=True)


def test_delegable_rejects_a_rule_whose_end_a_policy_picks() -> None:
    """Island-free and long, so every other condition passes — the ONE-END
    condition is what refuses it."""
    analysis = island_analysis(STOP_SET, "delegate-stop-set")
    assert "term" not in analysis.islands
    assert "term" in analysis.taxonomy.policy_ends
    assert not _delegable(analysis, "term")


def test_an_exact_lookahead_demotion_still_delegates() -> None:
    """Demoted, but by lookahead: no policy end, and the island keeps its one
    delegate."""
    analysis = island_analysis(LOOKAHEAD, "delegate-lookahead")
    assert analysis.demoted.get("term"), "the near miss stopped being demoted"
    assert "term" not in analysis.taxonomy.policy_ends
    compiled_grammar = compile_text(LOOKAHEAD, cache_key="delegate-lookahead-table")
    table = prod(compiled_grammar).pda.program.delegates.for_island("expr")
    assert len(table) == 1


def test_an_island_reached_only_through_a_group_disqualifies() -> None:
    """``w``'s one island reference sits inside an inline group, and a group is
    part of the rule that holds it — so the walk must enter it."""
    source = (
        'root ::= w+\nw ::= ("x" | item) "y"+\nitem ::= item "a" | item "b" | "c"\n'
    )
    grammar = compile_text(source, cache_key="delegate-island-in-group").codegen_grammar
    analysis = GrammarAnalysis(lift_optional_nullables(grammar))
    assert "item" in analysis.islands
    assert not _delegable(analysis, "w")


# ── the floor measures ONE match, never a sum across alternatives ───────────


def floor_clears(body: str) -> bool:
    """Whether rule ``x`` of ``body`` clears the floor, in a grammar where
    nothing else stops it from delegating."""
    source = f"root ::= x\nx ::= {body}\n"
    grammar = compile_text(source, cache_key=f"floor-{hash(body)}").codegen_grammar
    return _delegable(GrammarAnalysis(lift_optional_nullables(grammar)), "x")


def test_many_short_alternatives_stay_below_the_floor() -> None:
    """Twelve two-letter arms still match two letters: the tiny-span shape.
    (Two letters, because one-letter arms canonicalise into one class.)"""
    arms = [f'"{c}{c.lower()}"' for c in "RIPCUSANOEHW"]
    assert not floor_clears(" | ".join(arms))


def test_a_single_match_of_enough_atoms_clears_it() -> None:
    """Four atoms in sequence are four in every match."""
    assert floor_clears('"a" [b-c] "d" [e-f]')


def test_a_bounded_repeat_counts_every_occurrence() -> None:
    """``{4}`` is four atoms in one match; ``{3}`` is three."""
    assert floor_clears("[0-9]{4}")
    assert not floor_clears("[0-9]{3}")


def test_an_unbounded_loop_in_one_alternative_clears_it() -> None:
    """One arm can run long, so one match can: the largest arm decides."""
    assert floor_clears('"!" ("R" | "I" | "X:" [A-Z]+)')


# ── a delegate never holds a both-viable verdict site ───────────────────────

ATTEMPT_INTERIOR = (
    'root ::= expr\nexpr ::= expr op term | expr "or" term | term\n'
    'term ::= num | lst\nnum ::= "n" [0-9]+\nop ::= "and"\n'
    'lst ::= "(" sec+ tl ")"\nsec ::= stmt+ end\nstmt ::= [a!]\nend ::= [a;]\n'
    "tl ::= [a;!]*\n"
)
"""``expr`` is an island whose interior holds two kinds of rule side by side:
``num``, conflict-free and long, and ``lst``/``sec``, whose ``sec+`` loop the
analysis can only attempt (G4's shape)."""


def _reachable(root: FlatClone) -> list[FlatClone]:
    """Every clone a delegate can enter: its arms' payloads, dispatch targets
    and attempt entries' sub-clones, each once."""
    seen: set[int] = set()
    found: list[FlatClone] = []
    work: list[object] = [root]
    while work:
        clone = work.pop()
        if not isinstance(clone, FlatClone) or id(clone) in seen:
            continue
        seen.add(id(clone))
        found.append(clone)
        if clone.attempt is not None:
            work.extend(entry[-1] for entry in clone.attempt[1])
        if clone.mode == BUILD_DISPATCH:
            work.extend(target for *_gate, target in clone.selectors)
            work.append(clone.default)
        for arm in clone_arms(clone):
            work.extend(arm.payloads)
    return found


def _verdict_sites(clone: FlatClone) -> list[str]:
    """Where ``clone`` could reach a both-viable fork: an attempt clone, an
    attempt-gated loop, or an attempt-aware inline loop."""
    sites = ["attempt clone"] if clone.attempt is not None else []
    for arm in clone_arms(clone):
        for item, (kind, gate) in enumerate(zip(arm.kinds, arm.gate_kinds)):
            if gate == GATE_ATTEMPT or kind in (OP_AVSTR, OP_AVDISP):
                sites.append(f"item {item}")
    return sites


def _delegates(grammar: CompiledGrammar) -> list[FlatClone]:
    """Every delegate clone the grammar's islands compile."""
    source = prod(grammar).pda.program.delegates
    if source is None:
        return []
    islands = GrammarAnalysis(source.lifted).islands
    return [one for name in islands for one in source.for_island(name).values()]


def test_no_delegate_program_holds_a_verdict_site() -> None:
    """A delegate runs an island's interior as a document prefix
    (``prefix_run``), where "did this side complete" would read a delegate's
    early completion as a death. That never matters, because no delegate can
    fork: the delegated analysis files every conflicted rule as an island,
    and delegation drops islands and whatever reaches one. Every roster
    grammar's delegates, and :data:`ATTEMPT_INTERIOR`'s, are walked whole."""
    grammars = [bench.compiled for bench in BENCHES]
    grammars.append(
        compile_text(ATTEMPT_INTERIOR, cache_key="delegate-attempt-interior")
    )
    walked = 0
    for grammar in grammars:
        for delegate in _delegates(grammar):
            for clone in _reachable(delegate):
                walked += 1
                assert not _verdict_sites(clone), (clone.name, _verdict_sites(clone))
    assert walked, "no delegate clone was walked, so the contract proves nothing"


def test_an_interior_that_attempts_is_never_delegated_beside_one_that_is() -> None:
    """The conflict-free ``num`` is delegated; ``sec``, whose loop the
    whole-grammar analysis attempts, and ``lst``, which reaches it, are not."""
    grammar = compile_text(ATTEMPT_INTERIOR, cache_key="delegate-attempt-interior")
    source = prod(grammar).pda.program.delegates
    assert isinstance(source, DelegateSource)
    whole = GrammarAnalysis(source.lifted)
    attempting = {
        name
        for name, rule in whole.rules.items()
        for arm in rule.body
        for item in arm
        if id(item) in whole.taxonomy.attempt_loops
    }
    assert {"sec", "lst"} <= attempting, attempting
    delegated = {
        str(source.lifted.rules[rid].name) for rid in source.for_island("expr")
    }
    assert "num" in delegated
    assert not delegated & attempting, delegated & attempting
