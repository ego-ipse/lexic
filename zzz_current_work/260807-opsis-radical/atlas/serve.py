"""opsis-radical/facets — one subject, four facets, no windows.

The instrument holds the subject: a grammar, a document, a parsed model, and the
span fold derived from the model's own emit stream. The browser is the leaf — it
receives emitted frames (line-oriented plain text, no JSON anywhere) and sends
back gestures: a cursor, a selection, a retype. An edit is a RE-READING: the
document text is spliced and lexic parses it again, because grammar is the
ground truth and the text is primary — every facet re-derives or the engine
refuses in its own words.

Run from the repo root (fixture: meta | vyx | long):

    uv run python zzz_current_work/260807-opsis-radical/facets/serve.py [fixture] [port]
    uv run python zzz_current_work/260807-opsis-radical/facets/serve.py [fixture] --census
"""

import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

from lexic.compile import compile_ast, compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNone,
    IrNot,
    IrRuleRef,
    IrSequence,
)
from lexic.model import GrammarModel
from lexic.parsing import Kernel, PdaKernel, compile_tables, decode_item, earley_model, lift_optional_nullables, normalize
from lexic.parsing.pda.compiler import flatten as _flat
from lexic.parsing.pda.runtime.build import F_CLONE, F_START
from lexic.parsing.pda.core.errors import PdaFail

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEAF = HERE / "leaf"
# The three flavour spellings of a rule head: GBNF `::=`, ABNF `=` / `=/`, EBNF `=`.
RULE_LINE = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")


class Span(NamedTuple):
    """One model occurrence on the text axis, carrying its authored rule name."""

    start: int
    end: int
    depth: int
    rule: str
    field: str


def first(first_meaning: object, _witness: object) -> object:
    """The explicit ambiguity opt-out — a deterministic first-derivation resolver.

    No fixture needs it any more: the metagrammar stopped being ambiguous when
    ``relax_non_semantic`` was narrowed to nullable noise rules (see
    ``../../260807-pda-linearity/FINDING.md``). Kept as the instrument's opt-out channel — a
    subject that needs one sets ``self.resolve``, and the whole instrument
    branches on that switch.
    """
    return first_meaning


