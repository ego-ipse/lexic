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

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IR_DEFAULT,
    IrAction,
    IrCat,
    IrDispatch,
    IrDoc,
    IrGroup,
    IrLambda,
    IrLine,
    IrMapping,
    IrNamedTuple,
    IrNest,
    IrNoneType,
    IrScalar,
    IrSelf,
    IrText,
    IrTuple,
    IrTypeMap,
    render,
)

_CALL_INDENT = 4


class _Parts(NamedTuple):
    """A composite step result: constructor name + element values to emit."""

    name: str
    elements: tuple[object, ...]


class _Leaf(NamedTuple):
    """A leaf step result: its atomic doc + the symbols that doc spells.

    A leaf's doc is one indivisible :class:`~lexic.ir.text.layout.IrText`, so the
    symbol inside it cannot be recovered from the layout tree — the tier that
    chose the spelling is the only thing that knows it, and says so here.
    """

    doc: IrDoc
    symbols: tuple[str, ...] = ()


class _Build(NamedTuple):
    """A driver marker: fold the last ``arity`` docs into one call doc."""

    name: str
    arity: int


class _BuildTuple(NamedTuple):
    """A driver marker: fold the last ``arity`` docs into a plain tuple doc."""

    arity: int


class Notation(NamedTuple):
    """What emission produced: the layout doc and the symbols it spelled.

    ``symbols`` is the import list a module holding this notation needs. It is
    what emission RENDERED, which is neither the identifiers in the rendered
    text (a scan) nor the symbols the value holds (an over-count: the notation
    elides trailing defaults, so ``IrItem(IrLiteral("a"))`` never spells its
    unit ``IrQuantifier``).
    """

    doc: IrDoc
    symbols: frozenset[str]


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


def _tuple_doc(args: list[IrDoc]) -> IrDoc:
    """The plain-tuple shape: ``(a, b)`` flat, one element per line broken.

    The arity-1 tail differs from every other trailing comma in the notation.
    A call's trailing comma is a BREAK artefact — black writes it only when the
    call breaks — but a one-tuple's comma is the VALUE: ``(x)`` is ``x`` in
    Python and the parse half refuses it outright. So it renders flat and
    broken alike, and only the break after it is conditional.
    """
    if not args:
        return IrText("()")
    parts: list[IrDoc] = [args[0]]
    for arg in args[1:]:
        parts.extend((IrText(","), IrLine(" "), arg))
    tail = IrCat(IrText(","), IrLine("")) if len(args) == 1 else IrLine("", ",")
    return IrGroup(
        IrCat(
            IrText("("),
            IrNest(_CALL_INDENT, IrCat(IrLine(), *parts)),
            tail,
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


def _scalar_doc(_d: object, n: object, _nc: object) -> _Leaf:
    """A value-leaf: ``TypeName(payload_repr)`` — one atomic text."""
    payload = black_quoted(str(n)) if isinstance(n, str) else repr(int(cast(int, n)))
    name = type(n).__name__
    return _Leaf(IrText(f"{name}({payload})"), (name,))


def _repr_leaf(_d: object, n: object, _nc: object) -> _Leaf:
    """The leaf long tail (``IrGlyph``, ``IrThis``, …): ``repr`` IS codegen.

    A bare-name singleton spells as its VALUE (``IrNone``, not ``IrNoneType``),
    which is also the name an importer imports; anything else spells as a call
    on its own class name — which covers the engine's reduce sentinels, since
    ``Drop()`` reads back as THE ``DROP`` and needs no tier of its own.
    """
    spelling = repr(n)
    name = spelling if spelling.isidentifier() else type(n).__name__
    return _Leaf(IrText(spelling), (name,))


def _payload_doc(value: object) -> _Leaf:
    """A plain (non-``IrSelf``) payload — the notation's primitive vocabulary.

    Payloads are a CLOSED set by the notation's own definition: ``str`` /
    ``int`` / ``bool`` values and bare class names; anything else has no
    spelling. A bare class name IS a symbol the reader must import; a scalar
    payload is not. A plain ``tuple`` never reaches here — it has parts, so
    :func:`ir_doc` renders it through :func:`_tuple_doc`.

    :param value: The payload value.
    :returns: Its notation text and the symbols that text spells.
    :raises UnsupportedConstructError: On a value outside the vocabulary.
    """
    if isinstance(value, type):
        return _Leaf(IrText(value.__name__), (value.__name__,))
    if isinstance(value, bool):
        return _Leaf(IrText(repr(value)))
    if isinstance(value, str):
        return _Leaf(IrText(black_quoted(value)))
    if isinstance(value, int):
        return _Leaf(IrText(repr(value)))
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
        IrAction(
            IrNoneType,
            IrLambda(lambda _d, _n, _nc: _Leaf(IrText("IrNone"), ("IrNone",))),
        ),
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
            IrLambda(lambda _d, _n, _nc: _Leaf(IrText("IR_DEFAULT"), ("IR_DEFAULT",))),
        ),
        IrAction(IrLambda, IrLambda(_refuse_lambda)),
        # The leaf long tail (IrGlyph, IrThis, …): repr IS codegen and the
        # notation parses it — concrete tiers above win first on the MRO.
        IrAction(IrSelf, IrLambda(_repr_leaf)),
    ),
)
"""Per-tier emit step — leaf tiers yield an :class:`IrDoc`, composite tiers a
:class:`_Parts`; the raising default refuses unemittable values (functions,
lambdas — the same objects the notation cannot parse back)."""


