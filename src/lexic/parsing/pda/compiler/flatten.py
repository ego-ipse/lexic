"""Flat int-coded runtime program + post-flatten optimizer passes (Task 8).

The leaf half of the PDA compiler: the spec NamedTuples in
:mod:`lexic.parsing.pda.compiler.clones` are the compiler's *intermediate* (and the shape
the structural tests pin); :func:`~lexic.parsing.pda.compiler.clones.flatten_program`
lowers them, once per :func:`~lexic.parsing.pda.compiler.clones.compile_pda`, into the
flat int-coded artifact this module defines — :class:`FlatClone` /
:class:`FlatArm` carrying ``_OP_*`` op-codes and pre-resolved
``(chars, negated)`` membership sets, which
:class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` walks with
integer dispatch (the ``tables.py``/``kernel.py`` philosophy).

:func:`optimize_program` then runs the specialisation passes that carve the
hot-loop op-codes (exactly-once terminals, inlinable ``value_str`` references,
frame-less leaf clones, pass-through dispatch clones, exactly-once calls).
Everything here is a build-time cost only — the program is shared, immutable,
across every parse. This module imports nothing from ``pda_tables`` (it is a
leaf w.r.t. the compiler and the spec types); the ``spec → flat`` bridge lives
in ``pda_tables`` beside the specs it reads.
"""

from __future__ import annotations

from typing import Any

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.core.scanner import scan_gate_take

OP_LIT, OP_CC, OP_REF, OP_GRP, OP_ISLAND, OP_FAIL = 0, 1, 2, 3, 4, 5
"""Flat item op-codes: literal, char class, clone reference, inline group,
parse-island reference, fail-island reference."""

OP_LIT1, OP_CC1, OP_VSTR, OP_REF1 = 6, 7, 8, 9
"""Specialised op-codes cut by the post-flatten passes: an exactly-once
(``lo == hi == 1``) literal / char class (no quantifier loop, no gate); a
reference to a terminal-only ``value_str`` clone the runtime matches inline —
whole quantifier loop, arm selection, span slice and model build — without
pushing a frame; and an exactly-once clone entry (ref or group) in an arm that
keeps no item ends, so the driver advances past it before descending (no
count bookkeeping, no resume re-check)."""

_TERMINAL_OPS = frozenset((OP_LIT, OP_CC, OP_LIT1, OP_CC1))
"""The op-codes that consume input without descending — the ``OP_VSTR``
inlining licence (a clone is inlinable iff every arm is all-terminal)."""

GATE_STOP, GATE_PAIR, GATE_KWIN, GATE_PEEK, GATE_SCAN, GATE_ATTEMPT = 0, 1, 2, 3, 4, 5
"""Flat loop-gate codes: single-char stop-set, LL(2) 2-char pair set, the
``k``-window gate (Task 6.3 part c) — a set of ``≤k``-length pre-resolved
``(chars, negated)`` position windows the runtime matches EOF-exactly against
``text[pos:pos+k]`` (the P2 demotion of a loop the single-char stop-set /
LL(2) pair could not separate) — and the P3 noise-skip peek gate (Task 6.4):
``((w_chars, w_negated), (take_chars, take_negated))`` — skip the maximal
``W``-noise run *without consuming*, take another iteration iff the first
post-noise char is in ``take`` (the iteration then re-parses the noise
normally — the peek is recognition-only, so a wrong take fails the parse
rather than silently mis-building) — and the P3 *structured* / P5 gate
(:data:`GATE_SCAN`, Task 6.6), a :class:`~lexic.parsing.pda.core.scanner.ScanGate`
the runtime consults via
:func:`~lexic.parsing.pda.core.scanner.scan_gate_take` (folding-aware
comment-bearing noise, and the rulename probe)."""

BUILD_TRANSPARENT, BUILD_VALUE_STR, BUILD_ALT, BUILD_SEQ = 0, 1, 2, 3
"""Flat clone build-modes — how a completed frame folds to a model (or, for
``transparent``, funnels its children through without building)."""

