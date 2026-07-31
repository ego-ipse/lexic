"""Shell — the page as lexic layout docs, composed part by part.

No template blob: the document is an :class:`~lexic.ir.text.layout.IrDoc`
tree built from small element constructors and rendered by lexic's
layout algebra. Every region of the page — head, styles, sidebar, tabs,
views, each script behavior — is its own function or datum, alterable in
place. Escaping is intrinsic to the constructors: :func:`text` and
attribute values escape, :func:`raw` is the single deliberate pass-through
(pre-rendered SVG from :mod:`opsis.graphic`, the style/script bodies).
"""

from __future__ import annotations

from html import escape

from lexic.ir import IrCat, IrLine, IrText
from lexic.ir.text.layout import IrDoc, render


# ── element constructors ──────────────────────────────────────────────


def text(s: str) -> IrDoc:
    """An escaped text leaf."""
    return _lines(escape(s))


def raw(s: str) -> IrDoc:
    """A pass-through leaf — pre-rendered markup, styles, script."""
    return _lines(s)


def _lines(s: str) -> IrDoc:
    """Text as the algebra wants it — newlines are :class:`IrLine` breaks."""
    rows = s.split("\n")
    if len(rows) == 1:
        return IrText(s)
    parts: list[IrDoc] = []
    for i, row in enumerate(rows):
        if i:
            parts.append(IrLine("", ""))
        if row:
            parts.append(IrText(row))
    return IrCat(*parts)


def el(tag: str, attrs: dict[str, str | None] | None, *kids: IrDoc | str) -> IrDoc:
    """One element — attributes escaped, string children escaped.

    The doc check comes first: an :class:`IrText` IS a ``str`` (the node
    is its payload), and a doc child must never be re-escaped.
    """
    parts: list[IrDoc] = [raw(f"<{tag}{_attrs(attrs)}>")]
    parts.extend(k if isinstance(k, IrDoc) else text(k) for k in kids)
    parts.append(raw(f"</{tag}>"))
    return IrCat(*parts)


def void(tag: str, attrs: dict[str, str | None] | None = None) -> IrText:
    """A void element (``meta`` and kin)."""
    return raw(f"<{tag}{_attrs(attrs)}>")


def _attrs(attrs: dict[str, str | None] | None) -> str:
    """The attribute string — ``None`` values render as bare attributes."""
    if not attrs:
        return ""
    out = []
    for key, val in attrs.items():
        out.append(f" {key}" if val is None else f' {key}="{escape(val, quote=True)}"')
    return "".join(out)


# ── the public surface ────────────────────────────────────────────────


def live_page(source: str, flavour: str, sections: dict[str, str],
              input_text: str = "") -> str:
    """The live shell — editors enabled, current sections pre-filled."""
    return render(_page("live", source, flavour, sections, input_text), None)


def artifact(source: str, flavour: str, sections: dict[str, str],
             input_text: str = "") -> str:
    """A frozen session — sections in the DOM, editing off."""
    return render(_page("artifact", source, flavour, sections, input_text), None)


def fragments(sections: dict[str, str]) -> str:
    """A compile/parse response — every section as a swappable fragment.

    ``status`` is text (escaped); every other section is pre-rendered
    markup from its own renderer.
    """
    doc = IrCat(*(
        el("div", {"id": f"frag-{name}"},
           body if name == "status" else raw(body))
        for name, body in sections.items()
    ))
    return render(doc, None)


# ── the page ──────────────────────────────────────────────────────────


def _page(mode: str, source: str, flavour: str, sections: dict[str, str],
          input_text: str) -> IrDoc:
    return IrCat(
        raw("<!DOCTYPE html>"),
        el("html", {"lang": "en"}, _head(),
           _body(mode, source, flavour, sections, input_text)),
    )


def _head() -> IrDoc:
    return el(
        "head",
        None,
        void("meta", {"charset": "utf-8"}),
        el("title", None, "opsis"),
        el("style", None, raw(_css())),
    )


def _body(mode: str, source: str, flavour: str, sections: dict[str, str],
          input_text: str) -> IrDoc:
    return el(
        "body",
        {"data-mode": mode, "data-flavour": flavour},
        _side(source, sections, input_text),
        _main(sections),
        el("script", None, raw(_SCRIPT)),
    )


