"""Comment-channel directives for IR-level metadata.

Convention: a line of the form `<line_comment> @<name> <args...>` in the
grammar source declares an IR directive. The flavour declares its
line-comment marker; this module parses any such file regardless of flavour.

Directives are extracted by scanning raw source text *before* the meta-grammar
parser sees it — Lark's `%ignore` rules strip comments from the AST. The two
channels are independent: the grammar parses normally, AND the directive
scanner sees the comments.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Directives:
    """IR-level directives extracted from source comments."""

    non_semantic: frozenset[str] = frozenset()
    start: str | None = None  # @start <rule_name>; None = "use first rule" fallback


def parse_directives(text: str, line_comment: str) -> Directives:
    """Extract IR directives from source comments.

    `line_comment` is the flavour's line-comment marker (e.g. '#' for GBNF,
    ';' for ABNF). Empty string disables directive parsing entirely.
    """
    if not line_comment:
        return Directives()

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

    return Directives(non_semantic=frozenset(non_semantic), start=start_rule)