BUILD_DISPATCH = 4
"""A frame-less ``alternation`` clone: after hoist_arms every arm is a single
unit ruleref, and the alternation itself is a pass-through (the matched arm's
sub-model reports straight to the parent sink) — so the post-flatten pass
rewrites qualifying clones into dispatch tables whose selectors carry the
target :class:`FlatClone` directly and the runtime chases them in
:meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._enter` without a frame."""

BUILD_REDUCE = 5
"""The grammar-text (reducer) completion mode — the b1 twin of the model build
modes. A reduce clone captures every child into an ordered ``parts`` list and,
on completion, feeds the reducer's cleaned children to its reduction
``body.eval`` (:data:`R_KEEP`), contributes nothing (:data:`R_DROP`, a
DROP-noise rule its subtree is dropped from), or splices its parts straight
into the caller (:data:`R_SPLICE`, an inline group). One PDA compilation, one
frame/island stack — only this completion callback differs from the model
modes; see :mod:`lexic.parsing.pda.runtime.kernel.kernel`."""

R_KEEP, R_DROP, R_SPLICE = 0, 1, 2
"""Reduce completion kinds (:data:`BUILD_REDUCE` clones): KEEP evaluates the
rule's reduction body over its cleaned children; DROP (a DROP-noise rule)
recognises and consumes but yields nothing to its parent; SPLICE (an inline
group / synthetic clone) flattens its ordered children into the caller."""

DISPATCH_EMPTY = object()
"""The ``default`` sentinel of a dispatch clone whose alternation carried an
empty (nullable) arm — on a selector miss the runtime consumes nothing and
produces nothing, exactly as the empty arm's zero-item frame would."""

M_TEXT, M_GTEXT, M_MODEL, M_MODELS, M_SPAN = 0, 1, 2, 3, 4
"""Int-coded field-bind modes (:data:`~lexic.ir.spine.bind.BIND_MODES`, in order) —
what :attr:`FlatClone.fields` carries so the fused build never compares mode
strings."""

M_CONST, M_VALUE = 5, 6
"""The two plan-only modes. :data:`M_CONST` is a class field no bound field
supplies (the plan carries its default outright); :data:`M_VALUE` is a
``value_str`` rule's matched span. Neither is a :data:`BIND_MODES` entry —
they exist because :attr:`FlatClone.plan` covers every field of the class,
not just the bound ones."""

MODE_CODE = {
    "text": M_TEXT,
    "gtext": M_GTEXT,
    "model": M_MODEL,
    "models": M_MODELS,
    "span": M_SPAN,
}
"""Bind-mode string → flat int code."""

HI_UNBOUNDED = -1
"""The flat ``his`` sentinel for an unbounded (``None``) quantifier upper bound."""


def _window_admits(text: str, pos: int, windows: Any) -> bool:
    """Whether the input at ``pos`` is EOF-exactly consistent with a k-window.

    The runtime test for a ``k``-window gate (Task 6.3 part c) — a loop
    take/skip gate (:data:`GATE_KWIN`) or an arm selector
    (:attr:`FlatClone.kwin_selectors`). ``windows`` is a set of ``≤k``-length
    windows, each a tuple of pre-resolved ``(chars, negated)`` position sets. A
    position at or past end-of-input is the EOF sentinel ``""`` — matched
    **only** by a positive set that carries it (a FOLLOW-extended END position),
    never by a negated (co-finite) set. The sentinel may however be CARRIED in
    a negated set's ``chars`` (a stop set built from a FOLLOW that reaches
    END), where it is inert for matching — but a consumer iterating a gate
    charset as characters must expect it: ``ord("")`` raises. Consistency
    with any one window admits; the demoted branches are pairwise separable,
    so at most one side's windows
    can be consistent with a given lookahead.

    :param text: The whole input.
    :param pos: The cursor position the window is peeked from.
    :param windows: The ``taken`` / arm windows — a tuple of
        ``((chars, negated), ...)`` tuples.
    :returns: ``True`` iff the lookahead is consistent with some window.
    """
    n = len(text)
    for win in windows:
        ok = True
        for j, (chars, negated) in enumerate(win):
            p = pos + j
            char = text[p] if p < n else ""
            member = (char != "" and char not in chars) if negated else char in chars
            if not member:
                ok = False
                break
        if ok:
            return True
    return False


