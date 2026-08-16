"""Grammar-agnostic random string generator over a grammar ``IrAst``.

Walks a rules-by-name view of a (canonical) grammar: each rule body is an
:class:`IrAlternation` of arms, an arm a sequence of items. Generation picks a
random arm and expands each item by its atom kind and quantifier, recursing on
:class:`IrRuleRef` occurrences. ``max_depth`` decrements on each ref expansion.

Atom expansion is an open :class:`~lexic.ir.action.walk.IrDispatch` table keyed on the
atom type (``IrLiteral`` / ``IrCharClass`` / ``IrRuleRef`` / ``IrAlternation``
group), with a raising default — an unregistered atom type fails loudly rather
than silently generating ``""``. The generator documents itself over canonical
grammars, so ``IrNot`` never reaches it (the canonicaliser rewrites ``[^…]`` to
positive spans upstream); a stray one hits the raising default.

The same rule holds off the table: an **undefined rule name** and an
**arm-less alternation** refuse with words rather than expanding to ``""``.
Both once returned the empty string, which a consumer cannot tell from a
grammar that legitimately generates it — a generated sample and a failure
read identically. What still expands to ``""`` is what genuinely derives it:
an alternation with one EMPTY arm, and a quantifier rolled to zero.

``max_depth`` is a real bound, made real by rule HEIGHTS — the minimal
number of nested rule expansions a rule needs to reach a terminal
spelling, computed once per call by fixpoint. An arm that cannot ever
terminate (its rule loops forever) is never chosen at any depth; while
budget remains the choice among terminating arms is free; at an exhausted
budget it restricts to the minimal-height arms and a quantified ref
collapses to its lower bound, so every further step strictly descends the
height measure and generation terminates. A rule whose EVERY arm loops
refuses with words — the budget was once decremented and never read, so
``root ::= root "a"`` recursed to the interpreter's limit instead of
refusing at the caller's.
"""

from __future__ import annotations

import random as _random
from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrAlternation,
    IrCharClass,
    IrDispatch,
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

_UNIT = IrQuantifier(1, 1)


def _pick_count(q: IrQuantifier, rng: _random.Random) -> int:
    """Pick a repetition count within the quantifier's bounds.

    A fixed count (``hi == lo``) is returned verbatim. Otherwise the lower
    bound is rolled at 70%, else an expanded count in ``[lo + 1, hi]`` (with
    ``hi`` capped at ``lo + 2`` when unbounded above). This roll applies to a
    ``lo == 0`` quantifier (``*`` / ``?``) too — so a star/optional-rooted rule
    is empty most of the time but does expand, rather than always yielding ``""``.
    """
    if q.hi == q.lo:
        return q.lo
    hi = q.lo + 2 if isinstance(q.hi, IrNoneType) else min(q.hi, q.lo + 2)
    if rng.random() < 0.7:
        return q.lo
    return rng.randint(q.lo + 1, hi)


# ── per-atom generation bodies (dispatch on the atom; the owning IrItem
#    rides the argument channel so each body can read the quantifier) ──────


def _item(nc: Sequence[IrSelf]) -> IrItem:
    """The owning item riding the argument channel."""
    item = nc[0]
    assert isinstance(item, IrItem)
    return item


def _gen_literal(_d: _Generator, n: IrLiteral, nc: Sequence[IrSelf]) -> str:
    """Emit a literal verbatim, repeated when quantified."""
    q = _item(nc).quantifier
    return n * _pick_count(q, _d.rng) if q != _UNIT else n


def _gen_charclass(_d: _Generator, n: IrCharClass, nc: Sequence[IrSelf]) -> str:
    """Emit sampled characters from a char class under its quantifier."""
    count = _pick_count(_item(nc).quantifier, _d.rng)
    return "".join(chr(n.sample(_d.rng)) for _ in range(count))


