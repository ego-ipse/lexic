"""The split is grammar-universal: no single formulation is its witness.

Every shape the parallel layer knows how to cut — a terminated repetition
(plain and merged-literal tail), a separated repetition (bare and lead-rule),
a noise-enveloped repetition, a routed optional interior, a bracketed nested
region, a long-lexical-run repetition, a deeply recursive nested structure,
and a mixed-noise (comment/blank) repetition — gets its own small,
purpose-built grammar and document family here. None of them is the
benchmark's own demonstrator grammar; each is authored fresh, with its own
rule names and spellings, so passing this module can never be explained by
one privileged formulation.

Every family is driven through the same four checks: worker-count parity
against the ``cores=1`` model (exact equality, byte-identical round-trip),
non-vacuous multi-worker engagement on a comfortably splittable document,
refusal parity on one malformed document, and a clean, silent decline below
the per-worker floor — proven by intercepting the plan/safety/discovery
entry points a sub-floor call must never reach.
"""

from __future__ import annotations

import functools
import random
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from lexic.compile import CompiledGrammar, Directives, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing import parse_model
from lexic.parsing.parallel import orchestrate, split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.policy import MIN_CHUNK

# ── shared document vocabulary ─────────────────────────────────────────────


def _letters(i: int) -> str:
    """A two-letter deterministic label — unit text that never carries digits."""
    return chr(97 + i % 26) + chr(97 + (i // 26) % 26)


# ── family 1: terminated repetition, plain single-character tail ──────────

_TERMINATED = 'root ::= line+\nline ::= word nl\nword ::= [a-z]+\nnl ::= "\\n"\n'


def _terminated_text(n: int) -> str:
    return "".join(f"t{_letters(i)}\n" for i in range(n))


def _terminated_mutate(text: str) -> str:
    return text.replace("taa\n", "t0a\n", 1)


# ── family 2: terminated repetition, merged-literal tail (@lexical) ───────

_TERMINATED_MERGED = (
    'root ::= entry+\nentry ::= word "}" nl\nword ::= [a-z]+\nnl ::= "\\n"\n'
)
_MERGED_DIRECTIVES = Directives(lexical=frozenset({"entry"}))


def _terminated_merged_text(n: int) -> str:
    return "word}\n" * n


def _terminated_merged_mutate(text: str) -> str:
    return text.replace("word}\n", "wor#}\n", 1)


# ── family 3: separated repetition, bare single-character separator ───────

_SEP_CHAR = 'root ::= item more*\nmore ::= "," item\nitem ::= [a-z]+\n'


def _sep_char_text(n: int) -> str:
    return ",".join(f"i{_letters(i)}" for i in range(n))


def _sep_char_mutate(text: str) -> str:
    return text.replace("iaa", "i#a", 1)


# ── family 4: separated repetition, lead-rule separator (comma + noise) ───

_SEP_LEAD = (
    "root ::= slot chain*\n"
    "chain ::= mark slot\n"
    'mark ::= "|" pad\n'
    'slot ::= [a-z]+ "=" [0-9]+\n'
    'pad ::= " "*\n'
)


def _sep_lead_text(n: int) -> str:
    return "| ".join(f"k{_letters(i)}={i % 1000}" for i in range(n))


def _sep_lead_mutate(text: str) -> str:
    return text.replace("kaa=0", "k0a=0", 1)


# ── family 5: noise-enveloped repetition (head/tail + noise-run lead) ─────

_ENVELOPE = (
    "doc ::= lead? piece entry* gap* nl? trail?\n"
    'piece ::= [A-Z]+ ":" [0-9]+\n'
    "entry ::= gap* nl note* piece\n"
    'gap ::= " "\n'
    'nl ::= "\\n"\n'
    'note ::= "#" [^\\n]* "\\n"\n'
    'lead ::= "BEGIN\\n"\n'
    'trail ::= "END\\n"\n'
)


def _envelope_piece(i: int) -> str:
    return "K" + "EY"[i % 2] + ":" + str(i)


def _envelope_text(n: int) -> str:
    parts = ["BEGIN\n", _envelope_piece(0)]
    for i in range(1, n):
        prefix = "  " if i % 5 == 0 else ""
        note = f"# note {i}\n" if i % 7 == 0 else ""
        parts.append(prefix + "\n" + note + _envelope_piece(i))
    parts.append("\nEND\n")
    return "".join(parts)


def _envelope_mutate(text: str) -> str:
    return text.replace("KE:500", "KE?500", 1)


# ── family 6: routed optional interior (an inline or a block form) ────────

_ROUTED = (
    "entry ::= head body? nl?\n"
    'head ::= "!" word\n'
    "body ::= inline | block\n"
    'inline ::= " " word " >"\n'
    'block ::= nl line* ">"\n'
    "line ::= word nl\n"
    "word ::= [a-z]+\n"
    'nl ::= "\\n"\n'
)


def _routed_text(n: int) -> str:
    cycle = "abcdefghij"
    body = "".join(f"{cycle[i % 10]}wordy\n" for i in range(n))
    return "!abc\n" + body + ">"


def _routed_mutate(text: str) -> str:
    return text.replace("awordy\n", "awor?y\n", 1)


# ── family 7: bracketed nested regions, spelled with unrelated punctuation ─

_BRACKET = (
    "root ::= block\n"
    'block ::= "<" cell (";" cell)* ">"\n'
    "cell ::= leaf | block\n"
    "leaf ::= [a-z0-9]+\n"
)


def _bracket_text(n: int) -> str:
    left = ";".join(f"leftitem{i:04d}" for i in range(n))
    right = ";".join(f"rightitem{i:04d}" for i in range(n))
    return f"<<{left}>;<{right}>>"


def _bracket_mutate(text: str) -> str:
    return text.replace("leftitem0010", "leftitem00?0", 1)


# ── family 8: ambiguous-prefix, backtrack-shaped statement repetition ─────

_BACKTRACK = (
    "root ::= stmt+\n"
    "stmt ::= block | bind\n"
    'block ::= prefix ident open close " {" atom "}" eol\n'
    'bind ::= prefix ident open close " = " atom ";" eol\n'
    'prefix ::= "def "\n'
    "ident ::= [a-z] [a-z0-9]*\n"
    "atom ::= [a-z0-9]+\n"
    'open ::= "("\n'
    'close ::= ")"\n'
    'eol ::= "\\n"\n'
)


def _backtrack_text(n: int) -> str:
    return "".join(
        f"def f{i}() {{v{i}}}\n" if i % 2 == 0 else f"def f{i}() = v{i};\n"
        for i in range(n)
    )


def _backtrack_mutate(text: str) -> str:
    return text.replace("def f10()", "def f10)(", 1)


# ── family 9: mixed-noise repetition (comments and blanks) ────────────────

_NOISE = (
    "program ::= stmt+\n"
    "stmt ::= pad body pad nl\n"
    "pad ::= gap*\n"
    'gap ::= " " | "\\t" | comment\n'
    'comment ::= "#" [^\\n]*\n'
    'body ::= "V" [0-9]+\n'
    'nl ::= "\\n"\n'
)


def _noise_text(n: int) -> str:
    lines = []
    for i in range(n):
        prefix = "  " if i % 3 == 0 else ""
        comment = f"# c{i}" if i % 11 == 0 else ""
        lines.append(f"{prefix}V{i}{comment}\n")
    return "".join(lines)


def _noise_mutate(text: str) -> str:
    return text.replace("V10\n", "V1?0\n", 1)


# ── family 10: lexical-run repetition (long terminals per unit) ───────────

_RUN = 'stream ::= chunk+\nchunk ::= [A-Za-z0-9+/=]+ "\\n"\n'
_RUN_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="


def _run_text(n: int) -> str:
    rng = random.Random(7)
    return "".join("".join(rng.choices(_RUN_ALPHABET, k=300)) + "\n" for _ in range(n))


def _run_mutate(text: str) -> str:
    return text.replace("\n", "!\n", 1)


# ── family 11: recursive/deep nested structure ─────────────────────────────

_DEEP = (
    "root ::= forest\n"
    'forest ::= "[" tree (";" tree)* "]"\n'
    "tree ::= leaf | nest\n"
    'nest ::= "(" tree ")"\n'
    "leaf ::= [a-z0-9]+\n"
)


def _deep_tree(depth: int, leaf: str) -> str:
    return "(" * depth + leaf + ")" * depth


def _deep_text(n: int) -> str:
    trees = [_deep_tree(40, f"v{i}") for i in range(n)]
    return "[" + ";".join(trees) + "]"


def _deep_mutate(text: str) -> str:
    return text.replace("(v0)", "(v0", 1)


# ── the family table ───────────────────────────────────────────────────────


class Family(NamedTuple):
    """One grammar shape: its source, document builder, and refusal probe.

    :ivar sizes: Byte counts for ``"sub"`` (below the split floor), ``"mid"``
        (just above it) and ``"large"`` (comfortably several-way splittable),
        keyed by the item COUNT the builder takes — not the resulting length.
    """

    name: str
    source: str
    build: Callable[[int], str]
    mutate: Callable[[str], str]
    sizes: dict[str, int]
    directives: Directives = Directives()


FAMILIES: tuple[Family, ...] = (
    Family(
        "terminated",
        _TERMINATED,
        _terminated_text,
        _terminated_mutate,
        {"sub": 150, "mid": 1500, "large": 4000},
    ),
    Family(
        "terminated_merged",
        _TERMINATED_MERGED,
        _terminated_merged_text,
        _terminated_merged_mutate,
        {"sub": 300, "mid": 2000, "large": 5000},
        directives=_MERGED_DIRECTIVES,
    ),
    Family(
        "sep_char",
        _SEP_CHAR,
        _sep_char_text,
        _sep_char_mutate,
        {"sub": 300, "mid": 2000, "large": 5000},
    ),
    Family(
        "sep_lead",
        _SEP_LEAD,
        _sep_lead_text,
        _sep_lead_mutate,
        {"sub": 150, "mid": 1000, "large": 3000},
    ),
    Family(
        "envelope",
        _ENVELOPE,
        _envelope_text,
        _envelope_mutate,
        {"sub": 150, "mid": 1500, "large": 4000},
    ),
    Family(
        "routed",
        _ROUTED,
        _routed_text,
        _routed_mutate,
        {"sub": 150, "mid": 1500, "large": 4000},
    ),
    Family(
        "bracket",
        _BRACKET,
        _bracket_text,
        _bracket_mutate,
        {"sub": 30, "mid": 500, "large": 1200},
    ),
    Family(
        "backtrack",
        _BACKTRACK,
        _backtrack_text,
        _backtrack_mutate,
        {"sub": 60, "mid": 600, "large": 1500},
    ),
    Family(
        "noise",
        _NOISE,
        _noise_text,
        _noise_mutate,
        {"sub": 150, "mid": 2000, "large": 4000},
    ),
    Family("run", _RUN, _run_text, _run_mutate, {"sub": 5, "mid": 35, "large": 110}),
    Family(
        "deep", _DEEP, _deep_text, _deep_mutate, {"sub": 20, "mid": 150, "large": 350}
    ),
)

_NAMES = tuple(family.name for family in FAMILIES)
_BY_NAME = {family.name: family for family in FAMILIES}
_SIZE_LABELS = ("sub", "mid", "large")
_WORKERS = (1, 2, 4, 8)


@functools.cache
def _compiled(name: str) -> CompiledGrammar:
    family = _BY_NAME[name]
    return compile_text(family.source, directives=family.directives)


@functools.cache
def _document(name: str, size: str) -> str:
    family = _BY_NAME[name]
    return family.build(family.sizes[size])


# ── 1: worker-count parity — exact model, byte-identical text ─────────────


@pytest.mark.parametrize("workers", _WORKERS)
@pytest.mark.parametrize("size", _SIZE_LABELS)
@pytest.mark.parametrize("family", _NAMES)
def test_worker_counts_match_sequential_and_round_trip(
    family: str, size: str, workers: int
) -> None:
    """Every family, size and worker count reproduces the ``cores=1`` model."""
    compiled = _compiled(family)
    text = _document(family, size)
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=workers)

    assert type(parallel) is type(sequential)
    assert parallel == sequential
    assert parallel.to_text() == text


# ── 2: non-vacuity — the large document actually engages several workers ──


@pytest.mark.parametrize("family", _NAMES)
def test_family_engages_multiple_workers_at_large_size(family: str) -> None:
    """The split seam, not the sequential fallback, produced the large-size
    answer — proven by instrumenting the parse entry the same way the
    existing split differentials do."""
    compiled = _compiled(family)
    text = _document(family, "large")
    sequential = parse_model(compiled.codegen_grammar, text, compiled.product)
    calls: list[int] = []

    def recording_parse(grammar, source, fold, resolve=None):
        calls.append(len(source))
        return parse_model(grammar, source, fold, resolve)

    split = split_model(
        recording_parse,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        8,
    )

    assert split is not None, f"{family}: the large document never engaged the split"
    assert split == sequential
    assert split.to_text() == text
    assert len(calls) >= 2, f"{family}: only one worker actually parsed"


# ── 3: refusal parity — a malformed document refuses at every worker count ─


@pytest.mark.parametrize("family", _NAMES)
def test_malformed_document_refuses_at_every_worker_count(family: str) -> None:
    """Splitting never rescues, or re-labels, an input the grammar refuses."""
    fam = _BY_NAME[family]
    compiled = _compiled(family)
    bad = fam.mutate(_document(family, "large"))
    assert bad != _document(family, "large"), f"{family}: the mutation was a no-op"

    for cores in (1, 8):
        with pytest.raises(UnsupportedConstructError):
            compiled.parse(bad, cores=cores)


# ── 4: the floor — a sub-floor document declines before any analysis runs ──


@pytest.mark.parametrize("family", _NAMES)
def test_sub_floor_document_declines_before_any_plan_analysis(
    monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    """Below the per-worker floor, ``split_model`` returns before it ever
    derives a plan, checks ownership safety, or sweeps for a bracketed
    region — the instrumented early-return pattern the unit-level policy
    gate test pins, generalised across every family here."""
    compiled = _compiled(family)
    text = _document(family, "sub")
    assert len(text) < 2 * MIN_CHUNK, f"{family}: 'sub' size is not below the floor"

    def unexpected(*_args, **_kwargs):
        raise AssertionError(f"{family}: parallel analysis ran behind the floor gate")

    monkeypatch.setattr(orchestrate, "_split_plans", unexpected)
    monkeypatch.setattr(orchestrate, "owner_excludes", unexpected)
    monkeypatch.setattr(orchestrate, "terminates_once", unexpected)
    monkeypatch.setattr(orchestrate, "find", unexpected)

    declined = orchestrate.split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        16,
    )
    assert declined is None

    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=16)
    assert parallel == sequential
    assert parallel.to_text() == text


