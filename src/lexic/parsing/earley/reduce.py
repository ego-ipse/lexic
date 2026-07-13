"""Forest → IR reduction — the seam where a flavour's meaning attaches.

Recognition proves a derivation exists; reduction turns the derivation into the
target :class:`~lexic.ir.nodes.IrAst`. A flavour's "meta notation" is a reduction
table — an :class:`~lexic.ir.mapping.IrMap` from a rule's
:class:`~lexic.ir.nodes.IrRuleRef` to a body that folds the rule's matched
children into an IR node — paired with a **cleaning policy**: which children are
noise (whitespace, delimiters) and so dropped before a body sees them.

:class:`Reducer` folds a :class:`~lexic.parsing.earley.forest.ParseTree` bottom-up.
The fold is **depth-safe**: a right-recursive derivation is arbitrarily deep, so
the walk does not recurse through the Python call stack — it is driven by the
shared :class:`~lexic.parsing.earley.trampoline.Trampoline`. The per-node generators
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

from functools import partial
from typing import Iterator, Sequence, cast

from lexic.ir.base import IrLambda, IrLeaf, IrNone, IrSelf, IrStr, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
from lexic.ir.nodes import IrAst
from lexic.ir.walk import IrDispatch
from lexic.parsing.earley.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.lexruns import collapse_runs, unit_leaves
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX
from lexic.parsing.earley.tables import (
    ORIGIN_BITS,
    ORIGIN_MASK,
    RUN_DROP,
    RUN_LEAF,
    RUN_STR,
    ParserTables,
    RunTerm,
    predecessor_chain,
)
from lexic.parsing.earley.trampoline import ADVANCE, EMIT, EXHAUSTED

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
        if isinstance(n, PayloadLeaf):  # delegated child — its recorded span text
            return IrStr(n.text)
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
    :class:`~lexic.parsing.earley.forest.ForestCtx`): :attr:`red` maps ``id(tree)`` to
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

    :ivar _node: The :class:`~lexic.parsing.earley.forest.ParseTree` whose children to
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

    :ivar _node: The :class:`~lexic.parsing.earley.forest.ParseTree` to reduce.
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


_REDUCE, _SPLICE = 0, 1
"""Frame purposes for :class:`_FastReduce` — fold to a reduction, or flatten a
synthetic node's children into its caller's parts (never itself reduced)."""


class _FastReduce(IrLeaf[IrSelf, IrSelf]):
    """Iterative fold of a :class:`~lexic.parsing.earley.forest.ParseTree` into IR.

    The non-generator replacement for the :class:`Trampoline`-driven
    :class:`ReduceSource` / :class:`ResolveSource` pair — same depth-safety
    (an explicit stack, not the C call stack), no coroutine machinery. Unlike
    :class:`~lexic.parsing.earley.forest._FastTree`, a :class:`ParseTree` is already
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

    reducer: "Reducer"
    ctx: "ReduceCtx"
    stack: list[list]

    def __init__(self, reducer: "Reducer", ctx: "ReduceCtx") -> None:
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
            body = reducer.reductions.resolve(node.symbol)
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

DROP_KIND, KEEP_KIND, OTHER_KIND = 0, 1, 2
"""Compiled noise/literal policy kinds — DROP, KEEP_REDUCED (KEEP_RAW for the
literal policy), and anything else (an :data:`OTHER_KIND` noise policy makes
the fused fold miss so the general tree path handles it)."""


class _FusedMiss(Exception):
    """Internal abort: the packed SPPF is ambiguous under this handle — the
    fused fold cannot proceed and the caller falls back to the tree path."""


def _mentions_yield(body: IrSelf) -> bool:
    """Whether ``body``'s node tree contains the :data:`YIELD` singleton.

    Bodies are tuple-backed IR records, so the scan walks tuple elements; an
    opaque callable (:class:`~lexic.ir.base.IrLambda`) cannot be inspected and
    counts as not mentioning it.
    """
    stack: list[IrSelf] = [body]
    while stack:
        node = stack.pop()
        if node is YIELD:
            return True
        if isinstance(node, tuple):
            stack.extend(x for x in node if isinstance(x, IrSelf))
    return False


