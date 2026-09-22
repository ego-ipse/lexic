"""The worker ladder on large documents OF the grammar — wiring only.

The documents come from the library's own generator,
:func:`lexic.generate.generate` with ``size=``; nothing here generates. What
this module owns is which grammars, the ladder, and where each rung runs.

**Which grammars** is derived, not listed: every bench whose grammar has
derived bracket PAIRS (:func:`lexic.parsing.parallel.roles`) — where nested
regions, and the split protocol's large states, live — plus the ground-truth
``json.gbnf``, the second json formulation beside the bench's own.

**Where a rung runs.** Each rung is a fresh process pinned by :data:`PIN`
before it imports anything — importing the benches already starts threads —
so every thread it ever has inherits the mask, and the rung reports the mask it
holds rather than the one it was asked for. A rung of ``n`` workers gets ``n``
DISTINCT PHYSICAL cores while the machine has them (one logical CPU per core,
read from sysfs); a wider rung gets every logical CPU and records ``distinct=False``, because SMT
siblings share a core's execution units and a paired rung measures the pairing
as much as it measures lexic.

    uv run python -m tools.benchmark.diagnostics.ladder make <dir> [size]
    uv run python -m tools.benchmark.diagnostics.ladder run <dir> [rungs...]
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

from lexic.compile import canonical_grammar, compile_text
from lexic.generate import generate
from lexic.grammars import get_flavour
from lexic.parsing.parallel import roles
from tools.benchmark.cases.corpora import ground_truth
from tools.benchmark.cases.grammars import BENCHES

RUNGS = (1, 2, 4, 8, 16)
SIZE = 1_800_000
DEPTH = 48
"""Room for a 1.8 MB budget to nest: halving pieces reach it in about twenty
levels, and a few references sit between one bracket and the next."""
REPEATS = 3
SYSFS = Path("/sys/devices/system/cpu")
MODULE = "tools.benchmark.diagnostics.ladder"
PIN = (
    "import os, runpy, sys; "
    "os.sched_setaffinity(0, {int(c) for c in sys.argv.pop(1).split(',')}); "
    "runpy.run_module(sys.argv.pop(1), run_name='__main__', alter_sys=True)"
)
"""A rung's first statement: pin to the CPUs, then run the named module as
``__main__`` — :data:`MODULE`, by its import name, since under ``-m`` this
module's own ``__name__`` is ``__main__``."""


class Rung(NamedTuple):
    """Where one rung runs: its CPUs, and whether they are distinct cores."""

    workers: int
    cpus: tuple[int, ...]
    distinct: bool


def physical_cores(siblings: dict[int, tuple[int, ...]]) -> list[int]:
    """One logical CPU per physical core — the lowest of each sibling set."""
    return sorted({min(group) for group in siblings.values()})


def rung_for(workers: int, siblings: dict[int, tuple[int, ...]]) -> Rung:
    """The CPUs a rung of ``workers`` is pinned to."""
    cores = physical_cores(siblings)
    if workers <= len(cores):
        return Rung(workers, tuple(cores[:workers]), True)
    return Rung(workers, tuple(sorted(siblings)), False)


def read_siblings() -> dict[int, tuple[int, ...]]:
    """This machine's SMT sibling sets, by logical CPU."""
    out: dict[int, tuple[int, ...]] = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        text = (SYSFS / f"cpu{cpu}" / "topology" / "thread_siblings_list").read_text()
        out[cpu] = tuple(_expand(text.strip()))
    return out


def _expand(spec: str) -> list[int]:
    """A sysfs CPU list (``0,8`` or ``0-1``) as ints."""
    out: list[int] = []
    for part in spec.split(","):
        low, _dash, high = part.partition("-")
        out.extend(range(int(low), int(high or low) + 1))
    return out


def grammars() -> list[tuple[str, str, str]]:
    """``(label, flavour, source)`` for every grammar the ladder measures."""
    out = [
        (bench.name, bench.flavour, bench.source)
        for bench in BENCHES
        if roles(bench.compiled.codegen_grammar).pairs
    ]
    out.append(("json.gbnf", "gbnf", ground_truth("json.gbnf")))
    return out


def write_document(path: Path, text: str) -> None:
    """Store a generated document exactly — no newline translation."""
    path.write_text(text, newline="")


def read_document(path: Path) -> str:
    """Read a stored document back exactly. The default would turn every
    ``\r`` into ``\n``: a generated json's whitespace holds both, so the parse
    would be of a shorter, different document than the one generated."""
    return path.read_text(newline="")


def make(directory: Path, size: int) -> None:
    """Generate one document per grammar into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for label, flavour, source in grammars():
        ast = canonical_grammar(source, get_flavour(flavour))
        rules = {rule.name: rule for rule in ast.rules}
        rng = random.Random(0)
        text = generate(str(ast.start), rules, rng=rng, max_depth=DEPTH, size=size)
        write_document(directory / f"{label}.txt", text)
        print(f"{label}: {len(text):,} chars (target {size:,})", flush=True)


def measure(label: str, document: Path, workers: int) -> dict[str, object]:
    """One rung, in THIS process: already pinned by the caller."""
    source = {name: (flavour, text) for name, flavour, text in grammars()}[label]
    compiled = compile_text(source[1], flavour=source[0])
    text = read_document(document)
    model = compiled.parse(text, cores=workers)  # warm: replicas, pools, memos
    digest = hashlib.sha256(repr(model.dump()).encode()).hexdigest()[:16]
    times = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        compiled.parse(text, cores=workers)
        times.append(time.perf_counter() - start)
    return {"seconds": statistics.median(times), "all": times, "model": digest}


def run(directory: Path, rungs: tuple[int, ...]) -> None:
    """Every grammar at every rung, each rung a fresh pinned process."""
    siblings = read_siblings()
    rows = []
    for label, _flavour, _source in grammars():
        for workers in rungs:
            rung = rung_for(workers, siblings)
            document = str(directory / f"{label}.txt")
            cpus = ",".join(map(str, rung.cpus))
            cmd = [
                sys.executable,
                "-c",
                PIN,
                cpus,
                MODULE,
                "rung",
                label,
                document,
                str(workers),
            ]
            done = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if done.returncode:
                raise RuntimeError(f"{label} at {workers}: {done.stderr[-2000:]}")
            row = {"grammar": label, **rung._asdict(), **json.loads(done.stdout)}
            rows.append(row)
            print(json.dumps(row), flush=True)
    (directory / "ladder.json").write_text(json.dumps(rows, indent=1))


def main() -> None:
    """``make`` documents, ``run`` the ladder, or measure one pinned ``rung``."""
    verb, rest = sys.argv[1], sys.argv[2:]
    if verb == "rung":
        held = sorted(os.sched_getaffinity(0))
        print(
            json.dumps({**measure(rest[0], Path(rest[1]), int(rest[2])), "held": held})
        )
    elif verb == "make":
        make(Path(rest[0]), int(rest[1]) if len(rest) > 1 else SIZE)
    else:
        run(Path(rest[0]), tuple(int(n) for n in rest[1:]) or RUNGS)


if __name__ == "__main__":
    main()
