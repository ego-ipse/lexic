"""The generated-module self-grammar — lexic parses its own exports.

``parse_module(text)`` parses an exported twin module (the CANONICAL layout
``export_source`` writes — a formatter fixpoint) into a :class:`MModule`
model; ``verify_module(compiled, text)`` cross-checks that model against the
binding view the exporter rendered from, closing the emit→reparse loop at
file granularity (the old R1 remainder).

Grammar design (the 260718 spike, productionized):

- a STRICT statement skeleton — newlines and 4-space indents are REQUIRED
  ``IrLiteral``\\ s (the non-nullable-indent ruling), statement keywords are
  FIRST-disjoint;
- the notation rules embedded wholesale for every expression
  (``GRAMMAR``/inline ``__grammar__`` values, ``IrBind`` entries) — module
  rules take an ``m-`` prefix, merging is concatenation;
- the field-less-class ambiguity is killed by the ``m-body`` arm split
  (one nullable gap arm vs blank + body-lines + gap);
- an embedded expression's trailing ``ws`` swallows the NEXT line's leading
  indent (noise), so the rules for lines that can only follow an expression
  (``__binds__``) start at their keyword — a deliberate, documented
  indent-strictness gap on those lines only.
"""

from __future__ import annotations

from typing import ClassVar

import lexic.compile.notation as _notation
from lexic.compile.artifact import CompiledGrammar
from lexic.compile.binding import RuleBinding, compute_binding
from lexic.compile.export import docstring_lines, field_type, value_str_type
from lexic.compile.foldkit import ALT, passthrough
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import get_flavour
from lexic.ir.base import IrNamedTuple, IrNone, IrNoneType, IrSelf, IrSeq
from lexic.ir.bind import IrBind
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
from lexic.parsing import FieldFold, ModelFold, RuleFold, parse_model

__all__ = [
    "MClass",
    "MField",
    "MModule",
    "module_grammar",
    "parse_module",
    "verify_module",
]

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


# ── module model records (the fold's output, on the spine) ───────────────


class MField(IrNamedTuple[str, str, bool]):
    """One field line: name, rendered type text, default presence."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    type_text: str
    has_default: bool = False


class MClass(IrNamedTuple[str, tuple, str, tuple, IrSelf, tuple]):
    """One class block; ``inline_grammar``/``inline_binds`` only under
    ``inline_tables`` exports (else ``IrNone`` / empty)."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    bases: tuple
    doc: str
    fields: tuple = ()
    inline_grammar: IrSelf = IrNone
    inline_binds: tuple = ()


