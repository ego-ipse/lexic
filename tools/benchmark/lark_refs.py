"""Native Lark reference grammars for every sample in ``compare_bench``.

Each string the engine parses gets a faithful Lark grammar here so Lark has a
number for every row, written **the native Lark way** — whitespace skipped by
the contextual lexer via ``%ignore`` (not the engine's threaded explicit ``ws``
rules). Every grammar is tried under **both** of Lark's parsers, so each is a
column of its own:

- **lark-lalr** — Lark's fast native path (LALR + contextual lexer). Included
  only where the grammar actually builds *and* parses the corpus under LALR;
  where it does not (the two meta-grammars, whose rulename↔ruleref overlap needs
  unbounded lookahead — the same reason the engine compiles a probe gate) the
  column is left empty and the failure is reported, never silently swapped for
  Earley.
- **lark-earley** — Lark's general parser; always available.

Lark is timed at its native output — ``parser.parse(text)`` → a Lark ``Tree`` —
never a second-pass transform to ``IrAst``, which would burden it with work its
native pipeline does not do. Whitespace-significant chess and the
declaration-shaped C corpus are encoded to the structure their corpora
exercise; both do comparable per-token parsing work to the engine on the same
input.

The ABNF meta-grammar is the one recovered in ``parse_bench`` — reused, not
duplicated.
"""

from __future__ import annotations

from types import ModuleType
from typing import Callable

from tools.benchmark.parse_bench import META_GRAMMAR as ABNF_META

# ── instance grammars (LALR) ───────────────────────────────────────────────

JSON_LARK = r"""
start: value
?value: object | array | STRING | NUMBER | TRUE | FALSE | NULL
object: "{" [pair ("," pair)*] "}"
pair: STRING ":" value
array: "[" [value ("," value)*] "]"
TRUE: "true"
FALSE: "false"
NULL: "null"
STRING: /"(\\(["\\\/bfnrt]|u[0-9A-Fa-f]{4})|[^"\\\x00-\x1f])*"/
NUMBER: /-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/
%ignore /[ \t\n\r]+/
"""

ARITHMETIC_LARK = r"""
start: line+
line: expr "=" term _NL
expr: term (OP term)*
term: IDENT | NUM | "(" expr ")"
OP: /[-+*\/]/
IDENT: /[a-z][a-z0-9_]*/
NUM: /[0-9]+/
_NL: /\n/
%ignore /[ \t]+/
"""

CHESS_LARK = r"""
start: turn+
turn: NUM ". " MOVE " " MOVE _NL
MOVE: /([NBKQR][a-h]?[1-8]?x?[a-h][1-8]|([a-h]x)?[a-h][1-8](=[NBKQR])?|O-O(-O)?)[+#]?/
NUM: /[1-9][0-9]?/
_NL: /\n/
"""

C_LARK = r"""
start: decl+
decl: dtype IDENT "(" [param ("," param)*] ")" "{" stmt* "}"
param: dtype IDENT
dtype: "int" | "float" | "char"
stmt: dtype IDENT "=" expr ";" | IDENT "=" expr ";" | "return" expr ";"
expr: term (("+"|"-") term)*
term: factor (("*"|"/") factor)*
factor: IDENT | NUMBER | "(" expr ")"
IDENT: /[a-zA-Z_][a-zA-Z_0-9]*/
NUMBER: /[0-9]+/
%ignore /[ \t\n]+/
"""

# ── GBNF meta-grammar (Earley — rulename/ruleref overlap) ───────────────────

GBNF_META = r"""
start: rule+
rule: NAME "::=" alternation
alternation: sequence ("|" sequence)*
sequence: item*
item: element QUANT?
element: LITERAL | CHARCLASS | NAME | "(" alternation ")"
NAME: /[a-zA-Z][a-zA-Z0-9_-]*/
LITERAL: /"(\\.|[^"\\])*"/
CHARCLASS: /\[(\\.|[^\]\\])*\]/
QUANT: /[*+?]/
COMMENT: /#[^\n]*/
%ignore /[ \t\r\n]+/
%ignore COMMENT
"""

# ── the registry: sample key → grammar (parser-agnostic) ────────────────────

LARK_GRAMMARS: dict[str, str] = {
    "abnf": ABNF_META,
    "gbnf": GBNF_META,
    "arithmetic.gbnf": ARITHMETIC_LARK,
    "c.gbnf": C_LARK,
    "chess.gbnf": CHESS_LARK,
    "json.gbnf": JSON_LARK,
}


# ── same-grammar mirrors: the engine's OWN grammar, in Lark ────────────────
#
# The grammars above are written the native Lark way, which answers "how fast is
# each tool idiomatically". It does NOT answer "how fast is each engine", and the
# two were conflated for an entire effort: `json.gbnf` spells `digit` and `char`
# as RULES and threads `ws` explicitly, so it asks for a typed model per
# character, while `JSON_LARK` asks for one token per number or string.
#
# A mirror asks Lark the SAME question. Where a tool cannot express the grammar
# at all — LALR cannot take this one — that is a RESULT to print, not a reason to
# substitute an easier grammar and keep the row.

