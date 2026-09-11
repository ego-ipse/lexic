"""What a build plan MEANS, spelled out once and independently of `src`.

Two suites ask the same question of a composed builder — the unit pin over
synthetic shapes and the corpus walk over every ground-truth grammar — and the
answer is only worth anything if it is derived here rather than read back out
of the module under test. One copy, because two spellings of "what the plan
says" would drift until the two suites were pinning different contracts while
both still looked like this one.

Deliberately NOT imported from `lexic.parsing.pda.compiler.program.lowering`:
that is the thing being checked. This is a second, independent reading of the
same plan entries.
"""

from __future__ import annotations

from collections.abc import Sequence

from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.opcodes import (
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
)


def plan_means(
    plan: Sequence[tuple[int, int, int, object]],
    text: str,
    ends: Sequence[int],
    sinks: Sequence[Sequence[object] | None] | None,
) -> list:
    """One value per plan entry, read straight off the entry's own fields.

    :param plan: The clone's ``(mode, item, lo, default)`` entries.
    :param text: The document the items were consumed from.
    :param ends: Item boundaries — ``(ends[i], ends[i + 1])`` is item ``i``.
    :param sinks: Per-item sub-model lists, or ``None`` for a frame that never
        descended.
    :returns: The field values, in the record's own order.
    :raises AssertionError: On a mode no composed build may carry — ``M_VALUE``
        names the rule's own extent, which is not any item's span.
    """
    values: list = []
    for mode, item, lo, default in plan:
        if mode == M_MODEL:
            sub = sinks[item] if sinks else None
            values.append(sub[0] if sub else default)
        elif mode == M_MODELS:
            values.append(tuple((sinks[item] if sinks else None) or ()))
        elif mode == M_SPAN:
            values.append(IrSpan(ends[item], ends[item + 1]))
        elif mode == M_CONST:
            values.append(default)
        elif mode in (M_TEXT, M_GTEXT):
            span = text[ends[item] : ends[item + 1]]
            values.append(span if (span or lo or mode == M_TEXT) else default)
        else:
            raise AssertionError(f"a composed build carries mode {mode!r}")
    return values