class MModule(IrNamedTuple[str, tuple, tuple, tuple, IrSelf, bool]):
    """A parsed generated module."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    doc: str
    typing_names: tuple = ()
    ir_names: tuple = ()
    classes: tuple = ()
    grammar: IrSelf = IrNone
    has_bind: bool = False


# ── lexical pieces (statement layer — newline-significant) ───────────────

_NAME_FIRST = IrCharClass(_rng("A", "Z"), _rng("a", "z"), IrChr("_"))
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
    _rule(
        "m-body-line",
        IrSequence(_ref("m-field-line")),
        IrSequence(_ref("m-inline-grammar")),
        IrSequence(_ref("m-inline-binds")),
    ),
    _rule(
        "m-field-line",
        IrSequence(
            _lit("    "),
            _ref("m-name"),
            _lit(": "),
            _ref("m-type"),
            IrItem(IrRuleRef("m-default"), _OPT),
            _ref("m-nl"),
        ),
    ),
    _rule("m-default", IrSequence(_lit(" = None"))),
    # type expressions: T, list[T], Literal["…", …], unions with " | ".
    _rule(
        "m-type",
        IrSequence(_ref("m-type-atom"), IrItem(IrRuleRef("m-type-union"), _STAR)),
    ),
    _rule("m-type-union", IrSequence(_lit(" | "), _ref("m-type-atom"))),
    _rule(
        "m-type-atom",
        IrSequence(_ref("m-name"), IrItem(IrRuleRef("m-type-args"), _OPT)),
    ),
    _rule(
        "m-type-args",
        IrSequence(
            _lit("["),
            _ref("m-type-arg"),
            IrItem(IrRuleRef("m-more-type-arg"), _STAR),
            _lit("]"),
        ),
    ),
    _rule("m-more-type-arg", IrSequence(_lit(", "), _ref("m-type-arg"))),
    _rule(
        "m-type-arg",
        IrSequence(_ref("m-type")),
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
    # inline tables — the value's trailing ws swallows the next line's indent,
    # so the ``__binds__`` rule starts at its keyword (documented gap).
    _rule(
        "m-inline-grammar",
        IrSequence(_lit("    __grammar__: ClassVar[IrRule] = "), _ref("value")),
    ),
    _rule(
        "m-inline-binds",
        IrSequence(
            _lit(_BINDS_LIT),
            IrItem(IrRuleRef("m-bind-entry"), _PLUS),
            _lit("    }"),
            _ref("m-nl"),
        ),
    ),
    _rule(
        "m-bind-entry",
        IrSequence(
            _lit("        "),
            _ref("m-int"),
            _lit(': ("'),
            _ref("m-name"),
            _lit('", '),
            _ref("value"),
            _lit("),\n"),
        ),
    ),
    _rule("m-grammar-stmt", IrSequence(_lit("GRAMMAR: IrAst = "), _ref("value"))),
    _rule("m-bind-stmt", IrSequence(_lit("bind_module(GRAMMAR, globals())\n"))),
]


def module_grammar() -> IrAst:
    """The module self-grammar: statement skeleton + the notation rules.

    :returns: The merged ``IrAst`` (start ``m-module``).
    """
    notation_rules = [
        r for r in _notation.NOTATION_GRAMMAR.rules if str(r.name) != "start"
    ]
    return IrAst(IrSeq(*_MODULE_RULES, *notation_rules), "m-module")


# ── fold ctors (string composers + record assemblers) ────────────────────


def _text(*parts: object) -> str:
    """Join the string parts a rule's kids folded to (absent → '')."""
    return "".join(str(p) for p in parts if p is not None and p is not IrNone)


def _m_docstring(raw: str = "") -> str:
    return raw


def _m_dq_token(raw: str = "") -> str:
    return '"' + raw + '"'


def _m_sq_token(raw: str = "") -> str:
    return "'" + raw + "'"


def _m_name(head: str, tail: str = "") -> str:
    return head + tail


def _m_int(raw: str) -> int:
    return int(raw)


def _m_name_list(first: str, rest: list[object] | None = None) -> tuple:
    return (first, *(rest or []))


def _m_field(name: str, type_text: str, default: object = None) -> MField:
    return MField(name, type_text, default is not None)


def _m_type(atom: str, unions: list[object] | None = None) -> str:
    return _text(atom, *(unions or []))


def _m_type_union(atom: str) -> str:
    return " | " + atom


def _m_type_atom(name: str, args: object = None) -> str:
    return _text(name, args)


def _m_type_args(first: str, rest: list[object] | None = None) -> str:
    return "[" + _text(first, *(rest or [])) + "]"


def _m_more_type_arg(arg: str) -> str:
    return ", " + arg


def _m_inline_grammar(value: object) -> tuple:
    return ("grammar", value)


def _m_bind_entry(slot: int, name: str, value: object) -> tuple:
    return (slot, name, value)


def _m_inline_binds(entries: list[object] | None = None) -> tuple:
    return ("binds", tuple(entries or []))


def _m_body(lines: list[object] | None = None) -> tuple:
    return tuple(lines or [])


def _m_class(name: str, bases: tuple, doc: str, body: tuple = ()) -> MClass:
    fields = tuple(x for x in body if isinstance(x, MField))
    inline_grammar: IrSelf = IrNone
    inline_binds: tuple = ()
    for x in body:
        if isinstance(x, tuple) and len(x) == 2 and x[0] == "grammar":
            inline_grammar = x[1]
        elif isinstance(x, tuple) and len(x) == 2 and x[0] == "binds":
            inline_binds = x[1]
    return MClass(name, bases, doc, fields, inline_grammar, inline_binds)


