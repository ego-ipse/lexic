"""Terminal presentation for benchmark results."""

from __future__ import annotations

import os
import sys
from math import log10
from typing import NamedTuple

from tools.benchmark.bench import _JSON_SPECIALISTS, ENGINE, PRODUCT, Parse, _medians
from tools.benchmark.cases.grammars import Bench, declared_marks

BAR_WIDTH = 40
"""Bar length. Wide enough that a 2x gap reads differently from a 4x one —
at 22 columns the log scale gave them three characters between them."""

_TINT: dict[str, str] = {
    "lexic-pda": "\x1b[38;5;39m",
    "lexic-lex": "\x1b[38;5;45m",
    "lexic-lex-ns": "\x1b[38;5;51m",
    "lexic-earley": "\x1b[38;5;208m",
    "lexic-mt": "\x1b[38;5;118m",
    "lexic-mt-lex-ns": "\x1b[38;5;84m",
    "stdlib-json": "\x1b[38;5;213m",
    "msgspec": "\x1b[38;5;213m",
    "lark-earley-lex": "\x1b[38;5;250m",
    "lark-lalr-lex": "\x1b[38;5;250m",
    "parsimonious-lex": "\x1b[38;5;250m",
    "antlr-lex": "\x1b[38;5;250m",
    "antlr-py-lex": "\x1b[38;5;250m",
}
"""One distinct colour per lexic mode — the two rows this benchmark exists to
place are findable at a glance — plus one shared tint for the format
specialists, marking rows that answer a DIFFERENT question (no grammar taken).
Competitors keep the terminal's default foreground: colour marks whose row it
is and what kind, never better or worse.

The directive-matched lark seats take a DARKER tone of that default rather than
a colour of their own, because they are not a different tool — they are the
same one handed the grammar's own directives, and the pair reads as a pair."""

_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def _use_color(force: bool) -> bool:
    """Colour when forced, else only on a real terminal nobody opted out of.

    ``NO_COLOR`` (the informal cross-tool convention) wins over tty detection;
    piped output stays clean ANSI-free text either way.
    """
    return force or (sys.stdout.isatty() and "NO_COLOR" not in os.environ)


def _paint(text: str, code: str, on: bool) -> str:
    """``text`` wrapped in one ANSI colour, when colour is on and one applies."""
    return f"{code}{text}{_RESET}" if on and code else text


def _bar(value: float, best: float, worst: float) -> str:
    """A log-scaled bar, full width at the SLOWEST engine in this block.

    The scale used to be a fixed two decades, which saturated the moment one
    engine was 100x another — and with a JIT'd Java column in the table that is
    most rows. Every bar hit full width and the picture said nothing. Anchoring
    the top of the scale to the block's own worst ratio keeps the shape readable
    however far apart the engines turn out to be.
    """
    span = log10(max(worst / best, 10.0))
    ratio = max(value / best, 1.0)
    filled = min(BAR_WIDTH, round(log10(ratio) / span * BAR_WIDTH))
    return "█" * filled + "·" * (BAR_WIDTH - filled)


SPECIALISTS = frozenset(name for name, _make in _JSON_SPECIALISTS)
"""Rows that take NO grammar — hand-written C for one fixed format."""


def _amount(value: float) -> str:
    """One timing, in the unit that keeps its significant digits.

    Under a microsecond, three decimals of `µs/char` spends the whole number on
    leading zeros: the fastest rows here are tens of nanoseconds and `0.045`
    says less than `45.0` does.
    """
    return f"{value * 1000:9.1f} ns/char" if value < 1.0 else f"{value:9.3f} µs/char"


def _ranked_rows(timings: dict[str, float], color: bool) -> None:
    """The timed rows, fastest first, each with its bar and product.

    The `base` is the fastest engine that TAKES A GRAMMAR. A format specialist
    is a floor, not a competitor — anchoring the column to it would rate every
    general engine against hand-written C for one language and answer a question
    nobody asked. It still gets a ratio, below 1, which is the honest reading:
    what fraction of the specialist's cost the general engines run at.

    The BARS keep their own anchor at the block's genuine fastest row, so the
    picture is unchanged and the shift lives only in the ratio column.
    """
    ranked = sorted(timings.items(), key=lambda kv: kv[1])
    general = [v for n, v in ranked if n not in SPECIALISTS]
    fastest = ranked[0][1] if ranked else 1.0
    worst = ranked[-1][1] if ranked else 1.0
    best = general[0] if general else fastest
    for name, value in ranked:
        ratio = value / best
        rel = (
            "   base"
            if value == best
            else f"{ratio:6.3f}×"
            if ratio < 1
            else f"{ratio:6.1f}×"
        )
        tint = _TINT.get(name, "")
        label = _paint(f"{name:<17}", tint, color)
        shape = _paint(_bar(value, fastest, worst), tint, color)
        print(f"  {label}{_amount(value)} {rel}  {shape}  {PRODUCT.get(name, '?')}")


