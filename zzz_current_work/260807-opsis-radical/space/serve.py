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

import importlib

import irview

from lexic.compile import (
    compile_ast,
    compile_from_path,
    compile_text,
    compute_binding,
    export_module,
    export_source,
    parse_grammar,
    verify_module,
)
from lexic.compile.notation.parse import NOTATION_GRAMMAR
from lexic.compile.payload.export import export_value
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR, get_flavour
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # generated/ artefacts import from the root
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


FIXTURE_FILES: dict[str, tuple[str | None, str]] = {
    # name → (grammar file or None, document file). FILES ONLY — which text
    # can read which, and every rung above, is COMPUTED, never declared.
    "long": ("gt:json.gbnf", "tk:fixtures_long.json"),
    "meta": (None, "gt:json.gbnf"),
    "vyx": (None, "gt:vyx.gbnf"),
    "abnf": (None, "gt:json.abnf"),
    "decide": ("fx:decide.gbnf", "fx:decide.txt"),
    "amb": ("fx:amb.gbnf", "fx:amb.txt"),
}


def fixture_path(tag: str) -> Path:
    kind, _, name = tag.partition(":")
    bases = {"gt": ROOT / "resources" / "ground_truth",
             "tk": HERE.parent / "tk", "fx": HERE / "fixtures"}
    return bases[kind] / name if kind in bases else Path(tag)


_CHIRALITY: dict[int, str | None] = {}


def grammar_flavour_of(text: str) -> str | None:
    """The chirality gate, computed: the flavour whose metagrammar reads ``text``.

    Tried against the engine and cached; ``None`` means no flavour accepts —
    the text is a plain document and cannot climb.
    """
    key = hash(text)
    if key not in _CHIRALITY:
        found = None
        for name in ("gbnf", "abnf", "ebnf"):
            try:
                parse_grammar(text, get_flavour(name))
                found = name
                break
            except LexicError:
                continue
        _CHIRALITY[key] = found
    return _CHIRALITY[key]


class Subject:
    """The reading: reader text, document text, model, spans — and how to re-read."""

    def __init__(self, key: str, doc: str | None = None) -> None:
        self.key = key
        gtag, dtag = FIXTURE_FILES.get(key, (key, doc))
        if gtag is None:
            raise SystemExit(f"fixture '{key}' has no base grammar file")
        gpath = fixture_path(gtag)
        if not gpath.is_file():
            raise SystemExit(f"no fixture and no grammar file named '{key}'")
        if dtag is None:
            raise SystemExit("a file grammar needs a document: serve.py <grammar> <doc> [port]")
        self.compiled = compile_from_path(str(gpath))
        self.reader_text = gpath.read_text()
        self.reader_desc = gpath.name
        self.doc_path = fixture_path(dtag)
        self.graph_ast = self.compiled.grammar
        document = self.doc_path.read_text()
        # Corrupting a grammar text mid-document can land inside a comment,
        # where a control char is LEGAL (measured); a plain document has no
        # such shelter. Computed from chirality, not declared per fixture.
        self.corrupt_at = 0 if grammar_flavour_of(document) else len(document) // 2
        self._init_common(document)

    @classmethod
    def from_reading(cls, key, compiled, reader_text, reader_desc, document, doc_path=None):
        """A reading assembled from parts — the ladder's non-base rungs."""
        self = cls.__new__(cls)
        self.key = key
        self.compiled = compiled
        self.reader_text = reader_text
        self.reader_desc = reader_desc
        self.doc_path = doc_path
        self.graph_ast = compiled.grammar
        self.corrupt_at = 0
        self._init_common(document)
        return self

    def _init_common(self, document: str) -> None:
        """Everything after the fixture branch — one tail for every reading."""
        self.document = document
        self.resolve = None  # plugged on demand — the engine's refusal decides
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
        """One reading — parse, verify fidelity, fold spans. Raises on refusal.

        Ambiguity plugs the ``first`` resolver COMPUTEDLY: the bare parse is
        tried, and only the engine's own ambiguity refusal reaches for the
        plug — no fixture ever declares it. Once plugged, it stays (the
        refusal was about the reading, not about one document state).
        """
        t0 = time.perf_counter()
        try:
            model = self.compiled.parse(text, resolve=self.resolve)
        except UnsupportedConstructError as refusal:
            if self.resolve is not None or "ambiguous" not in str(refusal):
                raise
            self.resolve = first
            model = self.compiled.parse(text, resolve=first)
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
                result["pda_words"] = str(fork)[:200]
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
        if self.doc_path is None:
            return "this reading's document is an emitter's own spelling — nothing on disk to save"
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


def _rename_walk(node, ren):
    """Rebuild a rule body with rule references renamed — language identical."""
    if isinstance(node, IrRuleRef):
        return IrRuleRef(ren.get(str(node), str(node)))
    if isinstance(node, IrItem):
        return IrItem(_rename_walk(node.atom, ren), node.quantifier)
    if isinstance(node, IrSequence):
        return IrSequence(*(_rename_walk(x, ren) for x in node))
    if isinstance(node, IrAlternation):
        return IrAlternation(*(_rename_walk(x, ren) for x in node))
    if isinstance(node, IrNot):
        return IrNot(_rename_walk(node[0], ren))
    if isinstance(node, IrAlphabet):
        return IrAlphabet(str(node.encoding), _rename_walk(node.inner, ren))
    return node


