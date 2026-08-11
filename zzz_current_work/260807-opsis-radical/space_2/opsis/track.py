"""One rule as track — the railroad, emitted as marks.

Measured in characters and converted to pixels here, because a picture
measured by a font in a browser is a shape nothing can check. The leaf
receives boxes, lines and curves it already knows how to paint, and hit
rectangles carrying the rule each reference names.
"""

from __future__ import annotations

from lexic.ir import IrAlternation, IrAst, IrLiteral, IrRuleRef, IrSequence

__all__ = ["track"]

CELL = 7.0
ROW = 20.0


def _atoms(body: object) -> list[tuple[str, str]]:
    """The rule's body as a flat row of things — kind and what it says.

    A flat reading, deliberately: this shows what a rule is MADE OF at the
    cursor, and the full nesting is the relations graph's job.
    """
    out: list[tuple[str, str]] = []
    stack: list[object] = [body]
    while stack:
        node = stack.pop(0)
        if isinstance(node, IrRuleRef):
            out.append(("ref", str(node)))
        elif isinstance(node, IrLiteral):
            out.append(("lit", f'"{node}"'))
        elif isinstance(node, (IrAlternation, IrSequence)):
            kids = list(node.children())
            if isinstance(node, IrAlternation) and len(kids) > 1:
                out.append(("or", "|"))
            stack = kids + stack
        elif hasattr(node, "children"):
            stack = list(node.children()) + stack
        if len(out) > 24:
            break
    return out


def track(said: object, ast: IrAst, name: str, x: float, y: float, wide: float) -> None:
    """Draw one rule's track at (x, y), clipped to the width it was given."""
    rule = next(
        (r for r in ast.rules if str(r.name).casefold() == name.casefold()), None
    )
    if rule is None:
        return
    said.text(x, y - 6, "label", f"{name} ::=")
    cursor = x
    for kind, spelled in _atoms(rule.body):
        shown = spelled if len(spelled) <= 18 else spelled[:17] + "…"
        w = len(shown) * CELL + 10
        if cursor + w > x + wide:
            break
        if kind == "or":
            said.text(cursor + 2, y + 14, "dim", "|")
            cursor += 12
            continue
        said.box(cursor, y, w, ROW - 4, "ahead", "")
        said.text(cursor + 5, y + 13, "ink" if kind == "ref" else "dim", shown)
        if cursor > x:
            said.line(cursor - 6, y + 8, cursor, y + 8, "hair")
        if kind == "ref":
            said.hit(cursor, y, w, ROW - 4, "rule", shown)
        cursor += w + 6
