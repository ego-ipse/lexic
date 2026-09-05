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
from collections.abc import Mapping, Sequence
from typing import NamedTuple

type Json = str | int | float | bool | None | Sequence[Json] | Mapping[str, Json]
"""One decoded JSON value — what a worker writes and a reader must prove.

The wire is the one place a benchmark cannot assume its own vocabulary: the
process on the other side is a DIFFERENT revision of this harness. So the
payload arrives as what JSON actually offers, and every field is claimed by a
reader below that says which shape it must have and refuses anything else.
"""


def _text(payload: Mapping[str, Json], field: str) -> str:
    """One string field, or a refusal naming it."""
    value = payload[field]
    if not isinstance(value, str):
        raise ValueError(f"benchmark wire: {field} is not a string: {value!r}")
    return value


def _number(payload: Mapping[str, Json], field: str) -> float:
    """One numeric field, or a refusal naming it."""
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"benchmark wire: {field} is not a number: {value!r}")
    return value


def _flag(payload: Mapping[str, Json], field: str) -> bool:
    """One boolean field, or a refusal naming it."""
    value = payload[field]
    if not isinstance(value, bool):
        raise ValueError(f"benchmark wire: {field} is not a boolean: {value!r}")
    return value


def _names(payload: Mapping[str, Json], field: str) -> tuple[str, ...]:
    """One list-of-strings field, or a refusal naming it."""
    value = payload[field]
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"benchmark wire: {field} is not a list: {value!r}")
    return tuple(str(name) for name in value)


def _mapping(payload: Mapping[str, Json], field: str) -> Mapping[str, Json]:
    """One nested object, or a refusal naming it."""
    value = payload[field]
    if not isinstance(value, Mapping):
        raise ValueError(f"benchmark wire: {field} is not an object: {value!r}")
    return value


PROTOCOL = 5
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


class _Token(str):
    """Rendered punctuation, told apart from a value that happens to be text."""


def _labels(item: tuple) -> tuple[str, ...]:
    """The record's declared field names, or empty for a plain tuple.

    Field naming is part of the typed model product: a revision can rename a
    field while keeping the class name, the values and the round-trip text, and
    a rendering blind to names would call the two products the same. Read off
    the type rather than through any engine API, because this module is copied
    into the base arm and must not depend on that revision's internals.
    """
    fields = getattr(type(item), "_fields", ())
    named = isinstance(fields, tuple) and len(fields) == len(item)
    return tuple(str(name) for name in fields) if named else ()


def _pushed(item: tuple) -> list[object]:
    """One record's labelled children and separators, as a stack pops them.

    ``object`` for the same reason :func:`shape` takes one, and it is the same
    stack: a child is whatever the product held.
    """
    labels = _labels(item)
    order: list[object] = [_Token(")")]
    for at in range(len(item) - 1, -1, -1):
        order.append(item[at])
        if labels:
            order.append(_Token(f"{labels[at]}="))
        if at:
            order.append(_Token(","))
    return order


def shape(product: object) -> str:
    """A deterministic rendering of what a row BUILT — its structure.

    ``object`` is the honest domain, not a shrug, and no narrower type exists
    here. The walker reads whatever the SEAT it is measuring returned: a lexic
    ``GrammarModel``, a lark ``Tree`` or ``Token``, an ANTLR context, a
    parsimonious node, a plain string. Naming that union would mean importing
    four third-party vocabularies into a module that has no dependencies by
    design — it is copied into the base arm, where those packages need not be
    installed and where an older revision of them may not match — and a
    Protocol would name no members, since everything this walker does (``type``,
    ``repr``, ``isinstance`` against ``tuple``, reading ``_fields``) is defined
    on ``object`` itself. ``object`` promises nothing and permits nothing else,
    which is exactly the contract here.

    Class names, declared field names and values, in reading order. A digest
    of the rendered TEXT cannot stand in for this: a round-tripping parse emits
    its own input, so that digest answers "did the document survive" and never
    "is this the same product" — two different trees over one document render
    identically.

    Iterative because the depth is the grammar's: a recursive walk would refuse
    a deeply nested document the parser itself accepted.
    """
    out: list[str] = []
    stack: list[object] = [product]
    while stack:
        item = stack.pop()
        if isinstance(item, _Token):
            out.append(str(item))
        elif isinstance(item, tuple):
            out.append(f"{type(item).__name__}(")
            stack.extend(_pushed(item))
        else:
            out.append(f"{type(item).__name__}:{item!r}")
    return "".join(out)


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

    def wire(self) -> dict[str, Json]:
        """The JSON-safe form written by a worker."""
        return {
            field: list(value) if isinstance(value, tuple) else value
            for field, value in zip(RowContract.__annotations__, self, strict=True)
        }