def fold_safe(grammar):
    """A language-identical rename clearing name-fold collisions (esc-u/esc-U).

    Both the module self-grammar AND the notation grammar carry the collision;
    the ENGINE ASK stands (fold-safe self-grammar names, or exportability for
    IR-authored grammars) — until it lands, this rename is the honest bridge.
    """
    from lexic.ir import IrAst, IrRule
    seen, ren = {}, {}
    for rule in grammar.rules:
        name = str(rule.name)
        folded = name.lower()
        if folded in seen and name != seen[folded]:
            ren[name] = folded + "-cap"
        else:
            seen[folded] = name
    rules = [IrRule(ren.get(str(r.name), str(r.name)), _rename_walk(r.body, ren),
                    semantic=bool(r.semantic)) for r in grammar.rules]
    return IrAst(rules=rules, start=grammar.start)


_MODULE_READER = None
_NOTATION_READER = None
_NOTATION_SPELL = None


def module_reader():
    """The generated-module self-grammar, compiled through the standard
    pipeline (fold-safe renamed; the absolute fixpoint stays blocked)."""
    global _MODULE_READER
    if _MODULE_READER is None:
        from lexic.compile.module.selfgrammar import MODULE_GRAMMAR
        _MODULE_READER = compile_ast(fold_safe(MODULE_GRAMMAR))
    return _MODULE_READER


def notation_reader():
    """The IR-constructor notation grammar as a READER — the inward surface.

    ``repr`` of any IR value is notation text; this reader gives it the full
    room: spans, spine, rails, clocks, over the constructor expression.
    """
    global _NOTATION_READER
    if _NOTATION_READER is None:
        _NOTATION_READER = compile_ast(fold_safe(NOTATION_GRAMMAR))
    return _NOTATION_READER


def notation_spell() -> str:
    global _NOTATION_SPELL
    if _NOTATION_SPELL is None:
        _NOTATION_SPELL = str(GBNF_FLAVOUR.apply(fold_safe(NOTATION_GRAMMAR)))
    return _NOTATION_SPELL


_EXPORTS = {}


def export_doc(flavour) -> str:
    """The metagrammar of ``flavour`` as its export module — IR constructors."""
    key = id(flavour)
    if key not in _EXPORTS:
        from lexic.compile.module.export import export_source
        from lexic.compile import compile_text as _ct
        _EXPORTS[key] = export_source(_ct(str(flavour.apply(flavour.grammar)), flavour=flavour.name))
    return _EXPORTS[key]


_META_CG = {}


def flavour_cg(flavour):
    """The metagrammar compiled once per flavour, shared by every rung."""
    key = id(flavour)
    if key not in _META_CG:
        _META_CG[key] = compile_ast(flavour.grammar)
    return _META_CG[key]


