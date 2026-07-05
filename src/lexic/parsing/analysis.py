"""Grammar analysis + decision taxonomy — the PDA compiler's oracle.

:class:`GrammarAnalysis` computes, over a *lifted codegen grammar* (the same
shape the hybrid-parsing PoC analysed —
``lift_optional_nullables(build_codegen_grammar(canonical))``), the classical
predictive-parser fixpoints plus the pivot-6 decision taxonomy:

- **nullability** — which rules derive the empty string (fixpoint);
- **FIRST** — the leading characters of each rule/atom/sequence over
  :class:`~lexic.parsing.charsets.CharSet`, so an ``IrNot`` loop's co-finite
  FIRST stays exact instead of "poisoning" the rule into a fake island
  (INVESTIGATION.md pivot 1);
- **hard-FIRST** — FIRST with nullable items skipped: the characters a
  construct *requires* to progress. Drives loop stop-sets, while full FIRST
  drives entry gates (pivot 4, ``begin-object ::= ws "{" ws``);
- **FOLLOW** — the characters that may follow each rule (fixpoint, EOF-seeded
  at the start rule via the ``""`` sentinel);
- **2-char prefix sets** — the LL(2) discriminator for an optional atom whose
  FIRST collides with its continuation (chess ``fxf5`` vs ``f5``, pivot 6);
- **the taxonomy** — every decision point classified into ``island`` (search
  needed), ``stopset`` (non-greedy on the overlap) or an ``("pairs", set)``
  LL(2) gate; per-rule conflict classification yields the *island set*
  (:attr:`~GrammarAnalysis.conflicts`) and the *demotion notes*
  (:attr:`~GrammarAnalysis.demoted`).

**Open dispatch, no isinstance ladders.** Every per-atom-type decision routes
through a module-level :class:`~lexic.ir.mapping.IrTypeMap` whose bodies are
:class:`~lexic.ir.base.IrLambda` leaves — the ``lexic.codegen.binding``
``mode_for`` idiom: the atom is dispatched, the driving analysis rides the
dispatcher slot ``d`` (its state and its recursive helpers), and any extra
scalar context rides the argument channel ``nc`` on a small cursor leaf. An
unknown atom type misses every table and raises
:exc:`~lexic.exceptions.UnsupportedConstructError` (via ``IrTypeMap``'s
:exc:`~lexic.exceptions.IrKeyError`) — never a silent classification.

.. warning::
   **EOF-drop caveat.** :meth:`CharSet.union <lexic.parsing.charsets.CharSet.union>`
   cannot represent "co-finite over real characters, *plus* the EOF sentinel"
   — a negated ``CharSet`` never carries ``""``. The FOLLOW fixpoint unions
   FOLLOW (EOF-seeded) with FIRSTs that can be negated (``IrNot`` complements),
   so an EOF membership can silently drop from a FOLLOW set, which could under-
   detect a conflict whose FIRST ∩ FOLLOW overlap is EOF-only. This matches the
   PoC's identical ``(chars, negated)`` representation exactly (0 parity
   mismatches across all 10 ground-truth grammars), and the PDA's runtime
   safety net (a ``PdaFail`` falls back to the full engine) bounds any
   under-detection — so the analysis matches the PoC here rather than carrying a
   side-channel EOF flag. Task 7's differential CI is the watch for it.
"""

from __future__ import annotations

from typing import Mapping, Sequence, cast

from lexic.ir.base import IrAtom, IrLambda, IrLeaf, IrNoneType, IrSelf
from lexic.ir.action import IrAction
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.charsets import CharSet

__all__ = ["GrammarAnalysis", "nullable_names"]

_MAX_PAIR_PRODUCT = 4096
"""Cap on the ``|FIRST(a)| * |FIRST(b)|`` product a 2-char prefix set will
enumerate for two adjacent single-char atoms; a wider product is treated as
non-derivable (``None``) rather than materialised."""

_EOF: CharSet = CharSet.from_chars("")
"""The FOLLOW-set seed for the start rule: the empty-string end-of-input
sentinel living in a positive :class:`CharSet` (see the module docstring)."""


def _items(seq: Sequence[IrSelf]) -> list[IrItem]:
    """The :class:`IrItem` members of a sequence arm, in order.

    :param seq: An :class:`~lexic.ir.nodes.IrSequence` (or any node sequence).
    :returns: Its :class:`IrItem` children — anything else is skipped.
    """
    return [i for i in seq if isinstance(i, IrItem)]


