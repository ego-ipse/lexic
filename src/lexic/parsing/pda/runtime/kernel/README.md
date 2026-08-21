# `parsing/pda/runtime/kernel` — the fused model driver

The kernel is one cursor split by responsibility: `kernel.py` holds
`PdaKernel`, the paid loop, island splice, and public `pda_model` entry;
`decisions.py` holds the attempt/probe method group it inherits.

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

`Attempting` provides ordered speculative entries, watermarked sub-runs, and
two-sided boundary probes on structural stack copies. A probe compares
completed model values. An undecidable result is `ProbeFork`, which returns
control to the ordinary Earley completion.