class Subject:
    """The reading: reader text, document text, model, spans — and how to re-read."""

    def __init__(self, key: str, doc: str | None = None) -> None:
        self.key = key
        if key == "long":
            self.compiled = compile_from_path(str(ROOT / "resources" / "ground_truth" / "json.gbnf"))
            self.reader_text = (ROOT / "resources" / "ground_truth" / "json.gbnf").read_text()
            self.reader_desc = "json.gbnf"
            self.doc_path = HERE.parent / "tk" / "fixtures_long.json"
            self.graph_ast = self.compiled.grammar
            self.corrupt_at = len(self.doc_path.read_text()) // 2
        elif key == "abnf":
            self.compiled = compile_ast(ABNF_FLAVOUR.grammar)
            self.reader_text = str(ABNF_FLAVOUR.apply(ABNF_FLAVOUR.grammar))
            self.reader_desc = (f"the ABNF metagrammar ({len(ABNF_FLAVOUR.grammar.rules)} rules), "
                                "spelled by its own emitter")
            self.doc_path = ROOT / "resources" / "ground_truth" / "json.abnf"
            self.graph_ast = ABNF_FLAVOUR.grammar
            self.corrupt_at = 0
        elif key in ("meta", "vyx"):
            self.compiled = compile_ast(GBNF_FLAVOUR.grammar)
            self.reader_text = str(GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar))
            self.reader_desc = "the GBNF metagrammar (90 rules), spelled by its own emitter"
            name = "vyx.gbnf" if key == "vyx" else "json.gbnf"
            self.doc_path = ROOT / "resources" / "ground_truth" / name
            self.graph_ast = GBNF_FLAVOUR.grammar
            # A control char mid-document is VALID inside a GBNF comment
            # (cmchar admits \x00-\t) — measured, not assumed. Corrupt at 0,
            # where no line form can start with \x01.
            self.corrupt_at = 0
        elif key in ("decide", "amb"):
            # The observation fixtures: decisions (an undecidable arm choice —
            # the attempt machinery fires at every entry) and ambiguity (429
            # derivations; the reading exists via the `first` resolver, the
            # explicit opt-out — ambiguity becomes OBSERVABLE, never silent).
            gpath = HERE / "fixtures" / f"{key}.gbnf"
            self.compiled = compile_from_path(str(gpath))
            self.reader_text = gpath.read_text()
            self.reader_desc = (f"{key}.gbnf — an undecidable arm choice" if key == "decide"
                                else f"{key}.gbnf — an ambiguous sum, read via the first resolver")
            self.doc_path = HERE / "fixtures" / f"{key}.txt"
            self.graph_ast = self.compiled.grammar
            self.corrupt_at = 0
        else:
            # A file pair: any grammar the pipeline compiles, any document it reads.
            gpath = Path(key)
            if not gpath.is_file():
                raise SystemExit(f"no fixture and no grammar file named '{key}'")
            if doc is None:
                raise SystemExit("a file grammar needs a document: serve.py <grammar> <doc> [port]")
            self.compiled = compile_from_path(str(gpath))
            self.reader_text = gpath.read_text()
            self.reader_desc = gpath.name
            self.doc_path = Path(doc)
            self.graph_ast = self.compiled.grammar
            self.corrupt_at = 0
        self.document = self.doc_path.read_text()
        self.resolve = first if key == "amb" else None
        self.edges, self.rule_depth = rule_graph(self.graph_ast)
        self.generation = 0
        self.t = 0.0
        self.selection = -1
        self.policy: dict[str, str] = {}
        self.lock = threading.Lock()
        self.model: GrammarModel
        self.spans: list[Span]
        self.seconds: float
        self.faithful: bool
        self.route2: dict[str, str] = {}
        self.clock: dict = {"status": "pending"}
        self._instance_tables = None
        self._earley_kernel = None
        start_clone = self.compiled.pda_tables().program.start
        if isinstance(start_clone, _flat.FlatClone):
            clones, aedges, adepth = automaton_walk(start_clone)
        else:
            clones, aedges, adepth = [], [], {}  # the start itself is an island — no PDA machine
        self.auto_clones = clones
        self.auto_edges = aedges
        self.auto_depth = adepth
        self.auto_cid = {id(c): i for i, c in enumerate(clones)}
        self.verdicts = rule_verdicts(self.compiled)
        self.read(self.document)

    def read(self, text: str) -> None:
        """One reading — parse, verify fidelity, fold spans. Raises on refusal."""
        t0 = time.perf_counter()
        model = self.compiled.parse(text, resolve=self.resolve)
        self.seconds = time.perf_counter() - t0
        self.document = text
        self.model = model
        self.faithful = model.to_text() == text
        self.spans = fold_spans(model, text)
        self.generation += 1
        self.route2 = {"status": "pending"}
        threading.Thread(target=self.other_route, args=(self.generation,), daemon=True).start()
        self.clock = {"status": "pending"}
        threading.Thread(target=self.clock_route, args=(self.generation,), daemon=True).start()

    def other_route(self, generation: int) -> None:
        """Run the road NOT taken, in the background — observation, never product.

        PDA-routed subjects get an explicit Earley run and a parity verdict;
        resolver-routed subjects get the PDA's honest end (the probe-fork) —
        the inversion is the content. Results are discarded if a re-read
        moved the generation while this ran.
        """
        t0 = time.perf_counter()
        if self.resolve is None:
            try:
                instance = normalize(lift_optional_nullables(self.compiled.codegen_grammar))
                other = earley_model(instance, self.document, self.compiled.fold)
                seconds = time.perf_counter() - t0
                parity = "holds" if (other == self.model and other.to_text() == self.document) else "FAILS"
                result = {"status": "done", "name": "Earley", "seconds": f"{seconds:.2f}", "parity": parity}
            except Exception as refusal:
                result = {"status": "failed", "name": "Earley", "words": str(refusal)[:160]}
        else:
            try:
                PdaKernel(self.compiled.pda_tables(), self.document, self.compiled.fold).run()
                result = {"status": "done", "name": "PDA", "seconds": f"{time.perf_counter() - t0:.2f}",
                          "parity": "unmeasured"}
            except PdaFail as fork:
                result = {"status": "failed", "name": "PDA", "pos": str(fork.pos),
                          "words": str(fork)[:160]}
        with self.lock:
            if self.generation == generation:
                self.route2 = result

    def clock_route(self, generation: int) -> None:
        """Build both engine clocks in the background — observation, never product.

        The PDA's decision sequence (entries + real attempts per position) and
        Earley's chart columns (items per position) over the same document
        coordinate. Results are discarded if a re-read moved the generation.
        """
        result: dict = {"status": "done"}
        try:
            ck = ClockKernel(self.compiled.pda_tables(), self.document, self.compiled.fold,
                             cid_of=self.auto_cid)
            try:
                ck.run()
                result["pda_end"] = -1
            except PdaFail as fork:
                result["pda_end"] = fork.pos  # the inversion is content
                result["pda_failed"] = "1"  # even a positionless failure is a failure
            for rec in ck.frames:
                if rec[1] < 0:
                    rec[1] = max(ck.pos, rec[0])  # the live stack at death closes here
            result["frames"] = ck.frames
            result["events"] = ck.events
        except Exception as err:
            result["pda_error"] = str(err)[:160]
        try:
            if self._instance_tables is None:
                instance = normalize(lift_optional_nullables(self.compiled.codegen_grammar))
                self._instance_tables = compile_tables(instance)
            kernel = Kernel(self._instance_tables, self.document, record_links=False).run()
            self._earley_kernel = kernel  # retained for /column — the at-cursor item sets
            # every hypothesis (rule, origin) — born at origin, alive to its
            # last column, completed if a final-dot item ever appeared
            ext: dict[tuple[str, int], list] = {}
            for j, col in enumerate(kernel.cols):
                for packed in col:
                    rule, seq, dot, origin = decode_item(self._instance_tables, packed)
                    rec = ext.get((str(rule), origin))
                    if rec is None:
                        rec = ext[(str(rule), origin)] = [origin, j, 0]
                    if j > rec[1]:
                        rec[1] = j
                    if dot == len(seq):
                        rec[2] = 1
            hyp = [[o, last, comp, name] for (name, o), (o2, last, comp) in ext.items()]
            hyp.sort(key=lambda r: (r[0], -(r[1] - r[0])))
            dropped = 0
            if len(hyp) > 60000:
                hyp.sort(key=lambda r: (-r[2], -(r[1] - r[0])))
                dropped = len(hyp) - 60000
                hyp = hyp[:60000]
                hyp.sort(key=lambda r: (r[0], -(r[1] - r[0])))
            result["hyp"] = hyp
            result["dropped"] = dropped
        except Exception as err:
            result["earley_error"] = str(err)[:160]
        with self.lock:
            if self.generation == generation:
                self.clock = result

    def save_held(self) -> str:
        """Why a save must not write, or empty when writing is allowed."""
        if "ground_truth" in str(self.doc_path):
            return "the document is repo ground-truth corpus; the instrument will not overwrite it"
        return ""

    def frontier(self, text: str) -> int:
        """The PDA's deepest verified position on ``text``, read from its own words.

        Read off the PUBLIC parse surface now: a refused parse carries a
        ``Refusal`` readout (position, rule, expected-next), so this no longer
        reaches past the product into the engine floor — nor regexes prose.
        -1 when the text parses, or when the refusal carries no position.
        """
        try:
            self.compiled.parse(text, resolve=self.resolve)
        except UnsupportedConstructError as refusal:
            return refusal.readout.pos if refusal.readout else -1
        return -1

    def rule_lines(self) -> list[tuple[str, int, int]]:
        """Where each rule is defined in the reader text — name, first line, last line."""
        lines = self.reader_text.split("\n")
        heads = [(m.group(1), i) for i, line in enumerate(lines) if (m := RULE_LINE.match(line))]
        out = []
        for k, (name, start) in enumerate(heads):
            stop = heads[k + 1][1] - 1 if k + 1 < len(heads) else len(lines) - 1
            out.append((name, start, stop))
        return out


