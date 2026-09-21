"""A folded left recursion as a split source — locating the spine in the text.

`A ::= A β | γ` builds a spine as deep as the document, and the character sweep
has nothing to find: the repetition that carries it is not in the grammar at
all, it is in the fold the predictive path applies. So the third region SOURCE
reads the fold's own SHAPE ANALYSIS and says where the spine stands.

The category boundary is responsibility, not case count. A source LOCATES an
occurrence and preserves the shell around it; the split CERTIFIES boundaries
and partitions; the stitch RECONSTRUCTS through the original binding. Holding
a start rule's required tail out of the spine's extent is locating — the shell
is what the pieces re-wear to be documents again — and enumerating where the
separator stands inside that extent is describing the located shape. Which of
those offsets becomes a cut is the split's question, asked elsewhere.

The extent arithmetic is this module's own, deliberately. Its sibling in
:mod:`~lexic.parsing.parallel.plan.routed` ends a whole-extent interior at the
LAST mark, which is right for a terminated repetition whose units own their
final character — and wrong here, where the last mark is the last OPERATOR and
everything past it is the spine's final term. Sharing that arithmetic would
silently drop a term rather than decline.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.regions import Region, nearest_mark
from lexic.parsing.parallel.discovery.shapes import UNIT, exact_text
from lexic.parsing.parallel.plan.routed import REF, Descent
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.stitch.safety import owner_excludes
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec.shape import Fold, any_candidate, foldable

_PLANS: dict[int, tuple[IrAst, "FoldedPlan | None"]] = memo({})
"""Fold-source memo — id(grammar) → (grammar, plan). The strong reference pins
the id, so a recycled id can never alias a live entry."""


class FoldedPlan(NamedTuple):
    """The spine one grammar's fold carries, and where its text stands.

    :ivar rule: The left-recursive rule the fold takes.
    :ivar step: The hoisted arm rule one iteration builds through — the class
        the stitch rebuilds the spine's left edge with.
    :ivar lead: The rule spelling the separator between two terms.
    :ivar marks: Its spellings, longest first.
    :ivar owners: The rules the boundary proof cleared — the base arms' and
        the step's references, which between them own every character of the
        spine that is not a mark.
    :ivar chain: The descent from the start rule to :attr:`rule`, one
        :class:`~...plan.routed.Descent` per step.
    :ivar before: The fixed text standing before the spine in the enclosing
        arms, which every piece re-wears on the left.
    :ivar after: The fixed text standing after it, likewise.
    :ivar lead_grammar: The grammar rooted at :attr:`lead`, which the removed
        marks re-parse under so the join can rebuild them.
    """

    rule: str
    step: str
    lead: str
    marks: tuple[str, ...]
    owners: tuple[str, ...]
    chain: tuple[Descent, ...]
    before: str
    after: str
    lead_grammar: IrAst


def folded_plan(grammar: IrAst) -> FoldedPlan | None:
    """The spine the start rule's route reaches, memoised per identity.

    :param grammar: The codegen grammar.
    :returns: The plan, or ``None`` when any of its conditions is unproven.
    """
    entry = _PLANS.get(id(grammar))
    if entry is None:
        entry = (grammar, _derive(grammar))
        _PLANS[id(grammar)] = entry
    return entry[1]


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The rule's only arm, when it has exactly one."""
    arms = tuple(rule.body)
    return tuple(arms[0]) if len(arms) == 1 else None


def _unit_ref(item: IrItem) -> str | None:
    """The rule an item references exactly once, or ``None``."""
    atom = item.atom
    return (
        str(atom) if isinstance(atom, IrRuleRef) and item.quantifier == UNIT else None
    )


class _Step(NamedTuple):
    """One descent through a rule that wraps the spine in fixed text."""

    at: int
    ref: str
    before: str
    after: str


def _through(items: tuple[IrItem, ...], rules: dict[str, IrRule]) -> _Step | None:
    """The one item an arm descends through, and the text either side of it.

    Every other item must derive ONE fixed string, because a piece has to be
    able to wear it: an item whose text varies with the document leaves the
    shell unreconstructable and the arm declines.
    """
    spelled = [exact_text(one, rules, frozenset()) for one in items]
    open_at = [at for at, text in enumerate(spelled) if not text]
    if len(open_at) != 1:
        return None
    at = open_at[0]
    ref = _unit_ref(items[at])
    if ref is None:
        return None
    return _Step(at, ref, "".join(spelled[:at]), "".join(spelled[at + 1 :]))


