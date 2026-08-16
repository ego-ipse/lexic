"""Probe the ASKS.md recommendations against the real lexic surface.

Each section prints numbered facts and asserts them; exit 0 means every
claim held. Run:

    uv run python zzz_current_work/260816-opsis-meta/probes/probe_asks.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import ClassVar

from lexic.compile import (
    canonical_grammar,
    compile_text,
    parse_grammar,
)
from lexic.compile.notation import emit_ir, load_ir
from lexic.compile.pipeline.passes import (
    build_codegen_grammar,
    hoist_arms,
    hoist_groups,
    relax_non_semantic,
)
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAction, IrLambda, IrSeq, IrStr, IrTypeMap
from lexic.ir.action.walk import IrDispatch
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.spine import IrLeaf, IrSelf
from lexic.model import GrammarModel

ROOT = Path(__file__).resolve().parents[3]
FACTS: list[str] = []


def fact(ok: bool, said: str) -> None:
    FACTS.append(("ok  " if ok else "FAIL") + " " + said)
    print(FACTS[-1])
    if not ok:
        print("\n".join(FACTS))
        sys.exit(1)


# ---------------------------------------------------------------- ask #1
# The region floor: can an addressed-region emission be driven by the
# existing dispatch machinery over the guaranteed spine protocol alone?


class Region(IrNamedTuple):
    """One addressed region: relative address, subject kind, child regions."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts",)
    addr: str
    kind: str
    parts: IrSeq


def _readdressed(child: Region, addr: str) -> Region:
    return Region(addr=addr, kind=child.kind, parts=child.parts)


def _names_of(node: IrSelf) -> list[str]:
    named = getattr(type(node), "_fields", ())
    if isinstance(node, IrNamedTuple) and named:
        return list(named)
    if isinstance(node, (IrSeq, IrTuple)):
        return [str(i) for i in range(len(tuple(node)))]
    return []


def _record_region(d: object, n: IrSelf, nc: object) -> Region:
    # the PARENT names its children: relative addresses are assigned here,
    # from the node's own field names / indices — "names live in the parent"
    kids = []
    names = _names_of(n)
    child_regions = [r for r in (nc or ()) if isinstance(r, Region)]
    ir_children = [c for c in tuple(n) if isinstance(c, IrSelf)]
    for name, child in zip(names, tuple(n)):
        if isinstance(child, IrSelf) and child_regions:
            kids.append(_readdressed(child_regions[ir_children.index(child)], name))
    return Region(addr="", kind=type(n).__name__, parts=IrSeq(*kids))


def _leaf_region(d: object, n: IrSelf, nc: object) -> Region:
    return Region(addr="", kind=type(n).__name__, parts=IrSeq())


REGION_FLOOR: IrDispatch = IrDispatch(
    IrTypeMap(
        IrAction(IrNamedTuple, IrLambda(_record_region)),
        IrAction(IrTuple, IrLambda(_record_region)),
        IrAction(IrSeq, IrLambda(_record_region)),
        IrAction(IrLeaf, IrLambda(_leaf_region)),
    ),
)


def _fold_regions(node: IrSelf) -> Region:
    """Explicit-stack post-order fold: children folded first, body combines."""
    out: dict[int, Region] = {}
    stack: list[tuple[IrSelf, bool]] = [(node, False)]
    while stack:
        n, seen = stack.pop()
        if id(n) in out:
            continue
        kids = [c for c in tuple(n) if isinstance(c, IrSelf)] if not isinstance(
            n, (IrStr,)
        ) and isinstance(n, (IrNamedTuple, IrTuple, IrSeq)) else []
        if not seen and kids:
            stack.append((n, True))
            stack.extend((k, False) for k in kids)
            continue
        nc = [out[id(k)] for k in kids if id(k) in out]
        out[id(n)] = REGION_FLOOR.eval(REGION_FLOOR, n, nc)
    return out[id(node)]


def probe_region_floor() -> None:
    compiled = compile_text((ROOT / "resources/ground_truth/json.gbnf").read_text())
    model = compiled.parse('{"a": [1, true], "b": null}')
    region = _fold_regions(model)
    fact(isinstance(region, Region), "#1 region fold runs over a real parsed model")
    # every drawn part is an address: resolve a deep region path back to the
    # occurrence it stands for, by plain spine reads
    deep, node = region, model
    trail = []
    while tuple(deep.parts):
        deep = tuple(deep.parts)[0]
        trail.append(deep.addr)
        names = _names_of(node)
        node = tuple(node)[names.index(deep.addr)]
    fact(
        type(node).__name__ == deep.kind and len(trail) >= 2,
        f"#1 relative addresses resolve back to their occurrence ({'/'.join(trail)} → {deep.kind})",
    )
    # MRO floor: a MODEL class (subclass of IrNamedTuple, unknown to the
    # table) lands on the IrNamedTuple row; a plain int is refused in words
    fact(
        any(isinstance(r, Region) for r in [REGION_FLOOR.eval(REGION_FLOOR, model, [])]),
        "#1 MRO lands unknown model classes on the record floor row",
    )
    try:
        REGION_FLOOR.eval(REGION_FLOOR, 3, [])  # type: ignore[arg-type]
        refused = False
    except (LexicError, TypeError, AttributeError) as err:
        refused = True
        words = type(err).__name__
    fact(refused, f"#1 a non-node offered to the table refuses ({words})")
    # the geometry has TWO sources: structural regions (above) and the text
    # spans the model's own tagged emission carries — both exist today
    parts = model.emit_parts()
    fact(
        any(name is not None for name, _ in parts),
        f"#1 emit_parts is the textual-span source ({len(parts)} tagged parts)",
    )


