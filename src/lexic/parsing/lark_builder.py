"""LarkBuilder — RuleSpec list (IrItem-shape) → Lark grammar + Transformer.

Replaces the legacy codegen/lark_builder.py at cutover (Slice 4).

Decision CQ #2: non-semantic optionality is driven by RuleSpec.non_semantic_fields
+ IrItem.quantifier. No `name == "ws"` hardcoding.
"""

from __future__ import annotations

import lark

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNoneType
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec
from lexic.parsing.transformer.build_transformer import build_transformer
from lexic.utils.charclass import charclass_pattern
from lexic.utils.names import to_lark_name
from lexic.utils.quantifiers import bounds_to_quantifier


class _LarkLiteralEscapes(EscapeCodec):
    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


_LARK_ESCAPES = _LarkLiteralEscapes()


_LARK_TERMINAL_QUANTS = frozenset({"", "?", "*", "+"})

_LITERAL_REGEX_ESCAPES: dict[str, str] = {
    # Control characters → regex escape sequences
    "\n": r"\n",
    "\r": r"\r",
    "\t": r"\t",
    # Backslash must come first so we don't double-escape other entries
    "\\": r"\\",
    # Lark regex delimiter
    "/": r"\/",
    # Regex metacharacters
    ".": r"\.",
    "^": r"\^",
    "$": r"\$",
    "*": r"\*",
    "+": r"\+",
    "?": r"\?",
    "{": r"\{",
    "}": r"\}",
    "[": r"\[",
    "]": r"\]",
    "(": r"\(",
    ")": r"\)",
    "|": r"\|",
}


def literal_to_regex_pattern(value: str) -> str:
    """Escape a literal string so it matches exactly when used inside a regex pattern.

    Handles control characters (\\n, \\r, \\t), the backslash, regex
    metacharacters, and the Lark regex delimiter (/).
    """
    return "".join(_LITERAL_REGEX_ESCAPES.get(c, c) for c in value)


def _bracket(pattern: str, negated: bool) -> str:
    """Convert a character class pattern to a Lark bracket string."""
    return f"[{'^' if negated else ''}{pattern}]"


def _regex_terminal(pattern: str, q: IrQuantifier) -> str:
    """Format a regex pattern as a Lark terminal with the quantifier.

    Lark terminal syntax only supports ?, *, + as external quantifiers.
    For {n}/{m,n}, the quantifier is embedded inside the regex.
    For Q(0,n) with n>1, /pattern{0,n}/ would be zero-width (forbidden by
    dynamic Earley), so we use /pattern{1,n}/? instead — same semantics.
    """
    q_str = bounds_to_quantifier(q.lo, q.hi)
    if q_str in _LARK_TERMINAL_QUANTS:
        return f"/{pattern}/{q_str}"
    if q.lo == 0 and not isinstance(q.hi, IrNoneType):
        return f"/{pattern}{bounds_to_quantifier(1, q.hi)}/?"
    return f"/{pattern}{q_str}/"


def _atom_to_lark(item: IrItem) -> str:
    """Convert an IR item to a Lark atom string."""
    atom = item.atom
    q_str = bounds_to_quantifier(item.quantifier.lo, item.quantifier.hi)
    if isinstance(atom, IrLiteral):
        return f'"{_LARK_ESCAPES.encode(atom)}"{q_str}'
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            return _regex_terminal(
                _bracket(charclass_pattern(inner).replace("/", "\\/"), True),
                item.quantifier,
            )
    if isinstance(atom, IrCharClass):
        return _regex_terminal(
            _bracket(charclass_pattern(atom).replace("/", "\\/"), False),
            item.quantifier,
        )
    if isinstance(atom, IrRuleRef):
        return f"{to_lark_name(atom)}{q_str}"
    if isinstance(atom, IrAlternation):
        # Literal-only group arms are dropped by Lark (anonymous string terminals).
        # Use regex form so the matched token is preserved in children.
        literal_only = all(
            isinstance(sub.atom, IrLiteral)
            for arm in atom
            for sub in arm
            if isinstance(sub, IrItem)
        )
        seq_fn = _seq_to_lark_regex if literal_only else _seq_to_lark
        body = " | ".join(seq_fn(s) for s in atom)
        return f"({body}){q_str}"
    raise UnsupportedConstructError(
        f"_atom_to_lark: no handler for atom type {type(atom).__name__!r}"
    )