def _descend(
    grammar: IrAst, rules: dict[str, IrRule], folds: dict[str, Fold]
) -> tuple[str, tuple[Descent, ...], str, str] | None:
    """``(the folded rule, the chain to it, before, after)``, or ``None``.

    The walk stops at the first rule the fold takes. A rule it does not take
    must offer one descent whose siblings spell fixed text, or there is no
    shell to re-wear and the source declines.
    """
    name = str(grammar.start)
    chain: list[Descent] = []
    before, after = "", ""
    seen: set[str] = set()
    while name not in folds:
        rule = rules.get(name)
        items = _single_arm(rule) if rule is not None else None
        step = _through(items, rules) if items else None
        if step is None or name in seen:
            return None
        seen.add(name)
        chain.append(Descent(name, step.at, REF))
        before, after = before + step.before, step.after + after
        name = step.ref
    return name, tuple(chain), before, after


def _marks(lead: str, rules: dict[str, IrRule]) -> tuple[str, ...]:
    """Every fixed spelling the separator rule derives, longest first.

    An arm that does not derive one fixed string makes the whole separator
    unusable rather than one spelling fewer: a mark the scan cannot spell is a
    boundary the cut would step straight past.

    Longest first for the usual reason — a spelling whose prefix is also a
    mark must read as the wider one — and then by the spelling itself, so the
    order is TOTAL. Length alone leaves two equal-length marks in set order,
    which varies with the interpreter's string hashing and would make one
    grammar's plan differ between processes.
    """
    target = rules.get(lead)
    if target is None:
        return ()
    found = [
        "".join(exact_text(one, rules, frozenset()) for one in tuple(arm))
        for arm in target.body
    ]
    ordered = sorted(set(found), key=lambda mark: (-len(mark), mark))
    return () if not all(found) else tuple(ordered)


def _aligned(grammar: IrAst, owners: tuple[str, ...], marks: tuple[str, ...]) -> bool:
    """Whether every occurrence of a mark in the spine must BE a separator.

    Within the folded rule every character at the spine's own depth comes from
    a base arm, a mark, or a step's remainder. When the owners of those two
    non-mark parts can spell NO character of the mark, every character of any
    occurrence comes from a mark literal; and because the remainder is
    non-empty, no two literals are adjacent, so an occurrence lies inside one
    literal and — having its length — coincides with it.

    Every check is one character, so nothing here needs a mark narrower than
    the scan's, and nothing rests on the mark's border structure: ``" + "`` and
    ``"aba"`` have the same borders, and what separates them is whether the
    owner emits the character a spurious occurrence would need.

    The clause OVER-REFUSES and never mis-splits: an owner that can emit a
    mark character somewhere no occurrence could stand is refused anyway.
    """
    chars = {char for mark in marks for char in mark}
    return bool(marks) and all(
        owner_excludes(grammar, owner, char)
        and owner_excludes(grammar, owner, char, region_scan=True)
        for owner in owners
        for char in chars
    )


def _owners(rule: IrRule, fold: Fold) -> tuple[str, ...] | None:
    """The rules the base arms and the step's remainder are made of.

    Each must be a plain reference: the proof is asked per owner RULE, and an
    inline literal or class at the spine's own depth has no rule to ask it of.
    """
    arms = tuple(rule.body)
    items = [one for at in fold.base for one in tuple(arms[at])]
    items.extend(fold.steps[0].rest[1:])
    named = [found for one in items if (found := _unit_ref(one)) is not None]
    return (
        None if len(named) != len(items) or not named else tuple(dict.fromkeys(named))
    )


def _derive(grammar: IrAst) -> FoldedPlan | None:
    """Read the fold's shape analysis, certify the boundary, place the shell."""
    rules = {str(rule.name): rule for rule in grammar.rules}
    if not any_candidate(rules):
        return None
    nullable = GrammarAnalysis(grammar).item_nullable
    folds = {
        name: shape
        for name, rule in rules.items()
        if (shape := foldable(name, rule, rules, nullable)) is not None
    }
    found = _descend(grammar, rules, folds) if folds else None
    if found is None:
        return None
    name, chain, before, after = found
    fold = folds[name]
    return _certified(grammar, rules, (name, fold), (chain, before, after))


def _certified(
    grammar: IrAst,
    rules: dict[str, IrRule],
    taken: tuple[str, Fold],
    shell: tuple[tuple[Descent, ...], str, str],
) -> FoldedPlan | None:
    """The plan the boundary proof licenses over this shell, or ``None``."""
    name, fold = taken
    chain, before, after = shell
    lead = _unit_ref(fold.steps[0].rest[0]) if fold.steps[0].rest else None
    owners = _owners(rules[name], fold)
    marks = _marks(lead, rules) if lead else ()
    if lead is None or owners is None or not _aligned(grammar, owners, marks):
        return None
    # The shell's own text must be unreachable from inside the spine, or the
    # extent below is a guess: a tail the interior can also spell would make
    # the document's LAST occurrence of it the only certain one, which is what
    # the sibling source's arithmetic assumes and this one must not.
    if any(not owner_excludes(grammar, name, char) for char in before + after):
        return None
    return FoldedPlan(
        name,
        fold.steps[0].rule,
        lead,
        marks,
        owners,
        chain,
        before,
        after,
        IrAst(grammar.rules, lead),
    )