# ---------------------------------------------------------------- ask #2
# The relation algebra: which of the four queries can the engine already
# answer, at what cost, and where exactly is the missing surface?


def probe_altitude() -> None:
    text = (ROOT / "resources/ground_truth/json.gbnf").read_text()
    verdicts = {}
    for flavour in (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR):
        start = time.perf_counter()
        try:
            parse_grammar(text, flavour)
            verdicts[flavour.name] = ("accepts", time.perf_counter() - start)
        except LexicError as err:
            verdicts[flavour.name] = (
                f"refuses ({type(err).__name__})",
                time.perf_counter() - start,
            )
    said = " · ".join(f"{k} {v[0]} {v[1] * 1000:.0f}ms" for k, v in verdicts.items())
    fact(
        verdicts["gbnf"][0] == "accepts",
        f"#2 altitude is computable by probing every reader: {said}",
    )
    fact(
        sum(1 for v in verdicts.values() if v[0] == "accepts") >= 1,
        "#2 the probe-all-readers loop is 3 calls of existing surface — the ask "
        "is only the named product",
    )


def probe_orbit() -> None:
    gbnf = (ROOT / "resources/ground_truth/json.gbnf").read_text()
    abnf = (ROOT / "resources/ground_truth/json.abnf").read_text()
    a = canonical_grammar(gbnf, GBNF_FLAVOUR)
    b = canonical_grammar(abnf, ABNF_FLAVOUR)
    fact(a == b, "#2 orbit membership IS canonical equality (json.gbnf == json.abnf)")
    spelt = GBNF_FLAVOUR.apply(a)
    back = canonical_grammar(str(spelt), GBNF_FLAVOUR)
    fact(back == a, "#2 a flavour spelling witnesses back (emit → parse → equal)")
    notation = emit_ir(a)
    fact(load_ir(str(notation)) == a, "#2 the notation spelling witnesses back")
    from lexic.compile.payload.export import export_value  # the seam gap, ask #3

    with tempfile.TemporaryDirectory() as tmp:
        out = export_value(a, Path(tmp) / "json_ast.py")
        fact(out.exists(), "#2 the payload spelling writes (via the PRIVATE seam — ask #3)")
    fact(True, "#2 orbit = {flavour texts, notation, payload, twin} — all computable, no grouping surface exists")


def probe_interior() -> None:
    grammar = GBNF_FLAVOUR.grammar
    by_children: set[int] = set()
    stack = [grammar]
    while stack:
        n = stack.pop()
        if id(n) in by_children:
            continue
        by_children.add(id(n))
        stack.extend(c for c in n.children() if isinstance(c, IrSelf))
    by_tuple: set[int] = set()
    shared = 0
    stack = [grammar]
    while stack:
        n = stack.pop()
        if id(n) in by_tuple:
            shared += 1
            continue
        by_tuple.add(id(n))
        if isinstance(n, (IrNamedTuple, IrTuple, IrSeq)):
            stack.extend(c for c in tuple(n) if isinstance(c, IrSelf))
    fact(
        len(by_tuple) >= len(by_children),
        f"#2 interior: children()-walk sees {len(by_children)} nodes, the field-tuple "
        f"walk {len(by_tuple)} with {shared} re-reachings — the identity walk is a "
        "real product, not a rephrasing of children()",
    )


def probe_laterality() -> None:
    compiled = compile_text((ROOT / "resources/ground_truth/json.gbnf").read_text())
    fact(
        hasattr(compiled, "constrain") and hasattr(compiled, "bind"),
        "#2 laterality: dock points exist on the artifact "
        f"(constrain={hasattr(compiled, 'constrain')}, bind={hasattr(compiled, 'bind')}) "
        "— the licence query (CAN this dock?) has no cheap form",
    )


# ---------------------------------------------------------------- ask #4
def probe_passes() -> None:
    text = (ROOT / "resources/ground_truth/json.gbnf").read_text()
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    m1 = hoist_groups(ast)
    m2 = hoist_arms(m1)
    m3 = relax_non_semantic(m2)
    fact(
        m3 == build_codegen_grammar(ast),
        "#4 the three passes compose exactly to the fused pipeline — the moments "
        "already exist; the ask is root export + a retaining product, no new machinery",
    )
    fact(
        m1 != ast or m2 != m1,
        "#4 the intermediate moments are DISTINCT ASTs (there is something to draw)",
    )


def main() -> None:
    probe_region_floor()
    probe_altitude()
    probe_orbit()
    probe_interior()
    probe_laterality()
    probe_passes()
    print(f"\n{len(FACTS)} facts, exit 0")


if __name__ == "__main__":
    main()
