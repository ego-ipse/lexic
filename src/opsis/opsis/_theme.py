"""The register as data — palette and rules, never a stylesheet blob.

The Limit Theory register: a near-black blue void over a faint grid,
thin glowing wireframe nodes, translucent bracket-cornered windows.
Semantics ride hue — amber = flavour/compile, cyan = grammar/structure,
green = text/instance, magenta = engine/attempt. Everything here is a
datum a table can draw and the metarepresentation can open.
"""

from __future__ import annotations

__all__ = ["PALETTE", "RULES", "css"]

PALETTE: dict[str, str] = {
    "void": "#04070d",
    "grid": "#0a1220",
    "line": "#12365c",
    "cyan": "#6ad9ff",
    "amber": "#ffc46a",
    "green": "#7ee0a3",
    "magenta": "#d98cf5",
    "err": "#ff7a7a",
    "text": "#c9dcee",
    "dim": "#5f7a94",
    "panelbg": "rgba(8,16,28,.92)",
}
"""Named hues — the vocabulary scene records' ``hue`` fields draw from."""

_HUED = ("cyan", "green", "amber", "magenta")

_GLOW = "rgba(106,217,255,.25)"

RULES: tuple[tuple[str, dict[str, str]], ...] = (
    ("*", {"box-sizing": "border-box", "margin": "0"}),
    ("html,body", {"height": "100%", "overflow": "hidden"}),
    (
        "body",
        {
            "user-select": "none",
            "color": "var(--text)",
            "font": '13px/1.5 "Segoe UI", system-ui, sans-serif',
            "background": (
                "radial-gradient(1100px 700px at 70% 10%, #081426 0%, "
                "var(--void) 55%), var(--void)"
            ),
        },
    ),
    (
        "#space",
        {
            "position": "absolute",
            "inset": "0",
            "cursor": "grab",
            "background-image": (
                "linear-gradient(var(--grid) 1px, transparent 1px), "
                "linear-gradient(90deg, var(--grid) 1px, transparent 1px)"
            ),
            "background-size": "90px 90px",
        },
    ),
    (
        "#world",
        {
            "position": "absolute",
            "transform-origin": "0 0",
            "width": "1400px",
            "height": "900px",
        },
    ),
    (
        "#wires",
        {
            "position": "absolute",
            "inset": "0",
            "overflow": "visible",
            "filter": f"drop-shadow(0 0 5px {_GLOW})",
        },
    ),
    (
        ".wire",
        {"fill": "none", "stroke-width": "1.1", "stroke": "rgba(106,217,255,.3)"},
    ),
    (
        "#hud",
        {
            "position": "absolute",
            "left": "22px",
            "top": "18px",
            "z-index": "9",
            "pointer-events": "none",
        },
    ),
    (
        "#hud h1",
        {
            "font-size": "17px",
            "letter-spacing": "9px",
            "color": "var(--cyan)",
            "font-weight": "300",
            "text-transform": "uppercase",
            "text-shadow": "0 0 18px rgba(106,217,255,.8)",
        },
    ),
    (
        "#hud p",
        {
            "color": "var(--dim)",
            "font-size": "11px",
            "letter-spacing": "2px",
            "margin-top": "4px",
        },
    ),
    (
        ".nd",
        {
            "position": "absolute",
            "width": "0",
            "height": "0",
            "z-index": "3",
            "cursor": "pointer",
        },
    ),
    (
        ".rdot",
        {
            "position": "absolute",
            "left": "-14px",
            "top": "-14px",
            "width": "28px",
            "height": "28px",
            "border-radius": "50%",
            "border": "1.2px solid var(--cyan)",
            "background": "rgba(106,217,255,.10)",
            "transition": "box-shadow .15s",
        },
    ),
    (".nd:hover .rdot, .nd.on .rdot", {"box-shadow": f"0 0 14px {_GLOW}"}),
    (
        ".rlabel",
        {
            "position": "absolute",
            "left": "20px",
            "top": "-9px",
            "white-space": "nowrap",
            "font": '11px "Cascadia Mono", monospace',
            "letter-spacing": "1.5px",
            "color": "var(--dim)",
        },
    ),
    (".nd:hover .rlabel, .nd.on .rlabel", {"color": "var(--text)"}),
    (
        ".frame",
        {
            "position": "absolute",
            "z-index": "5",
            "background": "var(--panelbg)",
            "border": "1px solid var(--line)",
            "border-radius": "3px",
            "display": "flex",
            "flex-direction": "column",
            "box-shadow": "0 0 30px rgba(0,0,0,.6), 0 0 12px rgba(106,217,255,.12)",
        },
    ),
    (
        ".frame header",
        {
            "padding": "6px 10px",
            "font": '10px "Cascadia Mono", monospace',
            "letter-spacing": "1.6px",
            "text-transform": "uppercase",
            "color": "var(--cyan)",
            "border-bottom": "1px solid var(--line)",
            "border-left": "2px solid var(--cyan)",
            "display": "flex",
            "cursor": "move",
        },
    ),
    (".frame header span", {"flex": "1"}),
    (".frame header b", {"font-weight": "normal", "opacity": ".5", "cursor": "pointer"}),
    (".frame header b:hover", {"opacity": "1"}),
    (
        ".frame .fbody",
        {
            "flex": "1",
            "overflow": "auto",
            "padding": "10px",
            "user-select": "text",
            "font": '11.5px "Cascadia Mono", Consolas, monospace',
        },
    ),
    (
        ".frame::before, .frame::after",
        {
            "content": '""',
            "position": "absolute",
            "width": "10px",
            "height": "10px",
            "border": "1px solid var(--cyan)",
            "opacity": ".55",
            "pointer-events": "none",
        },
    ),
    (
        ".frame::before",
        {"left": "-1px", "top": "-1px", "border-right": "0", "border-bottom": "0"},
    ),
    (
        ".frame::after",
        {"right": "-1px", "bottom": "-1px", "border-left": "0", "border-top": "0"},
    ),
)
"""The canvas rules — (selector, properties), drawn in order."""


def _hue_rules() -> list[str]:
    """Per-hue ring tints, derived from the palette rather than written out."""
    out = []
    for hue in _HUED:
        out.append(
            f".ring.{hue} .rdot {{ border-color: var(--{hue}); "
            f"background: color-mix(in srgb, var(--{hue}) 12%, transparent); }}"
        )
    return out


def css() -> str:
    """The register rendered — :root palette variables, rules, hue tints."""
    root = "".join(f"--{name}:{value};" for name, value in PALETTE.items())
    rules = [f":root {{ {root} }}"]
    for selector, props in RULES:
        body = "".join(f"{key}:{value};" for key, value in props.items())
        rules.append(f"{selector} {{ {body} }}")
    rules.extend(_hue_rules())
    return "\n".join(rules)