def locate(text: str, plan: FoldedPlan) -> Region | None:
    """The spine's certified extent, with every separator inside it.

    The extent is read off the shell's fixed widths — the spine runs from the
    end of what precedes it to the start of what follows — and NOT from the
    last mark, which is this shape's last operator rather than its end.

    The region's marks are where the separators stand, in document order; the
    proof in :func:`_aligned` is what makes a bare search exact.
    """
    if not text.startswith(plan.before) or not text.endswith(plan.after):
        return None
    lo = len(plan.before)
    hi = len(text) - len(plan.after)
    return (
        Region(lo, hi, plan.rule, _marks_in(text, lo, hi, plan.marks))
        if lo < hi
        else None
    )


def _marks_in(text: str, lo: int, hi: int, marks: tuple[str, ...]) -> tuple[int, ...]:
    """Every separator offset inside the extent, in document order.

    Marks are read longest first at each position, so a spelling whose prefix
    is also a mark reads as the wider one and a cut cannot land mid-spelling.

    Each spelling keeps its OWN cursor, re-sought only once the scan has
    passed it. Searching every spelling from every accepted mark instead costs
    a sweep to the end of the extent for each one that is absent from the rest
    of the document — quadratic in a document holding one of two spellings,
    and measured at more than half an island-earley parse before it was this.
    """
    found: list[int] = []
    cursors = [text.find(mark, lo, hi) for mark in marks]
    while True:
        best = _earliest(cursors)
        if best < 0:
            return tuple(found)
        found.append(cursors[best])
        past = cursors[best] + len(marks[best])
        for index, mark in enumerate(marks):
            if 0 <= cursors[index] < past:
                cursors[index] = text.find(mark, past, hi)


def _earliest(cursors: list[int]) -> int:
    """The cursor standing earliest, or ``-1`` when every one is spent.

    Ties go to the lowest index, and the spellings are ordered longest first,
    so two marks at one offset read as the wider.
    """
    best = -1
    for index, where in enumerate(cursors):
        if where >= 0 and (best < 0 or where < cursors[best]):
            best = index
    return best


def mark_at(text: str, at: int, marks: tuple[str, ...]) -> str:
    """The separator standing at ``at``, or ``""`` when none does."""
    return next((mark for mark in marks if text.startswith(mark, at)), "")


class Pieces(NamedTuple):
    """One document's division into spine pieces and the marks between them.

    :ivar parts: Each piece wearing the shell, so it is a document under the
        start rule and parses to a spine of its own.
    :ivar leads: The separator text each cut removed — one fewer than
        :attr:`parts`, and what the join rebuilds the spine node with.
    """

    parts: tuple[str, ...]
    leads: tuple[str, ...]


def divide(text: str, region: Region, workers: int, plan: FoldedPlan) -> Pieces | None:
    """The spine cut into ``workers`` pieces, or ``None`` if it will not.

    The cut CONSUMES its separator, as every separated cut does: the mark's
    text comes back as a lead the stitch re-parses, because the spine node it
    belongs to is built across the boundary and neither piece can own it.
    """
    lo, hi = region.opener, region.closer
    workers = min(workers, (hi - lo) // MIN_CHUNK)
    if workers < 2 or not region.marks:
        return None
    target = (hi - lo) / workers
    chosen = _chosen_marks(region.marks, lo, hi, target, workers)
    leads = tuple(mark_at(text, at, plan.marks) for at in chosen)
    bounds = [lo, *chosen, hi]
    widest = max(bounds[at + 1] - bounds[at] for at in range(len(bounds) - 1))
    if not chosen or not all(leads) or widest > 2 * target:
        return None
    starts = [lo, *(at + len(mark) for at, mark in zip(chosen, leads, strict=True))]
    parts = tuple(
        plan.before + text[starts[at] : bounds[at + 1]] + plan.after
        for at in range(len(starts))
    )
    return Pieces(parts, leads)


def _chosen_marks(
    marks: tuple[int, ...], lo: int, hi: int, target: float, workers: int
) -> list[int]:
    """The separator offsets ``workers`` even pieces would cut at.

    A duplicate is dropped rather than made a zero-width piece: two targets
    landing on the same mark means the document has fewer usable boundaries
    than the policy asked for, and the width check decides whether what is
    left still divides.

    The nearest mark is the sweep path's own :func:`~...discovery.regions.
    nearest_mark`, which bisects. The marks arrive in document order from
    :func:`_marks_in`, which is the precondition that makes a bisect legal
    here — and the reason to care is cost: reading every mark for every cut
    makes cut selection dearer as the WORKER COUNT rises, measured at 1.06 ms
    of a 7.6 ms sixteen-worker parse before this call replaced a linear min.
    """
    chosen: list[int] = []
    for step in range(1, workers):
        at = nearest_mark(marks, lo + step * target)
        if at not in chosen and lo < at < hi:
            chosen.append(at)
    return chosen