class ReducePlan(IrLeaf[IrSelf, IrSelf]):
    """A reducer's policy tables compiled against one grammar's rule ids.

    Built once per ``(reducer, tables)`` pair and cached: the noise policy and
    synthetic flags resolve eagerly per rule_id; reduction bodies (and their
    YIELD-mention flags) fill lazily on first encounter. ``can_drop`` is the
    reachability closure of DROP-noise rules — a rule whose subtree can never
    contain a dropped span yields its source text as a single O(1) slice.

    :ivar refs: rule_id → the rule's :class:`~lexic.ir.nodes.IrRuleRef`.
    :ivar synthetic: rule_id → minted by normalisation (spliced, never reduced).
    :ivar noise_kind: rule_id → compiled noise policy kind.
    :ivar can_drop: rule_id → whether a DROP-noise rule is reachable beneath it.
    :ivar literal_kind: the compiled terminal-leaf policy kind.
    :ivar bodies: rule_id → its reduction body (lazily resolved).
    :ivar mentions: rule_id → whether the body mentions :data:`YIELD` (lazy).
    """

    __slots__ = (
        "refs",
        "synthetic",
        "noise_kind",
        "can_drop",
        "literal_kind",
        "bodies",
        "mentions",
    )

    def __init__(self, reducer: "Reducer", tables: ParserTables) -> None:
        """Compile ``reducer``'s policies against ``tables``' rule numbering.

        :param reducer: The reducer whose tables to compile.
        :param tables: The compiled grammar.
        """
        decode = tables.decode
        self.refs = decode.rule_refs
        self.synthetic = tuple(
            name.startswith(SYNTHETIC_PREFIX) for name in decode.rule_names
        )
        kinds = []
        for ref in decode.rule_refs:
            body = reducer.noise.resolve(ref)
            if body is DROP:
                kinds.append(DROP_KIND)
            elif body is KEEP_REDUCED:
                kinds.append(KEEP_KIND)
            else:
                kinds.append(OTHER_KIND)
        self.noise_kind = tuple(kinds)
        self.can_drop = self._reach_drop(tables, kinds)
        literal = reducer.literal
        if literal is DROP:
            self.literal_kind = DROP_KIND
        elif literal is KEEP_RAW:
            self.literal_kind = KEEP_KIND
        else:
            self.literal_kind = OTHER_KIND
        self.bodies: list[IrSelf | None] = [None] * len(kinds)
        self.mentions: list[bool] = [False] * len(kinds)

    def body(self, reducer: "Reducer", rid: int) -> IrSelf:
        """Rule ``rid``'s reduction body, resolved lazily and cached.

        The single home for reduction-body resolution + YIELD-mention flagging:
        :class:`FusedReduce` (the Earley fused path) and the predictive PDA's
        reduce completion both read the body through here, so the policy is
        compiled once per ``(reducer, tables)`` and never re-derived (H5).

        :param reducer: The reducer whose reduction table to resolve against.
        :param rid: The rule id.
        :returns: The rule's reduction body; :attr:`mentions` ``[rid]`` is set
            as a side effect.
        """
        body = self.bodies[rid]
        if body is None:
            body = reducer.reductions.resolve(self.refs[rid])
            self.bodies[rid] = body
            self.mentions[rid] = _mentions_yield(body)
        return body

    @staticmethod
    def _reach_drop(tables: ParserTables, kinds: list[int]) -> tuple[bool, ...]:
        """Per rule, whether a DROP-noise rule is reachable beneath it."""
        codes = tables.codes
        refs_of: list[set[int]] = [set() for _ in kinds]
        for arm_id, rid in enumerate(codes.arm_rule):
            code = codes.arm_base[arm_id]
            sym = codes.next_sym[code]
            while sym != 0:
                if sym > 0:
                    refs_of[rid].add(sym - 1)
                code += 1
                sym = codes.next_sym[code]
        can = [False] * len(kinds)
        changed = True
        while changed:
            changed = False
            for rid, targets in enumerate(refs_of):
                if can[rid]:
                    continue
                if any(kinds[t] == DROP_KIND or can[t] for t in targets):
                    can[rid] = True
                    changed = True
        return tuple(can)


_PLANS: dict[tuple[int, int], tuple[object, object, ReducePlan]] = {}
"""Plan memo — (id(reducer), id(tables)) → (reducer, tables, plan). The strong
references pin both ids, so recycled ids can never alias live entries."""


def plan_for(reducer: "Reducer", tables: ParserTables) -> ReducePlan:
    """The cached :class:`ReducePlan` for a ``(reducer, tables)`` pair."""
    key = (id(reducer), id(tables))
    entry = _PLANS.get(key)
    if entry is None:
        entry = (reducer, tables, ReducePlan(reducer, tables))
        _PLANS[key] = entry
    return entry[2]


