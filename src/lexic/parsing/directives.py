"""Comment-channel directives — the pre-lexical scan half of grammar parsing.

A pure text scanner: the comment-channel sibling of ``parse_grammar``'s Earley
half. With the directive *content* now living on :class:`~lexic.ir.nodes.IrAst`
(``start`` / ``non_semantic``), what remains here is parsing-side machinery, not
node algebra — hence its home in :mod:`lexic.parsing`.

A line of the form ``<line_comment> @<name> <args...>`` in grammar source
declares a directive:

- ``@start <rule>`` — override the start rule (default: first defined rule).
- ``@non-semantic <rule> ...`` — mark rules as structural noise; their refs
  get ``min=0`` in ``derive_specs`` and are filtered from ``semantic_dump``.

The scan is **pre-lexical**: it reads the raw source *before* the Earley
engine parses it, so comments feed this metadata channel without ever
becoming load-bearing grammar tokens (the self-grammars route comments to
noise, dropping them from the derivation). Keeping extraction out of the
parse is deliberate — in-parse capture would make comments structural and
block collapsing them below the chart. The extracted values are bound onto
the parsed :class:`~lexic.ir.nodes.IrAst`'s ``start`` / ``non_semantic``
payload by ``compile_grammar``.
"""

from __future__ import annotations


def parse_directives(text: str, line_comment: str) -> tuple[str | None, frozenset[str]]:
    """Extract ``(start, non_semantic)`` from source comments.

    :param text: Grammar source text.
    :param line_comment: The flavour's line-comment marker (e.g. ``#`` for
        GBNF, ``;`` for ABNF). An empty string disables directive parsing.
    :returns: ``(start, non_semantic)`` — ``start`` is the ``@start`` rule name
        or ``None`` (use the positional fallback); ``non_semantic`` is the set
        of ``@non-semantic`` rule names (empty if none).
    """
    if not line_comment:
        return None, frozenset()

    non_semantic: set[str] = set()
    start_rule: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(line_comment):
            continue
        rest = line[len(line_comment) :].lstrip()
        if not rest.startswith("@"):
            continue
        parts = rest[1:].split()
        if not parts:
            continue
        name, *args = parts
        if name == "non-semantic":
            non_semantic.update(args)
        elif name == "start" and args:
            start_rule = args[0]  # last @start wins on duplicates

    return start_rule, frozenset(non_semantic)