def _hi(item: IrItem) -> int | None:
    """The item's quantifier upper bound as an ``int``, or ``None`` (unbounded).

    :param item: The quantified item.
    :returns: ``int(hi)``, or ``None`` when ``hi`` is the unbounded sentinel.
    """
    hi = item.quantifier.hi
    return None if isinstance(hi, IrNoneType) else int(hi)


# ── context cursors (ride the argument channel) ───────────────────────────


class _FeedCtx(IrLeaf[IrSelf, IrSelf]):
    """FOLLOW-feed context: the effective continuation set and owning rule.

    Rides ``nc`` so the :data:`_FOLLOW_FEED` bodies (ref-update, group-recurse)
    read the per-item ``eff`` and ``rule`` without threading them as extra
    positional arguments through the typed dispatch protocol.

    :ivar eff: The continuation char set feeding this atom's FOLLOW.
    :ivar rule: The enclosing rule name (the recursion anchor).
    """

    __slots__ = ("eff", "rule")

    eff: CharSet
    rule: str

    def __init__(self, eff: CharSet, rule: str) -> None:
        """:param eff: the continuation set; :param rule: the enclosing rule."""
        self.eff = eff
        self.rule = rule


class _Notes(IrLeaf[IrSelf, IrSelf]):
    """The two conflict-note accumulators for one rule, appended in place.

    :ivar hard: Island-worthy conflict notes (their presence marks an island).
    :ivar soft: Stop-set / LL(2) demotion notes.
    """

    __slots__ = ("hard", "soft")

    hard: list[str]
    soft: list[str]

    def __init__(self) -> None:
        """Seed both note lists empty."""
        self.hard = []
        self.soft = []


class _Scope(IrLeaf[IrSelf, IrSelf]):
    """The enclosing rule and its FOLLOW tail — the conflict-walk context.

    :ivar rule: The enclosing rule name (the note-label anchor).
    :ivar tail: The FOLLOW char set at the arm's end.
    """

    __slots__ = ("rule", "tail")

    rule: str
    tail: CharSet

    def __init__(self, rule: str, tail: CharSet) -> None:
        """:param rule: the enclosing rule; :param tail: its FOLLOW tail."""
        self.rule = rule
        self.tail = tail


class _ConflictCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-item conflict-classification context for the :data:`_SEQ_ATOM` bodies.

    :ivar notes: The rule's note accumulators.
    :ivar eff: The group's effective continuation set (for a group recurse).
    :ivar rule: The enclosing rule name.
    :ivar index: The item's positional index (for note labelling).
    """

    __slots__ = ("notes", "eff", "rule", "index")

    notes: "_Notes"
    eff: CharSet
    rule: str
    index: int

    def __init__(self, notes: "_Notes", eff: CharSet, rule: str, index: int) -> None:
        """Bind the accumulators and the labelling context."""
        self.notes = notes
        self.eff = eff
        self.rule = rule
        self.index = index


class _Nullability(IrLeaf[IrSelf, IrSelf]):
    """The nullability fixpoint as a standalone solver.

    Homes the ``R`` derives-empty computation that both
    :func:`nullable_names` (for :func:`~lexic.parsing.fold.lift_optional_nullables`)
    and :class:`GrammarAnalysis` need — a single fixpoint, no duplication. It
    exposes ``rules`` and a growing ``nullable`` set so the shared
    :data:`_NULLABLE` bodies read the same ``d.nullable`` attribute whether ``d``
    is this solver (mid-fixpoint) or a finished :class:`GrammarAnalysis`.

    :ivar rules: Rule name → its :class:`IrRule`.
    :ivar nullable: The nullable-name set, grown to the fixpoint by :meth:`solve`.
    """

    __slots__ = ("rules", "nullable")

    rules: Mapping[str, IrRule]
    nullable: set[str]

    def __init__(self, rules: Mapping[str, IrRule]) -> None:
        """:param rules: the rule table to analyse."""
        self.rules = rules
        self.nullable = set()

    def solve(self) -> frozenset[str]:
        """Grow ``nullable`` to the least fixpoint and return it frozen.

        :returns: The names of every rule that derives the empty string.
        """
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


# ── nullability dispatch bodies ───────────────────────────────────────────


def _null_ruleref(d: "GrammarAnalysis | _Nullability", n: IrSelf, _nc: object) -> bool:
    """A rule ref is nullable iff its target is currently known nullable."""
    return str(n) in d.nullable


def _null_literal(_d: object, n: IrSelf, _nc: object) -> bool:
    """A literal is nullable iff it is the empty string."""
    return not str(n)


def _null_never(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class or negated class always consumes one char — never nullable."""
    return False