class Session:
    """The ladder of readings a fixture implies — subjects built lazily.

    Every reader is also a text; every text may also be a reader. The base
    rung is the fixture; above it, the grammar read by its metagrammar; at
    the top, the metagrammar reading ITS OWN spelling — the self-hosting
    fixpoint, where reader and document are the same text. Travel moves
    focus; the whole instrument re-derives. One policy record spans the
    session (the arrangement survives travel).
    """

    def __init__(self, key: str, doc: str | None = None) -> None:
        self.key = key
        self.rungs = self._ladder(key, doc)
        self.subjects: dict[int, Subject] = {}
        self.focus = 0
        self.policy: dict[str, str] = {}
        self.subject(0)

    def _ladder(self, key, doc):
        """The rungs, COMPUTED: chirality licenses each climb, never a table.

        A text climbs iff some flavour's metagrammar accepts it (tried,
        cached); the climb tops out where the metagrammar reads its own
        spelling — the text-level fixpoint. The export rung is the outward
        projection of the climb's flavour; the policy rung is the session
        reading its own record. §11's ruling embodied: the ladder does not
        store its rungs, it licenses them.
        """
        gtag, dtag = FIXTURE_FILES.get(key, (key, doc))
        rungs, climbed = [], None
        self.levels: list[int] = []
        self.lanes: list[int] = []
        self.lane_names: list[str] = []
        self.things: list[dict] = []
        self._artefacts = None
        self._ghost_cache: dict[int, list] = {}
        self.base_grammar = None
        if gtag is not None:
            gpath = fixture_path(gtag)
            self.base_grammar = gpath
            doc_lane = self._lane(fixture_path(dtag).name)
            rungs.append((f"{fixture_path(dtag).name} ⊳ {gpath.name}", "r",
                          lambda: Subject(key, doc)))
            self.levels.append(0)
            self.lanes.append(doc_lane)
            text, tpath = gpath.read_text(), gpath
        else:
            dpath = fixture_path(dtag)
            self.base_grammar = dpath
            doc_lane = None
            text, tpath = dpath.read_text(), dpath
        base_lane, level = None, 1
        while True:
            name = grammar_flavour_of(text)
            if name is None:
                break
            climbed = get_flavour(name)
            spell = str(climbed.apply(climbed.grammar))
            desc = (f"the {name.upper()} metagrammar "
                    f"({len(climbed.grammar.rules)} rules), spelled by its own emitter")
            if text == spell:
                meta_lane = self._lane(f"{name} metagrammar")
                rungs.append(("the metagrammar reads its own spelling", "r",
                              self._rung(climbed, spell, desc, spell, None)))
                self.levels.append(level)
                self.lanes.append(meta_lane)
                self.things.append(dict(
                    lane=meta_lane, name=f"{name} metagrammar", flavour=climbed,
                    text_fn=lambda s=spell: s,
                    reader_fn=lambda f=climbed: flavour_cg(f),
                    cg_fn=(lambda f=climbed, s=spell: compile_text(s, flavour=f))))
                break
            this_lane = self._lane(tpath.name if tpath else "its spelling")
            if base_lane is None:
                base_lane = this_lane
            rungs.append((f"{tpath.name if tpath else 'its spelling'} ⊳ {name} metagrammar",
                          "r", self._rung(climbed, spell, desc, text, tpath)))
            self.levels.append(level)
            self.lanes.append(this_lane)
            text, tpath = spell, None
            level += 1
        self.climbed = climbed
        if climbed is not None and base_lane is not None:
            base = dict(lane=base_lane, name=self.base_grammar.name,
                         flavour=climbed,
                         text_fn=lambda: self.base_grammar.read_text(),
                         reader_fn=lambda: flavour_cg(self.climbed),
                         cg_fn=lambda: compile_from_path(str(self.base_grammar)))
            if doc_lane is not None:
                dpath = fixture_path(dtag)
                self.things.append(dict(
                    lane=doc_lane, name=dpath.name, flavour=climbed,
                    text_fn=lambda p=dpath: p.read_text(),
                    reader_fn=base["cg_fn"], cg_fn=base["cg_fn"],
                    model_only=True))
            self.things.insert(0, base)
        self.places: dict[str, dict] = {}
        for thing in self.things:
            self._thing_places(thing)
        rungs.append(("⚙ the session policy ⊳ policy.gbnf", "o", self._policy_rung))
        self.levels.append(99)  # the instrument stands beside the chain, not in it
        self.lanes.append(self._lane("the instrument"))
        return rungs

    def _lane(self, name: str) -> int:
        self.lane_names.append(name)
        return len(self.lane_names) - 1

    # ── places: rooms typed by what the subject IS — never the parser ──

    def _place(self, pid, thing, band, kind, label, sections_fn) -> None:
        self.places[pid] = dict(pid=pid, lane=thing["lane"], band=band,
                                kind=kind, label=label, sections=sections_fn)

    def reductions(self, thing) -> list[dict]:
        """The reduction PLUG's candidates — real objects, different products.

        One reading, several reductions: the model fold builds a model; the
        flavour's own reducer builds the IR value. They are not two buttons
        for one thing — they are two codomains of the same text under the
        same reader, and a grammar text is the case where BOTH exist.
        """
        out = [dict(key="m", label="the model fold → a model instance",
                    fn=lambda t=thing: _model_of(t))]
        if not thing.get("model_only"):
            out.append(dict(key="i",
                            label="the flavour's own reducer → an IR value",
                            fn=lambda t=thing: parse_grammar(t["text_fn"](),
                                                             t["flavour"])))
            out.append(dict(key="f",
                            label="the flavour object that reads it — "
                                  "self-grammar, reducer, emit actions, escapes",
                            fn=lambda t=thing: t["flavour"]))
        return out

    def _thing_places(self, thing) -> None:
        """A thing's rooms: its VALUES (one per reduction), its COMPILER,
        its ARTEFACTS. Rooms are typed by what the subject is; the parsing
        window stays for readings."""
        lane = thing["lane"]
        for red in self.reductions(thing):
            pid = f"v{lane}{red['key']}"
            self._place(pid, thing, -1, "value",
                        f"{thing['name']} · {red['label']}",
                        lambda t=thing, r=red, s=self: value_sections(s, t, r))
            self.places[pid].update(value_fn=red["fn"], reduction=red["key"])
        if thing.get("model_only"):
            return
        cg_fn = thing["cg_fn"]
        self._place(f"c{lane}", thing, -2, "compiler",
                    f"the compiler over {thing['name']}",
                    lambda f=cg_fn, fl=thing["flavour"], ln=lane:
                    compiler_sections(f(), fl, ln))
        self.places[f"c{lane}"]["cg_fn"] = cg_fn
        self._place(f"a{lane}", thing, -3, "artefacts",
                    f"the artefacts of {thing['name']}",
                    lambda s=self, t=thing: artefact_sections(s, t))

    # ── the strata space: rooms by level, ghosts by tried licence ──────

    def ghosts_for(self, thing) -> list[tuple[str, bool, str]]:
        """Transpile offers ON A VALUE — an operation, not a place in the strata.

        Respelling is a lateral move performed on one grammar's IR value;
        it belongs where that value is, and its licence is tried against
        each emitter and quoted.
        """
        cache = self._ghost_cache.setdefault(thing["lane"], [])
        if cache or thing.get("model_only"):
            return cache
        try:
            ast = parse_grammar(thing["text_fn"](), thing["flavour"])
        except LexicError:
            return cache
        for name in ("gbnf", "abnf", "ebnf"):
            flavour = get_flavour(name)
            if type(flavour) is type(thing["flavour"]):
                continue
            try:
                spelled = str(flavour.apply(ast))
                cache.append((name, True, f"spells — {len(spelled):,} chars"))
            except LexicError as refusal:
                cache.append((name, False, str(refusal)[:150]))
        return cache

    def ghosts(self) -> list[tuple[str, bool, str]]:
        """The base grammar's offers — what the census and casts ask for."""
        base = next((t for t in self.things if not t.get("model_only")), None)
        return self.ghosts_for(base) if base else []

    def _base_ast(self):
        """The base grammar's IR value — parsed once, by the climb's flavour."""
        if getattr(self, "_ast", None) is None and self.climbed is not None:
            self._ast = parse_grammar(self.base_grammar.read_text(),
                                      self.climbed)
        return getattr(self, "_ast", None)

    def cast_transpile(self, name: str) -> str:
        """Take a transpile ghost: the peer becomes its OWN THING.

        Related to its origin, yes — but its own lane, with its own inward
        and compiler rungs and its own artefact family (its reader is
        flavour-kept, so its twin exports where the origin's may refuse).
        """
        licensed = {g[0]: g[1] for g in self.ghosts()}
        if not licensed.get(name):
            return "refuse unlicensed or unknown flavour\n"
        flavour = get_flavour(name)
        spelled = str(flavour.apply(self._base_ast()))
        spell_meta = str(flavour.apply(flavour.grammar))
        desc = (f"the {name.upper()} metagrammar "
                f"({len(flavour.grammar.rules)} rules), spelled by its own emitter")
        label = f"≅ {self.base_grammar.stem}.{name} ⊳ {name} metagrammar"
        if any(r[0] == label for r in self.rungs):
            return f"rung {next(i for i, r in enumerate(self.rungs) if r[0] == label)}\n"
        peer_lane = self._lane(f"≅ {self.base_grammar.stem}.{name}")
        index = len(self.rungs)
        self.rungs.append((label, "r",
                           self._rung(flavour, spell_meta, desc, spelled, None)))
        self.levels.append(1)
        self.lanes.append(peer_lane)
        thing = dict(lane=peer_lane, name=f"{self.base_grammar.stem}.{name}",
                     flavour=flavour, text_fn=lambda s=spelled: s,
                     reader_fn=lambda f=flavour: flavour_cg(f),
                     cg_fn=lambda f=flavour, s=spelled: compile_text(s, flavour=f))
        self.things.append(thing)
        self._thing_places(thing)
        self._artefacts = None
        return f"rung {index}\n"

    # ── the artefact FAMILY: species by codomain, load-backs tried ─────

    def artefacts(self) -> list[tuple]:
        """Per thing: ir value · twin · model molecule — never one file kind.

        Species is decided by the value's codomain ("there is no target
        flag"); every written artefact is LOADED BACK and compared to its
        origin; every refusal carries the engine's words.
        """
        if self._artefacts is None:
            rows: list[tuple] = []
            for thing in self.things:
                rows.extend(_thing_artefacts(self, thing))
            self._artefacts = rows
            for i, row in enumerate(rows):
                pid = f"a{row[0]}_{i}"
                self.places[pid] = dict(
                    pid=pid, lane=row[0], band=-3, kind="artefact",
                    label=f"{row[1]} — {row[3]}",
                    facts=row[4], ok=row[2],
                    sections=lambda r=row: artefact_sections(r))
        return self._artefacts

    def _rung(self, flavour, reader_text, desc, document, doc_path):
        """One climb rung as a lazy builder — bound now, built on focus."""
        return lambda: Subject.from_reading(
            self.key, flavour_cg(flavour), reader_text, desc, document, doc_path)

    def _policy_rung(self):
        subj = Subject.from_reading(
            self.key, compile_from_path(str(HERE / "fixtures" / "policy.gbnf")),
            (HERE / "fixtures" / "policy.gbnf").read_text(),
            "policy.gbnf — the instrument's own state; saving APPLIES the record",
            self.policy_text(), None)
        subj.is_policy = True
        return subj

    def policy_text(self) -> str:
        return "".join(f"{k} {v}\n" for k, v in self.policy.items())

    def subject(self, i: int | None = None) -> Subject:
        i = self.focus if i is None else max(0, min(i, len(self.rungs) - 1))
        if i not in self.subjects:
            subj = self.rungs[i][-1]()
            subj.policy = self.policy  # one record for the whole session
            self.subjects[i] = subj
        subj = self.subjects[i]
        if getattr(subj, "is_policy", False):
            fresh = self.policy_text()
            if fresh != subj.document:
                subj.read(fresh)  # the record moved on — the reading follows
        return subj


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

    session: Session

    @property
    def subject(self) -> Subject:
        return self.session.subject()

    @subject.setter
    def subject(self, value: Subject) -> None:
        # the census drives a bare handler with one subject — wrap it
        holder = Session.__new__(Session)
        holder.key = value.key
        holder.rungs = [("census", "r", None)]
        holder.subjects = {0: value}
        holder.focus = 0
        holder.policy = value.policy
        self.session = holder

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
                scene = build_scene(self.subject)
            rungs = [f"{i} {1 if i == self.session.focus else 0} {kind} {label}"
                     for i, (label, kind, *_b) in enumerate(self.session.rungs)]
            scene = scene.replace("#RULEDEFS", f"#LADDER {len(rungs)}\n" + "\n".join(rungs) + "\n#RULEDEFS", 1)
            self.send_text(scene)
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
            words = clock.get("pda_words") or clock.get("pda_error")
            if words:
                out.append(f"pda_words {words.splitlines()[0]}")
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
        if self.path == "/strata":
            self.send_text(strata_frame(self.session))
            return
        if self.path.startswith("/place?id="):
            pid = unquote(self.path.split("=", 1)[1])
            self.session.artefacts()
            if pid == "index":
                self.send_text(places_index(self.session))
                return
            place = self.session.places.get(pid)
            if place is None:
                self.send_text(f"no such place {pid}")
                return
            out = [f"#PLACE {pid} {place['kind']} {place['label']}"]
            try:
                emit_sections(out, place["sections"]())
            except LexicError as refusal:
                emit_sections(out, [("refusal", str(refusal)[:300])])
            self.send_text("\n".join(out) + "\n")
            return
        if self.path.startswith("/irvalue?"):
            query = dict(part.split("=", 1) for part in
                         self.path.split("?", 1)[1].split("&") if "=" in part)
            place = self.session.places.get(unquote(query.get("place", "")))
            if place is None or "value_fn" not in place:
                self.send_text("nodes 0\n#NODES 0\n#IREDGES 0\n#KIDS 0")
                return
            self.send_text(irview.frame(place["value_fn"](),
                                        unquote(query.get("path", ""))))
            return
        if self.path.startswith("/rulegraph?place="):
            spec = unquote(self.path.split("=", 1)[1])
            pid, _, stage = spec.partition("|")
            place = self.session.places.get(pid)
            if place is None or "cg_fn" not in place:
                self.send_text("#RG 0")
                return
            cg = place["cg_fn"]()
            ast = cg.grammar if stage != "codegen" else cg.codegen_grammar
            edges, depth = rule_graph(ast)
            rows = [f"n {rule.name} {i} {depth.get(str(rule.name), 99)}"
                    for i, rule in enumerate(ast.rules)]
            rows += [f"e {a} {b}" for a, b in dict.fromkeys(edges)]
            self.send_text(f"#RG {len(rows)}\n" + "\n".join(rows))
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
        if self.path == "/focus":
            i = int(body.split()[-1])
            self.session.focus = max(0, min(i, len(self.session.rungs) - 1))
            self.session.subject()  # build the rung now, synchronously
            print(f"focus -> rung {self.session.focus}: {self.session.rungs[self.session.focus][0]}")
            self.send_text("ok")
            return
        if self.path == "/cast":
            words = body.split()
            if len(words) == 2 and words[0] == "transpile":
                self.send_text(self.session.cast_transpile(words[1]))
            else:
                self.send_text("refuse unknown cast")
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
            if getattr(self.subject, "is_policy", False):
                self.session.policy.clear()
                for line in candidate.split("\n"):
                    if line.strip():
                        key, _, value = line.partition(" ")
                        self.session.policy[key] = value
                print(f"policy applied from the record — {len(self.session.policy)} keys")
                return f"ok {self.subject.seconds:.2f} applied — the session takes this record"
            held = self.subject.save_held()
            if held:
                return f"ok {self.subject.seconds:.2f} held {held}"
            self.subject.doc_path.write_text(self.subject.document)
            print(f"saved {self.subject.doc_path}")
            return f"ok {self.subject.seconds:.2f} saved"