def _atom_to_lark_regex(item: IrItem) -> str:
    """Like _atom_to_lark but always uses regex for literals so Lark preserves tokens.

    Used for value_str rules: Lark drops anonymous string-literal tokens from children,
    making it impossible to tell if optional literals matched. Regex form keeps all tokens.
    """
    atom = item.atom
    q_str = bounds_to_quantifier(item.quantifier.lo, item.quantifier.hi)
    if isinstance(atom, IrLiteral):
        return _regex_terminal(literal_to_regex_pattern(atom), item.quantifier)
    if isinstance(atom, IrNot):
        inner = atom[0]
        if isinstance(inner, IrCharClass):
            return _regex_terminal(
                _bracket(charclass_pattern(inner).replace("/", "\\/"), True),
                item.quantifier,
            )
    if isinstance(atom, IrCharClass):
        return _regex_terminal(
            _bracket(charclass_pattern(atom).replace("/", "\\/"), False),
            item.quantifier,
        )
    if isinstance(atom, IrRuleRef):
        return f"{to_lark_name(atom)}{q_str}"
    if isinstance(atom, IrAlternation):
        body = " | ".join(_seq_to_lark_regex(s) for s in atom)
        return f"({body}){q_str}"
    raise UnsupportedConstructError(
        f"_atom_to_lark_regex: no handler for atom type {type(atom).__name__!r}"
    )


def _seq_to_lark(seq: IrSequence) -> str:
    """Convert an IrSequence to a Lark sequence string."""
    return " ".join(_atom_to_lark(it) for it in seq)


def _seq_to_lark_regex(seq: IrSequence) -> str:
    return " ".join(_atom_to_lark_regex(it) for it in seq)


class LarkBuilder:
    """Build a Lark grammar string + Transformer factory from NewRuleSpecs."""

    def __init__(self, specs: list[RuleSpec], *, start_rule: str | None = None) -> None:
        self.specs = specs
        self._start_rule = start_rule or (specs[0].rule_name if specs else "")

    def build_grammar(self) -> tuple[str, str]:
        """Build a Lark grammar string from a list of NewRuleSpecs."""
        lines = [self._emit_rule(s) for s in self.specs]
        return "\n".join(lines) + "\n", to_lark_name(self._start_rule)

    def _emit_rule(self, spec: RuleSpec) -> str:
        """Build a Lark rule from a RuleSpec."""
        name = to_lark_name(spec.rule_name)
        body = self._emit_body(spec)
        return f"{name}: {body}"

    def _emit_body(self, spec: RuleSpec) -> str:
        """Build a Lark body from a RuleSpec."""
        if not spec.items:
            return '""'
        if spec.kind == "alternation":
            return " | ".join(
                to_lark_name(it.atom)
                for it in spec.items
                if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
            )
        first = spec.items[0]
        if spec.kind == "value_str":
            # Use regex for all atoms so Lark preserves tokens in children.
            # Lark drops anonymous string-literal tokens, which breaks reconstruction
            # of value_str fields when optional literals are present.
            if isinstance(first, IrAlternation):
                return " | ".join(_seq_to_lark_regex(s) for s in first)
            return " ".join(
                _atom_to_lark_regex(it) for it in spec.items if isinstance(it, IrItem)
            )
        if isinstance(first, IrAlternation):
            return " | ".join(_seq_to_lark(s) for s in first)
        return " ".join(
            _atom_to_lark(it) for it in spec.items if isinstance(it, IrItem)
        )

    def build_transformer(self, classes: dict[str, type]) -> lark.Transformer:
        """Build a Transformer instance from NewRuleSpecs"""
        return build_transformer(self.specs, classes)


def build_lark(
    specs: list[RuleSpec], classes: dict[str, type], start_rule: str
) -> tuple[str, lark.Lark, lark.Transformer]:
    """One-call helper for compile.py: specs → (grammar_str, parser, transformer)."""
    builder = LarkBuilder(specs, start_rule=start_rule)
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start)
    transformer = builder.build_transformer(classes)
    return grammar_str, parser, transformer
