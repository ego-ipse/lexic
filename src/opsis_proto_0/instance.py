"""Instance — the linked text↔tree view of one parsed model.

One iterative walk over the model's tagged part stream
(``GrammarModel.emit_parts`` — the same traversal ``to_text`` reads, so
spans cannot drift from emission) produces both panes at once: the
source text with nested navigable spans, and the collapsible model tree.
Both carry matching ``data-n`` addresses; the shell's sync behavior
links them.
"""

from __future__ import annotations

from html import escape
from typing import Any

from lexic.model import GrammarModel
from lexic.parsing import is_ambiguous


def instance_html(model: GrammarModel, text: str) -> str:
    """The two linked panes as one fragment."""
    tpane: list[str] = []
    tree: list[str] = []
    pos = 0
    nid = 0
    stack: list[tuple[str, Any, str | None]] = [("enter", model, None)]
    while stack:
        kind, node, field = stack.pop()
        if kind == "exit":
            tpane.append("</span>")
            tree.append("</ul></details></li>")
            continue
        if kind == "text":
            tpane.append(escape(str(node)))
            pos += len(str(node))
            continue
        nid += 1
        grammar = type(node).__grammar__
        label = escape(str(grammar.name))
        dim = "" if grammar.semantic else " dim"
        tag = f' <em>{escape(field)}</em>' if field else ""
        parts = GrammarModel.emit_parts(node)
        if all(not isinstance(p, (GrammarModel, list, tuple)) for _f, p in parts):
            value = "".join(str(p) for _f, p in parts)
            tpane.append(f'<span class="tspan{dim}" data-n="n{nid}">{escape(value)}</span>')
            pos += len(value)
            tree.append(
                f'<li data-n="n{nid}" class="leaf{dim}">{label}{tag}'
                f' <code>{escape(value)}</code></li>'
            )
            continue
        tpane.append(f'<span class="tspan{dim}" data-n="n{nid}">')
        tree.append(f'<li data-n="n{nid}" class="{dim.strip()}"><details open>'
                    f"<summary>{label}{tag}</summary><ul>")
        stack.append(("exit", None, None))
        for f, part in reversed(parts):
            if isinstance(part, GrammarModel):
                stack.append(("enter", part, f))
            elif isinstance(part, (list, tuple)):
                for element in reversed(part):
                    if isinstance(element, GrammarModel):
                        stack.append(("enter", element, f))
                    else:
                        stack.append(("text", element, None))
            else:
                stack.append(("text", part, None))
    drift = "" if pos == len(text) else (
        f'<div class="warn">span drift: walked {pos} of {len(text)} chars</div>'
    )
    return (
        f'{drift}<div class="inst">'
        f'<div class="txt"><pre>{"".join(tpane)}</pre></div>'
        f'<div class="tree"><ul>{"".join(tree)}</ul></div></div>'
    )


def ambiguity_note(grammar: Any, text: str) -> str | None:
    """A banner when the refusal is ambiguity — the honest diagnosis."""
    try:
        if is_ambiguous(grammar, text):
            return (
                "input is AMBIGUOUS — the engines refuse rather than pick a "
                "meaning; the forest holds more than one derivation"
            )
    except Exception:  # the probe is best-effort — the parse error stands
        return None
    return None
