"""Noise/semantic attribution — the P6 licence + P3 noise-skip substrate.

A non-semantic rule's greedy stop-set may legally over-eat only chars whose
every possible source is *noise* (then the same bytes land in a different
split between adjacent noise fields: ``semantic_dump`` and ``to_text`` are
unchanged). The raw soft-FOLLOW set cannot answer that — it forgets where its
chars came from — so this module runs the same two fixpoints with **decomposed
attribution**:

- :func:`_sem_first_table` — per rule, the FIRST chars attributable to
  *semantic content*: a terminal (or inline group terminal) counts only inside
  a ``semantic=True`` rule; a ref to a non-semantic rule contributes nothing
  (its whole subtree is excluded from ``semantic_dump``, so chars stolen from
  it are noise↔noise by construction); a ref to a semantic rule contributes
  that rule's own decomposition (NOT its raw FIRST, which is polluted by its
  leading noise refs); an undefined ref is conservatively
  :attr:`~lexic.parsing.pda.core.charsets.CharSet.ANY` (denies the licence).
- :func:`sem_follow_table` — the soft-FOLLOW fixpoint re-run over those
  semantic firsts, seeded empty (end-of-input is not semantic content).

It also homes the **P3 noise-skip** analysis half (Task 6.4): the
grammar-derived skippable alphabet :func:`noise_alphabet` (``W`` — the union
of FIRST over *nullable non-semantic* rules: json whitespace, ABNF
whitespace+``;``, GBNF whitespace+``#`` — never hardcoded), the residual-FIRST
fixpoint :class:`ResidualFirst` (the first NON-``W`` chars a sequence can
reach: pure-``W`` atoms are transparent, ``W``-free atoms contribute their
FIRST, a *terminal* mixing both poisons the branch, refs recurse), and the
:func:`peek_arm_gate` / :func:`peek_loop_gate` classifiers that decide whether
a decision separates on its first post-noise char. The runtime peek is
non-consuming (the winner re-parses its noise), so a P3 gate is structurally
fail-soft — these conditions buy *determinism* (zero fallback), not bare
soundness.

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis.analysis` (the kwindow precedent): the
analysis is taken as an ``Any``-typed oracle argument (``rules`` /
``atom_first`` / ``item_nullable``), so ``analysis`` imports this, never the
reverse. Atom steps route through open :class:`~lexic.ir.mapping.IrTypeMap`
tables with raising defaults.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

from lexic.ir.action import IrAction
from lexic.ir.base import IrLambda, IrLeaf, IrNoneType, IrSelf
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.pda.core.charsets import CharSet

__all__ = [
    "sem_follow_table",
    "stopset_escapes_soft_follow",
    "noise_greedy_licensed",
    "noise_alphabet",
    "ResidualFirst",
    "peek_arm_gate",
    "peek_loop_gate",
]


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


class _SemCtx(IrLeaf[IrSelf, IrSelf]):
    """The attribution context riding ``nc`` for the :data:`_SEM_FIRST` bodies.

    :ivar analysis: The grammar-analysis oracle (rules/atom_first/item_nullable).
    :ivar semantic: Whether the enclosing rule is ``semantic=True``.
    :ivar table: The growing per-rule semantic-FIRST table.
    """

    __slots__ = ("analysis", "semantic", "table")

    analysis: Any
    semantic: bool
    table: dict[str, CharSet]

    def __init__(self, analysis: Any, semantic: bool, table: dict[str, CharSet]):
        self.analysis = analysis
        self.semantic = semantic
        self.table = table


def _sf_terminal(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> CharSet:
    """A terminal's chars are semantic content iff the enclosing rule is."""
    ctx = cast(_SemCtx, nc[0])
    return ctx.analysis.atom_first(n) if ctx.semantic else CharSet.EMPTY


