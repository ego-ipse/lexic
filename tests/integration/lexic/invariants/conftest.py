"""Fixtures for the invariant suites that need a built competitor seat."""

from __future__ import annotations

import shutil
from collections.abc import Iterator

import pytest

from tools.benchmark.cases.grammars import BENCHES, Bench
from tools.benchmark.emitters.directives import NO_MARKS
from tools.benchmark.engines.antlr_java import JavaAntlr, java_antlr_parser

ESCALATING = {
    "csv": "a,,b",
    "arithmetic": "1++2",
}
"""Grammar → an invalid input that BAILS out of SLL, so stage two must run.

Each is already in its bench's declared rejects; what earns it a place here is
that stage one cannot decide it, which is what makes the parse take the
escalation branch at all. An input stage one refuses outright never reaches the
rewind and would pass that gate no matter how broken the branch was.
"""

NO_JAVA = shutil.which("java") is None or shutil.which("javac") is None
"""Whether the Java seat's toolchain is missing, so its gates must skip."""


def _bench(name: str) -> Bench:
    """The declared benchmark case called ``name``.

    A function rather than a `next(...)` inside the fixture: the fixture is a
    generator, where an exhausted `next` would surface as a silent stop rather
    than as the lookup failure it is.
    """
    for case in BENCHES:
        if case.name == name:
            return case
    raise LookupError(f"no benchmark case named {name!r}")


@pytest.fixture(scope="module", params=sorted(ESCALATING))
def seat(request: pytest.FixtureRequest) -> Iterator[tuple[JavaAntlr, str, str]]:
    """One built Java seat, its corpus, and the input that forces escalation.

    Built through the public constructor rather than through ``one_engine``, so
    the harness's own differential is NOT in the way: it already refuses a seat
    that accepts a declared reject, and a gate that can only ever fail through
    somebody else's assertion is not testing anything of its own.
    """
    name = request.param
    bench = _bench(name)
    label = "Seat" + "".join(part for part in name.title() if part.isalnum())
    try:
        parse = java_antlr_parser(bench.ast, label, NO_MARKS)
    except RuntimeError as absent:  # the jar `antlr4-tools` fetches, not our code
        pytest.skip(f"ANTLR toolchain unavailable: {absent}")
    yield parse, bench.corpus, ESCALATING[name]
    parse.close()
