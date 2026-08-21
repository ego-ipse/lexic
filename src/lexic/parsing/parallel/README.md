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

Ownership is non-overlapping. A divided outer region owns its descendants; if
a nested region is divided instead, its enclosing document parses a distinct
one-item stub and receives the completed items node afterward. Only bounded
separator joints are reparsed to recover their exact forward ownership.
