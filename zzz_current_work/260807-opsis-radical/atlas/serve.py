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

from lexic.compile import compile_ast, compile_from_path
from lexic.grammars import GBNF_FLAVOUR
from lexic.model import GrammarModel
from lexic.parsing import PdaKernel, earley_model, lift_optional_nullables, normalize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEAF = HERE / "leaf"
RULE_LINE = re.compile(r"^([A-Za-z0-9_-]+)\s*::=")
FRONTIER = re.compile(r"\bat (\d+)\b")


class Span(NamedTuple):
    """One model occurrence on the text axis, carrying its authored rule name."""

    start: int
    end: int
    depth: int
    rule: str
    field: str


def first(first_meaning: object, _witness: object) -> object:
    """The explicit ambiguity opt-out — a deterministic first-derivation resolver."""
    return first_meaning


class Subject:
    """The reading: reader text, document text, model, spans — and how to re-read."""

    def __init__(self, key: str) -> None:
        self.key = key
        if key == "long":
            self.compiled = compile_from_path(str(ROOT / "resources" / "ground_truth" / "json.gbnf"))
            self.reader_text = (ROOT / "resources" / "ground_truth" / "json.gbnf").read_text()
            self.reader_desc = "json.gbnf"
            self.doc_path = HERE.parent / "tk" / "fixtures_long.json"
            self.document = self.doc_path.read_text()
            self.resolve = None
        else:
            self.compiled = compile_ast(GBNF_FLAVOUR.grammar)
            self.reader_text = str(GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar))
            self.reader_desc = "the GBNF metagrammar (90 rules), spelled by its own emitter"
            name = "vyx.gbnf" if key == "vyx" else "json.gbnf"
            self.doc_path = ROOT / "resources" / "ground_truth" / name
            self.document = self.doc_path.read_text()
            self.resolve = first
        self.generation = 0
        self.t = 0.0
        self.selection = -1
        self.lock = threading.Lock()
        self.model: GrammarModel
        self.spans: list[Span]
        self.seconds: float
        self.faithful: bool
        self.route2: dict[str, str] = {}
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
            except Exception as fork:
                hit = FRONTIER.search(str(fork))
                result = {"status": "failed", "name": "PDA", "pos": hit.group(1) if hit else "-1",
                          "words": str(fork)[:160]}
        with self.lock:
            if self.generation == generation:
                self.route2 = result

    def save_held(self) -> str:
        """Why a save must not write, or empty when writing is allowed."""
        if "ground_truth" in str(self.doc_path):
            return "the document is repo ground-truth corpus; the instrument will not overwrite it"
        return ""

    def frontier(self, text: str) -> int:
        """The PDA's deepest verified position on ``text``, read from its own words.

        Only meaningful on the PDA route (no resolver): the kernel's failure
        signal spells its position in prose ("no arm at N") — no attribute
        carries it, which is the recorded lexic gap. -1 when unmeasurable.
        """
        if self.resolve is not None:
            return -1
        try:
            PdaKernel(self.compiled.pda_tables(), text, self.compiled.fold).run()
        except Exception as fail:
            hit = FRONTIER.search(str(fail))
            return int(hit.group(1)) if hit else -1
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
        f"#RULEDEFS {len(rules)}",
        *(f"{name} {a} {b}" for name, a, b in rules),
        f"#RULENAMES {len(rule_names)}",
        *rule_names,
        f"#FIELDNAMES {len(field_names)}",
        *field_names,
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
                pos = self.subject.frontier(candidate)
                print(f"refused at {pos}: {refusal}")
                return f"refuse {pos}\n{refusal}"
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
    # a mid-document control char is VALID inside the metagrammar's comments
    # (cmchar admits \x00-\t) — measured, not assumed. Corrupt where the
    # grammar cannot recover: mid-document on the PDA route (frontier check),
    # position 0 on resolver routes (no line form starts with \x01).
    mid = len(subject.document) // 2 if subject.resolve is None else 0
    refusal = handler.retype(f"{mid} {mid + 1}\n\x01")
    head, _, words = refusal.partition("\n")
    pos = int(head.split()[1]) if head.startswith("refuse") else -2
    ok_refuse = head.startswith("refuse") and subject.document[mid] != "\x01"
    ok_frontier = pos >= 0 if subject.resolve is None else pos == -1
    span0 = subject.spans[0]
    saved = handler.retype(
        f"{span0.start} {span0.end}\n{subject.document[span0.start:span0.end]}", persist=True
    )
    ok_save = saved.startswith("ok") and (" saved" in saved if subject.save_held() == "" else " held" in saved)
    print(f"{subject.key}: {len(subject.document):,} chars · {len(subject.spans):,} spans · "
          f"{len(subject.rule_lines())} rules in reader · parse {subject.seconds:.2f}s · scene {len(scene):,} bytes")
    print(f"faithful {subject.faithful} · scene integrity {ok_scene} · identity retype ok {ok_edit} · "
          f"garbage retype refused {ok_refuse} · frontier {pos} ({words[:48]}…)")
    print(f"save: {saved.split(chr(10))[0][:70]} · as expected {ok_save}")
    for _ in range(200):
        if subject.route2.get("status") != "pending":
            break
        time.sleep(0.05)
    r2 = subject.route2
    if subject.resolve is None:
        ok_routes = r2.get("status") == "done" and r2.get("parity") == "holds"
    else:
        ok_routes = r2.get("status") == "failed" and int(r2.get("pos", "-1")) >= 0
    print(f"other route: {r2} · as expected {ok_routes}")
    ok = subject.faithful and ok_scene and ok_edit and ok_refuse and ok_frontier and ok_save and ok_routes
    print("census ok" if ok else "census FAILED")
    return 0 if ok else 1


def main() -> int:
    """Entry — build the subject, then serve it or gate it."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    key = args[0] if args else "vyx"
    port = int(args[1]) if len(args) > 1 else 8901
    print(f"reading fixture '{key}' …")
    subject = Subject(key)
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
