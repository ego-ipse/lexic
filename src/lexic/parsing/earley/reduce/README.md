# `lexic.parsing.earley.reduce` — where meaning attaches

The forest is flavour-neutral: it records which derivations exist, not what any
of them means. This package is the seam where a flavour's reducer turns one
derivation into a value.

- `policy` — how a packed (ambiguous) family is resolved, and what a
  reduction is allowed to assume about the derivation it was handed.
- `reducer` — the general walk: a forest node, its arm's action, the value.
- `fused` — the same reduction with the tree elided, driven straight off the
  link table. Same result, one allocation tier cheaper; `reducer` stays the
  readable definition it is checked against.

The reduction's codomain is what decides a compiled artefact's target — there
is no flag for that, here or anywhere.
