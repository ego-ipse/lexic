"""Forest → IR reduction — the seam where a flavour's meaning attaches.

Recognition proves a derivation exists; reduction turns the derivation into the
target :class:`~lexic.ir.nodes.IrAst`. A flavour's "meta notation" is a reduction
table — an :class:`~lexic.ir.mapping.IrMap` from a rule's
:class:`~lexic.ir.nodes.IrRuleRef` to a body that folds the rule's matched
children into an IR node — paired with a **cleaning policy**: which children are
noise (whitespace, delimiters) and so dropped before a body sees them.

:class:`Reducer` folds a :class:`~lexic.parsing_2.forest.ParseTree` bottom-up.
The fold is **depth-safe**: a right-recursive derivation is arbitrarily deep, so
the walk does not recurse through the Python call stack — it is driven by the
shared :class:`~lexic.parsing_2.trampoline.Trampoline`. The per-node generators
:class:`ReduceSource` (a node → its reduced IR) and :class:`ResolveSource` (a
node → its resolved children) yield trampoline commands instead of recursing; a
:class:`ReduceCtx` cursor memoises each node's reduction so the ``noise`` policy's
:data:`KEEP_REDUCED` reads an already-reduced child rather than re-entering.

Child resolution: each child contributes :data:`DROP` (nothing),
:data:`KEEP_RAW`/:data:`KEEP_REDUCED` (one), or a spliced synthetic sub-tree
(many). The ``noise`` / ``literal`` policy picks the contribution per child; its
defaults reproduce a plain reduce, so a flavour opts into cleaning by overriding
them. :data:`YIELD` recovers a subtree's source text (skipping non-semantic
spans) for rules that yield text rather than build.
"""

from __future__ import annotations

from typing import Iterator, Sequence, cast

from lexic.ir.base import IrLambda, IrLeaf, IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.walk import IrDispatch
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import SYNTHETIC_PREFIX
from lexic.parsing_2.trampoline import ADVANCE, EMIT, EXHAUSTED, Trampoline

# ── Child contributions ───────────────────────────────────────────────
# Each body returns its contribution to the parent's argument channel as an
# IrTuple: drop = zero elements, keep = one, splice = many.

DROP = IrLambda(lambda d, n, nc: IrTuple())
"""Contribute nothing — a non-semantic rule or an inline-literal terminal."""

KEEP_RAW = IrLambda(lambda d, n, nc: IrTuple(n))
"""Contribute the node unchanged — a terminal leaf passed straight through."""

KEEP_REDUCED = IrLambda(lambda d, n, nc: IrTuple(d.eval(d, n, nc)))
"""Contribute the reduced node — a semantic sub-rule folded to its IR. ``nc``
threads the :class:`ReduceCtx` so the re-entrant ``d.eval`` reads the memo."""


# ── Subtree text ──────────────────────────────────────────────────────


class Yield(IrLeaf[IrSelf, IrSelf]):
    """Source text of a parse subtree, skipping non-semantic sub-rule spans.

    Collects ``n``'s consumed characters in source order, recursing into
    sub-trees but skipping any whose rule the reducer's ``noise`` policy marks
    :data:`DROP` (e.g. ABNF ``DQUOTE`` delimiters). Inline-literal terminals are
    kept — so a numeric token like ``%x41-5A`` survives intact while a quoting
    rule's characters drop out. The text-yielding mirror of building from ``nc``.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Concatenate the subtree's kept leaf characters.

        :param d: The driving :class:`Reducer` (supplies the ``noise`` policy).
        :param n: The parse node (or terminal leaf) whose text to recover.
        :returns: The subtree source text as an :class:`IrStr`.
        """
        if not isinstance(n, ParseTree):
            return IrStr(str(n))
        parts: list[str] = []
        for k in n.kids:
            if (
                isinstance(k, ParseTree)
                and cast("Reducer", d).noise.resolve(k.symbol) is DROP
            ):
                continue
            parts.append(str(self.eval(d, k, ())))
        return IrStr("".join(parts))


YIELD = Yield()
"""Shared subtree-text node — stateless, so one instance."""


# ── Reduction cursor + trampolined fold ───────────────────────────────


class ReduceCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-reduction cursor — memoises each node's reduced IR by identity.

    The mutable per-fold state (the cursor precedent, like
    :class:`~lexic.parsing_2.forest.ForestCtx`): :attr:`red` maps ``id(tree)`` to
    the node's reduced IR, filled by :class:`ReduceSource` before it emits. The
    cursor rides the argument channel ``nc`` so the ``noise`` policy's
    :data:`KEEP_REDUCED` re-entry (``d.eval(d, child, (ctx,))``) resolves to the
    already-computed reduction rather than recursing.

    :ivar red: ``id(ParseTree)`` → its reduced IR node.
    """

    __slots__ = ("red",)

    red: dict[int, IrSelf]

    def __init__(self) -> None:
        """Seed an empty reduction memo."""
        self.red = {}


class ResolveSource(IrLeaf[IrSelf, IrSelf]):
    """Trampoline generator: a node's children resolved onto the argument channel.

    Flat-maps each child to its contribution, in source order: a synthetic
    sub-tree splices its own resolved children in place; a terminal leaf goes
    through the reducer's ``literal`` policy; any other sub-tree through the
    ``noise`` policy keyed on its rule (``DROP`` contributes nothing and is never
    reduced; otherwise the child is reduced — depth-safe via a nested
    :class:`ReduceSource` — and the policy body applied).

    :ivar _node: The :class:`~lexic.parsing_2.forest.ParseTree` whose children to
        resolve.
    :ivar _ctx: The reduction cursor.
    :ivar _reducer: The driving :class:`Reducer` (the cleaning policy).
    """

    __slots__ = ("_node", "_ctx", "_reducer")

    _node: ParseTree
    _ctx: ReduceCtx
    _reducer: "Reducer"

    def __init__(self, node: ParseTree, ctx: ReduceCtx, reducer: "Reducer") -> None:
        """:param node: the tree; :param ctx: the cursor; :param reducer: the policy."""
        self._node = node
        self._ctx = ctx
        self._reducer = reducer

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Yield ``(EMIT, contribution)`` per resolved child element.

        :returns: A command iterator the :class:`Trampoline` drives.
        """
        reducer = self._reducer
        ctx_nc = IrTuple(self._ctx)
        for k in self._node.kids:
            if isinstance(k, ParseTree) and str(k.symbol).startswith(SYNTHETIC_PREFIX):
                spliced = iter(ResolveSource(k, self._ctx, reducer))
                element = yield (ADVANCE, spliced)
                while element is not EXHAUSTED:
                    yield (EMIT, element)
                    element = yield (ADVANCE, spliced)
            elif not isinstance(k, ParseTree):
                for element in reducer.literal.eval(reducer, k, ()):
                    yield (EMIT, element)
            else:
                body = reducer.noise.resolve(k.symbol)
                if body is DROP:  # contributes nothing; never reduced
                    continue
                reduced = iter(ReduceSource(k, self._ctx, reducer))
                value = yield (ADVANCE, reduced)
                while value is not EXHAUSTED:  # drain the single reduction emit
                    value = yield (ADVANCE, reduced)
                for element in body.eval(reducer, k, ctx_nc):
                    yield (EMIT, element)


class ReduceSource(IrLeaf[IrSelf, IrSelf]):
    """Trampoline generator: a node folded to its single reduced IR value.

    Resolves the node's children (via :class:`ResolveSource`), evaluates the body
    bound to the node's ``symbol`` with those resolved children on the argument
    channel, memoises the result on the cursor, then emits it (exactly once).

    :ivar _node: The :class:`~lexic.parsing_2.forest.ParseTree` to reduce.
    :ivar _ctx: The reduction cursor.
    :ivar _reducer: The driving :class:`Reducer`.
    """

    __slots__ = ("_node", "_ctx", "_reducer")

    _node: ParseTree
    _ctx: ReduceCtx
    _reducer: "Reducer"

    def __init__(self, node: ParseTree, ctx: ReduceCtx, reducer: "Reducer") -> None:
        """:param node: the tree; :param ctx: the cursor; :param reducer: the policy."""
        self._node = node
        self._ctx = ctx
        self._reducer = reducer

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Resolve children, fold, memoise, then ``(EMIT, reduced)`` once.

        :returns: A command iterator the :class:`Trampoline` drives.
        :raises IrKeyError: If no reduction matches the node's symbol and no
            ``IR_DEFAULT`` is set.
        """
        node = self._node
        children = iter(ResolveSource(node, self._ctx, self._reducer))
        parts: list[IrSelf] = []
        element = yield (ADVANCE, children)
        while element is not EXHAUSTED:
            parts.append(element)
            element = yield (ADVANCE, children)
        body = self._reducer.reductions.resolve(node.symbol)
        reduced = body.eval(self._reducer, node, IrTuple(*parts))
        self._ctx.red[id(node)] = reduced
        yield (EMIT, reduced)


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`~lexic.parsing_2.forest.ParseTree` into IR.

    Each node's children are resolved first (governed by ``noise`` / ``literal``),
    then the body bound to the node's ``symbol`` is evaluated with those resolved
    children on the argument channel (``nc``) and the tree as ``n``. Dispatch is
    on ``tree.symbol`` (a *value*, :class:`~lexic.ir.nodes.IrRuleRef`) via the
    ``reductions`` :class:`IrMap` — correct because every node is a ``ParseTree``,
    which is why this overrides ``eval`` rather than reusing the type-keyed table.

    The fold is driven by the depth-safe
    :class:`~lexic.parsing_2.trampoline.Trampoline` (so deep right-recursive trees
    do not overflow); ``eval`` on the entry establishes a :class:`ReduceCtx`, and
    a re-entrant ``eval`` carrying that cursor (the ``noise`` policy's
    :data:`KEEP_REDUCED`) returns the memoised reduction.

    :ivar reductions: Rule ref → reduction body, resolved with ``IR_DEFAULT``
        fallback (a flavour points it at ``YIELD`` for its text rules); a miss
        with no default raises.
    :ivar noise: Rule ref → child-contribution body (``DROP``/``KEEP_REDUCED``),
        defaulting (``IR_DEFAULT``) to ``KEEP_REDUCED``.
    :ivar literal: Contribution body for terminal-leaf children (default
        ``KEEP_RAW``).
    """

    reductions: IrMap = IrMap()
    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Reduce ``n`` (a :class:`~lexic.parsing_2.forest.ParseTree`) to its IR.

        :param d: The dispatcher (this reducer).
        :param n: The derivation to fold, or a child re-entered via the memo.
        :param nc: Empty at entry; ``(ReduceCtx,)`` on a ``KEEP_REDUCED`` re-entry.
        :returns: The IR node the matched rule reduces to.
        :raises IrKeyError: If no reduction matches and no ``IR_DEFAULT`` is set.
        """
        if nc and isinstance(nc[0], ReduceCtx):  # memo hit — child already reduced
            return cast(ReduceCtx, nc[0]).red[id(n)]
        ctx = ReduceCtx()
        root = cast(ParseTree, n)
        for _ in Trampoline(ReduceSource(root, ctx, self)):
            pass  # drive the single root reduction; result lands in the memo
        return ctx.red[id(root)]
