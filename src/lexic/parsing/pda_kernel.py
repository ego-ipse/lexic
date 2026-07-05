"""Fused predictive runtime — parses text to a model, no ParseTree on the path.

The runtime sibling of :class:`~lexic.parsing.kernel.Kernel`: where the Earley
kernel builds an SPPF a :class:`~lexic.parsing.fold.PositionalFold` later folds,
:class:`PdaKernel` walks the compiled :class:`~lexic.parsing.pda_tables.PdaTables`
and builds the model **directly during the walk** — the fold is fused into the
parse, so no intermediate :class:`~lexic.parsing.forest.ParseTree` is ever
allocated on the deterministic path.

**Explicit frame stack.** Rule, group and loop descent runs on an explicit
:attr:`PdaKernel.stack` of :class:`_Frame` work items — never Python recursion
(the PoC's ``_rule`` → ``_seq`` → ``_item`` → ``_atom`` → ``_rule`` cascade).
Per-parse state (the input, the cursor position, the frame stack) lives on the
kernel; :class:`PdaTables` is shared and immutable. A frame executes one arm's
item specs in order; a literal / char-class item runs its whole quantifier loop
inline (no descent), while a rule reference or inline group pushes a sub-frame
per iteration and resumes when it completes.

**Fused capture — the mirror of** :meth:`~lexic.parsing.fold.PositionalFold._models_at`.
A *clone frame* (a rule with a constructor) owns one :class:`_Slot` per item
(its consumed span and the models produced under it); a *transparent frame* (an
inline group, or a look-through ``fold=None`` clone) owns no slots and lets
everything produced inside it bubble straight through to the enclosing slot.
When a clone completes it builds exactly one model (:meth:`PdaKernel._build`)
and appends it to its parent's current slot — so a sub-model produced arbitrarily
deep, through any number of group and loop layers, lands in the nearest enclosing
*bound* slot, exactly as the fold's look-through ``_models_at`` collects the
topmost models under a kid. A slot's span slice (``text[start:end]``) reproduces
``_subtree_text``: the cursor advances monotonically, so a slot's consumed text
is one contiguous span.

Per fold kind (mirroring :meth:`~lexic.parsing.fold.PositionalFold._fold_node`):

- ``value_str`` → ``ctor(value=text[a:b])`` over the clone's whole span (its
  interior is pure-terminal — no sub-models are built below it);
- ``alternation`` → pass-through of the first model under the matched arm;
- ``sequence`` → per bound field, the slot's ``text`` / ``gtext`` span or its
  ``model`` / ``models`` collection; a zero-item arm match → ``ctor()``.

**Islands.** A reference to a conflicted (island) rule cannot be walked
deterministically, so it delegates to a windowed Earley sub-parse: a fresh
:class:`~lexic.parsing.kernel.Kernel` over the rule's
:meth:`~lexic.parsing.pda_tables.PdaTables.island_tables` runs
:meth:`~lexic.parsing.kernel.Kernel.longest_start_completion` over a doubling
window and takes the longest completion; the decoded
:class:`~lexic.parsing.forest.ParseTree` (via
:class:`~lexic.parsing.kernel.FastTree`, falling back to the first derivation
on ambiguity) folds through the supplied :class:`~lexic.parsing.fold
.PositionalFold` and the resulting sub-model splices into the current capture
exactly as a clone's model would — through the same nearest-bound-slot
look-through. The cursor advances past the consumed span. Without a fold
(:attr:`PdaKernel.fold` is ``None``, the island-free path) an island reference
raises :class:`PdaFail` so the engine reparses. A **fail-island** reference
(``IslandRef.fail`` — a semantic F1 stop-set-escape rule whose longest-match
split would silently diverge) always raises :class:`PdaFail`, independent of the
fold, so the compile seam falls back to the sound engine parse.

:class:`PdaFail` is internal to :mod:`lexic.parsing` — a PDA parse failure is
caught by the compile seam (Task 6) and retried on the full engine, which owns
the user-facing diagnostics. It never surfaces to the caller.
"""

from __future__ import annotations

from typing import cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrSelf, IrTuple
from lexic.parsing.charsets import CharSet
from lexic.parsing.engine import EarleyParser
from lexic.parsing.fold import PositionalFold, RuleFold
from lexic.parsing.forest import DERIVATION_STREAM, ParseTree, SppfNode
from lexic.parsing.kernel import FastTree, Kernel
from lexic.parsing.pda_tables import (
    CC,
    LIT,
    REF,
    ArmSpec,
    CloneKey,
    CloneSpec,
    GroupSpec,
    IslandRef,
    ItemSpec,
    PairGate,
    PdaTables,
)
from lexic.parsing.tables import ORIGIN_BITS, ParserTables