def _m_imports(
    typing_names: tuple = (), compile_import: object = None, ir_names: object = None
) -> tuple:
    return (typing_names or (), compile_import is not None, ir_names or ())


def _m_typing_import(names: tuple) -> tuple:
    return names


def _m_import_paren(lines: list[object] | None = None) -> tuple:
    return tuple(lines or [])


def _m_module(
    doc: str,
    imports: tuple,
    classes: list[object] | None = None,
    grammar: object = None,
    bind: object = None,
) -> MModule:
    typing_names, has_compile, ir_names = imports
    del has_compile  # coherence is verify_module's job, via has_bind
    parsed = grammar if isinstance(grammar, IrSelf) else IrNone
    return MModule(
        doc,
        tuple(typing_names),
        tuple(ir_names),
        tuple(classes or []),
        parsed,
        bind is not None,
    )


def _fold_config() -> dict[str, RuleFold]:
    """The module fold table (merged over the notation's own)."""
    seq = RuleFold
    cfg = dict(_notation.NOTATION_FOLD.baked)  # the public lowered table
    cfg.update(
        {
            "m-module": seq(
                "sequence",
                _m_module,
                7,
                (
                    FieldFold(0, "model", "doc", 1),
                    FieldFold(3, "model", "imports", 1),
                    FieldFold(4, "models", "classes", 0),
                    FieldFold(5, "model", "grammar", 1),
                    FieldFold(6, "model", "bind", 0),
                ),
            ),
            "m-nl": seq("sequence", lambda: True, 1, ()),
            "m-docstring": seq(
                "sequence", _m_docstring, 3, (FieldFold(1, "text", "raw", 0),)
            ),
            "m-imports": seq(
                "sequence",
                _m_imports,
                7,
                (
                    FieldFold(2, "model", "typing_names", 0),
                    FieldFold(3, "model", "compile_import", 0),
                    FieldFold(4, "model", "ir_names", 1),
                ),
            ),
            "m-typing-import": seq(
                "sequence", _m_typing_import, 4, (FieldFold(1, "model", "names", 1),)
            ),
            "m-compile-import": seq("sequence", lambda: True, 1, ()),
            "m-ir-import": seq(
                "sequence", passthrough, 2, (FieldFold(1, "model", "v", 1),)
            ),
            "m-import-tail": ALT,
            "m-import-paren": seq(
                "sequence",
                _m_import_paren,
                3,
                (FieldFold(1, "models", "lines", 0),),
            ),
            "m-import-flat": seq(
                "sequence", passthrough, 2, (FieldFold(0, "model", "v", 1),)
            ),
            "m-import-line": seq(
                "sequence", passthrough, 3, (FieldFold(1, "model", "v", 1),)
            ),
            "m-name-list": seq(
                "sequence",
                _m_name_list,
                2,
                (FieldFold(0, "model", "first", 1), FieldFold(1, "models", "rest", 0)),
            ),
            "m-more-name": seq(
                "sequence", passthrough, 2, (FieldFold(1, "model", "v", 1),)
            ),
            "m-name": seq(
                "sequence",
                _m_name,
                2,
                (FieldFold(0, "text", "head", 1), FieldFold(1, "text", "tail", 0)),
            ),
            "m-int": seq("sequence", _m_int, 1, (FieldFold(0, "text", "raw", 1),)),
            "m-class-block": seq(
                "sequence",
                _m_class,
                8,
                (
                    FieldFold(1, "model", "name", 1),
                    FieldFold(3, "model", "bases", 1),
                    FieldFold(5, "model", "doc", 1),
                    FieldFold(7, "model", "body", 1),
                ),
            ),
            "m-body": ALT,
            "m-filled-body": seq(
                "sequence", _m_body, 3, (FieldFold(1, "models", "lines", 0),)
            ),
            "m-empty-body": seq("sequence", _m_body, 1, ()),
            "m-body-line": ALT,
            "m-field-line": seq(
                "sequence",
                _m_field,
                6,
                (
                    FieldFold(1, "model", "name", 1),
                    FieldFold(3, "model", "type_text", 1),
                    FieldFold(4, "model", "default", 0),
                ),
            ),
            "m-default": seq("sequence", lambda: True, 1, ()),
            "m-type": seq(
                "sequence",
                _m_type,
                2,
                (FieldFold(0, "model", "atom", 1), FieldFold(1, "models", "unions", 0)),
            ),
            "m-type-union": seq(
                "sequence", _m_type_union, 2, (FieldFold(1, "model", "atom", 1),)
            ),
            "m-type-atom": seq(
                "sequence",
                _m_type_atom,
                2,
                (FieldFold(0, "model", "name", 1), FieldFold(1, "model", "args", 0)),
            ),
            "m-type-args": seq(
                "sequence",
                _m_type_args,
                4,
                (FieldFold(1, "model", "first", 1), FieldFold(2, "models", "rest", 0)),
            ),
            "m-more-type-arg": seq(
                "sequence", _m_more_type_arg, 2, (FieldFold(1, "model", "arg", 1),)
            ),
            "m-type-arg": ALT,
            "m-str-token": ALT,
            "m-dq-token": seq(
                "sequence", _m_dq_token, 3, (FieldFold(1, "text", "raw", 0),)
            ),
            "m-sq-token": seq(
                "sequence", _m_sq_token, 3, (FieldFold(1, "text", "raw", 0),)
            ),
            "m-inline-grammar": seq(
                "sequence", _m_inline_grammar, 2, (FieldFold(1, "model", "value", 1),)
            ),
            "m-inline-binds": seq(
                "sequence",
                _m_inline_binds,
                4,
                (FieldFold(1, "models", "entries", 0),),
            ),
            "m-bind-entry": seq(
                "sequence",
                _m_bind_entry,
                7,
                (
                    FieldFold(1, "model", "slot", 1),
                    FieldFold(3, "model", "name", 1),
                    FieldFold(5, "model", "value", 1),
                ),
            ),
            "m-grammar-stmt": seq(
                "sequence", passthrough, 2, (FieldFold(1, "model", "v", 1),)
            ),
            "m-bind-stmt": seq("sequence", lambda: True, 1, ()),
            "m-gap": seq("sequence", lambda: None, 1, ()),
        }
    )
    return cfg