def _gen_ruleref(_d: _Generator, n: IrRuleRef, nc: Sequence[IrSelf]) -> str:
    """Expand a rule ref, recursing at ``max_depth - 1`` under its quantifier.

    At an exhausted budget the quantifier collapses to its lower bound — an
    optional ref rolls zero — and a required expansion descends the height
    measure through its target's own minimal arms.
    """
    q = _item(nc).quantifier
    count = q.lo if _d.max_depth <= 0 else _pick_count(q, _d.rng)
    child = _Generator(
        rng=_d.rng, rules=_d.rules, heights=_d.heights, max_depth=_d.max_depth - 1
    )
    return "".join(child.run(str(n)) for _ in range(count))


def _gen_group(_d: _Generator, n: IrAlternation, nc: Sequence[IrSelf]) -> str:
    """Expand an inline group, repeated under its quantifier."""
    q = _item(nc).quantifier
    count = q.lo if _d.max_depth <= 0 else _pick_count(q, _d.rng)
    return "".join(_d.alternation(n, "an inline group") for _ in range(count))


# Dispatched on the atom; the owning IrItem rides the argument channel so each
# body can read the quantifier, and the _Generator rides the dispatcher channel
# so each body can reach the rng/rules/depth. The raising default refuses any
# unregistered atom type (e.g. a stray post-canon IrNot) instead of the old
# silent "".
_GEN_ATOM: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_gen_literal)),
        IrAction(IrCharClass, IrLambda(_gen_charclass)),
        IrAction(IrRuleRef, IrLambda(_gen_ruleref)),
        IrAction(IrAlternation, IrLambda(_gen_group)),
    ),
    default=IrRaise(message="generate: no atom rule for {node_type!r}"),
)


_INF = float("inf")


class _Coster(IrNamedTuple[dict[str, float]]):
    """Rides :data:`_COST_ATOM`'s dispatcher channel carrying the heights."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    heights: dict[str, float]


def _cost_terminal(_d: _Coster, _n: IrSelf, _nc: Sequence[IrSelf]) -> float:
    """A literal or char class spends no rule expansion."""
    return 0.0


def _cost_ref(d: _Coster, n: IrRuleRef, _nc: Sequence[IrSelf]) -> float:
    """A ref costs its target's height.

    An UNDEFINED target costs nothing — deliberately: pricing it bottomless
    would refuse it as "loops forever", which is not the fact. Free, it is
    entered, and :meth:`_Generator.run` refuses with the missing rule's name.
    """
    return d.heights.get(str(n), 0.0)


def _cost_group(d: _Coster, n: IrAlternation, _nc: Sequence[IrSelf]) -> float:
    """A group costs its cheapest arm."""
    return _alt_cost(n, d.heights)


# Cost mirrors _GEN_ATOM's keys with the same raising default: a new atom type
# must say what expanding it spends — a closed ladder would silently guess.
_COST_ATOM: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_cost_terminal)),
        IrAction(IrCharClass, IrLambda(_cost_terminal)),
        IrAction(IrRuleRef, IrLambda(_cost_ref)),
        IrAction(IrAlternation, IrLambda(_cost_group)),
    ),
    default=IrRaise(message="generate: no cost rule for {node_type!r}"),
)


def _item_cost(item: IrItem, heights: dict[str, float]) -> float:
    """What expanding this item must spend; an optional item can spend nothing."""
    if item.quantifier.lo == 0:
        return 0.0
    return float(_COST_ATOM.eval(_Coster(heights=heights), item.atom, ()))


def _arm_cost(arm: Sequence[IrItem], heights: dict[str, float]) -> float:
    """An arm spends what its required items spend together."""
    return sum(_item_cost(item, heights) for item in arm)


def _alt_cost(body: IrAlternation, heights: dict[str, float]) -> float:
    """An alternation spends its cheapest arm's cost; arm-less is bottomless."""
    return min((_arm_cost(arm, heights) for arm in body), default=_INF)