# ── room sections: what a subject IS, spelled as wire sections ─────────


def _short(value: object, n: int = 70) -> str:
    text = repr(value).replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 1] + "…"


def _floor_walk(value, depth: int, lines: list, limit: int = 140) -> None:
    """The floor's bounded structure walk — a facet degrades by deriving less."""
    if len(lines) >= limit or depth > 7:
        return
    fields = getattr(value, "_fields", None)
    for i, child in enumerate(tuple(value.children())[:14]):
        name = fields[i] if fields and i < len(fields) else ""
        head = f"·{name} " if name else ""
        lines.append((depth, f"{head}{type(child).__name__}  {_short(child, 52)}"))
        _floor_walk(child, depth + 1, lines, limit)


_WITNESS: dict[int, str] = {}


def _notation_witness(text: str) -> str:
    """CAN lexic re-read this spelling? A computed fact on the facet."""
    key = hash(text)
    if key not in _WITNESS:
        if len(text) > 40000:
            _WITNESS[key] = "not tried — large; the fact is computable on demand"
        else:
            try:
                model = notation_reader().parse(text)
                _WITNESS[key] = ("parses, re-emits byte-identical — holds"
                                 if str(model.to_text()) == text else "parses — re-emission differs")
            except UnsupportedConstructError as refusal:
                _WITNESS[key] = f"refuses: {str(refusal)[:90]}"
    return _WITNESS[key]


