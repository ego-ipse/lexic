"""Pattern-alias collection: walk specs once, emit unique pattern regexes.

A "pattern" is either an IrCharClass with a quantifier or a pure-pattern
IrAlternation. Each unique regex produces one PatternAlias
that the emitter renders as a module-level type alias.

Naming cascade:
  - Tier 2: bracket-only lookup in CHARCLASS_NAMES (e.g. ``[0-9]`` → ``Digit``).
  - Tier 3: positional fallback (``Pattern``).

Different regexes that resolve to the same base name are disambiguated by a
numeric suffix on subsequent occurrences (``Digit``, ``Digit2``). Alias names
are CamelCased because they appear as Python type identifiers.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import Field, IrLambda, IrNone, IrSelf
from lexic.ir.mapping import IrTypeMap
from lexic.ir.naming import CHARCLASS_NAMES
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec
from lexic.ir.walk import IrVisitor
from lexic.utils.quantifiers import bounds_to_quantifier


@dataclass(frozen=True)
class PatternAlias:
    """A CamelCase Python identifier paired with its anchored regex.

    Emitted by the model emitter as a module-level type alias of the form
    ``Name = Annotated[str, StringConstraints(pattern=regex)]``.
    """

    name: str
    regex: str


def _bracket(pattern: str, negated: bool) -> str:
    """Wrap a charclass pattern in brackets, with optional negation."""
    return f"[{'^' if negated else ''}{pattern}]"


def _suffix(q: IrQuantifier) -> str:
    """Render a IrQuantifier as its regex suffix."""
    return bounds_to_quantifier(q.lo, q.hi)


def _camel(s: str) -> str:
    """Convert snake_case to CamelCase for type alias names."""
    return "".join(p.capitalize() for p in s.split("_"))


def regex_for_charclass(
    cc: IrCharClass, q: IrQuantifier, *, negated: bool = False
) -> str:
    """Build the anchored regex for an IrCharClass at the given IrQuantifier.

    :param cc: The character class node.
    :param q: The quantifier to apply.
    :param negated: Whether to emit ``[^...]`` instead of ``[...]``.
    :returns: Anchored regex string.
    """
    return f"^{_bracket(cc.pattern(), negated)}{_suffix(q)}$"


def _atom_regex_fragment(item: IrItem) -> str:
    """Build the inner (unanchored) regex fragment for any pattern atom."""
    atom = item.atom
    q = _suffix(item.quantifier)
    if isinstance(atom, IrLiteral):
        return re.escape(atom) + q
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            return _bracket(inner.pattern(), True) + q
    if isinstance(atom, IrCharClass):
        return _bracket(atom.pattern(), False) + q
    if isinstance(atom, IrAlternation):
        return f"({_alt_regex_fragment(atom)}){q}"
    raise UnsupportedConstructError(
        f"Pattern fragment cannot include {type(atom).__name__}"
    )


def _seq_regex_fragment(seq: IrSequence) -> str:
    """Concatenate regex fragments for each item in the sequence."""
    return "".join(_atom_regex_fragment(it) for it in seq)


def _alt_regex_fragment(alt: IrAlternation) -> str:
    """Pipe-join regex fragments for the arms of the alternation."""
    return "|".join(_seq_regex_fragment(s) for s in alt)


def regex_for_group(grp: IrAlternation, q: IrQuantifier) -> str:
    """Build the anchored regex for a pure-pattern IrGroup at the given IrQuantifier."""
    return f"^({_alt_regex_fragment(grp)}){_suffix(q)}$"


def _name_for_charclass(cc: IrCharClass, *, negated: bool = False) -> str:
    """Return the Tier-2 CamelCase name for ``cc``, or empty string if no match.

    Looks up the bracket-only form (no quantifier suffix) in CHARCLASS_NAMES.
    IrQuantifier-driven disambiguation happens in the collector.

    :param cc: The character class node.
    :param negated: Whether this charclass is negated (wrapped in IrNot).
    :returns: CamelCase tier-2 name, or empty string if no Tier-2 match.
    """
    tier2 = CHARCLASS_NAMES.get(_bracket(cc.pattern(), negated))
    return _camel(tier2) if tier2 else ""


# ── Handler functions (defined before the class to resolve forward refs) ──────


def _mark_ruleref(d: _PatternAliasVisitor, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Mark the current frame dirty so the enclosing group is non-pure.

    :param d: The visitor driving the walk.
    :param _n: The dispatched node (dispatch guarantees IrRuleRef; unused).
    :param _nc: Pre-dispatched children (unused).
    :returns: :data:`IrNone`.
    """
    d.ruleref_frames[-1] = True
    return IrNone


