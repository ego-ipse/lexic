"""IR dataclasses for the GBNF → Pydantic pipeline.

RuleSpec is the canonical representation of a GBNF rule.
All emitters (ModelEmitter, GBNFEmitter, LarkBuilder) consume RuleSpec.
The GBNF AST (codegen/ast.py) is only consumed by IRBuilder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LiteralAtom:
    """A quoted string literal in the grammar, e.g. '=' or '('."""

    value: str


@dataclass
class CharClassAtom:
    """A character class with quantifier bounds, e.g. [a-z]{1,1} or [a-z0-9_]{0,}.

    pattern: full bracket expression as it appears in GBNF, e.g. '[a-z]'
    min: minimum occurrences (0 = *, 1 = required or +)
    max: maximum occurrences; None = unbounded
    """

    pattern: str
    min: int
    max: int | None


@dataclass
class RuleRefAtom:
    """A reference to another rule, with quantifier bounds.

    min=1, max=1  → required singular field
    min=0, max=1  → Optional[X] field
    min=1, max=None → List[X] field (one or more)
    min=0, max=None → List[X] field (zero or more)
    """

    rule_name: str
    min: int
    max: int | None


@dataclass
class AlternationAtom:
    """Names of the alternative arms of an alternation rule.

    Used in the items list of a RuleSpec with kind='alternation'.
    arm_rule_names: GBNF rule names (not class names) of the arms.
    """

    arm_rule_names: list[str]


Atom = LiteralAtom | CharClassAtom | RuleRefAtom | AlternationAtom


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
    class_name: str  # PascalCase, e.g. "Ident"
    parent_class_name: str  # e.g. "Term" or "GrammarModel"
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
