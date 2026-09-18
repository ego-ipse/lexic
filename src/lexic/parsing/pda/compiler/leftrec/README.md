# `pda/compiler/leftrec` — the left-recursion fold

A rule the predictive descent cannot run, rewritten into one it can, without
changing what it parses or what it builds.

`A ::= A β | γ` is parsed as `(γ)(β)*` — the classical rewrite, language
preserving — and its value is built by folding the iterations back through the
rule's OWN per-arm routine, so the model comes out left-nested exactly as the
grammar's arms build it. The two halves live together because neither is sound
alone: the rewrite without the fold changes the model, and the fold without the
rewrite has nothing to iterate.

A rule whose shape the fold cannot take is left alone and still islands. The
refusals divide by which half cannot proceed. `shape.py` declines what the
rewrite cannot express — a `β` that can vanish, whose loop would spin without
consuming. `build.py` declines what the fold cannot rebuild — an iteration
capturing nothing, whose depth is then unrecoverable from the sink. Each site
states its own reason at the return that carries it.
