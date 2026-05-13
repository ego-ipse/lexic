"""FlavourEmitter ABC — generic emit algorithm + default canonical-atom handlers.

Concrete flavour subclasses declare:
    - syntax constants (rule_separator, quote_char, alt_separator, ...)
    - the ClassVar[frozenset[str]] `supports` (set of capability names)
    - optional overrides: encode (escapes), render_charclass, render_inline_regex,
      format_quantifier, wrap_group, quote.

Atom handlers default to canonical implementations parameterised by the
decorators above; subclasses can pass extended handler tables in __init__.
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier

if TYPE_CHECKING:
    from lexic.ir.escapes import EscapeCodec


class FlavourEmitter(ABC):
    """Generic emit algorithm + default canonical-atom handlers."""

    # Syntax constants — overridable as class attributes.
    rule_separator: str = "::="
    rule_terminator: str = ""
    alt_separator: str = " | "
    quote_char: str = '"'
    group_open: str = "("
    group_close: str = ")"
    empty_body: str = '""'

    supports: ClassVar[frozenset[str]]
    """The set of atom types this emitter supports; used for testing."""

    def __init__(self, escapes: EscapeCodec) -> None:
        """Initialise with an escape codec and optional atom handlers."""
        self._escapes = escapes

    # ── Decorators (overridable per flavour) ──────────────────────────

    def quote(self, v: str) -> str:
        """Quote a literal value, escaping as needed."""
        return f"{self.quote_char}{self.encode(v)}{self.quote_char}"

    def wrap_group(self, body: str) -> str:
        """Wrap the body with group delimiters."""
        return f"{self.group_open}{body}{self.group_close}"

    def format_quantifier(self, lo: int, hi: int | None) -> str:
        """Format the quantifier for the given bounds."""
        return bounds_to_quantifier(lo, hi)

    def place_quantifier(self, atom_str: str, q_str: str) -> str:
        """Combine atom rendering with quantifier. Default suffix."""
        return f"{atom_str}{q_str}"

    def render_charclass(self, canonical_pattern: str, negated: bool = False) -> str:
        """Render a canonical char class interior. Subclasses may use negated."""
        return canonical_pattern

    def render_inline_regex(self, canonical: str) -> str:
        """Render a canonical inline regex."""
        return canonical

    def encode(self, v: str) -> str:
        """Encode a string value using the escape codec."""
        return self._escapes.encode(v)

    # ── Generic algorithm ────────────────────────────────────────────

    def emit(self, specs: list[RuleSpec]) -> str:
        """Emit the given rule specs as a string."""
        lines = [self.emit_rule(s) for s in specs]
        return "\n".join(lines) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        """Emit a single rule spec as a string."""
        body = self._emit_body(spec)
        return f"{spec.rule_name} {self.rule_separator} {body}{self.rule_terminator}"

    def _emit_body(self, spec: RuleSpec) -> str:
        if not spec.items:
            return self.empty_body
        if spec.kind == "alternation":
            return self.alt_separator.join(
                self._emit_item(it) for it in spec.items if isinstance(it, IrItem)
            )
        first = spec.items[0]
        if isinstance(first, IrAlternation):
            return self._emit_alternation(first)
        parts = [self._emit_item(it) for it in spec.items if isinstance(it, IrItem)]
        return " ".join(p for p in parts if p) or self.empty_body

    # ── IR-AST emit chain ────────────────────────────────────────────

    def emit_ast(self, ast: IrAst) -> str:
        """Emit all rules in an IrAst as a grammar string."""
        lines = [self.emit_rule_from_ast(r) for r in ast.rules]
        return "\n".join(lines) + "\n"

    def emit_rule_from_ast(self, rule: IrRule) -> str:
        """Emit a single IrRule as 'name sep body terminator'."""
        body = self._emit_alternation(rule.body)
        return f"{rule.name} {self.rule_separator} {body}{self.rule_terminator}"

    def _emit_alternation(self, alt: IrAlternation) -> str:
        """Emit an IrAlternation, joining arms with alt_separator."""
        return self.alt_separator.join(self._emit_sequence(arm) for arm in alt.arms)

    def _emit_sequence(self, seq: IrSequence) -> str:
        """Emit an IrSequence, joining non-empty item strings with a space."""
        parts = [p for p in (self._emit_item(item) for item in seq.items) if p]
        return " ".join(parts) if parts else self.empty_body

    def _emit_item(self, item: IrItem) -> str:
        """Emit an IrItem: render the atom then apply the quantifier."""
        atom_str = self._emit_ir_atom(item.atom)
        q_str = self.format_quantifier(item.quantifier.min, item.quantifier.max)
        return self.place_quantifier(atom_str, q_str)

    def _emit_ir_atom(self, atom: IrAtom) -> str:
        """Dispatch an IrAtom leaf or group to its render method."""
        if isinstance(atom, IrLiteral):
            return self.quote(atom.value)
        if isinstance(atom, IrCharClass):
            return self.render_charclass(atom.pattern, atom.negated)
        if isinstance(atom, IrRuleRef):
            return atom.name
        if isinstance(atom, IrGroup):
            return self.wrap_group(self._emit_alternation(atom.body))
        raise UnsupportedConstructError(
            f"No IR-atom handler for {type(atom).__name__!r}"
        )
