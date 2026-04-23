"""seq_to_atoms: convert a GBNF Sequence into a list of IR Atoms.

Extracted from ir_builder.py so the sequence-to-atom logic and its
Group-conversion helpers can be tested and evolved independently.
"""

from __future__ import annotations

import re
from typing import cast

from lexic.grammars.gbnf.ast import (
    Alternation,
    CharClass,
    Group,
    Literal,
    RuleRef,
    Sequence,
)
from lexic.codegen.ast_utils import is_pure_literal_seq, single_ruleref_of, strip_ws
from lexic.codegen.helpers import HelperRuleRegistry
from lexic.codegen.naming import assign_field_names
from lexic.ir import (
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.names import to_pascal
from lexic.utils.quantifiers import quantifier_to_bounds


def _to_regex(group: Group) -> str:
    """Convert a GBNF Group to a regex pattern string for Lark terminals."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                parts.append(re.escape(it.atom.value) + q)
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_regex(it.atom) + q)
            # RuleRef inside a group cannot be inlined — skip
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _to_gbnf(group: Group) -> str:
    """Convert a GBNF Group back to GBNF syntax for GBNFEmitter."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                parts.append(f'"{it.atom.value}"{q}')
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_gbnf(it.atom) + q)
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _build_inline_regex(group: Group, min_: int, max_: int | None) -> InlineRegexAtom:
    """Build an InlineRegexAtom from a pure-literal or mixed GBNF group."""
    return InlineRegexAtom(
        regex=_to_regex(group),
        gbnf=_to_gbnf(group),
        min=min_,
        max=max_,
    )


def seq_to_atoms(
    seq: Sequence,
    parent_class_name: str,
    helpers: HelperRuleRegistry,
    name_map: dict[str, str],
    parent_of: dict[str, str],
) -> list[Atom]:
    """Convert a single grammar sequence into a list of IR atoms.

    When a quantified group is encountered, a helper RuleSpec is created and
    registered in helpers, and a RuleRefAtom pointing to it is returned.
    """
    atoms: list[Atom] = []

    for item in seq.items:
        if isinstance(item.atom, Literal):
            if item.quantifier is not None:
                # Quantified literal: emit as QuantifiedLiteralAtom so the optional/
                # repeated nature is preserved in the IR and downstream emitters.
                min_, max_ = quantifier_to_bounds(item.quantifier)
                atoms.append(
                    QuantifiedLiteralAtom(value=item.atom.value, min=min_, max=max_)
                )
            else:
                atoms.append(LiteralAtom(value=item.atom.value))

        elif isinstance(item.atom, CharClass):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(CharClassAtom(pattern=item.atom.pattern, min=min_, max=max_))

        elif isinstance(item.atom, RuleRef):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(RuleRefAtom(rule_name=item.atom.name, min=min_, max=max_))

        elif isinstance(item.atom, Group):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            inner_arms = [
                a for a in (strip_ws(s) for s in item.atom.alt.seqs) if len(a.items) > 0
            ]

            # Inline literal alternation → InlineRegexAtom
            if all(is_pure_literal_seq(arm) for arm in inner_arms):
                atoms.append(_build_inline_regex(item.atom, min_, max_))
                continue

            # Inline union of named rules (no quantifier) → InlineAlternationAtom
            if (
                item.quantifier is None
                and len(inner_arms) > 1
                and all(single_ruleref_of(a) is not None for a in inner_arms)
            ):
                arm_names: list[str] = [
                    cast(str, single_ruleref_of(a)) for a in inner_arms
                ]
                atoms.append(InlineAlternationAtom(arm_rule_names=arm_names))
                continue

            # Unquantified single-arm group → inline its contents
            if item.quantifier is None and len(inner_arms) == 1:
                inner_atoms = seq_to_atoms(
                    inner_arms[0], parent_class_name, helpers, name_map, parent_of
                )
                atoms.extend(inner_atoms)
                continue

            # Quantified group → create helper RuleSpec
            helper_rule_name = helpers.reserve(f"{parent_class_name.lower()}-item")

            helper_class_name = to_pascal(helper_rule_name)
            helper_atoms = seq_to_atoms(
                inner_arms[0] if inner_arms else seq,
                helper_class_name,
                helpers,
                name_map,
                parent_of,
            )
            helper_fm = assign_field_names(helper_atoms)
            helper_spec = RuleSpec(
                rule_name=helper_rule_name,
                class_name=helper_class_name,
                parent_class_name="GrammarModel",
                kind="sequence",
                items=helper_atoms,
                field_map=helper_fm,
            )
            helpers.register(helper_spec)
            atoms.append(RuleRefAtom(rule_name=helper_rule_name, min=min_, max=max_))

    return atoms


def value_str_to_atoms(alt: Alternation) -> list[Atom]:
    """Build the atom list for a value_str rule (no rule references, only literals/chars/groups)."""
    items: list[Atom] = []
    for seq in alt.seqs:
        for it in seq.items:
            if isinstance(it.atom, CharClass):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(CharClassAtom(it.atom.pattern, min_, max_))
            elif isinstance(it.atom, Literal):
                if it.quantifier is not None:
                    min_, max_ = quantifier_to_bounds(it.quantifier)
                    items.append(
                        QuantifiedLiteralAtom(value=it.atom.value, min=min_, max=max_)
                    )
                else:
                    items.append(LiteralAtom(it.atom.value))
            elif isinstance(it.atom, Group):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(_build_inline_regex(it.atom, min_, max_))
    return items
