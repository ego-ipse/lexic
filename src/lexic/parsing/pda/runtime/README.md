# `parsing/pda/runtime` — the fused predictive model runtime

The runtime executes compiled `PdaTables` and builds a model during the walk.
Unlike Earley, it allocates no intermediate `ParseTree` on the deterministic
path. This folder imports the compiler and core layers and is the top of the
PDA dependency chain.

## Modules

- `kernel/` owns `PdaKernel`, `pda_model`, and the attempt/probe decisions.
- `admission.py` owns arm-admission tests and per-run scratch.
- `build.py` owns the frame layout and completed-frame model construction.
- `matchers.py` owns cursor-free terminal and quantifier matching.
- `islands.py` owns the cold windowed Earley escape and model splice.

There is one runtime product: models. Grammar-text reduction derives a pruned
model artefact in `lexic.compile` and uses this same model path before its thin
fold.
