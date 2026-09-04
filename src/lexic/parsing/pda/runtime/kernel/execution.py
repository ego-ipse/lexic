"""Leaf execution, island delegation, and completion for the PDA kernel."""

# The terminal loop this file shares with kernel.py is duplicated ON PURPOSE:
# both engines run it per character, and folding it into one callee would put
# a Python call on the paid path to save seven lines. `duplicate-code` cannot
# be answered at the site — it is reported for a pair of modules at the end of
# a run — so the withdrawal is stated here, for that pair and nothing else.
# pylint: disable=duplicate-code

from __future__ import annotations

from functools import partial
from typing import Any, cast

from lexic.parsing.earley.kernel.loop.kernel import Delegate
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    gate_take,
    no_fast_construction,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    OP_CC1,
    OP_LEAF1,
    OP_LIT,
    OP_LIT1,
    OP_V1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
)
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.admission import KernelCaches
from lexic.parsing.pda.runtime.build import (
    Frame,
    build_sequence,
    build_vstr,
    fast_values,
    finish_delegate,
    leaf_mismatch,
)
from lexic.parsing.pda.runtime.islands import IslandPolicy, island_parse, island_value
from lexic.parsing.pda.runtime.matchers import (
    loop_spec,
    match_cc,
    match_cc1,
    match_chartable,
    match_lit,
    run_span_once,
    select_arm,
    vdisp_once,
    vstr_once,
)
from lexic.parsing.product import Completed


