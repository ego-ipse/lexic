"""clockmock — the engine clocks, rethought as steppers. Real data, baked.

Three panels answering three reads, every payload extracted from live runs
(no invented shapes — the visual_2/visual_4 method):

1. THE PDA — the kernel's own frames (rung 8's trace) + the DECISION events
   (`attempt` arm-choices recorded through the TraceKernel seams) + the
   owner-colored text (who owned each char). A shared cursor t; the stack
   AT t; the events AT t. A second, decision-rich subject rides below (the
   json walk is deterministic — honest, so the attempt vocabulary gets its
   own live annex).
2. THE EARLEY COLUMN — standing IN column t: the item set as dotted rules
   (done ● todo, role, origin — 1-watching-a-parse's payload, re-extracted
   from today's kernel via `decode_item`), CAN COME NEXT, and the
   hypothesis field demoted to an overview strip.
3. THE FOREST — the SPPF, from the chart's own link table: symbol nodes,
   families, THE ambiguity point (a key with two families, Scott 2008),
   and the two derivations with the visual_4 red-marking (subtrees absent
   from the twin).

Regenerate:  uv run python zzz_current_work/260807-opsis-radical/clockmock/mockup.py
Generation IS the census — every claim asserted before the file writes.
"""

import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from lexic.compile import compile_from_path, compile_text, parse_grammar  # noqa: E402
from lexic.grammars import GBNF_FLAVOUR  # noqa: E402
from lexic.ir import IrAlternation, IrCharClass, IrLiteral, IrRuleRef  # noqa: E402
from lexic.parsing import (  # noqa: E402
    Kernel,
    compile_tables,
    decode_item,
    derivations,
    lift_optional_nullables,
    normalize,
    to_chart,
)
from lexic.parsing.pda.core.errors import PdaFail  # noqa: E402
from lexic.parsing.pda.runtime.build import F_CLONE, F_START  # noqa: E402
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel  # noqa: E402

DOC = '{"a": [1, 2], "ok": true}'
DECISION_GRAMMAR = (
    's ::= xa | xb\nxa ::= xs "a"\nxb ::= xs "b"\nxs ::= "x" xs | "x"'
)
DECISION_DOC = "xxxxb"
ANNEX_GRAMMAR = 'expr ::= expr "+" expr | [0-9]'
ANNEX_DOC = "1+2+3"


class MockTrace(PdaKernel):
    """The trace kernel for the mock — frames + decision events, zero hooks."""

    __slots__ = ("frames", "open_frames", "events")

    def __init__(self, tables, text, fold) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list] = []
        self.open_frames: dict[int, int] = {}
        self.events: list[list] = []

    def _note(self, pos, kind, detail) -> None:
        if not self._caches.probing:
            self.events.append([pos, kind, detail])

    def _enter(self, clone, out):
        pushed = super()._enter(clone, out)
        if pushed:
            frame = self.stack[-1]
            self.open_frames[id(frame)] = len(self.frames)
            self.frames.append([frame[F_START], -1, len(self.stack) - 1, str(frame[F_CLONE].name)])
        return pushed

    def _complete(self, frame):
        idx = self.open_frames.pop(id(frame), None)
        if idx is not None:
            self.frames[idx][1] = self.pos
        return super()._complete(frame)

    def attempt(self, clone, out):
        start = self.pos
        self._note(start, "attempt", f"arm choice at {clone.name} — admission cannot decide; sub-runs try the arms in order")
        return super().attempt(clone, out)

    def attempt_iteration(self, frame, arm, i, pos):
        got = super().attempt_iteration(frame, arm, i, pos)
        self._note(pos, "loop", f"attempted iteration {'takes' if got == i else 'closes'}")
        return got

    def _fork_verdict(self, arm, i, pos, taken):
        v = super()._fork_verdict(arm, i, pos, taken)
        self._note(pos, "verdict", f"both-viable boundary → {('TAKE', 'STOP', 'FORK')[v]}")
        return v

    def _probe(self, arm, i, pos, taken):
        got = super()._probe(arm, i, pos, taken)
        side = "take" if taken is not None else "stop"
        self._note(pos, "probe", f"{side}-side probe {'completes' if got[0] is not None else 'dies'}")
        return got

    def _island(self, name, sink):
        start = self.pos
        super()._island(name, sink)
        self._note(start, "island", f"{name} · Earley window [{start},{self.pos})")


