"""Walking a compiled PDA program's clones — the one walk the tests share.

`all_clones` follows ``OP_GRP`` payloads only, so it does not reach a clone
named by a rule REFERENCE, and it is not the walk a test asking "what is in
this program" wants.

The subtlety worth having in one place: a dispatch clone keeps its targets
where its selection does. A lead-char one carries them in ``selectors``; one
selecting by window or post-noise peek carries them in its own selection and
leaves ``selectors`` EMPTY. A walk reading only ``selectors`` therefore stops
at the first wide dispatch and silently misses every clone beyond it — which
censused one of markdown's two converted clones and none of the targets under
either.
"""

from __future__ import annotations

from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.specialize import clone_arms


def walk_program_clones(start: FlatClone) -> dict[int, FlatClone]:
    """Every clone reachable from ``start``, once, by identity.

    :param start: The program's start clone.
    :returns: ``{id(clone): clone}`` for everything reachable.
    """
    seen: dict[int, FlatClone] = {}
    work: list[object] = [start]
    while work:
        clone = work.pop()
        if not isinstance(clone, FlatClone) or id(clone) in seen:
            continue
        seen[id(clone)] = clone
        wide = clone.wide_selectors
        if wide is not None:
            work.extend(wide.arms)
        for _chars, _negated, target in clone.selectors:
            work.append(target)
        work.append(clone.default)
        for arm in clone_arms(clone):
            work.extend(arm.payloads)
    return seen
