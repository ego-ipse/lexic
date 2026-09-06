# Compilation output

Presentation views, span templates, cross-grammar transpilation, and the shared
Python module writer. These consume compiled artefacts but do not define the
compilation pipeline.

`SPAN_SYMBOLS` names the span surface's two transforms by the rules completing
through them. It exists because the engines take a product and a surface that
cannot say what its rules do cannot be parsed at all. It goes with templating:
the span parse is a separate architecture a target schema replaces.
