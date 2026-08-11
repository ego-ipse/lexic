"""A rule as track — the structural lines the leaf draws as a railroad.

The leaf owns every millimetre of geometry; this owns what the rule IS.
Lines are ``<depth> <kind> [payload]``, children one depth deeper, so a
nesting is a nesting and nothing here decides how wide a bracket should be.
"""

from __future__ import annotations

from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrLiteral,
    IrNone,
    IrRange,
    IrRuleRef,
    IrSequence,
)

__all__ = ["rail", "rails", "said"]

ESCAPES = {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\\": "\\\\", chr(34): chr(92) + chr(34)}


def rails(ast: IrAst) -> str:
    """Every rule's track, in AST order — the reader grammar never changes."""
    return "".join(rail(ast, str(rule.name)) for rule in ast.rules)


def rail(ast: IrAst, name: str) -> str:
    """One rule's body as track, or the refusal's own words."""
    found = next(
        (r for r in ast.rules if str(r.name).casefold() == name.casefold()), None
    )
    if found is None:
        return f"no such rule {name}\n"
    lines = _alt(found.body, 0)
    return f"#RAIL {name} {len(lines)}\n" + "".join(f"{line}\n" for line in lines)


def said(item: object) -> str:
    """One item, spelled the way the grammar spells it — never as a repr.

    A person reading "what can come next" is owed the grammar's own words;
    ``IrItem(IrRuleRef('quotation-mark'))`` is the notation of the notation.
    """
    atom = getattr(item, "atom", item)
    low, high = _bounds(getattr(item, "quantifier", None))
    body = _said_atom(atom)
    if (low, high) == (1, 1):
        return body
    if (low, high) == (0, 1):
        return f"{body}?"
    if (low, high) == (0, -1):
        return f"{body}*"
    if (low, high) == (1, -1):
        return f"{body}+"
    return f"{body}{{{low},{'' if high < 0 else high}}}"


def _said_atom(atom: object) -> str:
    """The atom itself: a name, a quoted literal, a bracketed class."""
    if isinstance(atom, IrRuleRef):
        return str(atom)
    if isinstance(atom, IrLiteral):
        return f'"{_spell(str(atom))}"'
    if isinstance(atom, IrCharClass):
        return f"[{_klass(atom)}]"
    if isinstance(atom, IrAlternation):
        return (
            "( "
            + " | ".join(" ".join(said(item) for item in arm) or "ε" for arm in atom)
            + " )"
        )
    return type(atom).__name__


def _alt(node: IrAlternation, depth: int) -> list[str]:
    """A choice. One arm is not a choice, so it collapses to the arm."""
    arms = list(node)
    if len(arms) == 1:
        return _seq(arms[0], depth)
    out = [f"{depth} alt"]
    for arm in arms:
        out.extend(_seq(arm, depth + 1))
    return out


def _seq(node: IrSequence, depth: int) -> list[str]:
    """A run. One item is not a run; no items is the empty derivation."""
    items = list(node)
    if not items:
        return [f"{depth} nil"]
    if len(items) == 1:
        return _item(items[0], depth)
    out = [f"{depth} seq"]
    for item in items:
        out.extend(_item(item, depth + 1))
    return out


def _item(item: object, depth: int) -> list[str]:
    """An atom, wrapped in its quantifier when it carries a real one."""
    atom = getattr(item, "atom", item)
    low, high = _bounds(getattr(item, "quantifier", None))
    if (low, high) == (1, 1):
        return _atom(atom, depth)
    return [f"{depth} many {low} {high}", *_atom(atom, depth + 1)]


def _bounds(quant: object) -> tuple[int, int]:
    """``(low, high)``; −1 high means unbounded, which is a real answer."""
    if quant is None or quant is IrNone or not isinstance(quant, tuple):
        return (1, 1)
    high = quant[1]
    return (int(quant[0]), -1 if high is IrNone else int(high))


def _atom(atom: object, depth: int) -> list[str]:
    """One atom, said as what it is. An unknown one is NAMED, never dropped."""
    if isinstance(atom, IrRuleRef):
        return [f"{depth} ref {atom!s}"]
    if isinstance(atom, IrLiteral):
        return [f"{depth} lit {_spell(str(atom))}"]
    if isinstance(atom, IrCharClass):
        return [f"{depth} class {_klass(atom)}"]
    if isinstance(atom, IrAlternation):
        return _alt(atom, depth)
    if isinstance(atom, IrAlphabet):
        return [f"{depth} alpha {atom[0]!s}", *_atom(atom[1], depth + 1)]
    return [f"{depth} other {type(atom).__name__}"]


def _klass(atom: IrCharClass) -> str:
    """A character class as its own spelling — ranges as ranges."""
    parts = []
    for part in atom:
        if isinstance(part, IrRange):
            parts.append(f"{_spell(_chr(part[0]))}-{_spell(_chr(part[1]))}")
        elif isinstance(part, IrChr):
            parts.append(_spell(chr(int(part))))
        else:
            parts.append(str(part))
    return "".join(parts)


def _chr(bound: object) -> str:
    """A range bound as its character; an absent bound says so, never crashes."""
    return chr(int(bound)) if isinstance(bound, int) else "…"


def _spell(text: str) -> str:
    """Control characters in the flavour's own escapes, never as holes."""
    return "".join(
        ESCAPES.get(ch, ch if ch.isprintable() else f"\\x{ord(ch):02x}") for ch in text
    )
