"""GbnfEmitter: RuleSpec list (IrItem-shape) → GBNF text.

Single-shape only — no legacy-atom dispatch. The mirror replaces
grammars/gbnf/emitter.py at cutover (Slice 4).
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.emit import FlavourEmitter
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier


def _quant_suffix(q) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    return bounds_to_quantifier(q.min, q.max)


def _bracket(pattern: str, negated: bool) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    return f"[{'^' if negated else ''}{pattern}]"


def _atom_to_gbnf_item(item: IrItem) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    atom = item.atom
    q = _quant_suffix(item.quantifier)
    if isinstance(atom, IrLiteral):
        return f'"{atom.value}"{q}'
    if isinstance(atom, IrNot) and isinstance(atom.body, IrCharClass):
        return _bracket(atom.body.value, True) + q
    if isinstance(atom, IrCharClass):
        return _bracket(atom.value, False) + q
    if isinstance(atom, IrRuleRef):
        return atom.value + q
    if isinstance(atom, IrGroup):
        body = _alt_to_gbnf(atom.body)
        return f"({body}){q}" if q else f"({body})"
    raise TypeError(f"Unsupported IR atom for GBNF emit: {type(atom).__name__}")


def _seq_to_gbnf(seq: IrSequence) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    return " ".join(_atom_to_gbnf_item(it) for it in seq.items)


def _alt_to_gbnf(alt: IrAlternation) -> str:
    """Convert (min, max) bounds to a GBNF/Lark quantifier string."""
    return " | ".join(_seq_to_gbnf(s) for s in alt.arms)


class GbnfEmitter(FlavourEmitter):
    """Emit GBNF text from RuleSpec list with IrItem-shaped items."""

    supports: ClassVar[frozenset[str]] = frozenset(
        {
            "literal",
            "char_class",
            "negated_class",
            "quantifier",
            "alternation",
            "non_capturing_group",
            "unicode_escape",
        }
    )

    def emit(self, specs: list[RuleSpec]) -> str:
        """Emit the given list of RuleSpecs as a GBNF grammar string."""
        return "\n".join(self.emit_rule(s) for s in specs) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        """Emit the given RuleSpec as a GBNF rule string."""
        return f"{spec.rule_name} ::= {self._emit_body(spec)}"

    def _emit_body(self, spec: RuleSpec) -> str:
        """Emit the given RuleSpec's body as a GBNF rule string."""
        if not spec.items:
            return '""'
        if spec.kind == "alternation":
            # items are IrItem(IrRuleRef(arm_name)) per arm
            return " | ".join(
                it.atom.value
                for it in spec.items
                if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
            )
        first = spec.items[0]
        if isinstance(first, IrAlternation):
            # Multi-arm value_str: bare IrAlternation at items[0]
            return _alt_to_gbnf(first)
        # Sequence of IrItems
        return " ".join(
            _atom_to_gbnf_item(it) for it in spec.items if isinstance(it, IrItem)
        )
