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

from parse_bench import META_GRAMMAR as ABNF_META

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
