"""Size-targeting — steering the free walk toward a document of about N characters.

:func:`lexic.generate.generate` with ``size=`` hands over to :func:`steer`,
passing its own free walk and arm filter, so both choose from one set of arms
and a budget near natural size is spent by exactly the walk ``generate`` runs
without ``size``. Everything here is read off the grammar — no grammar is
named and no formulation is privileged.

Every expansion carries a character BUDGET. One at or below the rule's NATURAL
size (the exact expectation of the free walk at :data:`_NATURAL_DEPTH`) is
spent by the free walk. A larger one takes an arm with ROOM for it — the most a
steered expansion can yield within its remaining depth, zero once the depth is
spent — preferring one that can NEST (holds an item reaching a reference
cycle), and shares the budget over the arm's growing items, nesting ones first,
each capped at its room with the excess re-shared. A repetition spends its
share measuring what it produced: a RECURSIVE atom takes heavy-tailed pieces of
at most half its share, so the document nests; any other takes natural-size
pieces, so it repeats as ordinary units.

The sizer is as lazy as the walk it predicts: an optional reference or group is
not sized where a spent depth would not expand it. A steered level costs more
stack than a free one and the frames per level depend on the grammar, so no
constant bounds it: a target that needs deeper nesting than the stack carries
is REFUSED, with words, rather than clamped behind the caller's back.
"""

from __future__ import annotations

import random as _random
from typing import Callable, ClassVar, NamedTuple, Protocol, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrDispatch,
    IrInt,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNamedTuple,
    IrNoneType,
    IrQuantifier,
    IrRaise,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)

Rules = dict[str, IrRule]
_INF = float("inf")
_UNIT = IrQuantifier(1, 1)


class Walk(Protocol):
    """The free walk, as steering uses it."""

    def run(self, rule_name: str) -> str:
        """Expand a named rule."""
        raise NotImplementedError

    def alternation(self, body: IrAlternation, where: str) -> str:
        """Expand one arm of ``body``."""
        raise NotImplementedError

    def atom(self, item: IrItem) -> str:
        """Expand one item."""
        raise NotImplementedError


Walker = Callable[[int], Walk]
"""The free walk at a depth."""

ArmFilter = Callable[[IrAlternation, int, str], list[Sequence[IrItem]]]
"""The arms a walk at a depth may choose, refusing an arm-less or looping body."""


class FreeWalk(NamedTuple):
    """The free walk ``generate`` runs without ``size``, as steering is handed it.

    :ivar rng: The random source both draw from.
    :ivar arms: Its arm filter, so both choose from one set of arms.
    :ivar walker: The walk itself at a depth.
    :ivar pick_mean: The walk's expected count for a quantifier — its own
        distribution's mean, owned where the distribution is.
    """

    rng: _random.Random
    arms: ArmFilter
    walker: Walker
    pick_mean: Callable[[IrQuantifier], float]


_NATURAL_DEPTH = 3
"""The depth a budget near natural size is spent at. Small on purpose: a free
walk's expected size can grow geometrically with depth in a recursive grammar."""

_SPREAD = 2.0
"""An item whose room is within this factor of its natural size cannot GROW:
it is walked freely at its natural size, not handed a share."""

_TAIL = 2.0
"""A recursive piece is ``natural * (share / natural) ** (u ** _TAIL)`` for a
uniform ``u``: small pieces common, whole-share pieces rare."""

Size = tuple[float, float]
"""``(mean, room)``: the free walk's expected size, and the most a steered
expansion can yield within its depth."""


def _most(q: IrQuantifier) -> float:
    """The most repetitions an item allows; unbounded is infinite."""
    return _INF if isinstance(q.hi, IrNoneType) else float(q.hi)


def _scaled(d: _Shape, q: IrQuantifier, depth: int, size: Size) -> Size:
    """A ref or group's size under its quantifier — the lower bound once spent."""
    count = float(q.lo) if depth <= 0 else d.free.pick_mean(q)
    return count * size[0] if count else 0.0, _most(q) * size[1] if size[1] else 0.0


def _channel(nc: Sequence[IrSelf]) -> tuple[IrItem, int]:
    """What rides a sizing table's argument channel: the item, and the depth."""
    item, depth = nc[0], nc[1]
    assert isinstance(item, IrItem) and isinstance(depth, IrInt)
    return item, int(depth)


def _size_literal(d: _Shape, n: IrLiteral, nc: Sequence[IrSelf]) -> Size:
    """Its length per repetition."""
    q = _channel(nc)[0].quantifier
    return d.free.pick_mean(q) * len(n), _most(q) * len(n) if len(n) else 0.0


