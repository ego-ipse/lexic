"""IR atom dataclasses for the GBNF → Pydantic pipeline."""

from __future__ import annotations

from dataclasses import dataclass


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