def rule_graph(ast) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Reference edges and BFS depth from the start rule — the graph facet's truth.

    Edges come from the AST's own ``IrRuleRef`` leaves; depth is derivation
    distance from the start rule (-1 for rules the start never reaches).
    """
    edges: list[tuple[str, str]] = []
    for rule in ast.rules:
        seen: set[str] = set()
        stack = [rule.body]
        while stack:
            node = stack.pop()
            if isinstance(node, IrRuleRef):
                name = str(node)
                if name not in seen:
                    seen.add(name)
                    edges.append((str(rule.name), name))
                continue
            stack.extend(node.children())
    out: dict[str, list[str]] = {}
    for a, b in edges:
        out.setdefault(a, []).append(b)
    start = str(ast.rules[0].name)
    depth = {str(r.name): -1 for r in ast.rules}
    depth[start] = 0
    frontier = [start]
    while frontier:
        nxt = []
        for name in frontier:
            for ref in out.get(name, []):
                if depth.get(ref, 0) == -1:
                    depth[ref] = depth[name] + 1
                    nxt.append(ref)
        frontier = nxt
    return edges, depth


_MODE_WORD = {
    _flat.BUILD_ALT: "alt",
    _flat.BUILD_SEQ: "seq",
    _flat.BUILD_DISPATCH: "dispatch",
    _flat.BUILD_VALUE_STR: "value_str",
    _flat.BUILD_TRANSPARENT: "group",
}


def automaton_walk(start) -> tuple[list, list[tuple[int, int]], dict[int, int]]:
    """The compiled machine — every reachable clone, its calls, its BFS depth.

    Follows what the runtime follows: arm refs (``OP_REF``/``OP_REF1``/
    ``OP_GRP``/``OP_VSTR``), dispatch targets, dispatch defaults, and attempt
    sub-clones. Nodes are CLONES, not rules — the same rule name appearing
    many times IS the machine (context clones per FOLLOW tail).
    """
    seen: dict[int, int] = {}
    clones: list = []
    edges: list[tuple[int, int]] = []
    work = [start]
    while work:
        clone = work.pop()
        if id(clone) in seen:
            continue
        seen[id(clone)] = len(clones)
        clones.append(clone)
        targets = []
        if clone.mode == _flat.BUILD_DISPATCH:
            targets.extend(target for _ch, _neg, target in clone.selectors)
            if clone.default is not None and clone.default is not _flat.DISPATCH_EMPTY:
                targets.append(clone.default)
        else:
            for arm in _flat._clone_arms(clone):
                for kind, payload in zip(arm.kinds, arm.payloads):
                    if kind in (_flat.OP_REF, _flat.OP_REF1, _flat.OP_GRP, _flat.OP_VSTR):
                        targets.append(payload)
        if clone.attempt is not None:
            targets.extend(entry[-1] for entry in clone.attempt[1])
        for target in targets:
            if isinstance(target, _flat.FlatClone):
                edges.append((id(clone), id(target)))
                work.append(target)
    edge_idx = [(seen[a], seen[b]) for a, b in edges]
    depth = {0: 0}
    adj: dict[int, list[int]] = {}
    for a, b in edge_idx:
        adj.setdefault(a, []).append(b)
    frontier = [0]
    while frontier:
        nxt = []
        for a in frontier:
            for b in adj.get(a, []):
                if b not in depth:
                    depth[b] = depth[a] + 1
                    nxt.append(b)
        frontier = nxt
    return clones, edge_idx, depth


def clone_flags(clone) -> str:
    """The clone's decision structure as flag letters (a=attempt, l=leaf, k/p/s gates)."""
    flags = ""
    if clone.attempt is not None:
        flags += "a"
    if clone.leaf:
        flags += "l"
    if clone.kwin_selectors is not None:
        flags += "k"
    if clone.pn_selectors is not None:
        flags += "p"
    if clone.struct_arm is not None:
        flags += "s"
    return flags or "-"