def _null_alternation(
    d: "GrammarAnalysis | _Nullability", n: IrSelf, _nc: object
) -> bool:
    """A group is nullable iff any arm's items are all nullable."""
    assert isinstance(n, IrAlternation)
    return any(_seq_nullable(d, _items(arm)) for arm in n)


# ── FIRST dispatch bodies ─────────────────────────────────────────────────


def _first_literal(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a literal: its leading character (empty literal → empty set)."""
    text = str(n)
    return CharSet.from_chars(text[0]) if text else CharSet.EMPTY


def _first_charclass(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a char class: its member set."""
    assert isinstance(n, IrCharClass)
    return CharSet.from_charclass(n)


def _first_not(_d: object, n: IrSelf, _nc: object) -> CharSet:
    """FIRST of an ``IrNot``: the complement of its inner class (else ANY)."""
    assert isinstance(n, IrNot)
    inner = n[0]
    if isinstance(inner, IrCharClass):
        return CharSet.from_not(inner)
    return CharSet.ANY


def _first_ruleref(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a rule ref: the target's current FIRST; undefined ref → ANY."""
    got = d.first.get(str(n))
    return CharSet.ANY if got is None else got


def _first_alternation(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> CharSet:
    """FIRST of a group: the union of its arms' sequence FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_first(_items(arm)))
    return out


# ── hard-FIRST dispatch bodies ────────────────────────────────────────────


def _hard_terminal(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a terminal atom equals its FIRST (it is not nullable)."""
    return d.atom_first(cast(IrAtom, n))


def _hard_ruleref(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a rule ref: the target's current hard-FIRST; else ANY."""
    got = d.hard.get(str(n))
    return CharSet.ANY if got is None else got


def _hard_alternation(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> CharSet:
    """hard-FIRST of a group: the union of its arms' sequence hard-FIRSTs."""
    assert isinstance(n, IrAlternation)
    out = CharSet.EMPTY
    for arm in n:
        out = out.union(d.seq_hard(_items(arm)))
    return out


# ── single-char-set dispatch bodies (LL(2) machinery) ─────────────────────


def _single_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The single leading char of a non-empty literal, as a one-element set."""
    text = str(n)
    return frozenset({text[0]}) if text else None


def _single_charclass(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The member set of a positive char class; ``None`` if it went co-finite."""
    assert isinstance(n, IrCharClass)
    cs = CharSet.from_charclass(n)
    return None if cs.negated else cs.chars


def _single_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """Rule refs, groups and negations are not single deterministic chars."""
    return None


# ── 2-char prefix dispatch bodies ─────────────────────────────────────────


def _two_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The 2-char prefix of a ≥2-char literal, else ``None``."""
    text = str(n)
    return frozenset({text[:2]}) if len(text) >= 2 else None


def _two_group(d: "GrammarAnalysis", n: IrSelf, _nc: object) -> frozenset[str] | None:
    """The union of the arms' 2-char prefixes, or ``None`` if any is underivable."""
    assert isinstance(n, IrAlternation)
    return d.group_two_prefix(n)


def _two_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """A char class, negation or rule ref yields no standalone 2-char prefix."""
    return None


def _lead_literal(_d: object, n: IrSelf, _nc: object) -> frozenset[str] | None:
    """A leading ≥2-char literal's 2-char prefix, else ``None`` (literal-only)."""
    text = str(n)
    return frozenset({text[:2]}) if len(text) >= 2 else None


def _lead_none(_d: object, _n: IrSelf, _nc: object) -> frozenset[str] | None:
    """Only a leading literal short-circuits a sequence's 2-char prefix."""
    return None


# ── stop-set-eligibility dispatch bodies ──────────────────────────────────


def _stopset_yes(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A char class / negated class is a single-char loop → stop-set eligible."""
    return True


def _stopset_no(_d: object, _n: IrSelf, _nc: object) -> bool:
    """Literals, refs and groups are not stop-set loop atoms."""
    return False


# ── FOLLOW-feed dispatch bodies ───────────────────────────────────────────


def _feed_ruleref(d: "GrammarAnalysis", n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Union the effective continuation into a defined ref target's FOLLOW.

    :returns: ``True`` iff the target's FOLLOW set grew.
    """
    name = str(n)
    if name not in d.rules:
        return False
    ctx = cast(_FeedCtx, nc[0])
    grown = d.follow[name].union(ctx.eff)
    if grown != d.follow[name]:
        d.follow[name] = grown
        return True
    return False


def _feed_alternation(d: "GrammarAnalysis", n: IrSelf, nc: Sequence[IrSelf]) -> bool:
    """Feed the effective continuation into each of a group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(_FeedCtx, nc[0])
    changed = False
    for arm in n:
        if d.feed_seq(_items(arm), ctx.eff, ctx.rule):
            changed = True
    return changed


def _feed_terminal(_d: object, _n: IrSelf, _nc: object) -> bool:
    """A terminal atom has no sub-rule FOLLOW to update."""
    return False


# ── sequence-conflict dispatch bodies ─────────────────────────────────────


def _seq_ruleref(d: "GrammarAnalysis", n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Flag a rule ref whose target the grammar never defines."""
    if str(n) not in d.rules:
        ctx = cast(_ConflictCtx, nc[0])
        ctx.notes.hard.append(f"{ctx.rule}[{ctx.index}]: undefined ref {str(n)!r}")


def _seq_alternation(d: "GrammarAnalysis", n: IrSelf, nc: Sequence[IrSelf]) -> None:
    """Recurse conflict analysis into an inline group's arms."""
    assert isinstance(n, IrAlternation)
    ctx = cast(_ConflictCtx, nc[0])
    sub_arms = [_items(arm) for arm in n]
    label = f"{ctx.rule}[{ctx.index}]grp"
    scope = _Scope(ctx.rule, ctx.eff)
    d.arm_conflicts(sub_arms, ctx.eff, label, ctx.notes)
    for sub in sub_arms:
        d.seq_conflicts(sub, scope, ctx.notes)


def _seq_noop(_d: object, _n: IrSelf, _nc: object) -> None:
    """A terminal atom contributes no sequence-level conflict."""
    return None


# ── dispatch tables (open, raising default via IrTypeMap miss) ─────────────

_NULLABLE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_null_literal)),
    IrAction(IrCharClass, IrLambda(_null_never)),
    IrAction(IrNot, IrLambda(_null_never)),
    IrAction(IrRuleRef, IrLambda(_null_ruleref)),
    IrAction(IrAlternation, IrLambda(_null_alternation)),
)

_FIRST: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_first_literal)),
    IrAction(IrCharClass, IrLambda(_first_charclass)),
    IrAction(IrNot, IrLambda(_first_not)),
    IrAction(IrRuleRef, IrLambda(_first_ruleref)),
    IrAction(IrAlternation, IrLambda(_first_alternation)),
)

