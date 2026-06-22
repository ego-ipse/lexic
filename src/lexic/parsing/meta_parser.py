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

from dataclasses import dataclass
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
from lexic.ir.base import IrAtom, IrSeq
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
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


def _unit_to_chr(unit: str) -> str:
    """Decode a verbatim escape unit to its single decoded glyph.

    A bare single-char unit is returned as-is; a backslash-prefixed escape
    unit (e.g. ``"\\x00"``) is decoded via :data:`CANONICAL_ESCAPES`.

    :param unit: A verbatim unit as returned by :func:`_read_unit`.
    :returns: The decoded single character.
    """
    if unit.startswith("\\") and len(unit) > 1:
        return CANONICAL_ESCAPES.read_escape(unit, 0)[0]
    return unit


def _build_charclass(flavour: IrFlavour, children: list) -> IrAtom:
    """Build a structured IrCharClass; wrap in IrNot when negated.

    The interior split lives here deliberately: it is Lark-era scaffolding
    that dies with this file when the IR-native parser replaces the
    metagrammars. ``x-y`` segments become :class:`IrRange` of decoded
    :class:`IrChr` code-point endpoints; every other unit becomes a single
    :class:`IrChr` code point; a ``-`` with nothing following stays a literal
    code point.

    :param flavour: The flavour providing ``parse_charclass``.
    :param children: Lark tree children; ``children[0]`` is the bracket token.
    :returns: ``IrCharClass(*elements)`` or ``IrNot(IrCharClass(*elements))``.
    """
    pattern, negated = flavour.parse_charclass(str(children[0]))
    elements: list[IrRange | IrChr] = []
    i = 0
    while i < len(pattern):
        unit, i = _read_unit(pattern, i)
        if i < len(pattern) and pattern[i] == "-" and i + 1 < len(pattern):
            hi_unit, i = _read_unit(pattern, i + 1)
            elements.append(
                IrRange(IrChr(_unit_to_chr(unit)), IrChr(_unit_to_chr(hi_unit)))
            )
        else:
            elements.append(IrChr(_unit_to_chr(unit)))
    atom: IrAtom = IrCharClass(*elements)
    return IrNot(atom) if negated else atom


@dataclass(slots=True)
class _IncrementalRule:
    """Marker for an ABNF ``name =/ body`` arm, merged by :func:`_build_start`.

    Not an IR node — a throwaway Lark-era carrier so ``start`` can fold the
    incremental alternation into the base rule defined earlier.
    """

    name: str
    body: IrAlternation


def _build_start(_flavour: IrFlavour, children: list) -> IrAst:
    """Assemble the rule list, folding ABNF ``=/`` incremental alternatives.

    A plain rule is appended; an :class:`_IncrementalRule` extends the arms of
    the same-named base rule defined earlier (RFC 5234 §3.3).

    :raises UnsupportedConstructError: an ``=/`` arm names an undefined rule.
    """
    rules: list[IrRule] = []
    position: dict[str, int] = {}
    for child in children:
        if isinstance(child, _IncrementalRule):
            if child.name not in position:
                raise UnsupportedConstructError(
                    f"ABNF '=/' for undefined rule {child.name!r}"
                )
            base = rules[position[child.name]]
            rules[position[child.name]] = IrRule(
                name=base.name, body=IrAlternation(*base.body, *child.body)
            )
        else:
            position[child.name] = len(rules)
            rules.append(child)
    return IrAst(rules=IrSeq(*rules), start=rules[0].name if rules else "")


def _build_numseq(_flavour: IrFlavour, children: list) -> IrLiteral:
    """Build a case-sensitive :class:`IrLiteral` from an ABNF value-sequence.

    ``%x66.61.6c`` (and ``%d``/``%b`` radixes) are dot-concatenated code
    points — exact, case-sensitive bytes, unlike a quoted ``"abc"`` literal
    (case-insensitive). They lower to a raw ``IrLiteral`` — the canonical form
    shared with a GBNF string literal of the same text.
    """
    token = str(children[0])
    radix = {"b": 2, "d": 10, "x": 16}[token[1].lower()]
    return IrLiteral("".join(chr(int(part, radix)) for part in token[2:].split(".")))


def _build_option(_flavour: IrFlavour, children: list) -> IrItem:
    """Build an optional ``[ ... ]`` element — an item bound to ``(0, 1)``."""
    return IrItem(atom=children[0], quantifier=IrQuantifier(0, 1))


def _build_literal_cs(flavour: IrFlavour, children: list) -> IrLiteral:
    """``%s"..."`` — case-sensitive string → raw ``IrLiteral`` (RFC 7405)."""
    return IrLiteral(flavour.escapes.decode(str(children[0])[3:-1]))


def _build_literal_ci(flavour: IrFlavour, children: list) -> object:
    """``%i"..."`` — explicit case-insensitive string (RFC 7405)."""
    return flavour.normalize_literal(flavour.escapes.decode(str(children[0])[3:-1]))


def _build_prose(_flavour: IrFlavour, children: list) -> object:
    """prose-val ``<...>`` — recognised, but has no machine-readable meaning.

    :raises UnsupportedConstructError: always; prose-val cannot be compiled.
    """
    raise UnsupportedConstructError(
        f"ABNF prose-val has no formal semantics: {str(children[0])!r}"
    )


_IR_BUILDERS: dict[str, _IrBuilder] = {
    "start": _build_start,
    "ir_rule": lambda _f, c: IrRule(name=str(c[0]), body=c[1]),
    "ir_rule_inc": lambda _f, c: _IncrementalRule(str(c[0]), c[-1]),
    "ir_alternation": lambda _f, c: IrAlternation(*c),
    "ir_sequence": lambda _f, c: IrSequence(*c),
    "ir_literal": lambda f, c: f.normalize_literal(f.escapes.decode(str(c[0])[1:-1])),
    "ir_literal_cs": _build_literal_cs,
    "ir_literal_ci": _build_literal_ci,
    "ir_charclass": _build_charclass,
    "ir_numseq": _build_numseq,
    "ir_option": _build_option,
    "ir_prose": _build_prose,
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
