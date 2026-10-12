# `parsing/pda/runtime/kernel` — the fused model driver

The kernel is one cursor split by responsibility: `kernel.py` holds
`PdaKernel`, the paid loop, island splice, and public `pda_model` entry;
`decisions.py` holds the attempt/probe method group it inherits;
`verdicts.py` holds the boundary verdict that group inherits in turn;
`sides.py` holds the sides that verdict is asked on; and
`attempt_inline.py` holds frame-less loops for attempt-aware value strings.

## `kernel.py`

The kernel walks the flat `PdaProgram`: integer opcodes, pre-resolved character
sets, and direct `FlatClone` references. Rule, group, and loop descent use an
explicit frame stack, so nesting depth never reaches Python recursion. The
program is immutable and shared; input, cursor, frames, and caches are per run.

Arm selection proceeds through dispatch, bounded lookahead/noise gates,
structured scan gates, leaf specialisation, and FIRST selection. An unlicensed
choice raises `PdaFail`; the model product then completes through Earley.
Island references likewise run a windowed Earley sub-parse and splice the
folded model into the live frame.

## `decisions.py`

`Attempting` provides ordered speculative entries and watermarked sub-runs. An
attempted iteration whose boundary is both viable asks the verdict. An
undecidable result is `ProbeFork`, which returns control to the ordinary Earley
completion.

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

## `attempt_inline.py`

`AttemptInlineMixin` executes `OP_AVSTR` and `OP_AVDISP` without constructing a
clone frame per iteration. The attempt gate remains the decision owner: only
FIRST-only iterations stay on the fast path, while soft-continuation overlaps
return to `Attempting` for the same fork audit as the generic loop.
