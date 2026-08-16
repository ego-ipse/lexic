"""Shared reads over `GrammarModel.emit_addressed` — used by two suites.

The corpus gates (`tests/integration/lexic/roundtrip/test_addressed_emission`)
check one claim per test for a readable failure; the property suite
(`tests/property/lexic/test_addressed_emission`) checks all of them per
generated document. Both need the same two reads of the product, so they live
here rather than in either.
"""

from __future__ import annotations

from lexic.ir import IrExtents, IrSpan
from lexic.model import GrammarModel


def spelling(part: object) -> str:
    """What an occurrence spells — the three cases emission distinguishes.

    :param part: A model, a repeated field's tuple, or a spelling.
    :returns: The text that occurrence contributes to the emission.
    """
    if isinstance(part, GrammarModel):
        return part.to_text()
    if isinstance(part, tuple):
        return "".join(spelling(element) for element in part)
    return part if isinstance(part, str) else str(part)


def leaf_spans(extents: IrExtents) -> list[IrSpan]:
    """The spans of the extents nothing descends into, in document order.

    A leaf extent is one whose address is no other address's parent — the
    parts that actually contributed text rather than containing it.

    :param extents: One emission's extents.
    :returns: The leaf spans, sorted by position.
    """
    paths = {tuple(extent.address) for extent in extents}
    parents = {path[:-1] for path in paths if path}
    spans = [e.span for e in extents if tuple(e.address) not in parents]
    return sorted(spans, key=lambda span: (span.start, span.end))


def check_addressed(model: GrammarModel, where: str) -> None:
    """Assert the whole addressed-emission contract for one model.

    Four claims in one pass, because they only mean anything together: the
    text agrees with ``to_text``, every address resolves to the occurrence its
    span selects, no two occurrences share an address, and the leaf extents
    tile the text with nothing unattributed.

    :param model: A parsed model.
    :param where: What is being checked, for the failure message.
    """
    emission = model.emit_addressed()
    assert emission.text == model.to_text(), f"Addressed text diverged [{where}]"
    paths = [tuple(extent.address) for extent in emission.extents]
    assert len(set(paths)) == len(paths), f"Two occurrences shared an address [{where}]"
    for extent in emission.extents:
        assert extent.span.of(emission.text) == spelling(
            model.occurrence(extent.address)
        ), f"Span/occurrence mismatch [{where}]: {extent.address!r}"
    at = 0
    for span in leaf_spans(emission.extents):
        assert span.start == at, f"Coverage gap [{where}] at {at}"
        at = span.end
    assert at == len(emission.text), f"Coverage short [{where}]"
