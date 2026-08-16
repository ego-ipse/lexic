"""3e acceptance harness — space_3's span derivation, before vs after.

Snapshot the spans `praxis.reading.fold` produces (`--save`), swap the
derivation onto `GrammarModel.emit_addressed`, then compare (`--check`).
Byte-identity of the five fields every space_3 consumer reads is the verdict.

    uv run python zzz_current_work/260816-opsis-meta/probes/adv_space3_spans.py --save
    uv run python zzz_current_work/260816-opsis-meta/probes/adv_space3_spans.py --check
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPACE3 = ROOT / "zzz_current_work/260807-opsis-radical/space_3"
if str(SPACE3) not in sys.path:
    sys.path.insert(0, str(SPACE3))

from praxis.reading import fold  # noqa: E402

from lexic.compile import canonical_grammar, compile_from_path  # noqa: E402
from lexic.generate import generate  # noqa: E402
from lexic.grammars.gbnf import GBNF_FLAVOUR  # noqa: E402

SNAPSHOT = Path(__file__).with_name("space3_spans.json")
GT = ROOT / "resources/ground_truth"
CORPUS = (
    "arithmetic.gbnf",
    "chess.gbnf",
    "japanese.gbnf",
    "json.gbnf",
    "json_arr.gbnf",
    "json_ws.gbnf",
    "list.gbnf",
)
SEEDS = range(6)
FIXTURES = (
    (SPACE3 / "fixtures/decide.gbnf", SPACE3 / "fixtures/decide.txt"),
    (SPACE3 / "fixtures/ambiguous.ebnf", SPACE3 / "fixtures/ambiguous.txt"),
)


def documents(name: str) -> list[str]:
    """Deterministic generated documents for one ground-truth grammar."""
    ast = canonical_grammar((GT / name).read_text(), GBNF_FLAVOUR)
    rules = {rule.name: rule for rule in ast.rules}
    texts = [generate(ast.start, rules, rng=random.Random(s)) for s in SEEDS]
    return [t for t in texts if t]


def rows() -> dict[str, list]:
    """Every case's `(text, spans)` as plain data, keyed by case name."""
    out: dict[str, list] = {}
    for name in CORPUS:
        compiled = compile_from_path(GT / name)
        for index, text in enumerate(documents(name)):
            spelled, spans = fold(compiled.parse(text))
            out[f"{name}#{index}"] = [
                spelled,
                [[s.start, s.end, s.depth, str(s.rule), s.field] for s in spans],
            ]
    for grammar, document in FIXTURES:
        if not (grammar.exists() and document.exists()):
            continue
        compiled = compile_from_path(grammar)
        spelled, spans = fold(compiled.parse(document.read_text()))
        out[grammar.name] = [
            spelled,
            [[s.start, s.end, s.depth, str(s.rule), s.field] for s in spans],
        ]
    return out


def main() -> None:
    """Save the snapshot, or check the live derivation against it."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    live = rows()
    if mode == "--save":
        SNAPSHOT.write_text(json.dumps(live, indent=1, ensure_ascii=False))
        total = sum(len(spans) for _text, spans in live.values())
        print(f"saved {len(live)} cases, {total} spans -> {SNAPSHOT.name}")
        return
    saved = json.loads(SNAPSHOT.read_text())
    if set(saved) != set(live):
        print(f"FAIL case sets differ: {set(saved) ^ set(live)}")
        sys.exit(1)
    bad = [key for key in saved if saved[key] != live[key]]
    total = sum(len(spans) for _text, spans in live.values())
    if bad:
        for key in bad[:3]:
            before, after = saved[key][1], live[key][1]
            print(f"FAIL {key}: {len(before)} spans before, {len(after)} after")
            for old, new in zip(before, after):
                if old != new:
                    print(f"   before {old}\n   after  {new}")
                    break
        sys.exit(1)
    print(f"IDENTICAL: {len(live)} cases, {total} spans, all five fields")


if __name__ == "__main__":
    main()
