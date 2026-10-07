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

from typing import Any, NamedTuple

from lexic.parsing.pda.compiler.program.flatten import (
    CHARTABLE_CAP,
    FlatArm,
    FlatClone,
    vstr_model,
)
from lexic.parsing.pda.compiler.program.gating import (
    arm_expected,
    gate_take,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    DISPATCH_EMPTY,
    GATE_STOP,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
)
from lexic.parsing.pda.core.errors import IslandEscape, PdaFail
from lexic.parsing.pda.runtime.admission import admits, clone_admits
from lexic.parsing.pda.runtime.build import Frame, InternMemo, build_vstr


def chase_dispatch[Carry](
    clone: FlatClone[Carry], text: str, pos: int
) -> FlatClone[Carry] | None:
    """Chase a frame-less dispatch alternation to its concrete target clone.

    The selection a dispatch alternation IS, per hop: a clone carrying a wide
    selection asks that selection, and one without walks its lead-char
    selectors. A chain may mix the two in any order — a lead-char dispatch can
    land on a window-gated one and the reverse — so both live in this one
    implementation, and the kernel's entry path, :meth:`_settle` and the
    inline :data:`~lexic.parsing.pda.compiler.program.flatten.OP_VDISP` matcher
    refuse in the same words at the same position.

    The position does NOT move across the chase: every hop selects at ``pos``,
    which is what makes the landed clone face exactly the cursor the elided
    frames would have handed it.

    A clone with no wide selection pays one attribute load and an ``is None``
    per hop — the loop reads ``wide_selectors`` where it already read ``mode``
    — and then runs the lead-char walk unchanged, with the lookahead character
    taken once before the loop rather than per hop.

    :param clone: A ``BUILD_DISPATCH`` clone.
    :param text: The document, for a wide selection's own match.
    :param pos: The cursor position, for the selection and for the refusal.
    :returns: The concrete target clone, or ``None`` on the empty (nullable)
        arm — the caller then consumes nothing.
    :raises PdaFail: When no selector matches and there is no default.
    """
    try:  # the lookahead: indexing, and end of input as the rare exception
        char = text[pos]
    except IndexError:
        char = ""
    while clone.mode == BUILD_DISPATCH:
        wide = clone.wide_selectors
        if wide is None:
            nxt = None
            for chars, negated, target in clone.selectors:
                if (char != "" and char not in chars) if negated else char in chars:
                    nxt = target
                    break
        else:
            nxt = wide.select(text, pos)
        if nxt is None:
            nxt = clone.default
            if nxt is None:
                if wide is not None:
                    # A wide clone's miss is the refusal `select_gated` raised
                    # before this clone was a dispatch — same rule, same
                    # wanted set. A bare refusal here would name no rule, and
                    # the document would be refused by an anonymous path.
                    raise PdaFail(
                        f"no arm at {pos}",
                        pos,
                        rule=clone.name,
                        wanted=arm_expected(clone),
                    )
                # A lead-char miss keeps the words it always had: the
                # `chartotal` refusal below mirrors them verbatim.
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
    target = chase_dispatch(clone, text, pos)
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
    try:
        char = text[pos]
    except IndexError:
        raise PdaFail(f"char class miss at {pos}", pos) from None
    if (char in chars) if negated else char not in chars:
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
        limit = len(text)
        if negated:
            while (hi < 0 or count < hi) and pos < limit and text[pos] not in chars:
                if not text.startswith(lit, pos):
                    raise PdaFail(f"expected {lit!r} at {pos}", pos)
                pos += llen
                count += 1
        else:
            while (hi < 0 or count < hi) and pos < limit and text[pos] in chars:
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

    The gate loop needs no atom re-check: a stop-set is a subset of
    the atom's own FIRST, so a gate-admitted char always matches.

    Each loop indexes the character and bounds-checks against the length, and
    the polarity — fixed for the whole run — chooses the loop once rather than
    being tested per character. Past the end there is no character at all, and
    BOTH polarities fail there: a negated class admits every character it does
    not hold, but it does not admit the absence of one.

    :raises PdaFail: On a mismatch in the mandatory run.
    """
    chars, negated = arm.payloads[i]
    lo, hi = arm.los[i], arm.his[i]
    limit = len(text)
    count = 0
    if negated:
        while count < lo:
            if pos >= limit or text[pos] in chars:
                raise PdaFail(f"char class miss at {pos}", pos)
            pos += 1
            count += 1
    else:
        while count < lo:
            if pos >= limit or text[pos] not in chars:
                raise PdaFail(f"char class miss at {pos}", pos)
            pos += 1
            count += 1
    gate = arm.gate_data[i]
    gk = arm.gate_kinds[i]
    if gk == GATE_STOP:  # the hot path, membership kept inline
        gchars, gnegated = gate
        if gnegated:
            while (hi < 0 or count < hi) and pos < limit and text[pos] not in gchars:
                pos += 1
                count += 1
        else:
            while (hi < 0 or count < hi) and pos < limit and text[pos] in gchars:
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
            try:  # inline: a call per exactly-once class is the cost here
                char = text[pos]
            except IndexError:
                raise PdaFail(f"char class miss at {pos}", pos) from None
            if (char in chars) if negated else char not in chars:
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
        try:  # end of input is the rare exception, not a test per character
            model = get(text[pos])
        except IndexError:
            model = get("")
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
    try:  # the lookahead: indexing, and end of input as the rare exception
        char = text[pos]
    except IndexError:
        char = ""
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
        take = clone.longest
        if take is not None and (
            take.exit_at.search(text, pos + take.lead, end)
            or (take.extends_at is not None and take.extends_at.match(text, end))
        ):
            # A shorter end this reference could continue from, or a longer
            # match: the span is not the island's answer, so ask the island.
            raise IslandEscape(take.island, pos)
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


STOP_DEAD, STOP_MAYBE, STOP_VIABLE = 0, 1, 2
"""What a stop side's literal continuation proves: it cannot match the text,
it might, or it reaches the end of the document exactly."""

_SKIP, _KILL, _MAYBE = -1, -2, -3
"""One item's step when it is not a match of known width (:func:`_item_step`)."""

