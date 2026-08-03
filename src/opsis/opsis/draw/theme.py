"""The register as data — palette, motions and rules, never a blob.

A near-black blue void over a faint grid; a reading is a ring that
breathes, with a glowing core and a slow dashed orbit; a relation is a
bowed rail that flows; a window is a translucent panel with bracket
corners.

Hue carries meaning and nothing else does: amber a reader, cyan a
grammar, green a text, magenta a choice the engine made, err a refusal,
dim something unread. Everything is a datum, which is what lets the
register be opened and edited like any other table.
"""

from __future__ import annotations

__all__ = ["HUES", "KEYFRAMES", "PALETTE", "RULES", "css"]

PALETTE = {
    "void": "#04070d",
    "grid": "#0a1220",
    "line": "#12365c",
    "cyan": "#6ad9ff",
    "cyandim": "#2f6f96",
    "amber": "#ffc46a",
    "green": "#7ee0a3",
    "magenta": "#d98cf5",
    "err": "#ff7a7a",
    "silver": "#c9d4df",
    "text": "#c9dcee",
    "dim": "#5f7a94",
    "panel": "rgba(8,16,28,.93)",
}
"""Named hues — what a scene record's ``hue`` field draws from."""

HUES = ("cyan", "amber", "green", "magenta", "err", "dim", "silver")

MONO = '"Cascadia Mono", Consolas, monospace'

KEYFRAMES = (
    ("breathe", "50% { transform:scale(1.06); opacity:.85; }"),
    ("spin", "to { transform:rotate(360deg); }"),
    ("flow", "to { stroke-dashoffset:-16; }"),
)
"""Three motions: a ring breathes, its orbit turns, a reading flows."""