def _skip_noise(text: str, pos: int, chars: frozenset, negated: bool) -> int:
    """The position past the maximal ``W``-noise run at ``pos`` (non-consuming).

    The P3 peek's first half: ``(chars, negated)`` is the pre-resolved
    skippable alphabet ``W``; the caller inspects the char at the returned
    position without ever moving the real cursor.
    """
    n = len(text)
    while pos < n:
        ch = text[pos]
        member = (ch not in chars) if negated else (ch in chars)
        if not member:
            break
        pos += 1
    return pos


def _peek_admits(text: str, pos: int, gate: Any) -> bool:
    """Whether a P3 peek gate (:data:`GATE_PEEK`) takes another iteration.

    Skips the maximal noise run, then tests the first post-noise char against
    the ``take`` set — end-of-input is never a member (the loop exits).
    """
    (w_chars, w_negated), (t_chars, t_negated) = gate
    p = _skip_noise(text, pos, w_chars, w_negated)
    ch = text[p : p + 1]
    if t_negated:
        return ch != "" and ch not in t_chars
    return ch in t_chars


def gate_take(text: str, pos: int, gk: int, gate: Any) -> bool:
    """Whether a flat loop gate of kind ``gk`` admits another iteration at ``pos``.

    :data:`GATE_ATTEMPT` here is the TERMINAL attempt loop's decision (the
    driver routes non-terminal attempt items to
    :meth:`PdaKernel._attempt_iteration` before consulting a gate): take while
    the char is in the FIRST alone, and a char viable for BOTH the FIRST and
    the stored soft continuation is an arm choice in loop clothing — with no
    sub-run to consult, the terminal loop bails to the gated engine.

    :raises PdaFail: A terminal attempt boundary whose char both sets accept.
    """
    if gk == GATE_STOP:
        ch = text[pos : pos + 1]
        chars, negated = gate
        return (ch != "" and ch not in chars) if negated else ch in chars
    if gk == GATE_ATTEMPT:
        ch = text[pos : pos + 1]
        chars, negated = gate[0]
        take = (ch != "" and ch not in chars) if negated else ch in chars
        if take:
            fchars, fnegated = gate[1]
            if (ch != "" and ch not in fchars) if fnegated else ch in fchars:
                raise ProbeFork(
                    f"attempt loop at {pos}: taking and stopping are both viable",
                    pos,
                )
        return take
    if gk == GATE_PAIR:
        return text[pos : pos + 2] in gate
    if gk == GATE_KWIN:
        return _window_admits(text, pos, gate)
    if gk == GATE_PEEK:
        return _peek_admits(text, pos, gate)
    return scan_gate_take(text, pos, gate)  # GATE_SCAN — the ScanGate itself


def arm_expected(clone: FlatClone) -> tuple[tuple[str, ...], bool]:
    """The characters that would have selected some arm of ``clone``.

    A no-arm refusal's expected set: the union of the FIRST-gated selectors. A
    single negated selector is reported with its polarity intact rather than
    enumerated; a mix of polarities cannot be unioned honestly in one pair, so
    it reports nothing rather than something wrong.
    """
    if clone.kwin_selectors is not None or clone.pn_selectors is not None:
        return (), False
    negated = [neg for _chars, neg, _arm in clone.selectors]
    if not negated or any(negated) != all(negated):
        return (), False
    merged: set[str] = set()
    for chars, _neg, _arm in clone.selectors:
        merged |= chars
    return tuple(sorted(merged)), negated[0]


