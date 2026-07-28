"""Leo right-recursion — the deterministic-chain analysis and its deferred rebuild.

Candidate ``lexic/parsing/earley/kernel/leo.py``. Leo's two halves are both
pure functions of the chart state and the compiled tables, so they take
:class:`~lexic.parsing.earley.kernel.loop.state.KernelState` and
:class:`~lexic.parsing.earley.kernel.tables.records.ParserTables` directly and
never the kernel cursor:

- **climbing** — :func:`leo_sole` / :func:`leo_resolve` answer *which* item a
  deterministic right-recursion jumps to, reading ``waiting`` and memoising per
  closed column in ``leo``;
- **rebuilding** — :func:`expand_leo` / :func:`expand_chain` replay the
  provenance a jump skipped, filing it back into ``links``.

Only the decision to jump is the driver's: ``Kernel._try_leo`` keeps the chart
write (it inserts the top item) and calls the climb here.
"""

from __future__ import annotations

from lexic.parsing.earley.kernel.loop.state import KernelState, KLink
from lexic.parsing.earley.kernel.tables.records import ParserTables


def leo_sole(st: KernelState, tables: ParserTables, col: int, rid: int) -> int:
    """The deterministic last-symbol waiter for ``rid`` in ``col``, else -1."""
    wl = st.waiting[col].get(rid)
    if wl is None or len(wl) != 1:
        return -1
    sole = wl[0]
    if tables.codes.next_sym[(sole >> tables.packing.bits) + 1] == 0:
        return sole
    return -1


def leo_resolve(
    st: KernelState, tables: ParserTables, cur: int, col: int, rid: int
) -> int:
    """Leo's transitive (topmost) item for completing ``rid`` at ``col``.

    Climbs the deterministic chain, memoising per closed column (the current
    column ``cur`` is recomputed — its waiters may still grow). A **same-column**
    (empty-span) step stops the climb: those steps are cycle- and
    ambiguity-prone and carry no asymptotic benefit (Leo's payoff is
    cross-column right recursion), so the normal completer — which records every
    family — handles them. Columns then strictly decrease up the climb, so
    termination needs no cycle guard.

    :returns: The packed topmost item, or ``-1``.
    """
    leo_col = st.leo[col]
    if col != cur:
        memo = leo_col.get(rid)
        if memo is not None:
            return memo
    pk = tables.packing
    found = leo_sole(st, tables, col, rid)
    if found < 0 or (found & pk.mask) == col:
        result = -1  # no sole waiter, or an empty-span step — no jump
    else:
        c = tables.codes
        parent = leo_resolve(
            st, tables, cur, found & pk.mask, c.arm_rule[c.code_arm[found >> pk.bits]]
        )
        result = parent if parent >= 0 else found + pk.advance
    if col != cur:
        leo_col[rid] = result
    return result


def expand_leo(st: KernelState, tables: ParserTables, key: int) -> None:
    """Rebuild the deferred right-recursion chain under Leo top ``key``.

    Files each skipped completion's family into :attr:`KernelState.links`
    bottom-up, O(chain), idempotent (families dedup).

    Invariant — **expand on presence, never gate on** ``links``. A Leo top can
    carry *mixed provenance*: some of its families recorded by the normal
    completer (a later completion of the same rule found ≥2 waiters), others
    deferred here. ``key in links`` therefore does NOT mean the deferred chains
    are represented — a caller that skips expansion on that test drops the
    deferred derivations (the L4 embedded-ambiguity undercount). Idempotence
    makes the unconditional call safe.
    """
    pk = tables.packing
    top = key >> pk.bits
    end = key & pk.mask
    for bottom in st.leo_links[key]:
        expand_chain(st, tables, top, end, bottom)


def expand_chain(
    st: KernelState, tables: ParserTables, top: int, end: int, bottom: KLink
) -> None:
    """Rebuild one deferred chain from its bottom family up to ``top``."""
    c = tables.codes
    packing = tables.packing
    waiter, waiter_end, child = bottom
    while True:
        adv = waiter + packing.advance
        k = (adv << packing.bits) | end
        entry: KLink = (waiter, waiter_end, child)
        bucket = st.links.get(k)
        if bucket is None:
            st.links[k] = [entry]
        elif entry not in bucket:
            bucket.append(entry)
        if adv == top:
            return
        # ``adv`` completes its rule over waiter_origin..end; the lone item
        # awaiting it there is the next chain link (deterministic by
        # construction — that is why Leo fired).
        child = k
        waiter_end = waiter & packing.mask
        rid = c.arm_rule[c.code_arm[waiter >> packing.bits]]
        waiter = st.waiting[waiter_end][rid][0]