def _sf_ruleref(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> CharSet:
    """A ref contributes the target's own decomposition — nothing for noise.

    An undefined target is conservatively ANY (the licence is an optimisation;
    unknown content must deny it, never grant it).
    """
    ctx = cast(_SemCtx, nc[0])
    name = str(n)
    rules = ctx.analysis.rules
    if name not in rules:
        return CharSet.ANY
    if not rules[name].semantic:
        return CharSet.EMPTY
    return ctx.table[name]


def _sf_group(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> CharSet:
    """A group's semantic FIRST is the union of its arms' (same enclosing rule)."""
    assert isinstance(n, IrAlternation)
    ctx = cast(_SemCtx, nc[0])
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(_seq_sem_first(_items(arm), ctx))
    return out


_SEM_FIRST: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_sf_terminal)),
    IrAction(IrCharClass, IrLambda(_sf_terminal)),
    IrAction(IrNot, IrLambda(_sf_terminal)),
    IrAction(IrRuleRef, IrLambda(_sf_ruleref)),
    IrAction(IrAlternation, IrLambda(_sf_group)),
)
"""Open atom-type semantic-FIRST dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


def _atom_sem_first(atom: IrSelf, ctx: _SemCtx) -> CharSet:
    """The semantic-FIRST contribution of one atom under ``ctx``."""
    return cast(CharSet, _SEM_FIRST.resolve(atom).eval(ctx.analysis, atom, (ctx,)))


def _seq_sem_first(items: Sequence[IrItem], ctx: _SemCtx) -> CharSet:
    """Semantic FIRST of an item sequence — union until the first non-nullable."""
    out = CharSet.EMPTY
    for item in items:
        out = out.union(_atom_sem_first(item.atom, ctx))
        if not ctx.analysis.item_nullable(item):
            break
    return out


def _sem_first_table(analysis: Any) -> dict[str, CharSet]:
    """The per-rule semantic-FIRST fixpoint (chaotic iteration to stability)."""
    table: dict[str, CharSet] = {name: CharSet.EMPTY for name in analysis.rules}
    changed = True
    while changed:
        changed = False
        for name, rule in analysis.rules.items():
            ctx = _SemCtx(analysis, bool(rule.semantic), table)
            acc = CharSet.EMPTY
            for arm in rule.body:
                acc = acc.union(_seq_sem_first(_items(arm), ctx))
            if acc != table[name]:
                table[name] = acc
                changed = True
    return table


class _SemFeed(IrLeaf[IrSelf, IrSelf]):
    """Feed context riding ``nc`` for the :data:`_SEM_FEED` bodies.

    :ivar eff: The effective semantic continuation feeding this atom.
    :ivar tgt: The growing semantic-FOLLOW table.
    :ivar ctx: The attribution context (analysis + semantic-FIRST table).
    """

    __slots__ = ("eff", "tgt", "ctx")

    eff: CharSet
    tgt: dict[str, CharSet]
    ctx: _SemCtx

    def __init__(self, eff: CharSet, tgt: dict[str, CharSet], ctx: _SemCtx):
        self.eff = eff
        self.tgt = tgt
        self.ctx = ctx


def _fd_terminal(_d: IrSelf, _n: IrSelf, _nc: object) -> bool:
    """A terminal atom has no sub-rule semantic FOLLOW to update."""
    return False


def _fd_ruleref(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Union the effective semantic continuation into a defined target's entry."""
    fd = cast(_SemFeed, nc[0])
    name = str(n)
    if name not in fd.tgt:
        return False
    grown = fd.tgt[name].union(fd.eff)
    if grown != fd.tgt[name]:
        fd.tgt[name] = grown
        return True
    return False


