"""The resumable recognizer — mark / extend / rollback on one growing chart.

:class:`ResumableKernel` is the :class:`~lexic.parsing.earley.kernel.Kernel`
specialisation that parses a *growing* input: :meth:`extend` appends columns
and drives them (the prefix chart is never re-built), :meth:`mark` /
:meth:`rollback` checkpoint and truncate — every per-parse index is
per-column (a list indexed by column), so rollback is pure list truncation.
Recognition-only: SPPF families are parse-global, so :meth:`extend` refuses
under ``record_links`` (the generation mask never reads a forest).

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
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel import Kernel


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
            is parse-global — rollback could not truncate it), or when the
            grown input exceeds the packed column capacity.
        """
        if self.record_links:
            raise UnsupportedConstructError(
                "parsing: extend() is recognition-only — record_links holds "
                "parse-global state a rollback cannot truncate"
            )
        if not chars:
            return
        n = len(self.text)
        end = n + len(chars)
        if end >= self.tables.packing.advance:
            raise UnsupportedConstructError(
                f"parsing: extending to {end} chars exceeds the packed "
                f"column capacity ({self.tables.packing.advance - 1})"
            )
        self.text = self.text + chars
        st = self.st
        for _ in chars:
            self.cols.append([])
            st.seen.append(set())
            st.waiting.append({})
            st.scannable.append({})
            st.predicted.append(set())
            st.leo.append({})
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
        keep = mark + 1
        st = self.st
        del self.cols[keep:]
        del st.seen[keep:]
        del st.waiting[keep:]
        del st.scannable[keep:]
        del st.predicted[keep:]
        del st.leo[keep:]
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
