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

from typing import Callable, ClassVar

import lexic.compile.notation.parse as _notation
from lexic.compile.foldkit import (
    AuthoredRule,
    first_rest,
    product_rules,
)
from lexic.compile.module.rules import module_grammar
from lexic.compile.product import rules_by_name
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrNamedTuple,
    IrNone,
    IrSelf,
)
from lexic.parsing import ModelBinding, parse_model
from lexic.parsing.product import CaptureMode, CaptureSpec, LoweringOwned

__all__ = [
    "MClass",
    "MField",
    "MModule",
    "module_grammar",
    "parse_module",
]

# ── module model records (the fold's output, on the spine) ───────────────


class MField(IrNamedTuple[str, str, bool]):
    """One field line: name, rendered type text, default presence."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    type_text: str
    has_default: bool = False


class MClass(IrNamedTuple[str, tuple, str, tuple, IrSelf, int, tuple]):
    """One class block; the inline tables only under ``inline_tables`` exports
    (else ``IrNone`` / ``0`` / empty)."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    bases: tuple
    doc: str
    fields: tuple = ()
    inline_grammar: IrSelf = IrNone
    inline_shape: int = 0
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


def _m_field_tail(
    name: str,
    atom: str,
    unions: list[object] | None = None,
    default: object = None,
) -> MField:
    return MField(name, _text(atom, *(unions or [])), default is not None)


def _m_type_union(atom: str) -> str:
    return " | " + atom


def _m_type_atom(name: str, args: object = None) -> str:
    return _text(name, args)


def _m_type_args(first: str, rest: list[object] | None = None) -> str:
    return "[" + _text(*first_rest(first, rest)) + "]"


def _m_arg_sep(arg: str) -> str:
    return ", " + arg


def _m_inline_grammar(value: object) -> tuple:
    return ("grammar", value)


def _m_inline_shape(value: object) -> tuple:
    return ("shape", value)


def _m_bind_entry(slot: int, name: str, value: object) -> tuple:
    return (slot, name, value)


def _m_inline_binds(entries: list[object] | None = None) -> tuple:
    return ("binds", tuple(entries or []))


def _m_body(lines: list[object] | None = None) -> tuple:
    return tuple(lines or [])


def _m_class(name: str, bases: tuple, doc: str, body: tuple = ()) -> MClass:
    fields = tuple(x for x in body if isinstance(x, MField))
    inline_grammar: IrSelf = IrNone
    inline_shape = 0
    inline_binds: tuple = ()
    for x in body:
        if not (isinstance(x, tuple) and len(x) == 2):
            continue
        if x[0] == "grammar":
            inline_grammar = x[1]
        elif x[0] == "shape":
            inline_shape = int(x[1])
        elif x[0] == "binds":
            inline_binds = x[1]
    return MClass(name, bases, doc, fields, inline_grammar, inline_shape, inline_binds)


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


def _true() -> bool:
    """A structural rule whose match is its own evidence — it folds to ``True``.

    Named rather than a lambda so the product half can register it: a symbol is
    a name in a registry, and four separate lambdas would be four names for one
    behaviour.
    """
    return True


def _none() -> None:
    """A structural rule that folds to nothing at all."""
    return None


MODULE_GRAMMAR = module_grammar()


def parse_module(text: str) -> MModule:
    """Parse an exported twin module into its :class:`MModule` model.

    :param text: The module source (the canonical exported layout).
    :returns: The parsed module model.
    :raises UnsupportedConstructError: When ``text`` is not a canonical
        generated module.
    """
    result = parse_model(MODULE_GRAMMAR, text, MODULE_BINDING)
    if not isinstance(result, MModule):
        raise UnsupportedConstructError(
            f"selfgrammar: module folded to {type(result).__name__!r}"
        )
    return result


# ── the same rules in the product vocabulary ──────────────────────────────

MODULE_SYMBOLS: dict[str, Callable[..., object]] = _notation.NOTATION_SYMBOLS | {
    fn.__name__.lstrip("_"): fn
    for fn in (
        _true,
        _none,
        _m_module,
        _m_docstring,
        _m_imports,
        _m_typing_import,
        _m_import_paren,
        _m_name,
        _m_class,
        _m_body,
        _m_field_tail,
        _m_type_union,
        _m_type_atom,
        _m_type_args,
        _m_arg_sep,
        _m_dq_token,
        _m_sq_token,
        _m_inline_grammar,
        _m_inline_shape,
        _m_inline_binds,
        _m_bind_entry,
    )
}
"""This surface's transforms by name, over the notation's — the self-grammar
EXTENDS the notation, so its whitelist does too. Keyed by each transform's own
name so a rename cannot leave the registry pointing at the old spelling."""

_ONE = int(CaptureMode.ONE)
_MANY = int(CaptureMode.MANY)
_TEXT = int(CaptureMode.TEXT)

