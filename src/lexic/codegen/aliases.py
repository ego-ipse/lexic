"""Pattern-alias collection: walk specs once, emit unique pattern regexes.

A "pattern" is either an IrCharClass with a quantifier or a pure-pattern
IrGroup (no IrRuleRef descendants). Each unique regex produces one PatternAlias
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

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.naming import CHARCLASS_NAMES
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
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


def _suffix(q: Quantifier) -> str:
    """Render a Quantifier as its regex suffix."""
    return bounds_to_quantifier(q.min, q.max)


def _camel(s: str) -> str:
    """Convert snake_case to CamelCase for type alias names."""
    return "".join(p.capitalize() for p in s.split("_"))


def regex_for_charclass(cc: IrCharClass, q: Quantifier) -> str:
    """Build the anchored regex for an IrCharClass at the given Quantifier."""
    return f"^{_bracket(cc.pattern, cc.negated)}{_suffix(q)}$"


def _atom_regex_fragment(item: IrItem) -> str:
    """Build the inner (unanchored) regex fragment for any pattern atom."""
    atom = item.atom
    q = _suffix(item.quantifier)
    if isinstance(atom, IrLiteral):
        return re.escape(atom.value) + q
    if isinstance(atom, IrCharClass):
        return _bracket(atom.pattern, atom.negated) + q
    if isinstance(atom, IrGroup):
        return f"({_alt_regex_fragment(atom.body)}){q}"
    raise UnsupportedConstructError(
        f"Pattern fragment cannot include {type(atom).__name__}"
    )


def _seq_regex_fragment(seq: IrSequence) -> str:
    """Concatenate regex fragments for each item in the sequence."""
    return "".join(_atom_regex_fragment(it) for it in seq.items)


def _alt_regex_fragment(alt: IrAlternation) -> str:
    """Pipe-join regex fragments for the arms of the alternation."""
    return "|".join(_seq_regex_fragment(s) for s in alt.arms)


def regex_for_group(grp: IrGroup, q: Quantifier) -> str:
    """Build the anchored regex for a pure-pattern IrGroup at the given Quantifier."""
    return f"^({_alt_regex_fragment(grp.body)}){_suffix(q)}$"


def _name_for_charclass(cc: IrCharClass) -> str:
    """Return the Tier-2 CamelCase name for ``cc``, or empty string if no match.

    Looks up the bracket-only form (no quantifier suffix) in CHARCLASS_NAMES.
    Quantifier-driven disambiguation happens in the collector.
    """
    tier2 = CHARCLASS_NAMES.get(_bracket(cc.pattern, cc.negated))
    return _camel(tier2) if tier2 else ""


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

    def __init__(self) -> None:
        """Initialize with empty state."""
        self.aliases: dict[str, PatternAlias] = {}
        self._name_counts: Counter[str] = Counter()
        # Sentinel frame: never popped, keeps `[-1]` indexing safe at top level.
        self._ruleref_frames: list[bool] = [False]

    def visit_IrRuleRef(self, _: IrRuleRef) -> None:  # pylint: disable=invalid-name
        """Mark the current frame dirty so the enclosing group is non-pure."""
        self._ruleref_frames[-1] = True

    def visit_IrItem(self, node: IrItem) -> None:  # pylint: disable=invalid-name
        """Visit an IrItem; if it's a pattern atom, record its alias."""
        atom, q = node.atom, node.quantifier
        if isinstance(atom, IrGroup):
            self._visit_group_item(atom, q, node)
            return
        if isinstance(atom, IrCharClass):
            self._record(
                regex_for_charclass(atom, q),
                _name_for_charclass(atom) or "Pattern",
            )
        self.generic_visit(node)

    def _visit_group_item(self, atom: IrGroup, q: Quantifier, node: IrItem) -> None:
        """Push a ruleref frame, descend, then decide whether the group is pure-pattern."""
        self._ruleref_frames.append(False)
        self.generic_visit(node)
        group_had_ruleref = self._ruleref_frames.pop()
        if group_had_ruleref:
            self._ruleref_frames[-1] = True
        else:
            self._record(regex_for_group(atom, q), "Pattern")

    def _record(self, regex: str, base: str) -> None:
        """Record an alias for ``regex`` (idempotent on regex); name from ``base``."""
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
    """
    visitor = _PatternAliasVisitor()
    for spec in specs:
        for item in spec.items:
            visitor.visit(item)
    return list(visitor.aliases.values())