def _side(source: str, sections: dict[str, str], input_text: str) -> IrDoc:
    return el(
        "div",
        {"id": "side"},
        el(
            "header",
            None,
            el("h1", None, "opsis"),
            el("span", {"id": "mode-tag"}),
        ),
        el(
            "textarea",
            {"id": "grammar", "spellcheck": "false", "placeholder": "type a grammar…"},
            source,
        ),
        el(
            "textarea",
            {"id": "input", "spellcheck": "false",
             "placeholder": "input text… (parses on pause)"},
            input_text,
        ),
        el("div", {"id": "status"}, sections.get("status", "")),
    )


def _main(sections: dict[str, str]) -> IrDoc:
    empty = el("div", {"class": "placeholder"}, "compile a grammar to begin")
    return el(
        "div",
        {"id": "main"},
        el(
            "div",
            {"id": "tabs"},
            el("button", {"data-tab": "topology", "class": "on"}, "Topology"),
            el("button", {"data-tab": "railroad"}, "Railroad"),
            el("button", {"data-tab": "verdicts"}, "Verdicts"),
            el("button", {"data-tab": "pipeline"}, "Pipeline"),
            el("button", {"data-tab": "instance"}, "Instance"),
            el("button", {"data-tab": "engine"}, "Engine"),
            el(
                "div",
                {"class": "right"},
                el("button", {"id": "freeze", "hidden": None}, "freeze ⭳"),
            ),
        ),
        el(
            "div",
            {"class": "view", "id": "view-topology"},
            raw(sections["topology"]) if "topology" in sections else empty,
        ),
        el(
            "div",
            {"class": "view", "id": "view-railroad", "hidden": None},
            raw(sections["railroad"]) if "railroad" in sections else empty,
        ),
        el(
            "div",
            {"class": "view", "id": "view-verdicts", "hidden": None},
            raw(sections["verdicts"]) if "verdicts" in sections else empty,
        ),
        el(
            "div",
            {"class": "view", "id": "view-pipeline", "hidden": None},
            raw(sections["pipeline"]) if "pipeline" in sections else empty,
        ),
        el(
            "div",
            {"class": "view", "id": "view-instance", "hidden": None},
            raw(sections["instance"]) if "instance" in sections
            else el("div", {"class": "placeholder"}, "parse an input to begin"),
        ),
        el(
            "div",
            {"class": "view", "id": "view-engine", "hidden": None},
            raw(sections["engine"]) if "engine" in sections
            else el("div", {"class": "placeholder"}, "parse an input to begin"),
        ),
    )


# ── styles: data, not blob — one (selector, declarations) pair each ───

_PALETTE = {
    "--bg": "#14161b", "--panel": "#1c1f26", "--edge": "#2a2e38",
    "--text": "#d6d9e0", "--dim": "#8a90a0", "--accent": "#6ea8fe",
    "--lit": "#7ee0a3", "--cls": "#f0b86e", "--ref": "#6ea8fe",
    "--err": "#ff7a7a", "--cyc": "#d98cf5",
}

_MONO = '13px/1.5 "SF Mono", "Cascadia Mono", Consolas, monospace'