def select_gated(text: str, pos: int, clone: FlatClone) -> Any:
    """The gated arm of a k-window or noise-skip alternation at ``pos``.

    A P2 clone matches ``text[pos:pos+k]`` EOF-exactly against each arm's
    window set; a P3 clone skips the maximal ``W``-noise run *without
    consuming* and selects the arm containing the first post-noise char (the
    winner re-parses its own noise — the peek is recognition-only, so a wrong
    pick fails the parse rather than silently mis-building). The gate sets are
    pairwise separable, so at most one arm can match.

    :raises PdaFail: When no arm's gate matches and there is no default.
    """
    got = None
    if clone.kwin_selectors is not None:
        for windows, candidate in clone.kwin_selectors:
            if _window_admits(text, pos, windows):
                got = candidate
                break
    else:
        (w_chars, w_negated), sels = clone.pn_selectors
        p = _skip_noise(text, pos, w_chars, w_negated)
        ch = text[p : p + 1]
        for chars, negated, candidate in sels:
            if (ch != "" and ch not in chars) if negated else ch in chars:
                got = candidate
                break
    if got is None and clone.default is None:
        raise PdaFail(
            f"no arm at {pos}", pos, rule=clone.name, wanted=arm_expected(clone)
        )
    return got if got is not None else clone.default


class FlatArm(IrLeaf[IrSelf, IrSelf]):
    """One arm lowered to parallel int-coded arrays — the hot-loop unit.

    Every per-item field is a positional tuple indexed by item number, so the
    runtime binds one local per array at frame entry and indexes with ``[i]``
    (no NamedTuple attribute descriptors on the hot path).

    :ivar n: Item count.
    :ivar kinds: Per-item op-code (one of the ``_OP_*`` constants).
    :ivar payloads: Per-item body — a ``str`` (lit), a ``(chars, negated)``
        membership pair (cc), the target :class:`FlatClone` (ref), a
        :class:`FlatClone` group body (grp), or the island rule name. Typed
        ``Any`` (a heterogeneous op-stream, the ``tables.py`` int-array
        precedent) so the hot loop reads it without a per-access ``cast``.
    :ivar los: Per-item quantifier lower bound.
    :ivar his: Per-item quantifier upper bound (``HI_UNBOUNDED`` for none).
    :ivar gate_kinds: Per-item loop-gate code (``GATE_STOP`` / ``GATE_PAIR``).
    :ivar gate_data: Per-item gate body — a ``(chars, negated)`` pair (stop) or
        a frozenset of 2-char prefixes (pair). ``Any``-typed for the same reason
        as :attr:`payloads`.
    """

    __slots__ = ("n", "kinds", "payloads", "los", "his", "gate_kinds", "gate_data")

    n: int
    kinds: tuple[int, ...]
    payloads: tuple[Any, ...]
    los: tuple[int, ...]
    his: tuple[int, ...]
    gate_kinds: tuple[int, ...]
    gate_data: tuple[Any, ...]

    # Built field-by-field by ``_flatten_arm`` (via ``__new__``) — the parallel
    # arrays are too many for a positional ``__init__`` signature.


