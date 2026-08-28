"""A routed-interior product as a suspended shell plus lawful fragments."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tests.unit.lexic.parsing.parallel.routed_fixtures import (
    ROUTED_GRAMMAR,
    routed_document,
    routed_pieces,
)


class ProductState(NamedTuple):
    """Finite lower, upper, and decoded-route continuation state."""

    lower: int
    upper: int
    route: int


class VerdictKey(NamedTuple):
    """Stable semantic failure order, independent of worker completion."""

    source: int
    phase: int
    declaration: int
    serial: int


class Verdict(NamedTuple):
    """One deferred semantic refusal."""

    key: VerdictKey
    message: str


class KeyFirst(NamedTuple):
    """The first decoded occurrence of one dynamic key in a fragment."""

    key: str
    source: int
    serial: int


class FragmentMeta(NamedTuple):
    """Associative duplicate state plus canonically ordered verdicts."""

    firsts: tuple[KeyFirst, ...]
    verdicts: tuple[Verdict, ...]


class FragmentProduct[Carry](NamedTuple):
    """One owned partial value between exact suspended product states."""

    entry: ProductState
    exit: ProductState
    carry: Carry
    meta: FragmentMeta


class ShellSuspension[Result](NamedTuple):
    """Coordinator-owned shell paused at one certified interior hole."""

    program: int
    hole_position: int
    hole_entry: ProductState
    hole_exit: ProductState
    resume_state: ProductState
    prefix_extent: tuple[int, int]
    suffix_extent: tuple[int, int]
    result_name: str


class LineCarry(NamedTuple):
    """Direct target accumulator for terminated interior units."""

    lines: tuple[str, ...]


class LineDocument(NamedTuple):
    """Final target result; no generated shell or interior model exists."""

    name: str
    lines: tuple[str, ...]


def _duplicate(key: KeyFirst) -> Verdict:
    """File a repeated decoded key at its later source occurrence."""
    return Verdict(
        VerdictKey(key.source, 1, 0, key.serial),
        f"duplicate key {key.key!r}",
    )


def merge_meta(left: FragmentMeta, right: FragmentMeta) -> FragmentMeta:
    """Merge first-occurrence state and derive cross-boundary duplicates."""
    firsts = {entry.key: entry for entry in left.firsts}
    cross: list[Verdict] = []
    for entry in right.firsts:
        if entry.key in firsts:
            cross.append(_duplicate(entry))
        else:
            firsts[entry.key] = entry
    merged_firsts = tuple(
        firsts[key] for key in sorted(firsts)
    )
    verdicts = tuple(sorted(left.verdicts + right.verdicts + tuple(cross)))
    return FragmentMeta(merged_firsts, verdicts)


def join_fragment[Carry](
    left: FragmentProduct[Carry],
    right: FragmentProduct[Carry],
    joined: Carry,
) -> FragmentProduct[Carry]:
    """Join adjacent pieces after a target law has combined their carries."""
    if left.exit != right.entry:
        raise UnsupportedConstructError(
            "prototype fragment: continuation state mismatch"
        )
    return FragmentProduct(
        left.entry,
        right.exit,
        joined,
        merge_meta(left.meta, right.meta),
    )


def join_lines(
    left: FragmentProduct[LineCarry],
    right: FragmentProduct[LineCarry],
) -> FragmentProduct[LineCarry]:
    """Associative terminated-run concatenation."""
    carry = LineCarry(left.carry.lines + right.carry.lines)
    return join_fragment(left, right, carry)


def parse_piece(text: str, state: ProductState) -> FragmentProduct[LineCarry]:
    """Witness the direct interior product over a certified rooted piece."""
    if not text.startswith("\n") or not text.endswith(">"):
        raise UnsupportedConstructError(
            "prototype fragment: routed piece lost its wrapper"
        )
    lines = tuple(text[1:-1].splitlines())
    if not lines or any(not line.isalpha() or not line.islower() for line in lines):
        raise UnsupportedConstructError(
            "prototype fragment: routed piece has an invalid line"
        )
    return FragmentProduct(
        state,
        state,
        LineCarry(lines),
        FragmentMeta((), ()),
    )


def suspend_shell(
    text: str, opener: int, closer: int, state: ProductState
) -> ShellSuspension[LineDocument]:
    """Pause the coordinator's direct product at the certified interior."""
    if text[opener] != "\n" or text[closer] != ">":
        raise UnsupportedConstructError(
            "prototype fragment: routed shell delimiters changed"
        )
    return ShellSuspension(
        7,
        3,
        state,
        state,
        ProductState(12, 22, 1),
        (0, opener + 1),
        (closer, len(text)),
        "routed-lines",
    )