_RULES: tuple[tuple[str, dict[str, str]], ...] = (
    ("*", {"box-sizing": "border-box", "margin": "0"}),
    ("body", {"background": "var(--bg)", "color": "var(--text)", "height": "100vh",
              "display": "flex", "font": _MONO}),
    ("#side", {"width": "380px", "min-width": "260px", "display": "flex",
               "flex-direction": "column", "border-right": "1px solid var(--edge)",
               "background": "var(--panel)"}),
    ("#side header", {"padding": "10px 14px", "display": "flex",
                      "align-items": "baseline", "gap": "8px",
                      "border-bottom": "1px solid var(--edge)"}),
    ("#side header h1", {"font-size": "15px", "letter-spacing": "2px",
                         "color": "var(--accent)"}),
    ("#side header span", {"color": "var(--dim)", "font-size": "11px"}),
    ("#grammar, #input", {"width": "100%", "resize": "none", "border": "0",
                          "outline": "0", "padding": "12px",
                          "background": "var(--panel)", "color": "var(--text)",
                          "font": "inherit", "tab-size": "4"}),
    ("#grammar", {"flex": "1"}),
    ("#input", {"flex": "0 0 26%", "border-top": "1px solid var(--edge)"}),
    ("#grammar[readonly], #input[readonly]", {"color": "var(--dim)"}),
    ("#status", {"padding": "8px 14px", "border-top": "1px solid var(--edge)",
                 "font-size": "12px", "color": "var(--dim)", "min-height": "56px",
                 "white-space": "pre-wrap"}),
    ("#status.err", {"color": "var(--err)"}),
    ("#main", {"flex": "1", "display": "flex", "flex-direction": "column",
               "min-width": "0"}),
    ("#tabs", {"display": "flex", "gap": "2px", "padding": "8px 12px 0",
               "border-bottom": "1px solid var(--edge)"}),
    ("#tabs button", {"background": "none", "border": "1px solid var(--edge)",
                      "border-bottom": "0", "color": "var(--dim)",
                      "padding": "6px 16px", "cursor": "pointer", "font": "inherit",
                      "border-radius": "6px 6px 0 0"}),
    ("#tabs button.on", {"color": "var(--text)", "background": "var(--bg)",
                         "border-color": "var(--accent)"}),
    ("#tabs .right", {"margin-left": "auto", "display": "flex", "gap": "8px",
                      "padding-bottom": "6px"}),
    ("#tabs .right button", {"border-radius": "6px",
                             "border-bottom": "1px solid var(--edge)"}),
    (".view", {"flex": "1", "overflow": "auto", "padding": "18px"}),
    (".view[hidden]", {"display": "none"}),
    ("svg text", {"font": '12px "SF Mono", Consolas, monospace',
                  "fill": "var(--text)"}),
    (".node rect", {"fill": "var(--panel)", "stroke": "var(--edge)"}),
    (".node.start rect", {"stroke": "var(--accent)", "stroke-width": "1.6"}),
    (".node.cyclic rect", {"stroke": "var(--cyc)"}),
    (".node.dim text", {"fill": "var(--dim)"}),
    (".node", {"cursor": "pointer"}),
    (".node:hover rect", {"stroke": "var(--accent)"}),
    (".edge", {"fill": "none", "stroke": "var(--edge)", "stroke-width": "1.2"}),
    (".rr-section", {"margin-bottom": "28px"}),
    (".rr-section h2", {"font-size": "13px", "color": "var(--accent)",
                        "margin-bottom": "6px"}),
    (".rr-section h2 .dim", {"color": "var(--dim)", "font-weight": "normal"}),
    (".rr rect.lit", {"fill": "#1f2a22", "stroke": "var(--lit)"}),
    (".rr text.lit", {"fill": "var(--lit)"}),
    (".rr rect.cls", {"fill": "#2a251c", "stroke": "var(--cls)"}),
    (".rr text.cls", {"fill": "var(--cls)"}),
    (".rr rect.ref", {"fill": "#1c2330", "stroke": "var(--ref)"}),
    (".rr text.ref", {"fill": "var(--ref)"}),
    (".rr g.ref", {"cursor": "pointer"}),
    (".rr g.ref:hover rect", {"stroke-width": "2"}),
    (".rr path.rail", {"fill": "none", "stroke": "var(--dim)",
                       "stroke-width": "1.3"}),
    (".rr text.quant", {"fill": "var(--dim)", "font-size": "10px"}),
    ("circle.dot", {"fill": "var(--dim)"}),
    (".placeholder", {"color": "var(--dim)", "padding": "40px"}),
    (".inst", {"display": "flex", "gap": "18px", "align-items": "flex-start"}),
    (".inst .txt", {"flex": "1", "min-width": "0"}),
    (".inst .txt pre", {"white-space": "pre-wrap", "word-break": "break-all",
                        "background": "var(--panel)", "padding": "14px",
                        "border-radius": "8px"}),
    (".inst .tree", {"flex": "1", "min-width": "0"}),
    (".tree ul", {"list-style": "none", "padding-left": "16px"}),
    (".tree summary", {"cursor": "pointer", "color": "var(--accent)"}),
    (".tree li.leaf", {"color": "var(--dim)"}),
    (".tree code", {"color": "var(--lit)"}),
    (".tree em", {"color": "var(--dim)", "font-style": "normal",
                  "font-size": "11px"}),
    (".tspan.dim", {"opacity": ".65"}),
    (".tspan.hot", {"outline": "1px solid var(--accent)",
                    "background": "#26304a"}),
    (".tree li.hot > details > summary, .tree li.leaf.hot",
     {"background": "#26304a"}),
    (".legend", {"display": "flex", "gap": "16px", "margin-bottom": "12px",
                 "color": "var(--dim)", "flex-wrap": "wrap"}),
    (".badge", {"padding": "1px 8px", "border-radius": "8px",
                "font-size": "11px"}),
    (".verdicts", {"border-collapse": "collapse", "width": "100%"}),
    (".verdicts td", {"padding": "4px 10px", "vertical-align": "top",
                      "border-bottom": "1px solid var(--edge)"}),
    (".verdicts .rule", {"color": "var(--accent)", "cursor": "pointer"}),
    (".notes div", {"color": "var(--dim)", "font-size": "11px"}),
    (".v-predictive .badge", {"background": "#1f2a22", "color": "var(--lit)"}),
    (".v-gated .badge", {"background": "#1c2330", "color": "var(--ref)"}),
    (".v-attempt .badge", {"background": "#2a1f30", "color": "var(--cyc)"}),
    (".v-island .badge", {"background": "#2a251c", "color": "var(--cls)"}),
    (".v-hard .badge", {"background": "#301c1c", "color": "var(--err)"}),
    (".warn", {"color": "var(--err)", "margin-bottom": "8px"}),
    (".okline", {"color": "var(--lit)", "margin-bottom": "8px"}),
    (".timeline", {"white-space": "pre-wrap", "word-break": "break-all",
                   "background": "var(--panel)", "padding": "14px",
                   "border-radius": "8px", "margin-bottom": "10px"}),
    (".tl-p", {"color": "var(--lit)"}),
    (".tl-i", {"color": "var(--cls)", "background": "#2a251c"}),
    (".tl-a", {"color": "var(--cyc)", "background": "#2a1f30"}),
    (".tl-x", {"color": "var(--err)"}),
    (".timeline .cursor", {"outline": "1px solid var(--accent)"}),
    ("#scrub", {"width": "100%", "margin": "8px 0"}),
    ("#evlog", {"max-height": "40vh", "overflow": "auto",
                "background": "var(--panel)", "border-radius": "8px",
                "padding": "8px 0"}),
    (".ev", {"padding": "1px 12px", "color": "var(--dim)"}),
    (".ev b", {"color": "var(--text)", "font-weight": "normal"}),
    (".ev .pos", {"display": "inline-block", "min-width": "48px",
                  "color": "var(--accent)"}),
    (".ev.cur", {"background": "#26304a"}),
    (".ev-island b", {"color": "var(--cls)"}),
    (".ev-verdict b, .ev-probe b, .ev-attempt b", {"color": "var(--cyc)"}),
    (".stage summary", {"cursor": "pointer", "color": "var(--accent)",
                        "margin-bottom": "4px"}),
    (".stage pre", {"background": "var(--panel)", "padding": "10px 14px",
                    "border-radius": "8px", "margin-bottom": "14px",
                    "white-space": "pre-wrap"}),
    (".pl-added", {"color": "var(--lit)"}),
    (".pl-changed", {"color": "var(--cls)"}),
    (".pl-removed", {"color": "var(--err)",
                     "text-decoration": "line-through"}),
    (".pl-same", {"color": "var(--dim)"}),
)