__all__ = ["PdaFail", "PdaKernel", "parse_pda"]

ISLAND_WINDOW = 256
"""Initial character window for an island Earley sub-parse; doubles on demand
while the best completion still touches the window edge and input remains."""

_DERIV_PARSER = EarleyParser()
"""The shared façade dispatcher the island derivation-stream fallback threads
through :data:`~lexic.parsing.forest.DERIVATION_STREAM`'s ``eval`` (stateless)."""


class PdaFail(Exception):
    """A predictive-parse failure — internal to :mod:`lexic.parsing`.

    Raised wherever the PDA cannot proceed deterministically (a terminal
    mismatch, no viable arm, trailing input, or an island reference this task
    does not yet resolve). Carries the failing position and a short reason for
    debugging; the compile seam catches it and falls back to the full engine,
    so it is **never** user-facing.
    """


class _Slot(IrLeaf[IrSelf, IrSelf]):
    """One item slot of a clone frame — its consumed span and its sub-models.

    A ``sequence`` clone binds fields to slots by item index; ``text``/``gtext``
    read the span, ``model``/``models`` read the collected sub-models.

    :ivar start: The cursor position where the item began.
    :ivar end: The cursor position where the item finished.
    :ivar models: The models produced anywhere under the item, in order.
    """

    __slots__ = ("start", "end", "models")

    start: int
    end: int
    models: list[object]

    def __init__(self) -> None:
        """Seed an empty, zero-width slot."""
        self.start = 0
        self.end = 0
        self.models = []


class _Frame(IrLeaf[IrSelf, IrSelf]):
    """One in-progress arm execution on the kernel's explicit descent stack.

    A frame executes :attr:`specs` (a rule clone's or inline group's selected
    arm) item by item. A *clone frame* (``fold`` set) owns one :class:`_Slot`
    per item and, on completion, builds a single model; a *transparent frame*
    (``fold is None`` — an inline group or look-through clone) owns no slots and
    funnels every model produced inside it straight to :attr:`out`.

    :ivar specs: The selected arm's item specs, in order.
    :ivar i: The current item index.
    :ivar count: Iterations completed for the current item (resumes a
        descending loop across sub-frame pushes).
    :ivar out: The parent slot's model list — where this frame's built model
        appends (clone frame) or where its children funnel (transparent frame).
    :ivar fold: The clone's baked fold config (``None`` for transparent frames).
    :ivar slots: One :class:`_Slot` per item (empty for transparent frames).
    """

    __slots__ = ("specs", "i", "count", "out", "fold", "slots")

    specs: tuple[ItemSpec, ...]
    i: int
    count: int
    out: list[object]
    fold: RuleFold | None
    slots: list[_Slot]

    def __init__(
        self, specs: tuple[ItemSpec, ...], out: list[object], fold: RuleFold | None
    ) -> None:
        """Seed a fresh frame.

        :param specs: The selected arm's item specs.
        :param out: The parent slot list this frame reports into.
        :param fold: The clone's fold config, or ``None`` for a transparent
            frame (which owns no slots).
        """
        self.specs = specs
        self.i = 0
        self.count = 0
        self.out = out
        self.fold = fold
        self.slots = [] if fold is None else [_Slot() for _ in specs]


