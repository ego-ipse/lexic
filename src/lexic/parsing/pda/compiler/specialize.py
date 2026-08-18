"""Post-flatten specialisation — the passes that carve the hot-loop op-codes.

Split from :mod:`lexic.parsing.pda.compiler.flatten`, which defines the flat
artefact and the readers the runtime walks it with; this module is everything
that REWRITES that artefact once it exists. :func:`optimize_program` is the
entry point and states the pass order, which is load-bearing: each pass reads
codes or licences an earlier one established.

Nothing here costs a parse anything — the program is built once, immutable, and
shared across every parse.
"""

from __future__ import annotations

from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.flatten import (
    CHARTABLE_CAP,
    FlatArm,
    FlatClone,
    vstr_model,
)
from lexic.parsing.pda.compiler.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_SEQ,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    GATE_ATTEMPT,
    OP_CC,
    OP_CC1,
    OP_GRP,
    OP_LEAF1,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_V1,
    OP_VDISP,
    OP_VRUN,
    OP_VSTR,
)

_TERMINAL_OPS = frozenset((OP_LIT, OP_CC, OP_LIT1, OP_CC1))
"""The op-codes that consume input without descending — the ``OP_VSTR``
inlining licence (a clone is inlinable iff every arm is all-terminal)."""


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


def _vdisp_landing(target: Any) -> bool:
    """Whether one chase step ends somewhere the inline matcher can run.

    Recursion terminates because a cycle of dispatch selectors is left
    recursion, which the analysis refuses before any clone exists — the same
    argument :func:`bake_chartables`' fixpoint rests on.
    """
    if not isinstance(target, FlatClone):
        return False  # DISPATCH_EMPTY: an empty arm is not a value_str match
    if target.mode != BUILD_DISPATCH:
        return _vstr_inlinable(target)
    steps = [step for _chars, _negated, step in target.selectors]
    if target.default is not None:
        steps.append(target.default)
    return bool(steps) and all(_vdisp_landing(step) for step in steps)


def vdisp_target(clone: Any) -> bool:
    """The :data:`OP_VDISP` licence: a chase that always lands frame-lessly.

    The chase is a lead-char walk and the match is then the landed clone's
    ordinary ``vstr_once`` — so the pair inlines whenever every clone the chase
    can reach is :func:`_vstr_inlinable`. Product-neutral by construction: the
    same ``vstr_once``, on the same clone, at the same position, same sink.

    A TABLED clone is refused because :data:`OP_VSTR` already answers it by
    lookup; a missing default is not refused, since the chase then raises on a
    miss exactly as the entry path does.
    """
    if not isinstance(clone, FlatClone) or clone.mode != BUILD_DISPATCH:
        return False
    return clone.chartable is None and _vdisp_landing(clone)


def _inline_value_strs(arm: FlatArm) -> None:
    """Rewrite refs the runtime can match inline to ``OP_VSTR`` in place.

    A terminal-only ``value_str`` clone qualifies, and so does any TABLED clone
    (:func:`chartable_for`) — a tabled dispatch alternation included, since the
    inline matcher answers it from the same table the entry would have chased to,
    reporting the same model into the same sink. An UNTABLED dispatch whose every
    target is inlinable becomes :data:`OP_VDISP` (:func:`vdisp_target`): the
    lookup is unavailable but the chase still is.

    **Never an item gated :data:`GATE_ATTEMPT`.** That gate is the TERMINAL
    attempt decision; the driver routes a non-terminal attempt item to
    :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel.attempt_iteration`
    instead, which speculates and rolls back. An inline matcher consults the
    gate directly, so rewriting such an item swaps a speculating loop for one
    that REFUSES when taking and stopping are both viable — the parse then falls
    back to the engine, same model, many times the cost.
    """
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if kind != OP_REF:
            continue
        target = arm.payloads[i]
        if _vstr_inlinable(target) or target.chartable is not None:
            kinds[i] = OP_VSTR
        elif vdisp_target(target) and arm.gate_kinds[i] != GATE_ATTEMPT:
            kinds[i] = OP_VDISP
    arm.kinds = tuple(kinds)