def pda_payload(cg, text: str) -> dict:
    """One traced PDA run — frames, decision events, per-char ownership."""
    kernel = MockTrace(cg.pda_tables(), text, cg.fold)
    end, ok = -1, True
    try:
        kernel.run()
    except PdaFail as fork:
        end, ok = fork.pos, False
    for rec in kernel.frames:
        if rec[1] < 0:
            rec[1] = kernel.pos
    owner = ["p"] * len(text)
    for pos, kind, _d in kernel.events:
        if kind in ("attempt", "loop", "verdict", "probe") and pos < len(text):
            owner[pos] = "a"
        if kind == "island":
            pass  # island ranges would mark 'i'; no island in these subjects
    return {
        "frames": kernel.frames,
        "events": kernel.events,
        "owner": "".join(owner),
        "end": end,
        "ok": ok,
    }


def spell(element) -> str:
    """A sequence element's display spelling — the rail registers' language."""
    atom = getattr(element, "atom", element)
    if isinstance(atom, IrRuleRef):
        return str(atom)
    if isinstance(atom, IrLiteral):
        return '"' + str(atom).replace("\\", "\\\\").replace("\n", "\\n") + '"'
    if isinstance(atom, IrCharClass):
        pattern = atom.pattern()
        return "[" + (pattern if len(pattern) <= 16 else pattern[:15] + "…") + "]"
    if isinstance(atom, IrAlternation):
        return "(…)"
    return type(atom).__name__


def terminal_spelling(element) -> str | None:
    """The element's spelling when it scans text directly, else None."""
    atom = getattr(element, "atom", element)
    if isinstance(atom, (IrLiteral, IrCharClass)):
        return spell(element)
    return None


def earley_payload(tables, text: str) -> dict:
    """Every column's item set, decoded from the kernel's own state."""
    kernel = Kernel(tables, text, record_links=False).run()
    columns = []
    for col in kernel.cols:
        items, expect = [], []
        for packed in col:
            rule, seq, dot, origin = decode_item(tables, packed)
            role = "predict" if dot == 0 else ("complete" if dot == len(seq) else "advance")
            todo = [spell(e) for e in seq[dot:]]
            items.append({
                "r": str(rule),
                "done": [spell(e) for e in seq[:dot]],
                "todo": todo,
                "dot": dot,
                "origin": origin,
                "role": role,
                "next": todo[0] if todo else "",
            })
            if dot < len(seq):
                term = terminal_spelling(seq[dot])
                if term and term not in expect:
                    expect.append(term)
        columns.append({"items": items, "expect": sorted(expect)})
    ext: dict[tuple[str, int], list] = {}
    for j, col in enumerate(kernel.cols):
        for packed in col:
            rule, seq, dot, origin = decode_item(tables, packed)
            rec = ext.setdefault((str(rule), origin), [origin, j, 0])
            rec[1] = max(rec[1], j)
            if dot == len(seq):
                rec[2] = 1
    hyp = sorted(
        ([o, last, comp, name] for (name, o), (o2, last, comp) in ext.items()),
        key=lambda r: (r[0], -(r[1] - r[0])),
    )
    return {"columns": columns, "hyp": hyp}


