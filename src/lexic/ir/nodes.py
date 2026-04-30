"""IR AST node dataclasses — canonical, frozen, hashable.

The IR AST is the lingua franca for transpilation. Every flavour produces
this AST from its source text. Leaves carry canonical values (escapes
decoded, POSIX-style char classes); quantifiers travel on `IrItem`,
not on leaves.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Quantifier:
    """Repetition bounds. `max=None` means unbounded."""

    min: int = 1
    max: int | None = 1


# ── Leaves ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral:
    """Literal string. `value` is canonical Python (escapes decoded)."""

    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass:
    """Character class. `pattern` is the canonical POSIX-style interior
    (e.g. 'a-z0-9'). `negated` is True if the source had `[^…]`.
    """

    pattern: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class IrRuleRef:
    """Reference to another rule by name."""

    name: str


# ── Structure (forward-declared for IrItem.atom union) ───────────────


@dataclass(frozen=True, slots=True)
class IrSequence:
    """Concatenation of items."""

    items: tuple["IrItem", ...] = ()


@dataclass(frozen=True, slots=True)
class IrAlternation:
    """Choice between sequences. Always >= 1 arm; single-arm is bare seq."""

    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True)
class IrGroup:
    """Parenthesised group. Body is always an IrAlternation."""

    body: IrAlternation


# ── Wrapper ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrItem:
    """An atom (leaf or group) with a quantifier."""

    atom: "IrLiteral | IrCharClass | IrRuleRef | IrGroup"
    quantifier: Quantifier = field(default_factory=Quantifier)


# ── Top-level ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrRule:
    """A named rule. Body is always an IrAlternation, even single-arm."""

    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrAst:
    """Full grammar: rules + start-rule name."""

    rules: tuple[IrRule, ...] = ()
    start: str = ""
