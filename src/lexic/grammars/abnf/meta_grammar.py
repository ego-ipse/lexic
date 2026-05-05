"""ABNF (subset) meta-grammar with canonical IR-AST tags.

Subset:
  - `name = body` (single =, not ::=)
  - alternation by `/`
  - prefix quantifiers `*N`, `n*`, `n*m`, `n`
  - charclasses via `%xNN` or `%xNN-MM`
  - case-insensitive `"abc"` literals (expansion via normalize_literal)
  - groups `(...)`, comments starting with `;`
"""

META_GRAMMAR = r"""
start: rule+

rule: NAME "=" alternation        -> ir_rule
alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                   -> ir_sequence
item: QUANTIFIER? atom            -> ir_item

atom: LITERAL                     -> ir_literal
    | HEXCC                       -> ir_charclass
    | NAME                        -> ir_ruleref
    | "(" alternation ")"         -> ir_group

NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
HEXCC: /%x[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
QUANTIFIER: /[0-9]+\*[0-9]*|\*[0-9]+|\*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""
