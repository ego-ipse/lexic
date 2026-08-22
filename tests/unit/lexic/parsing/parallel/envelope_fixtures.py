"""The envelope grammar fixture shared by the plan and stitch envelope tests.

An optional leading/trailing filler wraps a ``rule cont*`` core, and
``cont``'s lead is a noise item that may itself be a comment or a bare line
ending — shaped like ABNF's ``rulelist``/``rl-cont``, small enough to
hand-derive cut and stitch outcomes for.
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