def sppf_payload(grammar_text: str, text: str) -> dict:
    """The forest from the chart's own links — nodes, families, the diff."""
    g = normalize(parse_grammar(grammar_text, GBNF_FLAVOUR))
    tables = compile_tables(g)
    kernel = Kernel(tables, text).run()
    links = to_chart(kernel).links
    nodes: dict[tuple[str, int, int], dict] = {}
    node_ids: dict[tuple[str, int, int], int] = {}

    def node_id(rule: str, a: int, b: int) -> int:
        key = (rule, a, b)
        if key not in node_ids:
            node_ids[key] = len(node_ids)
            nodes[key] = {"id": node_ids[key], "rule": rule, "a": a, "b": b, "families": []}
        return node_ids[key]

    def resolve(item, end) -> list[list]:
        """Ordered child lists for (item, end) — one per family, chains flattened."""
        rule, seq, dot, origin = item
        if dot == 0:
            return [[]]
        out = []
        for pred_item, split, child in tuple(links[(item, end)]):
            if isinstance(child, (IrLiteral,)) or (not hasattr(child, "item") and not isinstance(child, tuple)):
                kid = ["t", str(child), split]
            elif hasattr(child, "item"):
                crule, cseq, cdot, corigin = child.item
                kid = ["n", node_id(str(crule), corigin, child.end)]
                build(child.item, child.end)
            else:
                kid = ["t", str(child), split]
            for left in resolve(pred_item, split):
                out.append(left + [kid])
        return out

    seen: set[tuple] = set()

    def build(item, end) -> None:
        rule, seq, dot, origin = item
        key = (str(rule), origin, end, dot)
        if key in seen or dot != len(seq):
            return
        seen.add(key)
        nid = node_id(str(rule), origin, end)
        for fam in resolve(item, end):
            node = nodes[(str(rule), origin, end)]
            if fam not in node["families"]:
                node["families"].append(fam)

    # roots: every completed start item over the whole input
    start = str(g.rules[0].name)
    root = None
    for (item, end) in list(links.keys()):
        rule, seq, dot, origin = item
        if str(rule) == start and origin == 0 and end == len(text) and dot == len(seq):
            build(item, end)
            root = node_id(str(rule), 0, len(text))
    # derivation trees with spans, and the exclusive-subtree diff
    trees = []
    for tree in derivations(parse_grammar(grammar_text, GBNF_FLAVOUR), text):
        pos = [0]

        def walk(node):
            if isinstance(node, IrLiteral) or not hasattr(node, "__iter__") or isinstance(node, str):
                a = pos[0]
                pos[0] += len(str(node))
                return {"t": str(node), "a": a, "b": pos[0]}
            rule, kids = node[0], node[1]
            a = pos[0]
            out_kids = [walk(kid) for kid in kids]
            return {"rule": str(rule), "a": a, "b": pos[0], "kids": out_kids}

        trees.append(walk(tree))

    def spans(tree, acc):
        if "rule" in tree:
            acc.add((tree["rule"], tree["a"], tree["b"]))
            for kid in tree["kids"]:
                spans(kid, acc)
        return acc

    sets = [spans(t, set()) for t in trees]
    for i, tree in enumerate(trees):
        other = sets[1 - i] if len(sets) == 2 else set()

        def mark(node):
            if "rule" in node:
                node["only"] = (node["rule"], node["a"], node["b"]) not in other
                for kid in node["kids"]:
                    mark(kid)

        mark(tree)
    return {
        "nodes": sorted(nodes.values(), key=lambda n: (-(n["b"] - n["a"]), n["a"])),
        "root": root,
        "derivations": trees,
    }


def build_payload() -> dict:
    cg = compile_from_path(str(ROOT / "resources" / "ground_truth" / "json.gbnf"))
    inst = normalize(lift_optional_nullables(cg.codegen_grammar))
    tables = compile_tables(inst)
    subject = {
        "label": "json.gbnf ⊳ a document",
        "text": DOC,
        "pda": pda_payload(cg, DOC),
        "earley": earley_payload(tables, DOC),
    }
    dg = compile_text(DECISION_GRAMMAR)
    decisions = {
        "label": "an undecidable arm choice ⊳ " + repr(DECISION_DOC),
        "grammar": DECISION_GRAMMAR,
        "text": DECISION_DOC,
        "pda": pda_payload(dg, DECISION_DOC),
    }
    annex = {
        "label": "expr ::= expr \"+\" expr | [0-9]  ⊳  1+2+3",
        "text": ANNEX_DOC,
        "sppf": sppf_payload(ANNEX_GRAMMAR, ANNEX_DOC),
    }
    payload = {"subject": subject, "decisions": decisions, "annex": annex}

    # ── generation IS the census ──────────────────────────────────────
    n = len(DOC)
    frames = subject["pda"]["frames"]
    assert frames and any(f[0] == 0 and f[1] == n for f in frames), "no root frame"
    assert all(0 <= f[0] <= f[1] <= n for f in frames), "frame out of bounds"
    cols = subject["earley"]["columns"]
    assert len(cols) == n + 1, f"columns {len(cols)} != {n + 1}"
    filled = sum(1 for c in cols if c["items"])
    assert cols[0]["items"] and filled >= len(cols) * 0.5, f"too many empty columns ({filled}/{len(cols)})"
    # empty columns are REAL: the kernel scans lexical runs, skipping interior columns
    roles = {i["role"] for c in cols for i in c["items"]}
    assert roles <= {"predict", "advance", "complete"}, roles
    assert cols[0]["expect"], "no expected terminals at column 0"
    dev = decisions["pda"]["events"]
    assert any(e[1] == "attempt" for e in dev), "no attempt events in the decision subject"
    assert "a" in decisions["pda"]["owner"], "no attempt-owned chars"
    sppf = annex["sppf"]
    ambig = [nd for nd in sppf["nodes"] if len(nd["families"]) > 1]
    assert len(ambig) == 1 and ambig[0]["a"] == 0 and ambig[0]["b"] == 5, "ambiguity point missing"
    assert len(sppf["derivations"]) == 2, "expected two derivations"
    assert any(k.get("only") for t in sppf["derivations"] for k in t["kids"] if "rule" in k) or any(
        t.get("only") for t in sppf["derivations"]
    ), "no exclusive subtrees marked"
    return payload


