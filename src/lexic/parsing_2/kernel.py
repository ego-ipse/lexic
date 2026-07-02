"""The flat Earley kernel — the compiled grammar's paid loop.

This module is the **compiled-form zone** of ``parsing_2`` (see
:mod:`lexic.parsing_2.tables`): the per-item loop runs over int-coded tables
and packed-int items instead of dispatching IR nodes. Logic stays on classes
and per-parse state on the :class:`Kernel` cursor — but no ``eval`` runs per
item, no IR object is ever a hot-path key, and no tuple is allocated per
advance. The IR seams sit at the edges: :func:`~lexic.parsing_2.tables
.compile_tables` walks the grammar in, and :meth:`Kernel.to_chart` decodes the
finished SPPF out for the IR-native forest readers.

**Packing.** With ``B = ORIGIN_BITS``:

- an *item* is ``code << B | origin`` — advance is ``+ ADVANCE``; for
  realistic grammars this stays a single-digit CPython int, so set/dict
  operations on items run at the primitive floor;
- a *handle* (item over a span, the SPPF link key) is ``item << B | end``;
- the per-column indexes (dedup, waiting, scannable, predicted, Leo memo)
  are position-indexed lists of small containers keyed by bare
  ``rule_id`` / ``term_id`` ints — no packed keys on the per-item path.

**What is preserved.** The full Scott (2008) SPPF (a key reached two ways
files an additional family; identical families dedup), Aycock-Horspool
nullable advance (recording the completer's own empty-completion handle so
the two provenances collapse), and Leo right-recursion with the deferred
``leo_links`` chain rebuild — all ported 1:1 from the IR-dispatch engine, on
ints.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrNone, IrSelf, IrSeq
from lexic.parsing_2.chart import Chart, EarleyItem
from lexic.parsing_2.forest import ParseTree, SppfNode
from lexic.parsing_2.tables import (
    ADVANCE,
    ORIGIN_BITS,
    ORIGIN_MASK,
    ParserTables,
    RunTerm,
    predecessor_chain,
)

KLink = tuple[int, int, "int | str"]
"""One packed SPPF family: ``(predecessor_item, predecessor_end, child)`` —
``child`` is a packed handle (completed sub-derivation) or the scanned char."""


class KernelState(IrLeaf[IrSelf, IrSelf]):
    """Per-parse index state — the kernel's mutable-chart exception.

    The five per-column indexes are position-indexed lists (one small
    container per column, created once); the SPPF tables are parse-global,
    keyed by packed handles. Everything mutates in place.

    :ivar seen: Per column, the packed items already filed (the dedup set).
    :ivar waiting: Per column, ``rule_id`` → items whose dot faces that rule.
    :ivar scannable: Per column, ``term_id`` → items whose dot faces that atom.
    :ivar predicted: Per column, the ``rule_id``\\ s already predicted.
    :ivar leo: Per column, ``rule_id`` → memoised Leo top (``-1`` = none).
    :ivar links: handle → its packed SPPF families.
    :ivar leo_links: deferred Leo provenance — top handle → the bottom
        family of every chain that jumped to it (converging ambiguous
        chains each file theirs), rebuilt into :attr:`links` on demand.
    """

    __slots__ = (
        "seen",
        "waiting",
        "scannable",
        "predicted",
        "leo",
        "links",
        "leo_links",
    )

    seen: list[set[int]]
    waiting: list[dict[int, list[int]]]
    scannable: list[dict[int, list[int]]]
    predicted: list[set[int]]
    leo: list[dict[int, int]]
    links: dict[int, list[KLink]]
    leo_links: dict[int, list[KLink]]

    def __init__(self, columns: int) -> None:
        """Seed empty per-parse state for ``columns`` columns."""
        self.seen = [set() for _ in range(columns)]
        self.waiting = [{} for _ in range(columns)]
        self.scannable = [{} for _ in range(columns)]
        self.predicted = [set() for _ in range(columns)]
        self.leo = [{} for _ in range(columns)]
        self.links = {}
        self.leo_links = {}


class Kernel(IrLeaf[IrSelf, IrSelf]):
    """One Earley parse over compiled tables — chart, SPPF and driver in one.

    Construct per parse, call :meth:`run` once, then read :attr:`accept` (a
    packed accepting item, ``-1`` on no parse) and either build the single
    derivation with :class:`FastTree` or decode to the IR-native forest with
    :meth:`to_chart` / :meth:`accept_node`.

    :ivar tables: The compiled grammar.
    :ivar text: The input.
    :ivar record_links: Whether SPPF families are recorded (off for pure
        recognition, which never reads the forest).
    :ivar cols: Per-column packed items, in insertion order.
    :ivar st: The mutable index state (:class:`KernelState`).
    :ivar accept: The packed accepting item after :meth:`run`, else ``-1``.
    """

    __slots__ = ("tables", "text", "record_links", "cols", "st", "accept")

    tables: ParserTables
    text: str
    record_links: bool
    cols: list[list[int]]
    st: KernelState
    accept: int

    def __init__(
        self, tables: ParserTables, text: str, record_links: bool = True
    ) -> None:
        """Prepare a parse of ``text`` over ``tables``.

        :param tables: The compiled grammar.
        :param text: The input string.
        :param record_links: Record SPPF provenance (skip for recognition).
        :raises UnsupportedConstructError: If ``text`` exceeds the packed
            column capacity (``2**ORIGIN_BITS - 1`` chars).
        """
        if len(text) >= ADVANCE:
            raise UnsupportedConstructError(
                f"parsing_2: input of {len(text)} chars exceeds the packed "
                f"column capacity ({ADVANCE - 1})"
            )
        self.tables = tables
        self.text = text
        self.record_links = record_links
        self.cols = [[] for _ in range(len(text) + 1)]
        self.st = KernelState(len(text) + 1)
        self.accept = -1

    # ── the driver ────────────────────────────────────────────────────

    def run(self) -> Kernel:
        """Build the chart: close each column to a fixpoint, scan one char.

        :returns: ``self``, with :attr:`accept` resolved.
        """
        n = len(self.text)
        if self.tables.start_id >= 0:
            self.st.predicted[0].add(self.tables.start_id)
            self._seed(0, self.tables.start_id)
        for i in range(n):
            self._close(i)
            self._scan(i)
        self._close(n)
        self.accept = self._accept_item(n)
        return self

    def _close(self, i: int) -> None:
        """Close column ``i`` to a fixpoint (predict / complete each item).

        The plain ``for`` over the live list picks up the items predict and
        complete append mid-pass — the Earley fixpoint.
        """
        codes = self.tables.codes
        nxt = codes.next_sym
        nullables = codes.nullable_completes
        predicted_i = self.st.predicted[i]
        for it in self.cols[i]:
            sym = nxt[it >> ORIGIN_BITS]
            if sym > 0:  # predict — and Aycock-Horspool over a nullable target
                rid = sym - 1
                if rid not in predicted_i:
                    predicted_i.add(rid)
                    self._seed(i, rid)
                if nullables[rid]:
                    self._nullable_advance(i, it, nullables[rid])
            elif sym == 0:  # complete
                self._complete(i, it)
            # else: terminal — scanned between columns via the scannable index

    def _seed(self, i: int, rid: int) -> None:
        """Predictor seeding: add rule ``rid``'s dot-0 items to column ``i``."""
        seen_i = self.st.seen[i]
        items_i = self.cols[i]
        codes = self.tables.codes
        nxt = codes.next_sym
        waiting_i = self.st.waiting[i]
        scannable_i = self.st.scannable[i]
        for code in codes.rule_dot0[rid]:
            new = (code << ORIGIN_BITS) | i
            if new not in seen_i:
                seen_i.add(new)
                items_i.append(new)
                s = nxt[code]
                if s > 0:
                    bucket = waiting_i.get(s - 1)
                    if bucket is None:
                        waiting_i[s - 1] = [new]
                    else:
                        bucket.append(new)
                elif s < 0:
                    bucket = scannable_i.get(-s - 1)
                    if bucket is None:
                        scannable_i[-s - 1] = [new]
                    else:
                        bucket.append(new)

    def _advance_all(self, j: int, source: list[int]) -> None:
        """Advance every item in ``source`` by one dot into column ``j``.

        The shared advance half of both the completer (``j`` is the current
        column) and the scanner (``j`` is the next column); dedups against
        column ``j`` and files each new item under its next symbol.
        """
        seen_j = self.st.seen[j]
        items_j = self.cols[j]
        nxt = self.tables.codes.next_sym
        waiting_j = self.st.waiting[j]
        scannable_j = self.st.scannable[j]
        for it in source:
            adv = it + ADVANCE
            if adv not in seen_j:
                seen_j.add(adv)
                items_j.append(adv)
                s = nxt[adv >> ORIGIN_BITS]
                if s > 0:
                    bucket = waiting_j.get(s - 1)
                    if bucket is None:
                        waiting_j[s - 1] = [adv]
                    else:
                        bucket.append(adv)
                elif s < 0:
                    bucket = scannable_j.get(-s - 1)
                    if bucket is None:
                        scannable_j[-s - 1] = [adv]
                    else:
                        bucket.append(adv)

    def _nullable_advance(self, i: int, it: int, completes: tuple[int, ...]) -> None:
        """Aycock-Horspool: advance ``it`` over its nullable target at once.

        Records, per empty-deriving arm, the **same** handle the completer
        files for that arm's empty completion — so the two provenances dedup
        into one family (no spurious ambiguity).
        """
        adv = it + ADVANCE
        seen_i = self.st.seen[i]
        if adv not in seen_i:
            seen_i.add(adv)
            self.cols[i].append(adv)
            s = self.tables.codes.next_sym[adv >> ORIGIN_BITS]
            if s:
                self._file(i, adv, s)
        if self.record_links:
            links = self.st.links
            key = (adv << ORIGIN_BITS) | i
            for done_code in completes:
                child = (((done_code << ORIGIN_BITS) | i) << ORIGIN_BITS) | i
                entry: KLink = (it, i, child)
                bucket = links.get(key)
                if bucket is None:
                    links[key] = [entry]
                elif entry not in bucket:
                    bucket.append(entry)

    def _file(self, i: int, item: int, s: int) -> None:
        """File a just-inserted item under the symbol its dot faces.

        The out-of-line filing used by the rare insert sites (nullable
        advance, Leo top); the hot loops inline this logic.

        :param i: The column the item was inserted into.
        :param item: The packed item.
        :param s: Its non-zero ``next_sym`` discriminator.
        """
        if s > 0:
            index, k = self.st.waiting[i], s - 1
        else:
            index, k = self.st.scannable[i], -s - 1
        bucket = index.get(k)
        if bucket is None:
            index[k] = [item]
        else:
            bucket.append(item)

    def _complete(self, i: int, it: int) -> None:
        """Earley completer: advance every item waiting on the finished rule."""
        c = self.tables.codes
        origin = it & ORIGIN_MASK
        wl = self.st.waiting[origin].get(c.arm_rule[c.code_arm[it >> ORIGIN_BITS]])
        if not wl:
            return
        if len(wl) == 1 and self._try_leo(i, it, wl[0]):
            return
        # wl is the live bucket: a plain ``for`` over the list picks up
        # same-pass appends (advancing files a new waiter when origin == i).
        self._advance_all(i, wl)
        if self.record_links:
            self._record_families(i, wl, origin, (it << ORIGIN_BITS) | i)

    def _record_families(self, i: int, wl: list[int], origin: int, child: int) -> None:
        """Record one packed family per advanced waiter (Scott 2008, deduped)."""
        links = self.st.links
        for w in wl:
            key = ((w + ADVANCE) << ORIGIN_BITS) | i
            entry: KLink = (w, origin, child)
            bucket = links.get(key)
            if bucket is None:
                links[key] = [entry]
            elif entry not in bucket:
                bucket.append(entry)

    def _scan(self, i: int) -> None:
        """Scan at ``text[i]``: advance items facing a matching terminal.

        A char-class match lands one column ahead; a k-char literal match
        (``startswith``, C-level) lands k ahead; a :class:`~lexic.parsing_2
        .tables.RunTerm` consumes its maximal run in one step and lands at
        the run's end.
        """
        text = self.text
        terms = self.tables.terms_for(text[i])
        if not terms:
            return
        scannable_i = self.st.scannable[i]
        literals = self.tables.terms.literals
        runs = self.tables.terms.runs
        lens = self.tables.terms.lens
        for tid in terms:
            bucket = scannable_i.get(tid)
            if not bucket:
                continue
            k = lens[tid]
            if k == 1:
                j = i + 1
            elif k > 1:  # multi-char literal — one C-level comparison
                if not text.startswith(literals[tid], i):
                    continue
                j = i + k
            else:  # k == 0 — a maximal-munch run terminal
                j = self._run_end(i, runs[tid])
                if j < 0:
                    continue
            self._advance_all(j, bucket)
            if self.record_links:
                self._record_scans(i, j, bucket)

    def _run_end(self, i: int, term: RunTerm) -> int:
        """The end of the maximal run of ``term`` starting at ``i``, or ``-1``.

        ``text[i]`` is already known to match (the scanner filtered by first
        char), so the walk starts at ``i + 1``.
        """
        text = self.text
        charset = term.charset
        n = len(text)
        j = i + 1
        while j < n and text[j] in charset:
            j += 1
        return j if j - i >= term.lo else -1

    def _record_scans(self, i: int, j: int, bucket: list[int]) -> None:
        """Record the consumed-text family for each scanned advance."""
        child = self.text[i:j]
        links = self.st.links
        for it in bucket:
            key = ((it + ADVANCE) << ORIGIN_BITS) | j
            entry: KLink = (it, i, child)
            fam = links.get(key)
            if fam is None:
                links[key] = [entry]
            elif entry not in fam:
                fam.append(entry)

    def _accept_item(self, n: int) -> int:
        """The completed start item spanning the whole input, else ``-1``."""
        accepts = self.tables.codes.accept_codes
        for it in self.cols[n]:
            if it >> ORIGIN_BITS in accepts and it & ORIGIN_MASK == 0:
                return it
        return -1

    # ── Leo right-recursion ───────────────────────────────────────────

    def _try_leo(self, i: int, done: int, sole: int) -> bool:
        """Leo fast path: jump a deterministic right-recursion to its top.

        Engages only for chains of length ≥ 2 (the one-level pre-check keeps
        shallow right-recursions on the normal completer); a nullable cycle
        (no topmost item) falls back too.

        :returns: ``True`` when Leo handled the completion.
        """
        c = self.tables.codes
        scode = sole >> ORIGIN_BITS
        if c.next_sym[scode + 1] != 0:  # the awaited ref is not last — no chain
            return False
        if self._leo_sole(sole & ORIGIN_MASK, c.arm_rule[c.code_arm[scode]]) < 0:
            return False  # chain length 1 — normal completion is cheaper
        top = self._leo_resolve(
            i, done & ORIGIN_MASK, c.arm_rule[c.code_arm[done >> ORIGIN_BITS]]
        )
        if top < 0:  # nullable cycle — run the normal completer
            return False
        seen_i = self.st.seen[i]
        if top not in seen_i:
            seen_i.add(top)
            self.cols[i].append(top)
            s = c.next_sym[top >> ORIGIN_BITS]
            if s:
                self._file(i, top, s)
        if self.record_links:
            key = (top << ORIGIN_BITS) | i
            entry: KLink = (sole, done & ORIGIN_MASK, (done << ORIGIN_BITS) | i)
            bucket = self.st.leo_links.get(key)
            if bucket is None:
                self.st.leo_links[key] = [entry]
            elif entry not in bucket:  # a second chain to the same top
                bucket.append(entry)
        return True

    def _leo_sole(self, col: int, rid: int) -> int:
        """The deterministic last-symbol waiter for ``rid`` in ``col``, else -1."""
        wl = self.st.waiting[col].get(rid)
        if wl is None or len(wl) != 1:
            return -1
        sole = wl[0]
        if self.tables.codes.next_sym[(sole >> ORIGIN_BITS) + 1] == 0:
            return sole
        return -1

    def _leo_resolve(self, cur: int, col: int, rid: int) -> int:
        """Leo's transitive (topmost) item for completing ``rid`` at ``col``.

        Climbs the deterministic chain, memoising per closed column (the
        current column ``cur`` is recomputed — its waiters may still grow).
        A **same-column** (empty-span) step stops the climb: those steps are
        cycle- and ambiguity-prone and carry no asymptotic benefit (Leo's
        payoff is cross-column right recursion), so the normal completer —
        which records every family — handles them. Columns then strictly
        decrease up the climb, so termination needs no cycle guard.

        :returns: The packed topmost item, or ``-1``.
        """
        leo_col = self.st.leo[col]
        if col != cur:
            memo = leo_col.get(rid)
            if memo is not None:
                return memo
        found = self._leo_sole(col, rid)
        if found < 0 or (found & ORIGIN_MASK) == col:
            result = -1  # no sole waiter, or an empty-span step — no jump
        else:
            c = self.tables.codes
            parent = self._leo_resolve(
                cur,
                found & ORIGIN_MASK,
                c.arm_rule[c.code_arm[found >> ORIGIN_BITS]],
            )
            result = parent if parent >= 0 else found + ADVANCE
        if col != cur:
            leo_col[rid] = result
        return result

    def expand_leo(self, key: int) -> None:
        """Rebuild the deferred right-recursion chain under Leo top ``key``.

        Files each skipped completion's family into :attr:`KernelState.links`
        bottom-up, O(chain), idempotent (families dedup).
        """
        top = key >> ORIGIN_BITS
        end = key & ORIGIN_MASK
        for bottom in self.st.leo_links[key]:
            self._expand_chain(top, end, bottom)

    def _expand_chain(self, top: int, end: int, bottom: KLink) -> None:
        """Rebuild one deferred chain from its bottom family up to ``top``."""
        links = self.st.links
        c = self.tables.codes
        waiter, waiter_end, child = bottom
        while True:
            adv = waiter + ADVANCE
            k = (adv << ORIGIN_BITS) | end
            entry: KLink = (waiter, waiter_end, child)
            bucket = links.get(k)
            if bucket is None:
                links[k] = [entry]
            elif entry not in bucket:
                bucket.append(entry)
            if adv == top:
                return
            # ``adv`` completes its rule over waiter_origin..end; the lone item
            # awaiting it there is the next chain link (deterministic by
            # construction — that is why Leo fired).
            child = k
            waiter_end = waiter & ORIGIN_MASK
            rid = c.arm_rule[c.code_arm[waiter >> ORIGIN_BITS]]
            waiter = self.st.waiting[waiter_end][rid][0]

    # ── decoding to the IR-native forest ──────────────────────────────

    def decode_item(self, item: int) -> EarleyItem:
        """The legacy :class:`EarleyItem` tuple for a packed ``item``."""
        t = self.tables
        code = item >> ORIGIN_BITS
        aid = t.codes.code_arm[code]
        return (
            t.decode.rule_refs[t.codes.arm_rule[aid]],
            t.decode.arm_seqs[aid],
            code - t.codes.arm_base[aid],
            item & ORIGIN_MASK,
        )

    def accept_node(self) -> IrSelf:
        """The accepting :class:`SppfNode` over the whole input, or IrNone."""
        if self.accept < 0:
            return IrNone
        return SppfNode(self.decode_item(self.accept), len(self.text))

    def to_chart(self) -> Chart:
        """Decode the packed SPPF into the IR-native :class:`Chart`.

        Deferred Leo chains are expanded eagerly first, so the decoded chart
        is complete and the forest readers never consult ``leo_links``. Used
        by the ambiguity / enumeration paths only — the unambiguous fast path
        (:class:`FastTree`) reads the packed links directly.
        """
        for key in list(self.st.leo_links):
            if key not in self.st.links:
                self.expand_leo(key)
        chart = Chart()
        links = chart.links
        for key, bucket in self.st.links.items():
            dkey = (self.decode_item(key >> ORIGIN_BITS), key & ORIGIN_MASK)
            for pred, pend, child in bucket:
                links += (dkey, (self.decode_item(pred), pend, self._child(child)))
        return chart

    def _child(self, child: int | str) -> IrSelf:
        """Decode a packed family child — a handle or a scanned char."""
        if isinstance(child, int):
            return SppfNode(self.decode_item(child >> ORIGIN_BITS), child & ORIGIN_MASK)
        return self.tables.char_leaf(child)


