"""The flat Earley kernel — the compiled grammar's paid loop.

This module is the **compiled-form zone** of ``parsing`` (see
:mod:`lexic.parsing.earley.tables`): the per-item loop runs over int-coded tables
and packed-int items instead of dispatching IR nodes. Logic stays on classes
and per-parse state on the :class:`Kernel` cursor — but no ``eval`` runs per
item, no IR object is ever a hot-path key, and no tuple is allocated per
advance. The IR seams sit at the edges: :func:`~lexic.parsing.earley.tables
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

from typing import Callable

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrNone, IrSelf, IrSeq
from lexic.parsing.earley.chart import Chart, EarleyItem
from lexic.parsing.earley.forest import ParseTree, PayloadLeaf, RootNode, SppfNode
from lexic.parsing.earley.tables import (
    ADVANCE,
    ORIGIN_BITS,
    ORIGIN_MASK,
    ParserTables,
    RunTerm,
    predecessor_chain,
)

KLink = tuple[int, int, "int | str | PayloadLeaf"]
"""One packed SPPF family: ``(predecessor_item, predecessor_end, child)`` —
``child`` is a packed handle (completed sub-derivation), the scanned char, or a
delegated :class:`~lexic.parsing.earley.forest.PayloadLeaf` (island-interior
delegation)."""

Delegate = Callable[[str, int], "tuple[int, object] | None"]
"""An island-interior delegate: ``(window_text, pos) -> (end, payload) | None``.
Opaque to the kernel (the ``pda`` package builds and populates it); ``None``
means the delegate declined, so the predictor falls through to normal
prediction (the fail-soft safety net). See :meth:`Kernel._seed`."""


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
    :ivar delegates: rule_id → its island-interior :data:`Delegate`, or an
        empty mapping (the common non-island case). Opaque callables the
        ``pda`` package populates; the kernel only invokes them in
        :meth:`_seed` (the kernel stays PDA-agnostic — see
        :mod:`lexic.parsing.pda.runtime.islands`).
    :ivar delegated: handle of an injected delegated completion → its
        :class:`~lexic.parsing.earley.forest.PayloadLeaf` (empty on every
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
            column capacity (``2**ORIGIN_BITS - 1`` chars).
        """
        if len(text) >= ADVANCE:
            raise UnsupportedConstructError(
                f"parsing: input of {len(text)} chars exceeds the packed "
                f"column capacity ({ADVANCE - 1})"
            )
        self.tables = tables
        self.text = text
        self.record_links = record_links
        self.cols = [[] for _ in range(len(text) + 1)]
        self.st = KernelState(len(text) + 1)
        self.delegates = delegates or {}
        self.delegated = {}

    @property
    def accept(self) -> int:
        """The packed accepting item after :meth:`run` (``-1`` on no parse).

        Computed on read from the final column rather than stored — one fewer
        per-parse slot, and only read a handful of times after a full run (the
        island path reads its completion off
        :meth:`longest_start_completion` instead, never this).
        """
        return self._accept_item(len(self.text))

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
        delegated = self.delegated
        for it in self.cols[i]:
            sym = nxt[it >> ORIGIN_BITS]
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
                    payload = delegated.get((it << ORIGIN_BITS) | i)
                    if payload is not None:
                        self._complete_delegated(i, it, payload)
                        continue
                if it & ORIGIN_MASK != i:
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
            bucket = links.get(key)
            if bucket is None:  # completes is never empty — no empty bucket
                bucket = links[key] = []
            for done_code in completes:
                entry: KLink = (
                    it,
                    i,
                    (((done_code << ORIGIN_BITS) | i) << ORIGIN_BITS) | i,
                )
                if entry not in bucket:
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
        if (
            len(wl) == 1
            # the awaited ref is the sole waiter's last symbol — the Leo
            # precondition, probed here so the miss costs no call
            and c.next_sym[(wl[0] >> ORIGIN_BITS) + 1] == 0
            and self._try_leo(i, it, wl[0])
        ):
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

    # ── island-interior delegation ────────────────────────────────────

    def _inject_delegate(self, i: int, rid: int, end: int, payload: object) -> None:
        """File a delegated completion of ``rid`` over ``[i, end]`` (origin ``i``).

        Adds one completed ``rid`` item to column ``end`` (so ``_close(end)``
        runs the completer once column ``i`` is fully closed and every waiter
        facing ``rid`` is present) and records the pre-built ``payload`` and the
        consumed span as a :class:`~lexic.parsing.earley.forest.PayloadLeaf` on
        :attr:`KernelState.delegated`. Deduped against column ``end`` so a rule
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
        done = codes.rule_seed_gates[rid][0][0] >> ORIGIN_BITS  # first arm's dot-0 code
        nxt = codes.next_sym
        while nxt[done] != 0:  # walk to that arm's completed code
            done += 1
        it = (done << ORIGIN_BITS) | i
        seen_end = self.st.seen[end]
        if it in seen_end:
            return
        seen_end.add(it)
        self.cols[end].append(it)
        if self.record_links:
            self.delegated[(it << ORIGIN_BITS) | end] = PayloadLeaf(
                payload, self.text[i:end]
            )

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
        origin = it & ORIGIN_MASK
        wl = self.st.waiting[origin].get(c.arm_rule[c.code_arm[it >> ORIGIN_BITS]])
        if not wl:
            return
        self._advance_all(end, wl)
        if self.record_links:
            links = self.st.links
            for w in wl:
                key = ((w + ADVANCE) << ORIGIN_BITS) | end
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

    def accept_items(self) -> list[int]:
        """Every completed start item spanning the whole input (origin 0).

        Two or more items means the start symbol derives the whole input via
        distinct productions — genuine arm ambiguity with no parent waiter to
        aggregate it (see :class:`~lexic.parsing.earley.forest.RootNode`).

        :returns: The accepting items, in chart order (empty on no parse).
        """
        n = len(self.text)
        accepts = self.tables.codes.accept_codes
        return [
            it
            for it in self.cols[n]
            if it >> ORIGIN_BITS in accepts and it & ORIGIN_MASK == 0
        ]

    @property
    def root_ambiguous(self) -> bool:
        """Whether the start symbol completes the whole input via ≥2 productions.

        The gate the single-derivation fast paths consult: a many-production
        root cannot be built by :class:`FastTree` off one accepting item (the
        sibling productions live in other items), so those paths fall through to
        the trampolined enumeration over the :class:`~lexic.parsing.earley.forest
        .RootNode`.
        """
        return len(self.accept_items()) > 1

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
        best: tuple[int, int] | None = None
        n = len(self.text)
        for j in range(n + 1):
            col = self.cols[j]
            if not col:
                continue
            self._close(j)
            for it in col:
                if it >> ORIGIN_BITS in accepts and it & ORIGIN_MASK == 0:
                    best = (it, j)
            if j < n:
                self._scan(j)
        return best

    def can_extend_at(self, col: int, char: str) -> bool:
        """Whether the parse at ``col`` could consume ``char`` next — a MAY answer.

        The islands seam's valid-prefix probe: after a windowed
        :meth:`longest_start_completion`, the caller asks whether the FULL
        text's next character is viable at a SHORT-OF-EDGE completion column
        — if it is, the completion may be a window-cut truncation and the
        window must grow.

        The chart is complete evidence exactly there: seeding is FIRST-gated
        by the column's own window character, and a short-of-edge column's
        window character IS the probe character, so every seed viable for it
        was admitted and registered — an empty/non-matching ``scannable`` is
        a *sighted* refusal, not blindness. Two conservative escapes remain,
        each answering MAY (which only ever grows the window):

        - a column where a delegate sub-run landed (the delegate's interior
          continuation items were never seeded into the chart) — derived
          from :attr:`delegated`'s handles, whose low bits are the landing
          column (islands always run with ``record_links``, so every
          landing is recorded);
        - a probe character that is NOT the column's window character (an
          out-of-domain call — the gates were evaluated with a different
          char, so the chart proves nothing about this one).

        :param col: The completion column to probe (its closure already ran).
        :param char: The next character of the full input.
        :returns: ``True`` when ``char`` may be consumable at ``col``.
        """
        if any(handle & ORIGIN_MASK == col for handle in self.delegated):
            return True
        if col >= len(self.text) or self.text[col] != char:
            return True
        return any(
            self.st.scannable[col].get(tid) for tid in self.tables.terms_for(char)
        )

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

        Invariant — **expand on presence, never gate on** ``links``. A Leo top
        can carry *mixed provenance*: some of its families recorded by the
        normal completer (a later completion of the same rule found ≥2
        waiters), others deferred here. ``key in links`` therefore does NOT
        mean the deferred chains are represented — a caller that skips
        expansion on that test drops the deferred derivations (the L4
        embedded-ambiguity undercount). Idempotence makes the unconditional
        call safe.
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
        """The :class:`EarleyItem` tuple for a packed ``item`` — the readable
        (non-int-coded) shape the chart/forest readers walk."""
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
        """The forest root over the whole input, or :data:`IrNone` on no parse.

        A single accepting production returns its :class:`SppfNode` directly (the
        common case — no aggregation needed). Two or more accepting productions
        return a :class:`RootNode` packing them, so the enumeration readers see
        every arm the start symbol derives the input through.
        """
        items = self.accept_items()
        if not items:
            return IrNone
        n = len(self.text)
        if len(items) == 1:
            return SppfNode(self.decode_item(items[0]), n)
        symbol = self.decode_item(items[0])[0]
        return RootNode(
            symbol, IrSeq(*(SppfNode(self.decode_item(it), n) for it in items))
        )

    def to_chart(self) -> Chart:
        """Decode the packed SPPF into the IR-native :class:`Chart`.

        Deferred Leo chains are expanded eagerly first, so the decoded chart
        is complete and the forest readers never consult ``leo_links``. Used
        by the ambiguity / enumeration paths only — the unambiguous fast path
        (:class:`FastTree`) reads the packed links directly.
        """
        for key in self.st.leo_links:
            self.expand_leo(key)
        chart = Chart()
        links = chart.links
        for key, bucket in self.st.links.items():
            dkey = (self.decode_item(key >> ORIGIN_BITS), key & ORIGIN_MASK)
            for pred, pend, child in bucket:
                links += (dkey, (self.decode_item(pred), pend, self._child(child)))
        return chart

    def _child(self, child: int | str | PayloadLeaf) -> IrSelf:
        """Decode a packed family child — a handle, a scanned char, or a payload."""
        if isinstance(child, int):
            return SppfNode(self.decode_item(child >> ORIGIN_BITS), child & ORIGIN_MASK)
        if isinstance(child, PayloadLeaf):  # delegated pre-folded child
            return child
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
        return self.memo.get(handle, IrNone)

    def _step(self) -> bool:
        """Process the top frame; ``False`` aborts the build (fast-path miss)."""
        handle, dest, slot, resolved = self.stack[-1]
        kernel = self.kernel
        if resolved is not None:  # revisit — every pending kid built in place
            self._build(handle, dest, slot, resolved)
            return True
        cached = self.memo.get(handle)
        if cached is not None:
            dest[slot] = cached
            self.stack.pop()
            return True
        item = handle >> ORIGIN_BITS
        if item & ORIGIN_MASK == handle & ORIGIN_MASK:  # zero-width
            t = kernel.tables
            tree = t.empty_tree(t.codes.arm_rule[t.codes.code_arm[item >> ORIGIN_BITS]])
            if tree is not None:  # the shared input-independent derivation
                dest[slot] = tree
                self.stack.pop()
                return True
        st = kernel.st
        if handle in st.leo_links:
            kernel.expand_leo(handle)
        resolved = self._collect(handle)
        if resolved is None:
            return False
        pending = self._pending(resolved)
        if pending:
            self.stack[-1] = (handle, dest, slot, resolved)
            self.stack.extend(pending)
            return True
        self._build(handle, dest, slot, resolved)
        return True

    def _build(self, handle: int, dest: list, slot: int, resolved: list) -> None:
        """Assemble and memoise the node's tree; pop its frame."""
        t = self.kernel.tables
        rid = t.codes.arm_rule[t.codes.code_arm[handle >> (2 * ORIGIN_BITS)]]
        tree = ParseTree(t.decode.rule_refs[rid], IrSeq(*resolved))
        self.memo[handle] = tree
        dest[slot] = tree
        self.stack.pop()

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
        return [
            c if isinstance(c, (int, PayloadLeaf)) else t.char_leaf(c)
            for _, _, c in chain
        ]

    def _pending(self, resolved: list) -> list:
        """Swap memoised kids in place; return frames for those still unbuilt."""
        memo = self.memo
        tables = self.kernel.tables
        codes = tables.codes
        out: list[tuple[int, list, int, None]] = []
        for idx, child in enumerate(resolved):
            if isinstance(child, int):  # a packed handle, not yet built
                cached = memo.get(child)
                if cached is not None:
                    resolved[idx] = cached
                    continue
                if (child >> ORIGIN_BITS) & ORIGIN_MASK == child & ORIGIN_MASK:
                    tree = tables.empty_tree(
                        codes.arm_rule[codes.code_arm[child >> (2 * ORIGIN_BITS)]]
                    )
                    if tree is not None:  # zero-width — the shared derivation
                        resolved[idx] = tree
                        continue
                out.append((child, resolved, idx, None))
        return out
