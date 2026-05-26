"""RuleSpec — canonical representation of one grammar rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lexic.ir.nodes import IrAlternation, IrItem, IrRule, IrSequence


@dataclass
class RuleSpec:
    """Complete specification of one grammar rule.

    All downstream emitters (ModelEmitter, GBNFEmitter, LarkBuilder) consume
    this instead of the raw GBNF AST.

    field_map: maps Pydantic field name → index in items list.
      - Structural IrLiteral items (quantifier (1,1)) are NEVER in field_map.
      - Alternation-kind items have field_map={}.
      - IrCharClass and IrRuleRef items each have exactly one field_map entry.

    kind='value_str': single `value: str` field; items holds atoms for emitters only.
    kind='alternation': abstract class; items=[IrItem(IrRuleRef(arm))...]; field_map={}.
    kind='sequence': concrete class; items lists IrItems in grammar order; field_map populated.

    Multi-arm value_str: items=[IrAlternation(...)]; emitters dispatch on isinstance.
    """

    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[IrItem | IrAlternation] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)

    def to_ir_rule(self) -> IrRule:
        """Reconstitute this spec as an IrRule.

        For sequence / value_str kinds, wraps ``items`` in a single
        IrAlternation arm. If ``items`` already contains a top-level
        IrAlternation (multi-arm value_str), it's used as the body
        directly.

        :returns: An IrRule whose body is an IrAlternation.
        """
        if len(self.items) == 1 and isinstance(self.items[0], IrAlternation):
            body = self.items[0]
        else:
            items_tuple = tuple(it for it in self.items if isinstance(it, IrItem))
            body = IrAlternation(arms=(IrSequence(items=items_tuple),))
        return IrRule(name=self.rule_name, body=body)
