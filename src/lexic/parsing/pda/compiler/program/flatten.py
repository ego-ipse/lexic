"""The flat int-coded records a compiled PDA IS.

The leaf half of the PDA compiler: the spec NamedTuples in
:mod:`lexic.parsing.pda.compiler.clones` are the compiler's *intermediate* (and the shape
the structural tests pin); :func:`~lexic.parsing.pda.compiler.clones.flatten_program`
lowers them, once per :func:`~lexic.parsing.pda.compiler.clones.compile_pda`, into the
flat artefact this module defines — :class:`FlatClone` / :class:`FlatArm`
carrying ``_OP_*`` op-codes and pre-resolved ``(chars, negated)`` membership
sets, which :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` walks
with integer dispatch (the ``tables.py``/``kernel.py`` philosophy).

Two neighbours hold what this one does not.
:mod:`lexic.parsing.pda.compiler.program.gating` holds the gates and the
selection that read these records — what admits the next character;
:mod:`lexic.parsing.pda.compiler.program.specialize.passes` holds the passes
that REWRITE the artefact once it exists. This module is the artefact, the
constructions that refuse, and the walks that enumerate it.

It imports nothing from ``pda_tables`` (it is a leaf w.r.t. the compiler and
the spec types); the ``spec → flat`` bridge lives in ``pda_tables`` beside the
specs it reads.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Never, Protocol

from lexic.exceptions import EngineInvariantError
from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.pda.compiler.program.bake.lowering import ShapeBuild, no_shape_build
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    M_VALUE,
    OP_GRP,
)
from lexic.parsing.product.abi.construction import ProductValue

type BuildPlan[Carry] = tuple[tuple[int, int, int, ProductValue[Carry]], ...]
type FastConstruction[Carry] = Callable[[list[ProductValue[Carry]]], Carry]


def no_construction(
    *_args: ProductValue[Never], **_kwargs: ProductValue[Never]
) -> Never:
    """Refuse an impossible call through a recognition-only clone."""
    raise EngineInvariantError("recognition-only clone has no construction")


def no_fast_construction[Carry](_values: list[ProductValue[Carry]]) -> Carry:
    """Refuse an impossible positional build without a granted licence."""
    raise EngineInvariantError("clone has no positional construction licence")


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
        """Every payload this selection can choose, gate stripped.

        Arms before the dispatch rewrite, target clones after it: the
        selection carries whatever its clone's mode says it carries.
        """
        raise NotImplementedError

    def select(self, text: str, pos: int) -> Any:
        """The payload this selection admits at ``pos``, or ``None`` for none."""
        raise NotImplementedError

    def with_payloads(self, payloads: tuple[Any, ...]) -> "WideSelect":
        """This selection with its payloads replaced, gates and order intact.

        The one operation the dispatch rewrite needs, so a wide alternation's
        targets live in the selection that chooses them rather than in a table
        beside it. Cold — it runs once at bake and never on a parse — and it
        RETURNS A NEW selection, because the record it maps is shared.

        :param payloads: New payloads, in :attr:`arms` order.
        :returns: A selection of the same kind, choosing the same way.
        """
        raise NotImplementedError


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
        (:func:`~lexic.parsing.pda.compiler.program.bake.lowering.shape_build`) — one
        operation per field, bound once, and no mode read per record. The two
        travel together: a pass that rewrites one MUST rewrite the other.
        :data:`~lexic.parsing.pda.compiler.program.bake.lowering.no_shape_build` when the
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
    :ivar longest: A longest-take rule's
        :class:`~lexic.parsing.pda.compiler.specs.LongestTake`: the matched span
        is checked for this reference's followers before it is committed. ``None``
        on every other clone.

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
        "longest",
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
    longest: Any  # LongestTake | None — the specs leaf holds the record


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


def clone_arms(clone: FlatClone) -> list[FlatArm]:
    """A clone's arms (gated + default), skipping dispatch clones' targets.

    Here beside :class:`FlatClone` and :class:`FlatArm` because it is their
    walker, not a specialisation policy: a dispatch clone holds TARGETS rather
    than arms, and a gated one holds its arms on its selection with
    ``selectors`` empty, so reading either structure directly is the mistake
    this exists to not make.

    :param clone: Any flat clone.
    :returns: Its arms, or ``[]`` for a dispatch clone.
    """
    if clone.mode == BUILD_DISPATCH:
        return []
    if clone.wide_selectors is not None:
        arms = list(clone.wide_selectors.arms)
    else:
        arms = [arm for _chars, _negated, arm in clone.selectors]
    if clone.default is not None:
        arms.append(clone.default)
    return arms


def all_clones(roots: list[FlatClone]) -> list[FlatClone]:
    """Every clone reachable from ``roots``, groups included (worklist walk).

    :param roots: The clones to start from.
    :returns: Every reachable clone, each once.
    """
    seen: set[int] = set()
    out: list[FlatClone] = []
    work = list(roots)
    while work:
        clone = work.pop()
        if id(clone) in seen:
            continue
        seen.add(id(clone))
        out.append(clone)
        for arm in clone_arms(clone):
            for kind, payload in zip(arm.kinds, arm.payloads):
                if kind == OP_GRP:
                    work.append(payload)
    return out
