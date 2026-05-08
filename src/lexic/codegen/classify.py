"""Classifier: determine a GBNF rule's IR kind.

Given a Rule from the GBNF AST, classify() returns one of four
Classification variants, each carrying exactly the payload its
downstream handler needs. Classify-internal predicates live as module
helpers (underscore-prefixed); shared AST helpers are imported from
codegen.ast_utils.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.codegen.ast_utils import (
    is_pure_literal_seq,
    is_ws_item,
    strip_ws,
    unwrap_group_alt,
)
from lexic.grammars.gbnf.ast import (
    Alternation,
    Group,
    Item,
    Rule,
    RuleRef,
    Sequence,
)


@dataclass(frozen=True)
class ValueStr:
    alt: Alternation


@dataclass(frozen=True)
class PureLiteralAlt:
    alt: Alternation


@dataclass(frozen=True)
class NamedAlt:
    arms: list[Sequence]


@dataclass(frozen=True)
class SequenceKind:
    body: Sequence


Classification = ValueStr | PureLiteralAlt | NamedAlt | SequenceKind


def _has_any_ruleref(items: list[Item]) -> bool:
    for it in items:
        if is_ws_item(it):
            continue
        if isinstance(it.atom, RuleRef):
            return True
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if _has_any_ruleref(seq.items):
                    return True
    return False


def _has_nontrivial_group(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if any(isinstance(i.atom, Group) for i in seq.items):
                    return True
    return False


def _has_group_with_alt(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group) and len(it.atom.alt.seqs) > 1:
            return True
    return False


def _is_structurally_complex(alt: Alternation) -> bool:
    for seq in alt.seqs:
        stripped = strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_group(inner_seq.items):
                        return True
    all_no_refs = not any(_has_any_ruleref(strip_ws(seq).items) for seq in alt.seqs)
    has_group_alt = any(_has_group_with_alt(strip_ws(seq).items) for seq in alt.seqs)
    return all_no_refs and has_group_alt


class Classifier:
    def classify(self, rule: Rule) -> Classification:
        if _is_structurally_complex(rule.body):
            return ValueStr(alt=rule.body)
        alt = unwrap_group_alt(rule.body)
        paired = [
            (seq, strip_ws(seq)) for seq in alt.seqs if len(strip_ws(seq).items) > 0
        ]
        if not paired:
            return ValueStr(alt=alt)
        full_arms = [full for full, _ in paired]
        arms = [stripped for _, stripped in paired]

        if len(arms) > 1 and all(is_pure_literal_seq(a) for a in arms):
            return PureLiteralAlt(alt=alt)
        if (
            len(arms) == 1
            and len(arms[0].items) == 1
            and isinstance(arms[0].items[0].atom, Group)
            and arms[0].items[0].quantifier is None
            and all(
                is_pure_literal_seq(strip_ws(s)) for s in arms[0].items[0].atom.alt.seqs
            )
        ):
            return PureLiteralAlt(alt=alt)
        if len(arms) == 1:
            full_seqs = alt.seqs
            has_any_rule_ref = any(
                any(isinstance(it.atom, RuleRef) for it in s.items) for s in full_seqs
            )
            if not has_any_rule_ref and is_pure_literal_seq(arms[0]):
                return ValueStr(alt=alt)
            return SequenceKind(body=full_arms[0])
        assert len(arms) > 1, "single-arm case handled above"
        return NamedAlt(arms=arms)