def _visit_item(d: _PatternAliasVisitor, n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Handle IrItem dispatch — group frames, pattern recording, then recurse.

    For IrGroup atoms: push a ruleref frame, recurse, then either propagate
    the dirty flag up or record the group as a pure-pattern alias.
    For IrCharClass and negated IrCharClass atoms: record the alias, then
    recurse into the atom's children.

    :param d: The visitor driving the walk.
    :param n: The dispatched node (dispatch guarantees IrItem).
    :param _nc: Pre-dispatched children (unused — we control recursion here).
    :returns: :data:`IrNone`.
    :raises UnsupportedConstructError: If ``n`` is not an IrItem.
    """
    if not isinstance(n, IrItem):
        raise UnsupportedConstructError(
            f"_visit_item: expected IrItem, got {type(n).__name__}"
        )
    atom, q = n.atom, n.quantifier
    if isinstance(atom, IrAlternation):
        d.ruleref_frames.append(False)
        d.eval(d, atom, ())
        group_had_ruleref = d.ruleref_frames.pop()
        if group_had_ruleref:
            d.ruleref_frames[-1] = True
        else:
            d.record(regex_for_group(atom, q), "Pattern")
        return IrNone
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            d.record(
                regex_for_charclass(inner, q, negated=True),
                _name_for_charclass(inner, negated=True) or "Pattern",
            )
    elif isinstance(atom, IrCharClass):
        d.record(
            regex_for_charclass(atom, q),
            _name_for_charclass(atom) or "Pattern",
        )
    d.eval(d, atom, ())
    return IrNone


# ── Stateful visitor ──────────────────────────────────────────────────────────


class _PatternAliasVisitor(IrVisitor):
    """Single-pass collector that emits a PatternAlias per pure-pattern subtree.

    A "pure-pattern" subtree contains no IrRuleRef descendants. We detect this
    inline using a stack of frames — one per enclosing IrGroup — instead of a
    separate scan. Visiting an IrRuleRef sets the current frame; leaving an
    IrGroup pops its frame and either records the group as an alias (clean
    frame) or propagates the flag up so ancestor groups see it (dirty frame).

    Aliases dedupe on regex. Different regexes that resolve to the same base
    name (a Tier-2 hit applies only to the bracket-only form, so ``[0-9]`` and
    ``[0-9]+`` collide on ``Digit``) get a numeric suffix on later occurrences.
    """

    aliases: dict[str, PatternAlias] = Field(default_factory=dict)
    _name_counts: Counter[str] = Field(default_factory=Counter)
    ruleref_frames: list[bool] = Field(default=[False])
    actions: IrTypeMap = IrTypeMap(
        IrAction(IrRuleRef, IrLambda(_mark_ruleref)),
        IrAction(IrItem, IrLambda(_visit_item)),
    )

    def record(self, regex: str, base: str) -> None:
        """Record an alias for ``regex`` (idempotent on regex); name from ``base``.

        :param regex: The anchored regex string.
        :param base: CamelCase base name (Tier-2 or ``"Pattern"``).
        """
        if regex in self.aliases:
            return
        self._name_counts[base] += 1
        n = self._name_counts[base]
        name = base if n == 1 else f"{base}{n}"
        self.aliases[regex] = PatternAlias(name=name, regex=regex)


def collect_aliases(specs: list[RuleSpec]) -> list[PatternAlias]:
    """Return one PatternAlias per unique pattern regex across all specs.

    Order is insertion order — first appearance wins for naming. Different
    regexes that resolve to the same Tier-2 base name get a numeric suffix on
    later occurrences (``Digit``, ``Digit2``).

    :param specs: All rule specs to scan.
    :returns: Deduplicated list of pattern aliases in first-appearance order.
    """
    visitor = _PatternAliasVisitor()
    for spec in specs:
        for item in spec.items:
            visitor.apply(item)
    return list(visitor.aliases.values())


def collect_aliases_grammar(grammar: IrAst) -> list[PatternAlias]:
    """Return one PatternAlias per unique pattern regex across a codegen grammar.

    The IR-native counterpart of :func:`collect_aliases`: it walks every item of
    every rule arm directly, so the same :class:`_PatternAliasVisitor` records
    each pure-pattern subtree. Naming and dedup rules are identical; order is
    rule order, then arm order, then item order.

    :param grammar: The (post-pass) codegen grammar to scan.
    :returns: Deduplicated list of pattern aliases in first-appearance order.
    """
    visitor = _PatternAliasVisitor()
    for rule in grammar.rules:
        for arm in rule.body:
            for item in arm:
                visitor.apply(item)
    return list(visitor.aliases.values())