class FlatClone(IrLeaf[IrSelf, IrSelf]):
    """A clone (or inline group) lowered to arm selectors + a build-mode.

    Groups reuse this shape with :data:`BUILD_TRANSPARENT` and no fold —
    entering either selects a FIRST-gated arm at the lookahead char and pushes a
    frame. Constructed empty (``__new__``) then filled by ``flatten_program``'s
    second pass so a recursive reference resolves to the live object (no id
    indirection on the hot path).

    A :data:`BUILD_DISPATCH` clone (cut by :func:`convert_dispatch`) reuses
    :attr:`selectors` and :attr:`default` with clone payloads instead of arms —
    the runtime chases them frame-lessly.

    :ivar name: The rule this clone stands for, or ``""`` when it stands for
        nothing the grammar named (an inline group). The flat artifact carries
        its own provenance: a consumer holding a clone — the runtime deciding
        which rule to island, a trace naming a frame — can say what it is
        without reaching back into the compile-side binding view for a name.
    :ivar selectors: FIRST-gated arms as ``(chars, negated, arm)`` triples;
        ``arm`` is the target :class:`FlatClone` on a dispatch clone.
    :ivar kwin_selectors: ``None`` on the single-char path; a tuple of
        ``(windows, arm)`` pairs on a ``k``-window-gated alternation (Task 6.3
        part c), where ``windows`` is a tuple of ``≤k``-length
        ``((chars, negated), ...)`` position windows. When set, the runtime
        selects an arm by EOF-exact window match (:meth:`~lexic.parsing.pda
        .runtime.PdaKernel._select_arm_kwin`) instead of the lead char, and the
        dispatch/leaf specialisations are skipped for this clone.
    :ivar pn_selectors: ``None`` on the single-char path; a
        ``((w_chars, w_negated), ((chars, negated, arm), ...))`` pair on a P3
        noise-skip alternation (Task 6.4): the runtime skips the maximal
        ``W``-noise run without consuming and selects the arm containing the
        first post-noise char (:meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel
        ._select_arm_peek`); the winner re-parses its own noise. The
        dispatch/leaf specialisations are skipped for this clone.
    :ivar default: The all-nullable default :class:`FlatArm`, or ``None``; on
        a dispatch clone the default target clone or :data:`DISPATCH_EMPTY`.
    :ivar struct_arm: The empty-arm structured-noise
        :class:`~lexic.parsing.pda.core.scanner.ScanGate`, or ``None``. When set, the
        runtime consults :func:`~lexic.parsing.pda.core.scanner.scan_gate_take` before
        the FIRST-gated selection: a take admits the gated arms, a refusal
        selects :attr:`default` (the escape arm). Dispatch conversion is skipped
        for such a clone (the gate branch must survive).
    :ivar attempt: ``None`` on an ordinary clone. On an ATTEMPT clone,
        ``(follow, entries)`` — the rule's soft-FOLLOW CharSet and, in attempt
        order, ``(chars, negated, sub)`` entries: ``chars`` the arm's FIRST
        pre-filter (``None`` for the always-admitted nullable default entry)
        and ``sub`` a single-arm :class:`FlatClone` sharing the parent's
        :class:`FlatArm` (so op specialisation reached it once). The runtime
        tries entries in order via the sub-run seam; the follow set is the
        second-success audit's composition evidence. Dispatch and leaf
        specialisation are skipped for such a clone.
    :ivar mode: The build-mode (one of the ``_BUILD_*`` constants).
    :ivar fold: The rule's :class:`~lexic.parsing.fold.RuleFold`, or ``None``
        (transparent).
    :ivar fields: The fold's bound fields with int-coded modes —
        ``(item, mode, name, lo)`` tuples (empty without a fast licence).
    :ivar plan: The fused build's POSITIONAL plan — one ``(mode, item, lo,
        default)`` entry per field of the model class, in the record's own
        field order, so a build reads the plan straight into a values list and
        constructs the tuple. Empty without a fast licence. Building by name
        instead cost a defaults-dict copy, a supplied-key set and a read-back
        through ``map(parts.get, cls._fields)`` per model.
    :ivar fast: The fold's :attr:`~lexic.parsing.fold.FastCtor.make` parts
        constructor, or ``None`` (the runtime uses the validated ``ctor``).
    :ivar defaults: The fold's :attr:`~lexic.parsing.fold.FastCtor.defaults`
        the fused build seeds each parts dict from, or ``None``.
    :ivar leaf: ``True`` for a fast-licenced ``sequence`` clone whose every arm
        is all-terminal (``OP_VSTR`` included) — the runtime runs it
        frame-lessly in :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._run_leaf`.
    :ivar needs_ends: ``True`` when any bound field reads an item span (a
        ``text``/``gtext`` mode) — only then does a frame allocate and write
        per-item end positions.

    Reduce clones (:data:`BUILD_REDUCE`, the grammar-text path) additionally
    carry the completion data below; a model clone never sets or reads them.

    :ivar reduce_kind: One of :data:`R_KEEP` / :data:`R_DROP` /
        :data:`R_SPLICE`.
    :ivar reduce_body: The rule's reduction body (an
        :class:`~lexic.ir.base.IrSelf`), or ``None`` for DROP / SPLICE.
    :ivar reduce_is_yield: ``True`` when the body IS ``YIELD`` (the clone's
        whole span is its value).
    :ivar reduce_span: ``True`` when the body mentions ``YIELD`` (its matched
        span is passed as ``n``).
    :ivar reduce_can_drop: ``plan.can_drop`` for the rule — whether a DROP-noise
        span is reachable beneath it (a span read then cannot be one O(1) slice).
    """

    __slots__ = (
        "name",
        "selectors",
        "kwin_selectors",
        "pn_selectors",
        "default",
        "struct_arm",
        "attempt",
        "mode",
        "fold",
        "fields",
        "plan",
        "fast",
        "defaults",
        "leaf",
        "needs_ends",
        "reduce_kind",
        "reduce_body",
        "reduce_is_yield",
        "reduce_span",
        "reduce_can_drop",
    )

    name: str
    selectors: tuple[tuple[frozenset[str], bool, Any], ...]
    kwin_selectors: Any
    pn_selectors: Any
    default: Any
    struct_arm: Any  # ScanGate | None — the empty-arm gate, consulted at select
    attempt: Any  # ((chars, negated), entries) | None — the attempt order
    mode: int
    fold: Any  # RuleFold | None — Any-typed like payloads: hot-loop reads
    fields: tuple[tuple[int, int, str, int], ...]
    plan: tuple[tuple[int, int, int, Any], ...]
    fast: Any
    defaults: Any
    leaf: bool
    needs_ends: bool
    reduce_kind: int
    reduce_body: Any  # IrSelf | None
    reduce_is_yield: bool
    reduce_span: bool
    reduce_can_drop: bool


