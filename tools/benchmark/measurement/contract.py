"""What a measured row IS, so two revisions can be compared or refused.

A benchmark number means nothing without the row that produced it. Two trees
agree on a comparison only when they agree on the grammar, the directives, the
document, the engine noun, the core request, the collector state and the clocks
— so those travel with the result rather than being inferred afterwards from a
display label.

The comparator refuses unequal contracts before any timing begins. That refusal
is the point: a row silently measuring a different document in one arm is the
failure a benchmark cannot see from its own numbers.
"""

from __future__ import annotations

import hashlib
from typing import Any, NamedTuple

PROTOCOL = 3
"""The wire protocol's version.

Bumped whenever a contract field or an observation field changes meaning. Two
copies of the harness with different protocol numbers cannot be compared, and
saying so is cheaper than discovering it in the numbers.
"""

CLOCKS = ("process_time", "perf_counter")
"""Both clocks are recorded for every observation, always.

Wall alone hides a parallel path that burns more total CPU per byte; CPU alone
cannot express a latency win. Recording one and deriving the other is not
possible, so both are measured.
"""


def digest(text: str) -> str:
    """A short stable content digest for a grammar, document or result."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class RowContract(NamedTuple):
    """The exact identity of one measured row, carried beside its numbers.

    :ivar protocol: The wire protocol version that produced this row.
    :ivar row: The row name — the engine noun, e.g. ``lexic-pda``.
    :ivar grammar: The bench case name.
    :ivar grammar_digest: Digest of the grammar SOURCE, so a silently edited
        fixture cannot pass as the same row.
    :ivar lexical: The exact ``@lexical`` rule names, sorted. Declared by the
        case, never derived from engine eligibility.
    :ivar non_semantic: The exact ``@non-semantic`` rule names, sorted.
    :ivar document_digest: Digest of the parsed input.
    :ivar document_bytes: Its length in bytes — the denominator of every
        per-byte figure, recorded rather than recomputed.
    :ivar scale: ``corpus`` or ``full``; which document the row read.
    :ivar product: What the engine BUILDS, e.g. ``typed model``.
    :ivar cores: The REQUESTED worker count. 1 pins sequential.
    :ivar gc_enabled: Whether the collector ran during the timed observation.
    :ivar clocks: The clocks recorded, in order.
    """

    protocol: int
    row: str
    grammar: str
    grammar_digest: str
    lexical: tuple[str, ...]
    non_semantic: tuple[str, ...]
    document_digest: str
    document_bytes: int
    scale: str
    product: str
    cores: int
    gc_enabled: bool
    clocks: tuple[str, ...]

    def mismatch(self, other: RowContract) -> tuple[str, ...]:
        """Field names on which two contracts disagree, in declaration order."""
        return tuple(
            field
            for field in RowContract.__annotations__
            if getattr(self, field) != getattr(other, field)
        )

    def wire(self) -> dict[str, Any]:
        """The JSON-safe form written by a worker."""
        return {
            field: list(value) if isinstance(value, tuple) else value
            for field, value in zip(RowContract.__annotations__, self, strict=True)
        }


def read_contract(payload: dict[str, Any]) -> RowContract:
    """Rebuild a contract from one worker's JSON, refusing a foreign protocol.

    :param payload: The ``contract`` object a worker wrote.
    :returns: The typed contract.
    :raises ValueError: If the protocol differs from this comparator's.
    """
    seen = int(payload["protocol"])
    if seen != PROTOCOL:
        raise ValueError(
            f"benchmark protocol mismatch: worker wrote {seen}, comparator "
            f"expects {PROTOCOL}; the two harness copies are not the same "
            f"instrument"
        )
    return RowContract(
        seen,
        str(payload["row"]),
        str(payload["grammar"]),
        str(payload["grammar_digest"]),
        tuple(str(name) for name in payload["lexical"]),
        tuple(str(name) for name in payload["non_semantic"]),
        str(payload["document_digest"]),
        int(payload["document_bytes"]),
        str(payload["scale"]),
        str(payload["product"]),
        int(payload["cores"]),
        bool(payload["gc_enabled"]),
        tuple(str(name) for name in payload["clocks"]),
    )


class Observation(NamedTuple):
    """One complete process-level measurement of one row.

    One observation is one process's whole answer. Several inner parses may be
    reduced to it, but the independent unit is the process — counting passes
    inside one interpreter as independent structural samples is what let a
    warm allocator state read as a result.

    :ivar wall: Seconds on ``perf_counter`` — the latency quantity.
    :ivar cpu: Seconds on ``process_time`` — the work quantity. For a threaded
        row this is aggregate process CPU across workers.
    :ivar result_digest: Digest of the parse product's text, so two arms are
        known to have built the same thing.
    :ivar verdict: ``accepted``, or the engine's refusal words verbatim.
    :ivar engaged: Whether a threaded row actually split; ``None`` if the row
        is sequential and the question does not apply.
    :ivar effective_cores: Workers the split actually occupied.
    """

    wall: float
    cpu: float
    result_digest: str
    verdict: str
    engaged: bool | None
    effective_cores: int

    def wire(self) -> dict[str, Any]:
        """The JSON-safe form written by a worker."""
        return dict(zip(Observation.__annotations__, self, strict=True))


def read_observation(payload: dict[str, Any]) -> Observation:
    """Rebuild one observation from a worker's JSON."""
    engaged = payload["engaged"]
    return Observation(
        float(payload["wall"]),
        float(payload["cpu"]),
        str(payload["result_digest"]),
        str(payload["verdict"]),
        None if engaged is None else bool(engaged),
        int(payload["effective_cores"]),
    )


class RowResult(NamedTuple):
    """A worker's whole answer: what it measured, and what it observed.

    :ivar contract: The row identity every observation was taken under.
    :ivar observations: One entry per complete process lifecycle.
    :ivar refusal: Why the row produced nothing, or ``None``.
    """

    contract: RowContract | None
    observations: tuple[Observation, ...]
    refusal: str | None


def read_result(payload: dict[str, Any]) -> RowResult:
    """Rebuild a whole row result from one worker's final JSON line."""
    refusal = payload.get("refusal")
    if refusal is not None:
        return RowResult(None, (), str(refusal))
    return RowResult(
        read_contract(payload["contract"]),
        tuple(read_observation(entry) for entry in payload["observations"]),
        None,
    )