def _arm_char_span(arm: FlatArm, char: str) -> "str | None":
    """The span a single-item arm matches at ``char``, or ``None`` if it refuses.

    The table's admissibility test per (selector char, arm) pair: only an arm
    that is one exactly-once character-wide atom can be answered by a lookup
    keyed on one character.
    """
    if arm.n != 1:
        return None
    kind = arm.kinds[0]
    if kind == OP_CC1:
        chars, negated = arm.payloads[0]
        member = (char != "" and char not in chars) if negated else char in chars
        return char if member else None
    if kind == OP_LIT1 and arm.payloads[0] == char:
        return char
    return None


def _one_char_arm(arm: FlatArm) -> bool:
    """Whether the arm is one exactly-once character-wide atom, any polarity.

    The shape test behind both table kinds — :func:`_arm_char_span` answers the
    same question for one CHARACTER, which a co-finite class cannot enumerate.
    """
    if arm.n != 1:
        return False
    kind = arm.kinds[0]
    if kind == OP_CC1:
        return True
    return kind == OP_LIT1 and len(arm.payloads[0]) == 1


def charcache_for(clone: FlatClone) -> "dict[str, object] | None":
    """The empty, fill-on-first-sight table of a one-char clone whose set is not
    enumerable.

    Same licence as :func:`chartable_for` — every arm is one character wide, so
    the model is a total function of that character — but the key set cannot be
    written down at compile time: a co-finite class is infinite, and a class over
    :data:`CHARTABLE_CAP` is not worth pre-building. The characters an input
    actually uses are few, so the table fills as they arrive (in
    :func:`~lexic.parsing.pda.runtime.matchers.vstr_once`, which builds the model
    it stores) and stops at the cap.

    A MISS therefore means "not seen yet", NOT a refusal — which is why the two
    kinds are distinguished by :attr:`FlatClone.chartotal` rather than merged.

    :param clone: The candidate clone (post-specialisation, no total table).
    :returns: An empty dict to fill, or ``None`` when the licence does not hold.
    """
    if clone.default is not None or clone.mode != BUILD_VALUE_STR:
        return None
    if not _vstr_inlinable(clone):
        return None
    if not all(_one_char_arm(arm) for arm in _clone_arms(clone)):
        return None
    return {}


def runarm_for(clone: FlatClone) -> "FlatArm | None":
    """The sole always-selected RUN arm of a ``value_str`` clone, or ``None``.

    The span-keyed half of the licence. A clone whose only arm is one quantified
    terminal — ``ws ::= [ \\t\\n]*``, ``chars ::= [^"]+`` — accepts spans of many
    widths, so no character keys it; but the arm is the clone's whole answer, its
    width is whatever the run consumes, and the model is a total function of the
    span. Matching it is :func:`match_cc`/:func:`match_lit` (the same call the
    untabled path makes), and only the SELECTION and the BUILD are then answered
    from :attr:`FlatClone.chartable`, keyed by the matched span.

    Restricted to the shape where SELECTION CANNOT CHANGE THE MATCH: a default
    arm exists (so no lookahead can be refused, which is what lets a nullable run
    answer ε anywhere) and every arm is the same single run — which is how a
    nullable run rule actually compiles, its one arm appearing as both the
    FIRST-gated selector and the default. Nothing is then being chosen, so no
    refusal or arm decision can hide behind the lookup.

    :param clone: The candidate clone (post-specialisation).
    :returns: The run arm, or ``None`` when the licence does not hold.
    """
    if clone.mode != BUILD_VALUE_STR or clone.default is None:
        return None
    if not _vstr_inlinable(clone):
        return None
    shapes = {
        (arm.kinds[0], arm.payloads[0], arm.los[0], arm.his[0], arm.gate_kinds[0])
        for arm in _clone_arms(clone)
        if arm.n == 1
    }
    if len(shapes) != 1 or any(arm.n != 1 for arm in _clone_arms(clone)):
        return None
    if clone.default.kinds[0] not in (OP_CC, OP_LIT):
        return None
    return clone.default


def _value_str_chartable(clone: FlatClone) -> "dict[str, object] | None":
    """The table of a ``value_str`` clone whose every accepted string is one char."""
    table: dict[str, object] = {}
    for chars, negated, arm in clone.selectors:
        if negated or "" in chars or len(chars) > CHARTABLE_CAP:
            return None
        for char in chars:
            if char in table:
                continue  # an earlier selector already owns this lookahead
            span = _arm_char_span(arm, char)
            if span is None:
                return None
            try:
                table[char] = vstr_model(clone, span)
            except LexicError:
                return None  # the ctor refuses a char its class admits
        if len(table) > CHARTABLE_CAP:
            return None
    return table or None


