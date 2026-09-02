"""Vyx D-layer integration tests — compile, recognise, ambiguity, round-trip.

The grammar lives at ``resources/ground_truth/vyx.gbnf`` (ruling 5). These
tests exercise the authored grammar against a self-contained corpus of
synthetic packets and representative real spec lines: every sample must be
recognised, ``is_ambiguous`` clean (ordered choice is encoded by charset
subtraction, so the Earley engine sees no genuine ambiguity), and round-trip
byte-exact through the generated models.

Non-ASCII content is legal (V20-RELAXED, user 2026-07-16): every content
position that admits printable ASCII also admits codepoints above U+007F, so
the spec's arrows/em-dashes/section-signs parse and round-trip. Escaped ``\\|``
inside a pipe element and the trailing-empty ``|`` form are legal (V23).
"""

from __future__ import annotations

import re
from functools import lru_cache

import pytest

from lexic.compile import canonical_grammar, compile_from_path, compile_text
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.parsing import is_ambiguous, recognize
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.lift import lift_optional_nullables
from tests.paths import GROUND_TRUTH

VYX_GBNF = GROUND_TRUTH / "vyx.gbnf"


@lru_cache(maxsize=None)
def grammar_text() -> str:
    """The vyx grammar source, read once."""
    return VYX_GBNF.read_text(encoding="utf-8")


def with_start(start: str) -> str:
    """The vyx grammar source with its start rule swapped to ``start``."""
    return re.sub(r"# @start \S+", f"# @start {start}", grammar_text(), count=1)


@lru_cache(maxsize=None)
def start_grammar(start: str):
    """The normalised vyx grammar (for recognise / is_ambiguous)."""
    ast = canonical_grammar(with_start(start), GBNF_FLAVOUR)
    return normalize(lift_optional_nullables(ast))


@lru_cache(maxsize=None)
def compiled(start: str):
    """The compiled vyx grammar rooted at ``start`` (for parse / round-trip)."""
    return compile_text(with_start(start), cache_key=f"vyx-rt-{start}")


def nested_body_packet(body: str) -> str:
    """A block-body packet wrapping ``body`` with an exact L-budget."""
    return f"!I o:wf L{len(body.encode())}<\n{body}>"


TABLE_BODY = (
    '$P [3]{id nm pr}:\n1 "Widget A" 19.99\n2 "Widget B" 24.50\n3 "Widget C" 12.00\n'
)
SEQ_BODY = (
    '- type=hero title="Welcome to Vyx"\n cta: text="Get Started" url=/docs\n'
    "- type=features cols=3\n"
)

# The three packet forms (D.13): none / inline / block bodies, plus the
# definition-carrying and template variants.
PACKET_SAMPLES = [
    ("bodyless", "!I o:inv ^003\n"),
    (
        "kv+scope block body",
        nested_body_packet("id=ORD-7291\n ship: meth=express carr=DHL\n"),
    ),
    ("table block body", nested_body_packet(TABLE_BODY)),
    ("sequence block body", nested_body_packet(SEQ_BODY)),
    ("nl+kv block body", nested_body_packet("free prose line\nid=ORD-7291\n")),
    ("template def + use", "T:w=o:inv s:@buyer r:@supplier\n!I %w n:7\n"),
    ("inline body (V11)", "!I o:env s:@weather L22< city=Porto temp=22 >\n"),
]

# Representative real spec lines per construct (a self-contained sample of the
# 61-file corpus). Each recognises, is unambiguous, and round-trips under its
# construct start rule.
CONSTRUCT_SAMPLES = [
    ("value", "Porto"),
    ("value", "|a|b|c"),
    ("value", "|a|_|c"),
    ("value", "|a|b|"),  # V23 trailing-empty pipe
    ("value", "_"),
    ("value", "^sk1"),
    ("value", "~sk1"),
    ("value", "-42"),
    ("value", "partly_cloudy"),
    ("value", "rust&lang"),  # V13 labeled-val in value
    ("value", "café"),  # V20-RELAXED non-ASCII unquoted
    ("value", r"|\||dquote|\n|\t"),  # V23 escaped "\|" inside a pipe element
    ("quoted", '"partly cloudy"'),
    ("quoted", '"arrow → section §"'),  # V20-RELAXED non-ASCII quoted
    ("kv-line", "city=Porto temp=22 wind=12"),
    ("kv-line", "avail=1 disc=0 note=_"),
    ("kv-line", "deps=^ref tags=|a|b|c"),
    ("kv-line", "debug-field= mean-unrounded= optional=1"),  # V22 empty values
    ("scope-line", 'ship/addr: st="x" city=Porto'),
    ("scope-line", "depth-limit: 32"),  # V16 loose scalar tail
    ("scope-line", "deps: |LF"),  # V16 pipe in loose tail
    ("scope-line", "unknown: UNKNOWN_TAG_REF severity=soft fallback=literal"),
    ("scope-line", 'unit: packets scope: session consistent-with: "+Np"'),
    ("scope-line", "cascade: revoked-dep→dependents=Suspended"),  # V20-RELAXED
    ("table-header", "$P [3]{id nm pr}:"),
    ("table-header", " $UM [2]{model behavior}:"),  # V18 indent before header
    ("table-row", '1 "Widget A" 19.99'),
    ("table-row", "active _ open"),
    ("schema-def", "S:weather={temp humid wind}"),
    ("dict-def", "D:col{a=1 b=2}"),
    ("dict-def", "D:col{}"),  # V12 empty dict
    ("dict-def", "D:{x=1}"),
    ("template-def", "T:w=o:inv s:@buyer r:@supplier"),
    ("seq-item", '- type=hero title="Welcome"'),
    ("seq-item", "- &s1 type=features cols=3"),
    ("nl-force", "# forced nl with = sign"),
    ("nl-escape", "\\#literal hash line"),
    ("nl-text", "some free prose here"),
    ("nl-text", "see the pipe section for details"),
]

