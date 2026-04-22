"""Shared GBNF-AST traversal helpers.

These functions are consumed by both classify.py and the residual
orchestration code in ir_builder.py. They are public (no leading
underscore) because more than one module depends on them.
"""

from __future__ import annotations

from lexic.codegen.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    RuleRef,
    Sequence,
)


def is_ws_item(item: Item) -> bool:
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def strip_ws(seq: Sequence) -> Sequence:
    """Drop `ws` rulerefs from a sequence; preserve order."""
    return Sequence([it for it in seq.items if not is_ws_item(it)])


def unwrap_group_alt(alt: Alternation) -> Alternation:
    """If `alt` is a 1-arm wrapper around a single unquantified group,
    return the inner alternation. Otherwise return `alt` unchanged."""
    if len(alt.seqs) != 1:
        return alt
    stripped = strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


def is_pure_literal_seq(seq: Sequence) -> bool:
    """True if seq (after ws-stripping) contains only Literal/CharClass items."""
    stripped = strip_ws(seq)
    return len(stripped.items) > 0 and all(
        isinstance(it.atom, (Literal, CharClass)) for it in stripped.items
    )


def single_ruleref_of(seq: Sequence) -> str | None:
    """If `seq` (ws-stripped) reduces to a single unquantified ruleref —
    either directly or as a 1-item 1-arm group containing a ruleref —
    return the referenced rule name. Otherwise return None."""
    stripped = strip_ws(seq)
    if len(stripped.items) != 1:
        return None
    it = stripped.items[0]
    if it.quantifier is not None:
        return None
    if isinstance(it.atom, RuleRef):
        return it.atom.name
    if isinstance(it.atom, Group):
        inner = it.atom.alt
        if len(inner.seqs) == 1:
            inner_stripped = strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None
