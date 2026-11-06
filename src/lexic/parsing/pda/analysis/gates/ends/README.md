# `lexic.parsing.pda.analysis.gates.ends` — where a run ends

A greedy loop over one character class meets the rest of the parse at the end
of its maximal run. When what follows needs part of that run before the
character that ends it, the loop must leave exactly that much — and only where
leaving that much is right whenever leaving more would be. Three modules carry
the decision from the grammar to the compiled gate:

- `leads.py` — the algebra: for each ending character, the fewest class
  characters a follower needs before it, and whether that prefix set is
  closed (FIXED, FULL, FREE) or MIXED, which is unknown and never stopped for.
  `RunLeads` solves it per class on demand, one strongly connected component
  at a time; `lead_windows` turns a lead into a k-window whose width is the
  grammar's own.
- `sites.py` — every place a loop's rule is referenced, up the chain the run
  can be crossed through, and the contexts each rule is reached in.
  `run_decides` is the cascade step `_stop_set` and the escape branch ask.
- `contexts.py` — what the clone compiler threads: the context at each arm's
  end, the part of each clone key a decided loop can see, and the run class
  and windows a decided loop compiles to.
