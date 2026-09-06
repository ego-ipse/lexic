"""Terminal matching — the PDA runtime's cursor-free recognition leaf.

Candidate ``lexic/parsing/pda/runtime/matchers.py``. Every function here reads
only the input ``text`` (plus the per-parse intern memo where it builds a
``value_str`` model), never the :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel`
cursor — the leaf shape :mod:`~lexic.parsing.pda.runtime.build` and
:mod:`~lexic.parsing.pda.runtime.islands` already have, so ``runtime`` imports
this, not the reverse.

Arm selection lives here too: a clone's FIRST-gated arm at a lookahead char is
a function of the clone and the char, not of the cursor.
"""

from __future__ import annotations

from typing import Any

from lexic.parsing.pda.compiler.program.flatten import (
    CHARTABLE_CAP,
    FlatArm,
    FlatClone,
    arm_expected,
    gate_take,
    vstr_model,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    DISPATCH_EMPTY,
    GATE_STOP,
    OP_CC,
    OP_CC1,
    OP_LIT,
    OP_LIT1,
)
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import InternMemo, build_vstr


def chase_dispatch[Carry](
    clone: FlatClone[Carry], char: str, pos: int
) -> FlatClone[Carry] | None:
    """Chase a frame-less dispatch alternation to its concrete target clone.

    The selection a dispatch alternation IS: a lead-char walk over selectors
    whose payloads are clones. Cursor-free, so both the kernel's entry path and
    the inline :data:`~lexic.parsing.pda.compiler.program.flatten.OP_VDISP` matcher run
    the one implementation — and refuse in the same words at the same position.

    :param clone: A ``BUILD_DISPATCH`` clone.
    :param char: The lookahead char selecting each dispatch step.
    :param pos: The cursor position, for the refusal.
    :returns: The concrete target clone, or ``None`` on the empty (nullable)
        arm — the caller then consumes nothing.
    :raises PdaFail: When no selector matches and there is no default.
    """
    while clone.mode == BUILD_DISPATCH:
        nxt = None
        for chars, negated, target in clone.selectors:
            if (char != "" and char not in chars) if negated else char in chars:
                nxt = target
                break
        if nxt is None:
            nxt = clone.default
            if nxt is None:
                raise PdaFail(f"no arm at {pos}", pos)
            if nxt is DISPATCH_EMPTY:
                return None
        clone = nxt
    return clone


def vdisp_once[Carry](
    text: str,
    intern: InternMemo[Carry],
    clone: FlatClone[Carry],
    sink: list[Carry],
    pos: int,
) -> int:
    """One :data:`~lexic.parsing.pda.compiler.program.flatten.OP_VDISP` iteration —
    chase, then the landed clone's ordinary ``value_str`` match.

    The two halves the entry path already ran, without the entry: by the
    licence (:func:`~lexic.parsing.pda.compiler.program.flatten.vdisp_target`) the chase
    always lands on a frame-less ``value_str``, which is precisely the clone
    ``_enter`` would have handed to this same :func:`vstr_once`.

    :raises PdaFail: From the chase (no arm) or the match (terminal mismatch).
    """
    target = chase_dispatch(clone, text[pos : pos + 1], pos)
    if target is None:  # licence-excluded; a defensive read, not a live path
        raise PdaFail(f"no arm at {pos}", pos)
    return vstr_once(text, intern, target, sink, pos)


def select_arm[Carry](clone: FlatClone[Carry], char: str, pos: int) -> FlatArm:
    """The clone's FIRST-gated arm at lookahead ``char``, or its default.

    :raises PdaFail: When no arm's FIRST matches and there is no default.
    """
    for chars, negated, candidate in clone.selectors:
        if (char != "" and char not in chars) if negated else char in chars:
            return candidate
    default = clone.default
    if default is None:
        raise PdaFail(
            f"no arm at {pos}", pos, rule=clone.name, wanted=arm_expected(clone)
        )
    return default