def _dispatch_chartable(clone: FlatClone) -> "dict[str, object] | None":
    """The table of a dispatch clone whose every target is itself tabled.

    A dispatch alternation is a pass-through: the target's model IS the model the
    entry reports. So when every selector's target can answer one character from
    its own table, the whole chase collapses into one composed lookup — the
    character-wide models of a lexical alternation, without the chase.
    """
    table: dict[str, object] = {}
    for chars, negated, target in clone.selectors:
        if negated or "" in chars or len(chars) > CHARTABLE_CAP:
            return None
        sub = target.chartable
        if sub is None:
            return None
        for char in chars:
            model = sub.get(char)
            if model is None:
                return None  # the selector admits what the target refuses
            table.setdefault(char, model)
        if len(table) > CHARTABLE_CAP:
            return None
    return table or None


def chartable_for(clone: FlatClone) -> "dict[str, object] | None":
    """The char → model table of a clone whose language is one character wide.

    The reconstruction licence, derived from the clone alone. A ``value_str``
    clone earns it on :func:`_vstr_inlinable`'s terms (no descent, no gated or
    attempted selection) when every selector is a positive character set whose
    arm matches exactly that one character; a :data:`BUILD_DISPATCH` clone earns
    it when every target is already tabled. Either way the model of every string
    the clone accepts is known at compile time, and one dict lookup stands in for
    the arm selection, the chase and the build.

    Totality is what makes a lookup safe to trust: the keys ARE the selector
    union and a defaulting clone is refused, so a MISS is exactly the refusal the
    untabled path raises — see
    :func:`~lexic.parsing.pda.runtime.matchers.table_miss`.

    :param clone: The candidate clone (post-specialisation, targets baked first).
    :returns: The table, or ``None`` when the licence does not hold.
    """
    if clone.default is not None:
        return None
    if clone.mode == BUILD_DISPATCH:
        return _dispatch_chartable(clone)
    if clone.mode == BUILD_VALUE_STR and _vstr_inlinable(clone):
        return _value_str_chartable(clone)
    return None


def bake_chartables(clones: list[FlatClone]) -> None:
    """Bake every clone's :attr:`FlatClone.chartable`, targets before referrers.

    A fixpoint rather than one pass: a dispatch clone's table composes its
    targets', and dispatch chains nest. It terminates — every new table is a
    clone that had none, so the loop can only run as many times as there are
    clones, and a cycle of dispatch selectors is left recursion the analysis
    refuses before any clone exists.

    What the fixpoint could not enumerate then gets a fill-on-first-sight table
    (:func:`charcache_for`, keyed by character; :func:`runarm_for`, keyed by the
    matched span) — same licence, key set discovered instead of written down, so
    :attr:`FlatClone.chartotal` records which kind a clone has.
    """
    pending = True
    while pending:
        pending = False
        for clone in clones:
            if clone.chartable is None:
                clone.chartable = chartable_for(clone)
                pending = pending or clone.chartable is not None
    for clone in clones:
        if clone.chartable is not None:
            continue
        clone.runarm = runarm_for(clone)
        filling = clone.runarm is not None or charcache_for(clone) is not None
        if filling:
            clone.chartable = {}
            clone.chartotal = False
    _share_filling_tables(clones)


def _share_filling_tables(clones: list[FlatClone]) -> None:
    """One filling table per rule constructor — the intern memo's own key space.

    A rule compiles to several context clones, and the per-parse memo keys
    ``value_str`` models by ``(ctor, span)``: equal models are ONE instance across
    every clone of that rule. A per-clone table would narrow that to per-context
    sharing — which the interning gate reads as a regression, correctly. Handing
    every clone of a ctor the same dict keeps the sharing exactly as wide as the
    memo's, and now spans parses too. Sound whatever the clones' gates are: a span
    determines the model, so two contexts that match different spans still agree
    on every span they share.
    """
    by_ctor: dict[Any, dict[str, object]] = {}
    for clone in clones:
        if clone.chartable is None or clone.chartotal:
            continue
        clone.chartable = by_ctor.setdefault(clone.fold.ctor, clone.chartable)