def ir_doc(root: object) -> Notation:
    """Build the doc for ``root`` — iterative post-order over the value tree.

    :param root: The IR value to emit.
    :returns: The layout doc and the symbols the doc spells.
    :raises UnsupportedConstructError: On a value outside the notation.
    """
    docs: list[IrDoc] = []
    plan: list[object] = [root]
    symbols: set[str] = set()
    while plan:
        item = plan.pop()
        if isinstance(item, (_Build, _BuildTuple)):
            args = docs[len(docs) - item.arity :]
            del docs[len(docs) - item.arity :]
            docs.append(
                _tuple_doc(args)
                if isinstance(item, _BuildTuple)
                else _call_doc(item.name, args)
            )
            continue
        if not isinstance(item, IrSelf):
            # A plain tuple is the one payload with parts. The markers above
            # are NamedTuples, so they have to be taken off the plan first.
            if isinstance(item, tuple):
                plan.append(_BuildTuple(len(item)))
                plan.extend(reversed(item))
                continue
            leaf = _payload_doc(item)
            symbols.update(leaf.symbols)
            docs.append(leaf.doc)
            continue
        step = _EMIT_STEP.eval(_EMIT_STEP, item, ())
        if isinstance(step, _Parts):
            symbols.add(step.name)
            plan.append(_Build(step.name, len(step.elements)))
            plan.extend(reversed(step.elements))
        else:
            symbols.update(step.symbols)
            docs.append(step.doc)
    return Notation(docs[0], frozenset(symbols))


def emit_ir(node: IrSelf, width: int = 88) -> str:
    """Emit ``node`` as formatted IR-constructor notation.

    The exact inverse of :func:`~lexic.compile.notation.parse.load_ir`
    (``load_ir(emit_ir(x)) == x``) and the layout twin of ``repr``: same
    constructor syntax and default elision (via
    :meth:`~lexic.ir.base.IrNamedTuple.repr_args`), width-solved by
    :func:`~lexic.ir.text.layout.render`.

    :param node: The IR value to emit.
    :param width: Target maximum line width.
    :returns: Formatted notation text (no trailing newline).
    :raises UnsupportedConstructError: On a value the notation cannot
        represent (e.g. an ``IrLambda`` body).
    """
    return render(ir_doc(node).doc, width)
