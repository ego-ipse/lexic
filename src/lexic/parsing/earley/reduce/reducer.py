"""Forest → IR reduction — the seam where a flavour's meaning attaches.

Recognition proves a derivation exists; reduction turns the derivation into the
target :class:`~lexic.ir.grammar.nodes.IrAst`. A flavour's "meta notation" is a reduction
table — an :class:`~lexic.ir.action.mapping.IrMap` from a rule's
:class:`~lexic.ir.grammar.nodes.IrRuleRef` to a body that folds the rule's matched
children into an IR node — paired with a **cleaning policy**: which children are
noise (whitespace, delimiters) and so dropped before a body sees them.

:class:`Reducer` folds a :class:`~lexic.parsing.earley.kernel.forest.ParseTree` bottom-up.
The fold is **depth-safe**: a right-recursive derivation is arbitrarily deep, so
the walk does not recurse through the Python call stack — it is driven by the
shared :class:`~lexic.parsing.earley.kernel.trampoline.Trampoline`. The per-node generators
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

from lexic.ir import (
    IR_DEFAULT,
    IrDispatch,
    IrLeaf,
    IrMap,
    IrSelf,
    IrTuple,
)
from lexic.parsing.earley.kernel.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.trampoline import ADVANCE, EMIT, EXHAUSTED
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX
from lexic.parsing.earley.reduce.policy import DROP, KEEP_RAW, KEEP_REDUCED

# ── Child contributions ───────────────────────────────────────────────
# Each body returns its contribution to the parent's argument channel as an
# IrTuple: drop = zero elements, keep = one, splice = many.


# ── Subtree text ──────────────────────────────────────────────────────


# ── Reduction cursor + trampolined fold ───────────────────────────────


class ReduceCtx(IrLeaf[IrSelf, IrSelf]):
    """Per-reduction cursor — memoises each node's reduced IR by identity.

    The mutable per-fold state (the cursor precedent, like
    :class:`~lexic.parsing.earley.kernel.forest.ForestCtx`): :attr:`red` maps ``id(tree)`` to
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

    :ivar _node: The :class:`~lexic.parsing.earley.kernel.forest.ParseTree` whose children to
        resolve.
    :ivar _ctx: The reduction cursor.
    :ivar _reducer: The driving :class:`Reducer` (the cleaning policy).
    """

    __slots__ = ("_node", "_ctx", "_reducer")

    _node: ParseTree
    _ctx: ReduceCtx
    _reducer: Reducer

    def __init__(self, node: ParseTree, ctx: ReduceCtx, reducer: Reducer) -> None:
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

    :ivar _node: The :class:`~lexic.parsing.earley.kernel.forest.ParseTree` to reduce.
    :ivar _ctx: The reduction cursor.
    :ivar _reducer: The driving :class:`Reducer`.
    """

    __slots__ = ("_node", "_ctx", "_reducer")

    _node: ParseTree
    _ctx: ReduceCtx
    _reducer: Reducer

    def __init__(self, node: ParseTree, ctx: ReduceCtx, reducer: Reducer) -> None:
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
        body = self._reducer.body(node.symbol)
        reduced = body.eval(self._reducer, node, IrTuple(*parts))
        self._ctx.red[id(node)] = reduced
        yield (EMIT, reduced)


_REDUCE, _SPLICE = 0, 1
"""Frame purposes for :class:`_FastReduce` — fold to a reduction, or flatten a
synthetic node's children into its caller's parts (never itself reduced)."""


