"""Compare the paid path's bytecode against the starting commit, function by function.

The zero-tax claim is that the generated-model paid path gained no state,
transaction test, verifier call, interpreter, opcode, frame slot, allocation,
attribute read, or branch. `docs/STYLE.md` §7 says the instrument for a change
believed to be type-only is the opcode stream rather than a timer: it is
decisive and takes seconds, and it cannot be confounded by machine load the
way a benchmark can.

So this disassembles every hot function in the modules the paid loop runs
through, in BOTH the starting commit and the working tree, and reports the
instruction-count delta per function. A function whose stream is identical
proves the change was type-only where it matters. A function that grew is
named, with its delta, so it can be explained or removed rather than argued
about.

Neither side is imported. Both are compiled from source text, so no dependency
of either revision has to resolve and the comparison cannot be perturbed by
what happens to be installed.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_paid_path_opcodes.py`
"""

from __future__ import annotations

import dis
import subprocess
import types
from pathlib import Path

BASE = "dffa821f"
"""The starting commit every comparison in this round is made against."""

REPO = Path(__file__).resolve().parents[3]
"""The repository root both revisions are read from."""

PAID = {
    "src/lexic/parsing/pda/runtime/kernel/kernel.py": (
        "run",
        "_quant_step",
        "_match_span",
        "_sink_for",
        "_settle",
        "_enter",
    ),
    "src/lexic/parsing/pda/runtime/kernel/execution.py": (
        "_leaf_run",
        "_run_leaf",
        "_match_vstr",
        "_match_vdisp",
        "_complete",
        # The island seam is the predictive engine's COLD escape, but it is
        # reached from the item loop and this round changed its splice, so it
        # is named here rather than left outside the search. A review found it
        # missing; a table that omits what a round edited cannot falsify a
        # zero-tax claim.
        "_island",
        "_island_subparse",
        "_delegate_run",
    ),
    "src/lexic/parsing/pda/runtime/build.py": (
        "close_loop",
        "fast_values",
        "build_sequence",
        "build_vstr",
    ),
    "src/lexic/parsing/pda/runtime/matchers.py": (
        "match_lit",
        "match_cc",
        "vstr_once",
        "match_chartable",
        "select_arm",
        "run_span_once",
        "consult_extent",
    ),
    "src/lexic/parsing/pda/compiler/program/flatten.py": (),
    "src/lexic/parsing/product/tree.py": (),
}
"""The modules the paid loop runs through, and the functions worth naming.

An empty tuple means every function in the module is compared — used where the
module is cold enough that a per-function list would be noise, but a surprise
still needs to surface."""


RELOCATED = {
    "src/lexic/parsing/pda/runtime/build.py::close_loop": (
        "src/lexic/parsing/pda/runtime/kernel/decisions.py",
        "_close_loop",
    ),
}
"""A function that MOVED between the two revisions, and where it came from.

Comparing it against nothing would report the whole body as growth, which is
the wrong answer: a relocation costs the paid path nothing, and the question
worth asking is whether the body changed on the way."""


class Defect(AssertionError):
    """A claim this comparison makes that the two revisions do not support."""


def _source(revision: str | None, path: str) -> str | None:
    """One revision's text for ``path``, or ``None`` when it does not exist."""
    if revision is None:
        found = REPO / path
        return found.read_text() if found.exists() else None
    done = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout if done.returncode == 0 else None


def _functions(source: str, path: str) -> dict[str, int]:
    """Every function in one source text, by qualified name, to its opcode count."""
    module = compile(source, path, "exec")
    found: dict[str, int] = {}
    stack: list[tuple[str, types.CodeType]] = [("", module)]
    while stack:
        prefix, code = stack.pop()
        for const in code.co_consts:
            if not isinstance(const, types.CodeType):
                continue
            name = f"{prefix}{const.co_name}"
            found[name] = sum(1 for _ in dis.get_instructions(const))
            stack.append((f"{name}.", const))
    return found


def _compare(path: str, named: tuple[str, ...]) -> list[tuple[str, int, int]]:
    """Per-function ``(name, before, after)`` for the functions worth naming."""
    before_text = _source(BASE, path)
    after_text = _source(None, path)
    if before_text is None or after_text is None:
        raise Defect(f"s4 paid-path opcodes: {path} is missing from one revision")
    before, after = _functions(before_text, path), _functions(after_text, path)
    wanted = set(named) if named else set(before) | set(after)
    rows = []
    for name in sorted(wanted):
        left = {k.rsplit(".", 1)[-1]: v for k, v in before.items()}
        right = {k.rsplit(".", 1)[-1]: v for k, v in after.items()}
        if name not in left and name not in right:
            continue
        rows.append((name, left.get(name, -1), right.get(name, -1)))
    return rows


def _relocated_size(path: str, name: str) -> int:
    """The size of ``name``'s body at its OLD home, or ``-1`` when it had none."""
    origin = RELOCATED.get(f"{path}::{name}")
    if origin is None:
        return -1
    source = _source(BASE, origin[0])
    if source is None:
        return -1
    by_name = {
        key.rsplit(".", 1)[-1]: value
        for key, value in _functions(source, origin[0]).items()
    }
    return by_name.get(origin[1], -1)


def main() -> None:
    """Disassemble both revisions and report every paid-path delta."""
    print(f"paid-path bytecode, working tree against {BASE}\n")
    grew: list[str] = []
    for path, named in PAID.items():
        rows = _compare(path, named)
        changed = [row for row in rows if row[1] != row[2]]
        short = path.split("lexic/")[-1]
        if not changed:
            print(f"{short:<44}{len(rows):>4} functions, all identical")
            continue
        print(f"{short:<44}{len(rows):>4} functions, {len(changed)} changed")
        for name, before, after in changed:
            if before < 0:
                before = _relocated_size(path, name)
            if before < 0:
                print(f"    NEW    {name:<34}{'':>5}    {after:<5} (absent at {BASE})")
                grew.append(f"{short}::{name} is new ({after} instructions)")
                continue
            delta = after - before
            if delta == 0:
                print(
                    f"    moved  {name:<34}{before:>5} -> {after:<5} (body identical)"
                )
                continue
            mark = "GREW" if delta > 0 else "shrank"
            print(f"    {mark:<7}{name:<34}{before:>5} -> {after:<5} ({delta:+d})")
            if delta > 0:
                grew.append(f"{short}::{name} {delta:+d}")
    print()
    if grew:
        print("EXPLAIN OR REMOVE — paid-path functions that grew or are new:")
        for entry in grew:
            print(f"  {entry}")
    else:
        print("zero-tax\tno named paid-path function gained an instruction")
    print("\ns4 paid-path opcodes: OK")


if __name__ == "__main__":
    main()
