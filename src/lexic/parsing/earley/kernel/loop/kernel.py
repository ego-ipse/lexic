"""The flat Earley kernel — the compiled grammar's paid loop.

This module is the **compiled-form zone** of ``parsing`` (see
:mod:`lexic.parsing.earley.kernel.tables`): the per-item loop runs over int-coded tables
and packed-int items instead of dispatching IR nodes. Logic stays on classes
and per-parse state on the :class:`Kernel` cursor — but no ``eval`` runs per
item, no IR object is ever a hot-path key, and no tuple is allocated per
advance. The IR seams sit at the edges: :func:`~lexic.parsing.earley.kernel.tables
.compile_tables` walks the grammar in, and :mod:`~lexic.parsing.earley.kernel
.readout` decodes the finished SPPF out for the IR-native forest readers.

**Packing.** With ``B = tables.packing.bits`` (the tables' tier):

- an *item* is ``code << B | origin`` — advance is ``+ packing.advance``; for
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

from itertools import islice
from typing import Callable, Self

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf
from lexic.parsing.earley.kernel.loop.leo import leo_resolve, leo_sole
from lexic.parsing.earley.kernel.loop.state import KernelState, KLink
from lexic.parsing.earley.kernel.tables.atoms import RunTerm
from lexic.parsing.earley.kernel.tables.records import ParserTables

Delegate = Callable[[str, int], tuple[int, object] | None]
"""An island-interior delegate: ``(window_text, pos) -> (end, payload) | None``.
Opaque to the kernel (the ``pda`` package builds and populates it); ``None``
means the delegate declined, so the predictor falls through to normal
prediction (the fail-soft safety net). See :meth:`Kernel._seed`."""


class Kernel(IrLeaf[IrSelf, IrSelf]):
    """One Earley parse over compiled tables — chart, SPPF and driver in one.

    Construct per parse, call :meth:`run` once, then read the result through
    :mod:`~lexic.parsing.earley.kernel.forest.readout` — :func:`~lexic.parsing.earley
    .kernel.readout.accept_item` for the packed accepting item (``-1`` on no
    parse), then either the single derivation via
    :class:`~lexic.parsing.earley.kernel.forest.fasttree.FastTree` or the IR-native
    forest via :func:`~lexic.parsing.earley.kernel.forest.readout.to_chart` /
    :func:`~lexic.parsing.earley.kernel.forest.readout.accept_node`.

    :ivar tables: The compiled grammar.
    :ivar text: The input.
    :ivar record_links: Whether SPPF families are recorded (off for pure
        recognition, which never reads the forest).
    :ivar cols: Per-column packed items, in insertion order.
    :ivar st: The mutable index state (:class:`KernelState`).
    :ivar delegates: rule_id → its island-interior :data:`Delegate`, or an
        empty mapping (the common non-island case). Opaque callables the
        ``pda`` package populates; the kernel only invokes them in
        :meth:`_seed` (the kernel stays PDA-agnostic — see
        :mod:`lexic.parsing.pda.runtime.islands`).
    :ivar delegated: handle of an injected delegated completion → its
        :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` (empty on every
        non-island parse).
    """

    __slots__ = (
        "tables",
        "text",
        "record_links",
        "cols",
        "st",
        "delegates",
        "delegated",
    )

    tables: ParserTables
    text: str
    record_links: bool
    cols: list[list[int]]
    st: KernelState
    delegates: dict[int, Delegate]
    delegated: dict[int, PayloadLeaf]

    def __init__(
        self,
        tables: ParserTables,
        text: str,
        record_links: bool = True,
        delegates: dict[int, Delegate] | None = None,
    ) -> None:
        """Prepare a parse of ``text`` over ``tables``.

        :param tables: The compiled grammar.
        :param text: The input string.
        :param record_links: Record SPPF provenance (skip for recognition).
        :param delegates: rule_id → island-interior :data:`Delegate`, or
            ``None`` (no delegation — every non-island parse). Populated by the
            ``pda`` package for island sub-parses only.
        :raises UnsupportedConstructError: If ``text`` exceeds the packed
            column capacity (``tables.packing.advance - 1`` chars).
        """
        if len(text) >= tables.packing.advance:
            raise UnsupportedConstructError(
                f"parsing: input of {len(text)} chars exceeds the packed "
                f"column capacity ({tables.packing.advance - 1})"
            )
        self.tables = tables
        self.text = text
        self.record_links = record_links
        self.cols = [[] for _ in range(len(text) + 1)]
        self.st = KernelState(len(text) + 1)
        self.delegates = delegates or {}
        self.delegated = {}

    # ── the driver ────────────────────────────────────────────────────

    def run(self) -> Self:
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
        return self

    def _close(self, i: int, start: int = 0) -> None:
        """Close column ``i`` to a fixpoint (predict / complete each item).

        The plain ``for`` over the live list picks up the items predict and
        complete append mid-pass — the Earley fixpoint. ``start`` skips the
        first ``start`` items (the resumable close-from-index: they were
        fully processed by an earlier close of this column); an ``islice``
        iterator picks up mid-pass appends exactly like the plain loop.
        """
        codes = self.tables.codes
        nxt = codes.next_sym
        nullables = codes.nullable_completes
        predicted_i = self.st.predicted[i]
        delegated = self.delegated
        bits, mask = self.tables.packing.bits, self.tables.packing.mask
        col = self.cols[i]
        for it in islice(col, start, None) if start else col:
            sym = nxt[it >> bits]
            if sym > 0:  # predict — and Aycock-Horspool over a nullable target
                rid = sym - 1
                if rid not in predicted_i:
                    predicted_i.add(rid)
                    self._seed(i, rid)
                if nullables[rid]:
                    self._nullable_advance(i, it, nullables[rid])
            elif sym == 0:  # complete — zero-width completions are redundant:
                # every waiter facing a nullable rule is advanced (and its
                # family recorded) by _nullable_advance at its own visit in
                # this same fixpoint pass, and Leo never engages on an empty
                # span (_leo_resolve stops on same-column steps), so the
                # completer would only re-derive deduped items and identical
                # families.
                if delegated:  # island-interior delegation (empty otherwise)
                    payload = delegated.get((it << bits) | i)
                    if payload is not None:
                        self._complete_delegated(i, it, payload)
                        continue
                if it & mask != i:
                    self._complete(i, it)
            # else: terminal — scanned between columns via the scannable index

    def _seed(self, i: int, rid: int) -> None:
        """Predictor seeding: add rule ``rid``'s FIRST-viable dot-0 items to ``i``.

        Invariant — **no dedup needed here.** Dot-0 items are minted only by
        this method, and both its call sites are ``predicted``-guarded
        (:meth:`run` for the start rule, :meth:`_close` for predictions), so a
        given ``(column, rule)`` seeds at most once. Every dotted position has
        a globally unique code and every *advanced* item (completer, scanner,
        nullable-advance, Leo top) carries dot ≥ 1, so a fresh seed can never
        collide with anything already in ``seen`` — the membership test and the
        ``seen.add`` are pure waste and omitted here (the seeds are simply not
        filed into ``seen``, which no lookup ever consults for a dot-0 code).
        This holds *only* while both call sites stay ``predicted``-guarded and
        no other code mints dot-0 items; either change reintroduces the
        collision and must restore the dedup. FIRST gating (below) only
        *removes* seeds, never re-adds one, so it leaves this proof intact.

        Invariant — **FIRST gating is sound.** An arm whose gate is a charset
        that misses ``text[i]`` can contribute to no derivation at ``i``: a
        non-empty derivation's first consumed char is in the arm's
        nullable-prefix-closed FIRST, and an empty derivation implies the arm
        is empty-deriving — whose gate is ``None`` (always seed). A poisoned
        FIRST is also ``None`` and never gates. Empty-deriving arms must
        ALWAYS seed: :meth:`_nullable_advance` records their done-codes as
        SPPF children, and a nested-nullable arm's empty completion needs its
        own advance links in the chart for :class:`FastTree` /
        :class:`~lexic.parsing.earley.reduce.FusedReduce` to walk. The ``predicted``
        guard stays valid (the char is fixed per column). Leo: fewer waiters
        can only shrink buckets — Leo may *engage more often*; the chart's
        shape changes, the language and derivation sets do not. At column
        ``n == len(text)`` the char slice is ``""``, which no charset
        contains — only always-seed arms file, exactly the EOF rule.

        Invariant — **delegation is a sound replacement.** When ``rid`` carries
        an island-interior :data:`Delegate` and the sub-run succeeds, the arm
        seeding below is *skipped* and a completed ``rid`` item is injected at
        the sub-run's end column instead (:meth:`_inject_delegate`): the normal
        completer advances the by-then-fully-populated ``waiting[i][rid]`` at
        ``_close(end)``, so late waiters (added after this predict) are covered.
        A delegable rule is conflict-free, so its parse from ``i`` is the unique
        one the grammar admits there — the injected span is a true derivation.
        A declined delegate (``None``) falls through to normal seeding (the
        fail-soft net); delegation never runs on a non-island parse
        (``delegates`` is empty).
        """
        if self.delegates:
            delegate = self.delegates.get(rid)
            if delegate is not None:
                result = delegate(self.text, i)
                if result is not None:
                    self._inject_delegate(i, rid, result[0], result[1])
                    return
        items_i = self.cols[i]
        waiting_i = self.st.waiting[i]
        scannable_i = self.st.scannable[i]
        char = self.text[i : i + 1]
        for shifted, s, gate in self.tables.codes.rule_seed_gates[rid]:
            if gate is not None and char not in gate:
                continue
            new = shifted | i
            items_i.append(new)
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
        pk = self.tables.packing
        bits, advance = pk.bits, pk.advance
        for it in source:
            adv = it + advance
            if adv not in seen_j:
                seen_j.add(adv)
                items_j.append(adv)
                s = nxt[adv >> bits]
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
        pk = self.tables.packing
        bits = pk.bits
        adv = it + pk.advance
        seen_i = self.st.seen[i]
        if adv not in seen_i:
            seen_i.add(adv)
            self.cols[i].append(adv)
            s = self.tables.codes.next_sym[adv >> bits]
            if s:
                self.st.file_item(i, adv, s)
        if self.record_links:
            links = self.st.links
            key = (adv << bits) | i
            bucket = links.get(key)
            if bucket is None:  # completes is never empty — no empty bucket
                bucket = links[key] = []
            for done_code in completes:
                entry: KLink = (
                    it,
                    i,
                    (((done_code << bits) | i) << bits) | i,
                )
                if entry not in bucket:
                    bucket.append(entry)

    def _complete(self, i: int, it: int) -> None:
        """Earley completer: advance every item waiting on the finished rule."""
        c = self.tables.codes
        bits = self.tables.packing.bits
        origin = it & self.tables.packing.mask
        wl = self.st.waiting[origin].get(c.arm_rule[c.code_arm[it >> bits]])
        if not wl:
            return
        if (
            len(wl) == 1
            # the awaited ref is the sole waiter's last symbol — the Leo
            # precondition, probed here so the miss costs no call
            and c.next_sym[(wl[0] >> bits) + 1] == 0
            and self._try_leo(i, it, wl[0])
        ):
            return
        # wl is the live bucket: a plain ``for`` over the list picks up
        # same-pass appends (advancing files a new waiter when origin == i).
        self._advance_all(i, wl)
        if self.record_links:
            self._record_families(i, wl, origin, (it << bits) | i)

    def _record_families(self, i: int, wl: list[int], origin: int, child: int) -> None:
        """Record one packed family per advanced waiter (Scott 2008, deduped)."""
        links = self.st.links
        pk = self.tables.packing
        bits, advance = pk.bits, pk.advance
        for w in wl:
            key = ((w + advance) << bits) | i
            entry: KLink = (w, origin, child)
            bucket = links.get(key)
            if bucket is None:
                links[key] = [entry]
            elif entry not in bucket:
                bucket.append(entry)

    # ── island-interior delegation ────────────────────────────────────

    def _inject_delegate(self, i: int, rid: int, end: int, payload: object) -> None:
        """File a delegated completion of ``rid`` over ``[i, end]`` (origin ``i``).

        Adds one completed ``rid`` item to column ``end`` (so ``_close(end)``
        runs the completer once column ``i`` is fully closed and every waiter
        facing ``rid`` is present) and records the pre-built ``payload`` and the
        consumed span as a :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` on
        :attr:`delegated`. Deduped against column ``end`` so a rule
        predicted twice at ``i`` files its span once. On the recognition path
        (``record_links`` off) no leaf is stored — the completion still advances
        waiters, exactly what recognition needs.

        :param i: The delegated rule's start column.
        :param rid: The delegated rule id.
        :param end: The sub-run's end column (``> i`` — nullable rules are never
            delegated, so the completion is non-empty and the normal completer
            fires on it).
        :param payload: The sub-run's pre-built value (model / reduced IR).
        """
        codes = self.tables.codes
        bits = self.tables.packing.bits
        done = codes.rule_seed_gates[rid][0][0] >> bits  # first arm's dot-0 code
        nxt = codes.next_sym
        while nxt[done] != 0:  # walk to that arm's completed code
            done += 1
        it = (done << bits) | i
        seen_end = self.st.seen[end]
        if it in seen_end:
            return
        seen_end.add(it)
        self.cols[end].append(it)
        if self.record_links:
            self.delegated[(it << bits) | end] = PayloadLeaf(payload, self.text[i:end])

    def _complete_delegated(self, end: int, it: int, payload: PayloadLeaf) -> None:
        """Advance every waiter on a delegated ``rid`` completion, payload-child.

        The completer for an injected delegated item: like :meth:`_complete` but
        the recorded family's consumed child IS the :class:`~lexic.parsing.earley
        .forest.PayloadLeaf` (the pre-folded sub-result), so the decoders splice
        it straight through — no ``rid`` sub-derivation is ever walked. Leo is
        not attempted (a delegated span is a self-contained sub-parse, not a
        right-recursion chain).
        """
        c = self.tables.codes
        pk = self.tables.packing
        bits = pk.bits
        origin = it & pk.mask
        wl = self.st.waiting[origin].get(c.arm_rule[c.code_arm[it >> bits]])
        if not wl:
            return
        self._advance_all(end, wl)
        if self.record_links:
            links = self.st.links
            advance = pk.advance
            for w in wl:
                key = ((w + advance) << bits) | end
                entry: KLink = (w, origin, payload)
                bucket = links.get(key)
                if bucket is None:
                    links[key] = [entry]
                elif entry not in bucket:
                    bucket.append(entry)

    def _scan(self, i: int) -> None:
        """Scan at ``text[i]``: advance items facing a matching terminal.

        A char-class match lands one column ahead; a k-char literal match
        (``startswith``, C-level) lands k ahead; a :class:`~lexic.parsing
        .tables.RunTerm` consumes its maximal run in one step and lands at
        the run's end.
        """
        text = self.text
        terms = self.tables.terms.terms_for(text[i])
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
        pk = self.tables.packing
        bits, advance = pk.bits, pk.advance
        for it in bucket:
            key = ((it + advance) << bits) | j
            entry: KLink = (it, i, child)
            fam = links.get(key)
            if fam is None:
                links[key] = [entry]
            elif entry not in fam:
                fam.append(entry)

    # ── windowed prefix completion (islands) ──────────────────────────

    def longest_start_completion(self) -> tuple[int, int] | None:
        """Longest whole-prefix completion of the start rule (origin 0).

        The islands seam (:mod:`lexic.parsing.pda.runtime.runtime`): seed the start
        rule at column 0, drive the chart column by column over the window,
        and after closing each reachable column record the widest completed
        start item spanning ``[0, j]``. A later column overwrites an earlier
        one, so the result is the *longest* completion; empty columns are
        skipped rather than terminal, since a multi-char literal scan can land
        past one. Additive to :meth:`run` — the main-loop fast path is
        untouched; a fresh kernel calls this *instead of* :meth:`run` (with
        ``record_links=True`` so :class:`FastTree` can decode the winner).

        :returns: ``(accepting_item, end_column)`` for the longest origin-0
            completion of the start rule, or ``None`` if it never completes.
        """
        tables = self.tables
        if tables.start_id < 0:
            return None
        self.st.predicted[0].add(tables.start_id)
        self._seed(0, tables.start_id)
        accepts = tables.codes.accept_codes
        bits, mask = tables.packing.bits, tables.packing.mask
        best: tuple[int, int] | None = None
        n = len(self.text)
        for j in range(n + 1):
            col = self.cols[j]
            if not col:
                continue
            self._close(j)
            for it in col:
                if it >> bits in accepts and it & mask == 0:
                    best = (it, j)
            if j < n:
                self._scan(j)
        return best

    # ── Leo right-recursion ───────────────────────────────────────────

    def _try_leo(self, i: int, done: int, sole: int) -> bool:
        """Leo fast path: jump a deterministic right-recursion to its top.

        Engages only for chains of length ≥ 2 (the one-level pre-check keeps
        shallow right-recursions on the normal completer); a nullable cycle
        (no topmost item) falls back too.

        :returns: ``True`` when Leo handled the completion.
        """
        t = self.tables
        c = t.codes
        bits, mask = t.packing.bits, t.packing.mask
        st = self.st
        if leo_sole(st, t, sole & mask, c.arm_rule[c.code_arm[sole >> bits]]) < 0:
            return False  # chain length 1 — normal completion is cheaper
        top = leo_resolve(st, t, i, done & mask, c.arm_rule[c.code_arm[done >> bits]])
        if top < 0:  # nullable cycle — run the normal completer
            return False
        seen_i = st.seen[i]
        if top not in seen_i:
            seen_i.add(top)
            self.cols[i].append(top)
            s = c.next_sym[top >> bits]
            if s:
                st.file_item(i, top, s)
        if self.record_links:
            key = (top << bits) | i
            entry: KLink = (sole, done & mask, (done << bits) | i)
            bucket = st.leo_links.get(key)
            if bucket is None:
                st.leo_links[key] = [entry]
            elif entry not in bucket:  # a second chain to the same top
                bucket.append(entry)
        return True
