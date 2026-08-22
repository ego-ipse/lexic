# Parallel parsing

Region discovery, worker planning, model replicas, and orchestration for the
single model parse path. Start-rule repetitions and nested bracketed regions
enter through the same `split_model` seam; the latter parse balanced re-rooted
pieces, restore their separator tails, and replace only the owning items node
in one small shell model. Reduction-specific products do not belong here: a
reducer-derived artefact benefits by using this same model path.

Derived artefacts retain their source grammar as a read-only split-analysis
view. Discovery uses that view for opaque interiors and structural characters,
while workers still parse the derived grammar and build its exact model
classes. This matters when recognition-only elision removes quote/escape
wrappers: braces inside strings must never become candidate regions.

Ownership is non-overlapping, but outermost is not automatically best. When a
nested region offers the useful cuts, it is delegated and its enclosing parse
uses a distinct stand-in for that known subtree; the completed items node is
reattached afterward. The larger parse must not repeat delegated work merely
because it contains it. Separator joints parse shallow grammatical witnesses
carrying the exact boundary noise, then attach the already parsed forward head.

One `WorkPool` owns all parallel phases of a split attempt, so a start-rule
scan and its piece parse reuse the same executor. The public `ParsePool` binds
one callable for repeated document maps. Both admit a bounded sliding window
from completion order (not result order) to keep uneven workloads scheduled,
wait out a failed phase before reuse, and close deterministically through their
context-manager lifetime.

`envelope.py` reads the two shapes a plain repetition is not. A container arm
may wrap its repeated core in optional head and tail items — the first piece
owns the head, the last owns the tail, and every middle piece must leave both
empty. A separator may be a noise RUN rather than one character, so a cut
lands on the mark and extends forward over whitespace and whole opaque regions
before the next unit begins.

Where the unit itself can emit the mark — a rule that legitimately spans lines
— extending is not exactness. `stitch/safety.unit_boundary` proves the landing
site instead: past the noise run a unit ANNOUNCES itself with a mandatory
guarded prefix, and a refutation walk shows no position inside a unit can spell
that prefix over head and noise characters alone. Consecutive marks separated
only by noise reach one unit start, and the earliest is the cut, so inter-unit
blank lines and comments stay in the separator span.

There is no privileged grammar here. JSON is a differential and benchmark
witness, not a parser mode or policy input. The measured split floor remains
2 KiB per worker: a regression above that floor is duplicated work to remove,
not a reason to raise the floor or silently decline MT.