type _Link = tuple[FlatArm, int, int, int]
"""One frame of the stop side: its arm, the item its rest starts at, the item
read as optional (or ``-1``), and the item that may iterate again (or ``-1``)."""


class _Rest(NamedTuple):
    """One stop side's walk: its frames innermost first, the text, and whether
    the outermost frame is the document's root (a prefix run's is not)."""

    chain: list[_Link]
    text: str
    rooted: bool


def stop_side_dead(
    stack: list[Frame], arm: FlatArm, i: int, text: str, at: tuple[int, bool]
) -> bool:
    """Whether stopping the loop at item ``i`` of the top frame provably dies.

    The stop side's continuation is walked against the TEXT, not one character:
    the rest of the top arm after ``i``, then each enclosing frame's rest (from
    :meth:`~lexic.parsing.pda.runtime.build.Frame.rest_after`, the item it is in
    counted as a further iteration where it can repeat). Only a literal or an
    exactly-once class is checked and advanced; anything wider stops the walk
    undecided once its first character could match, and an item with no first
    set the walk reads stops it at once. An optional or relaxed item that
    matches is tried both ways; only a non-nullable mandatory item that cannot
    match kills. Past the document's root the text must be spent; past a prefix
    run's root nothing is known. So DEAD is a proof: no string any stop
    continuation derives begins with the text at ``pos``.

    :param at: ``(pos, rooted)`` — where the boundary is, and whether the
        stack's outermost frame is the document's root.
    :returns: ``True`` only when the stop side is dead: taking is then the only
        resolution, and nothing was sampled.
    """
    pos, rooted = at
    chain: list[_Link] = [(arm, i + 1, -1, -1)]
    for frame in stack[-2::-1]:
        start, relax = frame.rest_after()
        again = frame.i if relax == -1 and _may_repeat(frame) else -1
        chain.append((frame.arm, start + 1, relax, again))
    return _walk(_Rest(chain, text, rooted), 0, i + 1, pos) == STOP_DEAD