def read_contract(payload: Mapping[str, Json]) -> RowContract:
    """Rebuild a contract from one worker's JSON, refusing a foreign protocol.

    :param payload: The ``contract`` object a worker wrote.
    :returns: The typed contract.
    :raises ValueError: If the protocol differs from this comparator's.
    """
    seen = int(_number(payload, "protocol"))
    if seen != PROTOCOL:
        raise ValueError(
            f"benchmark protocol mismatch: worker wrote {seen}, comparator "
            f"expects {PROTOCOL}; the two harness copies are not the same "
            f"instrument"
        )
    return RowContract(
        seen,
        _text(payload, "row"),
        _text(payload, "grammar"),
        _text(payload, "grammar_digest"),
        _names(payload, "lexical"),
        _names(payload, "non_semantic"),
        _text(payload, "document_digest"),
        int(_number(payload, "document_bytes")),
        _text(payload, "scale"),
        _text(payload, "product"),
        int(_number(payload, "cores")),
        _flag(payload, "gc_enabled"),
        _names(payload, "clocks"),
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
    :ivar result_digest: Digest of the product's TEXT — the fidelity check.
        On a round trip this is the input, so it proves the document survived
        and nothing more.
    :ivar shape_digest: Digest of :func:`shape` — the structural check. This
        is the one that says two arms built the same product.
    :ivar verdict: ``accepted``, or the engine's refusal words verbatim.
    :ivar engaged: Whether a threaded row actually split; ``None`` if the row
        is sequential and the question does not apply.
    :ivar effective_workers: Worker threads the split was OBSERVED to occupy on
        an untimed attempt, never the count requested. The policy clamps useful
        workers by document size and cut count and cut selection can clamp them
        again, so the request answers a different question and two arms echoing
        it can occupy different machines and still compare.
    """

    wall: float
    cpu: float
    result_digest: str
    shape_digest: str
    verdict: str
    engaged: bool | None
    effective_workers: int

    def wire(self) -> dict[str, Json]:
        """The JSON-safe form written by a worker."""
        return dict(zip(Observation.__annotations__, self, strict=True))


def read_observation(payload: Mapping[str, Json]) -> Observation:
    """Rebuild one observation from a worker's JSON."""
    engaged = payload["engaged"]
    return Observation(
        _number(payload, "wall"),
        _number(payload, "cpu"),
        _text(payload, "result_digest"),
        _text(payload, "shape_digest"),
        _text(payload, "verdict"),
        None if engaged is None else _flag(payload, "engaged"),
        int(_number(payload, "effective_workers")),
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


def read_result(payload: Mapping[str, Json]) -> RowResult:
    """Rebuild a whole row result from one worker's final JSON line."""
    refusal = payload.get("refusal")
    if refusal is not None:
        return RowResult(None, (), str(refusal))
    seen = payload["observations"]
    if isinstance(seen, str) or not isinstance(seen, Sequence):
        raise ValueError(f"benchmark wire: observations is not a list: {seen!r}")
    return RowResult(
        read_contract(_mapping(payload, "contract")),
        tuple(read_observation(_as_object(entry)) for entry in seen),
        None,
    )


def _as_object(value: Json) -> Mapping[str, Json]:
    """One list element that must itself be an object."""
    if not isinstance(value, Mapping):
        raise ValueError(f"benchmark wire: expected an object, got {value!r}")
    return value