class PdaProgram(IrLeaf[IrSelf, IrSelf]):
    """The flat int-coded runtime program — what :class:`PdaKernel` walks.

    :ivar start: The start :class:`FlatClone`, or an
        :class:`~lexic.parsing.pda.compiler.clones.IslandRef` when the start rule is
        itself an island (the whole-grammar opt-out).
    :ivar delegates: The island-interior
        :class:`~lexic.parsing.pda.compiler.delegate_compile.DelegateSource` (Task 6.2),
        or ``None`` — the lazy per-island delegate-clone table the island
        Earley sub-parses thread in. Homed here (not on ``PdaTables``) so the
        artifact's attribute count is untouched.
    """

    __slots__ = ("start", "delegates")

    start: Any  # FlatClone | IslandRef — the island marker lives in pda_tables
    delegates: Any  # DelegateSource | None — the delegate_compile leaf

    def __init__(self, start: Any, delegates: Any = None) -> None:
        """Bind the entry clone (or island opt-out marker) and delegate source."""
        self.start = start
        self.delegates = delegates


# ── post-flatten optimizer passes ──────────────────────────────────────────


def _clone_arms(clone: FlatClone) -> list[FlatArm]:
    """A clone's arms (gated + default), skipping dispatch clones' targets."""
    if clone.mode == BUILD_DISPATCH:
        return []
    if clone.kwin_selectors is not None:
        arms = [arm for _windows, arm in clone.kwin_selectors]
    elif clone.pn_selectors is not None:
        arms = [arm for _chars, _negated, arm in clone.pn_selectors[1]]
    else:
        arms = [arm for _chars, _negated, arm in clone.selectors]
    if clone.default is not None:
        arms.append(clone.default)
    return arms


