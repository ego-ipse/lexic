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

from lexic.parsing.pda.compiler.flatten import (
    GATE_STOP,
    OP_CC1,
    OP_LIT,
    OP_LIT1,
    FlatArm,
    FlatClone,
    gate_take,
)
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import build_vstr


def select_arm(clone: FlatClone, char: str, pos: int) -> FlatArm:
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
            raise PdaFail(f"expected {lit!r} at {pos}")
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
                raise PdaFail(f"expected {lit!r} at {pos}")
            pos += llen
            count += 1
        return pos
    while (hi < 0 or count < hi) and gate_take(text, pos, gk, gate):
        if not text.startswith(lit, pos):
            raise PdaFail(f"expected {lit!r} at {pos}")
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
            raise PdaFail(f"char class miss at {pos}")
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
                raise PdaFail(f"expected {lit!r} at {pos}")
            pos += len(lit)
        elif k == OP_CC1:
            chars, negated = arm.payloads[j]
            char = text[pos : pos + 1]
            if (char == "" or char in chars) if negated else char not in chars:
                raise PdaFail(f"char class miss at {pos}")
            pos += 1
        elif k == OP_LIT:
            pos = match_lit(text, arm, j, pos)
        else:
            pos = match_cc(text, arm, j, pos)
    return pos


def vstr_once(
    text: str, intern: dict[Any, object], clone: FlatClone, sink: list[Any], pos: int
) -> int:
    """One ``value_str`` iteration — select, match, slice, build, append.

    The single-item arm (the common case) skips both the item loop and the
    slice; a multi-item arm (a literal prefix then a char class, say) runs
    :func:`match_arm` over the whole arm and slices the combined span.

    :raises PdaFail: On a terminal mismatch or no viable arm.
    """
    char = text[pos : pos + 1]
    varm = select_arm(clone, char, pos)
    if varm.n != 1:  # the rare multi-item arm — cold, off the hot path
        end = match_arm(text, varm, pos)
        sink.append(build_vstr(clone, text[pos:end], intern))
        return end
    kj = varm.kinds[0]  # the common single-item arm — no item loop, no slice
    if kj == OP_CC1:
        chars, negated = varm.payloads[0]
        if (char == "" or char in chars) if negated else char not in chars:
            raise PdaFail(f"char class miss at {pos}")
        sink.append(build_vstr(clone, char, intern))
        return pos + 1
    if kj == OP_LIT1:
        lit = varm.payloads[0]
        if not text.startswith(lit, pos):
            raise PdaFail(f"expected {lit!r} at {pos}")
        sink.append(build_vstr(clone, lit, intern))
        return pos + len(lit)
    end = (
        match_lit(text, varm, 0, pos) if kj == OP_LIT else match_cc(text, varm, 0, pos)
    )
    sink.append(build_vstr(clone, text[pos:end], intern))
    return end
