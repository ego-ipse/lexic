"""Regenerate ``generated/`` — the importable twin modules of the GT corpus.

Exports every ground-truth grammar through the explicit-write seam
(``export_module``) into the repo's ``generated/`` scratch dir (git-ignored;
compile itself never writes files — ruling 2 of 260718-generated-files).

Run: ``uv run python tools/regen_generated.py`` (``--inline`` for the
self-contained ``inline_tables`` variant instead of the bind-at-import form).
"""

from __future__ import annotations

import sys
from pathlib import Path

from lexic.compile import compile_from_path, export_module

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    """Re-export every ground-truth twin into ``generated/``.

    :returns: The process exit code.
    """
    inline = "--inline" in sys.argv[1:]
    ground_truth = REPO / "resources" / "ground_truth"
    out = REPO / "generated"
    written: list[Path] = []
    for src in sorted(ground_truth.glob("*.gbnf")) + sorted(
        ground_truth.glob("*.abnf")
    ):
        compiled = compile_from_path(src)
        stem = src.stem if src.suffix == ".gbnf" else f"{src.stem}_abnf"
        written.append(
            export_module(compiled, out / f"{stem}.py", inline_tables=inline)
        )
    for path in written:
        print(f"  {path.relative_to(REPO)}")
    print(f"{len(written)} modules regenerated ({'inline' if inline else 'bind'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