JSON_LARK_MIRROR = r"""
start: ws value ws
value: object | array | string | number | "true" | "false" | "null"
object: "{" ws pairs? ws "}"
pairs: pair (ws "," ws pair)*
pair: string ws ":" ws value
array: "[" ws items? ws "]"
items: value (ws "," ws value)*
string: "\"" char* "\""
char: NOSPECIAL | "\\" ESCCHAR | "\\u" HEX HEX HEX HEX
number: MINUS? digit+ frac? expo?
frac: "." digit+
expo: E SIGN? digit+
digit: DIGIT
ws: WSCHAR*
NOSPECIAL: /[^"\\]/
ESCCHAR: /["\\\/bfnrt]/
HEX: /[0-9a-fA-F]/
DIGIT: /[0-9]/
MINUS: "-"
E: /[eE]/
SIGN: /[+-]/
WSCHAR: /[ \t\n\r]/
"""
"""`json.gbnf`'s own structure in Lark: per-char rules, explicit threaded `ws`,
no `%ignore`. Measured: LALR REFUSES to parse a json corpus with it, and Earley
takes ~80 µs/char against the engine's PDA at ~3 — so the engine is ~26x faster
than Lark's general parser on the grammar lexic is actually handed, and Lark's
fast parser cannot take it. That is the like-for-like comparison."""

LARK_MIRRORS: dict[str, str] = {"json.gbnf": JSON_LARK_MIRROR}
"""Registry key → the same-grammar mirror, where one has been written."""


def lark_variants(
    lark_mod: ModuleType, key: str, probe: str
) -> tuple[dict[str, Callable[[str], object]], str]:
    """Both native Lark parse callables for one sample, LALR-viability probed.

    Builds the Earley parser (always available) and the LALR parser. LALR can
    build with conflicts silently resolved and then fail at parse, so its
    ``parse`` is included only after it successfully parses ``probe`` — never
    swapped for Earley on failure; the failure is returned as a note instead.

    :param lark_mod: The imported ``lark`` module.
    :param key: A registry key (``abnf`` / ``gbnf`` / a ``.gbnf`` stem).
    :param probe: A representative input (the corpus) LALR must parse to count.
    :returns: ``(name -> parse, note)`` — ``name`` is ``lark-lalr`` /
        ``lark-earley``; ``note`` explains a missing ``lark-lalr`` (``""`` when
        LALR is viable or the key has no grammar).
    """
    grammar = LARK_GRAMMARS.get(key)
    if grammar is None:
        return {}, ""
    variants: dict[str, Callable[[str], object]] = {}
    note = ""
    try:
        lalr = lark_mod.Lark(grammar, parser="lalr")
        lalr.parse(probe)
        variants["lark-lalr"] = lalr.parse
    except lark_mod.exceptions.LarkError as exc:
        note = f"lalr N/A ({type(exc).__name__})"
    variants["lark-earley"] = lark_mod.Lark(grammar, parser="earley").parse
    return variants, note


def lark_mirror_variants(
    lark_mod: ModuleType, key: str, probe: str
) -> tuple[dict[str, Callable[[str], object]], str]:
    """Lark on the ENGINE's grammar — the like-for-like columns, when one exists.

    Same contract as :func:`lark_variants`, over :data:`LARK_MIRRORS` instead of
    the native grammars, and named ``lark-lalr-same`` / ``lark-earley-same`` so a
    reader cannot mistake one question for the other.

    A tool that cannot express the grammar is reported, never substituted: LALR
    refuses `json.gbnf`'s shape outright, and that refusal IS the finding. Only
    Lark's OWN failures are caught (`LarkError` covers both `GrammarError` at
    build and `UnexpectedToken` at parse) — anything else is our bug, not a
    tool declining a grammar, and must surface.

    :param lark_mod: The imported ``lark`` module.
    :param key: A registry key.
    :param probe: A representative input each parser must handle to count.
    :returns: ``(name -> parse, note)``; empty when no mirror is written yet.
    """
    grammar = LARK_MIRRORS.get(key)
    if grammar is None:
        return {}, ""
    out: dict[str, Callable[[str], object]] = {}
    notes: list[str] = []
    for label, parser in (("lark-earley-same", "earley"), ("lark-lalr-same", "lalr")):
        try:
            built = lark_mod.Lark(grammar, parser=parser)
            built.parse(probe)
        except lark_mod.exceptions.LarkError as exc:  # refusing IS the result
            notes.append(f"{label}: {type(exc).__name__}")
            continue
        out[label] = built.parse
    return out, "; ".join(notes)
