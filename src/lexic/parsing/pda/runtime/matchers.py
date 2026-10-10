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
    vstr_model,
)
from lexic.parsing.pda.compiler.program.gating import (
    arm_expected,
    chase_dispatch,
    gate_take,
    select_arm,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_DISPATCH,
    GATE_STOP,
    OP_CC,
    OP_CC1,
    OP_CONSULT,
    OP_FAIL,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    OP_RUNPAT,
)
from lexic.parsing.pda.compiler.specs import LongestTake
from lexic.parsing.pda.core.errors import IslandEscape, PdaFail
from lexic.parsing.pda.runtime.admission import admits
from lexic.parsing.pda.runtime.build import Frame, InternMemo, build_vstr


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
    kind = runarm.kinds[0]
    if kind == OP_CONSULT:
        # The proved pattern, matched in place; a miss goes to the refusal.
        matched = runarm.payloads[0].match(text, pos)
        end = (
            matched.end()
            if matched is not None
            else consult_extent(text, clone, runarm, pos)
        )
    elif kind == OP_RUNPAT:
        # A run that cannot refuse: its first character decides an empty one
        # without the match call, the pattern takes any longer one whole.
        char = text[pos : pos + 1]
        gchars, gnegated = runarm.gate_data[0]
        taken = (char != "" and char not in gchars) if gnegated else char in gchars
        end = runarm.payloads[0].match(text, pos).end() if taken else pos
    elif kind == OP_CC:
        end = match_cc(text, runarm, 0, pos)
    else:
        end = match_lit(text, runarm, 0, pos)
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


def taken_end(text: str, take: LongestTake, arm: FlatArm, pos: int) -> int:
    """Where a checked take's match ends, when the match is its rule's answer.

    :raises IslandEscape: When the span holds a shorter end this reference
        could continue from, the next character could lengthen it, or a
        stealing rule's arm missed: none of those is the rule's answer here,
        so the rule's island is asked.
    :raises PdaFail: When a rule that cannot steal misses.
    """
    extent = take.extent
    if extent is not None:
        # The proved greedy match: the span the item-wise match takes, in one
        # C-level call.
        matched = extent.match(text, pos)
        if matched is None:
            raise PdaFail(f"no match of {take.island[0]!r} at {pos}", pos)
        end = matched.end()
    else:
        try:
            end = match_arm(text, arm, pos)
        except PdaFail:
            if not take.steals:
                raise
            # A loop may have taken what the rest of the arm needed: the miss
            # is no more the rule's answer than a match would be.
            raise IslandEscape(take.island, pos) from None
    if take.exit_at.search(text, pos + take.lead, end) or (
        take.extends_at is not None and take.extends_at.match(text, end)
    ):
        raise IslandEscape(take.island, pos)
    return end


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
        take = clone.longest
        if take is None:
            end = match_arm(text, varm, pos)
        else:
            end = taken_end(text, take, varm, pos)
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


REST_DEAD, REST_ASCEND, REST_ADMITS, REST_ADMITS_HARD = 0, 1, 2, 3
"""An arm-rest walk's verdicts: a mandatory non-admitting item kills the
stop side; a fully-skippable rest defers to the enclosing frame; an
admitting OPTIONAL item is same-arm chain viability (the greedy split);
an admitting MANDATORY item is the terminator-theft shape — a possessive
take would steal the char the arm's own continuation requires, so the
probes decide (gbnf-meta's rule terminator: ``ws | '\n' next-rule``)."""


def item_admits(arm: FlatArm, j: int, char: str) -> bool:
    """MAY item ``j`` consume ``char`` first — conservative for clone items."""
    if char == "":
        return False
    k = arm.kinds[j]
    payload = arm.payloads[j]
    if k in (OP_LIT, OP_LIT1):
        return payload[0] == char
    if k in (OP_CC, OP_CC1):
        chars, negated = payload
        return (char not in chars) if negated else char in chars
    if k in (OP_FAIL, OP_ISLAND):
        return True  # no FIRST at hand — MAY (a spurious probe is safe)
    return clone_admits(payload, char)


def clone_admits(clone: FlatClone, char: str) -> bool:
    """MAY ``clone`` consume ``char`` first (selector union; default ⇒ MAY)."""
    if clone.attempt is not None:
        return any(admits(char, c, n) for c, n, _re, _win, _sub in clone.attempt[1])
    if clone.wide_selectors is not None:
        return True  # windowed selection — MAY
    if clone.default is not None:
        return True  # a nullable default may defer admission further down
    for chars, negated, _arm in clone.selectors:
        if (char not in chars) if negated else char in chars:
            return True
    return False


