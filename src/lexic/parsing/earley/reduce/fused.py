"""The fused reduction — folding straight off the packed forest.

The common path: no intermediate ``ParseTree`` at all, driven by a plan
compiled once per reducer. ``_FusedMiss`` is the abort that hands an
ambiguous handle back to the general tree walk in ``reducer``.
"""

from __future__ import annotations

from functools import partial

from lexic.ir import (
    IrAst,
    IrLeaf,
    IrNone,
    IrSelf,
    IrStr,
    IrTuple,
)
from lexic.parsing.earley.kernel.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import RunTerm, predecessor_chain
from lexic.parsing.earley.kernel.tables.records import (
    ORIGIN_BITS,
    RUN_DROP,
    RUN_LEAF,
    RUN_STR,
    ParserTables,
)
from lexic.parsing.earley.lexruns import collapse_runs, unit_leaves
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX
from lexic.parsing.earley.reduce.policy import DROP, KEEP_RAW, KEEP_REDUCED, YIELD
from lexic.parsing.earley.reduce.reducer import Reducer

DROP_KIND, KEEP_KIND, OTHER_KIND = 0, 1, 2
"""Compiled noise/literal policy kinds — DROP, KEEP_REDUCED (KEEP_RAW for the
literal policy), and anything else (an :data:`OTHER_KIND` noise policy makes
the fused fold miss so the general tree path handles it)."""
DROP_KIND, KEEP_KIND, OTHER_KIND = 0, 1, 2
"""Compiled noise/literal policy kinds — DROP, KEEP_REDUCED (KEEP_RAW for the
literal policy), and anything else (an :data:`OTHER_KIND` noise policy makes
the fused fold miss so the general tree path handles it)."""
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

    :ivar refs: rule_id → the rule's :class:`~lexic.ir.grammar.nodes.IrRuleRef`.
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

    def __init__(self, reducer: Reducer, tables: ParserTables) -> None:
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

    def body(self, reducer: Reducer, rid: int) -> IrSelf:
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
            body = reducer.body(self.refs[rid])
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


def plan_for(reducer: Reducer, tables: ParserTables) -> ReducePlan:
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
    :class:`~lexic.parsing.earley.kernel.forest.ParseTree` and folding it again, one
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

    __slots__ = ("kernel", "reducer", "plan", "memo", "stack", "_bits", "_mask")

    kernel: Kernel
    reducer: Reducer
    plan: ReducePlan
    memo: dict[int, IrSelf]
    stack: list[list]

    def __init__(self, kernel: Kernel, reducer: Reducer) -> None:
        """:param kernel: the finished kernel; :param reducer: the policies."""
        self.kernel = kernel
        self._bits = kernel.tables.packing.bits
        self._mask = kernel.tables.packing.mask
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
            leaf = self.kernel.tables.terms.char_leaf
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
            frame[3].append(self.kernel.tables.terms.char_leaf(char))
        elif kind == OTHER_KIND:
            reducer = self.reducer
            leaf = self.kernel.tables.terms.char_leaf(char)
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
                item = k >> self._bits
                out.append(text[item & self._mask : k & self._mask])
                continue
            sub = self._collect(k)
            if sub is None:
                raise _FusedMiss
            work.extend(reversed(sub))
        return "".join(out)

    def _rule_of(self, handle: int) -> int:
        """The rule_id owning ``handle``'s item."""
        codes = self.kernel.tables.codes
        return codes.arm_rule[codes.code_arm[handle >> (2 * self._bits)]]

    def _collect(self, handle: int) -> list | None:
        """Raw kids of ``handle`` in source order (chars and packed handles).

        Expands a deferred Leo top on first touch. ``None`` when a key is
        missing or packs more than one family (ambiguity — fall back).
        """
        kernel = self.kernel
        links = kernel.st.links
        if handle in kernel.st.leo_links:
            kernel.expand_leo(handle)
        tables = kernel.tables
        item = handle >> self._bits
        end = handle & self._mask
        base = tables.codes.arm_base[tables.codes.code_arm[item >> self._bits]]
        chain = predecessor_chain(links, item, end, base, self._bits)
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
                tid = -nxt[pred_item >> self._bits] - 1
                if lens[tid] == 0:  # a collapsed run — carry its RunTerm
                    child = (atoms[tid], child)
            kids.append(child)
        return kids


_COLLAPSED: dict[tuple[int, int, int], tuple[object, object, ParserTables]] = {}
"""Collapsed-tables memo — (id(reducer), id(grammar), bits) → (reducer,
grammar, tables). Strong references pin both ids against reuse."""


def _run_mode(reducer: Reducer, tables: ParserTables, unit_rid: int) -> int | None:
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
        elif noise is KEEP_REDUCED and reducer.body(ref) is YIELD:
            modes.add(RUN_STR)
        else:
            return None
    return modes.pop() if len(modes) == 1 else None


def collapsed_tables(
    reducer: Reducer, grammar: IrAst, bits: int = ORIGIN_BITS
) -> ParserTables:
    """Tables for ``grammar`` with every run provable safe *for this reducer*
    collapsed to a :class:`~lexic.parsing.earley.kernel.tables.RunTerm`.

    The grammar-side proof (charset, uniqueness, follow disjointness) comes
    from :func:`~lexic.parsing.earley.lexruns.run_candidates`; the reducer-side
    check (:func:`_run_mode`) keeps only runs whose per-char contributions
    the fused fold can reconstruct. Memoised per ``(reducer, grammar, bits)``.

    :param reducer: The reduction policy the collapse must respect.
    :param grammar: An Earley-normalised grammar.
    :param bits: The packing tier the tables compile at.
    :returns: The collapsed tables (the plain tables when nothing collapses).
    """
    key = (id(reducer), id(grammar), bits)
    entry = _COLLAPSED.get(key)
    if entry is not None:
        return entry[2]
    tables = collapse_runs(grammar, partial(_run_mode, reducer), bits)
    _COLLAPSED[key] = (reducer, grammar, tables)
    return tables