def _model_of(thing) -> object:
    """The model product of a thing's text under its reader — plug on refusal."""
    reader, text = thing["reader_fn"](), thing["text_fn"]()
    try:
        return reader.parse(text)
    except UnsupportedConstructError as refusal:
        if "ambiguous" not in str(refusal):
            raise
        return reader.parse(text, resolve=first)


def value_sections(session, thing, reduction) -> list:
    """The VALUE room, as FACETS: the reduction plug, the IR itself, the
    operations that take this value elsewhere.

    The IR is not shown as a string: `irvalue` is a live surface (identity,
    tiers, sharing, absence, refusal) the leaf draws and zooms.
    """
    lane = thing["lane"]
    candidates = [
        (("● " if r["key"] == reduction["key"] else "○ ") + r["label"],
         f"place:v{lane}{r['key']}")
        for r in session.reductions(thing)]
    facets = [("facet", "the reduction — a plug, with its candidates"),
              ("list", candidates),
              ("facet", "the value itself — IR as IR"),
              ("irvalue", f"v{lane}{reduction['key']}")]
    if not thing.get("model_only"):
        facets.append(("facet", "operations on this value"))
        ops = [(f"⧉ compile it — a reader over instances", f"place:c{lane}")]
        for name, ok, words in session.ghosts_for(thing):
            ops.append((("≅ respell through " + name + " — " + words)
                        if ok else ("≅ " + name + " refuses: " + words),
                        f"cast:transpile {name}" if ok else ""))
        facets.append(("list", ops))
    return facets


def compiler_sections(cg, flavour, lane: int) -> list:
    """The COMPILER room — ONE room, the pipeline's stages as facets.

    Canonical and codegen are not separate rooms: they are two states of
    one object, and the binding view is the bridge to the class world.
    """
    binding = compute_binding(cg.codegen_grammar)
    rows = [(f"{b.rule_name}  →  {b.class_name}  ({b.kind}; "
             f"{', '.join(b.fields) or 'no fields'})", "") for b in binding]
    delta = len(cg.codegen_grammar.rules) - len(cg.grammar.rules)
    return [
        ("facet", "the pipeline"),
        ("kv", [("stages", "canonical → hoist groups → hoist arms → relax noise "
                           "→ binding → classes"),
                ("canonical rules", str(len(cg.grammar.rules))),
                ("codegen rules", f"{len(cg.codegen_grammar.rules)} "
                                  f"({delta:+d} from hoisting)"),
                ("classes", str(len(cg.classes))),
                ("flavour", str(cg.flavour))]),
        ("facet", "canonical — the language-preserving normal form"),
        ("graphview", f"c{lane}|canonical"),
        ("textlines", str(flavour.apply(cg.grammar))),
        ("facet", "codegen — what the parser and the classes are built from"),
        ("graphview", f"c{lane}|codegen"),
        ("textlines", str(flavour.apply(cg.codegen_grammar))),
        ("facet", f"the binding view — {len(binding)} rules bound"),
        ("list", rows),
    ]