_HARD: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_hard_terminal)),
    IrAction(IrCharClass, IrLambda(_hard_terminal)),
    IrAction(IrNot, IrLambda(_hard_terminal)),
    IrAction(IrRuleRef, IrLambda(_hard_ruleref)),
    IrAction(IrAlternation, IrLambda(_hard_alternation)),
)

_SINGLE: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_single_literal)),
    IrAction(IrCharClass, IrLambda(_single_charclass)),
    IrAction(IrNot, IrLambda(_single_none)),
    IrAction(IrRuleRef, IrLambda(_single_none)),
    IrAction(IrAlternation, IrLambda(_single_none)),
)

_TWO_PREFIX: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_two_literal)),
    IrAction(IrCharClass, IrLambda(_two_none)),
    IrAction(IrNot, IrLambda(_two_none)),
    IrAction(IrRuleRef, IrLambda(_two_none)),
    IrAction(IrAlternation, IrLambda(_two_group)),
)

_LEAD_PREFIX: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_lead_literal)),
    IrAction(IrCharClass, IrLambda(_lead_none)),
    IrAction(IrNot, IrLambda(_lead_none)),
    IrAction(IrRuleRef, IrLambda(_lead_none)),
    IrAction(IrAlternation, IrLambda(_lead_none)),
)

_STOPSET_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_stopset_no)),
    IrAction(IrCharClass, IrLambda(_stopset_yes)),
    IrAction(IrNot, IrLambda(_stopset_yes)),
    IrAction(IrRuleRef, IrLambda(_stopset_no)),
    IrAction(IrAlternation, IrLambda(_stopset_no)),
)