def match_cc1(text: str, payload: tuple[frozenset[str], bool], pos: int) -> int:
    """Match one exactly-once char class, returning the position after it.

    The ``OP_CC1`` body, kept out of the driver's inner loop: the mismatch test
    is the only place the class's polarity is read, and no bench grammar emits
    the op-code at all, so the driver need not carry the test or its locals.

    :param payload: The item's ``(chars, negated)`` pair.
    :raises PdaFail: On a mismatch, end of input included.
    """
    chars, negated = payload
    char = text[pos : pos + 1]
    if (char == "" or char in chars) if negated else char not in chars:
        raise PdaFail(f"char class miss at {pos}", pos)
    return pos + 1


def match_lit(text: str, arm: FlatArm, i: int, pos: int) -> int:
    """Match a literal item's whole quantifier loop, returning the new pos.

    :raises PdaFail: On a mismatch in the mandatory run or a gate-admitted
        partial literal.
    """
    lit = arm.payloads[i]
    llen = len(lit)
    lo, hi = arm.los[i], arm.his[i]
    count = 0
    while count < lo:
        if not text.startswith(lit, pos):
            raise PdaFail(f"expected {lit!r} at {pos}", pos)
        pos += llen
        count += 1
    gate = arm.gate_data[i]
    gk = arm.gate_kinds[i]
    if gk == GATE_STOP:  # the hot path, membership kept inline
        chars, negated = gate
        while hi < 0 or count < hi:
            char = text[pos : pos + 1]
            if (char == "" or char in chars) if negated else char not in chars:
                break
            if not text.startswith(lit, pos):
                raise PdaFail(f"expected {lit!r} at {pos}", pos)
            pos += llen
            count += 1
        return pos
    while (hi < 0 or count < hi) and gate_take(text, pos, gk, gate):
        if not text.startswith(lit, pos):
            raise PdaFail(f"expected {lit!r} at {pos}", pos)
        pos += llen
        count += 1
    return pos


def match_cc(text: str, arm: FlatArm, i: int, pos: int) -> int:
    """Match a char-class item's whole quantifier loop, returning the new pos.

    The gate loop needs no atom re-check: a stop-set / LL(2) pair is a subset of
    the atom's own FIRST, so a gate-admitted char always matches.

    :raises PdaFail: On a mismatch in the mandatory run.
    """
    chars, negated = arm.payloads[i]
    lo, hi = arm.los[i], arm.his[i]
    count = 0
    while count < lo:
        char = text[pos : pos + 1]
        if (char == "" or char in chars) if negated else char not in chars:
            raise PdaFail(f"char class miss at {pos}", pos)
        pos += 1
        count += 1
    gate = arm.gate_data[i]
    gk = arm.gate_kinds[i]
    if gk == GATE_STOP:  # the hot path, membership kept inline
        gchars, gnegated = gate
        while hi < 0 or count < hi:
            char = text[pos : pos + 1]
            if (char == "" or char in gchars) if gnegated else char not in gchars:
                break
            pos += 1
            count += 1
        return pos
    while (hi < 0 or count < hi) and gate_take(text, pos, gk, gate):
        pos += 1
        count += 1
    return pos


def match_arm(text: str, arm: FlatArm, pos: int) -> int:
    """Match every item of an all-terminal arm, returning the end position.

    The whole-arm recogniser: the caller slices ``text[start:end]`` for the
    span it wanted. Only the driver's own per-item loop needs item *ends*;
    a caller that wants one contiguous span wants exactly this.

    :raises PdaFail: On a terminal mismatch.
    """
    for j in range(arm.n):
        k = arm.kinds[j]
        if k == OP_LIT1:
            lit = arm.payloads[j]
            if not text.startswith(lit, pos):
                raise PdaFail(f"expected {lit!r} at {pos}", pos)
            pos += len(lit)
        elif k == OP_CC1:
            chars, negated = arm.payloads[j]
            char = text[pos : pos + 1]
            if (char == "" or char in chars) if negated else char not in chars:
                raise PdaFail(f"char class miss at {pos}", pos)
            pos += 1
        elif k == OP_LIT:
            pos = match_lit(text, arm, j, pos)
        else:
            pos = match_cc(text, arm, j, pos)
    return pos