class FusedReduce(IrLeaf[IrSelf, IrSelf]):
    """Fold the kernel's packed SPPF straight to IR — no intermediate tree.

    The product path: instead of materialising a
    :class:`~lexic.parsing.earley.forest.ParseTree` and folding it again, one
    explicit-stack pass walks the packed links, resolves each node's cleaned
    children, and evaluates the reduction bodies in place. Rules whose body IS
    :data:`YIELD` reduce to their **source span** directly — an O(1)
    ``text[origin:end]`` slice when no DROP-noise rule is reachable beneath
    them (``plan.can_drop``), skipping their subtrees entirely. Reduction
    bodies receive the matched span text as ``n`` (only computed when the
    body mentions :data:`YIELD`) and the cleaned children on ``nc``.

    A fast-path miss — an ambiguous key, a KEEP_RAW/custom noise policy —
    returns ``None`` from :meth:`build`, and the caller falls back to the
    general tree-then-:class:`Reducer` path. Depth lives in the explicit
    stack, never the C stack.

    :ivar kernel: The finished kernel whose links to fold.
    :ivar reducer: The policy tables.
    :ivar plan: The compiled :class:`ReducePlan`.
    :ivar memo: handle → its reduced IR (the KEEP_REDUCED read).
    :ivar stack: Work frames ``[handle, kids, idx, parts, is_splice]``.
    """

    __slots__ = ("kernel", "reducer", "plan", "memo", "stack")

    kernel: Kernel
    reducer: "Reducer"
    plan: ReducePlan
    memo: dict[int, IrSelf]
    stack: list[list]

    def __init__(self, kernel: Kernel, reducer: "Reducer") -> None:
        """:param kernel: the finished kernel; :param reducer: the policies."""
        self.kernel = kernel
        self.reducer = reducer
        self.plan = plan_for(reducer, kernel.tables)
        self.memo = {}
        self.stack = []

    def build(self, handle: int) -> IrSelf | None:
        """The reduced IR under ``handle``, or ``None`` on a fast-path miss.

        :param handle: The packed accepting handle ``(item << B) | end``.
        :returns: The reduced IR node, or ``None`` (caller falls back).
        """
        kids = self._collect(handle)
        if kids is None:
            return None
        self.stack = [[handle, kids, 0, [], False]]
        try:
            while self.stack:
                if not self._step():
                    return None
        except _FusedMiss:
            return None
        return self.memo[handle]

    def _step(self) -> bool:
        """Advance the top frame by one kid, or close it out at the end."""
        frame = self.stack[-1]
        kids, idx = frame[1], frame[2]
        if idx == len(kids):
            self._close(frame)
            return True
        k = kids[idx]
        if isinstance(k, str):  # scanned text — the literal policy
            self._literal(frame, k)
            return True
        if isinstance(k, tuple):  # a collapsed run — reconstruct per char
            self._run_child(frame, k[0], k[1])
            return True
        return self._rule_child(frame, k)

    def _run_child(self, frame: list, term: RunTerm, s: str) -> None:
        """Contribute a collapsed run's per-char reconstruction."""
        mode = term.mode
        if mode == RUN_STR:  # the unit rule YIELDs its char
            frame[3].extend(IrStr(c) for c in s)
        elif mode == RUN_LEAF:  # bare terminal unit under KEEP_RAW
            leaf = self.kernel.tables.char_leaf
            frame[3].extend(leaf(c) for c in s)
        frame[2] += 1

    def _rule_child(self, frame: list, k: int) -> bool:
        """Contribute one rule-child kid per its splice / noise policy."""
        rid = self._rule_of(k)
        plan = self.plan
        if plan.synthetic[rid]:  # splice — flattened, never reduced
            sub = self._collect(k)
            if sub is None:
                return False
            self.stack.append([k, sub, 0, [], True])
            return True
        kind = plan.noise_kind[rid]
        if kind == DROP_KIND:  # contributes nothing; never reduced
            frame[2] += 1
            return True
        if kind != KEEP_KIND:  # KEEP_RAW / custom noise — the general path handles it
            return False
        return self._keep_reduced(frame, k, rid)

    def _keep_reduced(self, frame: list, k: int, rid: int) -> bool:
        """Contribute child ``k``'s reduction (memo, span fast path, or frame)."""
        cached = self.memo.get(k)
        if cached is not None:
            frame[3].append(cached)
            frame[2] += 1
            return True
        if self._body(rid) is YIELD:  # span fast path — skip the subtree
            value = IrStr(self._yield_text(k))
            self.memo[k] = value
            frame[3].append(value)
            frame[2] += 1
            return True
        sub = self._collect(k)
        if sub is None:
            return False
        self.stack.append([k, sub, 0, [], False])  # idx stays; resume on close
        return True

    def _literal(self, frame: list, char: str) -> None:
        """Apply the literal policy to a scanned char kid."""
        kind = self.plan.literal_kind
        if kind == KEEP_KIND:
            frame[3].append(self.kernel.tables.char_leaf(char))
        elif kind == OTHER_KIND:
            reducer = self.reducer
            leaf = self.kernel.tables.char_leaf(char)
            frame[3].extend(reducer.literal.eval(reducer, leaf, ()))
        frame[2] += 1

    def _close(self, frame: list) -> None:
        """Finish a fully-resolved frame and feed its result to its caller."""
        handle, _, _, parts, is_splice = frame
        self.stack.pop()
        if is_splice:
            self._close_splice(parts)
        else:
            self._close_reduce(handle, parts)

    def _close_splice(self, parts: list) -> None:
        """Flatten a spliced synthetic node's parts straight into its caller."""
        if not self.stack:
            return
        parent = self.stack[-1]
        parent[3].extend(parts)
        parent[2] += 1

    def _close_reduce(self, handle: int, parts: list) -> None:
        """Fold a reduced node's parts through its body and feed the caller."""
        rid = self._rule_of(handle)
        body = self._body(rid)
        if body is YIELD:
            value: IrSelf = IrStr(self._yield_text(handle))
        else:
            span = (
                IrStr(self._yield_text(handle)) if self.plan.mentions[rid] else IrNone
            )
            value = body.eval(self.reducer, span, IrTuple(*parts))
        self.memo[handle] = value
        if not self.stack:
            return
        parent = self.stack[-1]
        parent[3].append(value)
        parent[2] += 1

    def _body(self, rid: int) -> IrSelf:
        """Rule ``rid``'s reduction body, resolved lazily and cached.

        Delegates to :meth:`ReducePlan.body` — the single resolution home the
        predictive PDA's reduce completion shares (H5).
        """
        return self.plan.body(self.reducer, rid)

    def _yield_text(self, handle: int) -> str:
        """The source text under ``handle``, skipping DROP-noise sub-spans.

        A subtree with no reachable DROP rule contributes one O(1) slice;
        otherwise its kids are walked (depth on the explicit list).

        :raises _FusedMiss: If an ambiguous key is hit mid-walk.
        """
        plan = self.plan
        text = self.kernel.text
        out: list[str] = []
        kids = self._collect(handle)
        if kids is None:
            raise _FusedMiss
        work = list(reversed(kids))
        while work:
            k = work.pop()
            if isinstance(k, str):
                out.append(k)
                continue
            if isinstance(k, tuple):  # a collapsed run — its text, unless noise
                if k[0].mode != RUN_DROP:
                    out.append(k[1])
                continue
            rid = self._rule_of(k)
            if plan.noise_kind[rid] == DROP_KIND:
                continue
            if not plan.can_drop[rid]:  # pure span — no droppable descendant
                item = k >> ORIGIN_BITS
                out.append(text[item & ORIGIN_MASK : k & ORIGIN_MASK])
                continue
            sub = self._collect(k)
            if sub is None:
                raise _FusedMiss
            work.extend(reversed(sub))
        return "".join(out)

    def _rule_of(self, handle: int) -> int:
        """The rule_id owning ``handle``'s item."""
        codes = self.kernel.tables.codes
        return codes.arm_rule[codes.code_arm[handle >> (2 * ORIGIN_BITS)]]

    def _collect(self, handle: int) -> list | None:
        """Raw kids of ``handle`` in source order (chars and packed handles).

        Expands a deferred Leo top on first touch. ``None`` when a key is
        missing or packs more than one family (ambiguity — fall back).
        """
        kernel = self.kernel
        links = kernel.st.links
        if handle in kernel.st.leo_links and handle not in links:
            kernel.expand_leo(handle)
        tables = kernel.tables
        item = handle >> ORIGIN_BITS
        end = handle & ORIGIN_MASK
        base = tables.codes.arm_base[tables.codes.code_arm[item >> ORIGIN_BITS]]
        chain = predecessor_chain(links, item, end, base)
        if chain is None:
            return None
        return self._chain_kids(chain)

    def _chain_kids(self, chain: list) -> list:
        """Reconstruct one kid per predecessor link, tagging collapsed runs."""
        tables = self.kernel.tables
        nxt = tables.codes.next_sym
        lens = tables.terms.lens
        atoms = tables.terms.atoms
        kids: list = []
        for pred_item, _, child in chain:
            if isinstance(child, str):
                # the consumed terminal is what the predecessor's dot faces
                tid = -nxt[pred_item >> ORIGIN_BITS] - 1
                if lens[tid] == 0:  # a collapsed run — carry its RunTerm
                    child = (atoms[tid], child)
            kids.append(child)
        return kids


