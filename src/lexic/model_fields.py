"""What a field's own grammar ITEM admits — the per-field construction checks.

Hand construction (``cls(**kwargs)`` — tests, and the Earley completion path)
runs these; the trusted parse paths bypass ``__new__`` entirely, so the PDA hot
path pays nothing. Every check reads the field's own grammar item — char-class
membership + length bounds, ``Literal``-arm membership, the token field's
spelling — with no engine call and no regex compilation.

The checks that ask whether a value IS a sub-model are not here: they read the
model spine rather than a grammar item, so they stay beside the class that
defines what a sub-model is.

R7 holes (typed plain ``str`` and never validated, left unchecked
deliberately): a bound (always quantified) literal field, and a ref-bearing
``gtext`` group. A value_str whose value is a single char class or a lone
literal is likewise not checked — the char-class check is bind-driven (it reads
``IrBind.item.quantifier``) and a value_str field carries no bind; only the
multi-arm ``Literal[...]`` value_str is checked.
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.exceptions import FieldValidationError
from lexic.ir import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNamedTuple,
    IrNone,
    IrQuantifier,
    IrRule,
    IrSelf,
)

UNIT = IrQuantifier(1, 1)
"""The quantifier a single, unrepeated item carries."""


class FieldCheck(IrNamedTuple[str, object, str]):
    """State carrier for the per-field check dispatch (the ``d`` slot).

    Passed as the dispatcher to the field-check table so each open body reads
    the field name, its runtime value and its fold mode without a closure (the
    ``_FieldTyper`` idiom). ``_child_attrs`` is empty — none of the three is an
    IR-node child.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    field: str
    value: object
    mode: str


def uncovered_char(cc: IrCharClass, value: str) -> str | None:
    """The first char of ``value`` not covered by ``cc``, or ``None``.

    Tests membership against the class's interval cover, so a ``[^...]``
    complement is never materialised point-by-point.

    :param cc: The char class the field's characters must fall within.
    :param value: The field's string value.
    :returns: The first out-of-class character, or ``None`` if all are covered.
    """
    spans = cc.intervals()
    for ch in value:
        point = ord(ch)
        if not any(lo <= point <= hi for lo, hi in spans):
            return ch
    return None


def check_charclass(d: FieldCheck, n: IrSelf, nc: Sequence[IrSelf]) -> IrSelf:
    """Text-mode char class: every char covered, length within the quantifier."""
    assert isinstance(n, IrCharClass)
    value = d.value
    if not isinstance(value, str):
        raise FieldValidationError(
            f"field {d.field!r}: expected a str for char-class field, got "
            f"{type(value).__name__}"
        )
    bad = uncovered_char(n, value)
    if bad is not None:
        raise FieldValidationError(
            f"field {d.field!r}: character {bad!r} is not in [{n.pattern()}]"
        )
    quantifier = cast(IrItem, nc[0]).quantifier
    if len(value) not in quantifier:
        raise FieldValidationError(
            f"field {d.field!r}: length {len(value)} out of bounds {quantifier!r}"
        )
    return IrNone


def check_literal(_d: FieldCheck, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """R7 hole: a bound (quantified) literal field is plain ``str`` — unchecked."""
    return IrNone


def check_token(d: FieldCheck, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Text-mode token: the field holds the token's text.

    A plain ``str`` (an R7 hole like a bound literal) — the vocab-membership
    check needs a tokenizer, which is not a per-field intrinsic. The atom is
    always an ``IrAlphabet`` (negation lives inside it; char negation is
    canonicalised away).
    """
    if not isinstance(d.value, str):
        raise FieldValidationError(
            f"field {d.field!r}: expected a str for token field, got "
            f"{type(d.value).__name__}"
        )
    return IrNone


def value_str_literals(rule: IrRule) -> frozenset[str] | None:
    """The allowed set of a ``Literal[...]`` value_str rule, else ``None``.

    Mirrors the emitter's ``value_str_type`` ``Literal`` branch: a body whose
    every arm is a single unit-quantified literal (and which is not the
    single-item shortcut) is typed ``Literal[...]`` and membership-checked. A
    single-item value (str / char class) and any ref-bearing body are typed
    plain ``str`` / a pattern and are not checked here.

    :param rule: The value_str class's own ``__grammar__`` rule.
    :returns: The permitted literal strings, or ``None`` when not a
        ``Literal[...]`` value_str.
    """
    arms = [arm for arm in rule.body if arm]
    if len(arms) == 1 and len(arms[0]) == 1:
        return None
    if all(
        len(arm) == 1
        and isinstance(arm[0].atom, IrLiteral)
        and arm[0].quantifier == UNIT
        for arm in rule.body
    ):
        return frozenset(str(arm[0].atom) for arm in arms)
    return None