def all_clones(roots: list[FlatClone]) -> list[FlatClone]:
    """Every clone reachable from ``roots``, groups included (worklist walk)."""
    seen: set[int] = set()
    out: list[FlatClone] = []
    work = list(roots)
    while work:
        clone = work.pop()
        if id(clone) in seen:
            continue
        seen.add(id(clone))
        out.append(clone)
        for arm in _clone_arms(clone):
            for kind, payload in zip(arm.kinds, arm.payloads):
                if kind == OP_GRP:
                    work.append(payload)
    return out


def _specialize_terminals(arm: FlatArm) -> None:
    """Rewrite exactly-once terminals to their loop-free op-codes in place."""
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if arm.los[i] == 1 and arm.his[i] == 1:
            if kind == OP_LIT:
                kinds[i] = OP_LIT1
            elif kind == OP_CC:
                kinds[i] = OP_CC1
    arm.kinds = tuple(kinds)


def _vstr_inlinable(clone: Any) -> bool:
    """The ``OP_VSTR`` licence: a terminal-only ``value_str`` clone.

    Never an attempt clone — the inline matcher selects one arm by FIRST,
    which is exactly the decision an attempt clone exists to NOT make that
    way — and never a windowed / peeked / struct-gated clone: the inline
    matcher's ``select_arm`` reads ``selectors`` only, and a gated clone's
    live arms hang off its gate structures (a k-window ``value_str`` inlined
    here selected from an EMPTY list and failed every mandatory iteration —
    latent while such rules islanded, exposed when they began to run).
    """
    return (
        clone.mode == BUILD_VALUE_STR
        and clone.attempt is None
        and clone.kwin_selectors is None
        and clone.pn_selectors is None
        and clone.struct_arm is None
        and all(
            all(kind in _TERMINAL_OPS for kind in arm.kinds)
            for arm in _clone_arms(clone)
        )
    )


def _inline_value_strs(arm: FlatArm) -> None:
    """Rewrite refs to inlinable ``value_str`` clones to ``OP_VSTR`` in place."""
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if kind == OP_REF and _vstr_inlinable(arm.payloads[i]):
            kinds[i] = OP_VSTR
    arm.kinds = tuple(kinds)


def _unit_ref_target(arm: FlatArm) -> "FlatClone | None":
    """The arm's sole exactly-once clone reference, or ``None``.

    ``OP_REF1`` counts as well as ``OP_REF``: it is the same fact — an
    exactly-once reference whose payload is the target clone — and only the
    driver's resume bookkeeping differs. The main pass never sees one (calls
    specialise after this runs); :func:`~lexic.parsing.pda.compiler.lower
    .flatten_clones` does, when it optimises the attempt sub-clones, which
    share their parent's already-specialised arm.
    """
    if arm.n != 1 or arm.los[0] != 1 or arm.his[0] != 1:
        return None
    if arm.kinds[0] not in (OP_REF, OP_REF1):
        return None
    return arm.payloads[0]


def convert_dispatch(clone: FlatClone) -> None:
    """Rewrite a qualifying ``alternation`` clone into a dispatch table.

    Qualifies when every gated arm is a single unit clone reference and the
    default (if any) is empty or itself a unit clone reference — the exact
    shape hoist_arms guarantees for rule alternations. The alternation is a
    pass-through, so entering the selected target with the parent's sink is
    observationally identical to the frame it replaces.
    """
    if clone.mode != BUILD_ALT or clone.kwin_selectors is not None:
        return  # a k-window-gated alternation selects by window, not lead char
    if clone.pn_selectors is not None:
        return  # a noise-skip alternation selects by post-noise peek
    if clone.struct_arm is not None:
        return  # an empty-arm gate must run before any lead-char dispatch
    if clone.attempt is not None:
        return  # an attempt clone tries arms in order, never dispatches one
    targets = [_unit_ref_target(arm) for _chars, _negated, arm in clone.selectors]
    if any(target is None for target in targets):
        return
    default: Any = None
    if clone.default is not None:
        if clone.default.n == 0:
            default = DISPATCH_EMPTY
        else:
            default = _unit_ref_target(clone.default)
            if default is None:
                return
    clone.selectors = tuple(
        (chars, negated, target)
        for (chars, negated, _arm), target in zip(clone.selectors, targets)
    )
    clone.default = default
    clone.mode = BUILD_DISPATCH