def _size_charclass(d: _Shape, _n: IrCharClass, nc: Sequence[IrSelf]) -> Size:
    """One character per repetition."""
    q = _channel(nc)[0].quantifier
    return d.free.pick_mean(q), _most(q)


def _size_ruleref(d: _Shape, n: IrRuleRef, nc: Sequence[IrSelf]) -> Size:
    """The target's, one level down — not even looked at where the walk would
    not expand it (a spent depth and a lower bound of 0), which is what stops
    a self-reference in an optional group from sizing forever."""
    item, depth = _channel(nc)
    q = item.quantifier
    if depth <= 0 and q.lo == 0:
        return 0.0, 0.0
    return _scaled(d, q, depth, d.rule_size(str(n), depth - 1))


def _size_group(d: _Shape, n: IrAlternation, nc: Sequence[IrSelf]) -> Size:
    """The group's, at the same level — lazily, as :func:`_size_ruleref`."""
    item, depth = _channel(nc)
    q = item.quantifier
    if depth <= 0 and q.lo == 0:
        return 0.0, 0.0
    return _scaled(d, q, depth, d.alt_size(n, depth))


# One entry per atom kind, mirroring _GEN_ATOM — an atom that cannot be sized
# refuses rather than being guessed at.
_SIZE_ATOM: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_size_literal)),
        IrAction(IrCharClass, IrLambda(_size_charclass)),
        IrAction(IrRuleRef, IrLambda(_size_ruleref)),
        IrAction(IrAlternation, IrLambda(_size_group)),
    ),
    default=IrRaise(message="generate: no size rule for {node_type!r}"),
)


def _refs_terminal(_d: _Shape, _n: IrSelf, _nc: Sequence[IrSelf]) -> frozenset[str]:
    """A literal or char class names no rule."""
    return frozenset()


def _refs_ruleref(_d: _Shape, n: IrRuleRef, _nc: Sequence[IrSelf]) -> frozenset[str]:
    """A reference names its target."""
    return frozenset((str(n),))


def _refs_group(d: _Shape, n: IrAlternation, _nc: Sequence[IrSelf]) -> frozenset[str]:
    """A group names what its arms name."""
    return d.alt_refs(n)


_REFS_ATOM: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_refs_terminal)),
        IrAction(IrCharClass, IrLambda(_refs_terminal)),
        IrAction(IrRuleRef, IrLambda(_refs_ruleref)),
        IrAction(IrAlternation, IrLambda(_refs_group)),
    ),
    default=IrRaise(message="generate: no reference rule for {node_type!r}"),
)


class _Shape(
    IrNamedTuple[Rules, ArmFilter, dict[tuple[str, int], Size], frozenset[str]]
):
    """What size-steering reads off a grammar, computed once per call.

    :ivar rules: The rules by name.
    :ivar free: The free walk it predicts — its arms and its count distribution.
    :ivar memo: ``(rule, depth)`` → its :data:`Size`.
    :ivar recursive: The rules that reach a reference cycle.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rules: Rules
    free: FreeWalk
    memo: dict[tuple[str, int], Size]
    recursive: frozenset[str]

    @classmethod
    def of(cls, rules: Rules, free: FreeWalk, depth: int) -> _Shape:
        """Which rules reach a cycle, by fixpoint; then sizes bottom-up to ``depth``,
        so no reading recurses as deep as the budget."""
        bare = cls(rules=rules, free=free, memo={}, recursive=frozenset())
        reach = {name: set(bare.alt_refs(rule.body)) for name, rule in rules.items()}
        changed = True
        while changed:
            changed = False
            for seen in reach.values():
                more = set().union(*(reach.get(t, ()) for t in seen)) - seen
                seen |= more
                changed = changed or bool(more)
        cyclic = {name for name, seen in reach.items() if name in seen}
        recursive = frozenset(n for n, seen in reach.items() if seen & cyclic)
        shape = cls(rules=rules, free=free, memo={}, recursive=recursive)
        for level in range(depth + 1):
            for name in rules:
                shape.rule_size(name, level)
        return shape

    def alt_refs(self, body: IrAlternation) -> frozenset[str]:
        """Every rule an alternation names, groups included."""
        return frozenset().union(
            *(_REFS_ATOM.eval(self, item.atom, ()) for arm in body for item in arm)
        )

    def atom_recursive(self, item: IrItem) -> bool:
        """Whether an item's atom reaches a reference cycle."""
        return bool(_REFS_ATOM.eval(self, item.atom, ()) & self.recursive)

    def rule_size(self, name: str, depth: int) -> Size:
        """Rule ``name`` at ``depth``, memoised; no room once the depth is spent."""
        got = self.memo.get((name, depth))
        if got is None:
            rule = self.rules.get(name)
            got = (0.0, 0.0) if rule is None else self.alt_size(rule.body, depth)
            got = self.memo[(name, depth)] = (got[0], got[1] if depth > 0 else 0.0)
        return got

    def alt_size(self, body: IrAlternation, depth: int) -> Size:
        """The mean over the arms a walk at ``depth`` may choose; the roomiest."""
        arms = self.free.arms(body, depth, "an alternation")
        sizes = [self.arm_size(arm, depth) for arm in arms]
        return sum(m for m, _r in sizes) / len(sizes), max(r for _m, r in sizes)

    def arm_size(self, arm: Sequence[IrItem], depth: int) -> Size:
        """An arm's: its items' together."""
        sizes = [self.item_size(item, depth) for item in arm]
        return sum(m for m, _r in sizes), sum(r for _m, r in sizes)

    def item_size(self, item: IrItem, depth: int) -> Size:
        """One item's, under its quantifier."""
        size = _SIZE_ATOM.eval(self, item.atom, (item, IrInt(depth)))
        return float(size[0]), float(size[1])

    def unit_mean(self, item: IrItem) -> float:
        """One repetition of the atom, spent freely: a reference's target walked
        at the natural depth, as :meth:`_Filler.rule` walks it. At least 1."""
        unit = IrItem(item.atom, _UNIT)
        return max(1.0, self.item_size(unit, _NATURAL_DEPTH + 1)[0])