_COLLAPSED: dict[tuple[int, int], tuple[object, object, ParserTables]] = {}
"""Collapsed-tables memo — (id(reducer), id(grammar)) → (reducer, grammar,
tables). Strong references pin both ids against reuse."""


def _run_mode(reducer: "Reducer", tables: ParserTables, unit_rid: int) -> int | None:
    """The per-char contribution mode a collapsed run must reconstruct.

    ``None`` means the unit's contributions cannot be reconstructed from the
    run text under this reducer — the rule must stay per-char.
    """
    modes: set[int] = set()
    if unit_rid < 0:
        leaf_rids: set[int] = set()
        has_bare = True
    else:
        resolved = unit_leaves(tables, unit_rid)
        if resolved is None:
            return None
        leaf_rids, has_bare = resolved
    if has_bare:
        literal = reducer.literal
        if literal is DROP:
            modes.add(RUN_DROP)
        elif literal is KEEP_RAW:
            modes.add(RUN_LEAF)
        else:
            return None
    for rid in leaf_rids:
        ref = tables.decode.rule_refs[rid]
        noise = reducer.noise.resolve(ref)
        if noise is DROP:
            modes.add(RUN_DROP)
        elif noise is KEEP_REDUCED and reducer.reductions.resolve(ref) is YIELD:
            modes.add(RUN_STR)
        else:
            return None
    return modes.pop() if len(modes) == 1 else None


