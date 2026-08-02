"""CLI — ``python -m opsis [grammar] [--serve | -o out.html]``."""

from __future__ import annotations

import argparse
from pathlib import Path

from opsis_proto_0 import explore, report


def main() -> None:
    """Parse args; serve live by default, or write a frozen artifact."""
    ap = argparse.ArgumentParser(prog="opsis", description="the spectacle of lexic")
    ap.add_argument("grammar", nargs="?", help="grammar file (flavour from extension)")
    ap.add_argument("input", nargs="?", help="input file to parse with the grammar")
    ap.add_argument("-o", "--out", help="write a frozen artifact instead of serving")
    ap.add_argument("--flavour", default=None, help="override the flavour (default: extension)")
    ap.add_argument("--port", type=int, default=0, help="live-mode port (default: ephemeral)")
    args = ap.parse_args()

    source, flavour = "", "gbnf"
    if args.grammar is not None:
        path = Path(args.grammar)
        source = path.read_text(encoding="utf-8")
        flavour = args.flavour or path.suffix.lstrip(".") or "gbnf"
    elif args.flavour:
        flavour = args.flavour

    input_text = ""
    if args.input is not None:
        input_text = Path(args.input).read_text(encoding="utf-8")
    if args.out:
        if not source:
            ap.error("an artifact needs a grammar file")
        print(report(source, flavour, args.out, input_text))
    else:
        explore(source, flavour, args.port)


if __name__ == "__main__":
    main()
