"""Readout — what a finished kernel says about the parse it built.

Candidate ``lexic/parsing/earley/kernel/readout.py``. The decode seam, and the
symmetric counterpart of :mod:`~lexic.parsing.earley.kernel.tables`: where
``compile_tables`` walks a grammar *in*, these functions read the finished
packed SPPF *out* — the accepting items, the forest root, and the decoded
:class:`~lexic.parsing.earley.kernel.forest.chart.Chart`.

The dependency runs one way: ``kernel`` never imports ``readout``, so a readout
takes the :class:`~lexic.parsing.earley.kernel.loop.kernel.Kernel` itself and reads its
public fields (``tables``, ``text``, ``cols``, ``st``). It calls no method on
what it reads — which is what makes the seam a seam.
"""

from __future__ import annotations

from lexic.ir import IrNone, IrSelf, IrSeq
from lexic.parsing.earley.kernel.forest.chart import Chart, EarleyItem
from lexic.parsing.earley.kernel.forest.forest import PayloadLeaf, RootNode, SppfNode
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo
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
    aggregate it (see :class:`~lexic.parsing.earley.kernel.forest.forest.RootNode`).

    :returns: The accepting items, in chart order (empty on no parse).
    """
    accepts = kern.tables.codes.accept_codes
    pk = kern.tables.packing
    bits, mask = pk.bits, pk.mask
    n = len(kern.text)
    return [it for it in kern.cols[n] if it >> bits in accepts and it & mask == 0]


def start_completion_ends(kern: Kernel) -> tuple[int, ...]:
    """Every distinct end column where the start rule completes from origin 0.

    The island seam's cross-span evidence: after a windowed
    ``longest_start_completion`` drove the chart, these are ALL the spans the
    island could be — the (fixed) growth predicate guarantees none is
    reachable beyond the longest. More than one end is an arm choice the
    same-span gate cannot see; whether it must refuse is the caller's
    composition question.

    :returns: Ascending distinct completion ends (empty on no completion).
    """
    accepts = kern.tables.codes.accept_codes
    bits, mask = kern.tables.packing.bits, kern.tables.packing.mask
    ends = {
        j
        for j, col in enumerate(kern.cols)
        for it in col
        if it >> bits in accepts and it & mask == 0
    }
    return tuple(sorted(ends))


def root_ambiguous(kern: Kernel) -> bool:
    """Whether the start symbol completes the whole input via ≥2 productions.

    The gate the single-derivation fast paths consult: a many-production root
    cannot be built by :class:`~lexic.parsing.earley.kernel.forest.fasttree.FastTree` off
    one accepting item (the sibling productions live in other items), so those
    paths fall through to the trampolined enumeration over the
    :class:`~lexic.parsing.earley.kernel.forest.forest.RootNode`.
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
    (:class:`~lexic.parsing.earley.kernel.forest.fasttree.FastTree`) reads the packed
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
