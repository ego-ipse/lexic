"""Readout — what a finished kernel says about the parse it built.

Candidate ``lexic/parsing/earley/kernel/readout.py``. The decode seam, and the
symmetric counterpart of :mod:`~lexic.parsing.earley.kernel.tables`: where
``compile_tables`` walks a grammar *in*, these functions read the finished
packed SPPF *out* — the accepting items, the forest root, the decoded
:class:`~lexic.parsing.earley.kernel.chart.Chart`, and the valid-prefix probe an
island window asks of a completion column.

The dependency runs one way: ``kernel`` never imports ``readout``, so a readout
takes the :class:`~lexic.parsing.earley.kernel.kernel.Kernel` itself and reads its
four public fields (``tables``, ``text``, ``cols``, ``st``, plus ``delegated``
for the prefix probe). It calls no method on what it reads — which is what makes
the seam a seam.
"""

from __future__ import annotations

from lexic.ir import IrNone, IrSelf, IrSeq
from lexic.parsing.earley.kernel.chart import Chart, EarleyItem
from lexic.parsing.earley.kernel.forest import PayloadLeaf, RootNode, SppfNode
from lexic.parsing.earley.kernel.kernel import Kernel
from lexic.parsing.earley.kernel.leo import expand_leo
from lexic.parsing.earley.kernel.tables.records import ParserTables


def decode_item(tables: ParserTables, item: int) -> EarleyItem:
    """The :class:`EarleyItem` tuple for a packed ``item`` — the readable
    (non-int-coded) shape the chart/forest readers walk."""
    code = item >> tables.packing.bits
    aid = tables.codes.code_arm[code]
    return (
        tables.decode.rule_refs[tables.codes.arm_rule[aid]],
        tables.decode.arm_seqs[aid],
        code - tables.codes.arm_base[aid],
        item & tables.packing.mask,
    )


def accept_item(kern: Kernel) -> int:
    """The completed start item spanning the whole input, else ``-1``.

    Computed on read from the final column rather than stored — one fewer
    per-parse slot, and only read a handful of times after a full run (the
    island path reads its completion off ``longest_start_completion`` instead,
    never this).
    """
    accepts = kern.tables.codes.accept_codes
    pk = kern.tables.packing
    bits, mask = pk.bits, pk.mask
    for it in kern.cols[len(kern.text)]:
        if it >> bits in accepts and it & mask == 0:
            return it
    return -1


def accept_handle(kern: Kernel) -> int:
    """The accepting item packed over the whole input — the SPPF root key.

    The handle every single-derivation reader starts from. Undefined on no
    parse: check :func:`accept_item` first.
    """
    return (accept_item(kern) << kern.tables.packing.bits) | len(kern.text)


def accept_items(kern: Kernel) -> list[int]:
    """Every completed start item spanning the whole input (origin 0).

    Two or more items means the start symbol derives the whole input via
    distinct productions — genuine arm ambiguity with no parent waiter to
    aggregate it (see :class:`~lexic.parsing.earley.kernel.forest.RootNode`).

    :returns: The accepting items, in chart order (empty on no parse).
    """
    accepts = kern.tables.codes.accept_codes
    pk = kern.tables.packing
    bits, mask = pk.bits, pk.mask
    n = len(kern.text)
    return [it for it in kern.cols[n] if it >> bits in accepts and it & mask == 0]


def root_ambiguous(kern: Kernel) -> bool:
    """Whether the start symbol completes the whole input via ≥2 productions.

    The gate the single-derivation fast paths consult: a many-production root
    cannot be built by :class:`~lexic.parsing.earley.kernel.fasttree.FastTree` off
    one accepting item (the sibling productions live in other items), so those
    paths fall through to the trampolined enumeration over the
    :class:`~lexic.parsing.earley.kernel.forest.RootNode`.
    """
    return len(accept_items(kern)) > 1


def accept_node(kern: Kernel) -> IrSelf:
    """The forest root over the whole input, or :data:`IrNone` on no parse.

    A single accepting production returns its :class:`SppfNode` directly (the
    common case — no aggregation needed). Two or more accepting productions
    return a :class:`RootNode` packing them, so the enumeration readers see
    every arm the start symbol derives the input through.
    """
    items = accept_items(kern)
    if not items:
        return IrNone
    tables = kern.tables
    n = len(kern.text)
    if len(items) == 1:
        return SppfNode(decode_item(tables, items[0]), n)
    symbol = decode_item(tables, items[0])[0]
    return RootNode(
        symbol, IrSeq(*(SppfNode(decode_item(tables, it), n) for it in items))
    )


def to_chart(kern: Kernel) -> Chart:
    """Decode the packed SPPF into the IR-native :class:`Chart`.

    Deferred Leo chains are expanded eagerly first, so the decoded chart is
    complete and the forest readers never consult ``leo_links``. Used by the
    ambiguity / enumeration paths only — the unambiguous fast path
    (:class:`~lexic.parsing.earley.kernel.fasttree.FastTree`) reads the packed
    links directly.
    """
    st = kern.st
    tables = kern.tables
    for key in st.leo_links:
        expand_leo(st, tables, key)
    chart = Chart()
    links = chart.links
    bits, mask = tables.packing.bits, tables.packing.mask
    for key, bucket in st.links.items():
        dkey = (decode_item(tables, key >> bits), key & mask)
        for pred, pend, child in bucket:
            links += (
                dkey,
                (decode_item(tables, pred), pend, child_node(tables, child)),
            )
    return chart


def child_node(tables: ParserTables, child: int | str | PayloadLeaf) -> IrSelf:
    """Decode a packed family child — a handle, a scanned char, or a payload."""
    if isinstance(child, int):
        pk = tables.packing
        return SppfNode(decode_item(tables, child >> pk.bits), child & pk.mask)
    if isinstance(child, PayloadLeaf):  # delegated pre-folded child
        return child
    return tables.terms.char_leaf(child)


def can_extend_at(kern: Kernel, col: int, char: str) -> bool:
    """Whether the parse at ``col`` could consume ``char`` next — a MAY answer.

    The islands seam's valid-prefix probe: after a windowed
    ``longest_start_completion``, the caller asks whether the FULL text's next
    character is viable at a SHORT-OF-EDGE completion column — if it is, the
    completion may be a window-cut truncation and the window must grow.

    The chart is complete evidence exactly there: seeding is FIRST-gated by the
    column's own window character, and a short-of-edge column's window character
    IS the probe character, so every seed viable for it was admitted and
    registered — an empty/non-matching ``scannable`` is a *sighted* refusal, not
    blindness. Two conservative escapes remain, each answering MAY (which only
    ever grows the window):

    - a column where a delegate sub-run landed (the delegate's interior
      continuation items were never seeded into the chart) — derived from
      ``delegated``'s handles, whose low bits are the landing column (islands
      always run with ``record_links``, so every landing is recorded);
    - a probe character that is NOT the column's window character (an
      out-of-domain call — the gates were evaluated with a different char, so
      the chart proves nothing about this one).

    :param col: The completion column to probe (its closure already ran).
    :param char: The next character of the full input.
    :returns: ``True`` when ``char`` may be consumable at ``col``.
    """
    mask = kern.tables.packing.mask
    if any(handle & mask == col for handle in kern.delegated):
        return True
    if col >= len(kern.text) or kern.text[col] != char:
        return True
    scannable_col = kern.st.scannable[col]
    return any(scannable_col.get(tid) for tid in kern.tables.terms.terms_for(char))