def resume_shell(
    text: str,
    shell: ShellSuspension[LineDocument],
    interior: FragmentProduct[LineCarry],
) -> LineDocument:
    """Attach one joined carry and finalize the document root once."""
    if interior.entry != shell.hole_entry or interior.exit != shell.hole_exit:
        raise UnsupportedConstructError(
            "prototype fragment: interior cannot resume this shell"
        )
    prefix = text[shell.prefix_extent[0] : shell.prefix_extent[1]]
    suffix = text[shell.suffix_extent[0] : shell.suffix_extent[1]]
    if not prefix.endswith("\n") or suffix != ">":
        raise UnsupportedConstructError(
            "prototype fragment: shell continuation does not accept"
        )
    if interior.meta.verdicts:
        raise UnsupportedConstructError(interior.meta.verdicts[0].message)
    return LineDocument(shell.result_name, interior.carry.lines)


def prove_routed_interior() -> None:
    """Use the real routed plan without constructing a model shell."""
    compiled = compile_text(ROUTED_GRAMMAR)
    text = routed_document(700)
    found = routed_pieces(compiled.codegen_grammar, text, 4)
    if found is None:
        raise UnsupportedConstructError(
            "prototype fragment: real routed witness did not divide"
        )
    state = ProductState(11, 21, 1)
    shell = suspend_shell(text, found.region.opener, found.region.closer, state)
    fragments = tuple(parse_piece(part, state) for part in found.parts)
    joined = fragments[0]
    for fragment in fragments[1:]:
        joined = join_lines(joined, fragment)
    result = resume_shell(text, shell, joined)

    expected = tuple(text[found.region.opener + 1 : found.region.closer].splitlines())
    assert result.lines == expected
    assert len(result.lines) == 700


def _key_fragment(
    key: str,
    source: int,
    verdicts: tuple[Verdict, ...] = (),
) -> FragmentProduct[LineCarry]:
    """Build one map-like fragment for the associative metadata proof."""
    state = ProductState(1, 2, 3)
    meta = FragmentMeta((KeyFirst(key, source, source),), verdicts)
    return FragmentProduct(state, state, LineCarry((key,)), meta)


def prove_associative_metadata() -> None:
    """Grouping and worker completion order cannot alter failure order."""
    later = Verdict(VerdictKey(90, 2, 0, 0), "later")
    a = _key_fragment("same", 10)
    b = _key_fragment("other", 40, (later,))
    c = _key_fragment("same", 70)

    left_grouped = join_lines(join_lines(a, b), c)
    right_grouped = join_lines(a, join_lines(b, c))

    assert left_grouped == right_grouped
    assert left_grouped.meta.verdicts[0].message == "duplicate key 'same'"
    assert left_grouped.meta.verdicts[0].key.source == 70
    assert left_grouped.meta.verdicts[1] == later

    d = _key_fragment("same", 100)
    three_left = join_lines(join_lines(a, c), d)
    three_right = join_lines(a, join_lines(c, d))
    assert three_left == three_right


def main() -> None:
    """Run the real routed witness and associative metadata proof."""
    prove_routed_interior()
    prove_associative_metadata()
    print("PASS: suspended routed shell and lawful fragment joins")


if __name__ == "__main__":
    main()
