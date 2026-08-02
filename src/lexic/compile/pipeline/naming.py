"""What a generated class and its fields are CALLED.

Grammar names are not Python names, and a field name has to survive its
rule being renamed, reordered or repeated. Everything here is spelling: it
reads the grammar and produces identifiers and decides nothing about
shape — which is why it is a leaf, imported by the binding view and
importing nothing back."""

from __future__ import annotations

import keyword
from collections.abc import Sequence
from functools import cache

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrDispatch,
    IrLambda,
    IrLiteral,
    IrNode,
    IrNone,
    IrReturn,
    IrRuleRef,
    IrSelf,
    IrStr,
    IrTypeMap,
    IrVisitor,
)

_ASCII_ALNUM: frozenset[str] = frozenset(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)
"""``[0-9A-Za-z]`` as a set — ASCII only, unlike :meth:`str.isalnum`."""
_DROP_BRACKETS = str.maketrans("", "", "[]^")
"""``[][^]`` as a delete table."""
_SLUG_CHARS: frozenset[str] = frozenset("0123456789abcdefghijklmnopqrstuvwxyz_")
"""``[a-z0-9_]`` — what survives in a slug."""
CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[0-9A-Fa-f]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[A-Za-z]": "letter",
    "[0-9A-Z_a-z]": "alnum",
}
LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
}
_RESERVED_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "GrammarModel",
        "ClassVar",
        "Literal",
        "IrAlphabet",
        "IrAlternation",
        "IrAst",
        "IrBind",
        "IrCharClass",
        "IrChr",
        "IrItem",
        "IrLiteral",
        "IrNone",
        "IrNot",
        "IrQuantifier",
        "IrRange",
        "IrRule",
        "IrRuleRef",
        "IrSeq",
        "IrSequence",
        "IrStr",
    }
)
"""Module-scope names a generated twin module binds — the exporter's header
imports (``GrammarModel``, ``ClassVar``/``Literal`` from ``typing`` when
used) plus the IR constructor names that appear in the emitted notation. A
generated class of the same name would shadow them in that source; lowercase
(``bind_module``) and UPPERCASE (``GRAMMAR``) bindings can never collide
with a PascalCase class name. Drift-pinned against a real export by
``test_reserved_class_names_cover_the_export_header``."""
RESERVED_FIELD_NAMES: frozenset[str] = frozenset(keyword.kwlist) | frozenset(
    {
        # ``GrammarModel``'s whole public surface — the record spine it lives
        # on (settled 10): a rule named after one of these would generate a
        # field shadowing the IrSelf/tuple protocol or a GrammarModel method.
        # The nine spine-protocol names (``bind``/``bound``/``bound_type``/
        # ``children``/``count``/``ensure``/``eval``/``index``/``rebuild``)
        # shadow the inherited IrSelf/tuple protocol; ``dump`` and
        # ``emit_parts`` are GrammarModel methods. Only these curated names
        # are reserved — an arbitrary ``model_*`` name unmangles.
        "bind",
        "bound",
        "bound_fields",
        "bound_type",
        "children",
        "count",
        "dump",
        "emit_parts",
        "ensure",
        "eval",
        "fast_construct",
        "index",
        "rebuild",
        "repr_args",
        "semantic_dump",
        "to_grammar",
        "to_text",
    }
)
"""Field names that would break or shadow the generated model: Python keywords
(a ``class: ...`` annotation is a SyntaxError) and ``GrammarModel``'s whole
public surface (its methods plus the inherited IrSelf/tuple protocol). Curated
as a literal — importing ``lexic.model`` here would couple this module to the
runtime — and drift-pinned by a test against the real class."""


def _name_parts(rule_name: str) -> list[str]:
    """Split on ``-`` and ``_``, keeping the empty parts between adjacent ones.

    :param rule_name: The (canonical) rule name.
    :returns: The word parts, in order.
    """
    return rule_name.replace("-", "_").split("_")


def class_name_for(rule_name: str) -> str:
    """PascalCase class name for a rule; reserved names get a ``_`` suffix.

    Reserved: Python keywords and the emitted module's own header bindings.

    :param rule_name: The (canonical) rule name.
    :returns: A valid Python class name (``jp-char`` → ``JpChar``,
        ``true`` → ``True_``, ``ir-rule`` → ``IrRule_``).
    """
    pascal = "".join(part[:1].upper() + part[1:] for part in _name_parts(rule_name))
    reserved = keyword.iskeyword(pascal) or pascal in _RESERVED_CLASS_NAMES
    return pascal + "_" if reserved else pascal


def _to_underscores(text: str) -> str:
    """Rewrite every non-ASCII-alphanumeric character to ``_``.

    :param text: Arbitrary text.
    :returns: The rewritten text, same length.
    """
    return "".join(c if c in _ASCII_ALNUM else "_" for c in text)