_FOLLOW_FEED: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_feed_terminal)),
    IrAction(IrCharClass, IrLambda(_feed_terminal)),
    IrAction(IrNot, IrLambda(_feed_terminal)),
    IrAction(IrRuleRef, IrLambda(_feed_ruleref)),
    IrAction(IrAlternation, IrLambda(_feed_alternation)),
)

_SEQ_ATOM: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_seq_noop)),
    IrAction(IrCharClass, IrLambda(_seq_noop)),
    IrAction(IrNot, IrLambda(_seq_noop)),
    IrAction(IrRuleRef, IrLambda(_seq_ruleref)),
    IrAction(IrAlternation, IrLambda(_seq_alternation)),
)


# ── nullability helpers (shared by solver and analysis) ────────────────────


def _item_nullable(d: "GrammarAnalysis | _Nullability", item: IrItem) -> bool:
    """Whether ``item`` can consume nothing: ``lo == 0`` or a nullable atom."""
    if int(item.quantifier.lo) == 0:
        return True
    return cast(bool, _NULLABLE.resolve(item.atom).eval(d, item.atom, ()))


def _seq_nullable(d: "GrammarAnalysis | _Nullability", items: Sequence[IrItem]) -> bool:
    """Whether every item in a sequence arm is nullable (empty arm → True)."""
    return all(_item_nullable(d, i) for i in items)


def _rule_nullable(d: "GrammarAnalysis | _Nullability", rule: IrRule) -> bool:
    """Whether any arm of ``rule`` is all-nullable."""
    return any(_seq_nullable(d, _items(arm)) for arm in rule.body)


def nullable_names(rules: Sequence[IrRule]) -> frozenset[str]:
    """The names of every rule in ``rules`` that derives the empty string.

    The single home of the nullability fixpoint —
    :func:`~lexic.parsing.fold.lift_optional_nullables` consumes it from here
    (an intra-package import) rather than keeping its own copy.

    :param rules: The grammar's rules.
    :returns: The nullable rule names.
    """
    return _Nullability({str(r.name): r for r in rules}).solve()


# ── the analysis ──────────────────────────────────────────────────────────


class _Taxonomy(IrLeaf[IrSelf, IrSelf]):
    """The classified per-rule notes — the taxonomy result, held as one slot.

    :ivar conflicts: Rule name → island-worthy notes (presence marks an island).
    :ivar demoted: Rule name → stop-set / LL(2) demotion notes.
    """

    __slots__ = ("conflicts", "demoted")

    conflicts: dict[str, list[str]]
    demoted: dict[str, list[str]]

    def __init__(self) -> None:
        """Seed both note maps empty."""
        self.conflicts = {}
        self.demoted = {}


