# `lexic.parsing.pda.analysis.extend` — the charset fixpoints

Two questions about a grammar's strings, each answered as a fixpoint over
every rule, grown from empty and bounded by ALPHABET:

- **EXTEND** (`lengthen.py`) — every character at which a complete match can go
  on and still be a match. The stop-set settle, the island steal, the
  left-recursion fold and the speculation licence read it, through
  `rule_extensions`, built once per analysis and kept beside the FOLLOW windows.
- **NON_INITIAL** (`inner.py`) — every character some string carries past its
  first position. The folded-run split reads it: a character outside it, met
  past a string's start, begins one.

Where EXTEND's readings part inside a run (`C*` over one character set), the
ALPHABET fallback is too coarse: R3 (`lengthen.py`) takes the rest's EXTEND
there instead, when the shift is confined to the run. The structural facts it
needs (what a run is, what leads past one, when two arms part on one) are read
off the grammar alone in `runs.py`; its working answers ride `Confinement`.

Both ride `Extensions` (`maps.py`) through the dispatch's `nc` channel, and
share its atom bodies: a single string extends by `nothing`, a token atom by
`anything`, and a rule reference reads its target's current set
(`found_ruleref`). Each over-approximates, so a caller can only ever prove too
little with it.