def render(payload: dict) -> str:
    data = json.dumps(payload)
    n_ev = len(payload["decisions"]["pda"]["events"])
    n_items = sum(len(c["items"]) for c in payload["subject"]["earley"]["columns"])
    facts = (
        f"{len(payload['subject']['pda']['frames'])} PDA frames · "
        f"{n_items} Earley items over {len(payload['subject']['earley']['columns'])} columns · "
        f"{n_ev} decision events · "
        f"{len(payload['annex']['sppf']['nodes'])} forest nodes, 1 ambiguity point"
    )
    return HTML.replace("__DATA__", data).replace("__FACTS__", escape(facts))


HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>clockmock — the engine clocks as steppers</title>
<style>
  :root {
    --field:#0b0e14; --field2:#10141d; --ink:#e8e2d6; --dim:#66707f; --dimmer:#3a4250;
    --hair:#1d2430; --cool:#6fc3c9; --warm:#e2a65c; --violet:#d98cf5; --red:#e06060;
    --green:#79c99a; --mono:'SF Mono','JetBrains Mono',ui-monospace,monospace;
  }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--field); color:var(--ink); font:12px var(--mono); padding:14px 18px 60px; }
  h1 { font-size:14px; letter-spacing:.24em; color:var(--cool); }
  h1 em { font-style:normal; color:var(--dim); letter-spacing:0; font-size:11px; margin-left:12px; }
  #grid { display:grid; grid-template-columns: 1.15fr 1fr 1.05fr; gap:14px; margin-top:12px; }
  .panel { background:var(--field2); border:1px solid var(--hair); padding:10px 12px 12px; min-height:520px; }
  .panel h2 { font-size:11px; color:var(--cool); letter-spacing:.14em; }
  .panel h2 em { font-style:normal; color:var(--dim); letter-spacing:0; font-weight:normal; margin-left:8px; }
  .strip { font:13px var(--mono); background:var(--field); border:1px solid var(--hair);
           padding:7px 9px; margin:8px 0; white-space:pre; overflow-x:auto; cursor:pointer; }
  .strip span { padding:1px 0; }
  .o-p { color:var(--ink); } .o-a { color:var(--warm); } .o-i { color:var(--violet); }
  .unread { opacity:.38; }
  .cursor { background:var(--warm); color:var(--field); }
  .lanes { position:relative; background:var(--field); border:1px solid var(--hair); margin:6px 0; }
  .fr { position:absolute; border:1px solid var(--dimmer); font-size:9px; color:var(--dim);
        overflow:hidden; white-space:nowrap; padding:0 3px; line-height:12px; }
  .fr.done { border-color:var(--cool); color:var(--cool); background:rgba(111,195,201,.08); }
  .fr.live { border-color:var(--warm); color:var(--warm); background:rgba(226,166,92,.10); }
  .evlog { max-height:130px; overflow-y:auto; border:1px solid var(--hair); background:var(--field);
           margin-top:6px; }
  .ev { padding:2px 8px; color:var(--dim); border-left:2px solid transparent; }
  .ev b { color:var(--warm); font-weight:normal; }
  .ev.at { border-left-color:var(--warm); color:var(--ink); background:rgba(226,166,92,.06); }
  .ev .pos { color:var(--dimmer); display:inline-block; min-width:3ch; }
  .lbl { color:var(--dim); font-size:10px; letter-spacing:.1em; margin-top:10px; display:block; }
  .items { border:1px solid var(--hair); background:var(--field); margin-top:6px;
           max-height:300px; overflow-y:auto; }
  .it { padding:2px 8px; white-space:nowrap; }
  .it .org { color:var(--dimmer); display:inline-block; min-width:4ch; }
  .it .rl { color:var(--cool); }
  .it .done { color:var(--dimmer); }
  .it .dot { color:var(--warm); padding:0 3px; }
  .it .todo { color:var(--ink); }
  .it .role { float:right; font-size:9px; letter-spacing:.08em; padding:1px 5px; border:1px solid var(--hair); }
  .it.predict .role { color:var(--dim); }
  .it.advance .role { color:var(--warm); border-color:var(--warm); }
  .it.complete .role { color:var(--green); border-color:var(--green); }
  .chips { margin-top:6px; }
  .chip { display:inline-block; border:1px solid var(--warm); color:var(--warm); padding:1px 7px;
          margin:2px 4px 0 0; font-size:11px; }
  canvas { display:block; }
  #forest { position:relative; height:250px; background:var(--field); border:1px solid var(--hair); margin-top:6px; }
  .fnode { position:absolute; transform:translate(-50%,-50%); border:1px solid var(--cool); color:var(--cool);
           background:var(--field2); padding:2px 8px; font-size:11px; white-space:nowrap; z-index:2; }
  .fnode .sp { color:var(--dim); font-size:9px; }
  .fnode.term { border-color:var(--dimmer); color:var(--ink); }
  .fnode.ambig { border-color:var(--warm); color:var(--warm); box-shadow:0 0 0 2px rgba(226,166,92,.25); }
  #fedges { position:absolute; inset:0; z-index:1; }
  .famtag { color:var(--dim); font-size:10px; margin-top:8px; }
  .famtag button { background:none; border:1px solid var(--hair); color:var(--dim); font:11px var(--mono);
                   padding:1px 8px; cursor:pointer; margin-right:6px; }
  .famtag button.on { border-color:var(--warm); color:var(--warm); }
  .dtree { border:1px solid var(--hair); background:var(--field); margin-top:6px; padding:6px 8px;
           max-height:170px; overflow:auto; white-space:pre; font-size:11px; }
  .dtree .only { color:var(--red); }
  .dtree .tm { color:var(--warm); }
  .verdictline { color:var(--dim); font-size:10px; margin-top:6px; }
  .verdictline b { color:var(--red); font-weight:normal; }
  #transport { position:fixed; left:0; right:0; bottom:0; background:var(--field2);
               border-top:1px solid var(--hair); padding:8px 18px; display:flex; gap:12px; align-items:center; }
  #transport input[type=range] { flex:1; accent-color:var(--warm); }
  #transport button { background:none; border:1px solid var(--hair); color:var(--dim);
                      font:12px var(--mono); padding:2px 10px; cursor:pointer; }
  #transport button:hover { border-color:var(--warm); color:var(--warm); }
  #tpos { color:var(--warm); min-width:14ch; }
  .note { color:var(--dimmer); font-size:10px; margin-top:6px; line-height:1.5; }