class ClockKernel(PdaKernel):
    """The PDA's own trace — every frame the fused kernel pushes, as an extent.

    The zero-hook observation pattern: ``_enter`` records the pushed frame
    (start, stack depth, clone name), ``_complete`` closes its extent, and
    ``attempt`` marks where the real attempt machinery fired — then every
    override delegates. The parse is the engine's own; the clock only
    watches it. Frames still open when a parse dies keep ``end=-1`` and are
    closed at the failure position — the live stack at death IS the trace's
    last column. Probe sub-runs record their frames too: rolled-back work
    is real work, and the clock shows work.
    """

    __slots__ = ("frames", "open_frames", "events", "cid_of")

    def __init__(self, tables, text, fold, cid_of=None) -> None:
        super().__init__(tables, text, fold)
        self.frames: list[list] = []  # [start, end, depth, clone name, clone idx]
        self.open_frames: dict[int, int] = {}
        self.events: list[list] = []  # [pos, kind, detail]
        self.cid_of = cid_of or {}

    def _note(self, pos, kind, detail) -> None:
        if not self._caches.probing and len(self.events) < 20000:
            self.events.append([pos, kind, detail])

    def _sweep(self, depth, keep=None) -> None:
        """Close every open frame at ``depth`` or deeper — popped without
        completing means an attempt sub-run rolled it back (stack discipline:
        a completing frame's subtree has already completed, so anything still
        open below it was abandoned)."""
        for fid, idx in list(self.open_frames.items()):
            rec = self.frames[idx]
            if rec[2] >= depth and fid is not keep:
                rec[1] = max(self.pos, rec[0])
                rec[5] = 0
                del self.open_frames[fid]

    def _enter(self, clone, out):
        pushed = super()._enter(clone, out)
        if pushed:
            frame = self.stack[-1]
            depth = len(self.stack) - 1
            self._sweep(depth, keep=id(frame))
            self.open_frames[id(frame)] = len(self.frames)
            self.frames.append([
                frame[F_START], -1, depth,
                str(frame[F_CLONE].name), self.cid_of.get(id(frame[F_CLONE]), -1), 1,
            ])
        return pushed

    def _complete(self, frame):
        idx = self.open_frames.pop(id(frame), None)
        if idx is not None:
            self.frames[idx][1] = self.pos
            self._sweep(self.frames[idx][2] + 1)
        return super()._complete(frame)

    def attempt(self, clone, out):
        self._note(self.pos, "attempt", f"arm choice at {clone.name} — admission cannot decide; sub-runs try the arms")
        return super().attempt(clone, out)

    def attempt_iteration(self, frame, arm, i, pos):
        got = super().attempt_iteration(frame, arm, i, pos)
        self._note(pos, "loop", f"attempted iteration {'takes' if got == i else 'closes'}")
        return got

    def _fork_verdict(self, arm, i, pos, taken):
        verdict = super()._fork_verdict(arm, i, pos, taken)
        self._note(pos, "verdict", f"both-viable boundary → {('TAKE', 'STOP', 'FORK')[verdict]}")
        return verdict

    def _probe(self, arm, i, pos, taken):
        got = super()._probe(arm, i, pos, taken)
        side = "take" if taken is not None else "stop"
        self._note(pos, "probe", f"{side}-side probe {'completes' if got[0] is not None else 'dies'}")
        return got

    def _island(self, name, sink):
        start = self.pos
        super()._island(name, sink)
        self._note(start, "island", f"{name} · Earley window [{start},{self.pos})")


def _spell(element) -> str:
    """A sequence element's display spelling — the rail registers' language."""
    atom = getattr(element, "atom", element)
    if isinstance(atom, IrRuleRef):
        return str(atom)
    if isinstance(atom, IrLiteral):
        return '"' + str(atom).replace("\\", "\\\\").replace("\n", "\\n") + '"'
    if isinstance(atom, IrCharClass):
        pattern = atom.pattern()
        return "[" + (pattern if len(pattern) <= 14 else pattern[:13] + "…") + "]"
    if isinstance(atom, IrAlternation):
        return "(…)"
    return type(atom).__name__


def _terminal_spelling(element) -> str | None:
    """The element's spelling when it scans text directly, else None."""
    atom = getattr(element, "atom", element)
    if isinstance(atom, (IrLiteral, IrCharClass)):
        return _spell(element)
    return None


