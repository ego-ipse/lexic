# `pda/compiler/descent` — the grammar the predictive descent runs

`compile_clones` does not cut its clones against the lifted grammar as it
stands, but against the PDA's own rewrite of it: `descent_grammar`. Each
rewrite here preserves the language and the model, and each applies to the
predictive side alone. Earley parses the authored grammar, and its model is the
reference; the canonical grammar is the grammar's own normal form and does not
change for speed.

- `leftrec/` — the left-recursion fold: `A ::= A β | γ` parsed as `(γ)(β)*`,
  and the iterations built back through the rule's own arms. Its README
  carries the detail.
- `fusion.py` — a text-only rule's adjacent items of one class, where the run
  loops, as one item with summed bounds. The rule's value is its matched text,
  so where one run ends inside it is read by nothing, and every spelling of one
  class run compiles to one program.

The analysis runs over what comes out, so its stored decisions are keyed by
the items the descent actually runs.
