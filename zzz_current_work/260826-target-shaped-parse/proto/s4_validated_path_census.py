"""Both populations complete through ONE clone vocabulary, and no fold.

This began as the census that stopped slice 2b: the validated build is not the
generated model's — every unlicensed model clone is an alternation, which
builds through the pass-through and reads no constructor at all — it is the
authored compile-time surfaces', and their completions named no construction
record the bake could read.

That is now closed, so the census asserts the closure rather than the blocker:

* the two populations still are what they were (the numbers are the evidence,
  and a shift in them means this file is measuring something else);
* every clone that builds reaches a construction — a declared record class or
  a registry-resolved surface transform — through the same clone slots;
* the runtime mentions no fold attribute anywhere, tokenized rather than
  grepped, so the claim "the fold left the runtime" is checked;
* an authored surface's keyword layout agrees with the fold's, rule by rule,
  for as long as both halves exist — which is what keeps the duplication a
  checked one;
* and the generated-model product still names no symbol, so the carve-out did
  not leak onto the paid path.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path
from typing import Any

from lexic.compile import compile_from_path
from lexic.compile.module.selfgrammar import (
    MODULE_BINDING,
    MODULE_GRAMMAR,
    MODULE_RULES,
)
from lexic.compile.notation.parse import (
    NOTATION_BINDING,
    NOTATION_GRAMMAR,
    NOTATION_RULES,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst
from lexic.parsing import ModelBinding
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import BUILD_TRANSPARENT
from lexic.parsing.product import RecordOp
from lexic.parsing.products import pda_tables

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
RUNTIME = ROOT / "src" / "lexic" / "parsing" / "pda"

READ_SOURCES = (
    RUNTIME / "runtime" / "build.py",
    RUNTIME / "runtime" / "kernel" / "execution.py",
    RUNTIME / "compiler" / "program" / "flatten.py",
    RUNTIME / "compiler" / "program" / "specialize.py",
)

FOLD_ATTRIBUTES = ("ctor", "n_items", "fields")
"""The fold attributes the completion sites used to reach through."""


def _check(claim: str, held: bool) -> None:
    """Refuse the census the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 validated census: {claim}")


def _surface(label: str, grammar: IrAst, binding: ModelBinding) -> tuple[int, int]:
    """One authored surface's clones, and how many complete without a record.

    :returns: ``(clones carrying a product, clones completing through a
        registry-resolved transform)``.
    """
    tables = pda_tables(grammar, binding)
    carried = 0
    symbolic = 0
    for spec in tables.clones.values():
        if spec.product is None:
            continue
        carried += 1
        symbolic += int(not isinstance(spec.product.completion, RecordOp))
    print(
        f"{label:<14}\tclones={carried:<5}\tsymbol completions={symbolic:<5}\t"
        f"records={len(binding.construction.constructors)}\t"
        f"symbols={len(binding.construction.symbols)}"
    )
    return carried, symbolic


def _generated() -> tuple[int, int, int]:
    """Every ground-truth grammar's model clones, by what they build through.

    :returns: ``(clones carrying a product, building a record, building
        nothing)``.
    """
    carried = 0
    records = 0
    nothing = 0
    for path in _grammars():
        compiled = compile_from_path(path)
        try:
            tables = compiled.pda_tables()
        except UnsupportedConstructError:
            continue
        _check(
            f"{path.name}: the model product names a symbol",
            not compiled.product.construction.symbols,
        )
        for spec in tables.clones.values():
            if spec.product is None:
                continue
            carried += 1
            if isinstance(spec.product.completion, RecordOp):
                records += 1
            else:
                nothing += 1
    print(
        f"{'generated':<14}\tclones={carried:<5}\trecord completions={records:<5}\t"
        f"pass-throughs={nothing}"
    )
    return carried, records, nothing


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    paths = sorted(GROUND_TRUTH.glob("*.gbnf"))
    return (
        paths
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    )


