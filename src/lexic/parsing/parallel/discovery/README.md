# Region discovery

Grammar-shape analysis, opaque-interior discovery, anchors, window scanning,
and the region records shared by parallel parsing plans. Region division keeps
the exact removed separator offsets alongside balanced, self-bracketed pieces;
stub and shell spans remain source-text facts here, while model routing lives
under `parallel/stitch`.

A selected region must provide one `MIN_CHUNK` share per requested worker.
The older two-chunk-only floor produced hundreds of sub-kilobyte tasks when a
large document contained many modest nested runs.

`shapes.py` owns the questions the other analyses ask a grammar's arms: what
an item spells, whether it repeats, what every arm carries at one end, and
which characters a derivation can emit — anywhere, or first. `parallel/stitch`
reads the same predicates so its proofs cannot diverge from the scan.

An opaque interior is a shape plus a certificate. `interior_shapes` reads the
shape — a literal spelling that opens and closes an arm, of any length, around
items that cannot spell its lead character (or a one-character delimiter whose
body escapes it). `interiors` adds the certificate the region sweep needs:
nothing reachable without descending into the region spells that character, so
pairing occurrences left to right is exact. A shape that fails it can still be
skipped where its position is known rather than searched for, which is what
`Scanner.walk` does and `parallel/stitch/safety.py` certifies.