def rule_verdicts(cg) -> list[tuple[str, str, list[str]]]:
    """Per rule: the PDA's reaction, in the analysis' own words.

    The verdict vocabulary from opsis_proto_0's explainer: attempt (ordered
    attempts decide) · island (windowed Earley sub-parse) · hard (unresolved
    conflict) · gated (demoted to a stored gate) · predictive (single-pass
    deterministic). Nothing computed here — the analysis is the oracle.
    """
    from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
    analysis = GrammarAnalysis(lift_optional_nullables(cg.codegen_grammar))
    attempts = set(analysis.taxonomy.attempts)
    islands = set(analysis.islands) - attempts
    hard = {k: list(v) for k, v in analysis.taxonomy.conflicts.items() if v}
    soft = {k: list(v) for k, v in analysis.demoted.items() if v}
    out = []
    for name in analysis.rules:
        notes = hard.get(name, []) + soft.get(name, [])
        if name in attempts:
            cls = "attempt"
        elif name in islands:
            cls = "island"
        elif hard.get(name):
            cls = "hard"
        elif soft.get(name):
            cls = "gated"
        else:
            cls = "predictive"
        out.append((str(name), cls, [str(n) for n in notes]))
    return out


def rail_lines(ast, name: str) -> list[str] | None:
    """One rule's body as indented structural lines — the railroad's wire form.

    Each line is ``<depth> <kind> [payload]``; children sit one depth deeper.
    Kinds: ``alt``/``seq`` (containers), ``many lo hi`` (a real quantifier,
    hi -1 for unbounded), ``ref``/``lit``/``class`` (leaves), ``not``/``alpha``
    (one-child wrappers), ``nil`` (the empty sequence), ``other`` (anything
    this instrument does not yet draw — named, never silent).
    """
    for rule in ast.rules:
        if str(rule.name) == name:
            out: list[str] = []
            _rail(rule.body, 0, out)
            return out
    return None


def _rail(node, depth: int, out: list[str]) -> None:
    """One structural line for ``node`` — single-child containers collapse."""
    if isinstance(node, (IrAlternation, IrSequence)) and len(node) == 1:
        _rail(node[0], depth, out)
    elif isinstance(node, (IrAlternation, IrSequence)) and len(node) == 0:
        out.append(f"{depth} nil")
    elif isinstance(node, (IrAlternation, IrSequence)):
        out.append(f"{depth} {'alt' if isinstance(node, IrAlternation) else 'seq'}")
        for child in node:
            _rail(child, depth + 1, out)
    elif isinstance(node, IrItem) and node.quantifier.lo == 1 and node.quantifier.hi == 1:
        _rail(node.atom, depth, out)
    elif isinstance(node, IrItem):
        hi = -1 if node.quantifier.hi is IrNone else int(node.quantifier.hi)
        out.append(f"{depth} many {int(node.quantifier.lo)} {hi}")
        _rail(node.atom, depth + 1, out)
    elif isinstance(node, IrRuleRef):
        out.append(f"{depth} ref {node}")
    elif isinstance(node, IrLiteral):
        text = str(node).replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
        out.append(f"{depth} lit {text}")
    elif isinstance(node, IrCharClass):
        out.append(f"{depth} class {node.pattern()}")
    elif isinstance(node, IrNot):
        out.append(f"{depth} not")
        _rail(node[0], depth + 1, out)
    elif isinstance(node, IrAlphabet):
        out.append(f"{depth} alpha {node.encoding}")
        _rail(node.inner, depth + 1, out)
    else:
        out.append(f"{depth} other {type(node).__name__}")


def fold_spans(model: GrammarModel, document: str) -> list[Span]:
    """Every occurrence's span, folded from the model's own tagged emit stream."""
    spans: list[Span] = []
    end = _fold(model, 0, 0, "", spans)
    if end != len(document):
        raise AssertionError(f"span fold ended at {end}, document is {len(document)}")
    spans.sort(key=lambda s: (s.start, s.depth))
    return spans


def _fold(part: object, depth: int, off: int, field: str, spans: list[Span]) -> int:
    """Advance the offset through one part, recording model spans on the way."""
    if part is None:
        return off
    if isinstance(part, str):
        return off + len(part)
    if isinstance(part, tuple) and not isinstance(part, GrammarModel):
        for element in part:
            off = _fold(element, depth, off, field, spans)
        return off
    start = off
    for tag, inner in part.emit_parts():
        off = _fold(inner, depth + 1, off, tag or "", spans)
    if off > start:
        spans.append(Span(start, off, depth, str(type(part).__grammar__.name), field))
    return off