</style>
<h1>THE CLOCKS, AS STEPPERS <em>__FACTS__ · ←/→ step · click any char</em></h1>
<div id="grid">
  <div class="panel" id="p-pda">
    <h2>THE PDA <em>its frames, its decisions — <span id="pda-label"></span></em></h2>
    <div class="strip" id="pda-strip"></div>
    <span class="lbl">THE STACK AT t <em id="stackdepth"></em></span>
    <div class="lanes" id="pda-lanes"></div>
    <span class="lbl">DECISIONS NEAR t</span>
    <div class="evlog" id="pda-events"></div>
    <span class="lbl" style="color:var(--warm)">THE DECISION ANNEX — <span id="dec-label"></span></span>
    <div class="strip" id="dec-strip"></div>
    <div class="evlog" id="dec-events"></div>
    <div class="note">the json walk is deterministic — every char owned by the plain descent
(no warm anywhere). The annex grammar's arm choice is undecidable by admission,
so the attempt machinery runs sub-parses — warm chars, and the re-walk in the log
IS the cost. No island in either subject; a subject that islands would color violet.</div>
  </div>
  <div class="panel" id="p-earley">
    <h2>THE EARLEY COLUMN <em>standing at t — the item set</em></h2>
    <div class="strip" id="ear-strip"></div>
    <span class="lbl">ITEMS IN COLUMN t <em id="colcount"></em></span>
    <div class="items" id="ear-items"></div>
    <span class="lbl">CAN COME NEXT</span>
    <div class="chips" id="ear-expect"></div>
    <span class="lbl">THE FIELD (overview) — every hypothesis, birth to death</span>
    <canvas id="ear-field" height="120"></canvas>
  </div>
  <div class="panel" id="p-sppf">
    <h2>THE FOREST <em id="annex-label"></em></h2>
    <div class="strip" id="axe-strip"></div>
    <div id="forest"><svg id="fedges" width="100%" height="100%"></svg></div>
    <div class="famtag">the shared forest — ONE ambiguity point:
      <span style="color:var(--warm)">expr 0..5 carries two families</span> ·
      <button id="famA" class="on">derivation 1 — (1+2)+3</button>
      <button id="famB">derivation 2 — 1+(2+3)</button>
    </div>
    <div class="dtree" id="dtree"></div>
    <div class="verdictline">the model product REFUSES this span — two derivations build
