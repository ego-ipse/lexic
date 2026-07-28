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
"""

from __future__ import annotations

import random as _random
from typing import ClassVar, Sequence

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
    """Expand a rule ref, recursing at ``max_depth - 1`` under its quantifier."""
    count = _pick_count(_item(nc).quantifier, _d.rng)
    child = _Generator(rng=_d.rng, rules=_d.rules, max_depth=_d.max_depth - 1)
    return "".join(child.run(str(n)) for _ in range(count))


def _gen_group(_d: _Generator, n: IrAlternation, nc: Sequence[IrSelf]) -> str:
    """Expand an inline group, repeated under its quantifier."""
    count = _pick_count(_item(nc).quantifier, _d.rng)
    return "".join(_d.alternation(n) for _ in range(count))


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


class _Generator(IrNamedTuple[_random.Random, Rules, int]):
    """Random-string generator state over a rules-by-name view.

    Carries the shared random source, the grammar's rules and the remaining
    ref-expansion budget; :meth:`run` expands a named rule. It rides the
    dispatcher channel of :data:`_GEN_ATOM` so each atom body can reach this
    state. ``_child_attrs`` is empty — none of the fields is an IR-node child.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rng: _random.Random
    rules: Rules
    max_depth: int

    def run(self, rule_name: str) -> str:
        """Expand the named rule to a random string (``""`` for an unknown rule)."""
        rule = self.rules.get(rule_name)
        if rule is None:
            return ""
        return self.alternation(rule.body)

    def alternation(self, body: IrAlternation) -> str:
        """Pick a random arm of ``body`` and expand it."""
        if not body:
            return ""
        return "".join(self.atom(it) for it in self.rng.choice(body))

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
    :returns: A random string in the rule's language (``""`` for an unknown rule).
    """
    if rng is None:
        rng = _random.Random()
    return _Generator(rng=rng, rules=rules, max_depth=max_depth).run(rule_name)
