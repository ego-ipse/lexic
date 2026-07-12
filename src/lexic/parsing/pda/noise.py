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
  :attr:`~lexic.parsing.pda.charsets.CharSet.ANY` (denies the licence).
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

A leaf w.r.t. :mod:`lexic.parsing.pda.analysis` (the kwindow precedent): the
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
from lexic.parsing.pda.charsets import CharSet
from lexic.parsing.pda.scanner import (
    SG_MATCH,
    SG_PROBE,
    SG_SCAN,
    Recognizer,
    ScanGate,
    build_recognizer,
)

__all__ = [
    "sem_follow_table",
    "stopset_escapes_soft_follow",
    "noise_greedy_licensed",
    "noise_alphabet",
    "ResidualFirst",
    "peek_arm_gate",
    "peek_loop_gate",
    "noise_roots",
    "structured_loop_gate",
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
    table: "dict[str, CharSet | None]"

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


# ── P3 structured / P5 probe: folding-aware loop gates (Task 6.6) ────────────


def noise_roots(analysis: Any) -> frozenset[str]:
    """The run-forming noise-rule names — the structured scanner's roots.

    A non-semantic rule referenced *anywhere* with a nullable quantifier
    (``lo == 0``, i.e. ``*``/``?``) forms skippable runs (ABNF ``c-wsp``/
    ``filler``/``c-nl``; GBNF ``n``); the recognizer pulls their transitive
    closure. Non-nullable-only refs (required token markers) are excluded.
    """
    roots: set[str] = set()
    for rule in analysis.rules.values():
        for arm in rule.body:
            for item in _items(arm):
                atom = item.atom
                if not isinstance(atom, IrRuleRef) or int(item.quantifier.lo) != 0:
                    continue
                target = analysis.rules.get(str(atom))
                if target is not None and not target.semantic:
                    roots.add(str(atom))
    return frozenset(roots)


def _leading_roots(
    analysis: Any, all_roots: "frozenset[str]", atom: Any, seen: "frozenset[str]"
) -> "frozenset[str]":
    """The noise roots that lead the loop body — the only noise the gate skips.

    Skipping the *global* noise set is unsound: at ABNF ``concatenation`` it
    would eat the ``c-nl`` rule terminator into the next rule. The gate skips
    only what actually prefixes one loop iteration (``catrest`` leads with
    ``c-wsp``, never ``c-nl``), so a non-leading noise rule stays a real exit
    boundary.
    """
    if isinstance(atom, IrRuleRef):
        name = str(atom)
        if name in seen or name not in analysis.rules:
            return frozenset()
        out: set[str] = set()
        for arm in analysis.rules[name].body:
            out |= _seq_leading_roots(analysis, all_roots, _items(arm), seen | {name})
        return frozenset(out)
    if isinstance(atom, IrAlternation):
        out = set()
        for arm in atom:
            out |= _seq_leading_roots(analysis, all_roots, _items(arm), seen)
        return frozenset(out)
    return frozenset()


def _seq_leading_roots(
    analysis: Any,
    all_roots: "frozenset[str]",
    items: Sequence[IrItem],
    seen: "frozenset[str]",
) -> "frozenset[str]":
    """The leading noise roots of one sequence — up to the first content atom."""
    out: set[str] = set()
    for item in items:
        atom = item.atom
        if isinstance(atom, IrRuleRef) and str(atom) in all_roots:
            out.add(str(atom))
            continue
        out |= _leading_roots(analysis, all_roots, atom, seen)
        if not analysis.item_nullable(item):
            break
    return frozenset(out)


def _content_first(
    analysis: Any, roots: "frozenset[str]", atom: Any, seen: "frozenset[str]"
) -> CharSet:
    """The first *content* (non-noise) chars reachable at ``atom``'s start."""
    if isinstance(atom, IrRuleRef):
        name = str(atom)
        if name in seen or name not in analysis.rules:
            return CharSet.EMPTY
        out = CharSet.EMPTY
        for arm in analysis.rules[name].body:
            out = out.union(_seq_content(analysis, roots, _items(arm), seen | {name}))
        return out
    if isinstance(atom, IrAlternation):
        out = CharSet.EMPTY
        for arm in atom:
            out = out.union(_seq_content(analysis, roots, _items(arm), seen))
        return out
    return analysis.atom_first(atom)


def _seq_content(
    analysis: Any,
    roots: "frozenset[str]",
    items: Sequence[IrItem],
    seen: "frozenset[str]",
) -> CharSet:
    """Content FIRST of a sequence — leading noise-root refs skipped."""
    out = CharSet.EMPTY
    for item in items:
        atom = item.atom
        if isinstance(atom, IrRuleRef) and str(atom) in roots:
            continue  # a noise run the scanner skips
        out = out.union(_content_first(analysis, roots, atom, seen))
        if not analysis.item_nullable(item):
            return out
    return out


def _noise_or_nullable(analysis: Any, roots: "frozenset[str]", item: IrItem) -> bool:
    """Whether ``item`` is nullable or a noise-root reference (scanner-skipped)."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and str(atom) in roots:
        return True
    return analysis.item_nullable(item)


def _post_noise_follow(
    analysis: Any, roots: "frozenset[str]", skip: int | None = None
) -> dict[str, CharSet]:
    """Rule → the *content* (non-noise) chars reachable after it once the noise
    run is skipped — the sound exit set for a P3 loop peek.

    Raw FOLLOW conflates a noise-lead (the inter-construct separator) with real
    content; skipping the noise at the exit exposes whatever content lies behind
    it (e.g. after a GBNF ``sequence`` the separator ``n`` then the *next rule's*
    rulename), so a peek that ignores it would mistake the next construct for a
    loop continuation. This fixpoint threads content through noise the way the
    runtime scanner will, keeping the peek honest.

    :param skip: ``id()`` of one :class:`~lexic.ir.nodes.IrItem` occurrence to
        exclude from the feed — the P5 probe licence removes the candidate
        *header* occurrence itself when asking what else can follow the name
        rule (:func:`_probe_candidate`).
    """
    tgt: dict[str, CharSet] = {name: CharSet.EMPTY for name in analysis.rules}
    changed = True
    while changed:
        changed = False
        for name, rule in analysis.rules.items():
            for arm in rule.body:
                its = _items(arm)
                for i, item in enumerate(its):
                    atom = item.atom
                    if not isinstance(atom, IrRuleRef) or str(atom) not in tgt:
                        continue
                    if skip is not None and id(item) == skip:
                        continue
                    cont = _follow_content(analysis, roots, its[i + 1 :], tgt[name])
                    hi = item.quantifier.hi
                    if isinstance(hi, IrNoneType) or int(hi) > 1:
                        cont = cont.union(
                            _content_first(analysis, roots, atom, frozenset())
                        )
                    grown = tgt[str(atom)].union(cont)
                    if grown != tgt[str(atom)]:
                        tgt[str(atom)] = grown
                        changed = True
    return tgt


def _follow_content(
    analysis: Any,
    roots: "frozenset[str]",
    rest: Sequence[IrItem],
    tail: CharSet,
) -> CharSet:
    """Content FIRST of ``rest``, plus ``tail`` when ``rest`` is all noise/nullable."""
    out = _seq_content(analysis, roots, rest, frozenset())
    if all(_noise_or_nullable(analysis, roots, i) for i in rest):
        out = out.union(tail)
    return out


def _exit_is_noise(analysis: Any, items: Sequence[IrItem], k: int) -> bool:
    """Whether everything after ``k`` up to (and including) the first required
    item is non-semantic references.

    The ``SG_MATCH`` licence: a noise-root loop whose exit is itself noise —
    a required one (ABNF ``rule[5]``: ``c-wsp*`` before the noise ``c-nl``) or
    a run of optional ones to the arm's end (GBNF ``grammar``'s trailing
    ``n? tail-comment?``) — is pure folding, noise↔noise, so a maximal-munch
    recogniser match is the sound take decision. A nullable *semantic* follower
    denies it: an over-take could eat chars that were semantic content. An
    empty rest also denies — the exit is then the rule's FOLLOW, whose
    noise-ness this arm-local walk cannot see.
    """
    if not items[k + 1 :]:
        return False
    for item in items[k + 1 :]:
        atom = item.atom
        target = analysis.rules.get(str(atom)) if isinstance(atom, IrRuleRef) else None
        if target is None or target.semantic:
            return False
        if int(item.quantifier.lo) >= 1:
            return True
    return True


def _root_idxs(rec: Recognizer, names: "frozenset[str]") -> tuple[int, ...]:
    """The recognizer indices of ``names``, sorted for determinism."""
    return tuple(sorted(rec.index[n] for n in names))


def structured_loop_gate(
    analysis: Any, items: Sequence[IrItem], k: int, scope: Any
) -> "ScanGate | None":
    """A folding-aware loop gate for a comment-bearing / folding decision, or
    ``None`` when it does not separate (the loop stays an island).

    ``SG_MATCH`` — the loop item is itself a noise root and its exit is noise
    (pure folding); ``SG_SCAN`` — skip the loop body's leading noise, take iff
    the post-noise char is a loop-body content lead disjoint from the exit's;
    ``SG_PROBE`` — the P5 escalation when those leads overlap on a
    next-construct header (see :func:`_probe_gate`).
    """
    roots = noise_roots(analysis)
    if not roots:
        return None
    gate = _match_gate(analysis, roots, items, k)
    if gate is not None:
        return gate
    return _scan_or_probe_gate(analysis, roots, items, k, scope)


def _match_gate(
    analysis: Any, roots: "frozenset[str]", items: Sequence[IrItem], k: int
) -> "ScanGate | None":
    """The pure-folding ``SG_MATCH`` gate (ABNF ``rule[5]``), or ``None``."""
    atom = items[k].atom
    if (
        not isinstance(atom, IrRuleRef)
        or str(atom) not in roots
        or not _exit_is_noise(analysis, items, k)
    ):
        return None
    rec = build_recognizer(analysis.rules, roots)
    if rec is None:
        return None
    return ScanGate(SG_MATCH, rec, (rec.index[str(atom)],))


def _scan_or_probe_gate(
    analysis: Any, roots: "frozenset[str]", items: Sequence[IrItem], k: int, scope: Any
) -> "ScanGate | None":
    """The skip-then-peek ``SG_SCAN`` gate, escalating to ``SG_PROBE`` when the
    post-noise take and exit content leads overlap."""
    lead = _leading_roots(analysis, roots, items[k].atom, frozenset())
    if not lead:
        return None
    take = _content_first(analysis, lead, items[k].atom, frozenset())
    if take.is_empty() or take.negated:
        return None
    exit_cs = _follow_content(
        analysis, lead, items[k + 1 :], _post_noise_follow(analysis, lead)[scope.rule]
    )
    if take.overlaps(exit_cs):
        return _probe_gate(analysis, lead, take, exit_cs)
    rec = build_recognizer(analysis.rules, lead)
    if rec is None:
        return None
    return ScanGate(SG_SCAN, rec, _root_idxs(rec, lead), (take.chars, take.negated))


def _probe_gate(
    analysis: Any, lead: "frozenset[str]", take: CharSet, exit_cs: CharSet
) -> "ScanGate | None":
    """The P5 skip-then-probe gate (GBNF ``sequence[1]``), or ``None``.

    Licensed when the take/exit content overlap is exactly a next-construct
    *header*: some rule's arm reads ``ref(R) noise* lit(L) …`` (the "rulename …
    defined-as" shape) with the whole overlap inside ``FIRST(R)``, and ``L``'s
    lead char unable to follow an ``R`` occurrence anywhere else (the header
    occurrence itself excluded) — so a successful ``R noise* L`` match at the
    post-noise position *refutes the take reading* and the gate exits, while a
    failed match on an overlap char leaves the take side as the only
    header-free reading. Chars in neither content set exit (and fail soft
    downstream if they were junk). The candidate header must be unique
    grammar-wide, or the decision stays an island.
    """
    overlap = take.subtract(take.subtract(exit_cs))
    spec = _probe_candidate(analysis, lead, overlap)
    if spec is None:
        return None
    r_name, mid_root, lit = spec
    rec = build_recognizer(analysis.rules, lead | {r_name, mid_root})
    if rec is None:
        return None
    take_only = take.subtract(analysis.first[r_name])
    return ScanGate(
        SG_PROBE,
        rec,
        _root_idxs(rec, lead),
        (take_only.chars, take_only.negated),
        (rec.index[r_name], rec.index[mid_root], lit, False),
    )


def _probe_candidate(
    analysis: Any, lead: "frozenset[str]", overlap: CharSet
) -> "tuple[str, str, str] | None":
    """The unique ``(R, noise root, L)`` header spec explaining ``overlap``.

    Scans every semantic rule's arms for the header shape
    (:func:`_header_shape`), keeps candidates whose name rule covers the whole
    overlap and whose probe literal passes the refutation licence
    (:func:`_post_noise_follow` with the header occurrence skipped), and
    demands exactly one distinct spec grammar-wide.
    """
    cands: set[tuple[str, str, str]] = set()
    for rule in analysis.rules.values():
        if not rule.semantic:
            continue
        for arm in rule.body:
            shape = _header_shape(analysis, _items(arm))
            if shape is None:
                continue
            head, r_name, mid_root, lit = shape
            if not overlap.subtract(analysis.first[r_name]).is_empty():
                continue
            pnf = _post_noise_follow(analysis, lead, skip=id(head))[r_name]
            if pnf.has(lit[0]):
                continue
            cands.add((r_name, mid_root, lit))
    if len(cands) != 1:
        return None
    return next(iter(cands))


def _header_shape(
    analysis: Any, arm_items: Sequence[IrItem]
) -> "tuple[IrItem, str, str, str] | None":
    """Match ``[ref R (1,1)] [same noise ref]+ [lit L] …`` at an arm's head.

    :returns: ``(head item, R, noise root, L)``, or ``None`` on any other
        shape. The middle items must all reference one non-semantic rule (the
        probe skips a maximal run of it between the name and the literal;
        at least one such item — a zero-noise header would make the probe's
        noise run over-permissive for nothing).
    """
    if not arm_items:
        return None
    head = arm_items[0]
    hi = head.quantifier.hi
    if (
        not isinstance(head.atom, IrRuleRef)
        or str(head.atom) not in analysis.rules
        or int(head.quantifier.lo) != 1
        or isinstance(hi, IrNoneType)
        or int(hi) != 1
    ):
        return None
    mid: str | None = None
    for item in arm_items[1:]:
        atom = item.atom
        if isinstance(atom, IrLiteral):
            if mid is None or not str(atom) or int(item.quantifier.lo) < 1:
                return None
            return (head, str(head.atom), mid, str(atom))
        name = str(atom) if isinstance(atom, IrRuleRef) else None
        target = analysis.rules.get(name) if name is not None else None
        if target is None or target.semantic or mid not in (None, name):
            return None
        mid = name
    return None
