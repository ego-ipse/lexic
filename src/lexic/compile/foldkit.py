"""Shared authored-fold vocabulary — the build-path unification seed.

Every hand-authored grammar+fold pair in the compile package (the notation and
the module self-grammar today, future authored surfaces tomorrow) repeats the
same idioms. This module is their single home, so a fifth authored surface
never copies a fourth variant.

Two tiers live here:

- **the shared idioms** — the identity ctor (:func:`passthrough`), the
  first+rest list collector (:func:`first_rest`), the int decode
  (:func:`decode_int`), and the absent-default tail (:func:`absent_tail` with
  its :data:`ABSENT` sentinel), pooled in :data:`FOLD_SYMBOLS`;
- **the authored-product vocabulary** — :class:`AuthoredRule`,
  :class:`AuthoredProduct`, :data:`ALT_PRODUCT` and :func:`product_rules`,
  which say what a surface's rules capture and which transform completes them.

An authored record never holds a callable. A rule names its transform by
registry KEY, and lowering resolves that key through the surface's own
whitelist — the no-``eval`` boundary, drawn once, on the product side.
Everything a completion applies is therefore reachable by name from
:data:`FOLD_SYMBOLS` or a surface's extension of it, and a key that is not
there refuses with words rather than being called.

Transforms are applied BY KEYWORD, and that is a requirement rather than a
convention: :func:`absent_tail` distinguishes an omitted optional from a real
value, and only omission — not a filled placeholder — can express that.
Surface-specific transforms that are not shared stay on their own surface and
join that surface's registry.
"""

from __future__ import annotations

from typing import Callable, Mapping, NamedTuple, Sequence, cast

from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    ExprProgram,
    PassOp,
    RuleProduct,
    SymbolConstructor,
    SymbolExpr,
)

__all__ = [
    "ABSENT",
    "ALT_PRODUCT",
    "AuthoredProduct",
    "AuthoredRule",
    "FOLD_SYMBOLS",
    "absent_tail",
    "decode_int",
    "first_rest",
    "passthrough",
    "product_rules",
]


# ── the shared idioms ─────────────────────────────────────────────────────


def passthrough(v: object) -> object:
    """A single-field sequence rule's identity ctor.

    :param v: The one bound child.
    :returns: ``v`` unchanged.
    """
    return v


ABSENT: object = object()
"""The shared "no value supplied" marker for an omitted trailing group.

An optional tail that matched empty folds to this (via :func:`absent_tail`);
a surface's strictness pass filters or rejects it (``notation``'s ``_arglist``
refuses a bare comma anywhere but last)."""


def decode_int(raw: object) -> int:
    """The digit-run → ``int`` decode, under a name that takes a KEYWORD.

    The builtin is positional-only. A fold body reads a positional argument
    channel and can call it; a completion applies its transform by keyword, so
    that an absent capture can be OMITTED rather than filled. The registry
    carries both spellings of the one decode for exactly as long as both
    application conventions exist — the fold half, and ``"int"`` with it, goes
    when reducer semantics lower.

    :param raw: The matched digit run.
    :returns: Its integer value.
    """
    return int(cast(str, raw))


def first_rest(first: object, rest: Sequence[object] | None = None) -> tuple:
    """Head element prepended to the repeated tail — the list collector.

    :param first: The head element.
    :param rest: The repeated tail (``None``/empty ⇒ just the head).
    :returns: ``(first, *rest)`` as a tuple.
    """
    return (first, *(rest or ()))


def absent_tail(**kwargs: object) -> object:
    """An optional trailing group: its value, or :data:`ABSENT` when omitted.

    A kwargs ctor (not a channel body): the single optional field arrives BY
    KEYWORD when the tail matched — any value, **including
    :data:`~lexic.ir.base.IrNone`** as a legitimate argument — and an empty call
    means the tail matched nothing. Only the keyword mechanism can say that:
    the channel adapter fills an omitted optional with ``IrNone``, which would
    be indistinguishable from a real ``IrNone`` value, so this idiom stays a
    keyword ctor (reused via :class:`~lexic.ir.base.IrLambda`, field-name-generic
    through ``**kwargs``).

    :returns: The tail's folded value when present, else :data:`ABSENT`.
    """
    for value in kwargs.values():
        return value
    return ABSENT