def _keep_slug(text: str) -> str:
    """Drop every character outside ``[a-z0-9_]``.

    :param text: Arbitrary text.
    :returns: The surviving characters, in order.
    """
    return "".join(c for c in text if c in _SLUG_CHARS)


def _collapse_underscores(text: str) -> str:
    """Collapse each run of ``_`` to one.

    :param text: Arbitrary text.
    :returns: The text with no adjacent underscores.
    """
    out: list[str] = []
    previous_underscore = False
    for c in text:
        if c == "_" and previous_underscore:
            continue
        previous_underscore = c == "_"
        out.append(c)
    return "".join(out)


def _literal_token(text: str) -> str:
    """Name a literal: library hit, ASCII token of its value, or ``lit``."""
    named = LITERAL_NAMES.get(text)
    if named:
        return named
    token = _to_underscores(text).strip("_").lower()[:12]
    return token or "lit"


def _charclass_key(cc: IrCharClass) -> str:
    """The bracketed lookup key for a char class (``[0-9]``)."""
    return f"[{cc.pattern()}]"


def _pattern_slug(key: str) -> str:
    """Identifier-safe slug of a bracketed pattern; empty when nothing survives."""
    slug = key.translate(_DROP_BRACKETS).replace("-", "_").lower()
    slug = _collapse_underscores(_keep_slug(slug).strip("_"))
    if not slug:
        return ""
    if slug[0].isdigit():
        slug = "cc_" + slug
    return slug[:12].strip("_")


def _ref_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Tier-1 body: a rule ref names its field after the rule."""
    return IrStr(str(n).replace("-", "_"))


def _literal_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Tier-2 body: a (quantified) literal always names itself — never tier-3."""
    return IrStr(_literal_token(str(n)))


def _charclass_hint(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Hint body: char class names from the library, its slug, or ``cc``."""
    assert isinstance(n, IrCharClass)
    key = _charclass_key(n)
    return IrStr(CHARCLASS_NAMES.get(key) or _pattern_slug(key) or "cc")


def _charclass_field(_d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Tier-2 body: char class names only on a library hit, else tier-3."""
    assert isinstance(n, IrCharClass)
    named = CHARCLASS_NAMES.get(_charclass_key(n))
    return IrStr(named) if named else IrNone


def _group_field(d: IrSelf, n: IrSelf, nc: Sequence[IrSelf]) -> IrSelf:
    """Tier-2 body: group named by its hint unless the hint is a bare fallback."""
    hint = str(_group_hint(d, n, nc))
    return IrNone if hint in {"inline", "lit", "cc"} else IrStr(hint)


def _alphabet_field(_d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Name a token atom ``tok`` — the token-terminal field.

    A token terminal (an ``IrAlphabet``; negation lives inside it) captures its
    token's text, like a char class, so it takes a stable ``tok`` base
    (collision-numbered ``tok2``… in item order).
    """
    return IrStr("tok")


@cache
def has_ruleref(node: IrNode) -> bool:
    """True if any :class:`IrRuleRef` exists in the node subtree.

    Short-circuits on first hit: the singleton :class:`IrVisitor` carries an
    :class:`IrReturn` body for :class:`IrRuleRef`, which raises a control-flow
    exception caught by :meth:`IrDispatch.apply`. Cached on node identity.

    :param node: Root of the subtree to scan.
    :returns: ``True`` if an :class:`IrRuleRef` was found, else ``False``.
    """
    return _HAS_RULEREF.apply(node) is not IrNone


def _group_hint(d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf]) -> IrStr:
    """Hint body: ref-bearing group → ``kind``; else named from its first atom."""
    assert isinstance(n, IrAlternation)
    if has_ruleref(n):
        return IrStr("kind")
    if not (len(n) and len(n[0])):
        return IrStr("inline")
    return IrStr(str(_HINT.eval(d, n[0][0].atom, ())))


_HAS_RULEREF: IrVisitor = IrVisitor(
    actions=IrTypeMap(IrAction(IrRuleRef, IrReturn())),
)
TIER2: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_literal_field)),
        IrAction(IrRuleRef, IrLambda(_ref_field)),
        IrAction(IrCharClass, IrLambda(_charclass_field)),
        IrAction(IrAlphabet, IrLambda(_alphabet_field)),
        IrAction(IrAlternation, IrLambda(_group_field)),
    ),
)
_HINT: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrLiteral, IrLambda(_literal_field)),
        IrAction(IrRuleRef, IrLambda(_ref_field)),
        IrAction(IrCharClass, IrLambda(_charclass_hint)),
        IrAction(IrAlphabet, IrLambda(_alphabet_field)),
        IrAction(IrAlternation, IrLambda(_group_hint)),
    ),
)
