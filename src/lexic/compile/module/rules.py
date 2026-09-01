"""The module self-grammar's rules — the statement skeleton it is built from.

``module_grammar()`` merges a STRICT statement skeleton with the notation's
own rules, and that merge is what a generated module's language IS. It lives
beside the surface that parses with it rather than inside it: the skeleton is
one large rule list, the surface is records and completions, and reading
either does not require scrolling the other.

Grammar design (the 260718 spike, productionized):

- a STRICT statement skeleton — newlines and 4-space indents are REQUIRED
  ``IrLiteral``\\ s (the non-nullable-indent ruling), statement keywords are
  FIRST-disjoint;
- the notation rules embedded wholesale for every expression
  (``GRAMMAR``/inline ``__grammar__`` values, ``IrBind`` entries) — module
  rules take an ``m-`` prefix, merging is concatenation. The embedded token
  rules' trailing ``ws`` is rewritten to ``ws-inl`` (space/tab only, no
  newline) so a value-final statement's own newline is the consuming barrier,
  never swallowed — ``comma``/``lparen`` keep the newline-permitting ``ws``
  (a call spans lines after ``(`` or ``,``);
- the field-less-class ambiguity is killed by the ``m-body`` arm split
  (one nullable gap arm vs blank + body-lines + gap);
- every body line rides through ``m-indented-line`` (the shared leading
  4-space indent), so ``__binds__`` carries its own indent like every other
  line — there is no swallowed-indent gap.
"""

from __future__ import annotations

import lexic.compile.notation.parse as _notation
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

__all__ = ["module_grammar"]


_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)
_OPT = IrQuantifier(0, 1)


def _lit(text: str) -> IrItem:
    return IrItem(IrLiteral(text))


def _ref(name: str) -> IrItem:
    return IrItem(IrRuleRef(name))


def _rule(name: str, *arms: IrSequence, semantic: bool = True) -> IrRule:
    return IrRule(name, IrAlternation(*arms), semantic)


def _rng(lo: int | str, hi: int | str) -> IrRange:
    return IrRange(IrChr(lo), IrChr(hi))


# ── lexical pieces (statement layer — newline-significant) ───────────────

_NAME_FIRST = IrCharClass(_rng("A", "Z"), _rng("a", "z"), IrChr("_"))
_FIELD_FIRST = IrCharClass(_rng("A", "Z"), _rng("a", "z"))
_NAME_REST = IrCharClass(_rng("0", "9"), _rng("A", "Z"), _rng("a", "z"), IrChr("_"))
_DIGITS = IrCharClass(_rng("0", "9"))
# Docstring / string-token content units: anything but quote/backslash
# (newlines included — docstrings wrap), or a backslash escape pair.
_DOC_PLAIN = IrCharClass(_rng(0x00, 0x21), _rng(0x23, 0x5B), _rng(0x5D, 0x10FFFF))
_SQ_PLAIN = IrCharClass(_rng(0x00, 0x26), _rng(0x28, 0x5B), _rng(0x5D, 0x10FFFF))
_ANY = IrCharClass(_rng(0x00, 0x10FFFF))

_BINDS_LIT = "__binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {\n"