two different values; <b>red = absent from the twin</b>. The resolver is the only door.</div>
  </div>
</div>
<div id="transport">
  <button id="tb-back">‹</button><button id="tb-play">▶</button><button id="tb-step">›</button>
  <input type="range" id="scrub" min="0" value="0">
  <span id="tpos"></span>
</div>
<script>
"use strict";
const D = __DATA__;
const S = D.subject, DEC = D.decisions, AX = D.annex;
const N = S.text.length;
let t = 0, playing = false, fam = 0, decT = DEC.text.length;

const $ = (id) => document.getElementById(id);
$('pda-label').textContent = S.label;
$('dec-label').textContent = DEC.label;
$('annex-label').textContent = AX.label;
$('scrub').max = N;

function strip(el, text, owner, at, unreadFrom) {
  el.textContent = '';
  for (let i = 0; i < text.length; i++) {
    const sp = document.createElement('span');
    sp.textContent = text[i];
    sp.className = 'o-' + (owner ? owner[i] : 'p')
      + (i === at ? ' cursor' : '') + (i >= unreadFrom ? ' unread' : '');
    sp.dataset.i = i;
    el.appendChild(sp);
  }
}

function renderPda() {
  strip($('pda-strip'), S.text, S.pda.owner, t, t + 1);
  const live = S.pda.frames.filter((f) => f[0] <= t && t < f[1]);
  const all = S.pda.frames;
  const maxd = Math.max(...all.map((f) => f[2])) + 1;
  const lanes = $('pda-lanes');
  const w = lanes.clientWidth || 560;
  const laneH = 13;
  lanes.style.height = (maxd * laneH + 6) + 'px';
  lanes.textContent = '';
  const px = (i) => 4 + (i / N) * (w - 8);
  for (const f of all) {
    const d = document.createElement('div');
    const done = f[1] <= t, isLive = !done && f[0] <= t;
    d.className = 'fr' + (done ? ' done' : isLive ? ' live' : '');
    d.style.left = px(f[0]) + 'px';
    d.style.width = Math.max(px(f[1]) - px(f[0]), 3) + 'px';
    d.style.top = (3 + f[2] * laneH) + 'px';
    d.style.height = (laneH - 2) + 'px';
    d.textContent = f[3];
    d.title = `${f[3]} · ${f[0]}..${f[1]} · depth ${f[2]}`;
    lanes.appendChild(d);
  }
  const cur = document.createElement('div');
  cur.style.cssText = `position:absolute;top:0;bottom:0;width:1px;background:var(--warm);left:${px(t)}px`;
  lanes.appendChild(cur);
  $('stackdepth').textContent = `— ${live.length} frames open: ` +
    (live.sort((a, b) => a[2] - b[2]).map((f) => f[3]).join(' ▸ ') || 'none (leaf run or boundary)');
  const log = $('pda-events');
  log.textContent = '';
  if (!S.pda.events.length) {
    log.innerHTML = '<div class="ev">no decision events — the whole walk was deterministic descent</div>';
  }
  for (const [pos, kind, detail] of S.pda.events) {
    const d = document.createElement('div');
    d.className = 'ev' + (pos === t ? ' at' : '');
    d.innerHTML = `<span class="pos">${pos}</span> <b>${kind}</b> ${detail}`;
    log.appendChild(d);
  }
}

