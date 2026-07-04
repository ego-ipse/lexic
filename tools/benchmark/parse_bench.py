"""Pure-Lark parse benchmark — the reference baseline for the engine-perf effort.

The old ``zzz_current_work/bench_parsing.py`` raced the native IR Earley engine
against *Lark-inside-lexic* (``MetaGrammarParser``). That path is deleted. This
bench keeps the same corpus and timing discipline but pits the engine against
**pure Lark** — the Lark parse *and* the Lark → ``IrAst`` reduction recovered
verbatim from git history and embedded here, so the Lark side is fully
self-contained and carries no current-lexic parser/reducer/flavour machinery.

Corpora (two workloads, each concatenated x1/x2/x4 per :data:`SIZES`): a
concatenation of valid rulelists is itself a valid rulelist, so parse cost is
what scales; duplicate rule names are immaterial to the parser.

  self-emit    the ABNF-of-ABNF source (``ABNF_FLAVOUR.apply(grammar)``, ~2 KB)
  subset-920   the fixed old-subset-grammar self-emit pinned in
               ``corpus_subset_920.abnf`` (920 chars) — the corpus
               ``zzz_current_work/Disputed.md`` measured its regression
               claims against; kept byte-exact so this harness reproduces
               those numbers against whatever grammar is at HEAD.

Timing (unchanged): interleaved samples (one of every variant per round, so
machine drift hits all alike), median ± stdev in ms, gc disabled around each
sample, and µs/char throughput in the verdict.

**Stages timed (construction and table compilation are excluded from every
timed loop via warm-up, keeping the two sides symmetric):**

  stage          engine                          pure lark
  recognize      recognize()   → IrInt           (no counterpart — Lark has no
                                                   recognition-only mode)
  parse          parse()       → ParseTree       Lark.parse → Lark Tree
  parse+reduce   parse_reduced → IrAst           Lark.parse + embedded reducer
                                                   → IrAst

The engine ``parse`` stage (text → native tree) is the symmetric race against
Lark ``parse`` (text → Lark Tree). ``parse+reduce`` is the full product on both
sides (text → ``IrAst``). ``recognize`` is engine-only — Lark always builds a
tree, so there is no pure-recognition number to compare against; the row is kept
because it isolates the engine's recognition cost for the diagnosis below.

The DIAGNOSIS section answers *why* engine text→tree is ~2× Lark: a stage-delta
breakdown (recognition vs tree-materialisation vs fused product), a cProfile
pass over the engine ``parse`` stage, and a verdict on what must get faster.

Recovered-for-benchmark code (the ``RECOVERED`` block) is a faithful copy of the
pre-cutover ``MetaGrammarParser`` tree-walk (git ``HEAD:src/lexic/parsing/
meta_parser.py``) and the ABNF flavour callbacks it dispatched to (git
``HEAD:src/lexic/grammars/abnf.py``). Its *only* current-lexic dependency is the
shared IR node vocabulary (``lexic.ir.*``): the reduced ``IrAst`` must be
node-for-node comparable with the engine's, so both sides necessarily build the
same node types. No current parser/reducer/flavour machinery is touched.

Usage:
  uv run python tools/benchmark/parse_bench.py            # both sides if lark present
  uv run --with lark python tools/benchmark/parse_bench.py  # force lark available
  uv run python tools/benchmark/parse_bench.py --save      # also write bench_baseline.json
"""

from __future__ import annotations

import cProfile
import gc
import importlib
import importlib.util
import json
import pstats
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir.base import IrAtom, IrNone, IrSeq
from lexic.ir.canonical import canonicalize
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.parsing import parse as engine_parse
from lexic.parsing import parse_reduced as engine_parse_reduced
from lexic.parsing import recognize as engine_recognize
from lexic.parsing.normalize import normalize

