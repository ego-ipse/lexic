"""Envelope-shaped grammar fixtures shared across the parallel-package tests.

An optional leading/trailing filler wraps a ``rule cont*`` core, and
``cont``'s lead is a noise item that may itself be a comment or a bare line
ending — shaped like ABNF's ``rulelist``/``rl-cont``, small enough to
hand-derive cut and stitch outcomes for. ``GBNF_REGION_SOURCE`` is the
sibling fixture for I14's region-family shapes (a ``tok-id``-shaped
construct, character classes with an empty-instance arm), shared between the
integration end-to-end test and the adversarial density tests.
"""

from __future__ import annotations

ENVELOPE_SOURCE = (
    "root ::= filler? rule cont* filler?\n"
    'rule ::= name ws "=" ws value\n'
    "cont ::= ws cnl filler* rule\n"
    "cnl ::= comment | crlf\n"
    "filler ::= comment | blank\n"
    'comment ::= "; " word crlf\n'
    "blank ::= crlf\n"
    "name ::= [a-z]+\n"
    'ws ::= " "*\n'
    "value ::= word (crlf ws word)*\n"
    "word ::= [a-z]+\n"
    'crlf ::= "\\n"\n'
)

TWO_MARK_SOURCE = (
    "root ::= filler? rule cont* filler?\n"
    'rule ::= name ws "=" ws value\n'
    "cont ::= ws cnl filler* rule\n"
    "cnl ::= comment | crlf | tabsep\n"
    "filler ::= comment | blank\n"
    'comment ::= "; " word crlf\n'
    "blank ::= crlf\n"
    'tabsep ::= "\\t"\n'
    "name ::= [a-z]+\n"
    'ws ::= " "*\n'
    "value ::= word (crlf ws word)*\n"
    "word ::= [a-z]+\n"
    'crlf ::= "\\n"\n'
)
"""``ENVELOPE_SOURCE`` with a second provable separator character
(``tabsep``) added beside ``crlf`` — I14's gbnf tab-vs-newline shape
(codepoint order hands back the tab, but a document may carry only the
newline), authored generically rather than against gbnf itself."""

GBNF_REGION_SOURCE = (
    "root ::= rule cont* n?\n"
    'rule ::= name ws "::=" ws body\n'
    "cont ::= n rule\n"
    "n ::= (nl | comment)+\n"
    'comment ::= "#" cchar* "\\n"\n'
    "cchar ::= [^\\n]\n"
    'nl ::= "\\n"\n'
    'body ::= item ("|" item)*\n'
    "item ::= literal | charclass | tokid | ref\n"
    'literal ::= "\\"" lchar* "\\""\n'
    'lchar ::= [^"]\n'
    'charclass ::= "[" ccbody "]" | "[]"\n'
    "ccbody ::= ccitem+\n"
    "ccitem ::= [a-zA-Z0-9]\n"
    'tokid ::= "<[" digits tail\n'
    'tail ::= ">" | "-" digits ">"\n'
    "digits ::= [0-9]+\n"
    "ref ::= [a-z]+\n"
    "name ::= [a-z]+\n"
    'ws ::= " "*\n'
)
"""Multi-line rules (``n`` is the noise-run separator, comment or newline);
character classes with a fully-literal empty-instance arm (``"[]"``); and a
``tok-id``-shaped construct whose closer is reached through ``tail``'s
two-armed reference — the exact three shapes I14/I14b's region-family fix
was for, authored generically rather than against gbnf itself."""


CONTINUATION_SOURCE = (
    "root ::= defn+\n"
    "defn ::= name colons body nl\n"
    "name ::= [a-z]+\n"
    'colons ::= " ::= "\n'
    "body ::= piece morep*\n"
    "morep ::= sep piece\n"
    'sep ::= "\\n  | "\n'
    "piece ::= [a-z]+\n"
    'nl ::= "\\n"\n'
)
"""A unit that emits its own mark (a continuation separator), so
``terminates_once`` fails — but the unit still announces itself with a
mandatory head and literal, so the boundary route applies."""