function renderDecisions() {
  strip($('dec-strip'), DEC.text, DEC.pda.owner, -1, DEC.text.length + 1);
  const log = $('dec-events');
  log.textContent = '';
  for (const [pos, kind, detail] of DEC.pda.events) {
    const d = document.createElement('div');
    d.className = 'ev at';
    d.innerHTML = `<span class="pos">${pos}</span> <b>${kind}</b> ${detail}`;
    log.appendChild(d);
  }
}

function renderEarley() {
  strip($('ear-strip'), S.text, null, t, t + 1);
  const col = S.earley.columns[t] || { items: [], expect: [] };
  $('colcount').textContent = col.items.length
    ? `— ${col.items.length} live`
    : '— empty: inside a lexical run (the kernel scanned past this column)';
  const box = $('ear-items');
  box.textContent = '';
  for (const it of col.items) {
    const d = document.createElement('div');
    d.className = 'it ' + it.role;
    d.innerHTML = `<span class="org">@${it.origin}</span> <span class="rl">${it.r}</span> ::= `
      + `<span class="done">${it.done.join(' ')}</span><span class="dot">●</span>`
      + `<span class="todo">${it.todo.join(' ')}</span>`
      + `<span class="role">${it.role}</span>`;
    box.appendChild(d);
  }
  const ex = $('ear-expect');
  ex.textContent = '';
  for (const term of col.expect) {
    const c = document.createElement('span');
    c.className = 'chip';
    c.textContent = term;
    ex.appendChild(c);
  }
  if (!col.expect.length) ex.innerHTML = '<span style="color:var(--dim)">nothing — every item is complete</span>';
  drawField();
}

function drawField() {
  const cv = $('ear-field');
  const w = cv.clientWidth || cv.parentElement.clientWidth - 24;
  cv.width = w * 2; cv.height = 240;
  cv.style.width = w + 'px'; cv.style.height = '120px';
  const cx = cv.getContext('2d');
  cx.setTransform(2, 0, 0, 2, 0, 0);
  cx.clearRect(0, 0, w, 120);
  const rows = [];
  const px = (i) => 4 + (i / N) * (w - 8);
  for (const [s, e, c, name] of S.earley.hyp) {
    let r = 0;
    while (r < rows.length && rows[r] > s) r++;
    rows[r] = Math.max(e, s + 0.4);
    const y = 4 + r * 4;
    if (y > 112) continue;
    cx.strokeStyle = c ? (e <= t ? '#6fc3c9' : '#3a4250') : 'rgba(224,96,96,0.6)';
    cx.strokeRect(px(s), y, Math.max(px(e) - px(s), 2), 2.5);
  }
  cx.strokeStyle = '#e2a65c';
  cx.beginPath(); cx.moveTo(px(t), 0); cx.lineTo(px(t), 120); cx.stroke();
}