MODULE_GRAMMAR = module_grammar()
MODULE_FOLD: ModelFold = ModelFold.from_config(_fold_config())


def parse_module(text: str) -> MModule:
    """Parse an exported twin module into its :class:`MModule` model.

    :param text: The module source (the canonical exported layout).
    :returns: The parsed module model.
    :raises UnsupportedConstructError: When ``text`` is not a canonical
        generated module.
    """
    result = parse_model(MODULE_GRAMMAR, text, MODULE_FOLD)
    if not isinstance(result, MModule):
        raise UnsupportedConstructError(
            f"selfgrammar: module folded to {type(result).__name__!r}"
        )
    return result


# ── L2: the binding cross-check ──────────────────────────────────────────


def _expected_fields(
    bound: RuleBinding, rule: IrRule, class_by_rule: dict[str, str]
) -> tuple[MField, ...]:
    """The field records the exporter renders for ``bound`` — recomputed."""
    if bound.kind == "value_str":
        return (MField("value", value_str_type(rule), False),)
    if bound.kind == "alternation":
        return ()
    arm = next((a for a in rule.body if a), IrSequence())
    empty_arm = any(not a for a in rule.body)
    out = []
    for name, ibind in bound.fields.items():
        item = arm[ibind.item]
        optional = empty_arm or (ibind.mode != "models" and item.quantifier.lo == 0)
        type_str = field_type(ibind.mode, item, class_by_rule, optional=optional)
        out.append(MField(name, type_str, optional and ibind.mode != "models"))
    return tuple(out)