def _css() -> str:
    """The stylesheet from the rule data — root palette first."""
    root = "".join(f"{k}: {v}; " for k, v in _PALETTE.items())
    rules = [f":root {{ {root}}}"]
    for selector, props in _RULES:
        body = "".join(f"{k}: {v}; " for k, v in props.items())
        rules.append(f"{selector} {{ {body}}}")
    return "\n".join(rules)


# ── script: one small named behavior per constant ─────────────────────

_JS_BOOT = """
"use strict";
const MODE = document.body.dataset.mode;
const FLAVOUR = document.body.dataset.flavour;
const status_ = document.getElementById("status");
const editor = document.getElementById("grammar");
const input = document.getElementById("input");
const views = {
  topology: document.getElementById("view-topology"),
  railroad: document.getElementById("view-railroad"),
  verdicts: document.getElementById("view-verdicts"),
  pipeline: document.getElementById("view-pipeline"),
  instance: document.getElementById("view-instance"),
  engine: document.getElementById("view-engine"),
};
document.getElementById("mode-tag").textContent =
  (MODE === "live" ? "live" : "frozen") + " · " + FLAVOUR;
"""

_JS_TABS = """
document.querySelectorAll("#tabs button[data-tab]").forEach(b => {
  b.onclick = () => setTab(b.dataset.tab);
});
function setTab(tab) {
  document.querySelectorAll("#tabs button[data-tab]").forEach(x =>
    x.classList.toggle("on", x.dataset.tab === tab));
  for (const name in views) views[name].hidden = name !== tab;
}
"""