class PdaKernel(IrLeaf[IrSelf, IrSelf]):
    """One predictive parse of ``text`` over compiled :class:`PdaTables`.

    Construct per parse, call :meth:`run` once; it returns the start clone's
    model. Per-parse state (:attr:`pos`, :attr:`stack`) is mutable on the
    kernel; :attr:`tables` is the shared, immutable compiled artifact.

    :ivar tables: The compiled predictive-parser tables.
    :ivar text: The input string.
    :ivar pos: The cursor position (advances monotonically — no backtracking).
    :ivar stack: The explicit descent stack of :class:`_Frame` work items.
    :ivar fold: The full-grammar fold used to splice island sub-models, or
        ``None`` on the island-free path (an island reference then raises
        :class:`PdaFail`).
    """

    __slots__ = ("tables", "text", "pos", "stack", "fold")

    tables: PdaTables
    text: str
    pos: int
    stack: list[_Frame]
    fold: PositionalFold | None

    def __init__(
        self, tables: PdaTables, text: str, fold: PositionalFold | None = None
    ) -> None:
        """Prepare a parse of ``text`` over ``tables``.

        :param tables: The compiled predictive-parser tables.
        :param text: The input to parse.
        :param fold: The full-grammar :class:`~lexic.parsing.fold.PositionalFold`
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
        start = self.tables.start_key
        if isinstance(start, IslandRef):
            raise PdaFail(f"start rule {start.name!r} is an island — no PDA")
        holder: list[object] = []
        self._enter_clone(self.tables.clones[start], holder)
        stack = self.stack
        while stack:
            self._step(stack[-1])
        if self.pos != len(self.text):
            raise PdaFail(f"trailing input at {self.pos}")
        if not holder:
            raise PdaFail("start rule produced no model")
        return holder[0]

    def _step(self, frame: _Frame) -> None:
        """Advance one frame until it descends (push + return) or completes.

        Runs inline through terminal items; on a rule-reference or group item it
        pushes one sub-frame per iteration and returns so the sub-frame runs
        next, resuming here (with :attr:`_Frame.count` already incremented) once
        it completes.
        """
        specs = frame.specs
        while frame.i < len(specs):
            spec = specs[frame.i]
            if frame.count == 0 and frame.fold is not None:
                frame.slots[frame.i].start = self.pos
            if spec.kind in (LIT, CC):
                self._match_run(spec)
                self._finish_item(frame)
                continue
            if self._need_iteration(spec, frame.count):
                frame.count += 1
                sink = frame.out if frame.fold is None else frame.slots[frame.i].models
                self._descend(spec, sink)
                return
            self._finish_item(frame)
        self._complete(frame)

    def _finish_item(self, frame: _Frame) -> None:
        """Record the current slot's span end and advance to the next item."""
        if frame.fold is not None:
            frame.slots[frame.i].end = self.pos
        frame.i += 1
        frame.count = 0

    def _need_iteration(self, spec: ItemSpec, count: int) -> bool:
        """Whether the current item takes another iteration at the cursor.

        Mandatory while ``count < lo``; past that, gated by the item's loop gate
        (a :class:`~lexic.parsing.pda_tables.PairGate` LL(2) 2-char slice, or a
        :class:`~lexic.parsing.pda_tables.StopGate` single-char stop-set),
        bounded by ``hi``.
        """
        if count < spec.lo:
            return True
        if spec.hi is not None and count >= spec.hi:
            return False
        gate = spec.gate
        if isinstance(gate, PairGate):
            return self.text[self.pos : self.pos + 2] in gate.pairs
        return gate.charset.has(self.text[self.pos : self.pos + 1])

    # ── item execution ────────────────────────────────────────────────

    def _match_run(self, spec: ItemSpec) -> None:
        """Match a terminal item's whole quantifier loop inline, advancing pos.

        Consumes ``lo`` mandatory matches, then keeps matching while the loop
        gate passes (up to ``hi``); a mismatch inside the mandatory run — or a
        gate-admitted partial literal — raises :exc:`PdaFail`.
        """
        lo, hi, gate, text = spec.lo, spec.hi, spec.gate, self.text
        count = 0
        while count < lo:
            self._match_atom(spec)
            count += 1
        if isinstance(gate, PairGate):
            pairs = gate.pairs
            while (hi is None or count < hi) and text[self.pos : self.pos + 2] in pairs:
                self._match_atom(spec)
                count += 1
            return
        charset = gate.charset
        while (hi is None or count < hi) and charset.has(text[self.pos : self.pos + 1]):
            self._match_atom(spec)
            count += 1

    def _match_atom(self, spec: ItemSpec) -> None:
        """Match one literal or char-class atom, advancing the cursor.

        :raises PdaFail: On a literal that does not match or a char class the
            next char is not in.
        """
        if spec.kind == LIT:
            payload = cast(str, spec.payload)
            if not self.text.startswith(payload, self.pos):
                raise PdaFail(f"expected {payload!r} at {self.pos}")
            self.pos += len(payload)
            return
        char = self.text[self.pos : self.pos + 1]
        if not cast(CharSet, spec.payload).has(char):
            raise PdaFail(f"char class miss at {self.pos}")
        self.pos += 1

    def _descend(self, spec: ItemSpec, sink: list[object]) -> None:
        """Push a sub-frame for one iteration of a rule-reference or group item.

        :param spec: The ``ref`` or ``grp`` item.
        :param sink: The slot list the sub-frame (or spliced island model)
            reports into.
        :raises PdaFail: On a reference to a *fail-island* (``IslandRef.fail`` —
            a semantic F1 escape, always, regardless of :attr:`fold`), or to any
            island with no fold to splice with (the island-free path) — the
            engine then reparses.
        """
        if spec.kind == REF:
            target = spec.payload
            if isinstance(target, IslandRef):
                if target.fail:
                    raise PdaFail(
                        f"fail-island {target.name!r} at {self.pos}: "
                        "F1 semantic escape, engine fallback"
                    )
                self._island(target.name, sink)
                return
            self._enter_clone(self.tables.clones[cast(CloneKey, target)], sink)
            return
        self._enter_group(cast(GroupSpec, spec.payload), sink)

    # ── island sub-parse + splice ─────────────────────────────────────

    def _island(self, name: str, sink: list[object]) -> None:
        """Resolve an island reference: a windowed Earley sub-parse, spliced.

        The island rule parses over a doubling window from the cursor; the
        longest completion folds through :attr:`fold` and its sub-model appends
        to ``sink`` (the enclosing capture — text/gtext slots ignore it and read
        the span). The cursor advances past the consumed island span.

        :param name: The island rule name.
        :param sink: The enclosing slot's model list the sub-model splices into.
        :raises PdaFail: With no fold to splice (island-free path), or when the
            island rule completes over no window from the cursor.
        """
        fold = self.fold
        if fold is None:
            raise PdaFail(f"island {name!r} at {self.pos}: no fold for splice")
        tree, end = self._island_parse(self.tables.island_tables(name), name)
        model = fold.apply(tree)
        if model is not None:
            sink.append(model)
        self.pos += end

    def _island_parse(self, tables: ParserTables, name: str) -> tuple[ParseTree, int]:
        """Longest completion of island ``name`` over a doubling window.

        Grows the window while the best completion still touches its edge and
        input remains (the ambiguous-longest-match risk), then decodes the
        winning completion to a :class:`~lexic.parsing.forest.ParseTree`.

        :param tables: The island rule's :class:`~lexic.parsing.tables.ParserTables`.
        :param name: The island rule name (for the failure message).
        :returns: ``(tree, end)`` — the derivation and its consumed length.
        :raises PdaFail: When the island completes over no window.
        """
        text, pos = self.text, self.pos
        remaining = len(text) - pos
        window = ISLAND_WINDOW
        best = self._island_run(tables, text[pos : pos + window])
        while window < remaining and (
            best is None or best[2] == min(window, remaining)
        ):
            window *= 2
            best = self._island_run(tables, text[pos : pos + window])
        if best is None:
            raise PdaFail(f"island {name!r}: no match at {pos}")
        kern, item, end = best
        tree = FastTree(kern).build((item << ORIGIN_BITS) | end)
        if not isinstance(tree, ParseTree):  # ambiguous — take the first derivation
            tree = self._island_derivation(kern, item, end, name)
        return tree, end

    @staticmethod
    def _island_run(
        tables: ParserTables, window: str
    ) -> tuple[Kernel, int, int] | None:
        """Run the island start rule over ``window``, longest origin-0 completion.

        :returns: ``(kernel, accepting_item, end)`` for the longest completion,
            or ``None`` when the rule never completes in the window.
        """
        kern = Kernel(tables, window)
        result = kern.longest_start_completion()
        if result is None:
            return None
        item, end = result
        return kern, item, end

    def _island_derivation(
        self, kern: Kernel, item: int, end: int, name: str
    ) -> ParseTree:
        """First derivation of an ambiguous island completion (engine policy).

        :raises PdaFail: When the completion decodes to no derivation.
        """
        node = SppfNode(kern.decode_item(item), end)
        stream = DERIVATION_STREAM.eval(_DERIV_PARSER, node, IrTuple(kern.to_chart()))
        tree = next(iter(stream), None)
        if not isinstance(tree, ParseTree):
            raise PdaFail(f"island {name!r}: no derivation")
        return tree

    def _enter_clone(self, clone: CloneSpec, out: list[object]) -> None:
        """Select ``clone``'s arm at the cursor and push its frame.

        :param clone: The rule clone to descend into.
        :param out: The parent slot list the clone's model reports into.
        """
        char = self.text[self.pos : self.pos + 1]
        specs = self._select(clone.arms, clone.default, char, clone.name)
        self.stack.append(_Frame(specs, out, clone.fold))

    def _enter_group(self, group: GroupSpec, out: list[object]) -> None:
        """Select ``group``'s arm at the cursor and push a transparent frame.

        :param group: The inline group to descend into.
        :param out: The enclosing slot list the group's children funnel into.
        """
        char = self.text[self.pos : self.pos + 1]
        specs = self._select(group.arms, group.default, char, "group")
        self.stack.append(_Frame(specs, out, None))

    def _select(
        self,
        arms: tuple[ArmSpec, ...],
        default: tuple[ItemSpec, ...] | None,
        char: str,
        label: str,
    ) -> tuple[ItemSpec, ...]:
        """Pick the FIRST-gated arm the lookahead selects, else the default arm.

        :param arms: The FIRST-gated :class:`~lexic.parsing.pda_tables.ArmSpec`\\ s.
        :param default: The all-nullable default arm's specs, or ``None``.
        :param char: The lookahead char (``""`` at end of input).
        :param label: The rule / group name, for the failure message.
        :returns: The selected arm's item specs.
        :raises PdaFail: When no arm's FIRST matches and there is no default.
        """
        for arm in arms:
            if arm.first.has(char):
                return arm.specs
        if default is not None:
            return default
        raise PdaFail(f"{label}: no arm at {self.pos}")

    # ── frame completion → fused model build ──────────────────────────

    def _complete(self, frame: _Frame) -> None:
        """Pop a finished frame; build and report its model (if it has one)."""
        self.stack.pop()
        if frame.fold is None:
            return  # transparent — children already funnelled to frame.out
        model = self._build(frame)
        if model is not None:
            frame.out.append(model)

    def _build(self, frame: _Frame) -> object:
        """Build a clone frame's model from its captured slots — the fused fold.

        Mirrors :meth:`~lexic.parsing.fold.PositionalFold._fold_node`: a
        ``value_str`` clone slices its whole span, an ``alternation`` passes the
        first model under its matched arm through, and a ``sequence`` binds each
        field to its slot's span or model collection.

        :raises UnsupportedConstructError: On a fold kind outside the vocabulary.
        """
        fold = cast(RuleFold, frame.fold)
        kind = fold.kind
        if kind == "value_str":
            start = frame.slots[0].start if frame.slots else self.pos
            return fold.ctor(value=self.text[start : self.pos])
        if kind == "alternation":
            for slot in frame.slots:
                if slot.models:
                    return slot.models[0]
            return None
        if kind == "sequence":
            return self._build_sequence(frame, fold)
        raise UnsupportedConstructError(
            f"pda: {fold.ctor!r}: unknown fold kind {kind!r}"
        )

    def _build_sequence(self, frame: _Frame, fold: RuleFold) -> object:
        """Build a ``sequence`` clone's model from its bound field slots.

        A zero-item arm match builds ``ctor()`` (the rule's empty alternate arm);
        any other slot-count mismatch is a compile/runtime disagreement.

        :raises UnsupportedConstructError: On a slot count that matches neither
            the bound fields nor the empty arm.
        """
        if len(frame.specs) != fold.n_items:
            if frame.specs:
                raise UnsupportedConstructError(
                    f"pda: {fold.ctor!r}: {len(frame.specs)} slots match neither "
                    f"{fold.n_items} items nor the empty arm"
                )
            return fold.ctor()  # empty alternate arm matched
        kwargs: dict[str, object] = {}
        for field in fold.fields:
            value = self._field_value(frame.slots[field.item], field.mode, field.lo)
            if value is not None:
                kwargs[field.name] = value
        return fold.ctor(**kwargs)

    def _field_value(self, slot: _Slot, mode: str, lo: int) -> object:
        """One bound field's folded value from ``slot`` under ``mode``.

        :raises UnsupportedConstructError: On a mode outside
            :data:`~lexic.ir.bind.BIND_MODES`.
        """
        if mode == "text":
            return self.text[slot.start : slot.end]
        if mode == "gtext":
            span = self.text[slot.start : slot.end]
            return None if (not span and lo == 0) else span
        if mode == "models":
            return slot.models
        if mode == "model":
            return slot.models[0] if slot.models else None
        raise UnsupportedConstructError(f"pda: unknown field mode {mode!r}")


def parse_pda(
    tables: PdaTables, text: str, fold: PositionalFold | None = None
) -> object:
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