_MODULE_RULES = [
    _rule(
        "m-module",
        IrSequence(
            _ref("m-docstring"),
            _ref("m-nl"),
            _ref("m-gap"),
            _ref("m-imports"),
            IrItem(IrRuleRef("m-class-block"), _STAR),
            _ref("m-grammar-stmt"),
            _ref("m-gap"),
            IrItem(IrRuleRef("m-bind-stmt"), _OPT),
        ),
    ),
    _rule("m-nl", IrSequence(_lit("\n"))),
    _rule("m-gap", IrSequence(IrItem(IrLiteral("\n"), _STAR)), semantic=False),
    # ``"""`` content ``"""`` — content spans lines; escapes pair-wise.
    _rule(
        "m-docstring",
        IrSequence(_lit('"""'), IrItem(IrRuleRef("m-doc-unit"), _STAR), _lit('"""')),
    ),
    _rule(
        "m-doc-unit",
        IrSequence(IrItem(_DOC_PLAIN)),
        IrSequence(_lit("\\"), IrItem(_ANY)),
    ),
    # isort-canonical import order: __future__, [typing], compile?, ir, model.
    _rule(
        "m-imports",
        IrSequence(
            _lit("from __future__ import annotations\n"),
            _ref("m-gap"),
            IrItem(IrRuleRef("m-typing-import"), _OPT),
            IrItem(IrRuleRef("m-compile-import"), _OPT),
            _ref("m-ir-import"),
            _lit("from lexic.model import GrammarModel\n"),
            _ref("m-gap"),
        ),
    ),
    _rule(
        "m-typing-import",
        IrSequence(
            _lit("from typing import "),
            _ref("m-name-list"),
            _ref("m-nl"),
            _ref("m-gap"),
        ),
    ),
    _rule(
        "m-compile-import", IrSequence(_lit("from lexic.compile import bind_module\n"))
    ),
    _rule(
        "m-ir-import",
        IrSequence(_lit("from lexic.ir import "), _ref("m-import-tail")),
    ),
    # tail ::= paren | flat — sibling rules because the arms fold with
    # different arities (the m-body precedent).
    _rule(
        "m-import-tail",
        IrSequence(_ref("m-import-paren")),
        IrSequence(_ref("m-import-flat")),
    ),
    _rule(
        "m-import-paren",
        IrSequence(_lit("(\n"), IrItem(IrRuleRef("m-import-line"), _PLUS), _lit(")\n")),
    ),
    _rule("m-import-flat", IrSequence(_ref("m-name-list"), _ref("m-nl"))),
    _rule("m-import-line", IrSequence(_lit("    "), _ref("m-name"), _lit(",\n"))),
    _rule(
        "m-name-list",
        IrSequence(_ref("m-name"), IrItem(IrRuleRef("m-more-name"), _STAR)),
    ),
    _rule("m-more-name", IrSequence(_lit(", "), _ref("m-name"))),
    _rule("m-name", IrSequence(IrItem(_NAME_FIRST), IrItem(_NAME_REST, _STAR))),
    # Field names are never underscore-led (keyword-mangle is TRAILING);
    # the narrower first-char class is what gates a field line against
    # ``__grammar__`` at one char. ``m-name`` keeps '_' for ``__future__``.
    _rule("m-field-name", IrSequence(IrItem(_FIELD_FIRST), IrItem(_NAME_REST, _STAR))),
    _rule("m-int", IrSequence(IrItem(_DIGITS, _PLUS))),
    # class block: header, docstring line, then the arm-split body.
    _rule(
        "m-class-block",
        IrSequence(
            _lit("class "),
            _ref("m-name"),
            _lit("("),
            _ref("m-name-list"),
            _lit("):\n    "),
            _ref("m-docstring"),
            _ref("m-nl"),
            _ref("m-body"),
        ),
    ),
    # body ::= filled | empty — the field-less arm is a single nullable run,
    # so adjacent gaps never split ambiguously; separate rules because the
    # arms fold with different arities.
    _rule(
        "m-body",
        IrSequence(_ref("m-filled-body")),
        IrSequence(_ref("m-empty-body")),
    ),
    _rule(
        "m-filled-body",
        IrSequence(_lit("\n"), IrItem(IrRuleRef("m-body-line"), _PLUS), _ref("m-gap")),
    ),
    _rule("m-empty-body", IrSequence(_ref("m-gap"))),
    # Every body line rides through ``m-indented-line`` (the shared leading
    # 4-space indent); past the indent the three tails separate on their
    # keyword — a field name ([A-Za-z] — ``m-field-name``, never
    # underscore-led) vs ``__grammar__`` vs ``__shape__`` vs ``__binds__`` (the
    # three '_'-led keywords separate at k=3: ``__g``/``__s``/``__b``).
    # Predictive, no island.
    _rule("m-body-line", IrSequence(_ref("m-indented-line"))),
    _rule("m-indented-line", IrSequence(_lit("    "), _ref("m-line-tail"))),
    _rule(
        "m-line-tail",
        IrSequence(_ref("m-field-tail")),
        IrSequence(_ref("m-grammar-tail")),
        IrSequence(_ref("m-shape-tail")),
        IrSequence(_ref("m-inline-binds")),
    ),
    # The union loop rides INSIDE the line rule so the loop-exit has an
    # in-rule (soft) continuation — ``" |"`` vs ``" ="``/``"\\n"`` separates
    # at k=2. A standalone ``m-type`` rule would end on the loop (empty soft
    # FOLLOW, hard FOLLOW unsound for a stored gate) and island.
    _rule(
        "m-field-tail",
        IrSequence(
            _ref("m-field-name"),
            _lit(": "),
            _ref("m-type-atom"),
            IrItem(IrRuleRef("m-type-union"), _STAR),
            IrItem(IrRuleRef("m-default"), _OPT),
            _ref("m-nl"),
        ),
    ),
    _rule("m-default", IrSequence(_lit(" = None"))),
    # type expressions: T, list[T], Literal["…", …], unions with " | ".
    # Inside brackets the union/separator tails are one flat loop whose
    # in-rule exit is "]" — FIRST-disjoint from ' '/',' — so no rule ends
    # on a loop (the same no-island shape as the field line; the fold
    # concatenates, so the arg structure is not modelled, only spelled).
    _rule("m-type-union", IrSequence(_lit(" | "), _ref("m-type-atom"))),
    _rule(
        "m-type-atom",
        IrSequence(_ref("m-name"), IrItem(IrRuleRef("m-type-args"), _OPT)),
    ),
    _rule(
        "m-type-args",
        IrSequence(
            _lit("["),
            _ref("m-arg-unit"),
            IrItem(IrRuleRef("m-arg-tail"), _STAR),
            _lit("]"),
        ),
    ),
    _rule(
        "m-arg-tail",
        IrSequence(_ref("m-arg-union")),
        IrSequence(_ref("m-arg-sep")),
    ),
    _rule("m-arg-union", IrSequence(_lit(" | "), _ref("m-arg-unit"))),
    _rule("m-arg-sep", IrSequence(_lit(", "), _ref("m-arg-unit"))),
    _rule(
        "m-arg-unit",
        IrSequence(_ref("m-type-atom")),
        IrSequence(_ref("m-str-token")),
    ),
    # A raw string token (Literal[...] values) — spelling preserved verbatim.
    _rule(
        "m-str-token",
        IrSequence(_ref("m-dq-token")),
        IrSequence(_ref("m-sq-token")),
    ),
    _rule(
        "m-dq-token",
        IrSequence(_lit('"'), IrItem(IrRuleRef("m-dq-unit"), _STAR), _lit('"')),
    ),
    _rule(
        "m-sq-token",
        IrSequence(_lit("'"), IrItem(IrRuleRef("m-sq-unit"), _STAR), _lit("'")),
    ),
    _rule(
        "m-dq-unit",
        IrSequence(IrItem(_DOC_PLAIN)),
        IrSequence(_lit("\\"), IrItem(_ANY)),
    ),
    _rule(
        "m-sq-unit", IrSequence(IrItem(_SQ_PLAIN)), IrSequence(_lit("\\"), IrItem(_ANY))
    ),
    # inline tables — a value-final line, so it OWNS its trailing newline
    # (``value`` no longer swallows it; ``ws-inl`` stops at the newline).
    _rule(
        "m-grammar-tail",
        IrSequence(
            _lit("__grammar__: ClassVar[IrRule] = "), _ref("value"), _ref("m-nl")
        ),
    ),
    _rule(
        "m-shape-tail",
        IrSequence(_lit("__shape__: ClassVar[int] = "), _ref("pos-int"), _ref("m-nl")),
    ),
    # Each entry consumes its trailing newline PLUS the next line's leading
    # 4 spaces (one hoisted before the loop), so loop-take peeks ' ' against
    # the '}' closer — FIRST-disjoint, no island.
    _rule(
        "m-inline-binds",
        IrSequence(
            _lit(_BINDS_LIT),
            _lit("    "),
            IrItem(IrRuleRef("m-bind-entry"), _PLUS),
            _lit("}"),
            _ref("m-nl"),
        ),
    ),
    _rule(
        "m-bind-entry",
        IrSequence(
            _lit("    "),
            _ref("m-int"),
            _lit(': ("'),
            _ref("m-field-name"),
            _lit('", '),
            _ref("value"),
            _lit("),\n    "),
        ),
    ),
    _rule(
        "m-grammar-stmt",
        IrSequence(_lit("GRAMMAR: IrAst = "), _ref("value"), _ref("m-nl")),
    ),
    _rule("m-bind-stmt", IrSequence(_lit("bind_module(GRAMMAR, globals())\n"))),
]

