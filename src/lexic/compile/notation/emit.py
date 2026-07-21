"""The IR-constructor notation's emit half — IR → formatted notation text.

The layout twin of ``repr`` and the exact inverse of
:func:`~lexic.compile.notation.parse.load_ir`: ``load_ir(emit_ir(x)) == x``.
Values are rendered by TIER (scalar leaf / record / variadic / plain
payload), so a new node type needs no emitter change — the same openness the
symbol table gives the parse half. Never emits a trailing comma on a flat
call; a broken call carries black-style trailing commas (which the parse
half's ``arg-tail`` rules read back), so a fresh export is a formatter
fixpoint.
"""

from __future__ import annotations

from typing import NamedTuple, cast

from lexic.compile.notation.parse import INTERN
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import (
    IrLambda,
    IrNamedTuple,
    IrNoneType,
    IrScalar,
    IrSelf,
    IrTuple,
)
from lexic.ir.layout import IrCat, IrDoc, IrGroup, IrLine, IrNest, IrText, render
from lexic.ir.mapping import IR_DEFAULT, IrMapping, IrTypeMap
from lexic.ir.walk import IrDispatch

_CALL_INDENT = 4


class _Parts(NamedTuple):
    """A composite step result: constructor name + element values to emit."""

    name: str
    elements: tuple[object, ...]


class _Build(NamedTuple):
    """A driver marker: fold the last ``arity`` docs into one call doc."""

    name: str
    arity: int


def _call_doc(name: str, args: list[IrDoc]) -> IrDoc:
    """The call shape: ``Name(a, b)`` flat; broken, one arg per line with a
    trailing comma (the black form — a fresh export is a formatter fixpoint;
    the notation's arg-tail rules read the trailing comma back)."""
    if not args:
        return IrText(name + "()")
    parts: list[IrDoc] = [args[0]]
    for arg in args[1:]:
        parts.extend((IrText(","), IrLine(" "), arg))
    return IrGroup(
        IrCat(
            IrText(name + "("),
            IrNest(_CALL_INDENT, IrCat(IrLine(), *parts)),
            IrLine("", ","),
            IrText(")"),
        )
    )


def black_quoted(text: str) -> str:
    """``text`` as a Python string literal, double-quote-preferring.

    The black/ruff-format convention (so emitted notation is a formatter
    fixpoint): double quotes unless the content contains a double quote and
    no single quote — exactly the cases where ``repr`` keeps/uses each
    delimiter with no extra escapes.
    """
    plain = repr(text)
    if plain.startswith('"'):  # content has ' and no " — repr chose double
        return plain
    if '"' in text:  # content has " (and maybe ') — single-quoted is minimal
        return plain
    body = plain[1:-1].replace("\\'", "'")
    return f'"{body}"'


def _scalar_doc(_d: object, n: object, _nc: object) -> IrText:
    """A value-leaf: ``TypeName(payload_repr)`` — one atomic text."""
    payload = black_quoted(str(n)) if isinstance(n, str) else repr(int(cast(int, n)))
    return IrText(f"{type(n).__name__}({payload})")


def _payload_doc(value: object) -> IrText:
    """A plain (non-``IrSelf``) payload — the notation's primitive vocabulary.

    Payloads are a CLOSED set by the notation's own definition: ``str`` /
    ``int`` / ``bool`` values and bare class names; anything else has no
    spelling.

    :param value: The payload value.
    :returns: Its notation text.
    :raises UnsupportedConstructError: On a value outside the vocabulary.
    """
    if isinstance(value, type):
        return IrText(value.__name__)
    if isinstance(value, bool):
        return IrText(repr(value))
    if isinstance(value, str):
        return IrText(black_quoted(value))
    if isinstance(value, int):
        return IrText(repr(value))
    raise UnsupportedConstructError(f"emit_ir: {value!r} has no notation spelling")


def _refuse_lambda(_d: object, n: object, _nc: object) -> IrText:
    """Refuse an :class:`IrLambda` eagerly — its repr names a callable the
    notation cannot resolve back, so emitting it would produce unloadable text.
    """
    raise UnsupportedConstructError(
        f"emit_ir: {n!r} carries a callable — not representable in the notation"
    )


_EMIT_STEP: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrNoneType, IrLambda(lambda _d, _n, _nc: IrText("IrNone"))),
        IrAction(IrScalar, IrLambda(_scalar_doc)),
        IrAction(
            IrNamedTuple,
            IrLambda(lambda _d, n, _nc: _Parts(type(n).__name__, n.repr_args())),
        ),
        IrAction(
            IrTuple,
            IrLambda(lambda _d, n, _nc: _Parts(type(n).__name__, tuple(n))),
        ),
        IrAction(
            IrMapping,  # iterates as IrTuple dyads — the map-family repr shape
            IrLambda(lambda _d, n, _nc: _Parts(type(n).__name__, tuple(n))),
        ),
        IrAction(
            type(IR_DEFAULT),
            IrLambda(lambda _d, _n, _nc: IrText("IR_DEFAULT")),
        ),
        # Interned singletons (the INTERN registry) spell as their zero-arg
        # call — load_ir's interning maps it back to THE instance.
        *(
            IrAction(
                cast(type[IrSelf], cls),
                IrLambda(lambda _d, n, _nc: IrText(type(n).__name__ + "()")),
            )
            for cls in INTERN
        ),
        IrAction(IrLambda, IrLambda(_refuse_lambda)),
        # The leaf long tail (IrGlyph, IrThis, …): repr IS codegen and the
        # notation parses it — concrete tiers above win first on the MRO.
        IrAction(IrSelf, IrLambda(lambda _d, n, _nc: IrText(repr(n)))),
    ),
)
"""Per-tier emit step — leaf tiers yield an :class:`IrDoc`, composite tiers a
:class:`_Parts`; the raising default refuses unemittable values (functions,
lambdas — the same objects the notation cannot parse back)."""


def ir_doc(root: object) -> IrDoc:
    """Build the doc for ``root`` — iterative post-order over the value tree.

    :param root: The IR value to emit.
    :returns: The layout doc.
    :raises UnsupportedConstructError: On a value outside the notation.
    """
    docs: list[IrDoc] = []
    plan: list[object] = [root]
    while plan:
        item = plan.pop()
        if isinstance(item, _Build):
            args = docs[len(docs) - item.arity :]
            del docs[len(docs) - item.arity :]
            docs.append(_call_doc(item.name, args))
            continue
        if not isinstance(item, IrSelf):
            docs.append(_payload_doc(item))
            continue
        step = _EMIT_STEP.eval(_EMIT_STEP, item, ())
        if isinstance(step, _Parts):
            plan.append(_Build(step.name, len(step.elements)))
            plan.extend(reversed(step.elements))
        else:
            docs.append(cast(IrDoc, step))
    return docs[0]


def emit_ir(node: IrSelf, width: int = 88) -> str:
    """Emit ``node`` as formatted IR-constructor notation.

    The exact inverse of :func:`~lexic.compile.notation.parse.load_ir`
    (``load_ir(emit_ir(x)) == x``) and the layout twin of ``repr``: same
    constructor syntax and default elision (via
    :meth:`~lexic.ir.base.IrNamedTuple.repr_args`), width-solved by
    :func:`~lexic.ir.layout.render`.

    :param node: The IR value to emit.
    :param width: Target maximum line width.
    :returns: Formatted notation text (no trailing newline).
    :raises UnsupportedConstructError: On a value the notation cannot
        represent (e.g. an ``IrLambda`` body).
    """
    return render(ir_doc(node), width)
