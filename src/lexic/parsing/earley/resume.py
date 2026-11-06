"""The resumable recognizer — mark / extend / rollback on one growing chart.

:class:`ResumableKernel` is the :class:`~lexic.parsing.earley.kernel.loop.kernel.Kernel`
specialisation that parses a *growing* input: :meth:`extend` appends columns
and drives them (the prefix chart is never re-built), :meth:`mark` /
:meth:`rollback` checkpoint and truncate — every per-parse index is
per-column (a list indexed by column), so rollback is pure list truncation.
Recognition-only: SPPF families are parse-global, so :meth:`extend` refuses
under ``record_links`` (the generation mask never reads a forest). It also
refuses **run-collapsed** tables: a run terminal consumes the MAXIMAL run,
whose extent depends on input not yet appended, so a committed run could
never grow — maximal munch and incremental extension are incompatible by
construction. The resumable path builds plain tables, so this is a tripwire
against a future wiring rather than a live case.

**The junction re-seed.** A closed final column was seeded FIRST-gated on
the empty char slice — only always-seed arms filed (the EOF rule). When the
input grows past it, that column becomes interior: :meth:`extend` re-opens
it by filing every predicted rule's *dropped* arms (``gate is not None`` —
disjoint from the gated pass, so the seed no-dedup invariant survives) and
re-closing from the saved fixpoint index. New rules predicted during the
re-close seed **ungated** (all arms) via the :meth:`_seed` junction branch,
so a re-opened column is char-independent — a later rollback + re-extend
with a different character finds every arm already filed and re-files
nothing. Ungated extra seeds are harmless: the scanner tests the actual
character, so wrong-char seeds never advance (the E6-1 geometry).

:class:`WindowKernel` is the other growing chart: an island's window over a
document, widened without rollback, so it keeps its SPPF families and its
island-interior delegates. Its argument is on the class.
"""

from __future__ import annotations

from functools import partial
from typing import Self

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.loop.kernel import Delegate, Kernel
from lexic.parsing.earley.kernel.tables.records import ParserTables


def refuse_runs(tables: ParserTables) -> None:
    """Refuse to grow a chart over run-collapsed tables.

    A run terminal takes the MAXIMAL run, which depends on input not yet in
    the chart, so a committed run could never be extended.

    :raises UnsupportedConstructError: When the tables hold a run terminal.
    """
    if any(length == 0 for length in tables.terms.lens):  # a RunTerm
        raise UnsupportedConstructError(
            "parsing: a chart cannot grow over run-collapsed tables — a run "
            "terminal takes the MAXIMAL run, which depends on input not yet "
            "in the chart, so a committed run can never be extended"
        )