MODULE_RULES: dict[str, AuthoredRule] = _notation.NOTATION_RULES | {
    "m-module": AuthoredRule(
        "m_module",
        (
            CaptureSpec(_ONE, 0),
            CaptureSpec(_ONE, 3),
            CaptureSpec(_MANY, 4),
            CaptureSpec(_ONE, 5),
            CaptureSpec(_ONE, 7),
        ),
        ("doc", "imports", "classes", "grammar", "bind"),
        8,
    ),
    "m-nl": AuthoredRule("true", (), (), 1),
    "m-docstring": AuthoredRule("m_docstring", (CaptureSpec(_TEXT, 1),), ("raw",), 3),
    "m-imports": AuthoredRule(
        "m_imports",
        (CaptureSpec(_ONE, 2), CaptureSpec(_ONE, 3), CaptureSpec(_ONE, 4)),
        ("typing_names", "compile_import", "ir_names"),
        7,
    ),
    "m-typing-import": AuthoredRule(
        "m_typing_import", (CaptureSpec(_ONE, 1),), ("names",), 4
    ),
    "m-compile-import": AuthoredRule("true", (), (), 1),
    "m-ir-import": AuthoredRule("passthrough", (CaptureSpec(_ONE, 1),), ("v",), 2),
    "m-import-tail": AuthoredRule(""),
    "m-import-paren": AuthoredRule(
        "m_import_paren", (CaptureSpec(_MANY, 1),), ("lines",), 3
    ),
    "m-import-flat": AuthoredRule("passthrough", (CaptureSpec(_ONE, 0),), ("v",), 2),
    "m-import-line": AuthoredRule("passthrough", (CaptureSpec(_ONE, 1),), ("v",), 3),
    "m-name-list": AuthoredRule(
        "first_rest",
        (CaptureSpec(_ONE, 0), CaptureSpec(_MANY, 1)),
        ("first", "rest"),
        2,
    ),
    "m-more-name": AuthoredRule("passthrough", (CaptureSpec(_ONE, 1),), ("v",), 2),
    "m-name": AuthoredRule(
        "m_name", (CaptureSpec(_TEXT, 0), CaptureSpec(_TEXT, 1)), ("head", "tail"), 2
    ),
    "m-field-name": AuthoredRule(
        "m_name", (CaptureSpec(_TEXT, 0), CaptureSpec(_TEXT, 1)), ("head", "tail"), 2
    ),
    "m-int": AuthoredRule("decode_int", (CaptureSpec(_TEXT, 0),), ("raw",), 1),
    "m-class-block": AuthoredRule(
        "m_class",
        (
            CaptureSpec(_ONE, 1),
            CaptureSpec(_ONE, 3),
            CaptureSpec(_ONE, 5),
            CaptureSpec(_ONE, 7),
        ),
        ("name", "bases", "doc", "body"),
        8,
    ),
    "m-body": AuthoredRule(""),
    "m-filled-body": AuthoredRule("m_body", (CaptureSpec(_MANY, 1),), ("lines",), 3),
    "m-empty-body": AuthoredRule("m_body", (), (), 1),
    "m-body-line": AuthoredRule(""),
    "m-indented-line": AuthoredRule("passthrough", (CaptureSpec(_ONE, 1),), ("v",), 2),
    "m-line-tail": AuthoredRule(""),
    "m-field-tail": AuthoredRule(
        "m_field_tail",
        (
            CaptureSpec(_ONE, 0),
            CaptureSpec(_ONE, 2),
            CaptureSpec(_MANY, 3),
            CaptureSpec(_ONE, 4),
        ),
        ("name", "atom", "unions", "default"),
        6,
    ),
    "m-default": AuthoredRule("true", (), (), 1),
    "m-type-union": AuthoredRule("m_type_union", (CaptureSpec(_ONE, 1),), ("atom",), 2),
    "m-type-atom": AuthoredRule(
        "m_type_atom", (CaptureSpec(_ONE, 0), CaptureSpec(_ONE, 1)), ("name", "args"), 2
    ),
    "m-type-args": AuthoredRule(
        "m_type_args",
        (CaptureSpec(_ONE, 1), CaptureSpec(_MANY, 2)),
        ("first", "rest"),
        4,
    ),
    "m-arg-tail": AuthoredRule(""),
    "m-arg-union": AuthoredRule("m_type_union", (CaptureSpec(_ONE, 1),), ("atom",), 2),
    "m-arg-sep": AuthoredRule("m_arg_sep", (CaptureSpec(_ONE, 1),), ("arg",), 2),
    "m-arg-unit": AuthoredRule(""),
    "m-str-token": AuthoredRule(""),
    "m-dq-token": AuthoredRule("m_dq_token", (CaptureSpec(_TEXT, 1),), ("raw",), 3),
    "m-sq-token": AuthoredRule("m_sq_token", (CaptureSpec(_TEXT, 1),), ("raw",), 3),
    "m-grammar-tail": AuthoredRule(
        "m_inline_grammar", (CaptureSpec(_ONE, 1),), ("value",), 3
    ),
    "m-shape-tail": AuthoredRule(
        "m_inline_shape", (CaptureSpec(_ONE, 1),), ("value",), 3
    ),
    "m-inline-binds": AuthoredRule(
        "m_inline_binds", (CaptureSpec(_MANY, 2),), ("entries",), 5
    ),
    "m-bind-entry": AuthoredRule(
        "m_bind_entry",
        (CaptureSpec(_ONE, 1), CaptureSpec(_ONE, 3), CaptureSpec(_ONE, 5)),
        ("slot", "name", "value"),
        7,
    ),
    "m-grammar-stmt": AuthoredRule("passthrough", (CaptureSpec(_ONE, 1),), ("v",), 3),
    "m-bind-stmt": AuthoredRule("true", (), (), 1),
    "m-gap": AuthoredRule("none", (), (), 1),
}
"""Every rule of the module self-grammar in the product vocabulary, over the
notation's own — the same merge the fold table performs, said once more in the
form the engines will run."""

MODULE_PRODUCT = product_rules(MODULE_RULES)
"""The assembled product: one ``RuleProduct`` per rule, symbol keys pooled, and
the code each rule name resolves to."""

MODULE_BINDING = ModelBinding(
    rules_by_name(MODULE_PRODUCT.rules, MODULE_PRODUCT.codes),
    LoweringOwned(symbols=MODULE_PRODUCT.symbols, registry=MODULE_SYMBOLS),
)
"""What this surface hands a parse entry — its product, with the fold its
completions still read."""
