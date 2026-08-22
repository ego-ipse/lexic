"""Static safety proofs for a region's separator ownership.

A repeated tail leading with ``,`` does not make every visible comma a tail:
the preceding item may itself accept commas at the same bracket depth. A cut
is sound only when that one competing owner cannot emit the separator. Nested
delimited rules are deliberately opaque to this proof because the structural
scan attributes their punctuation to the nested region, not to the owner.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNot,
    IrRule,
    IrRuleRef,
)
from lexic.parsing.parallel.discovery.interiors import interior_rules
from lexic.parsing.parallel.discovery.regions import pair_rules
from lexic.parsing.parallel.discovery.shapes import UNIT
from lexic.parsing.parallel.roles import roles
from lexic.parsing.pda.core.charsets import CharSet


def _protected(grammar: IrAst, region_scan: bool) -> frozenset[str]:
    """Rules hidden or depth-owned by the scan the caller actually uses."""
    pairs = pair_rules(grammar)
    if region_scan:
        paired = {rule for _close, rule in pairs.values()}
        return frozenset(paired) | interior_rules(grammar)
    tracked = set(roles(grammar).pairs)
    return frozenset(
        rule for opener, (closer, rule) in pairs.items() if (opener, closer) in tracked
    )


def _item_emits(
    item: IrItem,
    char: str,
    rules: dict[str, IrRule],
    protected: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one item can emit ``char`` outside a nested delimiter."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        emits = char in str(atom)
    elif isinstance(atom, IrCharClass):
        emits = CharSet.from_charclass(atom).has(char)
    elif isinstance(atom, IrNot):
        inner = atom[0]
        charset = (
            CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
        )
        emits = charset.has(char)
    elif isinstance(atom, IrAlphabet):
        emits = True
    elif isinstance(atom, IrAlternation):
        emits = any(
            _item_emits(inner, char, rules, protected, path)
            for arm in atom
            for inner in arm
        )
    elif isinstance(atom, IrRuleRef):
        name = str(atom)
        if name in protected:
            emits = False
        else:
            target = rules.get(name)
            emits = target is None or (
                name not in path
                and _rule_emits(target, char, rules, protected, path | {name})
            )
    else:
        emits = True
    return emits


def _rule_emits(
    rule: IrRule,
    char: str,
    rules: dict[str, IrRule],
    protected: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a rule has any flat derivation that emits ``char``."""
    return any(
        _item_emits(item, char, rules, protected, path)
        for arm in rule.body
        for item in arm
    )


_OWNER_PROOFS: dict[tuple[int, str, str, bool], tuple[IrAst, bool]] = {}
"""Per-analysis-view ownership proofs, with a strong identity pin."""


def owner_excludes(
    grammar: IrAst, owner: str, separator: str, *, region_scan: bool = False
) -> bool:
    """Prove that ``owner`` cannot consume ``separator`` at this region depth.

    Failure to prove exclusion is an ordinary sequential decline. The proof is
    intentionally per owner: pooling every rule reachable anywhere would
    reject JSON because a nested object quite properly contains commas.
    """
    key = (id(grammar), owner, separator, region_scan)
    entry = _OWNER_PROOFS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        protected = _protected(grammar, region_scan)
        excludes = target is not None and (
            owner in protected
            or not _rule_emits(target, separator, rules, protected, frozenset({owner}))
        )
        entry = (grammar, excludes)
        _OWNER_PROOFS[key] = entry
    return entry[1]


def _ends_once(
    rule: IrRule,
    char: str,
    rules: dict[str, IrRule],
    protected: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether every arm emits ``char`` once, as its final flat edge."""
    for arm in rule.body:
        items = tuple(arm)
        if not items or any(
            _item_emits(item, char, rules, protected, path) for item in items[:-1]
        ):
            return False
        last = items[-1]
        if last.quantifier != UNIT:
            return False
        atom = last.atom
        if isinstance(atom, IrLiteral):
            valid = str(atom) == char
        elif isinstance(atom, IrRuleRef):
            name = str(atom)
            target = rules.get(name)
            valid = (
                name not in path
                and target is not None
                and _ends_once(target, char, rules, protected, path | {name})
            )
        else:
            valid = False
        if not valid:
            return False
    return True


_TERMINATOR_PROOFS: dict[tuple[int, str, str], tuple[IrAst, bool]] = {}
"""Per-analysis-view proof that a unit owns no internal terminator marks."""


def terminates_once(grammar: IrAst, owner: str, terminator: str) -> bool:
    """Prove every flat ``terminator`` in ``owner`` is its final edge."""
    key = (id(grammar), owner, terminator)
    entry = _TERMINATOR_PROOFS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        protected = _protected(grammar, False)
        proven = target is not None and _ends_once(
            target, terminator, rules, protected, frozenset({owner})
        )
        entry = (grammar, proven)
        _TERMINATOR_PROOFS[key] = entry
    return entry[1]