def _specialize_vruns(arm: FlatArm) -> None:
    """Rewrite exactly-once ``OP_VSTR`` references to their one-call op-codes.

    Known here, so the leaf walk does not re-derive it per occurrence.
    """
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if kind != OP_VSTR or arm.los[i] != 1 or arm.his[i] != 1:
            continue
        kinds[i] = OP_VRUN if arm.payloads[i].runarm is not None else OP_V1
    arm.kinds = tuple(kinds)


def _unit_ref_target(arm: FlatArm) -> "FlatClone | None":
    """The arm's sole exactly-once clone reference, or ``None``.

    ``OP_REF1`` and ``OP_LEAF1`` count as well as ``OP_REF``: all three are the
    same fact — an exactly-once reference whose payload is the target clone —
    and only how the driver reaches it differs. Omitting one costs the
    alternation its frame-less dispatch, which is a frame and a model per
    occurrence, not a missed micro-optimisation. The main pass never sees one (calls
    specialise after this runs); :func:`~lexic.parsing.pda.compiler.lower
    .flatten_clones` does, when it optimises the attempt sub-clones, which
    share their parent's already-specialised arm.
    """
    if arm.n != 1 or arm.los[0] != 1 or arm.his[0] != 1:
        return None
    if arm.kinds[0] not in (OP_REF, OP_REF1, OP_LEAF1):
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
    inline_ops = _TERMINAL_OPS | {OP_VSTR, OP_VRUN, OP_V1, OP_VDISP}
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


def _specialize_leaf_refs(clone: FlatClone) -> None:
    """Rewrite exactly-once references to frame-less leaves to ``OP_LEAF1``.

    Every consumer that sees THROUGH a reference must list this code beside
    ``OP_REF1`` — :func:`_unit_ref_target` (dispatch conversion) and
    ``lower._arm_prefix_steps`` (admission prefixes) both do. An omission
    there does not slow the parse; it changes which tier parses.
    """
    for arm in _clone_arms(clone):
        _mark_arm_leaf_refs(arm)


def _runs_frameless(sub: FlatClone) -> bool:
    """Whether ``_enter`` would run ``sub`` through ``_run_leaf`` — the same
    questions it asks, asked once at compile time instead of per occurrence."""
    gated = (
        sub.attempt is not None
        or sub.struct_arm is not None
        or sub.kwin_selectors is not None
        or sub.pn_selectors is not None
    )
    return sub.leaf and sub.mode == BUILD_SEQ and not gated


def _mark_arm_leaf_refs(arm: FlatArm) -> None:
    """One arm's exactly-once frame-less-leaf references."""
    kinds = list(arm.kinds)
    for i, kind in enumerate(kinds):
        if kind != OP_REF1:
            continue
        if _runs_frameless(arm.payloads[i]):
            kinds[i] = OP_LEAF1
    arm.kinds = tuple(kinds)


def optimize_program(roots: list[FlatClone]) -> None:
    """Run the post-flatten passes over every reachable clone, in order.

    Terminal specialisation first (``OP_LIT1``/``OP_CC1``), then **dispatch
    conversion**, then ``value_str`` inlining (its licence reads the
    specialised op-codes), then leaf marking (which reads ``OP_VSTR``), then
    call specialisation (``OP_REF1``). All compile-time only — nothing here is
    a per-parse cost.

    Char tables (:func:`bake_chartables`) come after dispatch conversion — a
    dispatch clone can be tabled, and only conversion makes it one — and BEFORE
    inlining, whose licence reads the tables. Tabled-reference specialisation
    (:func:`_specialize_vruns`) runs LAST: it reads the ``OP_VSTR`` codes inlining
    cut and the tables baking filled, and nothing downstream re-reads the codes it
    replaces.

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
    bake_chartables(clones)
    for clone in clones:
        for arm in _clone_arms(clone):
            _inline_value_strs(arm)
    for clone in clones:
        _mark_leaves(clone)
    for clone in clones:
        _specialize_calls(clone)
    for clone in clones:
        for arm in _clone_arms(clone):
            _specialize_vruns(arm)
    for clone in clones:
        _specialize_leaf_refs(clone)