class KernelExecutionMixin[Carry]:
    """Execution method group over state owned by ``PdaKernel``."""

    __slots__ = ()

    text: str
    pos: int
    stack: list[Frame[Carry]]
    tables: PdaTables
    policy: IslandPolicy
    _caches: KernelCaches[Carry]

    def _leaf_run(self, clone: FlatClone[Carry], out: list[Carry]) -> None:
        """A frame-less leaf clone's whole run — one of three shapes.

        A ``value_str`` leaf matches inline exactly as an ``OP_VSTR``
        reference to it would; an entry had been paying a frame for the
        identical match, which by the leaf licence cannot descend. A REDUCE
        leaf is the twin of that: its reduction reads only its own span, so
        the value its completion would have built is computed here instead.
        Anything else builds through :meth:`_run_leaf`.
        """
        if clone.mode == BUILD_VALUE_STR:
            self.pos = vstr_once(self.text, self._caches.intern, clone, out, self.pos)
        else:
            self.pos = self._run_leaf(clone, out, self.pos)

    def _run_leaf(self, clone: FlatClone[Carry], out: list[Carry], pos: int) -> int:
        """Run an all-terminal ``sequence`` clone frame-lessly — match and build.

        The leaf licence guarantees no descent: every item is a terminal or an
        ``OP_VSTR``, so item spans and sub-models are collected in locals and
        the model is built on the spot, exactly as the frame walk plus
        :meth:`_complete` would.

        :param clone: The leaf clone (``leaf`` flag set at flatten time).
        :param out: The sink the built model appends to.
        :param pos: The cursor position.
        :returns: The position after the clone's whole match.
        :raises PdaFail: On a terminal mismatch, or no viable arm.
        :raises UnsupportedConstructError: On an item count that matches
            neither the bound fields nor the empty arm.
        """
        text = self.text
        arm = select_arm(clone, text[pos : pos + 1], pos)
        if arm.n != clone.n_items:
            return leaf_mismatch(clone, out, arm.n, pos, self._caches.intern)
        start = pos
        ends = [start] * (arm.n + 1) if clone.needs_ends else None
        sinks: list[Any] | None = None
        for i in range(arm.n):
            k = arm.kinds[i]
            if k == OP_CC1:
                pos = match_cc1(text, arm.payloads[i], pos)
            elif k == OP_LIT1:
                lit = arm.payloads[i]
                if not text.startswith(lit, pos):
                    raise PdaFail(f"expected {lit!r} at {pos}", pos)
                pos += len(lit)
            elif k == OP_VSTR or k >= OP_VRUN:
                if sinks is None:
                    sinks = [None] * arm.n
                sinks[i] = sub = []
                # A tabled reference is exactly one iteration by its op-code, so
                # it calls the matcher straight instead of the loop driver.
                pos = (
                    run_span_once(text, arm.payloads[i], sub, pos)
                    if k == OP_VRUN
                    else vstr_once(text, self._caches.intern, arm.payloads[i], sub, pos)
                    if k == OP_V1
                    else self._match_vdisp(sub, arm, i, pos)
                    if k == OP_VDISP
                    # a leaf inside a leaf: recur rather than descend, so a
                    # chain of pass-throughs costs no frame at any depth
                    else self._run_leaf(arm.payloads[i], sub, pos)
                    if k == OP_LEAF1
                    else self._match_vstr(sub, arm, i, pos)
                )
            else:
                pos = (
                    match_lit(text, arm, i, pos)
                    if k == OP_LIT
                    else match_cc(text, arm, i, pos)
                )
            if ends is not None:
                ends[i + 1] = pos
        out.append(clone.fast(fast_values(self.text, clone, (ends or (), sinks))))
        return pos

    def _match_vstr(self, sink: list[Carry], arm: FlatArm, i: int, pos: int) -> int:
        """Inline a terminal-only ``value_str`` reference — no frame per iteration.

        Runs item ``i``'s whole quantifier loop: each iteration selects the
        target clone's arm at the lookahead, matches its (all-terminal) items,
        slices the consumed span and appends the built model to ``sink`` —
        exactly the frame push, walk and completion it replaces.

        :param sink: The sink the iteration models append to.
        :param arm: The current arm.
        :param i: The ``OP_VSTR`` item index.
        :param pos: The cursor position.
        :returns: The position after the whole quantifier loop.
        A target whose one-char language was tabled at compile time
        (:func:`~lexic.parsing.pda.compiler.program.flatten.chartable_for`) runs the loop
        in :func:`~lexic.parsing.pda.runtime.matchers.match_chartable` instead —
        a lookup per iteration rather than a selection and a build.

        :raises PdaFail: On a terminal mismatch or an unmatched mandatory
            iteration with no default arm.
        """
        text = self.text
        intern = self._caches.intern
        clone = arm.payloads[i]
        if clone.chartable is not None:
            return match_chartable(text, arm, i, sink, pos)
        lo, hi = arm.los[i], arm.his[i]
        gk, gate = arm.gate_kinds[i], arm.gate_data[i]
        count = 0
        while count < lo or ((hi < 0 or count < hi) and gate_take(text, pos, gk, gate)):
            pos = vstr_once(text, intern, clone, sink, pos)
            count += 1
        return pos

    def _match_vdisp(self, sink: list[Carry], arm: FlatArm, i: int, pos: int) -> int:
        """Inline a reference to an all-``value_str`` dispatch — no frame, no table.

        The lead char picks the target clone afresh each iteration (the cursor
        has moved), then that clone's ordinary ``vstr_once`` runs — the
        ``_enter`` and ``_settle`` steps the entry path made per occurrence,
        without the calls.

        :raises PdaFail: On a dispatch miss or a terminal mismatch.
        """
        text = self.text
        intern = self._caches.intern
        lo, hi, gk, gate = loop_spec(arm, i)
        count = 0
        while count < lo or ((hi < 0 or count < hi) and gate_take(text, pos, gk, gate)):
            pos = vdisp_once(text, intern, arm.payloads[i], sink, pos)
            count += 1
        return pos

    # ── island sub-parse + splice ─────────────────────────────────────

    def _island(self, name: str, sink: list[Carry]) -> None:
        """Resolve an island reference: a windowed Earley sub-parse, spliced.

        The island rule parses over a doubling window from the cursor — with its
        conflict-free interior rules delegated to their PDA clones
        (:meth:`_delegates`) — and the longest completion completes through the
        policy's product executor, its value appending to ``sink``. The cursor
        advances past the consumed island span.

        Presence is the product's answer, not a truth test on the value. A
        recognition-only island — a noise rule reached through an island
        reference — completes to nothing and splices nothing, while an island
        whose value IS ``None`` splices that ``None``. The fold could not tell
        those apart; the completion result can, which is why the splice reads
        it rather than the value.

        :param name: The island rule name.
        :param sink: The enclosing sink the value splices into.
        :raises PdaFail: With no product to splice (island-free path), when the
            island rule completes over no window from the cursor, or when the
            product refuses the completion (a window-truncated mis-parse — see
            :func:`~lexic.parsing.pda.runtime.islands.island_value`).
        """
        executor = self.policy.executor
        if executor is None:
            raise PdaFail(
                f"island {name!r} at {self.pos}: no product for splice", self.pos
            )
        tree, end = self._island_subparse(name)
        result = island_value(lambda: executor.splice(tree), name, self.pos)
        if isinstance(result, Completed):
            sink.append(result.value)
        self.pos += end

    def _island_subparse(self, name: str) -> tuple[Any, int]:
        """Windowed Earley sub-parse of island ``name`` from the cursor, delegated.

        The island tables over the cursor's window, with this cursor's interior
        delegate table threaded in.

        :param name: The island rule name.
        :returns: ``(tree, consumed length)``.
        """
        return island_parse(
            self.tables.island_tables(name, tier_for(len(self.text))),
            self.text,
            self.pos,
            name,
            self.policy.for_island(
                self._delegates(name), self.tables.island_follow.get(name)
            ),
        )

    def _delegates(self, name: str) -> dict[int, Delegate]:
        """The island ``name``'s interior delegate table, wrapped and cached.

        Wraps each of the island's delegable clones
        (:meth:`~lexic.parsing.pda.compiler.clones.PdaTables.island_delegates`) as a
        fail-soft callable bound to this cursor's :meth:`_delegate_run`. Cached
        per island name on this cursor.

        :param name: The island rule name.
        :returns: rule_id → its delegate callable (empty when nothing delegates).
        """
        cached = self._caches.deleg.get(name)
        if cached is None:
            cached = {
                rid: partial(self._delegate_run, clone)
                for rid, clone in self.tables.island_delegates(name).items()
            }
            self._caches.deleg[name] = cached
        return cached

    def _delegate_run(
        self, clone: FlatClone, window_text: str, pos: int
    ) -> tuple[int, object] | None:
        """Run a delegable clone as a self-contained sub-parse over the window.

        The model-path :data:`~lexic.parsing.earley.kernel.loop.kernel.Delegate` body: a
        fresh :class:`PdaKernel` over ``window_text`` drives ``clone`` to
        completion from ``pos`` (:meth:`prefix_run`) and builds its sub-model.
        On any :class:`PdaFail`, or when the sub-run reaches the window edge (a
        possibly-truncated span — fall through so the island doubling window
        grows instead of filing a short span), returns ``None`` and the island
        predictor falls back to normal Earley prediction.

        :param clone: The delegable rule's flat clone.
        :param window_text: The island window (the sub-parse's whole input).
        :param pos: The start position within ``window_text``.
        :returns: ``(end, sub_model)``, or ``None`` (declined — the safety net).
        """
        sub = cast(Any, type(self))(
            self.tables,
            window_text,
            self.policy.executor,
            resolve=self.policy.resolve,
        )
        return finish_delegate(sub, clone, window_text, pos)

    # ── frame completion → fused model build ──────────────────────────

    def _complete(self, frame: Frame[Carry]) -> None:
        """Pop a finished frame; build and report its model — the fused fold.

        A ``value_str`` frame slices its whole span, an ``alternation`` passes
        the first sub-model through, and a ``sequence`` binds each field to its
        item span or sub-model collection; a transparent frame builds nothing
        (its children already funnelled to ``out``).
        """
        self.stack.pop()
        mode = frame.clone.mode
        if mode == BUILD_TRANSPARENT:
            return  # children already funnelled to the nearest model sink
        clone = frame.clone
        if mode == BUILD_SEQ:
            if clone.fast is not no_fast_construction and frame.arm.n == clone.n_items:
                model = clone.fast(
                    fast_values(
                        self.text,
                        clone,
                        (frame.ends or (), frame.sinks),
                    )
                )
            else:
                model = build_sequence(self.text, frame, clone, self._caches.intern)
        elif mode == BUILD_VALUE_STR:
            model = build_vstr(
                clone, self.text[frame.span_start() : self.pos], self._caches.intern
            )
        else:  # BUILD_ALT
            model = frame.alt_model()
        if model is not None:
            frame.out.append(model)
