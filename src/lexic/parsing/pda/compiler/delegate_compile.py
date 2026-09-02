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

from typing import Any, Callable, Mapping

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrItem, IrLeaf, IrNoneType, IrRuleRef, IrSelf
from lexic.parsing.binding import ModelBinding
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis

_DELEGATE_MIN_ATOMS = 4
"""Triviality floor for delegation: a delegable rule must be able to match a run
*worth* the sub-run setup — an unbounded loop anywhere in its reachable
interior, or at least this many terminal atoms. Rules below it (1–3-char
literals / char classes) stay pure-Earley; the win is proportional to
delegated-span length, so short interiors sit near break-even. Benchmark-tuned
against the synthetic long-interior grammar + the four bench grammars (Task 6.2
perf gate); raise it if short-interior delegation regresses perf."""


def _delegable(analysis: GrammarAnalysis, name: str) -> bool:
    """Whether rule ``name`` is worth delegating: island-free AND above the floor.

    Two conditions over the rule's reachable interior (following non-island rule
    refs):

    1. **Island-free.** A reachable *island* reference disqualifies the rule —
       delegating it would still re-enter the Earley island sub-parse for that
       reference (nested ``island_parse``), so the PDA-clone wrapper adds cost
       without removing the Earley work. Only self-contained deterministic
       interiors (json ``number`` / ``string``, not the value-recursive
       ``object`` / ``array``) are a real win — measured: including
       island-referencing rules regressed json ~1.4×.
    2. **Above the floor.** The interior must match a run *worth* the sub-run
       setup — an unbounded (``*`` / ``+`` / ``{n,}``) loop, or at least
       :data:`_DELEGATE_MIN_ATOMS` terminal atoms.

    :param analysis: The island sub-grammar analysis.
    :param name: The candidate rule name.
    :returns: ``True`` when the rule is island-free and clears the floor.
    """
    seen: set[str] = set()
    stack = [name]
    atoms = 0
    worth = False
    while stack:
        rname = stack.pop()
        if rname in seen or rname not in analysis.rules:
            continue
        seen.add(rname)
        for arm in analysis.rules[rname].body:
            for item in arm:
                if not isinstance(item, IrItem):
                    continue
                hi = item.quantifier.hi
                if isinstance(hi, IrNoneType) or int(hi) > 1:
                    worth = True  # an unbounded / repeated loop — long span potential
                atom = item.atom
                if isinstance(atom, IrRuleRef):
                    if str(atom) in analysis.islands:
                        return False  # island ref — nested Earley, no delegation win
                    stack.append(str(atom))
                else:
                    atoms += 1
    return worth or atoms >= _DELEGATE_MIN_ATOMS


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
    binding: ModelBinding
    seams: tuple[Callable[..., Any], Callable[..., Any]]
    _cache: dict[str, dict[int, object]]

    def __init__(
        self,
        lifted: IrAst,
        name_to_rid: Mapping[str, int],
        binding: ModelBinding,
        seams: tuple[Callable[..., Any], Callable[..., Any]],
    ) -> None:
        """Bind one grammar's delegate-compile ingredients + the injected seams."""
        self.lifted = lifted
        self.name_to_rid = name_to_rid
        self.binding = binding
        self.seams = seams
        self._cache = {}

    def for_island(self, name: str) -> dict[int, object]:
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

    def _compile(self, island_name: str) -> dict[int, object]:
        """Compile island ``island_name``'s delegate clones (uncached)."""
        analysis = GrammarAnalysis(IrAst(self.lifted.rules, island_name))
        delegable = _delegable_names(analysis, island_name)
        if not delegable:
            return {}
        compiler_factory, flatten_clones = self.seams
        compiler: Any = compiler_factory(
            analysis, self.binding.rules, self.binding.construction
        )
        rid_key: dict[int, object] = {}
        try:
            for rname in delegable:
                rid_key[self.name_to_rid[rname]] = compiler.ensure_rule(
                    rname, analysis.hard_follow[rname]
                )
        except UnsupportedConstructError:
            return {}  # an interior atom the clone compiler cannot handle
        shells = flatten_clones(compiler.clones, self.binding)
        return {rid: shells[key] for rid, key in rid_key.items()}

    def reset(self) -> None:
        """Drop the per-island cache (a test seam for the A/B parity gate)."""
        self._cache.clear()