def build_scene(subject: Subject) -> str:
    """The emitted frame — line-oriented plain text; long blocks length-prefixed."""
    rules = subject.rule_lines()
    rule_names = sorted({s.rule for s in subject.spans})
    field_names = sorted({s.field for s in subject.spans})
    rule_idx = {n: i for i, n in enumerate(rule_names)}
    field_idx = {n: i for i, n in enumerate(field_names)}
    out = [
        "#META",
        f"fixture {subject.key}",
        f"reader {subject.reader_desc}",
        f"seconds {subject.seconds:.2f}",
        f"resolver {1 if subject.resolve else 0}",
        f"faithful {1 if subject.faithful else 0}",
        f"generation {subject.generation}",
        f"t {subject.t:.1f}",
        f"#POLICY {len(subject.policy)}",
        *(f"{k} {v}" for k, v in subject.policy.items()),
        f"#RULEDEFS {len(rules)}",
        *(f"{name} {a} {b}" for name, a, b in rules),
        f"#RULENAMES {len(rule_names)}",
        *rule_names,
        f"#FIELDNAMES {len(field_names)}",
        *field_names,
        f"#EDGES {len(subject.edges)}",
        *(f"{a} {b}" for a, b in subject.edges),
        f"#DEPTHS {len(subject.rule_depth)}",
        *(f"{name} {d}" for name, d in subject.rule_depth.items()),
        f"#SPANS {len(subject.spans)}",
        *(f"{s.start} {s.end} {s.depth} {rule_idx[s.rule]} {field_idx[s.field]}" for s in subject.spans),
        f"#READER {len(subject.reader_text)}",
        subject.reader_text,
        f"#DOC {len(subject.document)}",
        subject.document,
        "",
    ]
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    """The seam — frames out, gestures in. Addresses travel; subjects never do."""

    subject: Subject

    def log_message(self, *_args: object) -> None:
        """Quiet; the interesting events print themselves."""

    def send_text(self, body: str, kind: str = "text/plain") -> None:
        """One response, utf-8."""
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        """The page, the leaf artifacts, or the current frame."""
        files = {
            "/": ("index.html", "text/html"),
            "/leaf.css": ("leaf.css", "text/css"),
            "/leaf.js": ("leaf.js", "text/javascript"),
            "/pretext.js": ("pretext.js", "text/javascript"),
        }
        if self.path.split("?")[0] in files:
            name, kind = files[self.path.split("?")[0]]
            self.send_text((LEAF / name).read_text(), kind)
            return
        if self.path == "/scene":
            with self.subject.lock:
                self.send_text(build_scene(self.subject))
            return
        if self.path == "/policy":
            with self.subject.lock:
                body = "\n".join(f"{k} {v}" for k, v in self.subject.policy.items())
            self.send_text(body)
            return
        if self.path == "/verdicts":
            rows = []
            for name, cls, notes in self.subject.verdicts:
                rows.append(f"{cls} {len(notes)} {name}")
                rows.extend(notes)
            self.send_text(f"#VERDICTS {len(self.subject.verdicts)}\n" + "\n".join(rows))
            return
        if self.path == "/automaton":
            subj = self.subject
            names: dict[str, int] = {}
            rows = []
            for i, clone in enumerate(subj.auto_clones):
                idx = names.setdefault(str(clone.name), len(names))
                mode = _MODE_WORD.get(clone.mode, str(clone.mode))
                rows.append(f"{idx} {mode} {clone_flags(clone)} {subj.auto_depth.get(i, -1)}")
            out = [f"#ACLONES {len(rows)}", *rows,
                   f"#ANAMES {len(names)}", *names,
                   f"#AEDGES {len(subj.auto_edges)}",
                   *(f"{a} {b}" for a, b in subj.auto_edges)]
            self.send_text("\n".join(out))
            return
        if self.path.startswith("/column?i="):
            i = int(self.path.split("=", 1)[1])
            with self.subject.lock:
                kernel = self.subject._earley_kernel
                tables = self.subject._instance_tables
            if kernel is None or not (0 <= i < len(kernel.cols)):
                self.send_text("status pending")
                return
            rows, expect = [], []
            for packed in kernel.cols[i]:
                rule, seq, dot, origin = decode_item(tables, packed)
                role = "predict" if dot == 0 else ("complete" if dot == len(seq) else "advance")
                done = " ".join(_spell(e) for e in seq[:dot])
                todo = " ".join(_spell(e) for e in seq[dot:])
                rows.append(f"{origin} {role} {rule} ::= {done} \u25cf {todo}")
                if dot < len(seq):
                    term = _terminal_spelling(seq[dot])
                    if term and term not in expect:
                        expect.append(term)
            out = [f"#COLUMN {i} {len(rows)}", *rows,
                   f"#EXPECT {len(expect)}", *sorted(expect)]
            self.send_text("\n".join(out))
            return
        if self.path == "/clock":
            with self.subject.lock:
                clock = dict(self.subject.clock)
                generation = self.subject.generation
            if clock.get("status") != "done":
                self.send_text("status pending")
                return
            out = [f"status done", f"generation {generation}",
                   f"pda_end {clock.get('pda_end', -1)}",
                   f"dropped {clock.get('dropped', 0)}"]
            frames = clock.get("frames", [])
            fnames: dict[str, int] = {}
            rows = []
            for start, end, depth, name, cid, ok in frames:
                idx = fnames.setdefault(name, len(fnames))
                rows.append(f"{start} {end} {depth} {idx} {cid} {ok}")
            out.append(f"#PDAFRAMES {len(rows)}")
            out.extend(rows)
            out.append(f"#PDANAMES {len(fnames)}")
            out.extend(fnames)
            events = clock.get("events", [])
            out.append(f"#EVENTS {len(events)}")
            out.extend(f"{pos} {kind} {detail}" for pos, kind, detail in events)
            hyp = clock.get("hyp", [])
            hnames: dict[str, int] = {}
            rows = []
            for origin, last, comp, name in hyp:
                idx = hnames.setdefault(name, len(hnames))
                rows.append(f"{origin} {last} {comp} {idx}")
            out.append(f"#EARLEY {len(rows)}")
            out.extend(rows)
            out.append(f"#EARLEYNAMES {len(hnames)}")
            out.extend(hnames)
            self.send_text("\n".join(out))
            return
        if self.path == "/rails":
            with self.subject.lock:
                ast = self.subject.graph_ast
                out = []
                for rule in ast.rules:
                    lines = rail_lines(ast, str(rule.name)) or []
                    out.append(f"#RAIL {rule.name} {len(lines)}")
                    out.extend(lines)
            self.send_text("\n".join(out))
            return
        if self.path.startswith("/rail?rule="):
            name = unquote(self.path.split("=", 1)[1])
            with self.subject.lock:
                lines = rail_lines(self.subject.graph_ast, name)
            if lines is None:
                self.send_text(f"no such rule {name}")
                return
            self.send_text(f"#RAIL {name} {len(lines)}\n" + "\n".join(lines))
            return
        if self.path == "/routes":
            with self.subject.lock:
                primary = "PDA (fused kernel)" if self.subject.resolve is None else "Earley + first-derivation resolver"
                lines = [f"primary {primary}", f"primary_seconds {self.subject.seconds:.2f}"]
                lines += [f"{k} {v}" for k, v in self.subject.route2.items()]
            self.send_text("\n".join(lines))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        """Gestures: a cursor report, or a retype that triggers a re-reading."""
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
        if self.path == "/cursor":
            head = body.split()
            with self.subject.lock:
                self.subject.t = float(head[1])
                self.subject.selection = int(head[3])
            self.send_text("ok")
            return
        if self.path == "/policy":
            with self.subject.lock:
                for line in body.split("\n"):
                    if not line.strip():
                        continue
                    key, _, value = line.partition(" ")
                    if value == "-":
                        self.subject.policy.pop(key, None)
                    else:
                        self.subject.policy[key] = value
            self.send_text("ok")
            return
        if self.path == "/edit":
            self.send_text(self.retype(body, persist=False))
            return
        if self.path == "/save":
            self.send_text(self.retype(body, persist=True))
            return
        self.send_response(404)
        self.end_headers()

    def retype(self, body: str, persist: bool = False) -> str:
        """Splice and re-read; ``persist`` also writes the document to its own file.

        Saving compiles: a save that does not derive writes nothing. A save of
        corpus fixtures is HELD with its reason — re-reading still happened.
        """
        head, _, replacement = body.partition("\n")
        start, end = (int(x) for x in head.split())
        with self.subject.lock:
            candidate = self.subject.document[:start] + replacement + self.subject.document[end:]
            try:
                self.subject.read(candidate)
            except Exception as refusal:
                ro = getattr(refusal, "readout", None)
                pos = ro.pos if ro else -1
                extra = ""
                if ro and ro.rule:
                    extra += f" — while reading {ro.rule}"
                if ro and ro.expected:
                    joiner = "none of" if ro.negated else "expected:"
                    extra += f" — {joiner} " + " ".join(str(x) for x in tuple(ro.expected)[:12])
                print(f"refused at {pos}: {refusal}")
                return f"refuse {pos}\n{refusal}{extra}"
            print(f"generation {self.subject.generation}: re-read {len(candidate):,} chars in {self.subject.seconds:.2f}s")
            if not persist:
                return f"ok {self.subject.seconds:.2f}"
            held = self.subject.save_held()
            if held:
                return f"ok {self.subject.seconds:.2f} held {held}"
            self.subject.doc_path.write_text(self.subject.document)
            print(f"saved {self.subject.doc_path}")
            return f"ok {self.subject.seconds:.2f} saved"