class Block(NamedTuple):
    """One grammar's finished measurements, ready to print.

    :ivar bench: The grammar and its documents.
    :ivar samples: Per-row timings, one list per round.
    :ivar refused: Rows that earned words instead of a number.
    :ivar floor: The harness's own noise, as a percentage.
    :ivar documents: What each row actually parsed.
    :ivar mt_notes: Per-row reasons that a requested mt row ran sequentially.
    :ivar shares: Per-row fraction of the timed region spent building the
        input stream, for the rows that pay one.
    """

    bench: Bench
    samples: dict[str, list[float]]
    refused: dict[str, str]
    floor: float
    documents: dict[str, str]
    mt_notes: dict[str, str]
    shares: dict[str, float]


def _report(block: Block, color: bool) -> None:
    """One grammar's block: fastest first, with the bar and what each builds."""
    bench = block.bench
    sizes = {len(doc) for doc in block.documents.values()}
    note = (
        f"{len(bench.corpus):,} chars (mt rows: {len(bench.full):,})"
        if len(sizes) > 1
        else f"{max(sizes, default=len(bench.corpus)):,} chars"
    )
    print(
        f"\n─── {bench.name} · {note} · one grammar, "
        "every engine · bars log-scaled, full bar = slowest"
    )
    if not block.samples:
        print("    no engine could parse this grammar")
    _ranked_rows(_medians(block.samples), color)
    for name, why in sorted(block.refused.items()):
        label = _paint(f"{name:<17}", _TINT.get(name, ""), color)
        print(f"  {label}{'—':>9}             {_paint(why[:96], _DIM, color)}")
    print(
        f"  {'noise floor':<13}{block.floor:8.2f}%    "
        "smaller differences are not results"
    )
    for name, reason in sorted(block.mt_notes.items()):
        print(
            f"  {(name + ' check'):<17}{'off':>4}     {reason} — this row ran "
            "the same one-worker program as its sequential twin"
        )
    _seat_check(bench, block.samples)


def _seat_check(bench: Bench, samples: dict[str, list[float]]) -> None:
    """The harness's own error, read off two identical-by-construction rows.

    Where a grammar has NO `@non-semantic` marks, the two variant rows are
    compiled from identical `Directives` — the same program by construction —
    so any spread between them is instrument error, not a result, and the
    display says what it measured itself to be wrong by. That is the only
    identity this line claims: a non-empty mark set can change the compiled
    machine even when the codegen grammars compare equal (the noise
    declaration feeds the skip alphabet, not the grammar's shape), and no
    cheap artifact comparison certifies sameness in either direction — so a
    marked grammar gets no seat check rather than a false one. Each row now
    runs in its own process, so this is the spread between independent medians;
    it measures the isolation harness rather than a seating position.
    """
    if "lexic-lex" not in samples or "lexic-lex-ns" not in samples:
        return
    _, ns_marks = declared_marks(bench)
    if ns_marks:
        return
    lex = _medians({"lex": samples["lexic-lex"]})["lex"]
    ns = _medians({"ns": samples["lexic-lex-ns"]})["ns"]
    spread = (ns - lex) / max(min(lex, ns), 1e-9) * 100
    print(
        f"  {'seat check':<13}{spread:+8.2f}%    lexic-lex vs lexic-lex-ns run "
        "the same program — this spread is the harness's own error"
    )


def _warmup_note(engines: dict[str, Parse]) -> None:
    """What it took to make the JIT row honest, printed rather than assumed."""
    for name, parse in engines.items():
        warmed = getattr(parse, "warmed", None)
        if warmed is None:
            continue
        _warmup_values(
            name,
            warmed,
            getattr(parse, "cold_us_per_char", None),
            getattr(parse, "charstream_share", lambda: 0.0)(),
        )


def _warmup_values(
    name: str,
    warmed: tuple[int, bool],
    cold: float | None,
    share: float,
) -> None:
    """Print one Java worker's cold parse and warmup state."""
    if cold is not None:
        print(
            f"  {name + ' first':<17}{_amount(cold)}    cold first parse "
            "before JIT warmup"
        )
    spent, settled = warmed
    state = "median settled" if settled else "STILL MOVING — number is soft"
    print(
        f"  {name + ' warmup':<13}{spent:6} parses   {state}; "
        f"{share * 100:.0f}% of the timed region builds the CharStream"
    )


def _legend(color: bool) -> None:
    """The engine roster, once, before any grammar's rows."""
    print(_paint("engines — what each row IS:", _DIM, color))
    for name, note in ENGINE.items():
        tint = _TINT.get(name, "")
        print(f"  {_paint(f'{name:<16}', tint, color)} {_paint(note, _DIM, color)}")


def _mark(cores: int | None) -> str:
    """The header's cores marker, empty when no MT rows were asked for."""
    return f"  cores={cores}" if cores is not None else ""