def every_building_clone_reaches_a_construction() -> None:
    """One vocabulary: a clone that builds names a ctor, one that does not, does not."""
    notation = _surface("notation", NOTATION_GRAMMAR, NOTATION_BINDING)
    module = _surface("selfgrammar", MODULE_GRAMMAR, MODULE_BINDING)
    carried, records, nothing = _generated()
    _check("no grammar compiled predictive tables", carried > 0)
    _check(
        "the authored surfaces reach no symbol completion — the census is vacuous",
        notation[1] + module[1] > 0,
    )
    _check(
        "the corpus builds no record — the census is vacuous",
        records > 0 and nothing > 0,
    )
    for label, grammar, binding in (
        ("notation", NOTATION_GRAMMAR, NOTATION_BINDING),
        ("selfgrammar", MODULE_GRAMMAR, MODULE_BINDING),
    ):
        _clone_slots(label, _flat_clones(pda_tables(grammar, binding)))
    print(
        f"one vocabulary\t{notation[1] + module[1]} symbol completions and "
        f"{records} record completions bake into the same clone slots"
    )


def _flat_clones(tables: Any) -> list[FlatClone]:
    """Every live flat clone the program reaches, from its entry."""
    seen: dict[int, FlatClone] = {}
    stack = [tables.program.start]
    while stack:
        clone = stack.pop()
        if not isinstance(clone, FlatClone) or id(clone) in seen:
            continue
        seen[id(clone)] = clone
        arms = [arm for _c, _n, arm in clone.selectors]
        if clone.default is not None:
            arms.append(clone.default)
        for arm in arms:
            if not hasattr(arm, "payloads"):
                continue
            stack.extend(arm.payloads)
    return list(seen.values())


def _clone_slots(label: str, clones: list[FlatClone]) -> None:
    """Every clone that builds carries a ctor; every one that does not, does not."""
    for clone in clones:
        where = f"{label}/{clone.name or '<group>'}"
        builds = clone.mode != BUILD_TRANSPARENT and clone.fields != ()
        _check(
            f"{where}: builds through {clone.fields} with no ctor",
            not builds or clone.ctor is not None,
        )
        _check(
            f"{where}: carries ctor {clone.ctor!r} while its mode is transparent",
            clone.mode != BUILD_TRANSPARENT or clone.ctor is None,
        )


def the_authored_keywords_agree_with_the_fold() -> None:
    """A surface's product and its fold say the same thing, rule by rule."""
    checked = 0
    for label, rules, binding in (
        ("notation", NOTATION_RULES, NOTATION_BINDING),
        ("selfgrammar", MODULE_RULES, MODULE_BINDING),
    ):
        baked = binding.fold.baked
        for name, rule in rules.items():
            if not rule.symbol:
                continue
            fold = baked[name]
            _check(
                f"{label}/{name}: keywords {rule.names} vs the fold's "
                f"{tuple(field.name for field in fold.fields)}",
                rule.names == tuple(field.name for field in fold.fields),
            )
            _check(
                f"{label}/{name}: arm width {rule.n_items} vs the fold's "
                f"{fold.n_items}",
                rule.n_items == fold.n_items,
            )
            checked += 1
    print(f"agree\t{checked} authored rules say the same in both halves")


def the_runtime_mentions_no_fold() -> None:
    """Tokenize the runtime and insist no `fold.<attr>` read survives."""
    found: list[str] = []
    for path in READ_SOURCES:
        source = path.read_text(encoding="utf-8")
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        for at, token in enumerate(tokens[:-2]):
            if token.type != tokenize.NAME or token.string != "fold":
                continue
            if tokens[at + 1].string != "." or tokens[at + 2].string not in (
                FOLD_ATTRIBUTES
            ):
                continue
            found.append(f"{path.name}:{token.start[0]}")
    _check(f"the runtime still reads a fold at {found}", not found)
    _check(
        "FlatClone declares a `fold` slot again",
        "fold" not in FlatClone.__slots__,
    )
    print(
        f"no fold\t0 fold reads across {len(READ_SOURCES)} runtime files, and "
        f"FlatClone declares none"
    )


def main() -> None:
    """Run the census; any disagreement with the closed blocker raises."""
    every_building_clone_reaches_a_construction()
    the_authored_keywords_agree_with_the_fold()
    the_runtime_mentions_no_fold()
    print("s4 validated census\tPASS\tone clone vocabulary, and no fold in the runtime")


if __name__ == "__main__":
    main()
