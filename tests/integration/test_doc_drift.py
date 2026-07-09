"""Doc-drift guard: CLAUDE.md's §Project layout vs. src/lexic/ on disk.

CLAUDE.md once described a deleted shape (``IrComposite``) for roughly a
month before anyone noticed. This test catches the module-listing half of
that class of drift: every ``src/lexic/`` file the layout block names must
exist, and every ``.py`` file under ``src/lexic/`` must be named in the
layout block — both directions, so renames/deletions/additions all surface.

The parser below is intentionally forgiving: it only recognizes a line as a
file entry when the line's *first* token is a bare ``name.py`` (optionally
comma-joined with siblings, e.g. ``lexruns.py, trampoline.py``), and a line
as a directory header only when its first token is a single-segment
``name/``. Directory headers nest by indentation (a stack keyed on each
header's own indent), so a subdirectory listed under its parent — e.g.
``parsing/``'s ``earley/`` and ``pda/`` — resolves to the full nested path.
Prose that merely *mentions* a ``.py`` name or a ``a/b/`` path fragment
mid-sentence never matches, since it isn't the line's first token. The goal
is catching real listing drift, not enforcing layout formatting.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = ROOT / "CLAUDE.md"
SRC = ROOT / "src" / "lexic"

_FILENAME_RE = re.compile(r"[\w\-]+\.py")
_DIR_HEADER_RE = re.compile(r"[\w\-]+/")


def _extract_layout_block(text: str) -> list[str]:
    """Lines strictly inside the fenced code block under '## Project layout'."""
    lines = text.splitlines()
    heading = next(
        i for i, line in enumerate(lines) if line.strip() == "## Project layout"
    )
    fence_start = next(
        i for i in range(heading, len(lines)) if lines[i].strip() == "```"
    )
    fence_end = next(
        i for i in range(fence_start + 1, len(lines)) if lines[i].strip() == "```"
    )
    return lines[fence_start + 1 : fence_end]


def _listed_src_lexic_paths(block_lines: list[str]) -> set[str]:
    """Relative ``src/lexic/`` paths named in the layout block's src/lexic subtree.

    Only the subtree rooted at the block's opening ``src/lexic/`` line is
    read — the block also documents ``tests/``, ``resources/ground_truth/``,
    and ``generated/``, which are out of scope for this guard.
    """
    assert block_lines and block_lines[0].strip() == "src/lexic/", (
        "layout block does not open with 'src/lexic/' — CLAUDE.md's layout "
        "section shape changed; update this parser"
    )
    end = len(block_lines)
    for i in range(1, len(block_lines)):
        line = block_lines[i]
        if line and not line[0].isspace():
            end = i  # first top-level sibling after src/lexic/, e.g. "tests/"
            break

    listed: set[str] = set()
    stack: list[tuple[int, str]] = []  # (indent, dir_name), innermost last
    for line in block_lines[1:end]:
        stripped = line.strip()
        if not stripped:
            continue
        leading_ws = len(line) - len(line.lstrip(" "))
        first = stripped.split()[0]
        while stack and leading_ws <= stack[-1][0]:
            stack.pop()  # dedent past (or sibling of) an enclosing dir header
        if _DIR_HEADER_RE.fullmatch(first):
            stack.append((leading_ws, first))
            continue
        current_dir = "".join(name for _, name in stack)
        for token in stripped.split():
            token = token.rstrip(",")
            if _FILENAME_RE.fullmatch(token):
                listed.add(current_dir + token)
            else:
                break  # first non-filename token ends this line's file list
    return listed


def _actual_src_lexic_paths() -> set[str]:
    return {str(p.relative_to(SRC)).replace("\\", "/") for p in SRC.rglob("*.py")}


def test_claude_md_layout_matches_src_lexic_on_disk() -> None:
    """Every module the layout block names exists, and vice versa."""
    block = _extract_layout_block(CLAUDE_MD.read_text(encoding="utf-8"))
    listed = _listed_src_lexic_paths(block)
    actual = _actual_src_lexic_paths()

    missing_on_disk = sorted(listed - actual)
    missing_from_doc = sorted(actual - listed)

    assert not missing_on_disk, (
        "CLAUDE.md's §Project layout lists src/lexic/ files that no longer "
        f"exist on disk: {missing_on_disk}"
    )
    assert not missing_from_doc, (
        "src/lexic/ has .py files CLAUDE.md's §Project layout does not "
        f"mention: {missing_from_doc}"
    )
