# `lexic.parsing.pda.analysis.gates` — one analysis per decision

A predictive parser has to settle every choice point before it runs. Each module
here answers one kind: `kwindow` decides by bounded lookahead (FIRST_k over
char sets), `noise` by attribution (which rules are structural), `structured` by
folding-aware loop gates, and `leftrec` by refusing outright — left recursion is
the case predictive descent cannot have.

They report into `taxonomy`, which is the classified result `analysis` hands the
compiler.