RULES: tuple[tuple[str, str], ...] = (
    ("*", "box-sizing:border-box;margin:0"),
    ("html,body", "height:100%;overflow:hidden"),
    (
        "body",
        "user-select:none;color:var(--text);"
        'font:13px/1.5 "Segoe UI",system-ui,sans-serif;'
        "background:radial-gradient(1100px 700px at 70% 10%,#081426 0%,"
        "var(--void) 55%),var(--void)",
    ),
    (
        "#space",
        "position:absolute;inset:0;cursor:grab;"
        "background-image:linear-gradient(var(--grid) 1px,transparent 1px),"
        "linear-gradient(90deg,var(--grid) 1px,transparent 1px);"
        "background-size:90px 90px",
    ),
    ("#space.dragging", "cursor:grabbing"),
    ("#world", "position:absolute;transform-origin:0 0;width:9000px;height:6000px"),
    (
        "#wires",
        "position:absolute;inset:0;overflow:visible;pointer-events:none;"
        "filter:drop-shadow(0 0 5px rgba(106,217,255,.28))",
    ),
    # the HUD
    ("#hud", "position:fixed;left:22px;top:18px;z-index:9;pointer-events:none"),
    (
        "#hud h1",
        "font-size:17px;letter-spacing:9px;color:var(--cyan);font-weight:300;"
        "text-transform:uppercase;text-shadow:0 0 18px rgba(106,217,255,.8)",
    ),
    (
        "#hud p",
        "color:var(--dim);font-size:11px;letter-spacing:2px;margin-top:4px;"
        "text-transform:uppercase",
    ),
    (
        "#hint",
        "position:fixed;right:22px;bottom:80px;z-index:9;pointer-events:none;"
        "text-align:right;color:var(--dim);font-size:10.5px;letter-spacing:1.5px",
    ),
    (
        "#legend",
        "position:fixed;left:24px;bottom:80px;z-index:9;pointer-events:none;"
        "color:var(--dim);font-size:10px;letter-spacing:1.5px;"
        "text-transform:uppercase",
    ),
    (
        "#legend i",
        "display:inline-block;width:8px;height:8px;border-radius:50%;"
        "margin:0 5px 0 14px",
    ),
    # rings
    (".nd", "position:absolute;width:0;height:0;z-index:3"),
    (".ring", "cursor:move"),
    (
        ".ring .disc",
        "position:absolute;left:-34px;top:-34px;width:68px;height:68px;"
        "border:1px solid var(--cyan);border-radius:50%;"
        "box-shadow:0 0 22px rgba(106,217,255,.35),"
        "inset 0 0 14px rgba(106,217,255,.18);"
        "animation:breathe 4s ease-in-out infinite",
    ),
    (
        ".ring .disc::after",
        'content:"";position:absolute;inset:-9px;'
        "border:1px dashed rgba(106,217,255,.22);border-radius:50%;"
        "animation:spin 26s linear infinite",
    ),
    (
        ".ring .core",
        "position:absolute;left:-5px;top:-5px;width:10px;height:10px;"
        "border-radius:50%;background:var(--cyan);"
        "box-shadow:0 0 12px var(--cyan),0 0 30px rgba(106,217,255,.6)",
    ),
    (
        ".title",
        "position:absolute;left:-316px;top:-17px;width:262px;text-align:right;"
        f"font:12px {MONO};color:var(--text);letter-spacing:1px;"
        "pointer-events:none",
    ),
    (
        ".title span",
        "display:block;color:var(--dim);font-size:9.5px;margin-top:3px;"
        "line-height:1.35",
    ),
    (".ring:hover .title", "color:var(--cyan)"),
    (".ring.reads .disc", "border-width:2px"),
    (".ring.idle .disc", "border-style:dashed;animation:none;box-shadow:none"),
    (".ring.idle .disc::after", "display:none"),
    (".ring.idle .core", "width:7px;height:7px;left:-3.5px;top:-3.5px;box-shadow:none"),
    (
        ".ring.landing .disc",
        "border-color:var(--magenta);box-shadow:0 0 30px rgba(217,140,245,.7)",
    ),
    (".ring.landing .title", "color:var(--magenta)"),
    (".hide", "display:none !important"),
    # what a ring lets you do
    (
        ".act",
        "position:absolute;width:22px;height:22px;line-height:22px;"
        "text-align:center;color:var(--dim);cursor:pointer;font:13px monospace;"
        "opacity:0;transition:opacity .15s;z-index:6",
    ),
    (".act.unplug", "left:-46px;top:-40px"),
    (".act.remove", "left:-46px;top:16px"),
    (".act.fold", "left:24px;top:-40px"),
    (".ring:hover .act", "opacity:.8"),
    (".act:hover", "color:var(--cyan);opacity:1"),
    (".act.remove:hover", "color:var(--err)"),
    # moons
    (".moon", "position:absolute;cursor:pointer;z-index:4"),
    (
        ".moon .dot",
        "position:absolute;left:-7px;top:-7px;width:14px;height:14px;"
        "border:1px solid var(--cyandim);border-radius:50%;"
        "background:rgba(4,8,15,.9);transition:all .2s",
    ),
    (
        ".moon .dot::after",
        'content:"";position:absolute;left:4px;top:4px;width:4px;'
        "height:4px;border-radius:50%;background:var(--cyan);"
        "opacity:.55",
    ),
    (
        ".moon:hover .dot,.moon.on .dot",
        "border-color:var(--cyan);box-shadow:0 0 12px rgba(106,217,255,.55)",
    ),
    (".moon.on .dot::after", "opacity:1"),
    (
        ".moon em",
        "position:absolute;left:13px;top:-8px;white-space:nowrap;"
        f"font:10px {MONO};font-style:normal;letter-spacing:1.6px;"
        "text-transform:uppercase;color:var(--dim);opacity:0;"
        "transition:opacity .18s,color .2s;pointer-events:none",
    ),
    (".ring:hover .moon em,.moon:hover em,.moon.on em", "opacity:1"),
    (".moon:hover em,.moon.on em", "color:var(--cyan)"),
    # rails
    (".rail.under", "fill:none;stroke-width:7"),
    (
        ".rail.over",
        "fill:none;stroke-width:1.4;stroke-dasharray:7 9;"
        "animation:flow 1.4s linear infinite",
    ),
    (
        ".raillabel .big",
        f"font:10px {MONO};letter-spacing:2px;text-transform:uppercase",
    ),
    (".raillabel .small", f"font:9px {MONO};fill:var(--dim)"),
    (
        ".leader",
        "fill:none;stroke:var(--cyan);stroke-width:1;stroke-dasharray:2 5;opacity:.5",
    ),
    # windows
    (
        ".frame",
        "position:absolute;z-index:5;background:var(--panel);"
        "border:1px solid var(--line);border-radius:3px;display:flex;"
        "flex-direction:column;overflow:hidden;min-width:260px;min-height:36px;"
        "box-shadow:0 0 30px rgba(0,0,0,.6),0 0 12px rgba(106,217,255,.12)",
    ),
    (
        ".frame header",
        "flex:none;display:flex;gap:9px;padding:7px 10px;cursor:move;"
        f"font:10px {MONO};letter-spacing:1.6px;text-transform:uppercase;"
        "color:var(--cyan);border-bottom:1px solid var(--line);"
        "border-left:2px solid var(--cyan)",
    ),
    (".frame header span", "flex:1;overflow:hidden"),
    (".frame header b", "font-weight:normal;opacity:.45;cursor:pointer"),
    (".frame header b:hover", "opacity:1"),
    (
        ".frame .body",
        "flex:1;overflow:auto;padding:11px;user-select:text;"
        f"position:relative;font:11.5px {MONO}",
    ),
    ("::-webkit-scrollbar", "width:7px;height:7px"),
    ("::-webkit-scrollbar-thumb", "background:var(--line);border-radius:4px"),
    (
        ".frame::before,.frame::after",
        'content:"";position:absolute;width:10px;'
        "height:10px;border:1px solid var(--cyan);"
        "opacity:.55;pointer-events:none",
    ),
    (".frame::before", "left:-1px;top:-1px;border-right:0;border-bottom:0"),
    (".frame::after", "right:-1px;bottom:-1px;border-left:0;border-top:0"),
    (".grip", "position:absolute;z-index:7;touch-action:none"),
    (".g-n", "left:8px;right:8px;top:-3px;height:7px;cursor:ns-resize"),
    (".g-s", "left:8px;right:8px;bottom:-3px;height:7px;cursor:ns-resize"),
    (".g-e", "top:8px;bottom:8px;right:-3px;width:7px;cursor:ew-resize"),
    (".g-w", "top:8px;bottom:8px;left:-3px;width:7px;cursor:ew-resize"),
    (".g-ne", "top:-3px;right:-3px;width:13px;height:13px;cursor:nesw-resize"),
    (".g-nw", "top:-3px;left:-3px;width:13px;height:13px;cursor:nwse-resize"),
    (".g-se", "bottom:-3px;right:-3px;width:13px;height:13px;cursor:nwse-resize"),
    (".g-sw", "bottom:-3px;left:-3px;width:13px;height:13px;cursor:nesw-resize"),
    (
        ".g-se::after",
        'content:"";position:absolute;right:3px;bottom:3px;width:6px;height:6px;'
        "border-right:1px solid var(--line);border-bottom:1px solid var(--line)",
    ),
    (".frame:hover .g-se::after", "border-color:var(--cyan)"),
    # while anything is being dragged, nothing else may claim the pointer
    (".dragging-any", "user-select:none"),
    (".dragging-any .body,.dragging-any .gspace", "pointer-events:none"),
    (".frame.min", "height:auto !important;min-height:0"),
    (".frame.min .body,.frame.min .grip", "display:none"),
    (
        ".frame.hud",
        "position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:12",
    ),
    (".frame.sub", "z-index:6"),
    # bodies
    (".row", "margin:0 0 9px;border-left:2px solid var(--line);padding:1px 9px"),
    (".row.added", "border-left-color:var(--green)"),
    (".row.changed", "border-left-color:var(--amber)"),
    (".name", "color:var(--cyan);letter-spacing:1.5px;cursor:pointer;font-size:11px"),
    (".src", "margin:3px 0 0;color:var(--text);white-space:pre-wrap;opacity:.92"),
    (".src.was", "color:var(--dim);text-decoration:line-through;opacity:.7"),
    (".note", f"color:var(--dim);font:9.5px {MONO};letter-spacing:1px"),
    (
        ".refusal",
        "margin:6px 0;padding:5px 9px;color:var(--err);"
        "border-left:2px solid var(--err);white-space:pre-wrap",
    ),
    (".dx,.dx *", "color:#fff !important;text-shadow:0 0 12px rgba(255,255,255,.75)"),
    # graphs in windows
    (".gspace", "position:relative"),
    (".gwires", "position:absolute;left:0;top:0;overflow:visible"),
    (".gedge", "fill:none;stroke:rgba(106,217,255,.20);stroke-width:1"),
    (
        ".gnode",
        "position:absolute;transform:translateY(-50%);white-space:nowrap;"
        f"padding-left:14px;font:11px {MONO};letter-spacing:.5px;"
        "color:var(--text);cursor:pointer",
    ),
    (
        ".gnode i",
        "position:absolute;left:0;top:50%;transform:translateY(-50%);"
        "width:9px;height:9px;border-radius:50%;"
        "border:1px solid var(--cyan);background:rgba(106,217,255,.12)",
    ),
    (".gnode:hover", "color:var(--cyan)"),
    (".gnode:hover i", "box-shadow:0 0 9px var(--cyan)"),
    # twin panes
    (".twin", "display:flex;gap:12px;height:100%;align-items:stretch"),
    (
        ".pane",
        "flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;overflow:auto",
    ),
    (".pane.left", "border-right:1px solid var(--line);padding-right:11px"),
    (".target", "flex:1;overflow:auto;margin:0"),
    (
        ".target mark",
        "background:rgba(106,217,255,.25);color:var(--cyan);border-radius:2px",
    ),
    # trees
    (".tree", "margin-top:8px"),
    (
        ".twig",
        "display:flex;gap:8px;align-items:baseline;padding:1px 0;white-space:nowrap",
    ),
    (".twig.hide", "display:none"),
    (".twig b", "width:10px;flex:none;color:var(--cyandim);font-weight:normal"),
    (".twig.kids b", "cursor:pointer"),
    (".twig.shut b", "color:var(--amber)"),
    (".twig.kids:hover b", "color:var(--cyan)"),
    (".twig .txt", "color:var(--dim);overflow:hidden;text-overflow:ellipsis"),
    (".twig:hover .txt", "color:var(--text)"),
    # editors
    (".editor .body", "display:flex;flex-direction:column;gap:8px"),
    (
        ".editor textarea",
        "flex:1;width:100%;min-height:70px;padding:8px;resize:none;"
        "outline:none;background:rgba(4,8,15,.6);"
        "border:1px solid var(--line);color:var(--text);"
        f"font:11.5px {MONO}",
    ),
    (".editor textarea:focus", "border-color:var(--cyandim)"),
    (".controls", "display:flex;flex:none;gap:10px;align-items:center;flex-wrap:wrap"),
    (
        ".chip",
        "display:inline-flex;align-items:center;gap:6px;padding:2px 10px;"
        f"border:1px solid var(--line);border-radius:11px;font:9.5px {MONO};"
        "letter-spacing:1.2px;text-transform:uppercase;color:var(--dim)",
    ),
    (
        ".chip input",
        "width:110px;padding:0 2px;outline:none;background:transparent;"
        "border:0;border-bottom:1px solid var(--line);color:var(--amber);"
        f"font:10px {MONO};text-transform:none",
    ),
    (".chip input::placeholder", "color:var(--line)"),
    (".chip:focus-within", "border-color:var(--cyandim)"),
    (".chip.off", "opacity:.45"),
    (".chip.off input", "pointer-events:none"),
    # the bar
    (
        ".bar",
        "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);"
        "z-index:10;display:flex;gap:16px;align-items:center;padding:9px 20px;"
        "border:1px solid var(--line);border-radius:22px;"
        "background:rgba(8,16,28,.88);cursor:move",
    ),
    (
        ".bar u",
        f"text-decoration:none;color:var(--dim);font:9px {MONO};"
        "letter-spacing:2px;text-transform:uppercase",
    ),
    (
        ".bnode",
        "display:flex;flex-direction:column;align-items:center;gap:3px;"
        "width:78px;cursor:pointer",
    ),
    (
        ".bnode i",
        "width:16px;height:16px;border-radius:50%;"
        "border:1.2px solid var(--cyan);background:rgba(106,217,255,.12)",
    ),
    (
        ".bnode em",
        f"font:9px {MONO};font-style:normal;letter-spacing:1px;"
        "text-align:center;color:var(--dim)",
    ),
    (".bnode:hover em", "color:var(--text)"),
    (".ghost", "position:fixed;z-index:12;opacity:.85;pointer-events:none"),
    (".ghost i", "border-style:dashed"),
    # the picker
    (
        ".prow",
        "padding:3px 7px;cursor:pointer;border-left:2px solid transparent;"
        f"font:11px {MONO};color:var(--text)",
    ),
    (
        ".prow:hover",
        "color:var(--cyan);background:rgba(106,217,255,.06);"
        "border-left-color:var(--cyan)",
    ),
    (".prow.dir", "color:var(--cyan)"),
    (".prow em", "float:right;font-style:normal;font-size:9.5px;color:var(--line)"),
    (".prow:hover em", "color:var(--dim)"),
    # a refusal said out loud
    (
        ".toast",
        "position:fixed;left:50%;bottom:94px;transform:translateX(-50%);"
        "z-index:11;max-width:660px;padding:9px 15px;background:var(--panel);"
        "border:1px solid var(--err);border-left:3px solid var(--err);"
        f"color:var(--err);font:11px {MONO};white-space:pre-wrap;cursor:pointer",
    ),
    # a semantic reading: the grammar's own noise, dimmed
    ('.semantic .twig.noise,.semantic .twig[data-rule=""]', "opacity:.32"),
    (".semantic .twig:hover", "opacity:1"),
    # a document rendered at a width you can see the edge of
    (
        ".src.ruled",
        "position:relative;background:linear-gradient(to right,transparent 0,"
        "transparent calc(var(--cols) * 1ch),var(--panel) calc(var(--cols) * 1ch))",
    ),
    ('input[type="range"]', "accent-color:var(--cyan);width:200px"),
    # the execution bar: one mark per decision, laid over the input
    (
        ".exec",
        "position:relative;height:26px;margin:8px 0;border:1px solid var(--line);"
        "border-left:2px solid var(--cyan);background:var(--void)",
    ),
    (
        ".exec i",
        "position:absolute;top:3px;width:1px;height:20px;background:var(--cyan);"
        "opacity:.55",
    ),
    (".exec i:hover", "opacity:1;width:2px;background:var(--amber)"),
    # a group of readings, worn as one moon and opened in place
    (".moon.group .dot", "border-style:double;border-width:3px"),
    (".moon .sub", "position:absolute;left:0;top:0;pointer-events:none"),
    (
        ".moon .sub .moon",
        "opacity:0;transform:scale(.4);pointer-events:none;"
        "transition:opacity .16s,transform .16s",
    ),
    (
        ".moon.group.open .sub .moon",
        "opacity:1;transform:scale(1);pointer-events:auto",
    ),
    (".moon.group.open > .dot", "background:var(--cyan);border-color:var(--cyan)"),
    (".moon.inner .dot", "width:7px;height:7px"),
    # a measured claim — the mark carries the verdict, the hue repeats it
    (
        ".claim",
        "margin:7px 0;padding:6px 10px;border-left:2px solid var(--line);"
        f"font:11px {MONO};color:var(--dim);letter-spacing:.4px",
    ),
    (".claim em", "float:right;font-style:normal;color:var(--line)"),
    (".claim.ok", "border-left-color:var(--green);color:var(--green)"),
    (".claim.no", "border-left-color:var(--err);color:var(--err)"),
    (
        ".claim.un",
        "border-left-color:var(--amber);color:var(--amber);border-left-style:dashed",
    ),
    # a deed's button — it does one thing and says which
    (
        "button.go",
        "padding:4px 12px;background:transparent;border:1px solid var(--cyan);"
        f"color:var(--cyan);font:10px {MONO};letter-spacing:1.4px;"
        "text-transform:uppercase;cursor:pointer;transition:background .12s",
    ),
    ("button.go:hover", "background:var(--cyan);color:var(--void)"),
    ("button.go:disabled", "opacity:.4;cursor:progress"),
    # a dispatch table, as the data it is
    (
        ".table",
        "margin:10px 0;border:1px solid var(--line);"
        "border-left:2px solid var(--magenta)",
    ),
    (
        ".grid",
        "max-height:220px;overflow:auto;border-top:1px solid var(--line)",
    ),
    (
        ".cell",
        "display:flex;gap:10px;padding:3px 10px;"
        f"font:10.5px {MONO};border-bottom:1px solid var(--line)",
    ),
    (".cell:hover", "background:var(--panel)"),
    (".cell code", "flex:0 0 34%;color:var(--cyan);overflow:hidden"),
    (".cell span", "flex:1;color:var(--dim);overflow:hidden;white-space:pre"),
    # a frozen artifact: gestures dead, and drawn so
    (
        ".frozen .bnode,.frozen .chip,.frozen .act,.frozen textarea",
        "opacity:.35;pointer-events:none",
    ),
    (
        ".frozen .bar::after",
        'content:"frozen — these need the live loop";'
        f"color:var(--dim);font:9px {MONO};letter-spacing:1.5px",
    ),
)
"""The canvas rules — (selector, declarations), emitted in order."""


