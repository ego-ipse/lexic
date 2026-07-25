"""Tool-clean gate: fresh GT exports must satisfy pyright + pylint defaults
AND the self-grammar cross-check (verify_module — lexic parses its own output).

Exports every ground-truth grammar in both table modes to a temp dir, then
runs ``pyright`` and ``pylint`` (DEFAULT configs — the point is that a user
opening a generated file sees zero findings) and reports anything beyond the
accepted exceptions:

- pylint C0103 on keyword-mangled class names (``True_``/``False_`` — a
  ``class True`` is a SyntaxError, so some mangle must exist; accepted by
  ruling 8).

- pylint C0302 (module > 1000 lines) — a generated module is ONE artifact
  mirroring one grammar; a large grammar (vyx: 129 rules) legitimately
  renders long, and splitting it across modules would be meaningless.
- pylint R0801 (cross-file duplication) — a grammar's gbnf and abnf exports
  share the canonical AST BY DESIGN; the duplication only appears when
  linting the whole batch in one invocation, never to a user opening a file.

Exit 0 when clean. Run: ``uv run python tools/check_generated.py``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from lexic.compile import compile_from_path, export_module, verify_module

REPO = Path(__file__).resolve().parent.parent
ACCEPTED_PYLINT = re.compile(
    r"C0103.*Class name \"[A-Za-z0-9]+_\" doesn't conform"
    r"|C0302: Too many lines in module"
    r"|R0801: Similar lines"
)


def export_all(out_dir: Path) -> list[Path]:
    """Export every GT grammar in both table modes; return the file list."""
    files: list[Path] = []
    ground_truth = REPO / "resources" / "ground_truth"
    for gt in sorted(ground_truth.glob("*.gbnf")) + sorted(ground_truth.glob("*.abnf")):
        compiled = compile_from_path(gt)
        stem = f"{gt.stem}_{gt.suffix[1:]}"
        for name, inline in ((f"{stem}.py", False), (f"{stem}_inline.py", True)):
            path = export_module(compiled, out_dir / name, inline_tables=inline)
            # L2: lexic parses its own export and cross-checks the binding.
            verify_module(compiled, path.read_text(encoding="utf-8"))
            files.append(path)
    return files


def run_pyright(files: list[Path]) -> list[str]:
    """Pyright default config over the exports; returns finding lines."""
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", *map(str, files)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    report = json.loads(result.stdout or "{}")
    return [
        f"{Path(d['file']).name}:{d['range']['start']['line'] + 1} "
        f"{d['severity']}: {d['message']}"
        for d in report.get("generalDiagnostics", [])
        if d["severity"] == "error"
    ]


def run_pylint(files: list[Path]) -> list[str]:
    """Pylint default config over the exports; returns unaccepted findings."""
    result = subprocess.run(
        [sys.executable, "-m", "pylint", "--persistent=no", *map(str, files)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    findings = []
    for line in result.stdout.splitlines():
        if re.match(r".+:\d+:\d+: [CRWEF]\d{4}", line):
            if not ACCEPTED_PYLINT.search(line):
                findings.append(line)
    return findings


def main() -> int:
    """Export every twin to a temp dir and gate it on pyright + pylint.

    :returns: The process exit code — 0 when every generated module is clean.
    """
    with tempfile.TemporaryDirectory(prefix="lexic_genchk_") as tmp:
        files = export_all(Path(tmp))
        print(f"exported {len(files)} modules")
        pyright_findings = run_pyright(files)
        pylint_findings = run_pylint(files)
    for line in pyright_findings:
        print("PYRIGHT", line)
    for line in pylint_findings:
        print("PYLINT ", line)
    if pyright_findings or pylint_findings:
        print(f"FAIL: {len(pyright_findings)} pyright + {len(pylint_findings)} pylint")
        return 1
    print("CLEAN: 0 pyright errors, 0 unaccepted pylint findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