# The enumerated corpus exclusion ledger. These lines match NO D-layer body
# construct nor the assembly-layer table-row, and carry no residual NL match
# either — each is a documented category, never a silent skip. (Self-describing
# meta lines that begin with a bare ^/~/&/$ — e.g. `^ reference "..."`,
# `6 $ "table header ..."` — are NOT here: they parse correctly as nl-text
# residual, which is the right outcome for prose that names D-operators.)
#   V2   : known malformed spec fragment (doubled trailing quote).
#   ESC  : a line led by "\" that is not an nl-escape (spec documenting escapes).
#   V17  : a scope/key named "&" (dropped from the widened charset — it leads
#          the label syntax); a Task-4 spec-honesty fix.
#   V24  : a bare "|" inside an unquoted value (rejected as language; Task-4).
#   V25  : a bare "&" kv value (rejected as language; Task-4).
EXCLUDED_LINES = [
    ("V2", 'child_indent: "seq_indent \\" \\"+""'),
    ("V2", 'ann_indent: "\\" \\"+""'),
    ("ESC", '\\| "literal pipe" 1'),
    ("ESC", '\\" "literal double quote" 1'),
    ("V17", '&: id-len=1-12 chars="[a-zA-Z0-9_-]+"'),
    ("V24", "container: type=list|record mix=error"),
    ("V25", "create-or-join: key=& tag-exists=join tag-new=create"),
]


# A self-contained self.md-shaped document (ruling 7 file-level rule): a fenced
# "```@:tag" data block that toggles to prose and back, prose with backtick
# inline code, a non-ASCII arrow, and the closing comment. Whole-file parse +
# byte-exact round-trip is the self-hosting gate; the D-data lines inside are
# validated as D-constructs by the per-construct tests above.
FILE_DOC = "\n".join(
    [
        "```@:demo",
        'full="Demo Block"',
        "header:",
        "```",
        "All text is natural language. Inline `code` and an arrow → stay verbatim.",
        "```",
        "registries=|ontologies.root|ontologies.stubs",
        "```",
        "<!-- @demo -->",
        "",
    ]
)


def test_vyx_grammar_compiles():
    """The pinned vyx grammar compiles end-to-end into model classes."""
    cg = compile_from_path(VYX_GBNF)
    assert cg.classes
    # The three top-level constructs the D layer is built around.
    for name in ("Packet", "Envelope", "Value"):
        assert name in cg.classes


@pytest.mark.parametrize(
    "label,text", PACKET_SAMPLES, ids=[s[0] for s in PACKET_SAMPLES]
)
def test_packet_forms_recognised_and_unambiguous(label: str, text: str):
    """Every packet form parses and carries no genuine ambiguity."""
    grammar = start_grammar("packet")
    assert recognize(grammar, text), f"{label}: not recognised"
    assert not is_ambiguous(grammar, text), f"{label}: ambiguous"


@pytest.mark.parametrize(
    "label,text", PACKET_SAMPLES, ids=[s[0] for s in PACKET_SAMPLES]
)
def test_packet_forms_round_trip(label: str, text: str):
    """Every packet form round-trips byte-exact through the generated models."""
    assert compiled("packet").parse(text).to_text() == text, f"{label}: round-trip"


@pytest.mark.parametrize(
    "construct,line",
    CONSTRUCT_SAMPLES,
    ids=[f"{c}:{ln[:20]}" for c, ln in CONSTRUCT_SAMPLES],
)
def test_construct_lines_recognised_and_unambiguous(construct: str, line: str):
    """Each representative corpus line recognises under its construct, once."""
    grammar = start_grammar(construct)
    assert recognize(grammar, line), f"{construct}: {line!r} not recognised"
    assert not is_ambiguous(grammar, line), f"{construct}: {line!r} ambiguous"


@pytest.mark.parametrize(
    "construct,line",
    CONSTRUCT_SAMPLES,
    ids=[f"{c}:{ln[:20]}" for c, ln in CONSTRUCT_SAMPLES],
)
def test_construct_lines_round_trip(construct: str, line: str):
    """Each representative corpus line round-trips byte-exact."""
    assert compiled(construct).parse(line).to_text() == line


@pytest.mark.parametrize(
    "category,line",
    EXCLUDED_LINES,
    ids=[f"{c}:{ln[:16]}" for c, ln in EXCLUDED_LINES],
)
def test_excluded_corpus_lines_do_not_match(category: str, line: str):
    """The enumerated exclusion ledger: these lines match no D-construct.

    A documented exclusion (malformed V2 / leading-escape / "&"-name / bare-pipe
    V24 / bare-"&" V25), asserted explicitly rather than skipped. Checked against
    both the body grammar and the assembly-layer table-row.
    """
    for start in ("body-line", "table-row"):
        grammar = start_grammar(start)
        assert not recognize(grammar, line), (
            f"{category}: {line!r} unexpectedly matched {start}"
        )


def test_file_level_document_round_trips():
    """A whole self.md-shaped document parses, is unambiguous, and round-trips."""
    grammar = start_grammar("vyx-file")
    assert recognize(grammar, FILE_DOC)
    assert not is_ambiguous(grammar, FILE_DOC)
    assert compiled("vyx-file").parse(FILE_DOC).to_text() == FILE_DOC
