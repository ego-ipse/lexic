"""Per-node predicates, and the dispatch tables that read them.

One small function per node type, per question: is it nullable, what can it
start with, which of those are HARD, does it stop a window, how does it feed the
next item. They are separate because the analysis reads them through open
dispatch tables — a new node type joins by adding a row here, never by editing
a cascade.

The tables are public because they ARE this module's surface: the analysis
consumes them whole, and a predicate on its own is not usable without the table
that routes to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Sequence, cast

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAtom,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.pda.analysis.cursors import (
    ConflictCtx,
    FeedCtx,
    Scope,
    Site,
)
from lexic.parsing.pda.core.charsets import CharSet

if TYPE_CHECKING:  # `analysis` imports this module, so the reference is mutual
    from lexic.parsing.pda.analysis.analysis import GrammarAnalysis


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order (others skipped)."""
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded)."""
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


class _Nullability(IrLeaf[IrSelf, IrSelf]):
    """The nullability fixpoint as a standalone solver.

    Homes the derives-empty computation both :func:`nullable_names` (for
    :func:`~lexic.parsing.fold.lift_optional_nullables`) and
    :class:`GrammarAnalysis` need — one fixpoint, no duplication. Its growing
    ``nullable`` set is read by the shared :data:`NULLABLE` bodies whether
    ``d`` is this solver (mid-fixpoint) or a finished :class:`GrammarAnalysis`.
    """

    __slots__ = ("rules", "nullable")

    rules: Mapping[str, IrRule]
    nullable: set[str]

    def __init__(self, rules: Mapping[str, IrRule]) -> None:
        self.rules = rules
        self.nullable = set()

    def solve(self) -> frozenset[str]:
        """Grow ``nullable`` to the least fixpoint and return it frozen."""
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                if name in self.nullable:
                    continue
                if _rule_nullable(self, rule):
                    self.nullable.add(name)
                    changed = True
        return frozenset(self.nullable)


def _null_ruleref(d: GrammarAnalysis | _Nullability, n: IrSelf, _nc: object) -> bool:
    """A rule ref is nullable iff its target is currently known nullable."""
    return str(n) in d.nullable


def _null_literal(_d: object, n: IrSelf, _nc: object) -> bool:
    """A literal is nullable iff it is the empty string."""
    return not str(n)


def _null_never(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class or negated class always consumes one char — never nullable."""
    return False


def _null_alternation(
    d: GrammarAnalysis | _Nullability, n: IrSelf, _nc: object
) -> bool:
    """A group is nullable iff any arm's items are all nullable."""
    assert isinstance(n, IrAlternation)
    return any(seq_nullable(d, _items(arm)) for arm in n)