class ResumableKernel(Kernel):
    """A kernel whose chart grows with the input and truncates on rollback.

    Construct over the committed prefix (usually ``""``), :meth:`run` once,
    then interleave :meth:`mark` / :meth:`extend` / :meth:`rollback` freely;
    :attr:`accept` and the per-column indexes stay live views of the current
    chart throughout.

    :ivar _topped: column → rule ids whose arms are ALL filed there (the
        junction re-seed memo — survives rollback for columns ≤ the mark,
        exactly matching the surviving seeds).
    :ivar _junction: the column currently being re-opened (``-1`` outside
        :meth:`_reopen`) — routes fresh predictions to the ungated seed.
    """

    __slots__ = ("_topped", "_junction")

    _topped: dict[int, set[int]]
    _junction: int

    def __init__(self, *args, **kwargs) -> None:
        """Prepare a resumable parse (same signature as :class:`Kernel`)."""
        super().__init__(*args, **kwargs)
        self._topped = {}
        self._junction = -1

    def mark(self) -> int:
        """Checkpoint the current input length (the rollback token)."""
        return len(self.text)

    def extend(self, chars: str) -> None:
        """Append ``chars`` to the input and drive the new columns.

        Re-opens the old final column (junction re-seed + close-from-index),
        scans across the appended text and closes the new final column —
        the chart afterwards equals a fresh parse of the whole text, up to
        harmless extra (never-advancing) junction seeds.

        :param chars: The appended input (empty is a no-op).
        :raises UnsupportedConstructError: Under ``record_links`` (the SPPF
            is parse-global — rollback could not truncate it), over
            run-collapsed tables (maximal munch cannot be incremental — see
            below), or when the grown input exceeds the packed column capacity.
        """
        if self.record_links:
            raise UnsupportedConstructError(
                "parsing: extend() is recognition-only — record_links holds "
                "parse-global state a rollback cannot truncate"
            )
        refuse_runs(self.tables)
        if not chars:
            return
        n = len(self.text)
        end = n + len(chars)
        self.open_columns(end)
        self.text = self.text + chars
        self._reopen(n)
        self._scan(n)
        for i in range(n + 1, end):
            self._close(i)
            self._scan(i)
        self._close(end)

    def rollback(self, mark: int) -> None:
        """Truncate the chart and input back to a :meth:`mark` checkpoint.

        Columns past the mark drop wholesale (every index is per-column);
        the mark column itself keeps its junction seeds — they are exactly
        what the next :meth:`extend` would re-file, so :attr:`_topped` keeps
        their memo while entries for truncated columns purge.

        :param mark: A value previously returned by :meth:`mark`.
        """
        self.cut_columns(mark + 1)
        self.text = self.text[:mark]
        for col in [c for c in self._topped if c > mark]:
            del self._topped[col]

    # ── the junction ──────────────────────────────────────────────────

    def _seed(self, i: int, rid: int) -> None:
        """Seed as usual — but ungated (all arms) at the junction column.

        A rule first predicted while a junction re-closes must file every
        arm, not just the current character's: the column's seed set has to
        be char-independent so a rollback + re-extend with a different
        character finds it complete (see the module invariant).
        """
        if i == self._junction:
            self._file_seeds(i, rid, gated_only=False)
            self._topped[i].add(rid)
            return
        super()._seed(i, rid)

    def _reopen(self, n: int) -> None:
        """Re-open closed column ``n``: top up dropped arms, re-close.

        Every rule already predicted here was seeded gated (the empty-slice
        final close files only always-seed arms), so its ``gate is not
        None`` arms file now — disjoint from the gated pass. The re-close
        processes only the appended items (``start`` = the saved fixpoint
        length); fresh predictions inside it route through the junction
        branch of :meth:`_seed`.
        """
        topped = self._topped.setdefault(n, set())
        processed = len(self.cols[n])
        for rid in [r for r in self.st.predicted[n] if r not in topped]:
            self._file_seeds(n, rid, gated_only=True)
            topped.add(rid)
        self._junction = n
        self._close(n, processed)
        self._junction = -1

    def _file_seeds(self, i: int, rid: int, gated_only: bool) -> None:
        """File rule ``rid``'s dot-0 items into column ``i``, ignoring gates.

        :param i: The junction column.
        :param rid: The rule to seed.
        :param gated_only: File only ``gate is not None`` arms (the ones a
            previous empty-slice close dropped) — ``False`` files every arm
            (a fresh junction prediction).
        """
        items_i = self.cols[i]
        waiting_i = self.st.waiting[i]
        scannable_i = self.st.scannable[i]
        for shifted, s, gate in self.tables.codes.rule_seed_gates[rid]:
            if gated_only and gate is None:
                continue  # filed by the gated pass — never re-file
            new = shifted | i
            items_i.append(new)
            if s > 0:
                waiting_i.setdefault(s - 1, []).append(new)
            elif s < 0:
                scannable_i.setdefault(-s - 1, []).append(new)