_JS_GOTO = """
document.getElementById("main").addEventListener("click", e => {
  const target = e.target.closest("[data-goto]");
  if (!target) return;
  setTab("railroad");
  const el = document.getElementById("rr-" + target.dataset.goto);
  if (el) el.scrollIntoView({behavior: "smooth", block: "start"});
});
"""

_JS_LIVE = """
if (MODE === "artifact") {
  editor.readOnly = true;
  input.readOnly = true;
} else {
  document.getElementById("freeze").hidden = false;
  document.getElementById("freeze").onclick = () => { location.href = "/freeze"; };
  let timer = null;
  editor.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(compile, 350);
  });
  let ptimer = null;
  input.addEventListener("input", () => {
    clearTimeout(ptimer);
    ptimer = setTimeout(parseInput, 350);
  });
}
"""

_JS_COMPILE = """
async function compile() {
  try {
    const r = await fetch("/compile?flavour=" + encodeURIComponent(FLAVOUR), {
      method: "POST",
      headers: {"Content-Type": "text/plain; charset=utf-8"},
      body: editor.value,
    });
    const body = await r.text();
    if (!r.ok) {
      status_.className = "err";
      status_.textContent = body;
      return;
    }
    swapFragments(body);
  } catch (e) {
    status_.className = "err";
    status_.textContent = "server unreachable — " + e;
  }
}
function swapFragments(body) {
  const stage = document.createElement("div");
  stage.innerHTML = body;
  for (const name in views) {
    const frag = stage.querySelector("#frag-" + name);
    if (frag) views[name].innerHTML = frag.innerHTML;
  }
  status_.className = "";
  const st = stage.querySelector("#frag-status");
  if (st) status_.textContent = st.textContent;
}
"""

_JS_PARSE = """
async function parseInput() {
  try {
    const r = await fetch("/parse", {
      method: "POST",
      headers: {"Content-Type": "text/plain; charset=utf-8"},
      body: input.value,
    });
    const body = await r.text();
    if (!r.ok) {
      status_.className = "err";
      status_.textContent = body;
      return;
    }
    swapFragments(body);
    setTab("instance");
  } catch (e) {
    status_.className = "err";
    status_.textContent = "server unreachable — " + e;
  }
}
"""

_JS_SYNC = """
const inst = views.instance;
inst.addEventListener("mouseover", e => {
  const target = e.target.closest("[data-n]");
  syncHot(target ? target.dataset.n : null);
});
inst.addEventListener("mouseout", () => syncHot(null));
inst.addEventListener("click", e => {
  const target = e.target.closest("[data-n]");
  if (!target) return;
  const twin = [...inst.querySelectorAll('[data-n="' + target.dataset.n + '"]')]
    .find(x => x !== target);
  if (twin) twin.scrollIntoView({behavior: "smooth", block: "center"});
});
function syncHot(n) {
  inst.querySelectorAll(".hot").forEach(x => x.classList.remove("hot"));
  if (n) inst.querySelectorAll('[data-n="' + n + '"]').forEach(x =>
    x.classList.add("hot"));
}
"""

_JS_SCRUB = """
document.getElementById("view-engine").addEventListener("input", e => {
  if (e.target.id !== "scrub") return;
  const view = views.engine;
  const rows = view.querySelectorAll(".ev");
  const idx = Number(e.target.value);
  rows.forEach((row, i) => row.classList.toggle("cur", i === idx));
  const row = rows[idx];
  if (!row) return;
  row.scrollIntoView({block: "nearest"});
  const pos = Number(row.dataset.pos);
  view.querySelectorAll(".timeline .cursor").forEach(x =>
    x.classList.remove("cursor"));
  for (const run of view.querySelectorAll(".timeline [data-a]")) {
    if (Number(run.dataset.a) <= pos && pos < Number(run.dataset.b)) {
      run.classList.add("cursor");
      break;
    }
  }
});
"""

_SCRIPT = (_JS_BOOT + _JS_TABS + _JS_GOTO + _JS_LIVE + _JS_COMPILE
           + _JS_PARSE + _JS_SYNC + _JS_SCRUB)
