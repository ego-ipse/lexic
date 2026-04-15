"""GBNF abstract syntax tree nodes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Literal:
    """A quoted string literal, e.g. "+"."""
    value: str


@dataclass
class CharClass:
    """A character class, e.g. [a-z]."""
    pattern: str


@dataclass
class RuleRef:
    """A reference to another rule by name."""
    name: str


@dataclass
class Group:
    """A parenthesised alternation."""
    alt: Alternation


@dataclass
class Item:
    """An atom with an optional quantifier (?, *, +)."""
    atom: Literal | CharClass | RuleRef | Group
    quantifier: str | None = None


@dataclass
class Sequence:
    """An ordered list of items (one arm of an alternation)."""
    items: list[Item] = field(default_factory=list)


@dataclass
class Alternation:
    """A set of alternative sequences separated by |."""
    seqs: list[Sequence] = field(default_factory=list)


@dataclass
class Rule:
    """A named GBNF rule: name ::= body."""
    name: str
    body: Alternation