def artefact_sections(session, thing) -> list:
    """The ARTEFACTS room: the family compressed to a selector, then one file.

    Species is decided by the reduction's codomain — a value alone has three
    (ir · model · plain). Every row states its witnesses; the selected file
    is shown whole.
    """
    lane = thing["lane"]
    rows = [r for r in session.artefacts() if r[0] == lane]
    picks = [((("● " if i == 0 else "○ ") + f"{r[1]} — {r[3]}"),
              f"artefact:{lane}:{i}") for i, r in enumerate(rows)]
    facets: list = [("facet", f"the family — {len(rows)} artefacts, "
                              "species by the reduction's codomain"),
                    ("list", picks)]
    for i, row in enumerate(rows):
        facets.append(("kv", [(row[1], row[4])]))
    if rows:
        facets.append(("facet", f"the file — {rows[0][3]}"))
        facets.append(("textlines", _artefact_text(rows[0])))
    return facets


def _artefact_text(row) -> str:
    if not row[2]:
        return row[4]
    path = ROOT / "generated" / row[3]
    body = path.read_text() if path.is_file() else "(not on disk)"
    return body if len(body) < 80000 else body[:80000] + " …clipped"


def emit_sections(out: list[str], sections: list) -> None:
    for sec in sections:
        kind = sec[0]
        if kind == "textlines":
            lines = str(sec[1]).split("\n")
            out.append(f"#SEC textlines {len(lines)}")
            out.extend("|" + line for line in lines)
        elif isinstance(sec[1], str):
            # any single-line kind (title · refusal · facet · graphview ·
            # irvalue): a STRING payload is one line, never a row sequence
            out.append(f"#SEC {kind} 1")
            out.append(sec[1])
        else:
            out.append(f"#SEC {kind} {len(sec[1])}")
            out.extend("\t".join(str(cell) for cell in row) for row in sec[1])


def _gen_stem(key: str, name: str) -> str:
    return "space_" + re.sub(r"[^A-Za-z0-9_]", "_", f"{key}_{name}")


def _load_back(module_name: str):
    """Import a freshly written artefact — the loading half of the round trip."""
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


def _thing_artefacts(session: Session, thing: dict) -> list[tuple]:
    """Every species this thing's reductions can project to — never one kind."""
    rows = []
    stem = _gen_stem(session.key, thing["name"])
    gen = ROOT / "generated"
    if not thing.get("model_only"):
        rows.append(_ir_artefact(thing, gen, stem))
        rows.append(_twin_artefact(thing, gen, stem))
    rows.append(_molecule_artefact(thing, gen, stem))
    rows.append(_plain_artefact(thing, gen, stem))
    return rows


def _plain_artefact(thing: dict, gen: Path, stem: str) -> tuple:
    """The plain species: a reduction whose codomain names nothing of lexic.

    The text itself is the simplest such value — it imports nothing and
    carries a digest alone, which is exactly what the species means.
    """
    try:
        path = export_value(thing["text_fn"](), gen / f"{stem}_plain.py")
        back = _load_back(f"generated.{stem}_plain").VALUE == thing["text_fn"]()
        return (thing["lane"], "plain value", True, path.name,
                f"{path.stat().st_size:,} bytes · imports NOTHING · digest only "
                f"· loads back equal — {'holds' if back else 'FAILS'}")
    except LexicError as refusal:
        return (thing["lane"], "plain value", False, "refused", str(refusal)[:160])


def _ir_artefact(thing: dict, gen: Path, stem: str) -> tuple:
    """The grammar as an ir-value artefact: spine imports only, digest-gated."""
    try:
        grammar = thing["cg_fn"]().grammar
        path = export_value(grammar, gen / f"{stem}_grammar.py")
        back = _load_back(f"generated.{stem}_grammar").VALUE == grammar
        return (thing["lane"], "ir value", True, path.name,
                f"{path.stat().st_size:,} bytes · imports the spine only · "
                f"digest-gated · loads back equal — {'holds' if back else 'FAILS'}")
    except LexicError as refusal:
        return (thing["lane"], "ir value", False, "refused", str(refusal)[:160])


def _twin_artefact(thing: dict, gen: Path, stem: str) -> tuple:
    """The importable twin: grammar spelled twice, re-parsed and cross-checked."""
    try:
        cg = thing["cg_fn"]()
        source = export_source(cg, stem=stem)
        verify_module(cg, source)
        export_module(cg, gen / f"{stem}.py", stem=stem)
        return (thing["lane"], "twin", True, f"{stem}.py",
                f"{len(source):,} chars · the grammar spelled twice · re-parsed by "
                "lexic, GRAMMAR equals the canonical AST — holds")
    except LexicError as refusal:
        return (thing["lane"], "twin", False, "refused", str(refusal)[:160])


def _molecule_artefact(thing: dict, gen: Path, stem: str) -> tuple:
    """The parsed value as a two-file molecule importing its reader's twin."""
    try:
        model = _model_of(thing)
        reader_cg = thing["reader_fn"]()
        export_module(reader_cg, gen / f"{stem}_reader.py", stem=f"{stem}_reader")
        path = export_value(model, gen / f"{stem}_value.py",
                            module=f"generated.{stem}_reader")
        loaded = _load_back(f"generated.{stem}_value").VALUE
        # twin classes are never == runtime classes; behaviour is the witness
        # (the codebase's own sameness doctrine): SHAPE + byte-equal emission
        back = (type(loaded).__shape__ == type(model).__shape__
                and str(loaded.to_text()) == str(model.to_text()))
        return (thing["lane"], "model value", True, path.name,
                f"{path.stat().st_size:,} bytes · a molecule importing its reader's "
                f"twin · SHAPE-gated at import · loads back, SHAPE equal, "
                f"re-emits byte-identical — {'holds' if back else 'FAILS'}")
    except LexicError as refusal:
        return (thing["lane"], "model value", False, "refused", str(refusal)[:160])


