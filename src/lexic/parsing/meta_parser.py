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
from lexic.ir.base import IrAtom, IrSeq, IrStr
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

# ── builder functions ─────────────────────────────────────────────────

_IrBuilder: TypeAlias = Callable[[IrFlavour, list], object]


def _read_unit(s: str, i: int) -> tuple[str, int]:
    """Read one encoded escape unit at ``s[i]`` — text kept verbatim.

    The codec supplies only the unit *boundary* (``\\x1F`` is one unit of
    four source chars); nothing is decoded.
    """
    if s[i] == "\\" and i + 1 < len(s):
        _, j = CANONICAL_ESCAPES.read_escape(s, i)
        return s[i:j], j
    return s[i], i + 1


def _build_charclass(flavour: IrFlavour, children: list) -> IrAtom:
    """Build a structured IrCharClass; wrap in IrNot when negated.

    The interior split lives here deliberately: it is Lark-era scaffolding
    that dies with this file when the IR-native parser replaces the
    metagrammars. ``x-y`` segments become :class:`IrRange` (endpoints kept
    as encoded units, so emission stays byte-exact); other units accumulate
    into maximal :class:`IrStr` runs; a ``-`` with nothing following stays
    a literal run char.

    :param flavour: The flavour providing ``parse_charclass``.
    :param children: Lark tree children; ``children[0]`` is the bracket token.
    :returns: ``IrCharClass(*elements)`` or ``IrNot(IrCharClass(*elements))``.
    """
    pattern, negated = flavour.parse_charclass(str(children[0]))
    elements: list[IrRange | IrStr] = []
    run: list[str] = []
    i = 0
    while i < len(pattern):
        unit, i = _read_unit(pattern, i)
        if i < len(pattern) and pattern[i] == "-" and i + 1 < len(pattern):
            hi_unit, i = _read_unit(pattern, i + 1)
            if run:
                elements.append(IrStr("".join(run)))
                run = []
            elements.append(IrRange(unit, hi_unit))
        else:
            run.append(unit)
    if run:
        elements.append(IrStr("".join(run)))
    atom: IrAtom = IrCharClass(*elements)
    return IrNot(atom) if negated else atom


_IR_BUILDERS: dict[str, _IrBuilder] = {
    "start": lambda _f, c: IrAst(rules=IrSeq(*c), start=c[0].name if c else ""),
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