def _rule_heights(rules: Rules) -> dict[str, float]:
    """The minimal ref-expansion height of every rule, by fixpoint.

    ``inf`` marks a rule that derives no finite string — every arm loops.
    """
    heights = dict.fromkeys(rules, _INF)
    changed = True
    while changed:
        changed = False
        for name, rule in rules.items():
            best = 1 + _alt_cost(rule.body, heights)
            if best < heights[name]:
                heights[name] = best
                changed = True
    return heights


class _Generator(IrNamedTuple[_random.Random, Rules, dict[str, float], int]):
    """Random-string generator state over a rules-by-name view.

    Carries the shared random source, the grammar's rules, their computed
    heights and the remaining ref-expansion budget; :meth:`run` expands a
    named rule. It rides the dispatcher channel of :data:`_GEN_ATOM` so each
    atom body can reach this state. ``_child_attrs`` is empty — none of the
    fields is an IR-node child.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rng: _random.Random
    rules: Rules
    heights: dict[str, float]
    max_depth: int

    def run(self, rule_name: str) -> str:
        """Expand the named rule to a random string.

        :param rule_name: The rule to expand.
        :returns: A random string in the rule's language.
        :raises UnsupportedConstructError: When the grammar defines no rule of
            that name — a dangling reference generates nothing, and saying so
            with ``""`` is indistinguishable from a grammar that generates it.
        """
        rule = self.rules.get(rule_name)
        if rule is None:
            raise UnsupportedConstructError(
                f"generate: rule {rule_name!r} is not defined — the grammar "
                f"defines {sorted(self.rules)}"
            )
        return self.alternation(rule.body, f"rule {rule_name!r}")

    def alternation(self, body: IrAlternation, where: str) -> str:
        """Pick a random arm of ``body`` and expand it.

        :param body: The alternation to expand.
        :param where: What is being expanded, named in a refusal.
        :returns: The chosen arm's expansion.
        :raises UnsupportedConstructError: When ``body`` has no arms at all
            (an alternation with ONE EMPTY arm derives ``""`` and still
            expands here; one with no arms derives nothing, which is not the
            same fact), or when every arm loops forever — a non-terminating
            arm is never chosen at ANY depth, so an all-looping alternation
            has nothing to offer.
        """
        if not body:
            raise UnsupportedConstructError(
                f"generate: {where} has no arms to expand — an alternation "
                "with no arms derives nothing, not the empty string"
            )
        costs = [_arm_cost(arm, self.heights) for arm in body]
        floor = min(costs)
        if floor == _INF:
            raise UnsupportedConstructError(
                f"generate: {where} cannot terminate — every arm loops forever"
            )
        cap = _INF if self.max_depth > 0 else floor
        arms = [a for a, cost in zip(body, costs) if cost <= cap and cost < _INF]
        return "".join(self.atom(it) for it in self.rng.choice(arms))

    def atom(self, item: IrItem) -> str:
        """Expand one item by dispatching on its atom, item riding the channel."""
        return str(_GEN_ATOM.eval(self, item.atom, (item,)))


def generate(
    rule_name: str,
    rules: Rules,
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a random string matching the named rule.

    :param rule_name: The rule to expand.
    :param rules: The grammar as a rule-name → :class:`IrRule` mapping.
    :param rng: Random source; a fresh one is created when omitted.
    :param max_depth: Ref-expansion budget, decremented on each recursion.
        While it lasts, arm choice is free among terminating arms; exhausted,
        it restricts to minimal-height arms and quantified refs collapse to
        their lower bound, so generation terminates by strict height descent.
    :returns: A random string in the rule's language.
    :raises UnsupportedConstructError: When ``rule_name`` names no rule, when
        a reference reaches one, when an alternation has no arms, or when a
        rule's every arm loops forever (it derives no finite string).
    """
    if rng is None:
        rng = _random.Random()
    heights = _rule_heights(rules)
    return _Generator(rng=rng, rules=rules, heights=heights, max_depth=max_depth).run(
        rule_name
    )
