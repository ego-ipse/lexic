"""Kitty-graphics inline emitter — a PNG into the terminal, as text.

The terminal-native export target: the same frames the shot pipelines already
make, printed into scrollback wherever the kitty graphics protocol is spoken
(ghostty, kitty, wezterm). Zero dependencies, and the output is plain bytes —
`inline.py frame.png > frame.term` freezes an artifact that `cat` replays.

    uv run python zzz_current_work/260807-opsis-radical/atlas/inline.py shot.png
"""

import base64
import sys
from typing import TextIO

CHUNK = 4096


def emit(png_bytes: bytes, out: TextIO) -> None:
    """Write the chunked APC stream that displays ``png_bytes`` at the cursor.

    First chunk carries the control keys (``f=100`` PNG, ``a=T`` transmit and
    display); continuation chunks carry only ``m``; payload stays ≤4096 chars
    per chunk, as the protocol requires.
    """
    payload = base64.standard_b64encode(png_bytes).decode()
    first = True
    while payload:
        chunk, payload = payload[:CHUNK], payload[CHUNK:]
        keys = ("f=100,a=T," if first else "") + f"m={1 if payload else 0}"
        out.write(f"\x1b_G{keys};{chunk}\x1b\\")
        first = False
    out.write("\n")
    out.flush()


def main() -> int:
    """Emit each named PNG inline; with no arguments, read one PNG from stdin."""
    paths = sys.argv[1:]
    if not paths:
        emit(sys.stdin.buffer.read(), sys.stdout)
        return 0
    for path in paths:
        with open(path, "rb") as fh:
            emit(fh.read(), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