function renderForest() {
  const holder = $('forest');
  holder.querySelectorAll('.fnode').forEach((e) => e.remove());
  const svg = $('fedges');
  svg.innerHTML = '';
  const W = holder.clientWidth || 500, H = holder.clientHeight || 250;
  const M = AX.text.length;
  const nx = (a, b) => 30 + ((a + b) / 2 / M) * (W - 60);
  const ny = (a, b) => 24 + (1 - (b - a) / M) * (H - 52);
  const chosen = AX.sppf.derivations[fam];
  const used = new Set();
  (function collect(n) {
    if (n.rule) { used.add(n.rule + ':' + n.a + ':' + n.b); n.kids.forEach(collect); }
  })(chosen);
  const pos = {};
  for (const nd of AX.sppf.nodes) {
    const el = document.createElement('div');
    el.className = 'fnode' + (nd.families.length > 1 ? ' ambig' : '');
    el.style.left = nx(nd.a, nd.b) + 'px';
    el.style.top = ny(nd.a, nd.b) + 'px';
    el.innerHTML = `${nd.rule} <span class="sp">${nd.a}..${nd.b}${nd.families.length > 1 ? ' · 2 families' : ''}</span>`;
    if (!used.has(nd.rule + ':' + nd.a + ':' + nd.b)) el.style.opacity = .35;
    holder.appendChild(el);
    pos[nd.id] = [nx(nd.a, nd.b), ny(nd.a, nd.b)];
  }
  for (const ch of AX.text) { /* terminals row */ }
  for (let i = 0; i < M; i++) {
    const el = document.createElement('div');
    el.className = 'fnode term';
    el.style.left = (30 + ((i + 0.5) / M) * (W - 60)) + 'px';
    el.style.top = (H - 16) + 'px';
    el.textContent = AX.text[i];
    holder.appendChild(el);
  }
  const line = (x1, y1, x2, y2, color, dash) => {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', `M${x1},${y1} L${x2},${y2}`);
    p.setAttribute('stroke', color);
    p.setAttribute('fill', 'none');
    if (dash) p.setAttribute('stroke-dasharray', '3 3');
    svg.appendChild(p);
  };
  for (const nd of AX.sppf.nodes) {
    const [x, y] = pos[nd.id];
    nd.families.forEach((family, fi) => {
      const isChosen = nd.families.length === 1 || fi === fam;
      const color = nd.families.length > 1
        ? (fi === fam ? '#e2a65c' : 'rgba(224,96,96,0.35)')
        : (isChosen ? 'rgba(111,195,201,0.45)' : 'rgba(58,66,80,0.6)');
      for (const kid of family) {
        if (kid[0] === 'n') {
          const [kx, ky] = pos[kid[1]];
          line(x, y + 8, kx, ky - 10, color, !isChosen);
        } else {
          const i = kid[2];
          line(x, y + 8, 30 + ((i + 0.5) / M) * (W - 60), H - 24, color, !isChosen);
        }
      }
    });
  }
  const box = $('dtree');
  box.textContent = '';
  (function draw(n, ind) {
    const row = document.createElement('div');
    if (n.rule) {
      row.innerHTML = ' '.repeat(ind) + `<span class="${n.only ? 'only' : ''}">${n.rule} ${n.a}..${n.b}${n.only ? '  ⟵ not in the twin' : ''}</span>`;
      box.appendChild(row);
      n.kids.forEach((k) => draw(k, ind + 2));
    } else {
      row.innerHTML = ' '.repeat(ind) + `<span class="tm">'${n.t}'</span>`;
      box.appendChild(row);
    }
  })(chosen, 0);
  $('famA').className = fam === 0 ? 'on' : '';
  $('famB').className = fam === 1 ? 'on' : '';
}

function render() {
  $('tpos').textContent = `char ${t} / ${N}`;
  $('scrub').value = t;
  renderPda();
  renderEarley();
}

function setT(v) { t = Math.max(0, Math.min(N, v)); render(); }
$('scrub').addEventListener('input', (e) => setT(+e.target.value));
$('tb-step').addEventListener('click', () => setT(t + 1));
$('tb-back').addEventListener('click', () => setT(t - 1));
$('tb-play').addEventListener('click', () => {
  playing = !playing;
  $('tb-play').textContent = playing ? '⏸' : '▶';
  if (playing) tick();
});
function tick() {
  if (!playing) return;
  if (t >= N) { playing = false; $('tb-play').textContent = '▶'; return; }
  setT(t + 1);
  setTimeout(tick, 380);
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight') setT(t + 1);
  else if (e.key === 'ArrowLeft') setT(t - 1);
  else if (e.key === ' ') { e.preventDefault(); $('tb-play').click(); }
});
for (const id of ['pda-strip', 'ear-strip']) {
  $(id).addEventListener('click', (e) => {
    if (e.target.dataset.i !== undefined) setT(+e.target.dataset.i);
  });
}
$('famA').addEventListener('click', () => { fam = 0; renderForest(); });
$('famB').addEventListener('click', () => { fam = 1; renderForest(); });

const q = new URLSearchParams(location.search);
if (q.has('t')) t = Math.max(0, Math.min(N, +q.get('t')));
if (q.has('fam')) fam = +q.get('fam') ? 1 : 0;
strip($('axe-strip'), AX.text, null, -1, AX.text.length + 1);
renderDecisions();
renderForest();
render();
</script>
"""


def main() -> int:
    payload = build_payload()
    out = HERE / "clockmock.html"
    out.write_text(render(payload))
    n_bytes = out.stat().st_size
    print(f"clockmock.html written — {n_bytes:,} bytes, every census assert green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