def arm_rest_scan(arm: FlatArm, i: int, text: str, pos: int) -> tuple[int, bool]:
    """The rest-of-arm walk past item ``i``, at ``pos`` — ``(verdict,
    optional-admit seen)``.

    An optional admitting item does NOT settle the walk (both the chain and
    the terminator class can coexist — gbnf's ``bar-arm*`` admits the newline
    the rule's MANDATORY ``nl`` also wants, and the hard class must win); a
    mandatory item settles it either way (admits → the terminator class;
    refuses → the char cannot flow past, the stop side is dead).

    A run of exactly-once literals is read whole, at ``pos``: the stop side
    must spell all of it there, so ``" " ">"`` closing a body admits a space
    only where ``" >"`` follows, not at every space inside the body.
    """
    char = text[pos : pos + 1]
    kinds, los, n = arm.kinds, arm.los, arm.n
    opt = False
    for j in range(i + 1, n):
        if kinds[j] == OP_LIT1:  # the first literal in place; a run past it rarely
            lit = arm.payloads[j]
            admitted = text.startswith(lit, pos) and (
                j + 1 == n
                or kinds[j + 1] != OP_LIT1
                or spelled_run(arm, j + 1, text, pos + len(lit))[1] >= 0
            )
        else:
            admitted = item_admits(arm, j, char)
        if admitted:
            if los[j] > 0:
                return REST_ADMITS_HARD, opt
            opt = True
        elif los[j] > 0:
            return REST_DEAD, opt
    return REST_ASCEND, opt


def spelled_run(arm: FlatArm, j: int, text: str, pos: int) -> tuple[int, int]:
    """The exactly-once literals from item ``j`` on, spelled at ``pos`` one
    after another: ``(the item after the run, the position after it)``, or a
    position of ``-1`` at the first refusal."""
    kinds, payloads, n = arm.kinds, arm.payloads, arm.n
    while j < n and kinds[j] == OP_LIT1:
        literal = payloads[j]
        if not text.startswith(literal, pos):
            return j, -1
        pos += len(literal)
        j += 1
    return j, pos


_DEAD, _OPEN, _LIVE, _ON = 0, 1, 2, 3
"""What a stop side's walk against the text proves: no continuation it
derives begins with the text, one might, or one spends the document — and,
for one arm's rest, that it was spelled through and the walk goes on."""

type _Link = tuple[FlatArm, int, int]
"""One frame of a stop side: its arm, where its rest starts, and the item it is
suspended in when that may iterate again, else ``-1``."""


def stop_side_dead(
    stack: list[Frame], arm: FlatArm, i: int, text: str, pos: int
) -> bool:
    """Whether stopping the loop at item ``i`` of the top frame provably dies.

    The stop side's continuation is read against the TEXT, past the one
    character :func:`arm_rest_scan` classifies: the rest of the top arm, then
    each enclosing frame's rest from the item it is suspended in. A literal or
    a class that occurs at most once is matched and stepped over, an optional
    one that matches both ways; a mandatory one that cannot match kills. A
    repetition, a reference that could start here, an island and a further
    iteration of an enclosing item stop the walk undecided; a reference that
    cannot start here is read as deriving empty. Past the root the document
    must be spent. So ``True`` is a proof that no text any stop continuation
    derives begins at ``pos`` — for a run whose text and root are the
    document's (:meth:`~...admission.RunScope.whole`).
    """
    chain: list[_Link] = [(arm, i + 1, -1)]
    for frame in stack[-2::-1]:
        at = frame.suspended()
        chain.append((frame.arm, at + 1, at if frame.arm.his[at] != 1 else -1))
    return _walk(chain, 0, i + 1, text, pos) == _DEAD


def _walk(chain: list[_Link], f: int, j: int, text: str, pos: int) -> int:
    """The stop side from item ``j`` of link ``f`` at ``pos``."""
    while True:
        verdict, pos = _arm_walk(chain, f, j, text, pos)
        if verdict != _ON:
            return verdict
        f += 1
        if f == len(chain):
            return _LIVE if pos == len(text) else _DEAD
        arm, j, again = chain[f]
        if again != -1 and item_admits(arm, again, text[pos : pos + 1]):
            return _OPEN


def _arm_walk(
    chain: list[_Link], f: int, j: int, text: str, pos: int
) -> tuple[int, int]:
    """Link ``f``'s rest from item ``j``: ``(_ON, where it ends)`` once spelled
    through, else the walk's verdict."""
    arm = chain[f][0]
    while j < arm.n:
        if arm.kinds[j] == OP_LIT1:
            j, pos = spelled_run(arm, j, text, pos)
            if pos < 0:
                return _DEAD, pos
            continue
        width = _terminal_width(arm, j, text, pos)
        if width == -2:  # not a terminal: a reference, island or fail
            if item_admits(arm, j, text[pos : pos + 1]):
                return _OPEN, pos
        elif width < 0:
            if arm.los[j] > 0:
                return _DEAD, pos
        elif arm.his[j] != 1:
            return _OPEN, pos  # a run: where it ends is not the walk's to know
        elif arm.los[j] == 0 and width:
            taken = _walk(chain, f, j + 1, text, pos + width)
            if taken == _DEAD:
                taken = _walk(chain, f, j + 1, text, pos)
            return taken, pos
        else:
            pos += width
        j += 1
    return _ON, pos


def _terminal_width(arm: FlatArm, j: int, text: str, pos: int) -> int:
    """How much one occurrence of literal or class item ``j`` matches at
    ``pos``: its width, ``-1`` when it cannot, ``-2`` when it is no terminal."""
    kind, payload = arm.kinds[j], arm.payloads[j]
    if kind in (OP_LIT, OP_LIT1):
        return len(payload) if text.startswith(payload, pos) else -1
    if kind in (OP_CC, OP_CC1):
        return 1 if admits(text[pos : pos + 1], *payload) else -1
    return -2