def _first_literal(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a literal: its leading character (empty literal → empty set)."""
    text = str(n)
    return CharSet.from_chars(text[0]) if text else CharSet.EMPTY


def _first_charclass(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a char class: its member set."""
    assert isinstance(n, IrCharClass)
    return CharSet.from_charclass(n)


def _first_not(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of an ``IrNot``: the complement of its inner class (else ANY).

    Only a negated CHAR class reaches here — token negation lives INSIDE the
    alphabet (a fenced terminal), so ``IrNot`` never wraps an ``IrAlphabet``."""
    assert isinstance(n, IrNot)
    inner = n[0]
    if isinstance(inner, IrCharClass):
        return CharSet.from_not(inner)
    return CharSet.ANY


def _first_token(_d: object, _n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a token atom: EMPTY — it matches ids, not chars (forces island)."""
    return CharSet.EMPTY


def _first_ruleref(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a rule ref: the target's current FIRST; undefined ref → ANY."""
    got = d.first.get(str(n))
    return CharSet.ANY if got is None else got


def _first_alternation(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a group: the union of its arms' sequence FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_first(_items(arm)))
    return out


def _alpha_literal(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """Every character a literal holds — all of them, not just the leading one.

    This is where ALPHABET parts company with FIRST, and the whole reason it
    is a separate derivation: ``"ab"`` BEGINS with ``a`` and CONTAINS ``b``.
    """
    return CharSet.from_chars(*set(str(n))) if str(n) else CharSet.EMPTY


def _alpha_charclass(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """A char class holds exactly what it matches — its FIRST and its alphabet
    coincide, since it is one character wide."""
    assert isinstance(n, IrCharClass)
    return CharSet.from_charclass(n)


def _alpha_any(_d: object, _n: IrSelf, _nc: object) -> CharSet:
    """An atom whose characters are not enumerable: conservatively everything.

    ``ANY`` is the SAFE answer here in a way it is not for FIRST. A caller asks
    the alphabet to prove DISJOINTNESS from some other set, so an answer that
    is too large can only withdraw the proof; one that is too small would grant
    it wrongly. A negated class and a token atom both land here.
    """
    return CharSet.ANY


def _alpha_ruleref(_d: object, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A rule ref holds what its target holds; an undefined ref holds anything.

    The working map rides the ``nc`` channel, and reading the target's CURRENT
    value is what makes recursion terminate: :func:`rule_alphabets` iterates to
    stability, so a left-recursive rule reaches its own alphabet by growing
    into it rather than by descending into itself.
    """
    got = cast("dict[str, CharSet]", nc[0]).get(str(n))
    return CharSet.ANY if got is None else got


def _alpha_alternation(_d: object, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A group holds the union of everything its arms hold."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        for item in _items(arm):
            out = out.union(_atom_alphabet(item.atom, nc))
    return out


def _atom_alphabet(atom: IrSelf, nc: Sequence[object]) -> CharSet:
    """Dispatch one atom against :data:`ALPHABET`, carrying the working map."""
    return cast(CharSet, ALPHABET.resolve(atom).eval(None, atom, nc))


def rule_alphabets(rules: Mapping[str, IrRule]) -> dict[str, CharSet]:
    """Every character each rule can derive — the per-rule ALPHABET fixpoint.

    Distinct from FIRST in the two ways that make it its own derivation. It
    takes EVERY character of a literal rather than the leading one, and it
    iterates to a fixpoint over rule references, so a LEFT-RECURSIVE rule is
    answered rather than refused — a depth-capped descent returns "unknowable"
    for exactly the recursive rules a caller most wants the answer about.

    A free function rather than a :class:`GrammarAnalysis` attribute because
    that class sits at its instance cap, and a derivation with one consumer
    has no claim to the last slot over the ones already there. The working map
    rides the dispatcher's ``nc`` channel, which is what lets the fixpoint read
    its own partial answers.

    The one use is disjointness — whether a rule can derive any character of
    some other set — so every unknowable atom answers
    :attr:`~lexic.parsing.pda.core.charsets.CharSet.ANY`, which withdraws the
    proof rather than granting it.

    :param rules: The grammar's rules by name.
    :returns: Rule name → every character it can derive.
    :raises UnsupportedConstructError: On an unregistered atom type.
    """
    found = {name: CharSet.EMPTY for name in rules}
    nc = (found,)
    changed = True
    while changed:
        changed = False
        for name, rule in rules.items():
            acc = CharSet.EMPTY
            for arm in rule.body:
                for item in _items(arm):
                    acc = acc.union(_atom_alphabet(item.atom, nc))
            if acc != found[name]:
                found[name] = acc
                changed = True
    return found


def _hard_terminal(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a terminal atom equals its FIRST (it is not nullable)."""
    return d.atom_first(cast(IrAtom, n))


def _hard_ruleref(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a rule ref: the target's current hard-FIRST; else ANY."""
    got = d.hard.get(str(n))
    return CharSet.ANY if got is None else got


def _hard_alternation(d: GrammarAnalysis, n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a group: the union of its arms' sequence hard-FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_hard(_items(arm)))
    return out


def _stopset_yes(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class / negated class is a single-char loop → stop-set eligible."""
    return True


def _stopset_no(_d: object, _n: IrSelf, _nc: object) -> bool:
    """Literals, refs and groups are not stop-set loop atoms."""
    return False


def _feed_ruleref(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Union the effective continuation into a defined ref target's FOLLOW.

    :returns: ``True`` iff the target's FOLLOW set grew.
    """
    name = str(n)
    if name not in d.rules:
        return False
    ctx = cast(FeedCtx, nc[0])
    tgt = ctx.pass_.tgt
    grown = tgt[name].union(ctx.eff)
    if grown != tgt[name]:
        tgt[name] = grown
        return True
    return False


def _feed_alternation(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Feed the effective continuation into each of a group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(FeedCtx, nc[0])
    changed = False
    for arm in n:
        if d.feed_seq(_items(arm), ctx.eff, ctx.rule, ctx.pass_):
            changed = True
    return changed


def _feed_terminal(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A terminal atom has no sub-rule FOLLOW to update."""
    return False


def _seq_ruleref(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Flag a rule ref whose target the grammar never defines."""
    if str(n) not in d.rules:
        ctx = cast(ConflictCtx, nc[0])
        ctx.notes.hard.append(f"{ctx.rule}[{ctx.index}]: undefined ref {str(n)!r}")


def _seq_alternation(d: GrammarAnalysis, n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Recurse conflict analysis into an inline group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(ConflictCtx, nc[0])
    sub_arms = [_items(arm) for arm in n]
    label = f"{ctx.rule}[{ctx.index}]grp"
    scope = Scope(ctx.rule, ctx.cont, body=False)
    d.arm_conflicts(sub_arms, Site(label, id(n), ctx.cont.soft), ctx.notes)
    for sub in sub_arms:
        d.seq_conflicts(sub, scope, ctx.notes)


def _seq_noop(_d: object, _n: IrSelf, _nc: object) -> None:
    """A terminal atom contributes no sequence-level conflict."""
    return None


def item_nullable(d: GrammarAnalysis | _Nullability, item: IrItem) -> bool:
    """Whether ``item`` can consume nothing: ``lo == 0`` or a nullable atom."""
    if int(item.quantifier.lo) == 0:
        return True
    return cast(bool, NULLABLE.resolve(item.atom).eval(d, item.atom, ()))


def seq_nullable(d: GrammarAnalysis | _Nullability, items: Sequence[IrItem]) -> bool:
    """Whether every item in a sequence arm is nullable (empty arm → True)."""
    return all(item_nullable(d, i) for i in items)


def _rule_nullable(d: GrammarAnalysis | _Nullability, rule: IrRule) -> bool:
    """Whether any arm of ``rule`` is all-nullable."""
    return any(seq_nullable(d, _items(arm)) for arm in rule.body)


def nullable_names(rules: Sequence[IrRule]) -> frozenset[str]:
    """The names of every rule in ``rules`` that derives the empty string.

    The single home of the nullability fixpoint —
    :func:`~lexic.parsing.fold.lift_optional_nullables` consumes it from here
    (an intra-package import) rather than keeping its own copy.
    """
    return _Nullability({str(r.name): r for r in rules}).solve()


NULLABLE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_null_literal)),
    IrAction(IrCharClass, IrLambda(_null_never)),
    IrAction(IrNot, IrLambda(_null_never)),
    IrAction(IrAlphabet, IrLambda(_null_never)),
    IrAction(IrRuleRef, IrLambda(_null_ruleref)),
    IrAction(IrAlternation, IrLambda(_null_alternation)),
)
FIRST: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_first_literal)),
    IrAction(IrCharClass, IrLambda(_first_charclass)),
    IrAction(IrNot, IrLambda(_first_not)),
    IrAction(IrAlphabet, IrLambda(_first_token)),
    IrAction(IrRuleRef, IrLambda(_first_ruleref)),
    IrAction(IrAlternation, IrLambda(_first_alternation)),
)
ALPHABET: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_alpha_literal)),
    IrAction(IrCharClass, IrLambda(_alpha_charclass)),
    IrAction(IrNot, IrLambda(_alpha_any)),
    IrAction(IrAlphabet, IrLambda(_alpha_any)),
    IrAction(IrRuleRef, IrLambda(_alpha_ruleref)),
    IrAction(IrAlternation, IrLambda(_alpha_alternation)),
)
HARD: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_hard_terminal)),
    IrAction(IrCharClass, IrLambda(_hard_terminal)),
    IrAction(IrNot, IrLambda(_hard_terminal)),
    IrAction(IrAlphabet, IrLambda(_hard_terminal)),
    IrAction(IrRuleRef, IrLambda(_hard_ruleref)),
    IrAction(IrAlternation, IrLambda(_hard_alternation)),
)
STOPSET_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_stopset_no)),
    IrAction(IrCharClass, IrLambda(_stopset_yes)),
    IrAction(IrNot, IrLambda(_stopset_yes)),
    IrAction(IrAlphabet, IrLambda(_stopset_no)),
    IrAction(IrRuleRef, IrLambda(_stopset_no)),
    IrAction(IrAlternation, IrLambda(_stopset_no)),
)
FOLLOW_FEED: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_feed_terminal)),
    IrAction(IrCharClass, IrLambda(_feed_terminal)),
    IrAction(IrNot, IrLambda(_feed_terminal)),
    IrAction(IrAlphabet, IrLambda(_feed_terminal)),
    IrAction(IrRuleRef, IrLambda(_feed_ruleref)),
    IrAction(IrAlternation, IrLambda(_feed_alternation)),
)
SEQ_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_seq_noop)),
    IrAction(IrCharClass, IrLambda(_seq_noop)),
    IrAction(IrNot, IrLambda(_seq_noop)),
    IrAction(IrAlphabet, IrLambda(_seq_noop)),
    IrAction(IrRuleRef, IrLambda(_seq_ruleref)),
    IrAction(IrAlternation, IrLambda(_seq_alternation)),
)
