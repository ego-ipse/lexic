"""RuleSpec — canonical representation of one GBNF rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lexic.ir.atoms import Atom


@dataclass
class RuleSpec:
    """Complete specification of one GBNF rule.

    All downstream emitters (ModelEmitter, GBNFEmitter, LarkBuilder) consume
    this instead of the raw GBNF AST.

    field_map: maps Pydantic field name → index in items list.
      - LiteralAtom items are NEVER in field_map (they are structural).
      - AlternationAtom items are NEVER in field_map (abstract class has no fields).
      - CharClassAtom and RuleRefAtom items each have exactly one field_map entry.

    kind='value_str': single `value: str` field; items holds atoms for GBNFEmitter only.
    kind='alternation': abstract class; items=[AlternationAtom(...)]; field_map={}.
    kind='sequence': concrete class; items lists atoms in grammar order; field_map populated.
    """

    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)