class _FastReduce(IrLeaf[IrSelf, IrSelf]):
    """Iterative fold of a :class:`~lexic.parsing.earley.kernel.forest.ParseTree` into IR.

    The non-generator replacement for the :class:`Trampoline`-driven
    :class:`ReduceSource` / :class:`ResolveSource` pair — same depth-safety
    (an explicit stack, not the C call stack), no coroutine machinery. Unlike
    :class:`~lexic.parsing.earley.kernel.forest._FastTree`, a :class:`ParseTree` is already
    disambiguated (single-derivation by construction), so there is no
    ambiguity fallback: this always completes.

    A stack frame ``[node, kids, idx, parts, purpose, noise_body]`` resolves
    ``node``'s children left to right: a **REDUCE** frame folds the finished
    ``parts`` through ``node``'s reduction body and memoises the result; a
    **SPLICE** frame (a synthetic quantifier-group node) instead hands its
    flattened ``parts`` straight to its caller, never reduced. ``noise_body``
    is the caller's precomputed contribution body for a semantic child pushed
    as a REDUCE frame — read back when that frame completes, so the caller
    need not re-resolve the ``noise`` policy on resume.

    :ivar reducer: The driving :class:`Reducer` (policy tables).
    :ivar ctx: The reduction cursor — its ``red`` is this walk's memo.
    :ivar stack: The explicit work stack of frames still to resolve.
    """

    __slots__ = ("reducer", "ctx", "_ctx_nc", "stack")

    reducer: Reducer
    ctx: ReduceCtx
    stack: list[list]

    def __init__(self, reducer: Reducer, ctx: ReduceCtx) -> None:
        """:param reducer: the policy; :param ctx: the reduction cursor."""
        self.reducer = reducer
        self.ctx = ctx
        self._ctx_nc = IrTuple(ctx)
        self.stack = []

    def build(self, root: ParseTree) -> IrSelf:
        """The single reduced IR value ``root`` folds to.

        :param root: The derivation to fold.
        :returns: The reduced IR node, also left in ``ctx.red[id(root)]``.
        """
        self.stack = [[root, root.kids, 0, [], _REDUCE, None]]
        while self.stack:
            self._step()
        return self.ctx.red[id(root)]

    def _step(self) -> None:
        """Advance the top frame by one kid, or close it out at the end."""
        frame = self.stack[-1]
        node, kids, idx, parts, purpose, noise_body = frame
        if idx == len(kids):
            self._close(node, parts, purpose, noise_body)
            return
        k = kids[idx]
        reducer = self.reducer
        if isinstance(k, PayloadLeaf):  # delegated child — pre-reduced IR, pass through
            if k.payload is not None:
                parts.append(k.payload)
            frame[2] = idx + 1
            return
        if isinstance(k, ParseTree) and str(k.symbol).startswith(SYNTHETIC_PREFIX):
            self.stack.append([k, k.kids, 0, [], _SPLICE, None])
            return
        if not isinstance(k, ParseTree):  # terminal leaf — no recursion
            parts.extend(reducer.literal.eval(reducer, k, ()))
            frame[2] = idx + 1
            return
        body = reducer.noise.resolve(k.symbol)
        if body is DROP:  # contributes nothing; never reduced
            frame[2] = idx + 1
            return
        if id(k) in self.ctx.red:  # already reduced (a shared sub-derivation)
            parts.extend(body.eval(reducer, k, self._ctx_nc))
            frame[2] = idx + 1
            return
        # idx stays put — resume at the same kid once its REDUCE frame closes
        self.stack.append([k, k.kids, 0, [], _REDUCE, body])

    def _close(
        self, node: ParseTree, parts: list, purpose: int, noise_body: IrSelf | None
    ) -> None:
        """Finish a fully-resolved frame and feed its result to its caller.

        :param node: The frame's node (its frame is still on top of ``stack``).
        :param parts: The frame's fully-resolved parts.
        :param purpose: :data:`_REDUCE` or :data:`_SPLICE`.
        :param noise_body: The caller's contribution body, when ``node`` was
            pushed to reduce a semantic child (``None`` for the root or a
            spliced synthetic node).
        """
        reducer = self.reducer
        if purpose == _REDUCE:
            body = reducer.body(node.symbol)
            reduced = body.eval(reducer, node, IrTuple(*parts))
            self.ctx.red[id(node)] = reduced
        self.stack.pop()
        if not self.stack:
            return
        parent = self.stack[-1]
        if purpose == _REDUCE:
            if noise_body is not None:  # None only for the root — no caller to feed
                parent[3].extend(noise_body.eval(reducer, node, self._ctx_nc))
                parent[2] += 1
        else:  # _SPLICE — flatten straight into the caller's parts
            parent[3].extend(parts)
            parent[2] += 1


# ── Fused kernel reduction (the product path) ─────────────────────────


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`~lexic.parsing.earley.kernel.forest.ParseTree` into IR.

    A **real** dispatcher, not one beside a dispatcher: the reduction table IS
    :attr:`~lexic.ir.action.walk.IrDispatch.actions` and the fallback body IS
    :attr:`~lexic.ir.action.walk.IrDispatch.default`. Only resolution differs from the
    usual preset — dispatch is on ``tree.symbol`` (a *value*, so a plain
    value-keyed ``IrMap``) rather than on ``type(n)``, which is what
    :meth:`body` does.

    Not parameterised by a product type: :meth:`eval` is the PER-NODE
    protocol, re-entered on children through :data:`KEEP_REDUCED`, so its
    results are heterogeneous — only the start rule's reduction is the
    "product", and typing ``eval`` by it would be false at every child.

    Each node's children are resolved first (governed by ``noise`` / ``literal``),
    then the body bound to the node's ``symbol`` is evaluated with those resolved
    children on the argument channel (``nc``) and the tree as ``n``. Dispatch is
    on ``tree.symbol`` (a *value*, :class:`~lexic.ir.grammar.nodes.IrRuleRef`) via the
    ``actions`` :class:`IrMap` — correct because every node is a ``ParseTree``,
    which is why this overrides ``eval`` rather than reusing the type-keyed table.

    The fold is driven by the depth-safe iterative :class:`_FastReduce` (an
    explicit stack, not the C call stack, so deep right-recursive trees do not
    overflow); ``eval`` on the entry establishes a :class:`ReduceCtx`, and a
    re-entrant ``eval`` carrying that cursor (the ``noise`` policy's
    :data:`KEEP_REDUCED`) returns the memoised reduction.

    :ivar actions: Rule ref → reduction body (the inherited table); a miss
        falls through to ``default``.
    :ivar default: Body for a rule with no entry — a flavour points it at
        ``YIELD`` for its text rules (the inherited fallback).
    :ivar noise: Rule ref → child-contribution body (``DROP``/``KEEP_REDUCED``),
        defaulting (``IR_DEFAULT``) to ``KEEP_REDUCED``.
    :ivar literal: Contribution body for terminal-leaf children (default
        ``KEEP_RAW``).
    """

    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW

    def body(self, symbol: IrSelf) -> IrSelf:
        """The reduction body for ``symbol`` — the value-keyed resolve.

        One dict probe, falling through to :attr:`default` on a miss; the
        per-node hot read of the whole fold.
        """
        found = self.actions.get(symbol)
        return self.default if found is None else found

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Reduce ``n`` (a :class:`~lexic.parsing.earley.kernel.forest.ParseTree`) to its IR.

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
        return _FastReduce(self, ctx).build(root)