def collapsed_tables(reducer: "Reducer", grammar: IrAst) -> ParserTables:
    """Tables for ``grammar`` with every run provable safe *for this reducer*
    collapsed to a :class:`~lexic.parsing.earley.tables.RunTerm`.

    The grammar-side proof (charset, uniqueness, follow disjointness) comes
    from :func:`~lexic.parsing.earley.lexruns.run_candidates`; the reducer-side
    check (:func:`_run_mode`) keeps only runs whose per-char contributions
    the fused fold can reconstruct. Memoised per ``(reducer, grammar)``.

    :param reducer: The reduction policy the collapse must respect.
    :param grammar: An Earley-normalised grammar.
    :returns: The collapsed tables (the plain tables when nothing collapses).
    """
    key = (id(reducer), id(grammar))
    entry = _COLLAPSED.get(key)
    if entry is not None:
        return entry[2]
    tables = collapse_runs(grammar, partial(_run_mode, reducer))
    _COLLAPSED[key] = (reducer, grammar, tables)
    return tables


class Reducer(IrDispatch):
    """Bottom-up fold of a :class:`~lexic.parsing.earley.forest.ParseTree` into IR.

    Each node's children are resolved first (governed by ``noise`` / ``literal``),
    then the body bound to the node's ``symbol`` is evaluated with those resolved
    children on the argument channel (``nc``) and the tree as ``n``. Dispatch is
    on ``tree.symbol`` (a *value*, :class:`~lexic.ir.nodes.IrRuleRef`) via the
    ``reductions`` :class:`IrMap` — correct because every node is a ``ParseTree``,
    which is why this overrides ``eval`` rather than reusing the type-keyed table.

    The fold is driven by the depth-safe iterative :class:`_FastReduce` (an
    explicit stack, not the C call stack, so deep right-recursive trees do not
    overflow); ``eval`` on the entry establishes a :class:`ReduceCtx`, and a
    re-entrant ``eval`` carrying that cursor (the ``noise`` policy's
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
        """Reduce ``n`` (a :class:`~lexic.parsing.earley.forest.ParseTree`) to its IR.

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