def census(subject: Subject) -> int:
    """The gate — fidelity, fold, scene integrity, one accepted and one refused retype."""
    scene = build_scene(subject)
    ok_scene = f"#SPANS {len(subject.spans)}" in scene and scene.endswith(subject.document + "\n")
    first_span = subject.spans[0]
    handler = Handler.__new__(Handler)
    handler.subject = subject
    same = subject.document[first_span.start : first_span.end]
    ok_edit = handler.retype(f"{first_span.start} {first_span.end}\n{same}").startswith("ok")
    # Where the grammar cannot recover — the subject carries its own offset
    # and the reason (a control char is legal inside a GBNF comment).
    mid = subject.corrupt_at
    refusal = handler.retype(f"{mid} {mid + 1}\n\x01")
    head, _, words = refusal.partition("\n")
    pos = int(head.split()[1]) if head.startswith("refuse") else -2
    ok_refuse = head.startswith("refuse") and subject.document[mid] != "\x01"
    # PDA-routed fixtures measure the frontier; resolver routes honestly cannot
    ok_frontier = pos >= 0 if subject.resolve is None else True
    span0 = subject.spans[0]
    saved = handler.retype(
        f"{span0.start} {span0.end}\n{subject.document[span0.start:span0.end]}", persist=True
    )
    ok_save = saved.startswith("ok") and (" saved" in saved if subject.save_held() == "" else " held" in saved)
    start = str(subject.graph_ast.rules[0].name)
    ok_graph = len(subject.edges) > 0 and subject.rule_depth.get(start) == 0
    print(f"{subject.key}: {len(subject.document):,} chars · {len(subject.spans):,} spans · "
          f"{len(subject.rule_lines())} rules in reader · {len(subject.edges)} graph edges "
          f"(start depth {subject.rule_depth.get(start)}) · parse {subject.seconds:.2f}s · scene {len(scene):,} bytes")
    print(f"faithful {subject.faithful} · scene integrity {ok_scene} · identity retype ok {ok_edit} · "
          f"garbage retype refused {ok_refuse} · frontier {pos} ({words[:48]}…)")
    print(f"save: {saved.split(chr(10))[0][:70]} · as expected {ok_save}")
    handler.do_POST = handler.do_POST  # noqa: self-reference guard for direct use
    with subject.lock:
        subject.policy["graph.view"] = "arcs"
        subject.policy["pin.7"] = "span 10 20 3 test 100 100 300 200"
    round_trip = build_scene(subject)
    ok_policy = ("#POLICY 2" in round_trip and "graph.view arcs" in round_trip
                 and "pin.7 span 10 20 3 test 100 100 300 200" in round_trip)
    with subject.lock:
        subject.policy.clear()
    print(f"policy round-trips through the scene: {ok_policy}")
    for _ in range(400):
        if subject.clock.get("status") == "done":
            break
        time.sleep(0.05)
    ck = subject.clock
    frames = ck.get("frames", [])
    hyp = ck.get("hyp", [])
    n_doc = len(subject.document)
    pda_ok = ck.get("pda_end", -1) == -1 and "pda_error" not in ck and "pda_failed" not in ck
    ok_clock = (ck.get("status") == "done"
                and all(0 <= f[0] <= f[1] <= n_doc for f in frames)
                and (not pda_ok or (len(frames) > 0 and any(f[0] == 0 and f[1] == n_doc for f in frames)))
                and len(hyp) > 0
                and all(0 <= h[0] <= h[1] <= n_doc for h in hyp)
                and any(h[0] == 0 and h[1] == n_doc and h[2] for h in hyp))
    n_clones = len(subject.auto_clones)
    ok_auto = (all(0 <= a < n_clones and 0 <= b < n_clones for a, b in subject.auto_edges)
               and all(len(f) == 6 and -1 <= f[4] < n_clones for f in frames)
               and (n_clones == 0 or subject.auto_depth.get(0) == 0)
               and (not pda_ok or (n_clones > 0 and sum(1 for f in frames if f[4] >= 0) > 0)))
    ok_verdicts = (len(subject.verdicts) > 0
                   and all(cls in ("attempt", "island", "hard", "gated", "predictive")
                           for _n, cls, _o in subject.verdicts))
    print(f"clocks: pda {len(frames)} frames (depth {max((f[2] for f in frames), default=0)}, "
          f"{len(ck.get('events', []))} events, end {ck.get('pda_end')}) · "
          f"earley {len(hyp)} hypotheses ({sum(1 for h in hyp if h[2])} completed, "
          f"{ck.get('dropped', 0)} dropped) · well-formed {ok_clock}")
    from collections import Counter as _Counter
    vcount = _Counter(cls for _n, cls, _o in subject.verdicts)
    print(f"automaton: {n_clones} clones · {len(subject.auto_edges)} edges · "
          f"{len({str(c.name) for c in subject.auto_clones})} names · frames wired {ok_auto}")
    print(f"verdicts: {dict(vcount)} · well-formed {ok_verdicts}")
    rails = rail_lines(subject.graph_ast, start)
    ok_rail = (rails is not None and len(rails) > 0
               and all(len(ln.split(None, 1)) >= 2 for ln in rails)
               and any(ln.split()[1] in ("ref", "lit", "class") for ln in rails)
               and rail_lines(subject.graph_ast, "no-such-rule-xyz") is None
               and all(rail_lines(subject.graph_ast, str(r.name)) is not None
                       for r in subject.graph_ast.rules))
    print(f"rail lines for {start}: {len(rails or [])} · well-formed {ok_rail}")
    for _ in range(200):
        if subject.route2.get("status") != "pending":
            break
        time.sleep(0.05)
    r2 = subject.route2
    if subject.resolve is None:
        ok_routes = r2.get("status") == "done" and r2.get("parity") == "holds"
    else:
        # a resolver route's PDA honestly fails; an island-start failure has no position
        ok_routes = r2.get("status") == "failed"
    print(f"other route: {r2} · as expected {ok_routes}")
    ok = (subject.faithful and ok_scene and ok_edit and ok_refuse and ok_frontier
          and ok_save and ok_routes and ok_graph and ok_policy and ok_rail and ok_clock
          and ok_auto and ok_verdicts)
    print("census ok" if ok else "census FAILED")
    return 0 if ok else 1


def main() -> int:
    """Entry — build the subject, then serve it or gate it."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    key = args[0] if args else "vyx"
    doc = args[1] if len(args) > 1 and not args[1].isdigit() else None
    tail = args[2:] if doc is not None else args[1:]
    port = int(tail[0]) if tail else 8901
    print(f"reading fixture '{key}' …")
    subject = Subject(key, doc)
    print(f"{subject.reader_desc} read {len(subject.document):,} chars in {subject.seconds:.2f}s · "
          f"{len(subject.spans):,} spans · faithful {subject.faithful}")
    if "--census" in sys.argv:
        return census(subject)
    Handler.subject = subject
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"facets at http://127.0.0.1:{port}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
