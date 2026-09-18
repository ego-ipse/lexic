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

:mod:`lexic.parsing.pda.compiler.program.specialize` holds the passes that REWRITE
this artefact once it exists; this module is the artefact itself plus the
readers the runtime walks it with. It imports nothing from ``pda_tables`` (it
is a leaf w.r.t. the compiler and the spec types); the ``spec → flat`` bridge
lives in ``pda_tables`` beside the specs it reads.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, NamedTuple, Never, Protocol

from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.pda.compiler.program.lowering import ShapeBuild, no_shape_build
from lexic.parsing.pda.compiler.program.opcodes import (
    GATE_ATTEMPT,
    GATE_GREEDY,
    GATE_KWIN,
    GATE_PEEK,
    GATE_STOP,
    M_VALUE,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.core.scanner import scan_gate_take
from lexic.parsing.product.abi.construction import ProductValue

type BuildPlan[Carry] = tuple[tuple[int, int, int, ProductValue[Carry]], ...]
type FastConstruction[Carry] = Callable[[list[ProductValue[Carry]]], Carry]


def no_construction(
    *_args: ProductValue[Never], **_kwargs: ProductValue[Never]
) -> Never:
    """Refuse an impossible call through a recognition-only clone."""
    raise RuntimeError("recognition-only clone has no construction")


def no_fast_construction[Carry](_values: list[ProductValue[Carry]]) -> Carry:
    """Refuse an impossible positional build without a granted licence."""
    raise RuntimeError("clone has no positional construction licence")


def window_admits(text: str, pos: int, windows: Any, at_eof: bool = False) -> bool:
    """Whether the input at ``pos`` is EOF-exactly consistent with a k-window.

    The runtime test for a ``k``-window gate (Task 6.3 part c) — a loop
    take/skip gate (:data:`GATE_KWIN`) or an arm selector
    (:class:`KWindowSelect`). ``windows`` is a set of ``≤k``-length
    windows, each a tuple of pre-resolved ``(chars, negated)`` position sets.
    A position at or past end-of-input is the EOF sentinel ``""``, matched by a
    positive set carrying it and — only under ``at_eof`` — by a co-finite set
    that does not exclude it. A consumer iterating a gate charset as characters
    must expect the sentinel: ``ord("")`` raises. Consistency with any one
    window admits; the demoted branches are pairwise separable, so at most one
    side's windows can be consistent with a given lookahead.

    :param text: The whole input.
    :param pos: The cursor position the window is peeked from.
    :param windows: The ``taken`` / arm windows — a tuple of
        ``((chars, negated), ...)`` tuples.
    :param at_eof: Let a co-finite position match the EOF sentinel. OFF by
        default: unconditionally on, an earlier arm matches at end of input and
        SHADOWS a later one that would have parsed (87 more whole-parse
        fallbacks across the ground-truth corpora). :func:`select_gated` turns
        it on only for a rescue pass.
    :returns: ``True`` iff the lookahead is consistent with some window.
    """
    n = len(text)
    for win in windows:
        ok = True
        for j, (chars, negated) in enumerate(win):
            p = pos + j
            char = text[p] if p < n else ""
            member = (
                ((at_eof or char != "") and char not in chars)
                if negated
                else char in chars
            )
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
        return _attempt_admits(text, pos, gate)
    return _wide_gate_take(text, pos, gk, gate)


def _wide_gate_take(text: str, pos: int, gk: int, gate: Any) -> bool:
    """The gates that read more than two characters.

    Split from :func:`gate_take` so the three one- and two-character kinds —
    the ones a hot loop consults per iteration — keep their comparison and
    return with nothing in front of them. A gate that is about to scan a window,
    a noise run or a whole tail can afford the call it costs to get here.
    """
    if gk == GATE_GREEDY:
        return not _at_the_unit_end(text, pos, gate)
    if gk == GATE_KWIN:
        return window_admits(text, pos, gate)
    if gk == GATE_PEEK:
        return _peek_admits(text, pos, gate)
    return scan_gate_take(text, pos, gate)  # GATE_SCAN — the ScanGate itself


def _attempt_admits(text: str, pos: int, gate: Any) -> bool:
    """The TERMINAL attempt loop's decision — take while the char is FIRST-only.

    :raises PdaFail: A boundary whose char both the FIRST and the stored soft
        continuation accept is an arm choice in loop clothing, and a terminal
        loop has no sub-run to consult, so it bails to the gated engine.
    """
    ch = text[pos : pos + 1]
    chars, negated = gate[0]
    take = (ch != "" and ch not in chars) if negated else ch in chars
    if take:
        fchars, fnegated = gate[1]
        if (ch != "" and ch not in fchars) if fnegated else ch in fchars:
            raise ProbeFork(
                f"attempt loop at {pos}: taking and stopping are both viable", pos
            )
    return take


def _at_the_unit_end(text: str, pos: int, gate: Any) -> bool:
    """Is what remains the unit's tail and its certified continuation?

    The split-greedy licence's whole predicate. The loop runs greedily because
    the leftmost chain does, so the only place it may stop is where no further
    item could be carved without leaving the unit no tail to end with.

    ``starters`` present means the continuation's first characters cannot begin
    an item: the tail followed by one of them locates where the continuation
    BEGINS, and the continuation is parsed normally from there. Absent, the
    continuation is matched by spelling to the end of the input — its own
    characters could otherwise start an item, and a FIRST set is not an
    occurrence boundary.

    Answering ``False`` says only "not here": ordinary item recognition and the
    loop's minimum decide whether another iteration actually parses.
    """
    tail, close, starters = gate
    if not text.startswith(tail, pos):
        return False
    after = pos + len(tail)
    if starters is None:
        # Length FIRST, then a bounded startswith. `text[after:] == close`
        # copies the whole remaining suffix every time the tail matches, which
        # on a run of terminators is O(n) boundaries × O(n) copy — quadratic
        # character work, from a gate whose entire claim is that it reads a
        # bounded window.
        return after + len(close) == len(text) and text.startswith(close, after)
    return after == len(text) or text[after] in starters


def arm_expected(clone: FlatClone) -> tuple[tuple[str, ...], bool]:
    """The characters that would have selected some arm of ``clone``.

    A no-arm refusal's expected set: the union of the FIRST-gated selectors. A
    single negated selector is reported with its polarity intact rather than
    enumerated; a mix of polarities cannot be unioned honestly in one pair, so
    it reports nothing rather than something wrong.
    """
    if clone.wide_selectors is not None:
        return (), False
    negated = [neg for _chars, neg, _arm in clone.selectors]
    if not negated or any(negated) != all(negated):
        return (), False
    merged: set[str] = set()
    for chars, _neg, _arm in clone.selectors:
        merged |= chars
    return tuple(sorted(merged)), negated[0]


class WideSelect(Protocol):
    """A selection one lookahead character cannot make.

    What :attr:`FlatClone.wide_selectors` holds. Typed once here so a third
    kind of wide selection arrives by implementing this, not by widening a
    union at every site that names the two that exist today.
    """

    label: str
    """What this selection is called where a human reads it."""

    @property
    def arms(self) -> tuple[Any, ...]:
        """Every arm this selection can choose, gate stripped."""
        raise NotImplementedError

    def select(self, text: str, pos: int) -> Any:
        """The arm this selection admits at ``pos``, or ``None`` for none."""
        raise NotImplementedError


class KWindowSelect(NamedTuple):
    """Arms chosen by an EOF-exact match over ``≤k``-length position windows.

    :ivar entries: ``(windows, arm)`` pairs, where ``windows`` is a tuple of
        ``((chars, negated), ...)`` position windows.
    """

    entries: tuple[tuple[Any, Any], ...]

    label = "k-window"

    @property
    def arms(self) -> tuple[Any, ...]:
        """Every arm this selection can choose, gate stripped."""
        return tuple(arm for _windows, arm in self.entries)

    def select(self, text: str, pos: int) -> Any:
        """The arm whose window set matches at ``pos``, or ``None``."""
        for windows, candidate in self.entries:
            if window_admits(text, pos, windows):
                return candidate
        # Headed for a fallback: a co-finite window position cannot spell "any
        # character, OR the end", so an arm that legitimately ends the input is
        # unselectable. Retry admitting the sentinel — second pass, never
        # first, so it can only rescue a selection.
        for windows, candidate in self.entries:
            if window_admits(text, pos, windows, at_eof=True):
                return candidate
        return None


class NoiseSkipSelect(NamedTuple):
    """Arms chosen by the first character past a skipped ``W``-noise run.

    The skip does not consume: the winning arm re-parses its own noise, so the
    peek is recognition-only and a wrong pick fails the parse rather than
    silently mis-building.

    :ivar noise: ``(chars, negated)`` — the run skipped before peeking.
    :ivar entries: ``(chars, negated, arm)`` triples over the post-noise char.
    """

    noise: tuple[frozenset[str], bool]
    entries: tuple[tuple[frozenset[str], bool, Any], ...]

    label = "prefix negation"

    @property
    def arms(self) -> tuple[Any, ...]:
        """Every arm this selection can choose, gate stripped."""
        return tuple(arm for _chars, _negated, arm in self.entries)

    def select(self, text: str, pos: int) -> Any:
        """The arm admitting the first post-noise character, or ``None``."""
        at = _skip_noise(text, pos, self.noise[0], self.noise[1])
        char = text[at : at + 1]
        for chars, negated, candidate in self.entries:
            if (char != "" and char not in chars) if negated else char in chars:
                return candidate
        return None


def select_gated(text: str, pos: int, clone: FlatClone) -> Any:
    """The gated arm of a k-window or noise-skip alternation at ``pos``.

    Which of the two it is, is the selection's own business: both answer
    :meth:`~KWindowSelect.select`, so nothing here asks. The gate sets are
    pairwise separable, so at most one arm can match.

    :raises PdaFail: When no arm's gate matches and there is no default.
    """
    wide = clone.wide_selectors
    if wide is None:
        # Only reached through a `wide_selectors is not None` guard. Raised
        # rather than falling through to the default, which would turn an
        # impossible state into a quietly WRONG arm the moment that guard
        # moves. `RuntimeError` for the reason `frames_copy` uses it: the
        # engine seam catches `PdaFail` and would hide this behind an Earley
        # parse that succeeds.
        raise RuntimeError(f"select_gated: {clone.name!r} has no wide selection")
    got = wide.select(text, pos)
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
    :ivar gate_kinds: Per-item loop-gate code (``GATE_STOP`` / ``GATE_KWIN``).
    :ivar gate_data: Per-item gate body — a ``(chars, negated)`` pair (stop) or
        a tuple of `CharSet` windows (kwin). ``Any``-typed for the same reason
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


class FlatClone[Carry](IrLeaf[IrSelf, IrSelf]):
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
    :ivar wide_selectors: ``None`` on the single-char path; a
        :class:`KWindowSelect` or :class:`NoiseSkipSelect` when one lookahead
        character cannot make the choice. One slot, because the lowering sets
        at most one of the two by construction (:func:`_flatten_selectors`) and
        because every runtime site asks only WHETHER a wide selection is
        present, never which — :func:`select_gated` puts the question to the
        selection itself. When set, ``selectors`` is empty and the
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
        order, ``(chars, negated, prefix, window, sub)`` entries: ``chars`` the
        arm's FIRST pre-filter (``None`` for the always-admitted nullable
        default entry), ``prefix`` a leading-terminal regex and ``window`` the
        arm's compiled FIRST-k admission (both ``None`` when it has none), and
        ``sub`` a single-arm :class:`FlatClone` sharing the parent's
        :class:`FlatArm` (so op specialisation reached it once). The runtime
        tries entries in order via the sub-run seam; the follow set is the
        second-success audit's composition evidence. Dispatch and leaf
        specialisation are skipped for such a clone.
    :ivar mode: The build-mode (one of the ``_BUILD_*`` constants).
    :ivar ctor: What this clone's completion calls to build its value — the
        declared class, or the surface transform its symbol resolved to — or
        ``None`` when the clone builds nothing. Called by KEYWORD; a
        ``sequence`` clone's positional shortcut is :attr:`build`, and
        :attr:`fast` is the positional constructor :func:`vstr_model` calls.
    :ivar matched: The field :attr:`ctor` fills from the clone's OWN matched
        extent, ``""`` when no field does. What makes the ``value_str``
        construction sayable without a field name spelled in engine code.
    :ivar n_items: The rule's sequence-arm item count. A matched arm of a
        different width is the rule's EMPTY alternate arm, or a compile/runtime
        disagreement; nothing else distinguishes the two.
    :ivar fields: The keyword capture layout with int-coded modes —
        ``(item, mode, name, lo)`` tuples, one per capture. Empty when the
        clone builds nothing.
    :ivar plan: The fused build's POSITIONAL plan — one ``(mode, item, lo,
        default)`` entry per field of the model class, in the record's own
        field order. Read once, at bake, to compose :attr:`build`; no build
        walks it. Empty without a fast licence. Building by name instead cost
        a defaults-dict copy, a supplied-key set and a read-back through
        ``map(parts.get, cls._fields)`` per model.
    :ivar build: This shape's whole build, composed from :attr:`plan` at bake
        (:func:`~lexic.parsing.pda.compiler.program.lowering.shape_build`) — one
        operation per field, bound once, and no mode read per record. The two
        travel together: a pass that rewrites one MUST rewrite the other.
        :data:`~lexic.parsing.pda.compiler.program.lowering.no_shape_build` when the
        clone has no positional build, a ``value_str`` clone included
        (:func:`vstr_model` owns that construction).
    :ivar fast: The class's positional constructor when it granted the
        validation-skip licence, else ``None`` (the runtime builds through
        :attr:`ctor` by keyword). Called by :func:`vstr_model`; a ``sequence``
        clone's own build goes through :attr:`build`.
    :ivar defaults: The construction's field defaults the fused build seeds
        each plan entry from, or ``None``.
    :ivar leaf: ``True`` for a fast-licenced ``sequence`` clone whose every arm
        is all-terminal (``OP_VSTR`` included) — the runtime runs it
        frame-lessly in :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._run_leaf`.
    :ivar chartable: The char → model table of a clone whose language is one
        character wide, or ``None``. Its models are the ones :func:`vstr_model`
        builds, so an occurrence is a lookup rather than a build — the interior
        model of a lexical run RECONSTRUCTED from its span.
    :ivar runarm: The one quantified-terminal arm whose matched SPAN keys
        :attr:`chartable` (:func:`runarm_for`), or ``None`` — then the table is
        keyed by one character and the lookahead alone answers it.
    :ivar chartotal: Whether :attr:`chartable` is the clone's WHOLE language
        (:func:`chartable_for` — a miss is the refusal the untabled path raises)
        or a bounded fill-on-first-sight cache (:func:`charcache_for` — a miss
        means not seen yet). ``True`` whenever there is no table at all, so the
        pair is never read as "a cache with nothing in it".
    :ivar needs_ends: ``True`` when any bound field reads an item span (a
        ``text``/``gtext`` mode) — only then does a frame allocate and write
        per-item end positions.

    """

    # Declared in the order the annotations below read, which is the only
    # order that means anything: CPython SORTS __slots__ before it creates the
    # member descriptors, so the declaration cannot influence the layout and a
    # "hot slots first" ordering would be presentation dressed as mechanism.
    __slots__ = (
        "name",
        "selectors",
        "wide_selectors",
        "default",
        "struct_arm",
        "attempt",
        "mode",
        "ctor",
        "matched",
        "n_items",
        "fields",
        "plan",
        "fast",
        "build",
        "defaults",
        "leaf",
        "chartable",
        "chartotal",
        "runarm",
        "needs_ends",
        "completion",
    )

    name: str
    selectors: tuple[tuple[frozenset[str], bool, Any], ...]
    wide_selectors: WideSelect | None
    default: Any
    struct_arm: Any  # ScanGate | None — the empty-arm gate, consulted at select
    attempt: Any  # ((chars, negated), entries) | None — the attempt order
    mode: int
    ctor: Callable[..., Carry]
    matched: str
    n_items: int
    fields: tuple[tuple[int, int, str, int], ...]
    plan: BuildPlan[Carry]
    fast: FastConstruction[Carry]
    build: ShapeBuild[Carry]
    defaults: Mapping[str, ProductValue[Carry]] | None
    leaf: bool
    chartable: Any  # dict[str, Carry] | None — specialized table payload
    chartotal: bool
    runarm: Any  # FlatArm | None — the run whose SPAN keys the table
    needs_ends: bool
    completion: int


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


def clear_build[Carry](clone: FlatClone[Carry]) -> None:
    """Give a clone no build state — what a clone that builds nothing has.

    A transparent clone and a pass-through reach the same place: there is no
    construction, so the four fields say nothing rather than something
    empty-looking.
    """
    clone.fields = ()
    clone.plan = ()
    clone.fast = no_fast_construction
    clone.build = no_shape_build
    clone.defaults = None


def vstr_model[Carry](clone: FlatClone[Carry], span: str) -> Carry:
    """A ``value_str`` clone's model over its matched ``span``.

    The single home of that construction expression: the per-parse intern
    (:func:`~lexic.parsing.pda.runtime.build.build_vstr`) and the compile-time
    :attr:`FlatClone.chartable` both go through it, so a tabled model and a
    parse-built one cannot drift.

    :param clone: The ``value_str`` clone (or a ``value_str``-ref target).
    :param span: The matched source span — the model's ``value``.
    :returns: The built model.
    """
    fast = clone.fast
    if fast is not no_fast_construction and (plan := clone.plan):
        return fast(
            [span if mode == M_VALUE else default for mode, _i, _lo, default in plan]
        )
    return clone.ctor(**{clone.matched: span})


CHARTABLE_CAP = 256
"""Largest one-char language that earns a :attr:`FlatClone.chartable`.

A bound on compile-time work and artifact size, not on correctness: a wider
class keeps the per-occurrence build. Character classes carrying a model per
character are alphabets (digits, letters, a token's glyphs), and those fit.
"""


# ── post-flatten optimizer passes ──────────────────────────────────────────
