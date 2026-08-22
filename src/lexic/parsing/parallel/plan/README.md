# Split-plan shapes

What a repetition looks like BEFORE anything is parsed: the arm shape a
container presents, and where a cut may land in the text.

`envelope.py` reads a container arm as `head… unit item* tail…`, where every
item outside the repeated core can vanish — the first piece owns the head
fields, the last owns the tail, and a middle piece must leave both empty. It
also owns the noise-run vocabulary a separator may be (whitespace consumed
directly, opaque regions jumped whole) and the local admission match that
`stitch/safety.unit_boundary` licenses.

The cut normalization lives here because it is a fact about text, not models:
consecutive marks separated only by noise reach ONE unit start, and the
earliest is the cut, so inter-unit blank lines and comments stay in the
separator span where the lead reparses them. A later mark would strand that
run at the end of a piece, and an envelope tail absorbs one line ending rather
than a run of them.

`split.py` holds `SplitPlan` itself — what a split settles once per grammar and
reuses per document. It sits beside the analyses that produce it rather than in
the orchestrator that consumes it: the envelope reader, the routed-region
derivation and the plan record answer one question at different depths.