class WindowKernel(Kernel):
    """An island's window over a document, grown on one chart rather than
    re-parsed at every width.

    The chart a window leaves behind is exactly the one a parse of the wider
    window would have built over the same columns, so growing it is a plain
    continuation: no rollback, so the SPPF families can stay (nothing ever
    truncates them), and nothing to re-open. Three things make that hold.

    - **The edge column is closed as an interior one.** Its seeds are gated
      on the document's next character, not the empty slice of an input end,
      so the column the next width scans from is already the one it needs.
    - **A scan near the edge reads past it.** The text carries the longest
      literal's reach beyond the stop, so no literal is cut short there.
    - **A delegate reads the document.** Its sub-run decides its own extent,
      whatever the width, and its completion is filed wherever it lands.

    What lands past the stop is held aside while the window stands, so between
    widths the kernel reads exactly like a parse of the window's text: its
    text ends at the stop, and every column past it is out of sight. Island
    tables are never run-collapsed (`PdaTables` compiles them plain), and the
    one refusal that would mean otherwise stays: a run terminal's maximal run
    depends on input past any stop.

    :ivar document: The whole input the window opens on.
    :ivar origin: Where the window opens in it — column 0.
    :ivar stop: The window's width: its last closed column.
    :ivar live: Whether the chart reaches past the stop: something landed
        beyond it, or an item at it accepts the next character.
    """

    __slots__ = ("document", "origin", "stop", "live", "_ahead", "_aside")

    document: str
    origin: int
    stop: int
    live: bool
    _ahead: int
    _aside: tuple[list[list[int]], list[list]]

    def __init__(
        self,
        tables: ParserTables,
        document: str,
        origin: int,
        stop: int,
        delegates: dict[int, Delegate] | None = None,
    ) -> None:
        """Open a window of ``stop`` characters on ``document`` at ``origin``.

        :param tables: The island rule's compiled tables.
        :param document: The whole input.
        :param origin: Where the window opens.
        :param stop: The window's first width.
        :param delegates: rule_id → island-interior delegate, each re-anchored
            to read the document rather than the window.
        :raises UnsupportedConstructError: Over run-collapsed tables.
        """
        refuse_runs(tables)
        self.document = document
        self.origin = origin
        self.stop = stop
        self.live = False
        self._ahead = max(max(tables.terms.lens, default=1), 1)
        self._aside = ([], [])
        anchored: dict[int, Delegate] = {
            rid: partial(_anchored, delegate, document, origin)
            for rid, delegate in (delegates or {}).items()
        }
        super().__init__(tables, self._span(stop), delegates=anchored)

    def run(self) -> Self:
        """Build the chart up to the stop and close the stop column."""
        if self.tables.start_id >= 0:
            self.st.predicted[0].add(self.tables.start_id)
            self._seed(0, self.tables.start_id)
        self._drive(0, self.stop)
        return self

    def grow(self, stop: int) -> None:
        """Widen the window to ``stop`` characters on the same chart.

        :param stop: The new width, past the current one.
        """
        old = self.stop
        self.stop = stop
        self.text = self._span(stop)
        self._restore()
        if self.cols[old]:
            self._scan(old)
        self._drive(old + 1, stop)

    def _drive(self, start: int, stop: int) -> None:
        """Close and scan columns ``start`` .. ``stop - 1``, close ``stop``,
        then set the rest aside."""
        cols = self.cols
        for i in range(start, stop):
            if cols[i]:
                self._close(i)
                self._scan(i)
        self._close(stop)
        self._set_aside(stop)

    def _span(self, stop: int) -> str:
        """The window's text: ``stop`` characters and the reach past them."""
        return self.document[self.origin : self.origin + stop + self._ahead]

    def _set_aside(self, stop: int) -> None:
        """Hold every column past the stop out of sight, and record whether the
        chart reaches past it."""
        beyond = stop + 1
        self.live = any(self.cols[beyond:]) or self._accepts_next(stop)
        self._aside = self.cut_columns(beyond)
        self.text = self.text[:stop]

    def _restore(self) -> None:
        """Put the held columns back, and open the rest the text now covers."""
        self.restore_columns(self._aside)
        self._aside = ([], [])
        self._cover(len(self.text))

    def _cover(self, end: int) -> None:
        """Columns up to ``end``, and the text to read them."""
        self.open_columns(end)
        if len(self.text) < end:
            self.text = self.document[self.origin : self.origin + end + self._ahead]

    def _accepts_next(self, stop: int) -> bool:
        """Whether an item at the stop faces a terminal the next character
        starts."""
        char = self.text[stop : stop + 1]
        if not char:
            return False
        scannable = self.st.scannable[stop]
        return any(scannable.get(tid) for tid in self.tables.terms.terms_for(char))

    def _inject_delegate(self, i: int, rid: int, end: int, payload: object) -> None:
        """File a delegated completion wherever it lands — past the stop too."""
        self._cover(end)
        super()._inject_delegate(i, rid, end, payload)


def _anchored(
    delegate: Delegate, document: str, origin: int, _window: str, i: int
) -> tuple[int, object] | None:
    """A delegate re-anchored on the document: asked at a window column, it
    runs at the matching document position and answers in window columns.

    :param delegate: The island-interior delegate.
    :param document: The whole input.
    :param origin: Where the window opens in it.
    :param _window: The window's text, which the sub-run does not read.
    :param i: The window column it is asked at.
    """
    got = delegate(document, origin + i)
    return None if got is None else (got[0] - origin, got[1])