def _tints() -> list[str]:
    """Per-hue tints, derived from the palette rather than written out."""
    out: list[str] = []
    for hue in HUES:
        soft = f"color-mix(in srgb, var(--{hue}) 12%, transparent)"
        out += [
            f".ring.{hue} .disc,.ring.{hue} .disc::after {{border-color:var(--{hue})}}",
            f".ring.{hue} .disc {{box-shadow:0 0 22px "
            f"color-mix(in srgb,var(--{hue}) 35%,transparent),"
            f"inset 0 0 14px color-mix(in srgb,var(--{hue}) 18%,transparent)}}",
            f".ring.{hue} .core {{background:var(--{hue});"
            f"box-shadow:0 0 12px var(--{hue})}}",
            f".rail-{hue}.over {{stroke:var(--{hue})}}",
            f".rail-{hue}.under {{stroke:color-mix(in srgb,var(--{hue}) 10%,transparent)}}",
            f".rl-{hue} .big {{fill:var(--{hue})}}",
            f".bnode.{hue} i {{border-color:var(--{hue});background:{soft}}}",
            f".gnode.v-{hue} i {{border-color:var(--{hue});background:{soft}}}",
        ]
    out.append(".ring.dim .disc{animation:none;box-shadow:none}")
    out.append(".ring.dim .title{color:var(--dim)}")
    return out


def css() -> str:
    """The register rendered — palette variables, motions, rules, tints."""
    root = "".join(f"--{name}:{value};" for name, value in PALETTE.items())
    out = [f":root{{{root}}}"]
    out += [f"@keyframes {name}{{{body}}}" for name, body in KEYFRAMES]
    out += [f"{selector}{{{body}}}" for selector, body in RULES]
    out += _tints()
    return "\n".join(out)
