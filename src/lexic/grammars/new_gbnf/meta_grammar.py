"""GBNF meta-grammar — Lark grammar string with canonical IR-AST tags.

The MetaGrammarParser dispatches productions tagged `ir_rule`, `ir_literal`,
etc. to its generic IR-AST constructor. This file is data; no logic.
"""

META_GRAMMAR = r"""
start: rule+

rule: NAME "::=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                  -> ir_sequence
item: atom QUANTIFIER?           -> ir_item

atom: LITERAL                    -> ir_literal
    | CHARCLASS                  -> ir_charclass
    | NAME                       -> ir_ruleref
    | "(" alternation ")"        -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]|\{[0-9]+(?:,[0-9]*)?\}/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""
