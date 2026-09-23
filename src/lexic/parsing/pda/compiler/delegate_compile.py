"""Island-interior delegate compile (Task 6.2) — the per-island clone selector.

Split out of :mod:`lexic.parsing.pda.compiler.clones` (C0302 headroom, and a clean
leaf): given one island's sub-grammar, this picks the conflict-free interior
rules worth delegating and compiles each to a PDA clone the island's Earley
sub-parse runs in place of the item machinery — unconditionally, for every
island. A leaf w.r.t. the clone compiler — the two clone-compiler entry points
it needs (:class:`PdaCompiler` and the ``flatten_clones`` lowering) arrive as
**injected callables** on :class:`DelegateSource`, so this module imports
nothing from ``clones`` and the ``clones → delegate_compile`` arrow runs one
way.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Mapping

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLeaf,
    IrNoneType,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.specs import CloneKey

_DELEGATE_MIN_ATOMS = 4
"""Triviality floor for delegation: a delegable rule must be able to match a run
*worth* the sub-run setup. ONE match must be able to span this many terminal
atoms (:func:`_longest`), which an unbounded loop always can. Rules below it (1–3-char
literals / char classes) stay pure-Earley; the win is proportional to
delegated-span length, so short interiors sit near break-even. Benchmark-tuned
against the synthetic long-interior grammar + the four bench grammars (Task 6.2
perf gate); raise it if short-interior delegation regresses perf."""


def _delegable(analysis: GrammarAnalysis, name: str) -> bool:
    """Whether rule ``name`` may be delegated: one end, island-free, above the floor.

    Three conditions over the rule's reachable interior (:func:`_interior`,
    following non-island rule refs and inline groups):

    1. **One end.** A delegate files ONE completion, at the end its run
       reaches; the island's chart never sees another. That stands for every
       derivation only if no other end can be followed, which holds where every
       decision is settled by lookahead. A reachable rule that picks an extent
       by policy (:attr:`Taxonomy.policy_ends
       <lexic.parsing.pda.analysis.taxonomy.Taxonomy.policy_ends>`, a stop-set
       or greedy exit) can end at several places a continuation accepts, and
       injecting one would hide the rest: an arm choice the island must refuse
       would arrive with one arm already gone.
    2. **Island-free.** A reachable *island* reference disqualifies the rule —
       delegating it would still re-enter the Earley island sub-parse for that
       reference (nested ``island_parse``), so the PDA-clone wrapper adds cost
       without removing the Earley work. Only self-contained deterministic
       interiors (json ``number`` / ``string``, not the value-recursive
       ``object`` / ``array``) are a real win — measured: including
       island-referencing rules regressed json ~1.4×.
    3. **Above the floor.** ONE match must be able to span a run *worth* the
       sub-run setup: :data:`_DELEGATE_MIN_ATOMS` terminal atoms along a single
       derivation (:func:`_longest`), which any unbounded (``*`` / ``+`` /
       ``{n,}``) loop reaches. Counting across alternatives would let a rule
       of many short arms through, and that tiny-span shape is what regressed
       json.

    :param analysis: The island sub-grammar analysis.
    :param name: The candidate rule name.
    :returns: ``True`` when the rule has one end, is island-free and clears
        the floor.
    """
    if name in analysis.taxonomy.policy_ends:
        return False  # its run picks one of several followable ends
    for item in _interior(analysis, name):
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            if str(atom) in analysis.islands:
                return False  # island ref — nested Earley, no delegation win
            if str(atom) in analysis.taxonomy.policy_ends:
                return False  # its run picks one of several followable ends
    return _longest(analysis, name, {}) >= _DELEGATE_MIN_ATOMS


def _longest(analysis: GrammarAnalysis, name: str, memo: dict[str, int]) -> int:
    """How many terminal atoms ONE match of rule ``name`` can span, capped at
    the floor.

    The largest arm, not the sum of them: alternatives are never matched
    together, and twelve one-letter arms still match one letter. An unbounded
    loop, or a recursion back into a rule being measured, reaches the cap.
    """
    got = memo.get(name)
    if got is not None:
        return got
    rule = analysis.rules.get(name)
    if rule is None:
        return _DELEGATE_MIN_ATOMS
    memo[name] = _DELEGATE_MIN_ATOMS  # a recursion back here can grow without bound
    memo[name] = max(_seq_longest(analysis, list(arm), memo) for arm in rule.body)
    return memo[name]


def _seq_longest(
    analysis: GrammarAnalysis, items: list[IrSelf], memo: dict[str, int]
) -> int:
    """The longest single match of a sequence, capped at the floor: the sum of
    its items, each its atom's span times how often it can repeat."""
    total = 0
    for item in items:
        if not isinstance(item, IrItem):
            continue
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            one = _longest(analysis, str(atom), memo)
        elif isinstance(atom, IrAlternation):
            one = max(
                (_seq_longest(analysis, list(arm), memo) for arm in atom), default=0
            )
        else:
            one = 1
        if one == 0:
            continue
        hi = item.quantifier.hi
        total += _DELEGATE_MIN_ATOMS if isinstance(hi, IrNoneType) else one * int(hi)
    return min(total, _DELEGATE_MIN_ATOMS)


def _interior(analysis: GrammarAnalysis, name: str) -> Iterator[IrItem]:
    """Every item of rule ``name``'s reachable interior, each rule once.

    Descends rule references AND inline groups: a group is part of the rule
    that holds it, so what a group reaches is what the rule reaches.
    """
    seen: set[str] = set()
    rules = [name]
    while rules:
        rname = rules.pop()
        if rname in seen or rname not in analysis.rules:
            continue
        seen.add(rname)
        pending = [list(arm) for arm in analysis.rules[rname].body]
        while pending:
            for item in pending.pop():
                if not isinstance(item, IrItem):
                    continue
                yield item
                if isinstance(item.atom, IrAlternation):
                    pending.extend(list(arm) for arm in item.atom)
                elif isinstance(item.atom, IrRuleRef):
                    rules.append(str(item.atom))