# ── 5: a genuine ambiguity declines cleanly, never silently resolving ─────

_AMBIGUOUS_PREFIX = (
    "root ::= record+\n"
    "record ::= content nl\n"
    "content ::= plain | forced\n"
    "plain ::= [a-z@]+\n"
    'forced ::= "@" [a-z]*\n'
    'nl ::= "\\n"\n'
)
"""One unit reads two ways — whole, or split at its leading mark — placed
exactly at a 2-worker document's natural cut point."""


def test_genuine_prefix_ambiguity_declines_and_matches_sequential_refusal() -> None:
    """The chunk holding the ambiguous unit must fail to parse (the same
    ambiguity, the same grammar) so the split declines it outright — and the
    sequential fallback must then raise the identical refusal, never a
    silently chosen model."""
    compiled = compile_text(_AMBIGUOUS_PREFIX)
    grammar, binding = compiled.codegen_grammar, compiled.product
    lines = ["a" * 20 + "\n"] * 300
    lines[150] = "@ab\n"
    text = "".join(lines)
    assert len(text) >= 2 * MIN_CHUNK

    attempts: list[int] = []

    def counting_parse(gr, piece, model_binding, resolve=None):
        attempts.append(len(piece))
        return parse_model(gr, piece, model_binding, resolve)

    assert split_model(counting_parse, grammar, Request(text, binding), 2) is None
    assert len(attempts) >= 2, "both chunks must have actually been attempted"

    for cores in (1, 2):
        with pytest.raises(UnsupportedConstructError, match="ambiguous"):
            compiled.parse(text, cores=cores)


# ── 6: this module itself must not privilege one formulation ──────────────


def test_module_never_names_or_privileges_a_specific_grammar_format() -> None:
    """Every family here is an ordinary witness; none may be named specially
    — this file's own source is the thing under test. The forbidden word is
    assembled rather than spelled out, so this check cannot flag itself."""
    forbidden = "".join(("j", "s", "o", "n"))
    source = Path(__file__).read_text(encoding="utf-8")
    assert forbidden not in source.lower()