def _fd_group(_d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Feed the effective semantic continuation into each of a group's arms."""
    assert isinstance(n, IrAlternation)
    fd = cast(_SemFeed, nc[0])
    changed = False
    for arm in n:
        if _feed_sem(_items(arm), fd.eff, fd.ctx, fd.tgt):
            changed = True
    return changed


_SEM_FEED: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_fd_terminal)),
    IrAction(IrCharClass, IrLambda(_fd_terminal)),
    IrAction(IrNot, IrLambda(_fd_terminal)),
    IrAction(IrRuleRef, IrLambda(_fd_ruleref)),
    IrAction(IrAlternation, IrLambda(_fd_group)),
)
"""Open atom-type semantic-FOLLOW-feed dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


def _feed_sem(
    items: Sequence[IrItem], tail: CharSet, ctx: _SemCtx, tgt: dict[str, CharSet]
) -> bool:
    """One right-to-left semantic-FOLLOW feed over a sequence arm.

    Mirrors the soft-FOLLOW walk with the semantic decomposition in place of
    raw FIRSTs: every defined ref target's entry grows by the effective
    semantic continuation; a group recurses its arms against it.

    :returns: ``True`` iff any entry grew.
    """
    changed = False
    cont = tail
    for item in reversed(items):
        atom = item.atom
        hi = item.quantifier.hi
        eff = cont
        if isinstance(hi, IrNoneType) or int(hi) > 1:
            eff = eff.union(_atom_sem_first(atom, ctx))
        fd = _SemFeed(eff, tgt, ctx)
        if cast(bool, _SEM_FEED.resolve(atom).eval(ctx.analysis, atom, (fd,))):
            changed = True
        first = _atom_sem_first(atom, ctx)
        cont = cont.union(first) if ctx.analysis.item_nullable(item) else first
    return changed


def sem_follow_table(analysis: Any) -> dict[str, CharSet]:
    """Rule name → the chars that can follow it as *semantic* content.

    The P6 licence oracle: a non-semantic rule's greedy over-eat is
    noise↔noise exactly when its gap chars never intersect this set. Seeded
    empty at the start rule (end-of-input is not semantic content).

    :param analysis: The grammar analysis (``rules`` / ``atom_first`` /
        ``item_nullable`` oracle — ``Any``-typed to keep this module a leaf).
    :returns: The semantic-FOLLOW table.
    """
    sem_first = _sem_first_table(analysis)
    tgt: dict[str, CharSet] = {name: CharSet.EMPTY for name in analysis.rules}
    changed = True
    while changed:
        changed = False
        for name, rule in analysis.rules.items():
            ctx = _SemCtx(analysis, bool(rule.semantic), sem_first)
            for arm in rule.body:
                if _feed_sem(_items(arm), tgt[name], ctx, tgt):
                    changed = True
    return tgt


def stopset_escapes_soft_follow(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Any
) -> bool:
    """Whether item ``k``'s non-greedy stop-set is *not* call-site invariant.

    A stop-set is sound only when its continuation is invariant across reference
    sites. An all-nullable rest runs to the rule's FOLLOW; the PDA cuts each
    clone against its own *hard* tail, so a soft-only follower also in
    ``FIRST(atom)`` is over-eaten (``x ::= [a-c]*`` / ``root ::= x "ab"?`` silent
    wrong model) — a **semantic** such rule becomes a fail-island.

    :param analysis: The grammar-analysis oracle (``Any``-typed leaf argument).
    :param scope: The conflict-walk scope (``tail`` / ``hard_tail``).
    :returns: ``True`` iff the stop-set can escape into the soft FOLLOW.
    """
    if not all(analysis.item_nullable(i) for i in items[k + 1 :]):
        return False
    gap = analysis.cont_at(items, k, scope.tail).subtract(scope.hard_tail)
    return analysis.atom_first(items[k].atom).overlaps(gap)


def noise_greedy_licensed(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Any
) -> bool:
    """The P6 noise-greedy licence — an escaping stop-set may eat greedily when
    the over-eaten split is provably noise↔noise.

    Licensed iff (SIM_60's pinned condition + the plan's precision clause): a
    rule-body scope on a ``semantic=False`` rule; no hard (required) follower in
    the loop's own alphabet; and no over-eatable char — the SIM's ``gap``, the
    soft-only followers intersected with the loop's alphabet (which also
    structurally excludes the retained EOF sentinel) — can follow the rule as
    *semantic* content (:func:`sem_follow_table` — a gap char reachable via a
    semantic soft-follower keeps the island). Then the same bytes land in a
    different split between adjacent noise fields: ``semantic_dump`` and
    ``to_text`` are unchanged.

    :param analysis: The grammar-analysis oracle (``Any``-typed leaf argument).
    :param scope: The conflict-walk scope (``body`` / ``rule`` / ``tail`` /
        ``hard_tail``).
    :returns: ``True`` iff the greedy over-eat is licensed as noise↔noise.
    """
    if not scope.body or analysis.rules[scope.rule].semantic:
        return False
    first = analysis.atom_first(items[k].atom)
    if scope.hard_tail.overlaps(first):
        return False
    gap = analysis.cont_at(items, k, scope.tail).subtract(scope.hard_tail)
    eatable = gap.subtract(gap.subtract(first))
    return not sem_follow_table(analysis)[scope.rule].overlaps(eatable)


# ── P3: the noise-skip substrate ────────────────────────────────────────────


def noise_alphabet(analysis: Any) -> CharSet:
    """``W`` — the skippable-noise alphabet, derived from the grammar.

    The union of FIRST over *nullable non-semantic* rules: a rule that can
    derive ε and whose match is structural noise is a skippable run's root
    (json ``ws``; ABNF ``filler`` — whitespace + ``;``; GBNF whitespace +
    ``#``). Non-nullable non-semantic rules (``dquote``, ``defined`` — dropped
    from the reduced tree but syntactically *required*) contribute nothing:
    they are token markers, not runs.
    """
    out = CharSet.EMPTY
    for name, rule in analysis.rules.items():
        if not rule.semantic and name in analysis.nullable:
            out = out.union(analysis.first[name])
    return out


def _rf_terminal(d: IrSelf, n: IrSelf, _nc: object) -> "CharSet | None":
    """A terminal is opaque (``W``-free), transparent (pure-``W``), or poison.

    A terminal whose alphabet mixes ``W`` and non-``W`` chars poisons the
    branch: after a maximal skip the cursor could sit *inside* its match, so
    no post-noise selector is sound for it.
    """
    rf = cast(ResidualFirst, d)
    first = rf.analysis.atom_first(n)
    non_w = first.subtract(rf.w)
    if non_w.is_empty():
        return CharSet.EMPTY
    if not first.overlaps(rf.w):
        return non_w
    return None


def _rf_ruleref(d: IrSelf, n: IrSelf, _nc: object) -> "CharSet | None":
    """A ref contributes its target's residual FIRST (undefined → poison)."""
    rf = cast(ResidualFirst, d)
    return rf.table.get(str(n))


