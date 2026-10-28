# `parsing/pda/runtime/kernel/verdicts` — boundary decisions

A both-viable boundary in the kernel's attempt group (`kernel/decisions.py`) is
settled here: `verdicts.py` holds `Verdicts`, the host class that group
inherits, and `sides.py` holds `Sides`, the host class `Verdicts` inherits in
turn. Both are method groups of the one kernel cursor, split by responsibility.

## `verdicts.py`

`Verdicts` decides a both-viable boundary — take, stop or fork — on two sides
advanced in lockstep until they converge or run to end of input. Equal values
take; differing values are ranked as the gated engine ranks them, by the
decider's slots at the first step whose carving differs. An island whose
reference may follow several of its completions is settled the same way, one
side per completion.

## `sides.py`

`Sides` builds a side — a structural copy of the live stack with one decision
taken — and drives it one copied frame at a time, recording where each frame
completes (its ledger, which the rank reads) and settling each attempt sub-run
it stands inside as the sub-run's caller would, recovered from the stack.