# ── The pre-cutover Lark ABNF meta-grammar, recovered verbatim ─────────
# Source: git HEAD:src/lexic/grammars/abnf.py (the ``META_GRAMMAR`` string, RFC
# 5234 + RFC 7405). Embedded so the Lark side carries zero lexic machinery.
META_GRAMMAR = r"""
start: rule+

rule: NAME "=" alternation             -> ir_rule
    | NAME INCREMENTAL alternation     -> ir_rule_inc

alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                        -> ir_sequence

item: QUANTIFIER? element              -> ir_item
    | "[" alternation "]"              -> ir_option

element: LITERAL                       -> ir_literal
    | CS_STRING                        -> ir_literal_cs
    | CI_STRING                        -> ir_literal_ci
    | NUMSEQ                           -> ir_numseq
    | NUMVAL                           -> ir_charclass
    | PROSE                            -> ir_prose
    | NAME                             -> ir_ruleref
    | "(" alternation ")"              -> ir_group

INCREMENTAL.2: /=\//
NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
CS_STRING: /%[sS]"[^"\r\n]*"/
CI_STRING: /%[iI]"[^"\r\n]*"/
NUMSEQ.2: /%[bdxBDX][0-9A-Fa-f]+(?:\.[0-9A-Fa-f]+)+/
NUMVAL: /%[bdxBDX][0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
PROSE: /<[^>\r\n]*>/
QUANTIFIER: /[0-9]*\*[0-9]*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""

# ── Setup (excluded from every timed loop) ─────────────────────────────
BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_FLAVOUR.grammar))
NORM_GRAMMAR = normalize(ABNF_FLAVOUR.grammar)
REDUCER = ABNF_FLAVOUR.reducer
SIZES = (1, 2, 4)
LARK_HINT = "run: uv run --with lark python tools/benchmark/parse_bench.py"
BASELINE_PATH = Path(__file__).parent / "bench_baseline.json"


@dataclass(frozen=True, slots=True)
class Workload:
    """One timed corpus: a name and the base text repeated per :data:`SIZES`."""

    name: str
    base_text: str


SUBSET_TEXT = (Path(__file__).parent / "corpus_subset_920.abnf").read_text()
WORKLOADS: tuple[Workload, ...] = (
    Workload("self-emit", BASE_TEXT),
    Workload("subset-920", SUBSET_TEXT),
)

Variant = Callable[[str], object]

# ─────────────────────────────────────────────────────────────────────
# RECOVERED-FOR-BENCHMARK — the retired Lark → IrAst reduction.
# Faithful copy of git HEAD:src/lexic/parsing/meta_parser.py plus the ABNF
# flavour callbacks from git HEAD:src/lexic/grammars/abnf.py. Only current-
# lexic dependency: the IR node vocabulary (needed so the output IrAst is
# comparable with the engine's). No current parser/reducer/flavour is used.
# ─────────────────────────────────────────────────────────────────────

# ABNF's escape codec is the identity codec (empty escape tables), so its
# ``decode`` is a no-op; recovered as such rather than importing the codec.
_CANONICAL_SHORT_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    "]": "]",
    "-": "-",
    "^": "^",
}
_CANONICAL_HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


def _canonical_read_escape(source: str, i: int) -> tuple[str, int]:
    """Parse one canonical escape at ``source[i] == '\\'`` → (char, new_i).

    Recovered from ``EscapeCodec.read_escape`` for the ``CANONICAL_ESCAPES``
    tables; used only to split a decoded char-class pattern into units.

    :param source: The pattern text.
    :param i: Index of the backslash.
    :returns: The decoded char and the index just past the escape.
    """
    c = source[i + 1]
    if c in _CANONICAL_SHORT_ESCAPES:
        return _CANONICAL_SHORT_ESCAPES[c], i + 2
    for tag, n in _CANONICAL_HEX_ESCAPES:
        if c == tag and i + 1 + n < len(source):
            return chr(int(source[i + 2 : i + 2 + n], 16)), i + 2 + n
    return c, i + 2


def _read_unit(s: str, i: int) -> tuple[str, int]:
    """Read one encoded escape unit at ``s[i]`` — text kept verbatim.

    :param s: The pattern text.
    :param i: The read cursor.
    :returns: The verbatim unit and the next cursor.
    """
    if s[i] == "\\" and i + 1 < len(s):
        _, j = _canonical_read_escape(s, i)
        return s[i:j], j
    return s[i], i + 1


def _unit_to_chr(unit: str) -> str:
    """Decode a verbatim escape unit to its single decoded glyph.

    :param unit: A unit as returned by :func:`_read_unit`.
    :returns: The decoded single character.
    """
    if unit.startswith("\\") and len(unit) > 1:
        return _canonical_read_escape(unit, 0)[0]
    return unit


def _abnf_parse_quantifier(text: str) -> IrQuantifier:
    """ABNF quantifier parser. Forms ``*``, ``*N``, ``N*``, ``N*M``, ``N``.

    :param text: The raw quantifier token.
    :returns: The corresponding :class:`IrQuantifier`.
    """
    if text == "*":
        return IrQuantifier(0, IrNone)
    if text.startswith("*"):
        return IrQuantifier(0, int(text[1:]))
    if "*" in text:
        lo_str, hi_str = text.split("*", 1)
        return IrQuantifier(int(lo_str), int(hi_str) if hi_str else IrNone)
    n = int(text)
    return IrQuantifier(n, n)


def _abnf_parse_charclass(text: str) -> tuple[str, bool]:
    """Parse an ABNF num-val single value or range → (pattern, negated=False).

    :param text: ``%x41`` / ``%d65`` / ``%b1000001`` (single) or its range form.
    :returns: The decoded pattern and ``False`` (ABNF has no negation).
    """
    radix = {"b": 2, "d": 10, "x": 16}[text[1].lower()]
    body = text[2:]
    if "-" in body:
        lo_s, hi_s = body.split("-", 1)
        return f"{chr(int(lo_s, radix))}-{chr(int(hi_s, radix))}", False
    return chr(int(body, radix)), False


def _abnf_normalize_literal(decoded: str) -> IrLiteral | IrAlternation:
    """Case-insensitive expansion: ``abc`` → ``([aA][bB][cC])``; else verbatim.

    :param decoded: The decoded literal body.
    :returns: A raw :class:`IrLiteral`, or an :class:`IrAlternation` of the
        expanded case-insensitive char classes.
    """
    if not any(c.isalpha() for c in decoded):
        return IrLiteral(decoded)
    items: list[IrItem] = []
    for c in decoded:
        if c.isalpha():
            items.append(IrItem(atom=IrCharClass(IrChr(c.lower()), IrChr(c.upper()))))
        else:
            items.append(IrItem(atom=IrLiteral(c)))
    return IrAlternation(IrSequence(*items))


def _build_charclass(children: list) -> IrAtom:
    """Build a structured :class:`IrCharClass` (wrapped in IrNot when negated).

    :param children: Lark children; ``children[0]`` is the num-val token.
    :returns: The char class, negation-wrapped if the pattern was negated.
    """
    pattern, negated = _abnf_parse_charclass(str(children[0]))
    elements: list[IrRange | IrChr] = []
    i = 0
    while i < len(pattern):
        unit, i = _read_unit(pattern, i)
        if i < len(pattern) and pattern[i] == "-" and i + 1 < len(pattern):
            hi_unit, i = _read_unit(pattern, i + 1)
            elements.append(
                IrRange(IrChr(_unit_to_chr(unit)), IrChr(_unit_to_chr(hi_unit)))
            )
        else:
            elements.append(IrChr(_unit_to_chr(unit)))
    atom: IrAtom = IrCharClass(*elements)
    return IrNot(atom) if negated else atom


@dataclass(slots=True)
class _IncrementalRule:
    """Marker for an ABNF ``name =/ body`` arm, merged by :func:`_build_start`."""

    name: str
    body: IrAlternation


def _build_start(children: list) -> IrAst:
    """Assemble the rule list, folding ABNF ``=/`` incremental alternatives.

    :param children: The transformed rule / incremental-rule children.
    :returns: The assembled :class:`IrAst`.
    :raises ValueError: an ``=/`` arm names an undefined rule.
    """
    rules: list[IrRule] = []
    position: dict[str, int] = {}
    for child in children:
        if isinstance(child, _IncrementalRule):
            if child.name not in position:
                raise ValueError(f"ABNF '=/' for undefined rule {child.name!r}")
            base = rules[position[child.name]]
            rules[position[child.name]] = IrRule(
                name=base.name, body=IrAlternation(*base.body, *child.body)
            )
        else:
            position[child.name] = len(rules)
            rules.append(child)
    return IrAst(rules=IrSeq(*rules), start=rules[0].name if rules else "")


def _build_numseq(children: list) -> IrLiteral:
    """Build a case-sensitive :class:`IrLiteral` from an ABNF value-sequence.

    :param children: Lark children; ``children[0]`` is the num-seq token.
    :returns: The dot-concatenated code points as a raw literal.
    """
    token = str(children[0])
    radix = {"b": 2, "d": 10, "x": 16}[token[1].lower()]
    return IrLiteral("".join(chr(int(part, radix)) for part in token[2:].split(".")))


def _build_option(children: list) -> IrItem:
    """Build an optional ``[ ... ]`` element — an item bound to ``(0, 1)``.

    :param children: Lark children; ``children[0]`` is the inner alternation.
    :returns: The ``(0, 1)``-quantified item.
    """
    return IrItem(atom=children[0], quantifier=IrQuantifier(0, 1))


def _build_literal_cs(children: list) -> IrLiteral:
    """``%s"..."`` — case-sensitive string → raw :class:`IrLiteral` (RFC 7405).

    :param children: Lark children; ``children[0]`` is the ``%s"..."`` token.
    :returns: The raw literal (ABNF decode is identity).
    """
    return IrLiteral(str(children[0])[3:-1])


def _build_literal_ci(children: list) -> object:
    """``%i"..."`` — explicit case-insensitive string (RFC 7405).

    :param children: Lark children; ``children[0]`` is the ``%i"..."`` token.
    :returns: The case-insensitively expanded literal.
    """
    return _abnf_normalize_literal(str(children[0])[3:-1])


def _build_prose(children: list) -> object:
    """prose-val ``<...>`` — recognised, but has no machine-readable meaning.

    :param children: Lark children; ``children[0]`` is the prose token.
    :raises ValueError: always; prose-val cannot be compiled.
    """
    raise ValueError(f"ABNF prose-val has no formal semantics: {str(children[0])!r}")


_IR_BUILDERS: dict[str, Callable[[list], object]] = {
    "start": _build_start,
    "ir_rule": lambda c: IrRule(name=str(c[0]), body=c[1]),
    "ir_rule_inc": lambda c: _IncrementalRule(str(c[0]), c[-1]),
    "ir_alternation": lambda c: IrAlternation(*c),
    "ir_sequence": lambda c: IrSequence(*c),
    "ir_literal": lambda c: _abnf_normalize_literal(str(c[0])[1:-1]),
    "ir_literal_cs": _build_literal_cs,
    "ir_literal_ci": _build_literal_ci,
    "ir_charclass": _build_charclass,
    "ir_numseq": _build_numseq,
    "ir_option": _build_option,
    "ir_prose": _build_prose,
    "ir_ruleref": lambda c: IrRuleRef(str(c[0])),
    "ir_group": lambda c: c[0],
}


def _make_lark_reducer(lark_mod: ModuleType) -> Any:
    """Build the recovered Lark → ``IrAst`` transformer instance.

    :param lark_mod: The imported ``lark`` module.
    :returns: A ``lark.Transformer`` whose ``transform`` folds a Lark tree to IR.
    """
    token_type = lark_mod.Token

    class _IrTagTransformer(lark_mod.Transformer):
        """Thin Lark Transformer — dispatches all ir_* tags via _IR_BUILDERS."""

        def __default__(self, data: str, children: list, _meta: object) -> object:
            builder = _IR_BUILDERS.get(data)
            if builder is None:
                raise ValueError(f"unknown meta-grammar tag: {data!r}")
            return builder(children)

        def ir_item(self, items: list) -> IrItem:
            """Build an item, reading the optional prefix quantifier token."""
            tokens = [c for c in items if isinstance(c, token_type)]
            atoms = [c for c in items if not isinstance(c, token_type)]
            if len(tokens) > 1 or len(atoms) != 1:
                raise ValueError(f"ir_item: malformed children: {items!r}")
            quant = _abnf_parse_quantifier(str(tokens[0])) if tokens else IrQuantifier()
            return IrItem(atom=atoms[0], quantifier=quant)

    return _IrTagTransformer()


# ── Variant construction ───────────────────────────────────────────────
def load_lark() -> ModuleType | None:
    """Import ``lark`` if installed, else ``None`` — never a hard dependency.

    :returns: The ``lark`` module, or ``None`` when it is not importable.
    """
    if importlib.util.find_spec("lark") is None:
        return None
    return importlib.import_module("lark")


def make_input(base_text: str, repeat: int) -> str:
    """Return ``repeat`` concatenated copies of ``base_text``.

    :param base_text: A workload's base corpus (a valid rulelist).
    :param repeat: How many copies to concatenate.
    :returns: The concatenated (still valid) ABNF rulelist text.
    """
    return base_text * repeat


def build_variants(lark_mod: ModuleType | None) -> dict[str, Variant]:
    """Map ``"stage:engine"`` names to their timed one-shot callables.

    Grammar construction and table compilation happen here, once, outside every
    timed loop; the loop's warm-up primes any remaining lazy state so the two
    sides stay symmetric.

    :param lark_mod: The ``lark`` module, or ``None`` to omit the Lark side.
    :returns: An ordered name → callable mapping of timed variants.
    """
    variants: dict[str, Variant] = {
        "recognize:engine": lambda t: engine_recognize(NORM_GRAMMAR, t),
        "parse:engine": lambda t: engine_parse(NORM_GRAMMAR, t),
        "parse+reduce:engine": lambda t: engine_parse_reduced(NORM_GRAMMAR, t, REDUCER),
    }
    if lark_mod is not None:
        parser = lark_mod.Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
        reducer = _make_lark_reducer(lark_mod)
        variants["parse:lark"] = parser.parse
        variants["parse+reduce:lark"] = lambda t: reducer.transform(parser.parse(t))
    return variants


def sanity_check(lark_mod: ModuleType) -> bool:
    """Whether the embedded Lark reducer and the engine agree on the x1 IrAst.

    :param lark_mod: The imported ``lark`` module.
    :returns: ``True`` iff ``lark_ir == engine_ir`` for the x1 input.
    """
    parser = lark_mod.Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    reducer = _make_lark_reducer(lark_mod)
    text = make_input(BASE_TEXT, 1)
    lark_ir = reducer.transform(parser.parse(text))
    engine_ir = engine_parse_reduced(NORM_GRAMMAR, text, REDUCER)
    return lark_ir == engine_ir


# ── Timing ─────────────────────────────────────────────────────────────
def interleaved(
    variants: dict[str, Variant], text: str, rounds: int
) -> dict[str, list[float]]:
    """Time every variant ``rounds`` times, one sample each per round (ms).

    :param variants: Name → timed callable mapping.
    :param text: The input to parse.
    :param rounds: How many samples to take per variant.
    :returns: Name → list of per-sample durations in milliseconds.
    """
    samples: dict[str, list[float]] = {name: [] for name in variants}
    for fn in variants.values():  # warm up (compile tables, prime lazy state)
        fn(text)
    for _ in range(rounds):
        for name, fn in variants.items():
            gc.disable()
            start = time.perf_counter_ns()
            fn(text)
            elapsed = time.perf_counter_ns() - start
            gc.enable()
            samples[name].append(elapsed / 1e6)
    return samples


# ── Reporting ──────────────────────────────────────────────────────────
_STAGE_ROWS = (
    ("recognize", False, "  ← engine-only (lark has no recognition mode)"),
    ("parse", True, ""),
    ("parse+reduce", True, "  ← product"),
)


def _cell(samples: list[float]) -> str:
    """Format one ``median±stdev`` millisecond cell.

    :param samples: Per-sample durations in milliseconds.
    :returns: A right-aligned ``med±sd ms`` string.
    """
    return f"{statistics.median(samples):>7.1f}±{statistics.stdev(samples):<4.1f}ms"


def _report_scale(
    samples: dict[str, list[float]], text: str, rounds: int, base_len: int
) -> None:
    """Print the per-stage table for one input scale.

    :param samples: Name → per-sample durations for this scale.
    :param text: The scale's input (for the char count).
    :param rounds: Rounds used (for the header).
    :param base_len: Length of the workload's unrepeated base text (for the
        ``x{n}`` label).
    """
    print(f"input x{len(text) // base_len}  ({len(text)} chars · {rounds} rounds):")
    print(
        f"  {'stage':<14} {'lark med±sd':>16} {'engine med±sd':>18} {'engine/lark':>12}"
    )
    for stage, has_lark, tail in _STAGE_ROWS:
        engine = samples[f"{stage}:engine"]
        if has_lark and f"{stage}:lark" in samples:
            lark_samples = samples[f"{stage}:lark"]
            ratio = statistics.median(engine) / statistics.median(lark_samples)
            lark_cell, ratio_cell = _cell(lark_samples), f"{ratio:>10.2f}x"
        else:
            lark_cell, ratio_cell = f"{'—':>14}", f"{'—':>11}"
        print(f"  {stage:<14} {lark_cell} {_cell(engine)} {ratio_cell}{tail}")
    print()


# ── Diagnosis ──────────────────────────────────────────────────────────
def _stage_deltas(medians: dict[str, float], chars: int, have_lark: bool) -> None:
    """Print the recognition / materialisation / product breakdown (µs/char).

    Splits the engine's text→tree cost into recognition (the Earley chart) and
    tree materialisation (``parse − recognize``) so the reader sees where the
    gap against Lark lives.

    :param medians: ``"x{n}/{stage}:{engine}"`` → median ms.
    :param chars: Char count of the reported scale.
    :param have_lark: Whether Lark numbers are available.
    """
    big = SIZES[-1]
    recog = medians[f"x{big}/recognize:engine"]
    parse = medians[f"x{big}/parse:engine"]
    product = medians[f"x{big}/parse+reduce:engine"]
    per = 1e3 / chars
    print("stage-delta breakdown (engine, µs/char):")
    print(f"  recognition (Earley chart)         {recog * per:6.1f}")
    print(f"  tree materialisation (parse−recog) {max(parse - recog, 0.0) * per:6.1f}")
    print(f"  fused product (parse+reduce)       {product * per:6.1f}")
    if have_lark:
        lark_parse = medians[f"x{big}/parse:lark"]
        print(f"  — lark parse→tree, for reference    {lark_parse * per:6.1f}")
        print(
            f"  recognition alone is {recog / lark_parse:.2f}x lark's whole parse; "
            f"materialisation adds {max(parse - recog, 0.0) / lark_parse:.2f}x more."
        )
    print()


def _profile_parse(text: str, top: int = 10) -> list[tuple[str, float, float]]:
    """cProfile one engine ``parse`` run; print and return the top hotspots.

    :param text: The input to parse (profiled once, outside timed samples).
    :param top: How many functions to report, ranked by self (``tottime``).
    :returns: ``(label, tottime, cumtime)`` for the top functions.
    """
    engine_parse(NORM_GRAMMAR, text)  # warm — compile tables out of the profile
    profiler = cProfile.Profile()
    profiler.enable()
    engine_parse(NORM_GRAMMAR, text)
    profiler.disable()
    profile = pstats.Stats(profiler).get_stats_profile()
    rows: list[tuple[str, float, float]] = []
    for func, fp in profile.func_profiles.items():
        short = fp.file_name.rsplit("/", 1)[-1] or fp.file_name
        rows.append((f"{short}:{fp.line_number}({func})", fp.tottime, fp.cumtime))
    rows.sort(key=lambda r: r[1], reverse=True)
    top_rows = rows[:top]
    print(f"cProfile — engine parse, x1 (top {top} by self-time):")
    print(f"  {'tottime':>9} {'cumtime':>9}  function")
    for label, tottime, cumtime in top_rows:
        print(f"  {tottime * 1e3:>7.2f}ms {cumtime * 1e3:>7.2f}ms  {label}")
    return top_rows


def _interpret_profile(top_rows: list[tuple[str, float, float]]) -> None:
    """Print a one-line reading of which engine layer dominates self-time.

    :param top_rows: The ``_profile_parse`` output rows.
    """
    layers = (
        "kernel",
        "forest",
        "trampoline",
        "chart",
        "reduce",
        "tables",
        "normalize",
    )
    charged: dict[str, float] = {layer: 0.0 for layer in layers}
    for label, tottime, _cumtime in top_rows:
        for layer in layers:
            if layer in label:
                charged[layer] += tottime
    ranked = sorted(charged.items(), key=lambda kv: kv[1], reverse=True)
    named = (
        ", ".join(f"{layer} {t * 1e3:.1f}ms" for layer, t in ranked if t > 0) or "n/a"
    )
    leader = ranked[0][0] if ranked[0][1] > 0 else "the Python-level Earley loop"
    print(f"  self-time by layer (top rows): {named}")
    print(
        f"  interpretation: {leader} dominates — the per-item Python work in the "
        f"Earley/SPPF loop is the cost, not table compilation.\n"
    )


def _diagnose(medians: dict[str, float], have_lark: bool) -> None:
    """Print the full WHY section: stage deltas, profile, and closing verdict.

    Scoped to the self-emit workload — it is the deep dive into engine
    internals (cProfile), not a per-workload comparison.

    :param medians: The self-emit workload's ``"x{n}/{stage}:{engine}"`` →
        median ms.
    :param have_lark: Whether Lark numbers are available.
    """
    chars = len(make_input(BASE_TEXT, SIZES[-1]))
    print(
        f"== DIAGNOSIS — why engine text→tree is ~2× lark (x{SIZES[-1]}, {chars} chars) =="
    )
    _stage_deltas(medians, chars, have_lark)
    top_rows = _profile_parse(make_input(BASE_TEXT, 1))
    _interpret_profile(top_rows)


# ── Verdict ────────────────────────────────────────────────────────────
def _verdict(
    workload_name: str, medians: dict[str, float], have_lark: bool, chars: int
) -> None:
    """Print the headline verdict on the largest scale's ``parse`` stage.

    :param workload_name: The workload this verdict covers (for the banner).
    :param medians: The workload's ``"x{n}/{stage}:{engine}"`` → median ms.
    :param have_lark: Whether the Lark side ran.
    :param chars: Char count of the largest scale (``x{SIZES[-1]}``).
    """
    big = SIZES[-1]
    engine_ms = medians[f"x{big}/parse:engine"]
    product_ms = medians[f"x{big}/parse+reduce:engine"]
    print(
        f"== VERDICT [{workload_name}] (x{big}, {chars} chars) — parse stage, text→tree =="
    )
    if not have_lark:
        print(
            f"  engine parse {engine_ms:.0f}ms · {engine_ms / chars * 1e3:.1f} µs/char"
        )
        print(f"  lark side skipped — {LARK_HINT}")
        print(
            f"  engine product (parse+reduce) {product_ms:.0f}ms · "
            f"{product_ms / chars * 1e3:.1f} µs/char\n"
        )
        return
    lark_ms = medians[f"x{big}/parse:lark"]
    lark_product_ms = medians[f"x{big}/parse+reduce:lark"]
    ratio = engine_ms / lark_ms
    if ratio <= 1:
        print(
            f"  engine {engine_ms:.0f}ms BEATS lark {lark_ms:.0f}ms by {(1 - ratio) * 100:.0f}%"
        )
    else:
        print(
            f"  lark {lark_ms:.0f}ms wins {ratio:.2f}x over engine {engine_ms:.0f}ms — "
            f"cut {(ratio - 1) / ratio * 100:.0f}% of engine time to match it"
        )
    print(
        f"  throughput: engine {engine_ms / chars * 1e3:.1f} µs/char  "
        f"vs lark {lark_ms / chars * 1e3:.1f} µs/char"
    )
    print(
        f"  product text→IrAst: engine {product_ms / chars * 1e3:.1f} µs/char  "
        f"vs lark {lark_product_ms / chars * 1e3:.1f} µs/char\n"
    )


# ── Entry point ────────────────────────────────────────────────────────
def _print_header(have_lark: bool) -> None:
    """Print the banner, fixpoint check, and (when relevant) the Lark sanity check.

    :param have_lark: Whether the Lark side is available.
    """
    side = "engine + pure lark" if have_lark else "engine only (lark not installed)"
    print(f"== pure-lark parse benchmark: {side} ==")
    fixpoint = canonicalize(
        engine_parse_reduced(NORM_GRAMMAR, BASE_TEXT, REDUCER)
    ) == canonicalize(ABNF_FLAVOUR.grammar)
    print(
        f"ABNF self-host, {len(BASE_TEXT)} chars/copy.  engine parse+reduce fixpoint: {fixpoint}"
    )
    if not have_lark:
        print(f"lark not importable — {LARK_HINT}")
    print()


def _save_baseline(all_medians: dict[str, dict[str, float]]) -> None:
    """Write per workload × size × stage × engine median ms and µs/char.

    :param all_medians: Workload name → ``"x{n}/{stage}:{engine}"`` → median ms.
    """
    baseline: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for workload in WORKLOADS:
        medians = all_medians[workload.name]
        by_size: dict[str, dict[str, dict[str, float]]] = {}
        for repeat in SIZES:
            chars = len(workload.base_text) * repeat
            prefix = f"x{repeat}/"
            by_size[f"x{repeat}"] = {
                key[len(prefix) :]: {
                    "median_ms": median_ms,
                    "us_per_char": median_ms / chars * 1e3,
                }
                for key, median_ms in medians.items()
                if key.startswith(prefix)
            }
        baseline[workload.name] = by_size
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True))
    print(f"baseline saved → {BASELINE_PATH.name}")


def main() -> None:
    """Run the benchmark across all workloads and scales, then diagnose."""
    lark_mod = load_lark()
    have_lark = lark_mod is not None
    save = "--save" in sys.argv[1:]
    _print_header(have_lark)
    if lark_mod is not None:
        ok = sanity_check(lark_mod)
        print(
            f"sanity: embedded lark parse+reduce IrAst == engine IrAst (x1): "
            f"{'PASS' if ok else 'FAIL'}\n"
        )

    variants = build_variants(lark_mod)
    all_medians: dict[str, dict[str, float]] = {}
    for workload in WORKLOADS:
        print(f"--- workload: {workload.name} ---\n")
        medians: dict[str, float] = {}
        for repeat in SIZES:
            text = make_input(workload.base_text, repeat)
            rounds = max(7, 40 // repeat)
            samples = interleaved(variants, text, rounds)
            for name, series in samples.items():
                medians[f"x{repeat}/{name}"] = statistics.median(series)
            _report_scale(samples, text, rounds, len(workload.base_text))
        all_medians[workload.name] = medians
        _verdict(workload.name, medians, have_lark, len(workload.base_text) * SIZES[-1])

    _diagnose(all_medians["self-emit"], have_lark)

    if save:
        _save_baseline(all_medians)


if __name__ == "__main__":
    main()
