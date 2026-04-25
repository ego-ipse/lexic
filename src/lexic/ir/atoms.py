"""IR atom dataclasses for the GBNF → Pydantic pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class Atom(Protocol):
    """Marker protocol for IR atoms.

    Concrete atoms are frozen dataclasses. Atoms with bounded repetition
    expose `min: int` and `max: int | None`. The IR is open: flavours may
    define their own atom dataclasses next to their adapter — they qualify
    as `Atom` structurally.
    """


@dataclass(frozen=True)
class LiteralAtom:
    """A quoted string literal in the grammar, e.g. '=' or '('."""

    value: str


@dataclass(frozen=True)
class CharClassAtom:
    """A character class with quantifier bounds, e.g. [a-z]{1,1} or [a-z0-9_]{0,}.

    pattern: full bracket expression as it appears in GBNF, e.g. '[a-z]'
    min: minimum occurrences (0 = *, 1 = required or +)
    max: maximum occurrences; None = unbounded
    """

    pattern: str
    min: int
    max: int | None


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class AlternationAtom:
    """Names of the alternative arms of an alternation rule.

    Used in the items list of a RuleSpec with kind='alternation'.
    arm_rule_names: GBNF rule names (not class names) of the arms.
    """

    arm_rule_names: list[str]


@dataclass(frozen=True)
class QuantifiedLiteralAtom:
    """A quoted literal with a quantifier — must be a Pydantic field.

    e.g. "-"? becomes QuantifiedLiteralAtom(value="-", min=0, max=1).
    Replaces the CharClassAtom('"-"', 0, 1) kludge.
    """

    value: str
    min: int
    max: int | None


@dataclass(frozen=True)
class InlineRegexAtom:
    """An inlined group compiled to both regex and GBNF forms at IR build time.

    regex: ready for Lark /regex/ terminal.
    gbnf:  ready for GBNFEmitter, e.g. ("true"|"false"|"null").
    Replaces CharClassAtom('("true"|...)', ...) and the _normalize hack.
    """

    regex: str
    gbnf: str
    min: int
    max: int | None


@dataclass(frozen=True)
class InlineAlternationAtom:
    """Inline alternation inside a sequence, e.g. (pawn | nonpawn | castle).

    Only valid inside kind='sequence' RuleSpecs. Always in field_map.
    No quantifier — quantified inline alternations become helper rules.
    Replaces the AlternationAtom dual-contract problem.
    """

    arm_rule_names: list[str]
