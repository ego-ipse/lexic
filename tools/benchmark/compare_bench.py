"""Unified path comparison — the same input, every way at once.

The other two benches each measure one slice: ``parse_bench`` races Lark
against the engine's **Earley** grammar-text path, and ``pipeline_bench`` times
the instance product. Neither puts **Lark**, **Earley**, and the **full PDA**
on the same input side by side, so their numbers cannot be read against each
other. This harness does: for each input text it times every applicable path
and prints them in one row, so "on this string, the PDA is X, Earley is Y,
Lark is Z" is a direct read.

## The four columns

- **lark-lalr** / **lark-earley** — the external reference, given every sample a
  native Lark grammar (``lark_refs``) and run under **both** of Lark's parsers,
  each its own column, timed at Lark's native output: ``parser.parse(text)`` → a
  Lark ``Tree`` (LALR uses the contextual lexer). Lark is *not* burdened with a
  second-pass transform to ``IrAst`` — that is work its native pipeline does not
  do. Where LALR is not viable for a grammar (it builds with conflicts then
  fails to parse the corpus — the two meta-grammars), the ``lark-lalr`` cell is
  empty and the row carries the failure note; LALR is never silently swapped for
  Earley.
- **earley** — the engine's Earley completion (``earley_reduce`` for
  grammar-text, ``earley_model`` for instances) → the typed ``IrAst`` / model.
- **pda** — the engine's full predictive PDA (``parse_pda`` over the compiled
  tables — the exact path the product runs first, islands sub-parsed inline) →
  the typed ``IrAst`` / model.

Because Lark yields a generic ``Tree`` while the engine builds a typed result,
the two ``lark`` columns omit construction the ``earley`` / ``pda`` columns
include — a fair reading of the numbers keeps that in mind.

## The two input families

- **grammar-text** (text → ``IrAst``): the ABNF/GBNF self-emit sources, each
  concatenated x1/x2/x4.
- **instance** (text → model): the ground-truth arithmetic/c/chess/json
  corpora parsed against their compiled grammars.

## Correctness gate

Before timing a case, every path is run once. The two **engine** paths are
cross-checked for output equality (``IrAst`` for grammar-text, round-trip
``to_text`` for models) — racing diverging implementations is meaningless, so a
divergence is reported loudly. **Lark** is verified by *recognition* — that it
parses the input without error — since its native ``Tree`` is a different shape
from the engine's typed result and cannot be equality-compared. An engine path
that raises ``PdaFail`` (an island start) is dropped from the timing.

Timing discipline (shared with ``parse_bench``): interleaved samples (one of
every path per round, so machine drift hits all alike), gc disabled per sample,
median ± stdev in ms, µs/char throughput, and a ``×pda`` ratio column.

Usage:
  uv run python tools/benchmark/compare_bench.py
  uv run --with lark python tools/benchmark/compare_bench.py   # force lark on
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from lark_refs import lark_variants
from parse_bench import SIZES, interleaved, load_lark, make_input
from pipeline_bench import _INSTANCE_WORKLOADS, GROUND_TRUTH

from lexic.compile import compile_from_path
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.flavour import IrFlavour
from lexic.model import GrammarModel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import (
    _model_product,
    _reduce_product,
    earley_model,
    earley_reduce,
)

Path = Callable[[str], object]
# column order; absent paths render "—". Both Lark parsers race every sample.
_ORDER = ("lark-lalr", "lark-earley", "earley", "pda")


@dataclass(slots=True)
class Case:
    """One input text and the paths that parse it, all producing one output type.

    :ivar label: The row label in the report.
    :ivar text: The input parsed by every path.
    :ivar paths: Path name → its timed one-shot callable (closes over the
        pre-built grammar / tables; construction is outside every timed loop).
    :ivar same: ``(a, b) -> bool`` — do the two *engine* paths' outputs agree?
        (``IrAst`` equality for grammar-text; round-trip ``to_text`` for
        models.) Lark is excluded — its native output is a generic Lark ``Tree``,
        not the engine's typed result, so it is verified by recognition (it
        parses the input) rather than output equality.
    :ivar rounds: Timing samples per path.
    :ivar lark_note: A note about a missing ``lark-lalr`` (LALR not viable for
        this grammar), or ``""``.
    """

    label: str
    text: str
    paths: dict[str, Path]
    same: Callable[[object, object], bool]
    rounds: int
    lark_note: str = ""
    agree: bool = True


def _reduce_paths(flavour: IrFlavour, lark: dict[str, Path]) -> dict[str, Path]:
    """The grammar-text paths for one flavour — both Lark parsers, earley, pda.

    All construction (normalisation, reduce-PDA compilation) happens here, once,
    outside every timed loop.

    :param flavour: The flavour whose self-grammar parses the input.
    :param lark: The viable native Lark parse callables (``lark-lalr`` /
        ``lark-earley``).
    :returns: Path name → timed callable, in column order.
    """
    norm = normalize(flavour.grammar)
    reducer = flavour.reducer
    assert isinstance(reducer, Reducer)  # narrow the ClassVar[IrDispatch] declaration
    reduce_pda = _reduce_product(flavour.grammar, reducer).pda
    paths: dict[str, Path] = dict(lark)
    paths["earley"] = lambda t: earley_reduce(norm, t, reducer)
    paths["pda"] = lambda t: parse_pda(reduce_pda, t, None)
    return paths


def _model_paths(stem: str, lark: dict[str, Path]) -> dict[str, Path]:
    """The instance paths for one ground-truth grammar — both Lark parsers, earley, pda.

    Compiles the grammar and builds both products once, outside timing.

    :param stem: The ground-truth grammar file stem (e.g. ``json.gbnf``).
    :param lark: The viable native Lark parse callables (``lark-lalr`` /
        ``lark-earley``).
    :returns: Path name → timed callable, in column order.
    """
    compiled = compile_from_path(GROUND_TRUTH / stem)
    fold = compiled.fold
    product = _model_product(compiled.codegen_grammar, fold)
    paths: dict[str, Path] = dict(lark)
    paths["earley"] = lambda t: earley_model(
        product.instance_grammar, t, fold, product.tables
    )
    paths["pda"] = lambda t: parse_pda(product.pda, t, fold)
    return paths


def _ir_same(a: object, b: object) -> bool:
    """Grammar-text agreement: structural ``IrAst`` equality."""
    return a == b


def _model_same(a: object, b: object) -> bool:
    """Instance agreement: both models reconstruct the same text."""
    if isinstance(a, GrammarModel) and isinstance(b, GrammarModel):
        return a.to_text() == b.to_text()
    return a == b


def _lark(
    lark_mod: ModuleType | None, key: str, probe: str
) -> tuple[dict[str, Path], str]:
    """Both viable native Lark parse callables for a sample, plus any LALR note.

    :param lark_mod: The imported ``lark`` module, or ``None``.
    :param key: The registry key (``abnf`` / ``gbnf`` / a ``.gbnf`` stem).
    :param probe: The corpus LALR must parse to be counted viable.
    :returns: ``(name -> parse callable, lalr note)``.
    """
    if lark_mod is None:
        return {}, ""
    return lark_variants(lark_mod, key, probe)


def build_cases(lark_mod: ModuleType | None) -> list[Case]:
    """Assemble every timed case — grammar-text (x1/x2/x4) and instance.

    :param lark_mod: The imported ``lark`` module, or ``None`` to omit Lark.
    :returns: The ordered list of cases.
    """
    cases: list[Case] = []
    grammar_text = (
        ("abnf self-emit", "abnf", ABNF_FLAVOUR),
        ("gbnf self-emit", "gbnf", GBNF_FLAVOUR),
    )
    for label, key, flavour in grammar_text:
        base = str(flavour.apply(flavour.grammar))
        lark, note = _lark(lark_mod, key, base)
        paths = _reduce_paths(flavour, lark)
        for repeat in SIZES:
            text = make_input(base, repeat)
            cases.append(
                Case(
                    f"{label} x{repeat}",
                    text,
                    paths,
                    _ir_same,
                    max(7, 40 // repeat),
                    note,
                )
            )
    for stem, make_corpus in _INSTANCE_WORKLOADS:
        corpus = make_corpus()
        lark, note = _lark(lark_mod, stem, corpus)
        paths = _model_paths(stem, lark)
        cases.append(Case(f"instance {stem}", corpus, paths, _model_same, 15, note))
    return cases


def check(case: Case) -> None:
    """Run every path once; verify Lark recognises and the engine paths agree.

    An engine path that raises :class:`PdaFail` (an island start) is dropped.
    The two engine paths are cross-checked for output equality (referenced
    against the PDA, so a message names the lone outlier). Lark is *not*
    compared on output — its native ``Tree`` is not the engine's typed result —
    only that it ran (recognition). Mutates ``case`` in place so the timed loop
    races only the surviving paths.

    :param case: The case to verify (mutated in place).
    """
    outputs: dict[str, object] = {}
    for name, fn in list(case.paths.items()):
        try:
            outputs[name] = fn(case.text)
        except PdaFail:
            del case.paths[name]
            print(f"  ! {case.label}: {name} raised PdaFail (island start) — dropped")
    ref_name = next((n for n in ("pda", "earley") if n in outputs), None)
    if ref_name is None:
        return
    reference = outputs[ref_name]
    for name in ("earley", "pda"):  # lark's native Tree is a different shape
        if (
            name in outputs
            and name != ref_name
            and not case.same(outputs[name], reference)
        ):
            case.agree = False
            print(f"  ! {case.label}: {name} DIVERGES from {ref_name}")


def _cell(samples: list[float]) -> str:
    """Format one ``median±stdev`` millisecond cell."""
    sd = statistics.stdev(samples) if len(samples) > 1 else 0.0
    return f"{statistics.median(samples):>7.1f}±{sd:<4.1f}ms"


def report(case: Case, samples: dict[str, list[float]]) -> dict[str, float]:
    """Print one case's side-by-side table; return its per-path µs/char.

    :param case: The timed case.
    :param samples: Path name → per-sample durations (ms).
    :returns: Path name → µs/char (for the closing summary matrix).
    """
    chars = len(case.text)
    pda = statistics.median(samples["pda"]) if "pda" in samples else None
    flag = "" if case.agree else "   [DIVERGENCE — see above]"
    note = f" · {case.lark_note}" if case.lark_note else ""
    print(f"{case.label}  ({chars} chars · {case.rounds} rounds{note}){flag}")
    print(f"  {'path':<12}{'median±sd':>15}{'µs/char':>10}{'×pda':>8}")
    per_char: dict[str, float] = {}
    for name in _ORDER:
        if name not in samples:
            continue
        med = statistics.median(samples[name])
        per_char[name] = med / chars * 1e3
        ratio = f"{med / pda:>6.2f}x" if pda else f"{'—':>7}"
        tail = "  ← reference" if name == "pda" else ""
        print(
            f"  {name:<12}{_cell(samples[name]):>15}{per_char[name]:>9.1f}{ratio}{tail}"
        )
    print()
    return per_char


def summary(matrix: list[tuple[str, dict[str, float]]]) -> None:
    """Print the closing µs/char matrix — every input × every path.

    :param matrix: ``(case label, path → µs/char)`` for every case, in order.
    """
    print("== summary — µs/char (lower is faster) ==")
    heads = ("lk-lalr", "lk-earley", "earley", "pda")
    print(f"  {'input':<26}" + "".join(f"{h:>11}" for h in heads))
    for label, per_char in matrix:
        cells = "".join(
            f"{per_char[p]:>11.1f}" if p in per_char else f"{'—':>11}" for p in _ORDER
        )
        print(f"  {label:<26}{cells}")
    print()
    print("  lark-lalr / lark-earley = native parse → Lark Tree; an empty lk-lalr")
    print("  cell means LALR is not viable for that grammar (see the row's note).")
    print("  earley / pda = parse → typed IrAst / model, so those two columns")
    print("  include construction the lark columns omit.")
    print()


def main() -> None:
    """Build the cases, cross-check, time each path interleaved, and report."""
    lark_mod = load_lark()
    side = "lark + earley + pda" if lark_mod else "earley + pda (lark not installed)"
    print(f"== unified path comparison: {side} ==\n")

    cases = build_cases(lark_mod)
    matrix: list[tuple[str, dict[str, float]]] = []
    for case in cases:
        check(case)
        samples = interleaved(case.paths, case.text, case.rounds)
        matrix.append((case.label, report(case, samples)))
    summary(matrix)


if __name__ == "__main__":
    main()