# ── the notation token rules whose trailing ``ws`` must NOT cross a newline ─
# (so a value-final statement's own ``m-nl`` is the consuming barrier).
# ``comma``/``lparen`` keep the newline-permitting ``ws`` — a call spans lines
# after ``(`` or ``,``.
_INLINE_WS_RULES = frozenset(
    {"rparen", "dq-str", "sq-str", "name", "neg-int", "pos-int"}
)

_WS_INL = _rule(
    "ws-inl",
    IrSequence(IrItem(IrCharClass(IrChr(9), IrChr(32)), _STAR)),
    semantic=False,
)


def _inline_ws(rule: IrRule) -> IrRule:
    """Rewrite a notation token rule's trailing ``ws`` ref to ``ws-inl``.

    :param rule: A notation token rule (arity-preserving — only the ref name
        changes, so the rule's fold entry stays aligned).
    :returns: The rewritten rule.
    """
    arms = [
        IrSequence(
            *(
                IrItem(IrRuleRef("ws-inl"), it.quantifier)
                if isinstance(it.atom, IrRuleRef) and str(it.atom) == "ws"
                else it
                for it in arm
            )
        )
        for arm in rule.body
    ]
    return IrRule(rule.name, IrAlternation(*arms), rule.semantic)


def module_grammar() -> IrAst:
    """The module self-grammar: statement skeleton + the notation rules.

    :returns: The merged ``IrAst`` (start ``m-module``).
    """
    notation_rules = [
        _inline_ws(r) if str(r.name) in _INLINE_WS_RULES else r
        for r in _notation.NOTATION_GRAMMAR.rules
        if str(r.name) != "start"
    ]
    return IrAst(IrSeq(*_MODULE_RULES, *notation_rules, _WS_INL), "m-module")