def _delegable_names(analysis: GrammarAnalysis, island_name: str) -> list[str]:
    """The island-interior rules of ``island_name`` safe to delegate to a clone.

    A rule delegates when it is conflict-free under the sub-grammar analysis
    (not in :attr:`~GrammarAnalysis.islands`, which already subsumes
    :attr:`~GrammarAnalysis.fail_islands`), non-nullable (a zero-width delegated
    span would bypass the normal completer's non-empty-completion path — see
    :meth:`~lexic.parsing.earley.kernel.loop.kernel.Kernel._inject_delegate`), semantic (a
    noise rule carries no model / reduction the splice can pass through), not the
    island root itself, and :func:`_delegable` (island-free + above the floor).

    :param analysis: The island sub-grammar analysis.
    :param island_name: The island root (excluded — it is the conflicted rule).
    :returns: The delegable rule names.
    """
    return [
        rname
        for rname in analysis.rules
        if rname != island_name
        and rname not in analysis.islands
        and rname not in analysis.nullable
        and analysis.rules[rname].semantic
        and _delegable(analysis, rname)
    ]


class DelegateSource(IrLeaf[IrSelf, IrSelf]):
    """The lazy per-island delegate compiler — the runtime's delegate table.

    Holds one grammar's delegate-compile ingredients and a per-island cache; the
    runtime asks :meth:`for_island` for a rule_id → flat-clone map, computed
    once per island and cached. The clone-compiler entry points arrive in
    ``seams`` (injected as ``(clones.PdaCompiler,
    clones.flatten_clones)``) so this leaf never imports
    :mod:`lexic.parsing.pda.compiler.clones`. Attached to the runtime
    :class:`~lexic.parsing.pda.compiler.program.flatten.PdaProgram`, not the artifact, so the
    ``PdaTables`` attribute count is untouched.

    :ivar lifted: The lifted codegen grammar (analysis substrate).
    :ivar name_to_rid: Rule name → its id in the island tables.
    :ivar binding: The bound model product delegated clones are baked from —
        its rules give their build state, its constructor table is what a
        record completion indexes, and its fold is what they still complete
        through.
    :ivar seams: ``(compiler_factory, flatten_clones)`` — the injected clone
        compiler and its lowering pass.
    """

    __slots__ = ("lifted", "name_to_rid", "binding", "seams", "_cache")

    lifted: IrAst
    name_to_rid: Mapping[str, int]
    binding: ModelExecutable
    seams: tuple[Callable[..., Any], Callable[..., Any]]
    _cache: dict[str, dict[int, FlatClone]]

    def __init__(
        self,
        lifted: IrAst,
        name_to_rid: Mapping[str, int],
        binding: ModelExecutable,
        seams: tuple[Callable[..., Any], Callable[..., Any]],
    ) -> None:
        """Bind one grammar's delegate-compile ingredients + the injected seams."""
        self.lifted = lifted
        self.name_to_rid = name_to_rid
        self.binding = binding
        self.seams = seams
        self._cache = {}

    def for_island(self, name: str) -> dict[int, FlatClone]:
        """The delegate clones for island ``name`` (rule_id → flat clone), cached.

        Runs a fresh :class:`GrammarAnalysis` over the island sub-grammar
        (``IrAst(lifted.rules, name)``), selects the delegable interior rules
        (:func:`_delegable_names`), and compiles each to a PDA clone cut against
        its sub-grammar hard FOLLOW. A conflict-free rule's stop-sets are
        call-site invariant, so the hard-FOLLOW tail yields the same span every
        predicting site would — one clone serves all sites. The clones lower
        into an independent shell set (its own optimiser pass), and the result
        keys each by the delegated rule's id in the island tables (= its
        position in ``lifted.rules``, the shared numbering every island adopts).

        :param name: The island rule name.
        :returns: rule_id → its delegate flat clone (empty when nothing is
            delegable or the interior cannot compile).
        """
        cached = self._cache.get(name)
        if cached is None:
            cached = self._compile(name)
            self._cache[name] = cached
        return cached

    def held(self, name: str) -> dict[int, FlatClone]:
        """The delegate clones already compiled for island ``name``, compiling
        nothing: what the artefact holds, for a reader that must not grow it.

        :param name: The island rule name.
        :returns: rule_id → its delegate flat clone; empty when none is held.
        """
        return self._cache.get(name, {})

    def _compile(self, island_name: str) -> dict[int, FlatClone]:
        """Compile island ``island_name``'s delegate clones (uncached)."""
        analysis = GrammarAnalysis(
            IrAst(self.lifted.rules, island_name), delegated=True
        )
        delegable = _delegable_names(analysis, island_name)
        if not delegable:
            return {}
        compiler_factory, flatten_clones = self.seams
        compiler: Any = compiler_factory(analysis, self.binding.routines)
        rid_key: dict[int, CloneKey] = {}
        try:
            for rname in delegable:
                rid_key[self.name_to_rid[rname]] = compiler.ensure_rule(
                    rname, analysis.hard_follow[rname]
                )
        except UnsupportedConstructError:
            return {}  # an interior atom the clone compiler cannot handle
        shells = flatten_clones(compiler.clones)
        return {rid: shells[key] for rid, key in rid_key.items()}

    def reset(self) -> None:
        """Drop the per-island cache (a test seam for the A/B parity gate)."""
        self._cache.clear()