def _expected_doc(rule: IrRule, flavour_name: str) -> str:
    """The docstring CONTENT (between the triple quotes) for ``rule`` —
    exactly as the exporter renders it, backticks and wrap included."""
    rendered = docstring_lines(str(get_flavour(flavour_name).apply(rule)))
    text = "\n".join(line[4:] if line.startswith("    ") else line for line in rendered)
    return text[3:-3]  # strip the two triple-quote delimiters


def _collapse_wrap(doc: str) -> str:
    """Undo the exporter's docstring wrap: newline + indent → one space."""
    out = []
    for i, line in enumerate(doc.split("\n")):
        out.append(line if i == 0 else line.lstrip(" "))
    return " ".join(out)


def _check(cond: bool, message: str) -> None:
    if not cond:
        raise UnsupportedConstructError(f"verify_module: {message}")


class _VerifyCtx(IrNamedTuple[dict, str, bool]):
    """The per-module verify context threaded through the class checks."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    class_by_rule: dict
    flavour: str
    inline: bool


def _verify_class(
    mclass: MClass, bound: RuleBinding, rule: IrRule, ctx: _VerifyCtx
) -> None:
    """One class block against its binding."""
    class_by_rule, flavour_name, inline = ctx
    _check(
        mclass.name == bound.class_name,
        f"class {mclass.name!r} where {bound.class_name!r} expected",
    )
    expected_bases = bound.parent_class_names or ("GrammarModel",)
    _check(
        tuple(mclass.bases) == tuple(expected_bases),
        f"{mclass.name}: bases {mclass.bases!r} != {expected_bases!r}",
    )
    _check(
        _collapse_wrap(mclass.doc) == _collapse_wrap(_expected_doc(rule, flavour_name)),
        f"{mclass.name}: docstring drift",
    )
    expected = _expected_fields(bound, rule, class_by_rule)
    _check(
        tuple(mclass.fields) == expected,
        f"{mclass.name}: fields {tuple(mclass.fields)!r} != {expected!r}",
    )
    if inline:
        _check(
            mclass.inline_grammar == rule,
            f"{mclass.name}: inline __grammar__ != codegen rule",
        )
        expected_binds = tuple(
            (b.item, name, IrBind(b.item, b.mode, b.semantic))
            for name, b in bound.fields.items()
        )
        _check(
            tuple(mclass.inline_binds) == expected_binds,
            f"{mclass.name}: inline __binds__ drift",
        )
    else:
        _check(
            isinstance(mclass.inline_grammar, IrNoneType) and not mclass.inline_binds,
            f"{mclass.name}: inline tables in a bind-mode module",
        )


def verify_module(compiled: CompiledGrammar, text: str) -> MModule:
    """L2: parse ``text`` and cross-check it against ``compiled``'s binding.

    The expected values are recomputed with the SAME functions the exporter
    rendered from (`field_type`, `value_str_type`, `docstring_lines`,
    `compute_binding`), so a disagreement means the FILE drifted.

    :param compiled: The grammar the module claims to be the twin of.
    :param text: The module source.
    :returns: The parsed module model (for further inspection).
    :raises UnsupportedConstructError: On any drift, with the first
        disagreement named.
    """
    module = parse_module(text)
    _check(
        module.grammar == compiled.grammar,
        "GRAMMAR does not equal the compiled canonical AST",
    )
    inline = not module.has_bind
    binding = compute_binding(compiled.codegen_grammar)
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    class_by_rule = {b.rule_name: b.class_name for b in binding}
    _check(
        len(module.classes) == len(binding),
        f"{len(module.classes)} classes for {len(binding)} bindings",
    )
    ctx = _VerifyCtx(class_by_rule, compiled.flavour, inline)
    for mclass, bound in zip(module.classes, binding):
        _verify_class(mclass, bound, rules[bound.rule_name], ctx)
    return module