def _mark_leaves(clone: FlatClone) -> None:
    """Grant the frame-less licence to an all-terminal ``sequence``/``value_str``.

    A leaf's every arm consists of terminal (``OP_VSTR`` included) items only,
    so no descent can occur under it and the runtime builds its model inline
    without a frame.

    ``value_str`` earns it on exactly :func:`_vstr_inlinable`'s terms — the same
    licence that lets a REFERENCE to such a clone become ``OP_VSTR``. A clone
    reached by reference was already running frame-lessly; one reached by
    ENTRY (through a dispatch chase, say) was not, and paid a frame per
    occurrence for a match that cannot descend.
    """
    if clone.fast is None:
        return
    if clone.mode == BUILD_VALUE_STR:
        clone.leaf = _vstr_inlinable(clone)
        return
    if clone.mode != BUILD_SEQ:
        return
    if clone.kwin_selectors is not None or clone.pn_selectors is not None:
        return  # a gated selection cannot run frame-lessly by lead char
    if clone.struct_arm is not None or clone.attempt is not None:
        return
    inline_ops = _TERMINAL_OPS | {OP_VSTR}
    clone.leaf = all(
        all(kind in inline_ops for kind in arm.kinds) for arm in _clone_arms(clone)
    )


def _specialize_calls(clone: FlatClone) -> None:
    """Rewrite exactly-once clone entries to ``OP_REF1`` where ends are unkept.

    Licenced only in clones that never record item ends (non-``sequence``
    modes, or a ``sequence`` with no span-reading field) — the driver then
    advances past the item before descending, skipping the resume re-check
    that exists solely to write the item's end position.
    """
    if clone.mode == BUILD_SEQ and clone.needs_ends:
        return
    for arm in _clone_arms(clone):
        kinds = list(arm.kinds)
        for i, kind in enumerate(kinds):
            if kind in (OP_REF, OP_GRP) and arm.los[i] == 1 and arm.his[i] == 1:
                kinds[i] = OP_REF1
        arm.kinds = tuple(kinds)


def optimize_program(roots: list[FlatClone]) -> None:
    """Run the post-flatten passes over every reachable clone, in order.

    Terminal specialisation first (``OP_LIT1``/``OP_CC1``), then **dispatch
    conversion**, then ``value_str`` inlining (its licence reads the
    specialised op-codes), then leaf marking (which reads ``OP_VSTR``), then
    call specialisation (``OP_REF1``). All compile-time only — nothing here is
    a per-parse cost.

    Dispatch runs BEFORE ``value_str`` inlining because the two compete for
    the same arm and dispatch is never the worse of the pair. Inlining rewrites
    a unit ``OP_REF`` to ``OP_VSTR``, which :func:`_unit_ref_target` does not
    recognise — so one inlinable arm used to disqualify its whole alternation,
    and every OTHER arm then paid a pass-through frame to save nothing. Both
    specialisations remove exactly one frame from the inlined arm; only
    dispatch also removes it from the arms beside it.
    """
    clones = all_clones(roots)
    for clone in clones:
        for arm in _clone_arms(clone):
            _specialize_terminals(arm)
    for clone in clones:
        convert_dispatch(clone)
    for clone in clones:
        for arm in _clone_arms(clone):
            _inline_value_strs(arm)
    for clone in clones:
        _mark_leaves(clone)
    for clone in clones:
        _specialize_calls(clone)
