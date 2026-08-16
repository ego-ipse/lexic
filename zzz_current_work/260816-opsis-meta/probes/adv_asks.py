"""Adversarial counter-probe against probes/probe_asks.py and ASKS.md.

Each section tries to BREAK a claim. Prints numbered results; nothing is
asserted (the point is to show what is false), run:

    uv run python zzz_current_work/260816-opsis-meta/probes/adv_asks.py
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

from lexic.compile import canonical_grammar, compile_text, parse_grammar
from lexic.compile.pipeline.passes import (
    build_codegen_grammar,
    hoist_arms,
    hoist_groups,
    relax_non_semantic,
)
from lexic.exceptions import LexicError
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAction, IrLambda, IrSeq, IrStr, IrTypeMap
from lexic.ir.action.walk import IrDispatch
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.spine import IrLeaf, IrSelf
from lexic.model import GrammarModel

ROOT = Path(__file__).resolve().parents[3]
GT = ROOT / "resources/ground_truth"


def say(n: str, msg: str) -> None:
    print(f"[{n}] {msg}")


# ── A1: canonical equality is NOT language equality ─────────────────────
def a1_canonical_equality() -> None:
    gbnf = (GT / "json.gbnf").read_text()
    a = canonical_grammar(gbnf, GBNF_FLAVOUR)
    # rename ONE rule + its refs: same language, different spelling
    renamed = gbnf.replace("value", "vaLUE")
    b = canonical_grammar(renamed, GBNF_FLAVOUR)
    say("A1a", f"rename value→vaLUE (case fold): canonical equal = {a == b}")
    renamed2 = gbnf.replace("value", "val")
    c = canonical_grammar(renamed2, GBNF_FLAVOUR)
    say("A1b", f"rename value→val: canonical equal = {a == c}  (same language)")
    # a genuinely different FORMULATION of the same language
    ebnf = (GT / "json.ebnf").read_text()
    d = canonical_grammar(ebnf, EBNF_FLAVOUR)
    say("A1c", f"json.gbnf == json.ebnf canonically: {a == d}")
    say("A1c", f"  gbnf rules: {len(a.rules)}  ebnf rules: {len(d.rules)}")
    arr = (GT / "json_arr.gbnf").read_text()
    e = canonical_grammar(arr, GBNF_FLAVOUR)
    say("A1d", f"json.gbnf == json_arr.gbnf canonically: {a == e}")
    ws = (GT / "json_ws.gbnf").read_text()
    f = canonical_grammar(ws, GBNF_FLAVOUR)
    say("A1e", f"json.gbnf == json_ws.gbnf canonically: {a == f}")
    say("A1", f"gbnf rule names: {sorted(str(r.name) for r in a.rules)}")
    say("A1", f"ebnf rule names: {sorted(str(r.name) for r in d.rules)}")


# ── A2: the interior probe compares two different CHILD DEFINITIONS ─────
def _walk(root: IrSelf, kids) -> tuple[int, int]:
    seen: set[int] = set()
    re_reach = 0
    stack = [root]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            re_reach += 1
            continue
        seen.add(id(n))
        stack.extend(kids(n))
    return len(seen), re_reach


def a2_interior() -> None:
    g = GBNF_FLAVOUR.grammar

    def by_children(n):
        return [c for c in n.children() if isinstance(c, IrSelf)]

    def by_tuple(n):
        if isinstance(n, (IrNamedTuple, IrTuple, IrSeq)):
            return [c for c in tuple(n) if isinstance(c, IrSelf)]
        return []

    nc, rc = _walk(g, by_children)
    nt, rt = _walk(g, by_tuple)
    say("A2a", f"children() walk: {nc} nodes, {rc} re-reachings")
    say("A2b", f"field-tuple walk: {nt} nodes, {rt} re-reachings")
    say(
        "A2c",
        "the probe reported re-reachings ONLY for the tuple walk and compared "
        "node counts across TWO DIFFERENT child definitions",
    )
    # no-memo count under ONE definition = the real sharing measure
    def count_no_memo(root, kids, cap=2_000_000):
        n = 0
        stack = [root]
        while stack and n < cap:
            node = stack.pop()
            n += 1
            stack.extend(kids(node))
        return n

    say("A2d", f"children() walk WITHOUT memo: {count_no_memo(g, by_children)} visits")
    say("A2e", f"tuple walk WITHOUT memo:     {count_no_memo(g, by_tuple)} visits")


# ── A3: altitude cost — the probe measured a WARM accept + 2 early refusals
def a3_altitude() -> None:
    text = (GT / "json.gbnf").read_text()
    for flavour, src in (
        (GBNF_FLAVOUR, text),
        (ABNF_FLAVOUR, text),
        (EBNF_FLAVOUR, text),
    ):
        t = time.perf_counter()
        try:
            parse_grammar(src, flavour)
            verdict = "accepts"
        except LexicError as err:
            verdict = f"refuses({type(err).__name__})"
        say("A3a", f"cold {flavour.name}: {verdict} {1000 * (time.perf_counter() - t):.0f}ms")
    # second round = warm
    for flavour in (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR):
        t = time.perf_counter()
        try:
            parse_grammar(text, flavour)
            verdict = "accepts"
        except LexicError as err:
            verdict = f"refuses({type(err).__name__})"
        say("A3b", f"warm {flavour.name}: {verdict} {1000 * (time.perf_counter() - t):.0f}ms")
    # the EXPENSIVE altitude case: a reader that ACCEPTS a long text
    big = (GT / "c.gbnf").read_text()
    t = time.perf_counter()
    parse_grammar(big, GBNF_FLAVOUR)
    say("A3c", f"cold accept of c.gbnf ({len(big)} chars): {1000 * (time.perf_counter() - t):.0f}ms")
    t = time.perf_counter()
    try:
        parse_grammar(big, ABNF_FLAVOUR)
        v = "accepts"
    except LexicError as err:
        v = f"refuses({type(err).__name__})"
    say("A3d", f"abnf on c.gbnf: {v} {1000 * (time.perf_counter() - t):.0f}ms")


# ── A4: the pass moments — is the THIRD moment ever distinct? ───────────
def a4_passes() -> None:
    for name in ("json.gbnf", "vyx.gbnf", "c.gbnf", "chess.gbnf"):
        ast = canonical_grammar((GT / name).read_text(), GBNF_FLAVOUR)
        m1 = hoist_groups(ast)
        m2 = hoist_arms(m1)
        m3 = relax_non_semantic(m2)
        say(
            "A4",
            f"{name}: m1!=ast {m1 != ast} · m2!=m1 {m2 != m1} · m3!=m2 {m3 != m2} "
            f"· fused==m3 {build_codegen_grammar(ast) == m3} "
            f"· non_semantic={sorted(ast.non_semantic)}",
        )


# ── A5: emit_parts is SHALLOW and carries no offsets ────────────────────
def a5_emit_parts() -> None:
    compiled = compile_text((GT / "json.gbnf").read_text())
    doc = '{"a": [1, true], "b": null}'
    model = compiled.parse(doc)
    parts = model.emit_parts()
    say("A5a", f"root emit_parts: {len(parts)} items -> {[(k, type(v).__name__) for k, v in parts]}")
    total = 0
    stack = [model]
    while stack:
        n = stack.pop()
        if isinstance(n, GrammarModel):
            p = GrammarModel.emit_parts(n)
            total += len(p)
            stack.extend(v for _k, v in p)
        elif isinstance(n, (list, tuple)) and not isinstance(n, str):
            stack.extend(n)
    say("A5b", f"whole-document emit_parts items (recursive): {total} for {len(doc)} chars")
    say("A5c", f"any offset in an emit_parts item? tuple arity = {len(parts[0])} (field, part)")


# ── A6: addressing children by EQUALITY is broken on the value spine ────
class Region(IrNamedTuple):
    _child_attrs: ClassVar[tuple[str, ...]] = ("parts",)
    addr: str
    kind: str
    parts: IrSeq


def _names_of(node: IrSelf) -> list[str]:
    named = getattr(type(node), "_fields", ())
    if isinstance(node, IrNamedTuple) and named:
        return list(named)
    if isinstance(node, (IrSeq, IrTuple)):
        return [str(i) for i in range(len(tuple(node)))]
    return []


def a6_equality_addressing() -> None:
    compiled = compile_text((GT / "json.gbnf").read_text())
    model = compiled.parse('[1, 1]')
    kids = [c for c in tuple(model) if isinstance(c, IrSelf)]
    say("A6a", f"root children: {[type(k).__name__ for k in kids]}")
    # find any node with two equal IrSelf children — the probe's
    # `ir_children.index(child)` maps both to the FIRST one
    stack = [model]
    hits = 0
    while stack:
        n = stack.pop()
        ch = [c for c in tuple(n) if isinstance(c, IrSelf)] if isinstance(
            n, (IrNamedTuple, IrTuple, IrSeq)
        ) else []
        for i, c in enumerate(ch):
            if ch.index(c) != i:
                hits += 1
                say(
                    "A6b",
                    f"{type(n).__name__}: child {i} ({type(c).__name__}) is .index()-"
                    f"aliased to slot {ch.index(c)} — same VALUE, different occurrence",
                )
        stack.extend(ch)
    say("A6c", f"equality-aliased child slots in [1, 1]: {hits}")
    # and the identity trap: two equal models are the SAME dict key by id? no —
    # but the probe's fold memoises on id(), which is fine; the ALIASING is in
    # ir_children.index(child).
    same = compiled.parse('[1, 1]')
    say("A6d", f"two separately-parsed identical docs compare equal: {model == same}")


# ── A7: what the Region floor does NOT carry ───────────────────────────
def a7_region_has_no_geometry() -> None:
    say("A7", f"Region fields: {Region._fields} — no width, no coordinate, no span")
    from lexic.ir.text.layout import IrDoc, render

    say("A7", f"IrDoc.render solves ONE axis: {render.__doc__.splitlines()[0]!r}")
    say("A7", f"IrDoc protocol methods: {[m for m in ('layout', 'scan') if hasattr(IrDoc, m)]}")


def main() -> None:
    a1_canonical_equality()
    a2_interior()
    a3_altitude()
    a4_passes()
    a5_emit_parts()
    a6_equality_addressing()
    a7_region_has_no_geometry()


if __name__ == "__main__":
    main()