def _fill_ruleref(d: _Filler, n: IrRuleRef, _nc: Sequence[IrSelf]) -> str:
    """Spend the budget on the target, one level down."""
    return d.spending(d.budget, 1).rule(str(n))


def _fill_group(d: _Filler, n: IrAlternation, _nc: Sequence[IrSelf]) -> str:
    """Spend the budget on the group, at the same level."""
    return d.alternation(n, "an inline group")


# Only an atom with room is filled; a terminal's size is fixed, so its item
# repeats it instead and reaching one here is a defect.
_FILL_ATOM: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrRuleRef, IrLambda(_fill_ruleref)),
        IrAction(IrAlternation, IrLambda(_fill_group)),
    ),
    default=IrRaise(message="generate: no budget rule for {node_type!r}"),
)


class _Filler(IrNamedTuple[_random.Random, _Shape, Walker, int, float]):
    """Size-steered generation: one expansion and the budget it may spend.

    :ivar rng: The shared random source — the walker's too.
    :ivar shape: What the grammar says about sizes.
    :ivar walker: The free walk at a depth, which a small budget is spent by.
    :ivar max_depth: The remaining reference budget, as for the free walk.
    :ivar budget: The characters this expansion is to spend, about.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rng: _random.Random
    shape: _Shape
    walker: Walker
    max_depth: int
    budget: float

    def spending(self, budget: float, down: int = 0) -> _Filler:
        """This expansion with another budget, ``down`` references deeper."""
        return _Filler(
            rng=self.rng,
            shape=self.shape,
            walker=self.walker,
            max_depth=self.max_depth - down,
            budget=budget,
        )

    def free(self, depth: int = _NATURAL_DEPTH) -> Walk:
        """The free walk a small budget is spent by."""
        return self.walker(min(self.max_depth, depth))

    def rule(self, name: str) -> str:
        """Spend the budget on rule ``name``; within its natural size, walk it."""
        rule = self.shape.rules.get(name)
        near = self.shape.rule_size(name, _NATURAL_DEPTH)[0]
        if rule is None or self.max_depth <= 0 or self.budget <= near:
            return self.free().run(name)
        return self.alternation(rule.body, f"rule {name!r}")

    def alternation(self, body: IrAlternation, where: str) -> str:
        """Spend the budget on an arm with room for it — one that can NEST first,
        so a large budget becomes structure — else on the roomiest arm."""
        depth, shape = self.max_depth, self.shape
        arms = shape.free.arms(body, depth, where)
        rooms = [shape.arm_size(arm, depth)[1] for arm in arms]
        fits = [arm for arm, room in zip(arms, rooms) if room >= self.budget]
        nests = [arm for arm in fits if any(map(shape.atom_recursive, arm))]
        if fits:
            return self.arm(self.rng.choice(nests or fits))
        if max(rooms) <= _SPREAD * shape.alt_size(body, _NATURAL_DEPTH)[0]:
            return self.free().alternation(body, where)
        return self.arm(arms[rooms.index(max(rooms))])

    def arm(self, arm: Sequence[IrItem]) -> str:
        """Share the budget over the items that can grow — the ones that NEST, when
        any do — and walk the rest freely. A share is capped at its item's room
        and the excess re-shared; each item measures what it spends (:meth:`item`),
        so no sibling has to pay back another's miss."""
        sizes = [self.shape.item_size(item, self.max_depth)[1] for item in arm]
        means = [self.shape.item_size(item, _NATURAL_DEPTH)[0] for item in arm]
        grow = [room > _SPREAD * mean for room, mean in zip(sizes, means)]
        nest = [g and self.shape.atom_recursive(item) for item, g in zip(arm, grow)]
        grow = nest if any(nest) else grow  # structure first: flat runs stay natural
        spare = self.budget - sum(m for m, g in zip(means, grow) if not g)
        weights = [self.rng.random() + 0.25 if g else 0.0 for g in grow]
        shares = _spill(max(spare, 0.0), sizes, weights)
        return "".join(
            self.spending(share).item(item) if g else self.free().atom(item)
            for item, g, share in zip(arm, grow, shares)
        )

    def item(self, item: IrItem) -> str:
        """Spend the budget on one item's repetitions, measuring as it goes."""
        unit = IrItem(item.atom, _UNIT)
        each = self.shape.item_size(unit, self.max_depth)[1]
        natural = self.shape.unit_mean(item)
        q, most = item.quantifier, _most(item.quantifier)
        walk = self.free(_NATURAL_DEPTH + 1)
        out: list[str] = []
        made = 0
        while len(out) < most:
            left = self.budget - made
            if len(out) >= q.lo and left < natural / 2:
                break
            if each > _SPREAD * natural:
                piece = self.piece(item, left, natural, most - len(out))
                budget = max(min(piece, left), 0.0)
                out.append(str(_FILL_ATOM.eval(self.spending(budget), item.atom, ())))
            else:
                out.append(walk.atom(unit))
            made += len(out[-1])
        return "".join(out)

    def piece(self, item: IrItem, left: float, unit: float, slots: float) -> float:
        """The next repetition's share: heavy-tailed and at most half the budget
        for a recursive atom, so it nests; exactly natural for any other, which
        the free walk varies. A bounded count spreads what is left over its slots.
        """
        if item.quantifier.hi == item.quantifier.lo:
            return left / slots
        piece = unit
        if self.shape.atom_recursive(item):
            tail = unit * (max(left, unit) / unit) ** (self.rng.random() ** _TAIL)
            piece = min(tail, max(unit, self.budget / 2))
        return max(piece, left / slots) if slots < _INF else piece