def _band(subject: Subject, buckets: int = 64) -> list[int]:
    """The document as span density, downsampled — the card's miniature."""
    counts = [0] * buckets
    n = max(1, len(subject.document))
    for span in subject.spans:
        a = min(buckets - 1, span.start * buckets // n)
        b = min(buckets - 1, max(span.end - 1, span.start) * buckets // n)
        for k in range(a, b + 1):
            counts[k] += 1
    top = max(counts) or 1
    return [round(v * 9 / top) for v in counts]


def places_index(session: Session) -> str:
    """The place facet's own index — every room this session holds, by thing.

    The menu carries readings and nothing else; the rooms are reached from
    inside the instrument, where they belong.
    """
    out = ["#PLACE index index the rooms this session holds"]
    sections: list = []
    for thing in session.things:
        rows = [(p["label"], f"place:{p['pid']}")
                for p in session.places.values() if p["lane"] == thing["lane"]]
        if rows:
            sections.append(("facet", thing["name"]))
            sections.append(("list", rows))
    emit_sections(out, sections or [("refusal", "no rooms yet")])
    return "\n".join(out) + "\n"


def strata_frame(session: Session) -> str:
    """The session as a GRID: rows are the strata and bands (the shared
    vertical), columns are things; readings in the strata, rooms in the
    bands; plugs on readings; sibling reductions in the same cell."""
    session.artefacts()  # ensures the artefact places exist
    out = [f"#STRATA {len(session.rungs)} {session.focus}"]
    out.extend(f"L {i} {name}" for i, name in enumerate(session.lane_names))
    for i, (label, kind, _build) in enumerate(session.rungs):
        level = session.levels[i] if i < len(session.levels) else 0
        lane = session.lanes[i] if i < len(session.lanes) else 0
        visited = 1 if i in session.subjects else 0
        out.append(f"c {i} {level} {lane} {kind} {visited} {label}")
        if visited:
            subject = session.subjects[i]
            out.append(f"k {i} {len(subject.document)} {len(subject.spans)} "
                       f"{len(subject.rule_lines())} {subject.seconds:.2f} "
                       f"{1 if subject.faithful else 0} "
                       f"{1 if subject.resolve else 0}")
            out.append(f"b {i} " + " ".join(str(v) for v in _band(subject)))
            out.append(f"p {i} reduction=model "
                       f"resolver={'first' if subject.resolve else '—'} "
                       f"vocabulary="
                       f"{'token-segmented' if subject.compiled.tokens.segmented else 'char'}")
    for place in session.places.values():
        state = "no" if place.get("ok") is False else "ok"
        facts = place.get("facts", "")
        out.append(f"P {place['pid']} {place['lane']} {place['band']} "
                   f"{place['kind']} {state} {place['label']}\t{facts}")
    return "\n".join(out) + "\n"


def leaf_collisions() -> list[str]:
    """Top-level names the leaf declares TWICE — a silent-override gate.

    A second ``function f`` hoists over the first: the older one keeps its
    call sites and quietly becomes the new body. That is how the reader's
    rule graph went blank (a new `drawGraphView` shadowed atlas's), with
    every server-side gate still green. Names are cheap; measure them.
    """
    text = (LEAF / "leaf.js").read_text()
    names: dict[str, int] = {}
    for match in re.finditer(r"^(?:async )?function (\w+)|^(?:const|let|var) (\w+)",
                             text, re.M):
        name = match.group(1) or match.group(2)
        names[name] = names.get(name, 0) + 1
    return sorted(n for n, count in names.items() if count > 1)


def leaf_doors() -> list[str]:
    """Facets the dock cannot reach — a facet with no door is a facet gone.

    The rooms facet shipped invisible once (it was not in the default tree,
    and the dock only drew chips for tree leaves), so the capability was on
    the wire and off the screen. The dock is the REGISTRY: it iterates
    FACETS, not the current arrangement.
    """
    text = (LEAF / "leaf.js").read_text()
    match = re.search(r"const FACETS = \[([^\]]*)\]", text)
    names = re.findall(r"'(\w+)'", match.group(1)) if match else []
    registry = "for (const name of FACETS)" in text
    missing = [n for n in names if f'id="{n}"' not in (LEAF / "index.html").read_text()]
    return (missing if registry else names + ["dock draws the tree, not FACETS"])


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
    doors = leaf_doors()
    print(f"leaf: every facet has a door in the dock {not doors}"
          + (f" · NO DOOR: {', '.join(doors)}" if doors else ""))
    dupes = leaf_collisions()
    print(f"leaf: no top-level name declared twice {not dupes}"
          + (f" · COLLIDES: {', '.join(dupes)}" if dupes else ""))
    ok = (subject.faithful and ok_scene and ok_edit and ok_refuse and ok_frontier
          and ok_save and ok_routes and ok_graph and ok_policy and ok_rail and ok_clock
          and ok_auto and ok_verdicts and not dupes and not doors)
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
    session = Session(key, doc)
    subject = session.subject(0)
    print(f"{subject.reader_desc} read {len(subject.document):,} chars in {subject.seconds:.2f}s · "
          f"{len(subject.spans):,} spans · faithful {subject.faithful}")
    if "--census" in sys.argv:
        rc = census(subject)
        if len(session.rungs) > 2:
            oi = next(i for i, r in enumerate(session.rungs) if r[1] == "o")
            ok_export = True  # the twin's claim is witnessed in the artefacts room
            session.policy["graph.view"] = "rails"
            opsis = session.subject(oi)
            ok_opsis = opsis.faithful and "graph.view rails" in opsis.document
            handler = Handler.__new__(Handler)
            handler.session = session
            session.focus = oi
            reply = handler.retype(f"0 {len(opsis.document)}\narrange.top 0.5\ngraph.view rails\n",
                                   persist=True)
            ok_ring = "applied" in reply and session.policy.get("arrange.top") == "0.5"
            session.focus = 0
            print(f"ladder: {len(session.rungs)} rungs · "
                  f"opsis rung reads the record {ok_opsis} · the ring applies {ok_ring}")
            if not (ok_export and ok_opsis and ok_ring):
                rc = 1
            base_lane = min(t["lane"] for t in session.things
                            if not t.get("model_only"))
            vm = session.places[f"v{base_lane}m"]
            vi = session.places[f"v{base_lane}i"]
            model_v, ir_v = vm["value_fn"](), vi["value_fn"]()
            ok_two = type(model_v) is not type(ir_v)
            vroom = vi["sections"]()
            vkinds = [s[0] for s in vroom]
            ok_value = "irvalue" in vkinds and vkinds.count("facet") >= 2
            nodes, edges = irview.dag(ir_v)
            shared = [n for n in nodes if n[6] > 1]
            ok_dag = bool(nodes) and len(edges) >= len(nodes) - 1
            ok_ops = any(s[0] == "list" and any("respell" in r[0] or "compile it" in r[0]
                                                for r in s[1]) for s in vroom)
            croom = session.places[f"c{base_lane}"]["sections"]()
            ckinds = [s[0] for s in croom]
            ok_compiler = (ckinds.count("facet") >= 4
                           and ckinds.count("graphview") == 2
                           and ckinds.count("textlines") == 2)
            ok_grammar = ok_compiler
            aroom = session.places[f"a{base_lane}"]["sections"]()
            ok_art = any(s[0] == "list" and len(s[1]) >= 3 for s in aroom)
            print(f"values: two reductions give two types "
                  f"({type(model_v).__name__} vs {type(ir_v).__name__}) {ok_two} · "
                  f"IR DAG {len(nodes)} nodes / {len(edges)} edges / "
                  f"{len(shared)} shared {ok_dag} · operations on the value {ok_ops} · "
                  f"artefact selector {ok_art}")
            if not (ok_two and ok_dag and ok_ops and ok_art):
                rc = 1
            frame = strata_frame(session)
            ok_plugs = any(ln.startswith("p 0 reduction=")
                           for ln in frame.splitlines())
            ok_sibling = (f"P v{base_lane}m" in frame and f"P v{base_lane}i" in frame
                          and not any(ln.startswith("g ") for ln in frame.splitlines()))
            n_places = sum(1 for ln in frame.splitlines() if ln.startswith("P "))
            ok_places = n_places == len(session.places) and n_places >= 8
            print(f"rooms: value room (plug + IR surface + operations) {ok_value} · "
                  f"compiler is ONE room with both stages {ok_compiler} · "
                  f"{n_places} places · plugs stated {ok_plugs} · "
                  f"reduction candidates offered {ok_sibling}")
            if not (ok_value and ok_grammar and ok_compiler and ok_plugs
                    and ok_sibling and ok_places):
                rc = 1
            family = session.artefacts()
            species = {row[1] for row in family}
            ok_family = {"ir value", "twin", "model value"} <= species
            ok_backs = all("holds" in row[4] for row in family if row[2])
            ok_refusals = all(row[4] for row in family if not row[2])
            for lane, kind_, ok_, label_, facts in family:
                state = "ok " if ok_ else "REFUSED"
                print(f"  artefact [{session.lane_names[lane]}] {kind_}: {state} "
                      f"{label_} · {facts[:110]}")
            ok_lanes = (len(session.lanes) == len(session.rungs)
                        and all(0 <= ln < len(session.lane_names)
                                for ln in session.lanes))
            print(f"artefact family: species {sorted(species)} · every load-back "
                  f"holds {ok_backs} · refusals quoted {ok_refusals} · lanes {ok_lanes}")
            if not (ok_family and ok_backs and ok_refusals and ok_lanes):
                rc = 1
        frame = strata_frame(session)
        cards = [ln.split() for ln in frame.splitlines() if ln.startswith("c ")]
        ok_cards = (len(cards) == len(session.rungs)
                    and len(session.levels) == len(session.rungs))
        top = max(int(c[2]) for c in cards)
        ok_levels = top >= 1 and any(int(c[2]) == -3 for c in cards)
        ghosts = session.ghosts()
        ok_ghosts = len(ghosts) == 2 and all(w for _n, _ok, w in ghosts)
        licensed = [n for n, is_ok, _w in ghosts if is_ok]
        ok_cast, peer_note = True, "no licensed transpile — refusals quoted"
        if licensed:
            reply = session.cast_transpile(licensed[0])
            ok_cast = reply.startswith("rung ")
            if ok_cast:
                peer = session.subject(int(reply.split()[1]))
                ok_cast = peer.faithful
                peer_note = f"≅ {licensed[0]} peer built, faithful {peer.faithful}"
        print(f"strata: {len(cards)} cards, top level {top} · "
              f"ghosts {[(n, g) for n, g, _w in ghosts]} · {peer_note}")
        if not (ok_cards and ok_levels and ok_ghosts and ok_cast):
            rc = 1
        return rc
    Handler.session = session
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"facets at http://127.0.0.1:{port}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
