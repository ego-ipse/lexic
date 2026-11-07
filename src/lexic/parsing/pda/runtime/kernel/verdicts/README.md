# `parsing/pda/runtime/kernel/verdicts` — boundary decisions

A both-viable boundary in the kernel's attempt group (`kernel/decisions.py`) is
settled here, by four host classes the kernel inherits in turn: `Verdicts`
(`verdicts.py`), `LiveSet` (`liveset.py`), `Sides` (`sides.py`) and `Floors`
(`floors.py`). All are method groups of the one kernel cursor, split by
responsibility.

## `verdicts.py`

`Verdicts` answers a both-viable boundary — take, stop or fork — by the way its
live set keeps, and inside a set's reading raises the split instead. Two
readings that meet with different values are ranked here as the gated engine
ranks them, by the decider's slots at the first step whose carving differs. An
island whose reference may follow several of its completions, and an
attempt's arms that end apart, are settled the same way, one way per end.

## `liveset.py`

`LiveSet` carries a boundary's ways forward as a flat set of readings: a
reading that dies is pruned, one that meets a boundary splits, and two that
meet merge — equal values keep the take, different ones are ranked at the
split where they parted, a tie forks. Readings step in sync, the one ahead
first at a loop boundary, and the set is bounded; past a bound it forks by
name.

## `sides.py`

`Sides` builds a side — a structural copy of the live stack with one decision
taken — and drives it one copied frame at a time, recording where each frame
completes (its ledger, which the rank reads) and settling each attempt sub-run
it stands inside as the sub-run's caller would, recovered from the stack.

## `floors.py`

`Floors` drives a stack down to each sub-run left on it with no Python call
waiting — one a side stands inside, or one the live parse suspended past its
in-place depth — and settles it there as its caller would: the iteration's
commit or close, the attempt's next entry, the audit with its rivals, and on a
miss the island steal and the claim of an island's ends.