def _may_repeat(frame: Frame) -> bool:
    """Whether the item a frame is in can take a further iteration."""
    return frame.i < frame.arm.n and frame.arm.his[frame.i] != 1


def _walk(rest: _Rest, f: int, j: int, pos: int) -> int:
    """The stop side from item ``j`` of link ``f`` at ``pos``: DEAD, MAYBE or VIABLE."""
    chain, text = rest.chain, rest.text
    while f < len(chain):
        arm, _start, relax, again = chain[f]
        if (
            again != -1
            and j == again + 1
            and _item_step(arm, again, again, text, pos) != _SKIP
        ):
            return STOP_MAYBE  # a further iteration of the item it is in
        while j < arm.n:
            step = _item_step(arm, j, relax, text, pos)
            if step in (_KILL, _MAYBE):
                return STOP_DEAD if step == _KILL else STOP_MAYBE
            if step == _SKIP:
                j += 1
            elif arm.los[j] > 0 and j != relax:
                pos, j = pos + step, j + 1
            else:
                return _both_ways(rest, (f, j + 1), pos, step)
        f += 1
        j = chain[f][1] if f < len(chain) else 0
    if not rest.rooted:
        return STOP_MAYBE
    return STOP_VIABLE if pos == len(text) else STOP_DEAD


def _both_ways(rest: _Rest, at: tuple[int, int], pos: int, width: int) -> int:
    """An optional exactly-once item that matches: taken, then skipped.

    DEAD only when both readings die — taking alone and dying later would be a
    false DEAD wherever skipping lives.
    """
    f, j = at
    taken = _walk(rest, f, j, pos + width)
    return taken if taken != STOP_DEAD else _walk(rest, f, j, pos)


def _item_step(arm: FlatArm, j: int, relax: int, text: str, pos: int) -> int:
    """One rest item at ``pos``: a matched width, or SKIP / KILL / MAYBE.

    A width is returned only for a literal or class item that occurs at most
    once and matches; the caller advances (mandatory) or branches (optional).
    """
    if arm.kinds[j] not in _TERMINAL:
        return _clone_step(arm.kinds[j], arm.payloads[j], text, pos)
    if arm.payloads[j] == "":
        return _SKIP  # an empty literal matches everywhere and consumes nothing
    width = _terminal_width(arm, j, text, pos)
    if width == 0:
        return _KILL if arm.los[j] > 0 and j != relax else _SKIP
    return width if arm.his[j] == 1 else _MAYBE


def _clone_step(kind: int, payload: Any, text: str, pos: int) -> int:
    """A clone, island or fail item: MAYBE when it could start here or carries no
    first-character set the walk reads; otherwise skipped as possibly empty."""
    if kind in (OP_ISLAND, OP_FAIL) or not isinstance(payload, FlatClone):
        return _MAYBE
    if payload.attempt is not None or payload.wide_selectors is not None:
        return _MAYBE
    return _MAYBE if clone_admits(payload, text[pos : pos + 1]) else _SKIP


def _terminal_width(arm: FlatArm, j: int, text: str, pos: int) -> int:
    """How many characters one occurrence of a literal or class item matches here."""
    payload = arm.payloads[j]
    if arm.kinds[j] in (OP_LIT, OP_LIT1):
        return len(payload) if text.startswith(payload, pos) else 0
    return 1 if pos < len(text) and admits(text[pos], *payload) else 0


_TERMINAL = frozenset((OP_LIT, OP_LIT1, OP_CC, OP_CC1))
"""The item kinds that consume text themselves, which the walk can check."""
