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
from typing import TYPE_CHECKING, ClassVar, TypeVar, Callable

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier

if TYPE_CHECKING:
    from lexic.ir.protocols import EscapeCodec, AtomEmitHandler

A = TypeVar("A", bound=Atom)


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

    @staticmethod
    def handler(
        atom_type: type[A], fn: Callable[[A, FlavourEmitter], str]
    ) -> AtomEmitHandler:
        """Helper to make an AtomEmitHandler for a specific atom type from a simpler function."""

        def _handler(a: Atom, e: FlavourEmitter) -> str:
            """Handler that checks the atom type and delegates to the simpler function."""
            assert isinstance(a, atom_type)
            return fn(a, e)

        return _handler

    @staticmethod
    def make_handlers(
        *handlers: tuple[type, Callable[..., str]],
    ) -> dict[type, AtomEmitHandler]:
        """Helper to make a dict of AtomEmitHandlers from simpler functions."""
        handlers_dict: dict[type, AtomEmitHandler] = {}
        for atom_type, fn in handlers:

            def _handler(
                a: Atom,
                e: FlavourEmitter,
                _t: type = atom_type,
                _f: Callable[..., str] = fn,
            ) -> str:
                assert isinstance(a, _t)
                return _f(a, e)

            handlers_dict[atom_type] = _handler
        return handlers_dict

    DEFAULT_HANDLERS: ClassVar[dict[type, AtomEmitHandler]] = make_handlers(
        (LiteralAtom, lambda a, e: e.quote(a.value)),
        (
            QuantifiedLiteralAtom,
            lambda a, e: e.place_quantifier(
                e.quote(a.value), e.format_quantifier(a.min, a.max)
            ),
        ),
        (
            CharClassAtom,
            lambda a, e: e.place_quantifier(
                e.render_charclass(a.pattern), e.format_quantifier(a.min, a.max)
            ),
        ),
        (
            RuleRefAtom,
            lambda a, e: e.place_quantifier(
                a.rule_name, e.format_quantifier(a.min, a.max)
            ),
        ),
        (AlternationAtom, lambda a, e: e.alt_separator.join(a.arm_rule_names)),
        (
            InlineAlternationAtom,
            lambda a, e: e.wrap_group(e.alt_separator.join(a.arm_rule_names)),
        ),
        (
            InlineRegexAtom,
            lambda a, e: e.place_quantifier(
                e.render_inline_regex(a.regex), e.format_quantifier(a.min, a.max)
            ),
        ),
    )

    def __init__(
        self,
        escapes: EscapeCodec,
        handlers: dict[type, AtomEmitHandler] | None = None,
    ) -> None:
        """Initialise with an escape codec and optional atom handlers.

        Defaults to DEFAULT_HANDLERS.
        """
        self._escapes = escapes
        self._handlers: dict[type, AtomEmitHandler] = (
            dict(handlers) if handlers is not None else dict(self.DEFAULT_HANDLERS)
        )

    supports: ClassVar[frozenset[str]]
    """The set of atom types this emitter supports; used for testing."""

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

    def render_charclass(self, canonical_pattern: str) -> str:
        """Render a canonical char class pattern."""
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
        """Emit the body of a rule spec by rendering its atoms and joining with spaces."""
        parts = [self.render_atom(a) for a in spec.items]
        parts = [p for p in parts if p]
        if not parts:
            return self.empty_body
        return " ".join(parts)

    def render_atom(self, atom: Atom) -> str:
        """Render an atom using the appropriate handler."""
        try:
            _handler = self._handlers[type(atom)]
        except KeyError as exc:
            raise NotImplementedError(
                f"{type(self).__name__} has no handler for {type(atom).__name__}"
            ) from exc
        return _handler(atom, self)