def match_chartable[Carry](
    text: str, arm: FlatArm, i: int, sink: list[Carry], pos: int
) -> int:
    """Run an ``OP_VSTR`` loop whose target carries a
    :attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone.chartable`.

    One dict lookup per iteration stands in for the arm selection, the terminal
    match and the model build :func:`vstr_once` would run — the interior model
    of a lexical run read off a compile-time table instead of constructed per
    character. Same loop structure, same gate, same sink order.

    A lookup MISS routes to :func:`table_miss`, which produces exactly what the
    untabled path would.

    :param arm: The current arm.
    :param i: The ``OP_VSTR`` item index.
    :param pos: The cursor position.
    :returns: The position after the whole quantifier loop.
    :raises PdaFail: On an unmatched mandatory iteration (from the miss path).
    """
    clone = arm.payloads[i]
    if clone.runarm is not None:  # keyed by the matched span, not the lookahead
        return match_runtable(text, arm, i, sink, pos)
    get = clone.chartable.get
    append = sink.append
    lo, hi = arm.los[i], arm.his[i]
    gk, gate = arm.gate_kinds[i], arm.gate_data[i]
    count = 0
    while count < lo or ((hi < 0 or count < hi) and gate_take(text, pos, gk, gate)):
        model = get(text[pos : pos + 1])
        if model is None:
            pos = table_miss(text, clone, sink, pos)
        else:
            append(model)
            pos += 1
        count += 1
    return pos


def consult_extent[Carry](
    text: str, clone: FlatClone[Carry], runarm: FlatArm, pos: int
) -> int:
    """The end of a proved clone's whole extent, decided by its recognizer.

    The authoritative half of :func:`~lexic.parsing.product.regular
    .prove_regular`: the possessive pattern consumes exactly what the rule's own
    program would, so one C-level match stands in for the arm selection, every
    descent under it, and every per-character loop inside those. A miss is the
    refusal the selection would have raised, in the same words at the same
    position.

    :raises PdaFail: When the recognizer refuses at ``pos``.
    """
    matched = runarm.payloads[0].match(text, pos)
    if matched is None:
        raise PdaFail(
            f"no arm at {pos}", pos, rule=clone.name, wanted=arm_expected(clone)
        )
    return matched.end()


def run_span_once[Carry](
    text: str, clone: FlatClone[Carry], sink: list[Carry], pos: int
) -> int:
    """One iteration of a whole-extent ``value_str`` clone — match, then look up.

    The extent itself is matched by the same call the untabled path makes — or,
    for a proved clone, by the one pattern that stands for the whole program —
    so the span is identical; what the table answers is the SELECTION (there is
    one always-selected answer) and the BUILD, keyed by that span. Fills as
    spans arrive, capped — a corpus whose spans never repeat pays one dict miss
    per occurrence and keeps the saved calls.

    :returns: The position after the extent.
    """
    runarm = clone.runarm
    if runarm.kinds[0] == OP_CC:
        end = match_cc(text, runarm, 0, pos)
    elif runarm.kinds[0] == OP_LIT:
        end = match_lit(text, runarm, 0, pos)
    else:
        end = consult_extent(text, clone, runarm, pos)
    span = text[pos:end]
    table = clone.chartable
    model = table.get(span)
    if model is None:
        model = vstr_model(clone, span)
        if len(table) < CHARTABLE_CAP:
            table[span] = model
    sink.append(model)
    return end


def loop_spec(arm: FlatArm, i: int) -> tuple[int, int, int, Any]:
    """Item ``i``'s quantifier bounds and loop gate — every span loop's preamble.

    ``(lo, hi, gate_kind, gate_data)``, read once per item so the loop body
    reads locals. Shared by the span-matching loops rather than re-spelled in
    each: they differ only in which matcher runs per iteration.
    """
    return arm.los[i], arm.his[i], arm.gate_kinds[i], arm.gate_data[i]


