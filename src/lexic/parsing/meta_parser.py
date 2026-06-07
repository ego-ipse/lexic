"""MetaGrammarParser — generic Lark-based IR-AST parser.

Knows a fixed set of canonical tag names (ir_rule, ir_alternation, ir_sequence,
ir_item, ir_literal, ir_charclass, ir_ruleref, ir_group). The flavour's Lark
meta-grammar uses these names to label productions; this module dispatches each
tag to the appropriate IR AST constructor. Token-value handling (escape decoding,
charclass parsing, quantifier parsing) delegates to the IrFlavour.

Parse pipeline (text → IrAst):

  text  ──►  Lark(flavour.meta_grammar)  ──►  Tree
                                                │
                                                ▼
                              _IrTagTransformer(flavour)
                                                │
                                                ▼
                                              IrAst
                                                │
                                                ▼
              parse_directives(text, flavour.line_comment)  (separately, in compile_grammar)
                                                │
                                                ▼
                       Directives(non_semantic, start)

Lark errors and IrFlavour token-parser ValueErrors are caught at this boundary
and re-raised as UnsupportedConstructError with rule-first messages.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar, TypeAlias

from lark import (
    GrammarError,
    Lark,
    Token,
    Transformer,
    UnexpectedCharacters,
    UnexpectedToken,
)

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrFlavour
from lexic.ir.base import IrAtom, IrTuple
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)

# ── builder functions ─────────────────────────────────────────────────

_IrBuilder: TypeAlias = Callable[[IrFlavour, list], object]


def _build_charclass(flavour: IrFlavour, children: list) -> IrAtom:
    """Build an IrCharClass, wrapping in IrNot when the pattern is negated.

    :param flavour: The flavour providing ``parse_charclass``.
    :param children: Lark tree children; ``children[0]`` is the bracket token.
    :returns: ``IrCharClass(pattern)`` or ``IrNot(IrCharClass(pattern))``.
    """
    pattern, negated = flavour.parse_charclass(str(children[0]))
    atom: IrAtom = IrCharClass(pattern)
    return IrNot(atom) if negated else atom


_IR_BUILDERS: dict[str, _IrBuilder] = {
    "start": lambda _f, c: IrAst(rules=IrTuple(*c), start=c[0].name if c else ""),
    "ir_rule": lambda _f, c: IrRule(name=str(c[0]), body=c[1]),
    "ir_alternation": lambda _f, c: IrAlternation(*c),
    "ir_sequence": lambda _f, c: IrSequence(*c),
    "ir_literal": lambda f, c: f.normalize_literal(f.escapes.decode(str(c[0])[1:-1])),
    "ir_charclass": _build_charclass,
    "ir_ruleref": lambda _f, c: IrRuleRef(str(c[0])),
    "ir_group": lambda _f, c: c[0],
}

# ── transformer ───────────────────────────────────────────────────────


class _IrTagTransformer(Transformer):
    """Thin Lark Transformer — dispatches all ir_* tags via _IR_BUILDERS."""

    def __init__(self, flavour: IrFlavour) -> None:
        super().__init__()
        self._flavour = flavour

    def __default__(self, data: str, children: list, meta: object) -> Any:
        builder = _IR_BUILDERS.get(data)
        if builder is None:
            return super().__default__(data, children, meta)
        return builder(self._flavour, children)

    def ir_item(self, items: list) -> IrItem:
        """Handle either prefix or suffix quantifier ordering."""
        tokens = [c for c in items if isinstance(c, Token)]
        atoms = [c for c in items if not isinstance(c, Token)]
        if len(tokens) > 1:
            raise ValueError(f"ir_item: multiple quantifier tokens: {items!r}")
        if len(atoms) != 1:
            raise ValueError(f"ir_item: unexpected atom count: {items!r}")
        quantifier = (
            self._flavour.parse_quantifier(str(tokens[0])) if tokens else IrQuantifier()
        )
        return IrItem(atom=atoms[0], quantifier=quantifier)


# ── parser ────────────────────────────────────────────────────────────


class MetaGrammarParser:
    """Generic IR-AST parser. Stateless after construction."""

    _PARSERS: ClassVar[dict[IrFlavour, MetaGrammarParser]] = {}

    def __init__(self, flavour: IrFlavour) -> None:
        self._flavour = flavour
        self._lark = Lark(flavour.meta_grammar, parser="earley", ambiguity="resolve")
        self._transformer = _IrTagTransformer(flavour)

    @classmethod
    def for_flavour(cls, flavour: IrFlavour) -> MetaGrammarParser:
        """Return a memoised MetaGrammarParser for the given IrFlavour singleton."""
        if flavour not in cls._PARSERS:
            cls._PARSERS[flavour] = cls(flavour)
        return cls._PARSERS[flavour]

    def parse(self, text: str) -> IrAst:
        """Parse grammar text; wraps Lark errors as UnsupportedConstructError."""
        try:
            tree = self._lark.parse(text)
            return self._transformer.transform(tree)
        except (UnexpectedCharacters, UnexpectedToken, GrammarError) as exc:
            raise UnsupportedConstructError(
                f"Failed to parse {self._flavour.name} grammar: {exc}"
            ) from exc
        except ValueError as exc:
            raise UnsupportedConstructError(
                f"Invalid token in {self._flavour.name} grammar: {exc}"
            ) from exc
