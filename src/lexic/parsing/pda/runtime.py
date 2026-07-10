"""Fused predictive runtime — parses text to a model, no ParseTree on the path.

The runtime sibling of :class:`~lexic.parsing.earley.kernel.Kernel`: where the Earley
kernel builds an SPPF a :class:`~lexic.parsing.fold.ModelFold` later folds,
:class:`PdaKernel` walks the flat int-coded
:class:`~lexic.parsing.pda.clones.PdaProgram` and builds the model **directly
during the walk** — the fold is fused into the parse, so no intermediate
:class:`~lexic.parsing.earley.forest.ParseTree` is ever allocated on the deterministic
path.

**Flat program (Task 8).** The runtime walks the int-coded
:class:`~lexic.parsing.pda.clones.PdaProgram` (``_OP_*`` op-codes, pre-resolved
``(chars, negated)`` membership sets, direct :class:`_FlatClone` references),
not the compiler's :class:`~lexic.parsing.pda.clones.CloneSpec` NamedTuples —
integer dispatch, no attribute descriptors, no per-char method calls on the hot
loop (the ``tables.py``/``kernel.py`` philosophy).

**Explicit frame stack.** Rule, group and loop descent runs on an explicit
:attr:`PdaKernel.stack` of flat *list frames* (the ``kernel.py`` int-array
explicit-stack precedent; the class cursor is :class:`PdaKernel` itself — see the
frame layout below) — never Python recursion. Per-parse state (the input, the
cursor position, the frame stack) lives on the kernel;
:class:`~lexic.parsing.pda.clones.PdaProgram` is shared and immutable. A frame
executes one arm's items in order; a literal / char-class item runs its whole
quantifier loop inline in :meth:`PdaKernel._match_lit` /
:meth:`PdaKernel._match_cc` (no descent, no per-char call), while a rule
reference or inline group pushes a sub-frame per iteration and resumes when it
completes.

**Fused capture.** A *clone frame* with a build-mode (``sequence`` /
``alternation`` / ``value_str``) captures what its fold needs and, on
completion, builds exactly one model (:meth:`PdaKernel._complete`); a
*transparent frame* (an inline group, or a look-through no-constructor clone)
funnels every model produced inside it straight to its ``_F_OUT`` sink. Each
frame records item end positions in its ``_F_ENDS`` slot (item spans derive from
the contiguous, monotonic cursor — item ``i``'s span is
``(start if i==0 else ends[i-1], ends[i])``); only a span-reading ``sequence``
clone reads them back, but every frame keeps the slot so the driver's per-item
write stays branch-free. Descent sub-models are collected per bound item in a
lazily-allocated ``_F_SINKS`` list. So a sub-model produced arbitrarily deep,
through any number of group and loop layers, lands in the nearest enclosing
*bound* item's sink, exactly as the fold's look-through ``_models_at`` collects
the topmost models under a kid.

Per build-mode (mirroring :meth:`~lexic.parsing.fold.ModelFold._fold_node`):

- ``value_str`` → ``ctor(value=text[a:b])`` over the clone's whole span (its
  interior is pure-terminal — no sub-models are built below it);
- ``alternation`` → pass-through of the first model under the matched arm;
- ``sequence`` → per bound field, the item's ``text`` / ``gtext`` span or its
  ``model`` / ``models`` collection; a zero-item arm match → ``ctor()``.

**Islands.** A reference to a conflicted (island) rule cannot be walked
deterministically, so it delegates to a windowed Earley sub-parse: a fresh
:class:`~lexic.parsing.earley.kernel.Kernel` over the rule's
:meth:`~lexic.parsing.pda.clones.PdaTables.island_tables` runs
:meth:`~lexic.parsing.earley.kernel.Kernel.longest_start_completion` over a doubling
window and takes the longest completion; the decoded
:class:`~lexic.parsing.earley.forest.ParseTree` (via
:class:`~lexic.parsing.earley.kernel.FastTree`, falling back to the first derivation
on ambiguity) folds through the supplied :class:`~lexic.parsing.fold
.ModelFold` and the resulting sub-model splices into the current capture
exactly as a clone's model would. The cursor advances past the consumed span.
Without a fold (:attr:`PdaKernel.fold` is ``None``, the island-free path) an
island reference raises :class:`PdaFail` so the engine reparses. A
**fail-island** reference (a semantic F1 stop-set-escape rule whose longest-match
split would silently diverge) always raises :class:`PdaFail`, independent of the
fold, so the compile seam falls back to the sound engine parse.

:class:`PdaFail` is internal to :mod:`lexic.parsing` — a PDA parse failure is
caught by the compile seam and retried on the full engine, which owns the
user-facing diagnostics. It never surfaces to the caller.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrSelf
from lexic.parsing.fold import ModelFold, RuleFold
from lexic.parsing.pda.clones import PdaTables
from lexic.parsing.pda.errors import PdaFail
from lexic.parsing.pda.flatten import (
    _BUILD_DISPATCH,
    _BUILD_SEQ,
    _BUILD_TRANSPARENT,
    _BUILD_VALUE_STR,
    _DISPATCH_EMPTY,
    _GATE_PAIR,
    _M_GTEXT,
    _M_MODEL,
    _M_MODELS,
    _OP_CC,
    _OP_CC1,
    _OP_FAIL,
    _OP_GRP,
    _OP_LIT,
    _OP_LIT1,
    _OP_REF1,
    _OP_VSTR,
    _FlatArm,
    _FlatClone,
)
from lexic.parsing.pda.islands import island_parse

__all__ = ["PdaFail", "PdaKernel", "parse_pda"]

_EMPTY_SLOT: Any = None
"""An ``Any``-typed ``None`` — fills fresh per-item sink lists (``list[Any]``,
each slot later holding a sub-model list) without narrowing their type."""


# ── frame layout ───────────────────────────────────────────────────────────
#
# A frame is one in-progress arm execution on the kernel's explicit descent
# stack — a flat list (the ``kernel.py`` int-array explicit-stack precedent; the
# class *cursor* is :class:`PdaKernel` itself), indexed by the constants below.
# A *clone frame* (a non-transparent ``_F_MODE``) captures what its fold needs
# and, on completion, builds a single model; a *transparent frame*
# (``_BUILD_TRANSPARENT`` — an inline group or look-through clone) owns no
# capture and funnels every model produced inside it straight to ``_F_OUT``.
#
#   _F_ARM   the selected arm's flat item arrays (:class:`_FlatArm`)
#   _F_I     the current item index
#   _F_COUNT iterations completed for the current item (resumes a descending
#            loop across sub-frame pushes)
#   _F_OUT   the parent sink list — where a clone frame's model appends, or a
#            transparent frame's children funnel
#   _F_MODE  the build-mode (one of the ``_BUILD_*`` constants)
#   _F_CLONE the frame's :class:`_FlatClone` (its fold and baked build plan)
#   _F_START the cursor position where the frame began (its span start)
#   _F_ENDS  per-item end positions (``ends[i]`` written as each item finishes);
#            item ``i``'s span is ``(start if i==0 else ends[i-1], ends[i])``.
#            Allocated for every frame so the driver's write stays branch-free;
#            only span-reading ``sequence`` clones read it back
#   _F_SINKS per-item descent sub-model lists, allocated lazily on first descent
#            (capture frames), else ``None``
_F_ARM, _F_I, _F_COUNT, _F_OUT, _F_MODE, _F_CLONE, _F_START, _F_ENDS, _F_SINKS = range(
    9
)


class PdaKernel(IrLeaf[IrSelf, IrSelf]):
    """One predictive parse of ``text`` over a compiled :class:`PdaProgram`.

    Construct per parse, call :meth:`run` once; it returns the start clone's
    model. Per-parse state (:attr:`pos`, :attr:`stack`) is mutable on the
    kernel; :attr:`tables` is the shared, immutable compiled artifact.

    :ivar tables: The compiled predictive-parser tables (its
        :attr:`~lexic.parsing.pda.clones.PdaTables.program` is walked).
    :ivar text: The input string.
    :ivar pos: The cursor position (advances monotonically — no backtracking).
    :ivar stack: The explicit descent stack of flat frame lists (see the frame
        layout above).
    :ivar fold: The full-grammar fold used to splice island sub-models, or
        ``None`` on the island-free path (an island reference then raises
        :class:`PdaFail`).
    """

    __slots__ = ("tables", "text", "pos", "stack", "fold")

    tables: PdaTables
    text: str
    pos: int
    stack: list[list[Any]]
    fold: ModelFold | None

    def __init__(
        self, tables: PdaTables, text: str, fold: ModelFold | None = None
    ) -> None:
        """Prepare a parse of ``text`` over ``tables``.

        :param tables: The compiled predictive-parser tables.
        :param text: The input to parse.
        :param fold: The full-grammar :class:`~lexic.parsing.fold.ModelFold`
            for splicing island sub-models; ``None`` disables island resolution
            (any island reference raises :class:`PdaFail`).
        """
        self.tables = tables
        self.text = text
        self.pos = 0
        self.stack = []
        self.fold = fold

    # ── the driver ────────────────────────────────────────────────────

    def run(self) -> object:
        """Parse the whole input and return the start clone's model.

        :returns: The model instance the start rule folds to.
        :raises PdaFail: On any deterministic-parse failure — a terminal
            mismatch, no viable arm, an unresolved island reference, trailing
            input, or a start rule that is itself an island (the whole-grammar
            opt-out the compile seam reads).
        """
        start = self.tables.program.start
        if not isinstance(start, _FlatClone):  # IslandRef opt-out
            raise PdaFail(f"start rule {start.name!r} is an island — no PDA")
        holder: list[object] = []
        self._enter(start, holder)
        self._drive()
        if self.pos != len(self.text):
            raise PdaFail(f"trailing input at {self.pos}")
        if not holder:
            raise PdaFail("start rule produced no model")
        return holder[0]

    def _drive(self) -> None:
        """Drain the frame stack — the fused hot loop.

        The outer loop processes the top frame; the inner loop runs its items
        in order. A terminal item matches its whole quantifier loop inline (no
        descent, no per-char call; the exactly-once ``_OP_CC1``/``_OP_LIT1``
        specialisations skip even the helper call); an ``_OP_VSTR`` item runs
        its whole terminal-only ``value_str`` loop frame-lessly; an
        ``_OP_REF1`` item (an exactly-once entry in an ends-free arm) advances
        past itself before descending, so its resume needs no re-check. Any
        other quantified atom steps through :meth:`_quant_step` — descend,
        inline splice, or loop close. A frame whose items run out (the
        ``while``'s ``else``) completes.
        """
        stack = self.stack
        text = self.text
        while stack:
            frame = stack[-1]
            arm = frame[_F_ARM]
            kinds = arm.kinds
            n = arm.n
            ends = frame[_F_ENDS]
            i = frame[_F_I]
            pos = self.pos
            while i < n:
                k = kinds[i]
                if k == _OP_CC1:
                    payload = arm.payloads[i]
                    char = text[pos : pos + 1]
                    if (
                        (char == "" or char in payload[0])
                        if payload[1]
                        else (char not in payload[0])
                    ):
                        raise PdaFail(f"char class miss at {pos}")
                    pos += 1
                elif k == _OP_LIT1:
                    lit = arm.payloads[i]
                    if not text.startswith(lit, pos):
                        raise PdaFail(f"expected {lit!r} at {pos}")
                    pos += len(lit)
                elif k == _OP_REF1:
                    frame[_F_I] = i + 1
                    self.pos = pos
                    if self._enter(arm.payloads[i], self._sink_for(frame, arm, i)):
                        break  # pushed — the sub-frame drives next
                    pos = self.pos  # consumed inline — this item is done
                    i += 1
                    continue
                elif k == _OP_VSTR or k <= _OP_CC:  # value_str / quantified terminal
                    pos = self._match_span(frame, arm, i, pos)
                else:  # _OP_REF / _OP_GRP / _OP_ISLAND / _OP_FAIL
                    i = self._quant_step(frame, arm, i, pos)
                    if i < 0:
                        break  # pushed — the sub-frame drives next
                    pos = self.pos
                    continue
                ends[i] = pos
                i += 1
            else:  # items exhausted without a descent — the frame completes
                frame[_F_I] = i
                self.pos = pos
                self._complete(frame)

    def _quant_step(self, frame: list[Any], arm: _FlatArm, i: int, pos: int) -> int:
        """One step of a quantified atom's loop — descend, splice, or close.

        Consults the mandatory count then the loop gate; a due iteration
        descends (a clone entry pushes a frame; an island splices inline; a
        fail-island raises), a closed loop records the item's end and moves on.
        ``self.pos`` is left current in every non-pushing outcome.

        :returns: ``-1`` when a sub-frame was pushed; otherwise the item index
            the driver continues at (``i`` mid-loop, ``i + 1`` when closed).
        :raises PdaFail: On a fail-island reference, an island reference with
            no fold, or a mandatory iteration with no viable arm.
        """
        count = frame[_F_COUNT]
        if count < arm.los[i]:
            need = True
        else:
            hi = arm.his[i]
            need = (hi < 0 or count < hi) and self._gate_admits(arm, i, pos)
        if not need:
            frame[_F_COUNT] = 0
            frame[_F_I] = i + 1
            frame[_F_ENDS][i] = pos
            self.pos = pos
            return i + 1
        frame[_F_COUNT] = count + 1
        frame[_F_I] = i
        self.pos = pos
        k = arm.kinds[i]
        sink = self._sink_for(frame, arm, i)
        if k <= _OP_GRP:  # _OP_REF / _OP_GRP — a clone entry
            if self._enter(arm.payloads[i], sink):
                return -1
            return i  # consumed inline — same item continues
        if k == _OP_FAIL:
            raise PdaFail(
                f"fail-island {arm.payloads[i]!r} at {pos}: "
                "F1 semantic escape, engine fallback"
            )
        self._island(arm.payloads[i], sink)  # _OP_ISLAND — spliced inline
        return i

    # ── terminal matching (whole quantifier loop, inline, no per-char call) ─

    def _match_span(self, frame: list[Any], arm: _FlatArm, i: int, pos: int) -> int:
        """Match a span-producing item — a ``value_str`` ref or a quantified
        literal / char class — routing to its matcher (the cold-ish tail of the
        driver's op dispatch; the exactly-once terminals stay inline)."""
        k = arm.kinds[i]
        if k == _OP_VSTR:
            return self._match_vstr(self._sink_for(frame, arm, i), arm, i, pos)
        if k == _OP_LIT:
            return self._match_lit(arm, i, pos)
        return self._match_cc(arm, i, pos)

    def _match_lit(self, arm: _FlatArm, i: int, pos: int) -> int:
        """Match a literal item's whole quantifier loop, returning the new pos.

        :raises PdaFail: On a mismatch in the mandatory run or a gate-admitted
            partial literal.
        """
        text = self.text
        lit = arm.payloads[i]
        llen = len(lit)
        lo, hi = arm.los[i], arm.his[i]
        count = 0
        while count < lo:
            if not text.startswith(lit, pos):
                raise PdaFail(f"expected {lit!r} at {pos}")
            pos += llen
            count += 1
        gate = arm.gate_data[i]
        if arm.gate_kinds[i] == _GATE_PAIR:
            while (hi < 0 or count < hi) and text[pos : pos + 2] in gate:
                if not text.startswith(lit, pos):
                    raise PdaFail(f"expected {lit!r} at {pos}")
                pos += llen
                count += 1
            return pos
        chars, negated = gate
        while hi < 0 or count < hi:
            char = text[pos : pos + 1]
            admit = (char != "" and char not in chars) if negated else char in chars
            if not admit:
                break
            if not text.startswith(lit, pos):
                raise PdaFail(f"expected {lit!r} at {pos}")
            pos += llen
            count += 1
        return pos

    def _match_cc(self, arm: _FlatArm, i: int, pos: int) -> int:
        """Match a char-class item's whole quantifier loop, returning the new pos.

        The gate loop needs no atom re-check: a stop-set / LL(2) pair is a
        subset of the atom's own FIRST, so a gate-admitted char always matches.

        :raises PdaFail: On a mismatch in the mandatory run.
        """
        text = self.text
        chars, negated = arm.payloads[i]
        lo, hi = arm.los[i], arm.his[i]
        count = 0
        while count < lo:
            char = text[pos : pos + 1]
            if (char == "" or char in chars) if negated else char not in chars:
                raise PdaFail(f"char class miss at {pos}")
            pos += 1
            count += 1
        gate = arm.gate_data[i]
        if arm.gate_kinds[i] == _GATE_PAIR:
            while (hi < 0 or count < hi) and text[pos : pos + 2] in gate:
                pos += 1
                count += 1
            return pos
        gchars, gnegated = gate
        while hi < 0 or count < hi:
            char = text[pos : pos + 1]
            admit = (char != "" and char not in gchars) if gnegated else char in gchars
            if not admit:
                break
            pos += 1
            count += 1
        return pos

    def _gate_admits(self, arm: _FlatArm, i: int, pos: int) -> bool:
        """Whether item ``i``'s loop gate admits another iteration at ``pos``."""
        text = self.text
        gate = arm.gate_data[i]
        if arm.gate_kinds[i] == _GATE_PAIR:
            return text[pos : pos + 2] in gate
        chars, negated = gate
        char = text[pos : pos + 1]
        if negated:
            return char != "" and char not in chars
        return char in chars

    # ── descent ────────────────────────────────────────────────────────

    def _sink_for(self, frame: list[Any], arm: _FlatArm, i: int) -> list[Any]:
        """The sink item ``i``'s sub-models report into (allocated lazily).

        A transparent frame funnels everything to its parent sink; a capture
        frame collects per item in :attr:`_Frame.sinks`.
        """
        if frame[_F_MODE] == _BUILD_TRANSPARENT:
            return frame[_F_OUT]
        sinks = frame[_F_SINKS]
        if sinks is None:
            frame[_F_SINKS] = sinks = [_EMPTY_SLOT] * arm.n
        sink = sinks[i]
        if sink is None:
            sinks[i] = sink = []
        return sink

    def _select_arm(self, clone: _FlatClone, char: str, pos: int) -> _FlatArm:
        """The clone's FIRST-gated arm at lookahead ``char``, or its default.

        :raises PdaFail: When no arm's FIRST matches and there is no default.
        """
        for chars, negated, candidate in clone.selectors:
            if (char != "" and char not in chars) if negated else char in chars:
                return candidate
        default = clone.default
        if default is None:
            raise PdaFail(f"no arm at {pos}")
        return default

    def _enter(self, clone: _FlatClone, out: list[object]) -> bool:
        """Select ``clone``'s arm at the cursor and push its (flat) frame.

        A dispatch clone (a frame-less pass-through alternation) is chased
        first: its selectors carry target clones, so the walk lands on the
        concrete clone — reporting into the same ``out`` the alternation would
        have passed through to — before any frame is pushed. A leaf clone then
        runs frame-lessly in :meth:`_run_leaf`.

        :param clone: The clone (or inline group) to descend into.
        :param out: The parent sink list the clone's model reports into.
        :returns: ``True`` when a frame was pushed; ``False`` when the clone
            was consumed inline (a leaf run, or a dispatch clone's empty arm).
        :raises PdaFail: When no arm's FIRST matches and there is no default.
        """
        char = self.text[self.pos : self.pos + 1]
        while clone.mode == _BUILD_DISPATCH:
            nxt = None
            for chars, negated, target in clone.selectors:
                if (char != "" and char not in chars) if negated else char in chars:
                    nxt = target
                    break
            if nxt is None:
                nxt = clone.default
                if nxt is None:
                    raise PdaFail(f"no arm at {self.pos}")
                if nxt is _DISPATCH_EMPTY:
                    return False  # the empty (nullable) arm — nothing consumed
            clone = nxt
        if clone.leaf:
            self.pos = self._run_leaf(clone, out, self.pos)
            return False
        arm: _FlatArm | None = None
        for chars, negated, candidate in clone.selectors:
            if (char != "" and char not in chars) if negated else char in chars:
                arm = candidate
                break
        if arm is None:
            arm = clone.default
            if arm is None:
                raise PdaFail(f"no arm at {self.pos}")
        # frame layout: arm, i, count, out, mode, clone, start, ends, sinks
        # ``ends`` is per-frame so the driver's per-item span write stays
        # unconditional (only span-reading sequence clones ever read it back).
        self.stack.append(
            [arm, 0, 0, out, clone.mode, clone, self.pos, [0] * arm.n, None]
        )
        return True

    def _run_leaf(self, clone: _FlatClone, out: list[Any], pos: int) -> int:
        """Run an all-terminal ``sequence`` clone frame-lessly — match and build.

        The leaf licence guarantees no descent: every item is a terminal or an
        ``_OP_VSTR``, so item spans and sub-models are collected in locals and
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
        arm = self._select_arm(clone, text[pos : pos + 1], pos)
        if arm.n != clone.fold.n_items:
            return self._leaf_mismatch(clone, out, arm.n, pos)
        start = pos
        ends = [0] * arm.n
        sinks: list[Any] | None = None
        for i in range(arm.n):
            k = arm.kinds[i]
            if k == _OP_CC1:
                payload = arm.payloads[i]
                char = text[pos : pos + 1]
                if (
                    (char == "" or char in payload[0])
                    if payload[1]
                    else (char not in payload[0])
                ):
                    raise PdaFail(f"char class miss at {pos}")
                pos += 1
            elif k == _OP_LIT1:
                lit = arm.payloads[i]
                if not text.startswith(lit, pos):
                    raise PdaFail(f"expected {lit!r} at {pos}")
                pos += len(lit)
            elif k == _OP_VSTR:
                if sinks is None:
                    sinks = [_EMPTY_SLOT] * arm.n
                sinks[i] = sub = []
                pos = self._match_vstr(sub, arm, i, pos)
            elif k == _OP_LIT:
                pos = self._match_lit(arm, i, pos)
            else:
                pos = self._match_cc(arm, i, pos)
            ends[i] = pos
        out.append(self._build_fast(clone, start, ends, sinks))
        return pos

    @staticmethod
    def _leaf_mismatch(clone: _FlatClone, out: list[Any], n: int, pos: int) -> int:
        """A leaf arm whose item count misses the fold — empty arm, or error.

        :returns: ``pos`` unchanged (the empty alternate arm consumed nothing).
        :raises UnsupportedConstructError: On a non-empty mismatch (a
            compile/runtime disagreement).
        """
        fold = clone.fold
        if n:
            raise UnsupportedConstructError(
                f"pda: {fold.ctor!r}: {n} items match neither "
                f"{fold.n_items} slots nor the empty arm"
            )
        out.append(fold.ctor())  # empty alternate arm matched
        return pos

    def _match_vstr(self, sink: list[Any], arm: _FlatArm, i: int, pos: int) -> int:
        """Inline a terminal-only ``value_str`` reference — no frame per iteration.

        Runs item ``i``'s whole quantifier loop: each iteration selects the
        target clone's arm at the lookahead, matches its (all-terminal) items,
        slices the consumed span and appends the built model to ``sink`` —
        exactly the frame push, walk and completion it replaces.

        :param sink: The sink the iteration models append to.
        :param arm: The current arm.
        :param i: The ``_OP_VSTR`` item index.
        :param pos: The cursor position.
        :returns: The position after the whole quantifier loop.
        :raises PdaFail: On a terminal mismatch or an unmatched mandatory
            iteration with no default arm.
        """
        clone = arm.payloads[i]
        lo, hi = arm.los[i], arm.his[i]
        count = 0
        while count < lo or ((hi < 0 or count < hi) and self._gate_admits(arm, i, pos)):
            pos = self._vstr_once(clone, sink, pos)
            count += 1
        return pos

    def _vstr_once(self, clone: _FlatClone, sink: list[Any], pos: int) -> int:
        """One ``value_str`` iteration — select, match, slice, build, append.

        :param clone: The terminal-only ``value_str`` clone.
        :param sink: The sink the built model appends to.
        :param pos: The cursor position.
        :returns: The position after this iteration's match.
        :raises PdaFail: On a terminal mismatch or no viable arm.
        """
        text = self.text
        char = text[pos : pos + 1]
        varm = None
        for sel in clone.selectors:
            if (char != "" and char not in sel[0]) if sel[1] else char in sel[0]:
                varm = sel[2]
                break
        if varm is None:
            varm = clone.default
            if varm is None:
                raise PdaFail(f"no arm at {pos}")
        start = pos
        for j in range(varm.n):
            kj = varm.kinds[j]
            if kj == _OP_CC1:
                payload = varm.payloads[j]
                char = text[pos : pos + 1]
                if (
                    (char == "" or char in payload[0])
                    if payload[1]
                    else (char not in payload[0])
                ):
                    raise PdaFail(f"char class miss at {pos}")
                pos += 1
            elif kj == _OP_LIT1:
                lit = varm.payloads[j]
                if not text.startswith(lit, pos):
                    raise PdaFail(f"expected {lit!r} at {pos}")
                pos += len(lit)
            elif kj == _OP_LIT:
                pos = self._match_lit(varm, j, pos)
            else:
                pos = self._match_cc(varm, j, pos)
        span = text[start:pos]
        fast = clone.fast
        sink.append(
            fast({"value": span}, {"value"})
            if fast is not None
            else clone.fold.ctor(value=span)
        )
        return pos

    # ── island sub-parse + splice ─────────────────────────────────────

    def _island(self, name: str, sink: list[object]) -> None:
        """Resolve an island reference: a windowed Earley sub-parse, spliced.

        The island rule parses over a doubling window from the cursor; the
        longest completion folds through :attr:`fold` and its sub-model appends
        to ``sink``. The cursor advances past the consumed island span.

        :param name: The island rule name.
        :param sink: The enclosing sink the sub-model splices into.
        :raises PdaFail: With no fold to splice (island-free path), or when the
            island rule completes over no window from the cursor.
        """
        fold = self.fold
        if fold is None:
            raise PdaFail(f"island {name!r} at {self.pos}: no fold for splice")
        tree, end = island_parse(
            self.tables.island_tables(name), self.text, self.pos, name
        )
        model = fold.apply(tree)
        if model is not None:
            sink.append(model)
        self.pos += end

    # ── frame completion → fused model build ──────────────────────────

    def _complete(self, frame: list[Any]) -> None:
        """Pop a finished frame; build and report its model — the fused fold.

        A ``value_str`` frame slices its whole span, an ``alternation`` passes
        the first sub-model through, and a ``sequence`` binds each field to its
        item span or sub-model collection; a transparent frame builds nothing
        (its children already funnelled to ``_F_OUT``).
        """
        self.stack.pop()
        mode = frame[_F_MODE]
        if mode == _BUILD_TRANSPARENT:
            return  # children already funnelled to _F_OUT
        clone = frame[_F_CLONE]
        if mode == _BUILD_SEQ:
            if clone.fast is not None and frame[_F_ARM].n == clone.fold.n_items:
                model = self._build_fast(
                    clone, frame[_F_START], frame[_F_ENDS], frame[_F_SINKS]
                )
            else:
                model = self._build_sequence(frame, clone)
        elif mode == _BUILD_VALUE_STR:
            span = self.text[frame[_F_START] : self.pos]
            fast = clone.fast
            if fast is not None:
                model = fast({"value": span}, {"value"})
            else:
                model = clone.fold.ctor(value=span)
        else:  # _BUILD_ALT
            model = self._alt_model(frame)
        if model is not None:
            frame[_F_OUT].append(model)

    @staticmethod
    def _alt_model(frame: list[Any]) -> object:
        """The first sub-model under an ``alternation`` frame's matched arm."""
        sinks = frame[_F_SINKS]
        if sinks:
            for sub in sinks:
                if sub:
                    return sub[0]
        return None

    def _build_sequence(self, frame: list[Any], clone: _FlatClone) -> object:
        """Build a ``sequence`` clone's model from its bound field slots.

        The per-field fold is inlined (``text`` / ``gtext`` read the item's span
        off the frame's ``_F_ENDS``, ``model`` / ``models`` its ``_F_SINKS``). A
        zero-item arm match builds ``ctor()`` (the rule's empty alternate arm);
        any other item-count mismatch is a compile/runtime disagreement. With a
        :class:`~lexic.parsing.fold.FastCtor` licence the parts dict is seeded
        from the clone's baked defaults and handed to the validation-skip
        constructor; without one, :meth:`_build_validated` runs the rule's
        validated constructor.

        :raises UnsupportedConstructError: On an item count that matches neither
            the bound fields nor the empty arm, or a mode outside
            :data:`~lexic.ir.bind.BIND_MODES`.
        """
        fold = clone.fold
        arm = frame[_F_ARM]
        if arm.n != fold.n_items:
            if arm.n:
                raise UnsupportedConstructError(
                    f"pda: {fold.ctor!r}: {arm.n} items match neither "
                    f"{fold.n_items} slots nor the empty arm"
                )
            return fold.ctor()  # empty alternate arm matched
        if clone.fast is None:
            return self._build_validated(frame, fold)
        return self._build_fast(clone, frame[_F_START], frame[_F_ENDS], frame[_F_SINKS])

    def _build_fast(
        self,
        clone: _FlatClone,
        start: int,
        ends: list[int],
        sinks: list[Any] | None,
    ) -> object:
        """Build a fast-licenced ``sequence`` model from item spans and sinks.

        Seeds the parts dict from the clone's baked defaults, fills each bound
        field per its int-coded mode, and hands the parts to the
        validation-skip constructor — the shared build tail of
        :meth:`_build_sequence` and :meth:`_run_leaf`.

        :param clone: The clone (fast licence granted).
        :param start: The match's span start.
        :param ends: Per-item end positions.
        :param sinks: Per-item sub-model lists, or ``None``.
        :returns: The built model.
        """
        text = self.text
        parts = dict(clone.defaults)
        keys: set[str] = set()
        for item, mode, name, lo in clone.fields:
            if mode == _M_MODEL:
                sub = sinks[item] if sinks else None
                if sub:
                    parts[name] = sub[0]
                    keys.add(name)
            elif mode == _M_MODELS:
                sub = sinks[item] if sinks else None
                parts[name] = sub if sub is not None else []
                keys.add(name)
            elif mode == _M_GTEXT:
                span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
                if span or lo:
                    parts[name] = span
                    keys.add(name)
            else:  # _M_TEXT
                parts[name] = text[
                    (start if item == 0 else ends[item - 1]) : ends[item]
                ]
                keys.add(name)
        return clone.fast(parts, keys)

    def _build_validated(self, frame: list[Any], fold: RuleFold) -> object:
        """Build a ``sequence`` model through the validated constructor.

        The no-licence fallback of :meth:`_build_sequence` — field extraction
        is identical, but the values pass through ``fold.ctor`` (pydantic
        validation included).

        :raises UnsupportedConstructError: On a mode outside
            :data:`~lexic.ir.bind.BIND_MODES`.
        """
        fold_fields = fold.fields
        text = self.text
        ends = frame[_F_ENDS]
        sinks = frame[_F_SINKS]
        start = frame[_F_START]
        kwargs: dict[str, object] = {}
        for item, mode, name, lo in fold_fields:
            if mode == "text":
                kwargs[name] = text[
                    (start if item == 0 else ends[item - 1]) : ends[item]
                ]
            elif mode == "gtext":
                span = text[(start if item == 0 else ends[item - 1]) : ends[item]]
                if span or lo != 0:
                    kwargs[name] = span
            elif mode == "model":
                sub = sinks[item] if sinks else None
                if sub:
                    kwargs[name] = sub[0]
            elif mode == "models":
                sub = sinks[item] if sinks else None
                kwargs[name] = sub if sub is not None else []
            else:
                raise UnsupportedConstructError(f"pda: unknown field mode {mode!r}")
        return fold.ctor(**kwargs)


def parse_pda(tables: PdaTables, text: str, fold: ModelFold | None = None) -> object:
    """Parse ``text`` to a model with the fused predictive runtime.

    :param tables: The compiled predictive-parser tables.
    :param text: The input to parse.
    :param fold: The full-grammar fold for splicing island sub-models; ``None``
        (the island-free path) makes any island reference raise :class:`PdaFail`.
    :returns: The start rule's model instance.
    :raises PdaFail: On any deterministic-parse failure (caught by the compile
        seam, which retries on the full engine).
    """
    return PdaKernel(tables, text, fold).run()
