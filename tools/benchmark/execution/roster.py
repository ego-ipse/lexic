"""Report this checkout's benchmark row roster, as JSON, and exit.

The comparator must not import either revision's Lexic or benchmark cases — it
schedules and validates, and a parent that imported one arm's modules would be
holding one revision's idea of what the rows ARE. So it asks each tree for its
own roster the same way it asks for a measurement: by running that tree's code
in that tree's process.

Two rosters that differ are a refusal with the missing names, never a silent
intersection.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from tools.benchmark.bench import LEXIC_ROWS
from tools.benchmark.cases.grammars import BENCHES


def roster() -> list[list[str]]:
    """Every ``(grammar, row)`` this checkout can measure, sorted."""
    return sorted([bench.name, row] for bench in BENCHES for row in sorted(LEXIC_ROWS))


def main(argv: Sequence[str] | None = None) -> None:
    """Write this tree's row roster to standard output."""
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps({"rows": roster()}, separators=(",", ":")))


if __name__ == "__main__":
    main()