class GrammarAnalysis(IrLeaf[IrSelf, IrSelf]):
    """FIRST/hard-FIRST/FOLLOW/nullability + per-rule conflict classification.

    Constructed over a lifted codegen grammar; all fixpoints run in
    ``__init__`` and the results live on the instance. The analysis IS the
    dispatcher slot ``d`` handed to every atom-type table body — its ``first`` /
    ``hard`` / ``follow`` / ``nullable`` state and its recursive ``seq_*``
    helpers are read straight off ``d``.

    :ivar rules: Rule name → its :class:`IrRule`.
    :ivar start: The start rule name.
    :ivar nullable: Names of rules deriving empty.
    :ivar first: Rule name → its FIRST :class:`CharSet`.
    :ivar hard: Rule name → its hard-FIRST :class:`CharSet`.
    :ivar follow: Rule name → its FOLLOW :class:`CharSet`.
    """

    __slots__ = ("rules", "start", "nullable", "first", "hard", "follow", "_tax")

    rules: dict[str, IrRule]
    start: str
    nullable: frozenset[str]
    first: dict[str, CharSet]
    hard: dict[str, CharSet]
    follow: dict[str, CharSet]
    _tax: _Taxonomy

    def __init__(self, grammar: IrAst) -> None:
        """Run every fixpoint and classify every rule.

        :param grammar: The lifted codegen grammar to analyse.
        """
        self.rules = {str(r.name): r for r in grammar.rules}
        self.start = str(grammar.start)
        self.nullable = nullable_names(list(grammar.rules))
        self.first = self._first_sets()
        self.hard = self._hard_sets()
        self.follow = self._follow_sets()
        self._tax = _Taxonomy()
        self._classify()

    @property
    def conflicts(self) -> dict[str, list[str]]:
        """Rule name → island-worthy conflict notes (presence marks an island)."""
        return self._tax.conflicts

    @property
    def demoted(self) -> dict[str, list[str]]:
        """Rule name → stop-set / LL(2) demotion notes."""
        return self._tax.demoted

    @property
    def islands(self) -> frozenset[str]:
        """The island rule set — every rule with an island-worthy conflict.

        :returns: The names keying :attr:`conflicts`.
        """
        return frozenset(self._tax.conflicts)

    # ── nullability queries ────────────────────────────────────────────

    def atom_nullable(self, atom: IrAtom) -> bool:
        """Whether ``atom`` can consume nothing under the final nullable set.

        :param atom: The atom to test.
        :returns: ``True`` iff the atom derives empty.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(bool, _NULLABLE.resolve(atom).eval(self, atom, ()))

    def item_nullable(self, item: IrItem) -> bool:
        """Whether ``item`` can consume nothing (``lo == 0`` or nullable atom).

        :param item: The quantified item.
        :returns: ``True`` iff the item derives empty.
        """
        return _item_nullable(self, item)

    # ── FIRST ──────────────────────────────────────────────────────────

    def atom_first(self, atom: IrAtom) -> CharSet:
        """FIRST set of a single atom.

        :param atom: The atom.
        :returns: Its leading-character set.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, _FIRST.resolve(atom).eval(self, atom, ()))

    def seq_first(self, items: Sequence[IrItem]) -> CharSet:
        """FIRST set of an item sequence — union until the first non-nullable.

        :param items: The sequence arm's items.
        :returns: The sequence's leading-character set.
        """
        out = CharSet.EMPTY
        for item in items:
            out = out.union(self.atom_first(item.atom))
            if not self.item_nullable(item):
                break
        return out

    def _first_sets(self) -> dict[str, CharSet]:
        """The per-rule FIRST fixpoint (chaotic iteration to stability)."""
        self.first = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_first(_items(arm)))
                if acc != self.first[name]:
                    self.first[name] = acc
                    changed = True
        return self.first

    # ── hard-FIRST ─────────────────────────────────────────────────────

    def atom_hard(self, atom: IrAtom) -> CharSet:
        """hard-FIRST set of a single atom (nullable prefixes contribute nothing).

        :param atom: The atom.
        :returns: The characters the atom *requires* to progress.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(CharSet, _HARD.resolve(atom).eval(self, atom, ()))

    def seq_hard(self, items: Sequence[IrItem]) -> CharSet:
        """hard-FIRST of a sequence — the first non-nullable item's hard-FIRST.

        :param items: The sequence arm's items.
        :returns: The required leading chars, or empty if the arm is all-nullable.
        """
        for item in items:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return CharSet.EMPTY

    def hard_cont_at(
        self, items: Sequence[IrItem], k: int, hard_tail: CharSet
    ) -> CharSet:
        """hard continuation after item ``k``: the next required chars, else tail.

        :param items: The enclosing sequence arm.
        :param k: The index the loop-gate is being computed for.
        :param hard_tail: The rule's own hard continuation (used when the arm
            remainder is all-nullable).
        :returns: The hard continuation char set.
        """
        for item in items[k + 1 :]:
            if self.item_nullable(item):
                continue
            return self.atom_hard(item.atom)
        return hard_tail

    def _hard_sets(self) -> dict[str, CharSet]:
        """The per-rule hard-FIRST fixpoint."""
        self.hard = {name: CharSet.EMPTY for name in self.rules}
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                acc = CharSet.EMPTY
                for arm in rule.body:
                    acc = acc.union(self.seq_hard(_items(arm)))
                if acc != self.hard[name]:
                    self.hard[name] = acc
                    changed = True
        return self.hard

    # ── 2-char prefix sets (LL(2)) ─────────────────────────────────────

    def _single_chars(self, atom: IrAtom) -> frozenset[str] | None:
        """The finite positive single-char set of ``atom``, or ``None``.

        A literal contributes its leading char, a positive char class its
        members; refs, groups, negations and co-finite classes yield ``None``.
        """
        return cast("frozenset[str] | None", _SINGLE.resolve(atom).eval(self, atom, ()))

    def two_prefix_seq(self, items: Sequence[IrItem]) -> frozenset[str] | None:
        """The 2-char prefix set of a sequence, or ``None`` (not derivable).

        A leading ≥2-char literal supplies the prefix directly; otherwise the
        first two non-nullable single-char atoms' cross-product does, subject to
        the :data:`_MAX_PAIR_PRODUCT` cap.

        :param items: The sequence arm's items.
        :returns: The 2-char prefixes, or ``None``.
        """
        if items and not self.item_nullable(items[0]):
            lead = cast(
                "frozenset[str] | None",
                _LEAD_PREFIX.resolve(items[0].atom).eval(self, items[0].atom, ()),
            )
            if lead is not None:
                return lead
        if len(items) < 2:
            return None
        first_item, second_item = items[0], items[1]
        if self.item_nullable(first_item) or self.item_nullable(second_item):
            return None
        first_chars = self._single_chars(first_item.atom)
        second_chars = self._single_chars(second_item.atom)
        if first_chars is None or second_chars is None:
            return None
        if len(first_chars) * len(second_chars) > _MAX_PAIR_PRODUCT:
            return None
        return frozenset(a + b for a in first_chars for b in second_chars)

    def group_two_prefix(self, group: IrAlternation) -> frozenset[str] | None:
        """The union of a group's arms' 2-char prefixes, or ``None``.

        :param group: The inline group.
        :returns: The combined 2-char prefixes, or ``None`` if any arm's is
            not derivable.
        """
        out: set[str] = set()
        for arm in group:
            sub = self.two_prefix_seq(_items(arm))
            if sub is None:
                return None
            out |= sub
        return frozenset(out)

    def atom_two_prefix(self, atom: IrAtom) -> frozenset[str] | None:
        """The standalone 2-char prefix set of ``atom``, or ``None``.

        :param atom: The atom.
        :returns: Its 2-char prefixes (group union or ≥2-char literal), else
            ``None``.
        :raises UnsupportedConstructError: On an unregistered atom type.
        """
        return cast(
            "frozenset[str] | None", _TWO_PREFIX.resolve(atom).eval(self, atom, ())
        )

    # ── loop policy (the pivot-6 taxonomy) ─────────────────────────────

    def loop_policy(
        self, item: IrItem, rest: Sequence[IrItem]
    ) -> tuple[str, frozenset[str]] | str:
        """Classify a looping item whose FIRST overlaps its hard continuation.

        :param item: The optional/looping item.
        :param rest: The items following it in the arm.
        :returns: ``("pairs", set)`` for an LL(2) gate, ``"stopset"`` for a
            non-greedy single-char loop, or ``"island"`` otherwise.
        """
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if lo == 0 and hi == 1:
            taken = self.atom_two_prefix(atom)
            skip = self.two_prefix_seq(list(rest))
            if taken is not None and skip is not None and not taken & skip:
                return ("pairs", taken)
        if hi is None and self._stopset_eligible(atom):
            return "stopset"
        return "island"

    def _stopset_eligible(self, atom: IrAtom) -> bool:
        """Whether ``atom`` is a single-char loop atom (char class / negation)."""
        return cast(bool, _STOPSET_ATOM.resolve(atom).eval(self, atom, ()))

    # ── FOLLOW ─────────────────────────────────────────────────────────

    def _follow_sets(self) -> dict[str, CharSet]:
        """The per-rule FOLLOW fixpoint (EOF-seeded at the start rule)."""
        self.follow = {name: CharSet.EMPTY for name in self.rules}
        self.follow[self.start] = _EOF
        changed = True
        while changed:
            changed = False
            for name, rule in self.rules.items():
                for arm in rule.body:
                    if self.feed_seq(_items(arm), self.follow[name], name):
                        changed = True
        return self.follow

    def feed_seq(self, items: Sequence[IrItem], tail: CharSet, rule: str) -> bool:
        """Feed FOLLOW contributions of a sequence whose continuation is ``tail``.

        Walks the arm right to left, carrying the running continuation set; a
        repeating item feeds its own FIRST back into itself. Each atom's
        sub-rule FOLLOW update is delegated to :data:`_FOLLOW_FEED`.

        :param items: The sequence arm's items.
        :param tail: The continuation at the arm's end (the rule's FOLLOW).
        :param rule: The enclosing rule name.
        :returns: ``True`` iff any FOLLOW set grew.
        """
        changed = False
        cont = tail
        for item in reversed(items):
            atom = item.atom
            hi = _hi(item)
            eff = cont
            if hi is None or hi > 1:
                eff = eff.union(self.atom_first(atom))
            ctx = _FeedCtx(eff, rule)
            if cast(bool, _FOLLOW_FEED.resolve(atom).eval(self, atom, (ctx,))):
                changed = True
            first = self.atom_first(atom)
            cont = cont.union(first) if self.item_nullable(item) else first
        return changed

    # ── conflict classification ────────────────────────────────────────

    def _classify(self) -> None:
        """Fill :attr:`conflicts` and :attr:`demoted` from every rule."""
        for name, rule in self.rules.items():
            notes = _Notes()
            scope = _Scope(name, self.follow[name])
            arms = [_items(arm) for arm in rule.body]
            self.arm_conflicts(arms, self.follow[name], name, notes)
            for arm in arms:
                self.seq_conflicts(arm, scope, notes)
            if notes.hard:
                self._tax.conflicts[name] = notes.hard
            if notes.soft:
                self._tax.demoted[name] = notes.soft

    def arm_conflicts(
        self,
        arms: Sequence[Sequence[IrItem]],
        ext_follow: CharSet,
        label: str,
        notes: "_Notes",
    ) -> None:
        """Flag pairwise FIRST overlaps and empty-arm-vs-FOLLOW ambiguities.

        :param arms: The alternation's arms (as item lists).
        :param ext_follow: The FOLLOW set at the alternation's end.
        :param label: The note-label prefix (rule name or group tag).
        :param notes: The rule's note accumulators.
        """
        infos = [(self.seq_first(arm), _seq_nullable(self, arm)) for arm in arms]
        for i, (first_i, _) in enumerate(infos):
            for j, (first_j, _) in enumerate(infos[i + 1 :], i + 1):
                if first_i.overlaps(first_j):
                    notes.hard.append(f"{label}: arms {i}/{j} FIRST overlap")
        if any(nullable for _, nullable in infos):
            for i, (first_i, nullable) in enumerate(infos):
                if not nullable and first_i.overlaps(ext_follow):
                    notes.soft.append(f"{label}: arm {i} FIRST hits FOLLOW (greedy)")

    def seq_conflicts(
        self, items: Sequence[IrItem], scope: "_Scope", notes: "_Notes"
    ) -> None:
        """Classify every decision point in one sequence arm.

        :param items: The arm's items.
        :param scope: The enclosing rule and its FOLLOW tail.
        :param notes: The rule's note accumulators.
        """
        for k in range(len(items)):
            self._loop_conflict(items, k, scope, notes)
            self._sub_conflict(items, k, scope, notes)

    def _loop_conflict(
        self, items: Sequence[IrItem], k: int, scope: "_Scope", notes: "_Notes"
    ) -> None:
        """Classify item ``k``'s continue/exit decision (the pivot-6 taxonomy)."""
        item = items[k]
        atom = item.atom
        lo = int(item.quantifier.lo)
        hi = _hi(item)
        if hi is not None and hi <= lo:
            return
        if self.atom_nullable(atom) and (hi is None or hi - lo > 1):
            notes.hard.append(f"{scope.rule}[{k}]: unbounded loop over nullable atom")
            return
        if self.atom_first(atom).overlaps(self.hard_cont_at(items, k, scope.tail)):
            policy = self.loop_policy(item, items[k + 1 :])
            if policy == "island":
                notes.hard.append(f"{scope.rule}[{k}]: loop overlap, not gatable")
            elif policy == "stopset":
                notes.soft.append(f"{scope.rule}[{k}]: loop stop-set applied")
            else:
                notes.soft.append(f"{scope.rule}[{k}]: LL(2) pair gate")

    def _sub_conflict(
        self, items: Sequence[IrItem], k: int, scope: "_Scope", notes: "_Notes"
    ) -> None:
        """Dispatch item ``k``'s atom for undefined-ref / group-recursion checks."""
        item = items[k]
        atom = item.atom
        hi = _hi(item)
        cont = self._cont_at(items, k, scope.tail)
        eff = cont
        if hi is None or hi > 1:
            eff = eff.union(self.atom_first(atom))
        ctx = _ConflictCtx(notes, eff, scope.rule, k)
        _SEQ_ATOM.resolve(atom).eval(self, atom, (ctx,))

    def _cont_at(self, items: Sequence[IrItem], k: int, tail: CharSet) -> CharSet:
        """The continuation char set after item ``k`` (rest of arm, then tail)."""
        rest = items[k + 1 :]
        cont = self.seq_first(rest)
        if all(self.item_nullable(i) for i in rest):
            cont = cont.union(tail)
        return cont