FOLD_SYMBOLS: dict[str, Callable[..., object]] = {
    "decode_int": decode_int,
    "first_rest": first_rest,
    "passthrough": passthrough,
    "absent_tail": absent_tail,
}
"""The curated transform registry — the no-``eval`` boundary an authored
product's symbol keys resolve through. Every reachable name is a shared idiom
callable; a surface adds a symbol here, or extends this table with its own, to
make a transform nameable from a record that holds no callable."""


# ── authored-fold construction ────────────────────────────────────────────


# ── authored-product construction ─────────────────────────────────────────


class AuthoredRule(NamedTuple):
    """One authored surface rule, said in the product vocabulary.

    Everything a completion needs and nothing it does not: which transform
    runs, what the rule captures, which keyword each capture fills, which may
    be absent, and how wide the arm is. The transform is a registry KEY —
    an authored record never holds a callable.

    :ivar symbol: The registry key the completion applies; ``""`` is the
        alternation pass-through, which applies nothing.
    :ivar captures: What each captured occurrence hands the completion.
    :ivar names: The keyword each capture fills, in capture order.
    :ivar n_items: How many items the rule's sequence arm has.
    :ivar optional: Capture indices that may be absent, and are then OMITTED
        from the keywords rather than filled with anything.
    :ivar matched: The keyword the rule's OWN matched extent fills — the
        ``value_str`` shape, whose value has no capture to point at.
    """

    symbol: str
    captures: tuple[CaptureSpec, ...] = ()
    names: tuple[str, ...] = ()
    n_items: int = 0
    optional: tuple[int, ...] = ()
    matched: str = ""


class AuthoredProduct(NamedTuple):
    """One authored surface's rules in the product vocabulary.

    The half of an authored surface the engines will run. A rule that applies
    a transform names it; the name is resolved to a callable once, by
    lowering, through the surface's own registry — so nothing here holds a
    callable and no surface can put one on a completion by hand.

    :ivar rules: One :class:`RuleProduct` per rule, in contextual-code order.
    :ivar symbols: The authored constructors the rules name, in operand order.
    :ivar codes: Rule name → its contextual code.
    """

    rules: tuple[RuleProduct, ...]
    symbols: tuple[SymbolConstructor, ...]
    codes: dict[str, int]


ALT_PRODUCT = RuleProduct((CaptureSpec(int(CaptureMode.ONE), 0),), PassOp(0))
"""The alternation pass-through as a product: one child, handed on unchanged.

An alternation rule matches exactly one arm, so slot 0 IS the matched arm and
passing it through is the whole completion — the same thing :data:`ALT` says
in the fold vocabulary. It declares no arm width: there is no sequence arm to
count, and nothing that passes a child through asks how wide one is."""


def product_rules(authored: Mapping[str, AuthoredRule]) -> AuthoredProduct:
    """Assemble one surface's authored rules into its product.

    Symbol constructors are pooled by their whole record, so a transform
    several rules apply through the SAME keywords occupies one operand row
    while one applied through different keywords gets its own — which is the
    honest granularity, because the keywords are half of what an application
    is.

    :param authored: Rule name → its authored rule, in rule order.
    :returns: The surface's product half.
    """
    rules: list[RuleProduct] = []
    symbols: list[SymbolConstructor] = []
    codes: dict[str, int] = {}
    for name, rule in authored.items():
        codes[name] = len(rules)
        if not rule.symbol:
            rules.append(ALT_PRODUCT)
            continue
        entry = SymbolConstructor(rule.symbol, rule.names, rule.optional, rule.matched)
        if entry not in symbols:
            symbols.append(entry)
        rules.append(
            RuleProduct(
                rule.captures,
                ExprProgram((SymbolExpr(symbols.index(entry)),)),
                rule.n_items,
            )
        )
    return AuthoredProduct(tuple(rules), tuple(symbols), codes)