def _spill(spare: float, rooms: list[float], weights: list[float]) -> list[float]:
    """``spare`` shared by weight, each share capped at its room, excess re-shared."""
    shares = [0.0] * len(rooms)
    while spare > 1.0 and any(weights):
        total, over = sum(weights), 0.0
        for k, weight in enumerate(weights):
            if weight:
                shares[k] += spare * weight / total
                if shares[k] >= rooms[k]:
                    over += shares[k] - rooms[k]
                    shares[k], weights[k] = rooms[k], 0.0
        spare = over
    return shares


def steer(
    rule_name: str, rules: Rules, free: FreeWalk, max_depth: int, size: int
) -> str:
    """A document of rule ``rule_name`` of about ``size`` characters.

    :param rule_name: The rule to expand.
    :param rules: The grammar as a rule-name → :class:`IrRule` mapping.
    :param free: The free walk ``generate`` runs without ``size``.
    :param max_depth: How deep a budget may nest.
    :param size: The target, in characters.
    :returns: The document.
    :raises UnsupportedConstructError: When the target needs deeper nesting
        than the interpreter's stack carries at ``max_depth``. Only the FILL is
        guarded: :meth:`_Shape.of` sizes rules bottom-up per depth, so rule
        references never recurse deep there, but a grammar with thousands of
        nested INLINE groups would still raise raw from the sizing.
    """
    shape = _Shape.of(rules, free, max_depth)
    filler = _Filler(
        rng=free.rng,
        shape=shape,
        walker=free.walker,
        max_depth=max_depth,
        budget=float(size),
    )
    try:
        return filler.rule(rule_name)
    except RecursionError as exc:
        raise UnsupportedConstructError(
            f"generate: size={size} needs deeper nesting than the stack carries at "
            f"max_depth={max_depth} — lower max_depth or size"
        ) from exc