class FastTree(IrLeaf[IrSelf, IrSelf]):
    """Iterative single-derivation builder over the packed SPPF.

    The unambiguous fast path: an explicit work stack (never the C stack)
    resolves each handle's kids by walking the binarised predecessor chain,
    memoising built subtrees. :meth:`build` returns :data:`IrNone` on a
    fast-path miss (a key with more than one family, i.e. ambiguity, or a
    missing link) so the caller falls back to the trampolined enumeration
    over the decoded chart.

    :ivar kernel: The finished kernel whose links to walk.
    :ivar memo: handle → its built :class:`ParseTree`.
    :ivar stack: Work frames ``(handle, dest, slot, resolved | None)``.
    """

    __slots__ = ("kernel", "memo", "stack")

    kernel: Kernel
    memo: dict[int, ParseTree]
    stack: list[tuple[int, list, int, list | None]]

    def __init__(self, kernel: Kernel) -> None:
        """:param kernel: the finished kernel to read."""
        self.kernel = kernel
        self.memo = {}
        self.stack = []

    def build(self, handle: int) -> IrSelf:
        """The single :class:`ParseTree` under ``handle``, or :data:`IrNone`.

        :param handle: The packed accepting handle ``(item << B) | end``.
        :returns: The tree, or :data:`IrNone` on a fast-path miss.
        """
        holder: list[IrSelf] = [IrNone]
        self.stack = [(handle, holder, 0, None)]
        while self.stack:
            if not self._step():
                return IrNone
        return holder[0]

    def _step(self) -> bool:
        """Process the top frame; ``False`` aborts the build (fast-path miss)."""
        handle, dest, slot, resolved = self.stack[-1]
        cached = self.memo.get(handle)
        if cached is not None:
            dest[slot] = cached
            self.stack.pop()
            return True
        kernel = self.kernel
        if resolved is None:  # first visit — expand Leo, collect kids
            st = kernel.st
            if handle in st.leo_links and handle not in st.links:
                kernel.expand_leo(handle)
            resolved = self._collect(handle)
            if resolved is None:
                return False
            self.stack[-1] = (handle, dest, slot, resolved)
        pending = self._pending(resolved)
        if pending:
            self.stack.extend(pending)
            return True
        t = kernel.tables
        rid = t.codes.arm_rule[t.codes.code_arm[handle >> (2 * ORIGIN_BITS)]]
        tree = ParseTree(t.decode.rule_refs[rid], IrSeq(*resolved))
        self.memo[handle] = tree
        dest[slot] = tree
        self.stack.pop()
        return True

    def _collect(self, handle: int) -> list | None:
        """Kids of ``handle`` in source order, walking the predecessor chain.

        ``None`` when a key is missing or packs more than one family — the
        caller falls back to the trampolined enumeration.
        """
        t = self.kernel.tables
        item = handle >> ORIGIN_BITS
        end = handle & ORIGIN_MASK
        base = t.codes.arm_base[t.codes.code_arm[item >> ORIGIN_BITS]]
        chain = predecessor_chain(self.kernel.st.links, item, end, base)
        if chain is None:
            return None  # missing (no build) or ambiguous (fall back)
        return [c if isinstance(c, int) else t.char_leaf(c) for _, _, c in chain]

    def _pending(self, resolved: list) -> list:
        """Swap memoised kids in place; return frames for those still unbuilt."""
        memo = self.memo
        out: list[tuple[int, list, int, None]] = []
        for idx, child in enumerate(resolved):
            if isinstance(child, int):  # a packed handle, not yet built
                cached = memo.get(child)
                if cached is not None:
                    resolved[idx] = cached
                else:
                    out.append((child, resolved, idx, None))
        return out
