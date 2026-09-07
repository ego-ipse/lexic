"""Each benchmark case's EXACT authored directive sets.

Benchmark data, not a heuristic and not an engine question. A row label must
denote the same directives in every revision, or the label is comparing two
different workloads — so the sets are written out here, per case, the way that
grammar's author would write them, and they are never rewritten in response to
what an engine happens to find eligible or fast.

A revision that cannot execute the unchanged row reports a refusal. It does not
earn a number by dropping a mark.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, inline_refs

DIRECTIVES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "abnf-meta": (
        (
            "binglyph",
            "cchar",
            "crlf",
            "csbody",
            "cvalpha",
            "decglyph",
            "decits",
            "hexdig",
            "namechar",
            "prose",
            "wsp",
        ),
        ("c-nl", "c-wsp", "sp", "wsp"),
    ),
    "announced": (("header", "line"), ("nl",)),
    "arithmetic": (("number",), ()),
    "backtrack": (("bind", "block"), ("nl",)),
    "csv": (("field",), ("nl",)),
    "gbnf-meta": (
        (
            "cc-esc-other",
            "cc-esc-short",
            "cchex2",
            "cchex4",
            "cchex8",
            "comment-line",
            "decits",
            "hex2",
            "hex4",
            "hex8",
            "lesc-other",
            "lesc-short",
            "rulename",
            "tail-comment",
            "tok-text",
        ),
        (),
    ),
    "json": (("colon", "comma", "number", "string"), ("ws",)),
    "lexruns": (("quoted",), ("nl",)),
    "markdown": (
        ("blank", "code", "emphasis", "fenceline", "link", "rule", "strong", "text"),
        ("nl",),
    ),
    "mixedends": (("event", "note", "span"), ("nl", "sp")),
    "nested": ((), ()),
    "vyx": (
        (
            "col-name",
            "field-list",
            "label-field",
            "nl-head",
            "nl-word",
            "performative",
            "pipe-unquoted",
            "quoted-char",
            "r-field",
            "ref",
            "ref-field",
            "s-field",
            "scope-path",
            "scope-word",
            "spread",
            "subtable-ref",
            "template-use",
            "unquoted",
            "vyx-file",
        ),
        (),
    ),
}
"""Each case's EXACT authored directive sets — benchmark data, not a heuristic.

A row label must denote the same directives in every revision, or the label is
comparing two different workloads. So the sets are written here, per case, the
way that grammar's author would write them, and they are never rewritten in
response to what an engine happens to find eligible or fast. A revision that
cannot execute the unchanged row reports a refusal; it does not earn a number
by dropping a mark.

Validated against the grammar by :func:`validate_directives` — the names must
be real rules, and a `@lexical` name must be one the grammar can actually
inline. That is a language question, and both trees answer it identically.
"""


def validate_directives(
    name: str, ast: IrAst, lexical: tuple[str, ...], non_semantic: tuple[str, ...]
) -> None:
    """Refuse a declaration naming a rule this grammar does not have.

    Validation is a LANGUAGE question — does the rule exist, can it be inlined —
    never an engine-speed one, so it gives the same answer in every revision.

    :raises ValueError: If a declared name is not a rule of ``ast``, or a
        `@lexical` name names a rule the grammar cannot inline.
    """
    names = {str(rule.name) for rule in ast.rules}
    unknown = sorted((set(lexical) | set(non_semantic)) - names)
    if unknown:
        raise ValueError(f"bench {name}: directives name unknown rules: {unknown}")
    for rule in lexical:
        try:
            inline_refs(ast, frozenset({rule}))
        except UnsupportedConstructError as exc:
            raise ValueError(
                f"bench {name}: @lexical {rule!r} is not inlinable: {exc}"
            ) from exc