def match_runtable[Carry](
    text: str, arm: FlatArm, i: int, sink: list[Carry], pos: int
) -> int:
    """Run an ``OP_VSTR`` loop whose target is a span-tabled run clone."""
    clone = arm.payloads[i]
    lo, hi, gk, gate = loop_spec(arm, i)
    count = 0
    while count < lo or ((hi < 0 or count < hi) and gate_take(text, pos, gk, gate)):
        pos = run_span_once(text, clone, sink, pos)
        count += 1
    return pos


def table_miss[Carry](
    text: str, clone: FlatClone[Carry], sink: list[Carry], pos: int
) -> int:
    """What a char-table lookup miss means — the untabled path's own answer.

    A TOTAL dispatch table IS its clone's selector union, so a miss there is the
    no-arm refusal the chase raises. Every other miss re-runs through
    :func:`vstr_once` and lets the real selection speak — a total ``value_str``
    table because a refusal is a property of the licence and not of the runtime,
    a fill-on-first-sight cache because a miss there is simply a character not
    seen yet (and ``vstr_once`` is where it gets remembered). Uninterned: a raise
    stores nothing, and an equal model is what a memo hit would have handed back.

    :returns: The position after the fallen-through iteration.
    :raises PdaFail: On the refusal the untabled path raises.
    """
    if clone.chartotal and clone.mode == BUILD_DISPATCH:
        raise PdaFail(f"no arm at {pos}", pos)  # verbatim, the chase's own words
    return vstr_once(text, {}, clone, sink, pos)


def vstr_once[Carry](
    text: str,
    intern: InternMemo[Carry],
    clone: FlatClone[Carry],
    sink: list[Carry],
    pos: int,
) -> int:
    """One ``value_str`` iteration — select, match, slice, build, append.

    A tabled clone (:attr:`~lexic.parsing.pda.compiler.program.flatten.FlatClone
    .chartable`) answers from the table: this is the entry an inline reference
    does not reach — a dispatch chase or a frame-less clone ENTRY, which is where
    the character-wide models of a dispatching lexical alternation are built. It
    is also where a fill-on-first-sight table LEARNS: a single-character arm
    remembers the model it just built, so the next occurrence of that character
    is a lookup.
    The single-item arm (the common case) skips both the item loop and the
    slice; a multi-item arm (a literal prefix then a char class, say) runs
    :func:`match_arm` over the whole arm and slices the combined span.

    :raises PdaFail: On a terminal mismatch or no viable arm.
    """
    char = text[pos : pos + 1]
    table = clone.chartable
    if table is not None:
        if clone.runarm is not None:
            return run_span_once(text, clone, sink, pos)
        model = table.get(char)
        if model is not None:
            sink.append(model)
            return pos + 1

    varm = select_arm(clone, char, pos)
    if varm.n != 1:  # the rare multi-item arm — cold, off the hot path
        end = match_arm(text, varm, pos)
        sink.append(build_vstr(clone, text[pos:end], intern))
        return end
    kj = varm.kinds[0]  # the common single-item arm — no item loop, no slice
    if kj == OP_CC1:
        chars, negated = varm.payloads[0]
        if (char == "" or char in chars) if negated else char not in chars:
            raise PdaFail(f"char class miss at {pos}", pos)
        model = build_vstr(clone, char, intern)
        if table is not None and len(table) < CHARTABLE_CAP:
            table[char] = model  # the fill: this clone's language is this wide
        sink.append(model)
        return pos + 1
    if kj == OP_LIT1:
        lit = varm.payloads[0]
        if not text.startswith(lit, pos):
            raise PdaFail(f"expected {lit!r} at {pos}", pos)
        sink.append(build_vstr(clone, lit, intern))
        return pos + len(lit)
    end = (
        match_lit(text, varm, 0, pos) if kj == OP_LIT else match_cc(text, varm, 0, pos)
    )
    sink.append(build_vstr(clone, text[pos:end], intern))
    return end