def _rf_group(d: IrSelf, n: IrSelf, _nc: object) -> "CharSet | None":
    """A group's residual FIRST unions its arms' (any poisoned arm poisons)."""
    assert isinstance(n, IrAlternation)
    rf = cast(ResidualFirst, d)
    out = CharSet.EMPTY
    for arm in n:
        got = rf.seq(_items(arm))
        if got is None:
            return None
        chars, _open_end = got
        out = out.union(chars)
    return out


_RF_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_rf_terminal)),
    IrAction(IrCharClass, IrLambda(_rf_terminal)),
    IrAction(IrNot, IrLambda(_rf_terminal)),
    IrAction(IrRuleRef, IrLambda(_rf_ruleref)),
    IrAction(IrAlternation, IrLambda(_rf_group)),
)
"""Open atom-type residual-FIRST dispatch — an unregistered atom raises
:exc:`~lexic.exceptions.UnsupportedConstructError` on the miss."""


class ResidualFirst(IrLeaf[IrSelf, IrSelf]):
    """The residual-FIRST solver: first NON-``W`` chars, per rule and sequence.

    Pure-``W`` atoms are transparent (the runtime skip absorbs them, nullable
    or not); ``W``-free atoms contribute their FIRST and close the walk unless
    nullable; a terminal mixing both **poisons** (``None``) — the skip could
    land inside it. The solver IS the dispatcher slot ``d`` handed to the
    :data:`_RF_ATOM` bodies.

    :ivar analysis: The grammar-analysis oracle.
    :ivar w: The skippable alphabet (:func:`noise_alphabet`).
    :ivar table: Rule name → its residual FIRST (``None`` = poisoned), solved
        to fixpoint on construction.
    """

    __slots__ = ("analysis", "w", "table")

    analysis: Any
    w: CharSet
    table: dict[str, CharSet | None]

    def __init__(self, analysis: Any, w: CharSet) -> None:
        """Solve the per-rule residual-FIRST fixpoint over ``analysis.rules``."""
        self.analysis = analysis
        self.w = w
        self.table = {name: CharSet.EMPTY for name in analysis.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in analysis.rules.items():
                acc: CharSet | None = CharSet.EMPTY
                for arm in rule.body:
                    got = self.seq(_items(arm))
                    if got is None:
                        acc = None
                        break
                    assert acc is not None
                    acc = acc.union(got[0])
                if acc != self.table[name]:
                    self.table[name] = acc
                    changed = True

    def atom(self, atom: IrSelf) -> "CharSet | None":
        """The residual FIRST of one atom (``None`` = poisoned).

        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast("CharSet | None", _RF_ATOM.resolve(atom).eval(self, atom, ()))

    def seq(self, items: Sequence[IrItem]) -> "tuple[CharSet, bool] | None":
        """The residual FIRST of an item sequence, or ``None`` (poisoned).

        :returns: ``(chars, open_end)`` — ``open_end`` is ``True`` when the
            walk fell off the sequence's end (every item transparent or
            nullable), i.e. the post-noise char could come from the FOLLOW
            side too; a gate must then bail.
        """
        out = CharSet.EMPTY
        for item in items:
            sub = self.atom(item.atom)
            if sub is None:
                return None
            out = out.union(sub)
            first = self.analysis.atom_first(item.atom)
            transparent = first.subtract(self.w).is_empty()
            if not (self.analysis.item_nullable(item) or transparent):
                return out, False
        return out, True


def peek_arm_gate(
    analysis: Any, arms: Sequence[Sequence[IrItem]], w: CharSet
) -> "tuple[CharSet, ...] | None":
    """Per-arm post-noise selectors when the arm decision separates, else ``None``.

    Separates when every arm's residual FIRST is closed (not end-open),
    non-empty, unpoisoned, and pairwise disjoint — the runtime then skips the
    maximal ``W`` run (non-consuming) and selects the arm containing the first
    non-``W`` char; the winner re-parses its own noise (fail-soft).
    """
    if w.is_empty():
        return None
    rf = ResidualFirst(analysis, w)
    sets: list[CharSet] = []
    for items in arms:
        got = rf.seq(items)
        if got is None:
            return None
        chars, open_end = got
        if open_end or chars.is_empty():
            return None
        sets.append(chars)
    for i, chars_i in enumerate(sets):
        for chars_j in sets[i + 1 :]:
            if chars_i.overlaps(chars_j):
                return None
    return tuple(sets)


def peek_loop_gate(
    analysis: Any,
    items: Sequence[IrItem],
    idx: int,
    soft_cont: CharSet,
    w: CharSet,
) -> "CharSet | None":
    """The take-set when item ``idx``'s take/skip separates post-noise, else ``None``.

    ``take`` is the residual FIRST of one more iteration (plus the rest of the
    arm); the exit side is the soft continuation minus ``W``. Disjoint ⇒ the
    runtime peeks past the ``W`` run and takes another iteration exactly when
    the post-noise char is in ``take`` (the iteration re-parses the noise —
    fail-soft).
    """
    if w.is_empty():
        return None
    rf = ResidualFirst(analysis, w)
    item = items[idx]
    once = IrItem(item.atom, IrQuantifier(1, item.quantifier.hi))
    got = rf.seq([once, *items[idx + 1 :]])
    if got is None:
        return None
    take, open_end = got
    if open_end or take.is_empty():
        return None
    if take.overlaps(soft_cont.subtract(w)):
        return None
    return take
