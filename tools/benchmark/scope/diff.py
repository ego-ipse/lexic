"""What this tree changes against a revision — tracked and untracked.

Asked of ``git`` rather than inferred, and asked for BOTH halves: an untracked
file is invisible to ``git diff``, and a module written but not yet added is
exactly the change whose rows most need measuring.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["changed_paths"]


def changed_paths(base: str, root: Path) -> tuple[str, ...]:
    """Every path this tree changes against ``base`` — tracked AND untracked.

    Untracked files are included deliberately. ``git diff`` cannot see a module
    that has been written but not added, and a new file under ``parsing/pda/``
    is exactly the change that most needs its seats measured; selecting nothing
    for it would be the tool's worst failure, since it reads as a clean run.

    :param base: Any revision ``git`` resolves.
    :param root: The working tree to ask.
    :raises RuntimeError: When ``git`` cannot answer — an unknown revision, a
        directory that is not a work tree, or one that is not there at all. One
        error type on purpose: every one of them means the row set is unknown,
        and the only safe response to an unknown row set is to stop rather than
        to measure the empty one.
    """
    out: list[str] = []
    for command in (
        ("git", "diff", "--name-only", base, "--"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    ):
        try:
            done = subprocess.run(
                command, cwd=root, capture_output=True, text=True, check=False
            )
        except OSError as unreachable:
            raise RuntimeError(f"{' '.join(command)}: {unreachable}") from unreachable
        if done.returncode != 0:
            raise RuntimeError(f"{' '.join(command)}: {done.stderr.strip()}")
        out.extend(line for line in done.stdout.splitlines() if line)
    return tuple(sorted(set(out)))
